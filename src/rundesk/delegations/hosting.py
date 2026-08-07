"""The gateway's third tenant: answering what was handed to this agent, and collecting what it
handed out.

A sibling of `schedules.firing` and `channels.hosting` rather than a generalisation of either — the
same three seams, `settled` on the way up, `looked` every pass, `stopping` on the way out — because
what a gateway hosts is a list and not a hierarchy.

## Two sweeps, and they are not the same job

**Answering** is this agent doing somebody else's work. The brief is already a message in this
agent's own records, delivered when the delegation was admitted, so there is nothing to fetch: what
this sweep does is notice a delegation conversation nobody has answered in and start a turn on it.
That is the same thing a channel does with an inbound message, and it goes through the same seam.

**Collecting** is this agent being owed an answer. It reads the *other* agent's records — read-only,
which SQLite enforces — sees whether the turn doing its work has reached a terminal status, and if
it has, delivers the last thing that agent said into the conversation the work was asked in.

Both are driven by rows in a `delegations` table, and the two directions never touch the same row:
one reads other agents' tables looking for its own name in `to_agent`, the other reads its own.

## Why the answer becomes an ordinary message

Delivering it as a `rundesk` message in the delegator's own conversation is what makes the rest of
this free. *"A message nothing has answered yet"* is already how a person's message wakes an agent,
and `providers.answering` already does the three things that matter about it: start a turn when the
agent is idle, **say it into the turn already running** when it is busy, and ask again on a short
bound when the brain reads nothing mid-turn. Delivering an answer needed none of that written twice.

## What this module may not do

It may not import `providers`, so it cannot run a turn. It is handed an object that can — the same
shape `channels.hosting` takes — which is what keeps every decision here drivable by a case with no
brain, no adapter and no subprocess anywhere near it.

May depend on `agents`, `core` and `utils`.
"""

import json
import sqlite3
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Tuple

from rundesk.agents import directory, records
from rundesk.core import paths
from rundesk.delegations import kept
from rundesk.utils import locking, logs

#: How many delegations one pass will start work for. A gateway that came up to find fifty waiting
#: must not spend its whole first pass on them and answer nobody — the rest are still there next
#: beat, fifteen seconds later, and a pass that never returns is a gateway that never heartbeats.
STARTED_AT_MOST = 4

#: How many answers one pass will collect. The same reasoning, and a separate number because they
#: cost differently: collecting reads another store and delivers a message, and only *then* may a
#: turn begin.
COLLECTED_AT_MOST = 4

#: What `turns.turn_status` says while a turn is still going. Named here rather than imported,
#: because this package may not reach `providers` — and asserted against it by the suite, so the two
#: cannot drift into meaning different things.
WORKING = "working"


class CollectedAnswer(str):
    """Answer text carrying the terminal turn that makes one delivery cycle distinct."""

    def __new__(cls, text: str, turn: int) -> "CollectedAnswer":
        answer = str.__new__(cls, text)
        answer.answer_id = str(turn)
        return answer


class Answering:
    """What this tenant is handed so it can run a turn without knowing what one is.

    A class rather than a `Protocol` for the reason `channels.hosting.Answering` is one: the shape
    is published here and filled by `providers.answering`, and the two directions of work want two
    different methods rather than one with a flag saying which it is.
    """

    def answer_this(self, agent: str, conversation: int, delegation_id: str,
                    delegator: str) -> None:
        """Take a turn on a conversation another agent asked in. Never raises past the caller.

        `delegator` is who asked, and it is passed rather than looked up because the layer that
        names them is four sentences about who asked and where the answer goes — a turn that got
        this wrong would tell a brain `{caller_agent}` five times over.
        """
        raise NotImplementedError

    def review_this(self, agent: str, conversation: int, answer: str, from_agent: str,
                    delegation_id: str, answer_id: str) -> bool:
        """Durably offer an answer for review; `True` only once a turn has admitted it."""
        raise NotImplementedError


class Carrying(NamedTuple):
    """What this tenant carries between passes, which is **nothing**.

    It held two lists of delegation ids this process had already acted on, and that was a bug rather
    than an optimisation: a delegation carried on with more work is the same delegation, so an id
    remembered as *started* was one this gateway would never start again. Resuming wrote the message,
    cleared the answer, and nothing ever picked it up.

    Both questions are answerable from what is already written down — see `_is_waiting_on_us` and
    `kept.outstanding` — so there is no state to keep in step, and a gateway that restarts mid-flight
    reaches the same answer as one that did not.

    Kept as a type so the three seams have the shape the other two tenants have, and so the day this
    needs to carry something there is somewhere for it to go.
    """


