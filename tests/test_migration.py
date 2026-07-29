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

from rundesk import migration, store  # noqa: E402

AT = "2026-07-26T09:00:00Z"
LATER = "2026-07-26T10:00:00Z"

#: Where a step this suite writes for itself is numbered from — **above whatever ships**.
#: A case that builds its records through the real store gets them at the shape this rundesk
#: understands, so a step numbered at or below that has already run: the case then proves
#: nothing and says so by failing, a long way from the reason. Derived rather than written,
#: because it *was* written as `2` in twenty places and every one of them broke the day a
#: second step shipped.
MINE = store.VERSION + 1


def label(version: int) -> str:
    """What a step of this suite's own signs the ledger as — its file's own name."""
    return f"{version:03d}"

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
            migration.carry(self.at, self.home, MINE, where=self.steps)
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
                         migration.carry(self.at, self.home, MINE, where=self.steps))
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
        self.wrote(MINE, working("mark", label(MINE)))
        self.assertEqual(MINE, migration.carry(self.at, self.home, MINE, where=self.steps))
        self.assertEqual([label(MINE)], self.ran())
        self.assertIn("mark", self.columns())
        said = []
        self.assertEqual(MINE, migration.carry(self.at, self.home, MINE, where=self.steps,
                                               note=said.append))
        self.assertEqual([label(MINE)], self.ran(), "a step that had already run ran again")
        self.assertEqual([], said, "an update with nothing to do said it was doing something")
        self.assertEqual(MINE, self.stamped())

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
        ahead = MINE + 3
        self.raw().execute(f"PRAGMA user_version = {ahead}")
        self.wrote(MINE, working("mark", label(MINE)))
        with self.assertRaises(migration.Failed) as refused:
            migration.carry(self.at, self.home, MINE, where=self.steps)
        self.assertEqual(ahead, refused.exception.reached)
        self.assertIn(f"version {ahead}", str(refused.exception))
        self.assertIn(f"expects {MINE}", str(refused.exception))
        self.assertEqual(ahead, self.stamped())
        self.assertEqual([], self.ran(), "data nobody understood was migrated anyway")
        self.assertNotIn("mark", self.columns())

    def test_a_step_with_no_up_to_run_is_refused_by_name_rather_than_skipped(self):
        """A step whose work is spelled anything but `up` has not run, and skipping it would
        stamp the version saying it had — the one lie the version-as-record cannot survive."""
        self.records()
        self.wrote(MINE, "def down(conn, home):\n    return []\n")
        with self.assertRaises(migration.Failed) as refused:
            migration.carry(self.at, self.home, MINE, where=self.steps)
        self.assertIsInstance(refused.exception.why, AttributeError)
        self.assertIn(f"{label(MINE)}.py", str(refused.exception))
        self.assertIn("no `up`", str(refused.exception))
        self.assertEqual(store.VERSION, self.stamped())

    def test_one_readable_line_is_said_for_every_step_that_runs(self):
        """An update stands every agent down, so what it is doing to each of them is the
        only thing an owner has to watch. One line per step, naming the agent and the
        version its records are going to."""
        self.records()
        self.ledger()
        self.wrote(MINE, working("mark", label(MINE)))
        self.wrote(MINE + 1, working("named_model", label(MINE + 1)))
        said = []
        self.assertEqual(MINE + 1, migration.carry(self.at, self.home, MINE + 1,
                                                   where=self.steps, note=said.append))
        self.assertEqual([f"migrating ops to version {MINE}",
                          f"migrating ops to version {MINE + 1}"], said)

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
        self.wrote(MINE, working("mark", label(MINE)))
        self.wrote(MINE + 1, working("named_model", label(MINE + 1), TRIPS))
        self.wrote(MINE + 2, working("caused_by", label(MINE + 2)))
        (self.home / "trip").write_text("this step is not right yet\n")

    def test_a_step_that_fails_leaves_the_data_exactly_as_it_was(self):
        """Real DDL and real DML, and then it raises. SQLite keeps schema changes inside the
        transaction, so neither the column, nor the row, nor the line in the ledger survives
        — and an owner whose update went wrong has lost nothing at all."""
        self.records()
        self.ledger()
        self.wrote(MINE, f"""
            def up(conn, home):
                conn.execute("ALTER TABLE agent ADD COLUMN badge TEXT")
                conn.execute("UPDATE agent SET badge = 'kept' WHERE id = 1")
                conn.execute(
                    "INSERT INTO channel (name, kind, allow, created_at)"
                    " VALUES ('ops', 'discord', '[]', '2026-07-26T09:00:00Z')")
                conn.execute("INSERT INTO ran (step) VALUES ('{label(MINE)}')")
                raise RuntimeError("the shape underneath was not what this step assumed")
        """)
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, MINE, where=self.steps)
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
        self.wrote(MINE, """
            def up(conn, home):
                conn.execute("ALTER TABLE agent ADD COLUMN mark TEXT")
                conn.execute("UPDATE agent SET mark = 'carried' WHERE id = 1")
                if (home / "trip").exists():
                    raise RuntimeError("the shape underneath was not what this step assumed")
                return []
        """)
        (self.home / "trip").write_text("not yet\n")
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, MINE, where=self.steps)
        self.assertNotIn("mark", self.columns(),
                         "the work committed without the version that names it")
        self.assertEqual(store.VERSION, self.stamped())
        (self.home / "trip").unlink()
        self.assertEqual(MINE, migration.carry(self.at, self.home, MINE, where=self.steps))
        self.assertIn("mark", self.columns())
        self.assertEqual(MINE, self.stamped(),
                         "the work committed and the version did not follow")

    def test_a_step_that_finished_before_a_later_one_failed_stays_finished(self):
        """Each step is its own transaction, so an update stopped part-way is not one long
        thing rolled back — it is a version that moved as far as it honestly got."""
        self.three_steps_the_middle_one_tripping()
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, MINE + 2, where=self.steps)
        self.assertEqual(MINE, self.stamped(),
                         "the step that did finish was rolled back with the one that did not")
        self.assertEqual([label(MINE)], self.ran())
        self.assertIn("mark", self.columns())
        self.assertNotIn("named_model", self.columns(), "the step that failed left work behind")
        self.assertNotIn("caused_by", self.columns(), "a step after the failure ran anyway")

    def test_which_step_failed_and_the_version_it_reached_are_both_named(self):
        """What an owner is handed when an update stops. Naming the step without the version
        leaves them guessing what state their data is in, which is the thing they care
        about; naming neither leaves them restoring a backup."""
        self.three_steps_the_middle_one_tripping()
        with self.assertRaises(migration.Failed) as stopped:
            migration.carry(self.at, self.home, MINE + 2, where=self.steps)
        self.assertEqual(f"{label(MINE + 1)}.py", stopped.exception.step)
        self.assertEqual(MINE, stopped.exception.reached)
        self.assertIsInstance(stopped.exception.why, RuntimeError)
        self.assertIn(f"{label(MINE + 1)}.py", str(stopped.exception))
        self.assertIn(f"still at version {MINE}", str(stopped.exception))
        self.assertIn("the shape underneath was not what this step assumed",
                      str(stopped.exception))

    def test_running_again_after_the_step_is_fixed_resumes_at_it_and_does_not_redo_the_one_before(self):
        """The other half of the promise, and the reason a step needs no record of its own:
        the second run begins at the first step the version does not cover. The step that
        already ran would fail loudly if it were offered again, and the ledger says it was
        not offered."""
        self.three_steps_the_middle_one_tripping()
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, MINE + 2, where=self.steps)
        (self.home / "trip").unlink()
        said = []
        self.assertEqual(MINE + 2, migration.carry(self.at, self.home, MINE + 2,
                                                   where=self.steps, note=said.append))
        self.assertEqual([label(MINE), label(MINE + 1), label(MINE + 2)], self.ran(),
                         "the update began again from the start rather than where it stopped")
        self.assertEqual([f"migrating ops to version {MINE + 1}",
                          f"migrating ops to version {MINE + 2}"], said)
        self.assertEqual(MINE + 2, self.stamped())


