"""The gateway process itself: one agent, one name held, and one exit code that means everything.

This is what launchd starts. It claims the agent's name, writes down what it is, says so every
fifteen seconds, and stops when it is asked to. What it hosts — adapters, delegated work, the
subprocesses an agent runs — is not here yet, and when it arrives it arrives as something this
process hosts rather than as something that changes what this process is.

## The exit code is the whole conversation with launchd

The job carries `KeepAlive {"SuccessfulExit": false}`, which means exactly one thing:

    exit 0        do not bring me back
    exit anything else       bring me back

Read forwards that is obvious. Read backwards it is the sharpest edge in this product: **an uncaught
Python exception exits 1**, so a gateway that refuses to run because its agent does not exist would
be brought back, refuse again, and be brought back again — for ever, escalating into launchd's
exponential throttling until the restarts are minutes apart and the whole thing simply looks like a
hang. A permanent condition would have become a loop, and nothing anywhere would name it.

So every refusal reaches `0`, **including the case where the refusal check itself raises**, and that
is arranged structurally rather than intended: `_may_not_run` cannot propagate anything, and the
claim on the agent's name is entered inside a guard of its own so that a failure *there* is a
refusal while a failure while *serving* is a crash. Once this process is up and working, an
exception is a crash and a crash should be restarted — that distinction is the whole shape of the
file.

## The first line is written before anything else, and it is not decoration

launchd captures our standard output to `logs/gateway.out`. If a spawn fails outright the reason
goes to the unified log **only** — it cannot go to `StandardErrorPath`, because that is the thing
that failed to open — so an empty `gateway.out` beside a job launchd says has run is the one signal
that the failure is upstream of this code. That single line, written before any parsing and before
any reading, turns "cannot tell" into "look here".

It is written a second time when the rotation below has just emptied that file, and the repetition is
the point rather than an accident of the order: the copy carried into `gateway.out.1` ends with the
line naming the process that rotated it, and the live file begins with the same line, so the two are
plainly one story and the file everybody opens is never left empty by us.

## The two files the supervisor captured, and why they are rotated by content

launchd opens `StandardOutPath` and `StandardErrorPath` `O_CREAT|O_RDWR|O_APPEND` — **never
`O_TRUNC`** — and it never rotates them (`docs/research/launchd-on-macos.md` §8). In a crash loop
every restart appends another traceback, for ever, and nothing comes to sweep it. They are also the
**only** account of a start that died before this process had a log of its own, so neither of the two
easy answers is honest: left alone they grow without end, and truncated on every start they erase the
one crash somebody needed to see.

**Who holds that descriptor is not a guess.** `/usr/libexec/xpcproxy` carries the call it makes,
read straight out of the binary with `strings -a` and corroborated by `nm -u`:

    posix_spawn_file_actions_addopen(&ctx->filact, 1, stdout_path,
                                     0x00000200|0x0002|0x00000008|0x00020000, 0666)

`O_CREAT | O_RDWR | O_APPEND | O_CLOEXEC`, mode `0666`, on descriptor `1` — and it is a **spawn file
action**, which means the open happens as part of creating this process rather than in the supervisor
beforehand. Nothing upstream keeps a copy: the only holder of that descriptor is this process, and
after that whatever this process passes it to. That is the whole answer to the question a rotation
has to ask, and it is also why the answer is safe from being wrong later — a holder is a holder, and
the approach below is right whether there is one of them or three.

**A rename is the wrong move, and the reason is the descriptor.** A descriptor refers to an inode and
not to a name. Whatever holds one open when the name is moved goes on writing into that same inode
under its new name — so a gateway would spend its whole life writing into `gateway.out.1` while
`gateway.out`, the path in the plist and the file everybody opens, stayed empty. Unlinking is worse:
the writes go somewhere with no name at all. It is measured in two places rather than reasoned about:
`tests/test_utils.py` watches a held `O_APPEND` descriptor go on writing into a file that has been
renamed away underneath it, and `tests/test_gateway_host.py` watches a real gateway — holding a real
inherited descriptor, opened and handed over the same way — go on writing into the file it has just
had emptied.

**So the content moves and the file stays.** `logs.rotated` copies the head aside to `gateway.out.1`
and truncates the original in place — same inode, same name, same descriptor. `O_APPEND` is what
makes that safe rather than merely possible: under it every write takes the offset and the write
together at the current end, so the next line lands at zero. Without it a holder keeps an offset of
its own and the next write leaves a hole of NUL bytes as long as everything that was there, and that
is asserted beside the rest rather than assumed.

**Only when it is worth it.** A gateway that `KeepAlive` brings back every thirty seconds starts
2,880 times a day, and rotating on every start would roll the evidence off the end of the kept files
within minutes of a crash loop beginning. `CAPTURE_OVER` is a size and nothing happens below it.

**Nothing the rotation writes goes into the live file**, which is deliberate rather than tidy: an
empty `gateway.out` beside a job launchd says has run is the signal that the failure is upstream of
this code, and a rotation that left a "rotated at ..." marker there would have destroyed the one
thing that file says by being empty. What lands in the emptied file is the first line above, said
again when a rotation has just happened — so the guarantee survives the rotation that would otherwise
have carried it off into `gateway.out.1`.

## Stopping politely, and why that is visible in the log

`SIGTERM` and `SIGHUP` are turned into an exception, so an orderly stop unwinds through the same
`finally` blocks everything else does and writes a line saying it stopped. A gateway that was killed
outright writes nothing, and the two are told apart by reading the log rather than by guessing. It
also has to happen inside the job's `ExitTimeOut`: a gateway that ignores `SIGTERM` makes
`bootout --wait` block for that whole window and then be `SIGKILL`ed, which is the state launchd
calls *languishing*. `cli._asked_to_stop_politely` is the same shape for the same reason.

## The clock a beat is measured on stops when the machine sleeps, and must go on stopping

Every beat writes a `time.monotonic()` reading into the gateway's record, and that reading is the
only thing `standing` judges staleness by. **On macOS `time.monotonic()` does not advance across
system sleep** — measured on this machine as a 40.5-hour gap over 14.66 days of wall clock — and that
is precisely why it is the right clock rather than a defect somebody should correct. A sleeping
laptop freezes this process too: it misses no beat it was awake for, and a clock that had gone on
counting through the sleep would have every single wake report a perfectly healthy gateway as wedged.
Anything that replaces this with a sleep-continuous clock trades a real report for a false one on
every laptop this ever runs on, and `time.time()` is not a candidate for a different reason: it moves
in both directions, so an age taken from it can be negative or hours out after an NTP correction.

## Nothing here starts a child yet, and what the first one has to do

`utils.programs.start` gives every long-lived child a session and a process group of its own, which
is what lets a gateway stop the whole tree it started. That has a consequence which only appears when
the gateway does **not** get to run its shutdown: a child in its own group is outside this process's
group, so launchd's group-wide cleanup of this job cannot reach it either. If this process is
`SIGKILL`ed — by `bootout` once `ExitTimeOut` runs out, by the machine reclaiming memory, by a person
— and no pid was written down before the spawn, that child is left running with nobody able to name
it, find it or reap it. It survives the restart, the fresh gateway knows nothing about it, and the
two of them then host one agent between them. That is the state that must not be reachable.

**This is a constraint on whoever adds the first adapter, not something built here.** `host` spawns
nothing today, and a record with no writer is machinery with no caller. What the first one has to do:

- **Write the pid down before the spawn, never after.** Everything between `Popen` returning and a
  record reaching the disk is a window in which a kill orphans that child for good, and a record
  written after the fact is a record that is missing exactly when it was needed.
- **Record enough to prove identity later, because a pid alone cannot.** Numbers are reused: a
  recorded pid that is alive tomorrow may be somebody else's program, and a gateway that signalled it
  would end a stranger's work. What it was, when it was started, and which agent it belongs to are
  what let a fresh gateway say *this is still the one I mean* before it acts.
- **Reconcile at startup, before claiming anything durable.** A gateway coming up reads what the
  previous one left and settles each entry — still running and still the same program, so adopted or
  stopped; gone, so removed. A record nothing ever reads back is a record that is always wrong.
- **The shutdown budget is what bounds all of it.** The job carries `ExitTimeOut = 25`, so everything
  an orderly stop does — asking each child, waiting on it, then telling it — has to fit inside
  twenty-five seconds from the `SIGTERM` or launchd `SIGKILL`s this process and every paragraph above
  becomes real. That is a ceiling on how many children may be stopped one after another and on how
  long each may be given, and it is the reason the record has to be on disk rather than in memory:
  the code that would tidy up is exactly the code that does not run.

The teardown half already has a seam and it is not a new function — `held`, the `ExitStack` in `run`,
is entered before anything durable happens and unwound however this process leaves, so a child's stop
belongs in it and nowhere else. `_serving` is not handed it today because nothing needs it yet. The
record half has no seam and is not getting one invented before there is a caller.

## This may not import `job`

**A process never talks to its own supervisor.** A gateway that could bootstrap, boot out or kick
its own job could restart itself — which is the loop above, reached deliberately — and it would put
the decision to keep a gateway running inside the thing being kept running. The layer that hands a
job to the machine is the layer that takes it back, and it is not this one. It is also what lets
this whole module be driven by a test with no launchd anywhere near it: everything below runs the
same whether it was started by a job, by a person, or by a suite.

May depend on `agents`, `core` and `utils`.
"""

