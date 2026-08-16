"""Whether a gateway is online — asked of the kernel, and never of something a process wrote down.

**A gateway that was killed outright must never look alive.** That is the one property everything
here is arranged around, and it is the property a pid file cannot have. A pid file is a number a
process wrote about itself; nothing updates it when that process is `SIGKILL`ed, loses its machine to
a power cut, or is taken away by a supervisor. Worse, the number is reused — a recorded pid whose
process is gone is a pid that now belongs to something else, and a caller that signals it kills a
stranger's program.

So liveness is an exclusive `flock` on `<agent dir>/gateway.lock`, held for the whole life of the
gateway process. The kernel took it and the kernel releases it, however the process ended, and
nothing anywhere has to be tidied up for the answer to become correct. **Nothing in the record beside
it decides anything**: the record is read only once the lock has already said a gateway is running,
and the pid comes back as `None` otherwise.

**The lock file is never unlinked while it is not held, and there is no sweep.** A lock lives on the
inode, not on the name. Unlinking hands the name away: the next claim creates a fresh inode and locks
*that*, and two processes then hold two different locks while answering as one gateway — which is the
failure lockfile-by-existence schemes have, arrived at by the back door. A file left behind is not a
held lock, it is somewhere for the next one to hang.

**Asking and then acting are two decisions with a gap.** Between `standing()` saying offline and a
caller starting something, another process can claim the name — and the build this replaces recorded
exactly that: an ordinary `start` that had checked first ended a live agent's whole process tree. So
`holding()` exists and is what a start uses: the claim *is* the check, and there is no moment between
them for anybody to arrive in.

**Three answers, not two.** Online, offline, and nobody can tell — a lock file that could not be
opened at all, because its directory is unreadable or its permissions were changed. Unreadable is not
a quiet form of offline: reporting an agent nobody can ask about as "not running" is how a second
gateway gets started beside a first.

**Wedged is not the same report as healthy.** A gateway holding the lock while writing no beats is a
process that is up and doing nothing, which is the state a person most needs told. Measured with
`time.monotonic()` and never with the wall clock: the wall clock moves in *both* directions on
sleep, wake and NTP, so an age taken from it can be negative or hours wrong, and a healthy gateway
would report as wedged for reasons entirely outside this machine.

**And when it never stood up at all, where the only account of that is.** A gateway that died before
it could write a line of its own — a missing interpreter, a job the supervisor would not take, an
exception on the way up — leaves nothing in its own log, because nothing had opened it yet. What it
leaves is in the two files the machine's supervisor captured, and those are named here, beside the
question they are the answer to. Nothing in this product writes them; launchd does.
"""

import contextlib
import fcntl
import os
import time
from pathlib import Path
from typing import Any, Iterator, NamedTuple, Optional, Tuple

from rundesk.utils import files, locking, logs, programs

#: The name the kernel holds while a gateway is up, in the agent's own directory.
LOCK = "gateway.lock"

#: What the gateway wrote about itself. Never the thing that decides whether it is running.
RECORD = "gateway.json"

#: Where everything a gateway says is written, below the agent's own directory — a file per day,
#: kept by `utils.logs`.
LOGS = "logs"

#: What the machine's supervisor caught on its own, in the same directory. Written by launchd and
#: never by this — see the module docstring.
CAPTURED_OUT = "gateway.out"
CAPTURED_ERR = "gateway.err"

#: A gateway holds the lock.
ONLINE = "online"

#: Nobody holds the lock, whatever the record beside it says.
OFFLINE = "offline"

#: The lock could not be opened at all — a permission problem, a directory that cannot be read.
#: Deliberately not folded into `OFFLINE`: an agent nobody can ask about is a thing to say out loud.
CANNOT_TELL = "cannot tell"

#: How often a gateway that is working says so.
BEAT_SECONDS = 15.0

#: How many beats may be missed before it is wedged rather than healthy. Three, so an ordinary
#: pause — a slow disk, a machine under load — is never reported as a gateway that has stopped
#: working, and a gateway that really has stopped is named within a minute.
MISSED_BEATS = 3

#: How long a gateway may go without saying anything before it is wedged.
WEDGED_AFTER = BEAT_SECONDS * MISSED_BEATS

