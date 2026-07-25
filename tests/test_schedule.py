"""What rundesk guarantees about work that starts itself — the rows of platform-schedule.

No clock, no gateway, no process. The time is an argument, so a year of firings is
decided in a millisecond and nothing here waits for anything.
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import schedule  # noqa: E402


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


class ReadingWhatWasWrittenDown(unittest.TestCase):
    def test_schedules_are_read_from_what_was_written(self):
        """R-SCH-1, R-SCH-3"""
        kept, refused = schedule.read([
            {"name": "nightly", "when": "0 3 * * *", "run": ["/bin/echo", "hi"]},
            {"name": "paused", "when": "* * * * *", "enabled": False},
        ])
        self.assertEqual(["nightly", "paused"], [one.name for one in kept])
        self.assertEqual([], refused)
        self.assertEqual(["/bin/echo", "hi"], kept[0].run)
        self.assertFalse(kept[1].enabled)

    def test_one_schedule_nobody_can_understand_leaves_the_others_running(self):
        """R-SCH-10 — a typo in the fourth of five is a reason to say so about the
        fourth, not to leave a machine with nothing scheduled at all."""
        kept, refused = schedule.read([
            {"name": "good", "when": "0 3 * * *"},
            {"name": "bad", "when": "not a schedule"},
            {"name": "also good", "when": "*/5 * * * *"},
        ])
        self.assertEqual(["good", "also good"], [one.name for one in kept])
        self.assertEqual(["bad"], [name for name, _ in refused])

    def test_a_schedule_with_no_name_cannot_be_reported_on_and_is_refused(self):
        """R-SCH-8 — everything about a schedule is reported by its name."""
        kept, refused = schedule.read([{"when": "* * * * *"}, {"name": "", "when": "* * * * *"}])
        self.assertEqual([], kept)
        self.assertEqual(2, len(refused))

    def test_something_that_is_not_a_schedule_at_all_is_refused_by_itself(self):
        """R-SCH-10 — a list with a number in it is a mistake about one entry."""
        kept, refused = schedule.read([
            {"name": "good", "when": "* * * * *"}, 42, "not a schedule", None])
        self.assertEqual(["good"], [one.name for one in kept])
        self.assertEqual(3, len(refused))

    def test_nothing_written_down_is_no_schedules_rather_than_a_failure(self):
        """R-SCH-10"""
        for nothing in ([], None, "not a list", {}):
            with self.subTest(nothing=nothing):
                self.assertEqual(([], []), schedule.read(nothing))


if __name__ == "__main__":
    unittest.main()
