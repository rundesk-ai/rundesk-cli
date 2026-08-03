"""A program rundesk runs, and how rundesk keeps hold of it.

rundesk does not drive what these programs do — the agent brains it will run own their
own loop entirely. What rundesk owns is the process: when it starts, what it may see of
the machine, everything it says, when it stops, and what became of it.

Five things shape everything below, and all five come from what these programs are:
sessions that run for hours, say a great deal, start programs of their own, run many at
a time, and — the ones that are agent brains — are talked to rather than merely watched.

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

5. **A program is read one of two ways, and one of them answers back.** Output meant for a
   person is text, split into lines, handed over as it arrives (R-PROC-3). Output meant to
   be parsed is bytes, framed into whole records, never split (R-PROC-18) — and that kind
   is written to while it runs (R-PROC-14), with what it says went wrong kept off the
   stream that is being parsed (R-PROC-15) and drained regardless, because a stream nobody
   reads is a program that stops reading us (R-PROC-16). Between the reading and whoever
   receives it sits something bounded, so a slow or broken receiver can neither hold the
   program up nor end it (R-PROC-17). One loop serves both: when to stop reading is the
   same question either way.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import inspect
import os
import signal
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from rundesk import scripts_home, skills_home

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

#: How long the *receiver* gets to take what it is still owed once the program has gone
#: (R-PROC-17). Its own constant, because it is the opposite of a drain: nothing is
#: waiting on it, the read loop is finished and the program is already reaped, so the
#: only thing this bounds is how long a slow receiver may go on receiving. Shared with
#: `DRAIN_SECONDS` it was two seconds — a receiver spending a fifth of a second on a
#: record, which a rate-limited channel post easily does, got nine of fifty and the run
#: still reported that it had finished.
RECEIVING_SECONDS = 30.0

#: How many times one record is offered to a receiver that failed on it, and how long to
#: wait between (R-PROC-17). A receiver that fails is often about to recover — a channel
#: being rate-limited, a file being rotated — and the record it dropped is not
#: independent of the ones around it. Capped so a receiver that will never recover cannot
#: hold the queue, and doubled between tries so it cannot be spun on.
DELIVERY_TRIES = 4
DELIVERY_WAIT_SECONDS = 0.05
DELIVERY_WAIT_CAP_SECONDS = 1.0

#: How often a program that is saying nothing is looked in on. Silence is measured in
#: these, so it is also how close to the mark the measurement lands — near enough for a
#: window of half an hour, and cheap enough to spend on every session at once.
POLL_SECONDS = 1.0

#: How many lines of a program's output are kept to hand back at the end (R-PROC-12). Everything is
#: passed to the caller as it arrives; this is a tail for diagnosis, not a transcript —
#: the durable record is a concern of its own, and not this module's.
RETAINED_LINES = 200

#: The most a retained tail may hold, whatever the count (R-PROC-12). Counting items
#: bounds nothing when one item may be megabytes: two hundred records at the record cap
#: is most of a gigabyte, per stream, for one conversation.
TAIL_BYTES = 256 * 1024

#: What one held record costs before its own bytes are counted (R-PROC-12). Without it a
#: receiver that has stopped reading can be handed any number of empty records — or gaps,
#: which have no bytes at all — and the bound never notices.
HELD_OVERHEAD = 64

#: The most one record of structured output may be before it is dropped rather than
#: passed on in pieces (R-PROC-18). Counted in bytes, which is what is actually held —
#: unlike `MAX_LINE_CHARS`, whose characters may be several times as many bytes.
MAX_RECORD_BYTES = 4 * 1024 * 1024

#: The most that is held for a receiver that has fallen behind (R-PROC-17). Generous on
#: purpose: reaching it should mean a receiver is broken rather than busy, because what
#: happens at the bound is that records are lost.
HELD_BYTES = 8 * 1024 * 1024

#: How long to wait between asking whether a program has gone. Asked of its exit code
#: rather than waited on, because waiting resolves only once every pipe is closed too —
#: and a program rundesk talks to has three of them (R-PROC-16).
GONE_SECONDS = 0.05


class NotAbsolute(ValueError):
    """A program named rather than located.

    Refused because the one caller that matters runs under the machine's supervisor,
    which hands a job a bare environment — a name that resolves in your shell resolves
    to nothing there, and the failure arrives much later and reads like something else
    (R-PROC-2).
    """


def located(program: str) -> bool:
    """Is this a program rundesk can find, rather than a name a shell would look up?

    One rule in one place. Anything that writes down a program to be run later has to
    apply the same test `start` will, and a second copy of "is it absolute" somewhere
    else is a second copy that can come to disagree.
    """
    return os.path.isabs(program)


@dataclass
class Result:
    """What became of a program, once it is no longer running.

    `output` is the retained tail, not everything that was said — see `RETAINED_LINES`.
    """

    reason: str
    code: int | None
    output: str = ""
    #: How many records never reached whoever was receiving them (R-PROC-17). Part of the
    #: outcome rather than only a counter on the handle, because it is the difference
    #: between an account of a run and an account with holes in it.
    undelivered: int = 0

    @property
    def ok(self) -> bool:
        """Did it finish, *and* was everything it said handed over?

        Both, because a run whose records were lost is not one anything downstream can
        act on. Fifty records written, nine received and `ok` — which is what this said
        before — is the reading that misleads most: everything after the loss is read as
        though nothing were missing. A receiver that failed on a record and recovered is
        a different matter and does not land here; that is `refused`, and it is the
        receiver's own to answer for.
        """
        return self.reason == FINISHED and not self.undelivered


class NotListening(Exception):
    """Written to, and nothing is reading it (R-PROC-14).

    Three ways round to the same answer, and they are one answer on purpose: it was never
    opened to be written to, rundesk has already said there is no more coming, or it has
    gone. In every case the next thing written would land nowhere, which is the only fact
    a caller can act on. Told apart from `gone_within`, which asks the narrower question —
    whether the program itself has exited — because a program can be perfectly alive and
    still not listening.
    """


@dataclass(frozen=True)
class Gap:
    """Records that were lost, said where they were lost (R-PROC-17, R-PROC-18).

    Handed to the receiver in the place the loss happened rather than counted up at the
    end. A count says something was lost; a gap says *where*, and where is what decides
    whether what surrounds it can still be made sense of. Records are not independent —
    text arrives in pieces meant to be joined — so a hole nobody is told about is not
    less of an answer, it is a wrong one.
    """

    records: int
    why: str


class Held:
    """What a program said, held between the reading of it and the receiving of it.

    Between the two on purpose (R-PROC-17). Handed straight to a receiver, a slow one
    stops the reading — and for a program rundesk also writes to that is a deadlock: the
    program blocks writing what nobody is reading, so it never reads what we are writing.
    So offering never waits, and never raises.

    Bounded in bytes rather than in records, because one record may be megabytes and a
    count of them bounds nothing (R-PROC-12). Past the bound the *oldest* go: the end of
    what a program says is the part that matters — what it concluded, and that it is done.
    """

    def __init__(self, held: int | None = None):
        # Resolved here rather than in the signature: a default argument is bound once,
        # when this file is read, and nothing can reach it afterwards.
        self._held = HELD_BYTES if held is None else held
        self._waiting: deque = deque()
        self._bytes = 0
        self._lost = 0
        self._arrived = asyncio.Event()
        self._closed = False

    @property
    def lost(self) -> int:
        return self._lost

    @staticmethod
    def _weight(one) -> int:
        """What holding this costs. Never nothing, or a bound counts to infinity."""
        return HELD_OVERHEAD + (0 if isinstance(one, Gap) else len(one))

    def offer(self, record: bytes) -> None:
        """Take this, whatever state the receiver is in. Never waits, never raises."""
        self._waiting.append(record)
        self._bytes += self._weight(record)
        self._arrived.set()
        self._evict()

    def waiting(self) -> int:
        """How many records are still held, undelivered."""
        return sum(1 for one in self._waiting if not isinstance(one, Gap))

    def lose(self, records: int, why: str) -> None:
        """Say that records were lost here, without ever having held them.

        Bounded like everything else that adds to the queue (R-PROC-17). This path used
        to append and never check, so a program emitting nothing *but* records too large
        to hold grew the queue without limit — the one side of the bound left one-sided.
        A loss of the same kind is folded into the one before it rather than spending a
        queue item each, so the count stays exact without the markers themselves becoming
        the thing that overruns.
        """
        last = self._waiting[-1] if self._waiting else None
        if isinstance(last, Gap) and last.why == why:
            self._waiting[-1] = Gap(last.records + records, why)
        else:
            self._waiting.append(Gap(records, why))
            self._bytes += self._weight(self._waiting[-1])
        self._lost += records
        self._arrived.set()
        self._evict()

    def _evict(self) -> None:
        """Let the oldest go until what is held is inside the bound.

        Never the newest: the end of what a program says is the part that matters. Never
        the only one either — a bound smaller than a single record would otherwise drop
        everything and deliver nothing at all.
        """
        dropped = merged = 0
        while self._bytes > self._held and len(self._waiting) > 1:
            went = self._waiting.popleft()
            self._bytes -= self._weight(went)
            if isinstance(went, Gap):
                merged += went.records  # gaps merge rather than pile up
                continue
            dropped += 1
        if dropped or merged:
            self._waiting.appendleft(Gap(dropped + merged, "fell behind"))
            self._bytes += self._weight(self._waiting[0])
            # Only what was lost *now*. A merged gap was counted when it was made, and
            # counting it again turned eight lost records into thirty-six.
            self._lost += dropped

    def close(self) -> None:
        self._closed = True
        self._arrived.set()

    async def next(self):
        """The next record or gap, or None once there is nothing more coming."""
        while True:
            if self._waiting:
                it = self._waiting.popleft()
                self._bytes -= self._weight(it)
                if not self._waiting:
                    self._arrived.clear()
                return it
            if self._closed:
                return None
            self._arrived.clear()
            await self._arrived.wait()


class _Lines:
    """Framing for output meant to be read: text, split on line endings.

    What a program says is only useful in the order it said it, and a person reading a
    very long line would rather have it in pieces than not at all — so past the cap this
    passes on what it holds and carries on (R-PROC-3, R-PROC-12).

    Extracted from `wait()` unchanged, so that what a program rundesk only reads gets
    exactly the treatment it has always had.
    """

    def __init__(self, on_line: Callable[[str], None] | None):
        self._on_line = on_line
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._pending = ""
        self._tail: deque = deque()   # bounded by `_keep`, never by itself
        self._held_bytes = 0

    def feed(self, chunk: bytes) -> None:
        self._pending += self._decoder.decode(chunk)
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._emit(line)
        if len(self._pending) >= MAX_LINE_CHARS:
            self._emit(self._pending)
            self._pending = ""

    def finish(self) -> None:
        # Bytes the decoder was holding back in case the rest of a character followed. It
        # never did: the program has gone. Finalising turns them into what they can be
        # rather than dropping them, which is what happens if nothing ever asks.
        self._pending += self._decoder.decode(b"", final=True)
        if self._pending:
            self._emit(self._pending)
            self._pending = ""

    def _keep(self, one) -> None:
        """Hold this for the diagnosis tail, and let the oldest go once it is too much.

        Bounded in bytes as well as in count (R-PROC-12): two hundred of anything says
        nothing about how much that is, and one thing a program says may be megabytes.

        Both bounds are enforced *here*, and the deque deliberately has no `maxlen`. A
        deque that evicts on its own does it silently — the count stayed right while the
        byte total kept climbing past what was actually held, until it exceeded the bound
        on its own and started throwing away the newest lines to chase a number that had
        nothing behind it. The tail this exists to preserve collapsed to one line.
        """
        self._tail.append(one)
        self._held_bytes += len(one)
        while len(self._tail) > 1 and (
            self._held_bytes > TAIL_BYTES or len(self._tail) > RETAINED_LINES
        ):
            self._held_bytes -= len(self._tail.popleft())

    def _emit(self, line: str) -> None:
        self._keep(line)
        if self._on_line is not None:
            # Allowed to raise, and the loop above takes the program with it. A receiver
            # that cannot cope with what it is being handed is a reason to stop, for
            # output nobody else is holding (R-PROC-11).
            self._on_line(line)

    @property
    def held(self) -> str:
        return "\n".join(self._tail)


class _Records:
    """Framing for output meant to be parsed: bytes, whole or not at all (R-PROC-18).

    Half a record is not a smaller record, it is a corrupt one — and a receiver lenient
    enough to accept it turns a loud failure into a wrong answer. So past the cap this
    drops the record, finds the next line ending and carries on, saying a record was
    lost where it was lost. The framing survives, which is why one enormous record does
    not cost every record after it.

    Bytes rather than text: a record is a unit for a parser, not prose for a person, and
    decoding here would put a question mark where a byte was, which nothing can tell from
    one the program meant. It is also what makes the cap a true bound on what is held,
    which counting characters is not.
    """

    def __init__(self, held: Held):
        self._held = held
        self._pending = bytearray()
        self._skipping = False
        self._tail: deque = deque()   # bounded by `_keep`, never by itself
        self._held_bytes = 0

    def feed(self, chunk: bytes) -> None:
        self._pending += chunk
        while True:
            at = self._pending.find(b"\n")
            if at < 0:
                break
            record = bytes(self._pending[:at])
            del self._pending[:at + 1]
            if self._skipping:
                self._skipping = False  # the record being dropped ends here
                continue
            if len(record) > MAX_RECORD_BYTES:
                # Whole, and still too big. Asked only of what is left to arrive, the cap
                # would never see a record that turned up complete inside one read — and
                # the size at which this matters is well under a single read.
                self._held.lose(1, "too large")
                continue
            self._emit(record)
        if self._skipping:
            self._pending.clear()  # counted, never kept
        elif len(self._pending) > MAX_RECORD_BYTES:
            self._skipping = True
            self._pending.clear()
            self._held.lose(1, "too large")

    def finish(self) -> None:
        # What is left has no line ending, so it is not a record — it is the beginning of
        # one the program did not finish. Delivered, it would be indistinguishable from a
        # whole one, and nothing downstream could tell a forgotten terminator from a
        # program killed mid-sentence. Said, rather than passed on or passed over.
        if self._pending and not self._skipping:
            self._held.lose(1, "unterminated")
        self._pending.clear()
        self._skipping = False

    _keep = _Lines._keep

    def _emit(self, record: bytes) -> None:
        if record.endswith(b"\r"):
            record = record[:-1]  # exactly one, and only at the end: the rest is data
        self._keep(record)
        self._held.offer(record)

    @property
    def held(self) -> str:
        return "\n".join(one.decode("utf-8", "replace") for one in self._tail)


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
    #: Whether anything is ever written *to* it (R-PROC-14). Closed by default: a program
    #: nothing writes to that decides to read its input would wait on a terminal that is
    #: not there, forever. Opened only for one rundesk holds a conversation with.
    takes_input: bool = False
    #: Whether what it says and what went wrong are kept apart (R-PROC-15). Folded by
    #: default, because what a program said is only useful in the order it said it
    #: (R-PROC-3) — and at the price that, kept apart, there is no order between the two
    #: at all. Kept apart only for output meant to be parsed, which anything not part of
    #: the structure corrupts.
    errors_apart: bool = False
    #: Where it starts from (R-PROC-19). Nothing by default, which means wherever rundesk
    #: itself was started — under the machine's supervisor, a directory the owner never
    #: chose. Every agent brain works on a project rather than in the abstract, so the one
    #: it is pointed at is a decision rundesk has to be able to make rather than inherit.
    cwd: str | Path | None = None
    #: How long the receiver gets to take what it is owed once the program has gone
    #: (R-PROC-17). `None` means `RECEIVING_SECONDS`, resolved where it is used — a
    #: caller knows its own sink and nothing here does.
    receiving: float | None = None
    #: Handed every line the program says went wrong, as it says it (R-PROC-15). The
    #: `errors` property keeps only a tail for diagnosis; a caller that means to write
    #: all of it down somewhere durable needs each line, and a tail is not each line.
    on_error: Callable[[str], None] | None = None
    _proc: asyncio.subprocess.Process | None = field(default=None, repr=False, init=False)
    _ended: bool = field(default=False, repr=False, init=False)
    _writable: bool = field(default=True, repr=False, init=False)
    #: Held across write *and* drain, so two writes cannot interleave (R-PROC-14). Made in
    #: `start`, where there is a loop to make it against.
    _writing: object = field(default=None, repr=False, init=False)
    _refused: int = field(default=0, repr=False, init=False)
    _undelivered: int = field(default=0, repr=False, init=False)
    _heard: float = field(default=0.0, repr=False, init=False)
    #: What it said went wrong, when that is kept apart. Read rather than handed over:
    #: nothing parses it, and it is where a provider says why it died.
    _errors: object = field(default=None, repr=False, init=False)

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def errors(self) -> str:
        """The tail of what it said went wrong, when the two streams are kept apart."""
        return self._errors.held if self._errors is not None else ""

    @property
    def refused(self) -> int:
        """How many records the receiver failed on. Its failing is not the program's."""
        return self._refused

    @property
    def undelivered(self) -> int:
        """How many records were never handed over at all (R-PROC-17).

        Separate from `refused`, which is a receiver that was handed one and could not
        cope. This is the drain running out before a slow receiver had taken everything —
        and it used to be silent, so a run that lost forty-nine of fifty records still
        reported that it had finished.
        """
        return self._undelivered

    async def start(self) -> None:
        if not self.argv:
            raise NotAbsolute("a program to run was not named at all")
        program = self.argv[0]
        if not located(program):
            raise NotAbsolute(
                f"'{program}' is a name, not a location — resolve it before running it"
            )
        # Made here rather than in the field, because a lock belongs to the loop it is
        # made on and this dataclass is built long before there is one.
        self._writing = asyncio.Lock()
        self._proc = await asyncio.create_subprocess_exec(
            *self.argv,
            # Closed unless rundesk means to write to it (R-PROC-14). Nothing is read
            # from us otherwise, so a program that decides to read its input would wait
            # on a terminal that is not there, forever.
            stdin=asyncio.subprocess.PIPE if self.takes_input else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            # Folded together unless rundesk means to parse what it says (R-PROC-15). Two
            # pipes means two orderings, and what a program said is only useful in the
            # order it said it (R-PROC-3) — right for output meant to be read, and wrong
            # for output meant to be parsed, which anything not part of it corrupts.
            stderr=asyncio.subprocess.PIPE if self.errors_apart else asyncio.subprocess.STDOUT,
            # The whole environment a program gets, chosen here rather than inherited
            # from whatever happened to start us (R-PROC-1).
            env=dict(self.env),
            # Where it starts from, chosen rather than inherited (R-PROC-19). `None` is
            # asyncio's own "wherever we are", which under the supervisor is a directory
            # nobody picked.
            cwd=str(self.cwd) if self.cwd is not None else None,
            # Its own session, and so its own process group: see the module docstring.
            start_new_session=True,
        )

    async def wait(
        self,
        on_line: Callable[[str], None] | None = None,
        sink: Callable[[object], object] | None = None,
    ) -> Result:
        """Read everything it says until it stops, and report what became of it.

        Reads in chunks and finds the line endings here rather than asking the stream for
        a line: a stream asked for a line longer than it can hold raises, and an agent
        brain reporting one large tool result as one line is exactly what would do it.

        `on_line` is for output meant to be read and `sink` for output meant to be
        parsed, and they differ in every way that matters: what a unit is, what happens
        to one too big to hold, and whether a receiver's trouble is the program's. One
        loop serves both, because when to stop reading is the same question either way.
        """
        if self._proc is None:
            raise RuntimeError("wait() before start()")
        assert self._proc.stdout is not None
        if sink is not None and not self.errors_apart:
            # Refused rather than obliged. Folded together, everything the program says
            # went wrong arrives in the middle of what is meant to be parsed — so the
            # records would be corrupted by exactly the warning that explains why, and
            # nothing downstream could tell that apart from the program talking nonsense
            # (R-PROC-15, R-PROC-18). It is never what the caller meant.
            raise ValueError(
                "records cannot be read from a program whose streams are folded together "
                "— start it with errors_apart"
            )
        held = Held() if sink is not None else None
        frame = _Records(held) if held is not None else _Lines(on_line)
        went_silent = False
        overran = False
        began = time.monotonic()
        # Measured from the last thing it said on *either* stream (R-PROC-7). Counted on
        # stdout alone, a provider working steadily and reporting only diagnostics goes
        # quiet by this measure while it is plainly busy, and is ended for it.
        self._heard = time.monotonic()
        # Started before anything is read, and run whatever the receiver is doing: this
        # is what keeps the streams we are not framing from filling up (R-PROC-16).
        # Each with the budget its own kind of wait deserves — see `_settle`.
        beside = []
        if self.errors_apart and self._proc.stderr is not None:
            beside.append((asyncio.ensure_future(self._drain_errors()), DRAIN_SECONDS))
        if held is not None:
            receiving = RECEIVING_SECONDS if self.receiving is None else self.receiving
            beside.append((asyncio.ensure_future(self._deliver(held, sink)), receiving))

        # Read in short spells rather than one long one, so that between them we can look
        # at whether the program is still there. Waiting on its exit instead does not
        # work: that only resolves once every pipe is closed too, and anything the
        # program left running is holding one — the exit would land hours late, or never.
        reader: asyncio.Future | None = None
        drained_by: float | None = None
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
                #
                # A deadline for the whole drain, not a timeout for each read of it.
                # Spent per read, a child that inherited the pipe and keeps writing more
                # often than the drain allows completes every read, and the loop goes
                # round again with nothing ever reaching the break below — the wait ran
                # on to the 48-hour ceiling, holding the name against a restart of that
                # work for two days. Anything talkative does it: a dev server, a language
                # server, a log being followed.
                gone = self._proc.returncode is not None
                if gone and drained_by is None:
                    drained_by = time.monotonic() + DRAIN_SECONDS
                left = None if drained_by is None else drained_by - time.monotonic()
                if left is not None and left <= 0:
                    break  # drained as long as it is worth draining
                spell = self._spell() if left is None else left
                done, _ = await asyncio.wait({reader}, timeout=spell)
                if reader in done:
                    chunk = reader.result()
                    reader = None
                    if not chunk:
                        break  # the pipe closed: nothing holds it and nothing is coming
                    self._heard = time.monotonic()  # per stretch, never summed (R-PROC-6)
                    frame.feed(chunk)
                    continue
                if gone:
                    break  # drained as far as it will drain — something it left holds the pipe
                if self.silence is not None and time.monotonic() - self._heard >= self.silence:
                    went_silent = True
                    break
        except BaseException:
            # Anything at all going wrong in here — whoever was waiting giving up, or the
            # caller's own handler raising on a line it did not like — must still take the
            # program with it. Catching only cancellation left the whole tree running with
            # nothing holding it, which is the orphan this module exists to prevent
            # (R-PROC-4, R-PROC-11).
            await self.end()
            await self._settle(beside, held, sink)
            raise
        finally:
            if reader is not None:
                reader.cancel()

        frame.finish()
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
            if not await self.gone_within(self._patience_left(began)):
                overran = self._past_ceiling(began)
                went_silent = not overran
        # Ended here, after every way of deciding it should be — not before. Deciding it
        # overran and then reaping without ending it is a wait on a process nobody asked
        # to stop, which is the very shape of wedge this is all here to prevent.
        if overran or went_silent:
            await self.end()
        await self._settle(beside, held, sink)
        return await self._became(frame.held, overran, went_silent)

    async def _settle(self, beside: list, held: Held | None, sink=None) -> None:
        """Let what is running beside the reading finish, then stop waiting for it.

        Bounded, and quiet about it — but by **two** budgets, not one, because two
        opposite things are being waited on here. Draining what a departed program left
        holding the pipe is correctly impatient: nothing more is coming and something
        else is holding it open. Letting a receiver finish is the opposite — the read
        loop is over and the program is gone, so the only thing that patience costs is
        itself. Shared, the short one won, and a receiver that was merely slow was cut
        off mid-stream while the run reported that it had finished.
        """
        if held is not None:
            held.close()
        for one, budget in beside:
            # A deadline per task rather than one across them, now that they are not the
            # same kind of wait. They run concurrently, so the cost is the longest of
            # them and not their sum.
            try:
                await asyncio.wait_for(asyncio.shield(one), budget)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                one.cancel()
            except BaseException:
                pass  # whatever it was, it is not the program's to answer for
        # Awaited after cancelling, so that what is being reported about a program is
        # settled before anyone reads it — and so a task that raised on the way out is
        # collected here rather than surfacing later as an exception nobody retrieved.
        for one, _ in beside:
            if one.cancelled() or not one.done():
                with contextlib.suppress(BaseException):
                    await one
        beside.clear()
        if held is None:
            return
        # What the receiver never got. Said rather than discarded: patience that ran out
        # is a real answer, and one nobody was being given. Handed over as a gap as well
        # as counted, so the loss lands in the receiver's own stream where it can be
        # reasoned about, rather than only in a number the caller has to think to read.
        never = held.waiting()
        if never:
            self._undelivered += never
            if sink is not None:
                await self._taken(sink, Gap(never, "never delivered"), 1)

    async def _became(self, output: str, overran: bool, went_silent: bool) -> Result:
        """Reap it, take what it left running, and say what became of it.

        In one place because everything that reads a program ends at the same four
        answers, and a second copy of this is a second copy that can come to disagree
        (R-PROC-8, R-PROC-9).
        """
        code = await self._reap()
        await self._sweep()
        lost = self._undelivered
        if overran:
            return Result(OVERRAN, code, output, lost)
        if went_silent:
            return Result(SILENT, code, output, lost)
        if self._ended:
            return Result(ENDED, code, output, lost)
        return Result(FINISHED if code == 0 else FAILED, code, output, lost)

    async def _drain_errors(self) -> None:
        """Read what it says went wrong, always, whether or not anyone wants it.

        Not optional (R-PROC-16). A pipe nobody reads fills, and a program blocked
        writing to a full pipe stops reading what we write to it — so keeping the two
        streams apart without this buys a deadlock, and one that presents half an hour
        later as a perfectly healthy program having gone quiet.
        """
        assert self._proc is not None and self._proc.stderr is not None
        frame = _Lines(self._noted)
        self._errors = frame
        while True:
            chunk = await self._proc.stderr.read(READ_BYTES)
            if not chunk:
                break
            self._heard = time.monotonic()
            frame.feed(chunk)
        frame.finish()

    def _noted(self, line: str) -> None:
        """One line of what went wrong, handed on — and never allowed to stop the drain.

        Unlike `on_line`, this one may not raise its way out. Reading this stream is not
        optional (R-PROC-16): a pipe nobody empties fills, and a program blocked writing
        to a full one stops reading what we write to it. So a caller whose own writing
        fails loses that line and nothing else, which is a far smaller loss than a
        deadlock that shows up half an hour later as a healthy program having gone quiet.
        """
        if self.on_error is None:
            return
        with contextlib.suppress(BaseException):
            self.on_error(line)

    async def _deliver(self, held: Held, sink) -> None:
        """Hand records to whoever is receiving them, away from the reading.

        Its own task, so that a receiver taking its time slows nothing but itself
        (R-PROC-17) — and so that one which fails does not reach the read loop, where
        anything raised takes the program with it.

        A record a receiver failed on is offered again before anything later is, because
        records are not independent — text arrives in pieces meant to be joined, and one
        silently skipped leaves the receiver reading a sentence with a word missing and
        no way to know. Once a receiver has been given up on, the next record gets one
        attempt rather than four: it has just demonstrated that it is broken, and
        spending the full patience on every record afterwards is how a broken receiver
        comes to hold a program's whole output hostage.
        """
        tries = DELIVERY_TRIES
        while True:
            it = await held.next()
            if it is None:
                return
            if await self._taken(sink, it, tries):
                tries = DELIVERY_TRIES
                continue
            # Given up on, and said *here* — in the receiver's own stream, in the place
            # the loss happened, before anything later reaches it. A count at the end
            # says something went; only a gap in the right place says what the records
            # around it can still be read as.
            self._undelivered += 1
            await self._taken(sink, Gap(1, "not taken"), 1)
            tries = 1

    async def _taken(self, sink, it, tries: int) -> bool:
        """Offer this to the receiver until it takes it, or the patience runs out.

        Counted once per record rather than once per attempt: `refused` answers "how many
        records could this receiver not cope with", and offering the same one four times
        does not make it four records. A loss marker is not counted at all — that a
        broken receiver also failed to take the news of its own loss says nothing the
        `undelivered` count has not already said.
        """
        counted = isinstance(it, Gap)
        waited = DELIVERY_WAIT_SECONDS
        for attempt in range(tries):
            try:
                said = sink(it)
                if inspect.isawaitable(said):
                    # Anything that can be awaited, not only what `async def` makes. A
                    # receiver that hands back a task or a future is doing the ordinary
                    # thing, and asking the narrower question drops its work on the floor
                    # without awaiting it and without a word.
                    await said
                return True
            except asyncio.CancelledError:
                # Taken off the queue and never finished with. Counted here or it is
                # accounted for nowhere: the queue no longer holds it, and the receiver
                # never saw the end of it.
                self._undelivered += 1
                raise
            except BaseException:
                # A receiver that fails is not a reason to end the program. It may still
                # be owed an answer, and whatever went wrong is the receiver's to
                # recover from — counted here so it is not simply lost.
                if not counted:
                    self._refused += 1
                    counted = True
            if attempt + 1 < tries:
                await asyncio.sleep(waited)
                waited = min(waited * 2, DELIVERY_WAIT_CAP_SECONDS)
        return False

    async def send(self, record: bytes | str) -> None:
        """Write to it while it is running (R-PROC-14).

        Written and then waited on, always. Writing alone never blocks and never raises
        — on a program that has gone it silently discards what it was given — so the
        wait is the only place the truth arrives, and skipping it would report every
        failed write as a success.

        The wait is not bounded here, and deliberately. It ends by itself when the
        program does: the machine notices the far end close and the wait is woken with
        the failure. Bounding it would mean answering a caller that a write did not
        happen while the bytes were already on their way — and there is no unwriting
        them, so the next record would land behind half of one nobody thinks was sent.
        A caller that cannot wait can stop waiting itself, and decide for itself what
        that meant.

        **One writer at a time, across both halves.** The write and the wait are one
        operation: on the oldest Python this supports, the transport holds a single
        waiter and asserts that nobody else is already there, so two records offered
        close together — two channel messages, or an answer racing a queued message,
        which is this product's ordinary case — raised `AssertionError` at the second
        caller instead of the `NotListening` it is written to handle. With assertions off
        the second waiter simply replaced the first, which is a permanent hang rather
        than an error. Serialised here, both complete, and in the order they were issued.
        """
        if self._proc is None:
            raise RuntimeError("send() before start()")
        if self._proc.stdin is None:
            raise NotListening("this program was not started to be written to")
        data = record if isinstance(record, bytes) else record.encode("utf-8")
        if not data.endswith(b"\n"):
            data += b"\n"  # a record is a record because of where it ends
        async with self._writing:
            # Asked inside the hold, not before it: whoever went first may have found the
            # far end gone, and answering the second caller on what was true while it was
            # queued would report a write that landed nowhere as one that happened.
            if not self._writable:
                raise NotListening("this program is no longer being written to")
            try:
                self._proc.stdin.write(data)
                await self._proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as gone:
                self._writable = False
                raise NotListening("it is not there to be written to") from gone

    async def close_input(self) -> None:
        """Tell it there is no more coming, and leave it to finish (R-PROC-20).

        Not the same as ending it: a program that reads its input to the end before it
        will answer at all is waiting for exactly this, and ending it instead would take
        it away mid-answer. Asking twice is allowed, and asking it of a program with
        nothing to close does nothing.

        What is already written still goes — closing lets what is buffered drain before
        the far end sees the end of it. Waiting for that is bounded and its failures
        ignored: this is a signal, not a transaction, and a program that has stopped
        reading will never finish taking what it was sent.
        """
        if self._proc is None or self._proc.stdin is None or not self._writable:
            return
        self._writable = False
        try:
            self._proc.stdin.close()
            await asyncio.wait_for(self._proc.stdin.wait_closed(), DRAIN_SECONDS)
        except (BrokenPipeError, ConnectionResetError, OSError, asyncio.TimeoutError):
            pass  # it is shut either way, and nothing here is owed an answer

    async def gone_within(self, patience: float | None) -> bool:
        """Has the program itself gone? Asked of its exit code, never waited on.

        Waiting resolves only once every pipe is closed as well, and a program rundesk
        talks to has three of them — so a child that inherited one makes a program that
        exited promptly look like one that never went at all.
        """
        if self._proc is None:
            return True
        deadline = None if patience is None else time.monotonic() + patience
        while self._proc.returncode is None:
            if deadline is not None and time.monotonic() >= deadline:
                return False
            await asyncio.sleep(GONE_SECONDS)
        return True

    def _past_ceiling(self, began: float) -> bool:
        return self.ceiling is not None and time.monotonic() - began >= self.ceiling

    def _patience_left(self, began: float) -> float | None:
        """How long there is left to wait, on whichever clock runs out first."""
        left = self.silence
        if self.ceiling is not None:
            to_ceiling = max(0.0, self.ceiling - (time.monotonic() - began))
            left = to_ceiling if left is None else min(left, to_ceiling)
        return left

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

    async def end(self) -> bool:
        """End it, and everything it started, whether or not it cooperates (R-PROC-4).

        Asked first and taken second: a brain killed outright can leave its own session
        half-written, and the polite signal costs a few seconds at shutdown.

        **True only when the group is really gone.** Returning nothing meant a shutdown
        could not tell "ended" from "asked twice and it is still there": the gateway saw
        no timeout, called itself drained, and deleted the record naming the surviving
        group — so no successor of that name would ever sweep it (R-GW-17).
        """
        if self._proc is None:
            return True  # nothing was ever started, so nothing is out there
        # The leader having gone is not the tree having gone. Returning here because the
        # one process we started has exited left everything it spawned running — and a
        # shutdown asked to end this program then reported that it had (R-PROC-5,
        # R-PROC-11). What decides whether there is anything to do is the group, and
        # signalling an empty one costs a failed system call.
        #
        # Ended, though, only if there was still something of *ours* to end: a program
        # that finished on its own and left a talkative child behind is finished, and
        # relabelling it would rewrite what actually happened to it.
        if self._proc.returncode is None:
            self._ended = True
        try:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if not self._signal_group(sig):
                    return True  # nothing left in the group to signal
                if await self._group_gone(GRACE_SECONDS):
                    return True
        except asyncio.CancelledError:
            # Out of time, but not out of obligation. A shutdown that runs out of
            # patience cancels this mid-way, having asked politely and not yet insisted —
            # and unwinding there leaves running exactly the tree it was hurrying to
            # end. The signal that cannot be ignored goes out first (R-PROC-5).
            self._signal_group(signal.SIGKILL)
            raise
        # Both signals sent and something is still there. Nothing further can be done to
        # it — but whoever asked has to be told, because what they do next is decide
        # whether anything is left for a successor to find.
        return not self._signal_group(0)

    async def _group_gone(self, patience: float) -> bool:
        """Is *everything* in the group gone — not merely the one we started?

        The one we started leaving is not the tree leaving. A child that closed the
        output it inherited and ignores the polite signal outlives its own parent, and
        returning when the parent goes reports a shutdown that ended nothing (R-PROC-5,
        R-PROC-11). So this waits on the group, not on the leader.
        """
        assert self._proc is not None
        deadline = time.monotonic() + patience
        while time.monotonic() < deadline:
            if self._proc.returncode is None:
                # Reaped here, so a zombie of our own is not mistaken for the group
                # still standing.
                try:
                    await asyncio.wait_for(asyncio.shield(self._proc.wait()), 0.2)
                except asyncio.TimeoutError:
                    continue
            if not self._signal_group(0):
                return True
            await asyncio.sleep(0.1)
        return not self._signal_group(0)

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
    cwd: str | Path | None = None,
) -> Result:
    """Start a program, read it to the end, and say what became of it."""
    program = Program(argv, env=env or {}, silence=silence, ceiling=ceiling, cwd=cwd)
    await program.start()
    return await program.wait(on_line)


