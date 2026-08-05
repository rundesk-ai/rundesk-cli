"""What arrives through a channel, what may leave through one, and when the first is swept.

Two directions with almost nothing in common, kept in one module because they are the two halves of
one question — which files may cross this seam — and splitting them would let the answers drift.

## Coming in

**The adapter downloads and rundesk decides where it lands.** The adapter holds the credential and
rundesk does not; rundesk owns the filesystem and the adapter does not. So the adapter reports what
it fetched and this writes it down.

Two rules, and the second is the one that bit the previous build:

**A name from a platform is a stranger's text.** Anything outside letters, digits and `-_.` goes, so
traversal is not something to defend against — a name with no separators in it cannot reach out of
the directory it is written into.

**Sanitising is not enough on its own.** `report v2.csv` and `report-v2.csv` both flatten to
`report-v2.csv`; the second overwrote the first, and the agent opened exactly the name it had been
given and read somebody else's file. So a name is made *unused* as well as safe.

## Going out, and the check people skip

Three, and the third is the point:

1. Whatever wants to send names an absolute path.
2. **This** contains it to a permitted root and opens every component with `O_NOFOLLOW`, reporting
   the size and digest of what it actually opened.
3. **The adapter re-opens it the same way and refuses on any mismatch.**

Without the third, a concurrent write can replace the approved file — or a directory above it —
between the check and the send. Steps one and two look complete on their own and are not.

The permitted roots are the agent's own `home/`, what its schedules wrote, and what has already
arrived through its channels. Not `state.db`, which is the agent's entire history; not the install's
secrets; not the program; not another agent's anything.

## Going away

Attachments are the one thing here that grows without a person deciding to keep it, so the day is in
the path and whole days are removed. **Age from the name, never from the filesystem** — the rule
`utils.logs.swept` already keeps, and for the same reason: a restore resets every modification time,
so age taken from the disk would silently sweep everything it had just brought back.

May depend on `agents`, `core` and `utils`.
"""

import hashlib
import os
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, NamedTuple, Optional

from rundesk.agents import directory
from rundesk.utils import logs

#: Where what arrived stands, inside the channel's own directory.
ARRIVED_IN = "in"

#: What a name may hold once a platform's version of it has been flattened. Everything else goes,
#: which is what makes traversal impossible rather than merely refused.
PLAIN = re.compile(r"[^A-Za-z0-9._-]+")

#: How much of a name is kept, from the end — an extension is worth more than the beginning of a
#: long sentence somebody used as a filename.
NAME_AT_MOST = 120

#: What one message may bring. A chat platform accepts far more than a turn can use, and an agent's
#: directory is not somewhere a stranger gets to fill.
PER_MESSAGE = 10
EACH_AT_MOST = 32 * 1024 * 1024

#: How many days of arrivals are kept. Long enough that something referred to last month is still
#: there, short enough that a channel somebody uses every day is not an install that grows for ever.
#: Not configurable, for the reason `gateways.host.KEPT_DAYS` gives about its own.
KEPT_DAYS = 60

#: How much is read at a time when a file is being weighed and digested.
BLOCK = 1024 * 1024


class Refused(Exception):
    """A file that may not cross this seam, named with why."""


class Sending(NamedTuple):
    """One file approved to leave, and everything the far side needs to prove it is still that file.

    `bytes` and `sha256` are not description — they are what the adapter checks its own re-open
    against, and without them the third check cannot happen at all.
    """

    name: str
    at: Path
    bytes: int
    sha256: str


def arrived_at(agent: str, kind: str, message: str,
               when: Optional[datetime] = None) -> Path:
    """Where the files from one message land: a day, then that message.

    The day is in the path so a sweep can remove whole days without reading anything, and so age
    comes from the name rather than from a modification time a restore would have reset.
    """
    day = (when or datetime.now()).strftime(logs.DAY)
    return directory.channels(agent) / kind / ARRIVED_IN / day / _plainly(str(message))


def written(into: Path, name: str, body: bytes) -> Path:
    """Write one arriving file under a name that is both safe and unused. Hands back where it went.

    `Refused` when it is bigger than one message may bring — checked here rather than trusted from
    what the platform said it would be, because what a platform declares and what it sends are two
    different facts.
    """
    if len(body) > EACH_AT_MOST:
        raise Refused(f"{name} is {len(body)} bytes, and one file may be {EACH_AT_MOST}")
    into.mkdir(parents=True, exist_ok=True)
    at = _somewhere_new(into, _plainly(name))
    at.write_bytes(body)
    return at


