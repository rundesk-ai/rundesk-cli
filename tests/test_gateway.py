"""What rundesk guarantees about a gateway — the rows of platform-gateway.

Offline, and no provider. Where a real signal is the thing under test, a gateway is run
as a real process and really signalled; everything else drives the object directly.

The rows about staying up, coming back and surviving a reboot are the machine's
supervisor's, and are not here: they arrive with the job that describes one.
"""

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk_cli import gateway, process  # noqa: E402

PY = sys.executable

#: A program with no end of its own — still running whenever a test acts on it.
FOREVER = [PY, "-c", "import time; time.sleep(300)"]


class WithARunDirectory(unittest.IsolatedAsyncioTestCase):
    """Each case gets a machine of its own to be the only gateway on."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-gw-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.addCleanup(setattr, gateway, "STOP_SECONDS", gateway.STOP_SECONDS)
        gateway.STOP_SECONDS = 2.0
        self.addCleanup(setattr, process, "GRACE_SECONDS", process.GRACE_SECONDS)
        process.GRACE_SECONDS = 0.5

    def made(self, name: str = gateway.DEFAULT_NAME) -> gateway.Gateway:
        gw = gateway.Gateway(name, where=self.where)
        self.addCleanup(gw.release)
        return gw


class OnlyOneOfEachName(WithARunDirectory):
    async def test_only_one_gateway_of_a_name_runs_at_a_time(self):
        """R-GW-4"""
        first = self.made()
        first.claim()
        second = gateway.Gateway(gateway.DEFAULT_NAME, where=self.where)
        with self.assertRaises(gateway.AlreadyRunning):
            second.claim()

    async def test_a_second_gateway_says_why_it_will_not_start(self):
        """R-GW-5 — the message names the gateway, because with several running the
        one that refused is the thing you need to know."""
        self.made().claim()
        with self.assertRaises(gateway.AlreadyRunning) as refused:
            gateway.Gateway(gateway.DEFAULT_NAME, where=self.where).claim()
        self.assertIn(gateway.DEFAULT_NAME, str(refused.exception))

    async def test_gateways_of_different_names_run_alongside_each_other(self):
        """R-GW-4 — one gateway per agent is how one agent is restarted without
        disturbing the others, so two names must never contend."""
        self.made("agent-one").claim()
        self.made("agent-two").claim()
        self.assertTrue(gateway.standing("agent-one", self.where).running)
        self.assertTrue(gateway.standing("agent-two", self.where).running)

    async def test_the_name_a_gateway_gave_back_can_be_taken_again(self):
        """R-GW-12 — cycling a gateway is stopping one and starting another."""
        first = gateway.Gateway("agent-one", where=self.where)
        first.claim()
        first.release()
        second = self.made("agent-one")
        second.claim()  # no exception
        self.assertTrue(gateway.standing("agent-one", self.where).running)


class WhatIsRunning(WithARunDirectory):
    async def test_whether_a_gateway_is_running_is_answered_by_the_gateway(self):
        """R-GW-9"""
        self.assertFalse(gateway.standing(gateway.DEFAULT_NAME, self.where).running)
        gw = self.made()
        gw.claim()
        now = gateway.standing(gateway.DEFAULT_NAME, self.where)
        self.assertTrue(now.running)
        self.assertEqual(os.getpid(), now.pid)

    async def test_a_gateway_that_was_killed_is_not_reported_as_running(self):
        """R-GW-10 — a record is what a gateway said before it died, and a gateway
        killed outright never got to withdraw it. The lock is what the kernel knows."""
        (self.where / f"{gateway.DEFAULT_NAME}.lock").write_text("")
        (self.where / f"{gateway.DEFAULT_NAME}.json").write_text(
            json.dumps({"name": gateway.DEFAULT_NAME, "pid": 999999, "version": "9.9.9"})
        )
        left = gateway.standing(gateway.DEFAULT_NAME, self.where)
        self.assertFalse(left.running)
        self.assertIsNone(left.pid, "a pid from a dead gateway now belongs to something else")

    async def test_a_gateway_never_started_is_reported_as_not_running(self):
        """R-GW-9"""
        self.assertFalse(gateway.standing("never-started", self.where).running)

    async def test_a_record_that_is_not_about_a_gateway_at_all_is_survived(self):
        """R-GW-9 — valid text of the wrong shape is not the same as unreadable, and a
        reader that assumes shape fails differently from one that assumes nothing."""
        gw = self.made()
        gw.claim()
        (self.where / f"{gateway.DEFAULT_NAME}.json").write_text('["not", "a", "gateway"]')
        now = gateway.standing(gateway.DEFAULT_NAME, self.where)
        self.assertTrue(now.running)
        self.assertIsNone(now.version)

    async def test_a_running_gateway_keeps_saying_it_is_still_going_round(self):
        """R-GW-9 — the record is what tells an owner a gateway is up but wedged, so it
        has to keep moving on its own without anyone asking."""
        self.addCleanup(setattr, gateway, "BEAT_SECONDS", gateway.BEAT_SECONDS)
        gateway.BEAT_SECONDS = 0.1
        gw = self.made()
        serving = asyncio.ensure_future(gw.serve())
        record = self.where / f"{gw.name}.json"
        deadline = time.time() + 5
        while not record.exists() and time.time() < deadline:
            await asyncio.sleep(0.02)
        first = json.loads(record.read_text())["beat"]
        await asyncio.sleep(0.4)
        later = json.loads(record.read_text())["beat"]
        self.assertGreater(later, first, "the gateway stopped saying it was there")
        self.assertFalse(gateway.standing(gw.name, self.where).stale)
        gw.ask_to_stop()
        await asyncio.wait_for(serving, 10)

    async def test_a_record_that_cannot_be_read_is_survived(self):
        """R-GW-9 — a half-written record is what a crash mid-write leaves."""
        gw = self.made()
        gw.claim()
        (self.where / f"{gateway.DEFAULT_NAME}.json").write_text("{not json at all")
        now = gateway.standing(gateway.DEFAULT_NAME, self.where)
        self.assertTrue(now.running, "the lock still says it is there")
        self.assertIsNone(now.version)

    async def test_every_gateway_on_the_machine_is_listed(self):
        """R-GW-14 — managing gateways never means knowing their names in advance."""
        self.made("agent-one").claim()
        self.made("agent-two").claim()
        listed = {s.name: s for s in gateway.every(self.where)}
        self.assertEqual({"agent-one", "agent-two"}, set(listed))
        self.assertTrue(all(s.running for s in listed.values()))

    async def test_listing_gateways_where_there_are_none_says_so(self):
        """R-GW-14"""
        self.assertEqual([], gateway.every(self.where))
        self.assertEqual([], gateway.every(self.where / "not-even-there"))

    async def test_a_gateway_that_stopped_going_round_is_told_from_one_that_is_working(self):
        """R-GW-9 — up and wedged is not up, and no supervisor makes that distinction."""
        gw = self.made()
        gw.claim()
        record = self.where / f"{gateway.DEFAULT_NAME}.json"
        said = json.loads(record.read_text())
        said["beat"] = time.time() - gateway.BEAT_SECONDS * 10
        record.write_text(json.dumps(said))
        self.assertTrue(gateway.standing(gateway.DEFAULT_NAME, self.where).stale)


class WhereAGatewayKeepsWhatItNeeds(WithARunDirectory):
    def test_it_is_beside_the_install_rather_than_inside_the_source(self):
        """R-GW-12 — an update lays a new release over the install, and what is running
        is not part of the release."""
        self.addCleanup(os.environ.pop, "RUNDESK_RUN_DIR", None)
        os.environ.pop("RUNDESK_RUN_DIR", None)
        self.assertEqual(Path.home() / ".rundesk" / "run", gateway.home())

    def test_where_it_keeps_things_can_be_said(self):
        """R-GW-12 — so a machine can run one for real without touching the owner's own."""
        self.addCleanup(os.environ.pop, "RUNDESK_RUN_DIR", None)
        os.environ["RUNDESK_RUN_DIR"] = str(self.where / "elsewhere")
        self.assertEqual(self.where / "elsewhere", gateway.home())


