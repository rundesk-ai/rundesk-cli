"""Copies of what the owner keeps: making one, listing them, putting one back, and moving them.

Every function in `lifecycle/backups.py` is driven here by name, and the command group on top of it
is driven the way somebody types it. The two are separated on purpose: the module is where the
guarantees live, and a guarantee proved only through a command is a guarantee that stops being proved
the day somebody adds a second caller.

The cases that matter most are the ones about **not** losing a copy — a save that fails partway, a
restore that cannot finish, a move that dies halfway to another disk. Each of those is driven by
making the operation fail on purpose, because the only interesting question about a backup system is
what it does on the day something goes wrong.

Run directly: `python3 tests/test_backups.py`
"""

import os
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import support
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import backups
from rundesk.utils import jsonfile

A_STEP = '''
from pathlib import Path

def carry(data):
    (Path(data) / "carried").write_text("{name}")
'''

#: A step that records that it ran **without erasing what ran before it**, so a case can tell "this
#: step ran" from "this step ran twice". A step that overwrites cannot: re-running it looks identical
#: to running it once, which is exactly the mistake these cases exist to catch.
AN_APPENDING_STEP = '''
from pathlib import Path

def carry(data):
    at = Path(data) / "carried"
    was = at.read_text() if at.exists() else ""
    at.write_text(was + "{name}\\n")
'''

#: A fixed moment, so a name is asserted exactly rather than matched against a shape. The product
#: takes its clock as an argument for exactly this reason.
A_MOMENT = datetime(2026, 8, 4, 3, 0, 0, tzinfo=timezone.utc)
ITS_NAME = "2026-08-04T03-00-00Z"


def unwritable(where: Path) -> None:
    """Take away permission to change a directory, without taking away permission to read it.

    Enough to make a removal fail while a listing still works, which is the difference several of
    these cases turn on.
    """
    where.chmod(0o500)


class Copies(support.Isolated):
    """A scratch install with data worth copying, and a `backups/` to copy it into."""

    def setUp(self):
        super().setUp()
        self.data = self.home / "data"
        self.at = self.home / "backups"
        self.at.mkdir(parents=True, exist_ok=True)
        self.given_data()

    def given_data(self, marker: str = "what the owner keeps", **settled) -> Path:
        """Data that looks like an install's: a `config.json`, and something of the owner's."""
        self.data.mkdir(parents=True, exist_ok=True)
        (self.data / "marker.txt").write_text(marker)
        held = dict(config.INITIAL)
        held.update(settled)
        jsonfile.write(self.data / "config.json", held)
        return self.data

    def given_copy(self, name: str, marker: str = "", **settled) -> Path:
        """One copy already made, carrying whatever configuration it was made under.

        `migration=` is the field these cases turn on: it is how far the install had been carried
        **when the copy was taken**, which is the whole reason putting an old one back is not
        finished when the files land.
        """
        where = self.at / name
        where.mkdir(parents=True, exist_ok=True)
        held = dict(config.INITIAL)
        held.update(settled)
        jsonfile.write(where / "config.json", held)
        (where / "marker.txt").write_text(marker or name)
        return where

    def given_copies(self, *names: str) -> None:
        """Copies already made, each a real one so it can be put back."""
        for name in names:
            self.given_copy(name)

    def entries(self):
        return sorted(one.name for one in self.at.iterdir())


class WhereTheCopiesAre(Copies):
    """`location` — where the bytes are, which is not always where rundesk looks."""

    def test_it_is_the_directory_itself_when_it_has_not_been_moved(self):
        self.assertEqual(self.at, backups.location(self.at))

    def test_it_is_what_the_link_points_at_once_they_have_been_moved(self):
        elsewhere = self.home / "elsewhere"
        elsewhere.mkdir()
        shutil.rmtree(self.at)
        self.at.symlink_to(elsewhere)
        self.assertEqual(elsewhere.resolve(), backups.location(self.at))


class WhetherOneStandsInsideAnother(Copies):
    """`_inside` — the check that stops copies being moved into themselves."""

    def test_a_directory_stands_inside_itself(self):
        self.assertTrue(backups._inside(self.at, self.at))

    def test_a_child_stands_inside_its_parent(self):
        self.assertTrue(backups._inside(self.at / "below", self.home))

    def test_a_parent_does_not_stand_inside_its_child(self):
        self.assertFalse(backups._inside(self.home, self.at))

    def test_unrelated_directories_stand_inside_neither(self):
        self.assertFalse(backups._inside(self.home / "one", self.home / "two"))

    def test_it_sees_through_a_path_written_the_long_way_round(self):
        # `/x/./below/../below` is `/x/below`, and a check comparing them as typed would let a move
        # be pointed inside the directory it is moving.
        long_way = Path(str(self.at) + "/./below/../below")
        self.assertTrue(backups._inside(long_way, self.at))


class WhatThereIs(Copies):
    """`kept` — every copy, newest first, and the three answers it must tell apart."""

    def test_copies_are_listed_newest_first(self):
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-03T03-00-00Z", "2026-08-02T03-00-00Z")
        self.assertEqual(["2026-08-03T03-00-00Z", "2026-08-02T03-00-00Z", "2026-08-01T03-00-00Z"],
                         backups.kept(self.at))

    def test_a_counter_sorts_after_the_name_it_counts_from(self):
        # Two digits is what makes this hold: `-2` would sort before `-10`.
        self.given_copies(ITS_NAME, f"{ITS_NAME}-02", f"{ITS_NAME}-10")
        self.assertEqual([f"{ITS_NAME}-10", f"{ITS_NAME}-02", ITS_NAME], backups.kept(self.at))

    def test_nobody_having_made_one_is_no_copies(self):
        shutil.rmtree(self.at)
        self.assertEqual([], backups.kept(self.at))

    def test_a_directory_that_cannot_be_read_is_never_reported_as_no_copies(self):
        # The case this function exists for. Answering "none" for a directory that is merely
        # unreachable tells somebody their backups are gone, and they act on it.
        if os.geteuid() == 0:
            self.skipTest("root can read a directory with no permissions")
        self.given_copies(ITS_NAME)
        self.at.chmod(0o000)
        self.addCleanup(self.at.chmod, 0o700)
        with self.assertRaises(backups.Refused) as refused:
            backups.kept(self.at)
        self.assertIn("cannot be read", str(refused.exception))

    def test_what_is_not_a_copy_is_not_listed(self):
        self.given_copies(ITS_NAME)
        (self.at / "README.md").write_text("rundesk's own note")
        (self.at / "notes-of-my-own").mkdir()
        self.assertEqual([ITS_NAME], backups.kept(self.at))

    def test_a_copy_being_staged_is_not_listed_as_one(self):
        (self.at / f".{ITS_NAME}.incoming").mkdir()
        self.assertEqual([], backups.kept(self.at))

    def test_a_file_named_like_a_copy_is_not_one(self):
        (self.at / ITS_NAME).write_text("not a directory")
        self.assertEqual([], backups.kept(self.at))


