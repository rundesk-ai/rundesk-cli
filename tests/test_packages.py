"""The packages an install keeps for the programs it starts.

Nothing here reaches a network. What builds the environment is handed in, so a case that forgot to
would fail against the closed proxy `support` points everything at rather than quietly downloading
something — which is the rule every other collaborator in this product already keeps.

**The failure this exists to prevent has already happened once**: the pin was carried for a release
with nothing building from it, so a channel could be configured and could never start, and the
`ImportError` arrived later, somewhere else, in a process nobody was watching.

Run directly: `python3 tests/test_packages.py`
"""

import unittest
from typing import ClassVar, List

import support
from rundesk.lifecycle import packages
from rundesk.utils import programs

#: A `requirements.txt` that is mostly explanation, which is what this product's really is.
MOSTLY_COMMENTS = """# What rundesk needs beyond the standard library.
#
# discord.py is here ahead of the channel that will import it.
discord.py==2.7.1

slack_sdk==3.43.0
"""


class Recording:
    """A stand-in for running a program, which writes down what it was asked and answers as told."""

    def __init__(self, answers: List[programs.Ran]):
        self.answers = list(answers)
        self.asked: List[List[str]] = []

    def __call__(self, argv, waiting, where=None, env=None) -> programs.Ran:
        self.asked.append([str(one) for one in argv])
        return self.answers.pop(0) if self.answers else programs.Ran(0, "", "", None)


def worked() -> programs.Ran:
    return programs.Ran(0, "", "", None)


def refused(err="ERROR: Could not find a version that satisfies the requirement") -> programs.Ran:
    return programs.Ran(1, "", err, None)


class Packages(support.Isolated):

    def setUp(self):
        super().setUp()
        self.app = self.home / "app"
        self.app.mkdir(parents=True, exist_ok=True)

    def a_release_needing(self, said=MOSTLY_COMMENTS):
        (self.app / packages.WANTED_IN).write_text(said, encoding="utf-8")

    def an_environment(self):
        """A `.venv` that looks built, for the cases about what is there afterwards."""
        packages.interpreter(self.app).parent.mkdir(parents=True, exist_ok=True)
        packages.interpreter(self.app).write_text("#!/bin/sh\n", encoding="utf-8")


class WhatAReleaseSays(Packages):

    def test_comments_and_blank_lines_are_not_requirements(self):
        # Which is what makes "an empty file" a state somebody can actually reach: the file this
        # product ships is mostly explanation.
        self.a_release_needing()
        self.assertEqual(["discord.py==2.7.1", "slack_sdk==3.43.0"], packages.wanted(self.app))

    def test_a_file_holding_only_explanation_needs_nothing(self):
        self.a_release_needing("# nothing here yet\n#\n\n")
        self.assertEqual([], packages.wanted(self.app))

    def test_a_release_with_no_such_file_needs_nothing(self):
        self.assertEqual([], packages.wanted(self.app))


class BuildingIt(Packages):

    def test_a_release_that_needs_nothing_builds_nothing(self):
        # The state to return to if a dependency ever stops earning its place.
        self.a_release_needing("# nothing\n")
        running = Recording([])
        self.assertEqual("", packages.built(self.app, running))
        self.assertEqual([], running.asked, "something was run for a release that needs nothing")

    def test_the_environment_is_made_and_then_filled_from_the_file(self):
        self.a_release_needing()
        running = Recording([worked(), worked()])
        self.an_environment()
        self.assertEqual("", packages.built(self.app, running))
        self.assertIn("venv", running.asked[0])
        self.assertIn(str(packages.where(self.app)), running.asked[0])
        self.assertIn("install", running.asked[1])
        self.assertIn(str(self.app / packages.WANTED_IN), running.asked[1])

    def test_it_is_made_afresh_rather_than_added_to(self):
        # `pip install` into an environment a previous release left leaves that release's packages
        # standing beside this one's, so what is installed stops being what any release asked for.
        self.a_release_needing()
        running = Recording([worked(), worked()])
        self.an_environment()
        packages.built(self.app, running)
        self.assertIn("--clear", running.asked[0])

    def test_it_stands_inside_the_tree_an_update_replaces(self):
        # So the packages belong to the release that asked for them, and a new tree gets a new
        # environment rather than inheriting the last one's.
        self.assertEqual(self.app, packages.where(self.app).parent)

    def test_an_environment_that_could_not_be_made_is_said_rather_than_passed_over(self):
        self.a_release_needing()
        gone_wrong = packages.built(self.app, Recording([refused("No module named venv")]))
        self.assertIn("could not be made", gone_wrong)
        self.assertIn("No module named venv", gone_wrong)

    def test_packages_that_could_not_be_fetched_are_said_with_what_pip_managed_to_say(self):
        self.a_release_needing()
        self.an_environment()
        gone_wrong = packages.built(self.app, Recording([worked(), refused()]))
        self.assertIn("could not be fetched", gone_wrong)
        self.assertIn("Could not find a version", gone_wrong)

    def test_a_program_that_never_ran_is_told_apart_from_one_that_disagreed(self):
        self.a_release_needing()
        never = programs.Ran(None, "", "", "did not start: no such file")
        self.assertIn("did not start", packages.built(self.app, Recording([never])))

    def test_a_build_that_answered_zero_and_left_nothing_is_not_a_success(self):
        # The exact shape of a success nobody earned: pip says 0 and there is no interpreter.
        self.a_release_needing()
        gone_wrong = packages.built(self.app, Recording([worked(), worked()]))
        self.assertIn("holds no interpreter", gone_wrong)


