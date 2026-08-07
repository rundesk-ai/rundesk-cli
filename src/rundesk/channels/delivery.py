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

import re
from typing import List, NamedTuple, Optional, Sequence, Tuple

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


def stats(provider: str = "", input_tokens: Optional[int] = None,
          output_tokens: Optional[int] = None, cached_tokens: Optional[int] = None,
          context_tokens: Optional[int] = None, elapsed: Optional[float] = None) -> str:
    """What a turn cost, as the one line that stands above the answer. `""` when nothing is known.

    **Rendered here and rendered once**, for every platform. What it is *made to look like* is the
    adapter's — Discord has a subtext register and puts it there, another surface may have nothing of
    the kind — but which quantities a person is shown, and in what words, is a decision this product
    makes rather than one each surface makes again (R-DIS-17, R-DIS-33, R-CH-28).

    **The provider leads it** (R-DIS-33), because which brain answered is the first thing somebody
    wants when an answer reads oddly, and it is the one term that is never a number.

    **Which quantities are shown depends on whether the brain said how big the conversation got**
    (R-DIS-29). A footer is read to decide one thing — whether to start a fresh conversation — and
    none of the billed quantities answers it: fresh input is a handful of tokens on any warm turn,
    and nobody adds three numbers in their head. So a brain that reports a context size leads with
    that and keeps `output` beside it as the only other thing the turn itself did; a brain that
    cannot tell gets the useful cost summary instead. Both are the same rule, and it is why the
    same agent shows two different-looking lines on two different brains.

    **Cache writes are never shown** (R-DIS-17). They stay in the turn's own record, where the whole
    account is; a fourth number here buys nothing a reader acts on.

    **Absent and zero are different answers**, and every quantity is optional for that reason: a
    brain that could not tell says nothing about it rather than reporting a measured zero.
    """
    parts = [provider] if provider else []
    slots = ((("session", context_tokens), ("output", output_tokens))
             if isinstance(context_tokens, int)
             else (("input", input_tokens), ("output", output_tokens),
                   ("cached", cached_tokens)))
    parts.extend(f"{_amount(one)} {what}" for what, one in slots if isinstance(one, int))
    if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool):
        parts.append(f"{_duration(elapsed)} elapsed")
    return " · ".join(parts)


def _amount(tokens: int) -> str:
    """A count somebody can read, **without rounding it into a lie.**

    Everything was shown in thousands once, so a turn that answered in thirteen tokens reported
    `0k output` — which is a measurement, stated plainly, and wrong. Small numbers are shown as
    themselves, and only what is genuinely in thousands is abbreviated.

    A cache read is counted once per request, so a turn that made forty of them reported
    `15425k cached` — a unit nobody carries that far, and one a reader has to divide in their head
    before it means anything. Thousands stop at a thousand of them. Millions keep a decimal, because
    rounding one away is half a million tokens, which is a real amount of somebody's money.
    """
    if tokens < 1000:
        return str(tokens)
    if tokens < 10000:
        return f"{tokens / 1000:.1f}k".replace(".0k", "k")
    if round(tokens / 1000) < 1000:
        return f"{round(tokens / 1000)}k"
    return f"{tokens / 1000000:.1f}M".replace(".0M", "M")


def _duration(seconds: float) -> str:
    """How long a turn took, compact enough to sit in a line of small print beside four counts."""
    whole = max(0, int(seconds))
    if whole < 60:
        return f"{whole}s"
    if whole < 3600:
        return f"{whole // 60}m"
    return f"{whole // 3600}h"


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


#: How a brain says *send this file*: an ordinary Markdown link whose destination is an absolute
#: local path. `[the chart](/Users/…/home/chart.png)` and `[it](</Users/…/a file.png>)` both count.
#:
#: **A convention rather than a record, because no brain has an intent to report.** All three shipped
#: adapters refuse to emit a `file` record and each says why in its own words: a brain's stream says
#: which files it *touched* and never which one it made for the person who asked. So the intent is
#: taken from the one place it genuinely exists — the answer the brain chose to write. The build this
#: replaces settled on exactly this and for exactly this reason (R-CH-31).
#:
#: A link to `http://…` or to a relative path matches nothing here, which is what makes an ordinary
#: link in an answer stay an ordinary link. `//` is excluded too: that is a protocol-relative URL and
#: not a path anybody meant.
#:
#: The label may not itself hold brackets. Balanced-bracket parsing is what the previous build spent
#: ninety lines on, and what it bought was a label like `[see [1] here]` — against a rule that then
#: has to be re-derived by anybody reading it. A link that does not match is left in the prose it
#: stands in, which is visible and harmless, where a mis-parse would silently send the wrong file.
#: One level of balanced parentheses is allowed in an unwrapped path, because `Copy (1).pdf` is what
#: an operating system names a duplicate and a rule that stopped at the first `)` did not merely fail
#: to match — it captured half a path and left the other half as loose text in the answer.
A_LOCAL_LINK = re.compile(
    r"\[([^\[\]]*)\]\(<(/[^>\n\r]+)>\)"
    r"|\[([^\[\]]*)\]\((/(?:[^()\s]|\([^()\s]*\))*)\)")


def declared_in(said: str) -> Tuple[str, List[str]]:
    """What the brain wrote with its file links taken out, and the paths they named.

    **The path never reaches the room.** What is left behind is the label alone, because the
    destination is a location on the owner's own machine — the build this replaces got this right and
    said so: left in, an answer posts somebody's home directory into a chat room, and a reader
    cannot act on it anyway.

    Nothing here decides whether a file may actually be sent. That is `carried`, one call later,
    which contains it to the agent's own roots and fingerprints it — so a brain naming
    `/etc/passwd` produces a refusal and a sentence, never a delivery.

    **Order is kept**, because a brain that made three charts described them in an order and a
    platform hangs attachments under the message in the order they were given.

    **Nothing inside a fenced block counts.** A brain that has been taught this convention will
    sooner or later show somebody the convention — in an example, in a quoted past exchange, in
    documentation it wrote — and a link inside a fence is somebody being *shown* the syntax rather
    than asking for a file. Read as live it did two wrong things at once: the example was mangled
    into unformatted prose, and if the path happened to name a real file the agent could reach, that
    file was posted to somebody who never asked for it.

    An unclosed fence makes everything after it fenced, which is the safe direction to be wrong in:
    an unsent file is a sentence somebody can act on and an unasked-for one is not.
    """
    paths: List[str] = []

    def taken(found: "re.Match") -> str:
        label, at = (found.group(1), found.group(2)) if found.group(2) else (found.group(3),
                                                                            found.group(4))
        if at.startswith("//"):
            return found.group(0)
        paths.append(at)
        return label

    # Odd segments stand between fences. Rejoined with the fences they were split on, so what is
    # inside one comes back exactly as it was written.
    parts = said.split(FENCE)
    return FENCE.join(part if nth % 2 else A_LOCAL_LINK.sub(taken, part)
                      for nth, part in enumerate(parts)), paths


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