class WhatACopyIsCalled(Copies):
    """`named` — the moment it was made, and a counter only when that is taken."""

    def test_it_is_the_moment_it_was_made(self):
        self.assertEqual(ITS_NAME, backups.named(A_MOMENT, self.at))

    def test_a_second_copy_in_the_same_second_is_counted(self):
        self.given_copies(ITS_NAME)
        self.assertEqual(f"{ITS_NAME}-02", backups.named(A_MOMENT, self.at))

    def test_the_counter_is_two_digits_so_newest_first_stays_right(self):
        self.given_copies(ITS_NAME, *[f"{ITS_NAME}-{n:02d}" for n in range(2, 10)])
        self.assertEqual(f"{ITS_NAME}-10", backups.named(A_MOMENT, self.at))

    def test_a_hundred_in_one_second_is_refused_rather_than_named_wrongly(self):
        self.given_copies(ITS_NAME, *[f"{ITS_NAME}-{n:02d}" for n in range(2, 100)])
        with self.assertRaises(backups.Refused):
            backups.named(A_MOMENT, self.at)

    def test_the_clock_is_the_callers_and_not_one_bound_at_import(self):
        self.assertNotEqual(backups.named(A_MOMENT, self.at), backups.named(None, self.at))


class MakingOne(Copies):
    """`save` — a copy of everything, under a name nothing partial ever wears."""

    def test_it_copies_what_the_owner_keeps_and_says_what_it_is_called(self):
        name = backups.save(self.data, self.at, A_MOMENT)
        self.assertEqual(ITS_NAME, name)
        self.assertEqual("what the owner keeps", (self.at / name / "marker.txt").read_text())

    def test_the_copy_holds_the_configuration_too(self):
        name = backups.save(self.data, self.at, A_MOMENT)
        self.assertTrue((self.at / name / "config.json").is_file())

    def test_it_makes_the_directory_when_there_is_not_one_yet(self):
        shutil.rmtree(self.at)
        backups.save(self.data, self.at, A_MOMENT)
        self.assertEqual([ITS_NAME], backups.kept(self.at))

    def test_there_being_nothing_to_copy_is_refused(self):
        shutil.rmtree(self.data)
        with self.assertRaises(backups.Refused) as refused:
            backups.save(self.data, self.at, A_MOMENT)
        self.assertIn("nothing to copy", str(refused.exception))

    def test_a_copy_that_did_not_finish_is_never_named_like_one_that_did(self):
        # The guarantee the whole staging dance exists for: what is left behind may be litter, but
        # it is never a directory called `2026-08-04T03-00-00Z` holding half an install.
        with mock.patch.object(backups.shutil, "copytree", side_effect=OSError("the disk filled")):
            with self.assertRaises(OSError):
                backups.save(self.data, self.at, A_MOMENT)
        self.assertEqual([], backups.kept(self.at))
        self.assertEqual([], self.entries())

    def test_a_copy_that_could_not_be_renamed_into_place_leaves_nothing_named(self):
        with mock.patch.object(backups.os, "rename", side_effect=OSError("no")):
            with self.assertRaises(OSError):
                backups.save(self.data, self.at, A_MOMENT)
        self.assertEqual([], self.entries())

    def test_it_removes_nothing(self):
        # Letting go of old copies is `prune`, asked for separately — so that the copy a restore
        # takes of what it is replacing cannot push the copy being restored out of a retention
        # nobody asked it about.
        self.given_copies("2020-01-01T00-00-00Z")
        backups.save(self.data, self.at, A_MOMENT)
        self.assertIn("2020-01-01T00-00-00Z", backups.kept(self.at))


