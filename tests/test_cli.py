#!/usr/bin/env python3
"""The command surface: what rundesk offers, and what it honestly refuses.

The point of this file is that the shape of the CLI is asserted rather than
described. Every verb is walked automatically, so a command added to the parser and
forgotten everywhere else is caught here rather than by whoever runs it first.

Run: python3 tests/test_cli.py
"""

from __future__ import annotations

import argparse
import io
import contextlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import __version__  # noqa: E402
from rundesk_cli import cli  # noqa: E402


#: How long the command waits on a gateway to appear or to go. Real seconds in the wild,
#: and nothing worth spending here: what these cases assert is that it waits and then
#: answers honestly, never the duration. Set for the whole file rather than per case,
#: because the ones that spend the whole wait are exactly the ones nobody remembers to
#: turn down — a gateway that never comes up has no earlier moment to finish at.
_REAL_PATIENCE = (cli.START_PATIENCE, cli.CYCLE_PATIENCE, cli.LOOK_AGAIN_SECONDS)

#: The real removal, put back when the file is done with.
_REAL_REMOVAL = cli._remove_this_install


def _never_the_real_installer(installer, asked):
    """What `uninstall` reaches for, for the whole of this file — and never the real one.

    `uninstall` removes rundesk now, and the surface cases below walk *every* verb. So the
    case proving each verb is wired ran the real removal and took the developer's install
    with it: gateways stopped, launchd jobs gone, run state deleted. Nothing failed and
    nothing was said, because removing rundesk successfully is exactly what that command
    is for — which is why this is replaced for the whole file rather than in the cases
    that happen to think of it.

    Put back in `tearDownModule`, so the module is left as it was found.
    """
    _asked_of_the_installer.append(asked)
    return 0


#: What the stand-in above was asked for, in the order it was asked.
_asked_of_the_installer: list = []


def setUpModule():
    cli._remove_this_install = _never_the_real_installer
    # Both turned down together. Turning the patience down alone left a wait that had room
    # for one look and a fraction of a second's margin on the second — so a case proving a
    # cycle waits passed on a quick machine and reported a failure on a loaded one.
    cli.START_PATIENCE, cli.CYCLE_PATIENCE, cli.LOOK_AGAIN_SECONDS = 0.3, 0.3, 0.005


def tearDownModule():
    cli._remove_this_install = _REAL_REMOVAL
    cli.START_PATIENCE, cli.CYCLE_PATIENCE, cli.LOOK_AGAIN_SECONDS = _REAL_PATIENCE
from rundesk_cli import agent as real_agent  # noqa: E402
from rundesk_cli import channel  # noqa: E402
from rundesk_cli import gateway as real_gateway  # noqa: E402


def run(argv: list[str], published: str | None = None) -> tuple[int, str, str]:
    """One CLI invocation, with everything it printed.

    Offline: whatever the command would ask the forge, it is told here instead. A
    test suite that reaches the network passes or fails on somebody else's uptime.

    And no gateway, for the same reason one layer along: the surface cases below walk
    *every* verb, and `serve` runs until it is asked to stop — against a real gateway
    that is a suite that never finishes rather than one that fails.
    """
    out, err = io.StringIO(), io.StringIO()
    real = cli.updater.latest_version_online
    # Both halves, the way the real look-up answers: which kind of nothing it was
    # is part of the answer rather than something left behind for the caller.
    cli.updater.latest_version_online = lambda: (
        published, None if published else cli.updater.UNREACHABLE)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(argv, gateways=FakeGateways(), machine=FakeMachine(),
                                agents=FakeAgents())
            except SystemExit as usage:
                # What a shell sees, which is the subject of several cases here: argparse
                # refuses a usage error by exiting rather than returning, and a test that
                # let that escape could not say what code the caller was left with.
                code = usage.code if isinstance(usage.code, int) else 1
    finally:
        cli.updater.latest_version_online = real
    return code, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def taking_the_installer(instead):
    """Put something else in the place `uninstall` reaches for the installer.

    Never the real one: proving that this command runs the removal by running the removal
    would stop the gateways of whoever ran the suite, and delete their install.
    """
    was = cli._remove_this_install
    cli._remove_this_install = instead
    try:
        yield
    finally:
        cli._remove_this_install = was


def _offered(parser) -> dict:
    """What this parser offers under it, by name — or an empty mapping if nothing."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def _actions_of(parser) -> list[str]:
    """Every action this verb offers, however it happens to offer them.

    Two shapes, for one reason. A built verb naming its gateway with an option can use
    sub-parsers; a planned one naming its agent first cannot, because a sub-parser is
    itself a positional and would take `ava` in `runs ava show` for an action. Read off
    the parser either way, so neither shape needs a hand-kept list beside it.
    """
    under = sorted(_offered(parser))
    if under:
        return under
    for action in parser._actions:
        if action.dest == "act" and action.choices:
            return sorted(action.choices)
    return []


def verbs() -> list[str]:
    """Every command the parser offers, read off the parser rather than restated."""
    offered = _offered(cli.build_parser())
    if not offered:
        raise AssertionError("the parser offers no commands at all")
    return sorted(offered)


def operations() -> list[list[str]]:
    """Every operation the command offers, as the words a person types for it.

    A verb, and each action under a verb that has them. Walked off the parser for the
    same reason `verbs` is: a hand-kept copy of this list is one that stops covering the
    surface the day somebody adds to it, and the cases below are the only thing standing
    between a registered operation and one that answers nothing.
    """
    found = []
    for verb, parser in sorted(_offered(cli.build_parser()).items()):
        found.append([verb])
        found += [[verb, act] for act in _actions_of(parser)]
    return found


def planned() -> list[list[str]]:
    """Every operation that is planned and not built, as a person types it.

    An action is typed after the agent it is about, which is what a person types and so
    what these cases send: `runs <agent> show`, never `runs show`.
    """
    words = []
    for verb, parser in sorted(_offered(cli.build_parser()).items()):
        if verb not in cli.PLANNED:
            continue
        whose = ["an-agent"] if verb in cli.WHOSE else []
        words.append([verb] + whose)
        words += [[verb] + whose + [act] for act in _actions_of(parser)]
    return words


def planned_leaves() -> list[list[str]]:
    """The planned operations with nothing further expected after them.

    Those are the ones with arguments of their own to tolerate. A verb offering actions
    expects one next and nothing else, so `runs ava tomorrow` is a usage error and always
    will be — found by asking which of these no other one continues, rather than by a
    second list that would stop agreeing with the first.
    """
    every = planned()
    return [words for words in every
            if not any(other[:len(words)] == words and other != words for other in every)]


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
                # A verb whose next word says whose is a usage error without one, which is
                # the surface working rather than a verb nothing handles. Typed again with
                # a name, so what is asserted below is still that it reached a handler.
                if code == 2:
                    code, out, err = run([verb, "an-agent"], published=f"v{__version__}")
                self.assertNotIn("no handler for", err, f"'{verb}' is offered but nothing handles it")
                # 1 is allowed: a built verb given nothing to work on may honestly fail.
                # What must never happen is falling through to the catch-all above.
                self.assertIn(code, (0, 1, cli.NOT_AVAILABLE), f"'{verb}' exited {code}")

    def test_every_operation_is_reachable_including_the_ones_under_a_verb(self):
        """R-CMD-6 — an action registered under a verb and answered nowhere falls through
        exactly as a verb does, and there are now more actions than verbs.

        A built action may honestly refuse what it was given nothing to work on, so the
        claim here is only that nothing reaches the catch-all in `main`: an operation the
        parser offers and nothing answers.
        """
        for words in operations():
            with self.subTest(operation=" ".join(words)):
                _, _, err = run(words, published=f"v{__version__}")
                self.assertNotIn("no handler for", err,
                                 f"'{' '.join(words)}' is offered but nothing handles it")

    def test_a_planned_command_says_so_and_does_not_report_success(self):
        # Exiting 0 having done nothing is a lie a script will believe.
        for words in planned():
            with self.subTest(operation=" ".join(words)):
                code, _, err = run(words)
                self.assertEqual(code, cli.NOT_AVAILABLE,
                                 f"'{' '.join(words)}' reported success without doing anything")
                self.assertIn("NOT AVAILABLE", err)

    def test_a_planned_command_says_which_of_it_is_not_there(self):
        """R-CMD-4 — `agents` and `agents show` are different things to want. Told only
        that `agents` is planned, a reader takes the whole noun to be missing rather than
        one thing about it."""
        _, _, err = run(["runs", "ava", "show", "7"])
        self.assertIn("runs show", err)

    def test_a_planned_command_names_something_that_does_work(self):
        """R-CMD-4 — a refusal that leaves somebody with nowhere to go is half a message."""
        for words in planned():
            with self.subTest(operation=" ".join(words)):
                _, _, err = run(words)
                self.assertIn("rundesk --help", err)

    def test_a_planned_command_tolerates_the_arguments_it_will_take(self):
        """R-CMD-7 — `rundesk run agent-x "do a thing"` must answer in our words. An
        unknown *flag* is argparse's to reject, and rightly — that is a typo, not a
        planned command."""
        for words in planned_leaves():
            with self.subTest(operation=" ".join(words)):
                code, _, err = run(words + ["agent-x", "do a thing"])
                self.assertEqual(code, cli.NOT_AVAILABLE)
                self.assertIn("NOT AVAILABLE", err)

    def test_every_operation_the_reference_lists_is_answered_as_it_is_typed(self):
        """R-CMD-7 — read off the reference and typed exactly as written, options and all.

        The forms were only ever exercised as bare verbs, so a planned one given the
        arguments it will eventually take fell through to argparse: `channels ava add ops
        --kind discord`, listed in `CLI.md` in those words, ended on the usage code. That
        is the one thing a script has to be able to tell our refusal from, because the two
        want opposite things done about them.
        """
        listed = pathlib.Path(cli.REPO_ROOT) / "CLI.md"
        forms = [line.split("   ")[0].strip()
                 for line in listed.read_text().splitlines()
                 if line.startswith("rundesk ")]
        self.assertTrue(forms, "the reference lists no operations at all")
        for form in forms:
            # `<agent>` and friends stand for a word. A `[...]` group is optional and left
            # out whole — dropping only the token it starts with leaves the rest of the
            # group behind and types something nobody would.
            bare = re.sub(r"\[[^\]]*\]", " ", form)
            typed = ["an-agent" if word.startswith("<") else word
                     for word in bare.split()[1:]]
            if "--" in typed:                       # what follows is a program to run
                typed = typed[:typed.index("--")] + ["--", "/bin/echo"]
            with self.subTest(form=form):
                code, out, err = run(typed, published=f"v{__version__}")
                self.assertNotIn("invalid choice", err, f"'{form}' is listed and not offered")
                self.assertNotIn("unrecognized arguments", err,
                                 f"'{form}' is listed and refused by argparse rather than by us")
                self.assertIn(code, (0, 1, cli.NOT_AVAILABLE), f"'{form}' exited {code}")

    def test_a_command_that_is_not_there_is_told_apart_from_one_typed_wrong(self):
        """R-CMD-5, R-CMD-8 — two situations that shared one exit code, and want opposite
        things done about them: wait for the release, or read the help."""
        planned_code, _, _ = run(["usage"])
        with self.assertRaises(SystemExit) as usage:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                cli.main(["definitely-not-a-command"])
        self.assertEqual(planned_code, cli.NOT_AVAILABLE)
        self.assertNotEqual(planned_code, usage.exception.code,
                            "a command this rundesk lacks exits the same way a typo does")

    def test_update_says_where_it_stands_rather_than_reaching_out_blindly(self):
        behind, _, _ = run(["update", "--check"], published="v99.0.0")
        current, said, _ = run(["update", "--check"], published=f"v{__version__}")
        unreachable, _, _ = run(["update", "--check"], published=None)

        self.assertEqual(behind, 0)
        self.assertEqual(current, 0)
        self.assertIn("UP TO DATE", said)
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
            if verb in cli.HIDDEN:
                # Accepted and not offered, on purpose and in one place. Asserted rather
                # than skipped, so hiding a verb stays a decision somebody made.
                self.assertNotIn(f"    {verb} ", shown, f"'{verb}' is hidden and shown anyway")
                continue
            self.assertIn(verb, shown, f"'{verb}' is offered but never described")

    def test_what_is_hidden_is_still_accepted(self):
        """R-CMD-5 — `serve` is what every launchd job already on disk invokes. Taking it
        off the surface must not take it out of the command, or every job written before
        this stops working."""
        for verb in cli.HIDDEN:
            with self.subTest(verb=verb):
                self.assertIn(verb, verbs(), f"'{verb}' is hidden by being gone")


class BuiltCommandTests(unittest.TestCase):
    def test_version_says_what_is_installed(self):
        code, out, _ = run(["version"])
        self.assertEqual(code, 0)
        self.assertIn(__version__, out)

    def test_version_check_reports_against_what_is_published(self):
        # No network: the updater takes its source of truth as an argument.
        code = cli.updater.run(cli.REPO_ROOT, "0.1.0", check_only=True, latest=lambda: ("v9.9.9", None))
        self.assertEqual(code, 0)

    def test_no_case_in_this_file_can_reach_the_real_removal(self):
        """R-RM-1 — the guard on every other case here. Walking every verb dispatches
        `uninstall`, and once that removes rundesk rather than describing it, the case
        proving each verb is wired removed the developer's install: gateways stopped,
        launchd jobs gone. It passed, because a successful removal is what it does."""
        self.assertIsNot(cli._remove_this_install, _REAL_REMOVAL,
                         "this file can reach the real uninstall")

    def test_uninstall_removes_rundesk_rather_than_explaining_how_to(self):
        """R-RM-1 — it printed instructions and exited zero, so a script reading the code
        was told the uninstall had run when nothing had been removed at all."""
        asked = []
        with taking_the_installer(lambda installer, args: asked.append(args) or 0):
            code, out, _ = run(["uninstall"])
        self.assertEqual(0, code, out)
        self.assertEqual([["--uninstall"]], asked, "it did not run the removal")

    def test_uninstall_passes_a_purge_through_rather_than_deciding_for_you(self):
        """R-RM-10 — what an agent wrote is the owner's, and taking it is their call."""
        asked = []
        with taking_the_installer(lambda installer, args: asked.append(args) or 0):
            run(["uninstall", "--purge"])
        self.assertEqual([["--uninstall", "--purge"]], asked)

    def test_uninstall_that_removed_nothing_says_so_and_fails(self):
        """R-RM-1 — exiting zero after a removal that did not happen is the failure this
        product is most careful about everywhere else."""
        with taking_the_installer(lambda installer, args: 3):
            code, _, err = run(["uninstall"])
        self.assertEqual(1, code, "a failed uninstall reported success")
        self.assertIn("FAILED", err)

    def test_uninstall_with_no_installer_says_where_to_get_one(self):
        """R-RM-1 — removing rundesk is exactly when a broken install has to be removable,
        and being told only that it is broken leaves a reader where they started."""
        def gone(installer, args):
            raise AssertionError("it ran an installer that is not there")
        with taking_the_installer(gone):
            was = cli.REPO_ROOT
            cli.REPO_ROOT = pathlib.Path("/nowhere-at-all")
            try:
                code, _, err = run(["uninstall"])
            finally:
                cli.REPO_ROOT = was
        self.assertEqual(1, code)
        self.assertIn("curl", err, "it failed and never said how to remove it anyway")

    def test_the_planned_list_and_the_built_commands_do_not_overlap(self):
        # A command that is both "coming soon" and handled would answer twice, and
        # which answer wins would depend on the order of the checks in `main`.
        built = {"version", "update", "uninstall", "add", "ask", "doctor", "agents",
                 "serve", "start", "stop", "remove", "restart", "status", "logs", "schedules",
                 "channels"}
        self.assertEqual(built & set(cli.PLANNED), set())
        self.assertEqual(set(verbs()), built | set(cli.PLANNED))


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
                self.assertIn("UP TO DATE", current_said)

                unknown_code, unknown_said, _ = run(argv, published=None)
                self.assertEqual(unknown_code, 1, "could-not-ask reported as success")
                self.assertNotIn("UP TO DATE", unknown_said)

    def test_check_never_moves_the_install(self):
        # --check is a question. A question that changed the install would be a trap.
        moved = []
        code = cli.updater.run(
            cli.REPO_ROOT, __version__, check_only=True,
            latest=lambda: ("v99.0.0", None), apply=lambda root, tag: moved.append(tag) or 0,
        )
        self.assertEqual(code, 0)
        self.assertEqual(moved, [], "--check updated the install")

    def test_an_update_cannot_be_pointed_at_a_version_of_your_choosing(self):
        # There is one place to be: the newest published release. Holding at a version, or
        # going back to an older one, is deliberately not offered — an install that can sit
        # anywhere is a set of installs nobody can reason about.
        for argv in (["update", "--to", "0.1.0"], ["update", "0.1.0"], ["update", "--previous"]):
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as exited:
                    cli.main(argv)
                self.assertNotEqual(exited.exception.code, 0, f"{argv} was accepted")

        # And nothing but --check is offered, so there is no version to name in the first place.
        offered = {a for p in cli.build_parser()._subparsers._group_actions
                   for name, sub in p.choices.items() if name == "update"
                   for a in sum([list(x.option_strings) for x in sub._actions], [])}
        self.assertEqual(offered - {"-h", "--help"}, {"--check"}, "update offers a way to choose a version")


