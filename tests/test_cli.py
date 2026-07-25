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
import pathlib
import shutil
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import __version__  # noqa: E402
from rundesk_cli import cli  # noqa: E402
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
    cli.updater.latest_version_online = lambda: published
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv, gateways=FakeGateways(), machine=FakeMachine())
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
                # 1 is allowed: a built verb given nothing to work on may honestly fail.
                # What must never happen is falling through to the catch-all above.
                self.assertIn(code, (0, 1, cli.NOT_BUILT), f"'{verb}' exited {code}")

    def test_a_planned_command_says_so_and_does_not_report_success(self):
        # Exiting 0 having done nothing is a lie a script will believe.
        for verb in sorted(cli.COMING_SOON):
            with self.subTest(verb=verb):
                code, _, err = run([verb])
                self.assertEqual(code, cli.NOT_BUILT, f"'{verb}' reported success without doing anything")
                self.assertIn("NOT BUILT", err)

    def test_a_planned_command_tolerates_the_arguments_it_will_take(self):
        # `rundesk run agent-x "do a thing"` must answer in our words. An unknown *flag*
        # is argparse's to reject, and rightly — that is a typo, not a planned command.
        code, _, err = run(["run", "agent-x", "do a thing"])
        self.assertEqual(code, cli.NOT_BUILT)
        self.assertIn("NOT BUILT", err)

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
        built = {"version", "update", "uninstall",
                 "serve", "start", "stop", "restart", "status", "logs", "schedules"}
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
                self.assertIn("UP TO DATE", current_said)

                unknown_code, unknown_said, _ = run(argv, published=None)
                self.assertEqual(unknown_code, 1, "could-not-ask reported as success")
                self.assertNotIn("UP TO DATE", unknown_said)

    def test_check_never_moves_the_install(self):
        # --check is a question. A question that changed the install would be a trap.
        moved = []
        code = cli.updater.run(
            cli.REPO_ROOT, __version__, check_only=True,
            latest=lambda: "v99.0.0", apply=lambda root, tag: moved.append(tag) or 0,
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
                 schedules=None, ran_schedules=None):
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

    def every(self):
        return list(self._standing)

    def standing(self, name):
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

    def what_is_running(self, name):
        return self._working.get(name, [])

    def scheduled(self, name):
        from rundesk_cli import schedule
        return schedule.read(self._written_schedules.get(name, []))

    def written_schedules(self, name):
        return list(self._written_schedules.get(name, []))

    @contextlib.contextmanager
    def changing_schedules(self, name):
        """Read, change, write back — the shape the real one holds a lock across."""
        keeping = list(self._written_schedules.get(name, []))
        yield keeping
        self._written_schedules[name] = keeping

    def what_was_scheduled(self, name):
        return self._ran_schedules.get(name, {})

    def note(self, name, said):
        # Never the real home: without somewhere of its own to write, a stand-in that
        # fell back to the default would put test lines in the owner's own logs.
        assert self._written is not None, "this case writes a log line and was given nowhere to put it"
        from rundesk_cli import gateway as real
        real.note(name, said, self._written.parent)

    def log_path(self, name):
        return self._written if self._written is not None else pathlib.Path("/nowhere/x.log")

    def Gateway(self, name):
        gateways = self

        class One:
            async def serve(inner):
                if gateways._refuses:
                    raise gateways._refuses
                gateways.served.append(name)
                return 0

        return One()


class FakeMachine:
    """The supervisor, as far as the command line is concerned."""

    class NoSupervisor(Exception):
        pass

    class NotOurs(Exception):
        pass

    class Spoke:
        def __init__(self, ok, said=""):
            self.ok, self.said = ok, said

    def __init__(self, jobs=(), missing=False, refuses=False, foreign=(), refuse_acts=False):
        self.jobs = list(jobs)
        self.missing, self.refuses, self.foreign = missing, refuses, list(foreign)
        #: The supervisor saying no without raising — a job present but not loaded.
        self.refuse_acts = refuse_acts
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
        return not self.missing and name in self.jobs

    def install(self, name):
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


