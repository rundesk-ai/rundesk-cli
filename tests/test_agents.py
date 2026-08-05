"""What makes a directory an agent: naming one, finding them, making one, and taking one away.

The suite that stands where the old build lost data. Two of its cases are about failures that
really happened on a real machine — an agent named so that its own log collided with another
agent's records, and a make that was interrupted and left a directory that looked like an agent and
was not.

Run directly: `python3 tests/test_agents.py`
"""

import os
import shutil
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

import support
from rundesk.agents import directory, migration, records
from rundesk.core import paths
from rundesk.utils import files

#: A step that cannot finish, for proving an interrupted make leaves no agent behind. Its own copy
#: rather than `support.A_STEP_THAT_FAILS`, which is written to the *install* step contract and
#: takes one argument where an agent step takes two.
A_STEP_THAT_FAILS = """
def carry(conn, where):
    raise RuntimeError("this step could not finish")
"""

#: A step that writes down the name of the directory it was run in, which is the only way to see
#: from outside that an agent is built under a staged name and renamed into place at the end.
A_STEP_THAT_SAYS_WHERE_IT_IS = '''
from pathlib import Path

def carry(conn, where):
    (Path(where).parent / "seen").write_text(Path(where).name)
'''


class Agents(support.Isolated):
    """A scratch install with its agents directory laid down, as an install would leave it."""

    def setUp(self):
        super().setUp()
        self.agents = paths.agents()
        self.agents.mkdir(parents=True, exist_ok=True)

    def a_note(self) -> Path:
        """The note the install writes into `data/agents/`, which is not an agent."""
        note = self.agents / directory.NOTE
        note.write_text("# agents/\n", encoding="utf-8")
        return note


class WhatAnAgentMayBeCalled(Agents):
    """A name becomes a directory, so what a directory may not be, a name may not be."""

    def test_a_name_cannot_be_empty(self):
        self.assertIn("empty", directory.name_trouble(""))
        self.assertIn("empty", directory.name_trouble("   "))

    def test_a_name_cannot_be_a_directory_that_already_means_something(self):
        # `..` as a name would put the agent one level up, in `data/` itself.
        self.assertIn("directory", directory.name_trouble("."))
        self.assertIn("directory", directory.name_trouble(".."))

    def test_a_name_cannot_contain_a_separator(self):
        # The failure the old build recorded in one line: a name with a separator in it would put
        # the directory, the lock and the log somewhere else entirely.
        for said in ("one/two", "one\\two"):
            with self.subTest(said=said):
                self.assertIn("somewhere else", directory.name_trouble(said))

    def test_a_name_cannot_contain_a_null_byte(self):
        self.assertIn("null byte", directory.name_trouble("one\0two"))

    def test_a_name_cannot_start_with_a_dot(self):
        # Those are what a half-written thing and a lock wear, so `known` skips them — an agent
        # wearing one would be an agent no listing ever showed.
        self.assertIn("dot", directory.name_trouble(".hidden"))

    def test_a_name_cannot_contain_a_control_character(self):
        self.assertIn("control character", directory.name_trouble("one\ttwo"))

    def test_a_name_cannot_be_longer_than_a_filesystem_will_hold(self):
        self.assertIn("longer", directory.name_trouble("a" * 256))
        self.assertEqual("", directory.name_trouble("a" * 255))

    def test_the_note_the_install_writes_is_not_a_name_an_agent_may_have(self):
        # `data/agents/README.md` is rundesk's own note. An agent by that name would want the entry
        # the note already has, and the install rewrites that note on every update.
        self.assertIn("note", directory.name_trouble("README.md"))

    def test_the_note_is_refused_however_it_is_capitalised(self):
        # The volume a Mac ships with does not tell `readme.md` from `README.md`, so both are the
        # same collision on the machine this product is mostly run on.
        self.assertIn("note", directory.name_trouble("readme.md"))

    def test_an_ordinary_name_is_no_trouble_at_all(self):
        for said in ("cole", "nina-2", "an agent", "réponse", "foo.log"):
            with self.subTest(said=said):
                self.assertEqual("", directory.name_trouble(said))

    def test_a_name_that_would_have_collided_in_the_old_build_is_fine_here(self):
        # `foo.log` and `foo` wanted one file between them when the lock and the log stood *beside*
        # the name. Inside the agent's own directory there is nothing to collide with.
        directory.made("foo", "anthropic")
        directory.made("foo.log", "anthropic")
        self.assertEqual(["foo", "foo.log"], directory.known())
        self.assertNotEqual(directory.gateway_lock("foo"), directory.gateway_lock("foo.log"))


