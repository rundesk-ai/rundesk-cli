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
from typing import Any, Iterable, Sequence

#: The five fields a schedule is stated in, in order, and what each may say.
FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("weekday", 0, 7),  # 0 and 7 are both Sunday, as they are everywhere else
)

#: How far ahead to look for the next time a schedule is due before giving up. A year of
#: minutes covers everything statable in five fields; past it, the schedule can never run
#: — `0 0 30 2 *` says the thirtieth of February — and saying so beats searching forever.
LOOK_AHEAD = timedelta(days=366)


class NotASchedule(ValueError):
    """A schedule nobody can act on: what it says cannot be understood."""


@dataclass(frozen=True)
class Schedule:
    """One thing that should happen, and when.

    `run` is whatever the thing doing the starting understands — a command today, an
    agent and a task later. Carried, never looked at (R-SCH-3).
    """

    name: str
    when: str
    run: Any = None
    enabled: bool = True
    _fields: tuple = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_fields", _understand(self.when))

    def due_at(self, moment: datetime) -> bool:
        """Is this schedule due at this exact minute?"""
        return _matches(self._fields, moment)

    def next_after(self, moment: datetime) -> datetime | None:
        """The next minute this is due, after the one given — or None if never again."""
        found = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = moment + LOOK_AHEAD
        while found <= limit:
            if _matches(self._fields, found):
                return found
            found = _skip(self._fields, found)
        return None


def read(said: Any) -> list[Schedule]:
    """Turn what was written down into schedules, keeping the ones that make sense.

    One schedule nobody can understand does not stop the rest (R-SCH-10): a typo in the
    fourth of five is a reason to say so about the fourth, not to leave a machine with
    nothing scheduled at all. What could not be read comes back as its own list.
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
                when=str(one.get("when", "")),
                run=one.get("run"),
                enabled=bool(one.get("enabled", True)),
            ))
        except (NotASchedule, TypeError) as why:
            refused.append((str(name), str(why)))
    return kept, refused


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
        and already.get(one.name) != this_minute
    ]


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
    return tuple(understood)


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


def _matches(fields: tuple, moment: datetime) -> bool:
    """Does this minute satisfy all five fields?

    The one place this differs from what a reader expects: when *both* the day of the
    month and the day of the week are narrowed, either one being satisfied is enough.
    That is what every other scheduler does, and a schedule written for one of them would
    otherwise never run at all.
    """
    minute, hour, day, month, weekday = fields
    if moment.minute not in minute or moment.hour not in hour or moment.month not in month:
        return False
    day_said = len(day) < 31
    weekday_said = len(weekday) < 8
    on_day = moment.day in day
    on_weekday = _weekday(moment) in weekday
    if day_said and weekday_said:
        return on_day or on_weekday
    return on_day and on_weekday


def _weekday(moment: datetime) -> int:
    """Sunday is 0, the way schedules have always said it."""
    return (moment.weekday() + 1) % 7


def _skip(fields: tuple, found: datetime) -> datetime:
    """Jump to the next moment worth examining, rather than trying every minute.

    A schedule due once a year is otherwise half a million comparisons; this makes the
    search cost the shape of the schedule rather than the size of the calendar.
    """
    minute, hour, day, month, _ = fields
    if found.month not in month:
        year, next_month = (found.year + 1, 1) if found.month == 12 else (found.year, found.month + 1)
        return datetime(year, next_month, 1)
    if found.day not in day and len(day) < 31:
        days_in = calendar.monthrange(found.year, found.month)[1]
        if found.day >= days_in:
            year, next_month = (found.year + 1, 1) if found.month == 12 else (found.year, found.month + 1)
            return datetime(year, next_month, 1)
        return datetime(found.year, found.month, found.day) + timedelta(days=1)
    if found.hour not in hour:
        return found.replace(minute=0) + timedelta(hours=1)
    if found.minute not in minute:
        return found + timedelta(minutes=1)
    return found + timedelta(minutes=1)


def describe(one: Schedule, moment: datetime) -> str:
    """When this next runs, said the way a person would ask it."""
    following = one.next_after(moment)
    if not one.enabled:
        return "off"
    if following is None:
        return "never"
    return following.strftime("%Y-%m-%d %H:%M")