class WhatAStepKeepsAsFiles(WithStepsOfThisCasesOwn):
    """Moving a file is not part of any transaction, so a step copies and never renames."""

    def a_file_worth_keeping(self) -> Path:
        was = self.home / "kept" / "what-was-said.json"
        was.parent.mkdir()
        was.write_text('{"said": "what about the parser"}\n')
        self.wrote(MINE, COPYING)
        return was

    def test_what_a_step_copied_is_let_go_of_only_once_the_version_has_committed(self):
        """The step hands back what is now spare and the runner removes it afterwards, so
        what an owner had is never the thing at risk."""
        self.records()
        was = self.a_file_worth_keeping()
        now = self.home / "moved" / "what-was-said.json"
        self.assertEqual(MINE, migration.carry(self.at, self.home, MINE, where=self.steps))
        self.assertTrue(now.exists(), "the copy the step made is not there")
        self.assertEqual('{"said": "what about the parser"}\n', now.read_text())
        self.assertFalse(was.exists(), "what the step handed back was never let go of")
        self.assertEqual(MINE, self.stamped())

    def test_a_step_that_fails_after_copying_leaves_both_copies_and_the_version_where_it_was(self):
        """The same step, dying after the copy. A rename here would have taken the owner's
        file into a version that never committed; a copy leaves both, and running again is
        safe because the original is still where the step expects to find it."""
        kept = self.records()
        was = self.a_file_worth_keeping()
        now = self.home / "moved" / "what-was-said.json"
        (self.home / "trip").write_text("the records will refuse this\n")
        with self.assertRaises(migration.Failed):
            migration.carry(self.at, self.home, MINE, where=self.steps)
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
        run_id = kept.began(source="channel", provider="codex", posture="safe",
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
        # Which shape is expected is asked for rather than frozen, so a case says it out loud
        # instead of reaching into a shared global and having to put it back.
        with self.assertRaises(store.Behind) as refused:
            store.Store(self.at, version=behind + 1).made()
        self.assertEqual(behind, refused.exception.found)
        self.assertEqual(behind + 1, refused.exception.understood)
        self.assertEqual(behind, self.stamped(), "opening a database migrated it")
        self.assertEqual(1, self.raw().execute("SELECT count(*) FROM channel").fetchone()[0])


class CarryingTheShapeThatShippedForward(WithStepsOfThisCasesOwn):
    """The steps that really ship, against records built at the version an owner is on.

    The other cases here write the steps they are about, which is what keeps them true as
    steps land. These are the opposite claim and need the opposite arrangement: what has to
    be proved is that the file somebody's records were *actually built by* carries them into
    the shape this rundesk expects, so the first step is copied out of `migrations/` and run
    on its own to build a database at version one.

    Never the owner's install. A copy of one step, a scratch directory, and a database this
    case made.
    """

    #: The version an owner running the release before this one is on, and the only shape
    #: there has ever been to carry forward from.
    FIRST = 1

    def setUp(self):
        super().setUp()
        # A directory holding the first step alone, so `carry` can stop at version one the
        # way an owner's records really did.
        self.only_the_first = self.where / "first"
        self.only_the_first.mkdir()
        shutil.copy2(migration.STEPS / "001.py", self.only_the_first / "001.py")

    def built_at_the_first_shape(self) -> None:
        """Records at version one, furnished the way an owner's are.

        A cron schedule that has fired, the channel it reports to, and a run the clock
        started — which is the link the rebuild below can silently destroy.
        """
        self.assertEqual(self.FIRST, migration.carry(self.at, self.home, want=self.FIRST,
                                                     where=self.only_the_first))
        conn = sqlite3.connect(str(self.at), isolation_level=None, timeout=5.0)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("INSERT INTO channel (name, kind, allow, created_at)"
                         " VALUES ('ops', 'discord', '[]', ?)", (AT,))
            conn.execute(
                "INSERT INTO schedule (name, cron, command, channel, place,"
                " last_auto_run_at, last_outcome, created_at)"
                " VALUES ('nightly', '0 3 * * *', ?, 'ops', '#ops', '2026-07-25 03:00',"
                " 'ok', ?)", ('["/usr/local/bin/tidy", "--quiet"]', AT))
            # Added and taken away, so the id counter stands above the highest id left —
            # which is the only arrangement in which losing it can be seen.
            conn.execute("INSERT INTO schedule (name, cron, prompt, created_at)"
                         " VALUES ('weekly', '0 9 * * 1', 'what is worth knowing?', ?)", (AT,))
            conn.execute("DELETE FROM schedule WHERE name = 'weekly'")
            conn.execute(
                "INSERT INTO run (id, schedule_id, source, provider, posture, started_at)"
                " VALUES ('run-1', 1, 'schedule', 'codex', 'autonomous', ?)", (AT,))
        finally:
            # Closed before anything migrates it: a connection left open holds the
            # write-ahead log's read lock on newer Pythons and not on the floor version,
            # so the leak would be invisible exactly where CI would catch it.
            conn.close()

    def carried(self):
        """Forward to the shape this rundesk understands, through the steps that ship."""
        self.assertEqual(store.VERSION,
                         migration.carry(self.at, self.home, want=store.VERSION))
        conn = self.raw()
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def test_a_schedule_written_at_the_shape_that_shipped_is_carried_forward_untouched(self):
        """Every schedule anybody has is a repeating one, and stays exactly one. A step that
        rebuilds the table it lives in has every opportunity to drop a column quietly — what
        it reports back is not the check, what is in the row afterwards is."""
        self.built_at_the_first_shape()
        one = self.carried().execute("SELECT * FROM schedule").fetchone()
        self.assertEqual(
            ("nightly", 1, "0 3 * * *", '["/usr/local/bin/tidy", "--quiet"]', None,
             "ops", "#ops", "2026-07-25 03:00", "ok", AT),
            (one["name"], one["enabled"], one["cron"], one["command"], one["prompt"],
             one["channel"], one["place"], one["last_auto_run_at"], one["last_outcome"],
             one["created_at"]))
        self.assertIsNone(one["at"], "a schedule that recurs was given a single moment")

    def test_rows_written_before_there_was_a_column_for_cache_writes_stay_unknown(self):
        """R-USE-13. A run recorded before `002` has its cache writes already added into
        `tokens_in`, and nothing kept the split — not the row and not the transcript — so
        it cannot be recovered afterwards. NULL is the only honest value, and is the one the
        rest of this schema already uses for it: a cost that never arrived is absent rather
        than zero, because unknown and nil are different facts (R-USE-6).

        Filling these with 0 would say the split *is* known and was none, which is the one
        thing it is not — and a total summing that would quietly claim to know more than it
        does."""
        self.built_at_the_first_shape()
        conn = self.raw()
        try:
            conn.execute("UPDATE run SET tokens_in = 5552, tokens_out = 5,"
                         " tokens_cached = 15273, tokens_reported = 1 WHERE id = 'run-1'")
        finally:
            conn.close()
        one = self.carried().execute(
            "SELECT tokens_in, tokens_written FROM run WHERE id = 'run-1'").fetchone()
        self.assertEqual(5552, one["tokens_in"], "a folded total was rewritten after the fact")
        self.assertIsNone(one["tokens_written"],
                          "an unrecoverable split was recorded as though it were known")

    def test_a_run_written_after_the_column_exists_records_its_cache_writes(self):
        """The guard on the one above: leaving old rows alone must not leave the column
        inert. What is written once the step has run is kept and read back."""
        self.built_at_the_first_shape()
        conn = self.carried()
        conn.execute("INSERT INTO run (id, source, provider, posture, started_at,"
                     " tokens_in, tokens_written) VALUES ('run-2', 'terminal', 'claude',"
                     " 'work', ?, 2, 5550)", (AT,))
        one = conn.execute(
            "SELECT tokens_in, tokens_written FROM run WHERE id = 'run-2'").fetchone()
        self.assertEqual((2, 5550), (one["tokens_in"], one["tokens_written"]))

    def test_rows_written_before_there_was_a_column_for_a_reason_stay_unknown(self):
        """R-RUN-19. A run recorded before `003` failed with prose and nothing else, and
        nothing infers a word from that prose afterwards: reading a reason out of a sentence
        is guessing, and a guessed word counted in a total is worse than an absent one
        because absent can be seen. The sentence itself is left exactly as it was."""
        self.built_at_the_first_shape()
        conn = self.raw()
        try:
            conn.execute("UPDATE run SET outcome = 'failed', why = ? WHERE id = 'run-1'",
                         ("Claude AI usage limit reached|1784920200",))
        finally:
            conn.close()
        one = self.carried().execute(
            "SELECT why, because FROM run WHERE id = 'run-1'").fetchone()
        self.assertEqual("Claude AI usage limit reached|1784920200", one["why"])
        self.assertIsNone(one["because"], "a word was inferred from prose after the fact")

    def test_a_run_still_names_the_schedule_that_started_it_after_the_shape_changes(self):
        """The loss this step exists not to cause. With foreign keys on — which is how the
        runner opens every step — dropping the table a run references performs an implicit
        delete that fires `ON DELETE SET NULL`, so a rebuild that looks perfect leaves every
        run saying the clock started it and no longer saying which schedule."""
        self.built_at_the_first_shape()
        conn = self.carried()
        started_by = conn.execute("SELECT schedule_id FROM run WHERE id = 'run-1'").fetchone()
        self.assertEqual(1, started_by["schedule_id"],
                         "the run stopped saying which schedule started it")
        self.assertEqual(1, conn.execute(
            "SELECT id FROM schedule WHERE name = 'nightly'").fetchone()["id"])
        self.assertEqual([], conn.execute("PRAGMA foreign_key_check").fetchall())

    def test_records_carried_forward_refuse_a_schedule_stating_a_time_and_a_moment_both(self):
        """The rebuilt table has to enforce what the new shape says, not merely hold the
        column: a CHECK that did not survive the rebuild is a rule nothing keeps, and the
        first thing to notice would be two schedules disagreeing about when they run."""
        self.built_at_the_first_shape()
        conn = self.carried()
        for cron, at in (("0 3 * * *", "2026-07-28 09:00"), (None, None)):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO schedule (name, cron, at, command, created_at)"
                             " VALUES ('both-or-neither', ?, ?, '[]', ?)", (cron, at, AT))

    def test_a_schedule_added_after_the_shape_changes_never_takes_an_id_already_used(self):
        """Dropping a table takes its id counter with it. Left to restart from the highest
        id copied across, the next schedule added would take one a removed schedule already
        held — and a run still pointing at that id would read as this new schedule's."""
        self.built_at_the_first_shape()
        conn = self.carried()
        conn.execute("INSERT INTO schedule (name, at, command, created_at)"
                     " VALUES ('tidy-up', '2026-07-28 09:00', '[]', ?)", (AT,))
        self.assertEqual(3, conn.execute(
            "SELECT id FROM schedule WHERE name = 'tidy-up'").fetchone()["id"])


