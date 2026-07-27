"""rundesk — a lightweight, provider-agnostic multi-agent gateway.

The version here is the one source of it: the CLI reports it, the updater compares
against it, and a release tag is expected to match. So is `ROOT`: where this install
actually is, worked out once from a file that is always inside it — and `data_home()`,
which is the other half of the same idea and is deliberately not derived from it.
"""

from __future__ import annotations

import os
from pathlib import Path

__version__ = "0.7.0"

#: This install — the directory holding `rundesk`, `src/` and the virtualenv. Resolved
#: rather than assumed, because the command is reached through a symlink on a PATH and
#: the checkout it points into is what an update replaces.
ROOT = Path(__file__).resolve().parent.parent.parent


def data_home() -> Path:
    """Everything the owner keeps, in one directory that the program is never inside.

    **The program and the data are two directories, not one.** `app/` is what an update
    replaces and an uninstall takes away whole; this is everything beside it, and removal
    is then structurally incapable of reaching it rather than remembering a list of names
    to spare (R-INS-13, R-RM-8, R-RM-12).

    **Not derived from `ROOT`**, which is the trap worth naming: from a checkout the
    installer symlinks the checkout itself, so `ROOT` is wherever a developer keeps their
    source while their agents still belong under their home. Data is resolved from the
    home, and the program from the file it is in, because they genuinely are two questions.

    **An install pointed somewhere else keeps its data there too.** `RUNDESK_INSTALL_DIR`
    moves the whole install, and data that stayed under the person's home while the program
    moved would be an install that is not one directory but two — and a scratch install
    built to test one would quietly read and write what the real one has. That is not
    hypothetical: it is what this resolver did on its first draft, and the install suite
    caught it by finding a `~/.rundesk` it had never asked for.

    Resolved on every call and never cached: where an owner keeps things is machine state,
    and binding it once at import is how a suite comes to write into the real one.
    """
    said = os.environ.get("RUNDESK_DATA_DIR")
    if said:
        return Path(said)
    install = os.environ.get("RUNDESK_INSTALL_DIR")
    return Path(install if install else Path.home() / ".rundesk") / "data"
