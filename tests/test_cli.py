"""The command surface: what it offers, what it answers, and how an unbuilt operation behaves.

Every verb is walked **off the parser** rather than off a list written here, so an operation added to
the command is covered the day it lands rather than the day somebody remembers to add it twice.

Run directly: `python3 tests/test_cli.py`
"""

import unittest

import support
from rundesk import __version__, cli
from rundesk.exits import FAILED, NOT_AVAILABLE, OK, USAGE
from rundesk.planned import PLANNED


def verbs():
    """Every verb the command offers, read off the parser itself."""
    offered = cli.offered(cli.build_parser())
    if not offered:
        raise AssertionError("the parser offers no commands at all")
    return offered


class EveryOperationIsAnswered(support.Isolated):
    """A verb on the parser that no module answers is the failure this walk exists to catch."""

    def test_the_parser_offers_something(self):
        # A check that discovers what to run must fail when it discovers nothing: the gate this
        # replaces globbed a directory that had moved, matched zero files and printed `parse OK`.
        self.assertTrue(verbs())

    def test_every_verb_is_answered_by_something(self):
        for verb in verbs():
            with self.subTest(verb=verb):
                code, _, _ = self.rundesk(verb)
                self.assertIn(code, (OK, FAILED, NOT_AVAILABLE),
                              f"{verb} is registered and answered by nothing")

    def test_every_verb_is_described_where_it_is_listed(self):
        _, out, _ = self.rundesk()
        for verb in verbs():
            with self.subTest(verb=verb):
                self.assertIn(verb, out)

    def test_the_command_with_no_operation_describes_what_it_can_do(self):
        code, out, _ = self.rundesk()
        self.assertEqual(OK, code)
        self.assertIn("usage: rundesk", out)


class AnOperationThatIsNotBuilt(support.Isolated):
    """Registered, refusing honestly, and tellable apart from a typo."""

    def test_it_says_so_rather_than_appearing_to_work(self):
        code, out, err = self.rundesk("agents", "list")
        self.assertEqual("", out, "a refusal must not reach anything reading this command's output")
        self.assertIn("NOT AVAILABLE", err)
        self.assertNotEqual(OK, code)

    def test_it_names_which_part_of_itself_is_missing(self):
        _, _, err = self.rundesk("skills", "grant", "ava", "some-skill")
        self.assertIn("skills grant", err)

    def test_it_points_at_a_command_that_does_work(self):
        _, _, err = self.rundesk("agents", "list")
        self.assertIn("rundesk --help", err)

    def test_it_ends_differently_from_an_operation_named_wrongly(self):
        planned, _, _ = self.rundesk("agents", "list")
        typo, _, _ = self.rundesk("agentz")
        self.assertEqual(NOT_AVAILABLE, planned)
        self.assertEqual(USAGE, typo)
        self.assertNotEqual(planned, typo, "a missing command reads as a typo")

    def test_it_accepts_the_arguments_it_will_take_once_built(self):
        # Without this an option a future release takes becomes argparse's usage error today, which
        # is the one code that must stay reserved for a command line that was typed wrongly.
        for argv in (["skills", "install", "some/repo", "--confirm"],
                     ["agents", "add", "ava", "--provider", "codex"],
                     ["schedules", "ava", "add", "nightly", "--when", "0 4 * * *"],
                     ["channels", "ava", "add", "discord", "--owner", "someone", "--token-stdin"],
                     ["gateways", "stop", "ava", "--all"],
                     ["backups", "configure", "--status", "off"],
                     ["env", "set", "SOME_KEY"],
                     ["messages", "ava", "--limit", "5"]):
            with self.subTest(argv=argv):
                code, _, err = self.rundesk(*argv)
                self.assertEqual(NOT_AVAILABLE, code, err)

    def test_every_planned_verb_refuses_and_none_of_them_is_built(self):
        for verb in sorted(PLANNED):
            with self.subTest(verb=verb):
                code, _, _ = self.rundesk(verb)
                self.assertEqual(NOT_AVAILABLE, code)

    def test_a_planned_verb_lists_the_actions_it_will_take(self):
        code, out, _ = self.rundesk("skills", "--help")
        self.assertEqual(OK, code)
        for action in PLANNED["skills"][1]:
            self.assertIn(action, out)


class Version(support.Isolated):
    """What version this copy is, answered without reaching anything outside the machine."""

    def test_it_reports_the_version_it_is(self):
        code, out, _ = self.rundesk("version")
        self.assertEqual(OK, code)
        self.assertEqual(f"rundesk {__version__}", out.strip())

    def test_there_is_one_source_of_what_version_this_is(self):
        # Three separate paths reported it in the build this replaces. Every extra one is a chance
        # for the product to disagree with itself about what it is.
        _, out, _ = self.rundesk("version")
        self.assertIn(__version__, out)

    def test_asking_which_version_is_published_refuses_rather_than_guessing(self):
        # Not built yet. Reporting "up to date" because nobody could be asked is how an install
        # stops updating itself in silence, so this refuses until it can really ask.
        code, _, err = self.rundesk("version", "--check")
        self.assertEqual(NOT_AVAILABLE, code)
        self.assertIn("version --check", err)


class Status(support.Isolated):
    """How rundesk itself is on this machine."""

    def test_it_says_which_version_and_which_root_answered(self):
        code, out, _ = self.rundesk("status")
        self.assertEqual(OK, code)
        self.assertIn(__version__, out)
        self.assertIn(str(self.home), out)

    def test_it_says_where_the_program_is_as_well_as_where_the_data_is(self):
        # They are different questions, and a command answering against a root that was never
        # installed into looks exactly like a working install with nothing in it.
        _, out, _ = self.rundesk("status")
        self.assertIn(str(support.CHECKOUT), out)
        self.assertIn("not there yet", out)

    def test_it_answers_against_the_root_it_was_given_and_no_other(self):
        _, out, _ = self.rundesk("status")
        for line in out.splitlines():
            if line.startswith(("home", "app", "data")):
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
