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
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Tuple
from unittest import mock

import support
from rundesk.agents import directory, migration, records
from rundesk.core import config, paths
from rundesk.utils import files

#: How long a case waits for the threads it started. Generous, because it is there to end a wedged
#: run rather than to measure anything — and bounded, because a run that never ends is a run nobody
#: reads.
PATIENCE_SECONDS = 60.0

#: A step that changes a table and a file together, which is the whole reason a step is handed both.
A_STEP = '''
from pathlib import Path

def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS "{name}" (one TEXT) STRICT')
    (Path(where) / "{name}").write_text("{name}")
'''

#: A step that writes inside the agent's `home/`, which is a directory the rollback has to put back
#: whole rather than one file at a time.
A_STEP_THAT_WRITES_INTO_HOME = '''
from pathlib import Path

def carry(conn, where):
    (Path(where) / "home" / "notes.md").write_text("what the step wrote")
'''

#: A step that writes into `logs/` and then cannot finish — the one place a rollback deliberately
#: does not reach, because rolling back the record of what just went wrong is backwards.
A_STEP_THAT_LOGS_AND_FAILS = '''
from pathlib import Path

def carry(conn, where):
    (Path(where) / "logs" / "what_went_wrong.log").write_text("the step was here")
    raise RuntimeError("this step could not finish")
'''

#: A step that writes into `channels/`, which a rollback does not cover. It makes the directory
#: itself, because an agent with no channels configured does not carry an empty one.
A_STEP_THAT_WRITES_INTO_CHANNELS = '''
from pathlib import Path

def carry(conn, where):
    at = Path(where) / "channels" / "dm"
    at.mkdir(parents=True, exist_ok=True)
    (at / "lock").write_text("")
'''

#: A step that takes long enough for somebody else to reach the same agent while it is running.
#: Used only where the case is about two callers meeting, and short enough to cost a run nothing.
A_SLOW_STEP = '''
import time

def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS slowly (one TEXT) STRICT')
    time.sleep(0.2)
'''

#: A step that ends the runner's transaction from inside itself. With `isolation_level=None` the
#: standard library manages nothing, so this really does commit and everything after it — including
#: the runner's own row — lands in a separate autocommit.
A_STEP_THAT_COMMITS = '''
def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS committed_early (one TEXT) STRICT')
    conn.commit()
'''

#: The same trap one step further on: the rule bans `executescript()`, and `COMMIT` by hand does
#: exactly what `executescript()` was banned for.
A_STEP_THAT_COMMITS_BY_HAND = '''
def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS committed_early (one TEXT) STRICT')
    conn.execute("COMMIT")
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

#: A step that fails *and* makes the rollback fail, for proving that an agent left neither carried
#: nor put back is said out loud.
#:
#: **It takes the write bit off the agent's directory, not off the database.** Making the file
#: read-only used to be enough, because the restore copied onto the live file and could not open it
#: for writing. The restore is now staged beside its destination and renamed into place, and
#: `os.replace` asks permission of the *directory* — so a read-only database is now restored
#: perfectly well, which is a better product and a worse way to fail on purpose.
A_STEP_THAT_CANNOT_BE_PUT_BACK = '''
import os
from pathlib import Path

def carry(conn, where):
    os.chmod(Path(where), 0o500)
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

    def traced(self) -> List[str]:
        """Every statement the runner really hands SQLite, in order, across every connection.

        Asked of the driver rather than counting this module's own calls, which is the difference
        between proving the property and proving nothing: a step that commits inside itself takes
        exactly one `records.writing` and two transactions.
        """
        said: List[str] = []
        real = records._opened

        def opened(where, uri):
            conn = real(where, uri)
            conn.set_trace_callback(said.append)
            return conn

        self.addCleanup(setattr, records, "_opened", real)
        records._opened = opened
        return said


def where_it_says(said: List[str], fragment: str) -> List[int]:
    """Every position in `said` holding this fragment, asked without regard to case."""
    return [which for which, one in enumerate(said) if fragment.upper() in one.upper()]


