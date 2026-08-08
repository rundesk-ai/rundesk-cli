"""The directories an install keeps things in, and the note standing in each one.

Run directly: `python3 tests/test_home.py`
"""

import unittest

import support
from rundesk.core import paths
from rundesk.lifecycle import home


class TheDirectoriesAnInstallMakes(support.Isolated):

    def test_it_makes_every_one_of_them(self):
        home.prepare()
        for where in (paths.data(), paths.agents(), paths.backups(), paths.projects()):
            self.assertTrue(where.is_dir(), f"{where} was not made")

    def test_every_one_of_them_stands_below_the_root(self):
        # Below it, not directly below it: `agents` belongs under `data/`, because what protects
        # `data/` from an update is what has to protect an agent's records.
        for where in home.directories().values():
            with self.subTest(directory=where.name):
                self.assertIn(self.home, where.parents)

    def test_agents_stands_below_data_so_an_update_cannot_reach_it(self):
        # The one guarantee an agent's whole memory rests on. Asserted against `directories()`
        # rather than against `paths`, because this is the map the installer actually lays down.
        self.assertEqual(paths.data(), home.directories()["agents"].parent)

    def test_skills_stand_below_data_so_an_update_cannot_reach_them(self):
        # A skill an owner wrote is work rundesk did not do, so it is protected by the same thing
        # that protects an agent's memory — and it follows for free that a copy of `data/` carries
        # the whole library.
        self.assertEqual(paths.data(), home.directories()["skills"].parent)
        self.assertEqual(paths.skills(), home.directories()["skills"])

    def test_the_program_directory_is_not_one_of_them(self):
        # `app/` is placed whole by the installer rather than made empty and filled, and it is the
        # one directory an update replaces.
        self.assertNotIn(paths.app(), home.directories().values())

    def test_a_failure_names_the_directory_somebody_has_to_fix(self):
        # `agents` stands inside `data`, so walking these by name reaches the child first — and a
        # file sitting where `data/` belongs was then reported against `data/agents`, a path nobody
        # made and nobody can fix. Parents first, so the failure names the thing that is wrong.
        (self.home / "data").write_text("a file where a directory belongs")

        with self.assertRaises(OSError) as refused:
            home.prepare()

        self.assertIn("data", str(refused.exception))
        self.assertNotIn("agents", str(refused.exception))

    def test_running_it_twice_changes_nothing_the_second_time(self):
        home.prepare()
        self.assertEqual([], home.prepare(), "a second run rewrote something")


class TheNoteInEachDirectory(support.Isolated):
    """An agent that walks into an empty directory learns nothing from it."""

    def test_every_directory_has_one(self):
        home.prepare()
        for name, where in home.directories().items():
            with self.subTest(directory=name):
                self.assertTrue((where / "README.md").is_file(), f"{name} has no note")

    def test_the_projects_note_tells_an_agent_it_may_put_repositories_there(self):
        home.prepare()
        said = (paths.projects() / "README.md").read_text()
        self.assertIn("repositor", said.lower())
        self.assertIn("shared", said.lower())

    def test_the_data_note_says_it_is_protected(self):
        home.prepare()
        said = (paths.data() / "README.md").read_text()
        self.assertIn("update never touches it", said)

    def test_the_agents_note_tells_an_agent_which_directory_is_its_own(self):
        home.prepare()
        said = (paths.agents() / "README.md").read_text()
        self.assertIn("the one named after you is yours", said)

    def test_the_skills_note_says_where_an_agents_own_skill_goes(self):
        # An agent that wants to write one has to be told which directory is not replaced by the
        # next catalog check, because every other directory here is.
        home.prepare()
        said = (paths.skills() / "README.md").read_text()
        self.assertIn("local/", said)
        self.assertIn("replaced the next time that catalog is checked", said)

    def test_the_backups_note_says_copies_survive_a_purge(self):
        home.prepare()
        said = (paths.backups() / "README.md").read_text()
        self.assertIn("purge", said)

    def test_each_note_says_rundesk_wrote_it(self):
        # So nobody puts their own notes in a file that is rewritten under them.
        home.prepare()
        for where in home.directories().values():
            with self.subTest(directory=where.name):
                self.assertIn("Written by rundesk", (where / "README.md").read_text())

    def test_a_note_is_brought_up_to_date_on_a_later_run(self):
        home.prepare()
        stale = paths.projects() / "README.md"
        stale.write_text("something an older release wrote")
        touched = home.prepare()
        self.assertIn(stale, touched)
        self.assertIn("repositor", stale.read_text().lower())

    def test_a_note_that_cannot_be_read_is_replaced_rather_than_left(self):
        home.prepare()
        note = paths.data() / "README.md"
        note.write_bytes(b"\xff\xfe not text at all")
        home.prepare()
        self.assertIn("Written by rundesk", note.read_text())


class WhatAnInstallLaysDown(support.Isolated):
    """Through the real command, so the notes are proved to reach a machine."""

    def test_installing_lays_down_every_directory_and_its_note(self):
        root = self.home / "install"
        import os
        os.environ[paths.HOME_IS] = str(root)
        source = support.a_real_tree(self.home / "source")
        code, _, err = support.run(
            ["install", "--source", str(source), "--bin-dir", str(self.home / "bin")])
        self.assertEqual(0, code, err)
        for where in (paths.data(), paths.agents(), paths.backups(), paths.projects()):
            self.assertTrue((where / "README.md").is_file(), f"{where} has no note")


if __name__ == "__main__":
    unittest.main()
