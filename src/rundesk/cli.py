"""The command surface: the parser, the dispatch, and nothing else.

Every verb the finished product will offer is registered here from the outset — the four that are
built and the eight that are not — so the command describes the whole product rather than the part of
it that happens to exist today. What each verb *does* lives in its own module under `commands/`; this
file knows which verb goes where and nothing about locks, releases or directories.

The one rule: a verb's parser is built beside the verb, in a small function. The build this replaces
had one `build_parser()` of about 680 lines registering thirty verbs inline, which is where a surface
goes to stop being readable.
"""

import argparse
import sys
from typing import List, Optional

from rundesk import __version__
from rundesk.commands import not_available
from rundesk.commands.status import cmd_status
from rundesk.commands.uninstall import cmd_uninstall
from rundesk.commands.update import cmd_update
from rundesk.commands.version import cmd_version
from rundesk.exits import OK
from rundesk.planned import PLANNED, part_named

EPILOG = """\
examples:
  rundesk status                how rundesk is on this machine
  rundesk version               what version this install is
  rundesk update                move to the newest published release
  rundesk uninstall             remove rundesk from this machine

An operation listed here that is not built yet says so and exits 69, which is
its own code: a script can tell it from a command that does not exist.
"""


def build_parser() -> argparse.ArgumentParser:
    """The whole command surface, built once.

    Every verb rundesk will offer is registered, whether or not it is built. Nothing reads a list of
    verbs from anywhere but this parser — a list written twice is a list that disagrees with itself.
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
    _register_update(sub)
    _register_uninstall(sub)
    _register_planned(sub)
    return parser


def _register_status(sub) -> None:
    sub.add_parser("status", help="how rundesk itself is on this machine")


def _register_version(sub) -> None:
    said = sub.add_parser("version", help="what version this install is")
    said.add_argument("--check", action="store_true",
                      help="say whether a newer release has been published")


def _register_update(sub) -> None:
    moved = sub.add_parser("update", help="move to the newest published release")
    moved.add_argument("--check", action="store_true",
                       help="say what would happen, and change nothing")


def _register_uninstall(sub) -> None:
    gone = sub.add_parser("uninstall", help="remove rundesk from this machine")
    gone.add_argument("--purge", action="store_true",
                      help="also take the agents, logs and history rundesk kept")


def _register_planned(sub) -> None:
    """Register every operation that is not built yet, so the command lists the whole product.

    `argparse.REMAINDER` is what makes this honest rather than decorative: it swallows whatever
    follows the verb, so an option a future release will take is *accepted today* instead of turning
    into argparse's usage error. Without it, `skills install some/repo --confirm` would exit 2 —
    indistinguishable from a verb rundesk has never heard of.
    """
    for verb, (gloss, actions) in sorted(PLANNED.items()):
        registered = sub.add_parser(verb, help=f"{gloss} [coming soon]",
                                    description=_described(verb, gloss, actions),
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
        registered.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)


def _described(verb: str, gloss: str, actions) -> str:
    """The help for a planned verb: what it is for, and every action it will take."""
    lines = [f"{gloss} — planned, not built yet.", ""]
    for action in sorted(actions):
        lines.append(f"  rundesk {verb} {action:<12} {actions[action]}")
    return "\n".join(lines).rstrip()


def main(argv: Optional[List[str]] = None) -> int:
    """Parse what was typed and hand it to the one module that answers it.

    Bare `rundesk` describes what it can do and exits `0`: somebody who typed the command with no
    operation asked a reasonable question and got an answer.
    """
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.command is None:
        parser.print_help()
        return OK
    if args.command in PLANNED:
        return not_available(args.command, part_named(args.command, args.rest))
    if args.command == "status":
        return cmd_status(args)
    if args.command == "version":
        return cmd_version(args)
    if args.command == "update":
        return cmd_update(args)
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


__all__ = ["build_parser", "main", "offered", "__version__"]
