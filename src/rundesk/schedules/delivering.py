"""Where a finished scheduled report goes when it is not the owner's channel: another agent's turn.

A schedule that asks an agent reports where that agent is told things. `--deliver-to` adds one more
place for the finished report to land — **a turn taken by a named second agent**, on the ordinary
terms that agent works on: its own brain, its own records, its own final going wherever its finals
go. Nothing is owed back. This is a report handed over, not work handed over, so no delegation is
written anywhere and nothing waits for an answer.

## Two stores, one direction, and no cross-agent write

A clock-fired run freezes an obligation in its own agent's store before the child starts. A
successful result resolves that obligation into one outbox row; the recipient's gateway reads the
row out of the source's store, read-only, and records the report into its own. That is
the shape `delegations.hosting` already uses to find work addressed to this agent, and it is chosen
here for the same reason: there is no install-wide table for two gateways to disagree over, and no
gateway writes a store it does not own.

It is also what makes an **offline or busy recipient cost the report nothing**. The row is durable
before the source firing's recovery record is removed. A recipient whose gateway is down reads the
outbox when it comes up; one whose
agent is mid-turn admits the report into that turn or takes the next one; one that was never running
at all still finds every row waiting in the order they were written.

## Exactly once, three ways over

**At the writing end**, the obligation and outbox share a unique `run_key`: the scheduled
invocation's own conversation id, fixed before the work starts. The observed outcome is written into
the firing recovery record and the obligation before that record is removed. A replacement gateway
retries any successful unresolved obligation, while duplicate attempts find the same outbox row.

**At the reading end**, a mark per source says how far into that outbox this agent has read, and it
moves only after the report is durably in this agent's own records. A crash between the two re-reads
a row already recorded, which is the third guard: the conversation is unique by its `source_id` and
the message by its `external_id`, so recording it again writes nothing at all.

The source copies that mark into `acknowledged_at` on its own outbox row. That durable receipt is
what makes either agent removable after admission: deleting the recipient also deletes its mark,
but never deletes the source's proof that the report was already accepted.

**The mark is kept against the source's identity and never its name.** A source removed and re-made
under the same name is a different agent whose row ids start at one again; a mark kept by name would
read *already seen* over the new agent's first reports and lose every one of them.

## A name is not who somebody is

Both ends check identity, and neither trusts the name alone:

- The schedule stores who the target **was** when somebody typed it. A target removed and re-made is
  a different agent, so the row this run writes carries an identity nobody else can match.
- The recipient answers only rows whose `to_identity` is **its own**. A stranger holding the old name
  reads the row, sees an identity that is not its, and moves its mark past it without ever recording
  it.

The two together are why a schedule can never be silently redirected: there is no step at which a
name is resolved to whoever holds it now.

May depend on `agents`, `core` and `utils`.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, NamedTuple, Optional

from rundesk.agents import directory, records
from rundesk.core import config, paths
from rundesk.schedules import kept
from rundesk.utils import locking, logs

#: The two tables this reads and writes, named once.
OUTBOX = "schedule_deliveries"
OBLIGATIONS = "schedule_delivery_obligations"
MARKS = "schedule_delivery_marks"

#: How much of a finished report is carried. Generous — a scheduled report is the whole account of a
#: run and clipping it would lose the end, which is where a report says what it came to — and
#: bounded, because it is written into a second agent's records and an agent's memory is not
#: somewhere another agent's schedule gets to fill. The same figure `channels.arriving` keeps one
#: message to, spelled here because this layer may not import that one.
A_REPORT_AT_MOST = 60 * 1024
REPORT_OMISSION = "\n\n[… middle omitted to fit scheduled delivery …]\n\n"

#: How many rows one pass reads out of one source's outbox. A gateway that came up to find a
#: fortnight of reports waiting must not spend its whole first pass on them and answer nobody: the
#: rest are still there next beat, and the mark means none of them is lost by waiting.
FETCHED_AT_MOST = 8

#: How many delivered reports one pass will start a turn for. Fewer than the number fetched, and
#: fewer than a delegation's four, because each one is a whole brain run on this agent.
ANSWERED_AT_MOST = 2


class Delivery(NamedTuple):
    """One finished report a source agent's outbox is holding, as the recipient reads it."""

    id: int
    schedule_name: str
    run_key: str
    ran_at: str
    to_agent: str
    to_identity: str
    report: str


