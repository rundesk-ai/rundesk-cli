"""The command surface, and the two verbs that answer without touching the install.

Every verb is walked **off the parser** rather than off a list written here, so an operation added to
the command is covered the day it lands rather than the day somebody remembers to add it twice.

Run directly: `python3 tests/test_cli.py`
"""

import contextlib
import io
import json
import unittest
from unittest import mock

import support
from rundesk import __version__, cli, commands
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

    def test_json_is_one_versioned_document_for_a_local_consumer(self):
        code, out, err = self.rundesk("status", "--json")

        self.assertEqual(OK, code, err)
        self.assertEqual("", err)
        said = json.loads(out)
        self.assertEqual(1, said["schema_version"])
        self.assertEqual(__version__, said["status"]["version"])
        self.assertEqual(str(self.home), said["status"]["home"])
        self.assertEqual(1, len(out.splitlines()))

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

    def test_it_still_answers_when_the_configuration_cannot_be_read(self):
        # `status` is the one command that must answer whatever is wrong — it is what somebody runs
        # *because* something is wrong. It degrades to saying so rather than failing.
        paths.data().mkdir(parents=True, exist_ok=True)
        (paths.data() / "config.json").write_text("{ not json")

        code, out, _ = self.rundesk("status")

        self.assertEqual(OK, code)
        self.assertIn("cannot be read", out)
        self.assertIn(__version__, out, "it stopped answering the question it was asked")

    def test_it_refuses_when_the_interpreter_is_too_old_to_run_here(self):
        # The one thing that makes an install look finished and be unrunnable, and the reason
        # `install` proves itself with `status` rather than with `version`.
        from rundesk.commands import status as the_status
        with mock.patch.object(the_status, "PYTHON_FLOOR", (99, 0)):
            code, out, _ = self.rundesk("status")
        self.assertEqual(FAILED, code)
        self.assertIn("python99.0 or newer", out)
        self.assertIn("fit to run", out)

    def test_a_root_that_must_not_be_used_is_refused_rather_than_worked_on(self):
        import os
        os.environ["RUNDESK_HOME"] = "/"
        code, out, err = self.rundesk("status")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("root of the filesystem", err)


class WhatEveryCommandShares(support.Isolated):
    """`failed` and `as_written` — the two things every verb in the product prints through.

    Driven directly rather than only through the verbs that use them. A helper proved only by its
    callers stops being proved the day somebody adds a caller that gets it subtly wrong, and these
    two are the reason `status` and `configure` cannot come to describe the same install differently.
    """

    def said(self, *argv):
        """What `failed` puts on each stream, and what it hands back."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = commands.failed(*argv)
        return code, out.getvalue(), err.getvalue()

    def test_a_failure_is_reported_as_one(self):
        self.assertEqual(FAILED, self.said("backups: FAILED — no")[0])

    def test_it_goes_to_the_error_stream_and_never_to_the_output(self):
        # A failure on stdout is a failure a script reads as the answer.
        _, out, err = self.said("backups: FAILED — no", "nothing was changed")
        self.assertEqual("", out)
        self.assertIn("backups: FAILED — no", err)

    def test_what_it_leaves_is_indented_under_what_went_wrong(self):
        _, _, err = self.said("backups: FAILED — no", "nothing was restored")
        self.assertEqual(["backups: FAILED — no", "        nothing was restored"],
                         err.splitlines())

    def test_it_says_every_line_it_was_given(self):
        _, _, err = self.said("x: FAILED — no", "one", "two")
        self.assertEqual(3, len(err.splitlines()))

    def test_a_failure_with_nothing_further_to_say_says_nothing_further(self):
        _, _, err = self.said("x: FAILED — no")
        self.assertEqual(["x: FAILED — no"], err.splitlines())

    def test_the_first_line_is_the_callers_own_words(self):
        # `update` says NOT APPLIED where the others say FAILED, and the difference is deliberate:
        # an update that declined to move is not a command that broke. A helper that forced the word
        # would be changing what a command means rather than how it prints.
        _, _, err = self.said("update: NOT APPLIED — nothing newer is published")
        self.assertIn("NOT APPLIED", err)
        self.assertNotIn("FAILED", err)

    def test_a_value_nothing_has_set_says_so_rather_than_printing_pythons_word(self):
        self.assertEqual("not yet", commands.as_written(None))

    def test_yes_and_no_are_how_this_product_writes_a_boolean(self):
        self.assertEqual("yes", commands.as_written(True))
        self.assertEqual("no", commands.as_written(False))

    def test_everything_else_is_written_as_it_reads(self):
        for value, wanted in ((7, "7"), ("03:00", "03:00"), (0, "0")):
            with self.subTest(value=value):
                self.assertEqual(wanted, commands.as_written(value))

    def test_a_zero_is_not_mistaken_for_a_no(self):
        # `0` is falsey and is not `False`; a check written with `if not value` would print "no" for
        # a retention of zero, which is a different setting entirely.
        self.assertEqual("0", commands.as_written(0))


class AStopIsNotACrash(support.Isolated):
    """Every long verb can be Ctrl-C'd or sent a `SIGTERM`, and both arrive as `KeyboardInterrupt`.

    Left uncaught, somebody who stopped their own turn got twenty lines of traceback ending inside
    `queue.get` — which reads as a crash, on a command that did exactly what they asked.
    """

    def test_it_is_said_in_one_line_and_never_as_a_traceback(self):
        with mock.patch.object(cli, "_the_verb", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()) as printed:
            code = cli.main(["status"], asking=lambda: None)
        self.assertEqual(FAILED, code)
        self.assertIn("status: stopped", printed.getvalue())
        self.assertNotIn("Traceback", printed.getvalue())


if __name__ == "__main__":
    unittest.main()