def at_once(jobs: List[Callable[[], object]]) -> Tuple[List[object], List[str]]:
    """Run these callables in real threads, started together. Returns what each gave, and who hung.

    **Real threads rather than a simulated interleaving.** `flock` is held per open file description
    and `locking.only_one` counts nesting per thread, so two threads in one process contend for the
    install lock exactly as two processes do — which is the whole thing being proved.

    The wait is bounded: a case that can hang for ever is worse than one that fails, because a run
    that never ends is a run nobody reads.
    """
    answers: List[object] = [None] * len(jobs)
    together = threading.Barrier(len(jobs), timeout=PATIENCE_SECONDS)

    def run(which: int, job: Callable[[], object]) -> None:
        together.wait()
        try:
            answers[which] = job()
        except Exception as why:      # noqa: BLE001 — what a racing caller saw *is* the answer here
            answers[which] = why

    threads = [threading.Thread(target=run, args=(which, job), daemon=True)
               for which, job in enumerate(jobs)]
    for one in threads:
        one.start()
    for one in threads:
        one.join(PATIENCE_SECONDS)
    return answers, [one.name for one in threads if one.is_alive()]


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

    def test_the_sentence_names_a_deleted_or_renamed_step_as_well(self):
        # From here the two are indistinguishable, and the second is much the likelier for a
        # developer to have just caused: a step file that had already shipped was renamed or taken
        # out of this checkout. Naming only the newer release sent somebody looking for a rundesk
        # that does not exist.
        with self.assertRaises(migration.Ahead) as refused:
            migration.outstanding(["0001_the_records_an_agent_keeps", "0002_taken_away"],
                                  self.steps)
        self.assertIn("0002_taken_away", str(refused.exception))
        self.assertIn("deleted or renamed", str(refused.exception))

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
        # The guarantee, asked of SQLite rather than of this module. Counting how many times
        # `records.writing` was *called* proved nothing: a step that calls commit() inside itself
        # takes one context manager and two transactions, so that count stayed at one while the
        # property it was named for was broken. What is counted here is the statements the driver
        # really ran — one BEGIN, one COMMIT, and both the work and the row between them.
        self.an_agent("cole")
        self.given("0002_second")
        said = self.traced()
        self.assertIsNone(migration.carry_one("cole", self.steps))

        begun = where_it_says(said, "BEGIN")
        committed = where_it_says(said, "COMMIT")
        work = where_it_says(said, 'CREATE TABLE IF NOT EXISTS "0002_second"')
        row = where_it_says(said, "INSERT INTO migrations")
        self.assertEqual(1, len(begun), f"one step and its row took {len(begun)} transactions")
        self.assertEqual(1, len(committed), f"one step and its row took {len(committed)} commits")
        self.assertEqual(1, len(work), "the step's own statement was not run exactly once")
        self.assertEqual(1, len(row), "the row recording the step was not written exactly once")
        self.assertLess(begun[0], work[0], "the step's work ran outside the transaction")
        self.assertLess(work[0], row[0])
        self.assertLess(row[0], committed[0], "the row was written after the commit")

    def refused_for_ending_the_transaction(self, name: str, body: str) -> None:
        """Drive one step that ends the runner's transaction, and check every part of the refusal.

        **The row is what has teeth here.** Without the check, `records.writing`'s own `COMMIT`
        fails on the way out and the carry does report a failure — but only after the runner has
        already written `INSERT INTO migrations` in an autocommit of its own, which is precisely
        the row that a crash a moment earlier would have left standing alone. So what is asserted
        is that the row was never written at all, and that the sentence says what the step did
        rather than handing somebody `cannot commit - no transaction is active`.
        """
        self.an_agent("cole")
        self.given(name, body)
        said = self.traced()
        gone_wrong = migration.carry_one("cole", self.steps)

        self.assertIsNotNone(gone_wrong, "a step that committed was carried as though it were fine")
        self.assertIn(name, gone_wrong)
        self.assertIn("ended the transaction", gone_wrong)
        self.assertEqual([], where_it_says(said, "INSERT INTO migrations"),
                         "a row was written outside the transaction its own work was in")
        self.assertNotIn("committed_early", self.tables("cole"),
                         "a step's own commit survived the rollback")
        self.assertNotIn(name, self.recorded("cole"))

    def test_a_step_that_calls_commit_is_refused(self):
        # `executescript()` is banned because it commits. `commit()` does the same thing and was
        # banned by nothing: with `isolation_level=None` it ends the transaction the runner opened,
        # so everything after it — including the row recording the step — commits on its own.
        self.refused_for_ending_the_transaction("0002_committing", A_STEP_THAT_COMMITS)

    def test_a_step_that_commits_by_hand_is_refused_too(self):
        # The same trap one step further on, and the one a step author reaches for after reading
        # that `executescript()` is not allowed.
        self.refused_for_ending_the_transaction("0002_by_hand", A_STEP_THAT_COMMITS_BY_HAND)

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
        # The file too, and this is the half the case used to leave out. `0003_third` writes a
        # table *and* a file, which is the whole reason a step is handed both — asserting only on
        # the table left this green while a rolled-back step's files stayed on disk, disagreeing
        # with records that no longer mention them.
        self.assertFalse((directory.where("cole") / "0003_third").exists(),
                         "a step's file survived a rollback that put its table back")

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

    def test_the_records_are_never_half_restored_however_the_restore_is_interrupted(self):
        # The property the old restore could not have. It copied straight onto the live database,
        # which truncates it to nothing before writing a byte — so a machine that died partway
        # through a rollback left the records neither carried nor put back but *truncated*, which is
        # a state nothing recovers from. And a rollback runs after something has already gone wrong,
        # so it is the likeliest moment for that to happen, not the least.
        #
        # Driven by making the rename itself fail, which is the last instruction of the restore:
        # everything before it has run, so if any of it wrote onto the live file this case sees it.
        was = directory.records("cole").read_bytes()
        self.given("0003_broken", A_STEP_THAT_FAILS)

        def refuse(_staged, _one):
            raise OSError("interrupted exactly here")

        with mock.patch("rundesk.agents.migration.os.replace", side_effect=refuse):
            gone_wrong = migration.carry_one("cole", self.steps)

        self.assertIn("could not be put back", gone_wrong)
        self.assertEqual(was, directory.records("cole").read_bytes(),
                         "the live records were written into before the rename")

    def test_a_rollback_that_itself_fails_is_said_out_loud(self):
        # An agent left neither carried nor put back is the one state somebody has to be told
        # about, rather than counted in a summary of how many failed.
        self.given("0003_stuck", A_STEP_THAT_CANNOT_BE_PUT_BACK)
        self.addCleanup(os.chmod, str(directory.where("cole")), 0o700)
        gone_wrong = migration.carry_one("cole", self.steps)
        self.assertIn("0003_stuck", gone_wrong)
        self.assertIn("could not be put back", gone_wrong)

    def test_the_copy_is_kept_when_the_rollback_failed(self):
        # It is the only way back. Letting go of it because the operation is over would take away
        # the one thing that could still repair the agent.
        self.given("0003_stuck", A_STEP_THAT_CANNOT_BE_PUT_BACK)
        self.addCleanup(os.chmod, str(directory.where("cole")), 0o700)
        migration.carry_one("cole", self.steps)
        self.assertTrue((directory.where("cole") /
                         files.OUTGOING.format(name=migration.ASIDE)).is_dir())


