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
import threading
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
        # Beside the run directory, never inside it: what a gateway is doing is cleared
        # when it goes, and what it wrote is not.
        self.logs = Path(tempfile.mkdtemp(prefix="rundesk-logs-"))
        self.addCleanup(shutil.rmtree, self.logs, True)
        self.addCleanup(os.environ.pop, "RUNDESK_LOG_DIR", None)
        os.environ["RUNDESK_LOG_DIR"] = str(self.logs)
        self.addCleanup(setattr, gateway, "STOP_SECONDS", gateway.STOP_SECONDS)
        gateway.STOP_SECONDS = 2.0
        self.addCleanup(setattr, process, "GRACE_SECONDS", process.GRACE_SECONDS)
        process.GRACE_SECONDS = 0.5

    def made(self, name: str = gateway.DEFAULT_NAME) -> gateway.Gateway:
        gw = gateway.Gateway(name, where=self.where, logs=self.logs)
        self.addCleanup(gw.release)
        return gw


class OnlyOneOfEachName(WithARunDirectory):
    async def test_only_one_gateway_of_a_name_runs_at_a_time(self):
        """R-GW-4"""
        first = self.made()
        first.claim()
        second = gateway.Gateway(gateway.DEFAULT_NAME, where=self.where, logs=self.logs)
        with self.assertRaises(gateway.AlreadyRunning):
            second.claim()

    async def test_a_refused_gateway_refuses_promptly_rather_than_waiting(self):
        """R-GW-5 — the refusal has to come back. Asking for the lock without saying
        'do not wait' turns a clean refusal into a hang that no test can see, because
        a suite that never finishes reads as a stuck machine and not as a failure."""
        self.made().claim()
        second = gateway.Gateway(gateway.DEFAULT_NAME, where=self.where, logs=self.logs)

        def ask():
            with self.assertRaises(gateway.AlreadyRunning):
                second.claim()

        asking = threading.Thread(target=ask, daemon=True)
        asking.start()
        asking.join(timeout=10)
        self.assertFalse(asking.is_alive(), "asking for a taken name blocked instead of refusing")

    async def test_a_second_gateway_says_why_it_will_not_start(self):
        """R-GW-5 — the message names the gateway, because with several running the
        one that refused is the thing you need to know."""
        self.made().claim()
        with self.assertRaises(gateway.AlreadyRunning) as refused:
            gateway.Gateway(gateway.DEFAULT_NAME, where=self.where, logs=self.logs).claim()
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
        first = gateway.Gateway("agent-one", where=self.where, logs=self.logs)
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
        gw = gateway.Gateway("unfit", where=self.where, logs=self.logs, root=self._install("python3.4"))
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


