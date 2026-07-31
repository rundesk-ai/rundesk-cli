"""How this install is configured, as opposed to how any one agent is.

Everything else rundesk remembers belongs to an agent and is a row that agent keeps. This
is the other kind: decisions about the install itself, which no agent owns and which must
outlive every one of them. It is one file, `config.json`, and it stands under `data_home()`
— so an ordinary uninstall keeps it, a purge takes it, and a backup contains it, all without
anything here saying so.

**Called configuration and not settings, deliberately.** `settings` already means something
here: what one agent or one channel was told, kept as a row and reached through the store.
A second meaning for the same word is how two people come to be certain they are discussing
the same thing while reading different files.

Backups are the first thing kept here and are not expected to be the last, so the file is
sections at the top level rather than keys — one section per thing configured, and something
added later neither collides with what is here nor makes the reader guess what owns what.

**An owner writes this file by hand**, which is the whole reason it is JSON in the open
rather than a row in a database. So no *reader* here ever writes it back: a reader that
rewrites what it parsed is a reader that eventually reformats somebody's choices away.
Exactly two functions write. `ensure` puts in values an install has never stated and touches
nothing already there; `take_back` removes the untouched configuration the install wrote.

**The file is the source of truth.** The initial values below exist only to write a new
configuration and fill a value an older release never wrote. Runtime readers require the
value in the file; they never fall back around a missing one. A missing or unreadable value
is refused and said out loud, because silently reaching into Python makes `config.json`
untrue about what governs the install (R-STO-13 says the same thing about an agent's
records).
"""

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path

from rundesk import data_home

#: The file, under `data_home()`. Named plainly rather than hidden: an owner is expected to
#: open it, and a dotfile is a file people are not told about.
NAMED = "config.json"

#: What a new configuration says in full (R-INS-19). This is an installation seed, never a
#: runtime fallback: once written, `config.json` is what governs the install. Not every
#: shipped skill belongs here — these four are what every agent needs to work with rundesk.
INITIAL = {
    "backups": {"at": "04:00", "keep_days": 30},
    "updates": {"at": "03:00"},
    "skills": {
        "granted": [
            "managing-rundesk",
            "managing-rundesk-schedules",
            "managing-rundesk-backups",
            "filing-rundesk-issues",
        ]
    },
}

#: Every section this release knows, in the order an owner reads them.
SECTIONS = tuple(INITIAL)


class Unreadable(Exception):
    """There is a config file and it could not be understood. Never treated as absent."""


def path(where: Path | None = None) -> Path:
    """The file this install's configuration is in.

    `where` is the data directory, passed in rather than resolved twice, so a caller that
    is already working against a copy — a restore reading the configuration inside the archive
    it is about to swap in — asks the same question of that copy.
    """
    return (where if where is not None else data_home()) / NAMED


