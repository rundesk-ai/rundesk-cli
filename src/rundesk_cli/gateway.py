"""The part of rundesk that stays running, and everything it keeps hold of.

A gateway is one long-lived process. The machine's own supervisor keeps it up, brings it
back when it falls over and starts it again after a reboot; nothing here supervises
anything, and that is the point — see `.knowledge/prd-drafts/platform-gateway.md`.

**Every gateway has a name, and there is more than one.** There is exactly one today and
no agents to name it after, but the lock, the record and the supervisor's job are all keyed
by name from the outset. A gateway per agent is how one agent is restarted without
disturbing the others, and it is far cheaper to carry the name now than to introduce it
later: the version of this that shipped with a single shared job had to grow code to evict
it, because two gateways answering as one identity answer everything twice.

**Liveness is asked of the kernel, not of a file.** A gateway holds an exclusive lock for
as long as it runs, and the lock is released when the process dies however it died. So
"is it running" is answered by trying to take the lock, and a record left behind by a
gateway that was killed outright cannot make a dead gateway look alive (R-GW-10).
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import fcntl
import importlib.util
import re
import itertools
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from rundesk_cli import ROOT, __version__
from rundesk_cli import process

#: The gateway that exists before there are agents to name one after.
DEFAULT_NAME = "gateway"

class NotAName(ValueError):
    """A gateway name that would not stay inside the directory it belongs in."""


def checked(name: str) -> str:
    """A gateway's name becomes the name of its lock, its record and its log, so one
    containing a separator would put all three somewhere else entirely."""
    if not name or not all(ch.isalnum() or ch in "-_." for ch in name) or name.strip(".") == "":
        raise NotAName(
            f"'{name}' is not a usable gateway name — letters, digits, dash, dot and underscore"
        )
    return name


#: How a line in a gateway's log reads. One place, because anything else writing to that
#: log has to match it, and working the format out by hand somewhere else is how the two
#: come to differ with nothing to catch it.
WRITTEN_AS = "%(asctime)s %(levelname)-7s %(message)s"

#: How much a gateway may write before it starts again, and how many it keeps. A gateway
#: that has been up for a month should not be able to fill a disk, and the thing you want
#: when something happened at three in the morning is the part just before it.
LOG_BYTES = 2 * 1024 * 1024
LOG_KEEP = 3


def write_schedules(name: str, keeping: list, where: Path | None = None) -> None:
    """Write this gateway's schedules down, whole and in one move.

    The gateway reads this file every time it looks at the clock, so a change takes
    effect within a tick without anything being restarted — and a half-written file
    would be read as a gateway with no schedules at all.
    """
    _written_whole(schedules_path(name, where), json.dumps(keeping, indent=2) + "\n")


@contextlib.contextmanager
def changing_schedules(name: str, where: Path | None = None):
    """Read this gateway's schedules, change them, and write them back — alone.

    Held for the whole read-and-write, because writing whole is not the same as changing
    alone: two commands that each read the same list and each write theirs back leave one
    change gone, with both having reported success. The lock is the one the kernel drops
    however the process holding it ends, so a command that dies mid-change blocks nothing.
    """
    target = schedules_path(name, where)
    target.parent.mkdir(parents=True, exist_ok=True)
    guard = os.open(target.with_suffix(".changing"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(guard, fcntl.LOCK_EX)
        keeping = written_schedules(name, where)
        yield keeping
        _written_whole(target, json.dumps(keeping, indent=2) + "\n")
    finally:
        fcntl.flock(guard, fcntl.LOCK_UN)
        os.close(guard)


def written_schedules(name: str, where: Path | None = None) -> list:
    """What is written down for this gateway, as written — including what cannot be
    understood, because removing a broken schedule is the main thing anyone wants to do
    with one."""
    said = _read_json(schedules_path(name, where), [])
    return said if isinstance(said, list) else []


def logs_home() -> Path:
    """Where gateways write what happened. Kept apart from what they are *doing* now, in
    `home()`: that is state, cleared when a gateway goes, and this is history, which is
    only worth anything if it outlives the gateway that wrote it (R-GW-18)."""
    return Path(os.environ.get("RUNDESK_LOG_DIR") or Path.home() / ".rundesk" / "logs")


def log_path(name: str, logs: Path | None = None) -> Path:
    """The file a gateway of this name writes to — what `rundesk logs` reads."""
    return (logs or logs_home()) / f"{checked(name)}.log"


def note(name: str, said: str, logs: Path | None = None) -> None:
    """Add a line to a gateway's log from outside the gateway.

    Formatted by the same formatter the gateway itself writes through, rather than
    worked out by hand: a change to how a line reads would otherwise leave these lines
    looking like something else, in the one account that outlives the gateway.
    """
    record = logging.LogRecord(f"rundesk.gateway.{name}", logging.INFO, "", 0, said, None, None)
    try:
        with open(log_path(name, logs), "a", encoding="utf-8") as log:
            log.write(logging.Formatter(WRITTEN_AS).format(record) + "\n")
    except OSError:
        pass  # the change stands whether or not it could be written down


def _recorder(name: str, logs: Path) -> logging.Logger:
    """A log for one gateway, and no other.

    Built rather than fetched from the logging registry: two gateways in one process
    would otherwise share a name and write each other's lines, and nothing in this module
    is shared between two gateways.
    """
    logs.mkdir(parents=True, exist_ok=True)
    keeping = logging.Logger(f"rundesk.gateway.{name}", logging.INFO)
    to_file = logging.handlers.RotatingFileHandler(
        log_path(name, logs), maxBytes=LOG_BYTES, backupCount=LOG_KEEP, encoding="utf-8"
    )
    to_file.setFormatter(logging.Formatter(WRITTEN_AS))
    keeping.addHandler(to_file)
    # Also said out loud, so a gateway run in a terminal shows its working, and one run
    # by the machine has it in whatever the machine captures.
    aloud = logging.StreamHandler(sys.stderr)
    aloud.setFormatter(logging.Formatter(f"rundesk {name}: %(message)s"))
    keeping.addHandler(aloud)
    return keeping


def home() -> Path:
    """Where a gateway keeps what it needs while it runs.

    Beside the install rather than inside the source: an update lays a new release over
    the install, and what is running is not part of the release.
    """
    return Path(os.environ.get("RUNDESK_RUN_DIR") or Path.home() / ".rundesk" / "run")


def _written_whole(target: Path, text: str) -> None:
    """Put this where it belongs, whole, in one move.

    Beside and then renamed: a reader arriving mid-write would otherwise find half a
    file, and half a record reads as a gateway that cannot say what version it is, while
    half a schedules file reads as a gateway with no schedules at all.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    beside = target.with_suffix(f".{os.getpid()}.writing")
    beside.write_text(text)
    os.replace(beside, target)