class FakeGateways:
    """The gateway module, as far as the command line is concerned.

    The command line takes what it acts on as an argument, so every case below runs with
    no gateway, no lock and no process anywhere near it.
    """

    DEFAULT_NAME = "gateway"

    # What a gateway may be called is one rule with one answer, so the stand-in borrows
    # it rather than keeping a second copy that can drift from the real one.
    checked = staticmethod(real_gateway.checked)
    NotAName = real_gateway.NotAName
    Unreadable = real_gateway.Unreadable
    # The words a reader is shown are the module's own, not a second copy: a stand-in
    # spelling an outcome differently would let the surface and the store disagree with
    # nothing to catch it.
    STARTED = real_gateway.STARTED
    INTERRUPTED = real_gateway.INTERRUPTED
    GATEWAY_LOG = real_gateway.GATEWAY_LOG
    MACHINE_LOG = real_gateway.MACHINE_LOG
    EVERY_LOG = real_gateway.EVERY_LOG
    LOG_SOURCES = real_gateway.LOG_SOURCES

    class AlreadyRunning(Exception):
        pass

    class Unfit(Exception):
        pass

    class Standing:
        def __init__(self, name, running=False, pid=None, version=None, stale=False,
                     started=None):
            self.name, self.running, self.pid = name, running, pid
            self.version, self.stale, self.started = version, stale, started

    def __init__(self, standing=(), working=None, refuses=None, written=None,
                 stops_after=None, starts_after=None, becomes=None,
                 schedules=None, ran_schedules=None, unreadable=(),
                 interrupted=None, unloggable=None):
        #: What each gateway never got to finish. The store has existed since work could
        #: be interrupted and had no reader at all, so a stand-in for it is new here.
        self._interrupted = dict(interrupted or {})
        #: Why a log line could not be written, for the case that proves a mutation whose
        #: history failed does not report a plain success.
        self._unloggable = unloggable
        #: Gateways whose schedules file is there and cannot be read. Every way in refuses
        #: alike, because the command surface turned that into "there is nothing there" on
        #: all three of them.
        self._unreadable = set(unreadable)
        self._standing = list(standing)
        self._stops_after = stops_after
        self._starts_after = starts_after
        #: What `standing` reports, call by call — the last entry repeating. Cycling asks
        #: several times over (is it gone? is it back?), and a single flag cannot say
        #: "running, then stopped, then running again".
        self._becomes = list(becomes) if becomes else None
        self._asked = 0
        self._written_schedules = dict(schedules or {})
        self._ran_schedules = dict(ran_schedules or {})
        self._working = working or {}
        self._refuses = refuses
        self._written = written
        self.served = []
        #: What `remove` asked to be taken away, and whether it asked for the history too.
        self.forgotten = []
        #: Which directory each question about a gateway named. An agent's gateway keeps
        #: things in the agent's own, and a name with no agent keeps them where it always
        #: did — a surface that stopped saying which would send both to one place.
        self.asked_where = []

    def every(self):
        return list(self._standing)

    def standing(self, name, where=None):
        self.asked_where.append(where)
        if self._becomes is not None:
            running = self._becomes[min(self._asked, len(self._becomes) - 1)]
            self._asked += 1
            return self.Standing(name, running=running, pid=4242)
        if self._stops_after is not None:
            self._asked += 1
            return self.Standing(name, running=self._asked <= self._stops_after, pid=4242)
        if self._starts_after is not None:
            self._asked += 1
            return self.Standing(name, running=self._asked > self._starts_after, pid=4242)
        for it in self._standing:
            if it.name == name:
                return it
        return self.Standing(name)

    def what_is_running(self, name, where=None):
        self.asked_where.append(where)
        return self._working.get(name, [])

    def forget(self, name, where=None, schedules=None, logs=None, history=False):
        self.forgotten.append((name, history))
        self.asked_where.append(where)
        return [f"{name}.json"] + ([f"{name}.log"] if history else [])

    def _still_readable(self, name):
        if name in self._unreadable:
            raise self.Unreadable(f"{name}.json could not be read as schedules")

    def scheduled(self, name, where=None):
        from rundesk_cli import schedule
        self._still_readable(name)
        return schedule.read(self._written_schedules.get(name, []))

    def written_schedules(self, name, where=None):
        self._still_readable(name)
        return list(self._written_schedules.get(name, []))

    @contextlib.contextmanager
    def changing_schedules(self, name, where=None):
        """Read, change, write back — the shape the real one holds a lock across."""
        self._still_readable(name)
        keeping = list(self._written_schedules.get(name, []))
        yield keeping
        self._written_schedules[name] = keeping

    def what_was_scheduled(self, name, where=None):
        return self._ran_schedules.get(name, {})

    def what_was_interrupted(self, name, where=None):
        return dict(self._interrupted.get(name, {}))

    def remembered(self, where=None):
        return sorted(self._interrupted)

    def note(self, name, said, logs=None):
        # Never the real home: without somewhere of its own to write, a stand-in that
        # fell back to the default would put test lines in the owner's own logs.
        assert self._written is not None, "this case writes a log line and was given nowhere to put it"
        if self._unloggable is not None:
            return self._unloggable
        from rundesk_cli import gateway as real
        return real.note(name, said, self._written.parent)

    def log_sources(self, name, logs=None, source=real_gateway.EVERY_LOG):
        """Which files hold what this gateway said — the real rule, over the scratch
        directory this stand-in was given, so a case cannot reach the owner's own."""
        if self._written is None:
            return []
        return real_gateway.log_sources(name, self._written.parent, source)

    def fitness(self, root=None):
        return None

    def home(self):
        # Never the real one: a case that reached the machine's own run directory would be
        # reading whatever the developer happens to have.
        assert self._written is not None, "this case asked where gateways keep things"
        return self._written.parent

    def log_path(self, name, logs=None):
        return self._written if self._written is not None else pathlib.Path("/nowhere/x.log")

    def Gateway(self, name, where=None, logs=None, schedules=None, reachable=()):
        gateways = self

        class One:
            async def serve(inner):
                if gateways._refuses:
                    raise gateways._refuses
                gateways.served.append(name)
                return 0

        return One()


class FakeAgents:
    """The agent module, as far as the command line is concerned.

    Nothing here touches a disk: what an agent's home actually holds and where it stands is
    `tests/test_agent.py`'s, and what the surface does about it is this file's. The two
    rules that decide whether a name is usable are borrowed rather than copied, because a
    second answer to "may this be an agent" is one that drifts from the real one.
    """

    checked = staticmethod(real_agent.checked)
    NotAnAgentName = real_agent.NotAnAgentName
    Where = real_agent.Where

    def __init__(self, made=(), wrote=(), complaints=None, at=None):
        #: A real directory to resolve into, for the cases that write something. Without
        #: one every path here is under `/nowhere`, which is what keeps a case that only
        #: reads from ever touching a disk.
        self._at = pathlib.Path(at) if at else pathlib.Path("/nowhere/agents")
        #: What a gateway would be handed to hold open, and what could not be resolved.
        self._reachable: list = []
        self._unrunnable: list = []
        #: The agents that exist, and the directories each resolves.
        self._made = list(made)
        #: What a gateway of this name wrote before there were agents to own it.
        self._wrote = list(wrote)
        self._complaints = dict(complaints or {})
        self._chosen: dict = {}
        self.asked_runnable = None
        #: What was made, adopted and taken away, in the order it was asked for.
        self.added, self.adopted, self.forgotten = [], [], []

    def exists(self, name):
        return name in self._made

    def known(self):
        return sorted(self._made)

    def home(self, name):
        return self._at / name / "home"

    def resolved(self, name):
        if name not in self._made:
            return self.Where(None, None, None)
        at = self._at / name
        return self.Where(at / "run", at / "logs", at / "schedules")

    def channel_home(self, name, channel):
        # The real one runs the name past `gateway.checked` before building a path from
        # it. A stand-in that skipped that would let a case prove a safety property the
        # command does not actually have.
        return self._at / name / "channels" / real_gateway.checked(channel)

    def reachable(self, name, where=None, carry=None):
        return list(self._reachable)

    def unrunnable_channels(self, name, where=None):
        return list(self._unrunnable)

    def standing_before(self, name):
        return [pathlib.Path(f"/nowhere/{one}") for one in self._wrote] if name in ("gateway",) else []

    def add(self, name):
        self.added.append(name)
        made = [] if name in self._made else ["AGENTS.md", "home/"]
        if name not in self._made:
            self._made.append(name)
        return made

    def adopt(self, name):
        self.adopted.append(name)
        return list(self._wrote)

    def forget(self, name, history=False):
        self.forgotten.append((name, history))
        if name in self._made:
            self._made.remove(name)
        return ["home/"]

    def agents_home(self):
        return pathlib.Path("/nowhere/agents")

    def paths(self, name):
        at = self._at / name
        return {"agent": at, "home": at / "home", "workspace": at / "home" / "workspace",
                "run": at / "run", "logs": at / "logs", "schedules": at / "schedules"}

    def diagnosed(self, name, runnable=None):
        # Asked exactly as the real one is, so a check that is passed in is a check this
        # fake can be given — and one that stopped being passed would show up here.
        self.asked_runnable = runnable
        return self._complaints.get(name, [])

    def chosen(self, name):
        return self._chosen.get(name, {})

    def remember(self, name, provider=None, model=None, settings=None):
        keeping = self._chosen.setdefault(name, {})
        for what, value in (("provider", provider), ("model", model), ("settings", settings)):
            if value is not None:
                keeping[what] = value
        return keeping


