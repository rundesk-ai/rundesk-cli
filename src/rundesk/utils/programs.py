"""Running another program, and the three answers `subprocess` collapses into one.

A program that was asked to run can end three ways, and they are not degrees of the same thing:

**It ran, and said what it thought.** There is an exit code, and the code is the answer.

**It never started.** The file is not there, or is not executable, or the interpreter behind it is
missing. There is no exit code, because nothing ran — and reporting this as a failing exit code says
the program ran and disagreed, which is a different fact about the machine and leads somewhere else.

**It started and would not finish.** Something is wrong that waiting will not fix, and the output so
far is the only evidence there is.

`subprocess` gives the first as an exit code, the second as an exception, and the third as a
different exception, and every caller that writes `except Exception: return 1` has just told
somebody their program ran and failed when it was never on the machine. So `Ran` carries all three,
and `trouble` is the field that says which.

## Two things it will not let a caller forget

**Standard input is never inherited.** A program that reads from a terminal nobody is watching waits
for ever, and it waits holding whatever its parent was holding. Closed, always — a caller that needs
to send something sends it deliberately.

**There is always a ceiling.** A wait with no end is the failure this project refuses everywhere it
appears: the command somebody typed simply never returns, and nothing in the output says why. The
ceiling is an argument because how long is too long belongs to the caller — proving an installed
command answers and waiting for a release to download are not the same patience.

Knows nothing about rundesk.
"""

import contextlib
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import IO, Any, Dict, NamedTuple, Optional, Sequence, Union

#: What a program that never started, or would not finish, has instead of an exit code.
DID_NOT_START = "did not start"
WOULD_NOT_FINISH = "would not finish"

#: How much may be handed to a program on its standard input by `run`. Well under the 64 KiB a pipe
#: holds on this platform, and that headroom is the whole reason for the number: `run` writes the
#: whole of it before it waits, so a program that has not read a byte yet still takes it and this
#: side never blocks. Anything larger needs a reader on the other end and is a different mechanism.
TOLD_AT_MOST = 16 * 1024

#: What a caller that tried to hand over more than that is told, in place of an exit code. Named
#: rather than written inline, because it is the one `trouble` that is this side's mistake and not
#: the program's — and reading it as "the adapter failed" would send somebody to the wrong file.
TOO_MUCH_TO_TELL = "was handed more on its input than can be given to a program that is not reading"

#: How much of what a program printed is kept. Everything past it is read and thrown away rather
#: than left in the pipe — see `_Draining` for why those are not the same choice.
#:
#: Generous on purpose. The largest answer anything here asks for is a channel adapter's `search`,
#: whose published ceilings allow roughly a hundred kilobytes; this is two orders above that, so a
#: program reaching it is one printing without stopping rather than one answering fully.
SAID_AT_MOST = 8 * 1024 * 1024

#: How much is read from a program's stream at a time. Large enough that a big answer is a handful
#: of reads, small enough that nothing here holds a pathological block in memory twice.
A_BLOCK = 64 * 1024

#: How long a reader is waited for once the program's whole group has been signalled. It is not a
#: budget for the program — that is `waiting` — but a guard on this function: a stream something
#: unreachable is still holding open must not turn `run` into a call that never returns.
READING_ENDS_WITHIN = 5.0


class Ran(NamedTuple):
    """What became of a program, in the three parts that can differ.

    `trouble` is the field to read first. While it is `None` the program ran and `code` is its
    answer; once it is set there is no exit code at all, and a caller treating `code` as `0`-or-not
    would be reading a number nothing produced.

    **There is deliberately no `worked` shortcut.** One existed and was removed: it answered `False`
    both for a program that ran and disagreed and for one that was never on the machine, which is
    the single distinction this whole type exists to keep. Both real callers had already routed
    around it and asked `trouble` then `code` themselves — when the people who must get it right
    avoid the convenience, the convenience is a trap for whoever does not know to.
    """

    code: Optional[int]
    out: str
    err: str
    trouble: Optional[str]

    def __repr__(self) -> str:
        return f"<ran {self.trouble or self.code}>"


