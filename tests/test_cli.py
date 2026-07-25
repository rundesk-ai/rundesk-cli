#!/usr/bin/env python3
"""The command surface: what rundesk offers, and what it honestly refuses.

The point of this file is that the shape of the CLI is asserted rather than
described. Every verb is walked automatically, so a command added to the parser and
forgotten everywhere else is caught here rather than by whoever runs it first.

Run: python3 tests/test_cli.py
"""

from __future__ import annotations

import io
import contextlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import __version__  # noqa: E402
from rundesk_cli import cli  # noqa: E402


def run(argv: list[str], published: str | None = None) -> tuple[int, str, str]:
    """One CLI invocation, with everything it printed.

    Offline: whatever the command would ask the forge, it is told here instead. A
    test suite that reaches the network passes or fails on somebody else's uptime.
    """
    out, err = io.StringIO(), io.StringIO()
    real = cli.updater.latest_version_online
    cli.updater.latest_version_online = lambda: published
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
    finally:
        cli.updater.latest_version_online = real
    return code, out.getvalue(), err.getvalue()


def verbs() -> list[str]:
    """Every command the parser offers, read off the parser rather than restated."""
    for action in cli.build_parser()._actions:
        if isinstance(action, __import__("argparse")._SubParsersAction):
            return sorted(action.choices)
    raise AssertionError("the parser offers no commands at all")


class SurfaceTests(unittest.TestCase):
    def test_bare_command_describes_itself_and_succeeds(self):
        # Someone who types `rundesk` wants to know what it does, and has not failed.
        code, out, _ = run([])
        self.assertEqual(code, 0)
        self.assertIn("usage: rundesk", out)

    def test_every_verb_is_reachable_and_none_falls_through(self):
        # The guard on dispatch: a command registered on the parser and handled
        # nowhere would return the catch-all, which this is here to catch.
        for verb in verbs():
            with self.subTest(verb=verb):
                # Told it is current, so every verb takes its ordinary path.
                code, out, err = run([verb], published=f"v{__version__}")
                self.assertNotIn("no handler for", err, f"'{verb}' is offered but nothing handles it")
                self.assertIn(code, (0, cli.NOT_BUILT), f"'{verb}' exited {code}")

    def test_a_planned_command_says_so_and_does_not_report_success(self):
        # Exiting 0 having done nothing is a lie a script will believe.
        for verb in sorted(cli.COMING_SOON):
            with self.subTest(verb=verb):
                code, _, err = run([verb])
                self.assertEqual(code, cli.NOT_BUILT, f"'{verb}' reported success without doing anything")
                self.assertIn("coming soon", err)

    def test_a_planned_command_tolerates_the_arguments_it_will_take(self):
        # `rundesk start agent-x` must answer in our words. An unknown *flag* is
        # argparse's to reject, and rightly — that is a typo, not a planned command.
        code, _, err = run(["start", "agent-x"])
        self.assertEqual(code, cli.NOT_BUILT)
        self.assertIn("coming soon", err)

    def test_update_says_where_it_stands_rather_than_reaching_out_blindly(self):
        behind, _, _ = run(["update", "--check"], published="v99.0.0")
        current, said, _ = run(["update", "--check"], published=f"v{__version__}")
        unreachable, _, _ = run(["update", "--check"], published=None)

        self.assertEqual(behind, 0)
        self.assertEqual(current, 0)
        self.assertIn("up to date", said)
        # Not 0: "could not ask" must never read as "you are current".
        self.assertEqual(unreachable, 1)

    def test_every_verb_is_described(self):
        # A command with no help line is one nobody can discover.
        help_text = io.StringIO()
        with contextlib.redirect_stdout(help_text):
            with self.assertRaises(SystemExit):
                cli.main(["--help"])
        shown = help_text.getvalue()
        for verb in verbs():
            self.assertIn(verb, shown, f"'{verb}' is offered but never described")


class BuiltCommandTests(unittest.TestCase):
    def test_version_says_what_is_installed(self):
        code, out, _ = run(["version"])
        self.assertEqual(code, 0)
        self.assertIn(__version__, out)

    def test_version_check_reports_against_what_is_published(self):
        # No network: the updater takes its source of truth as an argument.
        code = cli.updater.run(cli.REPO_ROOT, "0.1.0", check_only=True, latest=lambda: "v9.9.9")
        self.assertEqual(code, 0)

    def test_uninstall_hands_the_job_to_the_installer(self):
        # It cannot remove itself — the command doing the removing goes with it.
        code, out, _ = run(["uninstall"])
        self.assertEqual(code, 0)
        self.assertIn("install.sh", out)
        self.assertIn("--uninstall", out)

    def test_the_planned_list_and_the_built_commands_do_not_overlap(self):
        # A command that is both "coming soon" and handled would answer twice, and
        # which answer wins would depend on the order of the checks in `main`.
        built = {"version", "update", "uninstall"}
        self.assertEqual(built & set(cli.COMING_SOON), set())
        self.assertEqual(set(verbs()), built | set(cli.COMING_SOON))


class BehindOrCurrentTests(unittest.TestCase):
    """What a person actually types to find out whether they are behind."""

    def test_version_says_what_is_installed_without_asking_anyone(self):
        # The common case, and it must work with no network at all.
        code, out, _ = run(["version"], published=None)
        self.assertEqual(code, 0, "plain `version` failed because it could not reach the forge")
        self.assertIn(__version__, out)

    def test_version_check_and_update_check_agree_on_where_this_install_stands(self):
        # Two ways in, one answer. Drifting apart is how you get told you are current by
        # one command and behind by the other.
        for argv in (["version", "--check"], ["update", "--check"]):
            with self.subTest(argv=argv):
                behind_code, behind_said, _ = run(argv, published="v99.0.0")
                self.assertEqual(behind_code, 0)
                self.assertIn("v99.0.0", behind_said)
                self.assertIn("rundesk update", behind_said, "it says you are behind, not what to do")

                current_code, current_said, _ = run(argv, published=f"v{__version__}")
                self.assertEqual(current_code, 0)
                self.assertIn("up to date", current_said)

                unknown_code, unknown_said, _ = run(argv, published=None)
                self.assertEqual(unknown_code, 1, "could-not-ask reported as success")
                self.assertNotIn("up to date", unknown_said)

    def test_check_never_moves_the_install(self):
        # --check is a question. A question that changed the install would be a trap.
        moved = []
        code = cli.updater.run(
            cli.REPO_ROOT, __version__, check_only=True,
            latest=lambda: "v99.0.0", apply=lambda root, tag: moved.append(tag) or 0,
        )
        self.assertEqual(code, 0)
        self.assertEqual(moved, [], "--check updated the install")


if __name__ == "__main__":
    unittest.main(verbosity=2)
