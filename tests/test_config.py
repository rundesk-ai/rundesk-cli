"""Install-wide configuration, and how far this install has been carried.

Run directly: `python3 tests/test_config.py`
"""

import fcntl
import json
import os
import time
import unittest
from datetime import datetime, timezone

import support
from rundesk.core import config, jsonfile


class WhatAFreshInstallIsWrittenWith(support.Isolated):

    def test_it_writes_every_value_this_release_knows_about(self):
        written = config.write_fresh(self.home / "data")
        self.assertEqual(set(config.INITIAL), set(written))
        self.assertTrue(config.where(self.home / "data").exists())

    def test_it_writes_the_settings_the_owner_asked_for(self):
        written = config.write_fresh(self.home / "data")
        for key in ("backup_enabled", "backup_retention", "update_enabled", "update_time"):
            self.assertIn(key, written)

    def test_it_carries_how_far_the_install_has_been_moved(self):
        # In the same file on purpose: "what state is this install in" is one question.
        self.assertIn("migration", config.write_fresh(self.home / "data"))

    def test_installing_over_an_install_does_not_reset_what_its_owner_stated(self):
        data = self.home / "data"
        config.write_fresh(data)
        config.stated("update_enabled", False, data)
        config.write_fresh(data)
        self.assertFalse(config.read(data)["update_enabled"])


class WhatAnUpdateMayChange(support.Isolated):

    def test_it_adds_a_value_a_newer_release_introduced(self):
        data = self.home / "data"
        jsonfile.write(config.where(data), {"backup_enabled": False})
        settled = config.fill_in(data)
        self.assertIn("update_time", settled)
        self.assertEqual(config.INITIAL["update_time"], settled["update_time"])

    def test_it_changes_nothing_already_stated(self):
        data = self.home / "data"
        jsonfile.write(config.where(data), {"backup_retention": 30})
        self.assertEqual(30, config.fill_in(data)["backup_retention"])

    def test_a_stated_false_is_an_answer_and_not_an_absent_one(self):
        # The one that looks like a default nobody set, and is not.
        data = self.home / "data"
        jsonfile.write(config.where(data), {"update_enabled": False})
        self.assertFalse(config.fill_in(data)["update_enabled"])
        self.assertFalse(config.read(data)["update_enabled"])


class AskingHowItIsConfigured(support.Isolated):

    def test_reading_answers_for_a_value_this_release_added_without_writing_one(self):
        data = self.home / "data"
        jsonfile.write(config.where(data), {"backup_enabled": True})
        self.assertEqual(config.INITIAL["update_time"], config.read(data)["update_time"])
        on_disk = json.loads(config.where(data).read_text())
        self.assertNotIn("update_time", on_disk, "asking how it is configured wrote to the file")

    def test_a_configuration_that_cannot_be_read_is_refused_rather_than_defaulted(self):
        # Treating it as unwritten would answer every question with the factory setting, so an owner
        # who turned updates off would find them on again and nothing would have said so.
        data = self.home / "data"
        config.where(data).parent.mkdir(parents=True, exist_ok=True)
        config.where(data).write_text("{ this is not json")
        with self.assertRaises(config.Unreadable):
            config.read(data)

    def test_a_value_rundesk_is_not_configured_with_is_refused(self):
        with self.assertRaises(config.Refused):
            config.stated("whatever_this_is", True, self.home / "data")