import contextlib
import datetime
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from rundesk import __version__
from rundesk.agents import directory, migration
from rundesk.exits import OK
from rundesk.gateways import standing
from rundesk.utils import logs

#: What the very first line looks like. Deliberately not through `utils.logs`: this is written to
#: whatever the supervisor captured, before anything has been read or resolved, and the whole value
#: of it is that it lands even when everything after it fails.
FIRST = "[{when}] gateway {name}: this process is pid {pid}, running {version}\n"

#: When one of the supervisor's captures is big enough to be worth moving aside, and how many
#: previous ones are kept. See the module docstring for why this is a size rather than a start:
#: a gateway `KeepAlive` brings back every thirty seconds starts 2,880 times a day.
#:
#: A quarter of a megabyte is a few hundred tracebacks, which is a crash loop with its beginning
#: still in it, and four files of that is the whole of what these two may ever cost — a megabyte per
#: stream, per agent, whatever happens.
CAPTURE_OVER = 256 * 1024
CAPTURES_KEPT = 3

#: How many days of this gateway's own log are kept. Long enough that somebody looking into
#: something they noticed a fortnight ago still has the day it happened on, and short enough that a
#: gateway running since March is not a directory with two hundred files in it.
#:
#: Not configurable, and deliberately: a retention that can be set is a value in `config.json`, which
#: is persisted state and a decision for the owner rather than for this file.
KEPT_DAYS = 14


