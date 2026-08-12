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
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from rundesk.agents import directory, records
from rundesk.core import config, paths
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
STOPPED = "stopped"

#: What a room is told about work this agent handed over, and the whole of that vocabulary
#: (R-DEL-16, R-DEL-23). Six words, and they divide into two kinds that the sweep below keeps
#: apart because a surface has to be told them under different rules.
#:
#: **Three are where the work stands** — it went, it is still going, it came back — and each is said
#: once for as long as it remains true. **Three are something that just happened to it**: somebody
#: put words into it, somebody asked it to end, somebody carried a finished one on. Those are
#: moments rather than states, they are said once each time they occur, and the work goes on
#: standing wherever it stood a moment before.
#:
#: **Words and never sentences.** What each one *looks like* is the surface's — see
#: `channels.hosting.delegating` — so a platform with a quiet register puts them in it and one
#: without renders them however it can. A sentence composed here would be this product choosing
#: Discord's small print for every surface that will ever exist.
#:
#: There is no word for a delegation that failed, and that is deliberate rather than missing. How
#: the work *went* is the answer's to say: a turn that failed still answers, with whatever it managed
#: to say, and that answer arrives in the room a moment later. A mark here saying "failed" would be
#: this sweep asserting something about words it has never read.
#:
#: `STOPPING` says what was *asked for*; `STOPPED` says the request reached its durable terminal
#: outcome. It is deliberately not an answer because it owes no review turn.
HANDED_OVER = "handed"
STILL_WORKING = "working-still"
CAME_BACK = "answered"
STANDS = (HANDED_OVER, STILL_WORKING, CAME_BACK, STOPPED)

GUIDED = "guided"
STOPPING = "stopping"
CARRIED_ON = "carried-on"
HAPPENED = (GUIDED, STOPPING, CARRIED_ON)

SHOWN = STANDS + HAPPENED

#: How long work stays out before the room is told it is still out, and how often after that.
#:
#: **Counted from the phase the work is in now, not from the last thing said**, so the number a
#: person reads is how long they have been waiting rather than how long since a notice. Twenty
#: minutes: long enough that ordinary work finishes without ever posting one — a delegation that
#: takes ninety seconds says only that it went and that it came back — and short enough that
#: something wedged for an hour says so three times rather than never.
STILL_WORKING_EVERY = 20 * 60


class CollectedAnswer(str):
    """Answer text carrying the terminal turn that makes one delivery cycle distinct."""

    def __new__(cls, text: str, turn: int, status: str,
                provider_name: str = "", model_name: Optional[str] = None) -> "CollectedAnswer":
        answer = str.__new__(cls, text)
        answer.answer_id = str(turn)
        answer.turn_status = status
        answer.provider_name = provider_name
        answer.model_name = model_name
        answer.requested_provider_name = None
        answer.requested_model_name = None
        answer.effective_provider_name = None
        answer.effective_model_name = None
        return answer


class Answering:
    """What this tenant is handed so it can run a turn without knowing what one is.

    A class rather than a `Protocol` for the reason `channels.hosting.Answering` is one: the shape
    is published here and filled by `providers.answering`, and the two directions of work want two
    different methods rather than one with a flag saying which it is.
    """

    def answer_this(self, agent: str, conversation: int, delegation_id: str,
                    delegator: str, provider_name: Optional[str] = None,
                    model_name: Optional[str] = None) -> None:
        """Take a turn on a conversation another agent asked in. Never raises past the caller.

        `delegator` is who asked, and it is passed rather than looked up because the layer that
        names them is four sentences about who asked and where the answer goes — a turn that got
        this wrong would tell a brain `{caller_agent}` five times over.
        """
        raise NotImplementedError

    def stop_this(self, agent: str, conversation: int, delegation_id: str,
                  delegator: str, provider_name: Optional[str] = None,
                  model_name: Optional[str] = None) -> bool:
        """Stop this delegation's live turn, or settle its pending brief without starting one."""
        raise NotImplementedError

    def review_this(self, agent: str, conversation: int, answer: str, from_agent: str,
                    delegation_id: str, answer_id: str) -> bool:
        """Durably offer an answer for review; `True` only once a turn has admitted it."""
        raise NotImplementedError

    def showed(self, agent: str, conversation: int, state: str, to_agent: str,
               delegation_id: str, seconds: Optional[int] = None) -> bool:
        """Show one of `SHOWN` in the room this conversation stands in. `False` where there is none.

        Handed in rather than reached for, like everything else here: what a room *is* belongs to
        `channels`, which this package may not import, and the layer that may reach both is the
        gateway. `False` for a conversation standing on no platform — a schedule, a terminal, another
        agent's ask — which is an ordinary answer and not a failure.
        """
        raise NotImplementedError