def run(argv: Sequence[str], waiting: float, where: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None, telling: Optional[str] = None) -> Ran:
    """Run a program and hand back all three answers. Never raises for anything the program did.

    `waiting` is required rather than defaulted, so no caller arrives at a wait with no end by
    forgetting an argument. What comes back is text, because every caller of this so far reads it as
    lines a person wrote.

    An exception from the program itself is not passed on: the whole point is that "it was not
    there" is an answer to be reported, not a traceback to be caught again at every call site.

    **`telling` is what to put on its standard input, and said-nothing is not said-empty.** `None`
    hands it `/dev/null` — which is what every caller had before this argument existed, and what a
    program that must not be able to read anything gets. A string, including `""`, hands it a pipe
    carrying exactly that and then closed, so a program waiting for a request gets one and then an
    end-of-file rather than a wait with no end.

    **It is written before the wait, and that ordering is the whole of why it is safe.** This waits
    for the program and only then reads it, so a request written *after* the wait would be one the
    program never sees while this side waits out the ceiling for it. Written first and closed, a
    request under `TOLD_AT_MOST` fits in the pipe whether or not anything is reading yet, so neither
    side blocks on the other. Larger than that is refused here rather than attempted: it needs a
    reader on the far end, and this function is for a program that answers and stops.
    """
    if telling is not None and len(telling.encode("utf-8", "replace")) > TOLD_AT_MOST:
        return Ran(None, "", "", f"{TOO_MUCH_TO_TELL} ({TOLD_AT_MOST} bytes)")
    try:
        started = subprocess.Popen(
            [str(one) for one in argv],
            stdin=subprocess.DEVNULL if telling is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # Its own session here too, and not only in `start`. Without it a timeout can reach
            # only the program itself, and a program that started something of its own and then
            # exited leaves that child holding the capture pipe — so this waits out the whole
            # ceiling for a program that finished immediately, reports it would not finish, and
            # leaves the real one running with nobody holding its id.
            start_new_session=True,
            cwd=str(where) if where else None,
            env=env,
            preexec_fn=a_clean_slate,          # see `a_clean_slate`
        )
    except (OSError, ValueError, IndexError) as why:
        return Ran(None, "", "", f"{DID_NOT_START}: {why}")

    group = _group_of(started.pid)
    if telling is not None:
        _told(started, telling)
    with started:
        # **Drained while it is waited on, and waited on by the child rather than by the pipe.**
        # Those are two rules that pull against each other and both have to hold.
        #
        # *Waited on by the child*, because a program that starts something of its own and exits
        # leaves that child holding the capture pipe: reading until the pipe closes would wait out
        # the whole ceiling for a program that finished instantly, report it would not finish, and
        # leave the real one running with nobody holding its id.
        #
        # *Drained meanwhile*, because a pipe nobody is reading fills, and a program writing into a
        # full one blocks for ever. That is not a hypothetical here: an adapter answering a `search`
        # inside the ceilings `channels.adapters` publishes may print far more than a pipe holds, so
        # waiting first and reading afterwards deadlocked a program that was obeying the contract
        # and then blamed it — `would not finish` about a program that had finished everything but
        # the last write. The threads are what let both rules hold at once.
        out, err = _drained(started.stdout), _drained(started.stderr)
        trouble = None
        try:
            started.wait(timeout=waiting)
        except subprocess.TimeoutExpired:
            trouble = f"{WOULD_NOT_FINISH} within {waiting:g} seconds"

        # Either way, whatever is still in the group is not part of the answer. `run` is for a
        # program that answers and stops; anything it left behind holding the output is taken away
        # rather than waited on, and `start` is the way to launch something meant to outlive this.
        # It is also what ends the readers: the last writer gone is the end-of-file they are on.
        _signalled(group, FIRMLY)
        said, wrong = out.what_it_said(), err.what_it_said()
    return Ran(None if trouble else started.returncode, said, wrong, trouble)