class WhatARollbackCovers(Steps):
    """The agent's whole directory, apart from what `NOT_PUT_BACK` names.

    A step is handed a connection *and* the agent's directory precisely so it can change tables and
    files together. A rollback that put back only `state.db` therefore restored half of what a step
    had done: the records said the step never happened and its files were still standing there, and
    the next step doing "check, then act" against one of them was answered by a shape nothing had
    recorded. Three reviewers reproduced that against the real code.
    """

    def setUp(self):
        super().setUp()
        self.given("0002_second")
        self.an_agent("cole")

    def test_a_file_a_step_wrote_goes_back_with_the_table_it_wrote(self):
        self.given("0003_third")
        self.given("0004_broken", A_STEP_THAT_FAILS)
        migration.carry_one("cole", self.steps)
        self.assertFalse((directory.where("cole") / "0003_third").exists(),
                         "a file a step wrote outlived the records that recorded it")

    def test_a_file_a_step_wrote_inside_a_directory_goes_back_too(self):
        # `home/` is a directory rather than a file, which is the one shape a single atomic rename
        # cannot put back — so it is the shape a snapshot of `state.db` alone missed most quietly.
        self.given("0003_meddling", A_STEP_THAT_WRITES_INTO_HOME)
        self.given("0004_broken", A_STEP_THAT_FAILS)
        migration.carry_one("cole", self.steps)
        self.assertFalse((directory.home("cole") / "notes.md").exists(),
                         "a file a step wrote inside home/ outlived the rollback")

    def test_what_the_owner_had_there_first_is_put_back_exactly(self):
        # The other half: a rollback that removed everything a step touched would be a rollback
        # that took the owner's own file with it.
        (directory.home("cole") / "notes.md").write_text("what the owner wrote", encoding="utf-8")
        self.given("0003_meddling", A_STEP_THAT_WRITES_INTO_HOME)
        self.given("0004_broken", A_STEP_THAT_FAILS)
        migration.carry_one("cole", self.steps)
        self.assertEqual("what the owner wrote",
                         (directory.home("cole") / "notes.md").read_text(encoding="utf-8"))

    def test_the_log_of_what_went_wrong_is_the_one_thing_left_alone(self):
        # Deliberate, and named in `migration.NOT_PUT_BACK`: rolling back the record of what has
        # just gone wrong is backwards — those lines are what somebody reads afterwards.
        self.given("0003_broken", A_STEP_THAT_LOGS_AND_FAILS)
        migration.carry_one("cole", self.steps)
        self.assertTrue((directory.logs("cole") / "what_went_wrong.log").is_file(),
                        "the record of the failure was rolled back along with the failure")

    def test_what_a_channel_keeps_is_left_alone_too(self):
        # Named in `migration.NOT_PUT_BACK` on two counts. A running adapter is holding a lock in
        # here and outlives a carry — a carry is a command, and the gateway hosting that adapter is
        # a different process that knows nothing about it, so putting the lock file back underneath
        # a live child puts back a claim that has moved on. It is also unbounded, holding every file
        # that has ever arrived through a channel.
        self.given("0003_channelling", A_STEP_THAT_WRITES_INTO_CHANNELS)
        self.given("0004_broken", A_STEP_THAT_FAILS)
        migration.carry_one("cole", self.steps)
        self.assertTrue((directory.channels("cole") / "dm" / "lock").is_file(),
                        "what a channel keeps was rolled back along with the step that failed")

    def test_the_records_go_back_before_the_files_do(self):
        # Nothing is atomic across several renames, so the order decides what an interruption
        # between two of them leaves. Records first means any file not yet put back belongs to a
        # step the records no longer claim, and the next carry runs that step again — which every
        # step is written to be safe about. Records last leaves the shape nothing recovers from:
        # records saying a step ran, standing over the files that were taken back out from under
        # it, and a next carry that skips the very step that would have rebuilt them.
        self.given("0003_meddling", A_STEP_THAT_WRITES_INTO_HOME)
        self.given("0004_broken", A_STEP_THAT_FAILS)
        put_back = []
        real = os.replace

        def watched(staged, one):
            put_back.append(Path(one).name)
            return real(staged, one)

        with mock.patch("rundesk.agents.migration.os.replace", side_effect=watched):
            migration.carry_one("cole", self.steps)
        self.assertIn(directory.RECORDS, put_back, "the records were never put back")
        self.assertIn(directory.HOME, put_back, "the agent's home was never put back")
        self.assertLess(put_back.index(directory.RECORDS), put_back.index(directory.HOME),
                        "the files went back before the records that say which steps ran")

    def test_the_sentence_says_what_was_put_back_rather_than_claiming_the_agent_is_untouched(self):
        # It must not read as "the agent is exactly as it was", because the logs are not — and a
        # promise that is true of most of a directory is the kind nobody checks.
        self.given("0003_broken", A_STEP_THAT_FAILS)
        gone_wrong = migration.carry_one("cole", self.steps)
        self.assertIn("its records and its files were put back", gone_wrong)
        self.assertIn(directory.LOGS, gone_wrong)


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


