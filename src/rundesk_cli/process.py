"""A program rundesk runs, and how rundesk keeps hold of it.

rundesk does not drive what these programs do — the agent brains it will run own their
own loop entirely. What rundesk owns is the process: when it starts, what it may see of
the machine, everything it says, when it stops, and what became of it.

Four things shape everything below, and all four come from what these programs are:
sessions that run for hours, say a great deal, start programs of their own, and run
many at a time.

1. **Its own session.** A program is started in one, so it and everything it spawns share
   a process group of their own. Ending it therefore ends the whole tree (R-PROC-5) — a
   brain runs editors, search tools and language servers, and signalling only the child we
   can see would leave every one of them behind. The cost is that our children are not in
   *our* group, so a gateway killed outright cannot take them with it. Whether that
   is acceptable is an open question on the contract, not a settled guarantee.

2. **Silence, not duration, is the failure.** A session may legitimately run for hours, so
   a clock that ends it is a clock that ends real work (R-PROC-6). What a wedged program
   does is go quiet, so that is what is measured (R-PROC-7).

3. **Nothing is accumulated (R-PROC-12).** Output is passed to the caller as it arrives and only a
   tail is retained. Hours of a streamed event log held in memory to be handed back once
   at the end is a leak with a long fuse.

4. **Nothing here is shared.** Every program is its own handle with its own state, so any
   number of them run at once without coordinating (R-PROC-10). There is no registry, no
   lock and no module-level mutable state in this file, and that is deliberate: what is
   running is the gateway's to know, and one process's trouble is never another's.
"""

from __future__ import annotations

import asyncio
import codecs
import os
import shutil
import signal
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

#: How a program ended. Told apart because each sends a reader somewhere different:
#: `FINISHED` needs nothing, `FAILED` is the program's own doing, `ENDED` and `SILENT`
#: are ours (R-PROC-8, R-PROC-9, R-PROC-13).
FINISHED = "finished"
FAILED = "failed"
ENDED = "ended"
SILENT = "silent"
OVERRAN = "overran"

#: How long a program gets to leave politely before it is taken out (R-PROC-5).
GRACE_SECONDS = 5.0

#: How long a program may say nothing before rundesk takes it for wedged (R-PROC-7).
#: Generous on purpose: a working session can be quiet for a long time while a single
#: tool call runs, and ending one of those would be ending real work.
SILENCE_SECONDS = 1800.0

#: The longest a program may run however much it is saying (R-PROC-13). Silence cannot
#: see a program wedged in a loop that keeps announcing itself, and that shape would
#: otherwise run until a person noticed. Set far past what real work reaches, because
#: this is the backstop and the silence window is the instrument.
CEILING_SECONDS = 48 * 60 * 60.0

#: Read size, and the point at which output with no line ending in it is passed on
#: anyway. Neither is a limit on what a program may say — only on how much is held
#: at once, so a program that never emits a newline cannot grow us without bound
#: (R-PROC-12). Counted in characters, which is what is actually held: the bytes
#: behind them can be several times as many.
READ_BYTES = 65536
MAX_LINE_CHARS = 4 * 1024 * 1024

#: How long what a program left behind gets to hand over the last of its output once the
#: program itself has gone. Short: this is a drain, not a wait for more work.
DRAIN_SECONDS = 2.0

#: How often a program that is saying nothing is looked in on. Silence is measured in
#: these, so it is also how close to the mark the measurement lands — near enough for a
#: window of half an hour, and cheap enough to spend on every session at once.
POLL_SECONDS = 1.0

#: How many lines of a program's output are kept to hand back at the end (R-PROC-12). Everything is
#: passed to the caller as it arrives; this is a tail for diagnosis, not a transcript —
#: the durable record is a concern of its own, and not this module's.
RETAINED_LINES = 200


class NotAbsolute(ValueError):
    """A program named rather than located.

    Refused because the one caller that matters runs under the machine's supervisor,
    which hands a job a bare environment — a name that resolves in your shell resolves
    to nothing there, and the failure arrives much later and reads like something else
    (R-PROC-2).
    """


