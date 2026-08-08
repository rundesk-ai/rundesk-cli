"""What a person sees: weight, colour, and columns that line up.

Everything about presenting a line of output to somebody watching, and nothing about deciding what
that line says.

**Nothing is emitted unless somebody is watching.** A person at a terminal reads faster when what
failed is red; a script reading the same output wants the characters and nothing else, because an
escape sequence in a captured value is not decoration but corruption — `$(rundesk backups save)`
holding `\x1b[1m2026-…` is a name that matches nothing. `NO_COLOR` set to anything at all means no,
`FORCE_COLOR` means yes even down a pipe, `TERM=dumb` means a terminal that cannot, and otherwise it
depends on whether the stream really is one.

**Decided on every call, never at import.** A module working out `ENABLED = isatty()` once, when it
was first imported, is a module nothing can drive afterwards — the value is fixed before a test sets
a variable and before a caller chooses where its output is going. The same mistake as a network call
bound in a signature, in a different costume.

**A column is padded by what a cell looks like, not by how long it is.** Once a cell can carry
escape sequences `len()` counts characters that draw nothing, so a column padded by it is right for
plain text and ragged for anything styled — and ragged only on somebody's real terminal, never in a
captured test. That is why measuring and styling live in one module: they are the same fact.

Knows nothing about rundesk.
"""

import os
import re
import sys
from typing import Optional, Sequence, TextIO

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

#: What a cell holds when there is no answer for it — an em dash, not an empty cell.
#:
#: Here because it is what a person sees and it knows nothing about this product, and in one place
#: because it was briefly in two: a renderer in `skills/` and a renderer in `commands/` both wanted
#: the same character, and the parameter passing it between them was a knob neither ever varied. A
#: blank cell reads as missing data rather than as an answer, which is the whole reason it is a
#: character at all.
NOTHING = "—"

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


def as_table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """Print a table, columns aligned to their widest cell, two spaces between, heading in bold.

    Nothing at all when there are no rows, headings included: a heading standing over an empty table
    reads as a listing that found nothing *and told you the shape of what it did not find*, which is
    a sentence, not a table. Whoever called this says the sentence.
    """
    if not rows:
        return
    every = [list(head)] + [list(row) for row in rows]
    widths = [max(width(row[i]) for row in every) for i in range(len(head))]
    for at, row in enumerate(every):
        cells = [cell + " " * (wide - width(cell)) for cell, wide in zip(row, widths)]
        line = "  ".join(cells).rstrip()
        print(bold(line) if at == 0 else line)