class FakeMachine:
    """The supervisor, as far as the command line is concerned."""

    class NoSupervisor(Exception):
        pass

    class NotOurs(Exception):
        pass

    class Unsure(Exception):
        pass

    class Spoke:
        def __init__(self, ok, said=""):
            self.ok, self.said = ok, said

    def __init__(self, jobs=(), missing=False, refuses=False, foreign=(), refuse_acts=False,
                 stubborn=(), uncertain=()):
        self.jobs = list(jobs)
        self.missing, self.refuses, self.foreign = missing, refuses, list(foreign)
        #: The supervisor saying no without raising — a job present but not loaded.
        self.refuse_acts = refuse_acts
        #: Gateways whose job the machine will not let go of. The real `take_back` keeps
        #: the description in that case: it is the only thing that finds them again.
        self.stubborn = set(stubborn)
        self.uncertain = set(uncertain)
        self.did = []

    def _check(self, name):
        if self.missing:
            raise self.NoSupervisor("this machine has no launchd")
        if name in self.foreign:
            raise self.NotOurs(f"the job for '{name}' was not written by this install")

    def available(self):
        return not self.missing

    def described(self):
        return list(self.jobs)

    def known(self, name):
        # Ownership-aware, exactly like the real one: a job written by another install is
        # NOT known to us. A stand-in that answered yes here would send the command down
        # a path the real code never takes, and prove a guarantee that does not hold.
        return name in self.jobs and name not in self.foreign

    def exists(self, name):
        return name in self.jobs

    def loaded(self, name):
        if name in self.uncertain:
            raise self.Unsure("the machine did not answer")
        return not self.missing and name in self.jobs

    def install(self, name, run=None, logs=None, schedules=None, agents=None):
        self.job_said = {'run': run, 'logs': logs, 'schedules': schedules, 'agents': agents}
        self._check(name)
        self.did.append(("install", name))
        if not self.refuses:
            self.jobs.append(name)
        return self.Spoke(not self.refuses, "the machine said no")

    def stop(self, name):
        self._check(name)
        self.did.append(("stop", name))
        return self.Spoke(not self.refuse_acts, "the supervisor said no")

    def start(self, name):
        self._check(name)
        self.did.append(("start", name))
        return self.Spoke(not self.refuse_acts, "the supervisor said no")

    def take_back(self, name):
        self._check(name)
        self.did.append(("take_back", name))
        if name in self.stubborn:
            return False
        if name in self.jobs:
            self.jobs.remove(name)
        return True


