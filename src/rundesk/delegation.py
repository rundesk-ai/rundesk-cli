"""One agent's ask of another, and the answer it returns.

A named agent, from inside its own turn, hands one bounded task to another named agent on
this install. That agent answers it once **as itself** — its own home, its own `SOUL.md`,
its own memory, its own skills and its own brain — and that single answer is delivered back
into the asking agent's conversation for it to review, exactly as a role's report is
(R-DEL-1, R-DEL-2).

**This is not a role run and borrows none of its machinery.** A role execution is the same
agent working in a mode, with its identity deliberately withheld; the whole point here is
the opposite, so there is no bundle, no locked rules, no skill snapshot and no digests.

**The record stands outside every agent's store, because there is no cross-agent one.**
Each agent has its own database, and `store.py` says so out loud: there is no cross-agent
table because there is no cross-agent database. So the transport is one small JSON file per
ask under `data_home()`, changed under an exclusive lock and renamed into place — the same
primitive `restart_request.py` and `update_request.py` already are. The answering agent's
gateway claims the rows addressed to it; the asking agent's gateway delivers the rows that
came from it. Neither process opens the other's store.

Knows nothing of gateways, channels or turns beyond what it is handed: what carries an ask
and what tells the asking agent are `agent.delegated`'s, and the durable record is all of
this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import re
import time
from datetime import timedelta
from pathlib import Path

from rundesk import data_home
from rundesk import agent as agents
from rundesk import durable, instructions, provider, store, turn
from rundesk import handoff as handoffs

#: Where every delegation on this install stands. One directory rather than one per agent,
#: because an ask belongs to two agents and neither of them owns it.
DIRECTORY = "delegations"

#: How long a brief may be. The same ceiling a role's brief has, and stated here rather than
#: imported from `role_run`: handing work to another named agent is not part of the role
#: feature, and an import would make it conceptually one.
BRIEF_LIMIT = 8192

#: How much of an answer is kept. Generous enough for a real report and bounded, because
#: this file is read whole into memory by two gateways and a command.
ANSWER_KEPT = 20_000

#: How long an ask may produce nothing at all before Rundesk settles it. Measured on
#: inactivity rather than on total runtime, for the reason a role run's window is: a
#: legitimately long job keeps moving, and ending one at six hours of honest work would be
#: worse than the wedged provider this exists for.
UNANSWERED_HOURS = 6

#: How long after its latest activity a settled ask stays readable and resumable. A
#: fortnight, matching what a role run keeps, so an owner reading last week's work back
#: finds it in both places. Measured from activity rather than from settling, for the reason
#: a role run's window is: an ask somebody is still carrying on at day thirteen is work in
#: progress, and a window counted from the first answer would sweep it (R-ROL-11).
RETAINED_DAYS = 14

#: How many unread words may wait for one ask before another is refused. The record is read
#: whole into memory by two gateways and a command, so an unbounded queue is the same
#: unbounded file `ANSWER_KEPT` exists to prevent — and twenty corrections nobody has read
#: is not steering, it is a conversation that needed a second ask.
SAID_WAITING = 20

#: How often a delegation turn looks for something the agent that asked has said to it.
#: The same beat a role execution keeps, and for the same reason: an agent that has just
#: corrected the work is waiting to see it land, and a word arriving after the work it was
#: meant to change arrived too late.
STEER_SECONDS = 3.0

#: How many times carrying one ask may throw before it is settled rather than tried again.
#: Three, because the fault this bounds is the one that happens every time: a brain that has
#: gone, an agent somebody removed, a record nobody can vouch for.
CARRY_CEILING = 3

#: How many times the asking agent may be woken to review one answer before it is written
#: off and the owner told instead. Three, matching what carrying an ask is allowed.
REVIEW_CEILING = 3

#: What one ask is, from the moment it is admitted to the moment nobody is owed anything
#: about it. Closed for the reason `store.SOURCES` is: this is the only word saying where an
#: ask has got to, and one nobody can read back is work whose state is lost.
#:
#: `answered`, `failed`, `stopped` and `undeliverable` are the four ways an ask settles, and
#: every one of them owes the asking agent exactly one review (R-DEL-11). `collected` is
#: what a delivered review leaves behind — and what giving up on an undeliverable one leaves
#: too, told apart by `given_up_at` rather than by inference.
#:
#: **`stopped` is a decision and not a fault** (R-DEL-18). An agent that ended work it had
#: handed over still owes itself the one review, exactly as R-ROL-43 holds for a role run —
#: what came back before it was ended is what there is, and a third word is the only way a
#: listing and a room can say so without calling a decision a failure.
ASKED = "asked"
WORKING = "working"
ANSWERED = "answered"
FAILED = "failed"
STOPPED = "stopped"
UNDELIVERABLE = "undeliverable"
COLLECTED = "collected"
UNFINISHED = (ASKED, WORKING)
SETTLED = (ANSWERED, FAILED, STOPPED, UNDELIVERABLE)

#: What is written down for an ask that was ended before it finished and had said nothing
#: worth keeping. Rundesk reporting on the delegation, as every other fixed wording here is.
STOPPED_EARLY = "this delegation was stopped before it finished"

#: What a carried-on ask is asked when the agent that resumed it said nothing more. Prose
#: rather than an empty prompt, for the reason a role's is: a brain handed nothing answers
#: about nothing, and the session it is carrying on already holds the work.
CARRY_ON = (
    "Carry on from where you stopped. Finish the task you were handed, and report as your "
    "rules require."
)

#: What Rundesk tells a parent when it could not carry an ask at all.
#:
#: **Rundesk reporting on the delegation, never on the work.** Nothing was checked and the
#: answering agent said nothing, so the one thing that must not happen is the asking agent
#: reading this as another agent's report of a failed job — those are different claims and
#: only one of them is being made here.
COULD_NOT_CARRY = (
    "Rundesk could not carry this delegation, and this is Rundesk reporting on the "
    "delegation rather than {to} reporting on the work. Nothing was checked and {to} said "
    "nothing. It was attempted {attempts} times and each attempt ended the same way:\n\n"
    "{why}"
)

#: The same, for an ask that stopped producing anything. Again about the delegation: the
#: work may have been half done or never started, and Rundesk does not know which.
WENT_UNANSWERED = (
    "Rundesk settled this delegation because it stopped producing any activity, and this "
    "is Rundesk reporting on the delegation rather than {to} reporting on the work. "
    "Nothing was checked and {to} never answered. It was last heard from at {seen}, more "
    "than {hours} hours before it was settled."
)

#: What an owner is told when an answer could not be reviewed at all.
#:
#: **Not one word of the answer.** The answering agent's words have still been read by
#: nobody, so putting any of them here would publish unreviewed work by the one route built
#: to prevent it. What this says is which ask, which agent, and that its answer is still
#: waiting — enough to go and ask for it.
ANSWER_UNDELIVERABLE = (
    "An agent answered work handed to it and Rundesk could not get that answer reviewed. "
    "This is Rundesk reporting on the delivery rather than on the work: the answer has not "
    "been read by anybody and none of it is repeated here. Delegation {ask}, handed to "
    "{to}, woken {attempts} times without the review ever answering."
)

#: A record that is there and cannot be trusted. The same rule every durable file here
#: holds: **what cannot be read is not empty**, and writing an empty value back over one is
#: how state is silently lost. Named here so a caller catches one word rather than knowing
#: which primitive this is built on.
Unreadable = durable.Unreadable

_NUMBERED = re.compile(r"^del-(\d+)-[a-z0-9]+$")


class NotDelegable(Exception):
    """This work cannot be handed to another agent, and the reason is the whole message.

    Raised before anything durable is written. A refusal that arrives afterwards has
    already left an owner a record to clean up, and one that arrives after a brain has
    started has already spent their money.
    """


def home() -> Path:
    """Where every delegation on this install stands.

    Below `data_home()`, so a backup already holds an ask that has not been collected and a
    scratch install cannot reach the owner's own (R-DEL-1).
    """
    return data_home() / DIRECTORY


def path(ask_id: str) -> Path:
    """The one file this ask is, proved to name a file rather than a way out of here."""
    return home() / f"{_checked(ask_id)}.json"


def _checked(ask_id: str) -> str:
    """A delegation's id, or why it cannot name a file.

    Asked exactly as a role run's id is, and for the same reason: an id reaches this from a
    durable record and from an environment variable, and one that resolved somewhere else
    would let a swept record take an owner's file with it.
    """
    if not ask_id or not _NUMBERED.match(str(ask_id)):
        raise NotDelegable(f"'{ask_id}' is not a delegation")
    return str(ask_id)


def retained_until(now=None, days: int = RETAINED_DAYS) -> str:
    """When this ask stops being readable and resumable, from its latest activity.

    Written on to the record at every change, so an ask somebody is still carrying on keeps
    moving its own deadline — the same arithmetic a role run's window uses, and for the same
    reason (R-ROL-11).
    """
    at = store.moment(store.stamped(now))
    return store.stamped(lambda: (at + timedelta(days=days)).timestamp())


# ── reading ───────────────────────────────────────────────────────────────────────────────


def read(ask_id: str) -> dict | None:
    """One delegation, or nothing where this install has no such ask."""
    # Told apart rather than collapsed: a file nobody wrote and a file that cannot be read
    # are different answers, and only one of them is "there is no such ask".
    state, said = durable.read(path(ask_id))
    if state == durable.MISSING:
        return None
    if state == durable.UNREADABLE or not isinstance(said, dict):
        raise Unreadable(f"the record of '{ask_id}' could not be read")
    if said.get("id") != ask_id:
        raise Unreadable(f"the record of '{ask_id}' has the wrong identity")
    return said


def every() -> list:
    """Every delegation this install is keeping, oldest ask first.

    Sorted rather than left in whatever order the filesystem answers, because this is what a
    listing shows and what two gateways walk.
    """
    root = home()
    if not root.is_dir():
        return []
    rows = []
    for at in sorted(root.glob("del-*.json")):
        row = read(at.name[: -len(".json")])
        if row is not None:
            rows.append(row)
    return sorted(rows, key=lambda one: (one.get("asked_at") or "", one["id"]))


def waiting(to: str) -> list:
    """Every ask addressed to this agent that is not finished with.

    **Including one already `working`**, and deliberately: a gateway standing down leaves an
    ask unfinished on purpose, and the next gateway to claim that name is what carries it
    on. Whatever is already in flight is held off by the thing carrying it, not by this.

    **Never one somebody has asked to end.** A gateway that started it would spend a brain
    on work that is about to be cancelled, and one that came up after the stop was asked
    would start it for the first time (R-DEL-18).
    """
    return [one for one in every()
            if one.get("to") == to and one.get("state") in UNFINISHED
            and not one.get("stop_asked_at")]


def stopping(to: str) -> list:
    """Every unfinished ask addressed to this agent that somebody has asked to end.

    Asked of every unfinished ask rather than of the ones ready to be carried: an agent that
    asked for work to end wants it ended now, and one waiting out a backoff is exactly the
    one nobody should have to wait for (R-DEL-18).
    """
    return [one for one in every()
            if one.get("to") == to and one.get("state") in UNFINISHED
            and one.get("stop_asked_at")]


def owed(by: str) -> list:
    """Every settled ask this agent handed over and has not yet reviewed (R-DEL-11)."""
    return [one for one in every()
            if one.get("from") == by and one.get("state") in SETTLED]


def shown(row: dict, now=None) -> dict:
    """One delegation as a person is shown it — never a local path, never the brief.

    A listing is read where other people can see it, so what is here is what Rundesk knows
    about the delegation and never a word of what was asked or answered (R-DEL-15).
    """
    began = store.moment(row.get("asked_at"))
    return {
        "id": row["id"],
        "from": row.get("from") or "",
        "to": row.get("to") or "",
        "label": row.get("label") or "",
        "state": row.get("state") or "",
        "posture": row.get("posture") or provider.WORK,
        "parent_run": row.get("parent_run") or "",
        "chain": list(row.get("chain") or []),
        "reviewed": bool(row.get("collected_at")) and not row.get("given_up_at"),
        "settled_at": row.get("settled_at") or "",
        # How long it stays resumable, said out loud rather than left to be worked out from
        # a fortnight and a date: an agent deciding whether to carry work on needs the
        # deadline, and one that computed it would be a second place it could be computed
        # differently (R-DEL-21).
        "retained_until": _retention(row),
        "stopped_by": row.get("stop_asked_by") or "",
        "elapsed": int(max(0, (now or time.time)() - began.timestamp())) if began else 0,
    }


def _retention(row: dict) -> str:
    """When this ask stops being readable, for a record written before it said so.

    An ask admitted by a build that kept no deadline of its own is given the one it would
    have had: a fortnight from the last thing that happened to it. Absent and computed are
    different answers everywhere else here — this is the one place they are not, because a
    record with no deadline at all would never be swept and never refuse a resume.
    """
    said = row.get("retained_until") or ""
    if said:
        return said
    latest = row.get("latest_at") or row.get("asked_at") or ""
    return retained_until(_clock_at(latest)) if latest else ""


def _clock_at(said: str):
    """That written moment, as the clock this module's arithmetic is handed.

    Named for what it is rather than `at`, which is the local this file already uses a
    dozen times over for the moment a change is being made.
    """
    return lambda: store.moment(said).timestamp()


# ── admission ─────────────────────────────────────────────────────────────────────────────


def ask(name: str, to: str, brief: str, parent_run: str, label: str | None = None,
        posture: str | None = None, chain=(), where: Path | None = None, now=None,
        pick=None, runnable=None) -> dict:
    """Hand one bounded task to another named agent, and write the record of it.

    The order is the whole of the safety here: everything refusable is refused first and
    costs nothing, and the durable record is written last — so an ask that was never going
    to work leaves nothing for an owner to clean up, and one that was written is one a
    gateway owes an answer for however soon this process dies.

    `runnable` is asked whether this machine has the brain the answering agent resolved,
    and is passed in rather than reached for, so the decision can be exercised against a
    machine that has a different one.
    """
    chain = [str(one) for one in (chain or [])]
    if not str(brief or "").strip():
        raise NotDelegable("a delegation needs a task, and none was given")
    if len(brief) > BRIEF_LIMIT:
        raise NotDelegable(
            f"the task is longer than {BRIEF_LIMIT} characters — an agent is handed a "
            "bounded task, never a conversation"
        )
    if to == name:
        raise NotDelegable(
            f"'{name}' cannot hand work to itself — that is a turn, not a delegation"
        )
    if to in chain:
        raise NotDelegable(
            f"'{to}' is already in this chain of work, and would be asked to answer itself"
        )
    if chain:
        # **Depth one** (R-DEL-8). An agent reached by delegation is answering somebody
        # else's bounded task with nobody present; letting it hand that on is a tree of
        # work nobody is left owning, and every branch of it owes a review to an agent
        # that has already answered.
        raise NotDelegable(
            "this work was handed over by another agent, so it cannot be handed on — "
            f"{' then '.join(chain)} asked for it"
        )
    if not agents.exists(to, where):
        raise NotDelegable(f"this install has no agent called '{to}'")
    _has_a_brain(to, where, runnable)
    kept = agents.reading(name, where)
    row = kept.run(parent_run)
    if row is None:
        raise NotDelegable(f"'{parent_run}' is not a run of this agent's, so it cannot delegate")
    if row.get("role_run"):
        raise NotDelegable(
            "a role execution cannot hand work to a named agent — the agent that put the "
            "role on does that itself"
        )
    if row.get("ended_at"):
        # A turn that is over is not delegating. The only identity a caller has is the run
        # it says it belongs to, and "still in flight" is the part of that claim these
        # records can actually check.
        raise NotDelegable(
            f"'{parent_run}' has already ended, so it is not a turn that can delegate"
        )
    where_it_is = row.get("conversation_id") or ""
    if not kept.reachable_conversation(where_it_is):
        # **Nowhere to report back to** (R-DEL-4). The answer arrives long after the turn
        # that asked for it has ended, and the review is delivered by waking this agent on
        # a surface it can be reached on. Refused here rather than found out afterwards,
        # which would be an answer owed for ever and work nobody is ever told about.
        raise NotDelegable(
            "this turn is not happening on a surface the agent can be reached on, so "
            "there would be nowhere to report the work back to"
        )
    at = store.stamped(now)
    record = {
        "id": "",
        "from": name,
        "to": to,
        # Everyone this work has passed through, the answering agent last. Written down
        # rather than counted, so a refusal can name them.
        "chain": [*chain, name],
        "label": handoffs.safe_label(label, to),
        "brief": brief,
        "posture": provider.narrowed(row.get("posture"), posture or provider.WORK),
        "parent_run": parent_run,
        "parent_conversation": where_it_is,
        "asked_at": at,
        "latest_at": at,
        "retained_until": retained_until(now),
        "settled_at": "",
        "state": ASKED,
        "carry_attempts": 0,
        "carry_failed_at": "",
        "answer": "",
        "why": "",
        "review_attempts": 0,
        "review_claimed_at": "",
        "collected_at": "",
        # What the asking agent has said to this ask and nothing has read yet. **Here and
        # not in either agent's store**: the process saying it is the asking agent's and the
        # process reading it is the answering agent's, and neither opens the other's
        # database (R-DEL-19).
        "said": [],
        "said_count": 0,
        "stop_asked_at": "",
        "stop_asked_by": "",
        # How many times this ask has been carried *on* — never how many turns it has had.
        # A first carry whose gateway died part-way is still a first carry and is asked the
        # task again; only `resume` moves this, which is what makes `_prompt` unable to hand
        # a brain a correction where it meant to hand it the work (R-DEL-20).
        "resumes": 0,
        # Whether the brain answering this reads anything after the prompt, written down by
        # the turn that actually started rather than resolved twice. Absent until one has
        # (R-PRV-15).
        "can_steer": None,
    }
    with _allocating():
        record["id"] = f"del-{_next_number()}-{store._marked(pick)}"
        durable.write_whole(path(record["id"]), _as_text(record), durable=True)
    return record


def _as_text(record: dict) -> str:
    """One record, as the bytes its file holds. Sorted, so two writes of one record match."""
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


def _has_a_brain(to: str, where: Path | None, runnable=None) -> None:
    """Prove the answering agent has a brain, before anything durable is written.

    **At admission and never mid-carry** (R-DEL-1). An agent with no brain configured, or
    one pinned to a brain this install has not got, is knowable from the records and the
    machine — and an ask admitted on it costs a durable record, three gateway attempts and
    a handoff saying Rundesk could not carry the work, for something answerable up front.

    The refusal names the brain *and* the agent, because neither alone is the fix.
    """
    on = agents.chosen(to, where).get("provider") or ""
    if not on:
        raise NotDelegable(
            f"nothing says which brain answers for '{to}', so it has none to run this "
            f"with — rundesk configure {to} --provider <provider>"
        )
    try:
        (runnable or provider.program)(on)
    except provider.NotRunnable as why:
        raise NotDelegable(
            f"'{to}' has no brain called '{provider.label(on)}' to run this with: {why}"
        ) from None


# ── steering, stopping and carrying on ────────────────────────────────────────────────────


def held(name: str, ask_id: str, now=None) -> dict:
    """The ask a verb is about, refused where it is not this agent's to guide.

    **Whose it is, and whether there is still time**, asked once for all three verbs so
    they cannot come to disagree. The agent named is the agent that *asked* — an ask is
    guided by the one that handed the work over and by nobody else, including the one
    answering it, whose own turn is the thing being guided.
    """
    row = read(ask_id)
    if row is None:
        raise NotDelegable(f"there is no delegation called '{ask_id}'")
    if row.get("from") != name:
        # Named without saying who it *is* handed over by: a listing in one agent's room
        # naming another agent's work is the leak `shown` exists to prevent (R-DEL-15).
        raise NotDelegable(f"'{ask_id}' is not a delegation '{name}' handed over")
    deadline = _retention(row)
    if deadline and store.stamped(now) > deadline:
        raise NotDelegable(
            f"'{ask_id}' is past its retention window and can no longer be carried on"
        )
    return row


def say(name: str, ask_id: str, said: str, where: Path | None = None, now=None) -> str:
    """Say something to an ask being answered now, and answer where it will land.

    One queue, because a word said to another agent's turn is one kind of thing. Where it
    goes is a fact about the ask at the moment it is read: one in flight is steered, and one
    that has settled and is still retained is carried on by `resume`. Said plainly rather
    than guessed at, so an agent that reached for the wrong verb is told which one it wanted
    (R-DEL-22).
    """
    row = held(name, ask_id, now)
    if not str(said or "").strip():
        raise NotDelegable("nothing was said")
    if len(said) > BRIEF_LIMIT:
        raise NotDelegable(
            f"more than {BRIEF_LIMIT} characters — a word said to work in flight is "
            "guidance, and a task that large is a delegation of its own"
        )
    if row.get("state") not in UNFINISHED:
        raise NotDelegable(
            f"'{ask_id}' is not being answered — to carry it on with more work, resume it"
        )
    if row.get("state") == WORKING and row.get("can_steer") is False:
        # **Said rather than queued behind a brain that will never read it.** Not every
        # brain can be sent to mid-turn, and a word accepted for one that cannot is a word
        # that sits unread while the command that took it reported success. Stopping it, or
        # waiting and resuming it, are the two things that do work.
        #
        # Read off what the answering turn recorded it could do, written into this record
        # when that turn started — never by opening the answering agent's own store, which
        # this side of a delegation never does, and never by asking an adapter a second
        # time, which could disagree with the turn already running (R-PRV-15, R-DEL-19).
        raise NotDelegable(
            f"{_which_brain(row, where)} cannot be sent to while it works — stop it, or "
            "wait for it and resume it with what you wanted to say"
        )
    _say(ask_id, said, now)
    if row.get("state") == WORKING:
        return "it reaches the work in flight; nothing is answered back here"
    return "it is added to what this ask is asked when it starts"


def _which_brain(row: dict, where: Path | None) -> str:
    """The brain answering this ask, as a refusal names it.

    Never the raw name (R-DEL-15): a brain may be a path to a program somebody wrote, and
    this sentence is read wherever the agent that asked is reached.
    """
    named = agents.chosen(row.get("to") or "", where).get("provider") or ""
    to = row.get("to") or "the agent it was handed to"
    return f"{provider.label(named)}, the brain answering for '{to}'," if named else (
        f"the brain answering for '{to}'")


def stop(name: str, ask_id: str, now=None, asked_by: str = "") -> bool:
    """Ask this delegation to end, and say whether there was one to end.

    The ask is durable and the acting is the answering agent's gateway's: what has to be
    ended is a turn that gateway owns, and the agent asking for it has not got it in hand.

    **It still answers back** (R-DEL-18). A stopped delegation settles like any other and
    owes the agent that asked exactly one review, because what came back before it was
    ended is what there is — and an ask that simply went quiet is the one outcome this
    whole module exists to make impossible.

    **Who asked arrives rather than being read here**, exactly as it does for a role run
    (R-ROL-43): whether this is an agent ending work it handed over or a person ending it
    from a terminal is a fact about the environment the ask was typed in, and this module
    never reads one.
    """
    row = held(name, ask_id, now)
    if row.get("state") not in UNFINISHED:
        return False
    at = store.stamped(now)
    with _changing(ask_id) as changing:
        if changing.get("state") not in UNFINISHED:
            return False
        changing.update({"latest_at": at, "retained_until": retained_until(now)})
        # **A second ask never rewrites whose decision the first one was**, exactly as
        # `store.ask_role_stop` holds it: the notice that says a stop was a decision names
        # who decided, so the two facts move together (R-ROL-43, R-DEL-18).
        if not changing.get("stop_asked_at"):
            changing["stop_asked_at"] = at
            changing["stop_asked_by"] = str(asked_by or "")
        return True


def resume(name: str, ask_id: str, more: str, now=None) -> str:
    """Carry a settled ask on, in the provider session it already has.

    **The conversation is the same conversation**, which is the whole of how the session is
    kept: the answering turn is opened on the caller and the run that asked, so a resumption
    a week later reaches the brain with everything it already knew rather than starting cold
    (R-DEL-20).

    Reopening re-owes the review. The agent that asked is never told twice about one answer
    — the settled one stops being owed the moment this reopens it — and is always told once
    about the latest, because the carried-on ask settles like any other (R-DEL-11).
    """
    row = held(name, ask_id, now)
    if not str(more or "").strip():
        raise NotDelegable("a resumed delegation needs something more to do, and none was given")
    if len(more) > BRIEF_LIMIT:
        raise NotDelegable(
            f"the continuation is longer than {BRIEF_LIMIT} characters — an agent is "
            "handed a bounded task, never a conversation"
        )
    if row.get("state") in UNFINISHED:
        raise NotDelegable(
            f"'{ask_id}' is still being answered — to guide the work it is doing now, say it"
        )
    at = store.stamped(now)
    with _changing(ask_id) as changing:
        if changing.get("state") in UNFINISHED:
            raise NotDelegable(f"'{ask_id}' is still being answered")
        changing["said"] = [*(changing.get("said") or []), {"at": at, "text": str(more)}]
        changing.update({
            "state": ASKED, "resumes": int(changing.get("resumes") or 0) + 1,
            "latest_at": at, "retained_until": retained_until(now),
            # Everything the settled ask owed and everything it came to. Cleared together,
            # because a record half reopened is one a listing reads as two different asks.
            "settled_at": "", "answer": "", "why": "",
            "review_attempts": 0, "review_claimed_at": "", "collected_at": "",
            "given_up_at": "", "stop_asked_at": "", "stop_asked_by": "",
            # The next turn resolves this for itself; the last one's answer is about a
            # brain that may since have been reconfigured.
            "can_steer": None,
        })
    return ask_id


def _say(ask_id: str, said: str, now=None) -> None:
    """Put one word on this ask's queue, under the hold every change here is made under."""
    with _changing(ask_id) as row:
        waiting = list(row.get("said") or [])
        if len(waiting) >= SAID_WAITING:
            raise NotDelegable(
                f"{len(waiting)} words are already waiting to be read — nothing here is "
                "reading them, and this one would wait behind them"
            )
        waiting.append({"at": store.stamped(now), "text": str(said)})
        row["said"] = waiting
        # Counted as well as queued, and never decremented: the queue empties the moment
        # the turn reads it, so a surface driven off *waiting* would show a steer only if
        # it happened to look in the seconds between (R-DEL-23).
        row["said_count"] = int(row.get("said_count") or 0) + 1
        row["latest_at"] = store.stamped(now)


