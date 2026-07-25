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
import errno
import fcntl
import itertools
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from rundesk_cli import ROOT, __version__
from rundesk_cli import process

#: The gateway that exists before there are agents to name one after.
DEFAULT_NAME = "gateway"

#: How often a running gateway records that it is still there. The lock is what proves it
#: is alive; this says when it last went round, which is what tells an owner a gateway is
#: up but wedged — a distinction no supervisor makes for you.
BEAT_SECONDS = 15.0

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


def home() -> Path:
    """Where a gateway keeps what it needs while it runs.

    Beside the install rather than inside the source: an update lays a new release over
    the install, and what is running is not part of the release.
    """
    return Path(os.environ.get("RUNDESK_RUN_DIR") or Path.home() / ".rundesk" / "run")


def _lock_path(name: str, where: Path) -> Path:
    return where / f"{name}.lock"


def _record_path(name: str, where: Path) -> Path:
    return where / f"{name}.json"


def fitness(root: Path | None = None) -> str | None:
    """Why this install cannot run here, or None when it can (R-GW-11).

    What rundesk needs beyond the standard library is built against one version of Python.
    A machine whose python3 has moved on since has a virtualenv that no longer matches, and
    the failure that follows is an import error deep inside a dependency — under a
    supervisor, in a restart loop, hours later. Refusing here says what is actually wrong.
    """
    root = root or ROOT
    venv = root / ".venv" / "lib"
    if not venv.is_dir():
        return None  # nothing was needed, so nothing can fail to fit
    mine = f"python3.{sys.version_info.minor}"
    built = sorted(p.name for p in venv.glob("python3.*"))
    if not built or mine in built:
        return None
    return (
        f"what rundesk needs was installed for {', '.join(built)}, and this is {mine}. "
        "Run the installer again to rebuild it."
    )


@dataclass
class Standing:
    """How a gateway looks from outside it — what `status` is made of (R-GW-9)."""

    name: str
    running: bool
    pid: int | None = None
    version: str | None = None
    started: float | None = None
    beat: float | None = None

    @property
    def stale(self) -> bool:
        """Running, but not round the loop lately — up and wedged rather than up."""
        if not self.running or self.beat is None:
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
    )


def every(where: Path | None = None) -> list[Standing]:
    """Every gateway this machine knows of, running or not (R-GW-14).

    What the command line answers from, so that managing gateways never means knowing
    their names in advance.
    """
    where = where or home()
    if not where.is_dir():
        return []
    names = sorted({p.stem for p in where.glob("*.lock")} | {p.stem for p in where.glob("*.json")})
    return [standing(name, where) for name in names]


class Gateway:
    """One gateway, for as long as it runs.

    Owns every program started through it, so that stopping ends all of them and none is
    left behind (R-GW-8). Nothing is shared between two gateways — that is what makes one
    restartable without disturbing the rest.
    """

    def __init__(self, name: str = DEFAULT_NAME, where: Path | None = None, root: Path | None = None):
        self.name = name
        self.where = where or home()
        self.root = root or ROOT
        #: What this gateway is running, by the name each was started under. Keyed
        #: rather than collected, because the same work started twice is the failure
        #: this guards (R-GW-15) — two sessions on one conversation answer it twice.
        self.running: dict[str, process.Program] = {}
        self._unnamed = itertools.count()
        self._lock: int | None = None
        self._stopping = False
        self._stopped = asyncio.Event()

    # -- what it is made of -------------------------------------------------------

    def claim(self) -> None:
        """Become the gateway of this name, or refuse (R-GW-4, R-GW-5, R-GW-11).

        The lock is taken before anything else is written, so a second gateway cannot get
        far enough to overwrite the first one's record.
        """
        unfit = fitness(self.root)
        if unfit:
            raise Unfit(unfit)
        self.where.mkdir(parents=True, exist_ok=True)
        handle = os.open(_lock_path(self.name, self.where), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as err:
            os.close(handle)
            if err.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                raise AlreadyRunning(
                    f"a gateway named '{self.name}' is already running on this machine"
                ) from err
            raise
        self._lock = handle
        self._record()

    def release(self) -> None:
        """Leave nothing of this gateway behind for the next start to find (R-GW-12)."""
        _record_path(self.name, self.where).unlink(missing_ok=True)
        _lock_path(self.name, self.where).unlink(missing_ok=True)
        if self._lock is not None:
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            os.close(self._lock)
            self._lock = None

    def _record(self) -> None:
        """What this gateway says about itself, for anything asking from outside."""
        now = time.time()
        _record_path(self.name, self.where).write_text(
            json.dumps(
                {
                    "name": self.name,
                    "pid": os.getpid(),
                    "version": __version__,
                    "started": getattr(self, "_started", now),
                    "beat": now,
                }
            )
        )
        if not hasattr(self, "_started"):
            self._started = now

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
            raise RuntimeError(f"gateway '{self.name}' is stopping and is taking no more work")
        held = as_name if as_name is not None else f"·{next(self._unnamed)}"
        if held in self.running:
            raise AlreadyStarted(f"'{held}' is already running under gateway '{self.name}'")
        program = process.Program(
            argv, env=env if env is not None else process.environment(self.where), silence=silence
        )
        # Registered before it is started, so two of the same name racing cannot both get
        # past the check above and into a subprocess.
        self.running[held] = program
        try:
            await program.start()
            return await program.wait(on_line)
        finally:
            self.running.pop(held, None)

    # -- being up, and going away --------------------------------------------------

    async def serve(self) -> int:
        """Stay up until something asks this gateway to stop.

        There is nothing to answer yet: agents and the surfaces they are reached on are
        not built. What this proves today is the part everything else will sit on — that
        a gateway starts once, stays up unattended, says so truthfully, and goes away
        without leaving anything running.
        """
        self.claim()
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.ask_to_stop)
        beating = asyncio.ensure_future(self._beat())
        try:
            await self._stopped.wait()
        finally:
            beating.cancel()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
            await self._go()
        return 0

    def ask_to_stop(self) -> None:
        """Take no more work, and begin going away (R-GW-6).

        Called from a signal handler, so it does no work itself — a handler that awaited
        anything would be a handler that could be interrupted halfway through.
        """
        self._stopping = True
        self._stopped.set()

    async def _go(self) -> None:
        """End everything, then leave nothing behind (R-GW-8, R-GW-12).

        Bounded, because the supervisor's patience is: past it, this process is killed,
        and a killed gateway leaves its children running — the one outcome worth
        hurrying to avoid.
        """
        self._stopping = True
        try:
            await asyncio.wait_for(process.end_all(list(self.running.values())), STOP_SECONDS)
        except asyncio.TimeoutError:
            pass  # out of time; the record still goes, and what is left is not ours to wait on
        finally:
            self.running.clear()
            self.release()

    async def _beat(self) -> None:
        """Say, at intervals, that this gateway is still going round."""
        while True:
            await asyncio.sleep(BEAT_SECONDS)
            try:
                self._record()
            except OSError:
                pass  # a record that could not be written is not a reason to stop serving