class LettingGoOfOldOnes(Copies):
    """`prune` — the only thing in this product that removes a copy."""

    def test_it_lets_go_of_the_oldest_past_what_is_kept(self):
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z", "2026-08-03T03-00-00Z")
        self.assertEqual([], backups.prune(2, self.at))
        self.assertEqual(["2026-08-03T03-00-00Z", "2026-08-02T03-00-00Z"], backups.kept(self.at))

    def test_it_removes_nothing_when_there_are_fewer_than_that(self):
        self.given_copies(ITS_NAME)
        backups.prune(7, self.at)
        self.assertEqual([ITS_NAME], backups.kept(self.at))

    def test_keeping_fewer_than_one_is_refused_rather_than_obeyed(self):
        # Nothing offers a zero, so arriving here with one means something else is wrong — and
        # obeying it would remove every copy the owner has on the strength of an unchecked number.
        self.given_copies(ITS_NAME)
        with self.assertRaises(backups.Refused):
            backups.prune(0, self.at)
        self.assertEqual([ITS_NAME], backups.kept(self.at))

    def test_it_never_touches_what_is_not_a_copy(self):
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z")
        (self.at / "notes-of-my-own").mkdir()
        (self.at / "0000-not-a-copy").mkdir()
        (self.at / "README.md").write_text("rundesk's own note")

        backups.prune(1, self.at)

        # Asserted as the whole directory rather than one name at a time, and that is not fussiness:
        # a version of this that swept every entry instead of the copies passed a name-by-name check
        # comfortably. It removed both copies and merely failed to remove the one *file* — because
        # removing a file as though it were a directory raises — so every individual name a
        # one-at-a-time check thought to ask about was still there.
        self.assertCountEqual(
            ["2026-08-02T03-00-00Z", "notes-of-my-own", "0000-not-a-copy", "README.md"],
            self.entries())

    def test_a_copy_that_cannot_be_put_back_never_evicts_one_that_can(self):
        # The whole reason retention has to ask what a copy is. `kept` and `prune` counted anything
        # shaped like a name while `_a_copy` refused anything without a readable config.json, so an
        # unrestorable copy sat at the newest end of the list, counted towards the number the owner
        # asked to keep, and pushed the last good one out. The owner asked to keep one copy and was
        # left holding the only one that does not work.
        self.given_copy("2020-01-01T00-00-00Z")
        broken = self.at / "2026-08-04T00-00-00Z"
        broken.mkdir()
        (broken / "config.json").write_text("{ not valid json")

        backups.prune(1, self.at)

        self.assertTrue((self.at / "2020-01-01T00-00-00Z").is_dir(),
                        "the only restorable copy was let go of")

    def test_it_leaves_a_copy_it_cannot_read_alone_rather_than_sweeping_it(self):
        # Still the owner's, and rundesk cannot say what is in it. Quietly deleting a directory
        # because a file inside it would not parse is not this command's decision to make.
        broken = self.at / "2026-08-04T00-00-00Z"
        broken.mkdir()
        (broken / "config.json").write_text("{ not valid json")
        self.given_copy("2020-01-01T00-00-00Z")

        backups.prune(1, self.at)

        self.assertTrue(broken.is_dir())

    def test_whether_a_copy_can_be_put_back_is_one_question_with_one_answer(self):
        self.given_copy(ITS_NAME)
        nameless = self.at / "2020-01-01T00-00-00Z"
        nameless.mkdir()
        self.assertTrue(backups.restorable(self.at, ITS_NAME))
        self.assertFalse(backups.restorable(self.at, "2020-01-01T00-00-00Z"))
        self.assertFalse(backups.restorable(self.at, "never-made"))

    def test_it_says_which_it_could_not_remove(self):
        if os.geteuid() == 0:
            self.skipTest("root may remove from a directory with no write permission")
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z")
        unwritable(self.at)
        self.addCleanup(self.at.chmod, 0o700)
        self.assertEqual(["2026-08-01T03-00-00Z"], backups.prune(1, self.at))

    def test_it_says_what_it_let_go_of(self):
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z")
        said = []
        backups.prune(1, self.at, said.append)
        self.assertEqual(["let go of 2026-08-01T03-00-00Z"], said)


class WhetherSomethingIsACopy(Copies):
    """`_a_copy` — three different mistakes, told apart."""

    def test_a_name_that_is_not_a_copys_shape_is_refused(self):
        with self.assertRaises(backups.Refused) as refused:
            backups._a_copy(self.at, "last-tuesday")
        self.assertIn("is not the name of a copy", str(refused.exception))

    def test_a_name_nobody_made_is_refused_differently(self):
        with self.assertRaises(backups.Refused) as refused:
            backups._a_copy(self.at, ITS_NAME)
        self.assertIn("there is no copy called", str(refused.exception))

    def test_a_directory_with_no_readable_configuration_is_not_a_copy(self):
        # Putting one back would leave `migration` reading as unset, and the next thing to look
        # would run every step this release ships over data that may already have had them.
        (self.at / ITS_NAME).mkdir()
        with self.assertRaises(backups.Refused) as refused:
            backups._a_copy(self.at, ITS_NAME)
        self.assertIn("config.json", str(refused.exception))

    def test_a_configuration_that_will_not_parse_is_not_readable(self):
        (self.at / ITS_NAME).mkdir()
        (self.at / ITS_NAME / "config.json").write_text("{ not json")
        with self.assertRaises(backups.Refused):
            backups._a_copy(self.at, ITS_NAME)

    def test_a_real_copy_is_handed_back(self):
        self.given_copies(ITS_NAME)
        self.assertEqual(self.at / ITS_NAME, backups._a_copy(self.at, ITS_NAME))


class PuttingOneBack(Copies):
    """`restore` — and the copy it takes of what it replaces, before it replaces it."""

    def setUp(self):
        super().setUp()
        self.steps = self.home / "steps"
        self.steps.mkdir(parents=True, exist_ok=True)

    def given_step(self, name: str, body: str = "") -> None:
        (self.steps / f"{name}.py").write_text(body or A_STEP.format(name=name))

    def test_it_puts_the_data_back(self):
        self.given_copies(ITS_NAME)
        self.given_data("changed since")
        backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)
        self.assertEqual(ITS_NAME, (self.data / "marker.txt").read_text())

    def test_it_keeps_a_copy_of_what_it_replaces_first(self):
        # A restore of the wrong name is the thing somebody does at four in the morning, and this is
        # what makes it cost a command rather than everything they had.
        self.given_copies(ITS_NAME)
        self.given_data("what was there before")
        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)
        self.assertIsNotNone(done.safety)
        self.assertEqual("what was there before",
                         (self.at / done.safety / "marker.txt").read_text())

    def test_the_copy_it_keeps_is_not_the_one_being_put_back(self):
        self.given_copies(ITS_NAME)
        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)
        self.assertNotEqual(ITS_NAME, done.safety)

    def test_there_being_no_data_yet_means_there_is_nothing_to_keep(self):
        self.given_copies(ITS_NAME)
        shutil.rmtree(self.data)
        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)
        self.assertIsNone(done.safety)
        self.assertEqual(ITS_NAME, (self.data / "marker.txt").read_text())

    def test_a_name_that_is_not_a_copy_changes_nothing(self):
        self.given_data("untouched")
        with self.assertRaises(backups.Refused):
            backups.restore("last-tuesday", self.data, self.at, A_MOMENT, self.steps)
        self.assertEqual("untouched", (self.data / "marker.txt").read_text())
        self.assertEqual([], backups.kept(self.at))

    def test_it_carries_what_comes_back_onto_this_release(self):
        # Data copied three releases ago has never been carried forward. Putting the files back is
        # not the end of a restore.
        self.given_copies(ITS_NAME)
        self.given_step("0001_first")
        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)
        self.assertIsNone(done.settled)
        self.assertTrue((self.data / "carried").is_file())
        self.assertEqual("0001_first", config.read(self.data)["migration"])

    def test_a_step_that_cannot_finish_is_said_rather_than_reported_as_restored(self):
        self.given_copies(ITS_NAME)
        self.given_step("0001_first", support.A_STEP_THAT_FAILS)
        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)
        self.assertIsNotNone(done.settled)
        self.assertIn("0001_first", done.settled)

    def test_what_it_did_is_three_answers_and_not_one(self):
        self.given_copies(ITS_NAME)
        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)
        self.assertEqual(ITS_NAME, done.name)
        self.assertIsNotNone(done.safety)
        self.assertIsNone(done.settled)


