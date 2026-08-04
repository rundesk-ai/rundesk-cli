"""Printing a table whose columns line up.

One function, shared so that every listing a program prints lines up the same way — a table that is
aligned on one screen and ragged on the next reads as two programs.

**Padded by what a cell looks like, not by how long it is.** A cell may arrive wearing bold or a
colour, and those are characters that draw nothing: `len()` counts them, so a column padded by it is
correct for plain text and ragged for anything styled. Wrong only on somebody's real terminal and
never in a captured test, which is the worst place for a defect to live. `style.width` is the number
this may use.

The heading is bold, and that decision is here rather than at each call site for the same reason the
alignment is: a product whose tables are bold in one command and plain in the next has two people's
tables in it. When nobody is watching — a pipe, a file, a test — `style` emits nothing at all and the
output is exactly the characters.

Layout only. **What a value says is not decided here**, because that is a choice about the words a
particular program speaks — "not yet" or "unset" or "—" for the same missing thing — and a module
that made it would be holding one program's voice under a name that promises arithmetic about column
widths.
"""

from typing import Sequence

from rundesk.utils import style


def as_table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """Print a table, columns aligned to their widest cell, two spaces between, heading in bold.

    Nothing at all when there are no rows, headings included: a heading standing over an empty table
    reads as a listing that found nothing *and told you the shape of what it did not find*, which is
    a sentence, not a table. Whoever called this says the sentence.
    """
    if not rows:
        return
    every = [list(head)] + [list(row) for row in rows]
    widths = [max(style.width(row[i]) for row in every) for i in range(len(head))]
    for at, row in enumerate(every):
        cells = [cell + " " * (wide - style.width(cell)) for cell, wide in zip(row, widths)]
        line = "  ".join(cells).rstrip()
        print(style.bold(line) if at == 0 else line)