class Obligation(NamedTuple):
    """One clock-fired invocation whose frozen target has not been resolved yet."""

    schedule_name: str
    run_key: str
    began_at: str
    to_agent: str
    to_identity: str
    outcome: str
    settled_at: Optional[str]


class Handing:
    """How a delivered report is put in front of this agent. Handed in, never reached for.

    The seam `channels.hosting` and `schedules.firing` already publish twice over, and for the same
    reason: this layer may not import `channels` or `providers`, so what it asks for is a *shape* —
    something that knows how to write a message into an agent's conversations and how to start an
    ordinary turn on one. The whole of this module stays drivable by a case with no brain, no
    adapter and no subprocess anywhere near it.

    `recorded` writes one delivered report into this agent's own records and answers whether it is
    durably there. **`False` moves no mark**: the row stays unread and the next pass tries again,
    which is what keeps a store that could not be written from losing a report.

    `answer_waiting` starts an ordinary turn for delivered reports nothing has picked up yet. It is
    asked every pass rather than only after something new arrives, because a report recorded while
    the agent was busy, or a moment before a gateway went down, is waiting with nobody coming back
    for it otherwise.
    """

    def recorded(self, agent: str, from_agent: str, from_identity: str, schedule: str,
                 run_key: str, ran_at: str, report: str) -> bool:
        raise NotImplementedError

    def answer_waiting(self, agent: str) -> None:
        raise NotImplementedError


# -- what one scheduled invocation owes ------------------------------------------------


def started(agent: str, schedule: str, run_key: str, began_at: str,
            to_agent: Optional[str], to_identity: Optional[str]) -> bool:
    """Freeze one invocation's delivery target before its work starts.

    `False` means this invocation uses the source's ordinary notice. The name and immutable identity
    are written together before the child is spawned, so changing the schedule while it runs cannot
    redirect its final report or disagree with whether its start notice was suppressed.
    """
    named, identity = str(to_agent or ""), str(to_identity or "")
    if not named or not identity:
        return False
    with locking.only_one(paths.lock(), "this install"):
        try:
            if identity_of(named) != identity:
                return False
        except (records.NotThere, records.Unreadable, OSError, sqlite3.Error):
            return False
        with records.writing(directory.records(agent)) as conn:
            _asked(conn, agent,
                   f"INSERT INTO {OBLIGATIONS}"
                   " (run_key, schedule_name, began_at, to_agent, to_identity)"
                   " VALUES (?, ?, ?, ?, ?) ON CONFLICT (run_key) DO NOTHING",
                   (run_key, schedule, began_at, named, identity))
    return True


def finished(agent: str, run_key: str, outcome: str,
             when: Optional[datetime] = None) -> None:
    """Settle a frozen obligation before the firing's recovery record is removed."""
    if not run_key:
        return
    with records.writing(directory.records(agent)) as conn:
        if outcome != kept.DONE:
            _asked(conn, agent, f"DELETE FROM {OBLIGATIONS} WHERE run_key = ?", (run_key,))
            return
        _asked(conn, agent,
               f"UPDATE {OBLIGATIONS} SET outcome = ?, settled_at = ?"
               " WHERE run_key = ? AND outcome = 'running'",
               (outcome, _now(when), run_key))


def unresolved(agent: str, most: int = FETCHED_AT_MOST) -> List[Obligation]:
    """Successful invocations whose final route has not been durably resolved, oldest first."""
    with records.reading(directory.records(agent)) as conn:
        rows = _asked(
            conn, agent,
            f"SELECT * FROM {OBLIGATIONS}"
            " WHERE outcome = 'done' AND resolved_at IS NULL ORDER BY began_at LIMIT ?",
            (most,)).fetchall()
    return [_obligation(one) for one in rows]