def claim_said(ask_id: str, now=None) -> list:
    """Take everything waiting for this ask, and leave nothing behind.

    Claimed rather than read, so a word cannot reach one turn twice — and under the same
    hold every other change here is made under, so a word said while this is running is
    read by the next claim rather than lost between the read and the write.
    """
    with _changing(ask_id) as row:
        waiting = list(row.get("said") or [])
        if not waiting:
            return []
        row["said"] = []
        row["latest_at"] = store.stamped(now)
        return [str(one.get("text") or "") for one in waiting]


def words_waiting(ask_id: str) -> int:
    """How many words nothing has read yet — what a listing shows and nothing else."""
    row = read(ask_id)
    return len(list((row or {}).get("said") or []))


async def steering(ask_id: str, every=None, now=None):
    """Everything the asking agent says to this turn while it is still running.

    **Never ends of its own accord**, exactly as a role execution's steering does not: what
    ends it is the turn ending, and `turn.carry` cancels this the moment the brain stops. A
    generator that ended early would close the input of a brain that is still working.

    Claimed from the durable record rather than handed over in memory, because the thing
    saying something is a different agent's process entirely and may be talking to a gateway
    that did not exist when this ask was admitted (R-DEL-19).
    """
    waited = STEER_SECONDS if every is None else every
    while True:
        for said in claim_said(ask_id, now):
            if said.strip():
                yield turn.Said(said, None)
        await asyncio.sleep(waited)


