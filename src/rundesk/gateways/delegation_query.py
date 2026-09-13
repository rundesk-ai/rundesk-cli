"""A conversation-scoped, read-only account of delegated work.

This is deliberately a gateway question. The answer joins three owners that may not import each
other: ``delegations`` knows what a named agent was handed, ``providers`` knows which turn and
session is current, and ``channels`` knows which conversation a platform place names. The gateway
is already the layer that wires those owners together and is the only place the join can live
without inverting the tree.

No prompt or result crosses this seam. A named task contributes only its flattened first line,
provider-local records contribute only the public ``delegate`` lifecycle word, and result messages
are queried without selecting their bodies. Every database connection below is opened by its owning
module through ``records.reading``; this module has no write path and never starts a provider.

One of those stores belongs to another agent, and it is the only optional read here: see
``_task_brief``. Everything a conversation is entitled to know about its own delegated work stands
in the records of the agent being asked, so a colleague's store nobody can open costs one identity
rather than the whole answer.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from rundesk.agents import records
from rundesk.channels import arriving, delivery
from rundesk.core import config
from rundesk.delegations import kept as delegations
from rundesk.providers import kept as turns

#: A task identity is recognition, not disclosure. One flattened line is enough to tell two pieces
#: of work apart while never reproducing a multi-paragraph brief.
TASK_AT_MOST = 96

#: What a query says when the platform place has no durable conversation, or that conversation has
#: no currently relevant work. Kept plain so an empty private response is immediately legible.
EMPTY = "No relevant delegations are active or recorded here."


class Item(NamedTuple):
    """One provider-neutral item rendered by whichever adapter offered the query."""

    item_id: str
    kind: str
    target: str
    task: str
    state: str
    origin: str
    delivery_target: str
    timing: str


class Result(NamedTuple):
    """The shared result contract: items once, plus the provider visibility boundary."""

    items: Tuple[Item, ...]
    provider_visibility: str


def summary(agent: str, kind: str, place: str,
            now: Optional[datetime] = None) -> str:
    """Read and render the relevant work for one platform conversation."""
    return render(read(agent, kind, place, now=now))


def read(agent: str, kind: str, place: str,
         now: Optional[datetime] = None) -> Result:
    """Build the provider-neutral result without waking a brain or changing delegation state."""
    conversation = arriving.standing_in(agent, place)
    if conversation is None:
        return Result((), "")

    at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    conversation_turns = turns.turns_in_conversation(agent, conversation)
    latest = conversation_turns[-1] if conversation_turns else None
    items: List[Item] = []
    for one in delegations.in_conversation(agent, conversation):
        item = _named_agent(agent, kind, place, one, conversation_turns, latest, at)
        if item is not None:
            items.append(item)

    local, visibility = _provider_local(agent, conversation_turns, at)
    items.extend(local)
    return Result(tuple(items), visibility)


def render(result: Result) -> str:
    """Render one shared answer; an adapter decides only how its private response is delivered."""
    if not result.items:
        return EMPTY if not result.provider_visibility else f"{EMPTY}\n\n{result.provider_visibility}"
    lines = ["Relevant delegations:"]
    for item in result.items:
        lines.extend((
            f"- **{_markdown(item.item_id)}** — {item.kind}",
            f"  - target: {_markdown(item.target)} · task: {_markdown(item.task)}",
            f"  - state: {item.state} · {item.timing}",
            f"  - origin: {item.origin}",
            f"  - delivery: {item.delivery_target}",
        ))
    if result.provider_visibility:
        lines.extend(("", result.provider_visibility))
    return "\n".join(lines)


def _named_agent(agent: str, kind: str, place: str, one: delegations.Delegation,
                 conversation_turns: List[Dict[str, Any]], latest: Optional[Dict[str, Any]],
                 now: datetime) -> Optional[Item]:
    """One durable named-agent item, or ``None`` once reviewed work has gone stale."""
    if one.stopped_at:
        return None
    review_turn = (arriving.delegation_review_turn(
        agent, one.parent_conversation, one.delegation_id) if one.answered_at else None)
    if one.answered_at:
        if review_turn is None:
            state = "returned — awaiting review"
        else:
            review = turns.get_turn(agent, review_turn)
            if review["turn_status"] == turns.WORKING:
                state = "returned — awaiting review"
            elif latest is not None and int(latest["id"]) == review_turn:
                state = "reviewed"
            else:
                return None
    else:
        state = "stopping" if one.stop_asked_at else "active"

    origin_turn = turns.get_turn(agent, one.parent_turn)
    origin_provider = _provider(origin_turn)
    replaced = any(
        int(row["id"]) > one.parent_turn
        and (not bool(row["session_resumed"])
             or _provider_identity(row) != _provider_identity(origin_turn))
        for row in conversation_turns
    )
    origin = (f"conversation {one.parent_conversation}, turn {one.parent_turn}, "
              f"{origin_provider} session")
    if replaced:
        origin += " (session reset/replaced)"

    if latest is None:
        target = f"{kind}:{place}, next turn"
    else:
        target = (f"{kind}:{place}, turn {latest['id']}, {_provider(latest)} session"
                  + (" (replacement target)" if replaced else " (current target)"))

    task = _task_identity(_task_brief(agent, one))
    timing = _timing(agent, one, state, now, review_turn)
    return Item(one.delegation_id, "named-agent", one.to_agent, task, state,
                origin, target, timing)


def _provider_local(agent: str, conversation_turns: List[Dict[str, Any]],
                    now: datetime) -> Tuple[List[Item], str]:
    """Observable helper lifecycle from the current provider session, never an inventory claim."""
    if not conversation_turns:
        return [], ""
    latest = conversation_turns[-1]
    provider = _provider_identity(latest)
    start = 0
    for at in range(len(conversation_turns) - 1, -1, -1):
        row = conversation_turns[at]
        if _provider_identity(row) == provider and not bool(row["session_resumed"]):
            start = at
            break
    current = [row for row in conversation_turns[start:]
               if _provider_identity(row) == provider]
    return _local_records(agent, current, now), _visibility(provider[0])


def _local_records(agent: str, current: List[Dict[str, Any]], now: datetime) -> List[Item]:
    """Provider-local items paired by the provider's private id but exposed by durable row id."""
    events: List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []
    results: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for turn in current:
        for row in turns.list_turn_records(agent, int(turn["id"])):
            try:
                data = json.loads(row["event_data"] or "{}")
            except (TypeError, ValueError):
                continue
            key = (int(turn["id"]), str(data.get("id") or ""))
            if row["record_type"] == "result" and key[1]:
                results[key] = row
            elif (row["record_type"] == "tool" and data.get("did") == "delegate"
                  and key[1]):
                events.append((turn, row, data))
    items = []
    seen = set()
    for turn, row, data in events:
        key = (int(turn["id"]), str(data["id"]))
        if key in seen:
            continue
        seen.add(key)
        finished = results.get(key)
        state = "returned" if finished is not None else "active"
        timing_at = str(finished["created_at"] if finished is not None else row["created_at"])
        timing = (_ago(timing_at, now) + (" ago" if finished is not None else " elapsed"))
        items.append(Item(
            f"local-{turn['id']}-{row['id']}", "provider-local", "provider helper",
            "task identity unavailable", state,
            f"conversation {turn['conversation_id']}, turn {turn['id']}, current provider session",
            f"provider turn {turn['id']} (provider-local; no Rundesk delivery route)", timing,
        ))
    return items


