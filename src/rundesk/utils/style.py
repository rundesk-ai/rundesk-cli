"""Weight and color on a line of terminal output, and the decision of whether to use any.

A command line is read by two audiences with opposite needs. A person at a terminal reads faster when
what failed is red and what a column is called stands out from what is in it. A script reading the
same output wants the characters and nothing else — and an escape sequence in a captured value is not
decoration, it is corruption: `$(rundesk backups save)` holding `\\x1b[1m2026-…` is a name that
matches nothing.

So **nothing here emits anything unless somebody is watching**, and the four ways to say so are
honoured in the order somebody would expect:

- `NO_COLOR` set to anything at all, including empty, means no. It is the established convention and
  the whole point of it is that a person sets it once and every program obeys.
- `FORCE_COLOR` means yes even down a pipe, which is what a build log that renders escapes wants.
- `TERM=dumb` means a terminal that cannot do this.
- Otherwise: colour only when the stream really is a terminal.

**Decided on every call and never at import.** A module that worked out `ENABLED = isatty()` once,
when it was first imported, is a module nothing can drive afterwards: the value is fixed before a
test sets an environment variable and before a command chooses where its output is going. It is the
same mistake as a network call bound in a signature, in a different costume.

## Why measuring belongs here too

Once a cell can carry escape sequences, `len()` stops answering how wide it looks — it counts the
bytes that draw nothing. A table padding with `len()` lines its columns up correctly for plain text
and raggedly for anything styled, which is the sort of defect that only appears on somebody's real
terminal and never in a captured test. `width` is what a person sees; `plain` is what a machine gets.

Knows nothing about rundesk.
"""

import os
import re
import sys
from typing import Optional, TextIO

#: The sequences, by the name a person uses for them. Deliberately few: this is for telling a
#: failure from a heading from an ordinary line, not for drawing.
CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
}

#: Back to whatever the terminal was doing, so nothing leaks into the next line.
RESET = "\x1b[0m"

_WORN = re.compile(r"\x1b\[[0-9;]*m")


def wanted(stream: Optional[TextIO] = None) -> bool:
    """Whether this stream should be written to with escapes at all. Answered now, never at import.

    `stream` defaults to whatever `sys.stdout` is **at the moment of the call**, which is what lets a
    caller redirect output and get the right answer — resolving it in the signature would bind the
    original stream once and answer about it for ever.
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("TERM", "") == "dumb":
        return False
    where = sys.stdout if stream is None else stream
    try:
        return bool(where.isatty())
    except (AttributeError, ValueError):
        # A stream that is closed, or is not really one. Not being able to ask is not a yes.
        return False


def paint(text: str, *how: str, stream: Optional[TextIO] = None) -> str:
    """`text` wearing these styles, or exactly `text` when nobody is watching.

    Several at once — `paint(name, "bold", "red")` — as one sequence rather than nested ones, so
    what comes out is short enough to read in a test failure.

    An unknown style is refused rather than dropped. Silently ignoring a typo would give back
    unstyled text that looks exactly like the ordinary no-terminal answer, so the mistake would only
    ever be visible to somebody who already suspected it.
    """
    unknown = [one for one in how if one not in CODES]
    if unknown:
        raise ValueError(f"{unknown[0]} is not a style — there is {', '.join(sorted(CODES))}")
    if not text or not how or not wanted(stream):
        return text
    return f"\x1b[{';'.join(CODES[one] for one in how)}m{text}{RESET}"


def bold(text: str, stream: Optional[TextIO] = None) -> str:
    """`text` in bold, for the word on a line that is the answer."""
    return paint(text, "bold", stream=stream)


def dim(text: str, stream: Optional[TextIO] = None) -> str:
    """`text` dimmed, for what stands beside the answer rather than being it."""
    return paint(text, "dim", stream=stream)


def red(text: str, stream: Optional[TextIO] = None) -> str:
    """`text` in red, for something that did not work."""
    return paint(text, "red", stream=stream)


def green(text: str, stream: Optional[TextIO] = None) -> str:
    """`text` in green, for something that did."""
    return paint(text, "green", stream=stream)


def yellow(text: str, stream: Optional[TextIO] = None) -> str:
    """`text` in yellow, for something that worked and is worth a second look."""
    return paint(text, "yellow", stream=stream)


def plain(text: str) -> str:
    """`text` with every escape sequence taken out — what a machine reading this would get."""
    return _WORN.sub("", text)


def width(text: str) -> int:
    """How wide `text` looks, which is not how long it is once it is wearing anything.

    The one number a layout may use. `len()` counts the characters that draw nothing, so a column
    padded by it is correct for plain text and wrong for everything else — and wrong only on a real
    terminal, never in a captured test.
    """
    return len(plain(text))
