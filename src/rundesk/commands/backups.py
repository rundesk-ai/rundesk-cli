"""The copies of what rundesk keeps, and the four things anybody does with them.

`rundesk backups` on its own lists them, because listing is what somebody wants nine times in ten and
a verb they have to remember for it is a verb they will not remember. The other three are named:
`save`, `restore` and `set-location`.

The first group in this product with sub-verbs, and the shape is the same one the top level uses —
each sub-verb registered in this one small function, each answered below, and an unhandled one
raising rather than exiting `0` in silence.

**`restore` asks for `--confirm`.** It replaces everything the owner has accumulated, which puts it
in the same company as `uninstall`, and a flag rather than a prompt for the same reason: a prompt in
a script is a command that hangs, and one that assumes yes with no terminal is worse than none. It
takes a copy of what it replaces regardless, so the confirmation guards the interruption rather than
the loss — but the two together are what make a mistyped name cost nothing.
"""

import argparse
import sys
from pathlib import Path

from rundesk import __version__
from rundesk.commands import Subcommands, failed
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import backups
from rundesk.utils.table import as_table


def register(sub: Subcommands) -> None:
    """Put `backups` on the parser, with one sub-verb for each thing that happens to a copy."""
    said = sub.add_parser("backups", help="the copies of what rundesk keeps for you")
    what = said.add_subparsers(dest="what", metavar="<what>")

    what.add_parser("save", help="copy what rundesk keeps, now")

    back = what.add_parser("restore", help="put a copy back, keeping a copy of what it replaces")
    back.add_argument("backup", metavar="<backup>",
                      help="which copy, named as `rundesk backups` lists it")
    back.add_argument("--confirm", action="store_true",
                      help="required — a restore replaces everything rundesk keeps for you")

    moved = what.add_parser("set-location", help="keep the copies in another directory")
    moved.add_argument("path", metavar="<path>", help="the directory to keep them in")


def cmd_backups(args: argparse.Namespace) -> int:
    """Answer whichever of the four was asked for; with none of them, list what there is."""
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    what = getattr(args, "what", None)
    if what is None:
        return _listed()
    if what == "save":
        return _saved()
    if what == "restore":
        return _restored(args.backup, args.confirm)
    if what == "set-location":
        return _somewhere_else(Path(args.path).expanduser())

    # Unreachable while every sub-verb above is answered, and that is the point: one registered on
    # the parser and wired to nothing fails here loudly rather than exiting 0 having done nothing.
    raise AssertionError(f"backups {what} is registered on the parser and answered by nothing")


def _listed() -> int:
    """Every copy there is, newest first, and where they are kept.

    Where they are kept is printed even when there are none. "No copies" and "no copies *here*" are
    different things to learn, and somebody who has moved theirs to another disk needs to see which
    directory was just found empty.
    """
    at = paths.backups()
    try:
        there = backups.kept(at)
    except backups.Refused as why:
        return _failed(str(why), "nothing was listed")

    print(f"copies in {_where(at)}")
    if not there:
        print("        none yet — make one with: rundesk backups save")
        return OK
    as_table(("BACKUP",), [(one,) for one in there])
    return OK


def _saved() -> int:
    """Copy what rundesk keeps, then let go of the oldest past what the owner asked to keep.

    The copy is reported before anything is let go, and a retention that could not be applied is said
    out loud rather than passed over — but neither changes the exit code, because the operation
    somebody asked for was a copy and the copy is there. Reporting a failure it did not have is the
    mirror of reporting a success it did not earn, and costs the same trust.
    """
    at, data = paths.backups(), paths.data()
    try:
        name = backups.save(data, at)
    except (backups.Refused, OSError) as why:
        return _failed(str(why), "no copy was made")

    print(f"saved {name}")
    print(f"        from   {data}")
    print(f"        in     {_where(at)}")

    try:
        keeping = int(config.read(data)["backup_retention"])
        stuck = backups.prune(keeping, at, saying=lambda line: print(f"        {line}"))
    except (config.Unreadable, backups.Refused, TypeError, ValueError) as why:
        print(f"backups: the copy was saved and nothing was let go — {why}", file=sys.stderr)
        return OK

    for one in stuck:
        print(f"backups: {one} is past the {keeping} copies you keep and would not be removed",
              file=sys.stderr)
    return OK


def _restored(name: str, confirming: bool) -> int:
    """Put a copy back, or — with nothing confirming it — say exactly what that would do."""
    at, data = paths.backups(), paths.data()
    if not confirming:
        return _needs_confirming(name, at, data)

    try:
        done = backups.restore(name, data, at, saying=lambda line: print(f"        {line}"))
    except backups.HalfRestored as why:
        return _failed(str(why), f"{data} is neither what it was nor what you asked for")
    except (backups.Refused, OSError) as why:
        return _failed(str(why), "nothing was restored")

    # What was kept is not repeated here: `restore` says it before it replaces anything, which is
    # the only ordering under which the name survives a failure partway through.
    print(f"restored {done.name}")
    print(f"        into   {data}")

    if done.settled:
        # The files really are the copy that was asked for, and they have not been carried onto this
        # release. Saying "restored" and exiting 0 here would be a migration that silently never
        # fired — which is the shape of every defect this product is written against.
        return _failed(
            f"the copy is back and could not be settled: {done.settled}",
            f"{data} is the copy you asked for, on a release it has not been carried to.",
            "`rundesk update` settles an install and is safe to run again.")
    return OK


def _needs_confirming(name: str, at: Path, data: Path) -> int:
    """Say what a restore would replace, and replace none of it.

    The name is checked against what is actually there first, so somebody who mistyped it finds out
    now rather than after typing the confirmation for a copy that does not exist.
    """
    try:
        there = backups.kept(at)
    except backups.Refused as why:
        return _failed(str(why), "nothing was restored")
    if name not in there:
        return _failed(f"there is no copy called {name} in {_where(at)}", "nothing was restored")

    print(f"restore: this would replace {data} with the copy {name}", file=sys.stderr)
    print(f"        keep   a copy of {data} as it is now, before anything is replaced",
          file=sys.stderr)
    print(f"        put    {name} in its place, from {_where(at)}", file=sys.stderr)
    print(f"        settle what comes back onto this release ({__version__})", file=sys.stderr)
    print("        nothing was restored. To go ahead:", file=sys.stderr)
    print(f"        rundesk backups restore {name} --confirm", file=sys.stderr)
    return FAILED


def _somewhere_else(to: Path) -> int:
    """Keep the copies in another directory, and link the old place at it."""
    at = paths.backups()
    if backups.location(at).resolve() == to.resolve():
        print(f"rundesk already keeps its copies in {to}")
        return OK

    try:
        landed = backups.relocate(to, at, saying=lambda line: print(f"        {line}"))
    except (backups.Refused, paths.Refused, OSError) as why:
        return _failed(str(why), "the copies are where they were")

    print(f"rundesk keeps its copies in {landed}")
    print(f"        linked {at} → {landed}")
    return OK


def _where(at: Path) -> str:
    """Where the copies are kept, and where that points when they have been moved elsewhere.

    One string rather than two rows, so the answer to "where are my copies" cannot be read off the
    half of it that is only true until somebody moves them.
    """
    real = backups.location(at)
    return str(at) if real == at else f"{at} → {real}"


def _failed(why: str, *and_so: str) -> int:
    """Say what went wrong, and what that leaves — never one without the other."""
    return failed(f"backups: FAILED — {why}", *and_so)