def resolve(name: str, path: str | None = None) -> str | None:
    """Where a program actually is, looked up once so nothing has to look again.

    Called when rundesk is installed rather than on every run: what is on a PATH is a
    property of the shell that asked, and the gateway has no shell (R-PROC-2).
    """
    if os.path.isabs(name):
        return name if os.path.exists(name) else None
    return shutil.which(name, path=path)


@dataclass
class Result:
    """What became of a program, once it is no longer running.

    `output` is the retained tail, not everything that was said — see `RETAINED_LINES`.
    """

    reason: str
    code: int | None
    output: str = ""

    @property
    def ok(self) -> bool:
        return self.reason == FINISHED


#: `eq=False` so a program is itself and nothing else: the gateway holds what it is
#: running in a set, and two programs with the same command line are two programs.
@dataclass(eq=False)
class Program:
    """One program rundesk runs, and the handle that keeps hold of it.

    A handle rather than a single call because the gateway has to be able to reach
    everything it is running at the moment it is told to stop (R-GW-8). Nothing is
    shared between two of these, so any number run at once (R-PROC-10).
    """

    argv: Sequence[str]
    #: Nothing, unless rundesk says otherwise. `None` would mean the machine's whole
    #: environment, which is the opposite of R-PROC-1 and would hand every secret the
    #: gateway holds to every program it runs. `environment()` builds the real one.
    env: dict[str, str] = field(default_factory=dict)
    silence: float | None = SILENCE_SECONDS
    ceiling: float | None = CEILING_SECONDS
    _proc: asyncio.subprocess.Process | None = field(default=None, repr=False, init=False)
    _ended: bool = field(default=False, repr=False, init=False)

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if not self.argv:
            raise NotAbsolute("a program to run was not named at all")
        program = self.argv[0]
        if not os.path.isabs(program):
            raise NotAbsolute(
                f"'{program}' is a name, not a location — resolve it before running it"
            )
        self._proc = await asyncio.create_subprocess_exec(
            *self.argv,
            # Nothing is read from us, so a program that decides to read its input would
            # otherwise wait on a terminal that is not there, forever. A program that took
            # further instruction while it ran would need this reopened — an open question
            # rather than a settled no.
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            # Folded together on purpose: two pipes means two orderings, and what a
            # program said is only useful in the order it said it (R-PROC-3). Right for
            # output meant to be read; an open question for output meant to be parsed,
            # where anything not part of the structure corrupts it.
            stderr=asyncio.subprocess.STDOUT,
            # The whole environment a program gets, chosen here rather than inherited
            # from whatever happened to start us (R-PROC-1).
            env=dict(self.env),
            # Its own session, and so its own process group: see the module docstring.
            start_new_session=True,
        )

    async def wait(self, on_line: Callable[[str], None] | None = None) -> Result:
        """Read everything it says until it stops, and report what became of it.

        Reads in chunks and finds the line endings here rather than asking the stream for
        a line: a stream asked for a line longer than it can hold raises, and an agent
        brain reporting one large tool result as one line is exactly what would do it.
        """
        if self._proc is None:
            raise RuntimeError("wait() before start()")
        assert self._proc.stdout is not None
        tail: deque[str] = deque(maxlen=RETAINED_LINES)
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        went_silent = False
        overran = False
        began = time.monotonic()

        def emit(line: str) -> None:
            tail.append(line)
            if on_line is not None:
                on_line(line)

        # Read in short spells rather than one long one, so that between them we can look
        # at whether the program is still there. Waiting on its exit instead does not
        # work: that only resolves once every pipe is closed too, and anything the
        # program left running is holding one — the exit would land hours late, or never.
        reader: asyncio.Future | None = None
        quiet_for = 0.0
        try:
            while True:
                # Checked on every pass, not only when nothing was said: the shape this
                # exists for is a program wedged in a loop that keeps announcing itself,
                # and that one never stops arriving (R-PROC-13).
                if self.ceiling is not None and time.monotonic() - began >= self.ceiling:
                    overran = True
                    break
                if reader is None:
                    reader = asyncio.ensure_future(self._proc.stdout.read(READ_BYTES))
                # Once it has gone there is nothing more coming but what is already in
                # flight, so the wait drops from "has it gone quiet" to "is it drained".
                gone = self._proc.returncode is not None
                spell = DRAIN_SECONDS if gone else self._spell()
                done, _ = await asyncio.wait({reader}, timeout=spell)
                if reader in done:
                    chunk = reader.result()
                    reader = None
                    if not chunk:
                        break  # the pipe closed: nothing holds it and nothing is coming
                    quiet_for = 0.0  # measured per stretch, never summed (R-PROC-6)
                    pending += decoder.decode(chunk)
                    while "\n" in pending:
                        line, pending = pending.split("\n", 1)
                        emit(line)
                    if len(pending) >= MAX_LINE_CHARS:
                        emit(pending)
                        pending = ""
                    continue
                if gone:
                    break  # drained as far as it will drain — something it left holds the pipe
                quiet_for += spell
                if self.silence is not None and quiet_for >= self.silence:
                    went_silent = True
                    break
        except BaseException:
            # Anything at all going wrong in here — whoever was waiting giving up, or the
            # caller's own handler raising on a line it did not like — must still take the
            # program with it. Catching only cancellation left the whole tree running with
            # nothing holding it, which is the orphan this module exists to prevent
            # (R-PROC-4, R-PROC-11).
            await self.end()
            raise
        finally:
            if reader is not None:
                reader.cancel()

        # Bytes the decoder was holding back in case the rest of a character followed. It
        # never did: the program has gone. Finalising turns them into what they can be
        # rather than dropping them, which is what happens if nothing ever asks.
        pending += decoder.decode(b"", final=True)
        if pending:
            emit(pending)
        if not overran and not went_silent and self._proc.returncode is None:
            # The pipe closing is not the program dying. One that closes what it writes
            # out and keeps going — anything that daemonises itself, or execs something
            # that does — reaches here alive, and waiting on it with nothing bounding the
            # wait is a wedge nothing recovers from: the silence window is already spent,
            # so R-PROC-7 would never fire, and the name it was started under would be
            # held against a restart of that work for as long as the gateway lives.
            # Bounded by whichever runs out first. Waiting on the silence alone loses
            # the ceiling entirely here — and a program allowed to be quiet indefinitely
            # (R-PROC-6) that closes its output and keeps going would then be waited on
            # forever, which is the one thing the ceiling exists to prevent.
            if not await self._exits_within(self._patience_left(began)):
                overran = self._past_ceiling(began)
                went_silent = not overran
        # Ended here, after every way of deciding it should be — not before. Deciding it
        # overran and then reaping without ending it is a wait on a process nobody asked
        # to stop, which is the very shape of wedge this is all here to prevent.
        if overran or went_silent:
            await self.end()
        code = await self._reap()
        await self._sweep()
        if overran:
            return Result(OVERRAN, code, "\n".join(tail))
        if went_silent:
            return Result(SILENT, code, "\n".join(tail))
        if self._ended:
            return Result(ENDED, code, "\n".join(tail))
        return Result(FINISHED if code == 0 else FAILED, code, "\n".join(tail))

    def _past_ceiling(self, began: float) -> bool:
        return self.ceiling is not None and time.monotonic() - began >= self.ceiling

    def _patience_left(self, began: float) -> float | None:
        """How long there is left to wait, on whichever clock runs out first."""
        left = self.silence
        if self.ceiling is not None:
            to_ceiling = max(0.0, self.ceiling - (time.monotonic() - began))
            left = to_ceiling if left is None else min(left, to_ceiling)
        return left

    async def _exits_within(self, patience: float | None) -> bool:
        """Does it go of its own accord in the time allowed? None means however long."""
        assert self._proc is not None
        if patience is None:
            await self._proc.wait()
            return True
        if patience <= 0:
            return self._proc.returncode is not None
        try:
            await asyncio.wait_for(asyncio.shield(self._proc.wait()), patience)
        except asyncio.TimeoutError:
            return False
        return True

    def _spell(self) -> float:
        """How long to read for before looking at the program again.

        Never longer than the silence allowed, or a program permitted to be quiet for
        less than one spell would not be noticed until the spell was up.
        """
        if self.silence is None:
            return POLL_SECONDS
        return min(POLL_SECONDS, self.silence)

    async def _reap(self) -> int | None:
        assert self._proc is not None
        return await self._proc.wait()

    async def end(self) -> None:
        """End it, and everything it started, whether or not it cooperates (R-PROC-4).

        Asked first and taken second: a brain killed outright can leave its own session
        half-written, and the polite signal costs a few seconds at shutdown.
        """
        if self._proc is None or self._proc.returncode is not None:
            return
        self._ended = True
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if not self._signal_group(sig):
                return  # nothing left in the group to signal
            try:
                await asyncio.wait_for(asyncio.shield(self._proc.wait()), GRACE_SECONDS)
                return
            except asyncio.TimeoutError:
                continue

    async def _sweep(self) -> None:
        """Take anything the program left running, once the program itself is gone.

        A program that exits does not take its children with it — they are reparented and
        carry on, still holding the pipe we were reading. Costs nothing when there is
        nothing left: signalling an empty group fails at once (R-PROC-5, R-PROC-11).
        """
        if self._proc is None or not self._signal_group(signal.SIGTERM):
            return
        await asyncio.sleep(GRACE_SECONDS)
        self._signal_group(signal.SIGKILL)

    def _signal_group(self, sig: int) -> bool:
        """Signal the whole group, so what it started goes with it (R-PROC-5).

        The group id is the program's own pid: `start_new_session` makes it the leader.
        Asking the system for the group instead would race the program's exit, and on a
        recycled pid would signal something else entirely.

        False means *there is nothing left to signal*, and nothing else. Being unable to
        reach a group that is still there is not that: treating the two alike meant one
        failed signal ended the whole escalation, so a program we could not ask politely
        was never asked firmly either — and `end()` returned as though it had worked.
        """
        assert self._proc is not None
        try:
            os.killpg(self._proc.pid, sig)
            return True
        except ProcessLookupError:
            return False  # the group is empty: everything in it has already gone
        except PermissionError:
            return True  # still there, and still ours to keep trying to end