class AStepNumberedBelowOneAlreadyRun(Steps):
    """The append-only rule, checked rather than asserted in prose in three docstrings.

    A step's number has to be above every number any previously shipped release used. Broken, an
    agent runs the back-filled step *after* the steps that were written assuming it had already
    happened — and an install, which records one id rather than a row set, never runs it at all and
    reports a success it did not earn.
    """

    def setUp(self):
        super().setUp()
        self.given("0010_later")
        self.an_agent("cole")             # carried to 0001 and 0010

    def test_a_step_back_filled_below_what_has_run_is_refused(self):
        self.given("0005_backfilled")     # a release that broke the rule
        gone_wrong = migration.carry_one("cole", self.steps)
        self.assertIsNotNone(gone_wrong, "a back-filled step was carried as though it were fine")
        self.assertIn("0005_backfilled", gone_wrong)

    def test_it_is_refused_rather_than_run_out_of_order(self):
        # The half that is worse than skipping it: `0010` was written expecting `0005` to have
        # happened, so running `0005` afterwards applies it to a shape it was never written for.
        self.given("0005_backfilled")
        migration.carry_one("cole", self.steps)
        self.assertNotIn("0005_backfilled", self.tables("cole"))
        self.assertNotIn("0005_backfilled", self.recorded("cole"))
        self.assertFalse((directory.where("cole") / "0005_backfilled").exists())

    def test_the_sentence_says_what_to_do_about_it(self):
        # Somebody reading this has a file to move, and the answer is never "renumber it back".
        self.given("0005_backfilled")
        gone_wrong = migration.carry_one("cole", self.steps)
        self.assertIn("new step", gone_wrong)
        self.assertIn("0010", gone_wrong)

    def test_outstanding_names_it_rather_than_handing_it_back_to_be_run(self):
        self.given("0005_backfilled")
        with self.assertRaises(migration.Backfilled) as refused:
            migration.outstanding(self.recorded("cole"), self.steps)
        self.assertIn("0005_backfilled", str(refused.exception))

    def test_a_gap_above_what_has_run_is_still_perfectly_fine(self):
        # Only *below* is ambiguous. Steps are appended and nothing says they must be contiguous.
        self.given("0020_much_later")
        self.assertIsNone(migration.carry_one("cole", self.steps))
        self.assertIn("0020_much_later", self.recorded("cole"))


