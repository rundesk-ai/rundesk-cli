"""What arrives through a channel, what may leave through one, and when the first is swept.

Two directions with almost nothing in common, kept in one module because they are the two halves of
one question — which files may cross this seam — and splitting them would let the answers drift.

## Coming in

**The adapter downloads and rundesk decides where it lands.** The adapter holds the credential and
rundesk does not; rundesk owns the filesystem and the adapter does not. So the adapter fetches into
its own channel directory under a name of no consequence, says where it put each one, and `landed`
takes it from there into the agent's own account of what arrived — under the day, under the message,
under a name that is both safe and unused.

**A download that succeeded is not a file that arrived**, and `landed` is where the two are told
apart: the staged path has to stand inside that channel's own directory, be an ordinary file rather
than a link or a device, and hold exactly as many bytes as the platform said it would. The previous
build reported the name a platform declared and the path it meant to write to, so a fetch that half
happened handed an agent a name it could open with nothing behind it.

Two rules about the name it is given, and the second is the one that bit the previous build:

**A name from a platform is a stranger's text.** Anything outside letters, digits and `-_.` goes, so
traversal is not something to defend against — a name with no separators in it cannot reach out of
the directory it is written into.

**Sanitising is not enough on its own.** `report v2.csv` and `report-v2.csv` both flatten to
`report-v2.csv`; the second overwrote the first, and the agent opened exactly the name it had been
given and read somebody else's file. So a name is made *unused* as well as safe.

## Going out, and the check people skip

Three, and the third is the point:

1. Whatever wants to send names an absolute path.
2. **This** resolves it once, opens the canonical path component-by-component with `O_NOFOLLOW`,
   and reports the size and digest of what it actually opened.
3. **The adapter re-opens it the same way and refuses on any mismatch.**

Without the third, a concurrent write can replace the approved file — or a directory above it —
between the check and the send. Steps one and two look complete on their own and are not.

An outgoing file is not copied. An explicit link in the answer may name any readable ordinary file
on the machine. Its canonical path is opened without following a link during the actual open, then
the adapter repeats that check before sending. This matches the authority provider agents already
have while avoiding a duplicate merely to cross the channel seam. Intent remains separate: merely
reading or editing a file never sends it.

**A directory on the way is searched and never read**, and **a refusal says which of the things it
was.** Both come from one incident: an ordinary readable PNG under a directory this process could
pass through but not list was refused, and the sentence written down said a symbolic link stood at
a directory that was not one. `SEARCHING` is the first half and `_would_not_open` is the second —
a link, a mode bit, a privacy grant, a component that went away and a component that is not a
directory are five different things to go and look at. **And the component an open failed on is not
always the one at fault** — a directory this process cannot search refuses the lookup of its own
child, so the refusal is asked about before it is worded rather than blaming whatever name the
error happened to carry.

## Going away

Attachments are the one thing here that grows without a person deciding to keep it, so the day is in
the path and whole days are removed. **Age from the name, never from the filesystem** — the rule
`utils.logs.swept` already keeps, and for the same reason: a restore resets every modification time,
so age taken from the disk would silently sweep everything it had just brought back.

May depend on `agents`, `core` and `utils`.
"""

import contextlib
import errno
import fcntl
import hashlib
import os
import re
import shutil
import stat
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

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

#: How a directory on the way to a file is opened: **passed through, never read.** A walk needs
#: permission to search a directory and never permission to list what is in it, and asking for the
#: larger of the two is how a file somebody explicitly named came to be refused for standing in a
#: directory that grants exactly one of them — measured here: `O_RDONLY | O_DIRECTORY` on a `--x`
#: directory is `EACCES`, and `O_SEARCH` on the same one opens and reads the named file below it.
#:
#: **Nothing about the link protection changes.** `O_NOFOLLOW` is still on every component, every
#: component is still opened from the descriptor above it, and the flag still requires a directory.
#: macOS calls the search-only form `O_SEARCH` (`O_EXEC`, `0x40000000`); some supported CPython 3.9
#: builds omit both names even though Darwin accepts the flag, so the stable system value is the
#: final Darwin spelling. Linux exposes the equivalent path descriptor as `O_PATH`. A platform with
#: neither keeps the older read-only fallback because the standard library offers no portable
#: search-only spelling there.
#:
#: **The two are not the same descriptor, and the difference lands on the refusals.** `O_SEARCH`
#: asks for search permission when it opens, so a directory that grants none is refused at itself;
#: `O_PATH` asks for nothing at all, so the same directory opens and the refusal arrives one
#: component later, on the child that was never the problem. Which is why nothing here reads the
#: component an open failed on as the component at fault — `_reached` asks the directory above
#: before a refusal is worded.
SEARCHING = ((getattr(os, "O_SEARCH", getattr(os, "O_EXEC", 0x40000000))
              if sys.platform == "darwin" else getattr(os, "O_PATH", os.O_RDONLY))
             | os.O_DIRECTORY)


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
    return directory.channels(agent) / kind / ARRIVED_IN / day / plainly(str(message))


