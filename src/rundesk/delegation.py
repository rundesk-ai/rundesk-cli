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

#: How long a settled ask stays readable before it is taken away. A fortnight, matching what
#: a role run keeps, so an owner reading last week's work back finds it in both places.
RETAINED_DAYS = 14

#: How many times carrying one ask may throw before it is settled rather than tried again.
#: Three, because the fault this bounds is the one that happens every time: a brain that has
#: gone, an agent somebody removed, a record nobody can vouch for.
CARRY_CEILING = 3

#: How long after a throw the same ask is left alone. Doubled per attempt, so three attempts
#: are spread over minutes rather than over the fifteen seconds a five-second look would
#: otherwise take — a ceiling on attempts is only a ceiling on cost if something puts time
#: between them.
CARRY_BACKOFF_SECONDS = 60.0

#: How often an ask that is still being answered says so where the work was asked for.
#: Twenty minutes, matching what a role run says: long enough that an hour's job is three
#: lines rather than forty, short enough that somebody who came back to the room can tell
#: work that is going from work that is gone. Counted from the ask, which is what `shown`
#: already reports as `elapsed`, so the line and the listing cannot disagree.
CHECK_IN_SECONDS = 1200.0

#: How many times the asking agent may be woken to review one answer before it is written
#: off and the owner told instead. Three, matching what carrying an ask is allowed.
REVIEW_CEILING = 3

#: What one ask is, from the moment it is admitted to the moment nobody is owed anything
#: about it. Closed for the reason `store.SOURCES` is: this is the only word saying where an
#: ask has got to, and one nobody can read back is work whose state is lost.
#:
#: `answered`, `failed` and `undeliverable` are the three ways an ask settles, and every one
#: of them owes the asking agent exactly one review (R-DEL-11). `collected` is what a
#: delivered review leaves behind — and what giving up on an undeliverable one leaves too,
#: told apart by `given_up_at` rather than by inference.
ASKED = "asked"
WORKING = "working"
ANSWERED = "answered"
FAILED = "failed"
UNDELIVERABLE = "undeliverable"
COLLECTED = "collected"
UNFINISHED = (ASKED, WORKING)
SETTLED = (ANSWERED, FAILED, UNDELIVERABLE)

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


