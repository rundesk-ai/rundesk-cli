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

import contextlib
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

#: What a new agent is given, when nothing here says otherwise. Not `shipped()`: a release
#: ships more than every agent should carry, and an agent that holds a skill it will never
#: reach for pays for it in the description every brain reads on every turn. These four are
#: what an agent needs to work *with rundesk* — everything else is granted when somebody
#: decides that agent does that job.
GRANTED = (
    "managing-rundesk",
    "managing-rundesk-schedules",
    "managing-rundesk-backups",
    "filing-rundesk-issues",
)

#: Every section this release knows, in the order an owner reads them. What `ensure` writes
#: and what an update adds to a file written before a section existed — the names only, so
#: the values stay here in code and a default improved in a later release still reaches an
#: install that never set one.
SECTIONS = ("backups", "updates", "skills")


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


def skills(where: Path | None = None) -> dict:
    """Which skills a newly made agent is given, with the default applied.

    **What a new agent gets, and never what an existing one gets back.** Nothing records
    that a grant was taken away, so anything reading this at any moment other than the
    making of an agent would hand back, on every update, the skill an owner had just
    revoked (`agent._given_what_ships` says the same thing from the other side).
    """
    said = read(where).get("skills")
    if said is None:
        said = {}
    if not isinstance(said, dict):
        raise Unreadable(f"{path(where)}: 'skills' holds "
                         f"{type(said).__name__} where it must hold an object")
    return {"granted": _granted(said.get("granted"), where)}


def _granted(said, where) -> tuple[str, ...]:
    """A list of skill names, or the default.

    An empty list is honoured rather than read as "said nothing": an owner who wants agents
    made with no skills at all has stated something, and turning it back into four is the
    kind of quiet override this whole file exists to prevent. `None` — the key absent — is
    the one that means the default.
    """
    if said is None:
        return GRANTED
    if not isinstance(said, list) or any(not isinstance(one, str) for one in said):
        raise Unreadable(f"{path(where)}: 'skills.granted' must be a list of skill names, "
                         f"and is {said!r}")
    return tuple(said)


def ensure(where: Path | None = None) -> list[str]:
    """Put the file there, with every section this release knows, and say which were added.

    **Written empty, deliberately.** A section holding `{}` is the shape of what can be set
    without being a value that has been set: an owner opens the file and sees what there is
    to configure, while every default still lives in code, where a later release can improve
    one and have it reach an install that never stated its own. A file written with real
    values in it pins them for ever, and looks correct while doing it.

    Run by the install, and again by an update so a file written before a section existed
    grows the new one. **Nothing already in the file is touched** — not a value, not a
    section, not a key this release has never heard of. An unreadable file is left exactly
    as it is and said out loud by whoever asked for it; rewriting one is how an owner's
    configuration is lost while a command reports success.
    """
    at = path(where)
    try:
        standing = read(where)
    except Unreadable:
        return []
    missing = [one for one in SECTIONS if one not in standing]
    if not missing and at.is_file():
        return []
    for one in missing:
        standing[one] = {}
    ordered = {one: standing[one] for one in SECTIONS if one in standing}
    ordered.update({one: standing[one] for one in standing if one not in SECTIONS})
    coming = at.with_name(f".{NAMED}.coming")
    try:
        at.parent.mkdir(parents=True, exist_ok=True)
        coming.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
        # Swapped in whole. A half-written configuration read at the wrong moment is the
        # value an owner set silently becoming the default.
        coming.replace(at)
    except OSError:
        with contextlib.suppress(OSError):
            coming.unlink()
        return []
    return missing


def take_back(where: Path | None = None) -> bool:
    """Take back a configuration nobody ever wrote anything into, and say whether it went.

    **The mirror of `ensure`, and the same rule as a built-in skill's** (R-RM-7): what the
    install put there is the program's and goes with it, and what the owner wrote is theirs
    and stays. A file whose every section is empty is the skeleton this install wrote and
    nothing else — nobody has stated anything, so there is nothing of theirs to keep, and
    leaving it is what makes a fresh install and an uninstall leave a directory behind
    (R-RM-8).

    One stated value anywhere, one key this release does not know, or a file that cannot be
    read, and it stays exactly as it is. Removing a configuration on the way out is not
    something to be nearly right about.
    """
    at = path(where)
    if not at.is_file():
        return False
    try:
        standing = read(where)
    except Unreadable:
        return False
    if any(one not in SECTIONS or said for one, said in standing.items()):
        return False
    try:
        at.unlink()
    except OSError:
        return False
    return True


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
