"""How rundesk itself is on this machine.

`status` answers *how rundesk is*: which version, which root answered, whether it is installed, how
far it has been carried, and whether it can run here. What agents there are and what they are doing
is a different question and will be a different command.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

from rundesk import __version__
from rundesk.agents import directory
from rundesk.commands import as_written, failed, print_json
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job
from rundesk.lifecycle import backups, migration
from rundesk.utils.terminal import as_table

#: The oldest Python a fresh macOS ships, which is the floor everything here is written against.
PYTHON_FLOOR = (3, 9)


def cmd_status(args: argparse.Namespace,
               supervising: Optional[job.Supervising] = None) -> int:
    """Print what rundesk is and where it keeps things; exit non-zero when it could not run.

    Takes no flags — a question with one answer does not need shaping.
    """
    try:
        where = paths.home()
    except paths.Refused as why:
        return failed(f"status: FAILED — {why}")

    unfit = _unfit()
    rows = [
        ("version", __version__),
        ("home", _shown(where)),
        ("program", _program()),
        ("data", _shown(paths.data())),
        ("backups", _backups()),
        ("secrets", _shown(paths.secrets())),
        ("projects", _shown(paths.projects())),
        ("agents", _agents()),
        ("fit to run", "yes" if not unfit else f"no — {unfit}"),
    ]
    rows.extend(_configured())
    from rundesk.commands import automatic_updates
    rows.append(("automatic update", automatic_updates.status(supervising)))
    if args.json:
        print_json({"status": {name.replace(" ", "_"): value for name, value in rows}})
    else:
        as_table(("WHAT", "IS"), rows)
    return FAILED if unfit else OK


def _configured() -> List[Tuple[str, str]]:
    """Every value this install is configured with, read from its own configuration.

    Walked off `config.read` rather than named here, so a value a release starts offering is shown
    the day it lands — a hand-kept list of settings is a list that quietly stops being complete.
    """
    try:
        settled = config.read(paths.data())
    except config.Unreadable as why:
        return [("config", f"? — {why}")]
    return [(key, _readably(key, settled[key])) for key in sorted(settled)]


def _readably(key: str, value: Any) -> str:
    """One configured value as a person reads it.

    `migration` is the one nobody states, so it says what it means rather than printing a bare id or
    an unexplained `None`. Everything else reads the way it reads everywhere else in the product.
    """
    if key == "migration":
        try:
            ships = migration.newest()
        except migration.Broken as why:
            # `status` is the one command that must answer whatever is wrong, and steps that
            # cannot be ordered are exactly the kind of wrong somebody runs it to find out about.
            return f"? — {why}"
        if ships is None:
            return "nothing to carry — this release ships no migration steps"
        if value is None:
            return f"not carried yet (this release ships up to {ships})"
        return str(value) if value == ships else f"{value} (this release ships up to {ships})"
    return as_written(value)


def _program() -> str:
    """Where the code answering this question is, and whether that is this root's own install.

    One row rather than two. Running from a checkout and running an installed copy are genuinely
    different situations and the difference has to be visible — but when they are the *same* place,
    printing it twice under two labels invites somebody to compare them and find them mismatched,
    which is exactly what happens: one is resolved through symlinks and the other is not.
    """
    running = paths.program()
    return (f"{running} (installed)" if running == paths.app().resolve()
            else f"{running} (a checkout — this root has no install)")


def _backups() -> str:
    """Where the copies are kept, and where they really are once they have been moved elsewhere.

    `set-location` leaves a link behind rather than a second location variable, so this row is the
    only place somebody sees which disk their copies are actually on — and the disk that filled up is
    the reason they came to look.

    A link pointing at nothing is its own answer and not the same as "not there yet": one is an
    install nobody has copied anything on, and the other is copies that were somewhere a moment ago.
    """
    at = paths.backups()
    if not at.is_symlink():
        return _shown(at)
    real = backups.location(at)
    if real.is_dir():
        return f"{at} → {real}"
    return f"{at} → {real} — that directory is not there"


def _agents() -> str:
    """Where the agents stand, and how many of them there are.

    One row rather than two, for the reason `_program` gives about itself: a directory and a count
    printed under two labels are two things somebody compares, and the count is only ever *of* that
    directory. Which agents they are is `rundesk agents`, so the names are not repeated here.

    **"Not there yet", "none yet" and "cannot be read" are three answers, not one.** A root nothing
    has been installed into, an install nobody has added an agent to, and an agents directory that
    is there and unreadable are different situations — and the last is precisely the kind of wrong
    somebody runs `status` to find out about, so it says so rather than reporting no agents.
    """
    at = paths.agents()
    if not at.is_dir():
        return f"{at} — not there yet"
    try:
        there = directory.known()
    except OSError as why:
        return f"{at} — ? — {why}"
    if not there:
        return f"{at} — none yet"
    return f"{at} — {len(there)} agent" + ("" if len(there) == 1 else "s")


def _shown(where: Path) -> str:
    """A path, and whether anything stands there.

    An empty root reads identically to a populated one when only the path is printed, and that is
    exactly the moment somebody needs the difference — a command answering against a directory that
    was never installed into looks like a working install with nothing in it.
    """
    return str(where) if where.exists() else f"{where} — not there yet"


def _unfit() -> str:
    """Why rundesk cannot run here, or `""` when it can.

    One reason today: the interpreter running this. rundesk declares no dependencies, so there is no
    virtualenv to be built for the wrong Python and nothing to be missing from it.
    """
    running = sys.version_info[:2]
    if running < PYTHON_FLOOR:
        floor = ".".join(str(part) for part in PYTHON_FLOOR)
        having = ".".join(str(part) for part in running)
        return f"rundesk needs python{floor} or newer, and this is python{having}"
    return ""
