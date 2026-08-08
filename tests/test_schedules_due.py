"""When a schedule is due, and when it is not.

Every case here is arithmetic. The clock is an argument, so a year of firings is decided in a
millisecond and nothing waits for a minute to arrive — which is the whole reason `schedules.due`
asks nothing of the machine.

**The rules that look wrong are the ones with the most expensive history**, and each of them has a
case saying so out loud: a day and a weekday together mean *either*, whether a field was narrowed is
what was written rather than what it adds up to, and a minute that has already fired is refused with
a strict `>` rather than a `!=`.

Nothing here touches the disk, so `support.Isolated` buys nothing — but every suite inherits it, and
a suite that opted out would be the one that later grew a case that did touch the disk.

Run directly: `python3 tests/test_schedules_due.py`
"""

import unittest
from datetime import datetime, timedelta

import support
from rundesk.schedules import due


def a_row(**also):
    """One row as the store hands it back. Built by hand, never through the product's own writer.

    A fixture built by the code under test is a fixture that agrees with a bug in it — so this
    spells out the column names the way SQLite would.
    """
    row = {"name": "nightly", "enabled": 1, "cron": "* * * * *", "run_at": None,
           "expire_at": None, "command": "/bin/echo hello", "prompt": None,
           "provider_name": None, "model_name": None, "channel": None,
           "channel_place_id": None, "last_fired_for": None}
    row.update(also)
    return row


def a_schedule(**also):
    return due.understood(a_row(**also))


