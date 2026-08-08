"""Install migrations: found rather than listed, run once each, and recorded as they land.

The steps under test are written here rather than taken from `lifecycle/steps/`, so this suite proves
the runner rather than whichever steps a release happens to ship — and goes on proving it when that
directory is empty.

Run directly: `python3 tests/test_migration.py`
"""

import ast
import unittest
from pathlib import Path
from typing import List, Set
from unittest import mock

import support
from rundesk.commands import update
from rundesk.core import config
from rundesk.lifecycle import migration

A_STEP = '''
from pathlib import Path

def carry(data):
    (Path(data) / "{name}").write_text("{name}")
'''

#: A step that reaches for the tool a file-moving step most wants. The rule it breaks is the one
#: with no runtime symptom until years later, on a machine nobody has in front of them.
A_STEP_THAT_REACHES_FOR_RUNDESK = '''
from rundesk.utils import files

def carry(data):
    files.discard(data / "gone")
'''

#: The same rule broken the other way round — `import` rather than `from`, which is the branch of
#: the walk a checker written against one of them only would miss.
A_STEP_THAT_REACHES_FOR_IT_AS_A_MODULE = '''
import rundesk.utils.files

def carry(data):
    rundesk.utils.files.discard(data / "gone")
'''


class Steps(support.Isolated):
    """A scratch step directory, so the suite is about the runner and not about any one release."""

    def setUp(self):
        super().setUp()
        self.steps = self.home / "steps"
        self.steps.mkdir(parents=True, exist_ok=True)
        self.data = self.home / "data"
        config.write_fresh(self.data)

    def given(self, name: str, body: str = "") -> None:
        (self.steps / f"{name}.py").write_text(body or A_STEP.format(name=name))

    def applied(self):
        return config.read(self.data).get("migration")


class StepsThatCannotBeOrdered(Steps):
    """Two steps numbered the same, which is how the append-only rule gets broken in practice."""

    def test_two_steps_with_one_number_are_refused(self):
        # How far an install has been carried is one id, so the order steps run in has to be the
        # same everywhere for ever. Two files numbered the same have no order but the one their
        # filenames happen to give: an install stamped with the first would run the second, and one
        # stamped with the second would skip the first, silently and for good.
        self.given("0001_alpha")
        self.given("0001_beta")
        with self.assertRaises(migration.Broken) as refused:
            migration.found(self.steps)
        self.assertIn("0001", str(refused.exception))

    def test_it_is_refused_where_it_is_still_only_a_broken_checkout(self):
        # Not after it has shipped and every install has already made a different arbitrary choice.
        self.given("0001_alpha")
        self.given("0001_beta")
        self.assertIsNotNone(migration.carry(self.data, self.steps))

    def test_status_still_answers_when_the_steps_cannot_be_ordered(self):
        # The one command that must answer whatever is wrong, and this is the kind of wrong
        # somebody runs it to find out about.
        self.given("0001_alpha")
        self.given("0001_beta")
        with mock.patch.object(migration, "STEPS", self.steps):
            code, out, _ = self.rundesk("status")
        self.assertEqual(0, code)
        self.assertIn("0001", out)

    def test_settling_a_fresh_install_says_it_rather_than_raising(self):
        # The fresh-install path stamps without running, which still has to *find* the steps — and
        # a broken checkout is most likely to be discovered on exactly that path. Uncaught, it left
        # `settle` as a raw traceback, through the subprocess an install settles in, folded into a
        # message somebody was meant to read.
        #
        # Driven against `settle` itself rather than through `install`: an install settles in its
        # own interpreter by design, so patching the steps in this one would never reach it.
        self.given("0001_alpha")
        self.given("0001_beta")
        # Genuinely fresh: the shared fixture writes a configuration, and `settle` decides which
        # path it is on by whether one exists. With it there this took the other branch entirely,
        # which is how the first version of this case passed against the bug it was written for.
        config.where(self.data).unlink()

        with mock.patch.object(migration, "STEPS", self.steps):
            code, _, _ = support.run_with(["status"])           # still answers when steps are broken
            self.assertEqual(0, code, "status stopped answering")
            code = update.settle()

        self.assertNotEqual(0, code)

    def test_settling_an_install_that_already_exists_says_it_too(self):
        self.given("0001_alpha")
        self.given("0001_beta")
        config.write_fresh(self.data)
        with mock.patch.object(migration, "STEPS", self.steps):
            self.assertNotEqual(0, update.settle())

    def test_a_gap_in_the_numbering_is_fine(self):
        # Only sameness is ambiguous. Steps are appended, and nothing says they must be contiguous.
        self.given("0001_first")
        self.given("0009_ninth")
        self.assertEqual(["0001_first", "0009_ninth"],
                         [step.id for step in migration.found(self.steps)])


