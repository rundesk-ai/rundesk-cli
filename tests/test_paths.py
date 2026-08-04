"""Where an install keeps everything: one root, and every place derived downward from it.

Run directly: `python3 tests/test_paths.py`
"""

import os
import unittest
from pathlib import Path

import support
from rundesk.core import paths


class OneRootDecidesEverything(support.Isolated):
    """Everything an install keeps is below the root, so redirecting the root redirects all of it."""

    def test_every_place_stands_below_the_one_root(self):
        for place in (paths.app(), paths.data(), paths.backups(), paths.projects()):
            self.assertEqual(self.home, place.parent, f"{place} is not below the root")

    def test_the_root_is_read_again_on_every_call(self):
        # A location bound once at import is how a suite comes to write into the real install: the
        # value is decided before the case that redirects it has run.
        first = paths.home()
        moved = self.home / "moved"
        os.environ[paths.HOME_IS] = str(moved)
        self.assertEqual(moved, paths.home())
        self.assertNotEqual(first, paths.home())

    def test_the_places_are_the_ones_the_owner_drew(self):
        self.assertEqual(self.home / "app", paths.app())
        self.assertEqual(self.home / "data", paths.data())
        self.assertEqual(self.home / "backups", paths.backups())
        self.assertEqual(self.home / "projects", paths.projects())

    def test_an_unset_root_falls_back_to_the_owners_install(self):
        # Named out loud because it is the dangerous default and every guard here exists for it.
        del os.environ[paths.HOME_IS]
        self.assertEqual(Path.home() / ".rundesk", paths.home())


class WhereTheProgramIs(support.Isolated):
    """A different question from where the data is, and answered differently."""

    def test_the_program_is_the_tree_holding_the_launcher(self):
        self.assertEqual(support.CHECKOUT, paths.program())
        self.assertTrue((paths.program() / "rundesk").is_file())

    def test_it_is_found_rather_than_counted_from_this_module(self):
        # Counting parent directories is right until a module moves one level deeper, and then it is
        # quietly wrong — `paths` moving into `core/` made a count report `src/` as the program and
        # nothing failed.
        self.assertNotEqual(paths.program().name, "src")
        self.assertTrue((paths.program() / "src" / "rundesk" / "__init__.py").is_file())

    def test_the_program_and_the_data_are_different_questions(self):
        # A checkout has the program in a source tree while the data belongs under the owner's home.
        self.assertNotIn(str(paths.program()), str(paths.data()))


class ARootThatMustNotBeUsed(support.Isolated):
    """A root that is too broad is one command away from taking somebody's home with it."""

    def _refused(self, said: str) -> str:
        os.environ[paths.HOME_IS] = said
        with self.assertRaises(paths.Refused) as refusal:
            paths.home()
        return str(refusal.exception)

    def test_a_root_that_is_set_and_empty_is_refused_rather_than_treated_as_unset(self):
        # The dangerous one. An empty value read as "nobody said" resolves to the owner's live
        # install at the exact moment something was trying to point the command elsewhere.
        self.assertIn("set and empty", self._refused(""))
        self.assertIn("set and empty", self._refused("   "))

    def test_a_relative_root_is_refused(self):
        self.assertIn("absolute", self._refused("rundesk-somewhere"))

    def test_the_filesystem_root_is_refused(self):
        self.assertIn("root of the filesystem", self._refused("/"))

    def test_the_home_directory_itself_is_refused(self):
        # The installer this replaces recorded that pointing an install here once emptied a home
        # directory, and then reported success.
        self.assertIn("home directory", self._refused(str(Path.home())))

    def test_a_refusal_names_the_variable_so_it_can_be_fixed(self):
        self.assertIn(paths.HOME_IS, self._refused("/"))


class WhatTheHarnessPromises(support.Isolated):
    """The isolation every other suite rests on, asserted rather than assumed."""

    def test_the_scratch_root_is_what_the_product_resolves(self):
        self.assertEqual(self.home, paths.home())

    def test_nothing_of_the_owners_survives_into_a_case(self):
        # An agent's shell carries the live install's variables, and a suite inherits them.
        leaked = [name for name in os.environ
                  if name.startswith("RUNDESK_") and name != paths.HOME_IS]
        self.assertEqual([], leaked)
        self.assertNotIn("XDG_CONFIG_HOME", os.environ)


if __name__ == "__main__":
    unittest.main()