def approved(agent: str, said: str) -> Sending:
    """Weigh and digest a file something wants to send, refusing anything that reaches outside.

    **Every component is opened with `O_NOFOLLOW`**, so a link anywhere along the way is refused
    rather than followed. Checking only the final name is not enough: a link two directories up
    redirects the whole path, and `Path.resolve()` answers about the moment it was asked rather than
    about the descriptor anything later opens.

    What comes back is measured from the descriptor this opened, never from a second look at the
    path — so the size and digest describe one file rather than whatever stood at that name twice.
    """
    at = Path(said)
    if not at.is_absolute():
        raise Refused(f"{said} is not an absolute path, and only an absolute one can be checked")
    root = _the_root_holding(agent, at)
    if root is None:
        raise Refused(
            f"{said} is not somewhere {agent} may send from — that is its own home, what its "
            "schedules wrote, and what has arrived through its channels")

    held = _opened_without_following(root, at)
    try:
        size, digest = _weighed(held)
    finally:
        os.close(held)
    if size > EACH_AT_MOST:
        raise Refused(f"{at.name} is {size} bytes, and one file may be {EACH_AT_MOST}")
    return Sending(name=_plainly(at.name), at=at, bytes=size, sha256=digest)


def swept(agent: str, kind: str, keeping: int = KEPT_DAYS,
          today: Optional[date] = None) -> List[Path]:
    """Remove whole days of arrivals older than `keeping`. Hands back what went.

    **Age from the name.** A day this cannot read as a date is left alone entirely — deciding what a
    directory is by what it is called is only safe when anything unrecognised is somebody else's.

    Never raises: sweeping is tidying, and a gateway that ended because it could not remove an old
    directory would be the same class of mistake as one that ended because it could not write a log.
    """
    gone: List[Path] = []
    if keeping < 1:
        return gone
    oldest = (today or date.today()) - timedelta(days=keeping - 1)
    where = directory.channels(agent) / kind / ARRIVED_IN
    try:
        days = sorted(where.iterdir())
    except OSError:
        return gone
    for one in days:
        was = _the_day_of(one.name)
        if was is None or was >= oldest:
            continue
        try:
            shutil.rmtree(one)
        except OSError:
            continue
        gone.append(one)
    return gone


def _the_root_holding(agent: str, at: Path) -> Optional[Path]:
    """Which permitted root this file stands under, or `None` when it stands under none.

    Compared on resolved roots and an unresolved file: the roots are directories this product made
    and may themselves be reached through a link — `/tmp` is `/private/tmp` on this platform — while
    the file is checked component by component afterwards, which is the check that actually holds.
    """
    for root in (directory.home(agent), directory.schedules(agent), directory.channels(agent)):
        try:
            settled = root.resolve()
        except OSError:
            continue
        if settled == at or settled in at.parents:
            return settled
        try:
            if root in at.parents or root == at:
                return root
        except OSError:
            continue
    return None


def _opened_without_following(root: Path, at: Path) -> int:
    """Open `at` under `root` refusing every link on the way. Hands back the descriptor.

    Walked a component at a time with `dir_fd`, because that is the only form where each step is
    checked as it is taken. A single `open` of the whole path with `O_NOFOLLOW` checks the *last*
    component only, which leaves the interesting attack — a link on a directory above it — working
    perfectly.
    """
    try:
        parts = at.relative_to(root).parts
    except ValueError as why:
        raise Refused(f"{at} does not stand under {root}") from why
    if not parts:
        raise Refused(f"{at} is a directory, and a directory is not a file to send")

    holding = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            try:
                stepping = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                   dir_fd=holding)
            except OSError as why:
                raise Refused(f"{at} could not be opened without following a link at {part}") from why
            os.close(holding)
            holding = stepping
        try:
            return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=holding)
        except OSError as why:
            raise Refused(f"{at} could not be opened without following a link") from why
    finally:
        os.close(holding)


def _weighed(held: int) -> tuple:
    """How big a descriptor's file is and what it hashes to, read once, from the descriptor.

    From the descriptor rather than from the path, which is the whole reason this takes one: two
    looks at a name can be two different files, and the pair reported here has to describe one.
    """
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(os.dup(held), "rb") as reading:
        while True:
            block = reading.read(BLOCK)
            if not block:
                break
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def _plainly(said: str) -> str:
    """A name from somewhere else, made into one this machine can hold and nothing can escape with.

    Everything outside letters, digits and `-_.` becomes a single `-`, which is what makes a
    separator impossible rather than refused. A name that flattens to nothing gets one, because a
    file has to be called something.
    """
    plain = PLAIN.sub("-", said).strip("-.") or "file"
    return plain[-NAME_AT_MOST:].strip("-.") or "file"


def _somewhere_new(into: Path, name: str) -> Path:
    """That name if nothing holds it, and a numbered one otherwise.

    **The half that sanitising alone misses.** `report v2.csv` and `report-v2.csv` flatten to the
    same thing, and in the previous build the second overwrote the first — after which the agent
    opened exactly the name it had been given and read somebody else's file.
    """
    at = into / name
    if not at.exists():
        return at
    stem, dot, ending = name.partition(".")
    for nth in range(1, 1000):
        tried = into / f"{stem}-{nth}{dot}{ending}"
        if not tried.exists():
            return tried
    raise Refused(f"{into} already holds a thousand files called something like {name}")


def _the_day_of(said: str) -> Optional[date]:
    """The day a directory is named for, or `None` when its name is not one.

    Shape first and then parsed, the way `utils.logs` does it: `2026-02-31` is shaped like a date
    and is not one, and a directory that is not a day is somebody else's to keep.
    """
    try:
        return datetime.strptime(said, logs.DAY).date()
    except ValueError:
        return None
