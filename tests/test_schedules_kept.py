"""The schedules one agent keeps: what is written, what is refused, and what is never written over.

Every case here works on a real agent with real records, made the way the product makes one — so the
`schedules` table under test is the one migration step `0002` laid down, and not a fixture that
agrees with it.

**The refusals are most of the value.** A store that writes what it is given is easy; what this one
has to do is refuse a row the clock could not act on, refuse half a change, and tell records that
are *not there* apart from records that are there and cannot be read. The last of those is the one
that costs something when it is collapsed: a caller told "not there" makes a new one, and an agent's
whole memory is what that overwrites.

Run directly: `python3 tests/test_schedules_kept.py`
"""

import sqlite3
import unittest
from datetime import datetime, timezone

import support
from rundesk.agents import directory, records
from rundesk.core import config
from rundesk.schedules import kept


class Keeping(support.Isolated):
    """An agent with real records, and the schedules it keeps in them."""

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")

    def given(self, name="nightly", **also):
        """One schedule, written through the store because that is the thing under test."""
        values = dict({"cron": "0 2 * * *", "command": "/bin/echo hello"}, **also)
        kept.added(self.agent, name, values)
        return name

    def rows(self):
        return kept.all(self.agent)


class WhatIsWrittenDown(Keeping):

    def test_a_schedule_reads_back_everything_it_was_given(self):
        self.given("nightly", cron="0 2 * * *", command="/bin/echo hello",
                   expire_at="2027-01-01T00:00", channel="discord", channel_place_id="42")
        one = kept.one(self.agent, "nightly")
        self.assertEqual("nightly", one["name"])
        self.assertEqual("0 2 * * *", one["cron"])
        self.assertEqual("/bin/echo hello", one["command"])
        self.assertEqual("2027-01-01T00:00", one["expire_at"])
        self.assertEqual("discord", one["channel"])
        self.assertEqual("42", one["channel_place_id"])

    def test_a_schedule_is_on_unless_somebody_says_otherwise(self):
        self.given()
        self.assertEqual(1, kept.one(self.agent, "nightly")["enabled"])

    def test_when_it_was_made_is_written_for_a_machine_to_compare(self):
        # UTC, to the second, in the one shape this product keeps a record in — because it is
        # sorted, and it may be read on another machine after a restore. The *stated* times beside
        # it are local and are not, which is the distinction this column exists on the other side of.
        self.given()
        made = kept.one(self.agent, "nightly")["created_at"]
        self.assertIsNotNone(datetime.strptime(made, config.MOMENT))
        self.assertTrue(made.endswith("Z"))

    def test_what_a_schedule_states_is_kept_exactly_as_it_was_typed(self):
        # Local, and not normalised. An owner who wrote `0 9 * * *` reads back `0 9 * * *`, and a
        # store that rewrote it into some canonical form would be a store answering a question
        # nobody asked with a string nobody typed.
        self.given("nine", cron="0  9  *  *  *")
        self.assertEqual("0  9  *  *  *", kept.one(self.agent, "nine")["cron"])

    def test_an_agent_with_no_schedules_says_so_rather_than_failing(self):
        self.assertEqual([], self.rows())

    def test_schedules_come_back_in_name_order(self):
        for name in ("zebra", "apple", "mango"):
            self.given(name)
        self.assertEqual(["apple", "mango", "zebra"], [one["name"] for one in self.rows()])

    def test_a_schedule_that_asks_an_agent_stores_and_reads_back_whole(self):
        # The kind no command can spell in this release. The store handles it, which is what makes
        # the provider process a thing to plug in rather than a thing to migrate for.
        kept.added(self.agent, "review", {"cron": "0 9 * * *", "agent_prompt": "review the queue",
                                          "agent_provider": "claude", "agent_model": "opus"})
        one = kept.one(self.agent, "review")
        self.assertEqual("review the queue", one["agent_prompt"])
        self.assertEqual("claude", one["agent_provider"])
        self.assertEqual("opus", one["agent_model"])
        self.assertIsNone(one["command"])


