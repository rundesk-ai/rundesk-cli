"""What a schedule says about when it runs, and whether it is due at a given minute.

This module knows three things: what a schedule says, when one is next due, and which of a set are
due at a given moment. It knows nothing else — not what a gateway is, not what a process is, and
**not what it is that gets started**. What a schedule names is carried and never read here, so the
day a schedule names a provider and a prompt instead of a program, nothing in this file changes.

Ported from the build this replaces, where every rule below was arrived at by something going
wrong. Two properties are the design rather than details of it:

**The time is an argument.** Nothing here asks the machine what time it is, so every case is decided
instantly and a year of firings is a test that runs in a millisecond.

**Nothing is remembered.** What has already run is passed in and handed back, never held. So a
schedule whose minute went by while nothing was running is not run late — not because anything
suppresses it, but because being due is only ever asked about *now*, and there is no backlog
anywhere to replay.

## The machine's own clock, deliberately

A schedule is stated in local time and matched against a local clock, and what it last fired for is
written down the same way. `docs/time.md` says a record takes UTC, and this is not an exception to
it: `cron`, `run_at` and `expire_at` are a *statement about the future* rather than a record of
something that happened, and a person who writes `0 9 * * *` means nine o'clock where they are.
What *happened* — `last_run_at`, `created_at` — is UTC in `core.config.MOMENT` like every other
record, written by `kept` and never read here.

The consequence is that a repeated wall-clock hour is something this has to survive rather than
avoid, and `_not_yet` is where that is survived.

May depend on `core` and `utils`, and reads neither today: this is arithmetic over what it is
handed.
"""

import calendar
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple

#: The five fields a schedule is stated in, in order, and what each may say.
FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("weekday", 0, 7),  # 0 and 7 are both Sunday, as they are everywhere else
)

#: How far ahead to look for the next time a schedule is due before giving up. Long enough for the
#: rarest date that can actually arrive: the twenty-ninth of February is four years apart, and eight
#: around a century year. A year would call that "never" for three years in every four, which is how
#: a working schedule comes to be deleted. Past this a schedule genuinely cannot run — `0 0 30 2 *`
#: says the thirtieth of February.
LOOK_AHEAD = timedelta(days=366 * 9)

#: How a single moment is written, and the only spelling there is. Minutes, because that is what a
#: schedule is due in — a moment carrying seconds would name a time the clock is never asked about.
#: `T` between the day and the time, with a space accepted because that is what a person types and
#: refusing it teaches nobody anything.
A_MOMENT = "%Y-%m-%dT%H:%M"
SAID_AS = "YYYY-MM-DDTHH:MM"

#: How a minute is written down and read back, in one place. `kept` writes `last_fired_for` with it
#: and this module parses it back: two copies, and the parse quietly falls to its `except`, every
#: schedule is taken as never having run, and they all fire again on the minute after a restart —
#: with nothing logged to say so.
A_MINUTE = "%Y-%m-%d %H:%M"

#: What a schedule that can never be due again is called, and the two facts that are not the same
#: one. An owner seeing only that a schedule is spent cannot tell work that happened from work that
#: silently did not, which is the question they are actually asking.
EXPIRED = "expired"
OFF = "off"
NEVER = "never"


class NotASchedule(ValueError):
    """A schedule nobody can act on: what it says cannot be understood.

    Raised for one row at a time and never for a set. A typo in the fourth of five schedules is a
    reason to say so about the fourth, not to leave an agent with nothing scheduled at all — which
    is why `read` catches this per row rather than letting it out.
    """