class _Draining:
    """One captured stream, read on a thread of its own so nothing on the far side ever blocks.

    **Bounded, and it goes on reading past the bound.** Keeping everything would let a program that
    prints without stopping exhaust this process's memory; *stopping* reading at the bound would put
    back the full pipe this exists to prevent. So it keeps the first `SAID_AT_MOST` and throws the
    rest away, which is the only combination where neither side can be hurt by the other.

    Never raises into the caller. A stream that goes away under it is a program that ended, which is
    the ordinary case and not a failure — what became of the program is `Ran`'s to report.
    """

    def __init__(self, stream: Optional[IO[str]]) -> None:
        self._held: list = []
        self._kept = 0
        self._reader = threading.Thread(target=self._reading, args=(stream,), daemon=True)
        self._reader.start()

    def _reading(self, stream: Optional[IO[str]]) -> None:
        if stream is None:
            return
        try:
            for block in iter(lambda: stream.read(A_BLOCK), ""):
                if self._kept < SAID_AT_MOST:
                    self._held.append(block[:SAID_AT_MOST - self._kept])
                    self._kept += len(self._held[-1])
        except (OSError, ValueError):
            pass                    # the program ended and took its stream with it

    def what_it_said(self) -> str:
        """Everything it wrote, once the last writer has gone. Bounded by the wait, never open-ended.

        **Joined with a ceiling of its own**, because the one thing that must not happen here is a
        `run` that never returns: the group has been signalled by the time this is called, so a
        reader still going is one whose far end something is holding open in a way this cannot
        reach, and waiting on that for ever would be worse than answering with what did arrive.
        """
        self._reader.join(READING_ENDS_WITHIN)
        return "".join(self._held)


def _drained(stream: Optional[IO[str]]) -> _Draining:
    """Start reading one of a program's streams straight away. See `_Draining`."""
    return _Draining(stream)


def _told(started: "subprocess.Popen", telling: str) -> None:
    """Hand a program its request and close its input, so it reads an end rather than waiting.

    **Nothing here is a failure of this side.** A program that has already exited — because it did
    not recognise the argument, or refused before reading — closes the pipe, and writing into a
    closed pipe raises `BrokenPipeError`. That program's own exit code and whatever it printed are
    the answer, and raising here would replace a readable refusal with a traceback from the one
    function that promises never to produce one.

    Closed either way, including on that failure: a program left holding an input nothing will ever
    close is a program waiting for a request that has already been sent.

    **And then forgotten, which is the part that is not obvious.** `communicate()` flushes and closes
    whatever `stdin` it still finds, and a handle this has already closed raises `ValueError` out of
    the wait — turning every search into a traceback from inside the one function that promises not
    to produce one. Setting it aside is how `subprocess` itself records that an input is spent.
    """
    if started.stdin is None:
        return
    try:
        started.stdin.write(telling)
    except (OSError, ValueError):
        pass
    with contextlib.suppress(OSError, ValueError):
        started.stdin.close()
    started.stdin = None


def _said(maybe: Optional[Union[str, bytes]]) -> str:
    """What a timed-out program had written, whichever way this Python hands it over.

    `TimeoutExpired` carries `bytes` on some versions and `str` on others depending on how the run
    was asked for, and `None` when it wrote nothing at all. A caller should not have to know which.
    """
    if maybe is None:
        return ""
    return maybe.decode("utf-8", "replace") if isinstance(maybe, bytes) else str(maybe)


