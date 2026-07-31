"""Handing a gateway to the machine — the rows of platform-gateway about staying up.

No launchd is involved. What the machine is asked is a function passed in, so every case
here runs on any machine, including one with no supervisor at all.
"""

import os
import pathlib
import plistlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import supervisor  # noqa: E402


class Machine:
    """A stand-in for the machine that behaves like the real one.

    It keeps whether a job is loaded, and it answers accordingly — because a stand-in
    that says yes to everything cannot fail the way the real one does, and that is
    exactly how a broken `start` passed every test it had.

    `slow_to_let_go` is the real behaviour that broke it: taking a job away returns
    before the machine has finished doing it, and offering a replacement into that gap
    is refused.
    """

    def __init__(self, refuse=(), slow_to_let_go: int = 0, deaf=()):
        self.asked: list[tuple] = []
        self.refuse = refuse
        #: Verbs the machine is too busy to answer at all. Told apart from `refuse`
        #: because the real one tells them apart: a question that timed out has said
        #: nothing, and a stand-in that answered "no" for both could not fail the way
        #: a loaded machine does.
        self.deaf = deaf
        self.holding: set[str] = set()
        self.slow_to_let_go = slow_to_let_go
        self._letting_go: dict[str, int] = {}

    def __call__(self, *args: str) -> supervisor.Spoke:
        self.asked.append(args)
        verb, target = args[0], args[-1]
        name = target.rsplit(".", 1)[-1] if verb != "bootstrap" else None
        if verb != "bootstrap" and target.endswith("/" + supervisor.update_label()):
            name = supervisor.update_label()
        if verb != "bootstrap" and target.endswith(
                "/" + supervisor.automatic_update_label()):
            name = supervisor.automatic_update_label()
        if verb in self.deaf:
            return supervisor.Spoke(False, "the machine did not answer in time", answered=False)
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
            named = (
                supervisor.update_label()
                if loaded == supervisor.update_label()
                else supervisor.automatic_update_label()
                if loaded == supervisor.automatic_update_label()
                else loaded[len(supervisor.prefix()) + 1:]
            )
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
    """Every case here, with the wait on the machine turned down.

    How long rundesk gives launchd to finish letting go is real seconds in the wild and
    nothing worth spending here: what is asserted is that it waits and then answers
    honestly, not the duration. Set once for every case rather than per test, because the
    two that most need it are the ones nobody remembers to turn down — the ones where the
    machine never lets go, which spend the whole patience by definition.

    **What this install calls its jobs is isolated here too**, beside the directories.
    The prefix is the one part of a job that is not a directory, so a fixture that
    redirects every path and leaves it alone is still reading the shell it was run from —
    and the shell this repo's own guide tells you to work in has it set. Three cases then
    fail for the person following that guide and for nobody else, which is the same shape
    as the trap they were written about.
    """

    SETTLE = 0.3

    def setUp(self):
        self.addCleanup(setattr, supervisor, "SETTLE_SECONDS", supervisor.SETTLE_SECONDS)
        supervisor.SETTLE_SECONDS = self.SETTLE
        # Taken out rather than pointed somewhere: unset is what rundesk ships, and a case
        # that wants a second install's name says so itself.
        restored = mock.patch.dict(os.environ)
        restored.start()
        self.addCleanup(restored.stop)
        os.environ.pop("RUNDESK_JOB_PREFIX", None)
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

    def _standing(self, running=()):
        """A stand-in for asking a gateway whether it is still there."""
        class Standing:
            def __init__(self, name):
                self.name, self.running = name, name in running
        return Standing

    def job_survives(self, name: str) -> bool:
        return supervisor.job_path(name, str(self.where)).exists()


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
        from rundesk import gateway as gw
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

    def test_removing_one_install_leaves_the_shared_jobs_another_install_wrote(self):
        """R-RM-15 — reported (#129): a gateway's job carries the gateway's name, so two
        installs never collide over one; the shared workers and the automatic-update job
        carry neither, so a second install finds the first install's job exactly where its
        own would go. Removing it would stop the machine updating the install somebody
        actually uses."""
        theirs = Path(tempfile.mkdtemp(prefix="rundesk-theirs-"))
        self.addCleanup(shutil.rmtree, theirs, True)
        (theirs / "rundesk").write_text("#!/usr/bin/env python3\n")
        supervisor.write_update_worker(theirs, self.logs, str(self.where))
        supervisor.write_restart_worker(theirs, self.logs, str(self.where))
        supervisor.write_automatic_update("03:00", theirs, self.logs, str(self.where))

        left = supervisor.remove_our_shared_jobs(str(self.where), self.root, self.machine)

        self.assertEqual([
            supervisor.update_label(), supervisor.restart_label(),
            supervisor.automatic_update_label(),
        ], left)
        self.assertTrue(supervisor.update_job_path(str(self.where)).exists(),
                        "it took another install's update worker")
        self.assertTrue(supervisor.restart_job_path(str(self.where)).exists(),
                        "it took another install's restart worker")
        self.assertTrue(supervisor.automatic_update_job_path(str(self.where)).exists(),
                        "it took another install's automatic-update job")

    def test_leaving_another_installs_jobs_alone_does_not_end_the_removal(self):
        """R-RM-15 — the refusal is right and escaping was not: uncaught, it ended the whole
        removal partway through and `install.sh` reported it as gateways that would not stop.
        Nothing on the machine says that, and a redirected install could not be uninstalled
        at all on any machine that already had an ordinary one."""
        theirs = Path(tempfile.mkdtemp(prefix="rundesk-theirs-"))
        self.addCleanup(shutil.rmtree, theirs, True)
        (theirs / "rundesk").write_text("#!/usr/bin/env python3\n")
        supervisor.write_automatic_update("03:00", theirs, self.logs, str(self.where))
        supervisor.install("mine", self.root, self.logs, str(self.where), self.machine)

        taken, stubborn = supervisor.take_all_back(
            str(self.where), self.root, self.machine, standing=self._standing())
        left = supervisor.remove_our_shared_jobs(str(self.where), self.root, self.machine)

        self.assertEqual((["mine"], []), (taken, stubborn), "its own gateway was not taken")
        self.assertEqual([supervisor.automatic_update_label()], left)

    def test_removing_the_install_that_wrote_the_shared_jobs_takes_them(self):
        """R-RM-9 — the ordinary case, unchanged: an install that wrote them removes them,
        and leaves nothing of itself behind."""
        supervisor.write_update_worker(self.root, self.logs, str(self.where))
        supervisor.write_restart_worker(self.root, self.logs, str(self.where))
        supervisor.write_automatic_update("03:00", self.root, self.logs, str(self.where))

        self.assertEqual([], supervisor.remove_our_shared_jobs(
            str(self.where), self.root, self.machine))
        self.assertFalse(supervisor.update_job_path(str(self.where)).exists())
        self.assertFalse(supervisor.restart_job_path(str(self.where)).exists())
        self.assertFalse(supervisor.automatic_update_job_path(str(self.where)).exists())

    def test_shared_jobs_that_were_never_written_are_not_a_refusal(self):
        """An install that never scheduled an update has nothing to leave alone, and a
        removal that reported one would be describing a job the machine does not have."""
        self.assertEqual([], supervisor.remove_our_shared_jobs(
            str(self.where), self.root, self.machine))

    def test_a_gateway_that_will_not_stop_is_reported_rather_than_assumed(self):
        """R-RM-9 — removal must not claim to have stopped what is still running."""
        supervisor.install("stubborn", self.root, self.logs, str(self.where), self.machine)
        taken, stubborn = supervisor.take_all_back(
            str(self.where), self.root, self.machine,
            standing=self._standing(running=("stubborn",)))
        self.assertEqual([], taken)
        self.assertEqual(["stubborn"], stubborn)

    def test_a_job_the_machine_still_holds_is_not_reported_as_taken_back(self):
        """R-RM-9 — two parties have to let go, and both are asked.

        Judged on the gateway process alone, a machine that refused to release its job
        was filed under 'taken back' as long as nothing was running. The installer then
        deleted rundesk, and the machine went on trying to start a command that was no
        longer there — every few seconds, and again at every login, forever.
        """
        machine = Machine(refuse=("bootout",))
        supervisor.install("held", self.root, self.logs, str(self.where), machine)
        taken, stubborn = supervisor.take_all_back(
            str(self.where), self.root, machine, standing=self._standing())
        self.assertEqual(([], ["held"]), (taken, stubborn))
        self.assertTrue(self.job_survives("held"), "it forgot a job the machine still holds")
        self.assertTrue(supervisor.loaded("held", machine))

    def test_a_machine_too_busy_to_answer_is_not_taken_as_having_nothing(self):
        """R-RM-9 — silence is not a no. A `print` that timed out has said nothing about
        whether the job is there, and reading it as 'no such job' deleted the only
        description a second attempt would have had, on nothing but a slow machine."""
        machine = Machine(refuse=("bootout",))
        supervisor.install("quiet", self.root, self.logs, str(self.where), machine)
        machine.deaf = ("print",)  # installed first, so the job really is there
        taken, stubborn = supervisor.take_all_back(
            str(self.where), self.root, machine, standing=self._standing())
        self.assertEqual(([], ["quiet"]), (taken, stubborn))
        self.assertTrue(self.job_survives("quiet"), "a timeout was read as 'there is no job'")

    def test_a_gateway_that_would_not_stop_can_still_be_found_next_time(self):
        """R-RM-9 — being reported as stubborn is only useful if something can act on it.

        The description was deleted as soon as the machine accepted the bootout, before
        anyone had waited on the gateway itself. The first attempt then said the name was
        stubborn and the second could not see it at all — with the thing still running.
        """
        supervisor.install("stubborn", self.root, self.logs, str(self.where), self.machine)
        still_up = self._standing(running=("stubborn",))
        first = supervisor.take_all_back(str(self.where), self.root, self.machine, standing=still_up)
        self.assertEqual(([], ["stubborn"]), first)
        self.assertTrue(self.job_survives("stubborn"))
        again = supervisor.take_all_back(str(self.where), self.root, self.machine, standing=still_up)
        self.assertEqual(([], ["stubborn"]), again, "a second attempt could not see it at all")

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
        # Every place rundesk can be pointed at. Asserted as a set rather than one by
        # one, because the fault this catches is one being *left out*: where schedules were
        # kept was, and a supervised gateway then read the default while `rundesk schedules
        # add` wrote where it was pointed — a schedule added, listed and shown as due by the
        # command line, and unknown to the gateway that would have run it. That one is gone
        # rather than fixed: a schedule is a row an agent keeps, so where agents are is the
        # whole of what has to agree.
        where = {
            "RUNDESK_RUN_DIR": "/tmp/rd-test-run",
            "RUNDESK_LOG_DIR": "/tmp/rd-test-logs",
            "RUNDESK_JOBS_DIR": "/tmp/rd-test-jobs",
            "RUNDESK_AGENTS_DIR": "/tmp/rd-test-agents",
        }
        for name, value in where.items():
            self.addCleanup(os.environ.pop, name, None)
            os.environ[name] = value
        said = supervisor.describe("gateway", self.root)["EnvironmentVariables"]
        for name, value in where.items():
            self.assertEqual(value, said.get(name), f"the job does not carry {name}")

    def test_the_job_carries_every_place_rundesk_can_be_pointed_at(self):
        """R-GW-9 — the guard on the one above: a new place to point rundesk that is
        added to the module and forgotten here leaves the supervised gateway reading
        somewhere else, which no test naming the variables by hand would ever notice."""
        import inspect
        import re as regex
        import rundesk as package
        from rundesk import agent as agents
        from rundesk import gateway as real

        # Read off what a supervised gateway actually asks the environment for, rather
        # than a list kept by hand here — a hand-kept list has the same gap as the one in
        # `describe` and goes stale in the same moment. All three, because an agent
        # resolves a directory of its own, the gateway the machine starts is an agent's,
        # and the root both of those default from is the package's: reading only some of
        # them is how the next one added is left out.
        pointed = set(regex.findall(
            r'environ\.get\("(RUNDESK_[A-Z_]+_DIR)"',
            inspect.getsource(real) + inspect.getsource(agents)
            + inspect.getsource(package)))
        self.assertTrue(pointed, "nothing reads a directory from the environment at all")
        said = supervisor.describe("gateway", self.root)["EnvironmentVariables"]
        for variable in sorted(pointed):
            self.assertIn(variable, said,
                          f"the gateway reads {variable}, and the job never tells it one")


    def test_the_job_carries_the_directories_it_was_given_rather_than_its_own(self):
        """R-AGT-9 — an agent keeps everything of its own in one directory, and which one
        that is has to reach the gateway the machine starts. Resolved here instead, a
        supervised agent would read the shared places while the command that started it
        wrote the agent's, and neither may be wrong about whether it is running."""
        said = supervisor.describe(
            "ava", self.root,
            logs=pathlib.Path("/nowhere/agents/ava/logs"),
            run=pathlib.Path("/nowhere/agents/ava/run"),
            agents=pathlib.Path("/nowhere/agents"),
        )["EnvironmentVariables"]
        self.assertEqual("/nowhere/agents/ava/run", said["RUNDESK_RUN_DIR"])
        self.assertEqual("/nowhere/agents/ava/logs", said["RUNDESK_LOG_DIR"])
        self.assertEqual("/nowhere/agents", said["RUNDESK_AGENTS_DIR"])


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
        one leaves no job at all, so it alternates forever.

        Given real patience rather than the file's turned-down default: this case is about
        a machine that takes several looks to let go, so it has to be allowed several.
        """
        supervisor.SETTLE_SECONDS = 2.0     # restored by setUp's cleanup
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
        empty = Machine()   # holding nothing, so bootout fails and it says so plainly
        taken, stubborn = supervisor.take_all_back(
            str(self.where), self.root, empty, standing=self._standing())
        self.assertEqual((["never-loaded"], []), (taken, stubborn))
        self.assertFalse(self.job_survives("never-loaded"))

    def test_taking_a_gateway_back_forgets_the_job_entirely(self):
        """R-GW-12"""
        supervisor.install("gateway", self.root, self.logs, str(self.where), self.machine)
        taken, _ = supervisor.take_all_back(
            str(self.where), self.root, self.machine, standing=self._standing())
        self.assertEqual(["gateway"], taken)
        self.assertFalse(self.job_survives("gateway"))
        self.assertEqual([], supervisor.described(str(self.where), self.root))

    def test_asking_the_machine_to_let_go_does_not_itself_forget_the_job(self):
        """R-RM-9 — `remove` asks; it does not decide. The description is the only thing
        that names a job, and whether it can go depends on the gateway too — which this
        cannot see. Forgetting here is what deleted the handle on a gateway that was
        still running, leaving every attempt after the first unable to find it at all."""
        supervisor.install("gateway", self.root, self.logs, str(self.where), self.machine)
        said = supervisor.remove("gateway", str(self.where), self.root, asking=self.machine)
        self.assertTrue(said.ok)
        self.assertTrue(self.job_survives("gateway"), "asking to let go forgot the job itself")

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


class WhereAJobCanFindThings(WithAJobDirectory):
    """R-GW-9 — what a supervised gateway can reach, which is only what the job says."""

    def test_a_job_can_find_the_tools_a_person_installed_for_themselves(self):
        """A brain is a program on the machine, and a person's own tools go in
        `~/.local/bin`. Left out, a fresh machine answers `the Codex CLI is not on this
        machine's path` while `which codex` in the owner's own shell finds it perfectly
        well — the shell has that directory and the job did not.

        It is rundesk's *own* default: `install.sh` puts the command there whenever
        `/usr/local/bin` is not writable, which on a machine without Homebrew is always. So
        rundesk installed itself into a directory it then would not look in."""
        said = supervisor.describe("gateway", self.root)["EnvironmentVariables"]["PATH"]
        self.assertIn(str(Path.home() / ".local" / "bin"), said.split(":"))

    def test_a_job_still_finds_what_the_machine_ships(self):
        """The guard on the one above: a PATH rebuilt around a person's own directory and
        losing the machine's own would find their brain and nothing else — no `git`, no
        `python3`, and a turn that fails on the first tool it reaches for."""
        said = supervisor.describe("gateway", self.root)["EnvironmentVariables"]["PATH"]
        for named in ("/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin"):
            self.assertIn(named, said.split(":"))

    def test_where_a_job_looks_is_resolved_rather_than_fixed_when_the_file_is_read(self):
        """A person's own directory is one person's, so a module-level string would write
        the developer's own into every job a suite wrote — the trap `MEMORY.md` records one
        level out, where a directory bound at import reached the real install."""
        was = Path.home()
        self.addCleanup(os.environ.pop, "HOME", None)
        os.environ["HOME"] = str(self.root / "somebody-else")
        self.assertIn(str(Path(self.root / "somebody-else") / ".local" / "bin"),
                      supervisor.path_for_a_job().split(":"))
        self.assertNotEqual(was, Path.home(), "HOME was not actually redirected")


class TheInstallsOwnDailyJob(WithAJobDirectory):
    """The job that belongs to the install rather than to any agent."""

    def written(self, at: str = "04:00"):
        return plistlib.loads(
            supervisor.write_backup(at, self.root, self.logs, str(self.where)).read_bytes())

    def test_the_daily_job_cannot_be_mistaken_for_a_gateway(self):
        """R-BKP-25 — gateways are found by globbing one namespace, so a daily backup named
        inside it would be reported as a gateway called `backup`: an uninstall would try to
        stop it as one, and an agent an owner really did call `backup` would collide with it
        outright. The glob wants a literal dot where this label has a hyphen, so it cannot
        match — structurally, rather than by anybody remembering to exclude it."""
        supervisor.write_backup("04:00", self.root, self.logs, str(self.where))
        supervisor.write("ava", self.root, self.logs, str(self.where))
        self.assertEqual(["ava"], supervisor.described(str(self.where), self.root))

    def test_an_agent_may_be_called_backup_without_colliding_with_the_daily_job(self):
        """R-BKP-25 — the collision the namespace exists to make impossible, asserted from
        the other side: the name an owner is most likely to choose is the one that would
        have overwritten the job."""
        supervisor.write_backup("04:00", self.root, self.logs, str(self.where))
        made = supervisor.write("backup", self.root, self.logs, str(self.where))
        self.assertNotEqual(made, supervisor.backup_job_path(str(self.where)))
        self.assertTrue(supervisor.keeps_backups(str(self.where)),
                        "an agent called backup wrote over the install's own job")

    def test_the_daily_job_runs_at_the_hour_it_was_given(self):
        """R-BKP-25 — an owner states a time of day. A period would drift against the clock
        and fire at a different hour after every restart."""
        said = self.written("04:30")
        self.assertEqual({"Hour": 4, "Minute": 30}, said["StartCalendarInterval"])
        self.assertEqual(["backups", "add"], said["ProgramArguments"][1:])

    def test_the_daily_job_is_never_kept_alive(self):
        """R-BKP-25 — every other job rundesk writes must stay up, and the key that keeps
        one up would start a job that finishes in a second again immediately, for ever."""
        said = self.written()
        self.assertNotIn("KeepAlive", said)
        self.assertFalse(said["RunAtLoad"],
                         "asking for a daily backup took one there and then")

    def test_the_daily_job_carries_where_backups_go(self):
        """R-BKP-25 — the machine hands a job almost nothing, so a backup started by it
        would otherwise write its copies somewhere the owner never looks."""
        self.assertIn("RUNDESK_BACKUP_DIR", self.written()["EnvironmentVariables"])

    def test_stopping_the_daily_job_takes_its_description_away_too(self):
        """R-BKP-25 — unlike a gateway's, nothing else names this job and it has no process
        that could outlive it. A description left behind is a job the machine picks up again
        at the next login, after an owner asked for it to stop."""
        supervisor.install_backup("04:00", self.root, self.logs, str(self.where), self.machine)
        self.assertTrue(supervisor.keeps_backups(str(self.where)))
        supervisor.remove_backup(str(self.where), asking=self.machine)
        self.assertFalse(supervisor.keeps_backups(str(self.where)),
                         "the job was left where the machine would find it again")


class TheExternalUpdateWorker(WithAJobDirectory):
    def written(self):
        return plistlib.loads(
            supervisor.write_update_worker(
                self.root, self.logs, str(self.where)
            ).read_bytes()
        )

    def test_the_update_worker_is_outside_the_gateway_namespace(self):
        """R-UPD-35"""
        supervisor.write_update_worker(self.root, self.logs, str(self.where))
        supervisor.write("ava", self.root, self.logs, str(self.where))
        self.assertEqual(["ava"], supervisor.described(str(self.where), self.root))

    def test_the_machine_owns_the_worker_that_may_stop_gateways(self):
        """R-UPD-35"""
        said = self.written()
        self.assertEqual(["update", "--worker"], said["ProgramArguments"][1:])
        self.assertTrue(said["RunAtLoad"])
        self.assertEqual({"SuccessfulExit": False}, said["KeepAlive"])

    def test_the_worker_carries_an_explicit_install_target(self):
        with mock.patch.dict(os.environ, {
            "RUNDESK_UPDATE_ROOT": str(self.where / "installed")
        }):
            said = self.written()
        self.assertEqual(
            str(self.where / "installed"),
            said["EnvironmentVariables"]["RUNDESK_UPDATE_ROOT"],
        )

    def test_installing_the_worker_loads_and_starts_it(self):
        supervisor.install_update_worker(
            self.root, self.logs, str(self.where), self.machine
        )
        verbs = [asked[0] for asked in self.machine.asked]
        self.assertIn("bootstrap", verbs)
        self.assertIn("kickstart", verbs)

    def test_the_loaded_worker_is_asked_of_the_machine_not_its_file(self):
        supervisor.write_update_worker(self.root, self.logs, str(self.where))
        self.assertFalse(supervisor.update_worker_loaded(self.machine))
        supervisor.install_update_worker(
            self.root, self.logs, str(self.where), self.machine
        )
        self.assertTrue(supervisor.update_worker_loaded(self.machine))

    def test_a_loaded_one_shot_worker_can_be_kicked_again(self):
        """R-UPD-45"""
        supervisor.kick_update_worker(self.machine)
        self.assertEqual("kickstart", self.machine.asked[-1][0])
        self.assertNotIn("-k", self.machine.asked[-1])

    def test_removing_an_install_with_no_worker_never_boots_out_another_one(self):
        said = supervisor.remove_update_worker(
            str(self.where), self.root, self.machine
        )
        self.assertTrue(said.ok)
        self.assertEqual([], self.machine.verbs())

    def test_an_install_never_removes_another_installs_worker(self):
        foreign = self.where / "foreign"
        (foreign / "rundesk").parent.mkdir(parents=True)
        (foreign / "rundesk").write_text("#!/usr/bin/env python3\n")
        path = supervisor.write_update_worker(
            foreign, self.logs, str(self.where)
        )
        with self.assertRaises(supervisor.NotOurs):
            supervisor.remove_update_worker(
                str(self.where), self.root, self.machine
            )
        self.assertTrue(path.exists())
        self.assertEqual([], self.machine.verbs())

    def test_an_install_removes_its_own_worker(self):
        path = supervisor.write_update_worker(
            self.root, self.logs, str(self.where)
        )
        self.machine.holding.add("ai.rundesk-update")
        said = supervisor.remove_update_worker(
            str(self.where), self.root, self.machine
        )
        self.assertTrue(said.ok)
        self.assertFalse(path.exists())
        self.assertIn("bootout", self.machine.verbs())


class AutomaticUpdates(WithAJobDirectory):
    def written(self):
        return plistlib.loads(
            supervisor.write_automatic_update(
                "03:00", self.root, self.logs, str(self.where)
            ).read_bytes()
        )

    def test_the_daily_trigger_defaults_to_three_in_the_morning(self):
        """R-UPD-42"""
        said = self.written()
        self.assertEqual(
            {"Hour": 3, "Minute": 0}, said["StartCalendarInterval"]
        )
        self.assertEqual(["update", "--automatic"], said["ProgramArguments"][1:])

    def test_the_daily_trigger_only_runs_when_the_calendar_fires(self):
        """R-UPD-42 — it queues a recoverable worker and ends, so keeping it alive would
        turn one daily event into an update loop."""
        said = self.written()
        self.assertFalse(said["RunAtLoad"])
        self.assertNotIn("KeepAlive", said)

    def test_the_daily_trigger_cannot_be_mistaken_for_a_gateway(self):
        """R-UPD-42"""
        supervisor.write_automatic_update(
            "03:00", self.root, self.logs, str(self.where)
        )
        supervisor.write("automatic-update", self.root, self.logs, str(self.where))
        self.assertEqual(
            ["automatic-update"],
            supervisor.described(str(self.where), self.root),
        )

    def test_installing_and_removing_the_daily_trigger_changes_only_its_job(self):
        """R-UPD-42"""
        path = supervisor.automatic_update_job_path(str(self.where))
        said = supervisor.install_automatic_update(
            "03:00", self.root, self.logs, str(self.where), self.machine
        )
        self.assertTrue(said.ok)
        self.assertTrue(path.exists())
        self.assertIn(supervisor.automatic_update_label(), self.machine.holding)

        removed = supervisor.remove_automatic_update(
            str(self.where), self.root, self.machine
        )
        self.assertTrue(removed.ok)
        self.assertFalse(path.exists())
        self.assertNotIn(supervisor.automatic_update_label(), self.machine.holding)

    def test_the_machine_is_given_the_owners_configured_time(self):
        """R-UPD-42"""
        said = supervisor.describe_automatic_update("21:45", self.root, self.logs)
        self.assertEqual(
            {"Hour": 21, "Minute": 45}, said["StartCalendarInterval"]
        )

    def test_changing_the_time_reloads_the_existing_daily_job(self):
        """R-UPD-42 — rewriting only the file leaves launchd running the old calendar."""
        supervisor.install_automatic_update(
            "03:00", self.root, self.logs, str(self.where), self.machine
        )
        self.machine.asked.clear()

        said = supervisor.install_automatic_update(
            "02:30", self.root, self.logs, str(self.where), self.machine
        )

        self.assertTrue(said.ok)
        self.assertEqual(["print", "bootout", "bootstrap"], self.machine.verbs())
        with open(supervisor.automatic_update_job_path(str(self.where)), "rb") as file:
            described = plistlib.load(file)
        self.assertEqual(
            {"Hour": 2, "Minute": 30}, described["StartCalendarInterval"]
        )

    def test_removing_the_job_removes_the_empty_default_log_directory_it_created(self):
        """R-RM-8 — a fresh install followed by uninstall leaves no Rundesk directory."""
        data = self.where / "data"
        logs = data / "logs"
        with mock.patch.dict(os.environ, {"RUNDESK_DATA_DIR": str(data)}):
            supervisor.install_automatic_update(
                "03:00", self.root, logs, str(self.where), self.machine
            )
            self.assertTrue(
                (logs / supervisor.AUTOMATIC_UPDATE_LOGS_MARKER).is_file()
            )
            supervisor.remove_automatic_update(
                str(self.where), self.root, self.machine, logs
            )
        self.assertFalse(logs.exists())

    def test_removing_the_job_preserves_logs_that_hold_gateway_history(self):
        """R-GW-18"""
        data = self.where / "data"
        logs = data / "logs"
        with mock.patch.dict(os.environ, {"RUNDESK_DATA_DIR": str(data)}):
            supervisor.install_automatic_update(
                "03:00", self.root, logs, str(self.where), self.machine
            )
            history = logs / "gateway.log"
            history.write_text("worth keeping\n", encoding="utf-8")
            supervisor.remove_automatic_update(
                str(self.where), self.root, self.machine, logs
            )
        self.assertEqual("worth keeping\n", history.read_text(encoding="utf-8"))


class WhatASecondInstallCallsItsJobs(WithAJobDirectory):
    """R-INS-18 — reported (#146). Two installs can be moved apart in every directory
    they touch, and none of it reaches the machine: a label is registered per person, so
    `ai.rundesk-automatic-update` names one registration on the whole machine. A second
    install checked the plist it was about to remove — its own, in its own directory —
    and then asked the machine to take away the only registration that name can have,
    which was the first install's. Nothing said so, and the first install's file stayed
    on disk looking perfectly well.
    """

    def named(self, prefix: str = "ai.rundesk-station"):
        """This install, saying who it is. Undone after the case, because the variable
        is the process's and a leaked one would rename every job a later case writes."""
        patch = mock.patch.dict(os.environ, {"RUNDESK_JOB_PREFIX": prefix})
        patch.start()
        self.addCleanup(patch.stop)

    def test_nothing_said_is_the_prefix_rundesk_ships(self):
        self.assertEqual("ai.rundesk", supervisor.prefix())
        self.assertEqual("ai.rundesk.gateway", supervisor.label("gateway"))
        self.assertEqual("ai.rundesk-automatic-update", supervisor.automatic_update_label())

    def test_a_second_install_names_every_job_apart_from_the_first(self):
        self.named()
        self.assertEqual("ai.rundesk-station.gateway", supervisor.label("gateway"))
        self.assertEqual("ai.rundesk-station-backup", supervisor.backup_label())
        self.assertEqual("ai.rundesk-station-update", supervisor.update_label())
        self.assertEqual("ai.rundesk-station-automatic-update",
                         supervisor.automatic_update_label())
        self.assertEqual(
            "ai.rundesk-station-automatic-update.plist",
            supervisor.automatic_update_job_path(str(self.where)).name,
        )

    def test_a_second_install_asks_the_machine_only_for_its_own_registration(self):
        """The defect itself: what the machine is *asked to take away* is the label, and
        that is the one thing a directory cannot move."""
        self.named()
        supervisor.install_automatic_update(
            "03:00", self.root, self.logs, str(self.where), self.machine
        )
        supervisor.remove_automatic_update(str(self.where), self.root, self.machine)

        asked = [args[-1] for args in self.machine.asked]
        self.assertTrue(asked, "the machine was never asked anything")
        for target in asked:
            self.assertNotIn("ai.rundesk-automatic-update", target,
                             "it reached for the other install's registration")
            self.assertIn("ai.rundesk-station-automatic-update", target)

    def test_a_gateway_of_another_prefix_is_not_this_installs(self):
        """Two installs may share a jobs directory — a suite redirects one there — and a
        job written under another prefix is not a gateway of this install to sweep."""
        supervisor.install("mine", self.root, self.logs, str(self.where), self.machine)
        self.named()
        supervisor.install("theirs", self.root, self.logs, str(self.where), self.machine)

        self.assertEqual(["theirs"], supervisor.described(str(self.where), self.root))

    def test_a_prefix_that_could_escape_the_jobs_directory_is_refused(self):
        for said in ("../elsewhere", "with space", "", "..", "under/neath"):
            with self.subTest(said=said), self.assertRaises(supervisor.NotAPrefix):
                supervisor.checked_prefix(said)

    def test_a_prefix_inside_the_default_namespace_is_refused(self):
        """`described()` globs `<prefix>.*.plist`, so a station named under a dot would
        have the ordinary install read every station gateway as one of its own."""
        self.named("ai.rundesk.station")
        with self.assertRaises(supervisor.NotAPrefix):
            supervisor.label("gateway")

    def test_every_job_carries_the_name_this_install_gave_it(self):
        """A job is the one place rundesk starts itself with no shell in between, so a
        prefix the job does not name is a prefix the started process does not have."""
        self.named()
        jobs = {
            "gateway": supervisor.describe("gateway", self.root, self.logs),
            "backup": supervisor.describe_backup("03:00", self.root, self.logs),
            "automatic update": supervisor.describe_automatic_update(
                "03:00", self.root, self.logs),
            "update worker": supervisor.describe_update_worker(self.root, self.logs),
            "restart worker": supervisor.describe_restart_worker(self.root, self.logs),
        }
        for what, job in jobs.items():
            with self.subTest(job=what):
                self.assertEqual(
                    "ai.rundesk-station",
                    job["EnvironmentVariables"].get("RUNDESK_JOB_PREFIX"),
                    "the job is named apart and then runs as the first install",
                )

    def test_a_job_of_this_install_asks_the_machine_only_for_this_installs(self):
        """The defect one process hop on, and the reason the environment above matters.

        Run verbatim: the automatic update job is fired with exactly the environment it
        was written with and nothing else, which is what the machine hands it, and it
        then does what it exists to do — queue the update by handing over the worker.
        Before the prefix reached the job, this asked the machine to take away
        `ai.rundesk-update`, the *first* install's, from a job called
        `ai.rundesk-station-automatic-update` (R-INS-18).
        """
        self.named()
        job = supervisor.describe_automatic_update("03:00", self.root, self.logs)
        self.assertEqual("ai.rundesk-station-automatic-update", job["Label"])

        machine = Machine()
        with mock.patch.dict(os.environ, job["EnvironmentVariables"], clear=True):
            supervisor.install_update_worker(
                self.root, self.logs, str(self.where), machine
            )

        asked = [args[-1] for args in machine.asked]
        self.assertTrue(asked, "the machine was never asked anything")
        for target in asked:
            with self.subTest(target=target):
                self.assertNotIn(
                    "/ai.rundesk-update", target,
                    "the job took the first install's update worker away")
                self.assertIn("ai.rundesk-station-update", target)
        self.assertEqual(
            ["ai.rundesk-station-update.plist"],
            [path.name for path in sorted(self.where.glob("*.plist"))],
        )

    def test_nothing_said_writes_the_job_that_shipped(self):
        """Upgrade safety, and the reason the prefix is written in only when it was said.

        `install_automatic_update` compares the description it would write against the one
        the machine already holds, key for key. A default written in unconditionally would
        make every existing registration differ from its own description, so an upgrade
        would take the owner's automatic update away and put it back for nothing.
        """
        described = supervisor.describe_automatic_update("03:00", self.root, self.logs)
        self.assertNotIn("RUNDESK_JOB_PREFIX", described["EnvironmentVariables"])
        self.assertEqual("ai.rundesk-automatic-update", described["Label"])

        supervisor.write_automatic_update("03:00", self.root, self.logs, str(self.where))
        self.machine.holding.add(supervisor.automatic_update_label())

        said = supervisor.install_automatic_update(
            "03:00", self.root, self.logs, str(self.where), self.machine
        )

        self.assertTrue(said.ok)
        self.assertNotIn(
            "bootout", [args[0] for args in self.machine.asked],
            "an upgrade took its own automatic update away and put it back",
        )


if __name__ == "__main__":
    unittest.main()
