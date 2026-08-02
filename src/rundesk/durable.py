"""A small file written whole, and changed under a lock nobody else holds.

The primitive everything durable in rundesk is built on. A value is written to a temporary
name beside its target and renamed into place, so a reader never sees half of one; and
`changing()` holds the read, the decision and the write under one `flock`, so two processes
deciding at once cannot lose one another's change.

**What cannot be read is not empty.** A missing file and an unreadable one are different
answers, and writing an empty value back over the second is how state is silently lost —
which is why `Unreadable` is raised rather than swallowed.

Imports nothing of rundesk's: this is the bottom of the stack, and every gateway, agent and
command path above it eventually writes through here.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path


#: What a read found. `MISSING` and `UNREADABLE` are different answers on purpose: one is
#: a file nobody has written, the other is a file that cannot be trusted, and writing an
#: empty value back over the second is how state is lost.
MISSING = "missing"
UNREADABLE = "unreadable"
WRITTEN = "written"


class Unreadable(Exception):
    """A file that is there and could not be read or understood (R-SCH-17)."""


@contextlib.contextmanager
def changing(target: Path, empty, what: str, durable: bool = False):
    """Read this file, change it, and write it back — alone, and whole.

    The one place a file rundesk keeps is read, decided on and written under a single
    hold. Writing whole is not the same as changing alone: two writers that each read the
    same contents and each write theirs back leave one change gone, with both having
    reported success (R-GW-27). The lock is the one the kernel drops however the process
    holding it ends, so a writer that dies mid-change blocks nothing.

    `durable` also asks the machine to put it on the disk before this returns. Renaming
    into place is enough against a reader arriving mid-write and against a process that
    dies. It is not enough against power loss, which is exactly the moment a run that
    already happened must not come back looking as though it never did (R-SCH-20). Not
    paid on what a gateway rewrites every few seconds — only on what records what has
    already happened.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    guard = os.open(target.with_suffix(".changing"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(guard, fcntl.LOCK_EX)
        # Read inside the hold, and refused before anything is yielded: a file that could
        # not be parsed still holds everything in it as recoverable text (R-SCH-17).
        keeping = _understood(target, empty, what)
        before = json.dumps(keeping, indent=2)
        yield keeping
        after = json.dumps(keeping, indent=2)
        # A writer that decided to change nothing writes nothing (R-SCH-19). Rewriting an
        # unchanged file puts all of it at the mercy of a failure nobody asked to risk.
        if after != before:
            written_whole(target, after + "\n", durable)
    finally:
        fcntl.flock(guard, fcntl.LOCK_UN)
        os.close(guard)


def _understood(target: Path, empty, what: str):
    """What is written there, refusing a file that is there and cannot be read.

    The one place that tells "never written" from "written and unreadable" (R-SCH-17).
    `empty` is what a file nobody has written yet means, and its type is what this file is
    supposed to be — an interruption file holding a list is as unreadable as one holding a
    stray character, and replacing either with nothing loses the same thing.
    """
    state, said = read(target)
    if state == MISSING:
        return empty  # never written, which is the ordinary case for a new gateway
    if state == UNREADABLE or not isinstance(said, type(empty)):
        raise Unreadable(f"{target} could not be read as {what}")
    return said


def written_whole(target: Path, text: str, durable: bool = False) -> None:
    """Put this where it belongs, whole, in one move.

    Beside and then renamed: a reader arriving mid-write would otherwise find half a
    file, and half a record reads as a gateway that cannot say what version it is, while
    half a schedules file reads as a gateway with no schedules at all.

    `durable` waits for the machine to say it is really there before returning (R-SCH-20).
    Both halves are needed and neither implies the other: the contents have to reach the
    disk, and so does the directory entry naming them, or the rename is the thing that is
    lost. Not asked for on what is rewritten every few seconds — the cost is real, and a
    beat that is a moment out of date costs nothing.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    beside = target.with_suffix(f".{os.getpid()}.writing")
    if not durable:
        beside.write_text(text)
        os.replace(beside, target)
        return
    with open(beside, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(beside, target)
    folder = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def read(path: Path) -> tuple[str, object]:
    """What is written there, and which of three things happened when we looked.

    The one place that decides what an unreadable file means. Four readers each worked it
    out for themselves, and they disagreed: one reported a broken record as an empty one,
    one wrote an empty list over a file it could not parse, and one read "I could not tell"
    as "there is nothing left running" and deleted the record naming it.
    """
    try:
        text = path.read_text()
    except FileNotFoundError:
        return MISSING, None
    except OSError:
        # There, and the machine would not hand it over — a stalled volume, a permission,
        # a descriptor limit. Nothing about its contents is known, least of all that it
        # is empty.
        return UNREADABLE, None
    try:
        return WRITTEN, json.loads(text)
    except ValueError:
        return UNREADABLE, None


def read_json(path: Path, missing):
    """What is written there, or `missing` if there is nothing readable to read.

    For readers that report rather than decide: to them, a file that is not there and one
    they could not read are the same nothing. Anything about to *write* asks `read`
    instead, because to a writer they are opposites.
    """
    state, said = read(path)
    return said if state == WRITTEN else missing
