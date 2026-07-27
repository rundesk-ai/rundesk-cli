"""Bringing what is already on a machine into the shape a newer rundesk expects.

A step forward exists and a step back does not. Going backwards is refusing to go forwards:
data a copy of rundesk does not understand keeps it down and says why, rather than being read
hopefully by code that cannot know what it is missing.

**A step is found, not listed.** Each is a file named for the version it brings data up to, so
what runs is whatever sits between the version on disk and the version installed. A list kept
beside the directory is a list that disagrees with it.

**There is no record of what has run, because the version *is* the record.** SQLite keeps DDL
inside a transaction, so a step's schema change, its data change and its version stamp commit
together — "ran but not recorded" is not a state that can exist. The tools that keep a
migrations table do so because their engine cannot promise that, and because they support
going back. Neither applies here.

**What a step may not do is delete.** Moving a file is not part of any transaction, so a step
copies and the runner removes the original only once the new version has committed. A step
that died halfway therefore leaves the old files where they were and the version unmoved, and
running it again is safe.
"""

from __future__ import annotations

import contextlib
import datetime
import importlib.util
import os
import re
import shutil
import sqlite3
from pathlib import Path

# `001.py`, `002.py`, `010.py` — the number is the version, and sorting the numbers is the
# whole of the ordering. Nothing else is in the name, so there is one obvious way to add a step
# and no second place for the order to be written down.
NAMED = re.compile(r"^(\d+)\.py$")

# A version is kept in the database header as a signed 32-bit integer. Going past this does not
# raise — it **wraps to zero**, which here is the value that means "written partway and cannot
# be read", so the failure would be silent and total. A plain sequence never comes near it; a
# date with a time on it would, which is one reason the name is a sequence. Rails and Django
# keep a table of applied versions precisely because their timestamps have nowhere else to live.
CEILING = 2147483647

STEPS = Path(__file__).resolve().parent.parent / "migrations"

#: What an agent's records are called. Here rather than in `store.py`, which is where a
#: reader would look for it, because the runner has to find one *without* the store — it is
#: the thing the store is built by, so `store` imports this and not the other way round.
#: Spelled out in both, `carry_every` would go on looking for the old name after the new one
#: shipped, walk every agent, find nothing, and report an update in which nothing moved.
RECORDS = "state.db"


class Failed(Exception):
    """A step did not finish. The data is as it was, and every agent stays down.

    Whose records these are is part of the answer, not context somebody looks up: an update
    walks every agent, so "a migration failed" without a name leaves an owner opening each
    of them in turn to find out which. `reached` is `None` where the version could not be
    read at all, which is not the same fact as reaching zero.
    """

    def __init__(self, step, reached, why: BaseException, agent=None):
        whose = f"{agent}: " if agent else ""
        got = (f"the data is still at version {reached}" if reached is not None
               else "the version on disk could not be read")
        super().__init__(
            f"{whose}migration {step} did not finish — {got}, "
            f"and nothing has been started: {why}"
        )
        self.agent = agent
        self.step = step
        self.reached = reached
        self.why = why


class Step:
    """One move forward: the version it brings data up to, and where it is written."""

    def __init__(self, version: int, at: Path):
        self.version = version
        self.at = at

    def __repr__(self) -> str:
        return self.at.name

    def loaded(self):
        """The module, read only when it is about to run.

        Importing every step to decide which ones apply would make an unrelated step's
        mistake break an update that was never going to run it.
        """
        spec = importlib.util.spec_from_file_location(f"_migration_{self.version}", self.at)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "up"):
            raise AttributeError(f"{self.at.name} has no `up` to run")
        return module


