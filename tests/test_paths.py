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

    def test_the_agents_stand_below_the_data_and_move_with_the_root(self):
        # Below `data/` and not below the root directly, because an agent's records are something
        # the owner accumulated: an update must not be able to reach them.
        self.assertEqual(paths.data() / "agents", paths.agents())
        moved = self.home / "moved"
        os.environ[paths.HOME_IS] = str(moved)
        self.assertEqual(moved / "data" / "agents", paths.agents())

    def test_no_variable_of_its_own_reaches_the_agents(self):
        # The defect this rebuild exists to fix, in its most expensive form: `RUNDESK_AGENTS_DIR`
        # beat the data directory's own variable, so a run that redirected four locations still made
        # three real agents in the owner's live install and reported success each time.
        os.environ["RUNDESK_AGENTS_DIR"] = str(Path.home() / ".rundesk" / "data" / "agents")
        self.addCleanup(os.environ.pop, "RUNDESK_AGENTS_DIR", None)
        self.assertEqual(self.home / "data" / "agents", paths.agents())

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


class WhichCopyOfTheCodeANewProcessImports(support.Isolated):
    """`paths.code`, and the arrangement nothing ever tested: a root with no install.

    Two things re-exec through this — the gateway's launchd shim and `update`'s handoff to the
    release that just landed — and both spelled `<home>/app/src` directly. That is right for an
    install and wrong for every checkout, which is the only way `./dev` is ever used. The gateway
    died with `ModuleNotFoundError: No module named 'rundesk'` on every spawn and launchd brought it
    back on the throttle for ever; `update` printed `UP TO DATE` and settled nothing, so an agent
    added before a release that ships a migration step stayed unsettled and its gateway refused to
    host it. Every live run installed first, and an install is the one arrangement where the wrong
    answer is also the right one.
    """

    def test_a_root_with_no_install_answers_the_running_program(self):
        self.assertFalse(paths.app().exists(), "this case is about a root that has no install")
        self.assertEqual(paths.program() / "src", paths.code())

    def test_and_what_it_answers_really_holds_rundesk(self):
        # The whole point: a path a subprocess can put on `sys.path` and then import from. The old
        # answer was a directory that had never been created, and nothing said so until launchd did.
        self.assertTrue((paths.code() / "rundesk" / "__init__.py").is_file())

    def test_an_install_answers_its_own_app_rather_than_the_running_program(self):
        # An installed job must go on working when the checkout it was built from is deleted, so
        # this must not drift to the running tree the moment both exist.
        (paths.app() / "src" / "rundesk").mkdir(parents=True)
        self.assertEqual(paths.app() / "src", paths.code())
        self.assertNotEqual(paths.program() / "src", paths.code())


class ARootThatMustNotBeUsed(support.Isolated):
    """A root that is too broad is one command away from taking somebody's home with it."""

    def _refused(self, said: str) -> str:
        os.environ[paths.HOME_IS] = said
        with self.assertRaises(paths.Refused) as refusal:
            paths.home()
        return str(refusal.exception)

    def test_a_root_that_reaches_the_home_directory_through_a_dotdot_is_refused(self):
        # `pathlib` never normalises `..` and never follows a symlink to decide `==`, so comparing
        # the path as typed compares a string that is not the directory anything will use. This got
        # through, and `uninstall --purge` removes `data/` below whatever root got through.
        self.assertIn("home directory", self._refused(str(Path.home() / "Library" / "..")))

    def test_a_root_that_reaches_the_home_directory_through_a_link_is_refused(self):
        pointing = self.home / "a-link-to-home"
        pointing.symlink_to(Path.home())
        self.assertIn("home directory", self._refused(str(pointing)))

    def test_a_root_that_reaches_the_filesystem_root_through_a_dotdot_is_refused(self):
        self.assertIn("root of the filesystem", self._refused("/tmp/../.."))

    def test_a_refusal_names_what_was_typed_and_what_it_turned_out_to_be(self):
        # Naming only what was typed reads as arbitrary; naming only what it resolved to reads as a
        # value nobody set. The person needs both to see why.
        said = self._refused(str(Path.home() / "Library" / ".."))
        self.assertIn("Library", said)
        self.assertIn(str(Path.home()), said)

    def test_a_relative_path_is_still_refused_rather_than_made_absolute(self):
        # Resolving makes a relative path absolute against whatever directory the command ran in, so
        # asking about it after resolving would quietly accept the exact thing this refuses.
        self.assertIn("absolute", self._refused("rundesk-somewhere"))

    def test_an_ordinary_root_is_handed_back_resolved(self):
        # What comes back is what everything below the root is derived from, so it is the canonical
        # form — otherwise a value that passed the check could still resolve elsewhere afterwards.
        through = self.home / "by-another-name"
        through.symlink_to(self.home)
        os.environ[paths.HOME_IS] = str(through / "root")
        self.assertEqual((self.home / "root").resolve(), paths.home())

    def test_a_root_that_is_set_and_empty_is_refused_rather_than_treated_as_unset(self):
        # The dangerous one. An empty value read as "nobody said" resolves to the owner's live
        # install at the exact moment something was trying to point the command elsewhere.
        self.assertIn("set and empty", self._refused(""))
        self.assertIn("set and empty", self._refused("   "))

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