def drive(argv, gateways=None, machine=None, agents=None):
    """Run the command line and hand back what it printed and what it returned."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv, gateways=gateways or FakeGateways(),
                            machine=machine or FakeMachine(), agents=agents or FakeAgents())
        except SystemExit as usage:
            # What a shell sees. Argparse refuses by exiting rather than returning, and a
            # case proving something is refused by the grammar could not otherwise say
            # what the caller was left with.
            code = usage.code if isinstance(usage.code, int) else 1
    return code, out.getvalue() + err.getvalue()


class ServingAGateway(unittest.TestCase):
    def test_serving_runs_the_gateway_of_the_name_given(self):
        """R-GW-13"""
        gateways = FakeGateways()
        code, _ = drive(["serve", "agent-one"], gateways)
        self.assertEqual(0, code)
        self.assertEqual(["agent-one"], gateways.served)

    def test_serving_without_a_name_is_a_usage_error(self):
        """R-CMD-5 — a verb says what and the next word says whose. There is no longer one
        gateway for it to have meant, so guessing would be guessing which agent."""
        gateways = FakeGateways()
        code, _, _ = run(["serve"])
        self.assertEqual(2, code)
        self.assertEqual([], gateways.served)

    def test_a_gateway_that_refuses_to_run_ends_well(self):
        """R-GW-25 — the machine starts a gateway again whenever it ends badly. One
        that will never start must therefore end well, or it is started every few
        seconds for as long as the machine is up."""
        for refusal in (FakeGateways.AlreadyRunning("already running"),
                        FakeGateways.Unfit("does not fit"),
                        FakeGateways.NotAName("not a name")):
            with self.subTest(refusal=type(refusal).__name__):
                code, said = drive(["serve", "gateway"], FakeGateways(refuses=refusal))
                self.assertEqual(0, code, "refusing to run ended badly, so it will be retried forever")
                self.assertIn(str(refusal), said, "it refused without saying why")


class HandingAGatewayToTheMachine(unittest.TestCase):
    def test_starting_hands_it_over_and_reports_the_gateway_that_resulted(self):
        """R-GW-13 — the supervisor taking the job is not a gateway running, and only
        one of those is what the person asking actually wanted."""
        machine = FakeMachine()
        code, said = drive(["start", "agent-one"], FakeGateways(starts_after=1), machine)
        self.assertEqual(0, code)
        self.assertIn(("install", "agent-one"), machine.did)
        self.assertIn("RUNNING", said)
        self.assertIn("4242", said, "it did not say which process")

    def test_starting_says_so_when_no_gateway_results(self):
        """R-GW-13 — a job can be accepted and the gateway then refuse to start, and
        refusing ends cleanly, so nothing else would ever say a word."""
        self.addCleanup(setattr, cli, "START_PATIENCE", cli.START_PATIENCE)
        cli.START_PATIENCE = 0.3
        code, said = drive(["start", "gateway"], FakeGateways(starts_after=10_000), FakeMachine())
        self.assertEqual(1, code)
        self.assertIn("FAILED", said)
        self.assertIn("rundesk logs", said, "it did not say where to look")

    def test_starting_a_gateway_that_is_already_running_changes_nothing(self):
        """R-GW-13 — handing it over again would boot the running one out first."""
        machine = FakeMachine(jobs=["gateway"])
        gateways = FakeGateways(standing=[FakeGateways.Standing("gateway", running=True, pid=7)])
        code, said = drive(["start", "gateway"], gateways, machine)
        self.assertEqual(0, code)
        self.assertIn("ALREADY RUNNING", said)
        self.assertEqual([], machine.did, "it touched the job of a gateway that was fine")

    def test_starting_a_gateway_running_with_nothing_keeping_it_is_not_success(self):
        """R-GW-13 — running is not the same as looked after.

        A gateway started by hand, or one left behind when its job was taken away,
        answers every question exactly as a supervised one does and will not come back
        when it exits or when the machine reboots. Reporting ALREADY RUNNING and exiting
        0 tells an owner they are covered at the one moment they are not.
        """
        machine = FakeMachine(jobs=[])  # a supervisor is here; it has no job for this
        gateways = FakeGateways(standing=[FakeGateways.Standing("gateway", running=True, pid=7)])
        code, said = drive(["start", "gateway"], gateways, machine)
        self.assertEqual(1, code, "it reported success for a gateway nothing is keeping up")
        self.assertIn("FAILED", said)
        self.assertIn("unsupervised", said)
        self.assertIn("7", said, "it did not say which process to deal with")

    def test_starting_a_gateway_already_running_where_there_is_no_supervisor_is_fine(self):
        """R-GW-13 — the check above is about a supervisor that has no job for this
        gateway, not about there being no supervisor. On a machine with none, running by
        hand is the arrangement rundesk itself recommends, and calling it a failure would
        make `rundesk serve` a thing that can never be reported as working."""
        machine = FakeMachine(missing=True)
        gateways = FakeGateways(standing=[FakeGateways.Standing("gateway", running=True, pid=7)])
        code, said = drive(["start", "gateway"], gateways, machine)
        self.assertEqual(0, code)
        self.assertIn("ALREADY RUNNING", said)

    def test_handing_over_a_name_belonging_to_something_else_is_refused(self):
        """R-GW-13 — handing over boots out whatever holds the name and writes over it,
        so this is the verb where getting ownership wrong costs the most."""
        code, said = drive(["start", "theirs"], machine=FakeMachine(foreign=["theirs"]))
        self.assertEqual(1, code)
        self.assertIn("not written by this install", said)

    def test_a_machine_with_no_supervisor_says_what_to_do_instead(self):
        """R-GW-13 — rundesk supervises nothing itself, so this is a real answer rather
        than a failure to explain."""
        code, said = drive(["start", "gateway"], machine=FakeMachine(missing=True))
        self.assertEqual(1, code)
        self.assertIn("serve", said, "it did not say how to run one without a supervisor")

    def test_a_machine_that_refuses_the_job_is_not_reported_as_success(self):
        """R-GW-13"""
        code, said = drive(["start", "gateway"], machine=FakeMachine(refuses=True))
        self.assertEqual(1, code)


class StandingGatewaysDown(unittest.TestCase):
    def test_stopping_a_named_gateway_stops_that_one(self):
        """R-GW-13"""
        machine = FakeMachine(jobs=["agent-one", "agent-two"])
        drive(["stop", "agent-one"], machine=machine)
        self.assertEqual([("stop", "agent-one")], machine.did)

    def test_stopping_without_saying_which_stops_nothing(self):
        """R-GW-14 — leaving the name out used to mean every gateway on the machine,
        silently. `rundesk restart` reads as the one you have, and took down every one."""
        for verb in ("stop", "restart"):
            with self.subTest(verb=verb):
                machine = FakeMachine(jobs=["agent-one", "agent-two"])
                code, said = drive([verb], machine=machine)
                self.assertEqual(2, code, said)
                self.assertEqual([], machine.did, f"bare `{verb}` reached the machine")
                self.assertIn("--all", said, "it refused and never said how to mean all")

    def test_stopping_every_agent_at_once_is_asked_for_out_loud(self):
        """R-GW-14 — the fan-out is kept; only the way of asking for it changed."""
        machine = FakeMachine(jobs=["agent-one", "agent-two"])
        drive(["stop", "--all"], machine=machine)
        self.assertEqual({("stop", "agent-one"), ("stop", "agent-two")}, set(machine.did))

    def test_stopping_a_gateway_that_was_never_handed_over_says_so(self):
        """R-GW-13 — and does not report having stopped something."""
        machine = FakeMachine(jobs=[])
        code, said = drive(["stop", "nobody"], machine=machine)
        self.assertEqual([], machine.did)
        self.assertIn("NO JOB", said)

    def test_stopping_a_job_this_install_did_not_write_is_refused(self):
        """R-GW-13"""
        machine = FakeMachine(jobs=["theirs"], foreign=["theirs"])
        code, said = drive(["stop", "theirs"], machine=machine)
        self.assertEqual(1, code)
        self.assertIn("another install", said)
        self.assertEqual([], machine.did, "it reached for a job belonging to something else")
        self.assertNotIn("NO JOB", said, "a job that plainly exists was called missing")

    def test_a_machine_that_refuses_without_explaining_is_still_reported(self):
        """R-GW-13 — the supervisor can simply say no: a job present but not loaded
        refuses a stop. Neither branch of that had a test in either direction."""
        machine = FakeMachine(jobs=["agent-one"], refuse_acts=True)
        gateways = FakeGateways(standing=[FakeGateways.Standing("agent-one", running=True, pid=9)])
        code, said = drive(["stop", "agent-one"], gateways, machine)
        self.assertEqual(1, code)
        self.assertIn("FAILED", said)

        idle = FakeMachine(jobs=["agent-one"], refuse_acts=True)
        code, said = drive(["stop", "agent-one"], FakeGateways(), idle)
        self.assertEqual(0, code)
        self.assertIn("ALREADY STOPPED", said)

    def test_cycling_a_gateway_stops_it_and_starts_it_again(self):
        """R-GW-13"""
        machine = FakeMachine(jobs=["agent-one"])
        drive(["restart", "agent-one"], machine=machine)
        self.assertEqual([("stop", "agent-one"), ("start", "agent-one")], machine.did)

    def test_a_cycle_that_could_not_start_it_again_is_a_failure(self):
        """R-GW-13 — stopping is half of a restart, and the half that leaves it down.

        A refused kickstart fell into the block written for `stop`: the gateway was not
        running (this command had just stopped it) and the job was known, so it came out
        as ALREADY STOPPED with a success exit. True, and completely wrong — it reads as
        'there was nothing to do' when what happened is 'I took it down and could not
        bring it back', which is the report a script acts on.
        """
        class RefusesToStart(FakeMachine):
            def start(self, name):
                self.did.append(("start", name))
                return self.Spoke(False, "the supervisor said no")

        machine = RefusesToStart(jobs=["agent-one"])
        code, said = drive(["restart", "agent-one"], FakeGateways(), machine)
        self.assertEqual([("stop", "agent-one"), ("start", "agent-one")], machine.did)
        self.assertEqual(1, code, "it reported success having left the gateway stopped")
        self.assertIn("FAILED", said)
        self.assertNotIn("ALREADY STOPPED", said, "it read as though there was nothing to do")

    def test_cycling_a_gateway_that_was_never_handed_over_is_a_failure(self):
        """R-GW-13 — 'nothing to stop' is a finished job for `stop` and a request that
        did not happen for `restart`: whoever asked wanted it running, and got nothing."""
        machine = FakeMachine(jobs=[])
        code, said = drive(["restart", "nobody"], machine=machine)
        self.assertEqual([], machine.did)
        self.assertIn("NO JOB", said)
        self.assertEqual(1, code, "it reported success without starting anything")
        # The same case under `stop` is genuinely fine, and must stay that way.
        code, said = drive(["stop", "nobody"], machine=FakeMachine(jobs=[]))
        self.assertEqual(0, code)
        self.assertIn("NO JOB", said)

    def test_a_gateway_running_with_no_job_is_not_blamed_on_another_install(self):
        """R-GW-13 — there is no other install, and no job of any kind. A stand-in
        refusal fed into the failure block said its job belonged to someone else, sending
        an owner hunting for a second copy of rundesk that does not exist."""
        machine = FakeMachine(jobs=[])
        gateways = FakeGateways(standing=[FakeGateways.Standing("gateway", running=True, pid=9)])
        code, said = drive(["stop", "gateway"], gateways, machine)
        self.assertEqual(1, code)
        self.assertIn("no job", said)
        self.assertNotIn("another install", said, "it blamed an install that does not exist")

    def test_cycling_waits_for_the_old_one_to_actually_go(self):
        """R-GW-13 — asking the machine to start a gateway that is still running does
        nothing, and the old one then ends *well*, which the machine is told not to
        undo. The gateway is left down, having just been reported as cycled."""
        machine = FakeMachine(jobs=["agent-one"])
        # running, then gone (so cycling sees it stop), then running again
        cycling = FakeGateways(becomes=[True, False, False, True])
        code, said = drive(["restart", "agent-one"], cycling, machine)
        self.assertEqual([("stop", "agent-one"), ("start", "agent-one")], machine.did)
        self.assertEqual(0, code)
        self.assertIn("RESTARTED", said)

    def test_cycling_says_so_rather_than_starting_one_that_never_stopped(self):
        """R-GW-13 — and does not report having cycled it."""
        self.addCleanup(setattr, cli, "CYCLE_PATIENCE", cli.CYCLE_PATIENCE)
        cli.CYCLE_PATIENCE = 0.3
        machine = FakeMachine(jobs=["agent-one"])
        gateways = FakeGateways(stops_after=10_000)  # never stops
        code, said = drive(["restart", "agent-one"], gateways, machine)
        self.assertEqual([("stop", "agent-one")], machine.did, "it started one that was still running")
        self.assertEqual(1, code)
        self.assertIn("still running", said)

    def test_cycling_one_gateway_leaves_the_others_alone(self):
        """R-GW-4"""
        machine = FakeMachine(jobs=["agent-one", "agent-two"])
        drive(["restart", "agent-one"], machine=machine)
        self.assertNotIn("agent-two", [name for _, name in machine.did])

    def test_stopping_them_all_where_there_are_none_says_so(self):
        """R-GW-13"""
        code, said = drive(["stop", "--all"], machine=FakeMachine(jobs=[]))
        self.assertEqual(0, code)
        self.assertIn("no agents", said)


class MakingAnAgent(unittest.TestCase):
    """`add` is the one place an agent and its gateway come into being together."""

    def test_making_an_agent_makes_it_and_says_where_it_stands(self):
        """R-AGW-1"""
        agents = FakeAgents()
        code, said = drive(["add", "ava"], agents=agents)
        self.assertEqual(0, code, said)
        self.assertEqual(["ava"], agents.added)
        self.assertIn("MADE", said)
        self.assertIn("home", said, "it made an agent and never said where it put it")

    def test_making_an_agent_that_exists_leaves_its_home_alone(self):
        """R-AGT-4 — repairing a home you half deleted must not be how you lose the rules
        you spent a month writing."""
        agents = FakeAgents(made=["ava"])
        code, said = drive(["add", "ava"], agents=agents)
        self.assertEqual(0, code, said)
        self.assertIn("ALREADY MADE", said)

    def test_making_an_agent_with_no_name_is_answered_in_our_words(self):
        """R-CMD-5 — argparse's usage dump says which token is missing; it does not say
        what there is already."""
        code, said = drive(["add"])
        self.assertEqual(1, code)
        self.assertIn("NAME REQUIRED", said)

    def test_a_name_that_cannot_be_an_agents_is_refused_before_anything_is_made(self):
        """R-AGT-5, R-AGT-6"""
        agents = FakeAgents()
        code, said = drive(["add", "ava.ran"], agents=agents)
        self.assertEqual(1, code)
        self.assertIn("INVALID NAME", said)
        self.assertEqual([], agents.added, "it refused the name and made one anyway")

    def test_adopting_a_gateway_that_has_no_agent_brings_what_it_wrote_in(self):
        """R-AGW-1 — one place afterwards, rather than two that disagree."""
        agents = FakeAgents(wrote=["gateway.log", "gateway.json"])
        code, said = drive(["add", "gateway"], agents=agents)
        self.assertEqual(0, code, said)
        self.assertEqual(["gateway"], agents.adopted)
        self.assertIn("gateway.log", said, "it moved things and never said which")

    def test_a_gateway_that_is_still_running_is_not_adopted(self):
        """R-AGW-1 — moving what a running gateway reads leaves it writing to one place
        while every command reads another."""
        agents = FakeAgents(wrote=["gateway.log"])
        gateways = FakeGateways(standing=[FakeGateways.Standing("gateway", running=True, pid=7)])
        code, said = drive(["add", "gateway"], gateways, agents=agents)
        self.assertEqual(1, code)
        self.assertEqual([], agents.adopted, "it moved what a running gateway is reading")
        self.assertIn("rundesk stop gateway", said, "it refused and never said what to do")


class TheVerbsNameTheAgent(unittest.TestCase):
    """The gateway is how an agent runs, so every verb asks where *that* agent keeps things."""

    def test_a_verb_asks_where_the_agent_it_names_keeps_things(self):
        """R-AGT-9 — an agent's gateway keeps its state in the agent's own directory. A
        command that asked the old shared one would report a running agent as stopped."""
        agents = FakeAgents(made=["ava"])
        gateways = FakeGateways()
        # Asked before the removal, which takes the agent away and with it the answer.
        its_own = agents.resolved("ava").run
        drive(["remove", "ava"], gateways, FakeMachine(), agents=agents)
        self.assertIn(its_own, gateways.asked_where,
                      "it asked about ava somewhere other than ava's own directory")

    def test_a_name_with_no_agent_is_asked_after_where_it_always_was(self):
        """R-AGT-9 — a gateway running since before there were agents keeps working, and
        adopting it is something an owner asks for rather than something it needs."""
        agents, gateways = FakeAgents(), FakeGateways()
        drive(["remove", "gateway"], gateways, FakeMachine(), agents=agents)
        self.assertTrue(gateways.asked_where, "it never asked the gateway anything")
        self.assertEqual({None}, set(gateways.asked_where),
                         "a name with no agent was asked after somewhere new")


class TwoQuestionsTwoCommands(unittest.TestCase):
    """`agents` says what you have; `status` says whether the thing running them is fit."""

    def test_status_answers_for_rundesk_and_lists_no_agents(self):
        """R-CMD-5 — one command answering both questions answered neither: a list of
        gateways says nothing about whether the install behind them can start one."""
        code, said = drive(["status"], agents=FakeAgents(made=["ava", "bo"]))
        self.assertEqual(0, code, said)
        self.assertIn(__version__, said)
        self.assertNotIn("ava", said, "`status` listed the agents again")
        self.assertNotIn("bo", said)

    def test_status_fails_when_the_install_cannot_run_an_agent(self):
        """R-GW-11 — an install that does not fit is the thing standing between every
        agent and a turn, and reporting it as fine is a success it did not earn."""
        gateways = FakeGateways()
        gateways.fitness = lambda root=None: "the virtualenv was built for another python"
        code, said = drive(["status"], gateways)
        self.assertEqual(1, code)
        self.assertIn("another python", said)

    def test_agents_lists_them_with_what_each_is_doing(self):
        """R-AGW-8"""
        agents = FakeAgents(made=["ava"])
        gateways = FakeGateways(standing=[FakeGateways.Standing("ava", running=True, pid=11)])
        code, said = drive(["agents"], gateways, agents=agents)
        self.assertEqual(0, code, said)
        self.assertIn("ava", said)
        self.assertIn("RUNNING", said)

    def test_the_name_column_holds_the_name_and_nothing_else(self):
        """R-AGW-8 — the table is read by things other than people: CI waits for a gateway
        to come up by matching the name at the start of its row. A marker put inside that
        cell made the column stop holding a name, and a running gateway was reported as one
        that never started — by the one step that proves an installed rundesk works."""
        gateways = FakeGateways(standing=[FakeGateways.Standing("probe", running=True, pid=9)])
        _, said = drive(["agents"], gateways, agents=FakeAgents())
        self.assertRegex(said, r"(?m)^probe +RUNNING",
                         "the name column holds something other than the name")

    def test_a_gateway_with_no_agent_is_listed_and_marked(self):
        """R-AGW-8 — still running, still holding a name. Leaving it off the one command
        that says what this install has is the worst of both."""
        gateways = FakeGateways(standing=[FakeGateways.Standing("gateway", running=True, pid=9)])
        code, said = drive(["agents"], gateways, agents=FakeAgents())
        self.assertEqual(0, code, said)
        self.assertIn("gateway", said)
        self.assertIn("no agent yet", said)
        self.assertIn("rundesk add gateway", said, "it marked one and never said what to do")

    def test_one_agent_says_every_place_it_resolves(self):
        """R-AGT-9 — which run state, which schedules and which log are authoritative is
        otherwise something an owner works out by reading the source."""
        code, said = drive(["agents", "ava"], agents=FakeAgents(made=["ava"]))
        self.assertEqual(0, code, said)
        for what in ("home", "workspace", "run", "logs", "schedules"):
            self.assertIn(what, said, f"it never said where {what} is")

    def test_asking_after_an_agent_that_is_not_there_says_so(self):
        """R-AGT-11"""
        code, said = drive(["agents", "nobody"], agents=FakeAgents())
        self.assertEqual(1, code)
        self.assertIn("NO SUCH AGENT", said)


class RunningOneHere(unittest.TestCase):
    def test_start_here_runs_it_in_this_terminal(self):
        """R-GW-13 — one verb for running an agent, with where it runs as an option."""
        gateways = FakeGateways()
        drive(["start", "ava", "--here"], gateways, FakeMachine())
        self.assertEqual(["ava"], gateways.served)

    def test_start_here_hands_nothing_to_the_machine(self):
        """R-GW-13 — `--here` means here. Writing a job as well would leave the machine
        starting a second one the moment this terminal closed."""
        machine = FakeMachine()
        drive(["start", "ava", "--here"], FakeGateways(), machine)
        self.assertEqual([], machine.did)

    def test_the_verb_a_job_already_on_disk_invokes_still_runs_it(self):
        """R-GW-13 — every launchd job written before this says `serve <name>`, and the
        plists are on disk. Folding it into `start` must not break one."""
        gateways = FakeGateways()
        drive(["serve", "ava"], gateways)
        self.assertEqual(["ava"], gateways.served)


class DiagnosingAnAgent(unittest.TestCase):
    def test_an_agent_with_nothing_wrong_is_ready(self):
        """R-AGT-11"""
        code, said = drive(["doctor", "ava"], agents=FakeAgents(made=["ava"]))
        self.assertEqual(0, code, said)
        self.assertIn("READY", said)

    def test_an_agent_with_something_wrong_says_what_and_fails(self):
        """R-AGT-11 — a diagnosis that exited zero would be read by a script as a working
        agent."""
        told = {"ava": [real_agent.Complaint("/nowhere/SOUL.md", "it is missing one it loads")]}
        code, said = drive(["doctor", "ava"], agents=FakeAgents(made=["ava"], complaints=told))
        self.assertEqual(1, code)
        self.assertIn("NOT READY", said)
        self.assertIn("SOUL.md", said)

    def test_diagnosing_with_no_name_asks_after_every_agent(self):
        """R-AGT-11"""
        code, said = drive(["doctor"], agents=FakeAgents(made=["ava", "bo"]))
        self.assertEqual(0, code, said)
        self.assertIn("ava", said)
        self.assertIn("bo", said)

    def test_diagnosing_where_there_are_no_agents_says_so(self):
        """R-AGT-11"""
        code, said = drive(["doctor"], agents=FakeAgents())
        self.assertEqual(0, code, said)
        self.assertIn("no agents", said)


class TakingAGatewayAway(unittest.TestCase):
    """Starting a gateway wrote a job the machine keeps forever; stopping one deliberately
    leaves that job alone. So a gateway an owner was finished with stayed in their
    machine's background items with no supported way to take it out."""

    def running(self, name="test2", **kw):
        return FakeGateways(standing=[FakeGateways.Standing(name, running=True, pid=64507)], **kw)

    def test_removing_a_gateway_takes_its_job_and_what_was_kept_for_it(self):
        """R-GW-31"""
        gateways, machine = FakeGateways(), FakeMachine(jobs=["test2"])
        code, said = drive(["remove", "test2"], gateways, machine)
        self.assertEqual(0, code, said)
        self.assertIn("REMOVED", said)
        self.assertIn(("take_back", "test2"), machine.did, "it left the job behind")
        self.assertEqual([("test2", False)], gateways.forgotten)

    def test_removing_a_gateway_that_is_running_removes_nothing(self):
        """R-GW-31 — asked of the gateway, not of the machine: one started by hand has no
        job to report and is exactly the one whose record must not be deleted under it."""
        gateways, machine = self.running(), FakeMachine(jobs=["test2"])
        code, said = drive(["remove", "test2"], gateways, machine)
        self.assertEqual(1, code)
        self.assertIn("STILL RUNNING", said)
        self.assertEqual([], gateways.forgotten, "it deleted what a running gateway is using")
        self.assertNotIn(("take_back", "test2"), machine.did)
        self.assertIn("rundesk stop test2", said, "it never said what to do about it")

    def test_removing_a_gateway_the_machine_will_not_let_go_of_removes_nothing(self):
        """R-GW-31 — the job is the only thing that finds this gateway again, so a
        half-done removal is worse than none: it leaves the thing running and unfindable."""
        gateways = FakeGateways()
        machine = FakeMachine(jobs=["test2"], stubborn=["test2"])
        code, said = drive(["remove", "test2"], gateways, machine)
        self.assertEqual(1, code)
        self.assertIn("would not let go", said)
        self.assertEqual([], gateways.forgotten, "it deleted rundesk's side anyway")

    def test_removing_a_gateway_belonging_to_another_install_is_refused(self):
        """R-GW-31, R-GW-13"""
        gateways = FakeGateways()
        machine = FakeMachine(jobs=["test2"], foreign=["test2"])
        code, said = drive(["remove", "test2"], gateways, machine)
        self.assertEqual(1, code)
        self.assertIn("another install", said)
        self.assertEqual([], gateways.forgotten)

    def test_removing_a_gateway_that_was_never_there_says_so_rather_than_failing(self):
        """R-GW-31 — running it twice, or on a name that never existed, is not an error."""
        gateways = FakeGateways()
        gateways.forget = lambda name, where=None, schedules=None, logs=None, history=False: []
        code, said = drive(["remove", "never-was"], gateways, FakeMachine())
        self.assertEqual(0, code, said)
        self.assertIn("NOTHING TO REMOVE", said)

    def test_removing_a_gateway_keeps_what_it_wrote_unless_purge_is_asked_for(self):
        """R-GW-31, R-GW-18 — what a gateway wrote outlives it, and an owner tidying up
        their background items has not asked to lose the account of what it did."""
        kept, purged = FakeGateways(), FakeGateways()
        _, said = drive(["remove", "test2"], kept, FakeMachine(jobs=["test2"]))
        self.assertEqual([("test2", False)], kept.forgotten)
        self.assertIn("--purge", said, "it never said the history could go too")

        _, told = drive(["remove", "test2", "--purge"], purged, FakeMachine(jobs=["test2"]))
        self.assertEqual([("test2", True)], purged.forgotten)
        self.assertIn("went with it", told)

    def test_there_is_one_way_to_remove_and_stop_is_not_it(self):
        """R-GW-31 — two ways to remove were two things to get right. `stop` stands an
        agent down and nothing else, so no flag on it can delete anything."""
        offered = {flag for parser in [_offered(cli.build_parser())["stop"]]
                   for action in parser._actions for flag in action.option_strings}
        self.assertEqual(offered - {"-h", "--help"}, {"--all"},
                         "`stop` offers a way to remove something")

    def test_remove_without_a_name_answers_in_our_words(self):
        """R-GW-31 — every other gateway verb defaults to one when the name is left out.
        This one must never guess, and an argparse usage dump is not an answer."""
        code, said = drive(["remove"], FakeGateways(), FakeMachine())
        self.assertEqual(1, code)
        self.assertIn("NAME REQUIRED", said)