class WhatTheRecordsRefuse(Keeping):
    """The two `CHECK`s, asked of the database rather than of a reader."""

    def test_a_schedule_saying_when_two_ways_cannot_be_written(self):
        with self.assertRaises(kept.Refused):
            kept.added(self.agent, "both", {"cron": "0 9 * * *", "run_at": "2026-08-05T09:00",
                                            "command": "/bin/echo hi"})
        self.assertEqual([], self.rows(), "nothing should have been written")

    def test_a_schedule_saying_when_no_way_at_all_cannot_be_written(self):
        with self.assertRaises(kept.Refused):
            kept.added(self.agent, "neither", {"command": "/bin/echo hi"})
        self.assertEqual([], self.rows())

    def test_a_schedule_naming_both_a_program_and_a_prompt_cannot_be_written(self):
        with self.assertRaises(kept.Refused):
            kept.added(self.agent, "both", {"cron": "0 9 * * *", "command": "/bin/echo hi",
                                            "agent_prompt": "and also this"})
        self.assertEqual([], self.rows())

    def test_a_schedule_naming_nothing_to_run_cannot_be_written(self):
        with self.assertRaises(kept.Refused):
            kept.added(self.agent, "nothing", {"cron": "0 9 * * *"})
        self.assertEqual([], self.rows())

    def test_a_name_that_is_already_a_schedules_is_refused_rather_than_replaced(self):
        # Two people reach for one name and the second must not silently take the first's away.
        self.given("nightly", command="/bin/echo first")
        with self.assertRaisesRegex(kept.Refused, "already has a schedule"):
            self.given("nightly", command="/bin/echo second")
        self.assertEqual("/bin/echo first", kept.one(self.agent, "nightly")["command"])

    def test_a_name_a_filesystem_cannot_hold_is_refused_where_it_is_typed(self):
        # A schedule's name becomes `<name>.lock` and `<name>.out` inside the agent's own directory,
        # so one of these could be added and could never be fired.
        for said in ("", "  ", ".", "..", "a/b", ".hidden", "a\0b"):
            with self.subTest(name=said):
                with self.assertRaises(kept.Refused):
                    self.given(said)

    def test_a_column_that_is_not_a_schedules_is_refused(self):
        with self.assertRaisesRegex(kept.Refused, "not something a schedule is given"):
            kept.added(self.agent, "odd", {"cron": "0 9 * * *", "command": "/bin/echo hi",
                                           "colour": "blue"})

    def test_what_the_records_keep_of_themselves_is_not_a_callers_to_state(self):
        # `created_at`, `last_outcome`, `last_run_at` and `last_fired_for` are the records' own
        # account of what happened. A caller that could set them could rewrite history and then read
        # it back as fact — and `last_fired_for` in particular is the only thing standing between a
        # restart and a schedule running twice.
        for column in ("created_at", "last_outcome", "last_run_at", "last_fired_for", "id", "name"):
            with self.subTest(column=column):
                with self.assertRaises(kept.Refused):
                    kept.added(self.agent, "odd", {"cron": "0 9 * * *",
                                                   "command": "/bin/echo hi", column: "x"})

    def test_an_outcome_that_is_not_one_of_three_is_refused_in_words(self):
        # The `CHECK` would raise about a constraint. The caller of this is a gateway writing into a
        # log somebody reads at two in the morning.
        self.given()
        with self.assertRaisesRegex(kept.Refused, "is not what a firing comes to"):
            kept.became(self.agent, "nightly", "started")


class ChangingOneInPlace(Keeping):

    def test_a_schedule_is_changed_and_keeps_what_it_has_already_done(self):
        self.given()
        kept.claimed(self.agent, "nightly", "2026-08-05 02:00")
        kept.became(self.agent, "nightly", kept.COMPLETED)
        kept.changed(self.agent, "nightly", {"cron": "0 3 * * *"})
        one = kept.one(self.agent, "nightly")
        self.assertEqual("0 3 * * *", one["cron"])
        self.assertEqual("2026-08-05 02:00", one["last_fired_for"])
        self.assertEqual(kept.COMPLETED, one["last_outcome"])

    def test_only_what_is_named_moves(self):
        self.given("nightly", cron="0 2 * * *", command="/bin/echo hello", expire_at="2027-01-01T00:00")
        kept.changed(self.agent, "nightly", {"cron": "0 3 * * *"})
        one = kept.one(self.agent, "nightly")
        self.assertEqual("/bin/echo hello", one["command"])
        self.assertEqual("2027-01-01T00:00", one["expire_at"])

    def test_a_repeating_time_and_a_single_moment_replace_each_other(self):
        self.given()
        kept.changed(self.agent, "nightly", {"cron": None, "run_at": "2026-08-05T09:00"})
        one = kept.one(self.agent, "nightly")
        self.assertIsNone(one["cron"])
        self.assertEqual("2026-08-05T09:00", one["run_at"])

    def test_a_change_that_would_leave_neither_of_a_pair_is_refused(self):
        self.given()
        with self.assertRaises(kept.Refused):
            kept.changed(self.agent, "nightly", {"cron": None})
        self.assertEqual("0 2 * * *", kept.one(self.agent, "nightly")["cron"])

    def test_naming_two_columns_and_getting_one_wrong_changes_neither(self):
        # Half of what was meant is not a smaller change — it is a different one nobody typed.
        self.given()
        with self.assertRaises(kept.Refused):
            kept.changed(self.agent, "nightly", {"cron": "0 3 * * *", "colour": "blue"})
        self.assertEqual("0 2 * * *", kept.one(self.agent, "nightly")["cron"])

    def test_changing_a_schedule_that_is_not_there_says_so_and_alters_nothing(self):
        self.given("nightly")
        with self.assertRaises(records.NotThere):
            kept.changed(self.agent, "missing", {"cron": "0 3 * * *"})
        self.assertEqual(["nightly"], [one["name"] for one in self.rows()])

    def test_a_change_naming_nothing_to_change_is_said_rather_than_reported_as_done(self):
        self.given()
        with self.assertRaises(kept.Refused):
            kept.changed(self.agent, "nightly", {})

    def test_a_schedule_is_turned_off_and_on_again_without_being_lost(self):
        self.given()
        kept.changed(self.agent, "nightly", {"enabled": 0})
        self.assertEqual(0, kept.one(self.agent, "nightly")["enabled"])
        kept.changed(self.agent, "nightly", {"enabled": 1})
        self.assertEqual(1, kept.one(self.agent, "nightly")["enabled"])


