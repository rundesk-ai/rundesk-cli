"""The command surface, and the two verbs that answer without touching the install.

Every verb is walked **off the parser** rather than off a list written here, so an operation added to
the command is covered the day it lands rather than the day somebody remembers to add it twice.

Run directly: `python3 tests/test_cli.py`
"""

import unittest

import support
from rundesk import __version__, cli
from rundesk.core import paths
from rundesk.exits import FAILED, OK, USAGE
from rundesk.lifecycle import release


def verbs():
    """Every verb the command offers, read off the parser itself."""
    offered = cli.offered(cli.build_parser())
    if not offered:
        raise AssertionError("the parser offers no commands at all")
    return offered


class EveryOperationIsBuilt(support.Isolated):
    """A verb on the parser that no module answers is the failure this walk exists to catch."""

    def test_the_parser_offers_something(self):
        # A check that discovers what to run must fail when it discovers nothing.
        self.assertTrue(verbs())

    def test_every_verb_is_answered_by_something(self):
        # `install`, `update` and `uninstall` act on the machine, so they are exercised in their own
        # suites; here every verb is only proved to reach a handler rather than raising.
        for verb in verbs():
            with self.subTest(verb=verb):
                code, _, _ = self.rundesk(verb, "--help")
                self.assertEqual(OK, code)

    def test_every_verb_is_described_where_it_is_listed(self):
        _, out, _ = self.rundesk()
        for verb in verbs():
            with self.subTest(verb=verb):
                self.assertIn(verb, out)

    def test_the_command_with_no_operation_describes_what_it_can_do(self):
        code, out, _ = self.rundesk()
        self.assertEqual(OK, code)
        self.assertIn("usage: rundesk", out)

    def test_nothing_is_offered_that_is_not_built(self):
        # There is no "coming soon" surface: a verb rundesk cannot perform is a verb it does not
        # have, so no operation may answer by refusing on the grounds of not being written.
        for verb in verbs():
            with self.subTest(verb=verb):
                _, out, err = self.rundesk(verb, "--help")
                self.assertNotIn("NOT AVAILABLE", out + err)
                self.assertNotIn("coming soon", out + err)

    def test_a_verb_named_wrongly_is_a_usage_error(self):
        code, _, _ = self.rundesk("statuz")
        self.assertEqual(USAGE, code)


class Version(support.Isolated):
    """What version this copy is, and where it stands against what is published."""

    def test_it_reports_the_version_it_is(self):
        code, out, _ = support.run_with(["version"], asking=lambda: (f"v{__version__}", None))
        self.assertEqual(OK, code)
        self.assertIn(f"rundesk {__version__}", out)

    def test_it_takes_no_flags(self):
        code, _, _ = self.rundesk("version", "--check")
        self.assertEqual(USAGE, code, "version grew a flag it is not meant to have")

    def test_it_checks_whether_it_is_out_of_date_without_being_asked(self):
        _, out, _ = support.run_with(["version"], asking=lambda: ("v99.0.0", None))
        self.assertIn("OUT OF DATE", out)
        self.assertIn("rundesk update", out)

    def test_being_current_is_reported_as_such(self):
        _, out, _ = support.run_with(["version"], asking=lambda: (f"v{__version__}", None))
        self.assertIn("UP TO DATE", out)

    def test_being_unable_to_ask_is_never_reported_as_being_current(self):
        # An install that reports UP TO DATE because GitHub timed out has silently stopped updating
        # itself, and nobody finds out until something else breaks.
        code, out, err = support.run_with(["version"], asking=lambda: (None, release.UNREACHABLE))
        self.assertIn("UNKNOWN", err)
        self.assertNotIn("UP TO DATE", out + err)
        # The version itself was still answered, from the machine, so the command did its job.
        self.assertEqual(OK, code)
        self.assertIn(__version__, out)

    def test_nothing_published_is_told_apart_from_being_unable_to_ask(self):
        _, _, unreachable = support.run_with(["version"], asking=lambda: (None, release.UNREACHABLE))
        _, _, nothing = support.run_with(["version"],
                                         asking=lambda: (None, release.NOTHING_PUBLISHED))
        self.assertNotEqual(unreachable, nothing)
        self.assertIn("NO RELEASES", nothing)

    def test_a_published_version_that_cannot_be_read_is_never_newer(self):
        code, out, _ = support.run_with(["version"], asking=lambda: ("not-a-version", None))
        self.assertNotIn("OUT OF DATE", out)
        self.assertEqual(OK, code)


class Status(support.Isolated):
    """How rundesk itself is on this machine."""

    def test_it_says_which_version_and_which_root_answered(self):
        code, out, _ = self.rundesk("status")
        self.assertEqual(OK, code)
        self.assertIn(__version__, out)
        self.assertIn(str(self.home), out)

    def test_it_says_where_the_program_is_as_well_as_where_the_data_is(self):
        _, out, _ = self.rundesk("status")
        self.assertIn(str(support.CHECKOUT), out)

    def test_it_tells_a_checkout_from_an_install(self):
        _, out, _ = self.rundesk("status")
        self.assertIn("a checkout", out)

    def test_it_shows_every_value_this_install_is_configured_with(self):
        from rundesk.core import config
        config.write_fresh(paths.data())
        _, out, _ = self.rundesk("status")
        for key in config.INITIAL:
            self.assertIn(key, out, f"status does not show {key}")

    def test_it_shows_a_configured_value_the_owner_changed(self):
        from rundesk.core import config
        config.write_fresh(paths.data())
        config.stated("backup_retention", 42, paths.data())
        _, out, _ = self.rundesk("status")
        self.assertIn("42", out)

    def test_it_says_how_far_the_install_has_been_carried(self):
        _, out, _ = self.rundesk("status")
        self.assertIn("migration", out)

    def test_it_takes_no_flags(self):
        code, _, _ = self.rundesk("status", "--verbose")
        self.assertEqual(USAGE, code, "status grew a flag it is not meant to have")

    def test_it_answers_against_the_root_it_was_given_and_no_other(self):
        _, out, _ = self.rundesk("status")
        for line in out.splitlines():
            if line.startswith(("home", "data", "backups")):
                self.assertIn(str(self.home), line)

    def test_a_root_that_must_not_be_used_is_refused_rather_than_worked_on(self):
        import os
        os.environ["RUNDESK_HOME"] = "/"
        code, out, err = self.rundesk("status")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("root of the filesystem", err)


if __name__ == "__main__":
    unittest.main()