class EachAgentIsCarriedOnItsOwn(WithStepsOfThisCasesOwn):
    """One database per agent means one migration per agent, and no agent waits on another.

    An update walks every agent in turn. Two of them are never at the same version — one was
    made last week and one this morning — so each must be brought forward from wherever it
    actually is, and one that cannot be moved must not take a healthy one with it.
    """

    SIGNS = """
        def up(conn, home):
            conn.execute("INSERT INTO ran (step) VALUES ('%s')")
            return []
        """

    def another(self, called: str):
        """A second agent, with records of its own beside the first."""
        home = self.where / called
        home.mkdir()
        at = store.path_for(home)
        store.Store(at).made()
        conn = sqlite3.connect(str(at), isolation_level=None, timeout=5.0)
        self.addCleanup(conn.close)
        conn.execute("CREATE TABLE ran (n INTEGER PRIMARY KEY AUTOINCREMENT, step TEXT NOT NULL)")
        return home, at, conn

    def test_each_agent_is_brought_forward_from_wherever_it_actually_is(self):
        self.records()
        self.ledger()
        theirs_home, theirs_at, theirs = self.another("plans")
        self.wrote(MINE, self.SIGNS % "two")
        self.wrote(MINE + 1, self.SIGNS % "three")

        # one of them is already part way, as an agent made after a release would be
        self.raw().execute(f"PRAGMA user_version = {MINE}")

        self.assertEqual(MINE + 1,
                         migration.carry(self.at, self.home, MINE + 1, where=self.steps))
        self.assertEqual(MINE + 1,
                         migration.carry(theirs_at, theirs_home, MINE + 1, where=self.steps))

        self.assertEqual(["three"], self.ran(), "a step already taken was taken again")
        self.assertEqual(
            [("two",), ("three",)],
            list(theirs.execute("SELECT step FROM ran ORDER BY n")),
            "the second agent was not brought forward from its own version")

    def test_an_agent_that_cannot_be_moved_leaves_every_other_agent_as_it_was(self):
        self.records()
        self.ledger()
        theirs_home, theirs_at, theirs = self.another("plans")
        self.wrote(MINE, self.SIGNS % "two")
        self.wrote(MINE + 1, """
            def up(conn, home):
                conn.execute("INSERT INTO ran (step) VALUES ('three')")
                raise RuntimeError("this one cannot be moved")
            """)

        with self.assertRaises(migration.Failed) as stopped:
            migration.carry(theirs_at, theirs_home, MINE + 1, where=self.steps)
        self.assertEqual(MINE, stopped.exception.reached,
                         "it stopped somewhere other than where the last good step left it")

        # the one that failed kept what it had, and stopped where it stopped
        self.assertEqual([("two",)], list(theirs.execute("SELECT step FROM ran ORDER BY n")))
        self.assertEqual(
            MINE, sqlite3.connect(str(theirs_at)).execute("PRAGMA user_version").fetchone()[0])
        # and the other agent was never opened at all
        self.assertEqual(store.VERSION, self.stamped(),
                         "one agent's failure reached another agent's records")
        self.assertEqual([], self.ran())


