"""One command group per module, and the only layer that may know argparse.

A group takes an `argparse.Namespace` and hands back an exit code. It does the work of one verb and
nothing else; it never builds a parser for another group, and it never calls a group that calls it.

May depend on `lifecycle`, `core` and `utils`. Nothing in any of them may depend on this.

Columns are laid out by `utils.terminal`, so every listing in the product lines up the same way. What a
value *says* is `as_written` below, and it is here rather than there on purpose: aligning columns is
something any program does, and choosing the words this one speaks is not.
"""

import argparse
import sys
from typing import Any

from rundesk.exits import FAILED

#: What `add_subparsers()` hands back, and what a verb is given to register itself on.
#:
#: argparse offers no public name for it, so the private one is named **here, once**, rather than
#: spelled out at each verb — and `cli.offered` reads the same private shape to walk the surface. If
#: a future Python renames it, this import fails loudly at start-up, which is the failure worth
#: having: the alternative is a walk that quietly finds no verbs and a suite that proves nothing.
#:
#: Stays here rather than in `utils` because it is argparse's, and argparse is this layer's alone.
Subcommands = argparse._SubParsersAction


def failed(saying: str, *and_so: str) -> int:
    """Say what went wrong on stderr, then what it leaves, indented under it. Returns `FAILED`.

    The mechanics only — the stream, the indent, the exit code — because that is the part every verb
    repeats and the part nobody should be able to get subtly different from everybody else. A failure
    on stdout is a failure a script reads as output.

    **`saying` is the whole first line, and the caller words it.** Not "the reason, and this adds the
    prefix": `update` says `NOT APPLIED` where the others say `FAILED`, and that is deliberate — an
    update that correctly declined to move is not a command that broke, and flattening the two into
    one word would be this function changing what commands mean rather than how they print.

    `and_so` is what the failure leaves behind, which is the half a person actually needs: knowing a
    restore failed is worth much less than knowing whether anything was replaced. Every caller here
    passes it, and a failure that says only what went wrong is one worth looking at twice.
    """
    print(saying, file=sys.stderr)
    for line in and_so:
        print(f"        {line}", file=sys.stderr)
    return FAILED


def the_reason(said: str) -> str:
    """One sentence out of whatever a subprocess wrote to its error stream.

    Two things run in an interpreter of their own here — the release settling the install it has
    just landed in, and the placed command being asked to prove it answers — and whatever they
    write is the only account of what went wrong. Forwarded whole it reads badly in both
    directions: a settle that failed already says `update: NOT APPLIED — …`, so wrapping that in
    `install: FAILED — …` says the same thing twice under two names, and a genuine crash arrives
    as a stack trace with internal paths in it, printed verbatim to whoever ran the installer.

    So: the last thing said, with any `verb: STATUS — ` prefix taken off. On a traceback the last
    line is the exception's own message, which is the one line of it worth reading; on an ordinary
    worded failure it is the sentence that was already written for a person.
    """
    lines = [one.rstrip() for one in said.splitlines() if one.strip()]
    if not lines:
        return ""
    last = lines[-1].strip()
    return last.split(" — ", 1)[1] if " — " in last else last


def as_written(value: Any) -> str:
    """One configured value as a person reads it, and as they would type it back.

    The one place that decision is made, so `status` and `configure` cannot come to disagree about
    how the same install reads — which is the kind of difference nobody notices and everybody
    distrusts once they do. A value nothing has set yet says so rather than printing `None`, which
    is Python's word for it and not anybody else's.

    **Here rather than in `utils`, though it looks like a formatter.** Choosing "not yet" over
    "unset" over "—" is choosing the words this product speaks, and a program's voice is not common
    functionality another project could pick up unchanged. `utils.terminal` lays the columns out; this
    decides what is in them.
    """
    if value is None:
        return "not yet"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)