class WhichStepsExist(Steps):

    def test_steps_are_found_rather_than_listed(self):
        self.given("0001_first")
        self.given("0002_second")
        self.assertEqual(["0001_first", "0002_second"],
                         [step.id for step in migration.found(self.steps)])

    def test_they_run_in_the_order_their_number_gives(self):
        self.given("0010_later")
        self.given("0002_earlier")
        self.assertEqual(["0002_earlier", "0010_later"],
                         [step.id for step in migration.found(self.steps)])

    def test_a_file_that_is_not_named_like_a_step_is_ignored(self):
        self.given("0001_first")
        (self.steps / "__init__.py").write_text("")
        (self.steps / "notes.md").write_text("")
        self.assertEqual(["0001_first"], [step.id for step in migration.found(self.steps)])

    def test_a_release_that_ships_no_steps_says_so_rather_than_failing(self):
        self.assertEqual([], migration.found(self.steps))
        self.assertIsNone(migration.newest(self.steps))


class CarryingAnInstallForward(Steps):

    def test_every_step_that_has_not_run_runs(self):
        self.given("0001_first")
        self.given("0002_second")
        self.assertIsNone(migration.carry(self.data, self.steps))
        self.assertTrue((self.data / "0001_first").exists())
        self.assertTrue((self.data / "0002_second").exists())

    def test_how_far_it_got_is_recorded(self):
        self.given("0001_first")
        self.given("0002_second")
        migration.carry(self.data, self.steps)
        self.assertEqual("0002_second", self.applied())

    def test_a_step_that_has_run_does_not_run_again(self):
        self.given("0001_first")
        migration.carry(self.data, self.steps)
        (self.data / "0001_first").unlink()
        self.assertIsNone(migration.carry(self.data, self.steps))
        self.assertFalse((self.data / "0001_first").exists(), "the step ran a second time")

    def test_only_the_steps_after_the_recorded_one_run(self):
        self.given("0001_first")
        migration.carry(self.data, self.steps)
        self.given("0002_second")
        migration.carry(self.data, self.steps)
        self.assertEqual("0002_second", self.applied())

    def test_carrying_an_install_that_is_already_forward_changes_nothing(self):
        self.given("0001_first")
        migration.carry(self.data, self.steps)
        self.assertIsNone(migration.carry(self.data, self.steps))
        self.assertEqual("0001_first", self.applied())


class WhenAStepFails(Steps):

    def test_it_says_which_step_and_stops(self):
        self.given("0001_first")
        self.given("0002_broken", support.A_STEP_THAT_FAILS)
        self.given("0003_third")
        gone_wrong = migration.carry(self.data, self.steps)
        self.assertIn("0002_broken", gone_wrong)
        self.assertFalse((self.data / "0003_third").exists(),
                         "a later step ran over a shape its predecessor never made")

    def test_the_steps_that_did_finish_stay_recorded(self):
        # Stamped one at a time, so whatever picks up next carries on rather than starting again
        # over changes already made.
        self.given("0001_first")
        self.given("0002_broken", support.A_STEP_THAT_FAILS)
        migration.carry(self.data, self.steps)
        self.assertEqual("0001_first", self.applied())

    def test_running_again_resumes_at_the_step_that_failed(self):
        self.given("0001_first")
        self.given("0002_broken", support.A_STEP_THAT_FAILS)
        migration.carry(self.data, self.steps)
        (self.steps / "0002_broken.py").write_text(A_STEP.format(name="0002_broken"))
        self.assertIsNone(migration.carry(self.data, self.steps))
        self.assertEqual("0002_broken", self.applied())

    def test_a_step_with_nothing_to_run_is_named_rather_than_skipped(self):
        self.given("0001_empty", "# this file has no carry()\n")
        self.assertIn("0001_empty", migration.carry(self.data, self.steps))