def owed(agent: str, schedule: str, run_key: str, ran_at: str, report: str,
         when: Optional[datetime] = None) -> bool:
    """Resolve one successful report while agent removal cannot cross the decision."""
    with locking.only_one(paths.lock(), "this install"):
        return _owed(agent, schedule, run_key, ran_at, report, when)


def _owed(agent: str, schedule: str, run_key: str, ran_at: str, report: str,
          when: Optional[datetime] = None) -> bool:
    """Write down that this finished run owes its report to another agent. **After it completed.**

    `True` when this run owes a delivery — whether this call was the one that wrote the row or found
    it already there. `False` when the schedule names nowhere to deliver, or when the run produced
    nothing to deliver: a report with no words in it would start a second agent's turn with nothing
    in front of it.

    **What this invocation froze before its child started**, never what the schedule says now.
    Adding, clearing, changing, or removing the schedule while it runs cannot redirect its final or
    disagree with the start-notice decision made from the same frozen pair.
    """
    with records.reading(directory.records(agent)) as conn:
        row = _asked(conn, agent, f"SELECT * FROM {OBLIGATIONS} WHERE run_key = ?",
                     (run_key,)).fetchone()
    if row is None:
        return False
    obligation = _obligation(row)
    if obligation.outcome != kept.DONE:
        return False
    to_agent, to_identity = obligation.to_agent, obligation.to_identity
    completed_at = obligation.settled_at or ran_at
    # A removed target is no longer somewhere this report can go. Resolve both the name and the
    # immutable identity at completion so a successful run falls back to the source's ordinary
    # notice instead of being hidden behind an outbox row no agent can ever claim.
    try:
        if identity_of(to_agent) != to_identity:
            return _resolved_to_source(agent, run_key, when)
    except (records.NotThere, records.Unreadable, OSError, sqlite3.Error):
        return _resolved_to_source(agent, run_key, when)
    said = report.strip()
    if not said:
        return False
    with records.writing(directory.records(agent)) as conn:
        current = _asked(conn, agent,
                         f"SELECT resolved_at FROM {OBLIGATIONS} WHERE run_key = ?",
                         (run_key,)).fetchone()
        if current is None:
            return False
        if current[0] is not None:
            existing = _asked(conn, agent,
                              f"SELECT 1 FROM {OUTBOX} WHERE run_key = ?", (run_key,)).fetchone()
            return existing is not None
        _asked(conn, agent,
               f"INSERT INTO {OUTBOX}"
               " (schedule_name, run_key, ran_at, to_agent, to_identity, report, created_at)"
               " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (run_key) DO NOTHING",
               (schedule, run_key, completed_at, to_agent, to_identity,
                _bounded_report(said), _now(when)))
        _asked(conn, agent,
               f"UPDATE {OBLIGATIONS} SET resolved_at = ?, resolution = 'delivered'"
               " WHERE run_key = ? AND resolved_at IS NULL", (_now(when), run_key))
    return True


def _resolved_to_source(agent: str, run_key: str, when: Optional[datetime]) -> bool:
    """Resolve an obligation to the source notice and answer `False` to its reporting caller."""
    with records.writing(directory.records(agent)) as conn:
        _asked(conn, agent,
               f"UPDATE {OBLIGATIONS} SET resolved_at = ?, resolution = 'source'"
               " WHERE run_key = ? AND resolved_at IS NULL", (_now(when), run_key))
    return False


