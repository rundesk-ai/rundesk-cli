"""Bringing an owner's records forward when rundesk moves on — every claim `migration.py` makes.

Nothing here reaches the network, starts a gateway, runs a program or goes near the machine's
own `~/.rundesk`: a database is a path and a step is a file, so each case gets a directory of
its own and **writes the steps it is about itself**. `found`, `between` and `carry` all take a
`where=`, which is the whole reason that works — a suite reading what happens to ship would
prove only what is in `migrations/` today, and would change meaning every time a step lands.
The cases about the shape an agent starts with are the exception, and say so.

Every connection a case opens itself is closed — a leaked one holds the WAL read lock on newer
Pythons and not on the floor version, so the leak is invisible exactly where CI would catch it.

Run: python3 tests/test_migration.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import migration, store  # noqa: E402

AT = "2026-07-26T09:00:00Z"

# What a step that is never meant to run looks like — enough to be found, and no work in it.
NOTHING = "def up(conn, home):\n    return []\n"

# Whatever a case wants to go wrong part-way through a step, arranged as a file rather than as
# a second copy of the step: the same step file then finishes or does not, and a case can prove
# what running the fixed one again does without the two ever having been different steps.
TRIPS = ('    if (home / "trip").exists():\n'
         '        raise RuntimeError("the shape underneath was not what this step assumed")\n')


def signs(step: str) -> str:
    """The body of a step whose whole job is to say it ran, and when."""
    return ("def up(conn, home):\n"
            f"    conn.execute(\"INSERT INTO ran (step) VALUES ('{step}')\")\n"
            "    return []\n")


def working(column: str, step: str, then: str = "") -> str:
    """The body of a step that really changes the records, and signs the ledger for it.

    A column the shape did not have, a value written into it and a line in the ledger — so
    what a step did, and whether it ever did it twice, is readable afterwards.
    """
    return (
        "def up(conn, home):\n"
        f'    conn.execute("ALTER TABLE agent ADD COLUMN {column} TEXT")\n'
        f"    conn.execute(\"UPDATE agent SET {column} = '{step}' WHERE id = 1\")\n"
        f"    conn.execute(\"INSERT INTO ran (step) VALUES ('{step}')\")\n"
        f"{then}"
        "    return []\n"
    )


# One step file, used by both of the cases about files: it copies, it does its work on the
# records, and it hands back what is now spare. Whether that work fails is the trip file's
# doing, so neither case is arguing with a step the other one did not run.
COPYING = '''
def up(conn, home):
    import shutil

    was = home / "kept" / "what-was-said.json"
    now = home / "moved" / "what-was-said.json"
    now.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(was), str(now))
    conn.execute("UPDATE agent SET instructions = 'what was said lives beside the records now'"
                 " WHERE id = 1")
    if (home / "trip").exists():
        raise RuntimeError("the records would not take what the file said")
    return [str(was)]
'''


class WithStepsOfThisCasesOwn(unittest.TestCase):
    """An agent's records to move, a directory of steps this case wrote, and nothing else."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-migration-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.steps = self.where / "steps"
        self.steps.mkdir()
        # Named as an agent is, because a step's line says which agent is being moved.
        self.home = self.where / "ops"
        self.home.mkdir()
        self.at = store.path_for(self.home)

    def records(self) -> store.Store:
        """One agent's records, as `store.py` really makes them."""
        kept = store.Store(self.at)
        kept.made()
        return kept

    def raw(self):
        """A connection of the case's own, for asking what no caller may ask.

        Registered for closing the moment it exists: a connection left to the garbage
        collector keeps its lock, and closing twice is harmless.
        """
        conn = sqlite3.connect(str(self.at), isolation_level=None, timeout=5.0)
        self.addCleanup(conn.close)
        return conn

    def wrote(self, version, body: str) -> Path:
        """A step file, dropped into this case's directory. Nothing is told that it is there.

        The version is the whole of the name — given as text where a case is about the name
        itself, and as a number where it is not.
        """
        at = self.steps / (version if isinstance(version, str) else f"{version:03d}.py")
        at.write_text(textwrap.dedent(body).lstrip("\n"))
        return at

    def ledger(self) -> None:
        """A table of the case's own for a step to sign, so what ran — and in what order — is
        readable afterwards. Made outside the migration, so a step that is rolled back takes
        its line back with it."""
        self.raw().execute(
            "CREATE TABLE ran (n INTEGER PRIMARY KEY AUTOINCREMENT, step TEXT NOT NULL)"
        )

    def ran(self) -> list:
        return [row[0] for row in self.raw().execute("SELECT step FROM ran ORDER BY n")]

    def stamped(self) -> int:
        """The version the data on disk says it is."""
        return int(self.raw().execute("PRAGMA user_version").fetchone()[0])

    def columns(self, table: str = "agent") -> list:
        return sorted(row[1] for row in self.raw().execute(f"PRAGMA table_info({table})"))

    def named(self, steps) -> list:
        return [repr(step) for step in steps]


