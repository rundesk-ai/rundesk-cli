"""What goes out through a channel: cut to what the platform will take, and vetted if it is a file.

**The cutting is here rather than in each adapter, and that is the whole reason this module
exists.** The build this replaces held the limit in the adapter — 1900 in Discord's, 3800 in
Slack's — and the two then drifted: Slack found that cutting at the last newline could put a single
completion line in a message of its own, carrying the mention, and fixed it. Discord still has the
original rule. One copy of a rule cannot drift from itself.

Three things it gets right that a naive split does not:

**A cut that lands too far back is not worth taking.** Cutting at the last newline before the limit
is right when that newline is near it and wrong when it is near the start — a paragraph of ten
thousand characters ending in a short line would be sent as one short message and one enormous one.
Past `RATHER_THAN_A_STUB` of the way back, the cut is taken at the limit instead.

**A fence that is open at the cut is closed and opened again — and room is kept for both.** A code
block split across two messages renders as one broken block and then a page of unformatted text, and
the reader cannot tell which. Reopening one costs four characters at the start of the next piece and
closing one costs four at the end of this one, and only the first of those was ever paid for: a
piece carrying an open block came back four characters past the limit, the adapter refused it
outright as rundesk having failed to split, and the delivery was dropped with nothing to retry.

**A message is never empty.** A platform refuses one, and the refusal arrives as a failed delivery
for something nobody needed sent.

## And what a delivery carries besides words

`carried` is the second of the three checks a file passes on its way out — the brain names one,
**this** contains it and fingerprints it through `channels.files.approved`, and the adapter re-opens
it with `O_NOFOLLOW` and refuses on any mismatch. The third is not belt-and-braces: between the
approval and the send a concurrent turn can replace the file, or a directory above it, and only a
re-open sees that.

May depend on `agents`, `core` and `utils`.
"""

from typing import List, NamedTuple, Optional, Sequence

from rundesk.channels import files, kept

#: What a fenced block is opened and closed with, and what one costs at a cut: the fence itself and
#: the newline that has to stand beside it, on whichever end of a piece it lands.
FENCE = "```"
FENCE_ROOM = len(FENCE) + 1

#: How far back a line boundary may be and still be worth cutting at, as a fraction of the limit.
#: Nearer the start than this and the cut is taken at the limit: the alternative is one very short
#: message followed by one very long one, which is how a completion line came to be posted alone.
RATHER_THAN_A_STUB = 0.5

#: What a platform is assumed to take when its adapter would not say. Small enough to be safe
#: everywhere rather than a guess at any particular platform's real limit.
WHEN_UNSAID = 2000


class Telling(NamedTuple):
    """One notice, and where it goes. `None` from `notice` when this agent tells nobody anything."""

    kind: str
    place: str
    pieces: List[str]


class Carrying(NamedTuple):
    """What a delivery may take with it, and what it may not.

    Both halves, because they go to different places: `files` crosses the seam and `refused` is a
    line in the agent's own log. A caller handed only the first would report a delivery as whole
    when part of what it was asked to send was quietly left behind — which is the failure this
    product is built around not committing.
    """

    files: List["files.Sending"]
    refused: List[str]


def notice(agent: str, saying: str, at_most: int = WHEN_UNSAID) -> Optional[Telling]:
    """What to send where, for something nobody asked for. `None` when no channel is the told one.

    **`None` is an ordinary answer.** An agent with no notified channel is an agent that says
    nothing, which is what somebody who configured none asked for — so a caller writes nothing and
    reports nothing, rather than treating a quiet install as a failure.
    """
    told = kept.told(agent)
    if told is None or not told.get("notify_place"):
        return None
    return Telling(str(told["kind"]), str(told["notify_place"]), split(saying, at_most))