class Schedule(NamedTuple):
    """One thing that should happen, and when.

    **When is said one of two ways, and never both.** `cron` is a repeating time, stated the way
    schedules ordinarily are; `run_at` is a single moment, after which this can never be due again.
    Cron has no year — `0 9 28 7 *` says every 28 July for ever — so a moment cannot be said in the
    first and a repetition cannot be said in the second. The records enforce that with a `CHECK`;
    `understood` asks it again because a row is still a person's typing at the moment it arrives.

    `command` and `prompt` are what to start, and **exactly one of them says anything** — again the
    records' rule, asked here too. Both are carried to whatever starts them and read by nothing
    here: this module still knows only *when*.

    `fired_for` is the minute the clock last claimed this for, carried exactly as `command` is. For
    a schedule stating one moment it is what makes that moment *used*: durable, written before the
    work began, and therefore the same answer through a restart, a clock stepped backwards and a
    second gateway. A repeating schedule ignores it — its guard is the minute passed to `due`.

    `expire_at` is the moment after which this is finished whatever it says. It is the only thing
    that can retire a repeating schedule, and it is read rather than stored as a flag for the reason
    `expired` gives.
    """

    name: str
    cron: Optional[str] = None
    run_at: Optional[str] = None
    expire_at: Optional[str] = None
    enabled: bool = True
    command: Optional[str] = None
    prompt: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    channel: Optional[str] = None
    place: Optional[str] = None
    fired_for: Optional[str] = None
    #: The five fields, each as the set of values it allows. Empty where this states one moment.
    fields: Tuple[frozenset, ...] = ()
    #: Which fields were written as `*`. Kept because "was anything allowed here?" cannot be
    #: answered by counting what a field ended up allowing: `0-6` allows every day of the week and
    #: is not a restriction, but it is one value short of the full set.
    anything: Tuple[bool, ...] = ()
    #: The single moment, understood. `None` where this repeats.
    moment: Optional[datetime] = None
    #: The moment it is finished, understood. `None` where it never expires.
    until: Optional[datetime] = None

    @property
    def once(self) -> bool:
        """Does this run one time and then never again?"""
        return self.moment is not None

    @property
    def used(self) -> bool:
        """Has the one moment this states already been reached and claimed?

        Only of a schedule that states one. A repeating schedule is never used up, however many
        times it has run. Asked of whether anything at all is written rather than of what it says,
        so no spelling of a minute can get this wrong.
        """
        return self.once and bool((self.fired_for or "").strip())


def understood(row: Dict[str, Any]) -> Schedule:
    """One row as the store hands it back, read as a schedule. `NotASchedule` when it cannot be.

    A factory rather than validation inside the type, so that "this row is not a schedule" is an
    answer at one call site instead of an exception that can come out of anywhere a `Schedule` is
    constructed — including out of a test fixture building one by hand.
    """
    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        raise NotASchedule("a schedule with no name cannot be reported on")

    cron = _said(row.get("cron"))
    moment = _said(row.get("run_at"))
    if bool(cron) == bool(moment):
        raise NotASchedule(
            "a schedule says when it runs over and over, or the one moment it runs — "
            + ("and this says both" if cron else "and this says neither"))

    command = _said(row.get("command"))
    prompt = _said(row.get("prompt"))
    if bool(command) == bool(prompt):
        raise NotASchedule(
            "a schedule starts a program, or asks an agent — "
            + ("and this says both" if command else "and this says neither"))

    expire = _said(row.get("expire_at"))
    fields, anything = _understand(cron) if cron else ((), ())
    return Schedule(
        name=name,
        cron=cron or None,
        run_at=moment or None,
        expire_at=expire or None,
        enabled=_switched(row.get("enabled", True)),
        command=command or None,
        prompt=prompt or None,
        provider=_said(row.get("provider_name")) or None,
        model=_said(row.get("model_name")) or None,
        channel=_said(row.get("channel")) or None,
        place=_said(row.get("channel_place_id")) or None,
        fired_for=_said(row.get("last_fired_for")) or None,
        fields=fields,
        anything=anything,
        moment=understood_moment(moment) if moment else None,
        until=understood_moment(expire) if expire else None,
    )