def settled(name: str, where) -> Carrying:
    """Reckon with what a gateway that is gone left behind, before anything new starts.

    There is nothing to undo. A delegation whose turn never finished is simply one with no terminal
    turn, which the next pass picks up again — `providers.turns` settles every admitted turn in a
    `finally` that survives the process being taken down, so there is no half-state to repair.

    The seam exists anyway, and is called anyway, because the shape is the other two tenants' and a
    third that quietly had two of the three would be one somebody has to remember is different.
    """
    return Carrying()


def looked(name: str, where, carrying: Carrying, answering: Answering) -> Carrying:
    """One pass: answer what was handed to this agent, then collect what it handed out.

    **Answering first.** A gateway that collected first would spend its pass delivering answers
    while work addressed to it sat untouched, and the agent waiting on that work is another agent
    whose own turn is already over.

    Never raises. A pass that threw would take the gateway's loop with it, and every other thing a
    gateway does — its heartbeat, its channels, its schedules — is more important than one
    delegation. What went wrong is written to this agent's own log and the pass goes on.
    """
    _whatever_happens(where, "answering what was handed here",
                      lambda: _answered_what_was_handed_here(name, where, answering))
    _whatever_happens(where, "collecting what came back",
                      lambda: _collected_what_came_back(name, where, answering))
    return carrying


def _whatever_happens(where, doing: str, sweep: Callable[[], None]) -> None:
    """Run one sweep, or write down why it did not happen and let the pass go on.

    **The whole sweep, not each item.** An agent removed while its gateway runs is the case this
    exists for: every read here is of a store that has just stopped being there, so the failure is
    not one delegation's but the sweep's, and a guard around each item would still let the listing
    that produced them raise.

    A gateway that ended because an agent went away is a gateway somebody has to restart by hand,
    and `test_gateway_host` holds this build to it: taking an agent away must not take down the
    process that was hosting it.
    """
    try:
        sweep()
    except Exception as why:  # noqa: BLE001 — see the docstring, and `looked`
        # **Only where there is still somewhere to write.** `gateways.host._refused` has the same
        # rule for the same reason: an agent taken away while its gateway runs is exactly when this
        # fires, and a directory invented by whatever is complaining that it is missing is one that
        # then looks half-made to everything else. Silence is the right answer here — the gateway's
        # own captured output already carries what happened.
        if Path(where).exists():
            logs.note(where, f"delegations: {doing} did not happen this pass ({why})", logs.ERROR)


def stopping(name: str, where, carrying: Carrying, within: float) -> None:
    """Stand down. **Nothing here stops anything**, and what that costs is worth stating plainly.

    A turn started for a delegation runs on a daemon thread this module never sees and nothing
    joins. A gateway told to stop does not wait for it: the process goes, and the turn goes with it
    part-written. The turn row is then settled by whatever next opens that agent's records rather
    than on the way out — the same is true of a channel-answering turn, which uses the identical
    pattern, so this is the shape the gateway already had rather than one delegation introduced.

    It is **not** what `settled` relies on. That one is safe because a delegation with no terminal
    turn is simply picked up again, which is true however the previous turn ended.

    Here so the three seams are three, and so the day something does need stopping there is a place
    for it the loop already calls.
    """


def _answered_what_was_handed_here(name: str, where, answering: Answering) -> None:
    """Start a turn for each delegation addressed to this agent that is waiting on one."""
    for delegator, one in _addressed_to(name, where)[:STARTED_AT_MOST]:
        conversation = _the_conversation(
            name, delegator, one.parent_turn, one.delegation_id)
        if conversation is None:
            # The row is there and the brief is not, which is the window between the two writes
            # `commands.ask` makes. It lands on the next pass.
            continue
        if not _is_waiting_on_us(name, conversation, delegator):
            continue
        try:
            answering.answer_this(name, conversation, one.delegation_id, delegator)
        except Exception as why:  # noqa: BLE001 — see `looked`
            logs.note(where, f"delegation {one.delegation_id} could not be answered ({why})",
                      logs.ERROR)


