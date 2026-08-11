"""The table an agent keeps about work it handed on, and its added configuration.

Two things this proves that nothing else can. **The constraints are the specification**: what a
delegation must name, and what it must point at, are the table's rather than Python's, so the cases
here insert rows that must be refused — a constraint nobody has watched refuse something is a
constraint nobody knows is there.

And **the step is safe against an agent that does not need it**: an install carrying forward already
has a `config` table, so the column is asked about before it is added, and running the step twice
has to be the same as running it once.

Run directly: `python3 tests/test_agent_delegations_step.py`
"""

import sqlite3
import unittest

import support
from rundesk.agents import directory, migration, records
from rundesk.core import paths

#: The step this suite is about, by the name the runner records it under.
THE_STEP = "0005_the_work_an_agent_delegates"


class OneAgentsDelegations(support.Isolated):
    """A real agent, made the way the product makes one — the schema is the shipped step's."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("ava", "a-stand-in")
        self.at = directory.records("ava")

    def rows(self, sql, *values):
        """Every row a query answers, against the agent's own records."""
        with records.reading(self.at) as conn:
            return list(conn.execute(sql, values))

    def write(self, sql, *values):
        """One statement, in the agent's own records, inside the writer's transaction."""
        with records.writing(self.at) as conn:
            conn.execute(sql, values)

    def a_conversation_and_a_turn(self):
        """The two rows a delegation must point at, since both are foreign keys with cascades."""
        with records.writing(self.at) as conn:
            conn.execute(
                "INSERT INTO conversations (source, source_id, created_at) VALUES (?, ?, ?)",
                ("terminal", "one", "2026-08-06T00:00:00Z"))
            conversation = conn.execute("SELECT id FROM conversations").fetchone()[0]
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation, "a-stand-in", "work", "done", "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns").fetchone()[0]
        return conversation, turn

    def back_to_before(self, step):
        """Unstamp this step **and every one after it**, the way a real older agent stands.

        Deleting only this step's own row was enough while it was the last one, and stopped being
        the day a later step landed: the runner refuses to run a step numbered below one an agent
        has already been carried past, which is the rule that keeps a shipped step from being
        back-filled. An agent that predates `0005` predates everything after it too.
        """
        self.write("DELETE FROM migrations WHERE key >= ?", step)

    def a_delegation(self, **moving):
        """Insert one, with every required column filled unless a case replaced it."""
        conversation, turn = getattr(self, "_pointing", (None, None))
        if conversation is None:
            conversation, turn = self.a_conversation_and_a_turn()
            self._pointing = (conversation, turn)
        said = {"delegation_id": "del-1-aaaa", "to_agent": "bob",
                "parent_conversation": conversation, "parent_turn": turn,
                "created_at": "2026-08-06T00:00:00Z", "latest_at": "2026-08-06T00:00:00Z"}
        said.update(moving)
        names = ", ".join(said)
        holes = ", ".join("?" for _ in said)
        self.write(f"INSERT INTO delegations ({names}) VALUES ({holes})", *said.values())


