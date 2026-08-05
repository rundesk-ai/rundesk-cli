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

Before an agent is carried, **the agent's directory is copied aside** — not only the database — and
if a step fails it is all put back, so the agent is as it was apart from what `NOT_PUT_BACK` names.
A step is handed a connection *and* a directory precisely so it can change tables and files
together, so a rollback that reached only `state.db` left a step's files standing beside records
that no longer mention them: the two then disagree about history, and the next step doing "check,
then act" against one of those files is answered by a shape nothing recorded.

**Per agent**, so one agent's rollback can never reach another's. And if the rollback itself fails,
the sentence says that too: an agent left neither carried nor put back is the one state somebody has
to be told about, and it is the one a summary of "3 failed" hides.

## One lock, around the whole of a carry

`BEGIN IMMEDIATE` protects the database *file*, and it is not the safety this level rests on. The
copy-aside-and-put-back bracket around the steps is plain file copying, and two carries of one agent
were measured destroying each other through it: the second took its copy before the first had
committed anything, lost the race for the write lock, concluded it had failed, and put that copy
back — retracting a step the first had already reported as done, with nothing anywhere saying so.
So `carry_one` holds the install's own lock around all of it, and `carry_every` holds it once around
the whole sweep rather than picking it up and putting it down between agents.

## Two clocks, and which one a moment belongs to

This product keeps time in two shapes and the rule is which reader the moment is for, never which
module wrote it. **Anything stored for a machine to order or compare is UTC**, to the second, in
`core.config.MOMENT` — the rows in this table, and the moment an install records a version arriving.
A database copied off this machine and restored on another must still sort into the order things
happened, and a local stamp would not: it carries an offset the restoring machine does not have, and
across a daylight-saving fall-back it repeats an hour, so two rows an hour apart compare as the same
moment. **Anything a person reads directly is the machine's own clock with its offset**, which is
`utils.logs.stamp` — the lines in a log, and what a gateway's record says it has been up since,
because the question anybody asks is *what happened at nine last night, when I noticed?*

Both exist because they answer to different readers, and neither is a better version of the other.
A moment that is written for a machine and shown to a person is a moment somebody has to convert in
their head; a moment written for a person and then sorted by a machine is one that sorts wrongly
twice a year.

