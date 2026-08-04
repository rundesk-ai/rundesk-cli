"""Placing the program, replacing it, and taking it away.

Three operations on one directory — `app/` — plus the one link that puts `rundesk` on a PATH.
Install, update and uninstall all act through here, which is what keeps them agreeing about what an
install is made of.

Two things this module is careful about, both because getting them wrong is expensive:

**Replacing is staged, then renamed.** Every entry of the new release is copied in beside the old one
under a `.incoming` name, and only when all of them are there does anything move. What was there is
renamed aside rather than deleted, and is put back if any part of the swap fails — so a release that
half-landed leaves the install on the version it was, not on neither.

**Removing only ever takes what an install placed.** The link is removed only when it points into
this install's own `app/`, and `app/` is removed only when it does not look like somebody's
checkout. An uninstall that deletes a link belonging to a different program, or a source tree
somebody was working in, has done something it cannot undo.
"""

import os
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from rundesk.core import paths

#: What the command is called wherever it is put on a PATH.
COMMAND = "rundesk"

#: Where the link goes when nobody says otherwise, in the order they are tried.
BIN_DIRS = ("/usr/local/bin", "~/.local/bin")

_INCOMING = ".{name}.incoming"
_OUTGOING = ".{name}.outgoing"


class Refused(Exception):
    """Something that must not be done to this machine, named with why."""


class HalfReplaced(Exception):
    """A swap failed and putting back what was there failed too.

    Its own exception because there is no clever recovery: the install is neither the old release nor
    the new one, and the only honest thing to say is that it must be installed again.
    """


def place(from_where: Path, root: Optional[Path] = None) -> Path:
    """Put the program at `app/`, replacing whatever is there. Returns where it landed.

    The same operation whether this is the first install or an update — an install that is a special
    case of itself is an install with a path nobody exercises.
    """
    into = (root or paths.home()) / "app"
    _check(from_where)
    if into.exists():
        return replace(from_where, into)
    into.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(from_where, into, symlinks=True, ignore=_never_copied)
    return into


def replace(from_where: Path, app: Path) -> Path:
    """Swap the program for a new one, and put the old one back if any part of it fails."""
    _check(from_where)
    staged: List[Path] = []
    swapped: List[Path] = []
    try:
        for entry in sorted(from_where.iterdir()):
            if _never_copied(str(entry.parent), [entry.name]):
                continue
            pending = app / _INCOMING.format(name=entry.name)
            _discard(pending)
            if entry.is_dir() and not entry.is_symlink():
                shutil.copytree(entry, pending, symlinks=True, ignore=_never_copied)
            else:
                shutil.copy2(entry, pending, follow_symlinks=False)
            staged.append(pending)

        for pending in staged:
            target = app / pending.name[1:-len(".incoming")]
            if target.exists() or target.is_symlink():
                aside = app / _OUTGOING.format(name=target.name)
                _discard(aside)
                os.rename(target, aside)
                swapped.append(target)
            os.rename(pending, target)
    except Exception:
        _put_back(app, swapped)
        for pending in staged:
            _discard(pending)
        raise

    for target in swapped:
        _discard(app / _OUTGOING.format(name=target.name))
    return app


def link(app: Path, bin_dir: Optional[Path] = None) -> Path:
    """Put `rundesk` on a PATH, and refuse to write over something that is not ours.

    A file of the same name that is not a link, or a link pointing at another program, belongs to
    somebody else. Refused rather than replaced: the install would otherwise silently take over a
    command that was already working.
    """
    where = Path(bin_dir).expanduser() if bin_dir else _a_bin_dir()
    where.mkdir(parents=True, exist_ok=True)
    at = where / COMMAND
    if at.is_symlink():
        if not _ours(at, app):
            raise Refused(f"{at} is a link to {os.readlink(at)}, which is not this install")
    elif at.exists():
        raise Refused(f"{at} already exists and is not a link — rundesk will not write over it")
    if at.is_symlink() or at.exists():
        at.unlink()
    at.symlink_to(app / COMMAND)
    return at


def unlink(app: Path, bin_dirs: Optional[Sequence[str]] = None) -> List[Path]:
    """Remove every PATH link that points into this install. Returns what was removed.

    Checked rather than assumed, one link at a time. Two installs on one machine is an ordinary
    thing, and removing one must leave the other's command working.
    """
    removed = []
    for where in (bin_dirs if bin_dirs is not None else BIN_DIRS):
        at = Path(where).expanduser() / COMMAND
        if at.is_symlink() and _ours(at, app):
            at.unlink()
            removed.append(at)
    return removed


def remove(app: Path) -> None:
    """Take the program away, refusing anything that looks like somebody's own work."""
    if not app.exists():
        return
    if (app / ".git").exists():
        raise Refused(f"{app} is a git checkout — rundesk will not delete somebody's own work")
    shutil.rmtree(app)


def _ours(at: Path, app: Path) -> bool:
    """Whether a link points at the command inside this install's own `app/`."""
    try:
        return Path(os.readlink(at)).resolve() == (app / COMMAND).resolve()
    except OSError:
        return False


def _a_bin_dir() -> Path:
    """The first directory on the list this machine will let us write to."""
    for said in BIN_DIRS:
        where = Path(said).expanduser()
        if where.is_dir() and os.access(where, os.W_OK):
            return where
    return Path(BIN_DIRS[-1]).expanduser()


def _check(from_where: Path) -> None:
    """Refuse a source that is not a rundesk tree, before anything is copied anywhere."""
    if not (from_where / COMMAND).is_file() or not (from_where / "src" / "rundesk").is_dir():
        raise Refused(f"{from_where} does not look like rundesk — it has no {COMMAND} and src/rundesk")


def _never_copied(_where: str, names: Iterable[str]) -> Set[str]:
    """What is never part of an install, whatever is in the tree it was built from."""
    unwanted = {".git", "__pycache__", ".scratch", "node_modules", ".venv",
                "src_old", "tests_old", "docs_old", ".knowledge_old", "old", "ui", "site"}
    return {name for name in names if name in unwanted or name.endswith(".pyc")}


def _put_back(app: Path, swapped: List[Path]) -> None:
    """Undo a half-finished swap, newest first."""
    for target in reversed(swapped):
        aside = app / _OUTGOING.format(name=target.name)
        try:
            _discard(target)
            os.rename(aside, target)
        except OSError as why:
            raise HalfReplaced(
                f"{target} could not be put back ({why}) — this install is part-replaced "
                "and must be installed again") from why


def _discard(where: Path) -> None:
    """Remove a staging entry, whatever kind it is. Never used on anything an owner keeps."""
    if where.is_dir() and not where.is_symlink():
        shutil.rmtree(where, ignore_errors=True)
    elif where.exists() or where.is_symlink():
        try:
            where.unlink()
        except OSError:
            pass