class OneGatewaysTroubleIsNotAnothers(WithARunDirectory):
    """The property a gateway per agent exists for: whatever happens inside one, the
    others carry on. Everything here runs two gateways at once on one machine."""

    async def test_one_gateway_stopping_leaves_the_others_running(self):
        """R-GW-4 — cycling one agent must not disturb the rest."""
        one, two = self.made("agent-one"), self.made("agent-two")
        two.claim()
        serving = asyncio.ensure_future(one.serve())
        deadline = time.time() + 5
        while not gateway.standing("agent-one", self.where).running and time.time() < deadline:
            await asyncio.sleep(0.02)
        one.ask_to_stop()
        await asyncio.wait_for(serving, 10)
        self.assertFalse(gateway.standing("agent-one", self.where).running)
        self.assertTrue(gateway.standing("agent-two", self.where).running, "the other went too")

    async def test_one_gateway_ending_its_work_leaves_another_gateways_work_alone(self):
        """R-GW-8 — a gateway ends *its* programs. Everything is in its own process
        group, so a signal meant for one must never reach the other's."""
        one, two = self.made("agent-one"), self.made("agent-two")
        one.claim()
        two.claim()
        ones = asyncio.ensure_future(one.start(FOREVER, as_name="work", silence=None))
        twos = asyncio.ensure_future(two.start(FOREVER, as_name="work", silence=None))
        await self._holding(one)
        await self._holding(two)
        survivor = next(iter(two.running.values()))
        await one._go()
        self.assertEqual(process.ENDED, (await ones).reason)
        self.assertTrue(survivor.alive, "ending one gateway's work ended another's")
        await process.end_all([survivor])
        await twos

    async def test_the_same_work_name_under_two_gateways_is_two_pieces_of_work(self):
        """R-GW-15 — the guard is per gateway, because a gateway is per agent: two
        agents each having a conversation of the same name is not a duplicate."""
        one, two = self.made("agent-one"), self.made("agent-two")
        one.claim()
        two.claim()
        ones = asyncio.ensure_future(one.start(FOREVER, as_name="convo", silence=None))
        twos = asyncio.ensure_future(two.start(FOREVER, as_name="convo", silence=None))
        await self._holding(one)
        await self._holding(two)
        self.assertNotEqual(
            next(iter(one.running.values())).pid, next(iter(two.running.values())).pid
        )
        await process.end_all(list(one.running.values()) + list(two.running.values()))
        await asyncio.gather(ones, twos)

    async def _holding(self, gw, seconds: float = 5.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if gw.running:
                return
            await asyncio.sleep(0.02)
        self.fail(f"gateway '{gw.name}' never took hold of its program")


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
        # Bounded on its own, not through the shutdown: a gateway that cleared what it
        # was running without ending it leaves this waiting forever, and an unbounded
        # wait turns that regression into a stuck build rather than a failing test.
        self.assertEqual(process.ENDED, (await asyncio.wait_for(running, 15)).reason)
        self.assertTrue(self._gone(pid), "a program outlived the gateway running it")

    async def test_asking_a_gateway_to_stop_both_refuses_work_and_ends_the_waiting(self):
        """R-GW-6 — two separate effects, and a version with only the second passes
        every other case here after a ten-second timeout rather than an assertion."""
        gw = self.made()
        gw.claim()
        self.assertFalse(gw._stopping)
        gw.ask_to_stop()
        self.assertTrue(gw._stopping, "it did not stop taking work")
        self.assertTrue(gw._stopped.is_set(), "it did not end the waiting")

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
        left_running = await asyncio.wait_for(serving, 10)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertNotEqual(0, left_running, "it went with work still running and said it was fine")
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


class WhatADeadGatewayLeftBehind(WithARunDirectory):
    async def test_taking_a_name_ends_what_the_last_gateway_of_it_was_running(self):
        """R-GW-16 — a gateway that was killed outright cannot end its own children:
        they are in their own groups, so nothing takes them with it. The next gateway
        of that name is the only thing that can, and it does so before it starts work."""
        left = await asyncio.create_subprocess_exec(*FOREVER, start_new_session=True)
        self.addCleanup(lambda: left.kill() if left.returncode is None else None)
        (self.where / "orphaned.json").write_text(
            json.dumps({"name": "orphaned", "pid": 999999, "working": {"a-conversation": left.pid}})
        )
        gw = self.made("orphaned")
        gw.claim()
        self.assertEqual(["a-conversation"], gw.swept)
        self.assertTrue(await self._gone(left))

    async def test_taking_a_name_nobody_left_anything_under_is_ordinary(self):
        """R-GW-16 — the common case costs nothing and says nothing."""
        gw = self.made("fresh")
        gw.claim()
        self.assertEqual([], gw.swept)

    async def test_work_recorded_by_a_gateway_that_has_since_gone_is_left_alone(self):
        """R-GW-16 — a recorded group that is already gone is the ordinary case, not a
        thing to report as swept."""
        (self.where / "orphaned.json").write_text(
            json.dumps({"name": "orphaned", "working": {"a-conversation": 999999}})
        )
        gw = self.made("orphaned")
        gw.claim()
        self.assertEqual([], gw.swept)

    async def test_a_record_saying_nothing_about_work_is_survived(self):
        """R-GW-16 — every gateway written before this existed says nothing about work."""
        (self.where / "orphaned.json").write_text(json.dumps({"name": "orphaned", "pid": 1}))
        gw = self.made("orphaned")
        gw.claim()
        self.assertEqual([], gw.swept)

    async def test_what_is_in_flight_is_written_down_as_it_happens(self):
        """R-GW-16 — the record is the only thing a successor has to go on, so it has to
        be true when the gateway dies, not fifteen seconds ago."""
        gw = self.made()
        gw.claim()
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="a-conversation", silence=None))
        deadline = time.time() + 5
        while not gw.running and time.time() < deadline:
            await asyncio.sleep(0.02)
        said = json.loads((self.where / f"{gw.name}.json").read_text())
        self.assertIn("a-conversation", said["working"])
        self.assertEqual(next(iter(gw.running.values())).pid, said["working"]["a-conversation"])
        await process.end_all(list(gw.running.values()))
        await running
        after = json.loads((self.where / f"{gw.name}.json").read_text())
        self.assertEqual({}, after["working"], "work that finished was still recorded as running")

    async def _gone(self, proc, seconds: float = 10.0) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if not gateway._still_there(proc.pid):
                return True
            await asyncio.sleep(0.05)
        return False