class WhatEachAgentIsDoing(unittest.TestCase):
    def test_status_where_there_is_nothing_says_so(self):
        """R-GW-14"""
        code, said = drive(["agents"])
        self.assertEqual(0, code)
        self.assertIn("no agents", said)

    def test_status_says_which_gateways_are_up(self):
        """R-GW-9, R-GW-14"""
        gateways = FakeGateways(standing=[
            FakeGateways.Standing("agent-one", running=True, pid=42, version="0.1.1"),
            FakeGateways.Standing("agent-two", running=False),
        ])
        code, said = drive(["agents"], gateways, FakeMachine(jobs=["agent-one"]))
        self.assertIn("RUNNING", said)
        self.assertIn("42", said)
        self.assertIn("STOPPED", said)

    def test_status_says_what_each_gateway_has_in_flight(self):
        """R-GW-9 — what is being worked on is the question an owner actually has."""
        gateways = FakeGateways(
            standing=[FakeGateways.Standing("agent-one", running=True, pid=7, version="0.1.1")],
            working={"agent-one": ["a-conversation", "another"]},
        )
        _, said = drive(["agents"], gateways)
        self.assertIn("2 (", said)
        self.assertIn("a-conversation", said)

    def test_status_tells_a_wedged_gateway_from_a_working_one(self):
        """R-GW-9 — the distinction no supervisor makes for you: up, and not going round."""
        gateways = FakeGateways(standing=[
            FakeGateways.Standing("stuck", running=True, pid=9, version="0.1.1", stale=True)])
        _, said = drive(["agents"], gateways)
        self.assertIn("WEDGED", said)

    def test_a_loaded_job_with_no_process_reports_both_facts(self):
        """R-GW-10, R-GW-34 — a loaded job is not a running gateway."""
        _, said = drive(["agents"], FakeGateways(), FakeMachine(jobs=["agent-one"]),
                        agents=FakeAgents(made=["agent-one"]))
        self.assertRegex(said, r"agent-one\s+STOPPED.*LOADED")
        self.assertIn("LAUNCHD JOB", said)
        self.assertNotIn("SUPERVISED", said)

    def test_a_running_process_with_no_loaded_job_reports_both_facts(self):
        """R-GW-9, R-GW-34 — a running gateway is not a loaded job."""
        gateways = FakeGateways(standing=[
            FakeGateways.Standing("agent-one", running=True, pid=7, version="0.1.1")])
        _, said = drive(["agents"], gateways, FakeMachine(),
                        agents=FakeAgents(made=["agent-one"]))
        self.assertRegex(said, r"agent-one\s+RUNNING\s+7.*NOT LOADED")
        self.assertNotIn("SUPERVISED", said)

    def test_an_unanswered_job_query_is_reported_as_unknown(self):
        """R-GW-34 — unknown is a named state, never a punctuation mark."""
        machine = FakeMachine(jobs=["agent-one"], uncertain=["agent-one"])
        _, said = drive(["agents"], FakeGateways(), machine,
                        agents=FakeAgents(made=["agent-one"]))
        self.assertRegex(said, r"agent-one\s+STOPPED.*UNKNOWN")
        self.assertNotIn("?", said)

    def test_a_loaded_same_name_job_does_not_claim_the_gateway_process(self):
        """R-GW-34 — the machine cannot identify the PID its same-name job owns."""
        gateways = FakeGateways(standing=[
            FakeGateways.Standing("agent-one", running=True, pid=7, version="0.1.1")])
        _, said = drive(["agents"], gateways, FakeMachine(jobs=["agent-one"]),
                        agents=FakeAgents(made=["agent-one"]))
        self.assertRegex(said, r"agent-one\s+RUNNING\s+7.*LOADED")
        self.assertIn("LAUNCHD JOB", said)
        self.assertNotIn("SUPERVISED", said)