def written(into: Path, name: str, body: bytes) -> Path:
    """Write one arriving file under a name that is both safe and unused. Hands back where it went.

    `Refused` when it is bigger than one message may bring — checked here rather than trusted from
    what the platform said it would be, because what a platform declares and what it sends are two
    different facts.
    """
    if len(body) > EACH_AT_MOST:
        raise Refused(f"{name} is {len(body)} bytes, and one file may be {EACH_AT_MOST}")
    into.mkdir(parents=True, exist_ok=True)
    at = _somewhere_new(into, plainly(name))
    at.write_bytes(body)
    return at


def landed(agent: str, kind: str, message: str, brought: Dict[str, Any],
           when: Optional[datetime] = None) -> Path:
    """Take one file the adapter fetched into the agent's own account of what arrived.

    `brought` is the adapter's own record of it, exactly as it crossed the seam: `at` is where the
    adapter put it, `name` is what the platform called it — a stranger's text, flattened here and
    nowhere else — and `bytes` is what the platform said it would be.

    **The staged path has to stand inside this channel's own directory.** An adapter is a program
    rundesk starts, and a buggy one naming `/etc/passwd` would otherwise have rundesk copy it into
    the agent's reach and then delete it. Contained first, so that everything after it is acting on
    a file that is the channel's own.

    **What was staged is taken away either way**, because the channel's directory is not a place a
    file that could not be landed gets to stay: a platform that sends a hundred unreadable files a
    day would otherwise fill a disk one refusal at a time.

    `Refused` says which it was — reaching outside, not there, not an ordinary file, too big, or not
    the size it was said to be — because each of those is a different thing to go and look at.
    """
    at = Path(str(brought.get("at") or ""))
    if not at.is_absolute() or any(part in (".", "..") for part in at.parts):
        raise Refused(f"{at} is not an absolute path to a file the adapter fetched")
    home = directory.channels(agent) / plainly(kind)
    try:
        # Resolved on both sides, the way `_the_root_holding` does it and for the same two reasons:
        # `/tmp` is `/private/tmp` on this platform, so a lexical comparison refuses every ordinary
        # path there; and a *directory* staged under a link would otherwise read as contained while
        # standing somewhere else entirely, which `lstat` below cannot see because a link two steps
        # up is not the component it is asked about.
        within, settled = home.resolve(), at.resolve()
    except OSError as why:
        raise Refused(f"{at} could not be checked against {kind}'s own directory ({why})") from why
    if within not in settled.parents:
        raise Refused(f"{at} did not come from {kind}'s own directory, so it is not a file that "
                      f"arrived through it")
    try:
        return _taken_over(agent, kind, message, at, brought, when)
    finally:
        with contextlib.suppress(OSError):
            at.unlink()
        if at.parent != home:
            with contextlib.suppress(OSError):
                at.parent.rmdir()         # empty only when this was the last of the message's files


def _taken_over(agent: str, kind: str, message: str, at: Path, brought: Dict[str, Any],
                when: Optional[datetime]) -> Path:
    """Weigh what was staged, write it where the agent will read it, and prove it got there."""
    try:
        how = at.lstat()
    except OSError as why:
        raise Refused(f"{at} was reported as fetched and is not there ({why})") from why
    # **`lstat`, so a link is refused rather than followed.** The staged name is the adapter's own,
    # but this is the one place a program on the far side of a seam names a path on this side, and a
    # link is how that name would come to mean somewhere else entirely.
    if not stat.S_ISREG(how.st_mode):
        raise Refused(f"{at} is not an ordinary file, so nothing arrived under that name")
    if how.st_size > EACH_AT_MOST:
        raise Refused(f"{at} is {how.st_size} bytes, and one file may be {EACH_AT_MOST}")
    said = brought.get("bytes")
    if isinstance(said, int) and not isinstance(said, bool) and said != how.st_size:
        # **The download succeeding is not the file arriving.** A fetch cut off part way leaves a
        # readable file of the wrong length, and the agent is then handed a name it can open and
        # half of what somebody sent it.
        raise Refused(f"{at} holds {how.st_size} bytes and was said to hold {said}, so what "
                      f"arrived is not what was sent")
    body = at.read_bytes()
    where = written(arrived_at(agent, kind, message, when), str(brought.get("name") or at.name),
                    body)
    if where.stat().st_size != len(body):
        raise Refused(f"{where} was written and does not hold what was written to it")
    return where