class WhatHappenedAndWhen(WithARunDirectory):
    """The log, which is the only thing there is to look at once a gateway has gone."""

    def written(self, name: str = gateway.DEFAULT_NAME) -> str:
        return gateway.log_path(name, self.logs).read_text()

    async def test_a_gateway_records_coming_up_and_going_down(self):
        """R-GW-18"""
        gw = self.made()
        serving = asyncio.ensure_future(gw.serve())
        deadline = time.time() + 5
        while not gateway.standing(gw.name, self.where).running and time.time() < deadline:
            await asyncio.sleep(0.02)
        gw.ask_to_stop()
        await asyncio.wait_for(serving, 10)
        said = self.written()
        self.assertIn("up", said)
        self.assertIn("asked to stop", said)
        self.assertIn("down", said)

    async def test_what_a_gateway_wrote_outlives_the_gateway(self):
        """R-GW-18 — the whole point: the gateway is gone, and something happened, and
        the only place left to look is what it wrote."""
        gw = self.made()
        gw.claim()
        gw.release()
        self.assertTrue(gateway.log_path(gw.name, self.logs).exists())
        self.assertIn("up", self.written())

    async def test_work_that_ended_badly_is_recorded_with_its_last_words(self):
        """R-GW-18 — the reason anyone opens this file is that something ended in a way
        they did not expect, so what it said before it went is the useful part."""
        gw = self.made()
        gw.claim()
        result = await gw.start(
            [PY, "-c", "import sys; print('the thing that went wrong'); sys.exit(3)"],
            as_name="doomed",
        )
        self.assertEqual(process.FAILED, result.reason)
        said = self.written()
        self.assertIn("doomed", said)
        self.assertIn("the thing that went wrong", said)

    async def test_work_that_was_refused_as_a_duplicate_is_recorded(self):
        """R-GW-18 — a refusal nobody can see afterwards looks like nothing happening."""
        gw = self.made()
        gw.claim()
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="convo", silence=None))
        deadline = time.time() + 5
        while not gw.running and time.time() < deadline:
            await asyncio.sleep(0.02)
        with self.assertRaises(gateway.AlreadyStarted):
            await gw.start(FOREVER, as_name="convo", silence=None)
        self.assertIn("already running", self.written())
        await process.end_all(list(gw.running.values()))
        await running

    async def test_what_was_swept_from_a_dead_gateway_is_recorded(self):
        """R-GW-18 — ending someone else's leftovers is exactly the kind of thing you
        want to find in a log rather than deduce."""
        left = await asyncio.create_subprocess_exec(*FOREVER, start_new_session=True)
        self.addCleanup(lambda: left.kill() if left.returncode is None else None)
        (self.where / "orphaned.json").write_text(
            json.dumps({"name": "orphaned", "working": {"a-conversation": left.pid}})
        )
        gw = self.made("orphaned")
        gw.claim()
        self.assertIn("a-conversation", self.written("orphaned"))

    async def test_a_gateway_that_refused_to_start_says_why_in_writing(self):
        """R-GW-18 — the case where there is no gateway afterwards to ask."""
        self.made("taken").claim()
        with self.assertRaises(gateway.AlreadyRunning):
            gateway.Gateway("taken", where=self.where, logs=self.logs).claim()
        self.assertIn("already running", self.written("taken"))

    async def test_a_gateway_that_cannot_say_it_is_alive_writes_that_down_and_carries_on(self):
        """R-GW-9, R-GW-18 — a full disk is not a reason to stop serving, but it is
        certainly a reason to be able to find out about it afterwards."""
        gw = self.made()
        gw.claim()
        broken = gateway.Gateway._record

        def refuses(_self):
            raise OSError("no space left on device")

        gateway.Gateway._record = refuses
        try:
            gw._say()  # does not raise
        finally:
            gateway.Gateway._record = broken
        self.assertIn("could not update the record", self.written())