class WhatAGatewayRunsOnItsOwn(unittest.TestCase):
    def setUp(self):
        self.written = pathlib.Path(tempfile.mkdtemp(prefix="rundesk-cli-sched-")) / "gateway.log"
        self.addCleanup(shutil.rmtree, self.written.parent, True)
        self.written.write_text("")

    def _gateways(self, **kw):
        return FakeGateways(written=self.written, **kw)

    def test_a_schedule_can_be_run_by_hand_whether_or_not_it_is_due(self):
        """R-SCH-21 — a real program, so this proves it ran rather than that it was asked
        to. The schedule is due at three in the morning and this is not three."""
        gateways = self._gateways(schedules={"ava": [
            {"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo", "swept"]}]})
        code, said = drive(["schedules", "ava", "run", "tidy"], gateways)
        self.assertEqual(0, code, said)
        self.assertIn("swept", said, "it reported running it without running it")
        self.assertIn("RAN", said)

    def test_running_a_schedule_by_hand_leaves_the_time_it_next_falls_due_alone(self):
        """R-SCH-22 — what is due is decided from when each last fired, so a run by hand
        that recorded itself would read as the schedule having come due, and would stop
        the real firing that minute."""
        scheduled = {"ava": [{"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]}]}
        ran = {"ava": {"tidy": {"at": "2026-01-01 03:00", "outcome": "finished"}}}
        gateways = self._gateways(schedules=scheduled, ran_schedules=ran)

        code, said = drive(["schedules", "ava", "run", "tidy"], gateways)
        self.assertEqual(0, code, said)
        self.assertEqual(scheduled, gateways._written_schedules, "running by hand rewrote them")
        self.assertEqual(ran, gateways._ran_schedules,
                         "running by hand recorded a firing, so the real one is now skipped")
        self.assertIn("unchanged", said)

    def test_running_a_schedule_that_failed_says_so_and_fails(self):
        """R-SCH-21 — a run reported as fine when the program ended badly is a success
        this command did not earn."""
        gateways = self._gateways(schedules={"ava": [
            {"name": "nope", "when": "0 3 * * *", "run": ["/bin/sh", "-c", "exit 3"]}]})
        code, said = drive(["schedules", "ava", "run", "nope"], gateways)
        self.assertEqual(1, code)
        self.assertIn("FAILED", said)

    def test_running_a_schedule_that_is_not_there_says_so(self):
        """R-SCH-21"""
        code, said = drive(["schedules", "ava", "run", "nope"], self._gateways())
        self.assertEqual(1, code)
        self.assertIn("NOT FOUND", said)

    def test_a_schedule_whose_gateway_is_gone_is_not_shown_as_still_running(self):
        """R-SCH-24 — a firing is written down before the run begins, so `started` on its
        own says only that. With no gateway of that name up, nothing it started is going,
        and the command presented dead work as in flight until the schedule next fell due
        — a day, for a daily one, and the first question anybody asks after a crash."""
        gateways = self._gateways(
            schedules={"ava": [{"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]}]},
            ran_schedules={"ava": {"tidy": {"at": "2026-07-25 03:00", "outcome": "started"}}})
        _, said = drive(["schedules", "ava"], gateways)
        self.assertIn("interrupted", said)
        self.assertNotIn("started", said, "dead work was still presented as in flight")

    def test_a_schedule_running_right_now_is_shown_as_started(self):
        """R-SCH-24 — the other half. Work genuinely in flight reads as in flight, or the
        reconciliation is just the same lie the other way up."""
        gateways = self._gateways(
            standing=[FakeGateways.Standing("ava", running=True, pid=7)],
            schedules={"ava": [{"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]}]},
            ran_schedules={"ava": {"tidy": {"at": "2026-07-25 03:00", "outcome": "started"}}})
        _, said = drive(["schedules", "ava"], gateways)
        self.assertIn("started", said, "work that is running was written off as interrupted")

    def test_a_change_that_could_not_be_logged_is_not_reported_as_a_plain_success(self):
        """R-GW-37 — the change stands; it is already on disk. What must not happen is the
        command saying ADDED and nothing else, with the one account that outlives the
        gateway silently missing it."""
        gateways = self._gateways(unloggable="Read-only file system")
        code, said = drive(
            ["schedules", "ava", "add", "tidy", "--when", "0 3 * * *", "/bin/echo"], gateways)
        self.assertIn("ADDED", said, "a good change was unwound because its audit line failed")
        self.assertIn("WARNING", said)
        self.assertIn("Read-only file system", said, "it did not say why")
        self.assertEqual(1, code, "it reported a plain success it had not earned")

    def test_the_agent_is_the_word_after_the_verb(self):
        """R-SCH-14 — as an option it sat in the one place `--run`'s remainder swallowed,
        so `--gateway beta` typed after the program became an argument to the program and
        the schedule landed on the default agent, reported as success."""
        gateways = self._gateways()
        code, said = drive(["schedules", "ava", "add", "tidy", "--when", "* * * * *",
                            "--", "/bin/echo", "--gateway", "beta"], gateways)
        self.assertEqual(0, code, said)
        self.assertIn("ava", gateways._written_schedules, "it landed on some other agent")
        self.assertEqual(["/bin/echo", "--gateway", "beta"],
                         gateways._written_schedules["ava"][0]["run"])

    def test_the_old_way_of_naming_the_agent_is_refused_with_the_new_one(self):
        """R-SCH-14 — answered in our words with what to type, rather than by an argparse
        dump about an option it does not recognise."""
        gateways = self._gateways()
        code, said = drive(["schedules", "ava", "--gateway", "beta"], gateways)
        self.assertEqual(2, code)
        self.assertIn("rundesk schedules beta", said, "it refused and never said what to say")
        self.assertEqual({}, gateways._written_schedules, "it refused and wrote anyway")

    def test_an_option_after_the_program_is_refused_rather_than_swallowed(self):
        """R-SCH-3 — what to run is the words after `--` and nothing else, so a rundesk
        option typed there is a usage error instead of an argument to the program."""
        gateways = self._gateways()
        code, said = drive(["schedules", "ava", "add", "tidy", "--when", "* * * * *",
                            "/bin/echo", "-n"], gateways)
        self.assertEqual(2, code, said)
        self.assertEqual({}, gateways._written_schedules)

    def test_every_outcome_says_which_agent_as_well_as_which_schedule(self):
        """R-SCH-14 — a line naming only the schedule could not tell you it had landed on
        the wrong agent, and a refusal is exactly when you most want to know which."""
        gateways = self._gateways()
        _, added = drive(["schedules", "ava", "add", "tidy", "--when", "* * * * *",
                          "--", "/bin/echo"], gateways)
        self.assertIn("ava/tidy", added)
        _, twice = drive(["schedules", "ava", "add", "tidy", "--when", "* * * * *",
                          "--", "/bin/echo"], gateways)
        self.assertIn("ava/tidy", twice, "a refusal named the schedule and not the agent")
        _, missing = drive(["schedules", "ava", "remove", "nope"], gateways)
        self.assertIn("ava/nope", missing, "a refusal named the schedule and not the agent")

    def test_a_gateway_with_no_schedules_says_so(self):
        """R-SCH-8"""
        code, said = drive(["schedules", "gateway"], self._gateways())
        self.assertEqual(0, code)
        self.assertIn("NO SCHEDULES", said)

    def test_schedules_are_listed_with_when_each_next_runs(self):
        """R-SCH-8 — what is scheduled, when it next runs, and what became of it last."""
        gateways = self._gateways(
            schedules={"gateway": [{"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]}]},
            ran_schedules={"gateway": {"tidy": {"at": "2026-07-25 03:00", "outcome": "finished"}}})
        code, said = drive(["schedules", "gateway"], gateways)
        self.assertEqual(0, code)
        for expected in ("tidy", "0 3 * * *", "2026-07-25 03:00", "finished"):
            self.assertIn(expected, said)

    def test_a_schedule_that_is_off_is_kept_and_shown_as_off(self):
        """R-SCH-11 — keeping one without running it is the whole point of turning it off."""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "paused", "when": "* * * * *", "run": ["/bin/echo"], "enabled": False}]})
        _, said = drive(["schedules", "gateway"], gateways)
        self.assertIn("paused", said)
        self.assertIn("OFF", said)

    def test_a_schedule_nobody_can_understand_is_named_and_the_rest_still_listed(self):
        """R-SCH-10"""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "good", "when": "0 3 * * *", "run": ["/bin/echo"]},
            {"name": "bad", "when": "nonsense"}]})
        code, said = drive(["schedules", "gateway"], gateways)
        self.assertEqual(1, code)
        self.assertIn("good", said)
        self.assertIn("NOT UNDERSTOOD", said)

    def test_listing_schedules_that_cannot_be_read_never_reports_having_none(self):
        """R-SCH-17 — before any destructive change, the control surface had already
        turned "cannot read the configuration" into a healthy empty state: it printed
        NO SCHEDULES and exited zero for a file that still held every one of them."""
        code, said = drive(["schedules", "gateway"], self._gateways(unreadable={"gateway"}))
        self.assertEqual(1, code)
        self.assertNotIn("NO SCHEDULES", said)
        self.assertIn("UNREADABLE", said)

    def test_changing_schedules_that_cannot_be_read_says_nothing_was_changed(self):
        """R-SCH-17 — the owner needs to know their schedules are still there. Every way
        in is refused alike, because every one of them wrote an empty list over the file."""
        for asked in (["schedules", "gateway", "add", "new", "--when", "* * * * *", "--", "/bin/echo"],
                      ["schedules", "gateway", "remove", "nightly"],
                      ["schedules", "gateway", "off", "nightly"],
                      ["schedules", "gateway", "on", "nightly"]):
            with self.subTest(asked=asked[1]):
                code, said = drive(asked, self._gateways(unreadable={"gateway"}))
                self.assertEqual(1, code)
                self.assertIn("UNREADABLE", said)
                self.assertIn("nothing was changed", said)

    def test_a_schedule_is_added_and_shows_when_it_next_runs(self):
        """R-SCH-1, R-SCH-8"""
        gateways = self._gateways()
        code, said = drive(["schedules", "gateway", "add", "tidy", "--when", "*/5 * * * *",
                            "--", "/bin/echo", "hi"], gateways)
        self.assertEqual(0, code)
        self.assertIn("ADDED", said)
        self.assertEqual([{"name": "tidy", "when": "*/5 * * * *", "run": ["/bin/echo", "hi"]}],
                         gateways.written_schedules("gateway"))
        self.assertIn("added", self.written.read_text(), "the change was not written to the log")

    def test_a_schedule_nobody_could_act_on_is_never_added(self):
        """R-SCH-1 — refused where it is written, not discovered when it fails to run."""
        gateways = self._gateways()
        code, said = drive(["schedules", "gateway", "add", "bad", "--when", "99 * * * *",
                            "--", "/bin/echo"], gateways)
        self.assertEqual(1, code)
        self.assertIn("NOT ADDED", said)
        self.assertEqual([], gateways.written_schedules("gateway"))

    def test_a_schedule_naming_nothing_to_run_is_never_added(self):
        """R-SCH-2 — refused by the grammar rather than by the command: what to run is
        the words after `--`, and there is no way to say none of them."""
        gateways = self._gateways()
        code, said = drive(["schedules", "gateway", "add", "empty", "--when", "* * * * *", "--"],
                           gateways)
        self.assertEqual(2, code, said)
        self.assertEqual({}, gateways._written_schedules, "it added a schedule naming nothing")

    def test_a_schedule_naming_a_program_rather_than_locating_it_is_never_added(self):
        """R-SCH-1, R-PROC-2 — refused where it is written, not discovered at three in
        the morning. The gateway runs with almost no PATH, so a bare name resolves in the
        shell that typed it and nowhere else. Written down, it failed every time it fell
        due — with nothing said anywhere an owner reads, and LAST RUN stuck at '-'."""
        gateways = self._gateways()
        code, said = drive(["schedules", "gateway", "add", "nightly", "--when", "0 3 * * *",
                            "--", "codex", "exec"], gateways)
        self.assertEqual(1, code)
        self.assertIn("NOT ADDED", said)
        self.assertIn("not a location", said)
        self.assertEqual([], gateways.written_schedules("gateway"),
                         "a schedule that can never start was written down anyway")

    def test_adding_a_name_that_is_taken_is_refused(self):
        """R-SCH-8 — everything about a schedule is reported by its name, so two of one
        name is two schedules nobody can tell apart."""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]}]})
        code, said = drive(["schedules", "gateway", "add", "tidy", "--when", "* * * * *",
                            "--", "/bin/echo"], gateways)
        self.assertEqual(1, code)
        self.assertIn("EXISTS", said)
        self.assertEqual(1, len(gateways.written_schedules("gateway")))

    def test_a_schedule_is_taken_away(self):
        """R-SCH-8"""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]},
            {"name": "other", "when": "0 4 * * *", "run": ["/bin/echo"]}]})
        code, said = drive(["schedules", "gateway", "remove", "tidy"], gateways)
        self.assertEqual(0, code)
        self.assertIn("REMOVED", said)
        self.assertEqual(["other"], [one["name"] for one in gateways.written_schedules("gateway")])
        self.assertIn("removed", self.written.read_text())

    def test_a_schedule_is_turned_off_and_on_again_without_being_lost(self):
        """R-SCH-11"""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]}]})
        drive(["schedules", "gateway", "off", "tidy"], gateways)
        self.assertIs(False, gateways.written_schedules("gateway")[0]["enabled"])
        drive(["schedules", "gateway", "on", "tidy"], gateways)
        kept = gateways.written_schedules("gateway")
        self.assertIs(True, kept[0]["enabled"])
        self.assertEqual(1, len(kept), "turning one off and on again lost it")
        self.assertIn("turned off", self.written.read_text())
        self.assertIn("turned on", self.written.read_text())

    def test_changing_a_schedule_that_is_not_there_says_so(self):
        """R-SCH-8"""
        for act in ("remove", "on", "off"):
            with self.subTest(act=act):
                code, said = drive(["schedules", "gateway", act, "nope"], self._gateways())
                self.assertEqual(1, code)
                self.assertIn("NOT FOUND", said)

    def test_schedules_are_asked_for_and_changed_on_one_gateway_only(self):
        """R-SCH-13, R-SCH-14 — a gateway's schedules are its own, which is what makes
        one agent's schedules that agent's alone."""
        gateways = self._gateways(schedules={"agent-two": [
            {"name": "theirs", "when": "* * * * *", "run": ["/bin/echo"]}]})
        _, said = drive(["schedules", "agent-one"], gateways)
        self.assertIn("NO SCHEDULES", said)
        drive(["schedules", "gateway", "add", "mine", "--when", "* * * * *", "--", "/bin/echo"], gateways)
        self.assertEqual(["theirs"], [one["name"] for one in gateways.written_schedules("agent-two")])