Finding steps and loading them is `utils.scripts`, shared with the install level. What is here is
only what differs: what an agent is handed, and how what has run is written down.
"""

import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from rundesk.agents import directory, records
from rundesk.core import config, paths
from rundesk.utils import files, locking, scripts

STEPS = Path(__file__).resolve().parent / "steps"

#: What a carry never copies aside and therefore never puts back. **Expected to grow, and the
#: growing is what keeps a rollback affordable.**
#:
#: `logs/` is here because rolling back the record of what has just gone wrong is backwards: the
#: lines explaining the failure are the one thing somebody needs afterwards.
#:
#: `schedules/` is here for that same principle: **an unbounded collection directory does not belong
#: in a rollback.** It holds what every firing of every schedule wrote, which grows for as long as
#: the agent has schedules, and copying it aside would make every future migration slowest on
#: exactly the agents somebody uses most. It also holds the lock a *running* firing is holding, and
#: putting a lock file back underneath a live child is putting back a claim that has moved on.
#:
#: The principle for everything after it is the same. `sessions/` and `providers/` are coming, one
#: directory per session kept for the life of the agent; neither exists yet, so neither is named
#: here — whoever adds the first one adds it to this tuple in the same change, and reads the rule in
#: `steps/__init__.py` that says what a step may then do inside it.
#:
#: Today the rest of an agent is `state.db` and `home/`, and `home/` is a few kilobytes of markdown,
#: so copying it aside costs nothing and makes the promise true. That is the trade now; this tuple
#: is what keeps it true later.
NOT_PUT_BACK = (directory.LOGS, directory.SCHEDULES)

#: What the copy of an agent's things is called while that agent is being carried. `utils.files`'
#: staging convention, so every walk over a directory already skips it, and **inside the agent's own
#: directory**, so one agent's rollback has no shared place to meet another's in.
ASIDE = "carry"

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
    """This agent holds a row for a step this release does not ship, so it may not be carried here.

    The fourth answer asking an agent for its records can give. **Two things look identical from
    here and the sentence names both**, because the second is by far the likelier one for a
    developer to have caused: either a newer rundesk moved this agent forward — in which case the
    agent is fine and this copy of the product is the one that is behind — or a step that had
    already shipped was deleted or renamed in this checkout, which the rules forbid and nothing
    prevents. Refused either way, because running this release's steps over a layout that was
    carried past them is how an agent's memory gets damaged.
    """


class Backfilled(Exception):
    """A step numbered below one this agent has already run, which nothing may do.

    **A step's number must exceed every number any previously shipped release used.** That rule is
    what makes "which steps have run" answerable at all, and until this it was asserted in prose in
    three docstrings and checked nowhere. A step back-filled below an agent's high-water mark runs
    *after* steps that were written assuming it had already happened — and at the install level,
    where how far something has got is one id rather than a row set, it never runs at all.
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

    `Ahead` when the table holds a key this release does not ship — a newer rundesk moved this agent
    forward, or a shipped step was deleted or renamed here.

    `Backfilled` when a step that has *not* run is numbered below one that has. The rows say the
    highest number this agent has ever seen, so this level can ask the question the install level
    cannot, and it is refused rather than run out of order: the steps written after it were written
    expecting it to have happened already.
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
            "either a newer release moved it forward, or a step that had already shipped was "
            "deleted or renamed in this copy of rundesk; going backwards is not supported")
    waiting = [step for step in steps if step.id not in already]
    # The high-water mark, asked of the rows rather than of the list's shape. Every step at or below
    # it has run, so one that has not is a step somebody added underneath an agent's own history.
    highest = max((step.order for step in steps if step.id in already), default=-1)
    behind = [step for step in waiting if step.order <= highest]
    if behind:
        raise Backfilled(
            f"{behind[0].id} is numbered below {highest:04d}, which this agent has already been "
            f"carried past — a step that has shipped is never renumbered, renamed or back-filled, "
            f"so {behind[0].id} either has to go or has to become a new step with a number above "
            "every number any release has used")
    return waiting