class Stopped(Exception):
    """A supervisor, or a person, asked this gateway to stop.

    Named rather than left as a flag somebody has to poll, and raised rather than set, because a
    flag does not interrupt a sleep: a handler that only recorded the request would leave this
    process waiting out the rest of its beat before noticing, and the beat is fifteen seconds inside
    a shutdown window of twenty-five.
    """


def run(name: str) -> int:
    """Host one agent until something stops this process. **Always `0` when it refuses to run.**

    The order is fixed and each step's answer is `0`, because each of them is a condition that
    restarting cannot fix:

    1. Say, on the very first line, what pid this is — before parsing or reading anything.
    2. The agent is not there. Nothing to host; being restarted every thirty seconds for ever would
       not make one appear.
    3. The agent is not settled onto this release. Its records were written by an older rundesk and
       the steps that would carry it have not run; `rundesk update` is the thing to do.
    4. Somebody else holds the name. **The claim is the check** — there is no version of this that
       asks first, because between asking and claiming another gateway can arrive.

    Only after all four does anything durable happen, and from then on an exception is a crash that
    launchd should restart. See the module docstring for why that asymmetry is the point.

    **What the supervisor captured is rotated in between, and every start reaches it — including
    every refusal.** A refusal is the case that fills those files in the first place: a gateway
    refusing for a permanent reason is a gateway launchd brings back and back, each time appending
    another sentence to a file nothing ever truncates. It is placed after the checks only because
    none of them can end this process, and before the claim so that a gateway which never gets to
    hold the name has still kept the growth bounded. Then the first line is said a second time, into
    the file the rotation has just emptied, so that what it guarantees survives the rotation.
    """
    _said_first(name)

    at, refusal = _may_not_run(name)
    if _kept_the_captures(at):
        _said_first(name)

    if refusal is None:
        # The claim, and nothing else, is inside this guard: a name that could not be taken is a
        # refusal and exits 0, while anything that fails once this gateway is *working* is a crash
        # and must exit non-zero so that launchd brings it back.
        held = contextlib.ExitStack()
        try:
            held.enter_context(standing.holding(at))
        except standing.Taken:
            # Guarded like the branch below it, and for the same reason. `_who_has_it` reads the
            # record to name the pid, and it is safe today only because a *different* module is
            # careful — `standing` catches every `OSError` it can produce. Nothing here guarantees
            # that, and the asymmetry with its neighbour was an oversight rather than a decision: a
            # refusal that raises while working out how to word itself still exits non-zero.
            try:
                refusal = _who_has_it(at, name)
            except BaseException:                      # noqa: BLE001 — same reason as below
                refusal = f"{name} is already being run by another gateway"
        except BaseException as why:                   # noqa: BLE001 — see the module docstring:
            # this is still the refusal phase, and the one thing it may never do is end in a
            # non-zero exit, which would turn a permanent condition into an endless restart.
            refusal = f"{name} could not claim its own name: {why}"
        else:
            with held:
                return _serving(name, at)

    _refused(at, name, refusal)
    return OK