# ---------------------------------------------------------------------------------------------
# A program that keeps running, which is a different problem from one that answers and stops.
# ---------------------------------------------------------------------------------------------
#
# `run` above waits for an answer. Everything below is for a program that is not going to give one
# for hours: it is started, it is watched, and eventually it is stopped. Four things make that
# different, and all four are things the build this replaces got wrong at least once.
#
# **It is started in a session of its own.** `start_new_session=True` gives it a new session and a
# new process group, and it becomes the leader. That one flag is what makes the rest possible: a
# program like this starts programs of its own, and signalling the *group* reaches all of them.
# Without it, stopping a gateway leaves whatever it spawned running — with nothing left holding the
# ids, so nobody can ever stop them.
#
# **Its output goes to a file, never to a pipe.** A pipe nobody is draining fills, and a program
# writing into a full pipe blocks for ever — a deadlock that looks exactly like a hang, and appears
# only once the thing has been running long enough to say 64KB.
#
# **A pid is not an identity.** The number is reused. A recorded pid that is alive today may be
# somebody else's process, and signalling it would kill a stranger's program. Nothing here can solve
# that alone, so nothing here pretends to: `alive` answers about a number, and whoever recorded the
# number owns proving it is still the same program.
#
# **Stopping is asked before it is insisted on.** A program gets a chance to finish what it was
# doing, and only then is it taken away.
#
# **None of this stops a program the machine's own supervisor is keeping up.** Measured against a
# real launchd job with `KeepAlive`: a SIGTERM is read as a crash and the job comes straight back
# under a new pid and a new group, neither of which anybody wrote down. `stop` then watches the old
# group go, correctly reports it gone, and the program is still running — untracked. That is not a
# defect here and cannot be fixed here: this module knows nothing about rundesk and still less about
# launchd. The layer that hands a job to the machine is the layer that has to take it back, with
# `launchctl bootout`, and whatever calls `stop` on a supervised process is asking the wrong
# question of the wrong thing.

#: How the group is asked, and then told. In this order, never the other way round.
GENTLY = signal.SIGTERM
FIRMLY = signal.SIGKILL

#: How often a wait for something to stop looks again.
LOOKING_AGAIN = 0.05

#: The children this process started with `start`, kept by process id.
#:
#: **Because starting one and reaping it are two calls, and the thing that knows a child's status is
#: the wrapper that created it.** `start` hands back a bare pid so a caller can write it down and
#: outlive it; the wrapper stays here so `collected` can take the status through `poll()`, which is
#: what actually settles the child rather than leaving a zombie.
#:
#: It is also what keeps the standard library quiet. A `Popen` collected while it still believes it
#: owns a running child emits `ResourceWarning: subprocess N is still running` — correct about the
#: facts and wrong about the intent, since detaching is the whole point of `start`. Holding the
#: wrapper until the child is reaped answers that honestly rather than silencing it.
#:
#: Entries go when the child is reaped or stopped, so this holds one per *live* child and not one
#: per child ever started.
_STARTED: Dict[int, subprocess.Popen] = {}


class CouldNotStart(Exception):
    """A long-lived program that never began, named with why.

    One exception rather than the five different things the standard library raises for this — a
    log path that is a directory, a directory that cannot be written, a program that is not there,
    one that is not executable, an empty argv. A caller supervising gateways has the same thing to
    do about all of them, and this module's whole point is that "it was not there" is an answer to
    report rather than a traceback to catch again at every call site. `run` says it in the `Ran` it
    returns; there is no equivalent here, because a start has two outcomes and not three.
    """


