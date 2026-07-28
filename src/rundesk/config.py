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
rather than a row in a database. So nothing here ever writes it back: a reader that rewrites
what it parsed is a reader that eventually reformats somebody's comments away, and a
half-written file read at the wrong moment is how the value they set silently becomes the
default.

**Missing is not the same as unreadable.** A file that is not there is an owner who never
wrote one, and every default applies. A file that is there and cannot be understood is
refused and said out loud, because treating it as absent means running on defaults an owner
believes they overrode — which they only discover when a backup they thought was kept for a
year has gone (R-STO-13 says the same thing about an agent's records).
"""

from __future__ import annotations

import json
from pathlib import Path

from rundesk import data_home

#: The file, under `data_home()`. Named plainly rather than hidden: an owner is expected to
#: open it, and a dotfile is a file people are not told about.
NAMED = "config.json"

#: How long a backup is kept before the next one prunes it. A default rather than a law —
#: this is the name the requirement cites, and the number lives only here.
KEEP_DAYS = 30

#: When the machine takes the daily one, on its own local clock, as a person states a time.
#: Early enough to be finished before a working day, late enough not to collide with the
#: nightly schedules an agent is likely to have.
DAILY_AT = "04:00"

#: When the machine checks for a new Rundesk release, on its own local clock.
UPDATE_AT = "03:00"


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
    """How backups are configured here, with every default already applied.

    One place decides both the defaults and what a stated value may be, so the command that
    takes a backup, the job the machine runs and the pruning that follows can never disagree
    about how long "kept" is.
    """
    said = read(where).get("backups")
    if said is None:
        said = {}
    if not isinstance(said, dict):
        raise Unreadable(f"{path(where)}: 'backups' holds "
                         f"{type(said).__name__} where it must hold an object")
    return {
        "keep_days": _days(said.get("keep_days"), where),
        "at": _at(said.get("at"), where, "backups"),
    }


def updates(where: Path | None = None) -> dict:
    """How automatic Rundesk updates are configured, with the default applied."""
    said = read(where).get("updates")
    if said is None:
        said = {}
    if not isinstance(said, dict):
        raise Unreadable(f"{path(where)}: 'updates' holds "
                         f"{type(said).__name__} where it must hold an object")
    return {"at": _at(said.get("at"), where, "updates", UPDATE_AT)}


def _days(said, where) -> int:
    """A number of days, or the default — never a number that would delete everything.

    `True` is an `int` in Python and would arrive here as one day, so the type is asked
    before the value. Zero and negatives are refused rather than clamped: an owner who wrote
    one meant something, and quietly turning it into the default keeps every backup for ever
    while quietly turning it into a day deletes their history.
    """
    if said is None:
        return KEEP_DAYS
    if isinstance(said, bool) or not isinstance(said, int) or said < 1:
        raise Unreadable(f"{path(where)}: 'keep_days' must be a whole number of days "
                         f"of at least one, and is {said!r}")
    return said


def _at(said, where, section: str, default: str = DAILY_AT) -> str:
    """A time of day the machine can be given, stated the way a person writes one."""
    if said is None:
        return default
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
