"""One command group per module, and the only layer that may know argparse.

A group takes an `argparse.Namespace` and hands back an exit code. It does the work of one verb and
nothing else; it never builds a parser for another group, and it never calls a group that calls it.

What lives here is what more than one group needs and nothing below wants — today, how a table is
printed and how an operation that is not built refuses.
"""

import sys
from typing import Sequence

from rundesk.exits import NOT_AVAILABLE


def as_table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """Print a table, columns aligned to their widest cell, two spaces between.

    The one place a table is printed, so every listing in the product lines up the same way.
    """
    if not rows:
        return
    every = [list(head)] + [list(row) for row in rows]
    widths = [max(len(row[i]) for row in every) for i in range(len(head))]
    for row in every:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())


def not_available(verb: str, part: str = "") -> int:
    """Say that a registered operation is not built yet, and exit unsuccessfully.

    Names the part rather than the verb alone, so `skills grant` is told from `skills list` and an
    owner knows which half of a group they are waiting for. Everything goes to stderr: a script
    reading this command's output must not find a refusal sitting in it looking like an answer.
    """
    asked = f"{verb} {part}" if part else verb
    print(f"{asked}: NOT AVAILABLE — planned, not built yet", file=sys.stderr)
    print("        what this rundesk can do:  rundesk --help", file=sys.stderr)
    return NOT_AVAILABLE