class PuttingBackSomethingOlder(Copies):
    """A copy older than this release, and the steps it never had run over it.

    The question somebody actually has: *this data is from three releases ago — does rundesk know
    what to do with it?* It does, and the mechanism is the install migration runner handed the
    restored `data/` once the files have landed. The copy carries its own `migration` mark, so what
    runs is exactly the steps taken after that mark — **the ones it missed, and not the ones it
    already had.** A step that ran twice is not a smaller mistake than a step that never ran; it is
    the reason steps are recorded at all.
    """

    def setUp(self):
        super().setUp()
        self.steps = self.home / "steps"
        self.steps.mkdir(parents=True, exist_ok=True)

    def given_steps(self, *names: str) -> None:
        for name in names:
            (self.steps / f"{name}.py").write_text(AN_APPENDING_STEP.format(name=name))

    def given_it_already_ran(self, copy: Path, *names: str) -> None:
        """Mark a copy as having had these steps run when it was made."""
        (copy / "carried").write_text("".join(f"{name}\n" for name in names))

    def carried(self):
        """Every step that has run over the restored data, in the order they ran."""
        at = self.data / "carried"
        return at.read_text().split() if at.exists() else []

    def test_a_copy_carried_to_nothing_has_every_step_run_over_it(self):
        self.given_steps("0001_first", "0002_second", "0003_third")
        self.given_copy(ITS_NAME, migration=None)
        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)
        self.assertIsNone(done.settled)
        self.assertEqual(["0001_first", "0002_second", "0003_third"], self.carried())
        self.assertEqual("0003_third", config.read(self.data)["migration"])

    def test_a_copy_carried_partway_has_exactly_the_steps_it_missed_run(self):
        # The case the whole after-hook exists for: a copy taken when the install had had `0001`
        # comes back onto a release shipping three, and picks up the two it never saw.
        self.given_steps("0001_first", "0002_second", "0003_third")
        copy = self.given_copy(ITS_NAME, migration="0001_first")
        self.given_it_already_ran(copy, "0001_first")

        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)

        self.assertIsNone(done.settled)
        self.assertEqual(["0001_first", "0002_second", "0003_third"], self.carried())
        self.assertEqual("0003_third", config.read(self.data)["migration"])

    def test_a_step_the_copy_already_had_is_not_run_a_second_time(self):
        # Told apart from the case above only because the step appends rather than overwrites: a
        # step that ran twice would otherwise look exactly like a step that ran once.
        self.given_steps("0001_first", "0002_second")
        copy = self.given_copy(ITS_NAME, migration="0001_first")
        self.given_it_already_ran(copy, "0001_first")

        backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)

        self.assertEqual(1, self.carried().count("0001_first"),
                         "a step the copy had already had was run over it again")

    def test_a_copy_already_on_the_newest_step_has_nothing_run_over_it(self):
        self.given_steps("0001_first")
        copy = self.given_copy(ITS_NAME, migration="0001_first")
        self.given_it_already_ran(copy, "0001_first")

        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)

        self.assertIsNone(done.settled)
        self.assertEqual(["0001_first"], self.carried())

    def test_a_copy_from_a_newer_release_is_said_rather_than_carried_backwards(self):
        # Running an older release's steps over a newer release's layout is how data gets damaged,
        # so this is refused — and the refusal reaches the caller instead of being swallowed.
        self.given_steps("0001_first")
        self.given_copy(ITS_NAME, migration="0009_from_a_release_this_one_never_saw")

        done = backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)

        self.assertIsNotNone(done.settled)
        self.assertIn("newer release", done.settled)
        # The files really are back regardless, which is why saying so matters rather than exiting 0.
        self.assertEqual(ITS_NAME, (self.data / "marker.txt").read_text())

    def test_the_steps_run_after_the_files_land_and_not_before(self):
        # A step reads the data it is carrying forward. Running one against `data/` as it was before
        # the restore would carry the wrong install and stamp the copy as though it had happened.
        self.given_steps("0001_first")
        self.given_copy(ITS_NAME, "the copy's own marker", migration=None)
        self.given_data("what was there before")

        backups.restore(ITS_NAME, self.data, self.at, A_MOMENT, self.steps)

        self.assertEqual("the copy's own marker", (self.data / "marker.txt").read_text())
        self.assertEqual(["0001_first"], self.carried())