def drive(argv, gateways=None, machine=None):
    """Run the command line and hand back what it printed and what it returned."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv, gateways=gateways or FakeGateways(), machine=machine or FakeMachine())
    return code, out.getvalue() + err.getvalue()


class ServingAGateway(unittest.TestCase):
    def test_serving_runs_the_gateway_of_the_name_given(self):
        """R-GW-13"""
        gateways = FakeGateways()
        code, _ = drive(["serve", "agent-one"], gateways)
        self.assertEqual(0, code)
        self.assertEqual(["agent-one"], gateways.served)

    def test_serving_without_a_name_runs_the_one_gateway_there_is(self):
        """R-GW-13 — a name is optional today and required by nothing, so what this
        does now stays true when there is one gateway per agent."""
        gateways = FakeGateways()
        drive(["serve"], gateways)
        self.assertEqual([FakeGateways.DEFAULT_NAME], gateways.served)

    def test_a_gateway_that_refuses_to_run_ends_well(self):
        """R-GW-25 — the machine starts a gateway again whenever it ends badly. One
        that will never start must therefore end well, or it is started every few
        seconds for as long as the machine is up."""
        for refusal in (FakeGateways.AlreadyRunning("already running"),
                        FakeGateways.Unfit("does not fit"),
                        FakeGateways.NotAName("not a name")):
            with self.subTest(refusal=type(refusal).__name__):
                code, said = drive(["serve"], FakeGateways(refuses=refusal))
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
        code, said = drive(["start"], FakeGateways(starts_after=10_000), FakeMachine())
        self.assertEqual(1, code)
        self.assertIn("FAILED", said)
        self.assertIn("rundesk logs", said, "it did not say where to look")

    def test_starting_a_gateway_that_is_already_running_changes_nothing(self):
        """R-GW-13 — handing it over again would boot the running one out first."""
        machine = FakeMachine(jobs=["gateway"])
        gateways = FakeGateways(standing=[FakeGateways.Standing("gateway", running=True, pid=7)])
        code, said = drive(["start"], gateways, machine)
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
        code, said = drive(["start"], gateways, machine)
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
        code, said = drive(["start"], gateways, machine)
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
        code, said = drive(["start"], machine=FakeMachine(missing=True))
        self.assertEqual(1, code)
        self.assertIn("serve", said, "it did not say how to run one without a supervisor")

    def test_a_machine_that_refuses_the_job_is_not_reported_as_success(self):
        """R-GW-13"""
        code, said = drive(["start"], machine=FakeMachine(refuses=True))
        self.assertEqual(1, code)


class StandingGatewaysDown(unittest.TestCase):
    def test_stopping_a_named_gateway_stops_that_one(self):
        """R-GW-13"""
        machine = FakeMachine(jobs=["agent-one", "agent-two"])
        drive(["stop", "agent-one"], machine=machine)
        self.assertEqual([("stop", "agent-one")], machine.did)

    def test_stopping_without_a_name_stops_every_gateway(self):
        """R-GW-14 — naming none and meaning one is the ambiguity worth refusing;
        naming none and meaning all of them is what shutting a machine down wants."""
        machine = FakeMachine(jobs=["agent-one", "agent-two"])
        drive(["stop"], machine=machine)
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

    def test_stopping_where_there_is_nothing_to_stop_says_so(self):
        """R-GW-13"""
        code, said = drive(["stop"], machine=FakeMachine(jobs=[]))
        self.assertEqual(0, code)
        self.assertIn("no gateway", said)


class WhatIsRunningRightNow(unittest.TestCase):
    def test_status_where_there_is_nothing_says_so(self):
        """R-GW-14"""
        code, said = drive(["status"])
        self.assertEqual(0, code)
        self.assertIn("no gateways", said)

    def test_status_says_which_gateways_are_up(self):
        """R-GW-9, R-GW-14"""
        gateways = FakeGateways(standing=[
            FakeGateways.Standing("agent-one", running=True, pid=42, version="0.1.1"),
            FakeGateways.Standing("agent-two", running=False),
        ])
        code, said = drive(["status"], gateways, FakeMachine(jobs=["agent-one"]))
        self.assertIn("RUNNING", said)
        self.assertIn("42", said)
        self.assertIn("STOPPED", said)

    def test_status_says_what_each_gateway_has_in_flight(self):
        """R-GW-9 — what is being worked on is the question an owner actually has."""
        gateways = FakeGateways(
            standing=[FakeGateways.Standing("agent-one", running=True, pid=7, version="0.1.1")],
            working={"agent-one": ["a-conversation", "another"]},
        )
        _, said = drive(["status"], gateways)
        self.assertIn("2 (", said)
        self.assertIn("a-conversation", said)

    def test_status_tells_a_wedged_gateway_from_a_working_one(self):
        """R-GW-9 — the distinction no supervisor makes for you: up, and not going round."""
        gateways = FakeGateways(standing=[
            FakeGateways.Standing("stuck", running=True, pid=9, version="0.1.1", stale=True)])
        _, said = drive(["status"], gateways)
        self.assertIn("WEDGED", said)

    def test_status_shows_a_gateway_the_machine_keeps_but_which_is_not_running(self):
        """R-GW-10 — the machine believing it has one is not the same as one being there."""
        _, said = drive(["status"], FakeGateways(), FakeMachine(jobs=["agent-one"]))
        self.assertIn("agent-one", said)
        self.assertIn("STOPPED", said)

    def test_status_says_a_gateway_is_not_supervised_when_the_machine_dropped_it(self):
        """R-GW-9 — a job description in a directory is not a job being kept, and they
        come apart exactly when something has gone wrong."""
        gateways = FakeGateways(standing=[FakeGateways.Standing("gateway", running=False)])
        machine = FakeMachine(jobs=["gateway"])
        machine.loaded = lambda name: False   # the supervisor no longer has it
        _, said = drive(["status"], gateways, machine)
        self.assertIn("STOPPED", said)
        self.assertIn("no", said, "it did not say the machine had stopped keeping it")


class WhatAGatewayRunsOnItsOwn(unittest.TestCase):
    def setUp(self):
        self.written = pathlib.Path(tempfile.mkdtemp(prefix="rundesk-cli-sched-")) / "gateway.log"
        self.addCleanup(shutil.rmtree, self.written.parent, True)
        self.written.write_text("")

    def _gateways(self, **kw):
        return FakeGateways(written=self.written, **kw)

    def test_a_gateway_with_no_schedules_says_so(self):
        """R-SCH-8"""
        code, said = drive(["schedules"], self._gateways())
        self.assertEqual(0, code)
        self.assertIn("NO SCHEDULES", said)

    def test_schedules_are_listed_with_when_each_next_runs(self):
        """R-SCH-8 — what is scheduled, when it next runs, and what became of it last."""
        gateways = self._gateways(
            schedules={"gateway": [{"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]}]},
            ran_schedules={"gateway": {"tidy": {"at": "2026-07-25 03:00", "outcome": "finished"}}})
        code, said = drive(["schedules"], gateways)
        self.assertEqual(0, code)
        for expected in ("tidy", "0 3 * * *", "2026-07-25 03:00", "finished"):
            self.assertIn(expected, said)

    def test_a_schedule_that_is_off_is_kept_and_shown_as_off(self):
        """R-SCH-11 — keeping one without running it is the whole point of turning it off."""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "paused", "when": "* * * * *", "run": ["/bin/echo"], "enabled": False}]})
        _, said = drive(["schedules"], gateways)
        self.assertIn("paused", said)
        self.assertIn("OFF", said)

    def test_a_schedule_nobody_can_understand_is_named_and_the_rest_still_listed(self):
        """R-SCH-10"""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "good", "when": "0 3 * * *", "run": ["/bin/echo"]},
            {"name": "bad", "when": "nonsense"}]})
        code, said = drive(["schedules"], gateways)
        self.assertEqual(1, code)
        self.assertIn("good", said)
        self.assertIn("NOT UNDERSTOOD", said)

    def test_a_schedule_is_added_and_shows_when_it_next_runs(self):
        """R-SCH-1, R-SCH-8"""
        gateways = self._gateways()
        code, said = drive(["schedules", "add", "tidy", "--when", "*/5 * * * *",
                            "--run", "/bin/echo", "hi"], gateways)
        self.assertEqual(0, code)
        self.assertIn("ADDED", said)
        self.assertEqual([{"name": "tidy", "when": "*/5 * * * *", "run": ["/bin/echo", "hi"]}],
                         gateways.written_schedules("gateway"))
        self.assertIn("added", self.written.read_text(), "the change was not written to the log")

    def test_a_schedule_nobody_could_act_on_is_never_added(self):
        """R-SCH-1 — refused where it is written, not discovered when it fails to run."""
        gateways = self._gateways()
        code, said = drive(["schedules", "add", "bad", "--when", "99 * * * *",
                            "--run", "/bin/echo"], gateways)
        self.assertEqual(1, code)
        self.assertIn("NOT ADDED", said)
        self.assertEqual([], gateways.written_schedules("gateway"))

    def test_a_schedule_naming_nothing_to_run_is_never_added(self):
        """R-SCH-2"""
        gateways = self._gateways()
        code, said = drive(["schedules", "add", "empty", "--when", "* * * * *", "--run"], gateways)
        self.assertEqual(1, code)
        self.assertIn("NOT ADDED", said)

    def test_a_schedule_naming_a_program_rather_than_locating_it_is_never_added(self):
        """R-SCH-1, R-PROC-2 — refused where it is written, not discovered at three in
        the morning. The gateway runs with almost no PATH, so a bare name resolves in the
        shell that typed it and nowhere else. Written down, it failed every time it fell
        due — with nothing said anywhere an owner reads, and LAST RUN stuck at '-'."""
        gateways = self._gateways()
        code, said = drive(["schedules", "add", "nightly", "--when", "0 3 * * *",
                            "--run", "codex", "exec"], gateways)
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
        code, said = drive(["schedules", "add", "tidy", "--when", "* * * * *",
                            "--run", "/bin/echo"], gateways)
        self.assertEqual(1, code)
        self.assertIn("EXISTS", said)
        self.assertEqual(1, len(gateways.written_schedules("gateway")))

    def test_a_schedule_is_taken_away(self):
        """R-SCH-8"""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]},
            {"name": "other", "when": "0 4 * * *", "run": ["/bin/echo"]}]})
        code, said = drive(["schedules", "remove", "tidy"], gateways)
        self.assertEqual(0, code)
        self.assertIn("REMOVED", said)
        self.assertEqual(["other"], [one["name"] for one in gateways.written_schedules("gateway")])
        self.assertIn("removed", self.written.read_text())

    def test_a_schedule_is_turned_off_and_on_again_without_being_lost(self):
        """R-SCH-11"""
        gateways = self._gateways(schedules={"gateway": [
            {"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo"]}]})
        drive(["schedules", "off", "tidy"], gateways)
        self.assertIs(False, gateways.written_schedules("gateway")[0]["enabled"])
        drive(["schedules", "on", "tidy"], gateways)
        kept = gateways.written_schedules("gateway")
        self.assertIs(True, kept[0]["enabled"])
        self.assertEqual(1, len(kept), "turning one off and on again lost it")
        self.assertIn("turned off", self.written.read_text())
        self.assertIn("turned on", self.written.read_text())

    def test_changing_a_schedule_that_is_not_there_says_so(self):
        """R-SCH-8"""
        for act in ("remove", "on", "off"):
            with self.subTest(act=act):
                code, said = drive(["schedules", act, "nope"], self._gateways())
                self.assertEqual(1, code)
                self.assertIn("NOT FOUND", said)

    def test_schedules_are_asked_for_and_changed_on_one_gateway_only(self):
        """R-SCH-13, R-SCH-14 — a gateway's schedules are its own, which is what makes
        one agent's schedules that agent's alone."""
        gateways = self._gateways(schedules={"agent-two": [
            {"name": "theirs", "when": "* * * * *", "run": ["/bin/echo"]}]})
        _, said = drive(["schedules", "--gateway", "agent-one"], gateways)
        self.assertIn("NO SCHEDULES", said)
        drive(["schedules", "add", "mine", "--when", "* * * * *", "--run", "/bin/echo"], gateways)
        self.assertEqual(["theirs"], [one["name"] for one in gateways.written_schedules("agent-two")])


class WhatAGatewayHasBeenSaying(unittest.TestCase):
    def setUp(self):
        self.written = pathlib.Path(tempfile.mkdtemp(prefix="rundesk-cli-log-")) / "gateway.log"
        self.addCleanup(shutil.rmtree, self.written.parent, True)

    def test_logs_shows_what_a_gateway_wrote(self):
        """R-GW-18"""
        self.written.write_text("first\nsecond\nthird\n")
        code, said = drive(["logs"], FakeGateways(written=self.written))
        self.assertEqual(0, code)
        self.assertIn("second", said)

    def test_logs_shows_the_last_of_it_rather_than_all_of_it(self):
        """R-GW-18 — a gateway up for a month has more than anyone wants at once."""
        self.written.write_text("".join(f"line {i}\n" for i in range(500)))
        _, said = drive(["logs", "-n", "5"], FakeGateways(written=self.written))
        self.assertIn("line 499", said)
        self.assertNotIn("line 100", said)

    def test_logs_for_a_gateway_that_has_said_nothing_says_so(self):
        """R-GW-18 — and does not print an empty answer as though that were the log."""
        code, said = drive(["logs"], FakeGateways(written=self.written))
        self.assertEqual(1, code)
        self.assertIn("nothing written yet", said)

    def test_a_log_that_cannot_be_read_is_reported_rather_than_crashing(self):
        """R-GW-18 — every other verb answers in our words when it cannot do the thing."""
        self.written.write_text("something\n")
        self.written.chmod(0o000)
        self.addCleanup(self.written.chmod, 0o600)
        code, said = drive(["logs"], FakeGateways(written=self.written))
        self.assertEqual(1, code)
        self.assertIn("could not read", said)

    def test_asking_for_none_of_the_log_shows_none_of_it(self):
        """R-GW-18 — a slice of minus nothing is the whole file."""
        self.written.write_text("first\nsecond\n")
        _, said = drive(["logs", "-n", "0"], FakeGateways(written=self.written))
        self.assertNotIn("first", said)

    def test_what_a_gateway_wrote_is_readable_after_it_has_gone(self):
        """R-GW-18 — the case the log exists for."""
        self.written.write_text("up\nsomething went wrong\ndown\n")
        _, said = drive(["logs"], FakeGateways(written=self.written))
        self.assertIn("something went wrong", said)


if __name__ == "__main__":
    unittest.main(verbosity=2)