# ── carrying ──────────────────────────────────────────────────────────────────────────────


def preface(name: str, row: dict, where: Path | None = None) -> str:
    """Everything the answering agent is told before it reads a word of the task.

    **The `agent_to_agent` layer, never `agent_to_role`** (R-DEL-2). This agent is itself,
    so it is given the whole of what a named agent is — its home, its memory, its voice —
    and then the layer saying another agent asked, and then its owner's own additions.

    **The roles listing is left out by the composer and not by this**, which is the whole
    point of the layer being named: the layer forbids putting a role on one paragraph later,
    and an agent offered a capability the same preface refuses it spends a turn finding out
    (R-DEL-9). Nothing here has to remember to strip a variable.
    """
    return instructions.build(
        variables={**agents.instruction_variables(name, where),
                   "caller_agent": row["from"]},
        trigger=instructions.DELEGATION,
        append=(agents.added_instructions(name, where),),
    )


def _prompt(row: dict, said: list) -> str:
    """What this turn is asked: the task the first time, and what was said after that.

    **"Has this ask ever been carried on" is the question, and `resumes` is the only thing
    that answers it.** A first carry whose gateway died part-way is still a first carry and
    must be asked the task again rather than a correction somebody steered it with — which
    is why this counts resumptions and never turns (R-DEL-20).

    Anything said before it ever started is folded into what it is being asked, rather than
    left for the steering seam: a brain that cannot be sent to mid-turn would never read it
    there and the words would simply be lost.
    """
    kept = [one for one in said if one.strip()]
    if not int(row.get("resumes") or 0):
        return "\n\n".join([row["brief"], *kept])
    return "\n\n".join(kept) or CARRY_ON


