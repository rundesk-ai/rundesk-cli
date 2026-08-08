"""The protected per-agent upkeep cadence, driven by usage rather than elapsed time."""

import datetime
import os
import unittest
from pathlib import Path
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import arriving
from rundesk.providers import kept as turns_kept
from rundesk.providers import protocol
from rundesk.schedules import due, firing, upkeep

UTC = datetime.timezone.utc


class Upkeep(support.Isolated):
    def setUp(self):
        super().setUp()
        directory.made("ava", "a-stand-in")
        self.conversation = arriving.recorded(
            "ava", "terminal", "ava", "owner", "start").conversation

    def used(self, day, status=turns_kept.DONE, schedule=None):
        at = datetime.datetime.combine(day, datetime.time(12), tzinfo=UTC)
        turn = turns_kept.add_turn(
            "ava", {"conversation_id": self.conversation,
                    "provider_name": "a-stand-in", "access_mode": protocol.ACCESS_WORK,
                    "schedule_name": schedule}, when=at)
        turns_kept.finish_turn("ava", turn, status, when=at)
        return turn

    def test_six_distinct_usage_dates_are_not_due_and_the_seventh_is(self):
        start = datetime.date(2026, 1, 1)
        for offset in range(6):
            self.used(start + datetime.timedelta(days=offset))
        self.assertIsNone(upkeep.window("ava", zone=UTC))

        self.used(start + datetime.timedelta(days=6))
        got = upkeep.window("ava", zone=UTC)
        self.assertEqual((got.start, got.end, got.days),
                         ("2026-01-01", "2026-01-07", 7))
        for phrase in (
                "retros/2026-01-07.md", "workspace and continuity maintenance",
                "previous entry", "self-improvement reference",
                "provider-local research helper", "token- and cost-efficient",
                "agent-owned script", "existing or proposed skill",
                "named specialist", "MUST launch at least one", "never their homes or memory",
                "post-edit fixture matrix", "unreadable directory",
                "MUST write", "exactly `## What went well`",
                "every safe authorized local improvement", "exact owner decision",
                "Anything unverified is blocked, not done", "no task scratch remains",
                "Throughout every phase", "never open a symlink or its target",
                "exactly one short attention-first sentence"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, got.prompt)

    def test_many_turns_on_one_date_count_once(self):
        one = datetime.date(2026, 2, 1)
        for _ in range(20):
            self.used(one)
        self.assertIsNone(upkeep.window("ava", zone=UTC))

    def test_terminal_failures_and_stops_count_but_working_does_not(self):
        start = datetime.date(2026, 3, 1)
        for offset, status in enumerate((turns_kept.DONE, turns_kept.FAILED,
                                         turns_kept.STOPPED) * 2):
            self.used(start + datetime.timedelta(days=offset), status)
        at = datetime.datetime(2026, 3, 7, 12, tzinfo=UTC)
        working = turns_kept.add_turn(
            "ava", {"conversation_id": self.conversation,
                    "provider_name": "a-stand-in", "access_mode": protocol.ACCESS_WORK}, when=at)
        self.assertIsNone(upkeep.window("ava", zone=UTC))
        turns_kept.finish_turn("ava", working, turns_kept.FAILED, when=at)
        self.assertEqual(7, upkeep.window("ava", zone=UTC).days)

    def test_an_upkeep_turn_never_counts_as_usage(self):
        start = datetime.date(2026, 4, 1)
        for offset in range(6):
            self.used(start + datetime.timedelta(days=offset))
        self.used(start + datetime.timedelta(days=6), schedule=upkeep.NAME)
        self.assertIsNone(upkeep.window("ava", zone=UTC))

    def test_the_last_attempt_starts_a_new_seven_date_window(self):
        start = datetime.date(2026, 5, 1)
        for offset in range(7):
            self.used(start + datetime.timedelta(days=offset))
        upkeep.prepared("ava", "first")
        from rundesk.schedules import kept as schedules_kept
        schedules_kept.became(
            "ava", upkeep.NAME, schedules_kept.FAILED,
            when=datetime.datetime(2026, 5, 8, tzinfo=UTC))
        for offset in range(6):
            self.used(datetime.date(2026, 5, 9) + datetime.timedelta(days=offset))
        self.assertIsNone(upkeep.window("ava", zone=UTC))
        self.used(datetime.date(2026, 5, 15))
        got = upkeep.window("ava", zone=UTC)
        self.assertEqual(("2026-05-09", "2026-05-15"), (got.start, got.end))

    def test_off_accumulates_this_agents_usage_and_reenable_is_immediately_due(self):
        from rundesk.agents import records
        records.stated(directory.records("ava"), {"self_improve": 0})
        start = datetime.date(2026, 6, 1)
        for offset in range(7):
            self.used(start + datetime.timedelta(days=offset))
        self.assertIsNone(upkeep.window("ava", zone=UTC))
        records.stated(directory.records("ava"), {"self_improve": 1})
        self.assertEqual(7, upkeep.window("ava", zone=UTC).days)

    def test_another_agents_usage_never_counts(self):
        directory.made("cole", "a-stand-in")
        conversation = arriving.recorded(
            "cole", "terminal", "cole", "owner", "start").conversation
        for offset in range(7):
            at = datetime.datetime(2026, 7, 1 + offset, 12, tzinfo=UTC)
            turn = turns_kept.add_turn(
                "cole", {"conversation_id": conversation, "provider_name": "a-stand-in",
                         "access_mode": protocol.ACCESS_WORK}, when=at)
            turns_kept.finish_turn("cole", turn, turns_kept.DONE, when=at)
        self.assertIsNone(upkeep.window("ava", zone=UTC))

    def test_local_calendar_dates_define_usage(self):
        west = datetime.timezone(datetime.timedelta(hours=-5))
        for hour in (1, 23):
            at = datetime.datetime(2026, 8, 2, hour, tzinfo=UTC)
            turn = turns_kept.add_turn(
                "ava", {"conversation_id": self.conversation,
                        "provider_name": "a-stand-in", "access_mode": protocol.ACCESS_WORK}, when=at)
            turns_kept.finish_turn("ava", turn, turns_kept.DONE, when=at)
        # 01:00 UTC is the prior local date; 23:00 is the stated UTC date.
        self.assertEqual(2, upkeep.activity("ava", zone=west).days)

    def test_default_local_dates_follow_historical_daylight_saving_transitions(self):
        for at in (datetime.datetime(2026, 1, 15, 4, 30, tzinfo=UTC),
                   datetime.datetime(2026, 7, 15, 3, 30, tzinfo=UTC)):
            turn = turns_kept.add_turn(
                "ava", {"conversation_id": self.conversation,
                        "provider_name": "a-stand-in", "access_mode": protocol.ACCESS_WORK},
                when=at)
            turns_kept.finish_turn("ava", turn, turns_kept.DONE, when=at)

        with mock.patch.dict(os.environ, {"TZ": "America/New_York"}):
            got = upkeep.activity("ava")

        self.assertEqual(("2026-01-14", "2026-07-14"), got.dates)

    def test_the_gateway_starts_one_due_window_through_the_schedule_lifecycle(self):
        start = datetime.date(2026, 9, 1)
        for offset in range(7):
            self.used(start + datetime.timedelta(days=offset))
        watching = firing.Watching({}, {})
        asking = mock.Mock()
        with mock.patch("rundesk.schedules.upkeep.firing.managed",
                        return_value=watching) as managed:
            got = upkeep.looked("ava", Path(self.home) / "log", watching, asking)
        self.assertIs(watching, got)
        managed.assert_called_once()
        one = managed.call_args.args[3]
        self.assertEqual(upkeep.NAME, one.name)
        self.assertIn("2026-09-01 through 2026-09-07", one.prompt)

    def test_a_second_gateway_beat_after_an_attempt_does_not_start_again(self):
        start = datetime.date(2026, 10, 1)
        for offset in range(7):
            self.used(start + datetime.timedelta(days=offset))
        upkeep.prepared("ava", "first")
        from rundesk.schedules import kept as schedules_kept
        schedules_kept.became(
            "ava", upkeep.NAME, schedules_kept.DONE,
            when=datetime.datetime(2026, 10, 8, tzinfo=UTC))
        watching = firing.Watching({}, {})
        with mock.patch("rundesk.schedules.upkeep.firing.managed") as managed:
            got = upkeep.looked("ava", Path(self.home) / "log", watching, mock.Mock())
        self.assertIs(watching, got)
        managed.assert_not_called()

    def test_a_beat_landing_in_the_spawn_gap_does_not_start_the_same_minute_twice(self):
        # **The gap `working` cannot cover.** `_fired` writes `last_fired_for` durably *before* it
        # spawns, and the child writes its own turn row some time after that — so between the two
        # there is no working turn and the window is still owed, and every beat in that gap used to
        # start another run of it. Measured on a loaded machine at the fifty-millisecond beat this
        # suite's gateway case uses: three runs of one window inside a second.
        #
        # Written as the claim actually lands rather than by calling `looked` twice, because what is
        # being proved is that the durable minute is *read* — the write was never in doubt.
        start = datetime.date(2026, 11, 1)
        for offset in range(7):
            self.used(start + datetime.timedelta(days=offset))
        from rundesk.schedules import kept as schedules_kept
        moment = datetime.datetime(2026, 11, 9, 9, 30, tzinfo=UTC)
        upkeep.prepared("ava", "first")
        schedules_kept.claimed("ava", upkeep.NAME, due.as_minute(moment))

        watching = firing.Watching({}, {})
        with mock.patch("rundesk.schedules.upkeep.firing.managed") as managed:
            got = upkeep.looked("ava", Path(self.home) / "log", watching, mock.Mock(),
                                moment=moment)
        self.assertIs(watching, got)
        managed.assert_not_called()

    def test_the_next_minute_may_still_start_one(self):
        # The other half: the guard is *this* minute and never a latch. A run that could not be
        # started is owed on the next beat, and a claim that stopped one for ever would be the
        # silent-never-again failure this codebase names everywhere else.
        start = datetime.date(2026, 11, 1)
        for offset in range(7):
            self.used(start + datetime.timedelta(days=offset))
        from rundesk.schedules import kept as schedules_kept
        claimed = datetime.datetime(2026, 11, 9, 9, 30, tzinfo=UTC)
        upkeep.prepared("ava", "first")
        schedules_kept.claimed("ava", upkeep.NAME, due.as_minute(claimed))

        watching = firing.Watching({}, {})
        with mock.patch("rundesk.schedules.upkeep.firing.managed",
                        return_value=watching) as managed:
            upkeep.looked("ava", Path(self.home) / "log", watching, mock.Mock(),
                          moment=claimed + datetime.timedelta(minutes=1))
        managed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