class WhatItIsMadeOf(WithARunDirectory):
    def _install(self, *pythons: str) -> Path:
        root = self.where / "install"
        for name in pythons:
            (root / ".venv" / "lib" / name / "site-packages").mkdir(parents=True)
        root.mkdir(exist_ok=True)
        return root

    def test_an_install_needing_nothing_always_fits(self):
        """R-GW-11 — no dependencies means no virtualenv, so there is nothing to mismatch."""
        root = self.where / "bare"
        root.mkdir()
        self.assertIsNone(gateway.fitness(root))

    def test_an_install_built_for_this_python_fits(self):
        """R-GW-11"""
        mine = f"python3.{sys.version_info.minor}"
        self.assertIsNone(gateway.fitness(self._install(mine)))

    def test_an_install_built_for_another_python_does_not_fit(self):
        """R-GW-11 — what rundesk needs is compiled against one version, and a machine
        whose python3 moved on has a virtualenv that no longer loads."""
        unfit = gateway.fitness(self._install("python3.4"))
        self.assertIsNotNone(unfit)
        self.assertIn("python3.4", unfit)

    def test_an_install_that_still_has_one_that_fits_fits(self):
        """R-GW-11 — an upgrade that left the old one behind is not a mismatch."""
        mine = f"python3.{sys.version_info.minor}"
        self.assertIsNone(gateway.fitness(self._install("python3.4", mine)))

    async def test_a_gateway_refuses_to_start_when_it_does_not_fit(self):
        """R-GW-11 — refused here, rather than as an import error deep inside a
        dependency, under a supervisor, in a restart loop."""
        gw = gateway.Gateway("unfit", where=self.where, root=self._install("python3.4"))
        with self.assertRaises(gateway.Unfit):
            gw.claim()
        self.assertFalse(gateway.standing("unfit", self.where).running)


