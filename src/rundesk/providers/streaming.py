"""An adapter that is running: the records coming off it, and the words going back to it.

`utils.programs.talking` starts the process and hands over two pipes. Everything between that and a
turn is here: reading without falling behind, bounding what is held, deciding when a program that has
gone quiet is wedged, saying something to one that is still working, and ending it.

Four things shape all of it, and every one comes from what these programs are.

**A thread does the reading, and it does nothing else.** `programs.talking` states the rule it hands
its caller: *whatever calls this must drain stdout continuously, on something that cannot fall
behind — not on a loop that also sleeps, because the sleep is how the pipe fills.* A turn cannot
promise that: it writes to a database, it hands records to whoever is watching, and a channel post
can take a fifth of a second. So the thread reads into a bounded queue and the turn drains the queue,
and a slow turn costs nothing but its own time.

**Silence is the failure, never duration.** A turn may legitimately run for hours, so a clock that
ends it is a clock that ends real work. What a wedged program does is go quiet, so that is what is
measured — and measured across **both** streams, because a brain working steadily and reporting only
diagnostics is plainly busy while looking silent on the one stream anybody watches. The error stream
is a file rather than a pipe, so what is watched there is whether the file grew.

**A ceiling sits behind the silence and is not the instrument.** Silence cannot see a program wedged
in a loop that keeps announcing itself, and that shape would otherwise run until somebody noticed.

**Losing a record is reported where it happened.** `utils.lines` already says so for a line that
would not fit or a stream that stopped mid-line; this adds the one loss it cannot see — a queue that
overflowed because the turn could not keep up. All three arrive in the same stream, in order, as the
same kind of thing, so nothing downstream has to know which layer lost something to report it.

Nothing here parses a record: `protocol.understood` does that, and this hands on whatever the line
was. Nothing here knows any particular brain.
"""

import contextlib
import queue
import threading
import time
from pathlib import Path
from typing import Iterator, List, Optional, Union

from rundesk.utils import lines, programs

#: How much of one line is read before it is refused. Not a limit on what an adapter may say, only on
#: what is held at once — see `utils.lines`, which explains why the bound has to be inside the read.
LINE_AT_MOST = 1024 * 1024

#: How long an adapter may say nothing at all before this takes it for wedged. Generous on purpose: a
#: working turn can be quiet for a long time while a single tool call runs, and ending one of those
#: is ending real work.
SILENCE_SECONDS = 1800.0

#: The longest a turn may run however much it is saying. The backstop, not the instrument — set far
#: past what real work reaches, because what this catches is a loop that keeps announcing itself.
CEILING_SECONDS = 48 * 60 * 60.0

#: How long the queue is drained for once the program has gone. A drain, not a wait for more work:
#: nothing further is coming, and something else may be holding the pipe open.
DRAIN_SECONDS = 2.0

#: How many records are held between the thread that reads them and the turn that consumes them.
#: Generous, because reaching it should mean a turn is broken rather than busy — what happens at the
#: bound is that records are lost, and a loss is worse than a slow turn.
HELD_AT_MOST = 4096

#: How often the reader is looked in on while it is saying nothing. Silence is measured in these, so
#: it is also how close to the mark that measurement lands.
LOOKING_AGAIN = 0.5

#: How long an adapter that has closed its output is given to leave on its own before it is
#: signalled. Short: this is a program that has already said everything and is tidying up, not a wait
#: for more work — and what it buys is the exit code, which signalling would consume.
SETTLING_SECONDS = 2.0

#: What a `Gap` from this layer says, as against the two `utils.lines` produces.
FELL_BEHIND = "fell behind"


