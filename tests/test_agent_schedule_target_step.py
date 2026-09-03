"""The column that says where one schedule reports, and what the records refuse about it.

Three things this proves that nothing else can.

**The step is additive and changes no row already there.** An agent carried forward has schedules
somebody is relying on, written by a release that never heard of a destination — so the case that
matters is the one where a real schedule stands in the table before the step runs and stands there
unchanged afterwards, still readable and still due when it was due.

**The constraint is the specification.** A row naming a person *and* a place names two destinations
and one report cannot go to both, and that is refused by the table rather than by Python — so this
inserts one and watches it refused. A constraint nobody has watched refuse something is a constraint
nobody knows is there.

**The step is safe against an agent that does not need it.** `ALTER TABLE ADD COLUMN` has no
`IF NOT EXISTS`, so running the step twice has to be the same as running it once — and an agent that
already has the column has to come out of it unharmed rather than failing the whole carry.

Run directly: `python3 tests/test_agent_schedule_target_step.py`
"""

import sqlite3
import unittest

import support
from rundesk.agents import directory, migration, records
from rundesk.core import paths

#: The step this suite is about, by the name the runner records it under.
THE_STEP = "0014_where_one_schedule_reports"

#: The column it adds, spelled here as well as in the step. Deliberately not imported: a step may
#: not be imported by anything, and a suite that read the name out of the file it is testing would
#: pass while the schema said something else.
THE_COLUMN = "channel_sender_id"


