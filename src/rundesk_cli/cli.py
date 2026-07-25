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
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rundesk_cli import __version__  # noqa: E402
from rundesk_cli import gateway as _gateway  # noqa: E402
from rundesk_cli import supervisor as _supervisor  # noqa: E402
from rundesk_cli import updater  # noqa: E402

#: Where this checkout lives — the thing an update replaces in place.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: How many of a gateway's last lines `logs` shows when not told otherwise.
LOG_LINES = 40

#: How long cycling waits for a gateway to actually go before giving up on it. Longer
#: than a gateway is allowed to take stopping, so a slow but correct shutdown is not
#: mistaken for one that is stuck.
CYCLE_PATIENCE = 20.0

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
        # Marked where the list is, not only when the verb is invoked. Eleven of fourteen
        # commands are planned, and a list that reads as fourteen working ones sends a
        # newcomer to try each in turn to find out which three do anything.
        planned = sub.add_parser(name, help=f"{help_text} [coming soon]",
                                 description=f"{help_text} — planned, not built yet.")
        # Whatever a planned command will eventually take, it takes nothing today —
        # but it must not choke on being given arguments, or the message it prints
        # would be argparse's rather than ours.
        planned.add_argument("args", nargs="*", help=argparse.SUPPRESS)

    said = sub.add_parser("version", help="what is installed, and whether that is current")
    said.add_argument("--check", action="store_true", help="say whether a newer release exists")

    moved = sub.add_parser("update", help="move to the newest published release")
    moved.add_argument("--check", action="store_true", help="say what would happen, and change nothing")

    sub.add_parser("uninstall", help="how to remove rundesk from this machine")

    # The gateway. Every one of these takes the gateway's name and can do without it,
    # because there is one gateway today and there will be one per agent. Leaving the
    # name out means all of them wherever that can mean anything, so what these do
    # today stays true once there are several.
    served = sub.add_parser("serve", help="run a gateway here, until it is asked to stop")
    served.add_argument("name", nargs="?", default=_gateway.DEFAULT_NAME)

    started = sub.add_parser("start", help="have the machine keep a gateway running")
    started.add_argument("name", nargs="?", default=_gateway.DEFAULT_NAME)

    stopped = sub.add_parser("stop", help="stand a gateway down")
    stopped.add_argument("name", nargs="?")

    cycled = sub.add_parser("restart", help="cycle a gateway, leaving the others alone")
    cycled.add_argument("name", nargs="?")

    sub.add_parser("status", help="every gateway, and what it is doing")

    said = sub.add_parser("logs", help="what a gateway has been saying")
    said.add_argument("name", nargs="?", default=_gateway.DEFAULT_NAME)
    said.add_argument("-n", "--lines", type=int, default=LOG_LINES,
                      help="how many of the last lines to show")
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


def cmd_serve(args: argparse.Namespace, gateways) -> int:
    """Run a gateway here, in the foreground. What the machine's job invokes.

    Refusing to run ends *well*, on purpose. The machine is told to start a gateway
    again whenever it ends badly, so a gateway that will never start — its virtualenv
    does not fit, or another already holds its name — would otherwise be started every
    few seconds for as long as the machine is up (R-GW-25).
    """
    try:
        return asyncio.run(gateways.Gateway(args.name).serve())
    except (gateways.AlreadyRunning, gateways.Unfit, gateways.NotAName) as why:
        print(f"rundesk {args.name}: {why}", file=sys.stderr)
        return 0


def cmd_start(args: argparse.Namespace, gateways, machine) -> int:
    """Hand a gateway to the machine, and let the machine keep it running."""
    try:
        said = machine.install(args.name)
    except machine.NotOurs as why:
        print(f"rundesk {args.name}: {why}", file=sys.stderr)
        return 1
    except machine.NoSupervisor as why:
        print(f"rundesk: {why}", file=sys.stderr)
        print(f"  run it yourself with: rundesk serve {args.name}", file=sys.stderr)
        return 1
    if not said.ok:
        print(f"rundesk {args.name}: the machine would not take it — {said.said}", file=sys.stderr)
        return 1
    print(f"rundesk {args.name}: handed to the machine, which will keep it running")
    return 0


def _named(args: argparse.Namespace, gateways, machine) -> list[str]:
    """The gateways a command is about: the one named, or every one there is.

    Naming none and meaning one is the ambiguity worth refusing; naming none and meaning
    all of them is what an owner wants when they are shutting the machine down.
    """
    if getattr(args, "name", None):
        return [args.name]
    return sorted({it.name for it in gateways.every()} | set(machine.described()))


def cmd_stop(args: argparse.Namespace, gateways, machine) -> int:
    return _stand_down(args, gateways, machine, "stop")


def cmd_restart(args: argparse.Namespace, gateways, machine) -> int:
    return _stand_down(args, gateways, machine, "restart")


def _gone(name: str, gateways, patience: float = CYCLE_PATIENCE) -> bool:
    """Has this gateway actually stopped? Asked of the gateway, not of the machine."""
    deadline = time.monotonic() + patience
    while time.monotonic() < deadline:
        if not gateways.standing(name).running:
            return True
        time.sleep(0.2)
    return not gateways.standing(name).running


