"""Taking rundesk off this machine.

The command in the product with the least room for being approximately right, in both directions. A
removal that did not happen must never report success — somebody believes their machine is clean and
it is not. And a removal that happened cannot be undone, so what it reaches has to be decided rather
than swept.

So it names what it takes, one thing at a time, and never globs:

- the PATH link, **only where it points into this install's own `app/`** — a second install on the
  machine keeps its command
- `app/`, whole, unless it looks like somebody's checkout
- `data/`, **only when `--purge` asks for it** — that is what the owner accumulated
- `backups/`, **never**. Not "not by default": there is no argument to this command that reaches
  them. A copy is worth nothing if the thing that takes the product away takes the copies too, and
  the way to guarantee that is for this file never to name the directory at all.
- `$RUNDESK_HOME` itself, only once nothing is left in it — so a purge tidies up and a plain removal
  leaves the root standing over the data it kept.
"""

import argparse
import shutil
import sys
from pathlib import Path

from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import tree


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Remove rundesk, and say exactly what was taken and what was kept."""
    try:
        root = paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    app = paths.app()
    if not app.exists() and not paths.data().exists():
        # Removing something that was never installed is not a failure; it is the state asked for.
        print(f"rundesk is not installed at {root}")
        return OK

    if not args.confirm:
        return _needs_confirming(root, args.purge)

    taken, kept = [], []

    try:
        for at in tree.unlink(app, _where_the_command_went()):
            taken.append(str(at))
    except OSError as why:
        return _failed(f"the command could not be unlinked: {why}")

    try:
        if app.exists():
            tree.remove(app)
            taken.append(str(app))
    except (tree.Refused, OSError) as why:
        return _failed(str(why))

    if args.purge:
        gone_wrong = _purge(paths.data(), taken)
        if gone_wrong:
            return _failed(gone_wrong)
    elif paths.data().exists():
        kept.append(str(paths.data()))

    if paths.backups().exists():
        kept.append(f"{paths.backups()} (copies always survive removal)")
    if paths.projects().exists():
        kept.append(str(paths.projects()))

    _tidy(root)

    print("rundesk removed")
    for one in taken:
        print(f"        took   {one}")
    for one in kept:
        print(f"        kept   {one}")
    return OK


def _where_the_command_went():
    """Every directory that might hold this install's command, the recorded one first.

    The install writes down where it put the link, because that directory is chosen at install time
    and can be anywhere. Without it a removal only knows the usual places, so an install linked
    somewhere else leaves a dangling link and says it removed everything.

    The usual places are still searched afterwards, so an install made before this was recorded is
    removed properly too. Every candidate is checked to be *this* install's before it is touched.
    """
    where = []
    try:
        recorded = config.read(paths.data()).get("command_link")
    except config.Unreadable:
        recorded = None
    if recorded:
        where.append(str(Path(recorded).parent))
    where.extend(one for one in tree.BIN_DIRS if one not in where)
    return where


def _needs_confirming(root: Path, purging: bool) -> int:
    """Say exactly what would be removed, and remove nothing.

    Confirmation is a required flag rather than a typed answer at a prompt, because this command has
    to work the same when nobody is watching it: a prompt in a script is a command that hangs, and a
    prompt that falls back to "yes" when there is no terminal is worse than no prompt at all.
    """
    print(f"uninstall: this would remove rundesk from {root}", file=sys.stderr)
    print(f"        take   the command, and {paths.app()}", file=sys.stderr)
    if purging:
        print(f"        take   {paths.data()} — everything rundesk kept for you", file=sys.stderr)
    else:
        print(f"        keep   {paths.data()}", file=sys.stderr)
    print(f"        keep   {paths.backups()}", file=sys.stderr)
    print("        nothing was removed. To go ahead:", file=sys.stderr)
    print(f"        rundesk uninstall --confirm{' --purge' if purging else ''}", file=sys.stderr)
    return FAILED


def _purge(data: Path, taken: list) -> str:
    """Take what the owner accumulated. Only ever the data directory, never a level above it."""
    if not data.exists():
        return ""
    try:
        shutil.rmtree(data)
    except OSError as why:
        return f"{data} could not be removed: {why}"
    taken.append(str(data))
    return ""


def _tidy(root: Path) -> None:
    """Remove the root itself, but only once it is genuinely empty.

    `rmdir` rather than a recursive delete, on purpose: it fails while anything is still there, which
    is exactly the behaviour wanted. A removal that kept the data must leave the directory holding it.
    """
    try:
        root.rmdir()
    except OSError:
        pass


def _failed(why: str) -> int:
    print(f"uninstall: FAILED — {why}", file=sys.stderr)
    print("        nothing further was removed", file=sys.stderr)
    return FAILED