class WhenAVersionLastArrived(support.Isolated):
    """`last_updated_at` is written only by the paths that really place a program."""

    def setUp(self):
        super().setUp()
        self.data = self.home / "data"
        config.write_fresh(self.data)

    def at(self, day: int) -> datetime:
        return datetime(2026, 8, day, 14, 30, 5, tzinfo=timezone.utc)

    def test_a_fresh_configuration_has_nothing_recorded_yet(self):
        self.assertIsNone(config.read(self.data)["last_updated_at"])

    def test_recording_a_move_writes_the_moment_it_was_given(self):
        self.assertEqual("2026-08-04T14:30:05Z", config.moved(self.at(4), self.data))
        self.assertEqual("2026-08-04T14:30:05Z", config.read(self.data)["last_updated_at"])

    def test_a_later_move_replaces_the_earlier_one(self):
        config.moved(self.at(4), self.data)
        config.moved(self.at(9), self.data)
        self.assertEqual("2026-08-09T14:30:05Z", config.read(self.data)["last_updated_at"])

    def test_the_clock_is_passed_in_rather_than_read(self):
        # A moment nothing could arrive at by reading the machine's own clock, so this fails if the
        # time is taken internally rather than from the caller.
        config.moved(datetime(1999, 12, 31, 23, 59, 59, tzinfo=timezone.utc), self.data)
        self.assertEqual("1999-12-31T23:59:59Z", config.read(self.data)["last_updated_at"])

    def test_with_no_clock_given_it_uses_now(self):
        before = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        config.moved(data=self.data)
        self.assertGreaterEqual(config.read(self.data)["last_updated_at"], before)

    def test_it_is_recorded_as_a_readable_moment_in_utc(self):
        config.moved(self.at(4), self.data)
        self.assertRegex(config.read(self.data)["last_updated_at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_it_leaves_everything_else_alone(self):
        config.stated("backup_retention", 30, self.data)
        config.moved(self.at(4), self.data)
        self.assertEqual(30, config.read(self.data)["backup_retention"])

    def test_nobody_may_set_it_by_hand(self):
        self.assertNotIn("last_updated_at", config.settable())


class WritingASmallFileSafely(support.Isolated):

    def test_a_file_nobody_wrote_and_one_that_will_not_parse_are_different_answers(self):
        at = self.home / "somewhere.json"
        self.assertEqual(jsonfile.MISSING, jsonfile.read(at)[0])
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_text("{ broken")
        self.assertEqual(jsonfile.UNREADABLE, jsonfile.read(at)[0])

    def test_nothing_writes_over_a_value_it_could_not_read(self):
        at = self.home / "somewhere.json"
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_text("{ broken")
        with self.assertRaises(ValueError):
            with jsonfile.changing(at, empty={}):
                pass
        self.assertEqual("{ broken", at.read_text(), "the unreadable value was overwritten")

    def test_a_value_is_renamed_into_place_rather_than_written_in_pieces(self):
        at = self.home / "somewhere.json"
        jsonfile.write(at, {"a": 1})
        self.assertEqual((jsonfile.READ, {"a": 1}), jsonfile.read(at))
        leftovers = [one.name for one in at.parent.iterdir() if one.name.endswith(".incoming")]
        self.assertEqual([], leftovers)


class WhenSomethingElseIsChangingTheSameFile(support.Isolated):
    """A wait with an end, and a name for the thing that was waited for."""

    def setUp(self):
        super().setUp()
        self.at = self.home / "somewhere.json"
        self.at.parent.mkdir(parents=True, exist_ok=True)
        # Shortened so the ceiling can be met in milliseconds. Read inside `_taken` on every call
        # rather than bound at import, which is what makes this reachable at all.
        self.addCleanup(setattr, jsonfile, "WAITING_SECONDS", jsonfile.WAITING_SECONDS)
        jsonfile.WAITING_SECONDS = 0.1

    def held_by_something_else(self):
        """Take the lock through a second descriptor, which flock treats as another holder."""
        lock = self.at.with_name(f".{self.at.name}.lock")
        holding = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, holding)
        fcntl.flock(holding, fcntl.LOCK_EX)
        return holding

    def test_it_gives_up_and_says_so_rather_than_waiting_for_ever(self):
        # A blocking wait cannot be interrupted and names nothing while it waits, so the command
        # somebody typed simply never returns. Without the ceiling this case does not fail — it
        # hangs, which is the failure being prevented.
        self.held_by_something_else()
        began = time.monotonic()
        with self.assertRaises(jsonfile.Stuck) as refused:
            with jsonfile.changing(self.at, empty={}):
                pass
        self.assertLess(time.monotonic() - began, 5, "it waited far past its own ceiling")
        self.assertIn(str(self.at), str(refused.exception))

    def test_it_writes_nothing_when_it_could_not_have_the_file(self):
        jsonfile.write(self.at, {"a": 1})
        self.held_by_something_else()
        with self.assertRaises(jsonfile.Stuck):
            with jsonfile.changing(self.at, empty={}) as held:
                held[0] = {"a": 2}
        self.assertEqual((jsonfile.READ, {"a": 1}), jsonfile.read(self.at))

    def test_a_lock_that_comes_free_is_simply_taken(self):
        # The ordinary case, so the ceiling cannot be mistaken for a refusal to share.
        holding = self.held_by_something_else()
        fcntl.flock(holding, fcntl.LOCK_UN)
        with jsonfile.changing(self.at, empty={}) as held:
            held[0] = {"a": 3}
        self.assertEqual((jsonfile.READ, {"a": 3}), jsonfile.read(self.at))

    def test_a_command_says_it_rather_than_ending_in_a_traceback(self):
        config.write_fresh(self.home / "data")
        self.addCleanup(setattr, jsonfile, "WAITING_SECONDS", jsonfile.WAITING_SECONDS)
        jsonfile.WAITING_SECONDS = 0.1
        lock = config.where(self.home / "data")
        holding = os.open(lock.with_name(f".{lock.name}.lock"), os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, holding)
        fcntl.flock(holding, fcntl.LOCK_EX)

        code, _, err = self.rundesk("configure", "--backup-retention", "30")
        self.assertNotEqual(0, code)
        self.assertIn("configure: FAILED", err)
        self.assertIn("nothing was changed", err)


class SettingSeveralValuesAtOnce(support.Isolated):
    """Several settings are one change, because half of what was meant is a different change."""

    def setUp(self):
        super().setUp()
        self.data = self.home / "data"
        config.write_fresh(self.data)

    def test_every_value_named_is_set(self):
        config.stated_all({"backup_retention": 30, "update_time": "04:30"}, self.data)
        settled = config.read(self.data)
        self.assertEqual(30, settled["backup_retention"])
        self.assertEqual("04:30", settled["update_time"])

    def test_it_leaves_every_other_value_exactly_as_it_was(self):
        config.stated("update_enabled", False, self.data)
        config.stated_all({"backup_retention": 30}, self.data)
        self.assertFalse(config.read(self.data)["update_enabled"])

    def test_naming_a_value_rundesk_does_not_have_changes_none_of_them(self):
        with self.assertRaises(config.Refused):
            config.stated_all({"backup_retention": 30, "whatever_this_is": True}, self.data)
        self.assertEqual(7, config.read(self.data)["backup_retention"],
                         "a refused change was half applied")

    def test_they_are_written_as_one_change_and_not_one_each(self):
        # The guarantee, and the only way to see it from outside: count the writes. Set one at a
        # time, three settings are three chances to be interrupted, and what is left behind is a
        # configuration nobody typed — two of the answers somebody gave and no sign of the third.
        writes = []
        real = jsonfile.write

        def counted(where, value):
            writes.append(where)
            return real(where, value)

        self.addCleanup(setattr, jsonfile, "write", real)
        jsonfile.write = counted
        config.stated_all({"backup_retention": 30, "update_time": "04:30",
                           "update_enabled": False}, self.data)
        self.assertEqual(1, len(writes), f"three settings were written {len(writes)} times")


if __name__ == "__main__":
    unittest.main()