def _stand_down(args: argparse.Namespace, gateways, machine, verb: str) -> int:
    names = _named(args, gateways, machine)
    if not names:
        print("rundesk: no gateway to " + verb)
        return 0
    worst = 0
    for name in names:
        try:
            if not machine.known(name):
                # Never a job this install did not write. The command this replaces uses
                # the same names for its own, and standing those down would take an
                # owner's live agents with it.
                said = machine.Spoke(False, "")
            elif verb == "restart":
                stopped = machine.stop(name)
                if not stopped.ok:
                    print(f"rundesk {name}: could not ask it to stop — {stopped.said}",
                          file=sys.stderr)
                    worst = 1
                    continue
                if not _gone(name, gateways):
                    # Starting it now does nothing — the machine sees a job already
                    # running — and the old one then ends *well*, which is the one
                    # outcome the machine is told not to undo. The gateway would be
                    # left down, having just reported that it was cycled.
                    print(f"rundesk {name}: still running after being asked to stop",
                          file=sys.stderr)
                    worst = 1
                    continue
                said = machine.start(name)
            else:
                said = machine.stop(name)
        except machine.NoSupervisor as why:
            print(f"rundesk: {why}", file=sys.stderr)
            return 1
        except machine.NotOurs as why:
            print(f"rundesk {name}: {why}", file=sys.stderr)
            worst = 1
            continue
        if said.ok:
            print(f"rundesk {name}: {'cycled' if verb == 'restart' else 'asked to stop'}")
        elif gateways.standing(name).running:
            print(f"rundesk {name}: running, but not the machine's to {verb}", file=sys.stderr)
            worst = 1
        else:
            print(f"rundesk {name}: not running")
    return worst


def cmd_status(_args: argparse.Namespace, gateways, machine) -> int:
    """Every gateway, and what it is actually doing.

    Answered by the gateways themselves rather than by the machine, because the machine
    cannot tell a gateway that is working from one that is up and stuck (R-GW-9).
    """
    known = set(machine.described()) if machine.available() else set()
    found = {it.name: it for it in gateways.every()}
    for name in sorted(known - set(found)):
        found[name] = gateways.Standing(name=name, running=False)
    if not found:
        print("no gateways")
        return 0
    for name in sorted(found):
        it = found[name]
        kept = " kept up" if name in known else ""
        if not it.running:
            print(f"{name:<20} not running{kept}")
            continue
        doing = gateways.what_is_running(name)
        work = f", {len(doing)} in flight ({', '.join(sorted(doing))})" if doing else ", idle"
        state = "WEDGED — not going round" if it.stale else "running"
        print(f"{name:<20} {state}{kept}, pid {it.pid}, version {it.version}{work}")
    return 0


def cmd_logs(args: argparse.Namespace, gateways) -> int:
    """What a gateway has been saying. Reads the file, so a gateway that has gone can
    still be asked what happened (R-GW-18)."""
    path = gateways.log_path(args.name)
    if not path.exists():
        print(f"rundesk {args.name}: nothing written yet ({path})", file=sys.stderr)
        return 1
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError as why:
        # Every other verb answers in our words when it cannot do the thing. A log that
        # cannot be read is a thing to be told about, not a traceback.
        print(f"rundesk {args.name}: could not read what it wrote — {why}", file=sys.stderr)
        return 1
    for line in lines[-args.lines:] if args.lines > 0 else []:
        print(line)
    return 0


def main(argv: list[str], gateways=None, machine=None) -> int:
    """The command surface.

    What the gateway commands act on is passed in rather than imported here, so this
    file knows the verbs and nothing about locks, records or process groups — and so
    every one of them is exercised without a gateway or a supervisor anywhere near it.
    """
    gateways = gateways if gateways is not None else _gateway
    machine = machine if machine is not None else _supervisor
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    named = getattr(args, "name", None)
    if named is not None:
        try:
            gateways.checked(named)
        except gateways.NotAName as why:
            print(f"rundesk: {why}", file=sys.stderr)
            return 1
    if args.command in COMING_SOON:
        return cmd_coming_soon(args.command)
    if args.command == "version":
        return cmd_version(args)
    if args.command == "update":
        return cmd_update(args)
    if args.command == "uninstall":
        return cmd_uninstall(args)
    if args.command == "serve":
        return cmd_serve(args, gateways)
    if args.command == "start":
        return cmd_start(args, gateways, machine)
    if args.command == "stop":
        return cmd_stop(args, gateways, machine)
    if args.command == "restart":
        return cmd_restart(args, gateways, machine)
    if args.command == "status":
        return cmd_status(args, gateways, machine)
    if args.command == "logs":
        return cmd_logs(args, gateways)

    # Unreachable through argparse, which rejects an unknown command before this —
    # but a dispatch that silently returns 0 for a verb nobody handled is how a
    # command comes to exist and do nothing.
    print(f"rundesk: no handler for '{args.command}'", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
