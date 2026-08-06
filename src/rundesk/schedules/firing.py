"""Turning a schedule that is due into work that has started, and writing down what became of it.

`due` decides *when* and knows nothing else. This is the other half: it starts what a schedule
names, keeps hold of it, reaps it, and says all of that where somebody can read it afterwards. It is
the first thing in this product to spawn a child, so the four rules `gateways.host`'s docstring sets
out for whoever did that first are answered here.

## The lock is the claim, and it is held by the child rather than by us

A firing takes an exclusive `flock` on `schedules/<name>.lock`, and **hands the descriptor to the
child**. A `flock` belongs to the open file description, so it lives exactly as long as the child and
everything it started, and the kernel drops it however they end — a clean exit, a crash, a `SIGKILL`,
the machine losing power. Nothing has to be tidied up for the answer to become correct.

Three things fall out of that, and each of them is a defect in the build this replaces:

**A schedule cannot begin again while the last one is still going**, across processes. The old build
funnelled by name *inside* the gateway, so `rundesk schedules run` typed at a terminal knew nothing
about it and could start a second copy of the same work.

**A schedule is never shown as running when it is not.** The question is put to the kernel, never to
something a process wrote down: a pid in a file is a number that is reused, and a gateway killed
outright leaves that number pointing at a stranger's program.

**A gateway that came up after the one which started the work still knows work is going on.** It
cannot reap it — a status belongs to the parent — so what it can honestly say is `stopped`, and that
is what it says.

## Written down before the spawn, and why the pid arrives a moment later

The record beside the lock is written **before** `Popen` is called, carrying everything known then:
which schedule, which minute it fired for, and where in the output file this run begins. The pid
cannot be in it, because the pid does not exist yet — it is written into the same record immediately
afterwards.

That window is one `os.replace` wide and it costs one thing only: a gateway `SIGKILL`ed inside it
cannot *stop* that child later. It can still see it — the lock says so — and it still refuses to
start a second one. The alternative, writing the record after the spawn, loses the firing entirely:
nothing on disk would say the work had begun, so the next gateway would run the same side-effecting
job again.

## An outcome is one of three words, and `stopped` is not a failure

`completed` and `failed` come from an exit code this process collected. `stopped` is *nobody can
say* — the gateway that started the work is gone, or the work was ended by a shutdown — and work
that may well have finished perfectly is never written down as having failed.

## Saying so out loud, without knowing what a channel is

Two of those three words are worth somebody hearing about, and the log is not where anybody hears
anything. But this layer may not import `channels` — that is the same boundary `gateways` is kept on
the other side of — so a `Telling` is handed in beside `starting` and `asking`, and the layer that
may see both fills it in. **`completed` is never told**, deliberately: a notice per successful
nightly job is how somebody learns to ignore the channel.

## Nothing here may end a gateway

Every failure in this module is caught and written to the agent's log. A firing that could not be
recorded, a program that is not on the machine, a disk that filled — none of them is a reason to
take down a gateway that is otherwise hosting its agent, and letting one through would exit non-zero
into `KeepAlive`, be brought straight back into the same condition, and become the endless restart
`gateways.host` is arranged to make unreachable.

May depend on `agents`, `core` and `utils`, and not on `gateways`: where a gateway keeps its log is
handed in, so every case here runs with no supervisor and no launchd anywhere near it.
"""

import contextlib
import datetime
import fcntl
import os
import shlex
import signal
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, NamedTuple, Optional, Protocol

from rundesk.agents import directory
from rundesk.core import paths
from rundesk.schedules import due, kept
from rundesk.utils import files, locking, logs, programs

#: What a firing keeps beside itself, inside the agent's own `schedules/` directory.
LOCK_ENDS = ".lock"
RECORD_ENDS = ".json"
OUTPUT_ENDS = ".out"

#: When a schedule's output file is worth moving aside, and how many previous ones are kept. The
#: same shape `gateways.host` rotates the supervisor's captures with, and for the same reason: a
#: schedule that runs every minute for a year would otherwise leave one file nothing ever sweeps.
OUTPUT_OVER = 256 * 1024
OUTPUTS_KEPT = 3

#: How much of what a run wrote is copied into the agent's log, and how much of one line.
#:
#: Bounded, because the log is the thing somebody reads to find out what went wrong and a program
#: that writes a megabyte of progress bars would roll the evidence off the end of it — the failure
#: destroyed in the act of reporting it. The whole output stays in `<name>.out`, which is where the
#: log line points.
SAID_AT_MOST = 20
LINE_AT_MOST = 500
READ_AT_MOST = 64 * 1024