#: How long a refused claim is asked again for before it is read as a gateway's.
#:
#: **Because asking the question excludes the answer.** `standing()` has to take a *shared* lock to
#: find out whether anybody holds the exclusive one, and a shared lock conflicts with an exclusive
#: one in both directions — so for the few microseconds a `rundesk status` is reading, a gateway
#: claiming its own name is refused, and told the name belongs to a gateway that does not exist.
#: Measured on this machine 2026-08-16, one process calling `standing()` in a loop and one calling
#: `holding()` in a loop against an agent with no gateway at all: **903 of 159,850 claims refused**,
#: every one of them by a reader. `gateways.host` turns that refusal into an **exit-zero** refusal,
#: which launchd does not retry — so the losing side of a microsecond race is a gateway that stays
#: down until somebody notices.
#:
#: **This is only ever spent once the kernel has already said no gateway is there.** A refused claim
#: asks a second question — see `_only_a_reader_has_it` — and a name a gateway really holds is
#: refused on the spot, exactly as it always was. This window is what a claim spends waiting out a
#: *reader*, which holds the lock for the length of one question and nothing longer, and it is a
#: ceiling rather than a wait: a reader that is somehow still there at the end is refused too.
PAST_A_PROBE_SECONDS = 0.5

#: How often the claim is asked again inside that window.
ASKING_AGAIN_SECONDS = 0.01


class Taken(Exception):
    """The name belongs to a gateway that is already running.

    Named rather than left an `OSError` with an errno, because this is the answer rather than the
    failure: a start that meets this has been told the agent is already up, and what it does about
    that is not an exception's business.
    """


class Unrecorded(Exception):
    """There is no record to beat in, so nothing was written over.

    A beat says *the gateway named in the record is still the one holding the lock*. With no record
    to read, writing one anyway would invent a gateway with no name and no pid, and whoever asked
    would be told a beat had landed. Refused out loud instead.
    """


class Standing(NamedTuple):
    """How a gateway stands, in answers that are kept apart because they mean different things.

    `how` is the field to read first, and it is one of three: `ONLINE`, `OFFLINE`, `CANNOT_TELL`.

    `pid` is only ever a number while `how` is `ONLINE` — the record is not trusted otherwise, and a
    pid read off a dead gateway's record is a number that now belongs to something else.

    `stale` is `None` rather than `False` when there is nothing to judge it by: a gateway holding the
    lock with no readable record is up, and answering `False` there would be a report of health that
    nothing measured.

    **There is deliberately no `online` shortcut**, for the reason `utils.programs.Ran` has no
    `worked` one: a boolean would answer `False` both for a gateway that is not running and for one
    nobody could ask about, and telling those apart is the whole point of the type.
    """

    how: str
    pid: Optional[int]
    stale: Optional[bool]
    why: str


