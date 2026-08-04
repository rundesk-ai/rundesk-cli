"""How rundesk itself is on this machine.

`status` answers *how rundesk is*: which version, which root answered, whether it is installed, how
far it has been carried, and whether it can run here. What agents there are and what they are doing
is a different question and will be a different command.
"""

import argparse
import sys

from rundesk import __version__
from rundesk.commands import as_table
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import migration

#: The oldest Python a fresh macOS ships, which is the floor everything here is written against.
PYTHON_FLOOR = (3, 9)


def cmd_status(_args: argparse.Namespace) -> int:
    """Print what rundesk is and where it keeps things; exit non-zero when it could not run.

    Takes no flags — a question with one answer does not need shaping.
    """
    try:
        where = paths.home()
    except paths.Refused as why:
        print(f"status: FAILED — {why}", file=sys.stderr)
        return FAILED

    unfit = _unfit()
    rows = [
        ("version", __version__),
        ("home", _shown(where)),
        ("program", _program()),
        ("data", _shown(paths.data())),
        ("backups", _shown(paths.backups())),
        ("projects", _shown(paths.projects())),
        ("fit to run", "yes" if not unfit else f"no — {unfit}"),
    ]
    rows.extend(_configured())
    as_table(("WHAT", "IS"), rows)
    return FAILED if unfit else OK


def _configured():
    """Every value this install is configured with, read from its own configuration.

    Walked off `config.read` rather than named here, so a value a release starts offering is shown
    the day it lands — a hand-kept list of settings is a list that quietly stops being complete.
    """
    try:
        settled = config.read(paths.data())
    except config.Unreadable as why:
        return [("config", f"? — {why}")]
    return [(key, _readably(key, settled[key])) for key in sorted(settled)]


def _readably(key: str, value) -> str:
    """One configured value as a person reads it.

    `migration` is the one nobody states, so it says what it means rather than printing a bare id or
    an unexplained `None`.
    """
    if key == "migration":
        ships = migration.newest()
        if ships is None:
            return "nothing to carry — this release ships no migration steps"
        if value is None:
            return f"not carried yet (this release ships up to {ships})"
        return str(value) if value == ships else f"{value} (this release ships up to {ships})"
    if value is None:
        return "not yet"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


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


def _shown(where) -> str:
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