def safe_label(said: str | None, fallback: str) -> str:
    """A short task label safe to show where other people are reading (R-DEL-15).

    Never a local path and never a person's words verbatim: this is written into a listing
    and into a line in the room the work was asked for in, and a label carrying a private
    directory has published one.
    """
    text = " ".join(str(said or "").split())
    kept = "".join(ch for ch in text if ch.isalnum() or ch in " -_.,'()")
    kept = " ".join(kept.split())[:60].strip()
    return kept or fallback


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
    """
    return [one for one in every()
            if one.get("to") == to and one.get("state") in UNFINISHED]


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
        "elapsed": int(max(0, (now or time.time)() - began.timestamp())) if began else 0,
    }


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
        "label": safe_label(label, to),
        "brief": brief,
        "posture": provider.narrowed(row.get("posture"), posture or provider.WORK),
        "parent_run": parent_run,
        "parent_conversation": where_it_is,
        "asked_at": at,
        "latest_at": at,
        "settled_at": "",
        "state": ASKED,
        "carry_attempts": 0,
        "carry_failed_at": "",
        "answer": "",
        "why": "",
        "review_attempts": 0,
        "review_claimed_at": "",
        "collected_at": "",
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


# ── carrying ──────────────────────────────────────────────────────────────────────────────


def preface(name: str, row: dict, where: Path | None = None) -> str:
    """Everything the answering agent is told before it reads a word of the task.

    **`build`, never `for_role`** (R-DEL-2). This agent is itself, so it receives
    `RUNDESK_INSTRUCTIONS` in full — its home, its memory, how to read its own history back
    — and then the delegation layer, and then its owner's own additions.

    **Without `roles`**, and that is not an omission: `build` emits the roles layer only
    where there is something to list, and the delegation layer forbids putting a role on
    one paragraph later. An agent offered a capability the same preface refuses it spends a
    turn finding out (R-DEL-9).
    """
    variables = {
        what: value
        for what, value in agents.instruction_variables(name, where).items()
        if what != "roles"
    }
    return instructions.build(
        variables={**variables, "caller_agent": row["from"]},
        trigger=instructions.DELEGATION,
        append=(agents.added_instructions(name, where),),
    )


async def carry(name: str, ask_id: str, where: Path | None = None, carrying=None,
                now=None, watching=None) -> turn.Outcome:
    """Answer one ask as a turn of this agent's own, and settle what became of it.

    Far smaller than carrying a role run, because there is nothing to verify: no bundle, no
    locked bytes, no digests. The answering agent runs on **its own** brain, model and
    settings — never the caller's — because the whole of what was asked for is this agent's
    judgement rather than a worker's (R-DEL-2).

    The conversation is keyed by the agent that asked and the run it asked from, so the
    answer is never in a conversation a person is typing into (R-DEL-5), and two asks from
    one turn carry on from each other.
    """
    row = read(ask_id)
    if row is None:
        raise NotDelegable(f"there is no delegation called '{ask_id}'")
    if row.get("to") != name:
        raise NotDelegable(f"'{ask_id}' was not handed to '{name}'")
    held = claim_work(ask_id, now)
    if held is None:
        raise NotDelegable(f"'{ask_id}' has already been settled")
    whose = agents.paths(name, where)
    chose = agents.chosen(name, where)
    named = chose.get("provider") or ""
    if not named:
        raise NotDelegable(f"'{name}' has no brain to answer '{ask_id}' with")
    outcome = await (carrying or turn.carry)(
        name, held["brief"], named,
        where=where,
        model=chose.get("model") or None,
        settings=chose.get("settings"),
        posture=held["posture"],
        conversation=f'{held["from"]}/{held["parent_run"]}',
        on=turn.AGENT,
        kind=turn.AGENT,
        source=turn.AGENT,
        preface=preface(name, held, where),
        prompt_author="rundesk",
        # The task carries everything it needs, so a stale session that handed the turn
        # straight back is worth asking again on a fresh one (R-RUN-24). A whole ask is
        # exactly the kind of prompt that survives being asked twice.
        stands_alone=True,
        context=turn.Execution(cwd=whose["home"], skills=whose["skills"],
                               delegating=ask_id),
        watching=watching,
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
    said = outcome.close
    if outcome.ok and said.strip():
        answered(ask_id, said, now)
    else:
        failed(ask_id, outcome.why or turn.NOTHING_SAID, now)
    return outcome


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
        return dict(row)


def working(ask_id: str, now=None) -> bool:
    """Say this ask is still being worked on, so the window nothing answered in moves."""
    with _changing(ask_id) as row:
        if row.get("state") not in UNFINISHED:
            return False
        row["latest_at"] = store.stamped(now)
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
                    "why": "", "latest_at": at, "settled_at": at})
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
                    "latest_at": at, "settled_at": at})
        return True


def check_in_due(elapsed: float, told: int = 0) -> int:
    """Which check-in this ask has reached, or 0 when it owes none.

    A bucket number rather than a timestamp, so a gateway that restarted mid-ask resumes
    the cadence from where the clock is rather than immediately saying something — and so
    two looks a second apart cannot produce two lines.
    """
    reached = int(max(0.0, float(elapsed)) // CHECK_IN_SECONDS)
    return reached if reached > max(0, int(told)) else 0


def backoff_seconds(attempts: int) -> float:
    """How long to leave an ask alone after this many failed attempts at carrying it."""
    return CARRY_BACKOFF_SECONDS * (2 ** max(0, int(attempts) - 1))


def ready_to_carry(row: dict, now=None) -> bool:
    """Whether enough time has passed since this ask's latest failed carry.

    Wall time on both sides, and deliberately: the gateway deciding this is usually not the
    gateway that failed, so there is no monotonic clock the two share — the same reason a
    retention window is a durable stamp rather than an elapsed count.
    """
    stumbled = store.moment(row.get("carry_failed_at"))
    if stumbled is None:
        return True
    waited = backoff_seconds(row.get("carry_attempts") or 0)
    return (now or time.time)() - stumbled.timestamp() >= waited


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
    at = store.moment(store.stamped(now))
    quiet_before = store.stamped(lambda: (at - timedelta(hours=UNANSWERED_HOURS)).timestamp())
    gone_before = store.stamped(lambda: (at - timedelta(days=RETAINED_DAYS)).timestamp())
    settled, removed = [], []
    for row in every():
        state = row.get("state")
        if state in UNFINISHED:
            seen = row.get("latest_at") or row.get("asked_at") or ""
            if seen and seen <= quiet_before and _went_unanswered(row["id"], seen, now):
                settled.append(row["id"])
            continue
        if (row.get("settled_at") or "") and row["settled_at"] <= gone_before:
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
            "why": WENT_UNANSWERED.format(
                to=row.get("to") or "the agent it was handed to", seen=seen,
                hours=UNANSWERED_HOURS),
        })
        return True
