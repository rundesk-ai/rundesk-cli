"""What version this copy of rundesk is."""

import argparse

from rundesk import __version__
from rundesk.commands import not_available
from rundesk.exits import OK


def cmd_version(args: argparse.Namespace) -> int:
    """Report the installed version — one line, and nothing reached outside the machine.

    Which version is *published* is a different question with a different failure mode, and it is
    not answered here yet: `--check` is registered and refuses rather than guessing. Reporting
    "up to date" because nobody could be asked is how an install stops updating itself in silence.
    """
    if args.check:
        return not_available("version", "--check")
    print(f"rundesk {__version__}")
    return OK