class WhenClaimingGoesWrong(WithARunDirectory):
    async def test_a_gateway_claiming_its_own_name_twice_is_not_a_clash(self):
        """R-GW-4 — the clash is another process holding the name, never this one
        holding it already. Serving claims for itself, so anything that claimed before
        calling it would otherwise refuse itself."""
        gw = self.made()
        gw.claim()
        gw.claim()  # no exception
        self.assertTrue(gateway.standing(gw.name, self.where).running)

    async def test_a_name_is_not_left_held_by_a_claim_that_did_not_finish(self):
        """R-GW-4 — a claim that failed part way through must not make the name
        unusable to the next attempt, including a retry of itself."""
        gw = gateway.Gateway("awkward", where=self.where, logs=self.logs)
        self.addCleanup(gw.release)
        broken = gateway.Gateway.__dict__["_record"]

        def refuses(self_):
            raise OSError("the record could not be written")

        gateway.Gateway._record = refuses
        try:
            with self.assertRaises(OSError):
                gw.claim()
        finally:
            gateway.Gateway._record = broken
        again = self.made("awkward")
        again.claim()  # the name is free, so this does not raise
        self.assertTrue(gateway.standing("awkward", self.where).running)


class AsARealProcess(unittest.TestCase):
    """One case driven the way the supervisor will drive it: a real process, a real
    signal. Everything above drives the object, which cannot prove that the handler is
    installed or that the signal is the one launchd sends."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-gw-real-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.logs = Path(tempfile.mkdtemp(prefix="rundesk-logs-"))
        self.addCleanup(shutil.rmtree, self.logs, True)
        self.addCleanup(os.environ.pop, "RUNDESK_LOG_DIR", None)
        os.environ["RUNDESK_LOG_DIR"] = str(self.logs)

    def test_being_asked_to_stop_twice_does_not_kill_it_mid_shutdown(self):
        """R-GW-8, R-GW-12 — removing the handlers before shutting down restores the
        system default for these signals, which is *terminate*. A second signal in that
        window then kills the gateway outright: it never finishes ending its programs,
        and it leaves its lock and its record behind for the next start to trip over.

        The gateway is given a program that ignores the polite signal, so that shutting
        down genuinely takes time — and is not signalled again until that program is
        recorded as in flight, since otherwise there is no window to arrive during.
        """
        served, where = self._serving("twice", holding=True)
        served.send_signal(signal.SIGTERM)
        time.sleep(1.0)  # inside the shutdown window
        served.send_signal(signal.SIGTERM)
        code = served.wait(timeout=60)
        self.assertEqual(0, code, "the second signal killed it rather than being taken as a repeat")
        self.assertEqual([], sorted(x.name for x in where.iterdir()), "it left something behind")

    def _serving(self, name: str, holding: bool = False):
        held = (
            "async def main():\n"
            "    serving = asyncio.ensure_future(gw.serve())\n"
            "    await asyncio.sleep(0.5)\n"
            "    asyncio.ensure_future(gw.start([sys.executable, '-c', "
            "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)'],"
            " as_name='stubborn', silence=None))\n"
            "    await asyncio.sleep(0.5)\n"
            "    return await serving\n"
            "raise SystemExit(asyncio.run(main()))\n"
        )
        served = subprocess.Popen(
            [
                PY,
                "-c",
                "import sys, asyncio, pathlib\n"
                f"sys.path.insert(0, {str(ROOT / 'src')!r})\n"
                "from rundesk_cli import gateway\n"
                f"gw = gateway.Gateway({name!r}, where=pathlib.Path({str(self.where)!r}))\n"
                + (held if holding else "raise SystemExit(asyncio.run(gw.serve()))\n"),
            ]
        )
        self.addCleanup(served.kill)
        deadline = time.time() + 20
        while time.time() < deadline:
            if gateway.standing(name, self.where).running and (
                not holding or self._in_flight(name)
            ):
                return served, self.where
            time.sleep(0.05)
        self.fail("the gateway never came up holding what it was meant to hold")

    def _in_flight(self, name: str) -> bool:
        try:
            said = json.loads((self.where / f"{name}.json").read_text())
        except (OSError, ValueError):
            return False
        return bool(said.get("working"))

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