#: The least any one child is given to stop before it is told, however many there are. The job's
#: whole `ExitTimeOut` is twenty-five seconds and everything an orderly stop does has to fit inside
#: it, so `stopping` divides the budget it was handed rather than spending a fixed amount each.
STOPPING_LEAST = 1.0

#: Which of the caller's own environment a started program inherits, and the whole of it.
#:
#: **`RUNDESK_HOME` and nothing else of this product's.** A schedule's program may itself be
#: `rundesk`, and it has to read the same install the gateway starting it reads — the build this
#: replaces had five location variables and left one out of the job, so a schedule could be added,
#: listed and shown as due by the command line while the gateway keeping the machine knew nothing
#: of it. One variable is why that is not expressible here.
#:
#: The rest is what any program needs to run at all. `TZ` is in the list because a schedule is
#: stated on this machine's clock, and a child that disagreed about the zone would date its own work
#: differently from the schedule that started it.
CARRIED = ("PATH", "HOME", "TMPDIR", "TZ", "LANG", "LC_ALL")

#: The signals a supervisor or a person ends a process with, held off for exactly as long as it
#: takes to start a child and write down that it was started. See `_uninterrupted`.
#:
#: Named here rather than read from `gateways.host`, which this layer may not import. That is the
#: layer boundary being kept rather than a duplication to remove: what a *stop* is asked with is a
#: fact about Unix, and this module needs it without needing to know what a gateway is.
STOPPED_WITH = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)

#: What is said about a schedule that asks an agent when nothing was handed in to start one.
#:
#: **Not the ordinary case.** A running gateway always hands one in, so this is what a caller that
#: did not — a test, or something driving `looked` by hand — is told. The sentence is about the
#: *runner* being absent and says so, because a schedule reported as failing for a reason nobody can
#: act on is worse than one that is refused in words.
NOT_PROVEN = ("no provider process was handed in, so a schedule that asks an agent cannot be "
              "started here — it is recorded and it is not run")


class Occupied(Exception):
    """What this schedule started last time is still running, so a second one may not begin.

    Named rather than answered as a boolean, because the two callers do different things with it: a
    gateway writes a line and goes on to the next schedule, and a person who typed
    `rundesk schedules run` is told to their face.
    """


class NoRunner(Exception):
    """Nothing in this release can start what this schedule names.

    Deliberately not the same answer as `Occupied`: one is a schedule that is working and busy, and
    the other is a schedule that has never been able to run and will not until a provider process
    exists. Told apart because what somebody does about them is different.
    """


class Running(NamedTuple):
    """One firing this process is watching, and whether it is one this process can answer for.

    `mine` is the field that decides what may be said at the end. A child this process started can
    be collected, so its exit code is a fact; one adopted from a gateway that is gone cannot be, and
    the only honest word for it is `stopped`.

    `from_byte` is where in `<name>.out` this run's output begins, so the lines copied into the log
    are this run's and not the whole history of the file.
    """

    name: str
    pid: Optional[int]
    fired_for: str
    mine: bool
    from_byte: int
    since: float


class Watching(NamedTuple):
    """What one gateway is keeping track of between beats.

    `running` is the firings in flight. `complained` is what has already been said, so that a bad
    cron or a database nobody can read is reported **once** rather than every fifteen seconds for as
    long as it stays wrong — which is a log that grows without bound in the act of reporting
    something that is not going to change.

    Held by the caller and handed back rather than kept here, the way `gateways.host` already
    carries `landing` and `swept_for`: a module that remembered this itself would be one that two
    gateways in one test process could not use independently.
    """

    running: Dict[str, Running]
    complained: Dict[str, str]


class Starting(Protocol):
    """How a schedule's work is actually begun, handed in rather than reached for.

    **This is the seam the provider process arrives at.** A schedule that asks an agent is decided
    by the clock exactly as one naming a program is; the only thing missing is something of this
    shape that knows how to start a turn. Given a schedule, the agent it belongs to, and a
    descriptor to keep hold of, start something and hand back its pid.
    """

    def start(self, one: due.Schedule, agent: str, holding: int) -> int:
        ...


class Telling(Protocol):
    """How a gateway says something out loud, to a person rather than to a file. Handed in.

    **The seam exists for the layer rule, not for elegance.** `schedules` may not import `channels`
    — a schedule is a row in an agent's records and what carries a sentence to a platform is a
    different question — so a firing that wanted to tell somebody a nightly job had failed would
    otherwise have had to reach a layer it is not allowed to know about. The same shape as `Starting`
    and for the same benefit: the whole of this module goes on running with no channel, no adapter
    and no platform anywhere near a case.

    `None` is an ordinary answer and means nobody is told anything, which is what an agent with no
    notified channel asked for.
    """

    def say(self, saying: str) -> None:
        ...


