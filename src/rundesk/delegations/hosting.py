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

from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Tuple

from rundesk.agents import directory, records
from rundesk.delegations import kept
from rundesk.utils import logs

#: How many delegations one pass will start work for. A gateway that came up to find fifty waiting
#: must not spend its whole first pass on them and answer nobody — the rest are still there next
#: beat, fifteen seconds later, and a pass that never returns is a gateway that never heartbeats.
STARTED_AT_MOST = 4

#: How many answers one pass will collect. The same reasoning, and a separate number because they
#: cost differently: collecting reads another store and delivers a message, and only *then* may a
#: turn begin.
COLLECTED_AT_MOST = 4


class Answering:
    """What this tenant is handed so it can run a turn without knowing what one is.

    A class rather than a `Protocol` for the reason `channels.hosting.Answering` is one: the shape
    is published here and filled by `providers.answering`, and the two directions of work want two
    different methods rather than one with a flag saying which it is.
    """

    def answer_this(self, agent: str, conversation: int, delegation_id: str) -> None:
        """Take a turn on a conversation another agent asked in. Never raises past the caller."""
        raise NotImplementedError

    def review_this(self, agent: str, conversation: int, answer: str, from_agent: str) -> None:
        """Put an answer in front of the agent that asked for it, and let it work."""
        raise NotImplementedError


class Carrying(NamedTuple):
    """What this tenant is in the middle of, carried from one pass to the next.

    `started` and `collected` are delegation ids this process has already acted on. Held in memory
    rather than written down, and that is safe in exactly one direction: forgetting them on restart
    costs a second look, which finds the work already done and does nothing. Writing them would be a
    second record of what the turn itself already says.
    """

    started: Tuple[str, ...] = ()
    collected: Tuple[str, ...] = ()


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
    return Carrying(
        started=_whatever_happens(where, "answering what was handed here", carrying.started,
                                  lambda: _answered_what_was_handed_here(
                                      name, where, carrying.started, answering)),
        collected=_whatever_happens(where, "collecting what came back", carrying.collected,
                                    lambda: _collected_what_came_back(
                                        name, where, carrying.collected, answering)))


def _whatever_happens(where, doing: str, keeping: Tuple[str, ...],
                      sweep: Callable[[], Tuple[str, ...]]) -> Tuple[str, ...]:
    """Run one sweep and answer what it carried, or keep what there was and write down why not.

    **The whole sweep, not each item.** An agent removed while its gateway runs is the case this
    exists for: every read here is of a store that has just stopped being there, so the failure is
    not one delegation's but the sweep's, and a guard around each item would still let the listing
    that produced them raise.

    A gateway that ended because an agent went away is a gateway somebody has to restart by hand,
    and `test_gateway_host` holds this build to it: taking an agent away must not take down the
    process that was hosting it.
    """
    try:
        return sweep()
    except Exception as why:  # noqa: BLE001 — see the docstring, and `looked`
        # **Only where there is still somewhere to write.** `gateways.host._refused` has the same
        # rule for the same reason: an agent taken away while its gateway runs is exactly when this
        # fires, and a directory invented by whatever is complaining that it is missing is one that
        # then looks half-made to everything else. Silence is the right answer here — the gateway's
        # own captured output already carries what happened.
        if Path(where).exists():
            logs.note(where, f"delegations: {doing} did not happen this pass ({why})", logs.ERROR)
        return keeping


def stopping(name: str, where, carrying: Carrying, within: float) -> None:
    """Stand down. **Nothing to stop and nothing to wait for**, which is why this is empty.

    A turn started for a delegation is an ordinary turn, claimed and settled by `providers.turns`,
    and the gateway's own shutdown already waits on those. What this tenant holds between passes is
    two lists of ids in memory, and losing them costs one repeated look.

    Here so the three seams are three, and so the day this grows something to stop there is a place
    for it that the loop already calls.
    """