def read(rows: Iterable[Dict[str, Any]]) -> Tuple[List[Schedule], List[Tuple[str, str]]]:
    """Every row that makes sense, and every one that does not with why.

    **One schedule nobody can understand does not stop the rest.** A typo in the fourth of five is a
    reason to say so about the fourth, not to leave an agent with nothing scheduled at all. What
    could not be read comes back as its own list so that a caller can report each of them by name.
    """
    kept: List[Schedule] = []
    refused: List[Tuple[str, str]] = []
    for row in rows:
        try:
            kept.append(understood(row))
        except NotASchedule as why:
            refused.append((str(row.get("name") or "")[:60], str(why)))
    return kept, refused


def due_at(one: Schedule, moment: datetime) -> bool:
    """Is this schedule due at this exact minute?

    A single moment is due in its own minute and in no other — never in one after it, which is what
    makes a moment that passed while nothing was running *not run late* rather than something this
    has to suppress.
    """
    if expired(one, moment):
        return False
    if one.once:
        return moment == one.moment
    return _matches(one.fields, moment, one.anything)


def next_after(one: Schedule, moment: datetime) -> Optional[datetime]:
    """The next minute this is due, after the one given — or `None` if never again."""
    if one.once:
        found = one.moment
        return found if not one.used and found > moment and not expired(one, found) else None
    found = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = moment + LOOK_AHEAD
    if one.until is not None and one.until < limit:
        limit = one.until
    while found <= limit:
        if _matches(one.fields, found, one.anything):
            return found
        found = _skip(one.fields, found, one.anything)
    return None


def expired(one: Schedule, moment: datetime) -> bool:
    """Can this never be due again?

    Three ways, and the first two are the two an owner has to be able to tell apart: the clock
    reached its one moment and started it, or that moment went by while nothing was running and it
    never ran at all. `used` is which. The third is an expiry that has passed, which is the only
    thing that can retire a *repeating* schedule.

    **Derived, never stored.** There is no column saying a schedule is spent, because a column is a
    second answer that can disagree with what happened. A moment is behind us or it is not, and that
    reads the same to a gateway coming up, to one whose clock stepped backwards and to a second one
    starting — none of which can be told a flag.

    Its own minute is not yet behind it: a schedule is live in the minute it is due, which is
    exactly when it runs. The expiry is the other way round and deliberately — `--until` names the
    moment it is finished, so a schedule due at exactly its expiry does not run.
    """
    this_minute = moment.replace(second=0, microsecond=0)
    if one.until is not None and one.until <= this_minute:
        return True
    return one.once and (one.used or one.moment < this_minute)


def due(schedules: Iterable[Schedule], moment: datetime,
        already: Optional[Dict[str, datetime]] = None) -> List[Schedule]:
    """Which of these are due right now, given what has already run.

    `already` is the minute each schedule last ran, passed in rather than remembered. A schedule
    runs once for the minute it is due however often this is asked, which is also what stops a clock
    stepping backwards from running one twice.

    A schedule stating a single moment carries a second guard of its own, in `used`: it is spent the
    moment anything durable says the clock started it. That one does not depend on what is passed in
    here, which is held in memory by whoever is asking and is empty in a gateway that has just come
    up.
    """
    already = already or {}
    this_minute = moment.replace(second=0, microsecond=0)
    return [one for one in schedules
            if one.enabled
            and due_at(one, this_minute)
            and _not_yet(already.get(one.name), this_minute)]


def passed_over(one: Schedule, since: datetime, moment: datetime) -> int:
    """How many times this would have run between then and now, and did not.

    Nothing acts on this — being due is only ever asked about now, so what is counted here has
    already been let go. It exists so that letting go can be *said* rather than being the silence it
    would otherwise be.
    """
    missed, at = 0, since
    while True:
        at = next_after(one, at)
        if at is None or at >= moment.replace(second=0, microsecond=0):
            return missed
        missed += 1
        if missed >= 1000:
            return missed  # enough to say "a great many"; counting further tells nobody more


def describe(one: Schedule, moment: datetime) -> str:
    """When this next runs, said the way a person would ask it.

    Off, expired and never are three different answers and none of them is a time. An owner reading
    a blank column cannot tell a schedule somebody switched off from one whose day of February never
    arrives.
    """
    if not one.enabled:
        return OFF
    if expired(one, moment):
        return EXPIRED
    following = next_after(one, moment)
    if following is None:
        return NEVER
    return following.strftime(A_MINUTE)