class TwoOfThemAtOnce(Steps):
    """Two callers reaching one agent together, which nothing here used to try.

    `BEGIN IMMEDIATE` protects the database *file*. It says nothing at all about the copy-aside and
    put-back bracket wrapped around the steps, which is plain file copying — and that gap is where
    three separate failures lived, invisible because no case ever ran two of anything at once.
    """

    def test_making_an_agent_carries_it_under_the_lock_it_already_holds(self):
        # `directory.made` takes the install lock and then calls `carry_one`, which takes the same
        # one. `locking.only_one` counts nesting per thread, so the inner one passes straight
        # through; taken again for real it would wait for itself until the ceiling and then say
        # something else had been changing the install for five minutes.
        at = directory.made("nina", "anthropic")
        self.assertTrue((at / directory.RECORDS).is_file())
        self.assertEqual(["nina"], directory.known())

    def test_two_carries_of_one_agent_never_undo_each_other(self):
        # Measured before the lock went round the whole of `carry_one`: the second copies the agent
        # aside before the first has committed anything, loses the race for the write lock, decides
        # it has failed, and puts that copy back — retracting a step the first already reported as
        # done, with nobody told. The loser's own rollback was the danger, never the refusal.
        self.an_agent("cole")
        self.given("0002_second")
        answers, hung = at_once([lambda: migration.carry_one("cole", self.steps),
                                 lambda: migration.carry_one("cole", self.steps)])
        self.assertEqual([], hung, "a carry never finished")
        self.assertEqual([None, None], answers,
                         f"a carry of an agent nothing else was changing failed: {answers}")
        self.assertIn("0002_second", self.recorded("cole"), "a committed step was retracted")
        self.assertIn("0002_second", self.tables("cole"))
        self.assertTrue((directory.where("cole") / "0002_second").is_file())

    def test_neither_of_them_leaves_a_copy_behind(self):
        # A carry that succeeded lets go of what it set aside. Two that raced must not leave one
        # holding the other's, or the next make finds an agent directory full of staging names.
        self.an_agent("cole")
        self.given("0002_second")
        at_once([lambda: migration.carry_one("cole", self.steps),
                 lambda: migration.carry_one("cole", self.steps)])
        self.assertEqual([], [one.name for one in directory.where("cole").iterdir()
                              if files.staged(one.name)])

    def test_a_carry_and_a_removal_of_one_agent_do_not_interleave(self):
        # Whichever goes first, the other sees what it did. Without the lock on both sides the
        # removal reported an agent gone and the carry's rollback then put it back — a removal that
        # did not happen, reported as one.
        self.an_agent("cole")
        self.given("0002_second")
        answers, hung = at_once([lambda: migration.carry_one("cole", self.steps),
                                 lambda: directory.forgotten("cole")])
        carried, removed = answers
        self.assertEqual([], hung, "a carry or a removal never finished")
        self.assertNotIsInstance(removed, Exception, f"the removal failed: {removed}")
        # The records are what make a directory an agent, so they are what a removal has to have
        # really removed. The directory itself is kept whenever anything else is standing in it,
        # which after a successful carry is the file the step wrote — that is `forgotten`'s own
        # documented answer and not a removal that half happened.
        self.assertFalse(directory.records("cole").exists(),
                         "the removal was reported and the records came back")
        self.assertNotIn("cole", directory.known(), "the removal was reported and the agent is here")
        if carried is not None:
            # The removal went first, so the carry has to say it could not be done rather than
            # report a success against records that were taken away underneath it.
            self.assertIn("could not be carried", carried)

    def test_a_carry_that_fails_never_puts_back_an_agent_somebody_removed(self):
        # The sharp end of the same race, and the reason a removal takes the lock too. A carry
        # copies the agent aside; a removal walks in while a step is still running and reports the
        # agent gone; the carry's next step fails and its rollback puts the whole agent back. The
        # removal did not happen, and it was reported as though it had.
        self.an_agent("cole")
        self.given("0002_slow", A_SLOW_STEP)
        self.given("0003_broken", A_STEP_THAT_FAILS)
        remover = threading.Thread(target=directory.forgotten, args=("cole",), daemon=True)

        def while_carrying(line: str) -> None:
            # Asked for at the one moment that matters rather than at the same instant as the
            # carry: the copy aside has been taken and a step is running, which is exactly what a
            # removal has to be made to wait for.
            if line.endswith("0002_slow"):
                remover.start()

        carried = migration.carry_one("cole", self.steps, while_carrying)
        remover.join(PATIENCE_SECONDS)
        self.assertFalse(remover.is_alive(), "the removal never finished")
        self.assertIsNotNone(carried, "the carry reported a success although a step failed")
        self.assertFalse(directory.records("cole").exists(),
                         "a rollback put back an agent that had been removed and reported gone")
        self.assertNotIn("cole", directory.known())

    def test_a_sweep_holds_the_lock_from_the_first_agent_to_the_last(self):
        # Once around the whole sweep, never once per agent. Picked up and put down between agents,
        # another writer lands in every gap — so a sweep that reported twenty agents carried would
        # be reporting on an install that changed halfway through it.
        self.an_agent("alpha")
        self.an_agent("zulu")
        self.given("0002_second")
        maker = threading.Thread(target=directory.made, args=("nina", "anthropic"), daemon=True)
        between = []
        real = migration.carry_one
        self.addCleanup(setattr, migration, "carry_one", real)

        def carried(name, where=None, saying=None):
            # The seam between one agent and the next, held open long enough to look at. Somebody
            # else is already asking for the lock; a lock taken per agent is free right here and
            # they walk in, and a lock taken once around the whole sweep is not, so this simply
            # runs out. Bounded either way — how long this case is willing to be wrong for.
            if name == "alpha":
                maker.start()
            elif name == "zulu":
                support.waited_until(lambda: "nina" in directory.known(), 0.5)
                between.append(directory.known())
            return real(name, where, saying)

        migration.carry_one = carried
        self.assertEqual({}, migration.carry_every(["alpha", "zulu"], self.steps))
        maker.join(PATIENCE_SECONDS)
        self.assertFalse(maker.is_alive(), "the make never finished")
        self.assertNotIn("nina", between[0], "an agent was made in the middle of a sweep")
        self.assertIn("nina", directory.known(), "the make never happened at all")

    def test_a_carry_and_a_make_of_a_different_agent_take_turns(self):
        # `directory.made` holds this same lock and then calls `carry_one`, so the nesting has to
        # pass straight through rather than wait for itself until the ceiling and fail.
        self.an_agent("cole")
        self.given("0002_second")
        answers, hung = at_once([lambda: migration.carry_one("cole", self.steps),
                                 lambda: directory.made("nina", "anthropic")])
        self.assertEqual([], hung, "a carry or a make never finished")
        self.assertIsNone(answers[0], f"the carry failed: {answers[0]}")
        self.assertNotIsInstance(answers[1], Exception, f"the make failed: {answers[1]}")
        self.assertEqual(["cole", "nina"], directory.known())


