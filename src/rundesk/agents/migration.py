"""Carrying one agent, and every agent, onto this release.

The second of the two levels of migration. The first is `lifecycle/migration.py` — the install as a
whole — and this is written to be read beside it, because most of it is the same: a step is a file
in `steps/` named `NNNN_what_it_does.py`, steps are **found rather than listed**, they run in the
order their number gives, and **a step that has shipped is never renumbered, renamed or edited**.

Three things are deliberately different, and each of them is different for a reason:

| | install | agent |
|---|---|---|
| what has run | one string in `config.json` | one row per step in the `migrations` table |
| unit of failure | the install carries once | one agent that cannot be moved must not stop the others |
| stamping | written immediately after the step | written in the **same transaction** as the step's work |

**A row per step rather than one id.** An install is one thing and carries once, so the last step
applied says everything. Agents are many and are carried at different moments — one made last week,
one made this morning, one restored from a copy taken before either — and a single id per agent
would say how far that agent got without saying which steps that meant on the release it was
carried by. Rows also make "carried further than this release ships" a question with an answer:
a key in the table that this rundesk does not ship is an agent a **newer** rundesk moved forward,
and running an older release's steps over a newer release's layout is how data is damaged. That is
`Ahead`, and it is refused rather than guessed at.

**One agent that cannot be moved must not stop the others.** An install that cannot be carried is
one failure and one thing to fix. Twenty agents where the third has a corrupt database is nineteen
agents that are fine, and stopping at the third would take them all down for one of them. So
`carry_every` carries all of them and hands back the ones that failed, by name.

**Stamped inside the step's own transaction.** SQLite keeps schema changes inside a transaction, so
the step's work and the row recording it commit together or not at all — "it ran but was not
recorded" is not a state that can exist here. The install level cannot promise that, because its
steps move files and its mark is a separate JSON file, so it stamps immediately afterwards instead
and accepts the window.

## Rolling back is not optional here

Before an agent is carried, its records are copied aside — the database and any `-wal`/`-shm` — and
if a step fails they are put back, so the agent is exactly as it was. **Per agent**, so one agent's
rollback can never reach another's. And if the rollback itself fails, the sentence says that too:
an agent left neither carried nor put back is the one state somebody has to be told about, and it
is the one a summary of "3 failed" hides.

Finding steps and loading them is `utils.scripts`, shared with the install level. What is here is
only what differs: what an agent is handed, and how what has run is written down.
"""

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from rundesk.agents import directory, records
from rundesk.utils import files, scripts

STEPS = Path(__file__).resolve().parent / "steps"

#: What a step's module is called while it is loaded. Its own prefix, so an agent step and an
#: install step that share a number cannot collide with each other in `sys.modules`.
LOADED_AS = "rundesk_agent_step"

#: One step: where it is, the order it runs in, and its id. `utils.scripts`' own record, named here
#: as well so a caller never has to know which file the mechanism lives in.
Step = scripts.Script

#: A step that cannot be run at all, as opposed to one that ran and failed — two files sharing a
#: number, or a file with no `carry()` in it. `utils.scripts`' answer, named here too.
Broken = scripts.Broken


class Ahead(Exception):
    """This agent has been carried further than this release ships, so it may not be carried here.

    The fourth answer asking an agent for its records can give, and the one that is only a failure
    from an *older* rundesk's point of view: the agent is fine, and this copy of the product is the
    one that is behind. Refused rather than worked around, because running this release's steps over
    a layout a newer release made is how an agent's memory gets damaged.
    """


def found(where: Optional[Path] = None) -> List[Step]:
    """Every step this release ships, in the order they run. Found rather than listed.

    Two steps may not share a number — enforced by `utils.scripts`, and it matters here because the
    ids are what the `migrations` table holds. Two files numbered the same would be recorded under
    two keys with no order between them, and which one an agent had run would depend on the machine.
    """
    return scripts.found(where or STEPS)