class WhichStepsThereAre(WithStepsOfThisCasesOwn):
    """A step is found, not listed — and what is found is ordered by the number it carries."""

    def test_a_step_dropped_into_the_directory_is_found_without_a_list_being_edited(self):
        """The claim the whole module rests on. Nothing is told a step exists: the same
        directory answers differently the moment a file lands in it, and no list anywhere
        was touched to make that happen."""
        self.assertEqual([], self.named(migration.found(self.steps)))
        self.wrote(2, NOTHING)
        self.assertEqual(["002.py"], self.named(migration.found(self.steps)))
        self.wrote(3, NOTHING)
        self.assertEqual(["002.py", "003.py"], self.named(migration.found(self.steps)))

    def test_steps_are_ordered_by_the_number_they_carry_and_never_by_their_name(self):
        """`010` runs after `009` and not after `001`, and the odd `2.py` is there on
        purpose: read as names rather than as numbers, these four sort `001`, `009`, `010`,
        `2` — so a sort that looks right on padded files alone is caught here."""
        self.ledger()
        for name, step in (("001.py", "001"), ("2.py", "2"), ("009.py", "009"),
                           ("010.py", "010")):
            self.wrote(name, signs(step))
        self.assertEqual(["001.py", "2.py", "009.py", "010.py"],
                         self.named(migration.found(self.steps)))
        self.assertEqual(10, migration.carry(self.at, self.home, 10, where=self.steps))
        self.assertEqual(["001", "2", "009", "010"], self.ran(),
                         "the order came off the name rather than the number")

    def test_only_what_is_above_the_shape_on_disk_and_at_or_below_the_one_installed_runs(self):
        """Both ends matter. A step at or below what the data already is has run; a step
        above what this rundesk installs describes a shape this code does not have."""
        for version in (2, 3, 4, 5):
            self.wrote(version, NOTHING)
        self.assertEqual(["002.py", "003.py", "004.py", "005.py"],
                         self.named(migration.between(1, 5, where=self.steps)))
        self.assertEqual(["003.py", "004.py"],
                         self.named(migration.between(2, 4, where=self.steps)))
        self.assertEqual([], self.named(migration.between(5, 5, where=self.steps)),
                         "data already at the shape installed was given work to do")
        self.assertEqual([], self.named(migration.between(4, 2, where=self.steps)),
                         "a step back was offered, and there is no step back")

    def test_two_steps_claiming_one_version_are_refused_rather_than_one_of_them_chosen(self):
        """`2.py` beside `002.py` is the shape this really arrives in. Which of them ran
        would be whatever the filesystem felt like that morning, and the other would be lost
        without a word — so neither runs, and the number they both claim is named."""
        self.records()
        self.wrote("002.py", working("mark", "002"))
        self.wrote("2.py", working("other_mark", "2"))
        with self.assertRaises(ValueError) as refused:
            migration.found(self.steps)
        self.assertIn("two steps claim the same version", str(refused.exception))
        self.assertIn("[2]", str(refused.exception))
        with self.assertRaises(ValueError):
            migration.carry(self.at, self.home, 2, where=self.steps)
        self.assertEqual(store.VERSION, self.stamped(), "a refused directory still moved data")
        self.assertNotIn("mark", self.columns())

    def test_a_file_that_is_not_a_step_is_left_alone_rather_than_run(self):
        """A directory of steps is a directory people put things in: a README saying what a
        step is, a note to themselves, a helper somebody imported once, the copy an editor
        left behind."""
        (self.steps / "README.md").write_text("# how to write a step\n")
        (self.steps / "notes.txt").write_text("002 was harder than it looked\n")
        (self.steps / "_helper.py").write_text("def shared():\n    return 1\n")
        (self.steps / "002.py.bak").write_text("def up(conn, home):\n    x\n")
        self.wrote(2, NOTHING)
        self.assertEqual(["002.py"], self.named(migration.found(self.steps)))

    def test_a_number_with_a_description_after_it_is_not_a_step_and_does_not_run(self):
        """The name somebody will reach for, because every other migration tool wants one.
        The version is the whole of the name here, so this file is a note about a step and
        not a step — and it is silently nothing rather than quietly half of one."""
        self.records()
        self.wrote("002-agents-carry-a-mark.py", working("mark", "002"))
        self.assertEqual([], self.named(migration.found(self.steps)))
        self.assertEqual(store.VERSION,
                         migration.carry(self.at, self.home, 2, where=self.steps))
        self.assertEqual(store.VERSION, self.stamped())
        self.assertNotIn("mark", self.columns())

    def test_a_number_that_could_not_be_a_version_is_refused_rather_than_wrapped(self):
        """A version lives in the database header as a signed 32-bit integer: go past it and
        it wraps to zero, which is the value meaning "written partway and unreadable". A
        step numbered like a date is how that happens, so the number is checked instead."""
        self.wrote("21474836470.py", NOTHING)
        with self.assertRaises(ValueError) as refused:
            migration.found(self.steps)
        self.assertIn("21474836470.py", str(refused.exception))
        (self.steps / "21474836470.py").unlink()
        self.wrote("000.py", NOTHING)
        with self.assertRaises(ValueError):
            migration.found(self.steps)