def _is_waiting_on_us(name: str, conversation: int, delegator: str) -> bool:
    """Whether the delegator has a message no turn has claimed yet.

    **The whole of "has this been answered yet", and it keeps no state.** A turn already running on
    this conversation is refused its claim by `providers.turns` and settles the question the moment
    it writes its reply, so two passes a beat apart cannot both start one.

    This replaces a list of ids the gateway used to remember having started, which was wrong the
    first time a delegation was carried on: the same id, more work to do, and a gateway that would
    never look at it again. What is being asked is about the conversation, not about the row.
    """
    try:
        with records.reading(directory.records(name)) as conn:
            # **A turn already going is the answer in progress.** Without this the next beat sees a
            # conversation whose newest message is still the other agent's — because the reply is
            # not written until the turn settles — and starts a second turn for the same work. It
            # was measured: one delegation, two turns, the second resuming the first's session and
            # answering again. `providers.turns` refuses the second its claim, but `Busy` is
            # retried on a short bound, and the first turn ending inside that bound lets it through.
            if conn.execute("SELECT 1 FROM turns WHERE conversation_id = ? AND turn_status = ?",
                            (conversation, WORKING)).fetchone():
                return False
            said = conn.execute(
                "SELECT 1 FROM conversation_messages"
                " WHERE conversation_id = ? AND author_id = ? AND turn_id IS NULL LIMIT 1",
                (conversation, delegator)).fetchone()
            if said and _legacy_terminal_answer(
                    conn, conversation, delegator, name) is not None:
                return False
    except (records.NotThere, records.Unreadable, OSError):
        return False
    return bool(said)


def _collected_what_came_back(name: str, where, answering: Answering) -> None:
    """Deliver the answer to each of this agent's own delegations whose work has settled.

    Keeps no list of what it has already collected either: `kept.outstanding` answers only what is
    still owed, and `kept.answered` is the `UPDATE` that decides — so the row is the guard, and a
    list beside it would be a second one to keep in step.
    """
    for one in kept.outstanding(name)[:COLLECTED_AT_MOST]:
        # `asked say` makes the opposite two-store move: it checks this row, then writes the target
        # conversation. One short shared lock makes those two decisions serial without inventing a
        # cross-database transaction. Re-read the row inside it because the listing above is only a
        # candidate by the time the lock is ours.
        with locking.only_one(paths.lock(), f"collection of {one.delegation_id}"):
            current = kept.one(name, one.delegation_id)
            if current.answered_at:
                continue
            said = _what_they_answered(
                current.to_agent, name, current.parent_turn, current.delegation_id)
            if said is None:
                continue
            try:
                admitted = answering.review_this(
                    name, current.parent_conversation, said, current.to_agent,
                    current.delegation_id, said.answer_id)
            except Exception as why:  # noqa: BLE001 — see `looked`
                logs.note(
                    where, f"the answer to {current.delegation_id} could not be delivered ({why})",
                    logs.ERROR)
                continue
            # **Settled only after a receiving turn owns the durable result.** An attended parent in
            # another process can be busy for minutes; marking first would orphan the result because
            # no in-memory turn here can steer it. The next gateway pass retries the same deduplicated
            # message until a live or newly started turn claims it.
            if not admitted:
                continue
            if not kept.answered(name, current.delegation_id):
                continue


def _addressed_to(name: str, where) -> List[Tuple[str, kept.Delegation]]:
    """Every delegation any agent on this install has handed to this one, oldest first.

    **Read out of every other agent's store, read-only.** There is no cross-agent table to ask, and
    this is what stands in for one: a handful of agents, an indexed query per store, once a beat.
    A store that cannot be read is skipped rather than raised on — one broken agent must not stop
    this one answering everybody else.
    """
    found = []
    for delegator in directory.known():
        if delegator == name:
            continue
        try:
            for one in kept.outstanding(delegator, to_agent=name):
                found.append((delegator, one))
        except (records.NotThere, records.Unreadable, OSError):
            continue
    return sorted(found, key=lambda pair: pair[1].created_at)


def _the_conversation(name: str, delegator: str, parent_turn: int,
                      delegation_id: Optional[str] = None) -> Optional[int]:
    """Which conversation of this agent's holds that delegation's work, or `None` before it does.

    Found by the key both sides construct — see `kept.source_id_for` — rather than by an id
    anybody stored.
    """
    try:
        with records.reading(directory.records(name)) as conn:
            row = _preferred_conversation(conn, delegator, parent_turn, delegation_id)
    except (records.NotThere, records.Unreadable, OSError):
        return None
    return int(row["id"]) if row else None