class WhereOneAgentsThingsStand(Agents):

    def test_everything_it_has_is_inside_its_own_directory(self):
        # The whole of the design: no sidecar stands beside the name, so no two names can want one
        # file between them.
        at = directory.where("cole")
        for one in (directory.records("cole"), directory.home("cole"), directory.logs("cole"),
                    directory.gateway_lock("cole"), directory.gateway_record("cole")):
            with self.subTest(one=one.name):
                self.assertEqual(at, one.parent)

    def test_it_is_resolved_on_every_call_and_never_at_import(self):
        # A location bound once, when the module was first imported, is how a suite comes to write
        # into the owner's live install: the root is set long after the value was decided.
        first = directory.where("cole")
        elsewhere = self.home / "somewhere-else"
        self.addCleanup(os.environ.__setitem__, paths.HOME_IS, os.environ[paths.HOME_IS])
        os.environ[paths.HOME_IS] = str(elsewhere)
        self.assertNotEqual(first, directory.where("cole"))
        self.assertEqual(elsewhere / "data" / "agents" / "cole", directory.where("cole"))


class WhichAgentsThereAre(Agents):
    """`known` answers off the disk, and an agent is a directory holding its records."""

    def test_an_install_with_no_agents_says_so_rather_than_failing(self):
        self.assertEqual([], directory.known())

    def test_an_install_whose_agents_directory_is_not_there_yet_says_so_too(self):
        # Before the first install has laid it down. Ordinary, and not a failure.
        self.agents.rmdir()
        self.assertEqual([], directory.known())

    def test_they_come_back_sorted_by_name(self):
        for name in ("zulu", "alpha", "mike"):
            directory.made(name, "anthropic")
        self.assertEqual(["alpha", "mike", "zulu"], directory.known())

    def test_a_stray_file_is_not_an_agent(self):
        directory.made("cole", "anthropic")
        (self.agents / "notes.txt").write_text("mine", encoding="utf-8")
        self.assertEqual(["cole"], directory.known())

    def test_the_note_the_install_writes_is_not_an_agent(self):
        self.a_note()
        self.assertEqual([], directory.known())

    def test_a_directory_with_no_records_is_not_an_agent(self):
        # Which is what a half-made one is. Counting it would offer somebody an agent that cannot
        # answer a single question about itself.
        (self.agents / "not-one").mkdir()
        (self.agents / "not-one" / "home").mkdir()
        self.assertEqual([], directory.known())

    def test_a_half_written_one_is_skipped_by_name_as_well(self):
        # Belt and braces: a staged name is skipped before its records are even looked at, so a
        # make interrupted after the database landed is still not offered as an agent.
        building = self.agents / files.INCOMING.format(name="cole")
        building.mkdir()
        (building / directory.RECORDS).write_text("", encoding="utf-8")
        self.assertEqual([], directory.known())


class WhetherANameMayBeUsedForANewAgent(Agents):

    def test_a_name_that_could_never_be_a_directory_is_refused_first(self):
        self.assertIn("empty", directory.taken(""))

    def test_an_agent_that_is_already_there_is_refused_by_name(self):
        directory.made("cole", "anthropic")
        self.assertIn("cole is already an agent", directory.taken("cole"))

    def test_a_name_differing_only_by_case_is_refused_and_names_the_one_that_exists(self):
        # macOS's default volume is case-insensitive, so `Cole` and `cole` are one directory.
        # Letting both be added gives two agents one `state.db`, each writing over the other's
        # memory, with nothing anywhere saying so.
        directory.made("cole", "anthropic")
        refused = directory.taken("Cole")
        self.assertIn("cole is already an agent", refused)
        self.assertIn("Cole", refused)
        self.assertIn(directory.RECORDS, refused)

    def test_the_name_the_owner_typed_is_never_changed_into_one_that_would_fit(self):
        # No slug, no fold, no rename on somebody's behalf: an agent whose name is not the name its
        # owner chose is a surprise that surfaces months later in something they have to type.
        directory.made("Cole", "anthropic")
        self.assertEqual(["Cole"], directory.known())

    def test_something_else_standing_under_that_name_is_refused_rather_than_written_over(self):
        (self.agents / "cole").mkdir()
        self.assertIn("is not an agent", directory.taken("cole"))

    def test_a_free_name_is_no_trouble(self):
        directory.made("cole", "anthropic")
        self.assertEqual("", directory.taken("nina"))