def carry_one(name: str, where: Optional[Path] = None,
              saying: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Run every step this agent has not run. `None` when all is well, else the sentence saying why.

    A sentence rather than an exception, because the caller of this is usually `carry_every`, whose
    whole job is to go on to the next agent — and an exception is the shape that stops a loop.

    The agent's directory is copied aside first — everything but `NOT_PUT_BACK` — and put back if
    any step fails, so the agent is either carried or as it was apart from its logs.

    **All the way back, not back to the last step that worked**, and that is the other place this
    differs from the install level. An install stamps each step as it lands and resumes from there,
    because its steps move files and there is nothing to undo them with. An agent's whole memory is
    one directory that can be copied, so the useful state to leave somebody in is the one they had
    before they asked — one thing to look at rather than an agent halfway between two releases.
    Running again re-runs the steps that worked, which is safe because every step is written to be
    safe against an agent that does not need it.

    **The whole of this is under the install's own lock, and that is the guarantee — not the write
    lock underneath it.** `BEGIN IMMEDIATE` protects the database *file*; it says nothing about the
    copy-aside-and-put-back bracket around the steps, which is plain file copying. Two carries of
    one agent were measured through that gap: the second copied the agent aside before the first had
    committed anything, lost the race for the write lock, concluded it had failed, and put its copy
    back — retracting a step the first had already reported as done. **The refusal was never the
    safety; the loser's own rollback was the danger.**

    `directory.made` holds this same lock and then calls this, which is why `locking.only_one`
    counts nesting per thread instead of locking twice: the outermost holder owns it and this passes
    straight through. Neither side of that may be "simplified" into the other — `made` needs it
    around the staged build it does before ever reaching here, and a carry that is not reached
    through `made` needs it just as much.

    Nothing here checks whether a gateway is reading this agent. A reader waits on the busy timeout,
    and the question of whether an agent should be running at all belongs to whoever is asking.
    """
    with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
        return _carried(name, where, saying or (lambda _line: None))


def carry_every(names: Iterable[str], where: Optional[Path] = None,
                saying: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
    """Carry every agent named, in name order. Maps the ones that failed to why.

    **One that fails does not stop the others**, which is the whole difference between this level
    and the install level. Nineteen agents that are fine are not something to take down because the
    third one's database cannot be read.

    An empty mapping means every one of them is on this release. Being handed no names is not a
    failure either — an install where nobody has added an agent yet has nothing to carry, and
    saying so is the honest answer rather than a discovery that found nothing.

    **The lock is taken once, around the whole sweep**, rather than per agent. Picking it up and
    putting it down between agents leaves a gap after every one of them for another writer to make
    an agent, remove one, or start a carry of its own — so a sweep that reported twenty agents
    carried would be reporting on an install that changed underneath it. `carry_one` takes the same
    lock and nests through it.
    """
    gone_wrong: Dict[str, str] = {}
    with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
        for name in sorted(names):
            trouble = carry_one(name, where, saying)
            if trouble:
                gone_wrong[name] = trouble
    return gone_wrong


def _carried(name: str, where: Optional[Path], said: Callable[[str], None]) -> Optional[str]:
    """Everything `carry_one` promises, with the lock already held. Never called from anywhere else."""
    at = directory.records(name)
    within = directory.where(name)
    try:
        waiting = outstanding(recorded(at), where)
    except (Ahead, Backfilled, Broken, records.NotThere, records.Unreadable) as why:
        return f"{name} could not be carried: {why}"

    if not waiting:
        return None

    try:
        aside = _set_aside(within)
    except OSError as why:
        # Refused rather than carried anyway. A carry with no way back is the one shape of this
        # that can leave an agent's whole memory in a state nobody chose.
        return f"{name} could not be carried: it could not be copied aside first ({why})"

    for step in waiting:
        said(f"carrying {name} to {step.id}")
        try:
            _one(at, within, step)
        except Exception as why:                      # noqa: BLE001 — a step is arbitrary code
            return _could_not(name, step, why, within, aside)
    _let_go(aside)
    return None


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

    **The transaction is checked to be still open before the row is written**, because a step is
    arbitrary code and `commit()`, `rollback()` and a raw `COMMIT` are all one call away. With
    `isolation_level=None` any of them ends the transaction this runner opened, and everything after
    — including the `INSERT` below — then runs in its own autocommit. The step's work would be
    durably on disk and the row recording it would be a separate write that a crash can land
    between, which is the one state this level exists not to have. Refused as `Broken` rather than
    stamped: a row written outside the transaction its work was in records nothing anybody can
    trust.
    """
    with records.writing(at, making=True) as conn:
        scripts.carrying(step, LOADED_AS)(conn, within)
        if not conn.in_transaction:
            raise Broken(
                f"{step.id} ended the transaction the runner opened around it — a step may not "
                "call commit() or rollback(), and may not issue BEGIN, COMMIT or END, because the "
                "row recording a step has to land in the same transaction as the step's work")
        conn.execute("INSERT INTO migrations (key, completed_at) VALUES (?, ?)", (step.id, _now()))


def _could_not(name: str, step: Step, why: BaseException, within: Path,
               aside: Optional[Path]) -> str:
    """Put this agent back, and say what happened — including if putting it back failed.

    Two different sentences, because they are two different things for somebody to do. The first is
    an agent that is as it was and a step to fix. The second is an agent that is neither carried nor
    as it was, which is the one state that has to be told to a person out loud rather than counted
    in a summary.

    **What was put back is named rather than implied.** Saying "the agent is exactly as it was"
    would be a claim about `NOT_PUT_BACK` as well, and that is not what happened: the logs of the
    failure are deliberately still there, which is the whole point of leaving them out.
    """
    stuck = _put_back(within, aside)
    if stuck:
        return (f"{name} could not be carried to {step.id}: {why} — and worse, it could "
                f"not be put back as it was: {', '.join(stuck)}")
    _let_go(aside)
    # Every one of `NOT_PUT_BACK` is named rather than the first of them. This sentence is the
    # caller's whole account of what happened, and one that named `logs/` alone would be a claim
    # that everything else went back — including the directory holding what a firing wrote.
    return (f"{name} could not be carried to {step.id}: {why} — its records and its files were "
            f"put back as they were, apart from {', '.join(f'{one}/' for one in NOT_PUT_BACK)}")


def _aside(within: Path) -> Path:
    """Where this agent's things are kept while it is being carried.

    Asked through `utils.files` rather than by formatting the staging name here, which is exactly
    the duplication that module's own docstring warns about.
    """
    return files.outgoing_of(within / ASIDE)


def _set_aside(within: Path) -> Optional[Path]:
    """Copy this agent aside, apart from `NOT_PUT_BACK`, and say where the copy stands.

    **The directory, not only the records**, and that is the whole of the fix this replaced. A step
    is handed a connection *and* the agent's directory so it can change tables and files together,
    so a rollback that reached only `state.db` put the tables back and left the files — after which
    the records and the directory disagree about what has happened, and a later step that checks a
    file before acting on it is answered by one nothing recorded.

    **Inside the agent's own directory**, so one agent's rollback has nowhere to meet another's, and
    under `utils.files`' staging convention, which is what a walk already knows to skip — including
    the walk below, so the copy can never end up copying itself.

    Nothing is made if there is no directory to copy. Creating one here would mean that carrying an
    agent nobody has ever made *makes* one, out of a typo.
    """
    if not within.is_dir():
        return None
    aside = _aside(within)
    files.discard(aside)
    aside.mkdir(parents=True)
    for one in sorted(within.iterdir()):
        if one.name in NOT_PUT_BACK or files.staged(one.name):
            continue
        _copied(one, aside / one.name)
    return aside


def _put_back(within: Path, aside: Optional[Path]) -> List[str]:
    """Put everything back as it was, and say what could not be. Every one is tried, never the first only.

    **What was not set aside is taken away rather than left**, which is as true of a file a step
    wrote as it is of a write-ahead log: a log written by the attempt that just failed, standing
    beside a database that has been put back, is read by the next connection as that database's most
    recent truth. The old build recorded exactly that.

    Nothing was set aside when there was no directory to copy, and then there is nothing to put
    back either.
    """
    if aside is None:
        return []
    stuck = []
    try:
        # A step is arbitrary code and may have taken the agent's own directory away with it. There
        # is something to put back, so somewhere to put it is made again rather than the rollback
        # giving up — and never when nothing was set aside, which is what keeps carrying an agent
        # nobody has ever made from making one.
        within.mkdir(parents=True, exist_ok=True)
    except OSError as why:
        return [f"{within.name} ({why})"]
    for name in _in_the_order_they_go_back(within, aside):
        try:
            _back(aside / name, within / name)
        except OSError as why:
            stuck.append(f"{name} ({why})")
    return stuck


def _in_the_order_they_go_back(within: Path, aside: Path) -> List[str]:
    """Everything to put back or take away, in the order an interruption can survive.

    **The records go back before anything else, and their sidecars go back before them.** Each
    replacement is atomic on its own and they are not atomic together, so the order decides what an
    interruption between two of them leaves.

    Sidecars first, because a restored write-ahead log beside a database that has not been put back
    yet is read by the next connection as that database's most recent truth.

    Then `state.db`, and **that single rename is the moment this agent's history flips.** Before it,
    nothing about what this agent has run has changed and every copy is still on disk, so the whole
    restore can simply be run again. After it, the records say the carried steps never ran — so any
    file below that has not been put back yet belongs to a step the records no longer claim, and the
    next carry runs that step again. Every step is required to be safe to run against an agent that
    does not need it, which is what makes that resolve to the pre-carry state rather than stick
    between the two. The other order — records last — leaves the opposite and unrecoverable shape:
    records saying a step ran, standing over files that have been taken back out from under it, and
    a next carry that skips the very step that would have rebuilt them.
    """
    first = [one.name for one in reversed(records.beside(Path(directory.RECORDS)))]
    rest = {one.name for one in _entries(aside)}
    rest.update(one.name for one in _entries(within)
                if one.name not in NOT_PUT_BACK and not files.staged(one.name))
    return first + sorted(one for one in rest if one not in first)


def _entries(where: Path) -> List[Path]:
    """What is standing in `where`, and nothing at all when it is not there.

    A rollback runs after something has already gone wrong, and what went wrong is arbitrary code:
    the directory it is reading may have been taken away by the very step that failed. That is a
    rollback with work to do rather than a reason to raise out of a function whose whole contract
    is to hand back a sentence.
    """
    try:
        return list(where.iterdir())
    except OSError:
        return []


def _back(copy: Path, one: Path) -> None:
    """Put one thing back as it was, or take it away when it was not there before."""
    if copy.exists() or copy.is_symlink():
        _replaced(copy, one)
    elif one.exists() or one.is_symlink():
        files.remove_one(one)


def _copied(one: Path, to: Path) -> None:
    """Copy one thing, whatever kind of thing it is.

    **A symlink is copied as a link and never followed.** An agent's `home` replaced by a link to
    somebody's documents would otherwise have the documents copied into the rollback — and then
    written back over the link, which is the shape `directory.where` exists to refuse on the way in.
    """
    if one.is_symlink():
        os.symlink(os.readlink(str(one)), str(to))
    elif one.is_dir():
        shutil.copytree(str(one), str(to), symlinks=True)
    else:
        shutil.copy2(str(one), str(to))


def _replaced(copy: Path, one: Path) -> None:
    """Put one thing back where it was, without it ever being half there.

    **`shutil.copy2` onto the live file would truncate it before writing a byte of the restore.**
    That is the failure `utils.files` exists to prevent, and this is the worst possible place to
    reintroduce it: a rollback runs *after* something has already gone wrong, so the machine is
    already the kind of machine that dies partway. An interruption there would leave the agent's
    records neither carried nor put back, but truncated — which is not a state anything can recover
    from, and it is the one the caller has just promised cannot happen.

    So the copy is staged beside its destination under a name the walks already skip, and renamed
    into place. `os.replace` is atomic within a filesystem, and both of these are inside the agent's
    own directory, so it always is one.

    A directory is the one thing that cannot be a single rename: `os.replace` refuses one that has
    anything in it, so the live directory is taken away first. The staged copy is finished before
    that happens and the copy it came from is still there, so the way back is on disk twice over
    while the gap is open. The records are a file and never take that branch — their rename, which
    is the moment history flips, stays atomic.
    """
    staged = files.incoming_of(one)
    files.discard(staged)
    _copied(copy, staged)
    if one.is_dir() and not one.is_symlink():
        files.remove_one(one)
    os.replace(staged, one)


def _let_go(aside: Optional[Path]) -> None:
    """Let go of the copy, now that the move it insured has been made."""
    if aside is not None:
        files.discard(aside)


def _now() -> str:
    """The moment a step landed, in the same shape the install records its own moments in.

    The same shape because it is the same constant, `core.config.MOMENT`, rather than the same
    literal typed twice — which is what this said before, in a sentence nothing enforced.
    """
    return datetime.now(timezone.utc).strftime(config.MOMENT)