def _said_first(name: str) -> None:
    """One line with the moment and this process's own id, before anything else happens at all.

    Written straight to the descriptor launchd handed us and flushed, rather than through the day
    files in `logs/`: those are opened by code that has not run yet, in a directory that may not be
    readable, for an agent that may not exist. **The point of this line is that it lands anyway.**
    An empty `gateway.out` next to a job launchd says has run means the failure is upstream of this
    file, and belongs in `log show` rather than here.

    Said again after a rotation has emptied that file, which is why this is a function rather than
    four lines at the top of `run`: the guarantee is about what is *in* `gateway.out`, not about how
    many times this process wrote it, and a rotation that moved the line aside and left nothing
    behind would have turned "look here" back into "cannot tell".

    Never raises. A gateway that fell over because it could not describe itself would be the same
    class of mistake as a command that failed because it could not write its own log.
    """
    with contextlib.suppress(Exception):
        sys.stdout.write(FIRST.format(when=logs.stamp(), name=name,
                                      pid=os.getpid(), version=__version__))
        sys.stdout.flush()


def _kept_the_captures(at: Optional[Path]) -> bool:
    """Move the supervisor's two capture files aside if they have grown. **Never raises.**

    Hands back whether the one this process's standard output points at was emptied, which is the
    only thing the caller has to do anything about: the first line has to be said again into it.
    Standard error is rotated in the same breath and answers for nothing, because nothing writes a
    line there deliberately — what lands in it is a traceback, and a traceback that was not written
    is not a fact anybody is missing.

    Guarded in the same way as `_said_first` and `_refused` and for the same reason: this runs on the
    path that must reach exit `0`, and failing to *tidy* a log may never become failing to *exit*.
    `logs.rotated` already promises not to raise; the promise is not repeated here on the strength of
    somebody else's docstring staying true.

    `at` is `None` when the agent's own directory could not even be worked out, and there is then no
    directory to hold a capture and nothing to rotate.
    """
    if at is None:
        return False
    moved = False
    with contextlib.suppress(Exception):
        out, err = standing.captured(at)
        moved = logs.rotated(out, CAPTURE_OVER, CAPTURES_KEPT) is not None
        logs.rotated(err, CAPTURE_OVER, CAPTURES_KEPT)
    return moved


def _may_not_run(name: str) -> Tuple[Optional[Path], Optional[str]]:
    """Where this agent stands and why this gateway may not host it — `(at, None)` when it may.

    **Nothing this raises escapes.** That is the structural half of the exit-0 contract: a check
    that raised would exit 1 through the interpreter, and launchd would read that as a crash worth
    restarting rather than as the permanent condition it is. Every unexpected failure here becomes
    a sentence and a `0`, which leaves a gateway down and says why — the honest failure, and the one
    somebody can act on.
    """
    at = None
    try:
        at = directory.where(name)
        if not directory.records(name).is_file():
            return at, (f"there is no agent called {name} on this install, so there is nothing to "
                        f"host — {at} holds no {directory.RECORDS}")
        waiting = migration.outstanding(migration.recorded(directory.records(name)))
        if waiting:
            return at, (f"{name} is not settled onto {__version__} — {len(waiting)} agent migration "
                        f"step(s) have not run, the first being {waiting[0].id}. "
                        "run: rundesk update")
        return at, None
    except BaseException as why:                       # noqa: BLE001 — see the docstring. A step
        # is arbitrary code, a database can be anything on disk, and a name can reach outside the
        # agents directory; what none of them may do is end this process non-zero.
        return at, f"{name} could not be started: {why}"


