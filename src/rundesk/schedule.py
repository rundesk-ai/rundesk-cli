"""Work that starts itself, because the time came.

This module knows three things: what a schedule is, when one is next due, and which are
due at a given moment. It knows nothing else — not what a gateway is, not what a process
is, not what it is that gets started. **What a schedule names is carried and never read**
(R-SCH-3), so the day a schedule names an agent and a task instead of a command, nothing
in here changes.

Two consequences of that worth stating plainly, because they are the design rather than
details of it:

**The time is an argument.** Nothing here asks the machine what time it is (R-SCH-12), so
every case is decided instantly and a year of firings is a test that runs in a
millisecond.

**Nothing is remembered.** What has already run is passed in and handed back, never held.
So a schedule missed while nothing was running is not run late (R-SCH-4) — not because
anything suppresses it, but because being due is only ever asked about *now*, and there
is no backlog anywhere to replay.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

#: The five fields a schedule is stated in, in order, and what each may say.
FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("weekday", 0, 7),  # 0 and 7 are both Sunday, as they are everywhere else
)

#: How far ahead to look for the next time a schedule is due before giving up. Long
#: enough for the rarest date that can actually arrive: the twenty-ninth of February is
#: four years apart, and eight around a century year. A year would call that "never" for
#: three years in every four, which is how a working schedule comes to be deleted. Past
#: this, a schedule genuinely cannot run — `0 0 30 2 *` says the thirtieth of February.
LOOK_AHEAD = timedelta(days=366 * 9)


class NotASchedule(ValueError):
    """A schedule nobody can act on: what it says cannot be understood."""


@dataclass(frozen=True)
class Schedule:
    """One thing that should happen, and when.

    `run` is whatever the thing doing the starting understands — a program, or nothing where
    this schedule asks a turn instead. Carried, never looked at (R-SCH-3).

    `prompt` and the three beside it are the same: what to ask, which brain, which model, and
    what it is told before it reads a word. Every one of them is carried to whatever admits
    the turn and read by nothing here — this module still knows only when.

    **Exactly one of `run` and `prompt` says anything.** That is the records' rule rather than
    this one's, and it is not re-checked here: what arrives is what was written down, and a
    row that broke it could not have been written.
    """

    name: str
    when: str
    run: Any = None
    enabled: bool = True
    prompt: str | None = None
    provider: str | None = None
    model: str | None = None
    instructions: str | None = None
    _fields: tuple = field(default=(), repr=False, compare=False)
    #: Which fields were written as `*`. Kept because "was anything allowed here?" cannot
    #: be answered by counting what a field ended up allowing: `0-6` allows every day of
    #: the week and is not a restriction, but it is one value short of the full set.
    _anything: tuple = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        fields, unrestricted = _understand(self.when)
        object.__setattr__(self, "_fields", fields)
        object.__setattr__(self, "_anything", unrestricted)

    def due_at(self, moment: datetime) -> bool:
        """Is this schedule due at this exact minute?"""
        return _matches(self._fields, moment, self._anything)

    def next_after(self, moment: datetime) -> datetime | None:
        """The next minute this is due, after the one given — or None if never again."""
        found = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = moment + LOOK_AHEAD
        while found <= limit:
            if _matches(self._fields, found, self._anything):
                return found
            found = _skip(self._fields, found, self._anything)
        return None


def read(said: Any) -> list[Schedule]:
    """Turn what an agent keeps into schedules, keeping the ones that make sense.

    Rows as the store hands them back — `cron` is when, and `command` is what — so this
    module still knows nothing about where they came from. It was a list read out of a file
    before that, and the two shapes differ by two key names and nothing else.

    One schedule nobody can understand does not stop the rest (R-SCH-10): a typo in the
    fourth of five is a reason to say so about the fourth, not to leave an agent with
    nothing scheduled at all. What could not be read comes back as its own list. The cron is
    the only part of a row that can be wrong — the shape is the database's now — and it is
    still a person's typing, so it is still refused one row at a time.
    """
    kept, refused = [], []
    for one in said if isinstance(said, list) else []:
        if not isinstance(one, dict):
            refused.append((str(one)[:40], "not a schedule at all"))
            continue
        name = one.get("name")
        try:
            if not isinstance(name, str) or not name.strip():
                raise NotASchedule("a schedule with no name cannot be reported on")
            kept.append(Schedule(
                name=name,
                when=str(one.get("cron", "")),
                run=one.get("command"),
                enabled=_switched(one.get("enabled", True)),
                prompt=one.get("prompt"),
                provider=one.get("provider"),
                model=one.get("model"),
                instructions=one.get("instructions"),
            ))
        except (NotASchedule, TypeError) as why:
            refused.append((str(name), str(why)))
    return kept, refused


def _switched(said: Any) -> bool:
    """On or off, and nothing else. `bool("false")` is True, and a schedules file is
    something a person edits by hand — so a plausible typo would quietly leave a
    schedule running rather than saying it made no sense."""
    if not isinstance(said, bool):
        raise NotASchedule(f"'{said}' is not on or off")
    return said


def due(
    schedules: Iterable[Schedule],
    moment: datetime,
    already: dict[str, datetime] | None = None,
) -> list[Schedule]:
    """Which of these are due right now, given what has already run.

    `already` is the minute each schedule last ran, passed in rather than remembered.
    A schedule runs once for the minute it is due however often this is asked (R-SCH-9),
    which is also what stops a clock stepping backwards from running one twice.
    """
    already = already or {}
    this_minute = moment.replace(second=0, microsecond=0)
    return [
        one for one in schedules
        if one.enabled
        and one.due_at(this_minute)
        and _not_yet(already.get(one.name), this_minute)
    ]


def _not_yet(last: datetime | None, this_minute: datetime) -> bool:
    """Has this schedule still not run for this minute — or any minute since?

    Strictly after, not merely different. A wall clock does not only stand still, it goes
    *backwards*: an hour repeats every autumn, and a correction can step it back at any
    time. Asking whether this minute differs from the last one lets every minute of a
    repeated hour through, which is an hour of double-firing once a year for anything
    that runs more often than hourly (R-SCH-9).
    """
    return last is None or this_minute > last


def passed_over(one: Schedule, since: datetime, moment: datetime) -> int:
    """How many times this would have run between then and now, and did not.

    Nothing acts on this — being due is only ever asked about now, so what is counted
    here has already been let go. It exists so that letting go can be *said* (R-SCH-5)
    rather than being the silence it would otherwise be.
    """
    missed, at = 0, since
    while True:
        at = one.next_after(at)
        if at is None or at >= moment.replace(second=0, microsecond=0):
            return missed
        missed += 1
        if missed >= 1000:
            return missed  # enough to say "a great many"; counting further tells nobody more


# -- understanding what a schedule says ------------------------------------------------

def _understand(when: str) -> tuple:
    """The five fields, each as the set of values it allows (R-SCH-1)."""
    said = (when or "").split()
    if len(said) != len(FIELDS):
        raise NotASchedule(
            f"'{when}' is not a schedule — it needs {len(FIELDS)} parts "
            f"({', '.join(name for name, _, _ in FIELDS)}), and has {len(said)}"
        )
    understood = [
        _values(part, low, high, name)
        for part, (name, low, high) in zip(said, FIELDS)
    ]
    # Seven and zero are the same day. Said in both places by different people, so a
    # schedule written either way has to run on the Sunday it names.
    weekday = understood[-1]
    if 7 in weekday:
        understood[-1] = frozenset(weekday | {0})
    return tuple(understood), tuple(part == "*" for part in said)


def _values(part: str, low: int, high: int, name: str) -> frozenset:
    allowed: set[int] = set()
    for piece in part.split(","):
        step = 1
        if "/" in piece:
            piece, _, said_step = piece.partition("/")
            if not said_step.isdigit() or int(said_step) < 1:
                raise NotASchedule(f"'{said_step}' is not a step for {name}")
            step = int(said_step)
        if piece in ("*", ""):
            first, last = low, high
        elif "-" in piece.lstrip("-"):
            start, _, end = piece.partition("-")
            first, last = _number(start, low, high, name), _number(end, low, high, name)
        else:
            first = last = _number(piece, low, high, name)
        if first > last:
            raise NotASchedule(f"'{piece}' runs backwards for {name}")
        allowed.update(range(first, last + 1, step))
    return frozenset(allowed)


def _number(said: str, low: int, high: int, name: str) -> int:
    if not said.isdigit():
        raise NotASchedule(f"'{said}' is not a number for {name}")
    value = int(said)
    if not low <= value <= high:
        raise NotASchedule(f"{name} is {low} to {high}, and '{said}' is not")
    return value


def _matches(fields: tuple, moment: datetime, anything: tuple) -> bool:
    """Does this minute satisfy all five fields?

    The one place this differs from what a reader expects: when *both* the day of the
    month and the day of the week are narrowed, either one being satisfied is enough.
    That is what every other scheduler does, and a schedule written for one of them would
    otherwise never run at all.
    """
    minute, hour, day, month, weekday = fields
    if moment.minute not in minute or moment.hour not in hour or moment.month not in month:
        return False
    # Written as `*` or not — the only honest way to ask whether a field was narrowed.
    # There was a fallback here that counted values instead, for a caller that cannot
    # happen: every schedule is understood before it is matched, and understanding always
    # yields all five. It was the very heuristic the line above exists to replace.
    day_said, weekday_said = not anything[2], not anything[4]
    on_day = moment.day in day
    on_weekday = _weekday(moment) in weekday
    if day_said and weekday_said:
        return on_day or on_weekday
    return on_day and on_weekday


def _weekday(moment: datetime) -> int:
    """Sunday is 0, the way schedules have always said it."""
    return (moment.weekday() + 1) % 7


def _month_after(found: datetime) -> datetime:
    """The first moment of the month after this one."""
    year, month = (found.year + 1, 1) if found.month == 12 else (found.year, found.month + 1)
    return datetime(year, month, 1)


def _skip(fields: tuple, found: datetime, anything: tuple) -> datetime:
    """Jump to the next moment worth examining, rather than trying every minute.

    A schedule due once a year is otherwise half a million comparisons; this makes the
    search cost the shape of the schedule rather than the size of the calendar.

    **A jump must never step over a minute `_matches` would have said yes to.** When both
    the day of the month and the day of the week are narrowed, either one is enough — so a
    day the day-of-month rules out is only a day to skip if the weekday rules it out too.
    Jumping on the day alone stepped straight over every weekday match: `0 9 15 * 1` fired
    on Mondays in the gateway and was reported by `next_after` as next due on the
    fifteenth, so the runtime and the thing an owner reads to predict it disagreed.
    """
    minute, hour, day, month, weekday = fields
    if found.month not in month:
        return _month_after(found)
    ruled_out = found.day not in day
    # Asked the way `_matches` asks it, off what was written rather than off what a field
    # adds up to — see the comment there.
    if ruled_out and not anything[2] and not anything[4]:
        ruled_out = _weekday(found) not in weekday
    if ruled_out and len(day) < 31:
        if found.day >= calendar.monthrange(found.year, found.month)[1]:
            return _month_after(found)
        return datetime(found.year, found.month, found.day) + timedelta(days=1)
    if found.hour not in hour:
        return found.replace(minute=0) + timedelta(hours=1)
    # Everything a jump can narrow already matches, so what is left is the day of the
    # week — which nothing here can skip to. That one is walked, a minute at a time.
    return found + timedelta(minutes=1)


#: How a minute is written down and read back. One place, because `_remember` writes it and
#: `_pick_up_where_it_left_off` parses it back: change one copy and the parse quietly falls to its
#: `except`, every schedule is taken as never having run, and they all fire again on the minute after a
#: restart — the exact fault R-SCH-9 exists to prevent, with nothing logged to say so.
A_MINUTE = "%Y-%m-%d %H:%M"


def describe(one: Schedule, moment: datetime) -> str:
    """When this next runs, said the way a person would ask it."""
    following = one.next_after(moment)
    if not one.enabled:
        return "off"
    if following is None:
        return "never"
    return following.strftime(A_MINUTE)
