"""The program behind a provider: finding it, asking what it can do, and where its things stand.

Every adapter here is a shell script this suite writes. Nothing needs a brain, an account or a
network — what is being proved is resolution, bounding and refusal, and those are the same whatever
program is on the end.

Run directly: `python3 tests/test_providers_adapters.py`
"""

import os
import unittest
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.core import adapters as core_adapters
from rundesk.core import paths
from rundesk.providers import adapters

#: An adapter that answers the one question asked of it offline, and nothing else. Built by
#: replacement rather than `str.format`, because a shell body is full of braces of its own.
SAYS = """#!/bin/sh
if [ "$1" = "--capabilities" ]; then
  printf '%s\\n' 'SAID'
  exit 0
fi
exit 1
"""


def saying(said: str) -> str:
    """An adapter that answers `--capabilities` with exactly this."""
    return SAYS.replace("SAID", said)


#: One that does not recognise the flag at all. A complete answer, and not an error.
SAYS_NOTHING = """#!/bin/sh
echo "I do not know that flag" >&2
exit 2
"""

#: One that prints a warning before its answer. It has still answered.
CHATTY = """#!/bin/sh
echo "warning: something" >&2
echo "note: something else"
printf '%s\\n' '{"tools": true}'
"""


class Adapters(support.Isolated):
    def setUp(self):
        super().setUp()
        # **`paths.code()` answers with the checkout's own `src` until an install exists**, so a
        # case that did not make one would look for shipped adapters among the *real* ones — and
        # `known()` would answer with whatever this release happens to ship, which changes the day
        # one is added. Making `app/src` points it inside the scratch home instead, which is also
        # what stops a case writing a fixture into the repository somebody is working in.
        (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.shipped = paths.code() / adapters.SHIPPED_IN
        self.assertNotIn(support.CHECKOUT, self.shipped.parents,
                         "a case was about to write an adapter into the checkout")

    def ships(self, name: str, body: str = "", runnable: bool = True):
        """An adapter that comes with the release, written where a shipped one is looked for."""
        return self._an_adapter(self.shipped / name, body, runnable)

    def given(self, name: str, body: str = "", runnable: bool = True):
        """An adapter this install has been given, written where one is looked for."""
        return self._an_adapter(paths.data() / adapters.GIVEN_IN / name, body, runnable)

    def _an_adapter(self, at, body: str, runnable: bool):
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_text(body or saying('{"tools": true}'), encoding="utf-8")
        if runnable:
            at.chmod(0o755)
        return at


class FindingOne(Adapters):
    def test_one_this_install_was_given_is_found_by_name(self):
        at = self.given("mine")
        self.assertEqual(adapters.where("mine"), at)

    def test_a_name_nothing_stands_behind_says_where_it_looked(self):
        with self.assertRaises(adapters.NotRunnable) as refused:
            adapters.where("nothing-here")
        said = str(refused.exception)
        self.assertIn(str(paths.data() / adapters.GIVEN_IN), said)
        self.assertIn("looked in", said)

    def test_a_file_that_is_there_and_not_executable_is_not_a_program(self):
        """A caller told "not there" about a program that is there goes looking in the wrong place."""
        self.given("mine", runnable=False)
        with self.assertRaises(adapters.NotRunnable):
            adapters.where("mine")

    def test_a_path_is_used_as_one(self):
        at = self.home / "somewhere" / "brain"
        at.parent.mkdir(parents=True)
        at.write_text(saying("{}"), encoding="utf-8")
        at.chmod(0o755)
        self.assertEqual(adapters.where(str(at)), at)

    def test_a_relative_path_resolves_rather_than_losing_its_separator(self):
        """`Path("./brain")` normalises to `brain`, and a bare name is looked for on PATH — so the
        refusal would name a program standing right there. `./name` is what anybody tries first."""
        at = self.home / "brain"
        at.write_text(saying("{}"), encoding="utf-8")
        at.chmod(0o755)
        here = os.getcwd()
        os.chdir(str(self.home))
        self.addCleanup(os.chdir, here)
        self.assertEqual(adapters.where("./brain"), at.resolve())

    def test_a_path_that_is_not_a_program_says_so_about_that_path(self):
        with self.assertRaises(adapters.NotRunnable) as refused:
            adapters.where(str(self.home / "nowhere" / "brain"))
        self.assertIn("brain", str(refused.exception))

    def test_every_one_this_install_can_run_is_found_by_looking(self):
        self.ships("shipped-one")
        self.given("one")
        self.given("two")
        self.given("three", runnable=False)
        self.assertEqual(adapters.known(), ["one", "shipped-one", "two"])

    def test_a_bare_name_finds_the_one_that_ships_before_one_this_install_was_given(self):
        """A release's own adapter is the one somebody gets by typing its name, and an install
        cannot quietly shadow it."""
        shipped = self.ships("codex")
        self.given("codex")
        self.assertEqual(adapters.where("codex"), shipped)

    def test_a_directory_that_is_not_there_yet_is_not_a_failure(self):
        self.assertEqual(adapters.known(), [])


class WhatItSaysItCanDo(Adapters):
    def test_what_it_answered_comes_back(self):
        self.given("mine", saying('{"tools": true, "steer": true}'))
        self.assertEqual(adapters.capabilities("mine"), {"tools": True, "steer": True})

    def test_one_that_does_not_know_the_flag_can_do_nothing(self):
        """A complete and honest answer, and never an error: the smallest legitimate adapter is a
        shell script that answers a prompt."""
        self.given("mine", SAYS_NOTHING)
        self.assertEqual(adapters.capabilities("mine"), {})

    def test_one_that_printed_something_that_is_not_an_object_can_do_nothing(self):
        self.given("mine", saying("[1, 2, 3]"))
        self.assertEqual(adapters.capabilities("mine"), {})

    def test_a_warning_before_the_answer_does_not_lose_the_answer(self):
        self.given("mine", CHATTY)
        self.assertEqual(adapters.capabilities("mine"), {"tools": True})

    def test_anything_else_it_reported_is_kept_exactly_as_it_said_it(self):
        """A version an adapter reports is answering a question rundesk did not ask, and it is what
        somebody reads a month later to find out what changed."""
        self.given("mine", saying('{"tools": true, "version": "0.146.0"}'))
        got = adapters.capabilities("mine")
        self.assertEqual(got["version"], "0.146.0")

    def test_it_is_asked_with_a_built_environment_and_not_this_ones(self):
        told = self.home / "told.json"
        self.given("mine", "#!/bin/sh\n"
                           f"env > {told}\n"
                           "printf '%s\\n' '{}'\n")
        os.environ["SOMETHING_PRIVATE"] = "a secret"
        self.addCleanup(os.environ.pop, "SOMETHING_PRIVATE", None)
        adapters.capabilities("mine")
        self.assertNotIn("SOMETHING_PRIVATE", told.read_text(encoding="utf-8"))

    def test_a_program_that_will_not_finish_is_bounded(self):
        """The one place rundesk runs an unvetted program before a turn has been admitted."""
        self.given("mine", "#!/bin/sh\nsleep 30\n")
        held = adapters.CAPABILITIES_WITHIN
        adapters.CAPABILITIES_WITHIN = 0.5
        self.addCleanup(setattr, adapters, "CAPABILITIES_WITHIN", held)
        self.assertEqual(adapters.capabilities("mine"), {})


class WhereItsThingsStand(Adapters):
    def setUp(self):
        super().setUp()
        directory.made("ava", "mine")

    def test_a_provider_home_is_named_per_agent_and_per_brain(self):
        self.assertEqual(adapters.home("ava", "mine").name, "mine")
        self.assertTrue(str(adapters.home("ava", "mine")).startswith(str(directory.where("ava"))))

    def test_two_adapters_of_one_name_in_two_places_are_two_brains(self):
        """One private home between them would hand one's credentials to the other."""
        here = adapters.key("/opt/one/brain")
        there = adapters.key("/opt/two/brain")
        self.assertNotEqual(here, there)
        self.assertTrue(here.startswith("brain-"))

    def test_a_key_is_the_same_every_time_it_is_asked(self):
        self.assertEqual(adapters.key("/opt/one/brain"), adapters.key("/opt/one/brain"))

    def test_a_bare_name_keeps_its_own_name(self):
        self.assertEqual(adapters.key("mine"), "mine")

    def test_a_name_that_would_not_stand_as_a_directory_is_made_to(self):
        self.assertNotIn("/", adapters.key("what../ever"))

    def test_a_conversations_things_stand_together_under_its_own_id(self):
        for at in (adapters.lock_of("ava", 7), adapters.raw_of("ava", 7),
                   adapters.errors_of("ava", 7)):
            with self.subTest(at=at.name):
                self.assertEqual(at.parent, adapters.conversation_at("ava", 7))
        self.assertNotEqual(adapters.conversation_at("ava", 7),
                            adapters.conversation_at("ava", 8))


class AdmittingOneScopedSelection(Adapters):
    def setUp(self):
        super().setUp()
        self.ships("configured")
        self.ships("scoped")

    def test_provider_only_uses_that_providers_default_model(self):
        chosen = adapters.admitted_selection("scoped", None, "configured", "configured-model")
        self.assertEqual(("scoped", None, "scoped", None), chosen)

    def test_model_only_uses_the_targets_default_provider(self):
        chosen = adapters.admitted_selection(None, "one-model", "configured", "old-model")
        self.assertEqual((None, "one-model", "configured", "one-model"), chosen)

    def test_both_requested_values_are_kept_exactly(self):
        chosen = adapters.admitted_selection(
            "scoped", " one-model ", "configured", "configured-model")
        self.assertEqual(("scoped", " one-model ", "scoped", " one-model "), chosen)

    def test_a_relative_path_is_stored_as_the_resolved_program(self):
        at = self.home / "brain"
        at.write_text(saying("{}"), encoding="utf-8")
        at.chmod(0o755)
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(str(self.home))

        chosen = adapters.admitted_selection(
            "./brain", None, "configured", "configured-model")

        self.assertEqual("./brain", chosen.requested_provider_name)
        self.assertEqual(str(at.resolve()), chosen.provider_name)
        os.chdir(str(self.shipped))
        self.assertEqual(at.resolve(), adapters.where(chosen.provider_name))

    def test_no_override_captures_the_targets_current_defaults(self):
        chosen = adapters.admitted_selection(
            None, None, "configured", "configured-model")
        self.assertEqual((None, None, "configured", "configured-model"), chosen)

    def test_a_blank_model_is_refused(self):
        with self.assertRaisesRegex(adapters.NotRunnable, "cannot be blank"):
            adapters.admitted_selection(None, " ", "configured", None)


class TheSeamNamesNoVendor(support.Isolated):
    def test_nothing_here_knows_a_brand(self):
        where = support.CHECKOUT / "src" / "rundesk" / "providers"
        for module in sorted(where.glob("*.py")):
            said = module.read_text(encoding="utf-8").lower()
            for vendor in ("claude", "anthropic", "codex", "openai", "grok", "gemini"):
                with self.subTest(module=module.name, vendor=vendor):
                    self.assertNotIn(vendor, said)


class WhichInterpreterRunsOne(Adapters):
    """An adapter is an executable with a shebang of its own, so the interpreter is chosen by
    putting this install's own `bin` first on `PATH` — never by prepending `python3` to the argv,
    which would be nonsense for a shell adapter."""

    def test_an_installs_own_packages_go_in_front(self):
        theirs = paths.app() / ".venv" / "bin"
        theirs.mkdir(parents=True)
        self.assertEqual(str(theirs), core_adapters.environment()["PATH"].split(":")[0])

    def test_a_checkout_keeps_its_packages_beside_the_code_and_is_found_there_too(self):
        """**Two arrangements, and a checkout is one of them.** Looking only where an install keeps
        them read as the shipped Discord adapter reporting that `discord.py` "is not installed", on
        a machine where it plainly was — which is a channel nobody can connect and a sentence that
        sends the reader to fix the wrong thing.

        **The checkout is made here rather than read off the one this suite is running from.**
        Whether the tree somebody is working in happens to have a virtualenv beside the code is a
        fact about their machine: the case passed on the machine it was written on and went red on
        every CI runner at once, where a fresh clone has no `.venv` and never will.
        """
        checkout = self.home / "somebodys-checkout"
        beside = checkout / ".venv" / "bin"
        beside.mkdir(parents=True)
        with mock.patch.object(paths, "program", return_value=checkout):
            self.assertEqual(str(beside), core_adapters.environment()["PATH"].split(":")[0])

    def test_an_install_with_no_packages_at_all_is_not_a_failure(self):
        """A machine with no network has a working install and no packages, and an adapter that
        needs none is unaffected."""
        with mock.patch.object(paths, "program", return_value=self.home / "nowhere"):
            self.assertIsNone(core_adapters.where_the_packages_are())


if __name__ == "__main__":
    unittest.main()