class Carrying(NamedTuple):
    """What this tenant carries between passes: **what it has already said out loud, and nothing
    else.**

    It once held two lists of delegation ids this process had already *acted on*, and that was a bug
    rather than an optimisation: a delegation carried on with more work is the same delegation, so an
    id remembered as *started* was one this gateway would never start again. Resuming wrote the
    message, cleared the answer, and nothing ever picked it up. Both of those questions are
    answerable from what is already written down — see `_is_waiting_on_us` and `kept.outstanding` —
    so neither is here.

    **What is here is a different kind of thing, and the difference is what makes it safe.** Nothing
    is decided from `said`: every delegation is answered, collected and settled exactly as it would
    be if this were empty. It only stops a room being told the same thing twice a beat. So the worst
    a stale or lost entry can do is one repeated line, where a stale entry in the old lists was work
    nobody would ever pick up again.

    That is also why it is not written to disk. A gateway restart seeds this process-local view from
    the retained rows, treating what already exists as a baseline rather than replaying it as new
    activity. Changes after that baseline are still announced on the next sweep.

    `said` maps a delegation's id to where it last stood: one of `STANDS`, or the check-in number
    for `STILL_WORKING`, so the twentieth minute and the fortieth are different answers.

    `marked` maps it to the last thing that *happened* to it: one of `HAPPENED`, stamped with the
    moment it happened at, so a second steer is not the first. **Two dictionaries and not one**,
    because the two questions are asked of the same delegation on the same beat and one answer
    cannot hold both: a delegation that stood at `handed`, was steered, and still stands at `handed`
    would otherwise have "handed" overwritten by "guided" and be announced as newly handed over the
    moment the steer stopped being the latest news.
    """

    said: Dict[str, str]
    marked: Dict[str, str]


def settled(name: str, where) -> Carrying:
    """Reckon with what a gateway that is gone left behind, before anything new starts.

    There is nothing to undo. A delegation whose turn never finished is simply one with no terminal
    turn, which the next pass picks up again — `providers.turns` settles every admitted turn in a
    `finally` that survives the process being taken down, so there is no half-state to repair.

    The seam exists anyway, and is called anyway, because the shape is the other two tenants' and a
    third that quietly had two of the three would be one somebody has to remember is different.

    **Restart is not an event in a delegation's life.** The current standing is used as the new
    process's baseline, so retained `answered` rows and old hand-offs are not replayed into the room
    merely because a gateway restarted. A later state change or check-in still differs from this
    baseline and is shown once.

    **What is said about a delegation does not depend on what this process remembers**, and that is
    worth stating because it did once. Telling a delegation somebody *carried on* from one somebody
    *steered* used to be done by remembering that this process last saw it answered, so a gateway
    restarted between the answer and the resume said "guided" where it should have said "carried
    on". `delegations.kept` now writes `working_since` and only a resume moves it, so the record
    answers that question on its own without manufacturing a restart notification.
    """
    said, marked = {}, {}
    for one in kept.every(name):
        standing, _since = _how_it_stands(one)
        happened = _what_just_happened(one)
        if standing is not None:
            said[one.delegation_id] = standing
        if happened is not None:
            marked[one.delegation_id] = happened
    return Carrying(said=said, marked=marked)