def found(where=None) -> list:
    """Every step there is, in the order they must run.

    Sorted by the number rather than by the name, so `010` follows `009` rather than `001`.
    """
    where = STEPS if where is None else Path(where)
    if not where.is_dir():
        return []
    steps = []
    for at in where.iterdir():
        said = NAMED.match(at.name)
        if not said:
            continue
        version = int(said.group(1))
        if not 1 <= version <= CEILING:
            raise ValueError(
                f"{at.name} cannot be a version: one runs from 1 to {CEILING}, and a number "
                "past that wraps to zero rather than failing, leaving records that claim to "
                "have no version at all"
            )
        steps.append(Step(version, at))
    steps.sort(key=lambda step: step.version)
    numbered = [step.version for step in steps]
    duplicated = sorted({one for one in numbered if numbered.count(one) > 1})
    if duplicated:
        raise ValueError(f"two steps claim the same version: {duplicated}")
    return steps


def between(at_version: int, want: int, where=None) -> list:
    """What has to run to get from the shape on disk to the shape installed."""
    return [step for step in found(where) if at_version < step.version <= want]


# Written the way a gateway writes its own line, so an owner reading one log reads one story.
WRITTEN_AS = "%(at)s %(level)-7s %(said)s"
LOG = "logs/gateway.log"


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def logged(home, said: str, level: str = "INFO", clock=None) -> None:
    """Leave a line in the agent's own log, where somebody will actually look for it.

    An update that failed at three in the morning is read afterwards, not watched. A migration
    that reported only to whoever ran it would leave nothing behind for the person who finds
    the agent down — and this is the one moment where what happened to an agent's records is
    not yet in those records.
    """
    at = Path(home) / LOG
    said = WRITTEN_AS % {"at": (clock or _now)(), "level": level, "said": said}
    try:
        at.parent.mkdir(parents=True, exist_ok=True)
        with open(at, "a", encoding="utf-8") as writing:
            writing.write(said + "\n")
    except OSError:
        # A log that cannot be written must not be the thing that stops an update. What is
        # happening is still reported to the caller, which is what decides.
        pass