class WhatASchedulesSays(support.Isolated):
    """Reading five fields off what somebody typed."""

    def test_a_schedule_is_stated_the_way_schedules_are_ordinarily_stated(self):
        one = a_schedule(cron="30 9 * * *")
        self.assertTrue(due.due_at(one, datetime(2026, 8, 5, 9, 30)))
        self.assertFalse(due.due_at(one, datetime(2026, 8, 5, 9, 31)))

    def test_a_schedule_says_lists_ranges_and_steps(self):
        cases = [
            ("0,30 * * * *", datetime(2026, 8, 5, 4, 30), True),
            ("0,30 * * * *", datetime(2026, 8, 5, 4, 15), False),
            ("0 9-17 * * *", datetime(2026, 8, 5, 17, 0), True),
            ("0 9-17 * * *", datetime(2026, 8, 5, 18, 0), False),
            ("*/15 * * * *", datetime(2026, 8, 5, 4, 45), True),
            ("*/15 * * * *", datetime(2026, 8, 5, 4, 46), False),
            ("0 0 1,15 * *", datetime(2026, 8, 15, 0, 0), True),
        ]
        for said, moment, wanted in cases:
            with self.subTest(cron=said, at=moment):
                self.assertEqual(wanted, due.due_at(a_schedule(cron=said), moment))

    def test_a_day_of_the_week_is_counted_from_sunday(self):
        # Sunday is 0 and 7 in every other scheduler there is, so a schedule written either way has
        # to run on the Sunday it names — otherwise half the world's crontabs are silently wrong.
        sunday = datetime(2026, 8, 9, 12, 0)
        self.assertEqual(6, sunday.weekday(), "the fixture is not a Sunday")
        for said in ("0 12 * * 0", "0 12 * * 7"):
            with self.subTest(weekday=said):
                self.assertTrue(due.due_at(a_schedule(cron=said), sunday))

    def test_a_day_and_a_weekday_together_mean_either_one(self):
        # What every other scheduler does. A schedule written for one of them would otherwise never
        # run at all, which is the kind of wrong nobody notices for a month.
        one = a_schedule(cron="0 9 15 * 1")
        a_monday = datetime(2026, 8, 3, 9, 0)
        self.assertEqual(0, a_monday.weekday(), "the fixture is not a Monday")
        self.assertTrue(due.due_at(one, a_monday), "the weekday alone should be enough")
        self.assertTrue(due.due_at(one, datetime(2026, 8, 15, 9, 0)), "the day alone should be enough")

    def test_a_day_and_a_weekday_are_both_required_when_only_one_was_narrowed(self):
        one = a_schedule(cron="0 9 15 * *")
        self.assertTrue(due.due_at(one, datetime(2026, 8, 15, 9, 0)))
        self.assertFalse(due.due_at(one, datetime(2026, 8, 3, 9, 0)))

    def test_whether_a_field_was_narrowed_is_what_was_written_not_what_it_adds_up_to(self):
        # `0-6` allows every weekday there is, so counting values would call it unrestricted — and
        # it is one value short of the full set, which is how the counting heuristic answered `*`
        # and `0-6` differently for no reason a reader could see.
        one = a_schedule(cron="0 9 15 * 0-6")
        self.assertTrue(due.due_at(one, datetime(2026, 8, 3, 9, 0)),
                        "0-6 is a narrowed weekday, so either the day or the weekday is enough")

    def test_a_schedule_nobody_can_understand_says_so(self):
        cases = [
            ("* * * *", "needs 5 parts"),
            ("60 * * * *", "minute is 0 to 59"),
            ("* 24 * * *", "hour is 0 to 23"),
            ("* * 0 * *", "day is 1 to 31"),
            ("* * * 13 *", "month is 1 to 12"),
            ("* * * * 8", "weekday is 0 to 7"),
            ("9-5 * * * *", "runs backwards"),
            ("*/0 * * * *", "is not a step"),
            ("nine * * * *", "is not a number"),
        ]
        for said, _why in cases:
            with self.subTest(cron=said):
                with self.assertRaises(due.NotASchedule):
                    a_schedule(cron=said)

    def test_a_schedule_that_says_when_two_ways_is_refused_and_so_is_one_that_says_neither(self):
        with self.assertRaisesRegex(due.NotASchedule, "says both"):
            a_schedule(cron="* * * * *", run_at="2026-08-05T09:00")
        with self.assertRaisesRegex(due.NotASchedule, "says neither"):
            a_schedule(cron=None, run_at=None)

    def test_a_schedule_that_names_what_to_start_two_ways_is_refused_and_so_is_one_that_names_neither(self):
        with self.assertRaisesRegex(due.NotASchedule, "says both"):
            a_schedule(command="/bin/echo hi", prompt="review the queue")
        with self.assertRaisesRegex(due.NotASchedule, "says neither"):
            a_schedule(command=None, prompt=None)

    def test_a_column_of_nothing_but_space_says_nothing(self):
        # `--ask "$UNSET"` writes a run of spaces, and a schedule that says it asks something and
        # asks nothing is one that fires for ever having no work to do.
        with self.assertRaisesRegex(due.NotASchedule, "says neither"):
            a_schedule(command="   ")

    def test_a_schedule_with_no_name_cannot_be_reported_on(self):
        for said in (None, "", "  "):
            with self.subTest(name=said):
                with self.assertRaises(due.NotASchedule):
                    a_schedule(name=said)

    def test_on_or_off_has_to_be_said_as_one_or_the_other(self):
        # `bool("false")` is True, and this column is reachable by a hand-edited database.
        for said in ("false", "yes", 2, None):
            with self.subTest(enabled=said):
                with self.assertRaises(due.NotASchedule):
                    a_schedule(enabled=said)

    def test_what_a_schedule_names_is_carried_and_never_read(self):
        # The whole point of the design: `due` decides *when*, and the kind of work is somebody
        # else's branch. So a schedule asking an agent is understood exactly as one naming a program.
        one = a_schedule(command=None, prompt="review the queue", provider_name="claude")
        self.assertEqual("review the queue", one.prompt)
        self.assertEqual("claude", one.provider)
        self.assertTrue(due.due_at(one, datetime(2026, 8, 5, 9, 0)))


