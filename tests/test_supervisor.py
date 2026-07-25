"""Handing a gateway to the machine — the rows of platform-gateway about staying up.

No launchd is involved. What the machine is asked is a function passed in, so every case
here runs on any machine, including one with no supervisor at all.
"""

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
    """A stand-in for the machine, which remembers what it was asked."""

    def __init__(self, refuse=()):
        self.asked: list[tuple] = []
        self.refuse = refuse

    def __call__(self, *args: str) -> supervisor.Spoke:
        self.asked.append(args)
        return supervisor.Spoke(args[0] not in self.refuse, "")

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
        self.assertEqual(["bootout", "bootstrap"], self.machine.verbs())

    def test_a_machine_that_will_not_take_it_is_reported_rather_than_assumed(self):
        """R-GW-1 — an install that reports success it did not earn is the thing this
        whole command surface refuses to do."""
        refusing = Machine(refuse=("bootstrap",))
        said = supervisor.install("gateway", self.root, self.logs, str(self.where), refusing)
        self.assertFalse(said.ok)

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