def owing(agent: str, to_agent: Optional[str] = None) -> List[Delivery]:
    """Everything this agent's outbox is holding, oldest first. Reads and changes nothing.

    Kept for the recipient's sweep and for a case that wants to see what a completed run wrote. The
    outbox is never swept by this module: a row is the account of what one run handed over, and the
    recipient cannot write it — see the module docstring on which store each end owns.
    """
    where, values = "", ()  # type: str, tuple
    if to_agent is not None:
        where, values = " WHERE to_agent = ?", (to_agent,)
    with records.reading(directory.records(agent)) as conn:
        found = _asked(conn, agent,
                       f"SELECT * FROM {OUTBOX}{where} ORDER BY id", values).fetchall()
    return [_read(one) for one in found]


def acknowledged(agent: str, when: Optional[datetime] = None) -> None:
    """Persist in this source store every recipient mark that proves admission.

    A recipient's mark disappears with that agent. Copying its proof here before removal is allowed
    makes acknowledgement survive at the end that owns the outbox; target removal waits while any
    row addressed to it is still unacknowledged.
    """
    with locking.only_one(paths.lock(), "this install"):
        from_identity = identity_of(agent)
        with records.reading(directory.records(agent)) as conn:
            rows = _asked(conn, agent,
                          f"SELECT id, to_agent, to_identity FROM {OUTBOX}"
                          " WHERE acknowledged_at IS NULL ORDER BY id").fetchall()
        admitted = []
        for row in rows:
            try:
                target, identity = str(row["to_agent"]), str(row["to_identity"])
                if identity_of(target) == identity and _mark(target, from_identity) >= int(row["id"]):
                    admitted.append(int(row["id"]))
            except (records.NotThere, records.Unreadable, OSError, sqlite3.Error):
                continue
        if admitted:
            with records.writing(directory.records(agent)) as conn:
                for row_id in admitted:
                    _asked(conn, agent,
                           f"UPDATE {OUTBOX} SET acknowledged_at = ?"
                           " WHERE id = ? AND acknowledged_at IS NULL",
                           (_now(when), row_id))


def has_unread_from(agent: str) -> bool:
    """Whether removing this source would destroy a report its recipient has not admitted."""
    if unresolved(agent, 1):
        return True
    with records.reading(directory.records(agent)) as conn:
        found = _asked(conn, agent,
                       f"SELECT 1 FROM {OUTBOX} WHERE acknowledged_at IS NULL LIMIT 1").fetchone()
    return found is not None


def has_unread_for(agent: str) -> bool:
    """Whether removing this target would strand a source outbox row addressed to its identity."""
    me = identity_of(agent)
    for source in directory.known():
        if source == agent:
            continue
        try:
            from_identity = identity_of(source)
            if not from_identity:
                continue
            with records.reading(directory.records(source)) as conn:
                found = _asked(
                    conn, source,
                    f"SELECT 1 FROM {OUTBOX} WHERE to_agent = ? AND to_identity = ?"
                    " AND acknowledged_at IS NULL LIMIT 1", (agent, me)).fetchone()
            if found is not None:
                return True
        except (records.NotThere, records.Unreadable, OSError, sqlite3.Error):
            return True
    return False


# -- where a schedule may be told to deliver -------------------------------------------


def target_trouble(owner: str, to_agent: Optional[str]) -> str:
    """Why this agent may not be given a schedule's finished report, or `""` when it may.

    A sentence rather than an exception, for the reason `commands.schedules.firing_trouble` gives:
    the caller is a command whose job is to tell somebody what to type instead, and the answer is
    wanted before anything is written and never again.

    **Refused where somebody typed it**, which is the only moment they can do anything about it. A
    target that is not on this machine, or is this agent itself, found instead by a gateway is a
    line in a log at six in the morning about a report that reached nobody.
    """
    if to_agent is None or not to_agent.strip():
        return ("nothing said which agent the report goes to — name one with: "
                "--deliver-to '<agent>'")
    named = to_agent.strip()
    if named == owner:
        return (f"{owner} cannot deliver its own report to itself — that is the report it already "
                "makes, and delivering it again would start a second turn about it")
    gone_wrong = directory.not_an_agent(named)
    if gone_wrong:
        return gone_wrong
    try:
        if not identity_of(named):
            return (f"{named} has no identity to deliver to yet — carry this install forward with: "
                    "rundesk update")
    except (records.NotThere, records.Unreadable, OSError, sqlite3.Error) as why:
        return f"{named} could not be read, so a schedule cannot be pointed at it ({why})"
    return ""