class TheMomentAStepLanded(Steps):
    """`completed_at`, which nothing asserted the shape of until now.

    Anything a machine will order or compare is UTC to the second, in `core.config.MOMENT` — a
    database copied off this machine and restored on another must still sort into the order things
    happened, and a local stamp carries an offset the restoring machine does not have.
    """

    def recorded_at(self, name: str) -> List[str]:
        with records.reading(directory.records(name)) as conn:
            return [row[0] for row in conn.execute("SELECT completed_at FROM migrations")]

    def test_a_step_that_ran_records_the_moment_in_the_shape_a_machine_can_order(self):
        self.given("0002_second")
        self.an_agent("cole")
        moments = self.recorded_at("cole")
        self.assertEqual(2, len(moments))
        for moment in moments:
            with self.subTest(moment=moment):
                datetime.strptime(moment, config.MOMENT)     # raises if it is any other shape

    def test_a_step_stamped_without_running_records_the_same_shape(self):
        # The other way a row gets written, and it used to be the same literal typed twice.
        self.given("0002_second")
        self.a_directory_for("cole")
        migration.carry_one("cole", _only_the_first(self.steps, self.home))
        migration.stamp_without_running(directory.records("cole"), self.steps)
        for moment in self.recorded_at("cole"):
            with self.subTest(moment=moment):
                datetime.strptime(moment, config.MOMENT)

    def test_it_is_utc_and_not_this_machine_s_own_clock(self):
        # The shape alone cannot tell them apart — both end in `Z` and both parse. What tells them
        # apart is the value, and only on a machine whose own clock is not UTC.
        here = datetime.now().replace(microsecond=0)
        universal = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        if abs((here - universal).total_seconds()) < 120:
            self.skipTest("this machine's clock is UTC, so the two cannot be told apart here")
        self.an_agent("cole")
        landed = datetime.strptime(self.recorded_at("cole")[0], config.MOMENT)
        self.assertLess(abs((landed - universal).total_seconds()), 120,
                        "the moment was written in this machine's own offset")


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