def approved(said: str) -> Sending:
    """Resolve, weigh and digest any explicitly named ordinary local file.

    A symbolic spelling is resolved once, then **every component of that canonical path is opened
    with `O_NOFOLLOW`** — the directories on the way searched rather than read, per `SEARCHING`.
    The adapter receives the canonical path and repeats the same walk, size and digest check, so a
    later replacement is refused instead of becoming a different attachment.

    What comes back is measured from the descriptor this opened, never from a second look at the
    path — so the size and digest describe one file rather than whatever stood at that name twice.

    **Every refusal names what actually stopped it**, including the one raised before the walk
    begins: a path that will not canonicalize is a missing file, a permission, or a loop, and
    collapsing the three loses the only thing anybody could act on.
    """
    at = Path(said)
    if not at.is_absolute():
        raise Refused(f"{said} is not an absolute path, and only an absolute one can be checked")
    # A path with navigation steps is ambiguous intent even when it resolves to an ordinary file.
    # Refused by shape before canonicalization, the same way `plainly` refuses an unsafe name.
    if any(part in (".", "..") for part in at.parts):
        raise Refused(
            f"{said} reaches through a relative step, and a path that does that cannot be checked "
            "— name the file where it actually stands")
    shown = at.name
    try:
        at = at.resolve(strict=True)
    except (ValueError, RuntimeError) as why:
        raise Refused(f"{said!r} could not be resolved to a file on this machine") from why
    except OSError as why:
        raise Refused(f"{said} could not be resolved to a file on this machine "
                      f"({_named(why)}: {why.strerror or why})") from why
    held = _opened_without_following(at)
    try:
        how = _ordinary_file(held, at)
        if how.st_size > EACH_AT_MOST:
            raise Refused(f"{at.name} is {how.st_size} bytes, and one file may be {EACH_AT_MOST}")
        size, digest = _weighed(held, at_most=EACH_AT_MOST)
    finally:
        os.close(held)
    if size > EACH_AT_MOST:
        raise Refused(f"{at.name} is {size} bytes, and one file may be {EACH_AT_MOST}")
    return Sending(name=plainly(shown), at=at, bytes=size, sha256=digest)


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


def _opened_without_following(at: Path) -> int:
    """Open canonical `at` from its filesystem root, refusing every link on the way.

    Walked a component at a time with `dir_fd`, because that is the only form where each step is
    checked as it is taken. A single `open` of the whole path with `O_NOFOLLOW` checks the *last*
    component only, which leaves the interesting attack — a link on a directory above it — working
    perfectly.
    """
    root = Path(at.anchor)
    try:
        parts = at.relative_to(root).parts
    except ValueError as why:
        raise Refused(f"{at} does not stand under {root}") from why
    if not parts:
        raise Refused(f"{at} is a directory, and a directory is not a file to send")

    holding = os.open(str(root), SEARCHING)
    try:
        for nth, part in enumerate(parts[:-1]):
            try:
                stepping = os.open(part, SEARCHING | os.O_NOFOLLOW, dir_fd=holding)
            except OSError as why:
                raise _would_not_open(why, at, root.joinpath(*parts[:nth + 1]), part,
                                      holding) from why
            os.close(holding)
            holding = stepping
        try:
            # **`O_NONBLOCK`, and it is not an optimisation.** Opening a named pipe for reading
            # waits for a writer that may never come, so a FIFO under the agent's own home — which
            # it may write in — wedged whatever thread asked, for ever. Refusing it afterwards is
            # too late, because the open is what blocks. It is cleared again below once the kind of
            # thing this is has been established.
            return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=holding)
        except OSError as why:
            raise _would_not_open(why, at, at, parts[-1], holding) from why
    finally:
        os.close(holding)


