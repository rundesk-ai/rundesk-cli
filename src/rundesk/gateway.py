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
import itertools
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from rundesk import ROOT, __version__, data_home
from rundesk import activity
from rundesk import dependencies
from rundesk.gateway_log import (  # noqa: F401 — several are reached as gateway.<name>
    DEFAULT_NAME, EVERY_LOG, GATEWAY_LOG, LOG_SOURCES, MACHINE_LOG, NotAName,
    channel_note, checked, log_path, log_sources, logs_home, note, recorder,
)
from rundesk.recovery import (  # noqa: F401 — reached as gateway.<name> by agent.py and the suites
    interrupted_path, note_interrupted, remembered, resolve_interruption,
    what_was_interrupted,
)
from rundesk.welcome import (  # noqa: F401 — reached as gateway.<name> by commands and the suites
    WELCOMED, forget_welcomed, owed_a_welcome, remember_no_one_welcomed, remember_welcomed,
    welcomed_path,
)
from rundesk.durable import UNREADABLE, Unreadable, read, read_json, write_whole
from rundesk import process
from rundesk import restart_request
from rundesk import secret
from rundesk import schedule
from rundesk import store
from rundesk import update_request
from rundesk import updater


#: What a schedule is doing, in the two words that are not a program's own outcome.
#: `STARTED` is written before the run begins and means nothing more than that — a
#: gateway that dies leaves it standing, so it is the one outcome that must be reconciled
#: rather than believed. `INTERRUPTED` is what it becomes.
STARTED = "started"
INTERRUPTED = "interrupted"
#: What a run nobody is doing is settled as when the gateway that began it is gone. Says
#: the gateway went rather than that the turn broke, because those are different news and
#: only one of them means somebody should look at something.
ABANDONED_WHY = "the gateway that began this turn went without settling it"

#: What a schedule's work is called while a gateway holds it. One place, because a
#: reconciliation matching an outcome to the work it named has to spell it the same way
#: the start did, and two spellings would silently match nothing.
SCHEDULED_AS = "schedule:"
UPDATE_AS = "update:"

#: How a scheduled program is told which schedule started it. Read by `rundesk ask`, which is
#: the one program a schedule is likely to name, so a turn the clock started says so in the
#: account rather than looking like one somebody typed.
SCHEDULE_IS = "RUNDESK_SCHEDULE"

#: What a channel's work is called while a gateway holds it. Named like a schedule's, so
#: what `status` shows and what a sweep ends read the same way for both.
CHANNEL_AS = "channel:"

#: How long to leave a channel that stopped before starting it again. Long enough not to
#: hammer a platform that is refusing us, short enough that an owner does not notice.
CHANNEL_AGAIN_SECONDS = 10.0


def home() -> Path:
    """Where a gateway keeps what it needs while it runs.

    Beside the install rather than inside the source: an update lays a new release over
    the install, and what is running is not part of the release.
    """
    return Path(os.environ.get("RUNDESK_RUN_DIR") or data_home() / "run")


#: What a file rundesk keeps turned out to be when it went to read it. `MISSING` and
#: `UNREADABLE` are the same absence and opposite decisions: nothing is lost by writing over
#: what was never written, and everything is lost by writing over what still holds the
#: owner's schedules as recoverable text (R-SCH-17).


def _lock_path(name: str, where: Path) -> Path:
    return where / f"{checked(name)}.lock"


def _record_path(name: str, where: Path) -> Path:
    return where / f"{checked(name)}.json"


#: A name no gateway would be given, used to read what each path helper adds to a name off
#: the path it hands back. It is the shortest thing `checked` accepts.
_PROBE = "0"

#: What is written beside a name by something other than a path helper: the guard a change
#: is held under, the file a whole write is staged in, and the two the machine captures of a
#: gateway that never reached its own log.
ALSO_WRITTEN = frozenset({".changing", ".writing", ".out", ".err"})


def reserved_suffixes() -> frozenset[str]:
    """Everything a gateway writes after its own name.

    Asked of the helpers that build the paths rather than listed here, because a list of
    these is a list that stops being true: a gateway named `foo.ran` and one named `foo`
    want one file between them, and the way that comes back is a sidecar added later that
    nobody thought to write down twice.

    Read by whatever decides a name is usable. Nothing here refuses one — a gateway's names
    are what they already are, and narrowing them is a separate decision from choosing what
    an agent may be called.
    """
    where = Path(os.sep)
    made = (
        _lock_path(_PROBE, where), _record_path(_PROBE, where), log_path(_PROBE, where),
        interrupted_path(_PROBE, where),
    )
    return frozenset({path.name[len(_PROBE):] for path in made} | ALSO_WRITTEN)