class BringingRecordsForward(WithStepsOfThisCasesOwn):
    """What `carry` does, and what it declines to do."""

    def test_a_step_runs_once_and_running_again_finds_nothing_left_to_do(self):
        """There is no record of what has run because the version is the record, so this is
        the case that proves the record works. The step's own `ALTER` would fail on a second
        run, which is the belt to the ledger's braces."""
        self.records()
        self.ledger()
        self.wrote(2, working("mark", "002"))
        self.assertEqual(2, migration.carry(self.at, self.home, 2, where=self.steps))
        self.assertEqual(["002"], self.ran())
        self.assertIn("mark", self.columns())
        said = []
        self.assertEqual(2, migration.carry(self.at, self.home, 2, where=self.steps,
                                            note=said.append))
        self.assertEqual(["002"], self.ran(), "a step that had already run ran again")
        self.assertEqual([], said, "an update with nothing to do said it was doing something")
        self.assertEqual(2, self.stamped())

    def test_records_already_at_the_shape_installed_need_no_step(self):
        """A fresh agent is born at the shape this rundesk installs, so the first thing an
        update ever does to it is nothing at all."""
        self.records()
        self.wrote(store.VERSION,
                   'def up(conn, home):\n    raise AssertionError("a step ran that was not due")\n')
        said = []
        self.assertEqual(store.VERSION,
                         migration.carry(self.at, self.home, store.VERSION, where=self.steps,
                                         note=said.append))
        self.assertEqual([], said)
        self.assertEqual(store.VERSION, self.stamped())

    def test_data_newer_than_this_rundesk_understands_is_refused_rather_than_read(self):
        """The dangerous direction: this code cannot know what it is missing, so it would
        read a partial truth and write over the rest. Refused before a step is even looked
        at, and both versions are named."""
        self.records()
        self.ledger()
        self.raw().execute("PRAGMA user_version = 5")
        self.wrote(2, working("mark", "002"))
        with self.assertRaises(migration.Failed) as refused:
            migration.carry(self.at, self.home, 2, where=self.steps)
        self.assertEqual(5, refused.exception.reached)
        self.assertIn("version 5", str(refused.exception))
        self.assertIn("expects 2", str(refused.exception))
        self.assertEqual(5, self.stamped())
        self.assertEqual([], self.ran(), "data nobody understood was migrated anyway")
        self.assertNotIn("mark", self.columns())

    def test_a_step_with_no_up_to_run_is_refused_by_name_rather_than_skipped(self):
        """A step whose work is spelled anything but `up` has not run, and skipping it would
        stamp the version saying it had — the one lie the version-as-record cannot survive."""
        self.records()
        self.wrote(2, "def down(conn, home):\n    return []\n")
        with self.assertRaises(migration.Failed) as refused:
            migration.carry(self.at, self.home, 2, where=self.steps)
        self.assertIsInstance(refused.exception.why, AttributeError)
        self.assertIn("002.py", str(refused.exception))
        self.assertIn("no `up`", str(refused.exception))
        self.assertEqual(store.VERSION, self.stamped())

    def test_one_readable_line_is_said_for_every_step_that_runs(self):
        """An update stands every agent down, so what it is doing to each of them is the
        only thing an owner has to watch. One line per step, naming the agent and the
        version its records are going to."""
        self.records()
        self.ledger()
        self.wrote(2, working("mark", "002"))
        self.wrote(3, working("named_model", "003"))
        said = []
        self.assertEqual(3, migration.carry(self.at, self.home, 3, where=self.steps,
                                            note=said.append))
        self.assertEqual(["migrating ops to version 2", "migrating ops to version 3"], said)

    def test_nothing_is_said_when_there_is_nothing_to_do(self):
        """Most agents on most updates. An owner reading a line about work that did not
        happen learns to read none of them."""
        self.records()
        self.wrote(2, NOTHING)
        said = []
        self.assertEqual(store.VERSION,
                         migration.carry(self.at, self.home, store.VERSION, where=self.steps,
                                         note=said.append))
        self.assertEqual([], said)


