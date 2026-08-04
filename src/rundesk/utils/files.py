"""Putting bytes on disk without ever leaving a reader something half-written.

Three things, and they are one concern: how a small file is kept, how anything on disk is replaced,
and whether a name may become a path at all. They live together because they fail together — a name
with a separator in it lands the file somewhere else, and a replacement that is not staged lands it
half-written.

## A value is renamed into place, never written in pieces

A reader opening a file mid-write sees half of one, and half a JSON document is not a smaller record
— it is an unreadable one. `os.replace` is atomic within a filesystem, so a reader sees the old value
or the new one and nothing between. That is also why staging happens *beside* the target rather than
in a temporary directory: across filesystems a rename is a copy, and a copy is what this avoids.

## What cannot be read is not empty

A file nobody has written and a file that will not parse are different answers, and collapsing them
is how state is lost: the second gets an empty value back, something writes that empty value down,
and what was there is gone. `read_json` says which it was; `changing_json` refuses to proceed on the
second rather than handing out a blank slate to overwrite it with.

## A half-written thing never wears a finished name

Everything that replaces something builds it under an `.incoming` name and renames it into place only
once all of it is there. The names are here rather than at each caller because a swap and the walk
that has to skip it must agree: two modules spelling the same convention are two modules that will
eventually spell it differently. A backup interrupted halfway and nevertheless called
`2026-08-04T03-00-00Z` is worse than no backup, because it is the one somebody reaches for.

## A name becomes a directory, a lock and a log

What a name may be and where the writing lands are the same decision. The build this replaces
recorded it exactly: *a name containing a separator would put all three somewhere else entirely.* A
name should be checked where it is accepted rather than at each of the places it later turns into a
path, because those are the places that cannot see what happened.

`name_trouble` is the check. **Nothing calls it yet** — there is no verb that takes a name — so this
is a rule the tree does not enforce anywhere today, and saying otherwise here would be this file
claiming a guarantee it does not make. It is written and proven now because the first verb that
takes a name is the one that would otherwise invent its own rules for one.

Beyond `locking`, which is how the read-decide-write is held together, this imports the standard
library and nothing else.
"""

import contextlib
import json
import os
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Tuple

from rundesk.utils import locking

#: Nobody has written this file.
MISSING = "missing"

#: The file is there and could not be understood. Never treated as empty.
UNREADABLE = "unreadable"

#: The file is there and was read.
READ = "read"


#: The same answer `locking` gives, named here as well because this is the module every caller
#: already imports — none of them should have to know which file the mechanism lives in.
Stuck = locking.Stuck


def _the_lock_for(where: Path) -> Path:
    """The lock file guarding one value, beside it and never it.

    Named through `staging`'s convention rather than spelled out again here: a leading dot to keep
    it out of an ordinary listing, and one place deciding what these files are called.
    """
    return where.with_name(f".{where.name}.lock")


def read_json(where: Path) -> Tuple[str, Any]:
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


def write_json(where: Path, value: Any) -> None:
    """Write a JSON value whole, and rename it into place.

    The temporary file is made beside the target rather than in a temp directory, because
    `os.replace` is only atomic within one filesystem.
    """
    where.parent.mkdir(parents=True, exist_ok=True)
    beside = where.with_name(INCOMING.format(name=where.name))
    # Cleared first, the way `stage_copy` does. A write that raised partway — an unserialisable
    # value, a full disk during `fsync` — leaves this file behind, and while the next write would
    # truncate it anyway, "the next write tidies it" is a thing to have decided rather than to have
    # happened to be true.
    discard(beside)
    with open(beside, "w", encoding="utf-8") as writing:
        json.dump(value, writing, indent=2, sort_keys=True)
        writing.write("\n")
        writing.flush()
        os.fsync(writing.fileno())
    os.replace(beside, where)
    _settle(where.parent)


