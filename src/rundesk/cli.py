"""The command surface: the parser, the dispatch, and nothing else.

Every verb registered here is built. There is no table of operations that are listed and do not work
— a verb rundesk cannot perform is a verb rundesk does not have, and the command describes exactly
what it can do.

The one rule: a verb's parser is built beside the verb, in a small function. The build this replaces
had one `build_parser()` of about 680 lines registering thirty verbs inline, which is where a surface
goes to stop being readable.
"""

import argparse
import contextlib
import signal
import sys
from typing import Callable, List, Optional

from rundesk.commands import Subcommands
from rundesk.commands.agents import cmd_agents
from rundesk.commands.agents import register as register_agents
from rundesk.commands.ask import cmd_ask
from rundesk.commands.ask import register as register_ask
from rundesk.commands.asked import cmd_asked
from rundesk.commands.asked import register as register_asked
from rundesk.commands.backups import cmd_backups
from rundesk.commands.backups import register as register_backups
from rundesk.commands.channels import Reaching, cmd_channels
from rundesk.commands.channels import register as register_channels
from rundesk.commands.configure import cmd_configure
from rundesk.commands.configure import register as register_configure
from rundesk.commands.env import cmd_env
from rundesk.commands.env import register as register_env
from rundesk.commands.gateways import Cycled, cmd_gateways
from rundesk.commands.gateways import register as register_gateways
from rundesk.commands.google import cmd_google
from rundesk.commands.google import register as register_google
from rundesk.commands.install import cmd_install
from rundesk.commands.login import cmd_login
from rundesk.commands.login import register as register_login
from rundesk.commands.messages import cmd_messages
from rundesk.commands.messages import register as register_messages
from rundesk.commands.permissions import cmd_permissions
from rundesk.commands.permissions import register as register_permissions
from rundesk.commands.providers import cmd_providers
from rundesk.commands.providers import register as register_providers
from rundesk.commands.schedules import cmd_schedules
from rundesk.commands.schedules import register as register_schedules
from rundesk.commands.skills import cmd_skills
from rundesk.commands.skills import register as register_skills
from rundesk.commands.status import cmd_status
from rundesk.commands.turns import cmd_turns
from rundesk.commands.turns import register as register_turns
from rundesk.commands.uninstall import cmd_uninstall
from rundesk.commands.update import Fetching, cmd_update
from rundesk.commands.version import cmd_version
from rundesk.core import google as google_oauth
from rundesk.exits import FAILED, OK
from rundesk.gateways import job
from rundesk.lifecycle import release
from rundesk.skills.catalogs import Fetching as Refreshing
from rundesk.utils.programs import Ran

#: What builds the packages a release asked for — `utils.programs.run`, handed in so no
#: suite reaches a network by forgetting it.
Building = Callable[..., Ran]

#: What starts a program while a capability is being proved. See `main`.
Probing = Callable[..., Ran]