def _what_they_answered(to_agent: str, delegator: str, parent_turn: int,
                        delegation_id: Optional[str] = None) -> Optional[str]:
    """The answering agent's reply to **the newest thing this agent said**, or `None` if it has not
    replied to that yet.

    **Newer than the ask, and that clause is the whole of it.** Without it, a delegation carried on
    with more work is answered instantly with the reply to the *previous* task: the last terminal
    turn is still the old one, so its last message reads as an answer, the row is marked collected,
    and the answering agent's gateway never sees the new work as outstanding at all. Measured — a
    resume that delivered a stale answer and left the further task untouched.

    **Only the last message, and only once its turn is terminal** (R-DEL-10). Everything said on the
    way is working narration, and handing that back would bury the report inside it.

    A turn that failed or was stopped still answers: what it managed to say is what the delegator
    reviews, and an empty one becomes a sentence saying so, because silence delivered as an answer
    reads as an answer.
    """
    try:
        with records.reading(directory.records(to_agent)) as conn:
            legacy = kept.source_id_for(delegator, parent_turn)
            conversation = _preferred_conversation(
                conn, delegator, parent_turn, delegation_id)
            if conversation is None:
                return None
            pending = conn.execute(
                "SELECT 1 FROM conversation_messages"
                " WHERE conversation_id = ? AND author_id = ? AND turn_id IS NULL LIMIT 1",
                (conversation["id"], delegator)).fetchone()
            if pending is not None:
                if str(conversation["source_id"]) != legacy:
                    return None
                previous = _legacy_terminal_answer(
                    conn, int(conversation["id"]), delegator, to_agent)
                if previous is None:
                    return None
                turn, status, body = previous
                return CollectedAnswer(
                    body or f"{to_agent} finished without saying anything ({status})", turn)
            asked = conn.execute(
                "SELECT turn_id FROM conversation_messages"
                " WHERE conversation_id = ? AND author_id = ? AND turn_id IS NOT NULL"
                " ORDER BY id DESC LIMIT 1",
                (conversation["id"], delegator)).fetchone()
            if asked is None:
                return None
            said = conn.execute(
                "SELECT t.turn_status, (SELECT m.body FROM conversation_messages m"
                " WHERE m.conversation_id = ? AND m.author_id = ? AND m.turn_id = t.id"
                " ORDER BY m.id DESC LIMIT 1) AS body"
                " FROM turns t WHERE t.id = ? AND t.turn_status <> ?",
                (conversation["id"], to_agent, asked["turn_id"], WORKING)).fetchone()
    except (records.NotThere, records.Unreadable, OSError):
        return None
    if said is None:
        return None
    body = (said["body"] or "").strip()
    return CollectedAnswer(
        body or f"{to_agent} finished without saying anything ({said['turn_status']})",
        int(asked["turn_id"]))


def _preferred_conversation(conn: sqlite3.Connection, delegator: str, parent_turn: int,
                            delegation_id: Optional[str]) -> Optional[dict]:
    """The delegation-specific conversation, or its pre-boundary legacy conversation."""
    current = kept.source_id_for(delegator, parent_turn, delegation_id)
    legacy = kept.source_id_for(delegator, parent_turn)
    row = conn.execute(
        "SELECT id, source_id FROM conversations WHERE source = ? AND source_id IN (?, ?)"
        " ORDER BY CASE source_id WHEN ? THEN 0 ELSE 1 END LIMIT 1",
        (kept.FROM_AGENT, current, legacy, current)).fetchone()
    return dict(row) if row else None


def _legacy_terminal_answer(conn, conversation: int, delegator: str,
                            to_agent: str) -> Optional[Tuple[int, str, str]]:
    """A pre-boundary terminal turn whose inbound brief was never associated with its turn.

    Old turns recorded the exact prompt in their `sent` event but left the inbound message's
    `turn_id` empty. Recognise only the unambiguous case where that prompt is the whole pending
    input. Further guidance makes the set differ, so an answer from a turn that never saw it cannot
    consume it and the next turn receives both messages.
    """
    turn = conn.execute(
        "SELECT id, turn_status FROM turns WHERE conversation_id = ? AND turn_status <> ?"
        " ORDER BY id DESC LIMIT 1", (conversation, WORKING)).fetchone()
    if turn is None:
        return None
    sent = conn.execute(
        "SELECT event_data FROM turn_records WHERE turn_id = ? AND record_type = 'sent'"
        " ORDER BY id LIMIT 1", (turn["id"],)).fetchone()
    if sent is None:
        return None
    try:
        prompt = str(json.loads(sent["event_data"] or "{}").get("text", ""))
    except (TypeError, ValueError):
        return None
    pending = conn.execute(
        "SELECT body FROM conversation_messages"
        " WHERE conversation_id = ? AND author_id = ? AND turn_id IS NULL ORDER BY id",
        (conversation, delegator)).fetchall()
    if len(pending) != 1 or str(pending[0]["body"] or "") != prompt:
        return None
    answer = conn.execute(
        "SELECT body FROM conversation_messages"
        " WHERE conversation_id = ? AND author_id = ? AND turn_id = ?"
        " ORDER BY id DESC LIMIT 1", (conversation, to_agent, turn["id"])).fetchone()
    return (int(turn["id"]), str(turn["turn_status"]),
            str(answer["body"] or "").strip() if answer else "")
