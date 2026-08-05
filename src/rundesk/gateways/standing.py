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

    Asked once and never waited on. A lock this one cannot have is not a busy moment to sit out: it
    is another gateway for this agent, which is the state the caller was checking for, and waiting
    would turn an immediate answer into a pause with nothing said during it.

    **Written here rather than taken from `utils.locking`**, which is the same mechanism with two
    differences that matter. That one waits to a ceiling, because it serialises commands that take
    turns; this one refuses at once, because a name that is held is an answer. And that one counts
    re-entry per thread, so a second claim inside one process passes straight through — right for a
    call stack that re-enters its own critical section, and wrong for an identity, where one process
    hosting two gateways for one agent is exactly what must not be allowed to happen. What *is* taken
    from there is `locking.busy`: reading a refusal apart from a real failure is one question with
    one answer, however differently the two locks are used.

    On the way out the descriptor is closed, which is what releases the lock. **The file itself is
    left alone** — see the module docstring on why unlinking it would let two gateways answer as one.
    """
    at.mkdir(parents=True, exist_ok=True)
    held = os.open(at / LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as why:
            if not locking.busy(why):
                raise
            raise Taken(f"a gateway is already running for {at}") from why
        yield
    finally:
        os.close(held)


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
        # Closing is what lets go of whatever was taken. Held for the length of one question, so a
        # gateway starting in this instant waits microseconds rather than meeting a refusal.
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
        "since_boot": time.monotonic(),
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
    kept["since_boot"] = time.monotonic()
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


def _wedged(said: Any) -> Optional[bool]:
    """Whether enough beats have been missed for this to be wedged rather than healthy.

    **Measured from `since_boot`, which is a `time.monotonic()` reading, and never from the two
    timestamps beside it.** Those are for a person to read. The wall clock moves in both directions —
    a laptop waking, an NTP correction — so an age taken from it can be negative or hours out, and a
    gateway beating every fifteen seconds would be reported wedged because somebody's clock was
    adjusted.

    `None` when there is nothing to measure. A monotonic reading is only comparable within one boot,
    and one from a previous boot cannot be reached here: the lock cannot outlive the machine, so
    this is only ever asked about a gateway that is running now.
    """
    if isinstance(said, bool) or not isinstance(said, (int, float)):
        return None
    return time.monotonic() - float(said) > WEDGED_AFTER


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