class WhereOneScheduleReports(support.Isolated):
    """A real agent, made the way the product makes one — the schema is the shipped steps'."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("ada", "a-stand-in")
        self.at = directory.records("ada")

    def columns(self):
        """Which columns `schedules` has right now."""
        with records.reading(self.at) as conn:
            return [row[1] for row in conn.execute("PRAGMA table_info(schedules)")]

    def rows(self, sql, *values):
        with records.reading(self.at) as conn:
            return list(conn.execute(sql, values))

    def write(self, sql, *values):
        with records.writing(self.at) as conn:
            conn.execute(sql, values)

    def back_to_before(self, step=THE_STEP):
        """Unstamp this step and every one after it, the way a real older agent stands.

        The same shape `tests/test_agent_delegations_step.py` uses and for its reason: the runner
        refuses a step numbered below one an agent has already been carried past, so an agent that
        predates this one predates everything after it too.
        """
        self.write("DELETE FROM migrations WHERE key >= ?", step)

    def without_the_column(self):
        """Stand this agent exactly where a release before this one left it.

        The column is dropped as well as unstamped, because unstamping alone would have the step run
        against a table that already has it — which is a different case, and one this suite proves
        separately.
        """
        self.back_to_before()
        self.write(f"ALTER TABLE schedules DROP COLUMN {THE_COLUMN}")

    def an_old_schedule(self, name="digest"):
        """One schedule of the shape a release before this one wrote: no destination of its own."""
        self.write("INSERT INTO schedules (name, cron, command, created_at) VALUES (?, ?, ?, ?)",
                   name, "0 9 * * 1", "/bin/echo digest", "2026-08-01T00:00:00Z")


class WhatTheStepAdds(WhereOneScheduleReports):
    """R-SCT-1. The column arrives, and it arrives by being carried."""

    def test_a_fresh_agent_already_holds_it(self):
        # Every step runs in order when an agent is made, so this is the ordinary state and the
        # baseline every case below moves away from.
        self.assertIn(THE_COLUMN, self.columns())

    def test_an_agent_that_predates_it_has_it_after_being_carried(self):
        self.without_the_column()
        self.assertNotIn(THE_COLUMN, self.columns())
        self.assertIsNone(migration.carry_one("ada"))
        self.assertIn(THE_COLUMN, self.columns())

    def test_it_is_the_step_that_is_recorded_as_having_run(self):
        self.without_the_column()
        self.assertIsNone(migration.carry_one("ada"))
        self.assertEqual(
            [(THE_STEP,)],
            [tuple(row) for row in
             self.rows("SELECT key FROM migrations WHERE key = ?", THE_STEP)])

    def test_nothing_is_owed_once_it_has_run(self):
        # What the gateway asks before it will host an agent at all, so an agent left reading as
        # owing a step it has run is an agent no gateway starts.
        self.assertEqual([], migration.outstanding(migration.recorded(self.at)))


class WhatItLeavesAlone(WhereOneScheduleReports):
    """R-SCT-2. A schedule written before this existed is untouched and goes on working."""

    def test_a_row_already_there_keeps_every_value_it_had(self):
        self.without_the_column()
        self.an_old_schedule()
        self.assertIsNone(migration.carry_one("ada"))
        self.assertEqual(
            [("digest", "0 9 * * 1", "/bin/echo digest", None, None, None)],
            [tuple(row) for row in self.rows(
                "SELECT name, cron, command, channel, channel_sender_id, channel_place_id "
                "FROM schedules")])

    def test_no_destination_is_written_for_it(self):
        # **The one thing a default would have got wrong.** A column defaulting to the notified
        # channel would turn *nobody chose* into a choice somebody made, and only one of those is
        # a thing an owner can be shown or asked about.
        self.without_the_column()
        self.an_old_schedule()
        self.assertIsNone(migration.carry_one("ada"))
        self.assertEqual([(None,)],
                         [tuple(row) for row in
                          self.rows(f"SELECT {THE_COLUMN} FROM schedules")])

    def test_it_is_still_a_schedule_the_product_can_read(self):
        from rundesk.schedules import due, kept

        self.without_the_column()
        self.an_old_schedule()
        self.assertIsNone(migration.carry_one("ada"))
        one = due.understood(kept.one("ada", "digest"))
        self.assertEqual("0 9 * * 1", one.cron)
        self.assertIsNone(one.reports_to)


class WhatTheRecordsRefuse(WhereOneScheduleReports):
    """R-SCT-3. One report cannot go to two places, and the table is what says so."""

    def test_a_row_naming_a_person_and_a_place_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.write(
                "INSERT INTO schedules (name, cron, command, channel, channel_sender_id, "
                "channel_place_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                "both", "0 9 * * 1", "/bin/echo x", "slack", "U09", "C0OPS",
                "2026-08-01T00:00:00Z")
        self.assertEqual([], self.rows("SELECT name FROM schedules WHERE name = 'both'"))

    def test_a_row_naming_only_a_person_is_taken(self):
        self.write(
            "INSERT INTO schedules (name, cron, command, channel, channel_sender_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            "dm", "0 9 * * 1", "/bin/echo x", "slack", "U09", "2026-08-01T00:00:00Z")
        self.assertEqual([("slack", "U09", None)],
                         [tuple(row) for row in self.rows(
                             "SELECT channel, channel_sender_id, channel_place_id FROM schedules "
                             "WHERE name = 'dm'")])

    def test_a_row_naming_only_a_place_is_taken(self):
        self.write(
            "INSERT INTO schedules (name, cron, command, channel, channel_place_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            "room", "0 9 * * 1", "/bin/echo x", "slack", "C0OPS", "2026-08-01T00:00:00Z")
        self.assertEqual([("slack", None, "C0OPS")],
                         [tuple(row) for row in self.rows(
                             "SELECT channel, channel_sender_id, channel_place_id FROM schedules "
                             "WHERE name = 'room'")])

    def test_moving_an_existing_row_to_both_is_refused_too(self):
        # The constraint arrives as a table constraint, so it is asked of an update and not only of
        # an insert — which is the case a schedule retargeted by hand would meet.
        self.write(
            "INSERT INTO schedules (name, cron, command, channel, channel_place_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            "room", "0 9 * * 1", "/bin/echo x", "slack", "C0OPS", "2026-08-01T00:00:00Z")
        with self.assertRaises(sqlite3.IntegrityError):
            self.write("UPDATE schedules SET channel_sender_id = ? WHERE name = ?", "U09", "room")


class WhenItIsNotNeeded(WhereOneScheduleReports):
    """R-SCT-4. A step is safe against an agent that has already had it."""

    def test_running_it_again_changes_nothing_and_does_not_fail(self):
        self.an_old_schedule()
        self.back_to_before()                       # unstamped, and the column still there
        self.assertIsNone(migration.carry_one("ada"))
        self.assertEqual(1, len([one for one in self.columns() if one == THE_COLUMN]))

    def test_a_row_already_naming_a_destination_survives_it_being_run_again(self):
        self.write(
            "INSERT INTO schedules (name, cron, command, channel, channel_place_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            "retro", "0 12 * * 5", "/bin/echo x", "slack", "C0OPS", "2026-08-01T00:00:00Z")
        self.back_to_before()
        self.assertIsNone(migration.carry_one("ada"))
        self.assertEqual([("slack", None, "C0OPS")],
                         [tuple(row) for row in self.rows(
                             "SELECT channel, channel_sender_id, channel_place_id FROM schedules "
                             "WHERE name = 'retro'")])

    def test_an_agent_with_no_schedules_table_is_left_alone(self):
        # Unreachable in the ordinary order and checked anyway, because a step never assumes the
        # shape it starts from. Proved by taking the table away, which is what an agent carried no
        # further than `0001` looks like from this step's point of view.
        self.back_to_before("0002")
        self.write("DROP TABLE schedules")
        self.assertIsNone(migration.carry_one("ada"))
        self.assertIn(THE_COLUMN, self.columns())


if __name__ == "__main__":
    unittest.main()
