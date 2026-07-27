"""What this install is made of beyond the standard library, and putting it there.

One place decides three things that were previously decided in two, and disagreed: what
`requirements.txt` declares, what the install's own virtualenv actually holds, and how the
second is made to satisfy the first. `install.sh` asked in shell, `gateway.fitness` asked in
Python, and neither could see a version — so a release that bumped one ran against the old
one and nothing anywhere noticed.

**This module imports nothing of rundesk's**, only the standard library. It is called by the
installer through a plain `python3` before there is a virtualenv to speak of, and by an
update that is part-way through replacing every other module here; a broken import anywhere
else must not be able to stop either.

Nothing here reaches the machine's Python. Everything goes into the install's own `.venv`
(R-INS-4), and `run` is an argument so the whole module is exercised without pip.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

#: What a declared requirement is called once it is installed, where the two differ.
IMPORTED_AS = {"discord.py": "discord"}

#: How long to wait on pip before deciding it is not coming back. An update stands every
#: gateway down first, so a build that hangs forever holds an owner's whole machine down.
PIP_SECONDS = 600

#: The comparisons this understands. Deliberately short: satisfying a full specifier is a
#: much larger problem than comparing two release tags, and a narrow answer with an honest
#: refusal is worth more than a broad guess. Anything else is reported as unjudged rather
#: than assumed to fit — see `_satisfied`.
UNDERSTOOD = ("==", ">=")

_LINE = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<rest>.*)$")
_RELEASE = re.compile(r"^\d+(\.\d+)*$")


class Requirement:
    """One line of `requirements.txt`, read as far as this understands it.

    `wanted` is None when the line names no version at all, and `how` is None when it names
    one this cannot judge — extras, markers, a URL, `~=`, or more than one clause. Those two
    are different answers and are never folded together: the first fits whatever is there,
    the second is a question nobody here can answer.
    """

    __slots__ = ("said", "name", "imported", "how", "wanted", "why")

    def __init__(self, said: str, name: str, how: str | None,
                 wanted: str | None, why: str | None = None):
        self.said = said
        self.name = name
        self.imported = IMPORTED_AS.get(name, name.replace("-", "_"))
        self.how = how
        self.wanted = wanted
        self.why = why

    def __repr__(self) -> str:
        return f"Requirement({self.said!r})"


def wanted_at(root: Path, requirements: Path | None = None) -> Path:
    """Which file says what this install needs.

    Its own, unless the caller names another. The installer does, through
    `RUNDESK_REQUIREMENTS`, which is how its suite drives a real install without ever
    reaching a package index — so the override has to reach every part of this, not only
    the part that installs.
    """
    return requirements if requirements is not None else root / "requirements.txt"


def declared(root: Path, requirements: Path | None = None) -> list:
    """What this install says it needs, in the order it says it.

    An unreadable or absent file is nothing needed rather than an error: no requirements
    means no virtualenv is made at all (R-INS-3), which is the state to return to if a
    dependency ever stops earning its place.
    """
    try:
        lines = wanted_at(root, requirements).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    wanted = []
    for line in lines:
        line = line.split("#")[0].strip()
        if not line:
            continue
        wanted.append(_read(line))
    return wanted


def _read(line: str) -> Requirement:
    """One declared line, and how much of it can be judged.

    What cannot be judged is *said*, not silently treated as satisfied. A requirement this
    does not understand and reports as fitting is the same failure as not looking at all,
    with the added cost that somebody believes it was checked.
    """
    said = _LINE.match(line)
    if not said:
        return Requirement(line, line, None, None, "it does not begin with a package name")
    name, rest = said.group("name"), said.group("rest").strip()
    if not rest:
        return Requirement(line, name, None, None)
    for how in UNDERSTOOD:
        if rest.startswith(how):
            asked = rest[len(how):].strip()
            if _RELEASE.match(asked):
                return Requirement(line, name, how, asked)
            # A pre-release, a post-release, a local version or a wildcard. Comparing those
            # correctly is PEP 440's whole problem and this is not the place for it.
            return Requirement(line, name, None, None,
                               f"'{asked}' is not a plain version this can compare")
    return Requirement(line, name, None, None,
                       f"'{rest}' is not a comparison this understands "
                       f"({', '.join(UNDERSTOOD)} only)")


def site_packages(root: Path) -> Path | None:
    """Where this install's own virtualenv keeps what was installed into it.

    None when there is no virtualenv, which is the ordinary state of an install that needs
    nothing. Asked of the directory rather than of `sys.path`, so it answers the same from
    the installer's bare `python3`, from an update part-way through, and from a gateway.
    """
    found = sorted((root / ".venv" / "lib").glob("python3.*/site-packages"))
    return found[-1] if found else None


def installed(root: Path) -> dict:
    """What is actually in the virtualenv, by declared name, with the version it is at.

    Read off the `.dist-info` directories rather than by importing anything. Importing
    answers for whatever is on *this* process's path — which, during an update, is the
    virtualenv as it stood when the process began — and it cannot report a version at all
    without loading the package, which is a great deal of somebody else's code to run in
    order to answer a question about a filename.
    """
    where = site_packages(root)
    if where is None:
        return {}
    held = {}
    for info in sorted(where.glob("*.dist-info")):
        name, _, version = info.name[: -len(".dist-info")].rpartition("-")
        if name:
            held[_normal(name)] = version
    return held


def _normal(name: str) -> str:
    """One spelling for a name pip writes several ways — `discord.py`, `discord_py`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def unsatisfied(root: Path, requirements: Path | None = None) -> list:
    """Every declared requirement this virtualenv does not meet, said in words.

    Empty when everything fits *or* when nothing is declared. A requirement this cannot
    judge is reported here too, saying so — the alternative is an install reporting that it
    fits on the strength of a line nobody read (R-GW-42).
    """
    wanted = declared(root, requirements)
    if not wanted:
        return []
    if site_packages(root) is None:
        return [f"{one.name} is declared and nothing is installed" for one in wanted]
    held = installed(root)
    missing = []
    for one in wanted:
        there = held.get(_normal(one.name))
        if there is None:
            missing.append(f"{one.name} is declared and is not installed")
        elif one.why:
            missing.append(f"{one.name} declares '{one.said}', which cannot be checked here "
                           f"— {one.why}")
        elif one.how and not _satisfied(one, there):
            missing.append(f"{one.name} {one.said.replace(one.name, '', 1).strip()} "
                           f"is declared and {there} is installed")
    return missing


