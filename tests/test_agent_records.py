"""The database one agent keeps: four answers, a reader that cannot write, and a wait that ends.

Every case here is about a distinction that costs something when it is collapsed. "Not there" and
"there and cannot be read" are the pair that loses an agent's whole memory: a caller told the first
makes a new set of records over the top of the second.

Run directly: `python3 tests/test_agent_records.py`
"""

import contextlib
import os
import sqlite3
import threading
import time
import unittest
from typing import List

import support
from rundesk.agents import directory, records
from rundesk.core import paths


class OneAgentsRecords(support.Isolated):
    """A real agent, made the way the product makes one — the schema is the shipped step's."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("cole", "anthropic")
        self.at = directory.records("cole")


class WhichOfTheFourAnswersItIs(OneAgentsRecords):

    def test_records_that_are_there_are_read(self):
        self.assertEqual("cole", records.read(self.at)["agent_name"])

    def test_records_that_are_not_there_say_so(self):
        with self.assertRaises(records.NotThere):
            records.read(self.home / "nowhere" / "state.db")

    def test_reading_records_that_are_not_there_does_not_make_them(self):
        # A read that creates the file is a read that has answered its own question, and the next
        # thing to look will find an empty database where an agent's memory used to be.
        missing = self.home / "nowhere.db"
        with self.assertRaises(records.NotThere):
            records.read(missing)
        self.assertFalse(missing.exists())

    def test_records_that_cannot_be_understood_are_not_records_that_are_missing(self):
        # The pair that loses everything. Told "not there", a caller makes a new set over the top.
        self.at.write_text("this is prose, not a database", encoding="utf-8")
        with self.assertRaises(records.Unreadable):
            records.read(self.at)
        self.assertNotIsInstance(records.NotThere(""), records.Unreadable)

    def test_a_database_that_is_not_an_agents_says_so_rather_than_answering_empty(self):
        # A real SQLite file with none of an agent's tables in it. Answering with an empty mapping
        # would let a caller write its defaults over whatever survived.
        elsewhere = self.home / "someone-elses.db"
        sqlite3.connect(str(elsewhere)).close()
        with self.assertRaises(records.Unreadable):
            records.read(elsewhere)

    def test_records_with_no_configuration_row_are_unreadable_rather_than_blank(self):
        with records.writing(self.at) as conn:
            conn.execute("DELETE FROM config")
        with self.assertRaises(records.Unreadable):
            records.read(self.at)

    def test_writing_to_records_that_are_not_there_says_so_rather_than_making_them(self):
        with self.assertRaises(records.NotThere):
            with records.writing(self.home / "nowhere.db"):
                pass

    def test_records_may_be_made_only_when_the_caller_says_so(self):
        # `making` is the migration runner's, and only its: it is the one thing that builds a set
        # of records from nothing.
        at = directory.where("cole") / "second.db"
        with records.writing(at, making=True) as conn:
            conn.execute("CREATE TABLE thing (one TEXT) STRICT")
        self.assertTrue(at.is_file())

    def test_records_are_not_made_in_a_directory_that_is_not_there(self):
        # Otherwise carrying an agent nobody has ever made *makes* one — a whole directory and a
        # database, from a typo.
        with self.assertRaises(records.NotThere):
            with records.writing(self.home / "no-such-agent" / "state.db", making=True):
                pass
        self.assertFalse((self.home / "no-such-agent").exists())


class AReaderThatCannotWrite(OneAgentsRecords):
    """Read-only is asked for at open time, because it cannot be relied on afterwards."""

    def test_a_reader_is_refused_by_the_database_and_not_by_convention(self):
        with records.reading(self.at) as conn:
            with self.assertRaises(sqlite3.OperationalError) as refused:
                conn.execute("UPDATE config SET agent_name = 'someone else' WHERE id = 1")
        self.assertIn("readonly", str(refused.exception))
        self.assertEqual("cole", records.read(self.at)["agent_name"])

    def test_beginning_a_write_on_a_reader_succeeds_which_is_why_it_is_asked_for_at_open(self):
        # The trap the old build recorded: `BEGIN IMMEDIATE` *succeeds* on a read-only connection,
        # so "this one only reads" cannot be something a caller intends and relies on later. This
        # case exists to keep that fact visible — if it ever starts failing, the reasoning in
        # `records` has changed and its docstring is no longer true.
        with records.reading(self.at) as conn:
            conn.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("UPDATE config SET agent_name = 'someone else' WHERE id = 1")


class WhichJournalTheseRecordsAreKeptIn(OneAgentsRecords):
    """WAL where the filesystem can, and the rollback journal where it cannot."""

    def test_records_made_on_an_ordinary_disk_are_kept_in_wal(self):
        with records.reading(self.at) as conn:
            self.assertEqual("wal", conn.execute("PRAGMA journal_mode").fetchone()[0].lower())

    def test_a_later_open_reads_the_mode_rather_than_changing_it(self):
        # A home directory is not always a local disk: on iCloud Drive, Dropbox or an SMB share WAL
        # does not work at all, and records that ended up on the rollback journal have to go on
        # working. Nothing on a later open asserts the mode or changes it — the file belongs to
        # whoever else has it open, and a live downgrade is a change made behind their back.
        with contextlib.closing(sqlite3.connect(str(self.at))) as conn:
            conn.execute("PRAGMA journal_mode=DELETE")
        records.stated(self.at, {"agent_model": "a-model"})
        self.assertEqual("a-model", records.read(self.at)["agent_model"])
        with records.reading(self.at) as conn:
            self.assertEqual("delete", conn.execute("PRAGMA journal_mode").fetchone()[0].lower())

    def test_records_that_could_not_be_kept_in_wal_are_kept_in_the_default_journal(self):
        # The fallback, driven where it can be driven: a filesystem that refuses WAL is not
        # something a suite in `/tmp` can produce, so this asks the same question of the one thing
        # that is checkable — that what comes back is a journal mode SQLite really has, arrived at
        # by reading rather than by asserting.
        at = directory.where("cole") / "second.db"
        with records.writing(at, making=True) as conn:
            said = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
        self.assertIn(said, ("wal", "delete"))


class WhatStandsBesideTheDatabase(OneAgentsRecords):

    def test_it_names_the_database_and_the_two_files_sqlite_keeps_with_it(self):
        self.assertEqual([self.at, self.at.with_name(self.at.name + "-wal"),
                          self.at.with_name(self.at.name + "-shm")], records.beside(self.at))

    def test_it_never_asks_whether_they_are_there(self):
        # They exist only while a writer is live, so a version of this that checked would be
        # checking the weather — and removal and rollback would name whatever happened to be
        # there at that moment rather than everything that could be.
        for one in records.beside(self.at)[1:]:
            if one.exists():
                one.unlink()
        self.assertEqual(3, len(records.beside(self.at)))


class StatingWhatAnAgentIs(OneAgentsRecords):

    def test_one_value_is_set_and_every_other_left_as_it_was(self):
        records.stated(self.at, {"agent_model": "a-model"})
        settled = records.read(self.at)
        self.assertEqual("a-model", settled["agent_model"])
        self.assertEqual("cole", settled["agent_name"])

    def test_several_are_set_together(self):
        records.stated(self.at, {"agent_model": "a-model", "owner_name": "somebody"})
        settled = records.read(self.at)
        self.assertEqual("a-model", settled["agent_model"])
        self.assertEqual("somebody", settled["owner_name"])

    def test_naming_a_column_the_table_does_not_have_changes_none_of_them(self):
        # The same rule as `configure`: half of what was meant is not a smaller change, it is a
        # different one that nobody typed.
        with self.assertRaises(records.Refused) as refused:
            records.stated(self.at, {"agent_model": "a-model", "whatever_this_is": True})
        self.assertIn("whatever_this_is", str(refused.exception))
        self.assertIsNone(records.read(self.at)["agent_model"], "a refused change was half applied")

    def test_the_column_that_holds_the_table_to_one_row_is_not_something_anybody_states(self):
        with self.assertRaises(records.Refused):
            records.stated(self.at, {"id": 2})

    def test_stating_nothing_changes_nothing(self):
        records.stated(self.at, {})
        self.assertEqual("cole", records.read(self.at)["agent_name"])

    def test_the_one_row_is_written_by_the_call_that_first_states_it(self):
        # There is exactly one configuration, so its absence is not a different question from its
        # contents. This is the path `made` takes on a database a step built a moment ago.
        with records.writing(self.at) as conn:
            conn.execute("DELETE FROM config")
        records.stated(self.at, {"agent_name": "nina", "agent_provider": "openai"})
        self.assertEqual("nina", records.read(self.at)["agent_name"])

    def test_stating_over_records_that_cannot_be_read_is_refused(self):
        self.at.write_text("prose", encoding="utf-8")
        with self.assertRaises(records.Unreadable):
            records.stated(self.at, {"agent_model": "a-model"})


class WhenSomethingGoesWrongPartWayThrough(OneAgentsRecords):

    #: Where this Unix asks how many files this process has open. `/dev/fd` is the same directory
    #: on macOS and on Linux, and this product is already Unix-only — it locks with `fcntl`.
    HANDLES = "/dev/fd"

    def setUp(self):
        super().setUp()
        self.prose = directory.where("cole") / "prose.db"
        self.prose.write_text("this is not a database", encoding="utf-8")
        if not os.path.isdir(self.HANDLES):
            self.skipTest(f"{self.HANDLES} is not there, so open handles cannot be counted")

    def open_handles(self) -> int:
        return len(os.listdir(self.HANDLES))

    def test_a_write_that_raised_leaves_nothing_behind(self):
        # `BEGIN IMMEDIATE` at the start and a rollback on the way down, so a change that could not
        # be finished is a change that never happened.
        with self.assertRaises(RuntimeError):
            with records.writing(self.at) as conn:
                conn.execute("UPDATE config SET agent_name = 'someone else' WHERE id = 1")
                raise RuntimeError("something went wrong")
        self.assertEqual("cole", records.read(self.at)["agent_name"])

    def test_no_lock_is_still_held_after_a_write_that_failed(self):
        self.addCleanup(setattr, records, "BUSY_SECONDS", records.BUSY_SECONDS)
        with self.assertRaises(RuntimeError):
            with records.writing(self.at) as conn:
                conn.execute("UPDATE config SET agent_name = 'someone else' WHERE id = 1")
                raise RuntimeError("something went wrong")
        records.BUSY_SECONDS = 0
        records.stated(self.at, {"agent_model": "a-model"})       # refused if a lock were held
        self.assertEqual("a-model", records.read(self.at)["agent_model"])

    def test_every_connection_is_let_go_of_on_every_path(self):
        # Counted, not inferred. "The next write still works" proves nothing here: a connection
        # that was rolled back holds no lock and still holds a file handle, and a command that
        # walks fifty agents leaking one each is a command that runs out of them.
        #
        # Three paths, and the two that fail are the ones a version of this would forget.
        held = self.open_handles()
        for _ in range(15):
            records.read(self.at)
            with self.assertRaises(RuntimeError):
                with records.writing(self.at) as conn:
                    conn.execute("UPDATE config SET agent_name = 'x' WHERE id = 1")
                    raise RuntimeError("something went wrong")
            with self.assertRaises(records.Unreadable):
                records.read(self.prose)
        self.assertLess(self.open_handles(), held + 5, "connections were left open")

    def test_the_file_that_could_not_be_understood_is_let_go_of_too(self):
        held = self.open_handles()
        for _ in range(15):
            with self.assertRaises(records.Unreadable):
                records.stated(self.prose, {"agent_model": "a-model"})
        self.assertLess(self.open_handles(), held + 5, "connections were left open")


class TwoWritersAtOnce(OneAgentsRecords):
    """A gateway reading while a command writes is the ordinary case, not the rare one."""

    def test_a_writer_waits_for_the_one_in_front_of_it_rather_than_being_refused(self):
        held = threading.Event()

        def holding() -> None:
            with records.writing(self.at) as conn:
                conn.execute("UPDATE config SET owner_name = 'first' WHERE id = 1")
                held.set()
                time.sleep(0.2)

        first = threading.Thread(target=holding)
        first.start()
        self.addCleanup(first.join)
        held.wait(5)
        records.stated(self.at, {"agent_model": "second"})        # waits, then lands
        first.join()
        settled = records.read(self.at)
        self.assertEqual("first", settled["owner_name"])
        self.assertEqual("second", settled["agent_model"])

    def test_with_neither_a_timeout_nor_a_second_attempt_the_writer_is_refused_at_once(self):
        # Which is what the two of them are for. Without either, SQLite does not wait at all: the
        # second writer is refused instantly, and the sentence it is refused with says nothing
        # about a database that is perfectly healthy.
        self.addCleanup(setattr, records, "BUSY_SECONDS", records.BUSY_SECONDS)
        self.addCleanup(setattr, records, "TRIES", records.TRIES)
        records.BUSY_SECONDS, records.TRIES = 0, 1
        with records.writing(self.at):
            with self.assertRaises(sqlite3.OperationalError) as refused:
                records.stated(self.at, {"agent_model": "a-model"})
        self.assertIn("locked", str(refused.exception))

    def test_a_writer_asks_again_after_the_timeout_rather_than_giving_up(self):
        # The retry above the timeout, on its own. SQLite's own backoff is close enough to
        # deterministic that two writers which collide once go on colliding in step, so both run
        # out of timeout together and both report a database that is fine. Driven with the timeout
        # switched off entirely, so only the asking-again can land this write.
        for name in ("BUSY_SECONDS", "WAIT_LEAST", "WAIT_MOST"):
            self.addCleanup(setattr, records, name, getattr(records, name))
        records.BUSY_SECONDS, records.WAIT_LEAST, records.WAIT_MOST = 0, 0.1, 0.15
        held = threading.Event()

        def holding() -> None:
            with records.writing(self.at) as conn:
                conn.execute("UPDATE config SET owner_name = 'first' WHERE id = 1")
                held.set()
                time.sleep(0.25)

        first = threading.Thread(target=holding)
        first.start()
        self.addCleanup(first.join)
        held.wait(5)
        records.stated(self.at, {"agent_model": "second"})
        first.join()
        self.assertEqual("second", records.read(self.at)["agent_model"])

    def test_a_writer_waits_out_the_busy_timeout_even_with_no_second_attempt(self):
        # The timeout on its own, with the asking-again switched off. The two cover each other, so
        # each is driven with the other out of the way or neither is proved.
        self.addCleanup(setattr, records, "TRIES", records.TRIES)
        records.TRIES = 1
        held = threading.Event()

        def holding() -> None:
            with records.writing(self.at) as conn:
                conn.execute("UPDATE config SET owner_name = 'first' WHERE id = 1")
                held.set()
                time.sleep(0.2)

        first = threading.Thread(target=holding)
        first.start()
        self.addCleanup(first.join)
        held.wait(5)
        records.stated(self.at, {"agent_model": "second"})
        first.join()
        self.assertEqual("second", records.read(self.at)["agent_model"])

    def test_the_ceiling_is_the_one_this_module_names_and_not_the_bindings(self):
        # Python's binding waits five seconds unless it is told otherwise, and five seconds nobody
        # chose is a number nobody can change with confidence. Shortened here: the writer has to
        # give up on *this* module's ceiling rather than on the one that came with the binding.
        for name in ("BUSY_SECONDS", "TRIES"):
            self.addCleanup(setattr, records, name, getattr(records, name))
        records.BUSY_SECONDS, records.TRIES = 0.05, 1
        held, letting_go = threading.Event(), threading.Event()

        def holding() -> None:
            with records.writing(self.at):
                held.set()
                letting_go.wait(5)

        first = threading.Thread(target=holding)
        first.start()
        self.addCleanup(first.join)
        self.addCleanup(letting_go.set)
        held.wait(5)
        started = time.monotonic()
        with self.assertRaises(sqlite3.OperationalError):
            records.stated(self.at, {"agent_model": "a-model"})
        self.assertLess(time.monotonic() - started, 1.0, "it waited out the binding's own ceiling")

    def test_a_refusal_that_is_not_the_lock_is_raised_at_once(self):
        # Waiting does not fix a database nobody may write to, and asking five times would only
        # take five times as long to say the same thing.
        #
        # Driven against the taking of the lock directly, and that is not laziness: SQLite defers
        # the write lock to the first statement that actually writes, so through the ordinary
        # surface a permission failure surfaces at the `UPDATE` and never reaches this branch —
        # measured, on a database chmodded to `0400`, in both journal modes. A branch nothing can
        # reach is a branch nothing can prove, so it is proved where it lives.
        for name in ("WAIT_LEAST", "WAIT_MOST"):
            self.addCleanup(setattr, records, name, getattr(records, name))
        records.WAIT_LEAST = records.WAIT_MOST = 0.2

        class Refusing:
            """A connection that refuses for a reason waiting cannot fix, and counts the asking."""

            asked = 0

            def execute(self, statement):
                Refusing.asked += 1
                raise sqlite3.OperationalError("attempt to write a readonly database")

        started = time.monotonic()
        with self.assertRaises(sqlite3.OperationalError):
            records._begun(Refusing())
        self.assertEqual(1, Refusing.asked, "a refusal that is not the lock was asked about again")
        self.assertLess(time.monotonic() - started, records.WAIT_LEAST)

    def test_many_writers_leave_one_row_that_says_one_thing(self):
        trouble: List[BaseException] = []

        def writing(said: str) -> None:
            try:
                for _ in range(15):
                    records.stated(self.at, {"agent_model": said, "owner_name": said})
            except BaseException as why:                # noqa: BLE001 — carried to the assertion
                trouble.append(why)

        threads = [threading.Thread(target=writing, args=(one,)) for one in ("alpha", "zulu")]
        for one in threads:
            one.start()
        for one in threads:
            one.join()
        self.assertEqual([], [repr(one) for one in trouble])
        settled = records.read(self.at)
        # Whichever went last, both columns are that writer's: a half-applied write would leave
        # one column from each.
        self.assertEqual(settled["agent_model"], settled["owner_name"])


if __name__ == "__main__":
    unittest.main()
