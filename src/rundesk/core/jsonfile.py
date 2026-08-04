"""Reading and writing a small JSON file safely.

Three functions: `read` one, `write` one, and `changing` one — which holds the read, the decision and
the write together so nothing else can get in between.

Everything rundesk keeps outside a database goes through here. Two guarantees, and both matter more
than they look:

**A value is renamed into place, never written in pieces.** A reader opening the file mid-write would
otherwise see half of one — and half a JSON document is not a smaller record, it is an unreadable
one. `os.replace` is atomic on the same filesystem, so a reader sees the old value or the new one.

**What cannot be read is not empty.** A file nobody has written and a file that will not parse are
different answers, and collapsing them is how state is lost: the second one gets an empty value back,
something writes that empty value down, and what was there is gone. So `read` says which it was, and
`changing` refuses to proceed on the second rather than handing you a blank slate to overwrite it
with.

Imports nothing of rundesk's, so it can be used from anywhere including part-way through replacing
every other module.
"""

import contextlib
import errno
import fcntl
import json
import os
from pathlib import Path
from typing import Any, Iterator, Tuple

#: Nobody has written this file.
MISSING = "missing"

#: The file is there and could not be understood. Never treated as empty.
UNREADABLE = "unreadable"

#: The file is there and was read.
READ = "read"


class Stuck(Exception):
    """The lock is held by something else and did not come free."""


def read(where: Path) -> Tuple[str, Any]:
    """Read a JSON value, saying which of the three answers this was.

    Returns `(MISSING, None)`, `(UNREADABLE, None)` or `(READ, value)`. Callers that treat the first
    two the same are usually about to lose something.
    """
    try:
        with open(where, "r", encoding="utf-8") as reading:
            return READ, json.load(reading)
    except FileNotFoundError:
        return MISSING, None
    except (OSError, ValueError):
        return UNREADABLE, None


def write(where: Path, value: Any) -> None:
    """Write a JSON value whole, and rename it into place.

    The temporary file is made beside the target rather than in a temp directory, because
    `os.replace` is only atomic within one filesystem.
    """
    where.parent.mkdir(parents=True, exist_ok=True)
    beside = where.with_name(f".{where.name}.incoming")
    with open(beside, "w", encoding="utf-8") as writing:
        json.dump(value, writing, indent=2, sort_keys=True)
        writing.write("\n")
        writing.flush()
        os.fsync(writing.fileno())
    os.replace(beside, where)
    _settle(where.parent)


@contextlib.contextmanager
def changing(where: Path, empty: Any) -> Iterator[list]:
    """Hold the read, the decision and the write under one lock.

    Yields a one-item list holding the current value; replace `held[0]` and it is written on the way
    out. A missing file yields `empty`; an unreadable one raises, because the whole point of this is
    that nothing overwrites a value it could not read.

    Two processes changing the same file is not hypothetical here: an update and a command a person
    typed can reach one at the same moment.
    """
    where.parent.mkdir(parents=True, exist_ok=True)
    with _only_one(where):
        how, value = read(where)
        if how == UNREADABLE:
            raise ValueError(f"{where} is there and cannot be read — refusing to write over it")
        held = [empty if how == MISSING else value]
        yield held
        write(where, held[0])


@contextlib.contextmanager
def _only_one(where: Path) -> Iterator[None]:
    """Hold an exclusive lock for the length of the block.

    The lock is its own file rather than the value's, so taking it never truncates or creates the
    thing being protected — and the kernel drops it when the process dies, however it dies.
    """
    at = where.with_name(f".{where.name}.lock")
    holding = os.open(at, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(holding, fcntl.LOCK_EX)
        except OSError as why:
            if why.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise Stuck(f"something else is changing {where}")
            raise
        yield
    finally:
        os.close(holding)


def _settle(directory: Path) -> None:
    """Ask the filesystem to record the rename itself, not only the bytes it moved.

    Without this the file's contents are durable and the directory entry pointing at them may not be,
    which after a hard stop leaves the new value written and invisible.
    """
    try:
        held = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(held)
    except OSError:
        pass
    finally:
        os.close(held)