class WhenAStepDoesNotFinish(WithStepsOfThisCasesOwn):
    """The whole promise: whole or not at all, and running again begins where it stopped."""

    def three_steps_the_middle_one_tripping(self) -> None:
        """An update of three steps that dies in the second, arranged so the same files can
        be run again once the trip is taken away."""
        self.records()
        self.ledger()
        self.wrote(2, working("mark", "002"))
        self.wrote(3, working("named_model", "003", TRIPS))
        self.wrote(4, working("caused_by", "004"))
        (self.home / "trip").write_text("this step is not right yet\n")

    def test_a_step_that_fails_leaves_the_data_exactly_as_it_was(self):
        """Real DDL and real DML, and then it raises. SQLite keeps schema changes inside the
        transaction, so neither the column, nor the row, nor the line in the ledger survives
        — and an owner whose update went wrong has lost nothing at all."""
        self.records()
        self.ledger()
        self.wrote(2, """
            def up(conn, home):
                conn.execute("ALTER TABLE agent ADD COLUMN badge TEXT")
                conn.execute("UPDATE agent SET badge = 'kept' WHERE id = 1")
                conn.execute(
                    "INSERT INTO channel (name, kind, allow, created_at)"
                    " VALUES ('ops', 'discord', '[]', '2026-07-26T09:00:00Z')")
                conn.execute("INSERT INTO ran (step) VALUES ('002')")
                raise RuntimeError("the shape underneath was not what this step assumed")
        """)
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, 2, where=self.steps)
        self.assertNotIn("badge", self.columns(), "a failed step left its column behind")
        self.assertEqual(0, self.raw().execute("SELECT count(*) FROM channel").fetchone()[0],
                         "a failed step left a row behind")
        self.assertEqual([], self.ran())
        self.assertEqual(store.VERSION, self.stamped())

    def test_a_steps_version_stamp_is_committed_with_its_work_and_never_apart_from_it(self):
        """The state that must not exist is the change present and the version not: an
        update run again would then do the work twice, and there is no record to stop it.
        One step file, tripped and then not, so the pair is read in both directions."""
        self.records()
        self.wrote(2, """
            def up(conn, home):
                conn.execute("ALTER TABLE agent ADD COLUMN mark TEXT")
                conn.execute("UPDATE agent SET mark = 'carried' WHERE id = 1")
                if (home / "trip").exists():
                    raise RuntimeError("the shape underneath was not what this step assumed")
                return []
        """)
        (self.home / "trip").write_text("not yet\n")
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, 2, where=self.steps)
        self.assertNotIn("mark", self.columns(),
                         "the work committed without the version that names it")
        self.assertEqual(store.VERSION, self.stamped())
        (self.home / "trip").unlink()
        self.assertEqual(2, migration.carry(self.at, self.home, 2, where=self.steps))
        self.assertIn("mark", self.columns())
        self.assertEqual(2, self.stamped(), "the work committed and the version did not follow")

    def test_a_step_that_finished_before_a_later_one_failed_stays_finished(self):
        """Each step is its own transaction, so an update stopped part-way is not one long
        thing rolled back — it is a version that moved as far as it honestly got."""
        self.three_steps_the_middle_one_tripping()
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, 4, where=self.steps)
        self.assertEqual(2, self.stamped(),
                         "the step that did finish was rolled back with the one that did not")
        self.assertEqual(["002"], self.ran())
        self.assertIn("mark", self.columns())
        self.assertNotIn("named_model", self.columns(), "the step that failed left work behind")
        self.assertNotIn("caused_by", self.columns(), "a step after the failure ran anyway")

    def test_which_step_failed_and_the_version_it_reached_are_both_named(self):
        """What an owner is handed when an update stops. Naming the step without the version
        leaves them guessing what state their data is in, which is the thing they care
        about; naming neither leaves them restoring a backup."""
        self.three_steps_the_middle_one_tripping()
        with self.assertRaises(migration.Failed) as stopped:
            migration.carry(self.at, self.home, 4, where=self.steps)
        self.assertEqual("003.py", stopped.exception.step)
        self.assertEqual(2, stopped.exception.reached)
        self.assertIsInstance(stopped.exception.why, RuntimeError)
        self.assertIn("003.py", str(stopped.exception))
        self.assertIn("still at version 2", str(stopped.exception))
        self.assertIn("the shape underneath was not what this step assumed",
                      str(stopped.exception))

    def test_running_again_after_the_step_is_fixed_resumes_at_it_and_does_not_redo_the_one_before(self):
        """The other half of the promise, and the reason a step needs no record of its own:
        the second run begins at the first step the version does not cover. The step that
        already ran would fail loudly if it were offered again, and the ledger says it was
        not offered."""
        self.three_steps_the_middle_one_tripping()
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, 4, where=self.steps)
        (self.home / "trip").unlink()
        said = []
        self.assertEqual(4, migration.carry(self.at, self.home, 4, where=self.steps,
                                            note=said.append))
        self.assertEqual(["002", "003", "004"], self.ran(),
                         "the update began again from the start rather than where it stopped")
        self.assertEqual(["migrating ops to version 3", "migrating ops to version 4"], said)
        self.assertEqual(4, self.stamped())