class Stream:
    """One running adapter, read from and spoken to.

    Built around a `programs.Talking` rather than starting one itself, so that every case here can be
    driven against an ordinary program and nothing in this module has to know what an adapter is or
    where one is found.

    Not reusable and not restartable: one of these is one adapter for one turn. `stop` is safe to
    call more than once and is called on the way out of `records` however that ends, so a caller
    that abandons the iterator does not leave a process behind.
    """

    def __init__(self, talking: programs.Talking, errors: Optional[Path] = None,
                 silence: float = SILENCE_SECONDS, ceiling: float = CEILING_SECONDS,
                 held_at_most: int = HELD_AT_MOST, line_at_most: int = LINE_AT_MOST):
        self.talking = talking
        self._errors = errors
        self._silence = silence
        self._ceiling = ceiling
        self._line_at_most = line_at_most
        self._held: queue.Queue = queue.Queue(maxsize=held_at_most)
        self._lost = 0
        self._reading: Optional[threading.Thread] = None
        self._saying = threading.Lock()
        self._writable = True
        self._stopped = False
        self._ending = False
        self._became: Optional[programs.Collected] = None
        #: Why this stream ended, when it was not the program's own doing. Read after `records` has
        #: run out — a caller that acted on the reason before then would be acting on nothing.
        self.trouble: Optional[str] = None

    def _went_wrong(self, why: str) -> None:
        """Record why this ended, **once**. The first reason is the one that explains the rest."""
        if self.trouble is None:
            self.trouble = why

    # -- reading -----------------------------------------------------------------------

    def records(self) -> Iterator[Union[str, lines.Gap]]:
        """Every line the adapter sent, and a `Gap` wherever one was lost. **Never raises.**

        Yields until the adapter's output ends, or until it has been quiet too long, or until the
        ceiling. The last two set `trouble` and end the program; the first is the ordinary way a turn
        finishes and sets nothing.

        The reading itself is on another thread, so a caller that spends a fifth of a second on a
        record — which a channel post easily does — slows nothing but itself, right up to the point
        where the queue is full and records start being lost. That point is reported rather than
        silent.
        """
        self._reading = threading.Thread(target=self._read, name="provider-records", daemon=True)
        self._reading.start()
        began = time.monotonic()
        heard = time.monotonic()
        grew = self._errors_grew()
        try:
            while True:
                if time.monotonic() - began >= self._ceiling:
                    self._went_wrong(f"it was still running after {self._ceiling:g} seconds")
                    return
                try:
                    said = self._held.get(timeout=LOOKING_AGAIN)
                except queue.Empty:
                    # Nothing on the record stream. Before calling that silence, ask whether it said
                    # anything on the other one — a brain reporting only diagnostics is working.
                    if self._errors_grew() != grew:
                        grew = self._errors_grew()
                        heard = time.monotonic()
                    elif time.monotonic() - heard >= self._silence:
                        self._went_wrong(f"it said nothing for {self._silence:g} seconds")
                        return
                    continue
                if said is None:                       # the reader reached the end of the output
                    return
                heard = time.monotonic()
                yield said
                if self._lost:
                    # **After the record and never before it.** The queue is first-in-first-out and
                    # drops happen at its tail, so everything still in it was put there before
                    # anything was lost — a gap yielded first would say the loss happened earlier
                    # than it did, and where a loss happened is the whole of what a gap says.
                    lost, self._lost = self._lost, 0
                    yield lines.Gap(lost, FELL_BEHIND)
        finally:
            # **Nothing to settle for when we are the ones ending it.** A stream that ran out
            # normally may be a program a moment from leaving on its own, and waiting buys its exit
            # code. One we cut off for going quiet or overrunning is by definition not about to
            # leave, so the same wait buys nothing and spends the shutdown budget on it.
            self.stop(settling_for=0.0 if self.trouble else SETTLING_SECONDS)

    def _read(self) -> None:
        """Pull lines off the adapter as fast as it produces them. **Never raises, ever.**

        A thread that raises takes its traceback nowhere anybody will look, so whatever went wrong is
        turned into the end of the stream and the reason is left where the turn will read it.

        A queue that is full is **not** waited on. Waiting here is the deadlock this whole shape
        exists to prevent: the program blocks writing to a pipe nobody is draining, so it never reads
        what is written to it, and a steered turn waits for ever on a brain that is waiting for us.
        The record is lost instead, and the loss is counted and reported.
        """
        try:
            for said in lines.read(self.talking.stdout, self._line_at_most):
                try:
                    self._held.put_nowait(said)
                except queue.Full:
                    self._lost += 1
        except Exception as why:                       # noqa: BLE001 — see the docstring
            if not self._ending:
                # A read that failed *because this turn closed the pipe* is not a reason for
                # anything: the turn already has the real one, and reporting ours over it turned a
                # ceiling into "I/O operation on closed file" — the reason nobody could act on
                # replacing the one they could.
                self._went_wrong(f"this turn stopped reading it ({why})")
        finally:
            # Always, however this ended, or a turn waits out its whole silence window on a stream
            # that is already finished.
            with contextlib.suppress(Exception):
                self._held.put(None, timeout=DRAIN_SECONDS)

    def _errors_grew(self) -> int:
        """How much the adapter has written to its error stream. `0` when there is nothing to ask.

        A size rather than a read: nothing here wants what the adapter said went wrong — the file
        keeps that, and a turn copies a tail of it when something goes wrong — only whether it is
        still saying anything, which is the half of the silence question the record stream cannot
        answer.
        """
        if self._errors is None:
            return 0
        try:
            return self._errors.stat().st_size
        except OSError:
            return 0

    # -- saying ------------------------------------------------------------------------

    def say(self, said: str) -> bool:
        """Send one line to a running adapter. `False` when there was nothing there to send it to.

        Held under a lock across the write **and** the flush, because two words offered close
        together — a person typing while a channel steers, which is this product's ordinary case —
        would otherwise interleave into one corrupt line.

        A closed or broken pipe is an answer rather than an exception: an adapter that has already
        finished while somebody was still typing is nobody's fault, and there is nothing lost that
        the caller has to act on beyond knowing it did not land.
        """
        with self._saying:
            if not self._writable:
                return False
            try:
                self.talking.stdin.write(said if said.endswith("\n") else said + "\n")
                self.talking.stdin.flush()
                return True
            except (BrokenPipeError, ValueError, OSError):
                self._writable = False
                return False

    def no_more(self) -> None:
        """Tell the adapter nothing further is coming, and leave it to finish.

        Not the same as ending it. An adapter that reads its input to the end before it will answer
        at all is waiting for exactly this, and ending it instead would take it away mid-answer.
        Asking twice is allowed.
        """
        with self._saying:
            if not self._writable:
                return
            self._writable = False
            with contextlib.suppress(Exception):
                self.talking.stdin.close()

    # -- ending ------------------------------------------------------------------------

    def stop(self, gently_for: float = 5.0, firmly_for: float = 5.0,
             settling_for: float = SETTLING_SECONDS) -> str:
        """End the adapter and everything it started. `""` when it is gone, otherwise why it is not.

        **Its own ending is waited for first, briefly.** The output stream closing is not the program
        exiting — one that has said everything and is tidying up is a moment away from leaving on its
        own, and signalling it there costs two things at once: a clean shutdown it was in the middle
        of, and its exit code, which `programs.stop` reaps on the way past. That code is not
        decoration. It is what became of the *program*, which the contract keeps deliberately apart
        from what the *brain* made of the turn — a brain that answered well inside an adapter that
        then crashed has to read as the failure it was, and nothing else can say so.

        Then the process **group**, which is what `programs.stop` signals and why it matters: a brain
        runs editors, search tools and language servers, and signalling only the child we can see
        would leave every one of them behind.

        Safe to call twice, and called on the way out of `records` however that ended — including
        when a caller abandoned the iterator, which is otherwise how a process is left running with
        nobody holding it.
        """
        if self._stopped:
            return ""
        self._stopped = True
        self._ending = True
        self.no_more()
        settle = time.monotonic() + settling_for
        while not self.outcome().over and time.monotonic() < settle:
            time.sleep(0.02)
        stuck = ""
        if self._became is None:
            stuck = programs.stop(self.talking.pid, gently_for=gently_for, firmly_for=firmly_for)
        # **The pipe is closed last, and that ordering is the whole of this.** A file object holds a
        # lock its reader takes for the length of a read, and the reading thread is blocked inside
        # `readline` on this very pipe — so closing it first waits for that read to return, which
        # happens only when the program at the other end says something or leaves. Measured: ending
        # a brain that had gone quiet took thirty seconds, which was exactly how long that brain had
        # left to sleep. A brain that is genuinely wedged never says anything again, so the wait was
        # not thirty seconds but for ever, inside a gateway shutdown with twenty-five to live.
        #
        # Ending the program first makes the pipe reach its end, the read return, and the lock free,
        # so the close below costs nothing.
        with contextlib.suppress(Exception):
            self.talking.stdout.close()
        return stuck

    def outcome(self) -> programs.Collected:
        """Whether the adapter has finished, and what it said if it has.

        Three answers rather than two — see `programs.Collected`. *Over, and nobody can say* is not a
        kind of failure: it is what a child of a process that is gone looks like.

        **Remembered once it is known**, because taking a child's status is what settles it: asking a
        second time answers *over, and nobody can say* however cleanly it left, and the exit code
        would be lost between the moment this is asked and the moment a turn writes it down.
        """
        if self._became is not None:
            return self._became
        got = programs.collected(self.talking.pid)
        if got.over:
            self._became = got
        return got

    def errors_tail(self, at_most_lines: int = 20, at_most_chars: int = 500) -> List[str]:
        """The last few things the adapter said went wrong, for a turn that has to explain itself.

        Bounded twice, because this is going into a log and into a sentence somebody reads: a program
        that writes a megabyte of progress bars would otherwise roll the evidence off the end of the
        very report it is meant to explain. **Never raises** — a turn that failed must not fail again
        while saying why.
        """
        if self._errors is None:
            return []
        try:
            with open(self._errors, "r", encoding="utf-8", errors="replace") as reading:
                said = reading.read()[-(at_most_lines * at_most_chars):]
        except OSError:
            return []
        kept = [one[:at_most_chars] for one in said.splitlines() if one.strip()]
        return kept[-at_most_lines:]


def started(argv, errors: Path, where: Optional[Path] = None,
            env: Optional[dict] = None, holding=(), **how) -> Stream:
    """Start an adapter and hand back the stream to read it on.

    A thin pairing of `programs.talking` with `Stream`, here rather than at each call site so that
    the error file the process writes to and the one the stream watches for silence are the same
    file. They were two arguments in an earlier shape, and two arguments that must agree is one that
    eventually will not.
    """
    errors.parent.mkdir(parents=True, exist_ok=True)
    talking = programs.talking(argv, errors, where=where, env=env, holding=holding)
    return Stream(talking, errors=errors, **how)
