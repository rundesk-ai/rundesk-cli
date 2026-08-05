"""Agent migrations: a row per step, one agent at a time, and a way back when a step cannot finish.

The three things that differ from the install level are what this suite is mostly about — a row per
step rather than one id, one agent failing without taking the others down, and the stamp landing in
the same transaction as the step's work.

The steps under test are written here rather than taken from `agents/steps/`, so the suite proves
the runner rather than whichever steps a release happens to ship. The one exception is the real
`0001`, which is copied into the scratch directory because it is what makes a directory an agent at
all — everything else has nowhere to be recorded without it.

Run directly: `python3 tests/test_agent_migration.py`
"""

import ast
import importlib.util
import os
import shutil
import unittest
from pathlib import Path
from typing import List

import support
from rundesk.agents import directory, migration, records
from rundesk.core import paths
from rundesk.utils import files

#: A step that changes a table and a file together, which is the whole reason a step is handed both.
A_STEP = '''
from pathlib import Path

def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS "{name}" (one TEXT) STRICT')
    (Path(where) / "{name}").write_text("{name}")
'''

#: A step that does some of its work and then cannot finish. The table it made must not survive.
A_STEP_THAT_FAILS = '''
def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS half_done (one TEXT) STRICT')
    raise RuntimeError("this step could not finish")
'''

#: A step that does its work and then makes the runner's own stamp impossible, by taking the key
#: the runner is about to write. The only way to see from outside that the work and the row are one
#: transaction: if they were two, the work would commit and only the stamp would fail.
A_STEP_WHOSE_STAMP_CANNOT_LAND = '''
def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS its_own_work (one TEXT) STRICT')
    conn.execute("INSERT INTO migrations (key, completed_at) VALUES ('0002_awkward', 'earlier')")
'''

#: A step that refuses to run unless the runner has already opened a transaction around it.
A_STEP_THAT_CHECKS_ITS_TRANSACTION = '''
def carry(conn, where):
    if not conn.in_transaction:
        raise RuntimeError("this step was handed a connection outside a transaction")
    conn.execute('CREATE TABLE IF NOT EXISTS inside (one TEXT) STRICT')
'''

#: A step that fails for one agent and not for the others, which is how "one that fails does not
#: stop the next" is proved rather than asserted.
A_STEP_THAT_FAILS_FOR_ONE = '''
from pathlib import Path

def carry(conn, where):
    if Path(where).name == "alpha":
        raise RuntimeError("this step could not finish")
    conn.execute('CREATE TABLE IF NOT EXISTS carried (one TEXT) STRICT')
'''

#: A step that fails *and* takes away the one permission putting the records back needs, so the
#: rollback fails too. The state somebody has to be told about out loud.
A_STEP_THAT_CANNOT_BE_PUT_BACK = '''
import os
from pathlib import Path

def carry(conn, where):
    os.chmod(Path(where) / "state.db", 0o400)
    raise RuntimeError("this step could not finish")
'''