def looked(name: str, where, carrying: Carrying, answering: Answering) -> Carrying:
    """One pass: answer what was handed to this agent, collect what it handed out, then say so.

    **Answering first.** A gateway that collected first would spend its pass delivering answers
    while work addressed to it sat untouched, and the agent waiting on that work is another agent
    whose own turn is already over.

    **Showing last, and that ordering is the whole of why a delegation reads correctly.** Collection
    is what settles a row, so a pass that showed first would say *still working* about work that this
    same pass is about to mark answered — and the room would read a check-in below the answer it was
    checking in on.

    Never raises. A pass that threw would take the gateway's loop with it, and every other thing a
    gateway does — its heartbeat, its channels, its schedules — is more important than one
    delegation. What went wrong is written to this agent's own log and the pass goes on.
    """
    _whatever_happens(where, "answering what was handed here",
                      lambda: _answered_what_was_handed_here(name, where, answering))
    _whatever_happens(where, "collecting what came back",
                      lambda: _collected_what_came_back(name, where, answering))
    _whatever_happens(where, "showing what became of what was handed out",
                      lambda: _showed_what_is_happening(name, carrying, answering))
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
        if one.stop_asked_at is not None:
            # The row belongs to the delegator and is read-only here. Its durable stop request is
            # acted on by the gateway that owns the provider process: a running turn is signalled,
            # and a brief that has not begun is settled stopped without launching a brain. A race
            # that owns the conversation but has not published its stream returns False and stays
            # here for the next beat; it must never fall through and start another turn.
            try:
                answering.stop_this(name, conversation, one.delegation_id, delegator,
                                     one.provider_name, one.model_name)
            except Exception as why:  # noqa: BLE001 — see `looked`
                logs.note(where, f"delegation {one.delegation_id} could not be stopped ({why})",
                          logs.ERROR)
            continue
        if not _is_waiting_on_us(name, conversation, delegator):
            continue
        try:
            answering.answer_this(name, conversation, one.delegation_id, delegator,
                                  one.provider_name, one.model_name)
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
            if current.answered_at or current.stopped_at:
                continue
            said = _what_they_answered(
                current.to_agent, name, current.parent_turn, current.delegation_id)
            if said is None:
                continue
            said.requested_provider_name = current.requested_provider_name
            said.requested_model_name = current.requested_model_name
            said.effective_provider_name = current.provider_name
            said.effective_model_name = current.model_name
            # **A requested stop is terminal, not another answer to review.** Before this branch a
            # stopped turn was converted into "finished without saying anything (stopped)" and
            # offered to `review_this`, which woke the delegating agent for one more provider turn.
            # That made a person who had explicitly ended work watch the agents answer anyway. A
            # stop that lost the race with a normally completed turn still delivers that real
            # answer; only the requested STOPPED outcome settles silently.
            if current.stop_asked_at is not None and said.turn_status == STOPPED:
                kept.stopped(name, current.delegation_id)
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


def _showed_what_is_happening(name: str, carrying: Carrying, answering: Answering) -> None:
    """Say, where the person asked, what has become of the work this agent handed out and what has
    just been done to it (R-DEL-16, R-DEL-23).

    **Every ask this agent handed over, and never the ones handed to it** (R-DEL-16). The other side
    of a delegation is somebody else's room, and an agent that announced work it was merely *doing*
    would be posting another person's task into its own.

    **Driven off the rows and off what this process has already said, on the beat rather than at the
    moment.** The verbs that hand work over, steer it, stop it and carry it on all run in command
    processes with no channel connection and nothing to post through, so the only thing able to say
    any of it happened is whatever is already watching — which is this loop. What makes it an event
    rather than a poll is that the record moved: nothing is said twice for the same movement.

    **At most one line per delegation per beat, and what just happened wins.** A steer that also
    crossed a twenty-minute boundary is one piece of news and not two, and of the two the steer is
    the one somebody scrolling has not already been able to work out. The check-in it displaced is
    recorded as said, so the room hears the next one rather than that one late.
    """
    for one in kept.every(name):
        stood = carrying.said.get(one.delegation_id)
        marked = carrying.marked.get(one.delegation_id)
        standing, since = _how_it_stands(one)
        if standing is None:
            continue
        happened = _what_just_happened(one)
        # Written before it is sent, and not after. A surface that throws costs one skipped line;
        # written after, a platform that refuses every write makes this say the same thing on every
        # beat for as long as the work is out. **Both are written whichever is spoken**, so the one
        # that lost this beat is not announced late on the next.
        carrying.said[one.delegation_id] = standing
        if happened is not None:
            carrying.marked[one.delegation_id] = happened
            if happened != marked:
                # No elapsed. How long the work has been out is news about the work, and this is
                # news about somebody reaching into it — a clause saying "· 41m" beside "updated
                # elena" would read as how long the steering took (R-DEL-23).
                answering.showed(name, one.parent_conversation, _as_shown(happened), one.to_agent,
                                 one.delegation_id)
                continue
        if standing != stood:
            answering.showed(name, one.parent_conversation, _as_shown(standing), one.to_agent,
                             one.delegation_id, since)
    _forgotten(carrying, {one.delegation_id for one in kept.every(name)})