class WhenPuttingOneBackGoesWrong(Copies):
    """`_swap` and `_put_back` — what `data/` looks like after a restore that could not finish."""

    def test_a_copy_that_will_not_copy_leaves_the_data_as_it_was(self):
        self.given_copies(ITS_NAME)
        self.given_data("untouched")
        with mock.patch.object(backups.shutil, "copytree", side_effect=OSError("the disk filled")):
            with self.assertRaises(OSError):
                backups._swap(self.at / ITS_NAME, self.data)
        self.assertEqual("untouched", (self.data / "marker.txt").read_text())

    def test_a_swap_that_fails_puts_back_what_was_there(self):
        self.given_copies(ITS_NAME)
        self.given_data("untouched")
        really = os.rename

        def not_the_last_move(src, dst):
            if str(src).endswith(".incoming"):
                raise OSError("interrupted")
            return really(src, dst)

        with mock.patch.object(backups.os, "rename", side_effect=not_the_last_move):
            with self.assertRaises(OSError):
                backups._swap(self.at / ITS_NAME, self.data)
        self.assertEqual("untouched", (self.data / "marker.txt").read_text())

    def test_it_leaves_no_staging_behind_when_it_fails(self):
        self.given_copies(ITS_NAME)
        self.given_data("untouched")
        with mock.patch.object(backups.os, "rename", side_effect=OSError("no")):
            with self.assertRaises(OSError):
                backups._swap(self.at / ITS_NAME, self.data)
        self.assertEqual([], [one.name for one in self.home.iterdir()
                              if one.name.startswith(".data")])

    def test_being_unable_to_put_it_back_says_so_rather_than_pretending(self):
        aside = self.home / "never-written"
        with self.assertRaises(backups.HalfRestored) as half:
            backups._put_back(aside, self.data)
        self.assertIn("could not be put back", str(half.exception))

    def test_a_restore_that_half_happened_names_the_copy_to_recover_from(self):
        # The one failure with nothing left to try, so the message has to carry the way out of it.
        self.given_copies(ITS_NAME)
        self.given_data("untouched")
        calls = []
        really = os.rename

        def only_the_safety_copy_and_the_move_aside(src, dst):
            # Three renames reach here: the safety copy landing, `data/` moving aside, and the
            # restored copy moving in. Failing from the third on means the swap is half done *and*
            # putting it back fails too, which is the only route to `HalfRestored`.
            calls.append(src)
            if len(calls) <= 2:
                return really(src, dst)
            raise OSError("interrupted")

        with mock.patch.object(backups.os, "rename",
                               side_effect=only_the_safety_copy_and_the_move_aside):
            with self.assertRaises(backups.HalfRestored) as half:
                backups.restore(ITS_NAME, self.data, self.at, A_MOMENT)
        self.assertRegex(str(half.exception), r"that copy is 2026-08-04T03-00-00Z")


class SettlingWhatCameBack(Copies):
    """`_settle` — the after-hook, which is what makes a restore finish rather than merely land."""

    def setUp(self):
        super().setUp()
        self.steps = self.home / "steps"
        self.steps.mkdir(parents=True, exist_ok=True)

    def test_it_fills_in_a_setting_the_copy_predates(self):
        jsonfile.write(self.data / "config.json", {"backup_enabled": False})
        self.assertIsNone(backups._settle(self.data, self.steps, lambda _line: None))
        settled = jsonfile.read(self.data / "config.json")[1]
        self.assertIn("update_time", settled)

    def test_it_leaves_a_value_the_owner_stated_exactly_as_it_was(self):
        jsonfile.write(self.data / "config.json", {"backup_enabled": False})
        backups._settle(self.data, self.steps, lambda _line: None)
        self.assertIs(False, jsonfile.read(self.data / "config.json")[1]["backup_enabled"])

    def test_it_carries_the_steps_the_copy_never_ran(self):
        (self.steps / "0001_first.py").write_text(A_STEP.format(name="0001_first"))
        self.assertIsNone(backups._settle(self.data, self.steps, lambda _line: None))
        self.assertEqual("0001_first", config.read(self.data)["migration"])

    def test_it_says_why_when_a_step_could_not_finish(self):
        (self.steps / "0001_first.py").write_text(support.A_STEP_THAT_FAILS)
        why = backups._settle(self.data, self.steps, lambda _line: None)
        self.assertIn("0001_first", why)

    def test_a_configuration_that_cannot_be_read_is_said_rather_than_written_over(self):
        (self.data / "config.json").write_text("{ not json")
        why = backups._settle(self.data, self.steps, lambda _line: None)
        self.assertIn("cannot be read", why)

    def test_carrying_that_cannot_read_the_configuration_is_said_and_not_raised(self):
        # `carry` reads the configuration before it runs anything and writes through it for every
        # stamp, so it gives the same two answers filling in does. Guarding only the first call
        # would let this out as a traceback — and out *after* `data/` had already been replaced,
        # which is the loudest failure at the quietest moment.
        (self.steps / "0001_first.py").write_text(A_STEP.format(name="0001_first"))
        with mock.patch.object(config, "read", side_effect=config.Unreadable("it went unreadable")):
            why = backups._settle(self.data, self.steps, lambda _line: None)
        self.assertEqual("it went unreadable", why)

    def test_a_configuration_held_by_something_else_is_said_and_not_raised(self):
        with mock.patch.object(config, "read", side_effect=config.Stuck("something else has it")):
            why = backups._settle(self.data, self.steps, lambda _line: None)
        self.assertEqual("something else has it", why)


class MovingThemSomewhereElse(Copies):
    """`relocate` — copied to the new place first, and taken from the old one only after."""

    def setUp(self):
        super().setUp()
        self.elsewhere = self.home / "elsewhere"

    def test_the_copies_are_at_the_new_place_and_the_old_one_is_a_link(self):
        self.given_copies(ITS_NAME)
        self.assertEqual(self.elsewhere, backups.relocate(self.elsewhere, self.at))
        self.assertTrue(self.at.is_symlink())
        self.assertEqual(ITS_NAME, (self.elsewhere / ITS_NAME / "marker.txt").read_text())

    def test_they_are_still_listed_afterwards(self):
        self.given_copies(ITS_NAME)
        backups.relocate(self.elsewhere, self.at)
        self.assertEqual([ITS_NAME], backups.kept(self.at))

    def test_it_carries_what_is_not_a_copy_too(self):
        # A move that carried the copies and left the owner's own files in a directory it then
        # replaced with a link has reported a move it did not make.
        self.given_copies(ITS_NAME)
        (self.at / "notes-of-my-own").write_text("mine")
        backups.relocate(self.elsewhere, self.at)
        self.assertEqual("mine", (self.elsewhere / "notes-of-my-own").read_text())

    def test_the_old_directory_is_gone_once_they_are_moved(self):
        self.given_copies(ITS_NAME)
        backups.relocate(self.elsewhere, self.at)
        self.assertFalse((self.home / ".backups.outgoing").exists())

    def test_moving_them_a_second_time_leaves_the_directory_the_owner_named_standing(self):
        # Their directory, not rundesk's to delete — but the copies in it really move.
        self.given_copies(ITS_NAME)
        backups.relocate(self.elsewhere, self.at)
        further = self.home / "further"
        backups.relocate(further, self.at)
        self.assertEqual([ITS_NAME], backups.kept(self.at))
        self.assertTrue(self.elsewhere.is_dir())
        self.assertFalse((self.elsewhere / ITS_NAME).exists())

    def test_a_relative_path_is_refused(self):
        # `paths.Refused` and not merely "something": the command catches an exact tuple, so a
        # refusal that changed type would reach somebody as a traceback while a looser assertion
        # here went on passing.
        with self.assertRaises(paths.Refused) as refused:
            backups.relocate(Path("somewhere"), self.at)
        self.assertIn("absolute", str(refused.exception))

    def test_the_home_directory_itself_is_refused(self):
        with self.assertRaises(paths.Refused) as refused:
            backups.relocate(Path.home(), self.at)
        self.assertIn("home directory", str(refused.exception))

    def test_a_directory_with_something_already_in_it_is_refused(self):
        self.elsewhere.mkdir()
        (self.elsewhere / "somebody-elses").write_text("theirs")
        with self.assertRaises(backups.Refused) as refused:
            backups.relocate(self.elsewhere, self.at)
        self.assertIn("already has something in it", str(refused.exception))

    def test_a_place_inside_the_one_they_are_in_is_refused(self):
        with self.assertRaises(backups.Refused) as refused:
            backups.relocate(self.at / "below", self.at)
        self.assertIn("inside one another", str(refused.exception))

    def test_a_place_that_is_not_a_directory_is_refused(self):
        self.elsewhere.write_text("a file")
        with self.assertRaises(backups.Refused) as refused:
            backups.relocate(self.elsewhere, self.at)
        self.assertIn("not a directory", str(refused.exception))

    def test_a_move_that_fails_partway_leaves_every_copy_where_it_was(self):
        # The whole reason for copying first: this failure is a tidying job, not a loss.
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z")
        with mock.patch.object(backups.shutil, "copytree", side_effect=OSError("the disk filled")):
            with self.assertRaises(OSError):
                backups.relocate(self.elsewhere, self.at)
        self.assertEqual(["2026-08-02T03-00-00Z", "2026-08-01T03-00-00Z"], backups.kept(self.at))
        self.assertFalse(self.at.is_symlink())