class TheSurfacesAnAgentIsReachableOn(unittest.TestCase):
    """R-CAD-9, R-CAD-10, R-CAD-12 — adding a channel, and what it takes.

    A channel is named the way a schedule is, and what it *is* comes from `--kind`.
    Everything a particular platform needs goes after `--` and is never read here.
    """

    def setUp(self):
        self.at = pathlib.Path(tempfile.mkdtemp(prefix="rundesk-cli-channels-"))
        self.addCleanup(shutil.rmtree, self.at, True)
        self.written = self.at / "logs" / "ava.log"
        self.agents = FakeAgents(made=["ava"], at=self.at)
        (self.at / "ava").mkdir(parents=True, exist_ok=True)

    def _adapter(self, source: str) -> str:
        at = self.at / "a-channel"
        at.write_text("#!%s\n%s" % (sys.executable, source), encoding="utf-8")
        at.chmod(0o755)
        return str(at)

    #: Says it can see what it was pointed at, and hands back what it wants kept.
    WORKS = '''
import json, sys
rest = sys.argv[sys.argv.index("--check") + 1:]
settings = {rest[i].lstrip("-"): rest[i + 1] for i in range(0, len(rest) - 1, 2)}
print(json.dumps({"ok": True, "settings": settings, "describes": "#operations in Acme",
                  "secret": {"env": "A_CHANNEL_TOKEN"}}))
'''
    #: Cannot, and says why.
    CANNOT = '''
import json, sys
print(json.dumps({"ok": False, "why": "that room does not exist"}))
raise SystemExit(1)
'''

    def _gateways(self, **kw):
        return FakeGateways(written=self.written, **kw)

    def test_adding_a_channel_that_cannot_connect_writes_nothing_and_says_why(self):
        """R-CAD-9 — an agent whose channel is misconfigured finds out while somebody is
        standing at the terminal, not at three in the morning when it is asked
        something."""
        code, said = drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.CANNOT),
                            "--allow", "2207"], self._gateways(), agents=self.agents)
        self.assertEqual(1, code)
        self.assertIn("NOT ADDED", said)
        self.assertIn("that room does not exist", said, "the adapter's reason was swallowed")
        self.assertFalse((self.at / "ava" / "channels.json").exists(),
                         "a channel that proved nothing was written down anyway")

    def test_adding_a_channel_with_nobody_allowed_is_refused(self):
        """R-CAD-10 — refused by the grammar, like the time a schedule runs at: an agent
        that answers whoever speaks to it, on a machine where it runs tools, is a
        misconfiguration and never a mode, and there is deliberately no way to ask for
        anybody."""
        code, said = drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS)],
                           self._gateways(), agents=self.agents)
        self.assertEqual(2, code)
        self.assertIn("--allow", said)
        self.assertFalse((self.at / "ava" / "channels.json").exists())

    def test_allowing_nobody_in_particular_is_refused_too(self):
        """R-CAD-10 — the grammar is satisfied by an empty one, and an empty one allows
        exactly as many people as no flag at all."""
        code, said = drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
                            "--allow", ""], self._gateways(), agents=self.agents)
        self.assertEqual(1, code)
        self.assertIn("nobody is allowed", said)
        self.assertFalse((self.at / "ava" / "channels.json").exists())

    def test_adding_a_channel_that_works_writes_what_the_adapter_asked_to_keep(self):
        """R-CAD-9, R-CAD-13 — the settings come back from the adapter rather than from
        the command line, so what an owner is running on in a year is what the adapter
        understood rather than what they typed."""
        code, said = drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
                            "--allow", "2207", "--", "--server", "9930", "--room", "1180"],
                           self._gateways(), agents=self.agents)
        self.assertEqual(0, code, said)
        self.assertIn("ADDED", said)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertEqual({"server": "9930", "room": "1180"}, kept["settings"])
        self.assertEqual(["2207"], kept["allow"])

    def test_what_a_platform_needs_is_never_read_by_the_command(self):
        """R-CAD-13 — the core parses `--kind` and `--allow`, and carries the rest. A
        second surface needs no change here, and no word of any platform's is in it."""
        drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
               "--allow", "2207", "--", "--workspace", "T04", "--dm"],
              self._gateways(), agents=self.agents)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertEqual({"workspace": "T04"}, kept["settings"],
                         "the command decided what a platform's options meant")

    def test_a_credential_is_named_as_present_rather_than_shown(self):
        """R-CAD-12 — the record holds the name of a variable the adapter said it read.
        There is no value here to print by accident, because nothing ever held one."""
        drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
               "--allow", "2207"], self._gateways(), agents=self.agents)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertEqual({"env": ["A_CHANNEL_TOKEN"]}, kept["secret"])
        was = os.environ.get("A_CHANNEL_TOKEN")
        os.environ["A_CHANNEL_TOKEN"] = "not for printing"
        self.addCleanup(lambda: os.environ.pop("A_CHANNEL_TOKEN", None)
                        if was is None else os.environ.__setitem__("A_CHANNEL_TOKEN", was))
        _, said = drive(["channels", "ava", "show", "ops"], self._gateways(), agents=self.agents)
        self.assertIn("A_CHANNEL_TOKEN", said)
        self.assertIn("present", said)
        self.assertNotIn("not for printing", said, "a channel's secret was printed")

    def test_what_an_agent_is_told_is_written_and_read_back(self):
        """R-CH-22 — a wording that reads well in a room is found by trying it, so it is
        its own action: rewording must not mean taking the agent off the channel and
        proving it all over again."""
        drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
               "--allow", "2207"], self._gateways(), agents=self.agents)
        code, said = drive(["channels", "ava", "says", "ops",
                            "--room", "You are in {where}. Others read this."],
                           self._gateways(), agents=self.agents)
        self.assertEqual(0, code)
        self.assertIn("TOLD", said)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertEqual({"room": "You are in {where}. Others read this."},
                         kept[channel.SAYS])
        _, back = drive(["channels", "ava", "says", "ops"], self._gateways(),
                        agents=self.agents)
        self.assertIn("Others read this", back)

    def test_one_situation_being_written_does_not_drop_another(self):
        """R-CH-22 — merged rather than replaced. An owner setting what is said in a room
        must not silently lose what they wrote for a direct message a week ago."""
        drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
               "--allow", "2207"], self._gateways(), agents=self.agents)
        for flag, said in (("--direct", "Private."), ("--room", "Public.")):
            drive(["channels", "ava", "says", "ops", flag, said],
                  self._gateways(), agents=self.agents)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertEqual({"direct": "Private.", "room": "Public."}, kept[channel.SAYS])
        drive(["channels", "ava", "says", "ops", "--room", ""],
              self._gateways(), agents=self.agents)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertEqual({"direct": "Private."}, kept[channel.SAYS],
                         "taking one situation back off took another with it")

    def test_a_name_that_cannot_be_filled_in_is_refused_before_it_is_written(self):
        """R-CH-22 — checked when it is written, which is the whole reason this is a
        command rather than a file to edit. Written, it would go quietly blank at every
        turn from then on and never say so."""
        drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
               "--allow", "2207"], self._gateways(), agents=self.agents)
        code, said = drive(["channels", "ava", "says", "ops", "--room", "Hello {wheree}."],
                           self._gateways(), agents=self.agents)
        self.assertEqual(1, code)
        self.assertIn("NOT CHANGED", said)
        self.assertIn("wheree", said)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertNotIn(channel.SAYS, kept)

    def test_telling_a_channel_that_is_not_there_says_so(self):
        """R-CH-22 — told apart from a record that could not be written, because one is
        the owner's typo and the other is a disk to look at."""
        code, said = drive(["channels", "ava", "says", "nowhere", "--any", "Hello."],
                           self._gateways(), agents=self.agents)
        self.assertEqual(1, code)
        self.assertIn("NOT FOUND", said)

    def test_a_channel_that_is_added_twice_is_refused(self):
        """R-CAD-9 — the second one would silently replace the first, including who was
        allowed to use it."""
        for _ in range(1):
            drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
                   "--allow", "2207"], self._gateways(), agents=self.agents)
        code, said = drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
                            "--allow", "9999"], self._gateways(), agents=self.agents)
        self.assertEqual(1, code)
        self.assertIn("EXISTS", said)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertEqual(["2207"], kept["allow"], "who may use it was replaced by a refusal")

    def test_an_agent_that_is_not_running_is_reported_as_out_of_reach(self):
        """R-CAD-8 — a channel on a stopped agent is deaf rather than quiet, and the
        difference is the whole of what an owner needs to know."""
        drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
               "--allow", "2207"], self._gateways(), agents=self.agents)
        _, said = drive(["channels", "ava"], self._gateways(), agents=self.agents)
        self.assertIn("REACHABLE", said)
        self.assertRegex(said, r"ops\s+.*\s+no")

    def test_a_channel_can_be_taken_off_an_agent(self):
        """R-CAD-9 — and the record says so afterwards."""
        drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
               "--allow", "2207"], self._gateways(), agents=self.agents)
        code, said = drive(["channels", "ava", "remove", "ops"],
                           self._gateways(), agents=self.agents)
        self.assertEqual(0, code, said)
        self.assertIn("REMOVED", said)
        self.assertEqual({}, json.loads((self.at / "ava" / "channels.json").read_text()))

    def test_an_agent_with_no_channels_says_so_and_says_what_to_do(self):
        code, said = drive(["channels", "ava"], self._gateways(), agents=self.agents)
        self.assertEqual(0, code)
        self.assertIn("NO CHANNELS", said)
        self.assertIn("rundesk channels ava add", said)

    def test_a_channel_name_that_would_escape_where_channels_are_kept_is_refused(self):
        """R-CAD-9, R-GW-20 — a channel's name becomes a directory. It was passed to the
        thing that builds one with nothing checking it, so an unusable name came back as
        a traceback rather than as an answer — and every other verb answers in our
        words."""
        code, said = drive(["channels", "ava", "add", "../../evil",
                            "--kind", self._adapter(self.WORKS), "--allow", "2207"],
                           self._gateways(), agents=self.agents)
        self.assertEqual(1, code)
        self.assertIn("INVALID NAME", said)
        self.assertNotIn("Traceback", said)
        self.assertFalse((self.at / "ava" / "channels.json").exists())

    def test_an_unusable_channel_name_is_refused_by_every_action_that_takes_one(self):
        """R-GW-20 — `show` and `remove` build the same path from the same word, so one
        of them left unchecked is the whole check missing."""
        for act in ("show", "remove"):
            code, said = drive(["channels", "ava", act, "../../evil"],
                               self._gateways(), agents=self.agents)
            self.assertEqual(1, code, f"{act} accepted a name that cannot be one")
            self.assertIn("INVALID NAME", said)

    def test_channels_for_an_agent_that_does_not_exist_says_so(self):
        code, said = drive(["channels", "nobody"], self._gateways(), agents=self.agents)
        self.assertEqual(1, code)
        self.assertIn("NO SUCH AGENT", said)

    def test_a_platforms_options_survive_looking_like_rundesks_own(self):
        """R-CAD-13 — `--server` and `--dm` are a platform's words, and argparse would
        refuse them as unrecognized. They are taken off before the parser, which is the
        only way a tail with an option in it parses on the oldest Python this runs on."""
        drive(["channels", "ava", "add", "ops", "--kind", self._adapter(self.WORKS),
               "--allow", "2207", "--", "--server", "9930", "--room", "1180"],
              self._gateways(), agents=self.agents)
        kept = json.loads((self.at / "ava" / "channels.json").read_text())["ops"]
        self.assertEqual({"server": "9930", "room": "1180"}, kept["settings"])

    def test_only_a_verb_that_carries_a_tail_has_one_taken_off_it(self):
        """R-CAD-13 — read off the parser rather than listed, and scoped: argparse can
        carry a tail into a positional that is required and greedy, which is what a
        schedule's program is, and taking that away would break a form it already
        accepts."""
        parser = cli.build_parser()
        self.assertEqual({"channels"}, cli._carries_a_tail(parser))
        rest, tail = cli._handed_on(
            ["schedules", "ava", "add", "t", "--when", "X", "--", "/bin/sh", "-c", "hi"],
            cli._carries_a_tail(parser))
        self.assertEqual([], tail, "a schedule's program was taken from the parser")
        self.assertEqual(["/bin/sh", "-c", "hi"], parser.parse_args(rest).run)


class WhatNeverFinished(unittest.TestCase):
    """R-GW-38, R-GW-39 — the store saying what never finished, given a reader.

    It had none: "what did not finish" meant reading JSON out of a directory by hand,
    during an incident, having already guessed the gateway's name.
    """

    def _gateways(self, **kw):
        written = pathlib.Path(tempfile.mkdtemp(prefix="rundesk-cli-unfinished-")) / "gateway.log"
        self.addCleanup(shutil.rmtree, written.parent, True)
        return FakeGateways(written=written, **kw)

    def test_what_never_finished_is_readable_without_opening_a_file(self):
        """R-GW-39 — the count itself, in the table an owner looks at first. Asserting on
        the column heading would pass against a column that is always empty."""
        gateways = self._gateways(
            standing=[FakeGateways.Standing("ava", running=True, pid=7)],
            interrupted={"ava": {
                "schedule:nightly": {"at": "2026-07-25 03:00", "ended": True, "why": "gone"},
                "schedule:weekly": {"at": "2026-07-24 03:00", "ended": True, "why": "gone"}}})
        code, said = drive(["agents"], gateways, agents=FakeAgents(made=["ava"]))
        self.assertEqual(0, code, said)
        self.assertIn("UNFINISHED", said)
        rows = [line for line in said.splitlines() if line.startswith("ava")]
        self.assertTrue(rows and rows[0].rstrip().endswith("2"),
                        f"two things never finished and the table did not say so: {rows}")

    def test_an_agent_with_nothing_unfinished_says_nothing_about_it(self):
        """R-GW-39 — the ordinary case must not read as an incident."""
        gateways = self._gateways(standing=[FakeGateways.Standing("ava", running=True, pid=7)])
        _, said = drive(["agents"], gateways, agents=FakeAgents(made=["ava"]))
        rows = [line for line in said.splitlines() if line.startswith("ava")]
        self.assertTrue(rows and rows[0].rstrip().endswith("-"),
                        f"an agent with nothing unfinished was given a count: {rows}")

    def test_each_thing_that_never_finished_is_shown_with_its_time_and_reason(self):
        """R-GW-39 — and told apart by whether it is definitely gone: one of them is over,
        the other may still be running with nobody owning it, and they are different
        problems with different things to do about them."""
        gateways = self._gateways(interrupted={"ava": {
            "schedule:nightly": {"at": "2026-07-25 03:00", "ended": True, "why": "gateway gone"},
            "schedule:weekly": {"at": "2026-07-24 03:00", "ended": False, "why": "would not go"},
        }})
        _, said = drive(["agents", "ava"], gateways, agents=FakeAgents(made=["ava"]))
        self.assertIn("2026-07-25 03:00", said)
        self.assertIn("gateway gone", said)
        self.assertIn("unproven", said, "work that may still be running read as definitely gone")

    def test_a_gateway_that_survives_only_as_history_is_still_listed(self):
        """R-GW-38 — its record was cleared and its agent taken away, so the one place it
        exists is what it never finished. That is the name an owner wants after a crash,
        and it was the one they had to know already before anything would tell them."""
        gateways = self._gateways(interrupted={"vanished": {"turn": {"ended": False}}})
        _, said = drive(["agents"], gateways, agents=FakeAgents())
        self.assertIn("vanished", said, "a gateway with nothing left but its history was invisible")


