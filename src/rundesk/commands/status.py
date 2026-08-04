"""How rundesk itself is on this machine.

`status` answers *how rundesk is*. What agents there are and what they are doing is `agents`, and
keeping the two apart is deliberate: they are two questions, and one command answering both is a
command nobody can predict the output of. Rows for agents, gateways and backups arrive here when
those parts are rebuilt.
"""

import argparse
import sys

from rundesk import __version__, paths
from rundesk.commands import as_table
from rundesk.exits import FAILED, OK

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
    as_table(("WHAT", "IS"), [
        ("version", __version__),
        ("home", _shown(where)),
        ("program", _shown(paths.program())),
        ("app", _shown(paths.app())),
        ("data", _shown(paths.data())),
        ("fit to run", "yes" if not unfit else f"no — {unfit}"),
    ])
    return FAILED if unfit else OK


def _shown(where) -> str:
    """A path, and whether anything stands there.

    An empty root reads identically to a populated one when only the path is printed, and that is
    exactly the moment somebody needs to be told the difference — a command answering against a
    directory that was never installed into looks like a working install with nothing in it.
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