def start(argv: Sequence[str], log: Path, where: Optional[Path] = None,
          env: Optional[Dict[str, str]] = None,
          holding: Sequence[int] = ()) -> int:
    """Start a long-lived program in a session of its own and hand back its process id.

    Everything it writes is appended to `log`, which is opened here rather than left to the caller
    so that no version of this ends up handing the program a pipe.

    The file is opened for appending on purpose: a restart adds to the history rather than replacing
    it, and history is most of what a log is for.

    **`holding` are descriptors the child keeps open, and the point of them is a lock it never asks
    about.** A `flock` belongs to the open file description rather than to a process, so one taken
    by *this* process and passed down is held for exactly as long as the child and everything it
    starts are alive, and the kernel drops it however they end — including a `SIGKILL` that lets no
    tidying code run anywhere. A caller wanting a claim that outlives its own process, and that
    another process can ask about, has no other way to get one: a pid it wrote down can be reused,
    and a file it created is not a lock.

    The caller closes its own copy afterwards, and must: the lock is let go only when the last
    descriptor onto that description is closed, so a parent that keeps its own is a parent still
    holding the claim it meant to hand over.
    """
    try:
        return _started(argv, log, where, env, holding)
    except (OSError, ValueError, IndexError) as why:
        raise CouldNotStart(f"{DID_NOT_START}: {why}") from why