class MakingAnAgent(Agents):

    def setUp(self):
        super().setUp()
        self.at = directory.made("cole", "anthropic")

    def test_it_hands_back_where_the_agent_stands(self):
        self.assertEqual(self.agents / "cole", self.at)

    def test_everything_an_agent_has_is_there(self):
        self.assertTrue(directory.records("cole").is_file())
        self.assertTrue(directory.home("cole").is_dir())
        self.assertTrue(directory.logs("cole").is_dir())

    def test_its_home_has_a_note_saying_whose_it_is(self):
        # A bare empty folder tells an agent walking into it nothing, which is why the install
        # writes a note in every directory it makes. An agent's own home is no different.
        note = directory.home("cole") / directory.NOTE
        self.assertIn("cole", note.read_text(encoding="utf-8"))

    def test_the_configuration_row_holds_the_name_and_the_provider(self):
        settled = records.read(directory.records("cole"))
        self.assertEqual("cole", settled["agent_name"])
        self.assertEqual("anthropic", settled["agent_provider"])

    def test_the_first_step_is_recorded_as_having_run(self):
        # Recorded because it really ran: the schema is built by the migration runner and never by
        # DDL kept somewhere else, so there is one description of an agent's records.
        self.assertIn("0001_the_records_an_agent_keeps",
                      migration.recorded(directory.records("cole")))

    def test_every_step_this_release_ships_is_recorded(self):
        self.assertEqual([step.id for step in migration.found()],
                         sorted(migration.recorded(directory.records("cole"))))

    def test_the_records_are_kept_in_wal_mode(self):
        # A gateway reads an agent's records while a command writes to them, and that is the
        # ordinary case. Without WAL the two have to take turns.
        with records.reading(directory.records("cole")) as conn:
            self.assertEqual("wal", conn.execute("PRAGMA journal_mode").fetchone()[0])

    def test_it_is_listed_as_an_agent_afterwards(self):
        self.assertEqual(["cole"], directory.known())

    def test_all_of_it_is_built_under_a_staged_name_and_renamed_into_place_at_the_end(self):
        # Asked of a step, because that is the only vantage point from outside: a step is handed
        # the directory it is being run in, and while an agent is being made that directory must
        # not be wearing the agent's own name. A make that built in place and was interrupted
        # would leave a directory that looks like an agent and is not, which is the one thing
        # worse than leaving nothing.
        steps = self.home / "steps"
        steps.mkdir(parents=True, exist_ok=True)
        shutil.copy2(migration.STEPS / "0001_the_records_an_agent_keeps.py", steps)
        (steps / "0002_seen.py").write_text(A_STEP_THAT_SAYS_WHERE_IT_IS, encoding="utf-8")
        with mock.patch.object(migration, "STEPS", steps):
            directory.made("nina", "openai")
        said = (self.agents / "seen").read_text(encoding="utf-8")
        self.assertTrue(files.staged(said), f"an agent was built in place, under the name {said}")
        self.assertIn("nina", said)

    def test_nothing_staged_is_left_behind(self):
        self.assertEqual([], [one.name for one in self.agents.iterdir()
                              if files.staged(one.name)])

    def test_making_one_that_is_already_there_is_refused(self):
        with self.assertRaises(directory.Refused) as refused:
            directory.made("cole", "anthropic")
        self.assertIn("already an agent", str(refused.exception))

    def test_a_name_that_cannot_be_a_directory_is_refused(self):
        with self.assertRaises(directory.Refused):
            directory.made("one/two", "anthropic")

    def test_an_agent_with_nothing_behind_it_is_refused(self):
        # A provider is what answers. An agent without one is a directory that can never reply.
        with self.assertRaises(directory.Refused) as refused:
            directory.made("nina", "  ")
        self.assertIn("provider", str(refused.exception))
        self.assertEqual(["cole"], directory.known())