def as_minute(moment: datetime) -> str:
    """One minute written the way `last_fired_for` keeps it. The only writer of that spelling."""
    return moment.replace(second=0, microsecond=0).strftime(A_MINUTE)


def from_minute(said: Optional[str]) -> Optional[datetime]:
    """One minute read back off `last_fired_for`, or `None` when it says nothing readable.

    A value nothing can parse comes back as `None` rather than raising, and the caller then treats
    the schedule as never having fired — which risks running it once more, and is the right way for
    this to be wrong. The other way round, a value that could not be read taken as "it already ran"
    is a schedule that silently stops for ever.
    """
    said = (said or "").strip()
    if not said:
        return None
    try:
        return datetime.strptime(said, A_MINUTE)
    except ValueError:
        return None


def understood_moment(said: str) -> datetime:
    """The one moment a schedule states, read off what somebody typed.

    **The machine's own clock, and deliberately.** A schedule is stated in local time and matched
    against a local clock everywhere else here, so a moment kept in any other clock face would be a
    schedule whose stated time and whose record of running sat one column apart in two different
    zones. Wrong by an hour for part of the year, and invisible for the rest of it.

    So a moment carrying a zone is **refused rather than converted**: an owner who wrote one means
    something this cannot honour, and quietly reinterpreting it is worse than saying so. Nothing is
    guessed from words either — *tomorrow at nine* is the caller's to resolve, and natural language
    in here would be a second thing to keep true.
    """
    said = (said or "").strip()
    if said.endswith("Z") or _zoned(said):
        raise NotASchedule(
            f"'{said}' names a time zone, and a schedule runs on this machine's own clock — "
            f"say the local moment, as {SAID_AS}")
    try:
        return datetime.strptime(said.replace(" ", "T", 1), A_MOMENT)
    except ValueError:
        raise NotASchedule(
            f"'{said}' is not a moment — say one as {SAID_AS}, such as 2026-07-28T09:00") from None


# -- understanding what a schedule says ------------------------------------------------


def _said(value: Any) -> str:
    """One column as text, with nothing and whitespace-only reading the same.

    SQLite hands back `None` for a null and the CLI hands over what somebody typed, so a column that
    is set to a run of spaces has to mean the same as one that is not set at all — otherwise `--ask
    "$UNSET"` writes a schedule that says it asks something and asks nothing.
    """
    return "" if value is None else str(value).strip()


def _switched(said: Any) -> bool:
    """On or off, and nothing else.

    `bool("false")` is `True`, and this column can be reached by a hand-edited database — so a
    plausible mistake would quietly leave a schedule running rather than saying it made no sense.
    SQLite's own `0`/`1` are accepted because that is what the `STRICT` column holds.
    """
    if isinstance(said, bool):
        return said
    if isinstance(said, int) and said in (0, 1):
        return bool(said)
    raise NotASchedule(f"'{said}' is not on or off")


def _zoned(said: str) -> bool:
    """Does this carry an offset? Asked of the time only — the date's own hyphens are not one."""
    _, _, clock = said.partition("T" if "T" in said else " ")
    return "+" in clock or "-" in clock


def _understand(when: str) -> Tuple[Tuple[frozenset, ...], Tuple[bool, ...]]:
    """The five fields, each as the set of values it allows."""
    said = when.split()
    if len(said) != len(FIELDS):
        raise NotASchedule(
            f"'{when}' is not a schedule — it needs {len(FIELDS)} parts "
            f"({', '.join(name for name, _, _ in FIELDS)}), and has {len(said)}")
    understood_fields = [_values(part, low, high, name)
                         for part, (name, low, high) in zip(said, FIELDS)]
    # Seven and zero are the same day. Said in both places by different people, so a schedule
    # written either way has to run on the Sunday it names.
    weekday = understood_fields[-1]
    if 7 in weekday:
        understood_fields[-1] = frozenset(weekday | {0})
    return tuple(understood_fields), tuple(part == "*" for part in said)


