"""How this install is configured, as opposed to how any one agent is.

One file — `data/config.json` — holding every install-wide value, and the source of all of them.
It sits under `data/` rather than beside the program, because it is something the owner made: an
update replaces the program and must not be able to reach it.

Two kinds of thing live in it, and they are told apart by who owns them:

**What the owner states** — whether backups are kept and for how long, whether rundesk updates itself
and at what hour. These are edited freely, by hand or by a command, and nothing rundesk does
overwrites a value somebody stated.

**How far the install has been carried** — `migration`, the last migration step applied to this
install. Nobody edits it by hand; the migration runner writes it, and it is here rather than in a
file of its own because "what state is this install in" is one question and deserves one place to
look.

An install writes this file complete. An update **adds values a newer release introduces and changes
nothing already stated** — a release that starts offering a setting must reach installs that predate
it, and an owner who turned something off must find it still off afterwards.
"""

from pathlib import Path
from typing import Any, Optional

from rundesk.core import jsonfile, paths

#: What a fresh install is written with, and the whole list of what an install may be configured with.
#: A key added here reaches existing installs through `fill_in`, which never touches a stated value.
INITIAL = {
    # Copies of what the owner keeps.
    "backup_enabled": True,
    "backup_retention": 7,

    # Keeping this copy of rundesk current.
    "update_enabled": True,
    "update_time": "03:00",

    # How far this install has been carried. Written by the migration runner, never by hand.
    "migration": None,
}

#: The one value nobody states, so `fill_in` can leave the owner's alone and still manage this.
MANAGED = ("migration",)

#: What each stated value has to look like, in the words somebody would use to correct it.
WANTED = {
    "backup_enabled": "yes or no",
    "backup_retention": "how many copies to keep, a whole number of at least 1",
    "update_enabled": "yes or no",
    "update_time": "a time of day as HH:MM, such as 03:00",
}

_YES = ("yes", "true", "on", "1")
_NO = ("no", "false", "off", "0")


def settable():
    """Every value somebody may state, in a settled order.

    Walked off `INITIAL` rather than listed, so a value a release starts offering is configurable the
    day it lands. `MANAGED` values are not here: `migration` is how far the install has been carried,
    and a person setting it by hand would make rundesk skip or repeat a step.
    """
    return [key for key in sorted(INITIAL) if key not in MANAGED]


def understood(key: str, said: str):
    """What a typed value means, or `Refused` saying what was wanted instead.

    Checked here rather than where it was typed, because the answer belongs to whoever owns the
    setting: a command that parsed its own booleans would be a second opinion about what `off` means.
    """
    if key not in INITIAL:
        raise Refused(f"{key} is not a value rundesk is configured with")
    wanted = INITIAL[key]
    given = said.strip()

    if isinstance(wanted, bool):
        if given.lower() in _YES:
            return True
        if given.lower() in _NO:
            return False
    elif isinstance(wanted, int):
        try:
            settled = int(given)
        except ValueError:
            settled = None
        if settled is not None and settled >= 1:
            return settled
    elif key == "update_time":
        if _a_time_of_day(given):
            return given
    else:
        if given:
            return given

    raise Refused(f"{key} wants {WANTED.get(key, 'a value')}, and was given {said!r}")


def _a_time_of_day(said: str) -> bool:
    """Whether this is `HH:MM` on a twenty-four hour clock."""
    hours, _, minutes = said.partition(":")
    if not (hours.isdigit() and minutes.isdigit()) or len(minutes) != 2 or len(hours) > 2:
        return False
    return 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59


class Refused(Exception):
    """A value that may not be set, or may not be set to that."""


def where(data: Optional[Path] = None) -> Path:
    """The configuration file, below the install's data."""
    return (data or paths.data()) / "config.json"


def read(data: Optional[Path] = None) -> dict:
    """Every effective value, with anything a newer release added filled in from `INITIAL`.

    Filled in **for the read only** — asking how rundesk is configured never writes. A release that
    added a setting answers for it immediately; the file catches up the next time something changes
    it, or at the next update.
    """
    how, said = jsonfile.read(where(data))
    if how == jsonfile.UNREADABLE:
        raise Unreadable(f"{where(data)} is there and cannot be read")
    settled = dict(INITIAL)
    if how == jsonfile.READ and isinstance(said, dict):
        settled.update(said)
    return settled


def write_fresh(data: Optional[Path] = None) -> dict:
    """Write the configuration a new install starts with, and refuse to flatten one already there.

    Installing over an existing install must not reset what its owner stated, so this writes only
    when there is nothing to write over; otherwise it fills in and leaves the rest alone.
    """
    at = where(data)
    if at.exists():
        return fill_in(data)
    jsonfile.write(at, dict(INITIAL))
    return dict(INITIAL)


def fill_in(data: Optional[Path] = None) -> dict:
    """Add values this release knows about and the file does not. Change nothing already stated.

    What an update calls. The asymmetry is the whole point: a missing key is this release offering
    something the file predates, and a present key is somebody's answer — including a `false` that
    looks exactly like a default nobody set.
    """
    at = where(data)
    with jsonfile.changing(at, empty={}) as held:
        settled = dict(held[0]) if isinstance(held[0], dict) else {}
        for key, value in INITIAL.items():
            settled.setdefault(key, value)
        held[0] = settled
        return dict(settled)


def stated(key: str, value: Any, data: Optional[Path] = None) -> None:
    """Set one value, leaving every other exactly as it was."""
    if key not in INITIAL:
        raise Refused(f"{key} is not a value rundesk is configured with")
    with jsonfile.changing(where(data), empty=dict(INITIAL)) as held:
        settled = dict(held[0]) if isinstance(held[0], dict) else dict(INITIAL)
        settled[key] = value
        held[0] = settled


class Unreadable(Exception):
    """The configuration is there and cannot be understood.

    Raised rather than defaulted. Treating an unreadable file as an unwritten one would answer every
    question with the factory setting — so an owner who turned automatic updates off would find them
    on again, and nothing would have said so.
    """