class AProgram:
    """Start the program a schedule names, in a session of its own, holding the firing's lock."""

    def start(self, one: due.Schedule, agent: str, holding: int) -> int:
        return programs.start(
            argv=argv_of(one.command or ""),
            log=output_of(agent, one.name),
            where=directory.home(agent),
            env=the_environment(),
            holding=(holding,),
        )


# -- where a firing keeps its things ---------------------------------------------------


def lock_of(agent: str, name: str) -> Path:
    """The file the kernel holds while this schedule's work is running."""
    return directory.schedules(agent) / f"{name}{LOCK_ENDS}"


def record_of(agent: str, name: str) -> Path:
    """What a firing wrote about itself. Never the thing that decides whether it is running."""
    return directory.schedules(agent) / f"{name}{RECORD_ENDS}"


def output_of(agent: str, name: str) -> Path:
    """Everything this schedule's work has ever written, appended to across runs."""
    return directory.schedules(agent) / f"{name}{OUTPUT_ENDS}"


def argv_of(said: str) -> List[str]:
    """What a schedule's `command` column means, as a list of words. **Never through a shell.**

    Split the way a shell would word-split it, so an owner can write
    `--run '/usr/local/bin/backup.sh --full'` and get the two words they meant — and then handed
    straight to `execve` as a list, so nothing in it is globbed, expanded, or read as `;`, `&&` or a
    redirection. A schedule that could reach a shell would be a schedule where `$HOME` means one
    thing when a person tests it and another when the gateway runs it.

    An unbalanced quote comes back as no words at all, which `programs` refuses as a program that
    did not start. It is refused where it is typed by the command layer, so reaching this at all
    means a row somebody edited by hand.
    """
    try:
        return shlex.split(said)
    except ValueError:
        return []


def the_environment() -> Dict[str, str]:
    """What a started program is given, and the whole of it. See `CARRIED`."""
    given = {paths.HOME_IS: str(paths.home())}
    for name in CARRIED:
        if name in os.environ:
            given[name] = os.environ[name]
    return given