def _values(part: str, low: int, high: int, name: str) -> frozenset:
    """One field as the whole set of values it allows: lists, ranges and steps, in any combination."""
    allowed = set()
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
    """One value out of a field, refused in the reader's words rather than the parser's.

    Asked with `isdigit` rather than by catching what `int()` raises, and the difference is which
    sentence somebody gets: `int("-5")` succeeds, so a negative would pass this and be refused a line
    later for being out of range — *"minute is 0 to 59, and '-5' is not"* — when what they actually
    typed is not a number for a cron field at all. A range is a thing to correct; a minus sign in a
    field that has never allowed one is a thing to notice.
    """
    if not said.isdigit():
        raise NotASchedule(f"'{said}' is not a number for {name}")
    value = int(said)
    if not low <= value <= high:
        raise NotASchedule(f"{name} is {low} to {high}, and '{said}' is not")
    return value


def _not_yet(last: Optional[datetime], this_minute: datetime) -> bool:
    """Has this schedule still not run for this minute — or any minute since?

    **Strictly after, not merely different.** A wall clock does not only stand still, it goes
    *backwards*: an hour repeats every autumn, and a correction can step it back at any time. Asking
    whether this minute differs from the last one lets every minute of a repeated hour through,
    which is an hour of double-firing once a year for anything that runs more often than hourly.
    """
    return last is None or this_minute > last


def _matches(fields: Tuple[frozenset, ...], moment: datetime, anything: Tuple[bool, ...]) -> bool:
    """Does this minute satisfy all five fields?

    The one place this differs from what a reader expects: when *both* the day of the month and the
    day of the week are narrowed, either one being satisfied is enough. That is what every other
    scheduler does, and a schedule written for one of them would otherwise never run at all.
    """
    minute, hour, day, month, weekday = fields
    if moment.minute not in minute or moment.hour not in hour or moment.month not in month:
        return False
    # Written as `*` or not — the only honest way to ask whether a field was narrowed. A fallback
    # here counted values instead, and it was the very heuristic this line exists to replace: `0-6`
    # allows every weekday there is and is one value short of the full set.
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


def _skip(fields: Tuple[frozenset, ...], found: datetime,
          anything: Tuple[bool, ...]) -> datetime:
    """Jump to the next moment worth examining, rather than trying every minute.

    A schedule due once a year is otherwise half a million comparisons; this makes the search cost
    the shape of the schedule rather than the size of the calendar.

    **A jump must never step over a minute `_matches` would have said yes to.** When both the day of
    the month and the day of the week are narrowed, either one is enough — so a day the day-of-month
    rules out is only a day to skip if the weekday rules it out too. Jumping on the day alone
    stepped straight over every weekday match: `0 9 15 * 1` fired on Mondays in the gateway and was
    reported by `next_after` as next due on the fifteenth, so the runtime and the thing an owner
    reads to predict it disagreed.
    """
    # Unpacked in full, with the one field a jump can never narrow named and unused: a minute is
    # what this walks *to*, so there is nothing to skip to within an hour that already matches.
    _minute, hour, day, month, weekday = fields
    if found.month not in month:
        return _month_after(found)
    ruled_out = found.day not in day
    # Asked the way `_matches` asks it, off what was written rather than off what a field adds up
    # to — see the comment there.
    if ruled_out and not anything[2] and not anything[4]:
        ruled_out = _weekday(found) not in weekday
    if ruled_out and len(day) < 31:
        if found.day >= calendar.monthrange(found.year, found.month)[1]:
            return _month_after(found)
        return datetime(found.year, found.month, found.day) + timedelta(days=1)
    if found.hour not in hour:
        return found.replace(minute=0) + timedelta(hours=1)
    # Everything a jump can narrow already matches, so what is left is the day of the week — which
    # nothing here can skip to. That one is walked, a minute at a time.
    return found + timedelta(minutes=1)