def split(said: str, at_most: int = WHEN_UNSAID) -> List[str]:
    """One piece of text as the several messages a platform will actually accept.

    Whole lines wherever a line boundary is near enough to the limit to be worth taking, and at the
    limit when it is not. A fence left open at a cut is closed and opened again on the next piece.

    Hands back every piece it takes to say the whole of it, and **none at all** for text that is
    empty or only whitespace — never a piece that is itself empty, which is what a platform actually
    refuses, arriving as a failed delivery for something nobody needed sent.
    """
    if at_most < 1:
        raise ValueError("a message has to be allowed at least one character")
    if not said.strip():
        return []
    pieces: List[str] = []
    rest = said
    open_fence = False
    # **The last piece wears a reopening fence too, and the condition is where that is paid for.**
    # Measured before it was: a tail exactly `at_most` long, following an open block, came back four
    # characters over — the same overshoot as the pieces above it, arrived at from the other end.
    while len(rest) + _reopening(open_fence) > at_most:
        taking = _how_much(rest, at_most, open_fence)
        piece = rest[:taking].rstrip()
        rest = rest[taking:].lstrip("\n")
        if not piece:
            continue                       # a cut that landed on nothing but the whitespace at one
            # end of a line is not a message, and a platform refuses an empty one.
        piece = _reopened(piece, open_fence)
        # Asked again of the piece as it now stands rather than taken from `_how_much`: a shorter cut
        # may not reach the fence that made it shorter, and closing a block that was never opened in
        # this piece would put a stray fence in front of a reader.
        open_fence = _fence_left_open(piece)
        if open_fence:
            piece = f"{piece}\n{FENCE}"
        pieces.append(piece)
    last = rest.rstrip()
    if last:
        pieces.append(_reopened(last, open_fence))
    return pieces or [said[:at_most]]


def carried(agent: str, named: Sequence[str]) -> "Carrying":
    """What of these files a delivery may actually take with it, and a sentence for each it may not.

    **Vetted here and verified again by the adapter, and the second check is not a duplicate of the
    first.** `files.approved` walks every component with `O_NOFOLLOW` and reports the size and digest
    of the descriptor it opened; the adapter re-opens the same way and refuses on any mismatch.
    Between those two moments a concurrent turn can replace the file or a directory above it, and
    nothing but a re-open sees that.

    **A refusal is an answer and never an exception**, because a delivery carrying four files of
    which one may not be sent is three files that still have to arrive, plus a line somebody reads.
    Bounded at `files.PER_MESSAGE` and de-duplicated by path: one file named twice is one file, and a
    platform would otherwise post it twice.
    """
    taking: List[files.Sending] = []
    refused: List[str] = []
    seen = set()
    for one in named:
        if one in seen:
            continue
        seen.add(one)
        if len(taking) >= files.PER_MESSAGE:
            refused.append(f"only the first {files.PER_MESSAGE} files of a delivery are sent, so "
                           f"{one} was left behind")
            continue
        try:
            taking.append(files.approved(agent, one))
        except (files.Refused, OSError) as why:
            refused.append(str(why))
    return Carrying(taking, refused)


def _how_much(said: str, at_most: int, open_fence: bool) -> int:
    """How much of what is left the next piece takes, with room kept for the fences it will wear.

    **Cut twice rather than guessed at.** Whether a piece leaves a block open is only knowable once
    it has been cut, so the first cut asks the question and the second one pays for the answer.
    Reserving for a closing fence unconditionally is the alternative and is wrong for the ordinary
    case: it would make every piece of ordinary prose four characters short of the limit for a fence
    that is never written.

    Never below one character, so that a limit smaller than a fence still makes progress instead of
    cutting nothing for ever.
    """
    room = max(1, at_most - _reopening(open_fence))
    taking = _where_to_cut(said, room)
    if not _fence_left_open(_reopened(said[:taking].rstrip(), open_fence)):
        return taking
    return _where_to_cut(said, max(1, room - FENCE_ROOM))


def _reopening(open_fence: bool) -> int:
    """How much room the fence reopening a block costs at the start of a piece, or none."""
    return FENCE_ROOM if open_fence else 0


def _reopened(said: str, open_fence: bool) -> str:
    """A piece with the block it continues opened again, or exactly as it stands."""
    return f"{FENCE}\n{said}" if open_fence else said


def _where_to_cut(said: str, at_most: int) -> int:
    """How much of this to take, preferring a line boundary but never a nearly-empty piece."""
    boundary = said.rfind("\n", 0, at_most + 1)
    if boundary >= int(at_most * RATHER_THAN_A_STUB):
        return boundary
    return at_most


def _fence_left_open(said: str) -> bool:
    """Whether a fenced block was opened in this piece and not closed again.

    Counted rather than parsed. A fence is three backticks at the start of a line, and an odd number
    of them means the block is still open — which is all the next piece needs to know.
    """
    return sum(1 for line in said.splitlines() if line.startswith(FENCE)) % 2 == 1
