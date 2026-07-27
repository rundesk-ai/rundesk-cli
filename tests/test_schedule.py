"""What rundesk guarantees about work that starts itself — the rows of platform-schedule.

No clock, no gateway, no process. The time is an argument, so a year of firings is
decided in a millisecond and nothing here waits for anything.
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import schedule  # noqa: E402


def at(said: str) -> datetime:
    """A moment, written the way a person would."""
    return datetime.strptime(said, "%Y-%m-%d %H:%M")


class SayingWhenSomethingRuns(unittest.TestCase):
    def test_a_schedule_is_stated_the_way_schedules_are_ordinarily_stated(self):
        """R-SCH-1 — the vocabulary people already know, so there is nothing to learn."""
        every_minute = schedule.Schedule("all", "* * * * *")
        self.assertTrue(every_minute.due_at(at("2026-07-25 13:37")))

        at_three = schedule.Schedule("nightly", "0 3 * * *")
        self.assertTrue(at_three.due_at(at("2026-07-25 03:00")))
        self.assertFalse(at_three.due_at(at("2026-07-25 03:01")))
        self.assertFalse(at_three.due_at(at("2026-07-25 04:00")))

    def test_a_schedule_says_lists_ranges_and_steps(self):
        """R-SCH-1"""
        cases = [
            ("0,30 * * * *", "2026-07-25 09:30", True),
            ("0,30 * * * *", "2026-07-25 09:31", False),
            ("*/15 * * * *", "2026-07-25 09:45", True),
            ("*/15 * * * *", "2026-07-25 09:46", False),
            ("0 9-17 * * *", "2026-07-25 17:00", True),
            ("0 9-17 * * *", "2026-07-25 18:00", False),
            ("0 0 1 1 *", "2027-01-01 00:00", True),
        ]
        for when, moment, expected in cases:
            with self.subTest(when=when, moment=moment):
                self.assertEqual(expected, schedule.Schedule("x", when).due_at(at(moment)))

    def test_a_day_of_the_week_is_counted_from_sunday(self):
        """R-SCH-1 — the way every other scheduler counts it."""
        sunday = schedule.Schedule("weekly", "0 0 * * 0")
        self.assertTrue(sunday.due_at(at("2026-07-26 00:00")))   # a Sunday
        self.assertFalse(sunday.due_at(at("2026-07-27 00:00")))  # the Monday after
        self.assertTrue(schedule.Schedule("also", "0 0 * * 7").due_at(at("2026-07-26 00:00")))

    def test_a_day_and_a_weekday_together_mean_either_one(self):
        """R-SCH-1 — the one place schedules surprise a reader, and every other
        scheduler agrees: narrow both and either satisfying it is enough. Treating it as
        both would mean a schedule written for any of them never runs at all."""
        first_or_monday = schedule.Schedule("odd", "0 0 1 * 1")
        self.assertTrue(first_or_monday.due_at(at("2026-07-01 00:00")), "the first, a Wednesday")
        self.assertTrue(first_or_monday.due_at(at("2026-07-27 00:00")), "a Monday, not the first")
        self.assertFalse(first_or_monday.due_at(at("2026-07-28 00:00")), "neither")

    def test_whether_a_field_was_narrowed_is_what_was_written_not_what_it_adds_up_to(self):
        """R-SCH-1 — the either/or rule turns on whether a field was left as `*`. Judging
        that by how many values a field ended up allowing cannot tell `*` from a range
        that happens to cover everything, and gets the rule backwards for it."""
        # Both narrowed, so either satisfying it is enough — it runs every day.
        spelled_out = schedule.Schedule("both", "0 0 1-5 * 0-6")
        self.assertTrue(spelled_out.due_at(at("2026-07-10 00:00")), "a Friday, outside 1-5")
        # Only the day narrowed, because the weekday really was left open.
        only_the_day = schedule.Schedule("one", "0 0 1-5 * *")
        self.assertFalse(only_the_day.due_at(at("2026-07-10 00:00")))
        self.assertTrue(only_the_day.due_at(at("2026-07-03 00:00")))
        # A day field written out in full is narrowed too, however many values it holds.
        every_day_written = schedule.Schedule("wide", "0 0 1-31 * 1")
        self.assertTrue(every_day_written.due_at(at("2026-07-10 00:00")), "a Friday, by the day")

    def test_a_schedule_nobody_can_understand_says_so(self):
        """R-SCH-10"""
        for nonsense in ("", "* * * *", "* * * * * *", "99 * * * *", "a * * * *",
                         "*/0 * * * *", "5-1 * * * *", "0 0 32 * *"):
            with self.subTest(when=nonsense):
                with self.assertRaises(schedule.NotASchedule, msg=f"accepted {nonsense!r}"):
                    schedule.Schedule("x", nonsense)


class WhenItNextRuns(unittest.TestCase):
    def test_the_next_time_is_the_next_one_after_now(self):
        """R-SCH-8"""
        nightly = schedule.Schedule("nightly", "0 3 * * *")
        self.assertEqual(at("2026-07-26 03:00"), nightly.next_after(at("2026-07-25 09:00")))
        self.assertEqual(at("2026-07-25 03:00"), nightly.next_after(at("2026-07-25 02:59")))

    def test_the_next_time_is_never_the_moment_asked_about(self):
        """R-SCH-8 — otherwise a schedule that just ran reports itself as due now."""
        every_minute = schedule.Schedule("all", "* * * * *")
        self.assertEqual(at("2026-07-25 09:01"), every_minute.next_after(at("2026-07-25 09:00")))

    def test_the_next_time_of_a_weekly_schedule_is_found(self):
        """R-SCH-8 — a day of the week narrows nothing the search can jump by, so this
        is the one shape that has to be walked rather than skipped to."""
        mondays = schedule.Schedule("weekly", "0 9 * * 1")
        self.assertEqual(at("2026-07-27 09:00"), mondays.next_after(at("2026-07-25 09:00")))
        self.assertEqual(at("2026-08-03 09:00"), mondays.next_after(at("2026-07-27 09:00")))

    def test_a_day_that_only_comes_round_every_few_years_is_still_found(self):
        """R-SCH-8 — the twenty-ninth of February can run. Looking only a year ahead
        would call it never for three years in every four, which is how a working
        schedule comes to be deleted."""
        leap = schedule.Schedule("leap", "0 0 29 2 *")
        self.assertEqual(at("2028-02-29 00:00"), leap.next_after(at("2025-01-01 00:00")))
        self.assertNotEqual("never", schedule.describe(leap, at("2025-01-01 00:00")))

    def test_a_schedule_that_can_never_run_says_never(self):
        """R-SCH-8 — the thirtieth of February is statable and unreachable, and searching
        for it forever is not an answer."""
        self.assertIsNone(schedule.Schedule("impossible", "0 0 30 2 *").next_after(at("2026-07-25 09:00")))
        self.assertEqual("never", schedule.describe(
            schedule.Schedule("impossible", "0 0 30 2 *"), at("2026-07-25 09:00")))

    def test_a_rare_schedule_is_found_without_examining_every_minute(self):
        """R-SCH-12 — once a year is half a million minutes; the search has to cost the
        shape of the schedule rather than the size of the calendar."""
        yearly = schedule.Schedule("yearly", "0 0 1 1 *")
        self.assertEqual(at("2027-01-01 00:00"), yearly.next_after(at("2026-01-02 00:00")))

    def test_a_schedule_that_is_off_says_so_rather_than_a_time(self):
        """R-SCH-11"""
        self.assertEqual("off", schedule.describe(
            schedule.Schedule("paused", "* * * * *", enabled=False), at("2026-07-25 09:00")))


class WhatIsDueRightNow(unittest.TestCase):
    def setUp(self):
        self.every_minute = schedule.Schedule("all", "* * * * *")
        self.nightly = schedule.Schedule("nightly", "0 3 * * *")

    def test_only_what_is_due_is_due(self):
        """R-SCH-2"""
        found = schedule.due([self.every_minute, self.nightly], at("2026-07-25 09:00"))
        self.assertEqual(["all"], [one.name for one in found])

    def test_a_schedule_runs_once_for_the_minute_it_is_due(self):
        """R-SCH-9 — being due is asked several times a minute, and a clock that steps
        backwards asks about a minute that has already run."""
        moment = at("2026-07-25 09:00")
        already = {}
        first = schedule.due([self.every_minute], moment, already)
        self.assertEqual(1, len(first))
        already["all"] = moment
        self.assertEqual([], schedule.due([self.every_minute], moment, already))
        self.assertEqual([], schedule.due([self.every_minute], moment + timedelta(seconds=30), already))
        self.assertEqual(1, len(schedule.due([self.every_minute], moment + timedelta(minutes=1), already)))

    def test_a_clock_stepping_backwards_does_not_run_a_schedule_again(self):
        """R-SCH-9 — a wall clock does not only stand still, it goes backwards: an hour
        repeats every autumn. Asking whether this minute *differs* from the last one lets
        every minute of that hour through, which is an hour of double-firing once a year
        for anything running more often than hourly."""
        every_minute = schedule.Schedule("all", "* * * * *")
        already = {"all": at("2026-11-01 01:59")}
        walked_back = [
            schedule.due([every_minute], at("2026-11-01 01:00") + timedelta(minutes=n), already)
            for n in range(60)
        ]
        self.assertEqual([], [one for found in walked_back for one in found],
                         "the repeated hour ran the schedule all over again")
        # And once the clock is genuinely past where it had got to, it runs again.
        self.assertEqual(1, len(schedule.due([every_minute], at("2026-11-01 02:00"), already)))

    def test_a_schedule_that_is_off_does_not_run(self):
        """R-SCH-11"""
        off = schedule.Schedule("paused", "* * * * *", enabled=False)
        self.assertEqual([], schedule.due([off], at("2026-07-25 09:00")))

    def test_a_time_that_passed_while_nothing_ran_is_not_run_late(self):
        """R-SCH-4 — the whole of it: being due is only ever asked about *now*, so there
        is no backlog anywhere for a restart to work through."""
        was_due_at_three = schedule.due([self.nightly], at("2026-07-25 03:00"))
        self.assertEqual(1, len(was_due_at_three))
        hours_later = schedule.due([self.nightly], at("2026-07-25 09:00"))
        self.assertEqual([], hours_later, "a schedule ran hours after its time")

    def test_what_was_passed_over_can_still_be_counted(self):
        """R-SCH-5 — letting go of a missed run is right; doing it silently is not."""
        hourly = schedule.Schedule("hourly", "0 * * * *")
        self.assertEqual(5, schedule.passed_over(hourly, at("2026-07-25 03:30"), at("2026-07-25 09:00")))
        self.assertEqual(0, schedule.passed_over(hourly, at("2026-07-25 08:30"), at("2026-07-25 08:45")))

    def test_a_very_long_absence_is_counted_up_to_a_point_and_no_further(self):
        """R-SCH-5 — past a certain number, counting further tells nobody anything, and
        a schedule due every minute over a month would count half a million."""
        every_minute = schedule.Schedule("all", "* * * * *")
        counted = schedule.passed_over(every_minute, at("2026-01-01 00:00"), at("2026-07-25 09:00"))
        self.assertEqual(1000, counted)

    def test_deciding_what_is_due_asks_nothing_of_the_machine(self):
        """R-SCH-12 — the time is an argument, so this is decided the same way on any
        machine, at any moment, without waiting."""
        far_future = at("2099-12-31 23:59")
        self.assertEqual(1, len(schedule.due([self.every_minute], far_future)))


class WhatASchedulNames(unittest.TestCase):
    def test_what_a_schedule_names_is_carried_and_never_read(self):
        """R-SCH-3 — the decoupling this rests on. The day a schedule names an agent and
        a task rather than a command, nothing in here changes."""
        for named in (["/bin/echo", "hello"],
                      {"agent": "agent-one", "task": "check the backups"},
                      "anything at all",
                      None):
            with self.subTest(named=named):
                one = schedule.Schedule("x", "* * * * *", run=named)
                self.assertEqual(named, one.run)
                self.assertEqual([one], schedule.due([one], at("2026-07-25 09:00")))


class ReadingWhatAnAgentKeeps(unittest.TestCase):
    def test_schedules_are_read_from_what_was_written(self):
        """R-SCH-1, R-SCH-3 — rows as the store hands them back: `cron` is when, `command`
        is what. This module still knows nothing about where they came from."""
        kept, refused = schedule.read([
            {"name": "nightly", "cron": "0 3 * * *", "command": ["/bin/echo", "hi"]},
            {"name": "paused", "cron": "* * * * *", "enabled": False},
        ])
        self.assertEqual(["nightly", "paused"], [one.name for one in kept])
        self.assertEqual([], refused)
        self.assertEqual(["/bin/echo", "hi"], kept[0].run)
        self.assertFalse(kept[1].enabled)

    def test_one_schedule_nobody_can_understand_leaves_the_others_running(self):
        """R-SCH-10 — a typo in the fourth of five is a reason to say so about the
        fourth, not to leave an agent with nothing scheduled at all."""
        kept, refused = schedule.read([
            {"name": "good", "cron": "0 3 * * *"},
            {"name": "bad", "cron": "not a schedule"},
            {"name": "also good", "cron": "*/5 * * * *"},
        ])
        self.assertEqual(["good", "also good"], [one.name for one in kept])
        self.assertEqual(["bad"], [name for name, _ in refused])

    def test_a_schedule_with_no_name_cannot_be_reported_on_and_is_refused(self):
        """R-SCH-8 — everything about a schedule is reported by its name."""
        kept, refused = schedule.read([{"cron": "* * * * *"}, {"name": "", "cron": "* * * * *"}])
        self.assertEqual([], kept)
        self.assertEqual(2, len(refused))

    def test_something_that_is_not_a_schedule_at_all_is_refused_by_itself(self):
        """R-SCH-10 — a list with a number in it is a mistake about one entry."""
        kept, refused = schedule.read([
            {"name": "good", "cron": "* * * * *"}, 42, "not a schedule", None])
        self.assertEqual(["good"], [one.name for one in kept])
        self.assertEqual(3, len(refused))

    def test_on_or_off_has_to_be_said_as_one_or_the_other(self):
        """R-SCH-11 — every non-empty string is true, so a plausible typo would quietly
        leave a schedule running rather than saying it made no sense."""
        kept, refused = schedule.read([
            {"name": "typo", "cron": "* * * * *", "enabled": "false"},
            {"name": "fine", "cron": "* * * * *", "enabled": False},
        ])
        self.assertEqual(["fine"], [one.name for one in kept])
        self.assertEqual(["typo"], [name for name, _ in refused])

    def test_nothing_written_down_is_no_schedules_rather_than_a_failure(self):
        """R-SCH-10"""
        for nothing in ([], None, "not a list", {}):
            with self.subTest(nothing=nothing):
                self.assertEqual(([], []), schedule.read(nothing))


class ADayAndAWeekdayAgreeWhicheverWayItIsAsked(unittest.TestCase):
    """R-SCH-25 — `due_at`, `next_after` and `passed_over` are three readers of one rule,
    and they disagreed. The matcher implemented cron's either/or correctly; the search that
    finds the *next* occurrence jumped a whole day whenever the day of the month missed,
    without asking whether the weekday had already matched. So the gateway fired on the
    Monday and the NEXT column, and the account of what fell due while nothing ran, both
    said that Monday never existed."""

    #: The 15th at nine, or any Monday at nine. 2026-07-12 is a Sunday, so the 13th is a
    #: Monday and the 15th is the Wednesday after it — one fixture that separates the two.
    BOTH = "0 9 15 * 1"

    def _steps(self, one, moment) -> int:
        """How many jumps the search made. Measured rather than assumed, because the whole
        point of the jump is that it is not a walk."""
        counted = []
        real = schedule._skip
        self.addCleanup(setattr, schedule, "_skip", real)

        def counting(fields, found, anything):
            counted.append(found)
            return real(fields, found, anything)

        schedule._skip = counting
        one.next_after(moment)
        return len(counted)

    def test_the_next_time_is_a_weekday_match_the_day_of_the_month_would_have_skipped(self):
        """R-SCH-25 — the reproduction, as a date a person can check: from the Sunday, the
        next occurrence is the Monday after it and not the fifteenth."""
        both = schedule.Schedule("odd", self.BOTH)
        self.assertTrue(both.due_at(at("2026-07-13 09:00")), "the matcher does fire on the Monday")
        self.assertEqual(at("2026-07-13 09:00"), both.next_after(at("2026-07-12 08:00")))

    def test_a_weekday_match_is_counted_among_what_was_passed_over(self):
        """R-SCH-25 — `passed_over` walks `next_after`, so the missed-run account said
        nothing fell due over a Monday the gateway would have run."""
        both = schedule.Schedule("odd", self.BOTH)
        self.assertEqual(
            1, schedule.passed_over(both, at("2026-07-12 08:00"), at("2026-07-14 00:00")))

    def test_what_is_due_and_what_is_next_agree_on_every_minute_of_a_week(self):
        """R-SCH-25 — the guarantee itself, rather than one date: whatever the matcher says
        yes to is exactly what the search hands back, over every minute in a range."""
        for when in (self.BOTH, "30 9 15 * 1", "0 0 1 * 1", "0 0 1-5 * 0-6", "0 9 15 * *",
                     "0 9 * * 1", "0 9 * * *"):
            with self.subTest(when=when):
                one = schedule.Schedule("x", when)
                begins, ends = at("2026-07-12 00:00"), at("2026-07-20 00:00")
                walked, minute = [], begins
                while minute < ends:
                    if one.due_at(minute):
                        walked.append(minute)
                    minute += timedelta(minutes=1)
                skipped, found = [], begins - timedelta(minutes=1)
                while True:
                    found = one.next_after(found)
                    if found is None or found >= ends:
                        break
                    skipped.append(found)
                self.assertEqual(walked, skipped)

    def test_a_schedule_no_weekday_could_rescue_still_jumps_by_the_day(self):
        """R-SCH-12 — the jump is what keeps a rare schedule from costing half a million
        comparisons, so suppressing it whenever a weekday was written would trade one fault
        for a slower one. It is suppressed only where a weekday match is actually possible."""
        yearly = schedule.Schedule("yearly", "0 0 1 1 *")
        self.assertLess(self._steps(yearly, at("2026-01-02 00:00")), 400,
                        "a yearly schedule was walked rather than jumped to")
        # Both narrowed, and the weekday cannot rescue a day in a month that is out anyway.
        rare = schedule.Schedule("rare", "0 0 1 1 1")
        self.assertLess(self._steps(rare, at("2026-02-01 00:00")), 3000,
                        "a combined schedule was walked minute by minute")


class WhenItRunsOnceAndNeverAgain(unittest.TestCase):
    """R-SCH-36, R-SCH-37 — a schedule that states one moment rather than a repeating time.

    Cron has no year, so `0 9 28 7 *` is every 28 July for ever and one occurrence cannot be
    said in it at all. The moment is the whole difference; everything after it — what it
    starts, where it reports, whether it is off — is the schedule this already was.
    """

    def once(self, said: str = "2026-07-28T09:00", **rest) -> schedule.Schedule:
        return schedule.Schedule("tidy-up", at=said, run=["/bin/tidy"], **rest)

    def test_a_schedule_states_a_repeating_time_or_one_moment_and_never_both(self):
        """R-SCH-36 — refused rather than ranked. A schedule naming both would leave rundesk
        choosing which, and the choice would be invisible in everything that shows it."""
        with self.assertRaises(schedule.NotASchedule) as refused:
            schedule.Schedule("both", "0 9 * * *", at="2026-07-28T09:00")
        self.assertIn("both", str(refused.exception))
        with self.assertRaises(schedule.NotASchedule) as empty:
            schedule.Schedule("neither")
        self.assertIn("neither", str(empty.exception))

    def test_a_moment_is_given_to_the_minute_and_never_as_a_phrase(self):
        """R-SCH-36 — turning *tomorrow at nine* into a time is the caller's job. Language in
        here would be a second thing to keep true, and it would be wrong in the dark."""
        self.assertEqual(at("2026-07-28 09:00"), self.once().stated)
        self.assertEqual(at("2026-07-28 09:00"), self.once("2026-07-28 09:00").stated)
        for said in ("tomorrow at nine", "2026-07-28", "09:00", "28/07/2026 09:00", ""):
            with self.assertRaises(schedule.NotASchedule, msg=said):
                self.once(said)

    def test_a_moment_carrying_a_time_zone_is_refused_rather_than_converted(self):
        """A schedule runs on the machine's own clock, and what it last did is written down
        on that clock too. Quietly reinterpreting somebody's zone would put the two an hour
        apart for part of the year and read perfectly for the rest of it."""
        for said in ("2026-07-28T09:00Z", "2026-07-28T09:00+01:00", "2026-07-28T09:00-05:00"):
            with self.assertRaises(schedule.NotASchedule, msg=said) as refused:
                self.once(said)
            self.assertIn("this machine's own clock", str(refused.exception))

    def test_a_schedule_stating_one_moment_is_due_in_that_minute_and_in_no_other(self):
        """R-SCH-4 inherited rather than re-decided: due only in its own minute means a
        moment that went by while nothing was running is not run late, because there is no
        later minute in which it is ever due."""
        one = self.once()
        self.assertTrue(one.due_at(at("2026-07-28 09:00")))
        self.assertFalse(one.due_at(at("2026-07-28 08:59")))
        self.assertFalse(one.due_at(at("2026-07-28 09:01")))
        self.assertFalse(one.due_at(at("2027-07-28 09:00")), "it came round the next year")

    def test_a_schedule_that_has_run_its_one_moment_can_never_be_due_again(self):
        """R-SCH-37 — and asked of the record rather than of anything held in memory, so a
        gateway that has just come up, one whose clock stepped backwards, and a second one
        starting all get the same answer."""
        used = self.once(ran_at="2026-07-28 09:00")
        self.assertFalse(used.due_at(at("2026-07-28 09:00")), "it ran a second time")
        self.assertEqual([], schedule.due([used], at("2026-07-28 09:00")))
        # Nothing is passed in about what has already run — which is exactly the state a
        # gateway is in on the way up, and the state the old guard could not survive.
        self.assertEqual([], schedule.due([used], at("2026-07-28 09:00"), already={}))
        self.assertIsNone(used.next_after(at("2026-07-27 00:00")))

    def test_a_clock_stepping_backwards_does_not_bring_one_moment_round_again(self):
        """The hour that repeats every autumn, and any correction at all. What refuses this
        is a durable record of the firing, so it refuses whatever the clock says."""
        used = self.once(ran_at="2026-07-28 09:00")
        self.assertFalse(used.due_at(at("2026-07-28 09:00")))
        self.assertTrue(used.expired_at(at("2026-07-28 08:00")),
                        "a clock put back made a schedule that has run wait to run")

    def test_the_next_time_a_schedule_runs_once_is_its_moment_and_then_never(self):
        """R-SCH-8 — every schedule says when it next runs, and one that can never run again
        has to be able to say so rather than naming a time that will not come."""
        one = self.once()
        self.assertEqual(at("2026-07-28 09:00"), one.next_after(at("2026-07-27 09:00")))
        self.assertIsNone(one.next_after(at("2026-07-28 09:00")), "its own minute is not next")
        self.assertIsNone(one.next_after(at("2026-07-29 09:00")))

    def test_a_schedule_is_live_in_the_minute_it_is_due_and_spent_after_it(self):
        """The boundary both ways round: it is not over while it is happening, and it is over
        the moment the clock has passed it — however that came about."""
        one = self.once()
        self.assertFalse(one.expired_at(at("2026-07-28 08:59")))
        self.assertFalse(one.expired_at(at("2026-07-28 09:00")), "it expired while it was due")
        self.assertTrue(one.expired_at(at("2026-07-28 09:01")))
        self.assertTrue(self.once(ran_at="2026-07-28 09:00").expired_at(at("2026-07-28 09:00")),
                        "one that had already run was still shown as waiting to")

    def test_one_that_ran_is_told_apart_from_one_whose_moment_passed_unrun(self):
        """R-SCH-40 — the two ways to be over, and the whole reason this is worth showing at
        all. An owner told only that a schedule is finished cannot tell work that happened
        from work that silently did not."""
        ran = self.once(ran_at="2026-07-28 09:00")
        self.assertEqual("finished", schedule.became_of(ran, "finished"))
        self.assertEqual(schedule.RAN, schedule.became_of(ran, None))
        self.assertEqual(schedule.RAN, schedule.became_of(ran, "  "))
        never = self.once()
        self.assertEqual(schedule.NEVER_RAN, schedule.became_of(never, None))
        self.assertEqual(schedule.NEVER_RAN, schedule.became_of(never, "failed"),
                         "an outcome from somewhere made a schedule that never ran look run")

    def test_a_repeating_schedule_is_never_used_up_however_often_it_has_run(self):
        """The other side of the same claim: `ran_at` says a single moment is spent and says
        nothing at all about a schedule that comes round again."""
        nightly = schedule.Schedule("nightly", "0 3 * * *", ran_at="2026-07-28 03:00")
        self.assertFalse(nightly.once)
        self.assertFalse(nightly.used)
        self.assertFalse(nightly.expired_at(at("2030-01-01 00:00")))
        self.assertTrue(nightly.due_at(at("2026-07-29 03:00")))

    def test_a_schedule_that_runs_once_and_is_off_does_not_run_when_its_moment_comes(self):
        """R-SCH-11 — off is off, whichever way when was said."""
        one = self.once(enabled=False)
        self.assertEqual([], schedule.due([one], at("2026-07-28 09:00")))
        self.assertEqual("off", schedule.describe(one, at("2026-07-27 09:00")))

    def test_when_a_schedule_that_runs_once_next_runs_is_said_as_a_moment_or_as_over(self):
        """R-SCH-8 — read straight into the listing, so what it says is what an owner sees."""
        one = self.once()
        self.assertEqual("2026-07-28 09:00", schedule.describe(one, at("2026-07-27 09:00")))
        self.assertEqual(schedule.EXPIRED, schedule.describe(one, at("2026-07-29 09:00")))
        self.assertEqual(schedule.EXPIRED,
                         schedule.describe(self.once(ran_at="2026-07-28 09:00"),
                                           at("2026-07-27 09:00")))

    def test_a_moment_that_went_by_while_nothing_ran_is_counted_among_what_was_passed_over(self):
        """R-SCH-5 — not run late, and not silent either. A gateway coming up says what fell
        due while it was away, and a single moment is exactly the kind an owner would
        otherwise never learn had been missed."""
        one = self.once()
        self.assertEqual(1, schedule.passed_over(one, at("2026-07-27 00:00"),
                                                 at("2026-07-29 00:00")))
        self.assertEqual(0, schedule.passed_over(one, at("2026-07-29 00:00"),
                                                 at("2026-07-30 00:00")))
        self.assertEqual(0, schedule.passed_over(self.once(ran_at="2026-07-28 09:00"),
                                                 at("2026-07-27 00:00"), at("2026-07-29 00:00")),
                         "one that ran was counted as having been missed")

    def test_what_a_schedule_that_runs_once_names_is_carried_exactly_as_any_other(self):
        """R-SCH-3 — the moment is the only difference. What it starts, which brain, what it
        is told and where it reports are carried past this module unread, as they always are."""
        one = schedule.Schedule("report", at="2026-07-28T09:00", prompt="how did it go?",
                                provider="codex", model="o4", instructions="be terse",
                                channel="ops")
        self.assertEqual(("how did it go?", "codex", "o4", "be terse", "ops"),
                         (one.prompt, one.provider, one.model, one.instructions, one.channel))
        self.assertIsNone(one.run)


class ReadingASingleMomentOffWhatAnAgentKeeps(unittest.TestCase):
    """A row as the store hands it back, which is the only way one ever arrives."""

    def row(self, **rest) -> dict:
        said = {"name": "tidy-up", "cron": None, "at": "2026-07-28 09:00",
                "command": ["/bin/tidy"], "enabled": True}
        said.update(rest)
        return said

    def test_a_schedule_that_runs_once_is_read_back_off_what_the_agent_keeps(self):
        kept, refused = schedule.read([self.row()])
        self.assertEqual([], refused)
        self.assertTrue(kept[0].once)
        self.assertEqual(at("2026-07-28 09:00"), kept[0].stated)
        self.assertEqual(["/bin/tidy"], kept[0].run)

    def test_that_the_clock_started_one_is_carried_off_the_row_and_never_read_as_a_time(self):
        """R-SCH-37 — what makes a moment spent is read on every look, out of the record that
        was written before the work began. Nothing parses it, so no spelling of a minute can
        turn a schedule that has run back into one that has not."""
        kept, _ = schedule.read([self.row(last_auto_run_at="2026-07-28 09:00")])
        self.assertTrue(kept[0].used)
        self.assertEqual([], schedule.due(kept, at("2026-07-28 09:00")))
        # Even written in a way nothing here could parse as a minute.
        odd, _ = schedule.read([self.row(last_auto_run_at="whenever it was")])
        self.assertTrue(odd[0].used, "a firing nobody could read was taken as never having been")
        self.assertEqual([], schedule.due(odd, at("2026-07-28 09:00")))

    def test_a_row_stating_both_a_time_and_a_moment_is_refused_by_itself(self):
        """R-SCH-10 — one schedule nobody can act on leaves every other one running. The
        records refuse this too, so it should not arrive; a row is still a person's typing."""
        kept, refused = schedule.read([
            self.row(name="broken", cron="0 3 * * *"),
            self.row(name="fine"),
        ])
        self.assertEqual(["fine"], [one.name for one in kept])
        self.assertEqual(["broken"], [name for name, _ in refused])


if __name__ == "__main__":
    unittest.main()