async def run(
    argv: Sequence[str],
    env: dict[str, str] | None = None,
    silence: float | None = SILENCE_SECONDS,
    ceiling: float | None = CEILING_SECONDS,
    on_line: Callable[[str], None] | None = None,
) -> Result:
    """Start a program, read it to the end, and say what became of it."""
    program = Program(argv, env=env or {}, silence=silence, ceiling=ceiling)
    await program.start()
    return await program.wait(on_line)


async def end_all(programs: Iterable[Program]) -> None:
    """End everything still running, at once rather than one after another.

    In turn would spend the grace period once per program, and the machine's own
    supervisor does not wait that long before taking the gateway out (R-GW-7, R-GW-8).
    """
    await asyncio.gather(*(p.end() for p in programs if p.alive), return_exceptions=True)


def environment(home: Path, path: str | None = None) -> dict[str, str]:
    """The environment a program rundesk runs is given (R-PROC-1).

    Built rather than inherited. The supervisor hands a job almost nothing, so anything
    a program needs has to be put here deliberately — and anything not put here is a
    thing rundesk has decided its programs do not see.
    """
    return {
        "HOME": str(Path.home()),
        "PATH": path if path is not None else os.environ.get("PATH", ""),
        "RUNDESK_HOME": str(home),
        # Provider CLIs render differently when they believe a person is watching, and
        # nobody is: this is the gateway.
        "TERM": "dumb",
        # Said, because a program told nothing falls back to whatever the machine's
        # default is — and on a bare environment that is ASCII, which turns the first
        # accented character in a transcript into a crash rather than a character.
        "LANG": "en_US.UTF-8",
    }
