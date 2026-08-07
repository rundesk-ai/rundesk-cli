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

#: What `turns.turn_status` says while a turn is still going. Named here rather than imported,
#: because this package may not reach `providers` — and asserted against it by the suite, so the two
#: cannot drift into meaning different things.
WORKING = "working"


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

    def review_this(self, agent: str, conversation: int, answer: str, from_agent: str) -> None:
        """Put an answer in front of the agent that asked for it, and let it work."""
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
        conversation = _the_conversation(name, delegator, one.parent_turn)
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
    """Whether the newest thing said in this conversation is the other agent's, and so unanswered.

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
                "SELECT author_id FROM conversation_messages"
                " WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conversation,)).fetchone()
    except (records.NotThere, records.Unreadable, OSError):
        return False
    return bool(said) and str(said["author_id"]) == delegator


def _collected_what_came_back(name: str, where, answering: Answering) -> None:
    """Deliver the answer to each of this agent's own delegations whose work has settled.

    Keeps no list of what it has already collected either: `kept.outstanding` answers only what is
    still owed, and `kept.answered` is the `UPDATE` that decides — so the row is the guard, and a
    list beside it would be a second one to keep in step.
    """
    for one in kept.outstanding(name)[:COLLECTED_AT_MOST]:
        said = _what_they_answered(one.to_agent, name, one.parent_turn)
        if said is None:
            continue
        # **Marked before it is delivered, and only by whoever won the row.** Two gateways looking
        # at the same settled work both get here; `answered` is an `UPDATE` matching a row that is
        # still owed, so exactly one of them goes on to wake the agent.
        if not kept.answered(name, one.delegation_id):
            continue
        try:
            answering.review_this(name, one.parent_conversation, said, one.to_agent)
        except Exception as why:  # noqa: BLE001 — see `looked`
            logs.note(where, f"the answer to {one.delegation_id} could not be delivered ({why})",
                      logs.ERROR)


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
            conversation = conn.execute(
                "SELECT id FROM conversations WHERE source = ? AND source_id = ?",
                (kept.FROM_AGENT, kept.source_id_for(delegator, parent_turn))).fetchone()
            if conversation is None:
                return None
            asked = conn.execute(
                "SELECT id FROM conversation_messages"
                " WHERE conversation_id = ? AND author_id = ? ORDER BY id DESC LIMIT 1",
                (conversation["id"], delegator)).fetchone()
            if asked is None:
                return None
            said = conn.execute(
                "SELECT m.body, t.turn_status FROM conversation_messages m"
                " JOIN turns t ON t.id = m.turn_id"
                " WHERE m.conversation_id = ? AND m.author_id = ? AND m.id > ?"
                "   AND t.turn_status <> ?"
                " ORDER BY m.id DESC LIMIT 1",
                (conversation["id"], to_agent, asked["id"], WORKING)).fetchone()
    except (records.NotThere, records.Unreadable, OSError):
        return None
    if said is None:
        return None
    body = (said["body"] or "").strip()
    return body or f"{to_agent} finished without saying anything ({said['turn_status']})"