class TakingOneAway(Keeping):

    def test_a_schedule_that_has_run_can_still_be_taken_away(self):
        # The old build could not: a foreign key without `ON DELETE SET NULL` made a schedule
        # permanent the first time the clock reached it, and nothing edited one.
        self.given()
        kept.claimed(self.agent, "nightly", "2026-08-05 02:00")
        kept.became(self.agent, "nightly", kept.FAILED)
        kept.forgotten(self.agent, "nightly")
        self.assertEqual([], self.rows())

    def test_a_removal_that_did_not_happen_is_a_failure(self):
        with self.assertRaises(records.NotThere):
            kept.forgotten(self.agent, "missing")

    def test_taking_one_away_leaves_the_others(self):
        self.given("one")
        self.given("two")
        kept.forgotten(self.agent, "one")
        self.assertEqual(["two"], [row["name"] for row in self.rows()])


class WhatAFiringWritesDown(Keeping):

    def test_that_a_schedule_fired_survives_being_read_back(self):
        # The whole of the once-per-minute guarantee: held in memory it died with the gateway, and a
        # supervisor bringing one back within seconds ran the same schedule twice.
        self.given()
        kept.claimed(self.agent, "nightly", "2026-08-05 02:00")
        self.assertEqual("2026-08-05 02:00", kept.one(self.agent, "nightly")["last_fired_for"])

    def test_claiming_a_schedule_that_is_not_there_says_so_rather_than_passing_over(self):
        # A caller that started the work anyway would leave work that visibly happened with nothing
        # durable saying it did — so this raises rather than answering.
        with self.assertRaises(records.NotThere):
            kept.claimed(self.agent, "missing", "2026-08-05 02:00")

    def test_what_a_firing_came_to_is_written_with_when_it_was_over(self):
        self.given()
        kept.became(self.agent, "nightly", kept.COMPLETED,
                    datetime(2026, 8, 5, 2, 4, 12, tzinfo=timezone.utc))
        one = kept.one(self.agent, "nightly")
        self.assertEqual(kept.COMPLETED, one["last_outcome"])
        self.assertEqual("2026-08-05T02:04:12Z", one["last_run_at"])

    def test_a_schedule_taken_away_mid_run_is_passed_over_rather_than_raised_about(self):
        # The removal is what somebody asked for and the child is being stopped along with it. A
        # gateway that raised here would end over a row that is gone on purpose.
        self.given()
        kept.forgotten(self.agent, "nightly")
        kept.became(self.agent, "nightly", kept.STOPPED)


class WhenTheRecordsThemselvesCannotAnswer(Keeping):
    """Four answers, never two."""

    def test_records_that_went_away_are_told_apart_from_records_that_cannot_be_read(self):
        directory.records(self.agent).unlink()
        with self.assertRaises(records.NotThere):
            self.rows()

    def test_records_that_cannot_be_read_are_never_read_as_no_schedules(self):
        # The expensive collapse: told "none", a caller writes its own over whatever survived.
        directory.records(self.agent).write_bytes(b"this is not a database")
        with self.assertRaises(records.Unreadable):
            self.rows()

    def test_records_holding_no_schedules_table_are_unreadable_rather_than_empty(self):
        # An agent carried no further than 0001 has schedules nobody has read, not no schedules.
        at = directory.records(self.agent)
        with records.writing(at) as conn:
            conn.execute("DROP TABLE schedules")
        with self.assertRaises(records.Unreadable):
            self.rows()

    def test_records_that_cannot_be_read_are_left_exactly_as_they_are(self):
        at = directory.records(self.agent)
        at.write_bytes(b"this is not a database")
        before = at.read_bytes()
        for attempt in (lambda: kept.added(self.agent, "x", {"cron": "* * * * *",
                                                             "command": "/bin/echo hi"}),
                        lambda: kept.changed(self.agent, "x", {"cron": "* * * * *"}),
                        lambda: kept.forgotten(self.agent, "x")):
            with self.subTest(attempt=attempt):
                with self.assertRaises((records.Unreadable, sqlite3.DatabaseError)):
                    attempt()
        self.assertEqual(before, at.read_bytes())

    def test_a_schedule_that_is_not_there_is_said_rather_than_shown_as_empty(self):
        with self.assertRaises(records.NotThere):
            kept.one(self.agent, "missing")


if __name__ == "__main__":
    unittest.main()