class WalkingEveryAgent(WithStepsOfThisCasesOwn):
    """An update moves every agent, one at a time, and writes down what it did to each."""

    def agent(self, called: str, signs: str = "") -> tuple:
        home = self.where / called
        home.mkdir(exist_ok=True)
        at = store.path_for(home)
        store.Store(at).made()
        conn = sqlite3.connect(str(at), isolation_level=None, timeout=5.0)
        self.addCleanup(conn.close)
        conn.execute("CREATE TABLE ran (n INTEGER PRIMARY KEY AUTOINCREMENT, step TEXT NOT NULL)")
        return home, at, conn

    def said(self, home) -> str:
        at = Path(home) / migration.LOG
        return at.read_text() if at.exists() else ""

    def nothing_open(self, made: tuple) -> None:
        """Close the connection the fixture left open on this agent's records.

        An update stands every gateway down before any of this, so nothing anywhere is
        reading them — which is the only reason copying and restoring a database as a plain
        file is honest. A connection held open across a restore sees the file change under
        it and answers `disk I/O error`, so a case that kept one would be proving something
        no update ever does.
        """
        made[2].close()

    def _aside(self) -> Path:
        """Where an update keeps what it may have to put back — outside where agents are
        kept, because anything standing there is walked as though it were one."""
        at = Path(tempfile.mkdtemp(prefix="rundesk-rollback-"))
        self.addCleanup(shutil.rmtree, at, True)
        return at

    def _stumbles_on(self, called: str):
        """A step that works for every agent but one. Two agents are never at the same
        version, so a walk always stops with earlier ones already carried."""
        self.wrote(MINE, f"""
            def up(conn, home):
                conn.execute("INSERT INTO ran (step) VALUES ('two')")
                if home.name == {called!r}:
                    raise RuntimeError("no such column")
                return []
            """)

    def _version(self, called: str) -> int:
        at = store.path_for(self.where / called)
        return int(sqlite3.connect(str(at)).execute("PRAGMA user_version").fetchone()[0])

    def _rows(self, called: str) -> list:
        at = store.path_for(self.where / called)
        return list(sqlite3.connect(str(at)).execute("SELECT step FROM ran"))

    def test_an_agent_already_carried_is_put_back_when_a_later_one_cannot_be(self):
        """R-MIG-19 — a step forward exists and a step back does not, so the way back is a
        copy taken before anything ran. Without it the walk stops with `ava` at the new
        version, the update puts the release back underneath it, and `ava` is left holding
        records newer than the only code left to read them — refused on open (R-MIG-10),
        which is an agent that will not start for a release the owner never received."""
        for called in ("ava", "john", "plans"):
            self.nothing_open(self.agent(called))
        self._stumbles_on("john")

        why = migration.carry_every_or_put_back(self.where, MINE, self._aside(),
                                                where=self.steps)

        self.assertIsNotNone(why, "a walk that stopped reported success")
        self.assertIn("john", why, "it never said which agent")
        self.assertIn("no such column", why, "it never said why")
        self.assertEqual(store.VERSION, self._version("ava"),
                         "an agent carried before the failure kept it")
        self.assertEqual([], self._rows("ava"), "what a step wrote was left behind")
        self.assertEqual(store.VERSION, self._version("john"))
        self.assertEqual(store.VERSION, self._version("plans"))

    def test_a_copy_is_let_go_of_once_the_move_it_insured_is_proved(self):
        """R-MIG-20 — kept exactly as long as it is the only way back, and no longer."""
        self.nothing_open(self.agent("ava"))
        self.wrote(MINE, """
            def up(conn, home):
                conn.execute("INSERT INTO ran (step) VALUES ('two')")
                return []
            """)
        aside = self._aside()

        self.assertIsNone(migration.carry_every_or_put_back(self.where, MINE, aside,
                                                            where=self.steps))
        self.assertEqual(MINE, self._version("ava"), "the agent was not carried")
        self.assertEqual([], list(aside.iterdir()),
                         "a proved update kept a copy of what it replaced")

    def test_which_steps_would_run_is_answerable_without_running_any_of_them(self):
        """R-MIG-21 — the question an owner asks *before* an update. Two agents are never
        at the same version, so "what will this do" has as many answers as there are
        agents, and reading three logs afterwards is what this exists to replace."""
        self.nothing_open(self.agent("ava"))
        self.nothing_open(self.agent("john"))
        self.wrote(MINE, signs("two"))
        self.wrote(MINE + 1, signs("three"))
        # One of them further along than the other, which is the whole point: two agents are
        # never at the same version, so what would run has as many answers as there are.
        migration.carry(store.path_for(self.where / "john"), self.where / "john", MINE,
                        where=self.steps)

        standing = migration.what_would_run(self.where, MINE + 1, where=self.steps)
        self.assertEqual({"ava", "john"}, set(standing))
        self.assertEqual([f"{label(MINE)}.py", f"{label(MINE + 1)}.py"],
                         [repr(one) for one in standing["ava"]])
        self.assertEqual([f"{label(MINE + 1)}.py"], [repr(one) for one in standing["john"]])
        self.assertEqual(store.VERSION, self._version("ava"),
                         "asking what would happen moved something")

    def test_asking_what_would_run_never_makes_records_for_an_agent_that_has_none(self):
        """`carry` reaches its database through `sqlite3.connect`, which *makes* one where
        there is none — so asking by way of the thing that does it would leave records
        behind on exactly the agents a preview must not touch."""
        (self.where / "fresh" / "home").mkdir(parents=True)
        self.wrote(2, signs("two"))

        standing = migration.what_would_run(self.where, 2, where=self.steps)
        self.assertEqual(["002.py"], [repr(one) for one in standing["fresh"]])
        self.assertFalse(store.path_for(self.where / "fresh").exists(),
                         "a preview made the records it was asked about")

    def test_what_may_have_to_be_put_back_is_kept_where_the_agents_are(self):
        """R-MIG-19 — and the reason it is there rather than inside the program.

        Whatever redirects where agents live redirects this with it, so a suite that
        isolated the one has isolated the other. Pointed at the program instead, driving an
        update wrote a real copy of a fake agent's records into the developer's own
        checkout — the trap `MEMORY.md` records one level down, at the next level up.
        """
        self.nothing_open(self.agent("ava"))
        self._stumbles_on("ava")

        migration.carry_every_or_put_back(self.where, MINE, where=self.steps)
        self.assertTrue((self.where / migration.ROLLBACK / "ava").is_dir(),
                        "the copy went somewhere the agents directory does not cover")

    def test_what_may_have_to_be_put_back_is_never_walked_as_an_agent(self):
        self.nothing_open(self.agent("ava"))
        self.wrote(MINE, signs("two"))

        migration.carry_every_or_put_back(self.where, MINE, where=self.steps)
        self.assertEqual(MINE, self._version("ava"))
        self.assertFalse((self.where / migration.ROLLBACK / migration.ROLLBACK).exists(),
                         "the place copies are kept was carried forward as though it were one")

    def test_an_agent_with_no_records_yet_is_neither_copied_nor_in_the_way(self):
        """An agent from a release before there were records has none to put back, and
        making one is what carrying it does — so there is nothing here to insure."""
        (self.where / "fresh" / "home").mkdir(parents=True)
        self.nothing_open(self.agent("ava"))
        self._stumbles_on("ava")

        why = migration.carry_every_or_put_back(self.where, MINE, self._aside(),
                                                where=self.steps)
        self.assertIsNotNone(why)
        self.assertIn("ava", why)

    def test_every_agent_is_walked_and_each_reaches_its_own_version(self):
        for called in ("ava", "john", "plans"):
            self.agent(called)
        self.wrote(MINE, """
            def up(conn, home):
                conn.execute("INSERT INTO ran (step) VALUES ('two')")
                return []
            """)
        reached = migration.carry_every(self.where, MINE, where=self.steps)
        self.assertEqual({"ava": MINE, "john": MINE, "plans": MINE}, reached)
        for called in ("ava", "john", "plans"):
            self.assertEqual(
                [("two",)],
                list(sqlite3.connect(str(store.path_for(self.where / called)))
                     .execute("SELECT step FROM ran")))

    def test_an_agent_from_before_there_were_records_is_given_them(self):
        """R-MIG-1 — the agents that most need moving forward are exactly the ones with no
        records at all: a release before there were any wrote `agent.json` and a home and
        nothing else. Passed over, an update reports success having moved nothing, and every
        one of those agents is then unable to start."""
        was = self.where / "ava"
        (was / "home").mkdir(parents=True)
        (was / "agent.json").write_text('{"provider": "codex"}')
        self.wrote(MINE, NOTHING)

        self.assertEqual({"ava": MINE}, migration.carry_every(self.where, MINE, where=self.steps))
        self.assertTrue(store.path_for(was).is_file(), "it was walked past")
        self.assertEqual(MINE, self.stamped_at(was))

    def test_a_directory_that_is_not_an_agent_is_walked_past(self):
        self.agent("ava")
        (self.where / "not-an-agent").mkdir()
        (self.where / "a-file").write_text("nor this")
        self.wrote(MINE, "def up(conn, home):\n    return []\n")
        self.assertEqual({"ava": MINE}, migration.carry_every(self.where, MINE, where=self.steps))

    def test_the_first_agent_that_cannot_be_moved_stops_the_walk(self):
        for called in ("ava", "john", "zeta"):
            self.agent(called)
        self.wrote(MINE, """
            def up(conn, home):
                if home.name == "john":
                    raise RuntimeError("this one cannot be moved")
                conn.execute("INSERT INTO ran (step) VALUES ('two')")
                return []
            """)
        with self.assertRaises(migration.Failed):
            migration.carry_every(self.where, MINE, where=self.steps)
        # what was carried before it stays carried; what came after is untouched
        self.assertEqual(MINE, self.stamped_at(self.where / "ava"))
        self.assertEqual(store.VERSION, self.stamped_at(self.where / "john"))
        self.assertEqual(store.VERSION, self.stamped_at(self.where / "zeta"),
                         "an agent after the failure was moved anyway")

    def stamped_at(self, home) -> int:
        conn = sqlite3.connect(str(store.path_for(home)))
        self.addCleanup(conn.close)
        return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def test_what_a_migration_did_is_left_in_the_agents_own_log(self):
        """Read afterwards, not watched. An update that failed overnight leaves the person who
        finds the agent down something to read — and this is the one moment where what happened
        to an agent's records is not yet in those records."""
        home, at, _ = self.agent("ava")
        self.wrote(MINE, "def up(conn, home):\n    return []\n")
        migration.carry_every(self.where, MINE, where=self.steps,
                              clock=lambda: "2026-07-26 03:00:00")
        wrote = self.said(home)
        self.assertIn(f"moving records from version {store.VERSION} to {MINE}", wrote)
        self.assertIn(f"{label(MINE)}.py finished — records are at version {MINE}", wrote)
        self.assertIn("2026-07-26 03:00:00", wrote)
        self.assertIn("INFO", wrote)

    def test_a_migration_that_failed_says_so_in_the_agents_own_log(self):
        home, at, _ = self.agent("ava")
        self.wrote(MINE, """
            def up(conn, home):
                raise RuntimeError("the machine went away")
            """)
        with self.assertRaises(migration.Failed):
            migration.carry_every(self.where, MINE, where=self.steps,
                                  clock=lambda: "2026-07-26 03:00:00")
        wrote = self.said(home)
        self.assertIn("ERROR", wrote)
        self.assertIn("did not finish", wrote)
        self.assertIn(f"still at version {store.VERSION}", wrote)
        self.assertIn("the machine went away", wrote)

    def test_a_log_that_cannot_be_written_does_not_stop_the_update(self):
        """Losing the note is bad. Refusing to move an owner's data because a note could not
        be written is worse, and the caller is told either way."""
        home, at, _ = self.agent("ava")
        self.wrote(MINE, "def up(conn, home):\n    return []\n")
        # A directory where the log file goes: appending to it raises, which is the shape of
        # a log that cannot be written without inventing a permission the suite cannot rely on.
        at = home / migration.LOG
        if at.exists():
            at.unlink()
        at.mkdir(parents=True)
        self.assertEqual({"ava": MINE}, migration.carry_every(self.where, MINE, where=self.steps))