class TheStepItself(OneAgentsDelegations):

    def test_a_made_agent_has_run_it(self):
        self.assertIn(THE_STEP, [one[0] for one in self.rows("SELECT key FROM migrations")])

    def test_an_agent_that_predates_it_gains_the_column_rather_than_a_new_table(self):
        # What an install carrying forward actually does: the column is not there, and the step adds
        # it without touching the rows already in `config`.
        self.write("ALTER TABLE config DROP COLUMN describes")
        self.back_to_before(THE_STEP)
        self.assertIsNone(migration.carry_one("ava"))
        self.assertEqual([("ava",)], [tuple(one) for one in
                                      self.rows("SELECT agent_name FROM config")])
        self.assertIn("describes", [one[1] for one in self.rows("PRAGMA table_info(config)")])

    def test_an_agent_that_predates_it_gets_self_improvement_on_by_default(self):
        self.write("ALTER TABLE config DROP COLUMN self_improve")
        self.back_to_before(THE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual(1, self.rows("SELECT self_improve FROM config")[0][0])

    def test_a_fresh_agent_has_self_improvement_on_by_default(self):
        self.assertEqual(1, self.rows("SELECT self_improve FROM config")[0][0])

    def test_running_it_twice_is_the_same_as_running_it_once(self):
        # A step is written to be safe against an agent that does not need it. `ALTER TABLE ADD
        # COLUMN` has no `IF NOT EXISTS`, so a second run that did not ask first would raise.
        self.back_to_before(THE_STEP)
        self.assertIsNone(migration.carry_one("ava"))
        self.assertEqual(1, len(self.rows("SELECT 1 FROM migrations WHERE key = ?", THE_STEP)))


class ThePhaseAStepLaterAdded(OneAgentsDelegations):
    """`0006`, which gives a delegation the moment its current phase of work began.

    A step of its own rather than an edit to `0005`, because `0005` shipped in 0.40.0 and its id is
    how every install on every machine knows it has run. What is checked here is the part an install
    carrying forward really does: the column is not there, the step adds it, and every row already
    written gets a phase start rather than a `NULL` for something to subtract from later.
    """

    THE_PHASE_STEP = "0006_the_phase_the_work_is_in"

    def test_a_made_agent_has_run_it(self):
        self.assertIn(self.THE_PHASE_STEP,
                      [one[0] for one in self.rows("SELECT key FROM migrations")])

    def test_an_agent_carried_forward_gains_the_column_and_keeps_its_rows(self):
        self.a_delegation()
        self.write("ALTER TABLE delegations DROP COLUMN working_since")
        self.back_to_before(self.THE_PHASE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertIn("working_since",
                      [one[1] for one in self.rows("PRAGMA table_info(delegations)")])
        self.assertEqual([("del-1-aaaa",)],
                         [tuple(one) for one in self.rows("SELECT delegation_id FROM delegations")])

    def test_a_row_that_predates_it_begins_its_phase_when_it_was_made(self):
        # Backfilling from `created_at` is not a guess: before this release nothing could carry work
        # on and have a clock notice, so every existing row is in its first phase by construction.
        self.a_delegation(created_at="2026-08-01T09:00:00Z", latest_at="2026-08-01T11:00:00Z")
        self.write("ALTER TABLE delegations DROP COLUMN working_since")
        self.back_to_before(self.THE_PHASE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([("2026-08-01T09:00:00Z",)],
                         [tuple(one) for one in
                          self.rows("SELECT working_since FROM delegations")])

    def test_running_it_twice_is_the_same_as_running_it_once(self):
        # `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS`, so a second run that did not ask first
        # would raise — and a step is written to be safe against an agent that does not need it.
        self.a_delegation(created_at="2026-08-01T09:00:00Z")
        self.write("UPDATE delegations SET working_since = '2026-08-05T09:00:00Z'")
        self.back_to_before(self.THE_PHASE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([("2026-08-05T09:00:00Z",)],
                         [tuple(one) for one in
                          self.rows("SELECT working_since FROM delegations")],
                         "a second run overwrote a phase start that was already there")


class TheAgentsOneMayDelegateTo(OneAgentsDelegations):
    """`0007`, which distinguishes the default open team from a deliberately empty one."""

    THE_SCOPE_STEP = "0007_the_agents_one_may_delegate_to"

    def test_a_made_agent_has_run_it_and_may_delegate_to_any_agent_by_default(self):
        self.assertIn(self.THE_SCOPE_STEP,
                      [one[0] for one in self.rows("SELECT key FROM migrations")])
        self.assertEqual([(None,)],
                         [tuple(one) for one in self.rows("SELECT delegates_to FROM config")])

    def test_an_agent_carried_forward_gains_the_unrestricted_default(self):
        self.write("ALTER TABLE config DROP COLUMN delegates_to")
        self.back_to_before(self.THE_SCOPE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertIn("delegates_to",
                      [one[1] for one in self.rows("PRAGMA table_info(config)")])
        self.assertEqual([(None,)],
                         [tuple(one) for one in self.rows("SELECT delegates_to FROM config")])

    def test_an_explicit_empty_scope_round_trips_apart_from_the_default(self):
        self.write("UPDATE config SET delegates_to = '[]'")
        self.assertEqual([("[]",)],
                         [tuple(one) for one in self.rows("SELECT delegates_to FROM config")])

    def test_the_scope_is_either_null_or_a_json_array(self):
        for invalid in ('not json', '"forge"', '{"agent":"forge"}'):
            with self.subTest(invalid=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.write("UPDATE config SET delegates_to = ?", invalid)

    def test_running_it_twice_is_the_same_as_running_it_once(self):
        self.write("UPDATE config SET delegates_to = '[\"forge\"]'")
        self.back_to_before(self.THE_SCOPE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([('["forge"]',)],
                         [tuple(one) for one in self.rows("SELECT delegates_to FROM config")],
                         "a second run reset the scope an owner had already configured")


class TheProviderOneDelegationUses(OneAgentsDelegations):
    """``0011`` adds immutable scoped provenance without backfilling a default."""

    THE_PROVIDER_STEP = "0011_the_brain_one_delegation_uses"
    COLUMNS = ("requested_provider_name", "requested_model_name",
               "provider_name", "model_name")

    def test_a_made_agent_has_run_it_and_new_columns_are_nullable(self):
        self.assertIn(self.THE_PROVIDER_STEP,
                      [one[0] for one in self.rows("SELECT key FROM migrations")])
        self.a_delegation()
        self.assertEqual([(None, None, None, None)], [tuple(one) for one in self.rows(
            "SELECT requested_provider_name, requested_model_name, provider_name, model_name"
            " FROM delegations")])

    def test_an_agent_carried_forward_keeps_rows_without_inventing_an_override(self):
        self.a_delegation()
        for column in reversed(self.COLUMNS):
            self.write(f"ALTER TABLE delegations DROP COLUMN {column}")
        self.back_to_before(self.THE_PROVIDER_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        columns = [one[1] for one in self.rows("PRAGMA table_info(delegations)")]
        self.assertTrue(all(column in columns for column in self.COLUMNS))
        self.assertEqual([("del-1-aaaa", None, None, None, None)],
                         [tuple(one) for one in self.rows(
                             "SELECT delegation_id, requested_provider_name,"
                             " requested_model_name, provider_name, model_name FROM delegations")])

    def test_running_it_twice_preserves_recorded_provenance(self):
        self.a_delegation()
        self.write("UPDATE delegations SET requested_provider_name = 'codex',"
                   " requested_model_name = 'asked', provider_name = 'codex',"
                   " model_name = 'effective'")
        self.back_to_before(self.THE_PROVIDER_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([("codex", "asked", "codex", "effective")],
                         [tuple(one) for one in self.rows(
                             "SELECT requested_provider_name, requested_model_name,"
                             " provider_name, model_name FROM delegations")])


class TheStoppedOutcome(OneAgentsDelegations):
    """`0008` gives an owner-requested end its own durable terminal outcome."""

    THE_STOPPED_STEP = "0008_a_stopped_delegation_is_not_an_answer"

    def test_a_made_agent_has_run_it(self):
        self.assertIn(self.THE_STOPPED_STEP,
                      [one[0] for one in self.rows("SELECT key FROM migrations")])

    def test_an_agent_carried_forward_gains_the_column_and_keeps_its_rows(self):
        self.a_delegation()
        self.write("DROP INDEX idx_delegations_waiting")
        self.write("ALTER TABLE delegations DROP COLUMN stopped_at")
        self.write("CREATE INDEX idx_delegations_waiting ON delegations(to_agent) "
                   "WHERE answered_at IS NULL")
        self.back_to_before(self.THE_STOPPED_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertIn("stopped_at",
                      [one[1] for one in self.rows("PRAGMA table_info(delegations)")])
        self.assertEqual([("del-1-aaaa",)],
                         [tuple(one) for one in self.rows(
                             "SELECT delegation_id FROM delegations")])
        self.assertIn("stopped_at IS NULL",
                      self.rows("SELECT sql FROM sqlite_master "
                                "WHERE name = 'idx_delegations_waiting'")[0][0])

    def test_running_it_twice_keeps_an_existing_stopped_outcome(self):
        self.a_delegation()
        self.write("UPDATE delegations SET stopped_at = '2026-08-10T12:00:00Z'")
        self.back_to_before(self.THE_STOPPED_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([("2026-08-10T12:00:00Z",)],
                         [tuple(one) for one in self.rows(
                             "SELECT stopped_at FROM delegations")])


class EveryAgentHasAnOperatingRole(OneAgentsDelegations):
    """`0009` makes the lifecycle distinction explicit without changing older agents' behavior."""

    THE_ROLE_STEP = "0009_every_agent_has_an_operating_role"

    def test_a_made_agent_has_run_it_and_defaults_to_domain(self):
        self.assertIn(self.THE_ROLE_STEP,
                      [one[0] for one in self.rows("SELECT key FROM migrations")])
        self.assertEqual([("domain",)],
                         [tuple(one) for one in self.rows("SELECT role FROM config")])

    def test_an_agent_carried_forward_becomes_domain(self):
        self.write("ALTER TABLE config DROP COLUMN role")
        self.back_to_before(self.THE_ROLE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([("domain",)],
                         [tuple(one) for one in self.rows("SELECT role FROM config")])

    def test_only_the_two_public_roles_can_be_stored(self):
        self.write("UPDATE config SET role = 'specialist'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.write("UPDATE config SET role = 'owner'")

    def test_running_it_twice_keeps_an_explicit_specialist(self):
        self.write("UPDATE config SET role = 'specialist'")
        self.back_to_before(self.THE_ROLE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([("specialist",)],
                         [tuple(one) for one in self.rows("SELECT role FROM config")])


class WhatTheConstraintsRefuse(OneAgentsDelegations):
    """Every rule the table holds, watched refusing something."""

    def test_a_delegation_that_names_no_agent_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.a_delegation(to_agent=None)

    def test_two_delegations_may_not_share_an_id(self):
        self.a_delegation(delegation_id="del-1-aaaa")
        with self.assertRaises(sqlite3.IntegrityError):
            self.a_delegation(delegation_id="del-1-aaaa", to_agent="nina")

    def test_a_delegation_must_point_at_a_turn_that_is_there(self):
        conversation, _ = self.a_conversation_and_a_turn()
        self._pointing = (conversation, 9999)
        with self.assertRaises(sqlite3.IntegrityError):
            self.a_delegation()

    def test_self_improvement_is_only_on_or_off(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.write("UPDATE config SET self_improve = 2")


class WhatTheCascadesTakeWithThem(OneAgentsDelegations):
    """The sweep deletes a conversation and everything under it goes. Proven, never assumed —
    `foreign_keys` is per connection and off by default, so a cascade that does not fire looks
    exactly like one that did until somebody counts the rows."""

    def test_deleting_the_conversation_takes_the_delegation(self):
        conversation, _ = self.a_conversation_and_a_turn()
        self._pointing = (conversation, self.rows("SELECT id FROM turns")[0][0])
        self.a_delegation()
        self.assertEqual(1, len(self.rows("SELECT 1 FROM delegations")))

        self.write("DELETE FROM conversations WHERE id = ?", conversation)

        self.assertEqual([], self.rows("SELECT 1 FROM delegations"))
        self.assertEqual([], self.rows("SELECT 1 FROM turns"))


class WhatAnAgentIsFor(support.Isolated):
    """`describes` is what another agent reads before delegating, so its bounds are the prompt's."""

    def test_an_agent_is_made_with_what_it_is_for(self):
        code, _, _ = self.rundesk("agents", "add", "ava", "--provider", "a-stand-in",
                                  "--describes", "Keeps the billing system.")
        self.assertEqual(0, code)
        with records.reading(directory.records("ava")) as conn:
            self.assertEqual("Keeps the billing system.",
                             conn.execute("SELECT describes FROM config").fetchone()[0])

    def test_an_agent_made_without_one_is_described_by_nothing_rather_than_by_blank(self):
        # Unset and set-to-empty are different answers. A listing has to tell an agent nobody has
        # described from one described as nothing, and `""` would collapse them.
        self.assertEqual(0, self.rundesk("agents", "add", "ava", "--provider", "a-stand-in")[0])
        with records.reading(directory.records("ava")) as conn:
            self.assertIsNone(conn.execute("SELECT describes FROM config").fetchone()[0])

    def test_one_longer_than_a_sentence_is_refused_naming_the_limit_and_the_length(self):
        code, _, err = self.rundesk("agents", "add", "ava", "--provider", "a-stand-in",
                                    "--describes", "x" * 201)
        self.assertEqual(1, code)
        self.assertIn(str(directory.DESCRIBES_AT_MOST), err)
        self.assertIn("201", err)

    def test_a_refused_description_leaves_no_agent_behind(self):
        self.rundesk("agents", "add", "ava", "--provider", "a-stand-in", "--describes", "x" * 201)
        self.assertEqual([], directory.known())

    def test_changing_it_changes_it(self):
        self.rundesk("agents", "add", "ava", "--provider", "a-stand-in", "--describes", "One.")
        self.assertEqual(0, self.rundesk("agents", "configure", "ava", "--describes", "Two.")[0])
        with records.reading(directory.records("ava")) as conn:
            self.assertEqual("Two.", conn.execute("SELECT describes FROM config").fetchone()[0])

    def test_an_empty_one_takes_it_away_rather_than_storing_a_blank(self):
        self.rundesk("agents", "add", "ava", "--provider", "a-stand-in", "--describes", "One.")
        self.assertEqual(0, self.rundesk("agents", "configure", "ava", "--describes", "")[0])
        with records.reading(directory.records("ava")) as conn:
            self.assertIsNone(conn.execute("SELECT describes FROM config").fetchone()[0])

    def test_naming_neither_flag_is_refused_rather_than_reported_as_a_change(self):
        self.rundesk("agents", "add", "ava", "--provider", "a-stand-in")
        code, _, err = self.rundesk("agents", "configure", "ava")
        self.assertEqual(1, code)
        self.assertIn("nothing was named to change", err)
        self.assertIn("--describes", err)

    def test_both_flags_move_together(self):
        self.rundesk("agents", "add", "ava", "--provider", "a-stand-in")
        self.assertEqual(0, self.rundesk("agents", "configure", "ava",
                                         "--provider", "another-stand-in",
                                         "--describes", "Both.")[0])
        with records.reading(directory.records("ava")) as conn:
            said = conn.execute("SELECT provider_name, describes FROM config").fetchone()
        self.assertEqual(("another-stand-in", "Both."), tuple(said))

    def test_a_refused_provider_moves_neither(self):
        # One write for both fields, so a refusal on either leaves the agent exactly as it was.
        self.rundesk("agents", "add", "ava", "--provider", "a-stand-in", "--describes", "One.")
        self.assertEqual(1, self.rundesk("agents", "configure", "ava",
                                         "--provider", "", "--describes", "Two.")[0])
        with records.reading(directory.records("ava")) as conn:
            said = conn.execute("SELECT provider_name, describes FROM config").fetchone()
        self.assertEqual(("a-stand-in", "One."), tuple(said))


if __name__ == "__main__":
    unittest.main()