def carry(database, home, want: int, where=None, note=None, clock=None) -> int:
    """Bring one agent's records up to date, and say what version they reached.

    Each step is one transaction that includes its own version stamp, so an update stopped
    partway leaves every step either wholly done or wholly not — and running again begins at
    the first one that has not.
    """
    say = note if note is not None else (lambda said: None)
    database = Path(database)
    conn = sqlite3.connect(str(database), timeout=30.0, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        reached = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if reached > want:
            raise Failed(
                f"(none)", reached,
                ValueError(f"this data is version {reached} and this rundesk expects {want}"),
            )
        due = between(reached, want, where)
        if due:
            logged(home, f"moving records from version {reached} to {want}: "
                         + ", ".join(repr(one) for one in due), clock=clock)
        for step in due:
            say(f"migrating {database.parent.name} to version {step.version}")
            try:
                spent = _one(conn, step, Path(home))
            except Failed as stopped:
                logged(home, f"{step} did not finish — records are still at version "
                             f"{stopped.reached}: {stopped.why}", "ERROR", clock=clock)
                raise
            reached = step.version
            logged(home, f"{step} finished — records are at version {reached}", clock=clock)
            # Only now that the version has moved: what a step copied is safe to let go of,
            # and a crash before this point leaves both copies rather than neither.
            for gone in spent:
                with contextlib.suppress(OSError):
                    os.remove(gone)
        return reached
    finally:
        conn.close()


def carry_every(agents, want: int, where=None, note=None, clock=None) -> dict:
    """Walk every agent and bring each forward on its own, in the order they are named.

    One database per agent means one migration per agent: each is opened alone, moved from
    wherever *it* actually is, and closed before the next is touched. Two agents are never at
    the same version — one was made last week and one this morning — so there is no single
    "the data" to move.

    **The first agent that cannot be moved stops the walk**, because bringing the rest back up
    onto data half-moved is worse than leaving them down and saying so. What had already been
    carried stays carried: each was whole before the next was opened.
    """
    say = note if note is not None else (lambda said: None)
    reached = {}
    for home in sorted(Path(agents).iterdir()):
        if not home.is_dir():
            continue
        if not _an_agent(home):
            continue
        # Made where it is not there, rather than skipped. An agent from a release before
        # there were records has none, and passing over it would leave an update reporting
        # success having moved nothing — and every one of those agents unable to start.
        database = home / RECORDS
        try:
            reached[home.name] = carry(database, home, want, where=where, note=say, clock=clock)
        except Failed as stopped:
            say(f"{home.name} could not be moved: {stopped}")
            raise Failed(stopped.step, stopped.reached, stopped.why,
                         agent=home.name) from stopped
        except Exception as trouble:   # noqa: BLE001 — see below
            # Records that cannot be opened at all never reach a step, so nothing above
            # would name the agent or leave a line in its log — and an owner would be told
            # only that a database somewhere was unreadable. Caught broadly because what
            # went wrong matters far less than which agent it went wrong for.
            logged(home, f"these records could not be opened at all: {trouble}",
                   "ERROR", clock=clock)
            say(f"{home.name} could not be moved: {trouble}")
            raise Failed("(opening)", None, trouble, agent=home.name) from trouble
    return reached


#: Where an update keeps what it may have to put back. Beside the agents rather than inside
#: the program, for two reasons: a copy of an owner's records is the owner's, so an ordinary
#: uninstall keeps it — and **whatever redirects where agents live redirects this with it**.
#: Pointed at the program instead, a suite driving an update wrote a real copy of a fake
#: agent's records into the developer's own checkout, which is the trap `MEMORY.md` already
#: records one level down. A second thing to redirect is a second thing to forget.
ROLLBACK = ".update.rollback"


def what_would_run(agents, want: int, where=None) -> dict:
    """Which steps each agent would take, without taking any of them (R-MIG-21).

    Answers the question an owner asks before an update rather than after it, and answers it
    for every agent at once — two are never at the same version, so "what will this do" has
    as many answers as there are agents.

    **Opens nothing that is not already there.** `carry` reaches its database through
    `sqlite3.connect`, which *makes* one where there is none — so asking what would happen
    by way of the thing that does it would leave records behind on every agent that has none
    yet, which is precisely the state a preview must not create. The connection is read-only
    and the file is looked for first.
    """
    standing = {}
    if not Path(agents).is_dir():
        return standing
    for home in sorted(Path(agents).iterdir()):
        if home.name == ROLLBACK or not home.is_dir() or not _an_agent(home):
            continue
        standing[home.name] = between(version_on_disk(home / RECORDS), want, where)
    return standing


def version_on_disk(records: Path) -> int:
    """What version these records say they are, or zero where there are none yet.

    Zero rather than an error: an agent from a release before there were records has none,
    and every step there is would run against it — which is what making one already does.
    """
    if not records.exists():
        return 0
    try:
        conn = sqlite3.connect(f"file:{records}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error:
        return 0
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error:
        # Unreadable is not the same as behind, and a preview is not the place to decide
        # which — `carry` says so properly, with the agent named, when it is asked to run.
        return 0
    finally:
        conn.close()


def carry_every_or_put_back(agents, want: int, aside: Path | None = None, where=None,
                            note=None, clock=None) -> str | None:
    """Move every agent forward, or leave every one of them exactly as it was.

    Says what went wrong rather than raising it, because the caller is a decision about an
    update and not a place to handle a database error.

    **A step forward exists and a step back does not**, which is the whole shape of
    migration here — so the way back is not a reverse step but a copy taken before anything
    ran (R-MIG-19). Two agents are never at the same version, so the first that cannot be
    moved stops the walk with earlier ones already carried; without this they would stay
    carried while the release went back underneath them, and an agent's records would be
    newer than the only code left to read them.

    The copy goes somewhere the program owns rather than beside the records it copies: an
    agent's own directory holds three files and nothing else, and a fourth appearing in it
    would be a surprise to everything that looks there.
    """
    say = note if note is not None else (lambda said: None)
    agents = Path(agents)
    kept = _set_aside(agents, agents / ROLLBACK if aside is None else Path(aside))
    try:
        carry_every(agents, want, where=where, note=say, clock=clock)
    except Exception as stopped:   # noqa: BLE001 — a boundary, reporting truthfully
        stuck = _put_records_back(kept)
        if stuck:
            return (f"{stopped}. What is worse, these could not be put back as they were: "
                    f"{', '.join(stuck)}")
        return str(stopped)
    _let_records_go(kept)
    return None


def _set_aside(agents: Path, aside: Path) -> list:
    """A copy of every agent's records, taken while nothing an owner runs is up.

    Nothing is reading them at this moment, which is the only reason a plain file copy is
    honest here: an open connection would have a write-ahead log beside it that the copy
    would not include, and the copy would be a database missing its most recent truth.
    """
    kept = []
    if not agents.is_dir():
        return kept
    _clear(aside)
    for home in sorted(agents.iterdir()):
        if home == aside or not home.is_dir() or not _an_agent(home):
            continue
        records = home / RECORDS
        if not records.exists():
            continue          # nothing yet to put back; making one is what `carry` does
        copy = aside / home.name / RECORDS
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(records, copy)
        kept.append((records, copy))
    return kept


def _put_records_back(kept: list) -> list:
    """Put every copy back where it came from, and say which could not be.

    Every one is tried rather than the walk ending at the first failure: a restore that gave
    up half way is the state this exists to prevent.
    """
    stuck = []
    for records, copy in kept:
        try:
            shutil.copy2(copy, records)
            # The write-ahead log and the shared-memory file belong to the records that were
            # *there*, not to the ones being put back, and a stale one beside a restored
            # database is read as its most recent truth.
            for beside in (records.with_name(records.name + "-wal"),
                           records.with_name(records.name + "-shm")):
                with contextlib.suppress(OSError):
                    if beside.exists():
                        os.remove(beside)
        except OSError:   # noqa: BLE001 — named and reported, never swallowed
            stuck.append(records.parent.name)
    return sorted(stuck)


def _let_records_go(kept: list) -> None:
    """Let go of the copies, now that the move they insured is proved (R-MIG-20)."""
    for _records, copy in kept:
        _clear(copy.parent)


def _clear(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)


#: What tells an agent's directory from anything else that happens to stand where agents
#: are kept. Any one of the three is enough: its records, the home it loads from, or what a
#: release before there were records wrote about it. Asked here rather than "has records",
#: because the agents that most need moving forward are exactly the ones that have none yet.
OF_AN_AGENT = (RECORDS, "home", "agent.json")


def _an_agent(home: Path) -> bool:
    return any((home / one).exists() for one in OF_AN_AGENT)


def _one(conn, step: Step, home: Path) -> list:
    """One step, whole or not at all.

    The version is read again **inside** the hold, not only before it. Two processes that both
    found the same version before either took the lock would otherwise both run the step: the
    first succeeds, and the second finds the work already done and reports a failure for a
    database that is perfectly healthy. The read, the decision and the write belong under one
    lock, which is the rule this file exists to obey rather than to demonstrate breaking.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        if int(conn.execute("PRAGMA user_version").fetchone()[0]) >= step.version:
            conn.execute("COMMIT")
            return []
        module = step.loaded()
        # A step may copy files. It may never delete one — what it hands back is removed
        # after the version has committed, which is what makes running again safe.
        spent = module.up(conn, home) or []
        conn.execute(f"PRAGMA user_version = {int(step.version)}")
    except BaseException as trouble:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ROLLBACK")
        reached = int(conn.execute("PRAGMA user_version").fetchone()[0])
        raise Failed(repr(step), reached, trouble)
    conn.execute("COMMIT")
    return [Path(one) for one in spent]