def _how_it_stands(one: kept.Delegation) -> Tuple[Optional[str], Optional[int]]:
    """Where this delegation stands now, and how long it has been out.

    The state is `HANDED_OVER`, `CAME_BACK`, or a check-in numbered by which twenty minutes it is
    in — so the fortieth minute is a different answer from the twentieth and gets its own line, while
    the nineteen beats inside one window are all the same answer and get none.

    **Counted from the phase the work is in now, and steering does not restart it.** `working_since`
    is the moment this stretch of waiting began: when the work went out, or when it was last carried
    on. A person who has been waiting an hour has been waiting an hour, whatever was said into it
    meanwhile — `guided` and `stop_asked` move `latest_at` and never this.

    **Carrying on does begin a new stretch, and that is the defect this closes.** Counted from
    `created_at`, a resumed delegation inherited the whole age of the original: the room said *"still
    working · 1h"* on the beat after the resume, before the agent had done a second of the new work;
    the first check-in was overdue the instant it began, so the twenty-minute silence a person reads
    as *"nothing to report yet"* never happened; and the answer was reported as having taken an hour
    when it took four minutes. Measured on a real Discord channel.

    `None` where a moment could not be read. **Unreadable is not "just handed over"**: a row whose
    timestamps do not parse would otherwise announce itself as new on every single beat.
    """
    since = _seconds_since(one.working_since)
    if one.stopped_at is not None:
        return STOPPED, _seconds_between(one.working_since, one.stopped_at)
    if one.answered_at is not None:
        return CAME_BACK, _seconds_between(one.working_since, one.answered_at)
    if since is None:
        return None, None
    checked = int(since // STILL_WORKING_EVERY)
    return (f"{STILL_WORKING}-{checked}" if checked else HANDED_OVER), since


def _what_just_happened(one: kept.Delegation) -> Optional[str]:
    """The last thing somebody did to this delegation, stamped with when they did it. `None` where
    nobody has done anything to it since it was handed over.

    **Read off `latest_at`, because that is the one column every one of these verbs moves** — and
    the reason `asked say` was given `kept.guided` to move it with. A row whose latest moment is
    still the moment it was created is a row nobody has touched.

    **Which verb moved it is told apart without a column saying so**, and each answer is exact
    except one:

    - a stop is the only one that also writes its own moment, so `stop_asked_at == latest_at` names
      it outright — and words said *after* a stop still show, because the stop's moment is then no
      longer the latest one;
    - **carrying on is the only verb that moves `working_since`**, so a row whose phase began after
      it was created, at the very moment it was last touched, was carried on. Read off the record
      rather than off what this process happens to remember, which is what `stood` was doing before
      `working_since` existed: a gateway restarted between the answer and the resume said "guided"
      where it should have said "carried on", and that trade no longer has to be made;
    - anything else that moved the moment is somebody putting words into work still going.

    **Stamped rather than named**, so two steers are two pieces of news. A word alone would make the
    second one look like the first still standing, and the room would hear nothing. It is also what
    makes the one ambiguity harmless: a steer landing in the same recorded moment as the resume it
    follows carries that moment's stamp either way, so the room hears one line about one moment
    rather than two.
    """
    if one.answered_at is not None or one.stopped_at is not None:
        return None
    if one.latest_at == one.created_at:
        return None
    if one.stop_asked_at == one.latest_at:
        return f"{STOPPING}@{one.latest_at}"
    if one.working_since == one.latest_at and one.working_since != one.created_at:
        return f"{CARRIED_ON}@{one.latest_at}"
    return f"{GUIDED}@{one.latest_at}"


def _as_shown(state: str) -> str:
    """The word that crosses the seam, out of what this process wrote down for itself.

    A check-in is remembered as `working-still-2` so that the second one is not the first; a steer is
    remembered as `guided@<moment>` so that the second one is not the first. What a surface is told
    is `working-still` and `guided`, because *which* one it is is already in the elapsed time beside
    it or in the words that prompted it, and a vocabulary that grew a word an hour — or a word a
    steer — would be no vocabulary at all.
    """
    word = state.split("@", 1)[0]
    return STILL_WORKING if word.startswith(STILL_WORKING) else word


def _forgotten(carrying: Carrying, standing: set) -> None:
    """Drop what this process remembers about delegations that are no longer there.

    A gateway runs for weeks and a settled delegation is eventually swept away; without this, both
    dictionaries only ever grow, keyed by something that stops existing.
    """
    for remembered in (carrying.said, carrying.marked):
        for gone in [one for one in remembered if one not in standing]:
            remembered.pop(gone, None)


def _seconds_since(at: str) -> Optional[int]:
    """How long ago that moment was, or `None` if it cannot be read as one."""
    return _seconds_between(at, config.moment_of())


def _seconds_between(this: str, that: str) -> Optional[int]:
    """Whole seconds from one stored moment to another, or `None` if either cannot be read.

    **Never negative.** A clock that went backwards between two writes — an install that changed
    time zone, an NTP correction — would otherwise put "· -3s" in front of somebody, which reads as
    a defect in the product rather than in the machine's clock.
    """
    first, second = config.read_moment(this), config.read_moment(that)
    if first is None or second is None:
        return None
    return max(0, int((second - first).total_seconds()))


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
                        delegation_id: Optional[str] = None) -> Optional[CollectedAnswer]:
    """The answering agent's reply to **the newest thing this agent said**, or `None` if it has not
    replied to that yet.

    **Newer than the ask, and that clause is the whole of it.** Without it, a delegation carried on
    with more work is answered instantly with the reply to the *previous* task: the last terminal
    turn is still the old one, so its last message reads as an answer, the row is marked collected,
    and the answering agent's gateway never sees the new work as outstanding at all. Measured — a
    resume that delivered a stale answer and left the further task untouched.

    **Only the last message, and only once its turn is terminal** (R-DEL-10). Everything said on the
    way is working narration, and handing that back would bury the report inside it.

    A failed turn still answers: what it managed to say is what the delegator reviews, and an empty
    one becomes a sentence saying so, because silence delivered as an answer reads as an answer.
    A stopped turn is returned with its status so collection can settle a requested stop silently.
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
                turn, status, body, provider_name, model_name = previous
                return CollectedAnswer(
                    body or f"{to_agent} finished without saying anything ({status})", turn,
                    status, provider_name, model_name)
            asked = conn.execute(
                "SELECT turn_id FROM conversation_messages"
                " WHERE conversation_id = ? AND author_id = ? AND turn_id IS NOT NULL"
                " ORDER BY id DESC LIMIT 1",
                (conversation["id"], delegator)).fetchone()
            if asked is None:
                return None
            said = conn.execute(
                "SELECT t.turn_status, t.provider_name, t.model_name,"
                " (SELECT m.body FROM conversation_messages m"
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
        int(asked["turn_id"]), str(said["turn_status"]), str(said["provider_name"] or ""),
        said["model_name"])


def terminal_provenance(to_agent: str, delegator: str, parent_turn: int,
                        delegation_id: str) -> Optional[Tuple[str, Optional[str]]]:
    """The actual provider/model on this delegation's newest terminal target turn."""
    answer = _what_they_answered(to_agent, delegator, parent_turn, delegation_id)
    if answer is None:
        return None
    return answer.provider_name, answer.model_name


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
                            to_agent: str) -> Optional[Tuple[int, str, str, str, Optional[str]]]:
    """A pre-boundary terminal turn whose inbound brief was never associated with its turn.

    Old turns recorded the exact prompt in their `sent` event but left the inbound message's
    `turn_id` empty. Recognise only the unambiguous case where that prompt is the whole pending
    input. Further guidance makes the set differ, so an answer from a turn that never saw it cannot
    consume it and the next turn receives both messages.
    """
    turn = conn.execute(
        "SELECT id, turn_status, provider_name, model_name FROM turns"
        " WHERE conversation_id = ? AND turn_status <> ?"
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
            str(answer["body"] or "").strip() if answer else "",
            str(turn["provider_name"] or ""), turn["model_name"])
