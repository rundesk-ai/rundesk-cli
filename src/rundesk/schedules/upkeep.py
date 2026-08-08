"""Automatic per-agent upkeep after seven distinct dates on which that agent was used.

This is a usage cadence rather than cron. A protected schedule row gives the work the mature
schedule lifecycle — a kernel claim, durable start record, child adoption, output, settlement and
final-only reporting — while this module alone decides when it is eligible.
"""

import datetime
import os
from typing import Dict, List, NamedTuple, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rundesk.agents import directory, records
from rundesk.core import config
from rundesk.schedules import due, firing, kept

NAME = kept.UPKEEP
DATES_REQUIRED = 7


class Activity(NamedTuple):
    """The distinct local usage dates after the last upkeep attempt."""

    dates: tuple

    @property
    def days(self) -> int:
        return len(self.dates)


class Window(NamedTuple):
    """One frozen evidence interval and the prompt that owns it."""

    start: str
    end: str
    days: int
    prompt: str


def activity(agent: str, zone=None) -> Activity:
    """Qualifying dates for this agent, never another, after its latest upkeep attempt.

    A settled turn means the agent was used even when it failed or was stopped; those are often the
    most useful evidence. Working turns have not happened yet. The upkeep turn itself never counts.
    Local dates match the owner's lived day, while the durable timestamps stay UTC as every record
    in this product does.
    """
    zone = zone if zone is not None else _local_zone()
    with records.reading(directory.records(agent)) as conn:
        managed = conn.execute(
            "SELECT last_run_at FROM schedules WHERE name = ? AND provider_name = ?",
            (NAME, kept.UPKEEP_PROVIDER)).fetchone()
        boundary = str(managed["last_run_at"]) if managed and managed["last_run_at"] else None
        sql = ("SELECT ended_at FROM turns WHERE ended_at IS NOT NULL "
               "AND turn_status IN ('done', 'failed', 'stopped') "
               "AND (schedule_name IS NULL OR schedule_name <> ?)")
        values: List[object] = [NAME]
        if boundary is not None:
            sql += " AND ended_at > ?"
            values.append(boundary)
        sql += " ORDER BY ended_at, id"
        rows = conn.execute(sql, values).fetchall()
    dates = sorted({_local_day(str(row["ended_at"]), zone) for row in rows})
    return Activity(tuple(dates))


def window(agent: str, zone=None) -> Optional[Window]:
    """The upkeep now owed, or ``None`` while disabled, busy, or short of seven dates."""
    with records.reading(directory.records(agent)) as conn:
        configured = conn.execute("SELECT self_improve FROM config WHERE id = 1").fetchone()
        if configured is None or not bool(configured["self_improve"]):
            return None
        if conn.execute("SELECT 1 FROM turns WHERE turn_status = 'working' LIMIT 1").fetchone():
            return None
    used = activity(agent, zone)
    if used.days < DATES_REQUIRED:
        return None
    start, end = used.dates[0], used.dates[-1]
    return Window(start, end, used.days, _prompt(start, end, used.days))


def prepared(agent: str, prompt: str, when: Optional[datetime.datetime] = None) -> Dict[str, object]:
    """Prepare the protected row. Public for deterministic tests and the gateway seam."""
    return kept.prepared_upkeep(agent, prompt, when)


def looked(agent: str, where, watching: firing.Watching,
           asking: firing.Starting, telling: Optional[firing.Telling] = None,
           moment: Optional[datetime.datetime] = None) -> firing.Watching:
    """Start one eligible upkeep through the ordinary schedule lifecycle. Never raises."""
    try:
        wanted = window(agent)
        if wanted is None:
            return watching
        row = prepared(agent, wanted.prompt, moment)
        one = due.understood(row)._replace(enabled=True)
        # **The minute this row already claimed is the guard, and nothing was reading it.**
        # `_fired` writes `last_fired_for` durably before it spawns, exactly so a firing survives a
        # restart and a second gateway — but a cron schedule's due check is what reads it back, and
        # eligibility here is decided by `window` instead, which reads neither.
        #
        # So the only thing standing between two beats and two upkeep runs was `window`'s *is any
        # turn working* question, and that answers **no** for the whole gap between spawning the
        # child and the child writing its own turn row. On the gateway's ordinary beat that gap is
        # narrow; measured on a loaded machine at a fifty-millisecond beat it let three runs of one
        # window start inside a second. The two guards are complementary and both are needed: this
        # one covers the spawn gap, and `working` covers a run that outlives its minute.
        now = moment if moment is not None else datetime.datetime.now()
        if one.fired_for and one.fired_for == due.as_minute(now):
            return watching
        return firing.managed(agent, where, watching, one, moment=moment,
                              asking=asking, telling=telling)
    except Exception as why:  # noqa: BLE001 — a bad account must not end a working gateway.
        firing.noted_once(where, watching, "weekly-self-improve-upkeep", f"agent upkeep could not start: {why}")
        return watching