def fitness(root: Path | None = None) -> str | None:
    """Why this install cannot run here, or None when it can (R-GW-11).

    Three ways it does not fit, and the second is why this asks rather than compares.

    What rundesk needs beyond the standard library is built against one version of
    Python, so a machine whose python3 has moved on has a virtualenv that no longer
    matches. That much a name tells you. But a virtualenv of exactly the right version
    can still be unusable — a half-finished install, an interrupted update laying a
    release over a running one — and a name check calls that fit. The failure then
    arrives as an import error deep inside a dependency, under a supervisor, in a
    restart loop, hours later, which is the whole thing this exists to prevent. So the
    question asked is whether what was declared can actually be loaded.

    **And which version of it** (R-GW-41). Asking only whether a name imports made
    `discord.py==2.7.1` satisfied by 2.0.0 read as a perfect fit, so a release that
    bumped what it needs ran against what was already there and failed wherever the
    difference bit — with nothing anywhere reporting a mismatch. What is declared is read
    by `dependencies`, which is also what an update and the installer build against, so
    the question and the answer cannot come apart.
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
    # Asked before the version question, because a name that will not load is the plainer
    # complaint and the one an owner can act on without knowing what a specifier is.
    missing = [one.imported for one in dependencies.declared(root)
               if importlib.util.find_spec(one.imported) is None]
    if missing:
        return (
            f"what rundesk needs is not all there: {', '.join(missing)} cannot be loaded. "
            "Run the installer again to rebuild it."
        )
    short = dependencies.unsatisfied(root)
    if short:
        return (
            f"what rundesk needs is not what is installed: {'; '.join(short)}. "
            "Run the installer again to rebuild it."
        )
    return None


def _group_went(pgid: int, patience: float) -> bool:
    """Has this whole group gone — waited for, not sampled once.

    Asked repeatedly because a signal is not an ending. What we are signalling is not our
    child, so nothing here reaps it: it is handed to whatever adopts orphans, and that
    happens when that machine gets round to it. Until it does, the group answers as
    present, and a single look a fixed moment later reports a group that is on its way out
    as one that would not go — which is how the same sweep passed here and failed on
    another machine, on nothing but timing.
    """
    deadline = time.monotonic() + patience
    while _still_there(pgid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _still_there(pgid: int) -> bool:
    """Is anything left in this process group?

    Only *gone* counts as gone. Being unable to reach a group is not the same as there
    being no group, and reading them alike here was the same fault `process` documents at
    length on its own side: a group we may not signal was reported as absent, so the sweep
    passed over it — and the record naming it was then deleted as having nothing left to
    find (R-GW-16). Anything else going wrong is not evidence of absence either.
    """
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False  # the group is empty: everything in it has gone
    except OSError:
        return True   # unreachable, or unanswerable — not the same as not there
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


def _ask_group(pgid: int, sig: int) -> bool:
    """Ask this process group to go, and say whether the asking got through.

    Already gone is the thing being asked for, so it counts as through. Anything else — a
    permission, a machine that will not — is a failure to ask, and an escalation that never
    reached its second signal has not been carried out (R-GW-28).
    """
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return True   # it went between being found and being asked, which is the ask granted
    except OSError:
        return False
    return True


@dataclass
class Left:
    """What became of one piece of work a gateway that is gone left running."""

    #: rundesk dealt with this entry and may stop naming it.
    swept: bool
    #: It is definitely gone. Distinct from `swept`: everything that could be done to a
    #: group can have been done and something in it still answer (R-GW-17).
    ended: bool
    #: What to write down about it, in the owner's words (R-GW-23).
    why: str
    #: Still out there, still ours, and nothing left naming it but our record.
    keep: bool


def _end_left_running(name: str, was, log: logging.Logger, present=None, started=None,
                      ask=None, gone_within=None) -> Left:
    """End one piece of work a gateway that is gone left running, and say what became of it.

    Every question this asks of the live world — is the group there, when did it start, will
    it take a signal, has it gone yet — arrives as an operation rather than being reached
    for, so the whole decision table can be scripted (R-GW-28). The cases that matter most
    are the ones a real process cannot be made to produce on demand: a signal the machine
    refuses, and an identity that changes between two looks.

    Failing to send, or stopping short of the second signal, leaves the entry unswept and
    kept. Everything else is reported as swept, and `ended` carries whether it really went.
    """
    present = present or _still_there
    started = started or started_at
    ask = ask or _ask_group
    gone_within = gone_within or _group_went

    pgid, since = (was.get("pgid"), was.get("since")) if isinstance(was, dict) else (was, None)
    if not isinstance(pgid, int):
        log.warning("left '%s' alone: the record does not say what was running", name)
        return Left(False, False, "the record does not say what was running", False)
    if not present(pgid):
        # The ordinary case: it went when its gateway did. Nothing to end, and still work
        # that never finished, which is the thing nobody was being told.
        return Left(False, True, "the gateway it was running under is gone", False)
    if not since:
        log.warning("left '%s' (group %s) alone: the record cannot prove it is ours", name, pgid)
        # Still there, and still unfinished. Kept for the same reason as one that would not
        # go: the record we are about to write replaces the only thing naming it.
        return Left(False, False, "the record could not prove it was ours to end", True)
    now = started(pgid)
    if now is None:
        # **Asked, and not told — which is not "it is a stranger".** `started_at` answers
        # None for a `ps` that timed out or a fork that failed, and a loaded machine at
        # boot is both when that happens and when work gets left behind. Read as a
        # mismatch it took the branch below: the group was left running *and* the record
        # naming it dropped, so nothing could ever find it again — the very loss
        # `_anything_left` refuses one function up. Kept for the same reason a record with
        # no fingerprint at all is kept.
        log.warning("left '%s' (group %s) alone: the machine would not say when it started",
                    name, pgid)
        return Left(False, False, "the machine would not say whether it is ours", True)
    if now != since:
        # The number now belongs to something that is not ours. Leaving a stray program
        # running is bad; a tree-kill aimed at a stranger because a number came round again
        # is very much worse, and has happened to others. Not kept, either — naming a
        # stranger in our record is how the next start comes to aim at it.
        log.warning("left '%s' alone: group %s is no longer the process we started", name, pgid)
        return Left(False, False, "its group now belongs to something that is not ours", False)

    log.warning("ending '%s' (group %s), left running by a gateway that is gone", name, pgid)
    gone = carried_out = False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not ask(pgid, sig):
            break
        if gone_within(pgid, ORPHAN_GRACE_SECONDS):
            gone = carried_out = True
            break
    else:
        # Both were sent and it was still answering at the last look. Asked once more
        # rather than waited on again: the kill lands inside the pause that just elapsed.
        carried_out = True
        gone = not present(pgid)
    if not carried_out:
        # The escalation stopped short, so the group has not had everything done to it that
        # can be. Counting it swept would report a success rundesk did not earn (R-GW-28),
        # and dropping it would throw away the only record naming a live process tree.
        log.error("could not end '%s' (group %s): the machine would not take the signal",
                  name, pgid)
        return Left(False, False, "rundesk could not end it", True)
    if not gone:
        # Asked and then insisted, and something still answers. Said out loud, because a
        # group that outlives being killed is not a thing to pass over — but still counted
        # as swept, because everything that can be done to it has been. What answers may be
        # no more than a leader nobody has reaped yet, and whether a reaped-but-not-
        # collected leader answers at all differs by machine: the same sweep looked
        # complete on one and unfinished on another, on that alone.
        log.error("ended '%s' (group %s), and something in it still answers", name, pgid)
    return Left(True, gone, "the gateway it was running under is gone", False)


def _sweep_predecessor(record: Path, log: logging.Logger, noting=None,
                       surviving: dict | None = None) -> list[str]:
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
    left = read_json(record, None)
    if not isinstance(left, dict) or not isinstance(left.get("working"), dict):
        return []
    swept = []
    # Every piece of work in here was in flight when its gateway went, so every one of
    # them is interrupted — including the ones there is nothing left to end. What differs
    # is only whether it is definitely gone, and that is what `ended` carries (R-GW-23).
    said = noting if noting is not None else (lambda *_args, **_kw: None)
    for name, was in left["working"].items():
        became = _end_left_running(name, was, log)
        pgid = was.get("pgid") if isinstance(was, dict) else was
        said(name, became.why, pgid if isinstance(pgid, int) else None, became.ended)
        if became.swept:
            swept.append(name)
        elif became.keep and surviving is not None:
            surviving[name] = was
    return swept


def _sweep_strays(where: Path, mine: str, log: logging.Logger,
                  logs: Path | None = None) -> list[str]:
    """End work left by *any* gateway that is gone, not only this one's predecessor.

    A gateway ends what the last holder of its own name left behind — but a name that is
    never taken up again is never anyone's to sweep, and an agent that is renamed or
    removed while it was working leaves programs that nothing would ever end. Every start
    therefore looks at every record, not just its own (R-GW-23).

    A record whose gateway is running is left strictly alone: it is that gateway's, and
    it is the one thing here that is not ours to touch. Its name is *taken* for the whole
    reckoning rather than asked about first, because the answer to a question stops being
    true the moment after it is given (R-GW-29).
    """
    swept: list[str] = []
    for record in sorted(where.glob("*.json")):
        name = record.stem
        if name == mine:
            continue
        with _holding_name(name, where) as taken:
            if not taken:
                continue  # live, or unanswerable — and neither is ours to touch
            # Into *that* gateway's file, not ours: the work was its, and its name is where
            # anything asking after it would look (R-GW-21, R-GW-23).
            left = _sweep_predecessor(
                record, log,
                lambda work, why, pgid, ended, whose=name: note_interrupted(
                    whose, logs, work, why, pgid, ended),
            )
            if left:
                log.warning("ended work left by '%s', a gateway nobody has started since: %s",
                            name, ", ".join(left))
                swept += [f"{name}/{one}" for one in left]
            # No second look needed: nothing of this name could have claimed, recorded or
            # started anything while the name was held here.
            if not _anything_left(record):
                record.unlink(missing_ok=True)
    return swept


@contextlib.contextmanager
def _holding_name(name: str, where: Path):
    """Take another gateway's name, and keep it for as long as reckoning with it takes.

    Taken and *kept*, rather than asked about. `_held()` answers about the moment it was
    called, and between that answer and a signal a gateway of that name can claim the name
    and start work — so an ordinary start ended a live agent's whole process tree
    (R-GW-29). A gateway claiming holds this same lock across its own predecessor sweep and
    its first record, so of the two, one always finds the name taken.

    Yields whether it was taken. A name that cannot be taken belongs to a gateway that is
    live, or to one this process cannot ask about, and both are left alone. That is the
    opposite default to `standing()`, which is reporting and answers "not running" when it
    cannot tell (R-GW-9) — being wrong there costs a misleading line, and being wrong here
    ends somebody else's session.
    """
    path = _lock_path(name, where)
    try:
        handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield False
        return
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        os.close(handle)


def _anything_left(record: Path) -> bool:
    """Does this record still name work that is running?

    The one caller deletes the record when this says no, so an unreadable one answers yes
    (R-GW-26). A record is the only thing naming a process group nobody owns; reading "I
    could not tell" as "there is nothing there" throws away the sole means of ever finding
    it again, and the sweep that could not read it reported having tidied up.
    """
    state, said = read(record)
    if state == UNREADABLE:
        return True
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

#: How often the gateway looks for a role run to carry and a parent to tell. Close to
#: the beat rather than to the clock: an agent that just delegated is waiting for work to
#: begin, and a parent whose worker has finished is waiting to be told (R-ROL-15).
ROLE_SECONDS = 5.0

#: How often expired role bundles are cleared. Once an hour, because retention is
#: measured in days and what a sweep finds on a machine where nothing has expired is
#: nothing (R-ROL-12).
ROLE_SWEEP_SECONDS = 3600.0

#: How long stopping may take before the gateway stops waiting for what it is running and
#: goes anyway (R-GW-7). Under what the supervisor allows: launchd sends SIGTERM, waits,
#: and then sends SIGKILL — and being killed is how children get left behind.
STOP_SECONDS = 15.0

#: How often what an agent may do is looked at, so its owner is told when it changes
#: (R-CH-32). Unhurried on purpose: a grant is changed by hand at human pace, and the look
#: is one directory listing — but a change made a minute before somebody uses the agent
#: should already have been said.
SKILLS_SECONDS = 10.0

#: How often who a channel allows is looked at, so somebody newly allowed is greeted
#: (R-CH-33). The same unhurried pace as the skills look and for the same reason — this is
#: one small file per channel — but what it may *start* is a whole turn, which is why each
#: person is attempted only once for as long as one gateway is up.
WELCOME_SECONDS = 10.0


class AlreadyRunning(Exception):
    """A gateway of this name is already up (R-GW-4, R-GW-5)."""


class Unfit(Exception):
    """What this install is made of does not fit the machine it is on (R-GW-11)."""


class AlreadyStarted(Exception):
    """This program is already running under this gateway (R-GW-15)."""


class Stopping(Exception):
    """This gateway is going away and is taking no more work (R-GW-6)."""


class Unrunnable(Exception):
    """This gateway was not given what the work it was asked to start needs.

    A schedule that asks a turn needs an agent, a brain and an account to write into, and a
    gateway is handed the way to all three rather than reaching for them. One that was handed
    nothing says so where it can be read, rather than passing the minute over in silence.
    """


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
    recorded = read_json(_record_path(name, where), {})
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


#: What the two readers below answer with when the record is there and could not be read.
#: **Named rather than left empty**, because `read_json` cannot tell "no record" from "a
#: record nobody could read" and five callers *decide* on that answer: a queued restart and
#: an interactive one stop the gateway, an update replaces this install, and a restore swaps
#: the owner's whole data tree (R-UPD-23). Every one of them treats a non-empty answer as
#: "refuse", so saying this is what makes an unreadable record safe. `_anything_left` below
#: has taken the same position since work could be interrupted at all.
CANNOT_BE_READ = "(the record could not be read)"


def could_not_be_read(working) -> bool:
    """Is this answer a record nobody could read, rather than a gateway doing nothing?

    Asked where a count is about to be printed. A caller that renders `len()` would
    otherwise report one process that may not exist, which is the same untruth the empty
    answer was — just the other way up.
    """
    return CANNOT_BE_READ in (working or ())


def what_is_running(name: str = DEFAULT_NAME, where: Path | None = None) -> list[str]:
    """What this gateway says it has in flight, by the name each was started under.

    Read from the record rather than asked of the gateway, because whoever is asking is
    a different process — that is the whole reason the record exists.
    """
    # Built first: a name that is not usable is a mistake to report, and `NotAName` is a
    # kind of ValueError, so a reader that swallowed one would swallow the other.
    where = where or home()
    record = _record_path(name, where)
    state, said = read(record)
    # Resolved once, above: this used to be handed the caller's unresolved `where`, and
    # `activity.active(None)` answers `[]` — so asking the ordinary way reported no turns
    # however many were running.
    turns = [f"turn:{row['run']}" for row in activity.active(where)]
    if state == UNREADABLE:
        return [CANNOT_BE_READ, *turns]
    working = said.get("working") if isinstance(said, dict) else None
    programs = sorted(working) if isinstance(working, dict) else []
    return programs + turns


def what_is_working(name: str = DEFAULT_NAME, where: Path | None = None) -> dict:
    """Safe process details for persistent work directly owned by a gateway.

    A record that cannot be read says so rather than answering with nothing: whether it is
    safe to stop this gateway is decided on this, and "I could not tell" is not "idle".
    """
    state, said = read(_record_path(name, where or home()))
    if state == UNREADABLE:
        return {CANNOT_BE_READ: {"pgid": None, "since": None}}
    working = said.get("working") if isinstance(said, dict) else None
    return dict(working) if isinstance(working, dict) else {}


def what_is_turning(name: str = DEFAULT_NAME, where: Path | None = None) -> list[dict]:
    """Safe identities for provider turns belonging to this agent."""
    return activity.active(where)


@contextlib.contextmanager
def holding(name: str, where: Path | None = None):
    """Take this gateway's name and keep it, for anything that must not act while it runs.

    The public way to `_holding_name`, for a caller that is about to move or delete what a
    gateway of this name is using. Asking `standing()` first is not enough on its own: it
    answers about the moment it was called, and a gateway can claim the name between that
    answer and the act. Holding the name is what makes the two one decision.
    """
    with _holding_name(name, where or home()) as held:
        yield held


def forget(name: str, where: Path | None = None, logs: Path | None = None,
           history: bool = False) -> list[str]:
    """Take away what rundesk keeps for a gateway of this name (R-GW-31).

    Called only once the gateway is proven stopped and its job is gone. This deletes, and
    deleting what something is still using is the one thing removal must not do.

    **The lock is taken before it is unlinked, and left alone if it cannot be.** A lock
    lives on the inode and not on the path, so unlinking one another process is holding
    hands the name away: the next claim makes a fresh inode, locks that, and two gateways
    answer as one identity — which is why `release` never removes one. Holding it first is
    the whole of what makes removing it safe, and a name that cannot be held belongs to
    something that is using it.

    `history` also takes what the gateway wrote. Kept otherwise, for the reason an uninstall
    keeps it: it is the owner's, and it is worth most long after the gateway that wrote it is
    gone (R-GW-18, R-RM-10).

    What a schedule is, what it last did and when a gateway of this name was last up are all
    rows an agent keeps, and go with that agent's records rather than from here.
    """
    where = where or home()
    taken = []
    # The record is what it was doing, which is not an account of anything.
    record = _record_path(name, where)
    if record.exists():
        record.unlink(missing_ok=True)
        taken.append(record.name)
    lock = _lock_path(name, where)
    if lock.exists():
        with _holding_name(name, where) as held:
            if held:
                lock.unlink(missing_ok=True)
                taken.append(lock.name)
    if history:
        # What a schedule is and what it last did are rows, and go with the agent's own
        # records rather than from here. What is left is the log, and the account of what
        # never finished, which is the one thing beside a schedule that is still a file.
        kept = (log_path(name, logs), interrupted_path(name, logs),
                interrupted_path(name, logs).with_suffix(".changing"))
        for path in kept:
            if path.exists():
                path.unlink(missing_ok=True)
                taken.append(path.name)
    return sorted(taken)


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
        reachable=(),
        agents: Path | None = None,
        records=None,
        asking=None,
        roles=None,
        granted=None,
        secrets_resolving=None,
    ):
        #: How the values every program this gateway starts is given are produced. An
        #: argument, and resolved at call time rather than bound here, so a suite drives
        #: the whole of this with no vault, no keeper and no store on the machine — and so
        #: a gateway that keeps none still asks the same question the same way.
        self._secrets_resolving = secrets_resolving
        self.name = checked(name)
        self.where = where or home()
        self.logs = logs or logs_home()
        #: Where agents are kept, carried so that a program this gateway starts reads the
        #: same root it does. A path it was handed and never looks inside: a gateway goes
        #: on knowing nothing of agents, and this is not knowledge of whose work it holds
        #: (R-AGT-9). Left unset, `process.environment` forwards whatever this process was
        #: given, which is the same answer by a shorter route.
        self.agents = agents
        #: Where this gateway's schedules are, and what each last did. Handed over already
        #: opened, the way the surfaces it holds are: a gateway reads rows out of it and
        #: never asks whose they are, so it goes on knowing nothing of agents.
        #:
        #: **None is a gateway with no schedules, and that is a whole gateway.** Schedules
        #: are something an agent keeps, so a name that is not an agent has none — it still
        #: starts, holds its lock, writes its log and ends what it started; the clock simply
        #: has nothing to start for it.
        self.records = records
        self.log = recorder(name, self.logs)
        self.root = root or ROOT
        #: What this gateway is running, by the name each was started under. Keyed
        #: rather than collected, because the same work started twice is the failure
        #: this guards (R-GW-15) — two sessions on one conversation answer it twice.
        self.running: dict[str, process.Program] = {}
        #: When each running program started, asked once and then kept (R-GW-30). A start
        #: time cannot change, so asking again can only make the answer worse — and the
        #: asking is a subprocess that fails on exactly the loaded machine where work gets
        #: left behind. One unanswered look replaced a fingerprint that was correct with
        #: nothing, and every later gateway then refused to touch the group for good.
        self._known_since: dict[str, str | None] = {}
        #: The minute each schedule last ran, so one runs once for the time it is due
        #: however often the clock is examined (R-SCH-9). Held by the gateway rather
        #: than by the schedules, which remember nothing.
        self._ran: dict[str, object] = {}
        self._complained: dict[str, str] = {}
        self._unnamed = itertools.count()
        self._lock: int | None = None
        self._released = False
        #: One gateway lifetime, handed to every adapter it holds open. Two adapters may
        #: belong to this same gateway and each may reconnect, while a successor must be
        #: distinguishable even though it uses the same run directory.
        self._instance = uuid.uuid4().hex
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
        #: The surfaces this agent is reachable on, resolved by whoever knows what an
        #: agent is and handed over already made (R-CAD-6). Handed over rather than
        #: looked up, for the reason every other directory is: a gateway that reached
        #: back for an agent would end the one rule this file is built on.
        self.reachable = list(reachable)
        #: Whether this gateway was asked to come back rather than merely to stop.
        self._come_back = False
        #: How to admit a turn for a schedule that asks one, handed over already made by
        #: whoever knows what an agent is. `None` is a gateway that can start programs and
        #: not turns, which is what one with no agent behind it is.
        self.asking = asking
        #: What this agent may do, asked afresh each time rather than kept, and handed over
        #: already made by whoever knows what an agent is — a gateway never reaches back for
        #: one (R-AGT-9). Asked rather than remembered because a grant is a link on disk that
        #: anything on the machine may add or take away while this gateway runs, which is the
        #: whole reason its owner is told (R-CH-32).
        #:
        #: **None is a name that is not an agent**, which has no grants and so nothing to
        #: watch — the same whole gateway a name with no schedules is.
        self.granted = granted
        #: What the owner is owed about their agent's skills and the list to write down
        #: once they have it, or None for nothing owed. Held here rather than in the loop
        #: so a surface that is not up yet is a wait: the news survives until it is
        #: actually delivered, and only then is it written down.
        self._skills_owed: tuple[list[str], tuple[str, ...]] | None = None
        #: The last complaint about looking at them, so a directory that cannot be read
        #: is said once rather than every ten seconds for as long as the gateway is up.
        self._skills_complaint: str | None = None
        #: Everybody this gateway has asked the agent to greet, whether or not it worked
        #: (R-CH-33). Held for this process's lifetime and never written down: what is
        #: written down is what was actually *delivered*, and this is what stops a brain
        #: that cannot run being asked for the same turn every ten seconds until somebody
        #: notices. A gateway that starts again tries each of them once more.
        self._welcome_attempted: set[str] = set()
        #: The last complaint about reading one of those records, said once for the same
        #: reason the skills one is.
        self._welcome_complaint: str | None = None
        #: Which schedules have a turn in flight. Kept apart from `running`, which holds
        #: programs a shutdown ends: a turn's brain is not a program this gateway started.
        self._asked_for: set[str] = set()
        #: How this gateway carries the role runs its agent has admitted, and tells
        #: their parents. Handed over already made by whoever knows what an agent is, the
        #: way `asking` is; `None` is a gateway with no agent behind it, which simply
        #: never carries one (R-ROL-4).
        self.roles = roles
        #: Which role roots have a turn in flight, by the run each is carrying. Kept
        #: apart from `running` for the same reason `_asked_for` is: a turn's brain is not
        #: a program this gateway started, and the same root started twice would be one
        #: execution answering its parent twice.
        self._role_tasks: dict = {}
        #: Which check-in each role run in flight has already been told about, by run. A
        #: number rather than a moment, so a gateway looking every five seconds says a
        #: run is still working once per window rather than once per look (R-ROL-36).
        self._role_checked: dict = {}
        #: Backend update turns this gateway owns. They remain pending durably until one
        #: returns, and shutdown cancels and awaits every task here.
        self._update_turn_tasks: dict[int, asyncio.Task] = {}
        #: Once a successful read finds none, none can appear until this gateway is down:
        #: update migrations run only inside the update window that stands gateways down.
        self._update_turns_drained = False
        #: The surfaces that are up right now, by name — what is held open and answering.
        #: `reachable` is what an agent *has*; this is what can be said something on, and the
        #: two differ for as long as an adapter is down and being started again.
        self._reached: dict = {}
        #: Which schedules have said on a surface that they have started and not yet said
        #: what they came to, and the conversation each notice went to (R-SCH-46). A notice
        #: with no outcome under it is worse than no notice, so every way out of a run that
        #: can still reach the surface answers whatever is in here — and a run whose gateway
        #: went is one whose notice dies with the process that could have answered it, which
        #: is why this is memory and not a record.
        #:
        #: The conversation is carried rather than resolved twice: where a schedule with no
        #: place named reports is the newest conversation on the surface, and a run long
        #: enough to be worth announcing is long enough for somebody to have spoken in
        #: another room. `None` where the notice went by a place word instead.
        self._announced: dict = {}

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
        # What the predecessor left that would not go. Kept, because the record we are
        # about to write replaces the one naming it, and `_sweep_strays` skips our own
        # name — so dropping it here makes a live process group permanently invisible.
        self._inherited: dict = {}
        self.swept = _sweep_predecessor(
            _record_path(self.name, self.where), self.log,
            lambda work, why, pgid, ended: note_interrupted(
                self.name, self.logs, work, why, pgid, ended),
            self._inherited,
        )
        self.swept += _sweep_strays(self.where, self.name, self.log, self.logs)
        if self.swept:
            self.log.warning(
                "ended work left running by a gateway that is gone: %s", ", ".join(self.swept)
            )
        self._reconcile_what_never_finished()
        self._settle_runs_nothing_is_doing()
        try:
            self._record()
        except OSError as err:
            # The lock is only ours while this object lives. Leaving it held by a claim
            # that did not finish would make the name unusable to a retry of itself.
            self.log.error("could not write the record, so did not start: %s", err)
            self.release()
            raise
        self.log.info("up — version %s, pid %s", __version__, os.getpid())

    def _schedules(self) -> list:
        """Every schedule this gateway has, as rows — and none at all where it has no
        records, which is what a gateway that is not an agent is.

        The one reader, so every caller here is asking the same question of the same place,
        and the one place a failure to read them is turned into an answer.

        **Nothing is ever mistaken for having no schedules.** Records that are there and
        cannot be read hold every schedule an owner ever wrote (R-SCH-17), so this refuses
        rather than returning none — and its callers each decide what to do about that,
        which for a gateway is to keep running and say so once (R-SCH-18).
        """
        if self.records is None:
            return []
        try:
            return self.records.schedules()
        except Exception as why:  # noqa: BLE001 — a records boundary; see below
            # Broad on purpose. What can go wrong belongs to whatever holds the records and
            # a gateway does not know what that is; naming those types here would be the one
            # place it learned. Every one of them means the same thing to every caller
            # below — these cannot be read — so it is said in rundesk's own words and once.
            raise Unreadable(f"this agent's schedules could not be read: {why}") from why

    def _last_seen(self):
        """When a gateway of this name was last up, as the wall clock a schedule is stated
        in — or None where there is nothing to measure a gap against.

        **Converted here, so nothing downstream can forget to.** What an agent keeps is UTC, so
        two agents' records sort against each other whatever machine wrote them; a cron field is
        the machine's own local time. What comes back says which of the two it is, which makes
        comparing them directly inexpressible rather than merely discouraged — an error
        invisible for most of the year and wrong by an hour for the rest of it.

        Nothing here reads a stored format. A gateway is handed its records and asks them
        questions; how a moment is written down is theirs.
        """
        if self.records is None:
            return None
        try:
            when = self.records.last_seen()
        except Exception as why:  # noqa: BLE001 — a records boundary; see `_schedules`
            raise Unreadable(f"when this agent was last up could not be read: {why}") from why
        return when.astimezone().replace(tzinfo=None) if when is not None else None

    def _pick_up_where_it_left_off(self) -> None:
        """Take on what the last gateway of this name knew about its schedules.

        A schedule that already ran this minute would otherwise run again: what has run is
        held in memory and a new gateway starts with none of it (R-SCH-9). What each
        schedule last did needs no picking up now that it is a row — it was a file the first
        record of a new gateway used to write over, which is how cycling a gateway erased
        the only account of what its schedules had been doing (R-SCH-8).
        """
        try:
            rows = self._schedules()
        except Unreadable as why:
            # Said, and it still starts (R-SCH-17). A gateway that refused to take its name
            # because one thing it keeps is broken would take down everything else it does.
            self.log.error("could not pick up what its schedules last did: %s", why)
            return
        for row in rows:
            try:
                self._ran[row["name"]] = datetime.strptime(
                    row["last_auto_run_at"], schedule.A_MINUTE)
            except (KeyError, TypeError, ValueError):
                continue

    async def _hold_channels(self) -> None:
        """Hold every surface this agent is reachable on open, for as long as it is up.

        One task per channel, each started through `start` — so ending it when the gateway
        goes, sweeping it if the gateway does not, and naming it in the record are all
        already done and none of it is written twice (R-CAD-6).
        """
        if not self.reachable:
            return
        await asyncio.gather(*(self._hold_one(one) for one in self.reachable))

    async def _hold_one(self, one) -> None:
        """One channel, held open, and started again when it stops.

        An adapter that exits is started again after a pause. That is the coarser of the
        two recoveries: an adapter reconnects to its own platform far better than this
        can, because it knows what its platform's backoff wants (R-CAD-7). This is what
        catches the case where it did not come back at all.
        """
        held = f"{CHANNEL_AS}{one.name}"
        while not self._stopping:
            answering = one.answering(
                lambda record: self._write_to(held, record),
                lambda: self.ask_to_stop(come_back=True),
                # Its own log, which is the one account that outlives the gateway. Left
                # to default it said nothing at all: a channel that connects, drops,
                # refuses somebody and comes back, in complete silence, is a channel
                # nobody can tell from one that never started (R-GW-18).
                self.log.info,
                lambda run: restart_request.waiting(self.name, run),
                lambda run: restart_request.ready(self.name, run))
            # Kept for as long as this adapter is up, so something other than an arriving
            # message can say a word on this surface — which is what a schedule finishing at
            # three in the morning needs and had no way to do (R-SCH-31).
            self._reached[one.name] = answering
            try:
                # No silence window and no ceiling: an idle channel says nothing for
                # hours by design, and a clock that ends one is a clock that ends the
                # thing a held-open surface exists for (R-PROC-6).
                outcome = await self.start(
                    [str(one.program)], as_name=held, env=await self._for_a_channel(one),
                    silence=None, ceiling=None, takes_input=True,
                    sink=answering.heard,
                    # As it is said, not when the program ends. A channel is held open
                    # for weeks, so waiting for it to end before showing what it
                    # complained about is never showing it: every failure to post, every
                    # refusal, every reconnection is invisible for as long as the thing
                    # doing it is working (R-GW-18).
                    on_error=lambda said, name=one.name: channel_note(
                        self.log, name, said))
            except (AlreadyStarted, Stopping):
                self._reached.pop(one.name, None)
                return
            except asyncio.CancelledError:
                self._reached.pop(one.name, None)
                with contextlib.suppress(BaseException):
                    await answering.stop()
                raise
            except BaseException as would_not_start:  # noqa: BLE001 — a task nobody awaits
                self._reached.pop(one.name, None)
                self.log.error("channel '%s' could not be started: %s",
                               one.name, would_not_start)
                return
            self._reached.pop(one.name, None)
            with contextlib.suppress(BaseException):
                await answering.stop()
            if self._stopping:
                return
            self.log.warning("channel '%s' stopped (%s) — starting it again in %ss",
                             one.name, outcome.reason, int(CHANNEL_AGAIN_SECONDS))
            await asyncio.sleep(CHANNEL_AGAIN_SECONDS)

    async def _kept(self, exclude=()) -> dict:
        """The values every program started from here is given, produced now.

        **Produced per spawn and never held**, which is what makes replacing one take
        effect without restarting anything: a brain gets the new value on its next turn,
        and an adapter on its next start.

        A value that could not be produced is left out and **said in this gateway's own
        log** — the account that outlives the gateway.

        **The name and which kind of not-given it was, and nothing else.** Never
        `Trouble.why`: that is the keeper's own words, and a keeper that fails routinely
        prints the thing it was reading — a vault path, a key's identity, and on a bad
        wrapper the value. This log stands under `data_home()`, which is what a backup
        copies whole, so writing it here would put a credential into the one place
        R-SEC-26 exists to keep structurally free of them. Whoever needs the keeper's
        words runs `rundesk env check <name>` at a terminal, where they are shown and
        not written down.
        """
        resolving = self._secrets_resolving or secret.resolved
        said = await resolving(exclude=exclude)
        if said.unreadable:
            # Rundesk's own words about rundesk's own file, naming a path and never a
            # value — the one thing here an owner cannot find out any other way.
            self.log.warning("the values this install keeps could not be read (%s) — "
                             "no program started now is given any of them", said.unreadable)
        for one in said.trouble:
            self.log.warning(
                "value '%s' was not given to what is starting — %s; "
                "see: rundesk env check %s",
                one.name, secret.plainly(one), one.name)
        return said.values

    async def _for_a_channel(self, one) -> dict[str, str]:
        """What one adapter is told that belongs to this gateway lifetime."""
        said = dict(one.env)
        said["RUNDESK_GATEWAY"] = self._instance
        # One exact path, so an adapter never has to know the runtime layout or guess why
        # it is being ended. The updater removes it only after this gateway is back
        # (R-UPD-43).
        said["RUNDESK_MAINTENANCE"] = str(
            update_request.maintenance_path(self.name, self.where)
        )
        # **The version of the process that actually came up**, and where what changed in
        # it is published (R-UPD-46). Told to the adapter rather than looked up by it: a
        # surface that asked GitHub what is newest would name a release this gateway is not
        # running, and one that read a version out of an updater transcript would have
        # nothing to read after an unattended update nobody's conversation started.
        said["RUNDESK_VERSION"] = __version__
        where = updater.release_url(__version__)
        if where:
            said["RUNDESK_RELEASE_URL"] = where
        # **Merged here rather than where the rest of this adapter's environment was
        # built**, and that is not tidiness. What an agent resolved is built once, when
        # this gateway took its channels; this runs on every adapter start, including
        # every restart after a crash — so a value replaced an hour ago reaches the
        # adapter the next time it comes up rather than the next time the machine
        # restarts the whole gateway (R-SEC-1).
        #
        # **Never what this surface reads its own credential from** (R-SEC-29). The
        # adapter reads its variable before the file beside it, and two agents may hold
        # two different bots — one install-wide value would make them the same bot,
        # silently, with each record still naming a file nobody read.
        return process.told(said, await self._kept(exclude=one.channel_secrets))

    async def _write_to(self, held: str, record: bytes) -> None:
        """Say something to a channel that is running, or say why it could not be said."""
        program = self.running.get(held)
        if program is None:
            raise process.NotListening(f"'{held}' is not running")
        await program.send(record)

    def _reconcile_what_never_finished(self) -> None:
        """Stop a schedule the last gateway died mid-run from reading as still going
        (R-SCH-23).

        What a schedule is doing is written down *before* the run begins, which is what
        R-SCH-9 rests on — and nothing ever rewrote it if the gateway then died. Two
        durable stores were left describing one event and disagreeing: the outcome said
        `started`, indistinguishable from running right now, while the interruption
        beside it said the same work had ended. `rundesk schedules` reads the first, so
        it presented dead work as in flight until that schedule next fell due, which for
        a daily one is a day. It is the first question asked after a crash, and the
        right answer was already on disk one file away.

        Called once the sweeps have returned, which is the moment the claim establishes
        that nothing of the last gateway is running except what it handed over. Work the
        sweep found *still* running is in `_inherited` and is left exactly alone: it is
        genuinely in flight, and saying otherwise would be the same lie the other way up.

        The minute is never moved. It is the minute the schedule *fell due*, and putting
        the moment of reconciling there would read as a later firing to the next gateway
        up, which would then pass over everything due in between.
        """
        surviving = set(self._inherited)
        try:
            stale = [row["name"] for row in self._schedules()
                     if row.get("last_outcome") == STARTED
                     and f"{SCHEDULED_AS}{row['name']}" not in surviving]
        except Unreadable as why:
            self.log.warning("could not read what never finished: %s", why)
            return
        for named in stale:
            self.log.warning("schedule '%s' never finished: the gateway running it is gone", named)
            # The minute is left where it is by `schedule_became`, which takes no minute at
            # all — putting the moment of reconciling there would read as a later firing to
            # the next gateway up, and everything due in between would be passed over.
            self._remember_outcome(named, INTERRUPTED)

    def _settle_runs_nothing_is_doing(self) -> None:
        """Settle a run the last gateway left marked as still going (R-GW-23).

        The schedule beside it was already reconciled here; the run row was not. A run is
        marked running when it starts and nothing rewrote it when the gateway died, was
        stopped, or was replaced by an update — so `rundesk runs` reported a turn in
        flight twenty-six hours after its transcript stopped being written, across three
        releases, and it would have stayed there for ever. The record is what answers
        "what is in flight" and "what did this cost", and a stranded row makes both untrue.

        Called at the same point and for the same reason as the schedule reconciliation:
        the claim has just established that nothing of the last gateway is running except
        what it handed over, and this gateway has begun nothing of its own. What *is* still
        turning says so for itself in the activity records, and is left exactly alone —
        settling live work would be the same lie the other way up.

        What those records leave behind is taken away here too, and this is the only place
        it can be: nothing else in the product removes one.
        """
        # Swept before anything is read, and here rather than anywhere else — the name's
        # lock is held, every stray the last gateway left has already been dealt with, and
        # this gateway has started nothing of its own. Anything still standing under a pid
        # that is gone, or under one the machine has since handed to somebody else, is
        # leftover by definition. Above the `records` guard because this is files rather
        # than rows: a name that is not an agent still owns the directory.
        try:
            swept = activity.sweep(self.where)
        except Exception as why:  # noqa: BLE001 — a filesystem boundary, and see below
            # The same posture as the records boundary below: a gateway that would not
            # come up because it could not tidy is a worse outage than what it could not
            # tidy.
            self.log.warning("could not sweep what crashed turns left behind: %s", why)
        else:
            if swept:
                self.log.info(
                    "swept %s turn record(s) left behind by work that is gone", len(swept))
        if self.records is None:
            return
        live = [row["run"] for row in activity.active(self.where)]
        try:
            settled = self.records.abandoned(
                store.stamped(), ABANDONED_WHY, keep=live)
        except Exception as why:  # noqa: BLE001 — a records boundary
            # Never worth refusing to start over. This is an account of turns that are
            # already over, and a gateway that would not come up because it could not
            # tidy the last one's records is a worse outage than the bad rows.
            self.log.warning("could not settle what the last gateway left running: %s", why)
            return
        if settled:
            self.log.warning(
                "settled %s run(s) left running by a gateway that is gone", settled)

    def _say_what_was_missed(self) -> None:
        """Say what fell due while nothing was running (R-SCH-5).

        None of it is run — a time that passed is gone, and running five at once on the
        way up is worse than not running them. But saying nothing at all is the silence
        an owner cannot tell from a schedule that never worked, so the count is written
        down even though nothing is done about it.
        """
        try:
            since = self._last_seen()
            if since is None:
                return
            wanted = schedule.read(self._schedules())[0]
        except Unreadable as why:
            # Said, and survived (R-SCH-18). A command refuses when it cannot read these,
            # because it was asked to change them. A gateway that refused to start over it
            # would take everything else it does down with the one thing that is broken.
            self.log.error("cannot say what fell due while nothing was running: %s", why)
            return
        for one in wanted:
            if not one.enabled:
                continue
            missed = schedule.passed_over(one, since, datetime.now())
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
                # What a predecessor left running and nothing could end comes first, so
                # our own work overwrites it only if it genuinely shares a name.
                **{name: was for name, was in getattr(self, "_inherited", {}).items()
                   if isinstance(was, dict) and isinstance(was.get("pgid"), int)
                   and _still_there(was["pgid"])},
                **{
                    name: {"pgid": program.pid, "since": self._known_since.get(name)}
                    for name, program in self.running.items()
                    if program.pid is not None
                },
            },
        }
        write_whole(_record_path(self.name, self.where), json.dumps(said))

    # -- what it runs -------------------------------------------------------------

    async def start(
        self,
        argv: Sequence[str],
        as_name: str | None = None,
        env: dict[str, str] | None = None,
        silence: float | None = process.SILENCE_SECONDS,
        ceiling: float | None = process.CEILING_SECONDS,
        on_line: Callable[[str], None] | None = None,
        sink: Callable[[object], object] | None = None,
        takes_input: bool = False,
        cwd: str | Path | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> process.Result:
        """Run a program as this gateway, and keep hold of it while it runs.

        Everything the gateway starts goes through here, which is the only reason
        stopping can promise to end all of it (R-GW-8).

        `as_name` is what this piece of work is, and starting it while it is already
        running is refused rather than doubled (R-GW-15) — a second session on the same
        conversation would answer it twice, each unaware of the other. Work with no name
        is work that cannot collide, and is given one of its own.

        `sink` is for a program whose output is meant to be parsed rather than read, and
        asking for one is what keeps its two streams apart (R-PROC-15) — what it says
        goes to the receiver, and what went wrong goes to this gateway's own log, where
        everything else that happened to it already goes (R-GW-18). `takes_input` opens
        the way back to it (R-PROC-14). What is running is reachable by name in
        `running` for as long as it runs, which is how anything writes to one.
        """
        if self._stopping:
            raise Stopping(f"gateway '{self.name}' is stopping and is taking no more work")
        held = as_name if as_name is not None else f"·{next(self._unnamed)}"
        if held in self.running:
            self.log.warning("refused '%s': it is already running", held)
            raise AlreadyStarted(f"'{held}' is already running under gateway '{self.name}'")
        program = process.Program(
            argv,
            env=env if env is not None
            else process.environment(self.where, agents=self.agents),
            silence=silence, ceiling=ceiling,
            takes_input=takes_input,
            # Kept apart exactly when what it says is going somewhere to be parsed, since
            # that is the only time anything not part of the structure does harm — and
            # keeping them apart costs the order between the two (R-PROC-3, R-PROC-15).
            errors_apart=sink is not None,
            # The workspace this piece of work happens in (R-PROC-19). An agent works on
            # a project rather than in the abstract, and the gateway is started by the
            # machine in a directory nobody chose.
            cwd=cwd,
            # What it says went wrong, as it says it. Kept for the end by default, which
            # is the right answer for work that ends — and no answer at all for work held
            # open for weeks, where everything it complained about would be invisible for
            # exactly as long as it was running.
            on_error=on_error,
        )
        # Registered before it is started, so two of the same name racing cannot both get
        # past the check above and into a subprocess.
        self.running[held] = program
        # Work under this name is going again, so whatever the last gateway wrote about
        # it never finishing has been answered (R-GW-40).
        resolve_interruption(self.name, self.logs, held)
        try:
            await program.start()
            # Asked once, before the record is written, and never asked again (R-GW-30).
            #
            # **Synchronously, and deliberately.** This is one bounded local look-up at the
            # moment a program is registered — not the per-beat storm R-GW-30 removed — and
            # it is asked here exactly as `_record` used to ask it, which is code that ran
            # on Linux for months. Both attempts to move it off the loop instead, a worker
            # thread and then the loop's own subprocess, hung the suite on Linux
            # indefinitely while macOS passed: spawning a second child from inside the
            # coroutine that is already spawning one is what neither survives.
            self._known_since[held] = started_at(program.pid)
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
            outcome = await program.wait(on_line, sink)
        finally:
            self.running.pop(held, None)
            self._known_since.pop(held, None)
            self._say()
        if program.errors:
            # What went wrong is not handed to the receiver — nothing parses it — but it
            # is where a program says why it died, so it goes where anything else worth
            # explaining in the morning goes (R-GW-18).
            self.log.warning("'%s' also said: %s", held, program.errors[-600:])
        if program.undelivered:
            # The receiver never got these at all. Distinct from refusing them, and the
            # difference decides whether what it did receive can be made sense of.
            self.log.warning("'%s': the receiver never got %d record(s)",
                             held, program.undelivered)
        if program.refused:
            # The receiver's trouble, not the program's (R-PROC-17) — but a receiver
            # silently dropping everything it was handed looks exactly like a program
            # that said nothing at all.
            self.log.warning("'%s': the receiver refused %d record(s)", held, program.refused)
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
        # The surfaces this agent is reachable on, held open for as long as it is up
        # (R-CAD-6). Not started per message and never polled: a reply that lands after
        # somebody has asked again is a reply that failed. Everything it starts goes
        # through `start`, so ending it, sweeping it and recording it are already done.
        holding = asyncio.ensure_future(self._hold_channels())
        notices = asyncio.ensure_future(self._deliver_update_notices())
        # Work this agent handed to a specialist, and the reviews it still owes for it.
        # A loop rather than a reaction, because the two things it does are both durable
        # facts a restart has to find again: a run admitted while nothing was up, and a
        # parent that was never told (R-ROL-15).
        specialists = asyncio.ensure_future(self._carry_roles())
        sweeping = asyncio.ensure_future(self._over_and_over(
            ROLE_SWEEP_SECONDS, self._sweep_roles,
            "could not sweep expired role runs: %s", at_once=True))
        watching = asyncio.ensure_future(self._tell_about_skills())
        greeting = asyncio.ensure_future(self._welcome_new_owners())
        try:
            await self._stopped.wait()
        finally:
            beating.cancel()
            ticking.cancel()
            holding.cancel()
            notices.cancel()
            specialists.cancel()
            sweeping.cancel()
            watching.cancel()
            greeting.cancel()
            for task in self._update_turn_tasks.values():
                task.cancel()
            for task in self._role_tasks.values():
                task.cancel()
            with contextlib.suppress(BaseException):
                await holding
            with contextlib.suppress(BaseException):
                await notices
            with contextlib.suppress(BaseException):
                await specialists
            with contextlib.suppress(BaseException):
                await sweeping
            with contextlib.suppress(BaseException):
                await watching
            with contextlib.suppress(BaseException):
                await greeting
            if self._update_turn_tasks:
                await asyncio.gather(
                    *tuple(self._update_turn_tasks.values()), return_exceptions=True)
            if self._role_tasks:
                await asyncio.gather(
                    *tuple(self._role_tasks.values()), return_exceptions=True)
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
        if self._come_back:
            # Ending badly on purpose, which is what asks the machine to start it again.
            # Said in the log first, so an owner reading it later does not find an
            # unexplained non-zero exit where a restart actually happened.
            self.log.info("ending so the machine starts this gateway again")
            return 1
        return 0 if drained else 1

    async def _carry_roles(self) -> None:
        """Carry the role runs this agent admitted, and tell each parent once.

        Both halves are driven off durable records rather than off anything held in this
        process, so a gateway that starts finds work admitted while nothing was up and
        reviews nobody was ever told about. That is the whole reason the acknowledging
        turn is allowed to end (R-ROL-15).
        """
        while not self._stopping:
            if self.roles is not None:
                try:
                    self._end_the_roles_asked_to_stop()
                    self._start_admitted_roles()
                    self._check_in_on_roles()
                except asyncio.CancelledError:
                    raise
                except BaseException as why:  # noqa: BLE001 — this loop must not die
                    self.log.warning("could not start a role run: %s", why)
                try:
                    await self._deliver_one_role_review()
                except asyncio.CancelledError:
                    raise
                except BaseException as why:  # noqa: BLE001 — retried after reconnect
                    self.log.warning("could not deliver a role handoff: %s", why)
            await asyncio.sleep(ROLE_SECONDS)

    def _start_admitted_roles(self) -> None:
        """Start every admitted root that nothing here is already carrying (R-GW-15)."""
        for row in self.roles.waiting():
            run_id = row["id"]
            if row.get("stop_asked_at"):
                continue   # asked to end before anything started it; settled below
            if run_id in self._role_tasks:
                continue
            self._role_tasks[run_id] = asyncio.ensure_future(self._carry_one(run_id))
            self.log.info("carrying role run %s", run_id)

    def _end_the_roles_asked_to_stop(self) -> None:
        """End every execution somebody asked to end (R-ROL-24).

        Cancelling is all this does. What the run is *settled* as belongs where every
        other way it can end is settled, so a stop and a failure cannot come to disagree
        about what a stopped run looks like — and a run nothing here is carrying is
        settled there too, without a provider ever being started for it.
        """
        for row in self.roles.stopping():
            task = self._role_tasks.get(row["id"])
            if task is not None and not task.done():
                task.cancel()
            else:
                self.roles.stopped(row["id"])
            self.log.info("ending role run %s because it was asked to stop", row["id"])

    async def _carry_one(self, run_id: str) -> None:
        """One role root, from here to its terminal outcome and no further.

        What a provider-native helper does inside it belongs to that turn and returns to
        it; nothing about one reaches this gateway, and none of them settles this run
        (R-ROL-14).
        """
        outcome = None
        self._show_role(run_id, working=True)
        try:
            outcome = await self.roles.carry(run_id)
        except asyncio.CancelledError:
            raise
        except BaseException as why:  # noqa: BLE001 — a boundary, reported truthfully
            self.log.warning("role run %s could not be carried: %s", run_id, why)
        finally:
            self._role_tasks.pop(run_id, None)
            self._role_checked.pop(run_id, None)
            # Said however it went, including the ways it can go wrong: work handed over
            # and never heard of again reads as work still running for ever.
            self._show_role(run_id, working=False, outcome=outcome)

    def _show_role(self, run_id: str, working: bool, outcome=None) -> None:
        """Show the work where the person who asked for it is waiting (R-ROL-27).

        One self-contained record either way, so a surface renders it without remembering
        anything it was told hours earlier. Never allowed to interrupt the work: a
        platform that cannot be told is a platform that shows less, and the run carries on
        either way.
        """
        try:
            where = self.roles.seen(run_id)
            answering = self._reached.get((where or {}).get("channel"))
            if where is None or answering is None or not answering.connected:
                return
            if working:
                answering.told_role_working(
                    where["conversation"], run_id, where["label"],
                    where.get("role", ""), where.get("elapsed", 0))
                return
            answering.told_role_settled(
                where["conversation"], run_id,
                bool(outcome is not None and getattr(outcome, "ok", False)),
                where["label"], where.get("role", ""), where.get("elapsed", 0),
            )
        except Exception as why:  # noqa: BLE001 — showing is never worth a run
            self.log.warning("could not show role run %s: %s", run_id, why)

    def _check_in_on_roles(self) -> None:
        """Say that a run still working is still working (R-ROL-36).

        Driven off the runs this gateway is carrying, so a check-in cannot outlive the
        work it describes. Never allowed to interrupt anything, for the same reason
        marking one is not.
        """
        for run_id in list(self._role_tasks):
            try:
                where = self.roles.checking_in(
                    run_id, self._role_checked.get(run_id, 0))
                if where is None:
                    continue
                answering = self._reached.get(where.get("channel"))
                if (answering is None or not answering.connected
                        or not where.get("conversation")):
                    continue
                # Written before the record is queued: a surface that throws costs one
                # skipped line rather than a line every five seconds for ever.
                self._role_checked[run_id] = where["due"]
                answering.told_role_checking_in(
                    where["conversation"], run_id, where["label"],
                    where.get("role", ""), where.get("elapsed", 0))
            except Exception as why:  # noqa: BLE001 — showing is never worth a run
                self.log.warning("could not check in on role run %s: %s", run_id, why)

    async def _deliver_one_role_review(self) -> None:
        """Wake the parent for the oldest handoff it is still owed, if it can be woken.

        Nothing is marked delivered until the parent's review turn has actually answered,
        so a surface that is down means the review waits rather than being lost, a review
        that answered nobody leaves the handoff owed, and a gateway that died anywhere in
        between finds it owing again.
        """
        # Imported here rather than at the top, the way `agent.playing` imports the same
        # module for the same reason: what a role run is reaches back through an agent to
        # this file, so a module-level import would close that circle and leave whether it
        # resolves depending on which of the three something happened to import first.
        from rundesk import role_run

        for owed in self.roles.owed():
            answering = self._reached.get(owed.get("channel"))
            if answering is None or not answering.connected or not owed.get("conversation"):
                # Not deliverable now, and possibly not ever — a channel the owner has
                # removed never comes back. Every later review is still tried, so one
                # undeliverable handoff cannot hold up the rest (R-ROL-15).
                continue
            if int(owed.get("attempts") or 0) >= role_run.REVIEW_CEILING:
                await self._give_up_on_one_role_review(answering, owed)
                continue
            if answering.answering_somebody(owed["conversation"]):
                # **A parent mid-turn is not an attempt.** The handoff waits, which is
                # correct and is retried every few seconds — but counting each look would
                # put seven hundred attempts on an agent that was simply busy for an hour,
                # and that count is the one thing an owner has for spotting a surface that
                # is never coming back (R-ROL-32).
                continue
            self.roles.claiming(owed["role_run"])
            await answering.told_role_finished(
                owed["conversation"], owed["handoff"],
                reviewing=lambda run, at=owed["role_run"]: self.roles.reviewing(at, run),
                # **Settled when the review answered, never when it was admitted.** A turn
                # a stale session handed straight back read nothing and reviewed nothing,
                # and writing the handoff off against one is a role run that was run, paid
                # for and read by nobody (R-ROL-15).
                delivered=lambda at=owed["role_run"]: self._role_review_delivered(at),
            )
            return

    def _role_review_delivered(self, run_id: str) -> None:
        """One handoff, reviewed by the parent it was owed to and settled for good.

        Said in the log here rather than where the turn was started, so "delivered" names
        the moment it was delivered rather than the moment it was attempted.
        """
        self.roles.reviewed(run_id)
        self.log.info("delivered the handoff for role run %s", run_id)

    async def _give_up_on_one_role_review(self, answering, owed: dict) -> None:
        """Settle a handoff nobody could be woken for, and tell the owner (R-ROL-37).

        A review that fails every time would otherwise be offered round a loop for the
        whole retention window, and the parent's own conversation is exactly where nothing
        can be said about it — the review turn there is the thing that is not working.

        **The owner is told before it is written off**, so a surface that throws leaves the
        callback owed and the notice is tried again rather than lost. And the notice carries
        the run and the role and nothing else: this report has still been read by nobody,
        and repeating a word of it here would publish unreviewed work by the one route built
        to prevent that (R-ROL-19).
        """
        from rundesk import role_run

        await answering.told_the_owner(role_run.REVIEW_UNDELIVERABLE.format(
            run=owed["role_run"], role=owed.get("role") or "",
            attempts=int(owed.get("attempts") or 0),
        ))
        self.roles.giving_up(owed["role_run"])
        self.log.warning(
            "gave up on the handoff for role run %s after %s attempts",
            owed["role_run"], owed.get("attempts"),
        )

    def _sweep_roles(self) -> None:
        """Settle what has gone quiet, then take away what has expired (R-ROL-12).

        Two things on one timer, and each is tried even where the other raised: how long
        silence is allowed to last is read from the owner's configuration, and a file
        somebody has broken must not also stop bundles being cleared.
        """
        if self.roles is None:
            return
        try:
            self._end_the_roles_that_went_quiet()
        except Exception as why:  # noqa: BLE001 — the sweep below still runs
            self.log.warning("could not settle role runs that went quiet: %s", why)
        for run_id in self.roles.sweep():
            self.log.info("role run %s is past its retention window", run_id)

    def _end_the_roles_that_went_quiet(self) -> None:
        """Settle every run that stopped producing anything, and let go of it (R-ROL-30).

        Cancelling is the second half and not an afterthought: a run settled while a task
        here is still awaiting a wedged provider is a run reported finished with somebody
        still paying for it.
        """
        for run_id in self.roles.quiet():
            task = self._role_tasks.get(run_id)
            if task is not None and not task.done():
                task.cancel()
            self.log.warning(
                "role run %s stopped producing activity and was settled", run_id)

    async def _deliver_update_notices(self) -> None:
        """Deliver a completed self-update once the originating channel is connected."""
        while not self._stopping:
            try:
                row = update_request.deliverable(self.name)
            except update_request.Unreadable as why:
                self.log.warning("could not read update outcome: %s", why)
                await asyncio.sleep(2)
                continue
            if row is not None:
                origin = row.get("origin") or {}
                channel_name = origin.get("channel")
                conversation = origin.get("conversation")
                answering = self._reached.get(channel_name) if channel_name else None
                if answering is not None and answering.connected and conversation:
                    try:
                        await answering.told_update_finished(
                            conversation, update_request.summary(row)
                        )
                        update_request.delivered(row["id"])
                        self.log.info("delivered update outcome for request %s", row["id"])
                    except Exception as why:  # noqa: BLE001 — retried after reconnect
                        self.log.warning("could not deliver update outcome: %s", why)
            try:
                restart = restart_request.deliverable(self.name)
            except restart_request.Unreadable as why:
                self.log.warning("could not read restart outcome: %s", why)
                restart = None
            if restart is not None:
                origin = restart.get("origin") or {}
                channel_name = origin.get("channel")
                conversation = origin.get("conversation")
                answering = self._reached.get(channel_name) if channel_name else None
                if answering is not None and answering.connected and conversation:
                    try:
                        await answering.told_restart_finished(
                            conversation, restart_request.summary(restart)
                        )
                        restart_request.delivered(self.name, restart["id"])
                        self.log.info(
                            "delivered restart outcome for request %s", restart["id"]
                        )
                    except Exception as why:  # noqa: BLE001 — retried after reconnect
                        self.log.warning("could not deliver restart outcome: %s", why)
            await asyncio.sleep(2)

    # -- what the agent may do ---------------------------------------------------------

    def _skills_last_seen(self) -> Path:
        """Where what this agent could do last time is written down.

        Runtime state and not the owner's: it belongs to this gateway's run directory
        beside its lock and its record, is nobody's to read but this loop, and says
        nothing an owner would ever want back. Named the way the update marker is —
        a dotfile keyed by the encoded name — because the run directory's `*.json`
        entries are *the gateways there are* (`known`, `sweep`), so a record of any
        other kind put there under that suffix invents a gateway nobody started.
        """
        identity = self.name.encode("utf-8").hex()
        return self.where / f".{identity}.skills-last-seen"

    def _skills_seen(self) -> tuple[str, ...] | None:
        """What this agent could do when its owner was last told, or None for never.

        None is deliberately not "it could do nothing": an install where this has never
        run would otherwise announce every skill the agent already holds as newly
        added, on the one startup that follows an update.
        """
        try:
            written = self._skills_last_seen().read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return tuple(line for line in written.splitlines() if line)

    def _remember_skills(self, names: Sequence[str]) -> None:
        """Write down what the owner has now been told about, or leave it alone.

        Replaced whole and atomically: a half-written list read back by the next look is
        a list of skills that were never taken away being announced as though they had
        been. A machine that will not take it keeps the old list, so the same change is
        said again on the next look rather than silently lost — being told twice is the
        smaller failure.
        """
        target = self._skills_last_seen()
        temporary = target.with_suffix(f".{os.getpid()}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(temporary, "w", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                handle.write("".join(f"{one}\n" for one in names))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except OSError as why:
            self.log.warning("could not write down what this agent may do: %s", why)
        finally:
            with contextlib.suppress(OSError):
                temporary.unlink()

    async def _tell_about_skills(self) -> None:
        """Tell the owner, privately, when this agent gains or loses a skill (R-CH-32).

        Looked at rather than reported: a grant is a link in a directory, and the four
        things that add or remove one — a command, a configured baseline reconciled at
        startup, a catalog update and a catalog removal — would each have to remember to
        say so, while somebody making the link by hand never could. What the directory
        holds is the whole truth about what an agent may do, so that is what is watched.

        **What was seen is written down, so a change made while the agent was stopped is
        still told.** Taking a skill away is exactly what an owner does with the gateway
        down, and a notice only the running process could have raised is one that case
        never gets.

        Nothing is written down until it has actually been delivered, which is what makes
        a surface that is not up yet a wait rather than a loss.
        """
        while not self._stopping:
            if self.granted is not None:
                try:
                    self._look_at_skills()
                except Exception as why:  # noqa: BLE001 — a loop nobody awaits
                    if self._skills_complaint != str(why):
                        self.log.warning("could not see what this agent may do: %s", why)
                        self._skills_complaint = str(why)
                else:
                    self._skills_complaint = None
                await self._say_skill_changes()
            await asyncio.sleep(SKILLS_SECONDS)

    def _look_at_skills(self) -> None:
        """Work out what changed, and hold it until somebody can be told.

        Worked out afresh every look rather than accumulated: what is owed is always the
        difference between the directory and the list, so a skill granted and revoked
        again before either could be said leaves nothing to say.
        """
        now = tuple(self.granted())
        seen = self._skills_seen()
        if seen is None or not self.reachable:
            # A first look has nothing to compare against, and an agent reached on no
            # surface has nobody to tell — both write down what is there and say nothing.
            # Without the second, an owner who adds a channel months later is greeted by
            # every grant they ever made.
            self._remember_skills(now)
            self._skills_owed = None
            return
        lines = (
            [f"🧩 **Skill added** — `{one}`" for one in now if one not in seen]
            + [f"🗑️ **Skill removed** — `{one}`" for one in seen if one not in now]
        )
        self._skills_owed = (lines, now) if lines else None

    async def _say_skill_changes(self) -> None:
        """Say what changed on one surface, and write it down only once it has gone.

        One surface and not every one: an agent reached on two of them has one owner, and
        the same news twice reads as two changes. The first by name, so which one it is
        does not depend on the order channels happened to connect in.
        """
        if self._skills_owed is None:
            return
        lines, now = self._skills_owed
        for named in sorted(self._reached):
            answering = self._reached[named]
            if not answering.connected:
                continue
            try:
                await answering.told_the_owner("\n".join(lines))
            except Exception as why:  # noqa: BLE001 — retried on the next look
                self.log.warning("could not tell the owner what changed: %s", why)
                return
            self.log.info("told the owner about %d skill change(s)", len(lines))
            self._remember_skills(now)
            self._skills_owed = None
            return

    # -- who has just been allowed to reach it -------------------------------------------

    async def _welcome_new_owners(self) -> None:
        """Introduce this agent, once, to everybody newly allowed to reach it (R-CH-33).

        A loop rather than something the command tells us, for the reason the skills one
        is: what a channel allows is changed by a command that may run while nothing is
        up, and by the time a gateway starts there is nobody left to have told it. What
        the record says is the whole truth about who may reach this agent, so that is what
        is looked at — and the introduction waits for the surface rather than being lost
        with it.
        """
        while not self._stopping:
            try:
                await self._welcome_anyone_owed()
            except asyncio.CancelledError:
                # The gateway is going. Swallowed, this would sleep and start the same
                # turn again after the surface it was for had been reported gone.
                raise
            except Exception as why:  # noqa: BLE001 — a loop nobody awaits
                self.log.warning("could not see who is owed an introduction: %s", why)
            await asyncio.sleep(WELCOME_SECONDS)

    def _owed_a_welcome(self) -> dict:
        """Who is owed an introduction, and on which of this agent's connected channels.

        One entry per person and not per channel: an agent reachable both by direct
        message and in rooms is *one* agent with one owner, and two greetings a minute
        apart read as two agents. The channel is the first by name that both allows them
        and is actually up, so which one it is does not depend on the order surfaces
        happened to connect in.
        """
        owed: dict = {}
        for one in self.reachable or ():
            home = getattr(one, "home", None)
            answering = self._reached.get(one.name)
            if home is None or answering is None or not answering.connected:
                continue
            allow = (getattr(answering, "record", None) or {}).get("allow") or []
            try:
                for user in owed_a_welcome(Path(home), allow):
                    owed.setdefault(user, one.name)
            except (OSError, Unreadable) as why:
                if self._welcome_complaint != str(why):
                    self.log.warning("could not see who channel '%s' has welcomed: %s",
                                     one.name, why)
                    self._welcome_complaint = str(why)
                continue
            self._welcome_complaint = None
        return owed

    async def _welcome_anyone_owed(self) -> None:
        """Ask the agent to greet each of them, and write it down once it has gone.

        **Attempted once for each person while this gateway is up, whatever comes of it.**
        Every other loop here is free to try again in ten seconds; this one asks a brain
        for a whole turn, so a provider that cannot run would spend an owner's tokens over
        and over for as long as the gateway lives. A failure is said in the log and left
        unwritten, so the next gateway that comes up well tries it again — which is the
        one retry that costs nothing when the reason is still there.
        """
        for user, named in sorted(self._owed_a_welcome().items()):
            if user in self._welcome_attempted:
                continue
            answering = self._reached.get(named)
            if answering is None or not answering.connected:
                continue
            # Before the turn, so a welcome that raises after the brain has already
            # written to somebody is not asked for a second time.
            self._welcome_attempted.add(user)
            try:
                await answering.welcomed(user)
            except asyncio.CancelledError:
                raise
            except Exception as why:  # noqa: BLE001 — a delivery boundary, retried later
                self.log.warning("channel '%s': could not introduce this agent to %s: %s",
                                 named, user, why)
                continue
            self.log.info("channel '%s': introduced this agent to %s", named, user)
            self._remember_welcomed_everywhere(user)

    def _remember_welcomed_everywhere(self, user: str) -> None:
        """Write one delivered introduction down against every channel of this agent.

        Against every one, not only the surface it went out on: the person has now been
        greeted by this agent, and a second channel still owing them would greet them
        again the moment this one went quiet — or on the next gateway, which is where a
        marker held only in memory stops helping.

        Written even where that channel does not allow them, which costs nothing and is
        the simpler rule: the next look prunes anybody a channel no longer allows, so a
        name written somewhere it does not belong takes itself back out.
        """
        for one in self.reachable or ():
            home = getattr(one, "home", None)
            if home is None:
                continue
            try:
                remember_welcomed(Path(home), user)
            except (OSError, Unreadable) as why:
                self.log.warning("channel '%s': could not write down that %s was "
                                 "introduced: %s", one.name, user, why)

    def ask_to_stop(self, come_back: bool = False) -> None:
        """Take no more work, and begin going away (R-GW-6).

        Called from a signal handler, so it does no work itself — a handler that awaited
        anything would be a handler that could be interrupted halfway through.

        `come_back` is how an agent is cycled from a surface it is reached on (R-CH-16).
        A gateway cannot start itself: what keeps it up brings it back when it ends
        *badly*, and lets it lie when it ends well (R-GW-25). So asking for a restart is
        asking to end badly on purpose, which is the one place that is the honest thing
        to do — the alternative is a gateway that says goodbye and never returns.
        """
        self._stopping = True
        self._come_back = come_back
        if self._stopped is not None:
            self._stopped.set()
        self.log.info("asked to restart" if come_back else "asked to stop")

    async def _go(self) -> bool:
        """End everything, then leave nothing behind (R-GW-8, R-GW-12).

        Bounded, because the supervisor's patience is: past it, this process is killed,
        and a killed gateway leaves its children running — the one outcome worth
        hurrying to avoid. True when everything really did go.

        **A turn a schedule asked for counts, and it is not in `running`.** Its brain is started
        by whatever admits the turn rather than by this gateway, so `end_all` cannot reach it —
        and taking that for nothing left reported a clean stop, exit code zero and "down", while
        a brain was still working. A supervisor reading zero has no way to know (R-GW-7), so it
        is counted here even though ending it is not yet something this can do.
        """
        self._stopping = True
        drained = True
        try:
            # Running out of time is not the only way to fail to end something. Both
            # signals can go out, the grace period can pass, and the group can still be
            # there — and taking "it returned" for "it went" had this report a clean
            # shutdown and then delete the record naming the survivors (R-GW-17).
            drained = await asyncio.wait_for(
                process.end_all(list(self.running.values())), STOP_SECONDS
            )
            if not drained:
                still = ", ".join(sorted(self.running)) or "something"
                self.log.error("could not end %s — it is still out there", still)
        except asyncio.TimeoutError:
            # Said out loud rather than swallowed: what is left is in its own process
            # group, so this process exiting will not take it, and the next start of
            # this name is the only thing that will.
            drained = False
            still = ", ".join(sorted(self.running)) or "something"
            self.log.error("gave up waiting for %s to stop — it is still out there", still)
        finally:
            asked = sorted(self._asked_for)
            if asked:
                # A turn nobody here started and nobody here can end. Said and counted, because
                # the alternative is a gateway that exits zero while a brain is answering.
                drained = False
                self.log.error("a turn is still going for %s — this gateway cannot end one it "
                               "did not start, so it is still out there", ", ".join(asked))
            if not drained:
                # Written before it is forgotten, and left behind on the way out: this
                # record is the only thing that names what is still running, and the
                # next gateway of this name is the only thing that will ever end it
                # (R-GW-16). Erasing it here is admitting to orphans and then losing them.
                self._say()
                # Freeze that final record before any running task can unwind. Clearing
                # `running` and only then releasing left a scheduling gap in which a
                # task's `finally` rewrote the record as empty (R-GW-16).
                self._released = True
                # And said where something other than a person can read it (R-GW-23). The
                # log already carries this, which answers the owner and nothing else.
                for held, program in self.running.items():
                    note_interrupted(
                        self.name, self.logs, held,
                        "the gateway went while it was still running", program.pid, False)
                for held in asked:
                    # No process group to name: what this gateway knows is that a turn under
                    # this name had not finished, which is what a later one has to reckon with.
                    note_interrupted(
                        self.name, self.logs, held,
                        "the gateway went while a turn it asked for was still going", None, False)
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

        **The first look happens straight away, not one interval later.** A schedule is due
        only in its stated minute, so a gateway that waited twenty seconds before looking
        lost every occurrence due in the last twenty seconds of the minute it started in —
        and the machine restarting a gateway is exactly the moment that happens. Nothing
        else covers it: what fell due while nothing was running is *reported* and
        deliberately not run late (R-SCH-4), and that runs during `claim`, before this gap
        exists at all. The per-minute guard is what makes the immediate look safe — this
        look and the first ordinary tick cannot start one minute twice (R-SCH-9).
        """
        await self._over_and_over(
            TICK_SECONDS, lambda: self._fire(schedule, datetime.now()),
            "could not look at the clock: %s", at_once=True,
        )

    def _fire(self, schedule, now) -> None:
        """Start everything due at this moment, and say what happened to each."""
        if self._stopping:
            return
        self._fire_update_turns(schedule, now)
        try:
            wanted, refused = schedule.read(self._schedules())
        except Unreadable as why:
            # Nothing runs, and it is said once rather than every tick (R-SCH-18). `None`
            # is the records themselves rather than a schedule in them — the coarser
            # version of the same news the loop below reports row by row.
            if self._complained.get(None) != str(why):
                self.log.error("no schedule can run: %s", why)
                self._complained[None] = str(why)
            return
        for name, why in refused:
            if self._complained.get(name) != why:
                self.log.error("schedule '%s' cannot be understood: %s", name, why)
                self._complained[name] = why
        for one in schedule.due(wanted, now, self._ran):
            fired = now.replace(second=0, microsecond=0)
            self._ran[one.name] = fired
            # Written down before it is started, not after it finishes. Held only in
            # memory, the fact that this minute had already fired died with the gateway:
            # a crash between starting and finishing, and a supervisor that brings the
            # gateway back within seconds, ran the same schedule twice for the one
            # minute it was due (R-SCH-9).
            #
            # And *only* if it was written down. Starting anyway leaves work that has
            # visibly happened with nothing durable saying it did, so the same
            # side-effecting run repeats on the way back up — which is the very thing
            # writing it first is for.
            if not self._remember_firing(one.name, fired):
                self.log.error("schedule '%s' was not started: its firing could not be "
                               "written down, and a run nothing records may happen twice",
                               one.name)
                continue
            asyncio.ensure_future(self._run_scheduled(one, fired))

    def _fire_update_turns(self, schedules, now) -> None:
        """Start release-requested turns through scheduled-turn semantics.

        R-MIG-23, R-MIG-24.

        These are deliberately not ordinary schedules. An ordinary one-time schedule that
        was missed is never replayed; an update migration must survive a slow restart and
        reach every agent. A request stays pending until a non-stopped run returns, while
        the synthetic expired schedule gives it the same fresh conversation, instructions
        and run accounting as other unattended work.
        """
        if self.records is None or self._update_turns_drained:
            return
        try:
            pending = self.records.pending_update_turns()
        except Exception as why:  # noqa: BLE001 — the records seam owns the failure types
            self.log.warning("could not read update migration turns: %s", why)
            return
        if not pending:
            self._update_turns_drained = True
            return
        fired = now.replace(second=0, microsecond=0)
        # One home is one mutable resource. Even if several releases accumulated while an
        # agent was unrunnable, only the oldest request may rewrite it at a time.
        for row in pending[:1]:
            version = int(row["migration"])
            if version in self._update_turn_tasks:
                continue
            conversation = f"migration-{version}"
            try:
                returned = self.records.update_turn_returned(conversation)
            except Exception as why:  # noqa: BLE001 — the records seam owns failure types
                self.log.warning("could not reconcile update migration %s: %s", version, why)
                continue
            if returned:
                try:
                    self.records.complete_update_turn(version, store.stamped())
                except Exception as why:  # noqa: BLE001 — a durable-write boundary
                    self.log.warning("could not complete update migration %s: %s",
                                     version, why)
                continue
            one = schedules.Schedule(
                name=conversation,
                at=fired.strftime(schedules.A_MINUTE),
                ran_at=fired.strftime(schedules.A_MINUTE),
                prompt=row["prompt"],
                instructions=row["instructions"],
                backend=True,
            )
            task = asyncio.ensure_future(
                self._run_update_turn(one, version, row["bootstrap"]))
            self._update_turn_tasks[version] = task
            task.add_done_callback(
                lambda finished, requested=version:
                self._update_turn_tasks.pop(requested, None)
            )

    async def _run_update_turn(self, one, version: int, bootstrap: str) -> None:
        """Run and settle one backend-only update migration turn."""
        self.log.info("update migration %s is due", version)
        try:
            self.records.replace_update_bootstrap(version, bootstrap)
        except Exception as why:  # noqa: BLE001 — a filesystem boundary
            self.log.error("update migration %s could not replace its bootstrap: %s",
                           version, why)
            return
        became = await self._run_scheduled(one, datetime.now())
        # A turn that could not begin remains pending for the next tick or gateway. Once a
        # brain actually returned, its run is the durable outcome and this request expires.
        if became in ("could not start", "still running", INTERRUPTED):
            return
        try:
            self.records.complete_update_turn(version, store.stamped())
        except Exception as why:  # noqa: BLE001 — a durable-write boundary
            self.log.warning("could not complete update migration %s: %s", version, why)

    async def _run_scheduled(self, one, fired: datetime) -> str:
        """Start what a schedule named, under the schedule's own name.

        Under its own name on purpose: that is what makes a schedule refuse to begin
        again while the last one is still going (R-SCH-6), using the guard that already
        exists rather than a second one that could disagree with it.

        **A schedule names a program or asks a turn**, and everything after starting it is
        the same either way — which is why the two are one function with one set of handlers
        rather than two that would drift about what an outcome is.
        """
        held = f"{UPDATE_AS if one.backend else SCHEDULED_AS}{one.name}"
        if not one.prompt and (not isinstance(one.run, (list, tuple)) or not one.run):
            self.log.error("schedule '%s' names nothing this gateway can start", one.name)
            return "could not start"
        self.log.info("schedule '%s' is due", one.name)
        try:
            # One word out of both branches, because everything after this is the same for
            # a program and for a turn. Which word it is differs: a program has one answer
            # and a turn has two — what became of the process, and what became of the turn
            # it was carrying — and only the second is what a schedule reports (R-SCH-8).
            if one.prompt:
                # **Only a schedule that asks a turn says it has started** (R-SCH-46). A
                # program has no report to anchor, so `💻 Working on…` for one is a promise
                # rundesk does not keep. Said from inside `_asked`, once the schedule's name
                # is claimed: announced here instead, a firing refused for still running
                # would have said work began that never did.
                result = await self._asked(
                    one, held, admitted=lambda: self._told_the_surface_it_started(one))
            else:
                ran = await self.start(list(one.run), as_name=held,
                                       env=await self._for_a_schedule(one.name))
                result = ran.reason
        except AlreadyStarted:
            # R-SCH-7: said, not passed over. A schedule quietly skipping every time
            # because the last run never ended looks exactly like one that is working.
            #
            # **And nothing is said on the surface.** This firing never announced itself,
            # and the notice that may be standing there belongs to the run still going —
            # answering it here would close off work that has not finished (R-SCH-46).
            self.log.warning("schedule '%s' skipped: what it started last time is still running",
                             one.name)
            if not one.backend:
                self._remember_outcome(one.name, "still running")
            return "still running"
        except Stopping:
            # Nothing spawned, so there is no process for the shutdown to end and nothing
            # for a later sweep to find and reckon with — and the firing was already
            # written down as `started` before this wrapper ran. Left alone it is a row
            # saying work is in flight that never began at all, and the one form of the
            # stale outcome that no reconciliation on the way back up can reach
            # (R-SCH-23).
            #
            # **And no notice to answer, by construction.** This is raised by `start` and
            # nowhere else, so only the program branch above can reach it — and a program
            # schedule never says it has started, having no report to anchor (R-SCH-46).
            if not one.backend:
                self._remember_outcome(one.name, INTERRUPTED)
            return INTERRUPTED
        except asyncio.CancelledError:
            # Not a failure to start, and told apart from one before the catch-all below
            # can call it that. This is what a run in flight *is* when the gateway goes:
            # `serve` returns and the loop cancels whatever is left, so a schedule that
            # started perfectly well arrived here — and was written down as 'could not
            # start', with no reason, one line after the log said it had started. A false
            # line in the one account that outlives the gateway (R-GW-18), and in the file
            # that is meant to say truthfully what each schedule last did.
            if not one.backend:
                self._remember_outcome(one.name, INTERRUPTED)
            await self._answered_any_notice(one, INTERRUPTED)
            raise
        except BaseException as would_not_start:  # noqa: BLE001 — see below
            # Nobody awaits this task, so anything raised here is raised nowhere at all:
            # asyncio reports it against the garbage-collected task, on stderr, which for
            # a supervised gateway is a file rundesk does not read. The schedule then sat
            # at LAST RUN '-' forever, indistinguishable from one that has never come due
            # — while failing again every single time it fell due (R-SCH-8).
            self.log.error("schedule '%s' could not be started: %s", one.name, would_not_start)
            if not one.backend:
                self._remember_outcome(one.name, "could not start")
            await self._answered_any_notice(one, "could not start")
            return "could not start"
        became = getattr(result, "became", result)
        if not one.backend:
            self._remember_outcome(one.name, became)
            await self._told_the_surface(one, result)
        return became

    async def _told_the_surface_it_started(self, one) -> None:
        """Say on the surface this schedule reports to that its run has begun (R-SCH-46).

        The mirror of `_told_the_surface`, and it refuses in the same places: a schedule
        naming no surface says nothing, and one naming a surface that is not up is said in
        the log rather than invented. Only what actually went out is remembered, so the
        outcome owes a reply to a notice and never to a delivery that never happened.

        A notice that could not be shown changes nothing about the run. The work is under
        way and the report at the end stands on its own, exactly as it did before there
        were notices at all.
        """
        answering = self._reached.get(one.channel) if one.channel else None
        if answering is None:
            if one.channel:
                self.log.warning(
                    "schedule '%s': nothing said on '%s' about starting — that channel "
                    "is not up", one.name, one.channel)
            return
        try:
            said, where = await answering.told_a_schedule_started(one.name)
            if said:
                # Where it went, not that it went: the report is delivered to this same
                # conversation rather than resolving the newest one again at the end
                # (R-SCH-46).
                self._announced[one.name] = where
        except Exception as why:  # noqa: BLE001 — a delivery boundary; see the docstring
            self.log.warning("channel '%s': could not say that '%s' started: %s",
                             one.channel, one.name, why)

    async def _answered_any_notice(self, one, became: str) -> None:
        """Put an outcome under a start notice on a run that ended without reaching the
        ordinary reporting below (R-SCH-46).

        A run that failed, was interrupted or never got going has said `💻 Working on…` on
        a surface and would otherwise leave it standing with nothing under it — which is a
        promise rundesk made and did not keep, and reads exactly like an agent that hung.
        A no-op where no notice went out, so nothing new is posted for a schedule that
        never announced itself.

        **A gateway going down is the one way out this cannot answer**, and knowingly: the
        shutdown takes the channels before it cancels what is still running, so by the time
        a run in flight is cancelled there is no surface left to say anything on and the log
        says so. The notice goes down with the process that made it, and the schedule's next
        firing posts its own — nothing is left standing that a later run would answer.
        """
        if one.name in self._announced:
            await self._told_the_surface(one, became)

    async def _told_the_surface(self, one, result) -> None:
        """Say what this schedule came to, on the surface it names.

        **The first trigger with no person at the other end.** Work that failed at three in the
        morning has to be readable where its owner already looks, rather than only in an account
        nobody opens until they think to. So the gateway tells the surface: it is the only thing
        that can, because a channel is held open here and a scheduled program is a child
        process that cannot reach it.

        **The surface the schedule names, and no other.** This went to every one the agent had,
        which is two notices about work that concerned one of them — and worse, it decided for
        the owner where a night's work is discussed. A schedule that names none reports where it
        always did: the account, and `schedules`. That is not silence, only not a chat message.

        A channel decides nothing about any of this; it is told, exactly as it is told about a
        turn. And an agent with no channel at all still ran and still recorded, because there is
        then nothing here to say anything on (R-SCH-31).

        A surface that will not take it changes nothing about what the schedule did: the work is
        over and the record of it is already written. Said in the log, and on.

        **This is what answers a start notice** (R-SCH-46), so the notice is forgotten here
        whether or not the report reaches anybody — a channel that went down between the two
        must not leave a name standing that the schedule's *next* firing would answer. What
        it is forgotten *with* is where it went, and that goes over with the report: the two
        messages are one delivery, and only the first of them is allowed to decide where.
        """
        where = self._announced.pop(one.name, None)
        became = getattr(result, "became", result)
        answering = self._reached.get(one.channel) if one.channel else None
        if answering is None:
            if one.channel:
                # Named and not up. Said, because an owner who asked to be told and was not is
                # owed the reason — a schedule that reports nowhere looks exactly like one that
                # did not run.
                self.log.warning("schedule '%s': nothing said on '%s' — that channel is not up",
                                 one.name, one.channel)
            return
        try:
            await answering.told_what_a_schedule_did(one.name, result, where=where)
        except Exception as why:  # noqa: BLE001 — a delivery boundary; see the docstring
            self.log.warning("channel '%s': could not say what '%s' did: %s",
                             one.channel, one.name, why)

    async def _for_a_schedule(self, named: str) -> dict[str, str]:
        """The environment a scheduled program is given: the ordinary one, and which schedule.

        One variable more than anything else this gateway starts, and it is here for the
        reason every addition to that environment has to have: a schedule whose program is
        itself `rundesk ask` is the clock's work, and nothing else can tell it so. Untold, it
        was admitted as though somebody had typed it — landing in the terminal's own
        conversation, resuming the session its owner types into, and reading back in `runs`
        as a turn a person asked for (R-RUN-16).
        """
        said = process.environment(self.where, agents=self.agents)
        said[SCHEDULE_IS] = named
        # The install's own values, produced now rather than when this gateway came up, so
        # a schedule firing tonight uses the credential replaced this afternoon (R-SEC-1).
        return process.told(said, await self._kept())

    async def _asked(self, one, held: str, admitted=None):
        """Admit a turn for a schedule that asks one, and hand back how it ended.

        **Through a collaborator, never by reaching for one.** A turn needs an agent, a brain
        and an account of what it did, and a gateway knows none of those — so whoever knows
        what an agent is builds this and hands it over already made, exactly as the surfaces
        this gateway holds open are handed over (R-AGT-9). The whole outcome comes back so
        the final channel report retains the usage and provider facts the turn recorded
        (R-SCH-50); this gateway still reads only `became` for its own schedule accounting.

        The overlap guard is the same one a program gets and is asked the same way: a turn is
        registered under the schedule's own name for as long as it runs, so a schedule cannot
        begin again over its own last one (R-SCH-6). A turn is not a program this gateway
        started, so it is not in `running` and a shutdown does not end it — what it *does* do
        is cancel the task waiting here, which is recorded as an interruption above.

        **`admitted` is told the moment this run is really going to happen** (R-SCH-46) —
        after the guard that refuses one still running, and before the brain is asked. That
        is the only point at which saying so is true: earlier includes firings that are
        about to be refused, and later is after the twenty minutes an owner spent wondering
        whether anything had started.
        """
        if self.asking is None:
            raise Unrunnable(
                f"schedule '{one.name}' asks a turn, and this gateway was given nothing to "
                f"ask one with")
        if held in self._asked_for or held in self.running:
            raise AlreadyStarted(f"'{held}' is already running under gateway '{self.name}'")
        self._asked_for.add(held)
        try:
            if admitted is not None:
                await admitted()
            return await self.asking(one)
        finally:
            self._asked_for.discard(held)

    async def _over_and_over(self, every: float, do, failed: str,
                             at_once: bool = False) -> None:
        """Do this at intervals, for as long as the gateway lives.

        Nothing short of being cancelled stops it. Both callers are tasks nobody awaits,
        so an exception in either is raised nowhere at all — it simply ends the task, and
        the gateway carries on having quietly stopped beating, or stopped looking at the
        clock, with nothing to say it had.

        `at_once` also does it before the first wait. Asked for rather than assumed,
        because the two callers want opposite things: the clock has a minute it can miss
        and the beat has nothing to say until there is something to say it about.
        """
        waiting = not at_once
        while True:
            try:
                if waiting:
                    await asyncio.sleep(every)
                # Set before `do`, not after: something that raised has still had its turn,
                # and a first look that failed must not become a second one with no wait.
                waiting = True
                do()
            except asyncio.CancelledError:
                raise
            except BaseException as went_wrong:  # noqa: BLE001 — see the docstring
                self.log.warning(failed, went_wrong)

    def _remember_firing(self, name: str, at: datetime) -> bool:
        """That the clock started this, written before it runs — and whether it was.

        `at` is the minute it *fell due*, and only the clock moves it: a run by hand leaves
        it alone, which is what keeps asking for something now from quietly cancelling
        tonight (R-SCH-22). Written in the minute a schedule is stated in, because that is
        what it is compared against and what an owner reads back.

        False rather than raising, because the caller's answer to a firing that could not be
        written down is not to start it: work that visibly happened with nothing durable
        saying so repeats on the way back up, which is the whole reason it is written first.
        """
        if self.records is None:
            return False
        try:
            self.records.schedule_fired(name, at.strftime(schedule.A_MINUTE), STARTED)
        except Exception as why:  # noqa: BLE001 — a durable-write boundary; see below
            # Broad on purpose, and narrower than the alternative. What can go wrong here
            # belongs to whatever holds the records, and a gateway does not know what that
            # is; naming those types here would be the one place it learned. Every one of
            # them means the same thing to the caller — the firing is not written down, so
            # the work must not start — and it is said rather than swallowed.
            self.log.warning("could not write down that '%s' fired: %s", name, why)
            return False
        return True

    def _remember_outcome(self, name: str, outcome: str) -> None:
        """What the work a schedule started turned out to be, once it is over.

        The minute is not passed and cannot be moved from here. Writing the moment a run
        *finished* into it moved the time forward, and a gateway restarting then read that
        later minute as the last one to have fired — so every schedule due in between was
        passed over as already done.

        Never worth raising over: this is an account of something that has already happened,
        and the work is done either way.
        """
        if self.records is None:
            return
        try:
            self.records.schedule_became(name, outcome)
        except Exception as why:  # noqa: BLE001 — see `_remember_firing`
            # And broad for one more reason here: this is called from inside the handlers
            # that catch a schedule failing, in a task nobody awaits. Raising from there
            # would replace the failure being recorded with this one, and asyncio would
            # report it on stderr — which for a supervised gateway is a file rundesk does
            # not read (R-GW-18).
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
            # The same moment, kept where it outlives this gateway. The record goes when
            # the gateway is stopped cleanly, and this is the only thing left that can
            # say how long nothing was running (R-SCH-5).
            if self.records is not None:
                self.records.seen()
        except Exception as err:  # noqa: BLE001 — a durable-write boundary
            # A gateway that cannot say it is alive is still alive, and stopping serving
            # over it would turn a full disk into an outage. Broad because this is called
            # from `start`'s `finally` and from the shutdown, where raising would replace
            # the thing being reported — and because what can go wrong here now belongs to
            # whatever holds the records, which this file does not know.
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
