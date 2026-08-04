"""Changing what this install is configured with.

The flags are **generated from the configuration itself** rather than written out here, so a value a
release starts offering is settable the day it lands and there is no second list to fall behind the
first. `--backup-retention 30` sets `backup_retention`; the mapping is that mechanical on purpose.

With nothing to set it shows what the install is configured with, which is the question somebody
usually has just before they change something.
"""

import argparse
import sys

from rundesk.commands import Subcommands, as_table, as_written
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK


def as_flag(key: str) -> str:
    """The command-line flag for a configured value: `backup_retention` -> `--backup-retention`."""
    return "--" + key.replace("_", "-")


def register(sub: Subcommands) -> None:
    """Put `configure` on the parser, with one flag per value that may be stated."""
    said = sub.add_parser("configure", help="change what this install is configured with")
    for key in config.settable():
        said.add_argument(as_flag(key), dest=key, metavar="<value>", default=None,
                          help=f"{config.WANTED.get(key, 'a value')} (now: {config.INITIAL[key]})")


def cmd_configure(args: argparse.Namespace) -> int:
    """Set what was named and leave everything else alone; with nothing named, show it all."""
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    asked = {key: getattr(args, key) for key in config.settable()
             if getattr(args, key, None) is not None}
    if not asked:
        return _shown()

    try:
        settled = {key: config.understood(key, said) for key, said in asked.items()}
    except config.Refused as why:
        # Nothing is written until every value asked for is understood, so a command naming two
        # settings and getting one wrong changes neither. Half-applied configuration is worse than
        # none: it leaves an install in a state nobody typed.
        return _failed(str(why))

    # And written as one change for the same reason. Set one at a time, the guarantee above holds
    # only against a value that was typed wrongly — an interruption partway through the writing
    # would still leave two settings changed and the third not, which is the state nobody typed
    # arrived at by a different road.
    try:
        config.stated_all(settled, paths.data())
    except (config.Unreadable, config.Refused, config.Stuck) as why:
        return _failed(str(why))

    for key in sorted(settled):
        print(f"{key} is now {as_written(settled[key])}")
    return OK


def _shown() -> int:
    """Print what the install is configured with, and what may be changed."""
    try:
        settled = config.read(paths.data())
    except config.Unreadable as why:
        return _failed(str(why))

    as_table(("SETTING", "IS", "SET IT WITH"),
             [(key, as_written(settled[key]), f"rundesk configure {as_flag(key)} <value>")
              for key in config.settable()])
    return OK


def _failed(why: str) -> int:
    print(f"configure: FAILED — {why}", file=sys.stderr)
    print("        nothing was changed", file=sys.stderr)
    return FAILED