@contextlib.contextmanager
def changing_json(where: Path, empty: Any) -> Iterator[list]:
    """Hold the read, the decision and the write under one lock.

    Yields a one-item list holding the current value; replace `held[0]` and it is written on the way
    out. A missing file yields `empty`; an unreadable one raises, because the whole point of this is
    that nothing overwrites a value it could not read.

    Two processes changing the same file is not hypothetical here: an update and a command a person
    typed can reach one at the same moment.

    **Take the install's own lock before this one, never after.** Some callers hold both — a restore
    swaps `data/` and then settles the configuration inside it — and two locks taken in two orders by
    two processes is the one deadlock this product can build for itself. The order is stated here
    because it is the invariant a caller cannot see from its own end.
    """
    where.parent.mkdir(parents=True, exist_ok=True)
    with locking.only_one(_the_lock_for(where), str(where)):
        how, value = read_json(where)
        if how == UNREADABLE:
            raise ValueError(f"{where} is there and cannot be read — refusing to write over it")
        held = [empty if how == MISSING else value]
        yield held
        write_json(where, held[0])


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


#: What a thing being built is called until all of it is there.
INCOMING = ".{name}.incoming"

#: What the thing being replaced is called while the swap is in flight, so it can be put back.
OUTGOING = ".{name}.outgoing"


def staged(name: str) -> bool:
    """Whether this is a name a swap is using rather than a finished thing.

    Asked by every walk over a directory something stages into, so a listing never offers half a
    copy and a move never carries one somewhere else.
    """
    return name.startswith(".") and name.endswith((".incoming", ".outgoing"))


def discard(where: Path) -> None:
    """Remove a staging entry, whatever kind it is.

    **Only ever used on a name the caller chose**, never on something an owner keeps — which is why
    it may be this forgiving about failing. A staging entry left behind is tidied by the next swap;
    raising here would turn a successful operation into a reported failure over litter.
    """
    if where.is_dir() and not where.is_symlink():
        shutil.rmtree(where, ignore_errors=True)
    elif where.exists() or where.is_symlink():
        try:
            where.unlink()
        except OSError:
            pass


def stage_copy(entry: Path, into: Path, ignore: Optional[Callable] = None) -> Path:
    """Copy `entry` into `into` under its staged name, and hand back where it landed.

    The caller decides when — or whether — to rename the result into place, because that is the part
    that genuinely differs: one caller stages every entry and swaps them together, another renames
    each as it lands. What is identical is this, and it has one subtlety worth having in one place.

    **A symlink is copied as a symlink, never followed.** `is_dir()` answers `True` for a link
    pointing at a directory, so a copy that asked only that question would walk through the link and
    duplicate the tree on the other side of it — silently, and only for the owner who had one.
    """
    pending = into / INCOMING.format(name=entry.name)
    discard(pending)
    if entry.is_dir() and not entry.is_symlink():
        shutil.copytree(entry, pending, symlinks=True, ignore=ignore)
    else:
        shutil.copy2(entry, pending, follow_symlinks=False)
    return pending


#: The longest a single path segment may be on the filesystems this runs on, in bytes rather than
#: characters — one accented letter can be several bytes, and the limit counts bytes.
LONGEST = 255

_SEPARATORS = ("/", "\\", "\0")


def name_trouble(said: str) -> str:
    """Why `said` may not be one segment of a path, or `""` when it may.

    A sentence rather than a `False`, because every caller has to tell somebody what to type
    instead, and a caller left to invent that wording is a caller that invents a different one.
    There was a `usable_name` boolean beside this for a while and it was deleted unused: a caller
    that had it still had to ask again for the words, so it saved nobody anything.
    """
    if not said or not said.strip():
        return "a name cannot be empty"
    if said in (".", ".."):
        return f"{said!r} is a directory, not a name"
    for one in _SEPARATORS:
        if one in said:
            shown = "a null byte" if one == "\0" else repr(one)
            return f"a name cannot contain {shown} — it would put the directory somewhere else"
    if said.startswith("."):
        return "a name cannot start with a dot — those are kept for locks and half-written things"
    if any(unicodedata.category(one) in ("Cc", "Cf") for one in said):
        return "a name cannot contain a control character"
    if len(said.encode("utf-8")) > LONGEST:
        return f"a name cannot be longer than {LONGEST} bytes"
    return ""