class AMakeThatIsInterrupted(Agents):
    """Half an agent is worse than none, because it is the one somebody reaches for."""

    def setUp(self):
        super().setUp()
        self.steps = self.home / "steps"
        self.steps.mkdir(parents=True, exist_ok=True)
        (self.steps / "0001_broken.py").write_text(A_STEP_THAT_FAILS, encoding="utf-8")

    def test_it_says_so_rather_than_reporting_an_agent_it_did_not_make(self):
        with mock.patch.object(migration, "STEPS", self.steps):
            with self.assertRaises(directory.Refused) as refused:
                directory.made("cole", "anthropic")
        self.assertIn("0001_broken", str(refused.exception))

    def test_no_directory_is_left_wearing_the_agents_own_name(self):
        with mock.patch.object(migration, "STEPS", self.steps):
            with self.assertRaises(directory.Refused):
                directory.made("cole", "anthropic")
        self.assertFalse(directory.where("cole").exists(),
                         "a make that failed left a directory under the agent's own name")

    def test_nothing_is_listed_as_an_agent(self):
        with mock.patch.object(migration, "STEPS", self.steps):
            with self.assertRaises(directory.Refused):
                directory.made("cole", "anthropic")
        self.assertEqual([], directory.known())

    def test_not_even_the_half_built_directory_is_left_behind(self):
        # Litter under a staged name is harmless and would be discarded by the next make anyway.
        # It is still tidied, because "the next one will clear it up" is a thing to have decided
        # rather than a thing that happens to be true today.
        with mock.patch.object(migration, "STEPS", self.steps):
            with self.assertRaises(directory.Refused):
                directory.made("cole", "anthropic")
        self.assertEqual([], list(self.agents.iterdir()))

    def test_the_name_can_be_used_again_straight_afterwards(self):
        # The staged directory is discarded, so somebody who fixes whatever went wrong is not left
        # having to tidy up by hand before they can try again.
        with mock.patch.object(migration, "STEPS", self.steps):
            with self.assertRaises(directory.Refused):
                directory.made("cole", "anthropic")
        self.assertEqual("", directory.taken("cole"))
        self.assertTrue(directory.made("cole", "anthropic").is_dir())