class WhatAnUpdateMustNotCost(WithStepsOfThisCasesOwn):
    """R-MIG-17, R-MIG-18 — an update never costs an owner what their agents said, did or
    were told, and nothing moved forward is ever moved back."""

    def furnished(self) -> str:
        """One agent with everything an owner would miss: what it was told, what it said,
        what it ran, what it cost, what its schedules last did, and its own log."""
        kept = self.records()
        kept.remember_agent(provider="codex", instructions="be terse")
        kept.remember_channel("ops", "discord", ["u1"], AT, describes="a room")
        kept.remember_schedule("nightly", "0 3 * * *", AT, prompt="what changed?")
        kept.schedule_fired("nightly", LATER, "finished")
        kept.opened("c1", "ops", "thread", "99123", AT)
        asked = kept.arrived("c1", AT, "what about the parser", who="u1")
        named = kept.began("channel", "codex", "safe", AT, conversation_id="c1",
                           trigger_message_id=asked, settings={"effort": "high"})
        kept.recorded(named, 1, AT, "tool", event={"name": "grep"}, raw='{"type":"tool"}')
        kept.answered("c1", named, LATER, "the parser was rewritten")
        kept.ended(named, LATER, "failed", exit_code=1, why="401 Unauthorized",
                   tokens={"input": 10, "output": 5, "reported": True})
        migration.logged(self.home, "this agent was up", clock=lambda: "2026-07-25 09:00:00")
        return named

    def test_nothing_an_update_moves_loses_an_account_a_log_or_what_a_schedule_last_did(self):
        """R-MIG-17 — asked of a step that really changes the shape, because a step that
        changed nothing would prove only that nothing happened."""
        named = self.furnished()
        self.wrote(MINE, """
            def up(conn, home):
                conn.execute("ALTER TABLE run ADD COLUMN carried TEXT")
                return []
            """)
        self.assertEqual({"ops": MINE},
                         migration.carry_every(self.where, MINE, where=self.steps))
        self.assertIn("carried", self.columns("run"), "the step never really ran")

        kept = store.Store(self.at, version=MINE)
        self.assertEqual("codex", kept.agent()["provider"])
        self.assertEqual(["ops"], [one["name"] for one in kept.channels()])
        self.assertEqual(LATER, kept.schedule("nightly")["last_auto_run_at"])
        self.assertEqual([("user", "what about the parser"),
                          ("agent", "the parser was rewritten")],
                         [(one["author"], one["text"]) for one in kept.messages("c1")])
        one = kept.run(named)
        self.assertEqual(("failed", "401 Unauthorized", 10), (one["outcome"], one["why"],
                                                              one["tokens_in"]))
        self.assertEqual({"effort": "high"}, one["settings"])
        self.assertEqual([(1, "tool")], [(r["seq"], r["kind"]) for r in kept.records(named)])
        self.assertIn("this agent was up", (self.home / migration.LOG).read_text())

    def test_records_moved_forward_are_never_moved_back(self):
        """R-MIG-18 — going backwards is refusing to go forwards. A rundesk that has been
        downgraded is kept down and told which version it found, rather than reading a shape
        it cannot know what it is missing from."""
        self.furnished()
        self.wrote(MINE, "def up(conn, home):\n    return []\n")
        migration.carry_every(self.where, MINE, where=self.steps)

        with self.assertRaises(migration.Failed) as refused:
            migration.carry_every(self.where, MINE - 1, where=self.steps)
        self.assertIn("ops", str(refused.exception), "it never said which agent")
        self.assertEqual(MINE, self.stamped(), "an older rundesk moved the records back")

    def test_an_agent_already_at_the_shape_installed_is_not_moved_again(self):
        """R-MIG-4 — the same update run twice migrates once, which is what makes an update
        that stopped part-way safe to simply run again."""
        self.furnished()
        self.ledger()
        self.wrote(MINE, """
            def up(conn, home):
                conn.execute("INSERT INTO ran (step) VALUES ('two')")
                return []
            """)
        migration.carry_every(self.where, MINE, where=self.steps)
        migration.carry_every(self.where, MINE, where=self.steps)
        self.assertEqual(["two"], self.ran())


if __name__ == "__main__":
    unittest.main(verbosity=2)
