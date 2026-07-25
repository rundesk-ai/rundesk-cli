"""Handing a gateway to the machine — the rows of platform-gateway about staying up.

No launchd is involved. What the machine is asked is a function passed in, so every case
here runs on any machine, including one with no supervisor at all.
"""

import pathlib
import plistlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk_cli import supervisor  # noqa: E402


class Machine:
    """A stand-in for the machine that behaves like the real one.

    It keeps whether a job is loaded, and it answers accordingly — because a stand-in
    that says yes to everything cannot fail the way the real one does, and that is
    exactly how a broken `start` passed every test it had.

    `slow_to_let_go` is the real behaviour that broke it: taking a job away returns
    before the machine has finished doing it, and offering a replacement into that gap
    is refused.
    """

    def __init__(self, refuse=(), slow_to_let_go: int = 0):
        self.asked: list[tuple] = []
        self.refuse = refuse
        self.holding: set[str] = set()
        self.slow_to_let_go = slow_to_let_go
        self._letting_go: dict[str, int] = {}

    def __call__(self, *args: str) -> supervisor.Spoke:
        self.asked.append(args)
        verb, target = args[0], args[-1]
        name = target.rsplit(".", 1)[-1] if verb != "bootstrap" else None
        if verb in self.refuse:
            return supervisor.Spoke(False, "the machine said no")
        if verb == "bootout":
            if name not in self.holding:
                return supervisor.Spoke(False, "Boot-out failed: 3: No such process")
            self._letting_go[name] = self.slow_to_let_go
            if not self.slow_to_let_go:
                self.holding.discard(name)
            return supervisor.Spoke(True, "")
        if verb == "print":
            left = self._letting_go.get(name, 0)
            if left:
                self._letting_go[name] = left - 1
                if left - 1 == 0:
                    self.holding.discard(name)
            return supervisor.Spoke(name in self.holding, "")
        if verb == "bootstrap":
            loaded = pathlib.Path(args[-1]).name[: -len(".plist")]
            named = loaded[len(supervisor.PREFIX) + 1:]
            if named in self.holding:
                return supervisor.Spoke(False, "Bootstrap failed: 5: Input/output error")
            self.holding.add(named)
            return supervisor.Spoke(True, "")
        if verb in ("kickstart", "kill"):
            return supervisor.Spoke(name in self.holding, "")
        return supervisor.Spoke(True, "")

    def verbs(self) -> list[str]:
        return [asked[0] for asked in self.asked]