class Steps(support.Isolated):
    """A scratch step directory, and agents carried by whatever is in it."""

    def setUp(self):
        super().setUp()
        self.steps = self.home / "steps"
        self.steps.mkdir(parents=True, exist_ok=True)
        paths.agents().mkdir(parents=True, exist_ok=True)
        # The real first step, because it is what lays down the `migrations` table every other step
        # is recorded in. A scratch stand-in for it would be a second description of an agent's
        # records, and the point of building them through the runner is that there is only one.
        shutil.copy2(migration.STEPS / "0001_the_records_an_agent_keeps.py", self.steps)

    def given(self, name: str, body: str = "") -> None:
        (self.steps / f"{name}.py").write_text(body or A_STEP.format(name=name), encoding="utf-8")

    def a_directory_for(self, name: str) -> Path:
        """A directory standing where an agent stands, with no records in it yet."""
        at = directory.where(name)
        (at / directory.HOME).mkdir(parents=True)
        (at / directory.LOGS).mkdir()
        return at

    def an_agent(self, name: str) -> Path:
        """A directory carried onto whatever steps are in place, the way `made` builds one."""
        self.a_directory_for(name)
        self.assertIsNone(migration.carry_one(name, self.steps))
        records.stated(directory.records(name),
                       {"agent_name": name, "agent_provider": "anthropic"})
        return directory.where(name)

    def recorded(self, name: str) -> List[str]:
        return sorted(migration.recorded(directory.records(name)))

    def tables(self, name: str) -> set:
        with records.reading(directory.records(name)) as conn:
            return {row[0] for row in
                    conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


class WhichStepsExist(Steps):

    def test_steps_are_found_rather_than_listed(self):
        self.given("0002_second")
        self.assertEqual(["0001_the_records_an_agent_keeps", "0002_second"],
                         [step.id for step in migration.found(self.steps)])

    def test_they_run_in_the_order_their_number_gives(self):
        self.given("0010_later")
        self.given("0002_earlier")
        self.assertEqual(["0001_the_records_an_agent_keeps", "0002_earlier", "0010_later"],
                         [step.id for step in migration.found(self.steps)])

    def test_a_file_that_is_not_named_like_a_step_is_ignored(self):
        (self.steps / "__init__.py").write_text("", encoding="utf-8")
        (self.steps / "notes.md").write_text("", encoding="utf-8")
        self.assertEqual(["0001_the_records_an_agent_keeps"],
                         [step.id for step in migration.found(self.steps)])

    def test_two_steps_with_one_number_are_refused(self):
        # The ids are the keys in the `migrations` table. Two files numbered the same would be two
        # rows with no order between them, and which one an agent had run would depend on which
        # machine it was on.
        self.given("0002_alpha")
        self.given("0002_beta")
        with self.assertRaises(migration.Broken) as refused:
            migration.found(self.steps)
        self.assertIn("0002", str(refused.exception))

    def test_it_is_said_rather_than_raised_when_an_agent_is_being_carried(self):
        self.an_agent("cole")
        self.given("0002_alpha")
        self.given("0002_beta")
        self.assertIn("0002", migration.carry_one("cole", self.steps))


class WhatHasRunIsARowPerStep(Steps):
    """Not one id — see the module docstring on why the two levels record differently."""

    def test_records_that_are_not_there_have_had_nothing_run_against_them(self):
        self.a_directory_for("cole")
        self.assertEqual([], migration.recorded(directory.records("cole")))

    def test_every_step_that_ran_is_its_own_row(self):
        self.given("0002_second")
        self.given("0003_third")
        self.an_agent("cole")
        self.assertEqual(["0001_the_records_an_agent_keeps", "0002_second", "0003_third"],
                         self.recorded("cole"))

    def test_records_that_do_not_say_which_steps_have_run_are_unreadable(self):
        self.an_agent("cole")
        with records.writing(directory.records("cole")) as conn:
            conn.execute("DROP TABLE migrations")
        with self.assertRaises(records.Unreadable):
            migration.recorded(directory.records("cole"))


class WhichStepsAreOutstanding(Steps):

    def test_a_step_with_no_row_is_outstanding(self):
        self.given("0002_second")
        self.assertEqual(["0001_the_records_an_agent_keeps", "0002_second"],
                         [step.id for step in migration.outstanding([], self.steps)])

    def test_a_step_that_has_a_row_is_not(self):
        self.given("0002_second")
        self.assertEqual(["0002_second"],
                         [step.id for step in migration.outstanding(
                             ["0001_the_records_an_agent_keeps"], self.steps)])

    def test_an_agent_carried_further_than_this_release_ships_is_refused(self):
        # Carried by a newer rundesk. Running this release's steps over a layout a newer release
        # made is how an agent's memory gets damaged.
        with self.assertRaises(migration.Ahead) as refused:
            migration.outstanding(["0001_the_records_an_agent_keeps", "9999_from_the_future"],
                                  self.steps)
        self.assertIn("9999_from_the_future", str(refused.exception))
        self.assertIn("newer release", str(refused.exception))

    def test_carrying_such_an_agent_says_it_rather_than_running_anything(self):
        self.an_agent("cole")
        self.given("0002_second")
        with records.writing(directory.records("cole")) as conn:
            conn.execute("INSERT INTO migrations (key, completed_at) VALUES (?, ?)",
                         ("9999_from_the_future", "2099-01-01T00:00:00Z"))
        gone_wrong = migration.carry_one("cole", self.steps)
        self.assertIn("9999_from_the_future", gone_wrong)
        self.assertFalse((directory.where("cole") / "0002_second").exists(),
                         "a step ran over a layout a newer release had already changed")


class CarryingOneAgentForward(Steps):

    def test_every_step_that_has_not_run_runs(self):
        self.given("0002_second")
        self.given("0003_third")
        self.an_agent("cole")
        self.assertIn("0002_second", self.tables("cole"))
        self.assertIn("0003_third", self.tables("cole"))

    def test_a_step_may_change_the_tables_and_the_files_together(self):
        # Which is why it is handed the open connection *and* the agent's own directory. A schema
        # that says a file is there, shipped beside a directory where it is not, is the failure.
        self.given("0002_second")
        self.an_agent("cole")
        self.assertTrue((directory.where("cole") / "0002_second").is_file())

    def test_a_step_that_has_run_does_not_run_again(self):
        self.given("0002_second")
        self.an_agent("cole")
        (directory.where("cole") / "0002_second").unlink()
        self.assertIsNone(migration.carry_one("cole", self.steps))
        self.assertFalse((directory.where("cole") / "0002_second").exists(),
                         "the step ran a second time")

    def test_only_the_steps_a_release_added_run_the_next_time(self):
        self.an_agent("cole")
        self.given("0002_second")
        self.assertIsNone(migration.carry_one("cole", self.steps))
        self.assertEqual(["0001_the_records_an_agent_keeps", "0002_second"], self.recorded("cole"))

    def test_an_agent_already_on_this_release_is_left_alone(self):
        self.an_agent("cole")
        self.assertIsNone(migration.carry_one("cole", self.steps))

    def test_a_step_with_nothing_to_run_is_named_rather_than_skipped(self):
        self.an_agent("cole")
        self.given("0002_empty", "# this file has no carry()\n")
        self.assertIn("0002_empty", migration.carry_one("cole", self.steps))

    def test_carrying_an_agent_that_does_not_exist_says_so_rather_than_making_one(self):
        gone_wrong = migration.carry_one("nobody", self.steps)
        self.assertIsNotNone(gone_wrong)
        self.assertFalse(directory.where("nobody").exists())


class TheStampLandsWithTheStep(Steps):
    """One transaction, so "it ran but was not recorded" is not a state that can exist here."""

    def test_a_step_that_could_not_finish_leaves_neither_its_work_nor_its_row(self):
        self.an_agent("cole")
        self.given("0002_broken", A_STEP_THAT_FAILS)
        migration.carry_one("cole", self.steps)
        self.assertNotIn("half_done", self.tables("cole"), "a failed step's work survived")
        self.assertNotIn("0002_broken", self.recorded("cole"), "a failed step was recorded as done")

    def test_a_step_is_handed_a_connection_already_inside_a_transaction(self):
        # The contract, checked by a step rather than believed. It is what lets a step change
        # tables and files together and have the tables go back if it cannot finish.
        self.an_agent("cole")
        self.given("0002_inside", A_STEP_THAT_CHECKS_ITS_TRANSACTION)
        self.assertIsNone(migration.carry_one("cole", self.steps))
        self.assertIn("inside", self.tables("cole"))

    def test_a_step_and_the_row_recording_it_are_written_as_one_transaction(self):
        # The guarantee, and the only way to see it from outside: count the transactions. Two
        # would mean the work commits before the row that records it, so a run stopped between
        # them leaves an agent changed and unstamped — and the rollback would hide that, because
        # it puts the whole database back either way.
        self.an_agent("cole")
        self.given("0002_second")
        opened = []
        real = records.writing

        def counted(at, making=False):
            opened.append(at)
            return real(at, making)

        self.addCleanup(setattr, records, "writing", real)
        records.writing = counted
        self.assertIsNone(migration.carry_one("cole", self.steps))
        self.assertEqual(1, len(opened),
                         f"one step and its record took {len(opened)} transactions")

    def test_work_whose_stamp_cannot_land_is_not_kept_either(self):
        # Two transactions instead of one would commit the step's work and then fail to record it,
        # which is the "ran but was not recorded" state this level does not have.
        self.an_agent("cole")
        self.given("0002_awkward", A_STEP_WHOSE_STAMP_CANNOT_LAND)
        self.assertIsNotNone(migration.carry_one("cole", self.steps))
        self.assertNotIn("its_own_work", self.tables("cole"),
                         "a step's work was kept although its record could not be written")

    def test_a_later_step_does_not_run_over_a_shape_its_predecessor_never_made(self):
        self.an_agent("cole")
        self.given("0002_broken", A_STEP_THAT_FAILS)
        self.given("0003_third")
        migration.carry_one("cole", self.steps)
        self.assertNotIn("0003_third", self.tables("cole"))


class WhenAStepCannotFinish(Steps):
    """The records are put back, so an agent is either carried or exactly as it was."""

    def setUp(self):
        super().setUp()
        self.given("0002_second")
        self.an_agent("cole")

    def test_the_records_are_put_back_to_exactly_the_bytes_they_were(self):
        self.given("0003_broken", A_STEP_THAT_FAILS)
        before = directory.records("cole").read_bytes()
        migration.carry_one("cole", self.steps)
        self.assertEqual(before, directory.records("cole").read_bytes())

    def test_and_they_read_back_saying_exactly_what_they_said(self):
        # The bytes are the mechanism; this is the thing somebody cares about.
        self.given("0003_broken", A_STEP_THAT_FAILS)
        before = records.read(directory.records("cole"))
        migration.carry_one("cole", self.steps)
        self.assertEqual(before, records.read(directory.records("cole")))
        self.assertEqual(["0001_the_records_an_agent_keeps", "0002_second"], self.recorded("cole"))

    def test_it_goes_all_the_way_back_and_not_to_the_last_step_that_worked(self):
        # Where this level deliberately parts company with the install level, which stamps each
        # step as it lands and resumes from there. An agent's whole memory is one file that can be
        # copied, so the useful state to leave somebody in is the one they had before they asked —
        # one thing to look at rather than a database halfway between two releases.
        self.given("0003_third")
        self.given("0004_broken", A_STEP_THAT_FAILS)
        migration.carry_one("cole", self.steps)
        self.assertNotIn("0003_third", self.recorded("cole"))
        self.assertNotIn("0003_third", self.tables("cole"))

    def test_the_sentence_says_which_step_and_that_the_records_were_put_back(self):
        self.given("0003_broken", A_STEP_THAT_FAILS)
        gone_wrong = migration.carry_one("cole", self.steps)
        self.assertIn("0003_broken", gone_wrong)
        self.assertIn("put back", gone_wrong)

    def test_an_agent_that_had_no_records_is_left_with_none(self):
        # The other half of putting them back: what was not set aside is taken away rather than
        # left. This is a make that got as far as building the database and then failed, and the
        # honest way back is a directory with no records in it — not one with half an agent's.
        self.given("0003_broken", A_STEP_THAT_FAILS)
        self.a_directory_for("nina")
        self.assertIsNotNone(migration.carry_one("nina", self.steps))
        for one in records.beside(directory.records("nina")):
            with self.subTest(one=one.name):
                self.assertFalse(one.exists(), f"{one.name} survived a carry that was rolled back")

    def test_the_copy_it_kept_is_let_go_of_once_it_is_no_longer_needed(self):
        self.given("0003_third")
        migration.carry_one("cole", self.steps)
        self.assertEqual([], [one.name for one in directory.where("cole").iterdir()
                              if files.staged(one.name)])

    def test_the_agent_beside_it_is_never_reached(self):
        # Per agent, so one agent's rollback cannot touch another's. The copies are taken beside
        # that agent's own records, and there is no shared directory for two of them to meet in.
        self.an_agent("nina")
        nina = directory.records("nina").read_bytes()
        self.given("0003_broken", A_STEP_THAT_FAILS)
        migration.carry_one("cole", self.steps)
        self.assertEqual(nina, directory.records("nina").read_bytes())

    def test_a_rollback_that_itself_fails_is_said_out_loud(self):
        # An agent left neither carried nor put back is the one state somebody has to be told
        # about, rather than counted in a summary of how many failed.
        self.given("0003_stuck", A_STEP_THAT_CANNOT_BE_PUT_BACK)
        self.addCleanup(os.chmod, str(directory.records("cole")), 0o600)
        gone_wrong = migration.carry_one("cole", self.steps)
        self.assertIn("0003_stuck", gone_wrong)
        self.assertIn("could not be put back", gone_wrong)

    def test_the_copy_is_kept_when_the_rollback_failed(self):
        # It is the only way back. Letting go of it because the operation is over would take away
        # the one thing that could still repair the agent.
        self.given("0003_stuck", A_STEP_THAT_CANNOT_BE_PUT_BACK)
        self.addCleanup(os.chmod, str(directory.records("cole")), 0o600)
        migration.carry_one("cole", self.steps)
        self.assertTrue((directory.where("cole") /
                         files.OUTGOING.format(name=directory.RECORDS)).is_file())


class CarryingEveryAgent(Steps):

    def test_an_install_with_no_agents_has_nothing_to_carry_and_that_is_not_a_failure(self):
        self.assertEqual({}, migration.carry_every([], self.steps))

    def test_every_agent_named_is_carried(self):
        self.an_agent("alpha")
        self.an_agent("zulu")
        self.given("0002_second")
        self.assertEqual({}, migration.carry_every(directory.known(), self.steps))
        for name in ("alpha", "zulu"):
            with self.subTest(name=name):
                self.assertIn("0002_second", self.recorded(name))

    def test_one_that_fails_does_not_stop_the_next(self):
        # The whole difference between this level and the install level. Nineteen agents that are
        # fine are not something to take down because the third one's database cannot be read.
        self.an_agent("alpha")
        self.an_agent("zulu")
        self.given("0002_awkward", A_STEP_THAT_FAILS_FOR_ONE)
        gone_wrong = migration.carry_every(["alpha", "zulu"], self.steps)
        self.assertEqual(["alpha"], sorted(gone_wrong))
        self.assertIn("carried", self.tables("zulu"), "the agent after the failure was not carried")
        self.assertIn("0002_awkward", self.recorded("zulu"))

    def test_the_one_that_failed_is_named_and_said_why(self):
        self.an_agent("alpha")
        self.given("0002_awkward", A_STEP_THAT_FAILS_FOR_ONE)
        gone_wrong = migration.carry_every(["alpha"], self.steps)
        self.assertIn("alpha", gone_wrong["alpha"])
        self.assertIn("0002_awkward", gone_wrong["alpha"])

    def test_they_are_carried_in_name_order(self):
        # So that a run over twenty agents reads the same way twice, and somebody comparing two
        # runs is comparing the runs rather than the order a directory happened to be walked in.
        for name in ("zulu", "alpha", "mike"):
            self.an_agent(name)
        self.given("0002_second")
        said = []
        migration.carry_every(directory.known(), self.steps, said.append)
        self.assertEqual(["alpha", "mike", "zulu"], [line.split()[1] for line in said])


class ABrandNewAgent(Steps):
    """Stamped without running, because there is nothing to carry."""

    def test_every_step_is_recorded_without_one_of_them_running(self):
        self.given("0002_second")
        self.given("0003_third")
        at = self.a_directory_for("cole")
        # Only the first step is really run — it is what builds the records at all. The rest are
        # stamped, exactly as a fresh install stamps the steps it never needed.
        migration.carry_one("cole", _only_the_first(self.steps, self.home))
        migration.stamp_without_running(directory.records("cole"), self.steps)
        self.assertEqual(["0001_the_records_an_agent_keeps", "0002_second", "0003_third"],
                         self.recorded("cole"))
        self.assertFalse((at / "0002_second").exists(), "a step ran against a brand new agent")

    def test_nothing_is_left_outstanding_afterwards(self):
        self.given("0002_second")
        self.a_directory_for("cole")
        migration.carry_one("cole", _only_the_first(self.steps, self.home))
        migration.stamp_without_running(directory.records("cole"), self.steps)
        self.assertEqual([], migration.outstanding(
            migration.recorded(directory.records("cole")), self.steps))

    def test_stamping_the_step_that_really_ran_is_not_an_error(self):
        # `0001` has already written its own row, in its own transaction. Re-stamping it is a
        # statement about something that is already true rather than a conflict.
        self.an_agent("cole")
        migration.stamp_without_running(directory.records("cole"), self.steps)
        self.assertEqual(["0001_the_records_an_agent_keeps"], self.recorded("cole"))

    def test_stamping_records_that_are_not_there_says_so(self):
        self.a_directory_for("cole")
        with self.assertRaises(records.NotThere):
            migration.stamp_without_running(directory.records("cole"), self.steps)


class HowAStepSplitsItsSql(Steps):
    """`executescript` drops the transaction, and splitting on `;` breaks the first trigger.

    Asked of the shipped first step, because it is the one that has to do this today and the one a
    later step author will copy.
    """

    def setUp(self):
        super().setUp()
        first = next(one for one in migration.found(self.steps) if one.id.startswith("0001"))
        # Loaded whole rather than through `scripts.carrying`, which hands back one callable: what
        # is under test here is the step's own splitting and the schema it splits.
        spec = importlib.util.spec_from_file_location("test_agent_first_step", first.at)
        self.step = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.step)
        self.statements = self.step.statements

    def test_a_statement_is_split_where_sqlite_says_one_ends(self):
        self.assertEqual(["SELECT 1;", "SELECT 2;"],
                         [one.strip() for one in self.statements("SELECT 1;\nSELECT 2;\n")])

    def test_a_trigger_body_is_not_split_at_its_own_semicolons(self):
        # The reason this is not `said.split(";")`. A trigger body carries semicolons of its own,
        # so the split that looks obvious hands `execute` half a trigger — and this build grows
        # triggers the moment there is full-text search over what an agent has said.
        trigger = ("CREATE TRIGGER seen AFTER INSERT ON config BEGIN\n"
                   "  UPDATE config SET last_seen_at = 'now';\n"
                   "  UPDATE config SET owner_name = 'nobody';\n"
                   "END;\n")
        self.assertEqual(1, len(list(self.statements(trigger))))

    def test_sql_that_never_finishes_a_statement_is_refused_rather_than_dropped(self):
        # Silently ignoring the tail would ship a step that lays down one table of two and reports
        # that it ran.
        with self.assertRaises(ValueError):
            list(self.statements("CREATE TABLE half (one TEXT) STRICT"))

    def test_the_schema_it_ships_really_is_more_than_one_statement(self):
        # Otherwise every case above is proving something about a step that never splits anything.
        self.assertGreater(len(list(self.statements(self.step.SCHEMA))), 1)

    def test_no_shipped_step_reaches_for_executescript(self):
        # The rule with the sharpest teeth in `steps/__init__.py`: `executescript` issues an
        # implicit COMMIT before it runs and silently drops the transaction around the step, so the
        # work and the row recording it stop being one thing. Checked over every step this release
        # ships rather than only the first, because the one that breaks it will be a later one.
        shipped = migration.found()
        self.assertTrue(shipped, "this release ships no agent steps at all")
        for step in shipped:
            with self.subTest(step=step.id):
                self.assertNotIn(".executescript(", step.at.read_text(encoding="utf-8"))

    def test_no_shipped_step_imports_anything_of_rundesks(self):
        # A step runs on agents carried forward by code that has moved on years past the release
        # that wrote it, and it is loaded from a file rather than imported as part of the package.
        for step in migration.found():
            with self.subTest(step=step.id):
                reached = {name.split(".")[0] for name in _imports(step.at)}
                self.assertNotIn("rundesk", reached)


def _imports(module: Path):
    """Every name this file imports, read off the source rather than by running it."""
    found = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"), str(module))):
        if isinstance(node, ast.Import):
            found.update(one.name for one in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _only_the_first(steps: Path, home: Path) -> Path:
    """A step directory holding just `0001`, which is what a brand new agent really runs.

    Here rather than in the fixture because only the brand-new-agent cases need it: everywhere else
    the point is that every outstanding step runs.
    """
    just_one = home / "first-step-only"
    just_one.mkdir(exist_ok=True)
    shutil.copy2(steps / "0001_the_records_an_agent_keeps.py", just_one)
    return just_one


if __name__ == "__main__":
    unittest.main()
