"""Taking rundesk off this machine.

Registered and not built. Of everything waiting to be rebuilt this is the one that must never report
a success it did not earn in the other direction either: a removal that did not happen is a failure,
and a removal that happened is irreversible. It gets its own module and its own contract.
"""

import argparse

from rundesk.commands import not_available


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Not built yet. Says so, names which part was asked for, and exits non-zero."""
    return not_available("uninstall", "--purge" if args.purge else "")