@contextlib.contextmanager
def holding(at: Path) -> Iterator[None]:
    """Claim an agent's name and keep it for the length of the block. `Taken` when somebody has it.

    **The claim is the check.** Anything that asks whether a gateway is running and then starts one
    has two decisions with a gap between them, and a gateway can claim the name inside that gap — an
    ordinary `start` ended a live agent's whole process tree that way once. There is no version of
    this that answers a question without also taking the name.

    **A gateway is never waited out, and a reader never wins.** A lock a *gateway* has is not a busy
    moment to sit out: it is the state the caller was checking for, and waiting on it would turn an
    immediate answer into a pause with nothing said during it. But the same lock is what `standing()`
    takes, *shared*, for the length of one question — so an ordinary `rundesk status` refuses this
    claim for the microseconds it is reading, and a claim asked once could lose to a reader and
    report a gateway that is not there. Which of the two refused it is asked rather than timed:
    `_only_a_reader_has_it` puts one more question to the kernel, and only a name held by readers is
    asked for again, to the ceiling in `PAST_A_PROBE_SECONDS`.

    **Written here rather than taken from `utils.locking`**, which is the same mechanism with two
    differences that matter. That one waits to a ceiling measured in whole seconds, because it
    serialises commands that take turns; this one asks only past a reader, because a name a gateway
    holds is an answer. And that one counts re-entry per thread, so a second claim inside one process
    passes straight through — right for a call stack that re-enters its own critical section, and
    wrong for an identity, where one process hosting two gateways for one agent is exactly what must
    not be allowed to happen. What *is* taken from there is `locking.busy`: reading a refusal apart
    from a real failure is one question with one answer, however differently the two locks are used.

    On the way out the descriptor is closed, which is what releases the lock. **The file itself is
    left alone** — see the module docstring on why unlinking it would let two gateways answer as one.
    """
    at.mkdir(parents=True, exist_ok=True)
    held = os.open(at / LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        _claimed(held, at)
        yield
    finally:
        os.close(held)


def _claimed(held: int, at: Path) -> None:
    """Take the name on this descriptor, or say who has it. See `holding`, which owns the reasoning.

    The loop is entered only by a claim that was refused, and left by the first of three things: the
    name coming free, the kernel saying a gateway rather than a reader is holding it, or the ceiling.
    """
    ceiling = time.monotonic() + PAST_A_PROBE_SECONDS
    while True:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as why:
            if not locking.busy(why):
                raise
            refused = why
        if not _only_a_reader_has_it(held) or time.monotonic() >= ceiling:
            raise Taken(f"a gateway is already running for {at}") from refused
        time.sleep(ASKING_AGAIN_SECONDS)


def _only_a_reader_has_it(held: int) -> bool:
    """Whether what refused the claim was a question being asked, rather than a gateway.

    **The one thing that tells them apart, and it is asked rather than assumed.** A shared lock is
    what `standing()` takes to read, and shared locks do not exclude each other — so a shared lock
    that can be taken here means every holder is reading and none of them is a gateway, and one that
    cannot be taken means somebody holds the exclusive lock. That is the whole of the distinction,
    and it is why a name a gateway really has is still refused in the same instant it always was.

    Asked on the descriptor the claim was refused on, because a second `open` would be a second
    open file description and this one is already here. Let go of again immediately: what is wanted
    is the answer, and a shared lock kept any longer would make this the very reader it is asking
    about. Anything other than a clean yes is a no — the caller has an answer to give either way,
    and a claim is not the place to start explaining a descriptor of its own.
    """
    try:
        fcntl.flock(held, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError:
        return False
    with contextlib.suppress(OSError):
        fcntl.flock(held, fcntl.LOCK_UN)
    return True


def standing(at: Path) -> Standing:
    """Whether a gateway is running for this agent: online, offline, or nobody can tell.

    The question is put to the kernel — can this lock be taken? — and nothing else is consulted until
    it has been answered. A gateway that crashed, was `SIGKILL`ed or lost its machine reads as
    offline here with its record still whole on disk, which is the proof the design works.

    **Asked with a shared lock, and that is not a detail.** An exclusive probe conflicts with another
    *probe*, so two people running `status` at the same moment would each read the other as a gateway
    and report an agent that is not running as online. A shared lock conflicts with the gateway's
    exclusive one and with nothing else.

    **The file is never created to answer the question.** A question that writes is a question that
    fails on a read-only disk, and a lock file that is not there means nobody has ever held this
    name — which is `MISSING` rather than `UNREADABLE`, in the words `utils.files` already uses.
    """
    lock = at / LOCK
    try:
        asked = os.open(lock, os.O_RDONLY)
    except FileNotFoundError:
        return Standing(OFFLINE, None, None, "")
    except OSError as why:
        return Standing(CANNOT_TELL, None, None, f"{lock} could not be opened ({why})")
    try:
        fcntl.flock(asked, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError as why:
        if locking.busy(why):
            return _what_it_said_about_itself(at)
        return Standing(CANNOT_TELL, None, None, f"{lock} could not be asked about ({why})")
    finally:
        # Closing is what lets go of whatever was taken. Held for the length of one question — and
        # a gateway claiming its name in that instant *is* refused by it, which is not something
        # this side can avoid: asking whether the exclusive lock is free means taking a lock that
        # conflicts with it. `holding` is where that is answered, by asking which kind of holder
        # refused it rather than believing the first no.
        os.close(asked)
    return Standing(OFFLINE, None, None, "")


def write_record(at: Path, name: str, version: str) -> None:
    """Write down what this gateway is, beside the lock it is holding.

    Called by the process that holds the lock and by nothing else: the record describes the holder,
    and one written by anybody else is a claim with nothing behind it.

    Written whole and renamed into place by `utils.files`, rather than opened and filled in — a
    reader arriving mid-write would otherwise get half a JSON document, which is not a smaller record
    but an unreadable one.
    """
    when = _when()
    files.write_json(at / RECORD, {
        "name": name,
        "pid": os.getpid(),
        "version": version,
        "started_at": when,
        "beat_at": when,
        "since_boot": _since_boot(),
    })


def write_beat(at: Path) -> None:
    """Say the gateway is still working, without touching what it said it was.

    Everything else in the record is carried across rather than re-stated, so a beat can never
    disagree with the record about which gateway this is.

    `Unrecorded` when there is nothing readable to beat in — including a record that is there and
    will not parse, which is never written over. Losing the pid and the name of a gateway that *is*
    running, in the act of reporting it healthy, is the worst of both.
    """
    how, said = files.read_json(at / RECORD)
    if how == files.READ and not isinstance(said, dict):
        # Valid JSON that is not a record is not a record.
        how = files.UNREADABLE
    if how != files.READ:
        raise Unrecorded(
            f"there is no record in {at / RECORD} to beat in — it is {how}, and a beat says the "
            "gateway named in the record is still the one holding the lock")
    kept = dict(said)
    kept["beat_at"] = _when()
    kept["since_boot"] = _since_boot()
    files.write_json(at / RECORD, kept)


def logs_at(at: Path) -> Path:
    """Where this gateway's own log stands: one file per day, written through `utils.logs`.

    Said here rather than by whatever writes a line, so that the gateway's log and the supervisor's
    capture of the same gateway cannot come to be in two different places.
    """
    return at / LOGS


def captured(at: Path) -> Tuple[Path, Path]:
    """Where the machine's supervisor puts what it caught: `(out, err)`.

    Nothing here writes them, and the reason they are named at all is that they are the **only**
    account of a start that died before the gateway had a log of its own. Whoever has to explain an
    agent that says it is offline and shows nothing in its own log needs to be able to find them.
    """
    return logs_at(at) / CAPTURED_OUT, logs_at(at) / CAPTURED_ERR


def _what_it_said_about_itself(at: Path) -> Standing:
    """The record, read only once the lock has already said a gateway is running.

    A gateway with nothing readable beside it is still online — the kernel said so. It simply has
    nothing to say about itself, which is `None` for both of the things the record would have
    answered rather than a number and a verdict nothing supports.
    """
    how, said = files.read_json(at / RECORD)
    if how != files.READ or not isinstance(said, dict):
        return Standing(ONLINE, None, None, "")
    return Standing(ONLINE, programs.a_pid(said.get("pid")), _wedged(said.get("since_boot")), "")


def _since_boot() -> float:
    """A clock reading **one process can compare against another's**, which is the whole job here.

    **Never `time.monotonic()`, and that was a real defect on the interpreter this project's floor
    pins.** On macOS, Python 3.9's `time.monotonic()` counts from the start of *this process* —
    3.9 reads 0.004 a moment after starting while 3.14 reads 1280225 on the same machine at the same
    instant. `since_boot` is written by a gateway and read by something else, so on 3.9 the
    subtraction was the *reader's* own age: anything that had been alive longer than `WEDGED_AFTER`
    reported every gateway it looked at as wedged, however healthy. A `rundesk status` is short-lived
    and got away with it; a gateway asking about another agent, or a test suite, did not.

    `clock_gettime(CLOCK_MONOTONIC)` is the same system-wide reading on both — 1432188.22 against
    1432188.24, measured. It is not on Windows, which this product does not run on: the job it is
    written against is `launchd`.

    Still monotonic, so the reasoning in `_wedged` holds unchanged — the wall clock moves in both
    directions and an age taken from it can be negative or hours out.
    """
    return time.clock_gettime(time.CLOCK_MONOTONIC)


def _wedged(said: Any) -> Optional[bool]:
    """Whether enough beats have been missed for this to be wedged rather than healthy.

    **Measured from `since_boot`, which is a monotonic reading two processes can compare — see
    `_since_boot` — and never from the two timestamps beside it.** Those are for a person to read. The wall clock moves in both directions —
    a laptop waking, an NTP correction — so an age taken from it can be negative or hours out, and a
    gateway beating every fifteen seconds would be reported wedged because somebody's clock was
    adjusted.

    `None` when there is nothing to measure. A monotonic reading is only comparable within one boot,
    and one from a previous boot cannot be reached here: the lock cannot outlive the machine, so
    this is only ever asked about a gateway that is running now.
    """
    if isinstance(said, bool) or not isinstance(said, (int, float)):
        return None
    return _since_boot() - float(said) > WEDGED_AFTER


def _when() -> str:
    """The moment, in the machine's own clock with its offset — the same shape a log line carries.

    For a person to read, and nothing decides anything from it: see `_wedged` for why staleness is
    measured from a monotonic reading instead.

    **The same shape because it is the same function**, `utils.logs.stamp`, and not the same literal
    written a second time. `status` shows what this record says a gateway has been up since, and the
    next thing anybody does is look at that gateway's log — so these two are read side by side, and
    two clocks there would mean arithmetic on every comparison. The reasoning for local time and for
    the offset that makes it safe is kept there, in the one place that decides it.
    """
    return logs.stamp()
