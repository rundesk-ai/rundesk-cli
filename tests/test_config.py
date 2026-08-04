"""Install-wide configuration, and how far this install has been carried.

Run directly: `python3 tests/test_config.py`
"""

import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