class WhenItNextRuns(support.Isolated):
    """`next_after`, which is what an owner reads to predict a schedule."""

    def test_the_next_time_is_never_the_moment_asked_about(self):
        # A schedule due every minute asked at 09:00 next runs at 09:01. Answering 09:00 would have
        # every listing say a schedule is due right now, for ever.
        one = a_schedule(cron="* * * * *")
        self.assertEqual(datetime(2026, 8, 5, 9, 1), due.next_after(one, datetime(2026, 8, 5, 9, 0)))

    def test_the_next_time_of_a_weekly_schedule_is_found(self):
        one = a_schedule(cron="0 9 * * 1")
        found = due.next_after(one, datetime(2026, 8, 5, 12, 0))
        self.assertEqual(datetime(2026, 8, 10, 9, 0), found)
        self.assertEqual(0, found.weekday())

    def test_a_day_that_only_comes_round_every_few_years_is_still_found(self):
        # The twenty-ninth of February. A one-year look-ahead calls this "never" three years in
        # four, which is how a working schedule comes to be deleted by somebody tidying up.
        one = a_schedule(cron="0 0 29 2 *")
        self.assertEqual(datetime(2028, 2, 29, 0, 0), due.next_after(one, datetime(2026, 8, 5, 9, 0)))

    def test_a_schedule_that_can_never_run_says_never(self):
        one = a_schedule(cron="0 0 30 2 *")            # the thirtieth of February
        self.assertIsNone(due.next_after(one, datetime(2026, 8, 5, 9, 0)))
        self.assertEqual(due.NEVER, due.describe(one, datetime(2026, 8, 5, 9, 0)))

    def test_the_next_time_is_a_weekday_match_the_day_of_the_month_would_have_skipped(self):
        # The jump has to agree with the match. `_skip` on the day alone stepped over every weekday
        # match, so the gateway fired on Mondays while the listing said the fifteenth — the runtime
        # and the thing an owner reads to predict it disagreed, and neither was obviously wrong.
        one = a_schedule(cron="0 9 15 * 1")
        found = due.next_after(one, datetime(2026, 8, 1, 0, 0))
        self.assertEqual(datetime(2026, 8, 3, 9, 0), found)
        self.assertEqual(0, found.weekday())

    def test_what_is_due_and_what_is_next_agree_on_every_minute_of_a_week(self):
        # The property that catches a `_skip` which jumps over a match: walk a whole week a minute
        # at a time and require that every minute `due_at` says yes to is one `next_after` predicts,
        # and that nothing between two predictions is due.
        one = a_schedule(cron="0 9 15 * 1")
        at = datetime(2026, 8, 1, 0, 0)
        ending = at + timedelta(days=7)
        walked = [at + timedelta(minutes=n) for n in range(int((ending - at).total_seconds()) // 60)]
        matched = [minute for minute in walked if due.due_at(one, minute)]
        predicted, cursor = [], at - timedelta(minutes=1)
        while True:
            cursor = due.next_after(one, cursor)
            if cursor is None or cursor >= ending:
                break
            predicted.append(cursor)
        self.assertEqual(matched, predicted)

    def test_a_rare_schedule_is_found_without_examining_every_minute(self):
        # Once a year is half a million comparisons walked a minute at a time. Not timed — a timing
        # assertion is a flaky assertion — but a suite that hangs here is the symptom, and the
        # answer being right at all is what proves the jump did not step over it.
        one = a_schedule(cron="0 0 1 1 *")
        self.assertEqual(datetime(2027, 1, 1, 0, 0), due.next_after(one, datetime(2026, 8, 5, 9, 0)))


class OneMomentAndNoMore(support.Isolated):
    """A schedule that states a single moment, which is a different thing from a rare cron."""

    def test_a_moment_is_given_to_the_minute_and_never_as_a_phrase(self):
        one = a_schedule(cron=None, run_at="2026-08-05T09:00")
        self.assertEqual(datetime(2026, 8, 5, 9, 0), one.moment)
        for said in ("tomorrow at nine", "2026-08-05", "09:00", "the fifth"):
            with self.subTest(at=said):
                with self.assertRaises(due.NotASchedule):
                    a_schedule(cron=None, run_at=said)

    def test_a_space_between_the_day_and_the_time_is_what_a_person_types(self):
        one = a_schedule(cron=None, run_at="2026-08-05 09:00")
        self.assertEqual(datetime(2026, 8, 5, 9, 0), one.moment)

    def test_a_moment_carrying_a_time_zone_is_refused_rather_than_converted(self):
        # An owner who wrote one means something this cannot honour, and quietly reinterpreting it
        # is worse than saying so: it would be wrong by an hour for part of the year and invisible
        # for the rest of it.
        for said in ("2026-08-05T09:00Z", "2026-08-05T09:00+02:00", "2026-08-05T09:00-04:00"):
            with self.subTest(at=said):
                with self.assertRaisesRegex(due.NotASchedule, "time zone"):
                    a_schedule(cron=None, run_at=said)

    def test_a_moment_is_due_in_its_own_minute_and_in_no_other(self):
        one = a_schedule(cron=None, run_at="2026-08-05T09:00")
        self.assertTrue(due.due_at(one, datetime(2026, 8, 5, 9, 0)))
        self.assertFalse(due.due_at(one, datetime(2026, 8, 5, 8, 59)))
        self.assertFalse(due.due_at(one, datetime(2026, 8, 5, 9, 1)))

    def test_a_moment_that_passed_while_nothing_ran_is_not_run_late(self):
        # Not because anything suppresses it: being due is only ever asked about *now*, and there is
        # no backlog anywhere to replay. A gateway coming up after a weekend does not fire Friday's.
        one = a_schedule(cron=None, run_at="2026-08-05T09:00")
        self.assertFalse(due.due_at(one, datetime(2026, 8, 7, 9, 0)))
        self.assertTrue(due.expired(one, datetime(2026, 8, 7, 9, 0)))

    def test_a_schedule_that_has_run_its_one_moment_can_never_be_due_again(self):
        one = a_schedule(cron=None, run_at="2026-08-05T09:00", last_fired_for="2026-08-05 09:00")
        self.assertTrue(one.used)
        self.assertFalse(due.due_at(one, datetime(2026, 8, 5, 9, 0)))
        self.assertIsNone(due.next_after(one, datetime(2026, 8, 5, 8, 0)))

    def test_a_moment_whose_firing_cannot_be_read_back_as_a_time_is_still_spent(self):
        # `used` asks whether anything at all is written, never what it says — so no spelling of a
        # minute can make a schedule that has already fired come round again.
        one = a_schedule(cron=None, run_at="2026-08-05T09:00", last_fired_for="who knows")
        self.assertTrue(one.used)
        self.assertFalse(due.due_at(one, datetime(2026, 8, 5, 9, 0)))

    def test_one_that_ran_is_told_apart_from_one_whose_moment_passed_unrun(self):
        # Both are expired and they are not the same news: an owner seeing only "spent" cannot tell
        # work that happened from work that silently did not.
        ran = a_schedule(cron=None, run_at="2026-08-05T09:00", last_fired_for="2026-08-05 09:00")
        never = a_schedule(cron=None, run_at="2026-08-05T09:00")
        later = datetime(2026, 8, 7, 9, 0)
        self.assertTrue(due.expired(ran, later))
        self.assertTrue(due.expired(never, later))
        self.assertTrue(ran.used)
        self.assertFalse(never.used)


class RunningOnceForTheMinuteItIsDue(support.Isolated):
    """The guard that survives a restart and a clock that moves backwards."""

    def test_a_schedule_runs_once_for_the_minute_it_is_due(self):
        one = a_schedule(cron="* * * * *")
        at = datetime(2026, 8, 5, 9, 0)
        self.assertEqual([one], due.due([one], at, {}))
        self.assertEqual([], due.due([one], at, {"nightly": at}))

    def test_a_clock_stepping_backwards_does_not_run_a_schedule_again(self):
        # **The reason it is `>` and not `!=`.** A wall clock repeats an hour every autumn, so
        # asking whether this minute *differs* from the last lets every minute of that hour through
        # — an hour of double-firing once a year for anything running more often than hourly.
        one = a_schedule(cron="* * * * *")
        already = {"nightly": datetime(2026, 11, 1, 1, 30)}
        self.assertEqual([], due.due([one], datetime(2026, 11, 1, 1, 0), already),
                         "a minute before the last one fired is not a minute to fire again")
        self.assertEqual([one], due.due([one], datetime(2026, 11, 1, 1, 31), already))

    def test_only_what_is_due_is_due(self):
        every_minute = a_schedule(name="tick", cron="* * * * *")
        at_nine = a_schedule(name="nine", cron="0 9 * * *")
        found = due.due([every_minute, at_nine], datetime(2026, 8, 5, 10, 0), {})
        self.assertEqual(["tick"], [one.name for one in found])

    def test_a_schedule_that_is_off_does_not_run(self):
        one = a_schedule(enabled=0)
        self.assertEqual([], due.due([one], datetime(2026, 8, 5, 9, 0), {}))
        self.assertEqual(due.OFF, due.describe(one, datetime(2026, 8, 5, 9, 0)))

    def test_a_schedule_that_is_off_says_so_rather_than_a_time(self):
        # An owner reading a next-due time beside a schedule that is switched off is an owner
        # waiting for something that is never going to happen.
        one = a_schedule(enabled=0, cron="0 9 * * *")
        self.assertEqual(due.OFF, due.describe(one, datetime(2026, 8, 5, 9, 0)))


class ASetTimeFrameThatRunsOut(support.Isolated):
    """`expire_at` — the only thing that can retire a repeating schedule."""

    def test_a_repeating_schedule_stops_at_its_expiry(self):
        one = a_schedule(cron="* * * * *", expire_at="2026-08-05T10:00")
        self.assertTrue(due.due_at(one, datetime(2026, 8, 5, 9, 59)))
        self.assertFalse(due.due_at(one, datetime(2026, 8, 5, 10, 0)),
                         "the expiry names the moment it is finished, so its own minute is out")
        self.assertFalse(due.due_at(one, datetime(2026, 8, 5, 10, 1)))

    def test_an_expired_schedule_says_so_rather_than_a_time(self):
        one = a_schedule(cron="* * * * *", expire_at="2026-08-05T10:00")
        self.assertEqual(due.EXPIRED, due.describe(one, datetime(2026, 8, 5, 11, 0)))
        self.assertIsNone(due.next_after(one, datetime(2026, 8, 5, 11, 0)))

    def test_an_expiry_still_ahead_of_us_changes_nothing(self):
        one = a_schedule(cron="0 9 * * *", expire_at="2027-01-01T00:00")
        at = datetime(2026, 8, 5, 8, 0)
        self.assertEqual(datetime(2026, 8, 5, 9, 0), due.next_after(one, at))
        self.assertNotEqual(due.EXPIRED, due.describe(one, at))

    def test_the_next_time_is_never_beyond_the_expiry(self):
        # The look-ahead has to be shortened by the expiry, or a schedule whose last occurrence is
        # behind the expiry is reported as next running on a day it can never run.
        one = a_schedule(cron="0 9 1 1 *", expire_at="2026-12-01T00:00")
        self.assertIsNone(due.next_after(one, datetime(2026, 8, 5, 9, 0)))

    def test_an_expiry_carrying_a_time_zone_is_refused_the_same_way_a_moment_is(self):
        with self.assertRaisesRegex(due.NotASchedule, "time zone"):
            a_schedule(expire_at="2026-08-05T10:00Z")

    def test_a_moment_expires_at_its_expiry_even_before_its_own_time(self):
        one = a_schedule(cron=None, run_at="2026-08-05T09:00", expire_at="2026-08-01T00:00")
        self.assertFalse(due.due_at(one, datetime(2026, 8, 5, 9, 0)))


class ReadingASetOfThem(support.Isolated):
    """One row nobody can understand does not stop the rest."""

    def test_one_schedule_nobody_can_understand_leaves_the_others_running(self):
        rows = [a_row(name="good"), a_row(name="bad", cron="not a cron"), a_row(name="also-good")]
        kept, refused = due.read(rows)
        self.assertEqual(["also-good", "good"], sorted(one.name for one in kept))
        self.assertEqual(["bad"], [name for name, _why in refused])

    def test_what_could_not_be_read_says_why_and_which(self):
        kept, refused = due.read([a_row(name="bad", cron="60 * * * *")])
        self.assertEqual([], kept)
        name, why = refused[0]
        self.assertEqual("bad", name)
        self.assertIn("minute is 0 to 59", why)

    def test_nothing_written_down_is_no_schedules_rather_than_a_failure(self):
        kept, refused = due.read([])
        self.assertEqual(([], []), (kept, refused))


class CountingWhatWasLetGo(support.Isolated):
    """What fell due while nothing was running is said, never run."""

    def test_what_was_passed_over_can_still_be_counted(self):
        one = a_schedule(cron="0 * * * *")
        self.assertEqual(5, due.passed_over(one, datetime(2026, 8, 5, 0, 0),
                                            datetime(2026, 8, 5, 5, 30)))

    def test_a_very_long_absence_is_counted_up_to_a_point_and_no_further(self):
        # Enough to say "a great many". Counting further tells nobody more and walks a decade.
        one = a_schedule(cron="* * * * *")
        self.assertEqual(1000, due.passed_over(one, datetime(2020, 1, 1, 0, 0),
                                               datetime(2026, 8, 5, 0, 0)))

    def test_a_weekday_match_is_counted_among_what_was_passed_over(self):
        one = a_schedule(cron="0 9 15 * 1")
        self.assertEqual(1, due.passed_over(one, datetime(2026, 8, 1, 0, 0),
                                            datetime(2026, 8, 4, 0, 0)))


class HowAMinuteIsWrittenDown(support.Isolated):
    """One spelling, because two would fire every schedule again after every restart."""

    def test_a_minute_written_down_reads_back_as_the_same_minute(self):
        at = datetime(2026, 8, 5, 9, 30, 45, 123)
        self.assertEqual(datetime(2026, 8, 5, 9, 30), due.from_minute(due.as_minute(at)))

    def test_a_minute_nothing_can_read_is_treated_as_never_having_fired(self):
        # Wrong in the direction that runs a schedule once more, never in the direction that stops
        # it for ever with nothing saying why.
        for said in (None, "", "   ", "who knows", "2026-08-05T09:30"):
            with self.subTest(said=said):
                self.assertIsNone(due.from_minute(said))


if __name__ == "__main__":
    unittest.main()
