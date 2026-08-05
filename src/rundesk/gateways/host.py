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

## Stopping politely, and why that is visible in the log

`SIGTERM` and `SIGHUP` are turned into an exception, so an orderly stop unwinds through the same
`finally` blocks everything else does and writes a line saying it stopped. A gateway that was killed
outright writes nothing, and the two are told apart by reading the log rather than by guessing. It
also has to happen inside the job's `ExitTimeOut`: a gateway that ignores `SIGTERM` makes
`bootout --wait` block for that whole window and then be `SIGKILL`ed, which is the state launchd
calls *languishing*. `cli._asked_to_stop_politely` is the same shape for the same reason.

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
    """
    _said_first(name)

    at, refusal = _may_not_run(name)
    if refusal is None:
        # The claim, and nothing else, is inside this guard: a name that could not be taken is a
        # refusal and exits 0, while anything that fails once this gateway is *working* is a crash
        # and must exit non-zero so that launchd brings it back.
        held = contextlib.ExitStack()
        try:
            held.enter_context(standing.holding(at))
        except standing.Taken:
            refusal = _who_has_it(at, name)
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

    Never raises. A gateway that fell over because it could not describe itself would be the same
    class of mistake as a command that failed because it could not write its own log.
    """
    with contextlib.suppress(Exception):
        sys.stdout.write(FIRST.format(when=logs.stamp(), name=name,
                                      pid=os.getpid(), version=__version__))
        sys.stdout.flush()


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
    """
    print(f"gateway: NOT RUNNING — {why}", flush=True)
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
    """
    _stop_politely()
    where = standing.logs_at(at)
    try:
        # Inside the `try`, not before it. A stop asked for in the instant between coming up and
        # the first beat is still an orderly stop, and leaving it outside would have this process
        # exit non-zero — which under `SuccessfulExit: false` is a request to be restarted.
        standing.write_record(at, name, __version__)
        logs.note(where, f"gateway up for {name} on {__version__} as pid {os.getpid()}")
        while True:
            time.sleep(standing.BEAT_SECONDS)
            standing.write_beat(at)
    except Stopped as why:
        # The orderly stop, and the only reason this line exists: a gateway that was killed outright
        # writes nothing at all, so the presence of this sentence is how the two are told apart.
        logs.note(where, f"gateway stopping for {name}: {why}")
        return OK


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
