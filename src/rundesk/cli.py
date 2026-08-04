"""The command surface: the parser, the dispatch, and nothing else.

Every verb registered here is built. There is no table of operations that are listed and do not work
— a verb rundesk cannot perform is a verb rundesk does not have, and the command describes exactly
what it can do.

The one rule: a verb's parser is built beside the verb, in a small function. The build this replaces
had one `build_parser()` of about 680 lines registering thirty verbs inline, which is where a surface
goes to stop being readable.
"""

import argparse
import sys
from typing import List, Optional

from rundesk.commands.configure import cmd_configure, register as register_configure
from rundesk.commands.install import cmd_install
from rundesk.commands.status import cmd_status
from rundesk.commands.uninstall import cmd_uninstall
from rundesk.commands.update import cmd_update
from rundesk.commands.version import cmd_version
from rundesk.exits import OK

EPILOG = """\
examples:
  rundesk status                how rundesk is on this machine
  rundesk configure             what this install is configured with
  rundesk version               what version this is, and whether it is out of date
  rundesk update                move to the newest published release
  rundesk uninstall --confirm   remove rundesk, keeping what it kept for you

Everywhere rundesk keeps something is below one directory, and RUNDESK_HOME
says which. It defaults to ~/.rundesk.
"""


def build_parser() -> argparse.ArgumentParser:
    """The whole command surface, built once.

    Nothing reads a list of verbs from anywhere but this parser — a list written twice is a list that
    disagrees with itself.
    """
    parser = argparse.ArgumentParser(
        prog="rundesk",
        description="A lightweight, provider-agnostic multi-agent gateway.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    _register_status(sub)
    _register_version(sub)
    register_configure(sub)
    _register_install(sub)
    _register_update(sub)
    _register_uninstall(sub)
    return parser


def _register_status(sub) -> None:
    sub.add_parser("status", help="how rundesk itself is on this machine")


def _register_version(sub) -> None:
    sub.add_parser("version", help="what version this install is, and whether it is out of date")


def _register_install(sub) -> None:
    put = sub.add_parser("install", help="install rundesk into RUNDESK_HOME")
    put.add_argument("--source", metavar="<dir>", default=None,
                     help="the tree to install from (default: the one this command is running from)")
    put.add_argument("--bin-dir", metavar="<dir>", default=None,
                     help="where to put the rundesk command on your PATH")


def _register_update(sub) -> None:
    sub.add_parser("update", help="move to the newest published release, or say it is up to date")


def _register_uninstall(sub) -> None:
    gone = sub.add_parser("uninstall", help="remove rundesk from this machine")
    gone.add_argument("--confirm", action="store_true",
                      help="required — removal does nothing without it")
    gone.add_argument("--purge", action="store_true",
                      help="also take the data rundesk kept — never the backups")


def main(argv: Optional[List[str]] = None, asking=None, fetching=None) -> int:
    """Parse what was typed and hand it to the one module that answers it.

    Bare `rundesk` describes what it can do and exits `0`: somebody who typed the command with no
    operation asked a reasonable question and got an answer.

    `asking` looks up what version is published and `fetching` downloads a release. Both arrive as
    arguments and default to `None`, which each command resolves to the real thing at the moment it
    needs it — so every state of `version` and `update` is driven with no network anywhere
    near the test, and the surface itself knows nothing about GitHub.
    """
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.command is None:
        parser.print_help()
        return OK
    if args.command == "status":
        return cmd_status(args)
    if args.command == "configure":
        return cmd_configure(args)
    if args.command == "version":
        return cmd_version(args, asking)
    if args.command == "install":
        return cmd_install(args)
    if args.command == "update":
        return cmd_update(args, asking, fetching)
    if args.command == "uninstall":
        return cmd_uninstall(args)

    # Unreachable while every registered verb is dispatched above, and that is the point: a verb
    # added to the parser and wired to nothing fails here loudly rather than exiting 0 in silence.
    raise AssertionError(f"{args.command} is registered on the parser and answered by nothing")


def offered(parser: argparse.ArgumentParser) -> List[str]:
    """Every verb the parser offers, read off the parser itself.

    The one way anything — a test, a reference generator — learns what the command surface is, so a
    verb is covered the day it lands rather than the day somebody remembers to add it to a list.
    """
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    return []


__all__ = ["build_parser", "main", "offered"]
