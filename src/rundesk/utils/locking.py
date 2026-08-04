"""Letting one process at a time change something, with a ceiling on the waiting.

Two processes reaching the same thing at once is not hypothetical for a program a person types and
a schedule also runs: an update and a command, a nightly copy and a manual one. What they need is
not to be clever about merging — it is to take turns.

**Asked for without blocking, in a loop with an end.** A plain `flock(LOCK_EX)` waits with no
ceiling and names nothing while it waits, so the command somebody typed simply never returns. A
wait that outlasts the ceiling here is not a busy machine, it is something that has gone wrong, and
the answer is to say so.

**The lock is its own file, never the thing being protected.** Taking it therefore cannot truncate
or create what it guards, and the kernel drops it when the process dies, however it dies — no stale
lock survives a crash.

**Re-entrant within one thread, and it has to be.** `flock` is held per open file description, so
a second `open` of the same lock file in the *same* process conflicts with the first exactly as
another process would — which is how a test can drive `Stuck` at all. That also means an operation
holding this lock and calling another operation that takes it would wait for itself until the
ceiling and then fail. Nesting is counted rather than re-locked, so the outermost holder owns it and
the inner ones pass straight through.

Knows nothing about rundesk.
"""

import contextlib
import errno
import fcntl
import os
import threading
import time
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple

#: How long to wait for something else to finish before saying so. Read at the moment of asking
#: rather than bound in a signature, so a test can shorten the ceiling and drive this in
#: milliseconds.
WAITING_SECONDS = 10.0

#: How often the wait looks again. Short enough that an ordinary hold is never noticed.
LOOKING_AGAIN = 0.02

#: How deep each *thread* is inside each lock it holds. See the module docstring on re-entrancy.
#:
#: Keyed by thread as well as by file, and that is the whole correctness of it. Keyed by file alone,
#: a second thread asking for a lock the first one holds would find a count already there, take the
#: fast path, and never touch `flock` — two callers inside a section that exists to hold one. Nesting
#: is about a call stack, and a call stack belongs to a thread.
#:
#: Keyed by the *resolved* path, because two spellings of one file are one file. A symlinked root
#: reaching the same lock by another name would miss its own count, take a real `flock` on a
#: descriptor this thread already holds, and wait out the whole ceiling for itself.
_HELD: Dict[Tuple[int, str], int] = {}


class Stuck(Exception):
    """The lock is held by something else and did not come free."""


@contextlib.contextmanager
def only_one(at: Path, guarding: Optional[str] = None) -> Iterator[None]:
    """Hold an exclusive lock on the file `at` for the length of the block.

    `guarding` is what the lock is protecting, in the words of whoever took it, so the message when
    it cannot be had names the thing a person cares about rather than a dotfile they have never
    seen.
    """
    key = (threading.get_ident(), os.path.realpath(str(at)))
    if _HELD.get(key):
        _HELD[key] += 1
        try:
            yield
        finally:
            _HELD[key] -= 1
        return

    at.parent.mkdir(parents=True, exist_ok=True)
    holding = os.open(at, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        _taken(holding, guarding or str(at))
        _HELD[key] = 1
        try:
            yield
        finally:
            _HELD.pop(key, None)
    finally:
        os.close(holding)


def _taken(holding: int, guarding: str) -> None:
    """Take the lock, looking again until the ceiling. `Stuck` when it never came free."""
    ceiling = time.monotonic() + WAITING_SECONDS
    while True:
        try:
            fcntl.flock(holding, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as why:
            if why.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise
            if time.monotonic() >= ceiling:
                raise Stuck(
                    f"something else has been changing {guarding} for longer than "
                    f"{WAITING_SECONDS:g} seconds, and this one gave up rather than wait for ever"
                ) from why
            time.sleep(LOOKING_AGAIN)