async def carry(name: str, ask_id: str, where: Path | None = None, carrying=None,
                now=None, watching=None, guiding=None) -> turn.Outcome:
    """Answer one ask as a turn of this agent's own, and settle what became of it.

    Far smaller than carrying a role run, because there is nothing to verify: no bundle, no
    locked bytes, no digests. The answering agent runs on **its own** brain, model and
    settings — never the caller's — because the whole of what was asked for is this agent's
    judgement rather than a worker's (R-DEL-2).

    The conversation is keyed by the agent that asked and the run it asked from, so the
    answer is never in a conversation a person is typing into (R-DEL-5), two asks from one
    turn carry on from each other, and **a resumption reaches the brain with the session it
    already had** rather than starting cold (R-DEL-20).
    """
    row = read(ask_id)
    if row is None:
        raise NotDelegable(f"there is no delegation called '{ask_id}'")
    if row.get("to") != name:
        raise NotDelegable(f"'{ask_id}' was not handed to '{name}'")
    taken = claim_work(ask_id, now)
    if taken is None:
        raise NotDelegable(f"'{ask_id}' has already been settled")
    whose = agents.paths(name, where)
    chose = agents.chosen(name, where)
    named = chose.get("provider") or ""
    if not named:
        raise NotDelegable(f"'{name}' has no brain to answer '{ask_id}' with")
    carried_on = bool(int(taken.get("resumes") or 0))
    outcome = await (carrying or turn.carry)(
        name, _prompt(taken, claim_said(ask_id, now)), named,
        where=where,
        model=chose.get("model") or None,
        settings=chose.get("settings"),
        posture=taken["posture"],
        conversation=f'{taken["from"]}/{taken["parent_run"]}',
        on=turn.AGENT,
        kind=turn.AGENT,
        source=turn.AGENT,
        preface=preface(name, taken, where),
        prompt_author="rundesk",
        # **The whole task stands alone; a continuation never does** (R-RUN-24). A stale
        # session that hands a fresh ask straight back read nothing, and the ask survives
        # being put again. A resumption is the opposite: it means nothing without the
        # session it carries on, and asked again on a fresh one the brain answers about
        # nothing while the work itself goes.
        stands_alone=not carried_on,
        context=turn.Execution(cwd=whose["home"], skills=whose["skills"],
                               delegating=ask_id),
        watching=watching,
        # What the agent that asked says to this turn while it runs. The same seam a role
        # execution is steered through, so a word said to another agent travels the path a
        # word typed at a terminal does — into the account first, and then to the brain.
        steering=(guiding if guiding is not None else steering(ask_id, now=now)),
        # Written down the moment there is a turn, because the agent that asked has to know
        # whether this brain reads anything after the prompt *before* it tries to say
        # something — and it may not open this agent's store to find out (R-DEL-19).
        admitted=lambda run, can: _turn_started(ask_id, can, now),
        # An agent asked for this to end, rather than a gateway going down under it. The
        # difference is the whole of what a room can say afterwards about work that stopped
        # (R-DEL-18).
        stopped_by_owner=lambda: bool((read(ask_id) or {}).get("stop_asked_at")),
        now=now,
    )
    # **Only the last complete thing it said is returned** (R-DEL-10). The delegation
    # layer tells the answering agent exactly that, so it has to be true: everything said
    # on the way is working narration, and handing it to the asking agent would bury the
    # report inside it. What the answering agent's *own* conversation keeps is unchanged
    # and is still all of it — this decides what leaves the turn, not what is written down.
    #
    # **A turn that produced nothing is not an answer.** `turn.carry` already decided
    # that — it makes such a turn `ok=False` with `NOTHING_SAID` — so nothing here judges
    # it a second time, and Rundesk reads nothing out of what was said either way
    # (R-DEL-14).
    #
    # **Three endings, and a stop is not a failure** (R-DEL-18). A turn that ended with
    # nothing to show while an agent was asking it to stop is a decision somebody made, and
    # settled by `ok` alone it would read in the room as a fault. An ask that *answered*
    # answered, whatever was being asked of it at the time — the stop lost the race, and
    # calling a real answer a stop would throw the work away in the record.
    #
    # The ordinary way a stop lands is not here at all: the gateway cancels the task, and
    # `agent.delegated` settles it on the way past. This is the narrower case where the
    # brain went down under the ask before the cancel reached it.
    said = outcome.close
    if outcome.ok and said.strip():
        answered(ask_id, said, now)
    elif (read(ask_id) or {}).get("stop_asked_at"):
        stopped(ask_id, said, now)
    else:
        failed(ask_id, outcome.why or turn.NOTHING_SAID, now)
    return outcome