def read(where: Path | None = None) -> dict:
    """Everything this install is configured with, or nothing where it is configured with nothing.

    Refuses rather than defaulting when there is something there it cannot read, and names
    the file, because the one thing an owner cannot debug is a value that was ignored
    without a word.
    """
    at = path(where)
    if not at.is_file():
        return {}
    try:
        said = json.loads(at.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as trouble:
        raise Unreadable(f"{at} could not be read: {trouble}") from trouble
    if not isinstance(said, dict):
        raise Unreadable(f"{at} holds {type(said).__name__} where it must hold an object")
    return said


def backups(where: Path | None = None) -> dict:
    """How backups are configured here, read completely from the file."""
    said = _section("backups", where)
    if not isinstance(said, dict):
        raise Unreadable(f"{path(where)}: 'backups' holds "
                         f"{type(said).__name__} where it must hold an object")
    return {
        "keep_days": _days(_value(said, "backups", "keep_days", where), where),
        "at": _at(_value(said, "backups", "at", where), where, "backups"),
    }


def updates(where: Path | None = None) -> dict:
    """How automatic Rundesk updates are configured, read completely from the file."""
    said = _section("updates", where)
    if not isinstance(said, dict):
        raise Unreadable(f"{path(where)}: 'updates' holds "
                         f"{type(said).__name__} where it must hold an object")
    return {"at": _at(_value(said, "updates", "at", where), where, "updates")}


def skills(where: Path | None = None) -> dict:
    """Which skills every agent is required to hold, read completely from the file.

    This is the install-wide baseline rather than every skill the release ships. A new
    agent receives each one, and the command refuses to revoke one while it remains named
    here (R-AGT-36).
    """
    said = _section("skills", where)
    if not isinstance(said, dict):
        raise Unreadable(f"{path(where)}: 'skills' holds "
                         f"{type(said).__name__} where it must hold an object")
    return {"granted": _granted(_value(said, "skills", "granted", where), where)}


def _granted(said, where) -> tuple[str, ...]:
    """A list of skill names, including an explicitly empty one."""
    if not isinstance(said, list) or any(not isinstance(one, str) for one in said):
        raise Unreadable(f"{path(where)}: 'skills.granted' must be a list of skill names, "
                         f"and is {said!r}")
    return tuple(said)


def ensure(where: Path | None = None) -> list[str]:
    """Put the file there with every effective value, and say which sections changed.

    Run by the install, and again by an update so a file written by an older release grows
    every section and key that release did not know. **Nothing already in the file is
    touched** — not a value, not a section, not a key this release has never heard of. This
    migrates v0.20.0's empty objects into a complete configuration without replacing
    anything an owner filled first (R-UPD-48).
    """
    at = path(where)
    try:
        standing = read(where)
    except Unreadable:
        return []
    changed = []
    for section, values in INITIAL.items():
        if section not in standing:
            standing[section] = copy.deepcopy(values)
            changed.append(section)
            continue
        current = standing[section]
        if not isinstance(current, dict):
            continue
        for key, value in values.items():
            if key not in current:
                current[key] = copy.deepcopy(value)
                if section not in changed:
                    changed.append(section)
    if not changed and at.is_file():
        return []
    if not _write(standing, at):
        return []
    return changed


def rename_skills(changes: dict[str, str], where: Path | None = None) -> list[str]:
    """Carry configured built-in names through an explicit release rename.

    `skills.granted` names identities, not prose. Leaving an old identity there after its
    package and every existing grant moved means new agents silently stop receiving what
    the owner required. Only exact names in release-controlled rename data change; every
    other configured value and unknown section is preserved.
    """
    if not changes:
        return []
    at = path(where)
    try:
        standing = read(where)
    except Unreadable:
        return []
    skills_section = standing.get("skills")
    if not isinstance(skills_section, dict):
        return []
    granted = skills_section.get("granted")
    if not isinstance(granted, list) or any(not isinstance(one, str) for one in granted):
        return []
    carried = []
    changed = []
    for name in granted:
        replacement = changes.get(name, name)
        if replacement != name:
            changed.append(name)
        if replacement not in carried:
            carried.append(replacement)
    if not changed:
        return []
    standing["skills"]["granted"] = carried
    if not _write(standing, at):
        return []
    return changed


def _write(standing: dict, at: Path) -> bool:
    """Write a complete configuration beside the old one and swap it in."""
    ordered = {one: standing[one] for one in SECTIONS if one in standing}
    ordered.update({one: standing[one] for one in standing if one not in SECTIONS})
    coming = at.with_name(f".{NAMED}.coming")
    try:
        at.parent.mkdir(parents=True, exist_ok=True)
        coming.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
        # Swapped in whole. A half-written configuration read at the wrong moment is an
        # owner's choice silently becoming something else.
        coming.replace(at)
    except OSError:
        with contextlib.suppress(OSError):
            coming.unlink()
        return False
    return True


def take_back(where: Path | None = None) -> bool:
    """Take back the unchanged configuration this release wrote.

    **The mirror of `ensure`, and the same rule as a built-in skill's** (R-RM-7): what the
    install put there is the program's and goes with it, and what the owner wrote is theirs
    and stays. The exact initial document is what this release put there; any difference,
    including an unknown key, makes it the owner's and leaves it alone (R-RM-8).
    """
    at = path(where)
    if not at.is_file():
        return False
    try:
        standing = read(where)
    except Unreadable:
        return False
    if standing != INITIAL:
        return False
    try:
        at.unlink()
    except OSError:
        return False
    return True


def _days(said, where) -> int:
    """A number of days — never one that would delete everything.

    `True` is an `int` in Python and would arrive here as one day, so the type is asked
    before the value. Zero and negatives are refused rather than clamped: an owner who wrote
    one meant something, and quietly turning it into the default keeps every backup for ever
    while quietly turning it into a day deletes their history.
    """
    if isinstance(said, bool) or not isinstance(said, int) or said < 1:
        raise Unreadable(f"{path(where)}: 'keep_days' must be a whole number of days "
                         f"of at least one, and is {said!r}")
    return said


def _at(said, where, section: str) -> str:
    """A time of day the machine can be given, stated the way a person writes one."""
    if not isinstance(said, str):
        raise Unreadable(
            f"{path(where)}: '{section}.at' must be a time of day, and is {said!r}"
        )
    hour, _, minute = said.partition(":")
    if not (hour.isdigit() and minute.isdigit()):
        raise Unreadable(
            f"{path(where)}: '{section}.at' must read as HH:MM, and is {said!r}"
        )
    if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        raise Unreadable(
            f"{path(where)}: '{section}.at' is not a time of day: {said!r}"
        )
    return f"{int(hour):02d}:{int(minute):02d}"


def _section(name: str, where) -> object:
    """One required section, never a hidden fallback."""
    configured = read(where)
    if name not in configured:
        raise Unreadable(f"{path(where)}: '{name}' is missing")
    return configured[name]


def _value(section: dict, name: str, key: str, where) -> object:
    """One required value, never a hidden fallback."""
    if key not in section:
        raise Unreadable(f"{path(where)}: '{name}.{key}' is missing")
    return section[key]