async def end_all(programs: Iterable[Program]) -> bool:
    """End everything still running, at once rather than one after another.

    In turn would spend the grace period once per program, and the machine's own
    supervisor does not wait that long before taking the gateway out (R-GW-7, R-GW-8).

    Everything, not only what is alive. `alive` asks after the one process we started,
    and a program whose leader has exited while its children carry on is exactly the one
    with something left to end — skipping it is how a shutdown came to report itself
    drained with a whole process group still running.

    True only if every one of them really went. An exception counts as not gone: whatever
    it was, nothing here watched that program leave.
    """
    each = await asyncio.gather(*(p.end() for p in programs), return_exceptions=True)
    return all(went is True for went in each)


def environment(home: Path, path: str | None = None, agents: Path | None = None,
                secrets: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment a program rundesk runs is given (R-PROC-1, R-SEC-1).

    Built rather than inherited. The supervisor hands a job almost nothing, so anything
    a program needs has to be put here deliberately — and anything not put here is a
    thing rundesk has decided its programs do not see. That is the rule, and every
    addition here is a decision rather than a convenience: a gateway must not hand every
    secret it holds to every program it runs.

    **`secrets` is the owner's own environment, and does not weaken that rule.** It is the
    most deliberate addition there could be: every name in it was typed at a terminal
    through a verb that refused the ones that decide what a program *is*. What it is not is
    resolved here — the values arrive already produced, because a value fetched by somebody
    else's command is a subprocess, this function is called from three `async def` bodies,
    and the whole of `process.py` exists never to block a gateway's loop.
    """
    inherited_path = path if path is not None else os.environ.get("PATH", "")
    # Forwarded when this is itself a nested Rundesk. Recomputing from the deliberately
    # restricted environment loses a redirected data root one agent turn down.
    commands = os.environ.get("RUNDESK_SCRIPTS") or str(scripts_home())
    library = os.environ.get("RUNDESK_SKILL_LIBRARY") or str(skills_home())
    said = {
        "HOME": str(Path.home()),
        # The owner's integration commands are ordinary CLIs rather than a provider
        # feature. Putting their directory first lets every brain's own shell find the
        # same command by name while leaving the rest of its PATH intact (R-PROC-22).
        "PATH": commands + (os.pathsep + inherited_path if inherited_path else ""),
        "RUNDESK_HOME": str(home),
        "RUNDESK_SCRIPTS": commands,
        "RUNDESK_SKILL_LIBRARY": library,
        # Provider CLIs render differently when they believe a person is watching, and
        # nobody is: this is the gateway.
        "TERM": "dumb",
        # Said, because a program told nothing falls back to whatever the machine's
        # default is — and on a bare environment that is ASCII, which turns the first
        # accented character in a transcript into a crash rather than a character.
        "LANG": "en_US.UTF-8",
    }
    # **Where agents are kept, because a program rundesk starts may itself be rundesk.**
    # Left out, `rundesk schedules ava run nightly` started `rundesk ask ava` and the child
    # answered NO SUCH AGENT while the gateway that started it was running ava — the same
    # split `supervisor.describe()` records having "silently split the machine in two", one
    # level further down. Everything of an agent's is derived from this one root, so it is
    # the whole of what a program has to agree with the gateway about; the pre-agent run,
    # log and schedule directories are deliberately not passed, and are on their way out.
    #
    # Forwarded when nothing was passed rather than defaulted here. A default written a
    # third time is a third thing to keep true, and it is not needed: with the variable
    # unset, this program and the gateway resolve the same root through the same code.
    known = str(agents) if agents is not None else os.environ.get("RUNDESK_AGENTS_DIR")
    if known:
        said["RUNDESK_AGENTS_DIR"] = known
    # **What this install calls its launchd jobs**, for the same reason and with more at
    # stake. `rundesk update` from inside a turn is a supported path (R-UPD), so a program
    # started here really does ask the machine about labels — and a label belongs to the
    # *person*, not to an install, so nothing a directory can be pointed at moves it. A
    # child that resolved the default would ask after `ai.rundesk.<agent>` and boot out
    # `ai.rundesk-update`, both of them the *first* install's, from a turn the second
    # install started (R-INS-18).
    #
    # Forwarded when it was said rather than defaulted here, exactly as the root above is:
    # unset already resolves to what rundesk ships, through the same code.
    prefix = os.environ.get("RUNDESK_JOB_PREFIX")
    if prefix:
        said["RUNDESK_JOB_PREFIX"] = prefix
    return told(said, secrets)


def told(said: dict[str, str], secrets: Mapping[str, str] | None) -> dict[str, str]:
    """A built environment, plus the owner's own values — **never over one of rundesk's**.

    The rule is `name in said` rather than a list consulted here (R-SEC-14): whatever
    rundesk just decided a program is told is exactly what a value may not be called, so
    the two cannot come apart however the builder above grows — and a name added to it is
    refused from the moment it lands, with nobody re-running a command.

    `secret.checked` says the same thing at a terminal, in words, before anything is
    written, and `secret.resolve` says it again over what is already kept. This is the one
    that is true whatever is in that file, including after somebody edits it by hand.

    Apart from `environment` because a gateway adds what belongs to its own lifetime to an
    environment that was built earlier, and has to merge into *that* — one rule, asked in
    both places, rather than a second copy of it that agrees today.

    Sorted, so the same set is the same bytes every spawn and one transcript can be
    compared with another (R-PRV-16).
    """
    for name in sorted(secrets or {}):
        if name not in said:
            said[name] = secrets[name]
    return said