def identity_of(agent: str) -> str:
    """Who this agent is, whatever it is called. `""` where its records do not say."""
    return records.identity(directory.records(agent))


# -- what the recipient's gateway does every pass --------------------------------------


def looked(agent: str, where: Path, handing: Handing) -> None:
    """One pass: read what other agents' schedules have handed here, then answer what is waiting.

    **Reading first.** A pass that answered first would start turns for what it already had while a
    report written a second ago sat unread — and the agent whose schedule wrote it has already
    finished and gone.

    Never raises. A pass that threw would take the gateway's loop with it, and every other thing a
    gateway does is more important than one delivery. What went wrong is written to this agent's own
    log and the pass goes on — the same rule, and the same shape, as `delegations.hosting.looked`.
    """
    _whatever_happens(where, "reading what other agents' schedules delivered here",
                      lambda: _fetched(agent, where, handing))
    _whatever_happens(where, "answering what was delivered here",
                      lambda: handing.answer_waiting(agent))


def _whatever_happens(where: Path, doing: str, sweep: Callable[[], None]) -> None:
    """Run one sweep, or write down why it did not happen and let the pass go on.

    **The whole sweep, not each item**, for the reason `delegations.hosting` gives: an agent removed
    while its gateway runs makes every read here fail at once, and that is the sweep's failure
    rather than one delivery's.
    """
    try:
        sweep()
    except Exception as why:  # noqa: BLE001 — see the docstring, and `looked`
        # Only where there is still somewhere to write. An agent taken away while its gateway runs
        # is exactly when this fires, and a directory invented by whatever is complaining that it is
        # missing is one that then looks half-made to everything else.
        if Path(where).exists():
            logs.note(where, f"deliveries: {doing} did not happen this pass ({why})", logs.ERROR)


def _fetched(agent: str, where: Path, handing: Handing) -> None:
    """Record every report addressed to this agent that it has not read yet, and move each mark.

    A source whose store cannot be read is skipped rather than raised on: one broken agent must not
    stop this one reading everybody else. A source carried no further than the release before this
    one has no outbox at all, which is the same skip and not a failure.
    """
    me = identity_of(agent)
    if not me:
        # Nothing can be proved to be addressed here, and answering a row by name alone is the one
        # thing this whole design exists to prevent.
        return
    for source in directory.known():
        if source == agent:
            continue
        try:
            from_identity = identity_of(source)
            if not from_identity:
                continue
            waiting = _addressed_here(source, agent, after=_mark(agent, from_identity))
        except (records.NotThere, records.Unreadable, OSError, sqlite3.Error):
            continue
        for one in waiting:
            if one.to_identity != me:
                # A stranger holding the name this schedule was pointed at. Never recorded, and the
                # mark moves past it because it will never become ours.
                _mark_moved(agent, from_identity, source, one.id)
                continue
            try:
                if not handing.recorded(agent, source, from_identity, one.schedule_name,
                                        one.run_key, one.ran_at, one.report):
                    # Left unread on purpose. The next pass reads this same row again rather than
                    # moving past a report this agent has not managed to write down.
                    break
            except Exception as why:  # noqa: BLE001 — one bad row may not end the sweep
                logs.note(where,
                          f"deliveries: {source}'s report from {one.schedule_name} could not be "
                          f"recorded ({why})", logs.ERROR)
                break
            _mark_moved(agent, from_identity, source, one.id)
            logs.note(where,
                      f"deliveries: recorded {source}'s report from schedule {one.schedule_name}")