def _turn_started(ask_id: str, can: dict, now=None) -> None:
    """Write down what the brain answering this ask can do, the moment it is known.

    Only what the agent on the other side has to be able to read: whether this brain can be
    sent to mid-turn. Not a copy of the turn's own account, which is the answering agent's
    and stays there — this record is the one thing both sides may open (R-DEL-19).
    """
    with contextlib.suppress(NotDelegable, Unreadable, OSError):
        with _changing(ask_id) as row:
            row["can_steer"] = bool((can or {}).get("steer"))


# ── changing ──────────────────────────────────────────────────────────────────────────────


@contextlib.contextmanager
def _changing(ask_id: str):
    """This ask's record, read, decided on and written back under one hold.

    Every change here goes through this. Two writers that each read the same record and each
    wrote theirs back would leave one change gone with both reporting success — which for a
    delegation is an answer delivered twice, or never.
    """
    with durable.changing(path(ask_id), {}, f"the record of '{ask_id}'") as row:
        if not row:
            raise NotDelegable(f"there is no delegation called '{ask_id}'")
        yield row


@contextlib.contextmanager
def _allocating():
    """The hold taken while a new ask is being numbered.

    The number comes off the directory, so two asks admitted at once would otherwise read
    the same highest one and the second would be written over the first. A lock of its own
    rather than the record's, because the record does not exist yet.
    """
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    guard = os.open(root / ".allocating", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(guard, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(guard, fcntl.LOCK_UN)
        os.close(guard)


def _next_number() -> int:
    """The number this ask takes, off the highest one standing in the directory."""
    root = home()
    highest = 0
    if root.is_dir():
        for at in root.glob("del-*.json"):
            found = _NUMBERED.match(at.name[: -len(".json")])
            if found:
                highest = max(highest, int(found.group(1)))
    return highest + 1


def claim_work(ask_id: str, now=None) -> dict | None:
    """Take one unfinished ask into hand, or answer that there was none to take.

    The whole of what stops one ask being carried twice: whoever wins the lock moves it to
    `working` and everybody after them is told there is nothing to do. An ask already
    settled is never carried again, whatever asked for it.
    """
    with _changing(ask_id) as row:
        if row.get("state") not in UNFINISHED:
            return None
        row["state"] = WORKING
        row["latest_at"] = store.stamped(now)
        row["retained_until"] = retained_until(now)
        return dict(row)


def working(ask_id: str, now=None) -> bool:
    """Say this ask is still being worked on, so the window nothing answered in moves."""
    with _changing(ask_id) as row:
        if row.get("state") not in UNFINISHED:
            return False
        row["latest_at"] = store.stamped(now)
        row["retained_until"] = retained_until(now)
        return True


def answered(ask_id: str, answer: str, now=None) -> bool:
    """Write down what the answering agent said, and owe the asking agent one review.

    Rundesk records the words and asserts nothing read out of them (R-DEL-14). An answer
    claiming the tests passed is an answer claiming the tests passed; whether they did is
    the asking agent's to check, and a gateway that inferred it would be manufacturing the
    one fact the review exists to establish.
    """
    at = store.stamped(now)
    with _changing(ask_id) as row:
        if row.get("state") not in UNFINISHED:
            return False
        row.update({"state": ANSWERED, "answer": str(answer or "")[-ANSWER_KEPT:],
                    "why": "", "latest_at": at, "settled_at": at,
                    "retained_until": retained_until(now)})
        return True


def stopped(ask_id: str, said: str = "", now=None) -> bool:
    """Settle an ask that was ended before it finished, and owe the review anyway.

    **A decision, not a fault** (R-DEL-18). The third ending exists because told apart by
    `ok` alone a stop and a failure are one line in a room saying work did not finish, which
    reads as a fault about something somebody chose. Whatever the answering agent had said
    by then is kept and reviewed: work stopped half done is exactly the case where what came
    back so far is worth reading.

    Reached both ways an ask can be ended — a turn the gateway cancelled outright, and one
    whose brain took the interruption and stopped on its own — so the settlement is the same
    settlement however far it had got.
    """
    at = store.stamped(now)
    with _changing(ask_id) as row:
        if row.get("state") not in UNFINISHED:
            return False
        row.update({"state": STOPPED, "answer": str(said or "")[-ANSWER_KEPT:],
                    "why": "" if str(said or "").strip() else STOPPED_EARLY,
                    "latest_at": at, "settled_at": at,
                    "retained_until": retained_until(now)})
        return True


def failed(ask_id: str, why: str, now=None) -> bool:
    """Settle an ask that produced no answer, and owe the asking agent one review anyway.

    However a delegation ends, the agent that handed the work over is told exactly once
    (R-DEL-11). An ask that quietly stopped being anything is the one outcome that must not
    be possible.
    """
    at = store.stamped(now)
    with _changing(ask_id) as row:
        if row.get("state") not in UNFINISHED:
            return False
        row.update({"state": FAILED, "answer": "", "why": str(why or ""),
                    "latest_at": at, "settled_at": at,
                    "retained_until": retained_until(now)})
        return True


def carry_failed(ask_id: str, why: str, now=None) -> dict:
    """Count one attempt at carrying this ask that threw, and settle it at the ceiling.

    Under the ceiling the ask is left exactly as it was, so the next look picks it up again
    once the backoff has passed and a transient fault heals itself without anybody hearing
    about it. At the ceiling it is settled with what actually went wrong, which owes the
    asking agent the one review it is owed however a delegation ends (R-DEL-11).
    """
    at = store.stamped(now)
    with _changing(ask_id) as row:
        attempts = int(row.get("carry_attempts") or 0) + 1
        row["carry_attempts"] = attempts
        row["carry_failed_at"] = at
        if attempts < CARRY_CEILING or row.get("state") not in UNFINISHED:
            return {"attempts": attempts, "settled": False}
        row.update({
            "state": FAILED, "answer": "", "latest_at": at, "settled_at": at,
            "retained_until": retained_until(now),
            "why": COULD_NOT_CARRY.format(
                to=row.get("to") or "the agent it was handed to", attempts=attempts,
                why=why or "it gave no reason"),
        })
        return {"attempts": attempts, "settled": True}


def claim_review(ask_id: str, now=None) -> int:
    """Count one attempt at getting this answer reviewed, and say how many there have been.

    Claimed rather than counted afterwards, so a gateway that died between waking the asking
    agent and hearing back has still spent an attempt — the ceiling is a ceiling on cost,
    and one that only counted successes would never fire.
    """
    with _changing(ask_id) as row:
        attempts = int(row.get("review_attempts") or 0) + 1
        row["review_attempts"] = attempts
        row["review_claimed_at"] = store.stamped(now)
        return attempts


def collected(ask_id: str, now=None) -> bool:
    """The asking agent reviewed this answer and answered somebody. Nobody is owed it now."""
    with _changing(ask_id) as row:
        if row.get("state") not in SETTLED:
            return False
        row["state"] = COLLECTED
        row["collected_at"] = store.stamped(now)
        return True


def giving_up(ask_id: str, now=None) -> bool:
    """Stop owing this answer a review, after the owner has been told it went unread.

    Told apart from a review that landed by `given_up_at`, and never by inferring it from
    the attempt count: "nobody has read this" is exactly the fact somebody reads a listing
    to find out, and a record that cannot say it plainly cannot be trusted with it.
    """
    at = store.stamped(now)
    with _changing(ask_id) as row:
        if row.get("state") not in SETTLED:
            return False
        row.update({"state": COLLECTED, "collected_at": at, "given_up_at": at})
        return True


def sweep(now=None) -> dict:
    """Settle every ask that went quiet, and take away every record past its retention.

    An ask nobody can hear from is not an ask that is going to be answered. Left alone it
    sits `working` until its retention window closes a fortnight later, and the agent that
    handed the work over is told nothing for the whole of it (R-DEL-13).
    """
    now_at = store.stamped(now)
    at = store.moment(now_at)
    quiet_before = store.stamped(lambda: (at - timedelta(hours=UNANSWERED_HOURS)).timestamp())
    settled, removed = [], []
    for row in every():
        state = row.get("state")
        if state in UNFINISHED:
            seen = row.get("latest_at") or row.get("asked_at") or ""
            if seen and seen <= quiet_before and _went_unanswered(row["id"], seen, now):
                settled.append(row["id"])
            continue
        # Off the deadline the record keeps rather than off its settling, because an ask
        # somebody carried on last week is work in progress and settled a fortnight ago
        # (R-DEL-21).
        if _retention(row) and _retention(row) <= now_at:
            with contextlib.suppress(OSError):
                path(row["id"]).unlink()
            with contextlib.suppress(OSError):
                path(row["id"]).with_suffix(".changing").unlink()
            removed.append(row["id"])
    return {"settled": settled, "removed": removed}


def _went_unanswered(ask_id: str, seen: str, now=None) -> bool:
    """Settle one ask nothing has answered inside the window, in Rundesk's own words."""
    at = store.stamped(now)
    with _changing(ask_id) as row:
        if row.get("state") not in UNFINISHED:
            return False
        row.update({
            "state": UNDELIVERABLE, "answer": "", "latest_at": at, "settled_at": at,
            "retained_until": retained_until(now),
            "why": WENT_UNANSWERED.format(
                to=row.get("to") or "the agent it was handed to", seen=seen,
                hours=UNANSWERED_HOURS),
        })
        return True