def _started(argv: Sequence[str], log: Path, where: Optional[Path],
             env: Optional[Dict[str, str]], holding: Sequence[int] = ()) -> int:
    """The start itself. See `start`, which turns everything this raises into one answer."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as writing:
        # A list, never a string through a shell: nothing here is ever word-split or expanded.
        started = subprocess.Popen(
            [str(one) for one in argv],
            stdin=subprocess.DEVNULL,
            stdout=writing,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(where) if where else None,
            env=env,
            # `pass_fds` is what clears close-on-exec for these and nothing else — every other
            # descriptor this process holds is still closed, so a child cannot inherit a database
            # connection or somebody else's lock by accident.
            pass_fds=tuple(holding),
            # See `a_clean_slate`: a blocked signal mask is inherited across the exec, and a child
            # that inherited one could not be stopped by the parent that started it.
            preexec_fn=a_clean_slate,
        )
    _STARTED[started.pid] = started
    return started.pid


class Talking(NamedTuple):
    """A long-lived program this process exchanges lines with, and the two ends of that.

    The fields are named for the child's own descriptors rather than for what this side does with
    them, because every other name is ambiguous about which way round it is: `stdout` is what the
    program says and `stdin` is what it hears, exactly as the program itself sees them.

    **Both are this process's to close**, and leaving them open is not tidy-untidy — it is a
    descriptor per channel per restart, in a process that runs for months.
    """

    pid: int
    stdout: IO[str]
    stdin: IO[str]


def talking(argv: Sequence[str], errors: Path, where: Optional[Path] = None,
            env: Optional[Dict[str, str]] = None,
            holding: Sequence[int] = ()) -> Talking:
    """Start a long-lived program and keep both ends of a conversation with it.

    The third shape in this module, and the one the other two were written to avoid. `run` waits for
    an answer; `start` detaches and writes to a file; this keeps a program that will be here in six
    months **and talks to it**, which needs the one thing the block comment above `start` refuses to
    give anybody by accident.

    **Standard output is a pipe, and that is the whole risk.** The comment above `start` says why it
    would not hand one out: *a pipe nobody is draining fills, and a program writing into a full pipe
    blocks for ever — a deadlock that looks exactly like a hang, and appears only once the thing has
    been running long enough to say 64KB.* That has not stopped being true; it has become the
    caller's to answer. **Whatever calls this must drain `stdout` continuously**, on something that
    cannot fall behind — not on a loop that also sleeps, because the sleep is how the pipe fills.

    **Standard error is a file, and deliberately not merged into standard output.** They carry
    different things here: `stdout` is a protocol nothing may interrupt, and one traceback written
    across it would be a line no reader can parse in the middle of a stream it is parsing. The file
    is opened here rather than left to the caller for the same reason `start` opens its log — so no
    version of this ends up handing the program a second pipe nobody drains.

    **Standard input is a pipe and is writable**, which is the other thing `start` will not do. Its
    docstring promises that a caller needing to send something *sends it deliberately*, and until
    now there was no deliberate path; this is it.

    Line buffered, so a line written here leaves this process when it is written rather than when
    some block fills — the answer to a message must not be waiting behind the answer to the next.

    **A byte that is not text is a bad character and never the end of the conversation.** Decoding
    is `errors="replace"`, because the alternative is `UnicodeDecodeError` raised *inside* the read
    — not from anything the caller wrote, and so not catchable per record — which ends whatever was
    draining this pipe while the program on the far side goes on running and holding whatever it
    holds. One invalid byte is a thing a long-lived program will eventually emit; permanently
    deafening its reader is not a proportionate answer to it.

    `holding` are descriptors the child keeps open, for the reason `start` gives: a `flock` belongs
    to the open file description, so one taken here and passed down is held for exactly as long as
    the child and everything it starts, and the kernel drops it however they end. The caller closes
    its own copy afterwards, and must.
    """
    try:
        return _talking(argv, errors, where, env, holding)
    except (OSError, ValueError, IndexError) as why:
        raise CouldNotStart(f"{DID_NOT_START}: {why}") from why


def _talking(argv: Sequence[str], errors: Path, where: Optional[Path],
             env: Optional[Dict[str, str]], holding: Sequence[int]) -> Talking:
    """The start itself. See `talking`, which turns everything this raises into one answer."""
    errors.parent.mkdir(parents=True, exist_ok=True)
    with open(errors, "a", encoding="utf-8") as complaining:
        started = subprocess.Popen(
            [str(one) for one in argv],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=complaining,
            text=True,
            # See `talking`: a `UnicodeDecodeError` here is raised inside the read itself, where the
            # caller's own guard around one record cannot reach it — so a single invalid byte ends
            # the drain for good while the program goes on running.
            errors="replace",
            # Line buffered, which `text=True` is what makes meaningful. Without it a line written
            # to a program sits in this process until a block's worth has piled up behind it.
            bufsize=1,
            # Its own session, exactly as `start` does it: this program starts programs of its own,
            # and signalling the group is what reaches them.
            start_new_session=True,
            cwd=str(where) if where else None,
            env=env,
            pass_fds=tuple(holding),
            preexec_fn=a_clean_slate,          # see `a_clean_slate`
        )
    # Held for the same reason `start` holds one: `collected` takes the status through `poll()`,
    # which is what actually settles the child rather than leaving a zombie.
    _STARTED[started.pid] = started
    return Talking(started.pid, started.stdout, started.stdin)


class Collected(NamedTuple):
    """What became of a child this process started, asked without waiting for it.

    `over` is the field to read first, and the pair says which of **three** things is true rather
    than the two a single number could:

    | `over` | `code` | |
    |---|---|---|
    | `False` | `None` | still running |
    | `True` | a number | finished, and this is what it said |
    | `True` | `None` | over, and nobody can say what it came to |

    The third is not a kind of failure and must never be reported as one. It is what a child of a
    *previous* process looks like — the one that started it is gone, so the exit status went with
    it — and work that may well have finished perfectly is not something to write down as failed.
    """

    over: bool
    code: Optional[int]


def collected(pid: int) -> Collected:
    """Ask whether a child this process started has finished, and take its status if it has.

    **Taking the status is not optional and cannot be deferred.** A child that has exited stays in
    the process table as a zombie until somebody collects it, and a zombie answers signal `0`
    exactly like a running program — so anything asking `alive` in a loop would spin for ever on a
    program that finished in a millisecond, and every short-lived child would hold a table slot
    until the machine ran out.

    **Only for a child of this very process.** `waitpid` answers about nobody else's, which is the
    honest boundary rather than a limitation: a status is something the parent holds, and a gateway
    that came up after the one which spawned this has no way to learn it. That case is `over` with
    no code, and the caller is expected to say so rather than to guess.

    Deliberately not folded into `alive`, which answers only whether something is there — the two
    answer different questions, and a caller that needed the code would find `alive` had already
    eaten it.
    """
    started = _STARTED.get(pid)
    if started is not None:
        code = started.poll()
        if code is None:
            return Collected(False, None)
        _STARTED.pop(pid, None)
        return Collected(True, code)
    try:
        gone, status = os.waitpid(pid, os.WNOHANG)
    except OSError:
        # Never ours, or already collected. Either way it is over and there is nothing to read.
        return Collected(True, None)
    if gone == 0:
        return Collected(False, None)
    return Collected(True, os.waitstatus_to_exitcode(status))


def ready_to_collect(pid: int) -> bool:
    """Whether this process's child has finished, without taking away its saved exit status.

    A lock or a missing pid answers a different question: the first can be released a scheduling
    instant before the parent observes the exit, and the second includes a zombie. ``poll`` records
    the status on the wrapper, so a later :func:`collected` still returns the exact exit code and
    remains the one operation that removes the child from this module's care.

    ``False`` for a process this module did not start. Its status belongs to its own parent and
    cannot be observed here without consuming or guessing it.
    """
    started = _STARTED.get(pid)
    return started is not None and started.poll() is not None


def a_pid(said: Any) -> Optional[int]:
    """A recorded process id, or `None` when it is not one anybody may act on.

    **`0` is every process in the caller's own group and `1` is the machine's init**, so a record
    holding either — corrupted, or written by hand — is a record that would have somebody signal the
    wrong thing entirely. `True` is an `int` to Python and is not a pid to anybody else.

    Here rather than beside either of the records that need it. `gateways.standing` reads a pid out
    of a gateway's record and `schedules.firing` reads one out of a firing's, and the question
    *"is this a number I may signal"* is neither module's domain — it is what this one already owns,
    beside `alive` and `stop`, which are the two things a caller does with the answer.
    """
    if isinstance(said, bool) or not isinstance(said, int) or said <= 1:
        return None
    return said


def a_clean_slate() -> None:
    """Give a child the signal mask a program expects, between the fork and the exec.

    **A blocked signal mask is inherited across `fork` *and* across `exec`, and dispositions are
    not.** So a parent that blocks `SIGTERM` for a moment — to make starting a child and writing
    down that it started one indivisible step, which is exactly what `schedules.firing` does — hands
    every child it starts in that moment a program that can never be terminated. Measured: a
    `/bin/sh` started that way survived `SIGTERM` and had to be `SIGKILL`ed, so a gateway stopping
    its work waited out its whole patience first and reported the child as one that would not stop.

    `subprocess`'s own `restore_signals` does not cover this. It restores *dispositions* Python set
    to `SIG_IGN`, which is a different thing from the mask, and the difference is invisible until
    something signals the child.

    Reset to empty rather than to whatever the parent had before it blocked, because that is what a
    program started from a shell gets and what every program is written expecting.
    """
    with contextlib.suppress(OSError, ValueError):
        signal.pthread_sigmask(signal.SIG_SETMASK, set())


def _settled(pid: int) -> None:
    """Take a child's status if it has finished, and let go of its wrapper once it has.

    One place, because two callers need it for two different reasons and both are easy to get wrong.
    `alive` needs it so a child that exited on its own is not counted as running for ever. `stop`
    needs it so the wrapper for a program it just ended does not sit here for the life of the
    process still believing it owns something that is running.

    Through the wrapper where this module has one, because that is what actually settles the child:
    a raw `waitpid` takes the status and leaves the wrapper believing otherwise, which is a
    `ResourceWarning` at interpreter exit about a child that was reaped correctly.
    """
    started = _STARTED.get(pid)
    if started is not None:
        with contextlib.suppress(OSError, ValueError):
            if started.poll() is not None:
                _STARTED.pop(pid, None)
        return
    with contextlib.suppress(ChildProcessError, OSError):
        os.waitpid(pid, os.WNOHANG)


def alive(pid: int) -> bool:
    """Whether a process with that id is running now.

    Signal `0` asks the kernel without sending anything. A process that is running but belongs to
    somebody else answers `EPERM`, which is still an answer: something is there.

    **This says a process exists, not that it is the one you meant.** Ids are reused.
    """
    if pid <= 1:
        return False
    # **Collected first, or a child that exited on its own answers "alive" for ever.** A process
    # this one started stays in the table as a zombie until somebody takes its status, and a zombie
    # answers signal `0` exactly like a running program — so the natural supervisor shape,
    # `while alive(pid): ...`, would spin on a program that finished in a millisecond, and every
    # short-lived child would hold a table slot until the machine ran out. `ECHILD` means it was
    # never ours to collect, which is ordinary: it may be from an earlier run of the command.
    _settled(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop(pid: int, gently_for: float, firmly_for: float = 5.0) -> str:
    """Stop a program and everything it started. `""` when it is gone, otherwise why it is not.

    Asked with `SIGTERM` first and given `gently_for` to finish; told with `SIGKILL` after. Sent to
    the process *group*, so what the program started stops with it rather than being orphaned.

    A program that is already gone is not a failure — it is the state that was asked for.
    """
    if pid <= 1:
        return f"{pid} is not a process this may signal"
    try:
        os.getpgid(pid)
    except PermissionError as why:
        return f"{pid} belongs to somebody else ({why})"
    except ProcessLookupError:
        # **Not gone — merely no longer askable.** Once the leader has been collected, `getpgid`
        # cannot resolve it, but the *group* it led outlives it and keeps whatever it started. This
        # said "stopped" in milliseconds while a survivor ran on, which is the same abandonment the
        # group-wide wait was written to prevent, reached by the other road: the leader that exits
        # the instant it has spawned its worker is not an edge case, it is the ordinary shape of a
        # program that backgrounds something. `_group_of` falls back to the pid, which is the group
        # id — `start_new_session` makes the leader its own group, so the two are the same number.
        pass
    group = _group_of(pid)

    # `killpg` on our own group signals this very process and everything beside it. It is reachable
    # by an honest mistake — a recorded id that was reused by something started from this shell —
    # and the result is the command killing itself mid-sentence.
    if group == os.getpgrp():
        return f"{pid} is in this command's own process group, and stopping it would stop this"

    for how, patience in ((GENTLY, gently_for), (FIRMLY, firmly_for)):
        trouble = _signalled(group, how)
        if trouble:
            return trouble
        if _gone_within(group, pid, patience):
            # Settled on the way out, so this module stops holding a wrapper for a program it has
            # just ended — see `_settled`.
            _settled(pid)
            return ""
    return f"{pid} and what it started were still running after being asked and then told to stop"


def _signalled(group: int, how: int) -> str:
    """Send one signal to a whole process group. `""` when it landed or there was nobody left."""
    try:
        os.killpg(group, how)
    except ProcessLookupError:
        return ""
    except PermissionError as why:
        return f"process group {group} could not be signalled ({why})"
    return ""


def _group_of(pid: int) -> int:
    """The process group a pid leads or belongs to, or the pid itself when it has already gone."""
    try:
        return os.getpgid(pid)
    except OSError:
        return pid


def _gone_within(group: int, pid: int, patience: float) -> bool:
    """Wait for the whole group to disappear, collecting the one process that was ours.

    **The group, not the pid.** Waiting on the recorded process alone is the difference between a
    tree that stopped and a tree whose leader stopped: a program that dies to the first signal
    while something it started ignores it would have this return `True` in milliseconds, report a
    clean stop, and leave the sibling running — un-escalated, and unreachable for ever after,
    because the only id anybody wrote down is the one that is now gone.

    `killpg` with signal `0` sends nothing and asks whether anyone is still in the group.
    """
    ceiling = time.monotonic() + patience
    while True:
        alive(pid)                       # collects it if it was ours, so a zombie is not counted
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            # Somebody is there and is not ours to ask about. Not gone.
            pass
        if time.monotonic() >= ceiling:
            return False
        time.sleep(LOOKING_AGAIN)
