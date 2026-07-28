"""rundesk — a lightweight, provider-agnostic multi-agent gateway.

The version here is the one source of it: the CLI reports it, the updater compares
against it, and a release tag is expected to match. So is `ROOT`: where this install
actually is, worked out once from a file that is always inside it — and `data_home()`,
which is the other half of the same idea and is deliberately not derived from it.

`backups_home()` is the third of those directories, and the only one an owner may point
off this machine entirely.
"""

from __future__ import annotations

import os
from pathlib import Path

__version__ = "0.15.2"

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


def scripts_home() -> Path:
    """The owner's commands that every agent may invoke.

    Derived below `data_home()` so a redirected or scratch install cannot accidentally
    reach the live owner's commands, and so backup and removal behavior follow from the
    existing data boundary rather than from another list of paths (R-PROC-22, R-PROC-23).
    """
    return data_home() / "scripts"


def skills_home() -> Path:
    """The owner's library of skills, beside the shared integration commands."""
    return data_home() / "skills"


def backups_home() -> Path:
    """Copies of what the owner keeps — the one directory removal may never reach.

    **The third directory, beside `app/` and `data/`.** An update replaces the first and an
    uninstall takes it whole; a purge takes the second as well; nothing takes this one. That
    is the whole point of it: somebody purges because something is wrong, and that is the
    worst possible moment to delete the only copy. Removal is structurally incapable of
    reaching it because nothing in removal ever names it — the same trick `data_home()`
    plays, rather than a list of names to spare.

    **The only one of the three an owner may point off this machine.** `skill.home()` is
    derived downwards from `data_home()` on purpose, so that a second name is not a second
    name to forget; this one cannot be, because pointing backups at iCloud Drive or an
    external disk is the thing it is for. The variable is read here and nowhere else.

    **A directory that syncs changes what can go wrong**, and the two failures are worth
    naming where somebody will read them. A half-written archive may sync, so one is written
    under a temporary name in this same directory and renamed into place — never streamed
    to its final name. And a cloud may evict a file it has uploaded, leaving it present in a
    listing and unreadable without a download, which is why reading one asks rather than
    assumes.

    Resolved on every call and never cached, and falling back through `RUNDESK_INSTALL_DIR`
    exactly as `data_home()` does — so a scratch install redirects its backups with it and a
    suite cannot write into the owner's.
    """
    said = os.environ.get("RUNDESK_BACKUP_DIR")
    if said:
        return Path(said)
    install = os.environ.get("RUNDESK_INSTALL_DIR")
    return Path(install if install else Path.home() / ".rundesk") / "backups"