class WhatAStepKeepsAsFiles(WithStepsOfThisCasesOwn):
    """Moving a file is not part of any transaction, so a step copies and never renames."""

    def a_file_worth_keeping(self) -> Path:
        was = self.home / "kept" / "what-was-said.json"
        was.parent.mkdir()
        was.write_text('{"said": "what about the parser"}\n')
        self.wrote(2, COPYING)
        return was

    def test_what_a_step_copied_is_let_go_of_only_once_the_version_has_committed(self):
        """The step hands back what is now spare and the runner removes it afterwards, so
        what an owner had is never the thing at risk."""
        self.records()
        was = self.a_file_worth_keeping()
        now = self.home / "moved" / "what-was-said.json"
        self.assertEqual(2, migration.carry(self.at, self.home, 2, where=self.steps))
        self.assertTrue(now.exists(), "the copy the step made is not there")
        self.assertEqual('{"said": "what about the parser"}\n', now.read_text())
        self.assertFalse(was.exists(), "what the step handed back was never let go of")
        self.assertEqual(2, self.stamped())

    def test_a_step_that_fails_after_copying_leaves_both_copies_and_the_version_where_it_was(self):
        """The same step, dying after the copy. A rename here would have taken the owner's
        file into a version that never committed; a copy leaves both, and running again is
        safe because the original is still where the step expects to find it."""
        kept = self.records()
        was = self.a_file_worth_keeping()
        now = self.home / "moved" / "what-was-said.json"
        (self.home / "trip").write_text("the records will refuse this\n")
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, 2, where=self.steps)
        self.assertTrue(was.exists(), "what the owner had was removed by a step that failed")
        self.assertTrue(now.exists(), "the copy went too, so a retry has nothing to compare")
        self.assertEqual(store.VERSION, self.stamped())
        self.assertIsNone(kept.agent()["instructions"], "a failed step's work was committed")