class TakingAnAgentAway(Agents):
    """Named one thing at a time, never a sweep and never a glob."""

    def setUp(self):
        super().setUp()
        self.note = self.a_note()
        directory.made("cole", "anthropic")
        directory.made("nina", "openai")
        directory.gateway_record("cole").write_text("{}", encoding="utf-8")
        directory.gateway_lock("cole").write_text("", encoding="utf-8")

    def test_it_names_everything_it_removed(self):
        gone = {one.name for one in directory.forgotten("cole")}
        named = {directory.RECORDS, directory.HOME, directory.LOGS,
                 directory.GATEWAY_RECORD, directory.GATEWAY_LOCK, "cole"}
        self.assertLessEqual(named, gone, f"these were not removed: {named - gone}")
        # Nothing beyond those, and beyond the two files SQLite keeps beside a database — whether
        # those are there at any given moment is SQLite's business and differs between versions,
        # which is exactly why `beside` names them rather than asserting they exist.
        beside = {directory.RECORDS + one for one in records.SIBLINGS}
        self.assertEqual(set(), gone - named - beside, "something not named was removed")

    def test_the_agent_is_gone(self):
        directory.forgotten("cole")
        self.assertFalse(directory.where("cole").exists())
        self.assertEqual(["nina"], directory.known())

    def test_the_write_ahead_log_goes_with_the_database(self):
        # Named rather than globbed. A stale `-wal` left beside a database is read by the next
        # connection as that database's most recent truth, which is how the old build recorded
        # losing one.
        for one in records.beside(directory.records("cole"))[1:]:
            one.write_bytes(b"")
        gone = [one.name for one in directory.forgotten("cole")]
        self.assertIn(directory.RECORDS + "-wal", gone)
        self.assertIn(directory.RECORDS + "-shm", gone)

    def test_the_agent_beside_it_is_untouched(self):
        # The failure this is written against is a removal that swept the directory it was
        # standing in rather than the one it was asked about.
        before = records.read(directory.records("nina"))
        directory.forgotten("cole")
        self.assertTrue(directory.records("nina").is_file())
        self.assertTrue(directory.home("nina").is_dir())
        self.assertEqual(before, records.read(directory.records("nina")))

    def test_the_note_the_install_keeps_is_untouched(self):
        directory.forgotten("cole")
        self.assertTrue(self.note.is_file())

    def test_something_the_owner_left_in_there_keeps_the_directory(self):
        # Taking an agent away is not a licence to sweep. What rundesk put there is named and
        # removed; what somebody else put there stays, and so does what is holding it.
        mine = directory.where("cole") / "notes.txt"
        mine.write_text("mine", encoding="utf-8")
        gone = directory.forgotten("cole")
        self.assertNotIn(directory.where("cole"), gone)
        self.assertTrue(mine.is_file())

    def test_a_home_that_is_a_link_is_unlinked_and_never_followed(self):
        # An agent's home replaced by a link to somebody's documents would otherwise have the
        # documents deleted rather than the link.
        theirs = self.home / "documents"
        theirs.mkdir()
        (theirs / "keep.txt").write_text("keep", encoding="utf-8")
        shutil.rmtree(directory.home("cole"))
        directory.home("cole").symlink_to(theirs)
        gone = directory.forgotten("cole")
        self.assertIn(directory.home("cole"), gone)
        self.assertTrue((theirs / "keep.txt").is_file(), "the link was followed and its target emptied")

    def test_an_agent_that_is_not_there_is_a_failure_and_not_a_quiet_success(self):
        # A removal that did not happen is never reported as one.
        with self.assertRaises(directory.Refused):
            directory.forgotten("nobody")

    def test_a_name_that_could_never_be_an_agent_is_refused_before_anything_is_touched(self):
        # `..` would resolve to `data/` itself, and everything below the agents directory would be
        # named one thing at a time out of it.
        with self.assertRaises(directory.Refused):
            directory.forgotten("..")
        self.assertEqual(["cole", "nina"], directory.known())


class WhatTheReleaseShips(Agents):
    """The real `agents/steps/` directory, whatever is in it."""

    def test_every_shipped_step_is_named_so_it_can_be_ordered(self):
        self.assertTrue(migration.found(), "this release ships no agent steps at all")
        for step in migration.found():
            with self.subTest(step=step.id):
                self.assertRegex(step.id, r"^\d{4}_[a-z0-9_]+$")

    def test_no_two_shipped_steps_share_a_number(self):
        orders = [step.order for step in migration.found()]
        self.assertEqual(len(orders), len(set(orders)))

    def test_the_first_step_lays_down_both_tables(self):
        directory.made("cole", "anthropic")
        with records.reading(directory.records("cole")) as conn:
            there = {row[0] for row in
                     conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertIn("config", there)
        self.assertIn("migrations", there)

    def test_the_configuration_is_held_to_one_row(self):
        # `CHECK (id = 1)` rather than everyone agreeing to write only one. A second row is not
        # extra information; it is two answers to a question that has one.
        directory.made("cole", "anthropic")
        with self.assertRaises(sqlite3.IntegrityError):
            with records.writing(directory.records("cole")) as conn:
                conn.execute("INSERT INTO config (id, agent_name, agent_provider) "
                             "VALUES (2, 'other', 'openai')")

    def test_a_column_that_says_text_holds_text_and_nothing_else(self):
        # What `STRICT` buys: without it a setting written as a number comes back as one, and the
        # conversion that grows to cope can never be removed.
        directory.made("cole", "anthropic")
        with self.assertRaises(sqlite3.IntegrityError):
            records.stated(directory.records("cole"), {"agent_model": b"not text"})


if __name__ == "__main__":
    unittest.main()