class NeverTheSameWorkTwice(WithARunDirectory):
    async def test_the_same_work_is_refused_while_it_is_already_running(self):
        """R-GW-15 — two sessions on one conversation answer it twice, each unaware of
        the other. The second is refused rather than started."""
        gw = self.made()
        gw.claim()
        first = asyncio.ensure_future(gw.start(FOREVER, as_name="a-conversation", silence=None))
        await self._holding(gw)
        with self.assertRaises(gateway.AlreadyStarted):
            await gw.start(FOREVER, as_name="a-conversation", silence=None)
        await process.end_all(list(gw.running.values()))
        await first

    async def test_different_work_runs_alongside_itself(self):
        """R-GW-15 — the guard is on the same work, never on there being work."""
        gw = self.made()
        gw.claim()
        running = [
            asyncio.ensure_future(gw.start(FOREVER, as_name=f"conversation-{i}", silence=None))
            for i in range(3)
        ]
        deadline = time.time() + 5
        while len(gw.running) < 3 and time.time() < deadline:
            await asyncio.sleep(0.02)
        self.assertEqual(3, len(gw.running))
        await process.end_all(list(gw.running.values()))
        await asyncio.gather(*running)

    async def test_work_that_finished_may_be_started_again(self):
        """R-GW-15 — a conversation gets a next turn; the guard is on running at once,
        not on having ever run."""
        gw = self.made()
        gw.claim()
        first = await gw.start([PY, "-c", "pass"], as_name="a-conversation")
        self.assertTrue(first.ok)
        again = await gw.start([PY, "-c", "pass"], as_name="a-conversation")
        self.assertTrue(again.ok, "a name was held after the work using it had finished")

    async def test_work_with_no_name_never_collides(self):
        """R-GW-15 — anonymous work is work that cannot be a duplicate of anything."""
        gw = self.made()
        gw.claim()
        running = [asyncio.ensure_future(gw.start(FOREVER, silence=None)) for _ in range(3)]
        deadline = time.time() + 5
        while len(gw.running) < 3 and time.time() < deadline:
            await asyncio.sleep(0.02)
        self.assertEqual(3, len(gw.running))
        await process.end_all(list(gw.running.values()))
        await asyncio.gather(*running)

    async def _holding(self, gw, seconds: float = 5.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if gw.running:
                return
            await asyncio.sleep(0.02)
        self.fail("the gateway never took hold of the program")


class GoingAway(WithARunDirectory):
    async def test_a_gateway_asked_to_stop_goes(self):
        """R-GW-12"""
        gw = self.made()
        serving = asyncio.ensure_future(gw.serve())
        await self._up(gw)
        gw.ask_to_stop()
        self.assertEqual(0, await asyncio.wait_for(serving, 10))
        self.assertFalse(gateway.standing(gw.name, self.where).running)

    async def test_stopping_leaves_nothing_for_the_next_start_to_find(self):
        """R-GW-12"""
        gw = self.made()
        serving = asyncio.ensure_future(gw.serve())
        await self._up(gw)
        gw.ask_to_stop()
        await asyncio.wait_for(serving, 10)
        self.assertEqual([], sorted(self.where.iterdir()))

    async def test_a_gateway_going_away_ends_what_it_was_running(self):
        """R-GW-8 — the whole reason every program goes through the gateway."""
        gw = self.made()
        serving = asyncio.ensure_future(gw.serve())
        await self._up(gw)
        running = asyncio.ensure_future(
            gw.start(FOREVER, silence=None)
        )
        await self._holding(gw)
        pid = next(iter(gw.running.values())).pid
        gw.ask_to_stop()
        await asyncio.wait_for(serving, 10)
        self.assertEqual(process.ENDED, (await running).reason)
        self.assertTrue(self._gone(pid), "a program outlived the gateway running it")

    async def test_a_gateway_that_is_stopping_takes_no_more_work(self):
        """R-GW-6"""
        gw = self.made()
        gw.claim()
        gw.ask_to_stop()
        with self.assertRaises(RuntimeError):
            await gw.start([PY, "-c", "pass"])

    async def test_stopping_does_not_wait_past_the_time_it_is_allowed(self):
        """R-GW-7 — past the supervisor's patience this process is killed, and a killed
        gateway is exactly how children get left behind."""
        gw = self.made()
        gateway.STOP_SECONDS = 0.3

        async def never(_programs):
            await asyncio.sleep(300)

        self.addCleanup(setattr, process, "end_all", process.end_all)
        process.end_all = never
        serving = asyncio.ensure_future(gw.serve())
        await self._up(gw)
        gw.ask_to_stop()
        started = time.monotonic()
        await asyncio.wait_for(serving, 10)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertFalse(gateway.standing(gw.name, self.where).running)

    async def _up(self, gw, seconds: float = 5.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if gateway.standing(gw.name, self.where).running:
                return
            await asyncio.sleep(0.02)
        self.fail("the gateway never came up")

    async def _holding(self, gw, seconds: float = 5.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if gw.running:
                return
            await asyncio.sleep(0.02)
        self.fail("the gateway never took hold of the program")

    def _gone(self, pid: int, seconds: float = 10.0) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                return True
            time.sleep(0.05)
        return False


class AsARealProcess(unittest.TestCase):
    """One case driven the way the supervisor will drive it: a real process, a real
    signal. Everything above drives the object, which cannot prove that the handler is
    installed or that the signal is the one launchd sends."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-gw-real-"))
        self.addCleanup(shutil.rmtree, self.where, True)

    def test_a_gateway_stops_when_the_machine_asks_it_to(self):
        """R-GW-6, R-GW-12"""
        served = subprocess.Popen(
            [
                PY,
                "-c",
                "import sys, asyncio\n"
                f"sys.path.insert(0, {str(ROOT / 'src')!r})\n"
                "from rundesk_cli import gateway\n"
                f"gw = gateway.Gateway('real', where=__import__('pathlib').Path({str(self.where)!r}))\n"
                "raise SystemExit(asyncio.run(gw.serve()))\n",
            ]
        )
        self.addCleanup(served.kill)
        deadline = time.time() + 15
        while time.time() < deadline:
            if gateway.standing("real", self.where).running:
                break
            time.sleep(0.05)
        else:
            self.fail("the gateway never came up")

        served.send_signal(signal.SIGTERM)
        self.assertEqual(0, served.wait(timeout=20), "it did not go quietly")
        self.assertFalse(gateway.standing("real", self.where).running)
        self.assertEqual([], sorted(self.where.iterdir()), "it left something behind")


if __name__ == "__main__":
    unittest.main()
