"""One command group per module, and the only layer that may know argparse.

A group takes an `argparse.Namespace` and hands back an exit code. It does the work of one verb and
nothing else; it never builds a parser for another group, and it never calls a group that calls it.

May depend on `lifecycle` and `core`. Nothing in either may depend on this.
"""

import argparse
from typing import Any, Sequence

#: What `add_subparsers()` hands back, and what a verb is given to register itself on.
#:
#: argparse offers no public name for it, so the private one is named **here, once**, rather than
#: spelled out at each verb — and `cli.offered` reads the same private shape to walk the surface. If
#: a future Python renames it, this import fails loudly at start-up, which is the failure worth
#: having: the alternative is a walk that quietly finds no verbs and a suite that proves nothing.
Subcommands = argparse._SubParsersAction


def as_written(value: Any) -> str:
    """One configured value as a person reads it, and as they would type it back.

    The one place that decision is made, so `status` and `configure` cannot come to disagree about
    how the same install reads — which is the kind of difference nobody notices and everybody
    distrusts once they do. A value nothing has set yet says so rather than printing `None`, which
    is Python's word for it and not anybody else's.
    """
    if value is None:
        return "not yet"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


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
