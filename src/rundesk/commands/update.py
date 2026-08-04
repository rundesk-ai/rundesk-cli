"""Moving this install to the newest published release.

Registered and not built. It stays a module of its own from the outset rather than sharing one with
`version` and `uninstall` the way the build being replaced did: those three ended up in a single file
named for one of them, and the two that were not it became hard to find and easy to change by
accident.
"""

import argparse

from rundesk.commands import not_available


def cmd_update(args: argparse.Namespace) -> int:
    """Not built yet. Says so, names which part was asked for, and exits non-zero."""
    return not_available("update", "--check" if args.check else "")