class WithAJobDirectory(unittest.TestCase):
    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-jobs-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.root = Path(tempfile.mkdtemp(prefix="rundesk-root-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "rundesk").write_text("#!/usr/bin/env python3\n")
        self.logs = self.where / "logs"
        self.machine = Machine()

    def written(self, name: str = "gateway") -> dict:
        with open(supervisor.job_path(name, str(self.where)), "rb") as file:
            return plistlib.load(file)


class WhatTheJobSays(WithAJobDirectory):
    def test_the_job_runs_the_command_this_install_placed(self):
        """R-GW-1 — the machine hands a job almost no path, so a command named rather
        than located is a command it cannot find."""
        runs = supervisor.describe("gateway", self.root, self.logs)["ProgramArguments"]
        self.assertEqual([str(self.root / "rundesk"), "serve", "gateway"], runs)
        self.assertTrue(Path(runs[0]).is_absolute())

    def test_the_job_is_named_for_the_gateway_it_runs(self):
        """R-GW-4 — one job each, so cycling one leaves the others alone. A shared name
        would have starting the second evict the first."""
        self.assertNotEqual(
            supervisor.describe("agent-one", self.root)["Label"],
            supervisor.describe("agent-two", self.root)["Label"],
        )
        self.assertIn("agent-one", supervisor.describe("agent-one", self.root)["Label"])

    def test_the_machine_is_told_to_start_it_at_load_and_keep_it_up(self):
        """R-GW-1, R-GW-2, R-GW-3"""
        job = supervisor.describe("gateway", self.root)
        self.assertTrue(job["RunAtLoad"])
        self.assertIn("KeepAlive", job)

    def test_a_gateway_that_ended_well_is_not_started_again(self):
        """R-GW-25 — a gateway refusing to run ends well on purpose. Told to bring it
        back regardless, the machine would start it every few seconds forever, which is
        the failure the refusal exists to prevent."""
        self.assertEqual({"SuccessfulExit": False}, supervisor.describe("gateway", self.root)["KeepAlive"])

    def test_a_gateway_that_cannot_start_is_not_started_as_fast_as_the_machine_can(self):
        """R-GW-25"""
        self.assertGreater(supervisor.describe("gateway", self.root)["ThrottleInterval"], 0)

    def test_what_it_says_goes_somewhere_a_person_can_read(self):
        """R-GW-18"""
        job = supervisor.describe("gateway", self.root, self.logs)
        self.assertTrue(job["StandardOutPath"].startswith(str(self.logs)))
        self.assertTrue(job["StandardErrorPath"].startswith(str(self.logs)))

    def test_the_job_is_written_where_the_machine_looks(self):
        """R-GW-1"""
        path = supervisor.write("gateway", self.root, self.logs, str(self.where))
        self.assertTrue(path.exists())
        self.assertEqual(supervisor.describe("gateway", self.root, self.logs)["Label"],
                         self.written()["Label"])


class OnlyWhatThisInstallWrote(WithAJobDirectory):
    """A job named like ours is not necessarily ours."""

    def _foreign(self, name: str) -> Path:
        path = supervisor.job_path(name, str(self.where))
        with open(path, "wb") as file:
            plistlib.dump({"Label": supervisor.label(name),
                           "ProgramArguments": ["/somewhere/else/rundesk", "serve", name]}, file)
        return path

    def test_a_job_this_install_wrote_is_ours(self):
        """R-GW-13"""
        path = supervisor.write("gateway", self.root, self.logs, str(self.where))
        self.assertTrue(supervisor.ours(path, self.root))

    def test_a_job_another_install_wrote_is_not_ours(self):
        """R-GW-13 — standing this one down would take somebody else's agents with it."""
        self.assertFalse(supervisor.ours(self._foreign("agent-codex"), self.root))

    def test_a_job_that_cannot_be_read_is_not_ours(self):
        """R-GW-13"""
        path = supervisor.job_path("broken", str(self.where))
        path.write_text("this is not a job")
        self.assertFalse(supervisor.ours(path, self.root))

    def test_only_our_jobs_are_listed(self):
        """R-GW-13 — what `status` and a bare `stop` act on."""
        supervisor.write("ours", self.root, self.logs, str(self.where))
        self._foreign("theirs")
        self.assertEqual(["ours"], supervisor.described(str(self.where), self.root))

    def test_a_job_belonging_to_someone_else_is_not_known_to_us(self):
        """R-GW-13"""
        self._foreign("theirs")
        self.assertFalse(supervisor.known("theirs", str(self.where), self.root))
        supervisor.write("ours", self.root, self.logs, str(self.where))
        self.assertTrue(supervisor.known("ours", str(self.where), self.root))

    def test_someone_elses_job_is_never_removed(self):
        """R-GW-13"""
        self._foreign("theirs")
        with self.assertRaises(supervisor.NotOurs):
            supervisor.remove("theirs", str(self.where), self.root, asking=self.machine)
        self.assertTrue(supervisor.job_path("theirs", str(self.where)).exists())
        self.assertEqual([], self.machine.verbs(), "it asked the machine anyway")

    def test_someone_elses_job_is_never_handed_to_the_machine_as_ours(self):
        """R-GW-13 — the worst of the four, and the one that was missing: handing over
        boots the old job out and then writes over it, so a job belonging to something
        else is both stopped and destroyed, in the most ordinary verb there is."""
        path = self._foreign("mybot")
        was = path.read_bytes()
        with self.assertRaises(supervisor.NotOurs):
            supervisor.install("mybot", self.root, self.logs, str(self.where), self.machine)
        self.assertEqual(was, path.read_bytes(), "it overwrote a job it did not write")
        self.assertEqual([], self.machine.verbs(), "it asked the machine to boot out someone else's job")

    def test_someone_elses_job_is_never_stopped_or_started(self):
        """R-GW-13"""
        self._foreign("theirs")
        for act in (supervisor.stop, supervisor.start):
            with self.assertRaises(supervisor.NotOurs):
                act("theirs", str(self.where), self.root, asking=self.machine)
        self.assertEqual([], self.machine.verbs())


class ANameIsNotAPath(WithAJobDirectory):
    async_safe = True

    def test_no_job_is_written_for_a_name_that_would_escape(self):
        """R-GW-20 — a job is a login-persistence mechanism the machine keeps running,
        so a name that reaches outside where jobs belong plants one wherever it likes."""
        from rundesk_cli import gateway as gw
        bad = "../../../../../../tmp/rundesk-escaped"
        for builds in (supervisor.label, supervisor.job_path):
            with self.assertRaises(gw.NotAName, msg=f"{builds.__name__} accepted it"):
                builds(bad)
        with self.assertRaises(gw.NotAName):
            supervisor.install(bad, self.root, self.logs, str(self.where), self.machine)
        self.assertEqual([], self.machine.verbs(), "it asked the machine about it anyway")


class WaitingOnTheMachine(WithAJobDirectory):
    def _asking(self, answering):
        """Stand in for the machine, and hand back what `ask` asked of it."""
        import subprocess as sub
        asked = {}
        self.addCleanup(setattr, supervisor.subprocess, "run", supervisor.subprocess.run)
        self.addCleanup(setattr, supervisor, "available", supervisor.available)
        supervisor.available = lambda: True

        def machine(*args, **kwargs):
            asked.update(kwargs)
            return answering(sub, kwargs)

        supervisor.subprocess.run = machine
        return asked

    def test_the_machine_is_never_waited_on_without_a_bound(self):
        """R-GW-13 — three verbs an owner types reach the machine, and nothing rundesk
        does may wait on an answer forever. Asserted on what is *asked* of the machine,
        because a stand-in that gives up regardless would prove this either way."""
        asked = self._asking(lambda sub, kwargs: sub.CompletedProcess([], 0, "", ""))
        supervisor.ask("bootstrap")
        self.assertIn("timeout", asked, "it asked the machine and would have waited forever")
        self.assertGreater(asked["timeout"], 0)

    def test_a_machine_that_does_not_answer_in_time_is_given_up_on(self):
        """R-GW-13 — and reported, rather than raising out of whatever verb was typed."""
        def times_out(sub, kwargs):
            raise sub.TimeoutExpired(cmd="launchctl", timeout=kwargs["timeout"])

        self._asking(times_out)
        said = supervisor.ask("bootstrap")
        self.assertFalse(said.ok)
        self.assertIn("did not answer", said.said)


class TakingItAllBack(WithAJobDirectory):
    """What removing rundesk has to do before anything is deleted."""

    def setUp(self):
        super().setUp()
        self.stopped = []

    def _standing(self, running=()):
        """A stand-in for asking a gateway whether it is still there."""
        class Standing:
            def __init__(self, name):
                self.name, self.running = name, name in running
        return Standing

    def test_removing_rundesk_stops_every_gateway_it_was_keeping(self):
        """R-RM-9 — a job outlives the command it names: the gateway keeps running,
        because deleting a program does not stop one, and the machine goes on trying to
        start it again every few seconds and at every login, against a path that is no
        longer there."""
        for name in ("agent-one", "agent-two"):
            supervisor.install(name, self.root, self.logs, str(self.where), self.machine)
        taken, stubborn = supervisor.take_all_back(
            str(self.where), self.root, self.machine, standing=self._standing())
        self.assertEqual(["agent-one", "agent-two"], sorted(taken))
        self.assertEqual([], stubborn)
        self.assertEqual([], supervisor.described(str(self.where), self.root))
        self.assertIn("bootout", self.machine.verbs())

    def test_removing_rundesk_leaves_a_job_it_did_not_write(self):
        """R-RM-3, R-RM-9 — someone else's agents are not ours to stand down, even on
        the way out."""
        path = supervisor.job_path("theirs", str(self.where))
        with open(path, "wb") as file:
            plistlib.dump({"Label": supervisor.label("theirs"),
                           "ProgramArguments": ["/somewhere/else/rundesk", "serve", "theirs"]}, file)
        taken, stubborn = supervisor.take_all_back(
            str(self.where), self.root, self.machine, standing=self._standing())
        self.assertEqual(([], []), (taken, stubborn))
        self.assertTrue(path.exists(), "it removed a job belonging to something else")

    def test_a_gateway_that_will_not_stop_is_reported_rather_than_assumed(self):
        """R-RM-9 — removal must not claim to have stopped what is still running."""
        supervisor.install("stubborn", self.root, self.logs, str(self.where), self.machine)
        self.addCleanup(setattr, supervisor, "SETTLE_SECONDS", supervisor.SETTLE_SECONDS)
        supervisor.SETTLE_SECONDS = 0.3
        taken, stubborn = supervisor.take_all_back(
            str(self.where), self.root, self.machine,
            standing=self._standing(running=("stubborn",)))
        self.assertEqual([], taken)
        self.assertEqual(["stubborn"], stubborn)

    def test_removing_rundesk_where_nothing_was_ever_started_is_ordinary(self):
        """R-RM-9"""
        self.assertEqual(([], []), supervisor.take_all_back(
            str(self.where), self.root, self.machine, standing=self._standing()))


class TheJobCarriesWhereThingsAre(WithAJobDirectory):
    def test_the_job_says_where_this_install_keeps_things(self):
        """R-GW-9 — the machine hands a job almost nothing. Without this a supervised
        gateway uses the default places while the command that started it reads wherever
        it was pointed, and the two then disagree about whether anything is running —
        which reads as a gateway that will not start, however many times you try."""
        import os
        for name, value in (("RUNDESK_RUN_DIR", "/tmp/rd-test-run"),
                            ("RUNDESK_LOG_DIR", "/tmp/rd-test-logs"),
                            ("RUNDESK_JOBS_DIR", "/tmp/rd-test-jobs")):
            self.addCleanup(os.environ.pop, name, None)
            os.environ[name] = value
        said = supervisor.describe("gateway", self.root)["EnvironmentVariables"]
        self.assertEqual("/tmp/rd-test-run", said["RUNDESK_RUN_DIR"])
        self.assertEqual("/tmp/rd-test-logs", said["RUNDESK_LOG_DIR"])
        self.assertEqual("/tmp/rd-test-jobs", said["RUNDESK_JOBS_DIR"])


class HandingItOver(WithAJobDirectory):
    def test_handing_a_gateway_over_writes_the_job_and_asks_the_machine_to_take_it(self):
        """R-GW-1"""
        said = supervisor.install("gateway", self.root, self.logs, str(self.where), self.machine)
        self.assertTrue(said.ok)
        self.assertTrue(supervisor.job_path("gateway", str(self.where)).exists())
        self.assertIn("bootstrap", self.machine.verbs())

    def test_an_older_job_of_the_same_name_goes_first(self):
        """R-GW-4 — two jobs for one gateway would have the machine starting a second
        that immediately refuses, over and over."""
        supervisor.install("gateway", self.root, self.logs, str(self.where), self.machine)
        self.assertEqual("bootout", self.machine.verbs()[0])
        self.assertEqual("bootstrap", self.machine.verbs()[-1])

    def test_handing_the_same_gateway_over_twice_running_works_both_times(self):
        """R-GW-1 — the machine finishes taking a job away *after* saying it has, and
        offering the replacement into that gap is refused with an error that says
        nothing about timing. Left unwaited, every second attempt fails — and the failed
        one leaves no job at all, so it alternates forever."""
        machine = Machine(slow_to_let_go=3)
        for attempt in range(4):
            said = supervisor.install("gateway", self.root, self.logs, str(self.where), machine)
            self.assertTrue(said.ok, f"attempt {attempt + 1} was refused: {said.said}")
            self.assertTrue(supervisor.loaded("gateway", machine))

    def test_whether_the_machine_has_a_job_is_asked_of_the_machine(self):
        """R-GW-9 — a job description in a directory is not a job the machine is
        keeping. The two come apart the moment one is taken away without the file going
        too, and a file read as a job tells an owner they are looked after when they are
        not."""
        supervisor.write("gateway", self.root, self.logs, str(self.where))
        self.assertTrue(supervisor.known("gateway", str(self.where), self.root))
        self.assertFalse(supervisor.loaded("gateway", self.machine),
                         "a job file was read as the machine keeping it")

    def test_a_machine_that_will_not_take_it_is_reported_rather_than_assumed(self):
        """R-GW-1 — an install that reports success it did not earn is the thing this
        whole command surface refuses to do."""
        refusing = Machine(refuse=("bootstrap",))
        said = supervisor.install("gateway", self.root, self.logs, str(self.where), refusing)
        self.assertFalse(said.ok)

    def test_a_job_the_machine_would_not_let_go_of_is_kept_to_try_again(self):
        """R-RM-9 — the description is what a second attempt needs. Deleting it after a
        refusal leaves a job the machine is still keeping and nothing left to name it
        with, so the next attempt asks the machine for nothing at all."""
        # One machine throughout, which takes the job and then will not let it go —
        # two of them would mean removing from a machine that never had it.
        machine = Machine(refuse=("bootout",))
        supervisor.install("stubborn", self.root, self.logs, str(self.where), machine)
        self.assertTrue(supervisor.loaded("stubborn", machine))
        said = supervisor.remove("stubborn", str(self.where), self.root, asking=machine)
        self.assertFalse(said.ok)
        self.assertTrue(supervisor.job_path("stubborn", str(self.where)).exists(),
                        "the job was forgotten while the machine still had it")
        self.assertEqual(["stubborn"], supervisor.described(str(self.where), self.root))

    def test_a_job_the_machine_never_had_is_forgotten_even_if_it_refuses(self):
        """R-RM-9 — refusing to boot out something that was never loaded is the ordinary
        case, and keeping the file for it would leave it there forever."""
        supervisor.write("never-loaded", self.root, self.logs, str(self.where))
        empty = Machine()   # holding nothing, so bootout fails and `loaded` is false
        said = supervisor.remove("never-loaded", str(self.where), self.root, asking=empty)
        self.assertFalse(said.ok)
        self.assertFalse(supervisor.job_path("never-loaded", str(self.where)).exists())

    def test_taking_a_gateway_back_forgets_the_job_entirely(self):
        """R-GW-12"""
        supervisor.install("gateway", self.root, self.logs, str(self.where), self.machine)
        supervisor.remove("gateway", str(self.where), self.root, asking=self.machine)
        self.assertFalse(supervisor.job_path("gateway", str(self.where)).exists())
        self.assertEqual([], supervisor.described(str(self.where), self.root))

    def test_a_machine_with_nothing_to_hand_it_to_says_so(self):
        """R-GW-1 — rundesk supervises nothing itself, so a machine without a supervisor
        is something an owner has to be told about rather than left to guess at."""
        self.addCleanup(setattr, supervisor, "available", supervisor.available)
        supervisor.available = lambda: False
        with self.assertRaises(supervisor.NoSupervisor):
            supervisor.ask("bootstrap")

    def test_nothing_is_listed_where_no_job_was_ever_written(self):
        """R-GW-13"""
        self.assertEqual([], supervisor.described(str(self.where / "nowhere"), self.root))


if __name__ == "__main__":
    unittest.main()