class WhenTheCopiesAreSomewhereUnplugged(Copies):
    """A `backups/` linked to a disk that is not there — the third answer `set-location` created.

    Every one of these went green before the guard existed, because a broken link gives exactly the
    same `FileNotFoundError` an install that has never copied anything gives. That is the whole
    defect: the worst moment answered with the most reassuring sentence.
    """

    def setUp(self):
        super().setUp()
        self.given_copies(ITS_NAME)
        self.elsewhere = self.home / "elsewhere"
        backups.relocate(self.elsewhere, self.at)
        shutil.rmtree(self.elsewhere)

    def test_listing_them_is_refused_rather_than_reported_as_none(self):
        with self.assertRaises(backups.Refused) as refused:
            backups.kept(self.at)
        self.assertIn("which is not there", str(refused.exception))

    def test_putting_one_back_does_not_claim_the_copy_was_never_made(self):
        with self.assertRaises(backups.Refused) as refused:
            backups.restore(ITS_NAME, self.data, self.at, A_MOMENT)
        self.assertNotIn("there is no copy called", str(refused.exception))
        self.assertIn("which is not there", str(refused.exception))

    def test_moving_them_again_is_refused_rather_than_orphaning_them(self):
        # Carrying nothing off a disk it cannot read, re-pointing the link, and reporting success
        # would leave every copy stranded where nothing on this machine says to look.
        further = self.home / "further"
        with self.assertRaises(backups.Refused):
            backups.relocate(further, self.at)
        self.assertEqual(self.elsewhere.resolve(), self.at.resolve(),
                         "the link was re-pointed away from the copies")

    def test_saving_says_what_happened_rather_than_an_errno(self):
        # The operation most likely to be running unattended when a disk is unplugged, and the one
        # entry point the guard did not reach: `mkdir(exist_ok=True)` raises on a broken link
        # because the directory entry is there, so this came out as `[Errno 17] File exists`.
        with self.assertRaises(backups.Refused) as refused:
            backups.save(self.data, self.at, A_MOMENT)
        self.assertIn("which is not there", str(refused.exception))

    def test_the_command_fails_rather_than_offering_to_make_a_first_copy(self):
        code, out, err = self.rundesk("backups")
        self.assertEqual(FAILED, code)
        self.assertNotIn("none yet", out)
        self.assertIn("which is not there", err)

    def test_a_directory_that_is_simply_not_there_yet_is_still_no_copies(self):
        # The guard must not have swallowed the ordinary case it sits next to.
        fresh = self.home / "a-fresh-install" / "backups"
        self.assertEqual([], backups.kept(fresh))


class CarryingThemAcross(Copies):
    """`_copy_across` — everything in the old place, and nothing left behind if part of it fails."""

    def setUp(self):
        super().setUp()
        self.elsewhere = self.home / "elsewhere"
        self.elsewhere.mkdir()

    def test_it_carries_every_entry_and_says_which(self):
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z")
        (self.at / "README.md").write_text("rundesk's own note")
        said = []
        landed = backups._copy_across(self.at, self.elsewhere, said.append)
        self.assertCountEqual(["2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z", "README.md"], landed)
        self.assertEqual(len(landed), len(said))

    def test_it_takes_back_what_it_wrote_when_part_of_it_fails(self):
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z")
        really = shutil.copytree
        seen = []

        def the_second_one_fails(*args, **kwargs):
            seen.append(args[0])
            if len(seen) == 2:
                raise OSError("the disk filled")
            return really(*args, **kwargs)

        with mock.patch.object(backups.shutil, "copytree", side_effect=the_second_one_fails):
            with self.assertRaises(OSError):
                backups._copy_across(self.at, self.elsewhere, lambda _line: None)
        self.assertEqual([], sorted(one.name for one in self.elsewhere.iterdir()))

    def test_it_does_not_carry_something_that_is_being_staged(self):
        (self.at / f".{ITS_NAME}.incoming").mkdir()
        self.assertEqual([], backups._copy_across(self.at, self.elsewhere, lambda _line: None))

    def test_there_being_nothing_to_carry_is_not_an_error(self):
        shutil.rmtree(self.at)
        self.assertEqual([], backups._copy_across(self.at, self.elsewhere, lambda _line: None))