class TheShapeAnAgentStartsWith(WithStepsOfThisCasesOwn):
    """The steps that really ship, which is the one place `where=` is left alone.

    Creating an agent runs them rather than building the tables directly, so this path is
    exercised every time anybody adds an agent — a step that has rotted is then found by the
    next person who makes one, not months later by an owner in the middle of an update.
    """

    def test_the_shape_this_rundesk_understands_is_the_last_step_that_ships(self):
        """One fact kept in two files. A step landing without the version moving means every
        fresh agent is born behind and refuses to open."""
        shipped = migration.found()
        self.assertTrue(shipped, "nothing ships to build an agent out of")
        self.assertEqual(sorted(step.version for step in shipped),
                         [step.version for step in shipped])
        self.assertEqual(store.VERSION, max(step.version for step in shipped),
                         "a step ships that the version this rundesk understands does not cover")

    def test_a_brand_new_agent_is_built_by_running_the_steps_that_ship(self):
        """Straight through the runner, with no store involved: an empty database, the steps
        that ship, and what comes out is one this rundesk opens, reads and writes."""
        born = self.where / "born"
        born.mkdir()
        at = store.path_for(born)
        self.assertEqual(store.VERSION, migration.carry(at, born, store.VERSION))
        arranged = sqlite3.connect(str(at), isolation_level=None)
        self.addCleanup(arranged.close)
        self.assertEqual(store.VERSION, arranged.execute("PRAGMA user_version").fetchone()[0])
        arranged.close()
        kept = store.Store(at)
        kept.made()
        kept.remember_channel("ops", "discord", ["u1"], AT)
        self.assertEqual(["ops"], [one["name"] for one in kept.channels()])

    def test_making_an_agent_leaves_records_that_are_complete_and_usable(self):
        """A shape that is only nearly there passes a version check and fails on the first
        thing an owner does, so the claim is a round trip and not a stamp."""
        kept = self.records()
        self.assertEqual(store.VERSION, kept.version())
        kept.remember_channel("ops", "discord", ["u1"], AT)
        kept.opened("c1", "ops", "thread", "99123", AT)
        kept.arrived("c1", AT, "what about the parser")
        run_id = kept.began(source="channel", provider="codex", brain="codex", posture="safe",
                            started_at=AT, conversation_id="c1")
        self.assertEqual(["ops"], [one["name"] for one in kept.channels()])
        self.assertEqual(["what about the parser"], [one["text"] for one in kept.messages("c1")])
        self.assertEqual([run_id], [one["id"] for one in kept.runs()])

    def test_opening_records_already_at_the_shape_installed_runs_no_step(self):
        """`made()` is what every entry point calls, so it runs far more often than once. A
        step running again would fail on its own `CREATE TABLE`, so records that still open
        and still hold what was put in them are the proof that none did."""
        kept = self.records()
        kept.remember_channel("ops", "discord", ["u1"], AT)
        kept.made()
        kept.made()
        self.assertEqual(store.VERSION, kept.version())
        self.assertEqual(["ops"], [one["name"] for one in kept.channels()])

    def test_records_behind_the_shape_installed_are_refused_on_open_and_never_moved_forward(self):
        """Moving forward happens deliberately, in the window an update already stands every
        gateway down for — never lazily, because something opened a database. Two gateways
        starting at once would otherwise both begin migrating the same records."""
        kept = self.records()
        kept.remember_channel("ops", "discord", ["u1"], AT)
        behind = store.VERSION
        self.addCleanup(setattr, store, "VERSION", store.VERSION)
        store.VERSION += 1
        with self.assertRaises(store.Behind) as refused:
            store.Store(self.at).made()
        self.assertEqual(behind, refused.exception.found)
        self.assertEqual(store.VERSION, refused.exception.understood)
        self.assertEqual(behind, self.stamped(), "opening a database migrated it")
        self.assertEqual(1, self.raw().execute("SELECT count(*) FROM channel").fetchone()[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
