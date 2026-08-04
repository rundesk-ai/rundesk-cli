"""What version this copy of rundesk is, and whether a newer one has been published.

One question with one answer, so it takes no flags: it reports the version and checks. The check is
not optional because the whole reason anybody asks a program its version is to find out whether it is
the one they should be running.
"""

import argparse
import sys

from rundesk import __version__
from rundesk.exits import OK
from rundesk.lifecycle import release


def cmd_version(_args: argparse.Namespace, asking=None) -> int:
    """Print the installed version, then where it stands against what is published.

    `asking` is how the published version is looked up, so a test drives every state of this with no
    network. Resolved here rather than bound in the signature — a default argument is decided once,
    when the function is defined, and nothing can reach past it afterwards.

    **Exits `0` even when the check could not be made.** The question asked was "what version is
    this", and that was answered from the machine itself. What must never happen is the *other*
    thing: being unable to ask is never printed as being up to date, so the line says UNKNOWN and
    goes to stderr where it cannot be mistaken for the answer.
    """
    print(f"rundesk {__version__}")

    line, _published, could_ask = release.standing(__version__, asking)
    print(f"        {line}", file=sys.stdout if could_ask else sys.stderr)
    return OK