def _would_not_open(why: OSError, at: Path, standing: Path, part: str, holding: int) -> Refused:
    """Why one component of an approved path would not open, in the terms of what happened.

    **Every failure here used to be reported as a link, and one of them was not one.** A gateway
    refused a directory it holds no privacy grant for was told `could not be opened without
    following a link at Downloads` — about a directory that was not a link, for a file that was an
    ordinary readable PNG — and whoever read it went looking for a link that had never been there.
    The open is refused either way; what changes is whether the sentence is true.

    So the errno is carried into the words, the component is named where it actually stands, and a
    refusal to read is never called a link. A permission this process does not hold is **this
    process's** — the same file may open perfectly from a terminal — which is why the sentence says
    so rather than leaving somebody to read a grant proved somewhere else as one that holds here.

    **The component an open failed on is not always the component at fault.** A descriptor held on
    a directory this process cannot search refuses every lookup made through it, so the child is
    where the error surfaces and the parent is where the mode bit is — which is what `O_PATH`
    produces on Linux for a directory `O_SEARCH` would have refused outright on macOS, and what any
    platform produces when a directory loses its mode between the walk opening it and the walk
    stepping through it. Naming the child there is the same class of untrue sentence as naming a
    link: it sends whoever reads it to change permissions on a file that was never refused. So a
    refusal to search is asked about before it is worded, and the answer is the same on both
    platforms.
    """
    code = _named(why)
    if why.errno == errno.ELOOP or (why.errno == errno.ENOTDIR and _a_link(part, holding)):
        # **Which errno arrives says nothing on its own.** A link opened `O_NOFOLLOW | O_DIRECTORY`
        # answers `ENOTDIR` on this platform and one opened as a file answers `ELOOP`, so the
        # component itself is asked about — *after* it has already been refused. This decides the
        # wording of a refusal and never whether to refuse.
        return Refused(f"{at} could not be opened to be sent: a symbolic link stands at {standing} "
                       f"and no component of a path being sent is ever followed ({code})")
    if why.errno in (errno.EPERM, errno.EACCES) and not _reached(part, holding):
        return Refused(f"{at} could not be opened to be sent: {standing.parent} cannot be searched "
                       f"by this process ({code}), so {standing} under it was never reached — the "
                       f"refusal belongs to that directory above and not to what was named under "
                       f"it, and it is not a link")
    if why.errno == errno.EPERM:
        return Refused(f"{at} could not be opened to be sent: the machine refuses this process "
                       f"{standing} ({code}) — on macOS that is a privacy grant, which belongs to "
                       f"the program this process runs as and not to the file, and it is not a "
                       f"link. A grant proved in another lineage is not this one's")
    if why.errno == errno.EACCES:
        return Refused(f"{at} could not be opened to be sent: {standing} refuses this process by "
                       f"its own permissions ({code}), which is a mode bit rather than a link")
    if why.errno == errno.ENOENT:
        return Refused(f"{at} could not be opened to be sent: {standing} was there when the path "
                       f"was resolved and is not there now ({code})")
    if why.errno == errno.ENOTDIR:
        return Refused(f"{at} could not be opened to be sent: {standing} is not a directory "
                       f"({code}), so nothing stands below it")
    return Refused(f"{at} could not be opened to be sent: {standing} would not open "
                   f"({code}: {why.strerror or why})")


def _named(why: OSError) -> str:
    """The name this platform gives the errno something failed with, carried into every sentence.

    The number alone is what a person then has to go and look up, and no number at all is what left
    a refusal saying only that something could not be opened.
    """
    return errno.errorcode.get(why.errno or 0) or f"errno {why.errno}"


def _a_link(part: str, holding: int) -> bool:
    """Whether this component is a symbolic link, asked of the directory it stands in.

    Only ever asked to word a refusal that has already happened, so a component that has changed
    again in between costs a sentence and never a decision.
    """
    try:
        return stat.S_ISLNK(os.lstat(part, dir_fd=holding).st_mode)
    except OSError:
        return False


def _reached(part: str, holding: int) -> bool:
    """Whether this component could be looked up at all in the directory above it.

    **A lookup needs search permission on the directory it is asked of and no permission at all on
    what it finds**, which is what makes it the question that separates the two. Refused here, and
    the directory above is the one holding the mode bit — the component named under it was never
    reached and its own permissions were never consulted. Answered here, and the refusal really is
    the component's own.

    Only ever asked to word a refusal that has already happened, so a component that has changed
    again in between costs a sentence and never a decision. Anything other than a refusal to search
    — the component going away between the open and this — leaves the refusal with the component,
    which is where the errno already pointed.
    """
    try:
        os.lstat(part, dir_fd=holding)
    except OSError as why:
        return why.errno not in (errno.EACCES, errno.EPERM)
    return True


def _ordinary_file(held: int, at: Path) -> os.stat_result:
    """Refuse anything that is not an ordinary file without blocking on a device or pipe."""
    how = os.fstat(held)
    if stat.S_ISREG(how.st_mode):
        # An ordinary file never blocks, so the flag that saved us from the pipe is taken off again
        # rather than left to make the read below answer short.
        with contextlib.suppress(OSError):
            fcntl.fcntl(held, fcntl.F_SETFL,
                        fcntl.fcntl(held, fcntl.F_GETFL) & ~os.O_NONBLOCK)
    if not stat.S_ISREG(how.st_mode):
        raise Refused(f"{at} is not an ordinary file, and only an ordinary file can be sent")
    return how


def _weighed(held: int, at_most: int = EACH_AT_MOST) -> tuple:
    """How big a descriptor's file is and what it hashes to, read once, from the descriptor.

    From the descriptor rather than from the path, which is the whole reason this takes one: two
    looks at a name can be two different files, and the pair reported here has to describe one.
    """
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(os.dup(held), "rb") as reading:
        while size <= at_most:
            block = reading.read(min(BLOCK, at_most + 1 - size))
            if not block:
                break
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def plainly(said: str) -> str:
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