def _satisfied(one: Requirement, there: str) -> bool:
    """Does the version that is there meet the one that was asked for?

    Both are plain dotted releases by the time they reach here — `_read` refuses anything
    else — so this is arithmetic on integers and never a guess. A version that is there but
    is not a plain release is not judged either, and reads as not fitting rather than as
    fitting, because the whole point is to stop a difference going unnoticed.
    """
    if not _RELEASE.match(there or ""):
        return False
    mine, asked = _numbers(there), _numbers(one.wanted or "")
    if one.how == "==":
        return mine == asked
    return mine >= asked


def _numbers(version: str) -> tuple:
    """A dotted release as numbers, padded so `2.7` and `2.7.0` compare equal."""
    parts = [int(part) for part in version.split(".")]
    return tuple(parts + [0] * (3 - len(parts)))[:max(3, len(parts))]


def provision(root: Path, run=None, requirements: Path | None = None) -> str | None:
    """Make this install's virtualenv hold what this install declares.

    Returns None when it does, or a sentence saying why it does not — the same
    returns-rather-than-raises shape `carry` and `pause` already use, because the caller is
    a decision about an update and not a place to handle an exception from pip.

    **What was there is set aside, not destroyed** (R-UPD-28). A build that fails half way
    through leaves a virtualenv that satisfies nothing, and an update whose files have
    already landed would then have neither the old dependencies nor the new — so the old one
    is moved aside, the new one built beside it, and the old one put back if anything goes
    wrong. Only a build that finishes and passes its own check lets go of it.

    `run` is the seam: the suite proves every one of these decisions without pip ever
    running, and without reaching a network.
    """
    asking = run if run is not None else _run
    wanted = wanted_at(root, requirements)
    if not declared(root, requirements):
        # Nothing declared means no virtualenv is made at all (R-INS-3). One left over from
        # a release that *did* declare something is taken away, or an install would go on
        # carrying a dependency no version of it asks for any more.
        return _nothing_needed(root)
    venv = root / ".venv"
    outgoing = root / ".venv.outgoing"
    _discard(outgoing)
    kept = False
    if venv.exists():
        os.rename(venv, outgoing)
        kept = True
    try:
        why = _build(root, venv, wanted, asking, requirements)
    except BaseException:
        _put_back(venv, outgoing, kept)
        raise
    if why:
        _put_back(venv, outgoing, kept)
        return why
    _discard(outgoing)
    return None


def _nothing_needed(root: Path) -> str | None:
    """No requirements: take away a virtualenv an older release left behind."""
    venv = root / ".venv"
    if venv.is_dir() and not venv.is_symlink():
        shutil.rmtree(venv, ignore_errors=True)
    return None


def _build(root: Path, venv: Path, wanted: Path, asking,
           requirements: Path | None = None) -> str | None:
    """Build the virtualenv and prove what landed in it can actually be used."""
    made = asking([sys.executable, "-m", "venv", str(venv)])
    if made:
        return f"could not make the virtualenv rundesk keeps its dependencies in: {made}"
    python = venv / "bin" / "python"
    # The virtualenv's own installer first, as the shell that used to do this always has:
    # what a given Python ships with can be old enough to resolve differently, and an
    # install that resolves differently on two machines is two different products.
    ready = asking([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    if ready:
        return f"could not prepare the virtualenv's installer: {ready}"
    put = asking([str(python), "-m", "pip", "install", "--quiet", "-r", str(wanted)])
    if put:
        return f"could not install what rundesk needs ({wanted}): {put}"
    # Installed is not the same as usable: pip will happily leave a set of packages that
    # cannot satisfy each other, and the failure then arrives as an import error deep inside
    # a dependency, under a supervisor, in a restart loop, hours later.
    fits = asking([str(python), "-m", "pip", "check", "--quiet"])
    if fits:
        return f"what rundesk needs was installed, but the versions do not fit together: {fits}"
    # Asked of the directory rather than taken on trust: pip reporting success and the
    # `.dist-info` saying another version is exactly the difference this exists to catch.
    short = unsatisfied(root, requirements)
    if short:
        return "what was installed is not what is declared: " + "; ".join(short)
    return None


def _run(command: list) -> str | None:
    """Run one program and say what went wrong, or None. The only place this reaches out."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=PIP_SECONDS)
    except OSError as err:
        return str(err)
    except subprocess.TimeoutExpired:
        return f"it did not finish within {PIP_SECONDS} seconds"
    if done.returncode == 0:
        return None
    said = (done.stderr or done.stdout or "").strip().splitlines()
    return said[-1] if said else f"it ended {done.returncode}"


def _put_back(venv: Path, outgoing: Path, kept: bool) -> None:
    """Put back the virtualenv that was working, and take away the one that is not."""
    _discard(venv)
    if kept and outgoing.exists():
        os.rename(outgoing, venv)


def _discard(path: Path) -> None:
    """Remove a virtualenv, whatever state it turned out to be in."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        try:
            path.unlink()
        except OSError:
            pass