class PointingTheOldPlaceAtTheNew(Copies):
    """`_point_at` — swapping a directory for a link without a moment holding neither."""

    def setUp(self):
        super().setUp()
        self.elsewhere = self.home / "elsewhere"
        self.elsewhere.mkdir()

    def test_a_real_directory_becomes_a_link(self):
        backups._point_at(self.at, self.elsewhere)
        self.assertTrue(self.at.is_symlink())
        self.assertEqual(self.elsewhere.resolve(), self.at.resolve())

    def test_a_link_that_is_already_one_is_re_pointed(self):
        backups._point_at(self.at, self.elsewhere)
        further = self.home / "further"
        further.mkdir()
        backups._point_at(self.at, further)
        self.assertEqual(further.resolve(), self.at.resolve())

    def test_there_being_nothing_there_yet_still_makes_the_link(self):
        shutil.rmtree(self.at)
        backups._point_at(self.at, self.elsewhere)
        self.assertTrue(self.at.is_symlink())

    def test_a_link_is_put_back_when_the_new_one_cannot_be_made(self):
        # The branch that only runs the *second* time somebody moves their copies, which is why it
        # was the one missing a rollback. Losing the link is worse than losing a directory here: the
        # copies are still on the old disk and nothing left on this machine says where.
        self.given_copies(ITS_NAME)
        backups.relocate(self.elsewhere, self.at)
        further = self.home / "further"
        really = Path.symlink_to

        def not_the_new_one(where, target, *args, **named):
            if Path(target) == further:
                raise OSError("no")
            return really(where, target, *args, **named)

        with mock.patch.object(Path, "symlink_to", not_the_new_one):
            with self.assertRaises(OSError):
                backups._point_at(self.at, further)

        self.assertTrue(self.at.is_symlink(), "the link was removed and never put back")
        self.assertEqual(self.elsewhere.resolve(), self.at.resolve())
        self.assertEqual([ITS_NAME], backups.kept(self.at))

    def test_a_link_that_cannot_be_put_back_either_is_said_and_not_swallowed(self):
        # Both the new link and the rollback failing leaves no link at all where the copies were
        # reached through. Swallowed, that is the worse of the two bugs: a missing directory is not
        # a broken symlink, so `_reachable` never fires on it, `kept` legitimately answers "none",
        # and the owner is told they have no copies while every one sits intact on the other disk.
        self.given_copies(ITS_NAME)
        backups.relocate(self.elsewhere, self.at)

        with mock.patch.object(Path, "symlink_to", side_effect=OSError("the disk is full")):
            with self.assertRaises(backups.HalfRestored) as half:
                backups._point_at(self.at, self.home / "further")

        self.assertIn(str(self.elsewhere), str(half.exception),
                      "the message does not say where the copies still are")

    def test_the_directory_is_put_back_when_the_link_cannot_be_made(self):
        # Between removing a directory and creating a link there is a moment with neither, and what
        # was there has to survive it.
        self.given_copies(ITS_NAME)
        with mock.patch.object(Path, "symlink_to", side_effect=OSError("no")):
            with self.assertRaises(OSError):
                backups._point_at(self.at, self.elsewhere)
        self.assertTrue(self.at.is_dir())
        self.assertFalse(self.at.is_symlink())
        self.assertEqual([ITS_NAME], backups.kept(self.at))


class TakingBackWhatWasWritten(Copies):
    """`_could_not_remove` — exactly the names it was given, and the ones that would not go."""

    def test_it_removes_exactly_the_names_it_was_given(self):
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z")
        self.assertEqual([], backups._could_not_remove(self.at, ["2026-08-01T03-00-00Z"]))
        self.assertEqual(["2026-08-02T03-00-00Z"], backups.kept(self.at))

    def test_a_name_that_is_not_there_is_not_a_failure(self):
        self.assertEqual([], backups._could_not_remove(self.at, ["never-written"]))

    def test_it_removes_a_file_as_readily_as_a_directory(self):
        (self.at / "a-file").write_text("something")
        self.assertEqual([], backups._could_not_remove(self.at, ["a-file"]))
        self.assertFalse((self.at / "a-file").exists())

    def test_it_says_which_would_not_go(self):
        if os.geteuid() == 0:
            self.skipTest("root may remove from a directory with no write permission")
        self.given_copies(ITS_NAME)
        unwritable(self.at)
        self.addCleanup(self.at.chmod, 0o700)
        self.assertEqual([ITS_NAME], backups._could_not_remove(self.at, [ITS_NAME]))


