"""One command group per module, and the only layer that may know argparse.

A group takes an `argparse.Namespace` and hands back an exit code. It does the work of one verb and
nothing else; it never builds a parser for another group, and it never calls a group that calls it.

May depend on `lifecycle` and `core`. Nothing in either may depend on this.
"""

from typing import Sequence


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