EPILOG = """\
examples:
  rundesk status                how rundesk is on this machine
  rundesk configure             what this install is configured with
  rundesk agents                the agents this install keeps
  rundesk agents add <agent> --provider <provider>
  rundesk gateways              every agent, and how its gateway stands
  rundesk gateways start <agent>
  rundesk gateways logs <agent>
  rundesk schedules             work an agent starts because the time came
  rundesk schedules add <agent> <schedule> --when '0 9 * * *' --run '<program>'
  rundesk schedules run <agent> <schedule>
  rundesk channels              how each agent is reached, and how it reaches back
  rundesk channels add <agent> <adapter> --allow <id>
  rundesk channels doctor       what a channel cannot do, and exactly why
  rundesk backups               the copies of what rundesk keeps for you
  rundesk backups save          copy what rundesk keeps, now
  rundesk env list              the values rundesk hands to what it talks to
  rundesk login google          connect a verified Google account in the browser
  rundesk skills                the skills this install has, and who holds which
  rundesk skills doctor         what an agent cannot use, and exactly why
  rundesk permissions           what this Mac lets rundesk do, as last checked
  rundesk permissions check     prove it now, and say what is still not allowed
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
    register_agents(sub)
    register_gateways(sub)
    register_backups(sub)
    register_env(sub)
    register_login(sub)
    register_ask(sub)
    register_asked(sub)
    register_messages(sub)
    register_providers(sub)
    register_permissions(sub)
    register_turns(sub)
    register_schedules(sub)
    register_channels(sub)
    register_skills(sub)
    register_google(sub)
    _register_install(sub)
    _register_update(sub)
    _register_uninstall(sub)
    return parser


def _register_status(sub: Subcommands) -> None:
    sub.add_parser("status", help="how rundesk itself is on this machine")


def _register_version(sub: Subcommands) -> None:
    sub.add_parser("version", help="what version this install is, and whether it is out of date")


def _register_install(sub: Subcommands) -> None:
    put = sub.add_parser("install", help="install rundesk into RUNDESK_HOME")
    put.add_argument("--source", metavar="<dir>", default=None,
                     help="the tree to install from (default: the one this command is running from)")
    put.add_argument("--bin-dir", metavar="<dir>", default=None,
                     help="where to put the rundesk command on your PATH")


def _register_update(sub: Subcommands) -> None:
    update = sub.add_parser(
        "update", help="move to the newest published release, or say it is up to date")
    update.add_argument(
        "--continue", action="store_true", dest="continuation",
        help="resume this channel conversation once the guarded update has a terminal outcome")


def _register_uninstall(sub: Subcommands) -> None:
    gone = sub.add_parser("uninstall", help="remove rundesk from this machine")
    gone.add_argument("--confirm", action="store_true",
                      help="required — removal does nothing without it")
    gone.add_argument("--purge", action="store_true",
                      help="also take the data rundesk kept — never the backups")


def main(argv: Optional[List[str]] = None, asking: Optional[release.Asking] = None,
         fetching: Optional[Fetching] = None,
         supervising: Optional[job.Supervising] = None,
         refreshing: Optional[Refreshing] = None,
         building: Optional[Building] = None,
         reaching: Optional[Reaching] = None,
         probing: Optional[Probing] = None,
         google_authorizing: Optional[google_oauth.Authorizing] = None,
         google_posting: Optional[google_oauth.Posting] = None) -> int:
    """Parse what was typed and hand it to the one module that answers it.

    Bare `rundesk` describes what it can do and exits `0`: somebody who typed the command with no
    operation asked a reasonable question and got an answer.

    `asking` looks up what version is published, `fetching` downloads a release, `refreshing` brings
    down a catalog of skills, `reaching` runs the program behind a channel, and `supervising` is the
    machine's supervisor. All five arrive as
    arguments and default to `None`, which each command resolves to the real thing at the moment it
    needs it — so every state of `version`, `update`, `gateways` and `skills` is driven with no
    network and no `launchctl` anywhere near the test, and the surface itself knows nothing about
    GitHub or launchd.

    **The third one is the one with no safety net.** A suite that forgot `asking=` fails loudly,
    because the harness points every proxy variable at a closed port; there is no closed port for
    launchd, and the real supervisor would answer a test perfectly well against the owner's own
    login session, booting out jobs that keep real work running. So `tests/support.py` passes a
    stand-in by default, which is the reverse of what it does for the other two, and that reversal
    is deliberate.

    **`probing` is the second with no safety net, and for a sharper reason.** There is no closed
    port for `osascript` either — and unlike launchd, the real thing can raise a consent dialog on
    whoever's desktop is in front of the suite, where one wrong click denies a grant permanently.
    Worse, `screencapture` from an ungranted process was measured making macOS *write* a grant. So
    `tests/support.py` passes a stand-in by default here too.

    **`backups` and `update` are handed a fourth thing, built here out of the third.** A restore
    replaces the file every running gateway's lock stands on, and an update replaces the imported
    program beneath every gateway. Both stand online gateways down and start exactly them again —
    and what they stand them down *with* is `commands.gateways.Cycled`, which is the same
    `stop` and `start` a person types. Built here rather than defaulted in that command's signature,
    for every reason `Cycled` gives for having no default of its own: it is built out of
    `supervising`, so a suite that replaced the supervisor has replaced this too, without knowing it
    exists.
    """
    _asked_to_stop_politely()
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return _the_verb(args, asking, fetching, supervising, refreshing, building, reaching,
                         probing, parser, google_authorizing, google_posting)
    except KeyboardInterrupt:
        # **A stop is a normal way for a command to end, and it must read like one.** Every long
        # verb — a turn, a restore, an update — can be Ctrl-C'd or sent a `SIGTERM`, and both
        # arrive here as this. Left uncaught, somebody who stopped their own turn got twenty lines
        # of traceback ending inside `queue.get`, which reads as a crash; and a supervisor stopping
        # a scheduled turn wrote the same thing into that schedule's output.
        #
        # Caught *here*, at the top, and nowhere lower: what makes a stop safe is that the `finally`
        # blocks under this ran on the way out, which they have by the time it lands.
        # `FAILED` and not a fourth code: `exits` says there are three answers and no others, and
        # a stopped command did not do the work — which is exactly what that code means.
        print(f"\n{args.command or 'rundesk'}: stopped")
        return FAILED


def _the_verb(args: argparse.Namespace, asking, fetching, supervising, refreshing, building,
              reaching, probing, parser: argparse.ArgumentParser, google_authorizing=None,
              google_posting=None) -> int:
    """Which module answers what was typed. One `if` per verb, in the order `rundesk` lists them."""
    if args.command is None:
        parser.print_help()
        return OK
    if args.command == "status":
        return cmd_status(args, supervising)
    if args.command == "configure":
        return cmd_configure(args, supervising)
    if args.command == "agents":
        return cmd_agents(args)
    if args.command == "gateways":
        return cmd_gateways(args, supervising)
    if args.command == "backups":
        return cmd_backups(args, _gateways(supervising))
    if args.command == "env":
        return cmd_env(args)
    if args.command == "login":
        return cmd_login(args, google_authorizing)
    if args.command == "ask":
        return cmd_ask(args)
    if args.command == "asked":
        return cmd_asked(args)
    if args.command == "messages":
        return cmd_messages(args)
    if args.command == "turns":
        return cmd_turns(args)
    if args.command == "permissions":
        return cmd_permissions(args, probing)
    if args.command == "providers":
        return cmd_providers(args)
    if args.command == "schedules":
        return cmd_schedules(args)
    if args.command == "channels":
        return cmd_channels(args, reaching)
    if args.command == "skills":
        return cmd_skills(args, refreshing)
    if args.command == "_google":
        return cmd_google(args, google_authorizing, google_posting)
    if args.command == "version":
        return cmd_version(args, asking)
    if args.command == "install":
        return cmd_install(args, refreshing, building)
    if args.command == "update":
        return cmd_update(args, asking, fetching, refreshing, building, _gateways(supervising))
    if args.command == "uninstall":
        return cmd_uninstall(args, supervising)

    # Unreachable while every registered verb is dispatched above, and that is the point: a verb
    # added to the parser and wired to nothing fails here loudly rather than exiting 0 in silence.
    raise AssertionError(f"{args.command} is registered on the parser and answered by nothing")


def _gateways(supervising: Optional[job.Supervising]) -> Cycled:
    """Something a command can stand a gateway down with, built out of the supervisor `main` was given.

    Resolved here, in a body, and never bound in a signature — the same rule the supervisor itself
    is held to one line below, and for the same reason: what a default cannot be reached past is
    `launchctl`, in the login session of whoever is at the machine.

    **Built out of `supervising` rather than beside it**, which is what makes the isolation
    automatic: `tests/support.py:run_with` hands every command a stand-in supervisor and replaces
    `job.Launchd` with something that raises, so this is a stand-in in every case that drives the
    command and reaches nothing on the machine.
    """
    return Cycled(supervising if supervising is not None else job.Launchd())


def _asked_to_stop_politely() -> None:
    """Turn a hang-up or a termination request into something the rollbacks can catch.

    **Ctrl-C already raises; closing the terminal does not.** Python installs no handler for
    `SIGHUP`, so the kernel ends the process outright — no exception, no `except` clause of any
    kind, and every rollback in this product skipped. Measured: a worker sent a real `SIGHUP`
    mid-copy exited `-1` with nothing run. That is the same window `KeyboardInterrupt` was already
    fixed for, reached by a signal no amount of care in an `except` could have caught.

    So the two signals a person actually causes — closing the window, and a supervisor asking a
    command to stop — are turned into `KeyboardInterrupt`, which is precisely what Ctrl-C raises and
    what every rollback here now catches. One shape of interruption, one way of unwinding.

    `SIGKILL` cannot be handled by anything and is not attempted: what protects against that is the
    staging convention, not a handler.

    Done here rather than at import: a module that installed handlers merely by being imported would
    change the behaviour of anything that imported it, including the suite.
    """
    def leave(_signal: int, _frame: object) -> None:
        raise KeyboardInterrupt()

    for asked in (signal.SIGHUP, signal.SIGTERM):
        with contextlib.suppress(ValueError, OSError, AttributeError):
            # Only the main thread of the main interpreter may install one, and a platform that
            # has no `SIGHUP` is not a reason for the command to refuse to run.
            signal.signal(asked, leave)


def offered(parser: argparse.ArgumentParser) -> List[str]:
    """Every verb the parser offers, read off the parser itself.

    The one way anything — a test, a reference generator — learns what the command surface is, so a
    verb is covered the day it lands rather than the day somebody remembers to add it to a list.

    Read off argparse's own private shape, which is the only place the answer exists. Returning
    nothing is not treated as "no verbs" by anybody: `tests/test_cli.py` refuses an empty walk, so a
    Python that renamed this out from under us fails the suite rather than passing it with nothing
    checked.
    """
    for action in parser._actions:
        if isinstance(action, Subcommands):
            return sorted(name for name in action.choices if not name.startswith("_"))
    return []


__all__ = ["build_parser", "main", "offered"]