class GoingBackwards(Steps):

    def test_an_install_carried_by_a_newer_release_is_refused(self):
        # Running an older release's steps over a newer release's layout is how data gets damaged.
        self.given("0001_first")
        config.stated("migration", "0009_from_the_future", self.data)
        gone_wrong = migration.carry(self.data, self.steps)
        self.assertIn("0009_from_the_future", gone_wrong)
        self.assertIn("newer release", gone_wrong)

    def test_nothing_runs_when_it_is_refused(self):
        self.given("0001_first")
        config.stated("migration", "0009_from_the_future", self.data)
        migration.carry(self.data, self.steps)
        self.assertFalse((self.data / "0001_first").exists())

    def test_the_sentence_names_a_deleted_or_renamed_step_as_well(self):
        # From here the two look identical, and the second is much the likelier for a developer to
        # have just caused: a step that had already shipped was renamed or taken out of this
        # checkout, which the rules forbid and nothing prevents. Naming only the newer release sent
        # somebody looking for a rundesk that did not exist.
        self.given("0002_second")
        config.stated("migration", "0001_first", self.data)      # its file is no longer here
        gone_wrong = migration.carry(self.data, self.steps)
        self.assertIn("0001_first", gone_wrong)
        self.assertIn("deleted or renamed", gone_wrong)
        self.assertFalse((self.data / "0002_second").exists(), "a step ran anyway")

    def test_it_is_ahead_rather_than_broken(self):
        # `Broken` is a script that cannot be run at all — a checkout somebody has to fix. This is
        # the opposite kind of answer: every step here is fine and the install is the thing that is
        # further forward than this release goes. Both raised one type and only the sentence told
        # them apart, which is a distinction nothing but a reader could act on.
        self.given("0001_first")
        with self.assertRaises(migration.Ahead) as refused:
            migration.outstanding("0009_from_the_future", self.steps)
        self.assertIn("newer release", str(refused.exception))

    def test_a_checkout_that_cannot_be_ordered_is_broken_and_not_ahead(self):
        # The other side of the same pin. Without it, `Ahead` could be raised for everything and
        # every case above would still pass.
        self.given("0001_alpha")
        self.given("0001_beta")
        with self.assertRaises(migration.Broken) as refused:
            migration.found(self.steps)
        self.assertNotIsInstance(refused.exception, migration.Ahead)

    def test_being_ahead_is_still_a_broken_so_nothing_stops_catching_it(self):
        # Deliberate, and the one place this differs from `agents.migration.Ahead`. Everything that
        # already answers "this install cannot be carried" names `Broken` — `carry`, and
        # `commands.update` at both of the places it asks what is outstanding — and `settle` runs in
        # a subprocess whose stderr is folded whole into what a person reads, so an answer that
        # escaped those would arrive as a traceback. Narrowing the answer must not stop anybody
        # hearing it: whoever makes this a plain `Exception` names it at those callers first.
        self.assertTrue(issubclass(migration.Ahead, migration.Broken))

    def test_settling_an_install_a_newer_release_carried_says_it_rather_than_raising(self):
        # What the case above is protecting, driven end to end. `settle` asks what is outstanding
        # twice — once to decide whether to keep a copy first, and once to carry — and only the
        # second of those answers with a sentence. A named refusal that escaped the first would
        # come out of the subprocess an install settles in as a raw traceback, folded whole into a
        # message somebody was meant to read.
        self.given("0001_first")
        config.stated("migration", "0009_from_the_future", self.data)
        with mock.patch.object(migration, "STEPS", self.steps):
            self.assertNotEqual(0, update.settle())
        self.assertFalse((self.data / "0001_first").exists(), "a step ran anyway")


class WhenTheConfigurationCannotBeRead(Steps):
    """`carry` answers with a sentence or with `None`, and never by raising past both."""

    def test_it_says_so_rather_than_raising_past_its_own_contract(self):
        # The read was outside the `try`, so a `data/config.json` that is there and cannot be read
        # came out of `carry` as an exception — through `update.settle`, which is a subprocess, and
        # out as a traceback folded into a message somebody was meant to read. The agent level has
        # always read what has run inside its own `try`.
        self.given("0001_first")
        config.where(self.data).write_text("{ this is not json", encoding="utf-8")
        gone_wrong = migration.carry(self.data, self.steps)
        self.assertIsNotNone(gone_wrong)
        self.assertIn(str(config.where(self.data)), gone_wrong)
        self.assertFalse((self.data / "0001_first").exists(),
                         "a step ran against an install whose configuration could not be read")