def _who_has_it(at: Path, name: str) -> str:
    """The refusal for a name another gateway holds, carrying that gateway's pid when there is one.

    The pid is read from the record and **only** after the lock has already said somebody is there,
    which is `standing`'s whole rule: a pid read off a gateway that is gone is a number that now
    belongs to something else.
    """
    how = standing.standing(at)
    return (f"a gateway is already running for {name}"
            + (f" as pid {how.pid}" if how.pid else "")
            + " — one agent has one gateway, and this one is standing down")


def _refused(at: Optional[Path], name: str, why: str) -> None:
    """Say why this gateway is not running, in both places somebody will look.

    Standard output because that is what launchd captured and what a person reaching for
    `gateway.out` will read, and the agent's own day file because that is where everything else this
    gateway ever said is. Written to the log only when there is an agent directory to write into —
    inventing one for an agent that does not exist would make a directory that then looks half-made.

    **Never raises, and that is the whole of this function's contract rather than a nicety.** This
    runs on the path that must reach exit `0`, and `stdout` here is `gateway.out` — a file launchd
    opens `O_APPEND` and never truncates. A full disk, a volume remounted read-only, or a mode
    changed underneath it makes this write fail, the exception leaves `run`, the interpreter exits
    `1`, and `KeepAlive {SuccessfulExit: false}` reads that as *bring it back*. The permanent
    condition recurs, the same write fails the same way, and a gateway that correctly refused to run
    becomes an endless restart escalating into launchd's exponential throttling — which looks like a
    hang and is the exact failure the module docstring claims is structurally impossible.

    `logs.note` already promises never to raise. The `print` beside it did not, while `_said_first`
    was guarded for precisely this reason one function up. Failing to *report* a refusal must never
    become failing to *exit* from one.
    """
    with contextlib.suppress(Exception):
        print(f"gateway: NOT RUNNING — {why}", flush=True)
    with contextlib.suppress(Exception):
        if at is not None and at.is_dir():
            logs.note(standing.logs_at(at), f"gateway did not start: {why}", logs.WARNING)


def _serving(name: str, at: Path) -> int:
    """Hold the name, say so, and go on saying so until something stops this process.

    Everything from here on is a working gateway, so **an exception is a crash and is let through**:
    it exits non-zero, launchd brings the gateway back, and that is the right answer for a fault
    that restarting might clear. Only `Stopped` is caught, because a stop that was asked for is not
    a fault and the difference between the two is exactly what somebody reads this log to find out.

    The record is written *inside* the claim and never outside it: it describes the holder of the
    lock, and one written by anything else is a claim with nothing behind it.

    **The loop is written for a process that is still in it in six months.** Two things happen every
    time round rather than once on the way up, because a gateway that is never restarted never
    reaches the way up again: the beat, which says this process is still working, and the sweep,
    which is what stops one file a day accumulating for as long as the process lives. Neither is
    allowed to end the gateway — see `_still_working` — and neither may say the same thing every
    fifteen seconds either, because a log that grows with the beat is the growth it was meant to
    bound, arrived at from the other side.
    """
    _stop_politely()
    where = standing.logs_at(at)
    try:
        # Inside the `try`, not before it. A stop asked for in the instant between coming up and
        # the first beat is still an orderly stop, and leaving it outside would have this process
        # exit non-zero — which under `SuccessfulExit: false` is a request to be restarted.
        standing.write_record(at, name, __version__)
        logs.note(where, f"gateway up for {name} on {__version__} as pid {os.getpid()}")
        # Both start as "nothing has happened yet", and the first sweep is the loop's first pass
        # rather than a call of its own before it. One call site: a sweep done on the way up as well
        # as in the loop is one that goes on looking right with the loop's half deleted, and the
        # loop's half is the one that matters — a gateway doing its job is one nobody restarts.
        landing, swept_for = True, ""
        while True:
            time.sleep(standing.BEAT_SECONDS)
            landing = _still_working(at, where, landing)
            swept_for = _kept_the_days(where, swept_for)
    except Stopped as why:
        # The orderly stop, and the only reason this line exists: a gateway that was killed outright
        # writes nothing at all, so the presence of this sentence is how the two are told apart.
        logs.note(where, f"gateway stopping for {name}: {why}")
        return OK