class TheCommand(Copies):
    """`rundesk backups` and its three sub-verbs, driven the way somebody types them."""

    def test_with_nothing_named_it_lists_them(self):
        self.given_copies("2026-08-01T03-00-00Z", "2026-08-02T03-00-00Z")
        code, out, _ = self.rundesk("backups")
        self.assertEqual(OK, code)
        self.assertLess(out.index("2026-08-02T03-00-00Z"), out.index("2026-08-01T03-00-00Z"),
                        "copies are not listed newest first")

    def test_it_says_where_they_are_kept_even_when_there_are_none(self):
        # "No copies" and "no copies *here*" are different things to learn.
        code, out, _ = self.rundesk("backups")
        self.assertEqual(OK, code)
        self.assertIn(str(self.at), out)
        self.assertIn("none yet", out)

    def test_a_directory_that_cannot_be_read_fails_rather_than_reporting_none(self):
        if os.geteuid() == 0:
            self.skipTest("root can read a directory with no permissions")
        self.at.chmod(0o000)
        self.addCleanup(self.at.chmod, 0o700)
        code, out, err = self.rundesk("backups")
        self.assertEqual(FAILED, code)
        self.assertNotIn("none yet", out)
        self.assertIn("cannot be read", err)

    def test_save_makes_one_and_says_what_it_is_called(self):
        code, out, _ = self.rundesk("backups", "save")
        self.assertEqual(OK, code)
        self.assertEqual(1, len(backups.kept(self.at)))
        self.assertIn(backups.kept(self.at)[0], out)

    def test_save_lets_go_of_the_oldest_past_what_is_configured(self):
        config.stated("backup_retention", 1, self.data)
        self.given_copies("2020-01-01T00-00-00Z")
        self.rundesk("backups", "save")
        self.assertEqual(1, len(backups.kept(self.at)))
        self.assertNotIn("2020-01-01T00-00-00Z", backups.kept(self.at))

    def test_save_reports_the_copy_even_when_the_retention_cannot_be_read(self):
        # The operation asked for was a copy, and the copy is there. Reporting a failure it did not
        # have costs the same trust as reporting a success it did not earn.
        jsonfile.write(self.data / "config.json", dict(config.INITIAL, backup_retention="seven"))
        code, out, err = self.rundesk("backups", "save")
        self.assertEqual(OK, code)
        self.assertIn("saved", out)
        self.assertIn("nothing was let go", err)

    def test_restore_without_confirming_changes_nothing(self):
        self.given_copies(ITS_NAME)
        self.given_data("untouched")
        code, _, err = self.rundesk("backups", "restore", ITS_NAME)
        self.assertEqual(FAILED, code)
        self.assertIn("nothing was restored", err)
        self.assertEqual("untouched", (self.data / "marker.txt").read_text())

    def test_restore_of_a_name_nobody_made_is_refused_before_it_is_confirmed(self):
        code, _, err = self.rundesk("backups", "restore", ITS_NAME)
        self.assertEqual(FAILED, code)
        self.assertIn("there is no copy called", err)

    def test_restore_with_confirming_puts_it_back_and_keeps_what_it_replaced(self):
        self.given_copies(ITS_NAME)
        self.given_data("changed since")
        code, out, _ = self.rundesk("backups", "restore", ITS_NAME, "--confirm")
        self.assertEqual(OK, code)
        self.assertEqual(ITS_NAME, (self.data / "marker.txt").read_text())
        self.assertIn("kept", out)
        self.assertEqual(2, len(backups.kept(self.at)))

    def test_set_location_moves_them_and_links_back(self):
        self.given_copies(ITS_NAME)
        elsewhere = self.home / "elsewhere"
        code, out, _ = self.rundesk("backups", "set-location", str(elsewhere))
        self.assertEqual(OK, code)
        self.assertIn(str(elsewhere), out)
        self.assertTrue((elsewhere / ITS_NAME).is_dir())
        self.assertTrue(self.at.is_symlink())

    def test_set_location_to_where_they_already_are_changes_nothing(self):
        self.given_copies(ITS_NAME)
        elsewhere = self.home / "elsewhere"
        self.rundesk("backups", "set-location", str(elsewhere))
        code, out, _ = self.rundesk("backups", "set-location", str(elsewhere))
        self.assertEqual(OK, code)
        self.assertIn("already keeps", out)
        self.assertEqual([ITS_NAME], backups.kept(self.at))

    def test_set_location_somewhere_refused_leaves_them_where_they_were(self):
        self.given_copies(ITS_NAME)
        code, _, err = self.rundesk("backups", "set-location", "somewhere")
        self.assertEqual(FAILED, code)
        self.assertIn("the copies are where they were", err)
        self.assertEqual([ITS_NAME], backups.kept(self.at))
        self.assertFalse(self.at.is_symlink())

    def test_listing_says_where_they_really_are_once_they_have_been_moved(self):
        self.given_copies(ITS_NAME)
        elsewhere = self.home / "elsewhere"
        self.rundesk("backups", "set-location", str(elsewhere))
        _, out, _ = self.rundesk("backups")
        self.assertIn(f"{self.at} → {elsewhere}", out)

    def test_status_says_where_they_really_are_once_they_have_been_moved(self):
        elsewhere = self.home / "elsewhere"
        self.rundesk("backups", "set-location", str(elsewhere))
        _, out, _ = self.rundesk("status")
        self.assertIn(f"{self.at} → {elsewhere}", out)

    def test_status_tells_a_link_pointing_nowhere_from_an_install_with_no_copies(self):
        elsewhere = self.home / "elsewhere"
        self.rundesk("backups", "set-location", str(elsewhere))
        shutil.rmtree(elsewhere)
        _, out, _ = self.rundesk("status")
        self.assertIn("that directory is not there", out)
        self.assertNotIn(f"{self.at} — not there yet", out)

    def test_a_restore_that_could_not_be_carried_forward_is_not_reported_as_done(self):
        # This release ships no steps, so the only way to reach the branch is to hand the command a
        # restore that did not settle. What is being proved is the command's reading of it: files
        # back, not carried forward, and an exit code that says the work is unfinished.
        self.given_copies(ITS_NAME)
        unsettled = backups.Restored(ITS_NAME, "2020-01-01T00-00-00Z", "0002_second did not finish")
        with mock.patch("rundesk.commands.backups.backups.restore", return_value=unsettled):
            code, out, err = self.rundesk("backups", "restore", ITS_NAME, "--confirm")
        self.assertEqual(FAILED, code)
        self.assertIn("could not be settled", err)
        self.assertIn("0002_second", err)
        self.assertIn("rundesk update", err)
        self.assertIn(ITS_NAME, out)

    def test_a_restore_that_half_happened_is_reported_as_the_worst_case_it_is(self):
        # The single worst outcome in the system, and it was proved only one layer down. A reorder
        # of these except clauses would have gone unnoticed.
        self.given_copies(ITS_NAME)
        half = backups.HalfRestored("could not be put back, and that copy is 2020-01-01T00-00-00Z")
        with mock.patch("rundesk.commands.backups.backups.restore", side_effect=half):
            code, _, err = self.rundesk("backups", "restore", ITS_NAME, "--confirm")
        self.assertEqual(FAILED, code)
        self.assertIn("2020-01-01T00-00-00Z", err)
        self.assertIn("neither what it was nor what you asked for", err)

    def test_a_save_that_could_not_be_made_says_so_and_makes_none(self):
        shutil.rmtree(self.data)
        code, out, err = self.rundesk("backups", "save")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("no copy was made", err)
        self.assertEqual([], backups.kept(self.at))

    def test_a_sub_verb_that_is_not_one_is_a_usage_error(self):
        code, _, _ = self.rundesk("backups", "delete-everything")
        self.assertEqual(2, code)

    def test_restore_wants_a_copy_to_be_named(self):
        code, _, _ = self.rundesk("backups", "restore")
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