class AFreshInstall(Steps):

    def test_it_is_stamped_without_running_anything(self):
        # The directories were made correctly a moment ago; the steps describe changes from releases
        # this install never had.
        self.given("0001_first")
        self.given("0002_second")
        migration.stamp_without_running(self.data, self.steps)
        self.assertEqual("0002_second", self.applied())
        self.assertFalse((self.data / "0001_first").exists())
        self.assertFalse((self.data / "0002_second").exists())

    def test_nothing_is_left_outstanding_afterwards(self):
        self.given("0001_first")
        migration.stamp_without_running(self.data, self.steps)
        self.assertEqual([], migration.outstanding(self.applied(), self.steps))

    def test_a_release_shipping_no_steps_stamps_nothing_and_still_works(self):
        migration.stamp_without_running(self.data, self.steps)
        self.assertIsNone(self.applied())
        self.assertIsNone(migration.carry(self.data, self.steps))


class NoStepReachesForRundesk(Steps):
    """Rule 1 in `steps/__init__.py`, checked rather than remembered.

    A step is loaded from a file years after it was written, by code that has moved on, so anything
    of this product's it reaches for is a name that has to still exist and still mean the same thing
    then. The failure has no symptom until that day and on a machine nobody has in front of them,
    which is exactly the kind of rule that has to be read off the source now. The agent level checks
    its own steps the same way; the walks are siblings and so are these cases.

    Read with `ast` rather than run: importing a step to look at it would run it.
    """

    def test_a_step_that_reaches_for_rundesk_is_named(self):
        self.given("0001_reaching", A_STEP_THAT_REACHES_FOR_RUNDESK)
        self.assertEqual(["0001_reaching"], _reaching_for_rundesk(migration.found(self.steps)))

    def test_a_step_that_reaches_for_it_as_a_module_is_named_too(self):
        # `import rundesk.utils.files` and `from rundesk.utils import files` are two different nodes,
        # and a walk that knows only one of them passes the step that used the other.
        self.given("0001_reaching", A_STEP_THAT_REACHES_FOR_IT_AS_A_MODULE)
        self.assertEqual(["0001_reaching"], _reaching_for_rundesk(migration.found(self.steps)))

    def test_a_step_that_keeps_to_the_standard_library_is_fine(self):
        # The rule is about this product, not about imports. A step carries what it needs itself,
        # and what it needs is the standard library.
        self.given("0001_first")
        self.assertEqual([], _reaching_for_rundesk(migration.found(self.steps)))

    def test_no_step_this_release_ships_reaches_for_rundesk(self):
        # Every step in `lifecycle/steps/`, and one written here beside them so the walk is never
        # empty: that directory holds none today, and a check that read nothing would pass without
        # having proved a thing. When the first real step lands it is read by this same case.
        self.given("0001_first")
        reading = migration.found() + migration.found(self.steps)
        self.assertTrue(reading, "this walk read no steps at all, so it checked nothing")
        self.assertEqual([], _reaching_for_rundesk(reading))


class WhatTheReleaseShips(support.Isolated):
    """The real `lifecycle/steps/` directory, whatever is in it."""

    def test_every_shipped_step_is_named_so_it_can_be_ordered(self):
        for step in migration.found():
            with self.subTest(step=step.id):
                self.assertRegex(step.id, r"^\d{4}_[a-z0-9_]+$")

    def test_no_two_shipped_steps_share_a_number(self):
        orders = [step.order for step in migration.found()]
        self.assertEqual(len(orders), len(set(orders)))


def _reaching_for_rundesk(steps: List[migration.Step]) -> List[str]:
    """The id of every step that imports something of this product's, in the order they run."""
    return [step.id for step in steps
            if "rundesk" in {name.split(".")[0] for name in _imports(step.at)}]


def _imports(module: Path) -> Set[str]:
    """Every name this file imports, read off the source rather than by running it."""
    found: Set[str] = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"), str(module))):
        if isinstance(node, ast.Import):
            found.update(one.name for one in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


if __name__ == "__main__":
    unittest.main()