def _still_working(at: Path, where: Path, landing: bool) -> bool:
    """Say the gateway is still working. Hands back whether it landed, and **never ends the loop.**

    **A beat is an account of the work and not the work itself**, which is the rule `logs.note` is
    already written to: a gateway that could not say it is alive is still hosting its agent, and
    ending it over that would take a working gateway down. The failures are real and they are not
    ones a restart clears — a full disk, a volume gone read-only, an agent directory taken away from
    underneath a process that is still holding its lock — so letting this through would exit non-zero
    and be brought straight back into the same condition, which is the endless restart this whole
    module is arranged to make unreachable.

    **And it is never silent.** A beat that stopped landing with nothing said is exactly the "up and
    doing nothing" state a person most needs told about, so the first failure is written down. Only
    the first: a line every fifteen seconds for as long as the disk stays full is a log that grows
    without bound in the act of reporting something that will not change. The recovery is written
    down too, because a warning nothing ever retracts is one somebody goes on believing.

    `standing` answers for the same fact from outside, and answers it correctly on its own: with no
    beat landing, the reading in the record stops moving and the gateway reads as stale. Nothing here
    is covering that up — this is the half of it that says *why*.

    `Stopped` is let through untouched. It arrives from the signal handler and can land anywhere,
    including in the middle of the write below, and a request to stop is not a beat that failed.
    """
    try:
        standing.write_beat(at)
    except Stopped:
        raise
    except BaseException as why:                       # noqa: BLE001 — see the docstring. A record
        # can be missing, unparsable or unwritable, the disk can be full and the directory can have
        # been taken away; what none of them may do is end a gateway that is otherwise working.
        if landing and at.is_dir():
            # Written only while the agent's own directory is still standing, for the reason
            # `_refused` gives: `logs.note` makes the directory it writes into, so a gateway whose
            # agent has been taken away would put it back in the act of complaining that it is gone.
            logs.note(where, f"gateway could not say it is still working: {why}", logs.WARNING)
        return False
    if not landing:
        logs.note(where, "gateway is saying it is still working again")
    return True


def _kept_the_days(where: Path, swept_for: str) -> str:
    """Sweep this gateway's old day files, once a day. Hands back the day it has now been done for.

    **Once a day rather than once at startup**, because a gateway that is doing its job is one nobody
    restarts: a process up since March would have swept once, in March, and be sitting on a directory
    of two hundred files. Which day it last ran for is held in this process rather than written down
    — the only thing it decides is whether to do the arithmetic again, and a gateway that comes up,
    sweeps, and finds nothing to remove has lost nothing.

    Cheap enough to do this way round: one `strftime` per beat, and a listing of the directory on the
    one beat a day that crosses midnight.

    `swept_for` starts as `""`, which is no day, so the loop's first pass always sweeps — that is
    the sweep on the way up, and it is deliberately not a call of its own before the loop.

    Guarded, because a sweep is tidying and tidying may not end a gateway. Removing an old day file
    is the least important thing this process does and the disk it lives on is the most likely thing
    to refuse it.
    """
    today = logs.named_for(datetime.datetime.now())
    if today != swept_for:
        with contextlib.suppress(OSError):
            logs.swept(where, KEPT_DAYS)
    return today


def _stop_politely() -> None:
    """Turn a request to stop into an exception this process unwinds through.

    **A flag would not be enough.** `time.sleep` resumes after a handler that returns, so a gateway
    that only recorded the request would sit out the rest of its beat — up to fifteen seconds — and
    the whole shutdown has to fit inside the job's twenty-five second `ExitTimeOut` or launchd
    `SIGKILL`s it and calls it *languishing*. Raising ends the sleep at once.

    `SIGHUP` as well as `SIGTERM`, for the reason `cli._asked_to_stop_politely` gives: Python
    installs no handler for `SIGHUP`, so the kernel ends the process outright with no exception and
    no `finally` anywhere — which for this process would mean an orderly stop that is
    indistinguishable in the log from being killed.

    `SIGKILL` is not attempted and cannot be. What answers for that is `standing`: the kernel drops
    the lock as it takes the process apart, so a gateway that was killed outright reads as offline
    with nothing to tidy up.

    Installed here rather than at import, so importing this module changes nothing for whoever
    imported it — including the suite.
    """
    def leave(asked: int, _frame: object) -> None:
        raise Stopped(f"asked to stop with signal {asked}")

    for asked in (signal.SIGHUP, signal.SIGTERM):
        # Only the main thread of the main interpreter may install one, and a platform without a
        # `SIGHUP` is not a reason for a gateway to refuse to run.
        with contextlib.suppress(ValueError, OSError, AttributeError):
            signal.signal(asked, leave)