class WhatAGatewayHasBeenSaying(unittest.TestCase):
    def setUp(self):
        self.written = pathlib.Path(tempfile.mkdtemp(prefix="rundesk-cli-log-")) / "gateway.log"
        self.addCleanup(shutil.rmtree, self.written.parent, True)

    def test_logs_shows_what_a_gateway_wrote(self):
        """R-GW-18"""
        self.written.write_text("first\nsecond\nthird\n")
        code, said = drive(["logs", "gateway"], FakeGateways(written=self.written))
        self.assertEqual(0, code)
        self.assertIn("second", said)

    def test_logs_shows_the_last_of_it_rather_than_all_of_it(self):
        """R-GW-18 — a gateway up for a month has more than anyone wants at once."""
        self.written.write_text("".join(f"line {i}\n" for i in range(500)))
        _, said = drive(["logs", "-n", "5", "gateway"], FakeGateways(written=self.written))
        self.assertIn("line 499", said)
        self.assertNotIn("line 100", said)

    def test_logs_for_a_gateway_that_has_said_nothing_says_so(self):
        """R-GW-18 — and does not print an empty answer as though that were the log."""
        code, said = drive(["logs", "gateway"], FakeGateways(written=self.written))
        self.assertEqual(1, code)
        self.assertIn("nothing written yet", said)

    def test_a_log_that_cannot_be_read_is_reported_rather_than_crashing(self):
        """R-GW-18 — every other verb answers in our words when it cannot do the thing."""
        self.written.write_text("something\n")
        self.written.chmod(0o000)
        self.addCleanup(self.written.chmod, 0o600)
        code, said = drive(["logs", "gateway"], FakeGateways(written=self.written))
        self.assertEqual(1, code)
        self.assertIn("could not read", said)

    def test_asking_for_none_of_the_log_shows_none_of_it(self):
        """R-GW-18 — a slice of minus nothing is the whole file."""
        self.written.write_text("first\nsecond\n")
        _, said = drive(["logs", "-n", "0", "gateway"], FakeGateways(written=self.written))
        self.assertNotIn("first", said)

    def test_what_a_gateway_wrote_is_readable_after_it_has_gone(self):
        """R-GW-18 — the case the log exists for."""
        self.written.write_text("up\nsomething went wrong\ndown\n")
        _, said = drive(["logs", "gateway"], FakeGateways(written=self.written))
        self.assertIn("something went wrong", said)

    def test_a_startup_failure_that_never_reached_the_logger_is_still_shown(self):
        """R-GW-36 — a failed start tells the owner to run this command, and the whole of
        the answer is in what the machine captured: a traceback, or a refusal printed
        before there was a logger to print it. Reading only `.log` answered the one
        question this command exists for with NO LOG."""
        (self.written.parent / "gateway.err").write_text("Traceback (most recent call last):\n")
        code, said = drive(["logs", "gateway"], FakeGateways(written=self.written))
        self.assertEqual(0, code, "the answer was there and the command said there was none")
        self.assertIn("Traceback", said)

    def test_the_lines_that_explain_the_tail_are_shown_with_it(self):
        """R-GW-36 — rotation cuts one account into four files, and the part explaining
        the current tail is as often in the one behind it."""
        (self.written.parent / "gateway.log.1").write_text("what actually went wrong\n")
        self.written.write_text("and then this\n")
        _, said = drive(["logs", "gateway"], FakeGateways(written=self.written))
        self.assertIn("what actually went wrong", said)
        self.assertLess(said.index("what actually went wrong"), said.index("and then this"),
                        "one account was put back together out of order")

    def test_who_wrote_a_line_is_said_when_more_than_one_did(self):
        """R-GW-36 — two writers say different kinds of thing about one gateway, and a
        reader deciding which is which by eye is a reader who gets it wrong."""
        self.written.write_text("up\n")
        (self.written.parent / "gateway.err").write_text("Traceback\n")
        _, said = drive(["logs", "gateway"], FakeGateways(written=self.written))
        self.assertRegex(said, r"gateway\s+up")
        self.assertRegex(said, r"machine\s+Traceback")

    def test_one_source_can_be_asked_for_on_its_own(self):
        """R-GW-36 — labelled by default, narrowed on request."""
        self.written.write_text("up\n")
        (self.written.parent / "gateway.err").write_text("Traceback\n")
        _, said = drive(["logs", "gateway", "--source", "machine"],
                        FakeGateways(written=self.written))
        self.assertIn("Traceback", said)
        self.assertNotIn("up", said, "it showed a source it was told not to")


class WhatIsInFlightWhenAnUpdateAsks(unittest.TestCase):
    def test_what_is_in_flight_is_asked_of_every_gateway_that_is_running(self):
        """R-UPD-23 — every gateway, not the default one, and named so an owner knows
        which of several to wait for. A gateway that is stopped has nothing in flight
        however stale its record is, so it is never asked."""

        class Standing:
            def __init__(self, name, running):
                self.name, self.running = name, running

        class Gateways:
            def remembered(self, where=None):
                return []   # nothing here is a name that survives only as history

            def every(self):
                return [Standing("alpha", True), Standing("beta", True),
                        Standing("gamma", False)]

            def standing(self, name, where=None):
                return Standing(name, name in ("alpha", "beta"))

            def what_is_running(self, name, where=None):
                return {"alpha": ["turn-1", "turn-2"], "beta": ["turn-3"],
                        "gamma": ["stale"]}[name]

        self.assertEqual(
            ["alpha/turn-1", "alpha/turn-2", "beta/turn-3"],
            cli._in_flight(Gateways(), FakeAgents()),
        )

    def test_a_machine_with_no_gateways_has_nothing_in_flight(self):
        """R-UPD-23 — the ordinary case, and the one that must never refuse an update."""

        class Gateways:
            def remembered(self, where=None):
                return []   # nothing here is a name that survives only as history

            def every(self):
                return []

            def standing(self, name, where=None):
                raise AssertionError("it asked about a gateway that does not exist")

            def what_is_running(self, name, where=None):
                raise AssertionError("it asked about a gateway that does not exist")

        self.assertEqual([], cli._in_flight(Gateways(), FakeAgents()))


class StoppingWhatAnUpdateWouldReplace(unittest.TestCase):
    """R-UPD-21, R-UPD-22 — which gateways an update may take down, and which it may not."""

    class Standing:
        def __init__(self, name, running=True, pid=1, version="0.1.0"):
            self.name, self.running, self.pid, self.version = name, running, pid, version

    def _machine(self, loaded=(), available=True, stops=True):
        outer = self

        class Machine:
            NotOurs = RuntimeError
            NoSupervisor = RuntimeError
            asked = []

            def available(self):
                return available

            def loaded(self, name):
                return name in loaded

            def described(self):
                return []

            def stop(self, name):
                Machine.asked.append(("stop", name))
                return type("Spoke", (), {"ok": stops})()

            def start(self, name):
                Machine.asked.append(("start", name))
                return type("Spoke", (), {"ok": True})()

        Machine.asked = []
        return Machine()

    def _gateways(self, standing, gone_after_stop=True, comes_up=True, working=()):
        outer = self
        #: How many times each has been asked after. The first answer is what it was doing
        #: before anything was asked of it, and the ones after are whether it has gone —
        #: the same gateway, asked twice, which is what the real one does.
        asked = {}

        class Gateways:
            def remembered(self, where=None):
                return []   # nothing here is a name that survives only as history

            def every(self):
                return standing

            def standing(self, name, where=None):
                for it in standing:
                    if it.name == name:
                        asked[name] = asked.get(name, 0) + 1
                        if asked[name] == 1 or not gone_after_stop:
                            return it
                        return outer.Standing(name, running=False)
                return outer.Standing(name, running=False)

            def what_is_running(self, name, where=None):
                return list(working)

            def fitness(self, root=None):
                return None
        return Gateways()

    def test_an_update_stops_every_supervised_gateway_that_is_running(self):
        """R-UPD-21"""
        up = [self.Standing("alpha"), self.Standing("beta"), self.Standing("idle", running=False)]
        machine = self._machine(loaded=("alpha", "beta"))
        stopped, refused = cli._stand_all_down(self._gateways(up), machine, FakeAgents())
        self.assertIsNone(refused)
        self.assertEqual(["alpha", "beta"], stopped)
        self.assertEqual([("stop", "alpha"), ("stop", "beta")], machine.asked,
                         "it stopped a gateway that was not running")

    def test_an_update_refuses_rather_than_taking_down_what_it_cannot_start_again(self):
        """R-UPD-21 — launchctl has no handle on a process it never started, and nothing
        records the terminal a hand-started gateway came from."""
        machine = self._machine(loaded=())     # running, but the machine holds no job
        stopped, refused = cli._stand_all_down(self._gateways([self.Standing("scratch", pid=8812)]), machine, FakeAgents())
        self.assertEqual([], stopped)
        self.assertIn("unsupervised", refused)
        self.assertIn("rundesk start scratch", refused)
        self.assertEqual([], machine.asked, "it tried to stop one it could not start again")

    def test_an_update_on_a_machine_with_no_supervisor_stops_nothing(self):
        """R-UPD-21 — nothing to hand a gateway to means nothing to take one from."""
        stopped, refused = cli._stand_all_down(self._gateways([self.Standing("alpha")]), self._machine(available=False), FakeAgents())
        self.assertEqual(([], None), (stopped, refused))

    def test_a_gateway_that_will_not_stop_leaves_the_install_untouched(self):
        """R-UPD-21 — replacing files under something that refused to go is the failure
        this whole sequence exists to avoid."""
        machine = self._machine(loaded=("alpha",), stops=False)
        stopped, refused = cli._stand_all_down(self._gateways([self.Standing("alpha")]), machine, FakeAgents())
        self.assertEqual([], stopped)
        self.assertIn("would not stop", refused)

    def test_work_begun_while_the_update_was_starting_is_not_taken_down(self):
        """R-UPD-23 — what is in flight is asked once, before any of this. A turn that
        began between that answer and this moment would be killed by the very stop that
        exists to protect it, so it is asked again with nothing left in between."""
        machine = self._machine(loaded=("alpha",))
        stopped, refused = cli._stand_all_down(self._gateways([self.Standing("alpha")], working=("a-turn",)), machine, FakeAgents())
        self.assertEqual([], stopped)
        self.assertIn("began work", refused)
        self.assertEqual([], machine.asked, "it stopped a gateway that had just taken work")

    def test_a_gateway_that_does_not_come_back_is_reported_rather_than_passed_over(self):
        """R-UPD-22 — a release needing something this install does not have starts a
        gateway that ends *well* so as not to be restarted forever, and the machine calls
        that a job accepted. Only asking the gateway itself catches it."""
        self.addCleanup(setattr, cli, "START_PATIENCE", cli.START_PATIENCE)
        cli.START_PATIENCE = 0.1
        machine = self._machine(loaded=("alpha",))
        never = self._gateways([self.Standing("alpha", running=False)], gone_after_stop=False)
        self.assertEqual(["alpha"], cli._bring_all_back(["alpha"], never, machine, FakeAgents()))


class WhichVersionEachGatewayIsActuallyOn(unittest.TestCase):
    def test_status_says_which_version_each_gateway_is_running(self):
        """R-GW-9 — asked of the gateway's own record, because that and this install come
        apart exactly when it matters."""
        from rundesk_cli import __version__
        it = type("S", (), {"running": True, "version": __version__})()
        self.assertEqual(__version__, cli._version_of(it))

    def test_a_gateway_left_on_an_older_version_is_marked_rather_than_merely_shown(self):
        """R-GW-9 — an update replaces the files while a gateway keeps the code it already
        imported. Two numbers a reader has to compare by eye is a difference nobody sees."""
        it = type("S", (), {"running": True, "version": "0.0.1"})()
        self.assertIn("old", cli._version_of(it))

    def test_a_gateway_that_is_not_running_has_no_version_to_report(self):
        """R-GW-9 — a version read off a record whose process is gone says nothing."""
        self.assertEqual("-", cli._version_of(type("S", (), {"running": False, "version": "9"})()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