class WhatThisReleaseReallyShips(support.Isolated):
    """The real steps against a real agent, with nothing patched.

    Every class above works in a scratch step directory, which is what lets them drive failures and
    orderings that no shipped step has. The cost is that none of them ever runs what is actually in
    `agents/steps/` — so a step that ships broken, or one whose table never lands, passes every one
    of them. This is the case that opens the agent the product just made and looks.
    """

    def test_the_steps_this_release_ships_are_numbered_in_order_and_unique(self):
        shipped = migration.found()
        self.assertTrue(shipped, "this release ships no agent migration steps at all")
        numbers = [step.order for step in shipped]
        self.assertEqual(sorted(set(numbers)), numbers,
                         "two shipped steps share a number, or they are not in order")

    def test_a_brand_new_agent_holds_every_table_this_release_expects(self):
        directory.made("cole", "claude")
        with records.reading(directory.records("cole")) as conn:
            there = {row[0] for row in
                     conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertLessEqual({"config", "migrations", "schedules"}, there)

    def test_a_brand_new_agent_is_stamped_with_every_step_and_has_none_outstanding(self):
        directory.made("cole", "claude")
        applied = migration.recorded(directory.records("cole"))
        self.assertEqual([step.id for step in migration.found()], sorted(applied))
        self.assertEqual([], migration.outstanding(applied))

    def test_an_agent_carried_from_the_first_step_alone_reaches_the_same_shape(self):
        # The other way in, and the one every existing agent on a real machine takes: records built
        # by `0001` and then carried forward. A step that only ever runs against a brand new agent
        # is a step nobody's actual data has been through.
        at = directory.where("cole")
        (at / directory.HOME).mkdir(parents=True)
        (at / directory.LOGS).mkdir()
        self.assertIsNone(migration.carry_one("cole", _only_the_first(migration.STEPS, self.home)))
        self.assertIsNone(migration.carry_one("cole"))
        with records.reading(directory.records("cole")) as conn:
            there = {row[0] for row in
                     conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertIn("schedules", there)
        self.assertEqual([], migration.outstanding(migration.recorded(directory.records("cole"))))

    def test_carrying_an_agent_that_already_has_every_step_changes_nothing(self):
        # Rule 5: a step is safe against an agent that does not need it. Proved by running the whole
        # carry twice and requiring the second to be a no-op rather than a refusal.
        directory.made("cole", "claude")
        self.assertIsNone(migration.carry_one("cole"))
        self.assertEqual([step.id for step in migration.found()],
                         sorted(migration.recorded(directory.records("cole"))))


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