@contextlib.contextmanager
def claiming(agent: str, name: str) -> Iterator[int]:
    """Take this schedule's lock for the length of the block. `Occupied` when somebody has it.

    **The claim is the check**, exactly as `gateways.standing.holding` is: anything that asks
    whether a firing is running and then starts one has two decisions with a gap between them, and a
    second firing can arrive inside it.

    Asked once and never waited on — a lock this cannot have is not a busy moment to sit out, it is
    the answer.

    Yields the descriptor, because a caller that is about to spawn has to hand it to the child. On
    the way out this process's own copy is closed, which is what lets go of the claim *here* — the
    child's copy keeps it for as long as the child lives.

    **The file itself is left alone.** A lock lives on the inode, so unlinking it hands the name
    away and lets the next claim lock a fresh inode while this one is still held.
    """
    at = directory.schedules(agent)
    at.mkdir(parents=True, exist_ok=True)
    held = os.open(at / f"{name}{LOCK_ENDS}", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as why:
            if not locking.busy(why):
                raise
            raise Occupied(f"what {name} started last time is still running") from why
        yield held
    finally:
        os.close(held)


@contextlib.contextmanager
def _uninterrupted() -> Iterator[None]:
    """Hold off a request to stop for the length of the block, and let it through afterwards.

    **For starting a child and writing down that it was started, and for nothing else.** Those two
    have to be one step: a stop landing between them leaves work running that the shutdown then in
    progress cannot see, and the only thing left pointing at it is a lock nobody will look at until
    the next gateway comes up.

    Blocked at the thread rather than by ignoring the signal, so nothing is *lost*: a stop asked for
    inside the block is delivered the moment the block ends, which is the next thing that happens.
    A gateway is never held for longer than one `fork` and `exec` by this.

    A platform without `pthread_sigmask` is not a reason to refuse to fire a schedule — the window
    goes back to being what it was, which is what every version of this before it had.

    `STOPPED_WITH` names the signals rather than reaching for `gateways.host`, which this layer may
    not import. They are the three a supervisor or a person ends a process with, and the list is
    short because the block is short.
    """
    try:
        before = signal.pthread_sigmask(signal.SIG_BLOCK, STOPPED_WITH)
    except (AttributeError, OSError, ValueError):
        yield
        return
    try:
        yield
    finally:
        with contextlib.suppress(OSError, ValueError):
            signal.pthread_sigmask(signal.SIG_SETMASK, before)


def still_running(agent: str, name: str) -> bool:
    """Whether a firing of this schedule is in flight, asked of the kernel.

    **Probed with a shared lock**, for the reason `standing.standing` gives: an exclusive probe
    conflicts with another *probe*, so two people asking at the same moment would each read the
    other as a running firing.

    **Never creates the file.** A lock that is not there means this schedule has never fired, and a
    question that writes is a question that fails on a read-only disk.

    **"In flight" begins at the claim and not at the spawn**, and the difference is a moment long
    but it is real: the lock is taken *before* the child exists, which is what stops two gateways
    starting one schedule between them. So this answers yes for the instant between claiming and
    spawning, when there is nothing yet to stop. That is the right answer for the question it is
    asked — may a second firing begin? — and the wrong one for *has the work started?*, which is
    what the log line says and what a caller wanting that should read.
    """
    try:
        asked = os.open(lock_of(agent, name), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(asked, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError as why:
        return locking.busy(why)
    finally:
        os.close(asked)
    return False


def in_flight(agent: str) -> List[str]:
    """Every schedule of this agent's with work still going, by name. Asked of the kernel.

    **For whoever is about to take something away from underneath it.** Removing an agent unlinks
    this whole directory, and unlinking a lock somebody is holding is how two firings of one schedule
    come to run at once: the name is handed away, so the next claim creates a fresh inode and locks
    *that* while the original child holds the old one. `agents remove` is the caller, and it needs to
    know before it acts rather than after.

    Read off the lock files rather than off the records, and that is the point of it: a removal has
    to be able to ask this even when the database is unreadable, and a firing that is running is
    running whether or not anything can still say why.
    """
    try:
        locks = sorted(directory.schedules(agent).glob(f"*{LOCK_ENDS}"))
    except OSError:
        return []
    return [one.name[:-len(LOCK_ENDS)] for one in locks
            if still_running(agent, one.name[:-len(LOCK_ENDS)])]


# -- coming up, and looking at the clock -----------------------------------------------


def settled(agent: str, where: Path) -> Watching:
    """Reckon with what a previous gateway left, before this one starts anything. **Never raises.**

    Every record standing in `schedules/` belongs to a firing that was never reaped, because a
    reaped one takes its record with it. Two things it can be, told apart by the kernel and not by
    the record:

    **The lock is free** — the work is over, and the gateway that could have said what it came to is
    gone. Written down as `stopped`, which is *nobody can say*, and said in the log so that a person
    looking at a schedule with an odd outcome finds out why rather than inferring it.

    **The lock is held** — the work is still going, under a gateway that no longer exists. Adopted
    and watched, so this gateway will not start a second one and will say `stopped` when it ends.
    Not `mine`: its exit status belonged to a process that is gone.
    """
    watching = Watching({}, {})
    try:
        left = sorted(directory.schedules(agent).glob(f"*{RECORD_ENDS}"))
    except OSError:
        return watching
    for one in left:
        name = one.name[:-len(RECORD_ENDS)]
        with contextlib.suppress(Exception):                    # coming up may not
            # fail over a record somebody left; see the module docstring.
            _reckoned(agent, where, name, watching)
    return watching


def _reckoned(agent: str, where: Path, name: str, watching: Watching) -> None:
    """One record a previous gateway left, adopted or written off. Called only by `settled`."""
    if still_running(agent, name):
        said = _read_record(agent, name)
        _note(where, f"schedule {name} was already running when this gateway came up, under a "
                         "gateway that is gone — it is being watched, and what it comes to cannot "
                         "be read", logs.WARNING)
        watching.running[name] = Running(
            name=name, pid=programs.a_pid(said.get("pid")), fired_for=str(said.get("fired_for") or ""),
            mine=False, from_byte=_a_size(said.get("from_byte")), since=time.monotonic())
        return
    _note(where, f"schedule {name} was interrupted: the gateway that started it is gone, so "
                     "what it came to cannot be read", logs.WARNING)
    _became(agent, where, name, kept.STOPPED)
    files.remove_one(record_of(agent, name))


def looked(agent: str, where: Path, watching: Watching,
           moment: Optional[datetime.datetime] = None,
           starting: Optional[Starting] = None,
           asking: Optional[Starting] = None,
           telling: Optional[Telling] = None) -> Watching:
    """Look at the clock, reap what has finished, and start whatever the time has come for.

    **This never ends the caller.** Everything below is guarded, for the reason
    `host._still_working` gives: a gateway that could not fire a schedule is still hosting its
    agent, and ending it over that would take a working gateway down into a restart loop it can
    never leave.

    `moment` and both starters arrive as arguments and are resolved **in the body**, never bound in
    the signature — a default decided once, when the function is defined, is a default nothing can
    reach past.

    **What has already fired is read off the records, not remembered.** Every schedule's own
    `last_fired_for` is the guard, so a gateway that has just come up knows exactly as much as one
    that has been up for a week, and the same minute cannot fire twice across a restart. The build
    this replaces held that in memory and lost it with the process.

    `asking` is what starts a schedule that asks an agent, and `gateways.host` hands one in on every
    beat — so it is `None` only where a caller left it out, which is every case in this suite and
    nothing in a running gateway. A schedule of that kind with nothing to start it is claimed,
    refused in one line, and written down as `failed`, because a schedule silently passed over looks
    exactly like one that is working. **`firing` still knows nothing about a brain**: it starts what
    it was handed and reaps a pid.

    `telling` is where a firing that went wrong is said out loud, and it reaches `_finished` and
    nothing else — see there for why a firing that went *right* says nothing.
    """
    now = moment if moment is not None else datetime.datetime.now()
    starting = starting if starting is not None else AProgram()

    watching = _reaped(agent, where, watching, telling)
    try:
        rows = kept.all(agent)
    except Exception as why:                                    # noqa: BLE001 — records can be
        # anything at all on disk, and a gateway that cannot read them is still a gateway.
        return _said_once(where, watching, None, f"no schedule can run: {why}", logs.ERROR)

    wanted, refused = due.read(rows)
    for name, why in refused:
        watching = _said_once(where, watching, f"row:{name}",
                              f"schedule {name} cannot be understood: {why}", logs.ERROR)

    already = {}
    for one in wanted:
        minute = due.from_minute(one.fired_for)
        if minute is not None:
            already[one.name] = minute

    for one in due.due(wanted, now, already):
        with contextlib.suppress(Exception):                    # see the docstring.
            watching = _fired(agent, where, watching, one, now, starting, asking)
    return watching


def _fired(agent: str, where: Path, watching: Watching, one: due.Schedule,
           now: datetime.datetime, starting: Starting,
           asking: Optional[Starting]) -> Watching:
    """Start one schedule that is due, in the order the guarantees require.

    1. **Take the lock**, because that is what says the last one has finished. Refused → say so, and
       claim the minute anyway so the refusal is written once per occurrence rather than once per
       beat for as long as the work runs.
    2. **Claim the minute durably**, and start nothing if that write failed. Work that has visibly
       happened with nothing recording it is work that repeats on the way back up, which is the very
       thing writing it first is for.
    3. **Write the record**, then spawn.
    """
    minute = due.as_minute(now)
    try:
        with claiming(agent, one.name) as held:
            _note(where, f"schedule {one.name} is due for {minute}")
            if not _claimed(agent, where, one.name, minute):
                _note(where, f"schedule {one.name} was not started: its firing could not be "
                                 "written down, and a run nothing records may happen twice",
                          logs.ERROR)
                return watching
            run_by = starting if one.command else asking
            if run_by is None:
                _note(where, f"schedule {one.name} cannot be started: {NOT_PROVEN}", logs.ERROR)
                _became(agent, where, one.name, kept.FAILED)
                return watching
            return _spawned(agent, where, watching, one, minute, held, run_by)
    except Occupied:
        _note(where, f"schedule {one.name} skipped: what it started last time is still running",
                  logs.WARNING)
        _claimed(agent, where, one.name, minute)
        return watching


def _spawned(agent: str, where: Path, watching: Watching, one: due.Schedule, minute: str,
             held: int, run_by: Starting) -> Watching:
    """Write the firing down, start it, and take hold of it. The lock is already claimed."""
    output = output_of(agent, one.name)
    output.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        logs.rotated(output, OUTPUT_OVER, OUTPUTS_KEPT)
    from_byte = output.stat().st_size if output.is_file() else 0

    said = {"schedule": one.name, "fired_for": minute, "from_byte": from_byte,
            "started_at": logs.stamp(), "pid": None}
    # Before the spawn, without the pid, which does not exist yet — see the module docstring on the
    # one `os.replace` of window this leaves, and why the other order is worse.
    files.write_json(record_of(agent, one.name), said)

    # **Starting a child and taking hold of it are one indivisible step.** A gateway asked to stop
    # raises from a signal handler, which lands wherever the interpreter happens to be — so a stop
    # arriving anywhere between `Popen` returning and the line below left a running child that the
    # shutdown then in progress knew nothing about, with nobody to reap it and nothing but its lock
    # to find it by. Measured rather than imagined: one run in three of the case that stops a
    # gateway mid-firing left the work running and the gateway gone.
    #
    # The `finally` alone was not enough, because the window is also *inside* `programs.start`,
    # between `Popen` returning and its own bookkeeping. Holding the stop off is what closes it, and
    # it is held off for these few instructions and nothing else.
    pid, trouble = None, None
    with _uninterrupted():
        try:
            pid = run_by.start(one, agent, held)
        except programs.CouldNotStart as why:
            trouble = why
        finally:
            if pid is not None:
                watching.running[one.name] = Running(
                    name=one.name, pid=pid, fired_for=minute, mine=True, from_byte=from_byte,
                    since=time.monotonic())

    if trouble is not None:
        # A program that was never on the machine has no exit code, and reporting one would say it
        # ran and disagreed — a different fact about the machine, leading somewhere else.
        _note(where, f"schedule {one.name} did not start: {trouble}", logs.ERROR)
        _became(agent, where, one.name, kept.FAILED)
        files.remove_one(record_of(agent, one.name))
        return watching

    said["pid"] = pid
    with contextlib.suppress(OSError):
        files.write_json(record_of(agent, one.name), said)
    _note(where, f"schedule {one.name} started as pid {pid}: "
                 f"{' '.join(argv_of(one.command or ''))}")
    return watching


def _reaped(agent: str, where: Path, watching: Watching,
            telling: Optional[Telling] = None) -> Watching:
    """Take the status of every firing that has finished, and say what it came to.

    A child this process started answers with an exit code. One adopted from a gateway that is gone
    cannot — a status belongs to the parent — so it is watched until the kernel drops its lock, and
    then written down as `stopped`.
    """
    for name in list(watching.running):
        one = watching.running[name]
        with contextlib.suppress(Exception):                    # reaping is an
            # account of the work and never the work: nothing here may end a gateway.
            if one.mine and one.pid:
                gone = programs.collected(one.pid)
                if not gone.over:
                    continue
                code = gone.code
            else:
                if still_running(agent, name):
                    continue
                code = None
            del watching.running[name]
            files.remove_one(record_of(agent, name))
            _finished(agent, where, one, code, telling)
    return watching


def _finished(agent: str, where: Path, one: Running, code: Optional[int],
              telling: Optional[Telling] = None) -> None:
    """Write down what one firing came to, in the row and in the log, with what it wrote.

    **The time is said as an upper bound, because that is the only honest thing to say about it.**
    A gateway notices a child has finished on the beat after it did, so the figure here is the age of
    the firing when it was *noticed* and not how long the work took — measured on a real run, an
    `/bin/echo` that took milliseconds was reported as having taken fifteen seconds. Somebody sizing
    a backup window would read that and believe it. Saying *under* is true whatever the beat is, and
    on a run of any real length the difference stops mattering.

    **Said out loud only when it went wrong**, and that restraint is the whole of what makes a
    notified channel worth having: a message for every successful nightly job is how somebody learns
    to ignore the channel, and the one they then miss is this one. `stopped` is told as well as
    `failed`, because *nobody can say what it came to* is exactly the answer somebody would want to
    hear about rather than find later.

    Told **last**, and inside a guard of its own. What became of a firing is written down whatever a
    platform does with it, and a notice that could not go out may not cost the record that says the
    work happened.
    """
    took = _how_long(time.monotonic() - one.since)
    if code is None:
        outcome, level = kept.STOPPED, logs.WARNING
        said = f"stopped within {took} — nobody can say what it came to"
    elif code == 0:
        outcome, level = kept.COMPLETED, logs.INFO
        said = f"completed in under {took}"
    else:
        outcome, level = kept.FAILED, logs.ERROR
        said = f"failed with exit {code} in under {took}"
    _note(where, f"schedule {one.name} {said}", level)
    for line in _what_it_wrote(output_of(agent, one.name), one.from_byte):
        _note(where, f"  {line}", level)
    _became(agent, where, one.name, outcome)
    if telling is not None and outcome != kept.COMPLETED:
        with contextlib.suppress(Exception):                    # a channel that is
            # down is not a reason to lose a firing, and this module may never end a gateway.
            telling.say(f"schedule {one.name} {said}")


def let_go(agent: str, name: str) -> List[Path]:
    """Take away what a schedule's firings left behind, and say what went. Nothing when work is live.

    **Only while the lock is free, and that is not tidiness — unlinking a held lock is how two
    firings of one schedule come to run at once.** A lock lives on the inode: removing the name hands
    it away, so the next claim creates a fresh inode and locks *that*, while the child still holding
    the old one goes on running. So a schedule taken away mid-run keeps its files, the work finishes,
    and the next gateway reckons with the record exactly as it would have anyway.

    Named one thing at a time and never globbed, for the reason `directory.forgotten` gives: a glob
    over a schedule's name is easy to get subtly wrong, and what is left behind is a lock file the
    next schedule of that name inherits.
    """
    if still_running(agent, name):
        return []
    gone = []
    for one in (lock_of(agent, name), record_of(agent, name), output_of(agent, name)):
        if files.remove_one(one):
            gone.append(one)
    return gone


# -- going down ------------------------------------------------------------------------


def stopping(agent: str, where: Path, watching: Watching, within: float) -> Watching:
    """Stop everything this gateway started, inside the budget it was given.

    **No ordinary failure escapes this**, which is not quite the same promise as *never raises* and
    the difference was worth finding: a request to *stop* is deliberately a `BaseException` so that
    the guards in this module cannot swallow it, and this function is reached during a shutdown that
    is itself the answer to one. A second `SIGTERM` landing in the middle of it would therefore go
    straight through `suppress(Exception)` and out of the gateway, exit non-zero, and be read as a
    request to be restarted. **The caller is what makes that unreachable** — `gateways.host` stands
    its handlers down once a stop is under way, and says so where it does it.

    The whole of an orderly stop has to fit inside the job's `ExitTimeOut`, or launchd `SIGKILL`s
    the gateway and every child is orphaned still holding its lock — so the budget is divided among
    the children rather than spent per child, and a gateway with ten of them gives each a tenth.

    **Only what this process started.** A firing adopted from a gateway that is gone belongs to
    nobody here: its process group was never ours to signal, and ending a stranger's program on the
    way out is worse than leaving it to finish.
    """
    mine = [one for one in watching.running.values() if one.mine and one.pid]
    if not mine:
        return watching
    each = max(STOPPING_LEAST, within / len(mine))
    for one in mine:
        with contextlib.suppress(Exception):                    # a stop that failed
            # may not stop the next one, and this gateway is on its way out either way.
            gone = programs.collected(one.pid)
            if gone.over:
                # **Finished between the last beat and this shutdown, so it is reaped and not
                # stopped.** Two reasons, and the second is the one that was measured. It gets its
                # real outcome rather than being written down as `stopped`, which would be a worse
                # answer than the one available. And nothing signals a process that has gone: a pid
                # whose leader has been collected no longer resolves to a group, `programs.stop`
                # falls back to treating the pid *as* the group id, and process ids are reused — so
                # a gateway going down was seen asking the kernel to end a group that had nothing to
                # do with it, and being told it had no permission. Being refused is luck, not a
                # design.
                _finished(agent, where, one, gone.code)
                files.remove_one(record_of(agent, one.name))
                del watching.running[one.name]
                continue
            stuck = programs.stop(one.pid, gently_for=each * 0.6, firmly_for=each * 0.4)
            said = f"would not stop: {stuck}" if stuck else "was stopped with this gateway"
            _note(where, f"schedule {one.name} {said}", logs.WARNING)
            _became(agent, where, one.name, kept.STOPPED)
            files.remove_one(record_of(agent, one.name))
            del watching.running[one.name]
    return watching


# -- by hand -----------------------------------------------------------------------------


def by_hand(agent: str, name: str, waiting: float, where: Optional[Path] = None,
            moment: Optional[datetime.datetime] = None) -> programs.Ran:
    """Run one schedule now, in the foreground, and hand back everything the program said.

    **The one moment a schedule states is never used up by this, and when it next falls due does not
    move.** Running by hand is a person checking their own work; a run that consumed the occurrence
    would mean testing a schedule is how you stop it happening.

    What it *does* write is the outcome, because it did run and "what became of it last time" is now
    this. And it takes the same lock the clock takes, so a person cannot start a second copy of work
    a gateway is already doing — which the build this replaces could not prevent, its guard living
    inside the gateway process.

    `waiting` is required rather than defaulted, for the reason `programs.run` requires it: a wait
    with no end is a command that simply never returns.
    """
    one = due.understood(kept.one(agent, name))
    if not one.command:
        raise NoRunner(f"{name} cannot be run: {NOT_PROVEN}")

    with claiming(agent, name):
        output = output_of(agent, name)
        output.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            logs.rotated(output, OUTPUT_OVER, OUTPUTS_KEPT)
        if where is not None:
            _note(where, f"schedule {name} is being run by hand")
        ran = programs.run(argv_of(one.command), waiting=waiting,
                           where=directory.home(agent), env=the_environment())
        _kept_what_it_wrote(output, ran)

    outcome = kept.COMPLETED if (ran.trouble is None and ran.code == 0) else kept.FAILED
    with contextlib.suppress(Exception):                        # the run happened,
        # and failing to write down what it came to is not a reason to lose what it said.
        kept.became(agent, name, outcome, moment)
        if where is not None:
            became = ran.trouble or f"exit {ran.code}"
            _note(where, f"schedule {name} run by hand {outcome}: {became}",
                      logs.INFO if outcome == kept.COMPLETED else logs.ERROR)
    return ran


def _kept_what_it_wrote(output: Path, ran: programs.Ran) -> None:
    """Append what a foreground run said to the same file the clock's runs write to.

    The same file deliberately: somebody looking into a schedule should find every run of it in one
    place, whether the clock started it or they did.
    """
    with contextlib.suppress(OSError):
        with open(output, "a", encoding="utf-8") as writing:
            writing.write(ran.out)
            writing.write(ran.err)


# -- saying things -------------------------------------------------------------------------


def _note(where: Path, said: str, level: str = logs.INFO) -> None:
    """Write one line to the agent's log — unless the agent's own directory has gone.

    **`logs.note` makes the directory it writes into**, which is right for an agent that exists and
    wrong for one that has just been removed from under a running gateway: the gateway would put
    that directory back in the act of complaining that it is missing, leaving something on disk that
    looks like a half-made agent and that `directory.known` would go on skipping for ever.

    `gateways.host._still_working` guards the same way for the same reason. It is a single function
    here rather than a condition at each call site, because there are a dozen call sites and the one
    that forgot would be the one that ran on the day an agent was removed.

    **And it never raises.** A gateway loop is not a place to find out that a disk filled: writing a
    line about the work is not the work, and a beat that died complaining about its own logging
    would take every schedule on the machine with it. Its two siblings — `channels.hosting._note`
    and `providers.answering._note` — were written this way and this one was not, so one of them
    said it was guarded "for the same reason as `firing._note`" while `firing._note` was the one
    that was not.
    """
    with contextlib.suppress(Exception):
        if where.parent.is_dir():
            logs.note(where, said, level)


def _said_once(where: Path, watching: Watching, about: Optional[str], said: str,
               level: str) -> Watching:
    """Write a line only if it is not the same one this gateway last wrote about the same thing.

    A bad cron does not fix itself, so a gateway saying so every fifteen seconds would fill a day's
    log with one sentence — the growth `logs.swept` exists to bound, arrived at from the other side.
    `about` is `None` for the records themselves, which is a coarser piece of news than any one row's.
    """
    key = about or ""
    if watching.complained.get(key) == said:
        return watching
    _note(where, said, level)
    watching.complained[key] = said
    return watching


def _claimed(agent: str, where: Path, name: str, minute: str) -> bool:
    """Write down that this minute has been taken. `False` when it could not be written."""
    try:
        kept.claimed(agent, name, minute)
        return True
    except Exception as why:                                    # noqa: BLE001 — a database can be
        # anything on disk, and the caller's whole job is to start nothing when this failed.
        _note(where, f"schedule {name} could not have its firing written down: {why}",
                  logs.ERROR)
        return False


def _became(agent: str, where: Path, name: str, outcome: str) -> None:
    """Write down what a firing came to, and say so in the log if even that could not be done."""
    try:
        kept.became(agent, name, outcome)
    except Exception as why:                                    # noqa: BLE001 — see `_claimed`.
        _note(where, f"schedule {name} came to {outcome} and it could not be written down: "
                         f"{why}", logs.ERROR)


def _read_record(agent: str, name: str) -> Dict[str, Any]:
    """What a firing wrote about itself, or nothing at all when it cannot be read.

    Nothing here decides whether the work is running — the kernel does — so a record that will not
    parse costs only the pid, and answering with an empty mapping is the honest version of that.
    """
    how, said = files.read_json(record_of(agent, name))
    return dict(said) if how == files.READ and isinstance(said, dict) else {}


def _a_size(said: Any) -> int:
    """Where in the output file a run began, or the top of it when the record does not say."""
    if isinstance(said, bool) or not isinstance(said, int) or said < 0:
        return 0
    return said


def _what_it_wrote(one: Path, from_byte: int) -> List[str]:
    """The last few lines this run wrote, read from where this run began.

    From an offset rather than from the top, because the file is appended to across every run of the
    schedule: reading the whole of it would put last week's output under today's failure.
    """
    try:
        with open(one, "r", encoding="utf-8", errors="replace") as reading:
            reading.seek(from_byte)
            said = reading.read(READ_AT_MOST)
    except OSError:
        return []
    lines = [line[:LINE_AT_MOST] for line in said.splitlines() if line.strip()]
    return lines[-SAID_AT_MOST:]


def _how_long(seconds: float) -> str:
    """A duration as a person would say it. Measured on `time.monotonic()` and never on the clock.

    The wall clock moves in both directions — a laptop waking, an NTP correction — so a duration
    taken from it can come out negative or hours wrong, and the line reporting a run that took four
    minutes would say it took minus one.
    """
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}h{int(seconds % 3600 // 60):02d}m"