def _answered_what_was_handed_here(name: str, where, started: Tuple[str, ...],
                                   answering: Answering) -> Tuple[str, ...]:
    """Start a turn for each delegation addressed to this agent that nothing has answered."""
    doing = list(started)
    for delegator, one in _addressed_to(name, where)[:STARTED_AT_MOST]:
        if one.delegation_id in doing:
            continue
        conversation = _the_conversation(name, delegator, one.parent_turn)
        if conversation is None:
            # The row is there and the brief is not, which is the window between the two writes
            # `commands.ask` makes. It lands on the next pass.
            continue
        doing.append(one.delegation_id)
        try:
            answering.answer_this(name, conversation, one.delegation_id)
        except Exception as why:  # noqa: BLE001 — see `looked`
            logs.note(where, f"delegation {one.delegation_id} could not be answered ({why})",
                      logs.ERROR)
    return tuple(doing)


def _collected_what_came_back(name: str, where, collected: Tuple[str, ...],
                              answering: Answering) -> Tuple[str, ...]:
    """Deliver the answer to each of this agent's own delegations whose work has settled."""
    doing = list(collected)
    for one in kept.outstanding(name)[:COLLECTED_AT_MOST]:
        if one.delegation_id in doing:
            continue
        said = _what_they_answered(one.to_agent, name, one.parent_turn)
        if said is None:
            continue
        # **Marked before it is delivered, and only by whoever won the row.** Two gateways looking
        # at the same settled work both get here; `answered` is an `UPDATE` matching a row that is
        # still owed, so exactly one of them goes on to wake the agent.
        if not kept.answered(name, one.delegation_id):
            continue
        doing.append(one.delegation_id)
        try:
            answering.review_this(name, one.parent_conversation, said, one.to_agent)
        except Exception as why:  # noqa: BLE001 — see `looked`
            logs.note(where, f"the answer to {one.delegation_id} could not be delivered ({why})",
                      logs.ERROR)
    return tuple(doing)


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


def _the_conversation(name: str, delegator: str, parent_turn: int) -> Optional[int]:
    """Which conversation of this agent's holds that delegation's work, or `None` before it does.

    Found by the key both sides construct — see `kept.source_id_for` — rather than by an id
    anybody stored.
    """
    try:
        with records.reading(directory.records(name)) as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE source = ? AND source_id = ?",
                (kept.FROM_AGENT, kept.source_id_for(delegator, parent_turn))).fetchone()
    except (records.NotThere, records.Unreadable, OSError):
        return None
    return int(row["id"]) if row else None


def _what_they_answered(to_agent: str, delegator: str, parent_turn: int) -> Optional[str]:
    """The last complete thing the answering agent said, once its turn has settled — else `None`.

    **Only the last message, and only once the turn is terminal** (R-DEL-10). Everything said on the
    way is working narration, and handing that back would bury the report inside it.

    A turn that failed or was stopped still answers: what it managed to say is what the delegator
    reviews, and an empty one becomes a sentence saying the work did not report anything, because
    silence delivered as an answer reads as an answer.
    """
    try:
        with records.reading(directory.records(to_agent)) as conn:
            turn = conn.execute(
                "SELECT t.id, t.turn_status FROM turns t"
                " JOIN conversations c ON c.id = t.conversation_id"
                " WHERE c.source = ? AND c.source_id = ?"
                " ORDER BY t.id DESC LIMIT 1",
                (kept.FROM_AGENT, kept.source_id_for(delegator, parent_turn))).fetchone()
            if turn is None or turn["turn_status"] == "working":
                return None
            said = conn.execute(
                "SELECT body FROM conversation_messages"
                " WHERE turn_id = ? AND author = 'agent' ORDER BY id DESC LIMIT 1",
                (turn["id"],)).fetchone()
    except (records.NotThere, records.Unreadable, OSError):
        return None
    body = (said["body"] if said else "") or ""
    return body.strip() or f"{to_agent} finished without saying anything ({turn['turn_status']})"