def recorded(at: Path) -> List[str]:
    """The id of every step already run against these records, in the order the table gives.

    **A row per step, not one id** — see the module docstring. Records that are not there have had
    nothing run against them, which is an answer rather than a failure: it is what a brand new agent
    looks like a moment before its first step.
    """
    if not at.is_file():
        return []
    with records.reading(at) as conn:
        try:
            return [row[0] for row in conn.execute("SELECT key FROM migrations")]
        except sqlite3.DatabaseError as why:
            raise records.Unreadable(
                f"{at} does not say which steps have run against it: {why}") from why


def outstanding(applied: Iterable[str], where: Optional[Path] = None) -> List[Step]:
    """The steps that have not run yet, given which ones are already rows.

    `Ahead` when the table holds a key this release does not ship. That agent was carried by a newer
    rundesk, and the steps here were written against a layout that no longer describes it.
    """
    # **Never gate a repair on how far something has been carried.** A fix written as `if the agent
    # has not run 0012` never runs on the agents that actually had the bug, and a row-per-step table
    # makes that worse than a single version does: a repair shipped as a new step runs only on the
    # agents that have not run it, which is precisely the wrong set when the damage was done by an
    # earlier step those agents already have. A step that heals something looks at the data.
    steps = found(where)
    already = set(applied)
    beyond = sorted(already - {step.id for step in steps})
    if beyond:
        raise Ahead(
            f"this agent has been carried to {beyond[0]}, which this rundesk does not ship — "
            "it has been moved forward by a newer release, and going backwards is not supported")
    return [step for step in steps if step.id not in already]


