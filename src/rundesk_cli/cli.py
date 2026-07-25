"""The rundesk command line — the one interface anyone using rundesk goes through.

Every verb the finished product will have is registered here from the start, so
`rundesk` and `rundesk --help` describe the whole shape of the thing rather than
whatever happens to be built this week. What is not built yet says so and exits
non-zero: a command that did nothing and reported success is a lie a script will
believe.

Only the install-lifecycle commands are real today — `version` and `update`, plus
the `install.sh` that put the command there in the first place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rundesk_cli import __version__  # noqa: E402
from rundesk_cli import updater  # noqa: E402

#: Where this checkout lives — the thing an update replaces in place.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: What a command that exists but is not built yet exits with. Not 0, which a
#: script would take as done; not 1, which is reserved for a command that ran and
#: failed. See `COMING_SOON`.
NOT_BUILT = 2

#: Every verb that is planned but not built, and the one line `--help` shows for it.
#: The finished shape of the CLI, declared up front — each entry graduates out of
#: this table into a real command as it lands.
COMING_SOON: dict[str, str] = {
    "agents": "list the agents this install defines",
    "new": "give an agent a directory to be itself in",
    "doctor": "what stands between an agent and a working turn",
    "run": "one turn, streamed to this terminal",
    "replay": "re-print a stored run",
    "serve": "answer messages in the foreground",
    "start": "run an agent in the background, and keep it running",
    "stop": "stand an agent down",
    "restart": "cycle an agent after a change",
    "status": "what is running",
    "logs": "what an agent has been saying",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rundesk",
        description="A lightweight, provider-agnostic multi-agent gateway.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"rundesk {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    for name, help_text in COMING_SOON.items():
        planned = sub.add_parser(name, help=help_text, description=help_text)
        # Whatever a planned command will eventually take, it takes nothing today —
        # but it must not choke on being given arguments, or the message it prints
        # would be argparse's rather than ours.
        planned.add_argument("args", nargs="*", help=argparse.SUPPRESS)

    said = sub.add_parser("version", help="what is installed, and whether that is current")
    said.add_argument("--check", action="store_true", help="say whether a newer release exists")

    moved = sub.add_parser("update", help="move to the newest published release")
    moved.add_argument("--check", action="store_true", help="say what would happen, and change nothing")

    sub.add_parser("uninstall", help="how to remove rundesk from this machine")
    return parser


def cmd_version(args: argparse.Namespace) -> int:
    if args.check:
        return updater.run(REPO_ROOT, __version__, check_only=True)
    print(f"rundesk {__version__}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    return updater.run(REPO_ROOT, __version__, check_only=args.check)


def cmd_uninstall(_args: argparse.Namespace) -> int:
    # The one thing the command cannot do for you: removing it removes the command
    # that is doing the removing. The installer owns it, and it is what you already
    # have on disk.
    print("Removing rundesk is the installer's job, since it removes this command too:")
    print()
    print(f"  {REPO_ROOT / 'install.sh'} --uninstall [--purge]")
    print()
    print("Or, without a checkout:")
    print("  curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh"
          " | bash -s -- --uninstall")
    return 0


def cmd_coming_soon(name: str) -> int:
    print(f"rundesk {name}: coming soon — this command is planned, not built yet.", file=sys.stderr)
    return NOT_BUILT


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command in COMING_SOON:
        return cmd_coming_soon(args.command)
    if args.command == "version":
        return cmd_version(args)
    if args.command == "update":
        return cmd_update(args)
    if args.command == "uninstall":
        return cmd_uninstall(args)

    # Unreachable through argparse, which rejects an unknown command before this —
    # but a dispatch that silently returns 0 for a verb nobody handled is how a
    # command comes to exist and do nothing.
    print(f"rundesk: no handler for '{args.command}'", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
