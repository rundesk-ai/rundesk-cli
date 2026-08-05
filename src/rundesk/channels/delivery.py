"""What goes out through a channel, cut to what the platform on the other end will take.

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

**A fence that is open at the cut is closed and opened again.** A code block split across two
messages renders as one broken block and then a page of unformatted text, and the reader cannot tell
which. Closing and reopening costs a few characters and is the difference between two readable
messages and two wrong ones.

**A message is never empty.** A platform refuses one, and the refusal arrives as a failed delivery
for something nobody needed sent.

May depend on `agents`, `core` and `utils`.
"""

from typing import List, NamedTuple, Optional

from rundesk.channels import kept

#: What a fenced block is opened and closed with, and how much room reopening one needs.
FENCE = "```"

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
    while len(rest) > at_most:
        room = at_most - (len(FENCE) + 1 if open_fence else 0)
        cut = _where_to_cut(rest, room)
        piece = rest[:cut].rstrip()
        if open_fence:
            piece = f"{FENCE}\n{piece}"
        open_fence = _fence_left_open(piece)
        if open_fence:
            piece = f"{piece}\n{FENCE}"
        pieces.append(piece)
        rest = rest[cut:].lstrip("\n")
    last = rest.rstrip()
    if last:
        pieces.append(f"{FENCE}\n{last}" if open_fence else last)
    return pieces or [said[:at_most]]


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
