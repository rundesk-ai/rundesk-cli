"""Changing what this install is configured with.

Run directly: `python3 tests/test_configure.py`
"""

import unittest

import support
from rundesk.commands import configure
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK, USAGE


class Configuring(support.Isolated):

    def setUp(self):
        super().setUp()
        config.write_fresh(paths.data())

    def settled(self, key):
        return config.read(paths.data())[key]


class WhatMayBeSet(Configuring):

    def test_every_configured_value_has_a_flag(self):
        # Generated from the configuration rather than written out, so a value a release starts
        # offering is settable the day it lands.
        code, out, err = self.rundesk("configure", "--help")
        self.assertEqual(OK, code, err)
        for key in config.settable():
            with self.subTest(key=key):
                self.assertIn(configure.as_flag(key), out)

    def test_every_flag_it_offers_really_sets_something(self):
        # The other direction: a flag on the parser that writes nothing is the failure this catches.
        for key in config.settable():
            with self.subTest(key=key):
                said = {bool: "no", int: "3", str: "05:00"}[type(config.INITIAL[key])]
                code, _, err = self.rundesk("configure", configure.as_flag(key), said)
                self.assertEqual(OK, code, err)
                self.assertNotEqual(config.INITIAL[key], self.settled(key),
                                    f"{configure.as_flag(key)} changed nothing")

    def test_how_far_the_install_has_been_carried_is_not_settable_by_hand(self):
        # Setting it would make rundesk skip or repeat a migration step.
        self.assertNotIn("migration", config.settable())
        code, _, _ = self.rundesk("configure", "--migration", "0001_whatever")
        self.assertEqual(USAGE, code, "the migration marker can be set from the command line")

    def test_a_flag_is_the_value_with_dashes(self):
        self.assertEqual("--backup-retention", configure.as_flag("backup_retention"))


class SettingAValue(Configuring):

    def test_it_sets_what_was_named(self):
        code, out, err = self.rundesk("configure", "--backup-retention", "30")
        self.assertEqual(OK, code, err)
        self.assertEqual(30, self.settled("backup_retention"))
        self.assertIn("backup_retention is now 30", out)

    def test_it_leaves_everything_else_exactly_as_it_was(self):
        self.rundesk("configure", "--backup-retention", "30")
        settled = config.read(paths.data())
        self.assertEqual(config.INITIAL["update_time"], settled["update_time"])
        self.assertEqual(config.INITIAL["update_enabled"], settled["update_enabled"])

    def test_it_sets_more_than_one_at_a_time(self):
        self.rundesk("configure", "--backup-enabled", "no", "--update-time", "04:30")
        self.assertFalse(self.settled("backup_enabled"))
        self.assertEqual("04:30", self.settled("update_time"))

    def test_a_yes_or_no_is_understood_however_it_is_written(self):
        for said in ("no", "NO", "false", "off", "0"):
            with self.subTest(said=said):
                self.rundesk("configure", "--backup-enabled", said)
                self.assertFalse(self.settled("backup_enabled"), said)
        for said in ("yes", "TRUE", "on", "1"):
            with self.subTest(said=said):
                self.rundesk("configure", "--backup-enabled", said)
                self.assertTrue(self.settled("backup_enabled"), said)

    def test_what_it_sets_survives_being_read_back_by_the_command(self):
        self.rundesk("configure", "--update-time", "23:59")
        _, out, _ = self.rundesk("configure")
        self.assertIn("23:59", out)


class AValueThatIsNotAllowed(Configuring):

    def test_a_retention_that_keeps_nothing_is_refused(self):
        code, _, err = self.rundesk("configure", "--backup-retention", "0")
        self.assertEqual(FAILED, code)
        self.assertIn("at least 1", err)
        self.assertEqual(config.INITIAL["backup_retention"], self.settled("backup_retention"))

    def test_a_retention_that_is_not_a_number_is_refused(self):
        code, _, _ = self.rundesk("configure", "--backup-retention", "lots")
        self.assertEqual(FAILED, code)
        self.assertEqual(config.INITIAL["backup_retention"], self.settled("backup_retention"))

    def test_a_yes_or_no_that_is_neither_is_refused(self):
        code, _, err = self.rundesk("configure", "--backup-enabled", "maybe")
        self.assertEqual(FAILED, code)
        self.assertIn("yes or no", err)

    def test_a_time_that_is_not_a_time_is_refused(self):
        for said in ("25:00", "3pm", "04:60", "0430", "4:5"):
            with self.subTest(said=said):
                code, _, _ = self.rundesk("configure", "--update-time", said)
                self.assertEqual(FAILED, code, f"{said} was accepted as a time")
        self.assertEqual(config.INITIAL["update_time"], self.settled("update_time"))

    def test_a_time_at_the_edges_of_the_day_is_accepted(self):
        for said in ("00:00", "23:59", "9:05"):
            with self.subTest(said=said):
                code, _, err = self.rundesk("configure", "--update-time", said)
                self.assertEqual(OK, code, err)

    def test_naming_two_values_and_getting_one_wrong_changes_neither(self):
        # Half-applied configuration leaves an install in a state nobody typed.
        code, _, err = self.rundesk(
            "configure", "--backup-retention", "30", "--update-time", "not a time")
        self.assertEqual(FAILED, code)
        self.assertEqual(config.INITIAL["backup_retention"], self.settled("backup_retention"))
        self.assertIn("nothing was changed", err)


class ShowingWhatItIs(Configuring):

    def test_with_nothing_named_it_shows_every_value(self):
        code, out, err = self.rundesk("configure")
        self.assertEqual(OK, code, err)
        for key in config.settable():
            self.assertIn(key, out)

    def test_it_shows_how_to_change_each_one(self):
        _, out, _ = self.rundesk("configure")
        self.assertIn("rundesk configure --backup-retention", out)

    def test_showing_changes_nothing(self):
        before = config.where(paths.data()).read_text()
        self.rundesk("configure")
        self.assertEqual(before, config.where(paths.data()).read_text())

    def test_a_configuration_that_cannot_be_read_is_refused_rather_than_defaulted(self):
        config.where(paths.data()).write_text("{ this is not json")
        code, _, err = self.rundesk("configure")
        self.assertEqual(FAILED, code)
        self.assertIn("cannot be read", err)


if __name__ == "__main__":
    unittest.main()