def _read_json(path: Path, missing):
    """What is written there, or `missing` if there is nothing readable to read."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return missing


def schedules_home() -> Path:
    """Where each gateway's schedules are kept — one file per gateway (R-SCH-13).

    Apart from the run directory because a schedule is something a person decided and
    not something a gateway is doing, and one file each because that is the whole of the
    isolation: a gateway reads its own and has no way to name another's. When a gateway
    is an agent, that is exactly one agent's schedules, its own to change and nobody
    else's to run (R-SCH-14).
    """
    return Path(os.environ.get("RUNDESK_SCHEDULES_DIR") or Path.home() / ".rundesk" / "schedules")


def schedules_path(name: str, where: Path | None = None) -> Path:
    return (where or schedules_home()) / f"{checked(name)}.json"


def ran_path(name: str, where: Path | None = None) -> Path:
    """Where what each schedule last did is kept.

    Beside the schedules, not with the run state. Stopping a gateway clears what it is
    *doing*, record and all (R-GW-12) — and what its schedules have done is history, the
    same as the log, which is kept for exactly that reason (R-GW-18). Held with the run
    state it would be erased by every ordinary restart.
    """
    return (where or schedules_home()) / f"{checked(name)}.ran.json"


def scheduled(name: str = DEFAULT_NAME, where: Path | None = None):
    """This gateway's schedules, and any that could not be understood (R-SCH-10).

    Nothing else's, ever: the name is the file, and a name that would reach outside the
    directory it belongs in was refused long before this (R-GW-20).
    """
    from rundesk_cli import schedule

    # Read once, understood here: the same file read two ways is one rule stated twice.
    return schedule.read(written_schedules(name, where))


def _lock_path(name: str, where: Path) -> Path:
    return where / f"{checked(name)}.lock"


def _record_path(name: str, where: Path) -> Path:
    return where / f"{checked(name)}.json"


#: What a declared requirement is called once it is installed, where the two differ.
IMPORTED_AS = {"discord.py": "discord"}


def _declared(root: Path) -> list[str]:
    """What this install says it needs, by the name it is imported under."""
    try:
        lines = (root / "requirements.txt").read_text().splitlines()
    except OSError:
        return []
    wanted = []
    for line in lines:
        line = line.split("#")[0].strip()
        if not line:
            continue
        name = re.split(r"[=<>!\[ ]", line)[0]
        wanted.append(IMPORTED_AS.get(name, name.replace("-", "_")))
    return wanted


def fitness(root: Path | None = None) -> str | None:
    """Why this install cannot run here, or None when it can (R-GW-11).

    Two ways it does not fit, and the second is why this asks rather than compares.

    What rundesk needs beyond the standard library is built against one version of
    Python, so a machine whose python3 has moved on has a virtualenv that no longer
    matches. That much a name tells you. But a virtualenv of exactly the right version
    can still be unusable — a half-finished install, an interrupted update laying a
    release over a running one — and a name check calls that fit. The failure then
    arrives as an import error deep inside a dependency, under a supervisor, in a
    restart loop, hours later, which is the whole thing this exists to prevent. So the
    question asked is whether what was declared can actually be loaded.
    """
    root = root or ROOT
    venv = root / ".venv" / "lib"
    if not venv.is_dir():
        return None  # nothing was needed, so nothing can fail to fit
    mine = f"python3.{sys.version_info.minor}"
    built = sorted(p.name for p in venv.glob("python3.*"))
    if built and mine not in built:
        return (
            f"what rundesk needs was installed for {', '.join(built)}, and this is {mine}. "
            "Run the installer again to rebuild it."
        )
    missing = [name for name in _declared(root) if importlib.util.find_spec(name) is None]
    if missing:
        return (
            f"what rundesk needs is not all there: {', '.join(missing)} cannot be loaded. "
            "Run the installer again to rebuild it."
        )
    return None


def _still_there(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    return True


def started_at(pid: int) -> str | None:
    """When this process started, as the machine reports it — or None if it is gone.

    A number on its own does not identify a process: the machine reissues them, and it
    reissues them from low numbers first after a reboot, which is exactly when a record
    written before that reboot is read. A number *and* a start time do identify one, so
    this is what turns "something is running under that number" into "the thing we left
    running is still there". Asked of `ps` because the standard library has no way to
    ask, and rundesk adds no dependency to find out.
    """
    try:
        said = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True, text=True, timeout=PS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return said.stdout.strip() or None


def _sweep_predecessor(record: Path, log: logging.Logger) -> list[str]:
    """End whatever the last gateway of this name was still running, and say what it was.

    Called once, at the moment a gateway takes the name — so by definition the gateway
    that wrote this record no longer holds the lock, and anything it was running is
    running with nobody owning it. Two things follow from ending it here rather than
    leaving it: the same work cannot end up running twice over once the new gateway is
    asked for it (R-GW-15), and nothing rundesk started outlives rundesk (R-GW-16).

    A recorded group that has already gone is the ordinary case and costs nothing. A
    number that has since been given to something else is the risk this carries; it is
    narrow — the group leader must have exited, been reaped, and had its exact number
    reissued to another leader — and it is named in the contract's open questions.
    """
    try:
        left = json.loads(record.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(left, dict) or not isinstance(left.get("working"), dict):
        return []
    swept = []
    for name, was in left["working"].items():
        pgid, since = (was.get("pgid"), was.get("since")) if isinstance(was, dict) else (was, None)
        if not isinstance(pgid, int):
            log.warning("left '%s' alone: the record does not say what was running", name)
            continue
        if not _still_there(pgid):
            continue  # the ordinary case: it went when its gateway did
        if not since:
            log.warning("left '%s' (group %s) alone: the record cannot prove it is ours", name, pgid)
            continue
        if started_at(pgid) != since:
            # The number now belongs to something that is not ours. Leaving a stray
            # program running is bad; a tree-kill aimed at a stranger because a number
            # came round again is very much worse, and has happened to others.
            log.warning(
                "left '%s' alone: group %s is no longer the process we started", name, pgid
            )
            continue
        log.warning("ending '%s' (group %s), left running by a gateway that is gone", name, pgid)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pgid, sig)
            except OSError:
                break
            time.sleep(ORPHAN_GRACE_SECONDS)
            if not _still_there(pgid):
                break
        swept.append(name)
    return swept


def _sweep_strays(where: Path, mine: str, log: logging.Logger) -> list[str]:
    """End work left by *any* gateway that is gone, not only this one's predecessor.

    A gateway ends what the last holder of its own name left behind — but a name that is
    never taken up again is never anyone's to sweep, and an agent that is renamed or
    removed while it was working leaves programs that nothing would ever end. Every start
    therefore looks at every record, not just its own (R-GW-23).

    A record whose gateway is running is left strictly alone: it is that gateway's, and
    it is the one thing here that is not ours to touch.
    """
    swept: list[str] = []
    for record in sorted(where.glob("*.json")):
        name = record.stem
        if name == mine or _held(name, where):
            continue
        left = _sweep_predecessor(record, log)
        if left:
            log.warning("ended work left by '%s', a gateway nobody has started since: %s",
                        name, ", ".join(left))
            swept += [f"{name}/{one}" for one in left]
        # Asked again, immediately before removing anything: a gateway of this name can
        # have claimed it and written a fresh record while this pass was running, and
        # that record is the live one. Removing it would leave a gateway that is
        # genuinely up with nothing saying so until its next beat.
        if not _held(name, where) and not _anything_left(record):
            record.unlink(missing_ok=True)
    return swept


def _anything_left(record: Path) -> bool:
    """Does this record still name work that is running?"""
    try:
        said = json.loads(record.read_text())
    except (OSError, ValueError):
        return False
    working = said.get("working") if isinstance(said, dict) else None
    if not isinstance(working, dict):
        return False
    for was in working.values():
        pgid = was.get("pgid") if isinstance(was, dict) else was
        if isinstance(pgid, int) and _still_there(pgid):
            return True
    return False


#: How often a running gateway records that it is still there. The lock is what proves it
#: is alive; this says when it last went round, which is what tells an owner a gateway is
#: up but wedged — a distinction no supervisor makes for you.
BEAT_SECONDS = 15.0

#: How long work left by a gateway that died gets to go on its own before it is taken.
#: Short: nobody is waiting on what it was doing, and a gateway is starting up behind it.
ORPHAN_GRACE_SECONDS = 0.5

#: How long to wait on the machine to say when a process started. Short: it is a local
#: question, and a gateway must not be held up starting because an answer is slow.
PS_TIMEOUT_SECONDS = 5.0

#: How often the gateway looks at the clock. Several times a minute, because a schedule
#: is stated to the minute and a tick that only just misses one would lose it entirely.
#: Firing is recorded per minute, so looking more often costs nothing (R-SCH-9).
TICK_SECONDS = 20.0

#: How long stopping may take before the gateway stops waiting for what it is running and
#: goes anyway (R-GW-7). Under what the supervisor allows: launchd sends SIGTERM, waits,
#: and then sends SIGKILL — and being killed is how children get left behind.
STOP_SECONDS = 15.0


class AlreadyRunning(Exception):
    """A gateway of this name is already up (R-GW-4, R-GW-5)."""


class Unfit(Exception):
    """What this install is made of does not fit the machine it is on (R-GW-11)."""


class AlreadyStarted(Exception):
    """This program is already running under this gateway (R-GW-15)."""


class Stopping(Exception):
    """This gateway is going away and is taking no more work (R-GW-6)."""


@dataclass
class Standing:
    """How a gateway looks from outside it — what `status` is made of (R-GW-9)."""

    name: str
    running: bool
    pid: int | None = None
    version: str | None = None
    started: float | None = None
    beat: float | None = None
    #: The same beat, on a clock that only ever goes forward. Compared against ours
    #: because both are counted from when this machine started.
    since_boot: float | None = None

    @property
    def stale(self) -> bool:
        """Running, but not round the loop lately — up and wedged rather than up.

        Measured against a clock that cannot be stepped where one is recorded. The wall
        clock moves when a machine wakes or its time is corrected, and it moves in both
        directions: forward, and a healthy gateway is called wedged; back, and a wedged
        one looks fine.
        """
        if not self.running:
            return False
        if self.since_boot is not None:
            return time.monotonic() - self.since_boot > BEAT_SECONDS * 3
        if self.beat is None:
            return False
        return time.time() - self.beat > BEAT_SECONDS * 3


def _held(name: str, where: Path) -> bool:
    """Is some other process holding this gateway's lock?

    Asked by taking it and giving it straight back. The kernel drops a lock when the
    process holding it dies, so this is true only while a gateway is genuinely alive —
    a record left by one that was killed says nothing (R-GW-10).
    """
    path = _lock_path(name, where)
    if not path.exists():
        return False
    try:
        handle = os.open(path, os.O_RDWR)
    except OSError:
        return False
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as err:
        if err.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
            return True
        raise
    else:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False
    finally:
        os.close(handle)


def standing(name: str = DEFAULT_NAME, where: Path | None = None) -> Standing:
    """What is true of the gateway of this name right now (R-GW-9, R-GW-10)."""
    where = where or home()
    running = _held(name, where)
    try:
        recorded = json.loads(_record_path(name, where).read_text())
    except (OSError, ValueError):
        recorded = {}
    if not isinstance(recorded, dict):
        recorded = {}
    return Standing(
        name=name,
        running=running,
        # Only ever reported for a gateway that is actually there. A pid read off a
        # record whose process is gone is a pid that now belongs to something else.
        pid=recorded.get("pid") if running else None,
        version=recorded.get("version") if running else None,
        started=recorded.get("started") if running else None,
        beat=recorded.get("beat") if running else None,
        since_boot=recorded.get("since_boot") if running else None,
    )


def what_was_scheduled(name: str = DEFAULT_NAME, where: Path | None = None) -> dict:
    """When each of this gateway's schedules last ran, and what became of it (R-SCH-8).

    Read from a file rather than asked of the gateway, because whoever is asking is a
    different process — and kept where history is kept, so it outlives the gateway that
    wrote it.
    """
    said = _read_json(ran_path(name, where), {})
    return {name: did for name, did in said.items() if isinstance(did, dict)} \
        if isinstance(said, dict) else {}


def what_is_running(name: str = DEFAULT_NAME, where: Path | None = None) -> list[str]:
    """What this gateway says it has in flight, by the name each was started under.

    Read from the record rather than asked of the gateway, because whoever is asking is
    a different process — that is the whole reason the record exists.
    """
    # Built before the try: a name that is not usable is a mistake to report, and
    # `NotAName` is a kind of ValueError, so catching one here would swallow the other.
    record = _record_path(name, where or home())
    try:
        said = json.loads(record.read_text())
    except (OSError, ValueError):
        return []
    working = said.get("working") if isinstance(said, dict) else None
    return sorted(working) if isinstance(working, dict) else []


def every(where: Path | None = None) -> list[Standing]:
    """Every gateway this machine knows of, running or not (R-GW-14).

    What the command line answers from, so that managing gateways never means knowing
    their names in advance.
    """
    where = where or home()
    if not where.is_dir():
        return []
    names = sorted({p.stem for p in where.glob("*.lock")} | {p.stem for p in where.glob("*.json")})
    found = [standing(name, where) for name in names]
    # A lock file is never removed — removing one hands its name away (see `release`) —
    # so a name that has been gone a long time still has an empty file sitting there.
    # It is a gateway only if it is running, or if it left a record saying what it left.
    return [it for it in found if it.running or _record_path(it.name, where).exists()]


class Gateway:
    """One gateway, for as long as it runs.

    Owns every program started through it, so that stopping ends all of them and none is
    left behind (R-GW-8). Nothing is shared between two gateways — that is what makes one
    restartable without disturbing the rest.
    """

    def __init__(
        self,
        name: str = DEFAULT_NAME,
        where: Path | None = None,
        root: Path | None = None,
        logs: Path | None = None,
        schedules: Path | None = None,
    ):
        self.name = checked(name)
        self.where = where or home()
        self.logs = logs or logs_home()
        self.schedules = schedules or schedules_home()
        self.log = _recorder(name, self.logs)
        self.root = root or ROOT
        #: What this gateway is running, by the name each was started under. Keyed
        #: rather than collected, because the same work started twice is the failure
        #: this guards (R-GW-15) — two sessions on one conversation answer it twice.
        self.running: dict[str, process.Program] = {}
        #: The minute each schedule last ran, so one runs once for the time it is due
        #: however often the clock is examined (R-SCH-9). Held by the gateway rather
        #: than by the schedules, which remember nothing.
        self._ran: dict[str, object] = {}
        self._outcomes: dict[str, dict] = {}
        self._complained: dict[str, str] = {}
        self._unnamed = itertools.count()
        self._lock: int | None = None
        self._released = False
        #: What this gateway ended on the way in, left by whoever held the name before.
        #: Set here as well as in `claim`, so reading it never depends on having claimed.
        self.swept: list[str] = []
        self._stopping = False
        #: Made when serving begins, never here. On the oldest Python this runs on, an
        #: Event binds to whatever loop exists when it is *constructed* — and a gateway
        #: is constructed before there is a loop, so one made here belongs to no loop
        #: and waiting on it inside `asyncio.run` fails outright. Every in-process test
        #: happened to build its gateway inside a running loop and so never saw this.
        self._stopped: asyncio.Event | None = None

    # -- what it is made of -------------------------------------------------------

    def claim(self) -> None:
        """Become the gateway of this name, or refuse (R-GW-4, R-GW-5, R-GW-11).

        The lock is taken before anything else is written, so a second gateway cannot get
        far enough to overwrite the first one's record.
        """
        if self._lock is not None:
            return  # this gateway already holds its own name; asking twice is not a clash
        unfit = fitness(self.root)
        if unfit:
            self.log.error("refusing to start: %s", unfit)
            raise Unfit(unfit)
        self.where.mkdir(parents=True, exist_ok=True)
        handle = os.open(_lock_path(self.name, self.where), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as err:
            os.close(handle)
            if err.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                self.log.error("refusing to start: a gateway of this name is already running")
                raise AlreadyRunning(
                    f"a gateway named '{self.name}' is already running on this machine"
                ) from err
            self.log.error("refusing to start: could not take the lock (%s)", err)
            raise
        self._lock = handle
        self._released = False
        # Whatever the last gateway of this name was running is, by definition, running
        # with nobody owning it: we now hold the lock it held. Taken before anything of
        # ours starts, so the same work can never be running twice over (R-GW-15, R-GW-16).
        self._pick_up_where_it_left_off()
        self._say_what_was_missed()
        self.swept = _sweep_predecessor(_record_path(self.name, self.where), self.log)
        self.swept += _sweep_strays(self.where, self.name, self.log)
        if self.swept:
            self.log.warning(
                "ended work left running by a gateway that is gone: %s", ", ".join(self.swept)
            )
        try:
            self._record()
        except OSError as err:
            # The lock is only ours while this object lives. Leaving it held by a claim
            # that did not finish would make the name unusable to a retry of itself.
            self.log.error("could not write the record, so did not start: %s", err)
            self.release()
            raise
        self.log.info("up — version %s, pid %s", __version__, os.getpid())

    def _pick_up_where_it_left_off(self) -> None:
        """Take on what the last gateway of this name knew about its schedules.

        Two things are lost otherwise, both on an ordinary restart rather than a crash.
        A schedule that already ran this minute runs again, because what has run is held
        in memory and a new gateway starts with none of it (R-SCH-9). And what each
        schedule last did is wiped by the first record this gateway writes, so cycling a
        gateway erases the only account of what its schedules have been doing (R-SCH-8).
        """
        self._outcomes = what_was_scheduled(self.name, self.schedules)
        for name, did in self._outcomes.items():
            try:
                self._ran[name] = datetime.strptime(did["at"], "%Y-%m-%d %H:%M")
            except (KeyError, TypeError, ValueError):
                continue

    def _say_what_was_missed(self) -> None:
        """Say what fell due while nothing was running (R-SCH-5).

        None of it is run — a time that passed is gone, and running five at once on the
        way up is worse than not running them. But saying nothing at all is the silence
        an owner cannot tell from a schedule that never worked, so the count is written
        down even though nothing is done about it.
        """
        from rundesk_cli import schedule

        left = _read_json(_record_path(self.name, self.where), {})
        since = left.get("beat") if isinstance(left, dict) else None
        if not isinstance(since, (int, float)):
            return
        was_down_since = datetime.fromtimestamp(since)
        for one, _ in [(one, None) for one in scheduled(self.name, self.schedules)[0]]:
            if not one.enabled:
                continue
            missed = schedule.passed_over(one, was_down_since, datetime.now())
            if missed:
                self.log.warning(
                    "schedule '%s' fell due %d time(s) while nothing was running, and was not run late",
                    one.name, missed,
                )

    def release(self, keep_record: bool = False) -> None:
        """Give the name back, leaving nothing that misleads the next start (R-GW-12).

        **The lock file is never removed.** A lock lives on the inode, not the path, so
        unlinking it while another gateway holds it hands the name away: the next claim
        makes a fresh inode and locks that one, and two gateways answer as one identity.
        An unlocked lock file tells a reader nothing, which is what "nothing to find"
        actually requires — `_held` asks the kernel, never the directory.

        What this gateway *wrote* is not removed either: the log is history and outlives
        the gateway, which is why it is kept somewhere else entirely (R-GW-18).

        `keep_record` leaves the record in place for a successor to read. Used when going
        away with work still running, since that record is the only thing naming it.
        """
        if self._lock is None:
            return  # not ours to give back; releasing a name we never took is how two
            # gateways come to hold one, since the unlink would be someone else's
        self._released = True
        if not keep_record:
            _record_path(self.name, self.where).unlink(missing_ok=True)
        fcntl.flock(self._lock, fcntl.LOCK_UN)
        os.close(self._lock)
        self._lock = None

    def _record(self) -> None:
        """What this gateway says about itself, for anything asking from outside.

        Written whole and moved into place rather than written over what is there: a
        reader asking while a beat is landing would otherwise find half a record, and
        report a healthy gateway as one that cannot say what version it is.

        Carries what is in flight, so that a gateway which dies leaves behind the one
        thing its successor needs — the names and process groups of work nobody is left
        owning (R-GW-16).
        """
        now = time.time()
        if not hasattr(self, "_started"):
            self._started = now
        said = {
            "name": self.name,
            "pid": os.getpid(),
            "version": __version__,
            "started": self._started,
            "beat": now,
            # The same moment on a clock that only counts forward from when this machine
            # started. Read back by anything asking whether this gateway is still going
            # round, because a wall clock can be stepped and this cannot.
            "since_boot": time.monotonic(),
            # A number and when it started: see `started_at`. Without the second half a
            # successor cannot tell our leftovers from whatever now shares the number.
            "working": {
                name: {"pgid": program.pid, "since": started_at(program.pid)}
                for name, program in self.running.items()
                if program.pid is not None
            },
        }
        _written_whole(_record_path(self.name, self.where), json.dumps(said))

    # -- what it runs -------------------------------------------------------------

    async def start(
        self,
        argv: Sequence[str],
        as_name: str | None = None,
        env: dict[str, str] | None = None,
        silence: float | None = process.SILENCE_SECONDS,
        on_line: Callable[[str], None] | None = None,
    ) -> process.Result:
        """Run a program as this gateway, and keep hold of it while it runs.

        Everything the gateway starts goes through here, which is the only reason
        stopping can promise to end all of it (R-GW-8).

        `as_name` is what this piece of work is, and starting it while it is already
        running is refused rather than doubled (R-GW-15) — a second session on the same
        conversation would answer it twice, each unaware of the other. Work with no name
        is work that cannot collide, and is given one of its own.
        """
        if self._stopping:
            raise Stopping(f"gateway '{self.name}' is stopping and is taking no more work")
        held = as_name if as_name is not None else f"·{next(self._unnamed)}"
        if held in self.running:
            self.log.warning("refused '%s': it is already running", held)
            raise AlreadyStarted(f"'{held}' is already running under gateway '{self.name}'")
        program = process.Program(
            argv, env=env if env is not None else process.environment(self.where), silence=silence
        )
        # Registered before it is started, so two of the same name racing cannot both get
        # past the check above and into a subprocess.
        self.running[held] = program
        try:
            await program.start()
            self._say()  # now it has a process group worth recording
            self.log.info("started '%s' (group %s)", held, program.pid)
            if self._stopping:
                # Born into a shutdown, and so invisible to it. Registration above happens
                # before there is a process, and going away ends what is *alive* — work
                # still being spawned is neither running to be ended nor stopped from
                # starting, so it came up moments after the gateway had gone and outlived
                # the one thing that would ever end it (R-GW-8). Nothing else can do it:
                # by now `running` has been swept and cleared.
                self.log.warning("ending '%s': it started as the gateway was going away", held)
                await program.end()
            outcome = await program.wait(on_line)
        finally:
            self.running.pop(held, None)
            self._say()
        if outcome.ok:
            self.log.info("'%s' finished", held)
        else:
            # The tail is already in hand, and the reason someone opens this file at all
            # is that something ended in a way they did not expect.
            self.log.warning("'%s' %s — last words: %s", held, outcome.reason, outcome.output[-600:])
        return outcome

    # -- being up, and going away --------------------------------------------------

    async def serve(self) -> int:
        """Stay up until something asks this gateway to stop.

        There is nothing to answer yet: agents and the surfaces they are reached on are
        not built. What this proves today is the part everything else will sit on — that
        a gateway starts once, stays up unattended, says so truthfully, and goes away
        without leaving anything running.
        """
        # Able to be asked to stop *before* it can be found, and in that order. A gateway
        # becomes discoverable the moment it takes its name, and until these are installed
        # the system default for both signals is terminate — so a supervisor asking it to
        # stop inside that window killed it outright: it left its record behind for the
        # next start to trip over, and never ran the shutdown that ends what it started
        # (R-GW-6, R-GW-12). Taking the name is not instant either; it reads what the last
        # gateway of this name left and what its schedules missed, and the window is as
        # wide as that takes on a loaded machine.
        self._stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.ask_to_stop)
        try:
            self.claim()
        except BaseException:
            # A gateway that never got the name leaves nothing of itself on this loop —
            # including handlers, which outlive `serve` and would answer for a gateway
            # that is not there.
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
            raise
        if self._stopping:
            self._stopped.set()  # asked to stop before it got going, or while taking hold
        beating = asyncio.ensure_future(self._beat())
        ticking = asyncio.ensure_future(self._tick())
        try:
            await self._stopped.wait()
        finally:
            beating.cancel()
            ticking.cancel()
            # The handlers stay installed across `_go()`. Removing them here restores the
            # system default, which for these two signals is *terminate* — so a second
            # signal arriving during the shutdown window would kill the gateway outright,
            # orphaning every program it was in the middle of ending. Asking twice is
            # something an impatient operator does; `ask_to_stop` is happy to be asked.
            drained = await self._go()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
        # Not a success if it went with work still running: something is still out there,
        # and a supervisor reading zero would have no way to know (R-GW-7).
        return 0 if drained else 1

    def ask_to_stop(self) -> None:
        """Take no more work, and begin going away (R-GW-6).

        Called from a signal handler, so it does no work itself — a handler that awaited
        anything would be a handler that could be interrupted halfway through.
        """
        self._stopping = True
        if self._stopped is not None:
            self._stopped.set()
        self.log.info("asked to stop")

    async def _go(self) -> bool:
        """End everything, then leave nothing behind (R-GW-8, R-GW-12).

        Bounded, because the supervisor's patience is: past it, this process is killed,
        and a killed gateway leaves its children running — the one outcome worth
        hurrying to avoid. True when everything really did go.
        """
        self._stopping = True
        drained = True
        try:
            await asyncio.wait_for(process.end_all(list(self.running.values())), STOP_SECONDS)
        except asyncio.TimeoutError:
            # Said out loud rather than swallowed: what is left is in its own process
            # group, so this process exiting will not take it, and the next start of
            # this name is the only thing that will.
            drained = False
            still = ", ".join(sorted(self.running)) or "something"
            self.log.error("gave up waiting for %s to stop — it is still out there", still)
        finally:
            if not drained:
                # Written before it is forgotten, and left behind on the way out: this
                # record is the only thing that names what is still running, and the
                # next gateway of this name is the only thing that will ever end it
                # (R-GW-16). Erasing it here is admitting to orphans and then losing them.
                self._say()
            self.running.clear()
            self.release(keep_record=not drained)
        self.log.info("down%s", "" if drained else " — with work still running")
        return drained

    async def _tick(self) -> None:
        """Look at the clock, and start whatever the time has come for (R-SCH-2).

        The gateway is what turns a schedule into work: it knows what it is to start
        something and how to keep hold of it, and the schedules know only when. Nothing
        of what is due is worked out here.

        Unkillable by anything but cancellation, for the same reason the beat is: this is
        a task nobody awaits, so an exception in it would simply end the ticking and
        every schedule would quietly stop running.
        """
        from rundesk_cli import schedule

        await self._over_and_over(
            TICK_SECONDS, lambda: self._fire(schedule, datetime.now()),
            "could not look at the clock: %s",
        )

    def _fire(self, schedule, now) -> None:
        """Start everything due at this moment, and say what happened to each."""
        if self._stopping:
            return
        wanted, refused = scheduled(self.name, self.schedules)
        for name, why in refused:
            if self._complained.get(name) != why:
                self.log.error("schedule '%s' cannot be understood: %s", name, why)
                self._complained[name] = why
        for one in schedule.due(wanted, now, self._ran):
            self._ran[one.name] = now.replace(second=0, microsecond=0)
            asyncio.ensure_future(self._run_scheduled(one))

    async def _run_scheduled(self, one) -> None:
        """Start what a schedule named, under the schedule's own name.

        Under its own name on purpose: that is what makes a schedule refuse to begin
        again while the last one is still going (R-SCH-6), using the guard that already
        exists rather than a second one that could disagree with it.
        """
        if not isinstance(one.run, (list, tuple)) or not one.run:
            self.log.error("schedule '%s' names nothing this gateway can start", one.name)
            return
        self.log.info("schedule '%s' is due", one.name)
        try:
            outcome = await self.start(list(one.run), as_name=f"schedule:{one.name}")
        except AlreadyStarted:
            # R-SCH-7: said, not passed over. A schedule quietly skipping every time
            # because the last run never ended looks exactly like one that is working.
            self.log.warning("schedule '%s' skipped: what it started last time is still running",
                             one.name)
            self._remember(one.name, "still running")
            return
        except Stopping:
            return
        self._remember(one.name, outcome.reason)

    async def _over_and_over(self, every: float, do, failed: str) -> None:
        """Do this at intervals, for as long as the gateway lives.

        Nothing short of being cancelled stops it. Both callers are tasks nobody awaits,
        so an exception in either is raised nowhere at all — it simply ends the task, and
        the gateway carries on having quietly stopped beating, or stopped looking at the
        clock, with nothing to say it had.
        """
        while True:
            try:
                await asyncio.sleep(every)
                do()
            except asyncio.CancelledError:
                raise
            except BaseException as went_wrong:  # noqa: BLE001 — see the docstring
                self.log.warning(failed, went_wrong)

    def _remember(self, name: str, outcome: str) -> None:
        """What a schedule last did, kept where anything asking can read it."""
        self._outcomes[name] = {
            "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "outcome": outcome,
        }
        try:
            _written_whole(ran_path(self.name, self.schedules), json.dumps(self._outcomes, indent=2))
        except OSError as why:
            self.log.warning("could not write down what '%s' did: %s", name, why)

    def _say(self) -> None:
        """Update the record, and never let failing to do so stop the work.

        Silent once the name has been given back: the tasks that were running unwind
        after the gateway has gone, and writing then recreates a record for a gateway
        that no longer exists — one that says nothing is running, which is exactly the
        lie the not-drained path above went to trouble to avoid.
        """
        if self._released:
            return
        try:
            self._record()
        except OSError as err:
            # A gateway that cannot say it is alive is still alive, and stopping serving
            # over it would turn a full disk into an outage.
            self.log.warning("could not update the record: %s", err)

    async def _beat(self) -> None:
        """Say, at intervals, that this gateway is still going round.

        Nothing short of being cancelled stops this. It is a task nobody awaits, so an
        exception in here is not raised anywhere — it simply ends the task, the record
        stops moving, and the gateway is reported wedged for as long as it stays healthy.
        That is the inverse of the fault this exists to reveal, and the worse of the two.
        """
        await self._over_and_over(
            BEAT_SECONDS, self._say, "could not say it is still going round: %s")
