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
import importlib.util
import os
import re
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

STEPS = Path(__file__).resolve().parent / "migrations"


class Failed(Exception):
    """A step did not finish. The data is as it was, and every agent stays down."""

    def __init__(self, step, reached: int, why: BaseException):
        super().__init__(
            f"migration {step} did not finish — the data is still at version {reached}, "
            f"and nothing has been started: {why}"
        )
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


def carry(database, home, want: int, where=None, note=None) -> int:
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
        for step in between(reached, want, where):
            say(f"migrating {database.parent.name} to version {step.version}")
            spent = _one(conn, step, Path(home))
            reached = step.version
            # Only now that the version has moved: what a step copied is safe to let go of,
            # and a crash before this point leaves both copies rather than neither.
            for gone in spent:
                with contextlib.suppress(OSError):
                    os.remove(gone)
        return reached
    finally:
        conn.close()


def _one(conn, step: Step, home: Path) -> list:
    """One step, whole or not at all."""
    conn.execute("BEGIN IMMEDIATE")
    try:
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