def carry_one(name: str, where: Optional[Path] = None,
              saying: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Run every step this agent has not run. `None` when all is well, else the sentence saying why.

    A sentence rather than an exception, because the caller of this is usually `carry_every`, whose
    whole job is to go on to the next agent — and an exception is the shape that stops a loop.

    The records are copied aside first and put back if any step fails, so an agent is either carried
    or exactly as it was.

    **All the way back, not back to the last step that worked**, and that is the other place this
    differs from the install level. An install stamps each step as it lands and resumes from there,
    because its steps move files and there is nothing to undo them with. An agent's whole memory is
    one file that can be copied, so the useful state to leave somebody in is the one they had before
    they asked — one thing to look at rather than a database halfway between two releases. Running
    again re-runs the steps that worked, which is safe because every step is written to be safe
    against an agent that does not need it.

    Nothing here checks whether a gateway is reading this agent: a carry takes the write lock at
    `BEGIN IMMEDIATE`, so a reader waits and a second writer is refused, and the question of whether
    an agent should be running at all belongs to whoever is asking for it.
    """
    said = saying or (lambda _line: None)
    at = directory.records(name)
    within = directory.where(name)
    try:
        waiting = outstanding(recorded(at), where)
    except (Ahead, Broken, records.NotThere, records.Unreadable) as why:
        return f"{name} could not be carried: {why}"

    if not waiting:
        return None

    try:
        kept = _set_aside(at)
    except OSError as why:
        # Refused rather than carried anyway. A carry with no way back is the one shape of this
        # that can leave an agent's whole memory in a state nobody chose.
        return f"{name} could not be carried: its records could not be copied aside first ({why})"

    for step in waiting:
        said(f"carrying {name} to {step.id}")
        try:
            _one(at, within, step)
        except Exception as why:                      # noqa: BLE001 — a step is arbitrary code
            return _could_not(name, step, why, at, kept)
    _let_go(kept)
    return None


def carry_every(names: Iterable[str], where: Optional[Path] = None,
                saying: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
    """Carry every agent named, in name order. Maps the ones that failed to why.

    **One that fails does not stop the others**, which is the whole difference between this level
    and the install level. Nineteen agents that are fine are not something to take down because the
    third one's database cannot be read.

    An empty mapping means every one of them is on this release. Being handed no names is not a
    failure either — an install where nobody has added an agent yet has nothing to carry, and
    saying so is the honest answer rather than a discovery that found nothing.
    """
    gone_wrong: Dict[str, str] = {}
    for name in sorted(names):
        trouble = carry_one(name, where, saying)
        if trouble:
            gone_wrong[name] = trouble
    return gone_wrong


def stamp_without_running(at: Path, where: Optional[Path] = None) -> None:
    """Record every step as done without running one. What a **brand new agent** gets.

    There is nothing to carry: these records were built correctly a moment ago, and the steps
    describe changes from releases this agent never had. The same decision a fresh install makes,
    for the same reason.

    `OR IGNORE` because the step that built the records has already written its own row, in its own
    transaction — this is the rest of them, and re-stamping the first would be an error about a
    thing that is already true.
    """
    with records.writing(at) as conn:
        for step in found(where):
            conn.execute("INSERT OR IGNORE INTO migrations (key, completed_at) VALUES (?, ?)",
                         (step.id, _now()))


def _one(at: Path, within: Path, step: Step) -> None:
    """One step and its stamp, in one transaction, whole or not at all.

    **The row goes in with the work.** SQLite keeps schema changes inside a transaction, so a step
    that dies halfway leaves neither its change nor its record — there is no "ran but was not
    recorded" for an agent, which is a state the install level has to live with and this one does
    not.

    The step is handed the open connection and the agent's own directory, so it can change tables
    and files together.
    """
    with records.writing(at, making=True) as conn:
        scripts.carrying(step, LOADED_AS)(conn, within)
        conn.execute("INSERT INTO migrations (key, completed_at) VALUES (?, ?)", (step.id, _now()))


def _could_not(name: str, step: Step, why: BaseException, at: Path, kept: List[Path]) -> str:
    """Put this agent's records back, and say what happened — including if putting them back failed.

    Two different sentences, because they are two different things for somebody to do. The first is
    an agent that is exactly as it was and a step to fix. The second is an agent that is neither
    carried nor as it was, which is the one state that has to be told to a person out loud rather
    than counted in a summary.
    """
    stuck = _put_back(at, kept)
    if stuck:
        return (f"{name} could not be carried to {step.id}: {why} — and worse, its records could "
                f"not be put back as they were: {', '.join(stuck)}")
    _let_go(kept)
    return (f"{name} could not be carried to {step.id}: {why} — "
            "its records were put back as they were")


def _set_aside(at: Path) -> List[Path]:
    """Copy this agent's records aside, and hand back the copies that were taken.

    **This agent's, beside its own records**, so one agent's rollback cannot reach another's — there
    is no shared directory for two of these to meet in.

    Named through `utils.files`' staging convention, which is what a walk over an agent's directory
    already knows to skip. `OUTGOING` rather than `INCOMING` because that is exactly what these are:
    what is being replaced, kept so it can be put back.

    Only what is there is copied. The siblings exist only while a writer is live, and a brand new
    agent has no database at all — for which the honest rollback is to leave none.
    """
    kept = []
    for one in records.beside(at):
        if not one.exists():
            continue
        copy = one.with_name(files.OUTGOING.format(name=one.name))
        files.discard(copy)
        shutil.copy2(one, copy)
        kept.append(one)
    return kept


def _put_back(at: Path, kept: List[Path]) -> List[str]:
    """Put every copy back, and say which could not be. Every one is tried, never stopping at the first.

    **What was not set aside is taken away rather than left.** A write-ahead log written by the
    attempt that just failed, standing beside a database that has been put back, is read by the next
    connection as that database's most recent truth — so restoring the file alone would restore the
    bytes and none of the meaning. The old build recorded exactly this.
    """
    stuck = []
    for one in records.beside(at):
        copy = one.with_name(files.OUTGOING.format(name=one.name))
        try:
            if one in kept:
                shutil.copy2(copy, one)
            elif one.exists():
                one.unlink()
        except OSError as why:
            stuck.append(f"{one.name} ({why})")
    return stuck


def _let_go(kept: List[Path]) -> None:
    """Let go of the copies, now that the move they insured has been made."""
    for one in kept:
        files.discard(one.with_name(files.OUTGOING.format(name=one.name)))


def _now() -> str:
    """The moment a step landed, in the same shape the install records its own moments in."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