def state(agent: str, zone=None) -> Dict[str, object]:
    """The protected schedule's owner-facing effective state."""
    with records.reading(directory.records(agent)) as conn:
        configured = conn.execute("SELECT self_improve FROM config WHERE id = 1").fetchone()
        row = conn.execute("SELECT * FROM schedules WHERE name = ?", (NAME,)).fetchone()
    used = activity(agent, zone)
    on = bool(configured and configured["self_improve"])
    conflict = row is not None and row["provider_name"] != kept.UPKEEP_PROVIDER
    managed = None if conflict else row
    remaining = max(0, DATES_REQUIRED - used.days)
    try:
        running = firing.still_running(agent, NAME)
    except OSError:
        running = False
    following = ("running" if running else
                 "off" if not on else
                 "due" if not remaining else
                 f"after {remaining} more usage dates")
    return {"enabled": on, "days": used.days, "remaining": remaining,
            "conflict": conflict,
            "next": following, "running": running,
            "last_outcome": managed["last_outcome"] if managed else None,
            "last_run_at": managed["last_run_at"] if managed else None}


def _local_day(stamp: str, zone) -> str:
    """One stored UTC moment as the machine-local calendar date chosen for this evaluation."""
    at = datetime.datetime.strptime(stamp, config.MOMENT).replace(tzinfo=datetime.timezone.utc)
    return at.astimezone(zone).date().isoformat()


def _local_zone() -> datetime.tzinfo:
    """The machine's transition-aware timezone, not today's fixed UTC offset.

    ``datetime.now().astimezone().tzinfo`` is only the offset in force today. Reusing it for a
    historical winter turn while the machine is on summer time can move a near-midnight turn onto
    the wrong usage date. ``TZ`` is the process's explicit answer when present; otherwise the
    system tzfile carries the same historical transition rules without adding a dependency.
    """
    named = os.environ.get("TZ", "").lstrip(":")
    if named:
        try:
            return ZoneInfo(named)
        except (ValueError, ZoneInfoNotFoundError):
            pass
    try:
        with open("/etc/localtime", "rb") as local:
            return ZoneInfo.from_file(local)
    except (OSError, ValueError):
        return datetime.datetime.now().astimezone().tzinfo


def _prompt(start: str, end: str, days: int) -> str:
    """The hard-coded task. Timing is supplied; the brain never calculates or guesses it."""
    return (
        "Perform this agent's automatic upkeep with the granted managing-rundesk skill. "
        f"Evidence interval (inclusive): {start} through {end}, covering {days} distinct usage "
        f"dates. Diary date: {end}; use `retros/{end}.md`. "
        "Work sequentially: (1) read only the maintenance reference, complete workspace and "
        "continuity maintenance, and verify every change and preservation; (2) only then read the "
        "retrospective reference, compare the previous entry and bounded public history, MUST write "
        f"and reread `retros/{end}.md` with exactly `## What went well`, "
        "`## What did not go well`, and `## What to improve`; (3) only then read the "
        "self-improvement reference and finish its evidence and solution review. For each material "
        "friction, identify the smallest durable, token- and cost-efficient route across memory or "
        "indexes, a verified agent-owned script, an existing or proposed skill, a materially better "
        "named specialist, or a provider-local research helper. When material friction has an "
        "independent heavy research question and provider helpers are available, MUST launch at "
        "least one and synthesize its result; otherwise record why none qualifies. Evaluate named "
        "agents only through public Rundesk surfaces, never their homes or memory. Apply and verify "
        "every safe authorized local improvement now; any script is incomplete until a post-edit "
        "fixture matrix covers each documented input type and error branch, including missing, "
        "unreadable file, unreadable directory, and direct symlink inputs; otherwise name the "
        "exact owner decision and reason. Before final, prove the diary exists "
        "with all three headings, reread every changed artifact, verify every requested phase and "
        "improvement, and prove no task scratch remains. Throughout every phase, never open a "
        "symlink or its target; inspect only link metadata and target spelling. Anything unverified "
        "is blocked, not done. "
        "Return exactly one short attention-first sentence and no audit detail: either "
        "`Upkeep completed — no owner action is needed.` or "
        "`Upkeep needs attention — <the owner action and its reason>.`")