def _visibility(provider: str) -> str:
    return (f"Provider-local visibility is partial for {_markdown(_provider_name(provider))}: "
            "only helper lifecycle events reported by the current provider session are shown.")


def _task_brief(agent: str, one: delegations.Delegation) -> str:
    """The target's own first task message, or ``""`` where its records cannot be read.

    **The only read in this query that leaves the asking agent's own store, and the only optional
    one.** A task identity is recognition: the asking agent's records already prove the work exists,
    what state it is in and where its answer goes, and none of that needs the target's copy of the
    brief. Leaving the target's store able to end the query turned two colleagues' unopenable
    ``state.db`` into one generic failure for a whole conversation, while `rundesk asked` went on
    listing the same work as active out of the very records the query had in its hands.

    Not there, there and half-written, and there and impossible to open are all answered as an
    identity that is unavailable — never guessed at from the delegation row, which holds no brief,
    and never recorded, because the distinction belongs to the store that owns those records and
    this query keeps no state to hold it in. Every other read here is the asking agent's own, and a
    failure of one of those is still a failure of the query.
    """
    try:
        return arriving.delegation_brief(
            one.to_agent, agent, one.parent_turn, one.delegation_id)
    except (records.NotThere, records.Unreadable, sqlite3.DatabaseError, OSError):
        return ""


def _task_identity(body: str) -> str:
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    flattened = " ".join(first.split())
    if not flattened:
        return "task identity unavailable"
    return flattened[:TASK_AT_MOST] + ("…" if len(flattened) > TASK_AT_MOST else "")


def _timing(agent: str, one: delegations.Delegation, state: str, now: datetime,
            review_turn: Optional[int]) -> str:
    if state in ("active", "stopping"):
        return f"{_ago(one.working_since, now)} elapsed"
    if state == "returned — awaiting review":
        return f"returned {_ago(one.answered_at or one.latest_at, now)} ago"
    if review_turn is not None:
        review = turns.get_turn(agent, review_turn)
        return f"review completed {review.get('ended_at') or 'at an unknown time'}"
    return "review completed"


def _ago(moment: str, now: datetime) -> str:
    at = config.read_moment(moment)
    if at is None:
        return "unknown time"
    return delivery.duration(max(0.0, (now - at).total_seconds()))


def _provider(row: Dict[str, Any]) -> str:
    provider, alias = _provider_identity(row)
    shown = _provider_name(provider)
    if alias:
        shown += f" ({alias})"
    return _markdown(shown)


def _provider_identity(row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    return (str(row.get("provider_name") or "unknown provider"),
            str(row["provider_alias"]) if row.get("provider_alias") else None)


def _provider_name(provider: str) -> str:
    return provider.replace("\\", "/").rsplit("/", 1)[-1]


def _markdown(value: Any) -> str:
    flattened = " ".join(str(value or "").split())
    return "".join(f"\\{one}" if one in "\\`*_~|" else one for one in flattened)