class WhetherAChannelCanStart(Packages):

    def test_a_release_needing_nothing_is_always_ready(self):
        self.assertTrue(packages.ready(self.app))

    def test_a_release_needing_packages_is_not_ready_without_an_environment(self):
        self.a_release_needing()
        self.assertFalse(packages.ready(self.app))

    def test_it_is_ready_once_the_environment_is_there(self):
        self.a_release_needing()
        self.an_environment()
        self.assertTrue(packages.ready(self.app))

    def test_it_is_asked_of_the_disk_every_time_rather_than_remembered(self):
        # A tree can be replaced and a volume unmounted since the install, so anything deciding
        # whether a channel can start has to ask now.
        self.a_release_needing()
        self.an_environment()
        self.assertTrue(packages.ready(self.app))
        packages.interpreter(self.app).unlink()
        self.assertFalse(packages.ready(self.app))


class WhatEveryPinIsFor(unittest.TestCase):
    """Every pin this repository ships is imported by an adapter this repository ships.

    **The failure this catches has already happened once**, and the file it guards says so in its own
    comments: a pin was carried for a release with nothing importing it, so every `install` and every
    `update` fetched and built a package for a channel that did not exist. A pin is a thing a user
    pays for on every install, so one with no reader is one to take out.

    It reads the repository's real `requirements.txt` and the real adapters, because a fixture
    agreeing with itself would prove neither.
    """

    #: Which module each distribution is imported as. A table rather than a rule, because the two
    #: names are unrelated — `discord.py` is imported as `discord` — and a rule guessing between them
    #: would be a rule that goes wrong the first time somebody adds a third.
    IMPORTED_AS: ClassVar[dict] = {"discord.py": "discord", "slack_sdk": "slack_sdk"}

    def pinned(self):
        return [one.split("==")[0]
                for one in packages.wanted(support.CHECKOUT) if one.strip()]

    def test_there_is_something_to_check(self):
        # A discovery check that discovered nothing has proved nothing, whatever it returns.
        self.assertTrue(self.pinned(), "requirements.txt named no distribution at all")

    def test_every_pin_is_named_here(self):
        # So that adding a pin without saying what imports it fails in this file rather than on
        # somebody's install six months later.
        self.assertEqual(sorted(self.IMPORTED_AS), sorted(self.pinned()))

    def test_every_pin_is_imported_by_an_adapter_that_ships(self):
        adapters = [one for one in (support.CHECKOUT / "src").rglob("*")
                    if one.is_file() and one.parent.name in ("channels", "providers")]
        self.assertTrue(adapters, "no shipped adapter was found to read")
        read = "\n".join(one.read_text(encoding="utf-8") for one in adapters)
        for named in self.pinned():
            with self.subTest(named=named):
                self.assertIn(f"import {self.IMPORTED_AS[named]}", read,
                              f"{named} is pinned and no shipped adapter imports it")

    def test_nothing_under_src_rundesk_imports_one(self):
        # The other half of the same rule, and the one the product's own brief promises: rundesk's
        # code is standard library only, and a pin lives on the far side of a pipe.
        core = "\n".join(one.read_text(encoding="utf-8")
                          for one in (support.CHECKOUT / "src" / "rundesk").rglob("*.py"))
        for named in self.pinned():
            with self.subTest(named=named):
                self.assertNotIn(f"import {self.IMPORTED_AS[named]}", core)


if __name__ == "__main__":
    unittest.main()