def _addressed_here(source: str, agent: str, after: int) -> List[Delivery]:
    """What one source agent's outbox is holding for this one, oldest first and bounded.

    **Read out of that agent's store, read-only**, which is what stands in for a cross-agent table:
    a handful of agents, an indexed query per store, once a beat.
    """
    with records.reading(directory.records(source)) as conn:
        found = _asked(conn, source,
                       f"SELECT * FROM {OUTBOX} WHERE to_agent = ? AND id > ?"
                       " ORDER BY id LIMIT ?",
                       (agent, after, FETCHED_AT_MOST)).fetchall()
    return [_read(one) for one in found]


def _mark(agent: str, from_identity: str) -> int:
    """How far into that source's outbox this agent has already read. `0` before it has read any."""
    with records.reading(directory.records(agent)) as conn:
        found = _asked(conn, agent, f"SELECT last_id FROM {MARKS} WHERE from_identity = ?",
                       (from_identity,)).fetchone()
    return int(found[0]) if found is not None else 0


def _mark_moved(agent: str, from_identity: str, from_agent: str, last_id: int,
                when: Optional[datetime] = None) -> None:
    """Move the mark forward, and never back.

    `max` of the two rather than assignment, because two passes of one gateway may overlap on the
    slow beat a busy machine gives them, and a mark that went backwards would read a report a second
    time. Reading one twice costs nothing — the conversation and the message are both already there
    — but a mark that can move either way is one nothing can reason about.
    """
    with records.writing(directory.records(agent)) as conn:
        _asked(conn, agent,
               f"INSERT INTO {MARKS} (from_identity, from_agent, last_id, updated_at)"
               " VALUES (?, ?, ?, ?) ON CONFLICT (from_identity) DO UPDATE SET"
               " last_id = max(last_id, excluded.last_id), from_agent = excluded.from_agent,"
               " updated_at = excluded.updated_at",
               (from_identity, from_agent, int(last_id), _now(when)))


def _read(row: Any) -> Delivery:
    """One outbox row as the thing it is, whichever store it was read out of."""
    got = dict(row)
    return Delivery(id=int(got["id"]), schedule_name=str(got["schedule_name"]),
                    run_key=str(got["run_key"]), ran_at=str(got["ran_at"]),
                    to_agent=str(got["to_agent"]), to_identity=str(got["to_identity"]),
                    report=str(got["report"] or ""))


def _obligation(row: Any) -> Obligation:
    """One durable invocation target as the thing it is."""
    got = dict(row)
    return Obligation(schedule_name=str(got["schedule_name"]), run_key=str(got["run_key"]),
                      began_at=str(got["began_at"]), to_agent=str(got["to_agent"]),
                      to_identity=str(got["to_identity"]), outcome=str(got["outcome"]),
                      settled_at=(str(got["settled_at"]) if got["settled_at"] else None))


def _bounded_report(said: str) -> str:
    """Fit one report while retaining both its opening and its conclusion."""
    if len(said) <= A_REPORT_AT_MOST:
        return said
    remaining = A_REPORT_AT_MOST - len(REPORT_OMISSION)
    opening = remaining // 2
    return said[:opening] + REPORT_OMISSION + said[-(remaining - opening):]


def _asked(conn: sqlite3.Connection, agent: str, sql: str,
           values: tuple = ()) -> sqlite3.Cursor:
    """Ask, saying which agent it was when the records cannot answer.

    A store carried no further than the release before this one has no outbox, and *no such table*
    arrives here as the same `DatabaseError` a corrupt file does. Both are `Unreadable` for this
    agent, which is what the sweep skips on — and neither is a reason to stop reading everybody
    else.
    """
    try:
        return conn.execute(sql, values)
    except sqlite3.DatabaseError as why:
        raise records.Unreadable(
            f"{agent} does not hold deliveries that can be read: {why}") from why


def _now(when: Optional[datetime] = None) -> str:
    """A moment this product keeps for a machine to compare, in the one shape it keeps them in."""
    return config.moment_of(when)
