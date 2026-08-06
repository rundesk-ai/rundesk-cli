"""Reading a program's output one whole line at a time, and saying so where a line is lost.

A program that talks to this one sends a record per line, and two things about that are easy to get
wrong in ways that only appear months later on somebody else's machine.

**A read has to be bounded, and `for line in stream` is not.** That form is `readline()` with no
size, which pulls until it meets a newline or the end of the stream — so a check on how long the
line is happens only once the whole of it is already held. Measured on a real gateway: an adapter
that wrote 300 MB with no newline in it took the hosting process from 17 MB to 735 MB before
anything refused it, and the kernel ended the process outright, which logs nothing anywhere.
`readline(at_most + 1)` is what makes "bounded" true, and the `+ 1` is what lets a caller tell a
line that *fitted* from one that was cut off: a full read with no newline on the end is the second.

**Half a record is not a smaller record, it is a corrupt one.** Handing on the first megabyte of a
line and then the rest of it as though they were two lines turns a loud failure into a wrong answer,
and nothing downstream can tell that apart from the program talking nonsense. So an over-long line
is read to its end, discarded whole, and reported as a `Gap` in the place it happened — which is the
only report that says what the lines around it can still be read as.

**What this bounds is characters, not bytes**, because the streams it is given are already decoded —
`utils.programs.talking` opens them in text mode with `errors="replace"` so that one invalid byte is
a bad character rather than an exception raised inside the read, past every guard a caller can put
around a record. A character may be several bytes, so the true ceiling on what is held at once is a
small multiple of `at_most`. That is still a ceiling, which is the whole point; it is written down
here because "a megabyte" would otherwise read as a promise about memory that it is not.

Knows nothing about rundesk, and nothing about what a line means.
"""

from typing import IO, Callable, Iterator, NamedTuple, Optional, Tuple, Union

#: A line that would not fit, read to its end and kept nowhere.
TOO_LONG = "too long"

#: The stream ended in the middle of a line. Not a line — it is the beginning of one the program did
#: not finish, and passed on it would be indistinguishable from a whole one. Nothing downstream could
#: then tell a forgotten terminator from a program killed mid-sentence.
UNTERMINATED = "unterminated"


class Gap(NamedTuple):
    """Lines that were lost, said where they were lost.

    Handed to the reader in the position the loss happened rather than counted up at the end. A
    count says something went missing; a gap says **where**, and where is what decides whether what
    surrounds it can still be made sense of — lines are not independent, and text arrives in pieces
    meant to be joined.

    `reason` is one of the two words above when this came from `read`. Anything further down the chain
    that loses something of its own — a queue that overflowed, a receiver that would not take one —
    makes its own `Gap` with its own word, so whoever is reading a stream of these never has to know
    which layer a loss came from in order to report it honestly.
    """

    lost_count: int
    reason: str


def read(stream: IO[str], at_most: int,
         noticing: Optional[Callable[[str], None]] = None) -> Iterator[Union[str, Gap]]:
    """Every whole line the stream has, and a `Gap` wherever one could not be given whole.

    Lines keep their newline, exactly as `readline` gives them, so a caller writing them somewhere
    does not have to put one back. The last line of a stream that ended without one is not yielded
    at all — it is an `UNTERMINATED` gap, because a partial line handed on as a whole one is the
    corrupt-record failure this module exists to prevent.

    **Consecutive losses of the same kind are folded into one gap.** A program that has stopped
    ending its lines produces one of these per read, and a caller that logged each would be writing
    the log the loss was meant to be visible in. Folding here rather than in each caller means the
    say-it-once state lives in one place instead of in every reader that has to remember to be
    careful.

    **`noticing` is called the moment a loss is detected, before the rest of that line is read
    past.** A gap can only be yielded between lines, so a program writing one endless line yields
    nothing at all — bounded in memory, and completely silent about why nothing is arriving. That is
    the state somebody is most likely to be staring at, so a caller that wants to say so while it is
    still happening is handed the reason as it happens rather than after it stops. Anything it
    raises is the caller's own to answer for and is not caught here.

    Ends when the stream does. It never raises for anything the *program* did; a stream that fails at
    the operating-system level still raises, because that is the caller's process to answer for and
    not something to be quietly turned into an empty result.
    """
    pending = None                              # a Gap still being accumulated, or None
    while True:
        said = stream.readline(at_most + 1)
        if not said:
            break
        if len(said) > at_most and not said.endswith("\n"):
            # It did not fit. Said *now* — reading past the rest of it may never return, and a
            # caller that only heard about this afterwards would hear nothing at all.
            if noticing is not None:
                noticing(TOO_LONG)
            # Read past the rest so the framing survives: one enormous line must not cost every
            # line after it.
            _discarded(stream, at_most)
            finished, pending = _one_more_lost(pending, TOO_LONG)
            if finished is not None:
                yield finished
            continue
        if not said.endswith("\n"):
            # The stream ended mid-line. Nothing more is coming, so this is the last thing to say.
            if noticing is not None:
                noticing(UNTERMINATED)
            finished, pending = _one_more_lost(pending, UNTERMINATED)
            if finished is not None:
                yield finished
            break
        if pending is not None:
            yield pending
            pending = None
        yield said
    if pending is not None:
        yield pending


def _one_more_lost(pending: Optional[Gap], reason: str) -> Tuple[Optional[Gap], Gap]:
    """One more line lost: the gap that is now finished, and the one still being accumulated.

    Two kinds never merge. `TOO_LONG` and `UNTERMINATED` are different news, and a reader shown one
    count under one word would be told the wrong thing about half of it.

    **A gap of the other kind is handed back to be said, never replaced.** Returning only the new
    gap is what an earlier version of this did, and it dropped the finished one on the floor — so a
    program that wrote a line too long and *then* died mid-sentence reported the second loss and not
    the first. Losing the report of a loss is the one failure this whole module is written against,
    which is why this hands back a pair rather than a single gap.
    """
    if pending is None:
        return None, Gap(1, reason)
    if pending.reason == reason:
        return None, Gap(pending.lost_count + 1, reason)
    return pending, Gap(1, reason)


def _discarded(stream: IO[str], at_most: int) -> None:
    """Read what is left of a line that was already too long, and keep none of it.

    Bounded on every call, for the same reason the caller is: what is being skipped past is by
    definition a program writing without ever ending a line, so anything here that read *to* the
    newline in one go would be the same unbounded read under another name.
    """
    while True:
        more = stream.readline(at_most + 1)
        if not more or more.endswith("\n"):
            return
