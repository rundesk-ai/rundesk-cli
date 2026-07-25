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
        self.schedules = Path(tempfile.mkdtemp(prefix="rundesk-sched-"))
        self.addCleanup(shutil.rmtree, self.schedules, True)
        self.addCleanup(os.environ.pop, "RUNDESK_SCHEDULES_DIR", None)
        os.environ["RUNDESK_SCHEDULES_DIR"] = str(self.schedules)
        self.addCleanup(setattr, gateway, "STOP_SECONDS", gateway.STOP_SECONDS)
        gateway.STOP_SECONDS = 2.0
        self.addCleanup(setattr, process, "GRACE_SECONDS", process.GRACE_SECONDS)
        process.GRACE_SECONDS = 0.5

    def made(self, name: str = gateway.DEFAULT_NAME) -> gateway.Gateway:
        gw = gateway.Gateway(name, where=self.where, logs=self.logs, schedules=self.schedules)
        self.addCleanup(gw.release)
        return gw

    def scratch(self) -> Path:
        made = Path(tempfile.mkdtemp(prefix="rundesk-scratch-"))
        self.addCleanup(shutil.rmtree, made, True)
        return made

    def schedules_for(self, name: str, *written) -> None:
        """Write this gateway's schedules — and only this gateway's."""
        (self.schedules / f"{name}.json").write_text(json.dumps(list(written)))


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

    async def test_whether_it_is_going_round_survives_the_clock_being_changed(self):
        """R-GW-9 — a wall clock moves when a machine wakes or its time is corrected,
        and it moves both ways: forward and a healthy gateway is called wedged, back and
        a wedged one looks fine. The beat is recorded on a clock that cannot be stepped."""
        gw = self.made()
        gw.claim()
        record = self.where / f"{gw.name}.json"
        said = json.loads(record.read_text())
        self.assertIn("since_boot", said, "nothing was recorded that a clock step cannot move")
        said["beat"] = time.time() - gateway.BEAT_SECONDS * 100  # as if the clock jumped
        record.write_text(json.dumps(said))
        self.assertFalse(
            gateway.standing(gw.name, self.where).stale,
            "a clock jump made a gateway that is going round look wedged",
        )

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
        # Both clocks moved back, because a gateway that stopped going round stopped
        # writing either of them.
        said["beat"] = time.time() - gateway.BEAT_SECONDS * 10
        said["since_boot"] = time.monotonic() - gateway.BEAT_SECONDS * 10
        record.write_text(json.dumps(said))
        self.assertTrue(gateway.standing(gateway.DEFAULT_NAME, self.where).stale)


class WhereAGatewayKeepsWhatItNeeds(WithARunDirectory):
    def test_it_is_beside_the_install_rather_than_inside_the_source(self):
        """R-GW-12 — an update lays a new release over the install, and what is running
        is not part of the release."""
        self.addCleanup(os.environ.pop, "RUNDESK_RUN_DIR", None)
        os.environ.pop("RUNDESK_RUN_DIR", None)
        self.assertEqual(Path.home() / ".rundesk" / "run", gateway.home())

    def test_what_it_writes_goes_beside_the_run_directory_by_default(self):
        """R-GW-18 — history and state are kept apart, so giving a name back cannot take
        the record of what happened with it."""
        self.addCleanup(os.environ.__setitem__, "RUNDESK_LOG_DIR", os.environ["RUNDESK_LOG_DIR"])
        del os.environ["RUNDESK_LOG_DIR"]
        self.assertEqual(Path.home() / ".rundesk" / "logs", gateway.logs_home())
        self.assertNotEqual(gateway.home(), gateway.logs_home())

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
        self.assertFalse((self.where / f"{gw.name}.json").exists(), "it left its record behind")
        self.assertFalse(gateway.standing(gw.name, self.where).running)
        again = self.made()
        again.claim()  # the name is immediately free, which is what "nothing to find" is for

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
        self.assertFalse(gw._stopping)
        gw.ask_to_stop()
        self.assertTrue(gw._stopping, "it did not stop taking work")
        # Asked before it ever served: serving must then not sit there waiting to be
        # asked a second time.
        self.assertEqual(0, await asyncio.wait_for(gw.serve(), 10), "it went on serving")

    async def test_a_gateway_that_is_stopping_takes_no_more_work(self):
        """R-GW-6"""
        gw = self.made()
        gw.claim()
        gw.ask_to_stop()
        with self.assertRaises(gateway.Stopping):
            await gw.start([PY, "-c", "pass"])

    async def test_stopping_does_not_wait_past_the_time_it_is_allowed(self):
        """R-GW-7 — past the supervisor's patience this process is killed, and a killed
        gateway is exactly how children get left behind."""
        gw = self.made()
        gateway.STOP_SECONDS = 0.3
        really_end = process.end_all  # kept, because the stand-in below never returns

        async def never(_programs):
            await asyncio.sleep(300)

        self.addCleanup(setattr, process, "end_all", really_end)
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
            json.dumps({
                "name": "orphaned",
                "pid": 999999,
                "working": {"a-conversation": {"pgid": left.pid, "since": gateway.started_at(left.pid)}},
            })
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
            json.dumps({"name": "orphaned", "working": {"a-conversation": {"pgid": 999999, "since": "whenever"}}})
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
        self.assertEqual(
            next(iter(gw.running.values())).pid, said["working"]["a-conversation"]["pgid"]
        )
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
            json.dumps({
                "name": "orphaned",
                "working": {"a-conversation": {"pgid": left.pid, "since": gateway.started_at(left.pid)}},
            })
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


class TheNameCannotBeGivenAwayByAccident(WithARunDirectory):
    """A lock lives on the inode, never on the path. Removing the file while someone
    holds it hands the name out twice, which is the one thing the lock exists to stop."""

    async def test_giving_back_a_name_never_removes_the_lock_itself(self):
        """R-GW-4 — the next claim would make a fresh inode and lock that instead."""
        gw = self.made()
        gw.claim()
        gw.release()
        self.assertTrue((self.where / f"{gw.name}.lock").exists(), "the lock file was removed")

    async def test_a_gateway_that_never_claimed_cannot_give_the_name_away(self):
        """R-GW-4 — reproduced: a second object of the same name calling release() (or
        shutting down, which calls it) took the lock file out from under the holder, and
        a third gateway then claimed a name that was already held."""
        holder = self.made("shared")
        holder.claim()
        passerby = gateway.Gateway("shared", where=self.where, logs=self.logs)
        passerby.release()  # never claimed, so it must touch nothing
        third = gateway.Gateway("shared", where=self.where, logs=self.logs)
        with self.assertRaises(gateway.AlreadyRunning):
            third.claim()

    async def test_shutting_down_a_gateway_that_never_claimed_touches_nothing(self):
        """R-GW-4 — `_go()` releases unconditionally, and it must still be no-one else's
        name it gives back."""
        holder = self.made("shared")
        holder.claim()
        passerby = gateway.Gateway("shared", where=self.where, logs=self.logs)
        await passerby._go()
        self.assertTrue(gateway.standing("shared", self.where).running, "the holder lost its name")

    async def test_a_name_that_would_escape_its_directory_is_refused(self):
        """R-GW-20 — the name becomes the name of a lock, a record and a log."""
        for bad in ("../escape", "a/b", "", "..", "with space"):
            with self.assertRaises(gateway.NotAName, msg=f"accepted {bad!r}"):
                gateway.Gateway(bad, where=self.where, logs=self.logs)

    async def test_nothing_builds_a_path_from_a_name_that_would_escape(self):
        """R-GW-20 — making a gateway is not the only way in. Everything that reaches a
        gateway by name builds a path out of it, and the verbs that stop, start and read
        one never construct a gateway at all — so a check only in the constructor guards
        the one path nobody takes."""
        bad = "../../../../../../tmp/rundesk-escaped"
        for builds in (gateway.log_path, gateway.what_is_running, gateway.standing):
            with self.assertRaises(gateway.NotAName, msg=f"{builds.__name__} accepted it"):
                builds(bad)
        with self.assertRaises(gateway.NotAName):
            gateway._lock_path(bad, self.where)
        with self.assertRaises(gateway.NotAName):
            gateway._record_path(bad, self.where)


class WhatIsLeftWhenItCouldNotFinish(WithARunDirectory):
    """Going away with work still running is the one case where the record must survive:
    it is the only thing naming what is out there, and R-GW-16 is the only thing that
    will ever end it."""

    async def test_going_with_work_still_running_leaves_the_record_naming_it(self):
        """R-GW-16, R-GW-17 — reproduced: the path that admits it left orphans was the
        path that erased what a successor needs to find them."""
        gw = self.made()
        gateway.STOP_SECONDS = 0.3
        really_end = process.end_all  # kept, because the stand-in below never returns

        async def never(_programs):
            await asyncio.sleep(300)

        self.addCleanup(setattr, process, "end_all", really_end)
        process.end_all = never
        serving = asyncio.ensure_future(gw.serve())
        deadline = time.time() + 5
        while not gateway.standing(gw.name, self.where).running and time.time() < deadline:
            await asyncio.sleep(0.02)
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="abandoned", silence=None))
        while not gw.running and time.time() < deadline:
            await asyncio.sleep(0.02)
        left = next(iter(gw.running.values()))
        gw.ask_to_stop()
        self.assertNotEqual(0, await asyncio.wait_for(serving, 10))
        said = json.loads((self.where / f"{gw.name}.json").read_text())
        self.assertIn("abandoned", said["working"], "it forgot what it left running")
        self.assertEqual(left.pid, said["working"]["abandoned"]["pgid"])
        process.end_all = really_end
        await really_end([left])
        self.assertEqual(process.ENDED, (await asyncio.wait_for(running, 15)).reason)

    async def test_work_unwinding_after_the_gateway_has_gone_does_not_rewrite_the_record(self):
        """R-GW-12 — a task finishing after its gateway left used to recreate the record
        from an already-cleared set, leaving a gateway listed forever as running nothing."""
        gw = self.made()
        gw.claim()
        gw.release()
        gw._say()  # the shape of a late unwind
        self.assertFalse((self.where / f"{gw.name}.json").exists())
        self.assertEqual([], gateway.every(self.where))


class WhoseProcessIsItAnyway(WithARunDirectory):
    async def test_a_number_that_now_belongs_to_something_else_is_left_alone(self):
        """R-GW-16 — numbers come round again, and low ones come round first after a
        restart, which is exactly when a record written before it is read. Ending a
        stranger's whole process tree is far worse than leaving one program running."""
        stranger = await asyncio.create_subprocess_exec(*FOREVER, start_new_session=True)
        self.addCleanup(lambda: stranger.kill() if stranger.returncode is None else None)
        (self.where / "orphaned.json").write_text(
            json.dumps({
                "name": "orphaned",
                "working": {"a-conversation": {"pgid": stranger.pid, "since": "a different time"}},
            })
        )
        gw = self.made("orphaned")
        gw.claim()
        self.assertEqual([], gw.swept)
        self.assertIsNone(stranger.returncode, "it ended a process that was not ours")
        self.assertIn("no longer the process we started", gateway.log_path("orphaned", self.logs).read_text())

    async def test_a_record_that_cannot_prove_what_it_left_is_left_alone(self):
        """R-GW-16 — a record from before rundesk knew how to tell proves nothing."""
        stranger = await asyncio.create_subprocess_exec(*FOREVER, start_new_session=True)
        self.addCleanup(lambda: stranger.kill() if stranger.returncode is None else None)
        (self.where / "orphaned.json").write_text(
            json.dumps({"name": "orphaned", "working": {"a-conversation": stranger.pid}})
        )
        gw = self.made("orphaned")
        gw.claim()
        self.assertEqual([], gw.swept)
        self.assertIsNone(stranger.returncode)
        self.assertIn("cannot prove it is ours", gateway.log_path("orphaned", self.logs).read_text())

    async def test_a_record_that_does_not_say_what_was_running_is_left_alone(self):
        """R-GW-19 — a record whose entries are not numbers at all says nothing about
        what to end, and guessing is how the wrong thing gets ended."""
        (self.where / "orphaned.json").write_text(
            json.dumps({"name": "orphaned", "working": {"a-conversation": "not a number"}})
        )
        gw = self.made("orphaned")
        gw.claim()
        self.assertEqual([], gw.swept)
        self.assertIn("does not say what was running", gateway.log_path("orphaned", self.logs).read_text())

    async def test_a_lock_that_cannot_be_opened_is_not_read_as_running(self):
        """R-GW-9 — a lock nobody can open proves nothing, and reporting a gateway as
        running on the strength of a file we could not read is the lie to avoid."""
        gw = self.made("guarded")
        gw.claim()
        gw.release()
        lock = self.where / "guarded.lock"
        lock.chmod(0o000)
        self.addCleanup(lock.chmod, 0o600)
        self.assertFalse(gateway.standing("guarded", self.where).running)

    async def test_a_leftover_that_ignores_the_polite_signal_is_ended_anyway(self):
        """R-GW-16 — this is the case the sweep exists for: a gateway killed outright,
        leaving a tool process behind. A tool is as free to ignore a polite signal as
        anything else, and nothing here made one do so, so the second signal was never
        load-bearing."""
        stubborn = await asyncio.create_subprocess_exec(
            PY, "-c",
            "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(300)\n",
            start_new_session=True,
        )
        self.addCleanup(lambda: stubborn.kill() if stubborn.returncode is None else None)
        await asyncio.sleep(0.4)  # let it install the handler before anything signals it
        (self.where / "orphaned.json").write_text(
            json.dumps({
                "name": "orphaned",
                "working": {"a-tool": {"pgid": stubborn.pid, "since": gateway.started_at(stubborn.pid)}},
            })
        )
        gw = self.made("orphaned")
        gw.claim()
        self.assertEqual(["a-tool"], gw.swept)
        deadline = time.time() + 10
        while gateway._still_there(stubborn.pid) and time.time() < deadline:
            await asyncio.sleep(0.05)
        self.assertFalse(gateway._still_there(stubborn.pid), "a deaf leftover outlived the sweep")

    def test_when_the_machine_cannot_say_when_a_process_started(self):
        """R-GW-19 — if asking fails, every record is written without a fingerprint and
        the sweep then leaves everything alone forever. That would turn the whole orphan
        clean-up off silently, so it must at least be a path something has walked."""
        real = gateway.subprocess.run
        self.addCleanup(setattr, gateway.subprocess, "run", real)

        def cannot(*_args, **_kwargs):
            raise OSError("ps is not on this machine")

        gateway.subprocess.run = cannot
        self.assertIsNone(gateway.started_at(os.getpid()))

    def test_when_a_process_started_is_answered_for_one_that_exists(self):
        """R-GW-16 — the fingerprint the whole guard rests on."""
        self.assertIsNotNone(gateway.started_at(os.getpid()))
        self.assertIsNone(gateway.started_at(999999))


class WorkNobodyIsComingBackFor(WithARunDirectory):
    """A name that is never taken up again is never anyone's to sweep, so work left
    under it would run until the machine was restarted."""

    async def _stray(self, name: str):
        left = await asyncio.create_subprocess_exec(*FOREVER, start_new_session=True)
        self.addCleanup(lambda: left.kill() if left.returncode is None else None)
        (self.where / f"{name}.json").write_text(
            json.dumps({
                "name": name,
                "working": {"a-conversation": {"pgid": left.pid, "since": gateway.started_at(left.pid)}},
            })
        )
        return left

    async def test_starting_any_gateway_ends_work_left_under_a_name_nobody_uses(self):
        """R-GW-23 — an agent renamed or removed while it was working leaves programs
        that nothing else would ever end."""
        left = await self._stray("an-agent-since-renamed")
        gw = self.made("something-else-entirely")
        gw.claim()
        self.assertTrue(await self._gone(left), "work under a forgotten name outlived everything")
        self.assertIn("nobody has started since", gateway.log_path(gw.name, self.logs).read_text())

    async def test_a_record_with_nothing_left_running_is_not_kept_forever(self):
        """R-GW-23 — otherwise every name ever used is listed as a gateway for good."""
        (self.where / "long-gone.json").write_text(
            json.dumps({"name": "long-gone", "working": {"a-conversation": {"pgid": 999999, "since": "then"}}})
        )
        self.made("someone-else").claim()
        self.assertFalse((self.where / "long-gone.json").exists())
        self.assertNotIn("long-gone", [s.name for s in gateway.every(self.where)])

    async def test_a_running_gateways_work_is_never_swept_by_another(self):
        """R-GW-23 — the one record that is not ours to touch is one whose gateway is
        still there. Sweeping it would be a gateway ending another's work."""
        busy = self.made("busy")
        busy.claim()
        running = asyncio.ensure_future(busy.start(FOREVER, as_name="its-own-work", silence=None))
        deadline = time.time() + 5
        while not busy.running and time.time() < deadline:
            await asyncio.sleep(0.02)
        theirs = next(iter(busy.running.values()))
        other = self.made("newcomer")
        other.claim()
        self.assertTrue(theirs.alive, "a gateway swept the work of one that was still running")
        self.assertTrue((self.where / "busy.json").exists())
        await process.end_all([theirs])
        await running

    async def _gone(self, proc, seconds: float = 10.0) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if not gateway._still_there(proc.pid):
                return True
            await asyncio.sleep(0.05)
        return False


class WorkThatStartsItself(WithARunDirectory):
    """The gateway's half of a schedule: turning what is due into work it owns."""

    def setUp(self):
        super().setUp()
        from rundesk_cli import schedule
        self.schedule = schedule
        self.told = self.scratch() / "it-ran"

    def _writes(self, name="ran"):
        return {"name": name, "when": "* * * * *",
                "run": [PY, "-c", f"import pathlib; pathlib.Path({str(self.told)!r}).write_text('yes')"]}

    async def _fired(self, gw, moment=None):
        from datetime import datetime
        gw._fire(self.schedule, moment or datetime.now())
        deadline = time.time() + 10
        while not self.told.exists() and time.time() < deadline:
            await asyncio.sleep(0.05)
        return self.told.exists()

    async def test_a_schedule_that_is_due_starts_what_it_names(self):
        """R-SCH-2"""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, self._writes())
        self.assertTrue(await self._fired(gw), "the time came and nothing started")

    async def test_a_gateway_runs_only_its_own_schedules(self):
        """R-SCH-13, R-SCH-14 — the whole of the isolation, and what makes one agent's
        schedules that agent's alone: a gateway reads its own file and has no way to
        name another's."""
        self.schedules_for("someone-else", self._writes())
        gw = self.made("mine")
        gw.claim()
        gw._fire(self.schedule, __import__("datetime").datetime.now())
        await asyncio.sleep(0.5)
        self.assertFalse(self.told.exists(), "a gateway ran another gateway's schedule")
        self.assertEqual(([], []), gateway.scheduled("mine", self.schedules))

    async def test_a_schedule_does_not_begin_again_while_the_last_is_still_running(self):
        """R-SCH-6, R-SCH-7 — and says so, because a schedule quietly skipping every
        time looks exactly like one that is working."""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, {"name": "slow", "when": "* * * * *", "run": list(FOREVER)})
        from datetime import datetime, timedelta
        first = datetime(2026, 7, 25, 9, 0)
        gw._fire(self.schedule, first)
        deadline = time.time() + 5
        while not gw.running and time.time() < deadline:
            await asyncio.sleep(0.02)
        self.assertEqual(1, len(gw.running))
        gw._fire(self.schedule, first + timedelta(minutes=1))   # due again, still running
        await asyncio.sleep(0.5)
        self.assertEqual(1, len(gw.running), "a schedule began again over its own last run")
        self.assertIn("still running", gateway.log_path(gw.name, self.logs).read_text())
        await process.end_all(list(gw.running.values()))

    async def test_a_schedule_runs_once_for_the_minute_it_is_due(self):
        """R-SCH-9 — the clock is looked at several times a minute."""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, self._writes())
        from datetime import datetime
        moment = datetime(2026, 7, 25, 9, 0)
        self.assertTrue(await self._fired(gw, moment))
        self.told.unlink()
        gw._fire(self.schedule, moment)
        await asyncio.sleep(0.4)
        self.assertFalse(self.told.exists(), "one minute ran a schedule twice")

    async def test_a_schedule_nobody_can_understand_is_reported_and_the_others_run(self):
        """R-SCH-10"""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, {"name": "broken", "when": "not a schedule"}, self._writes())
        self.assertTrue(await self._fired(gw))
        self.assertIn("cannot be understood", gateway.log_path(gw.name, self.logs).read_text())

    async def test_a_schedule_naming_nothing_this_gateway_can_start_is_reported(self):
        """R-SCH-3 — what a schedule names is carried without being read, so whether it
        means anything is the gateway's to decide, and to say."""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, {"name": "vague", "when": "* * * * *", "run": "do a thing"})
        gw._fire(self.schedule, __import__("datetime").datetime.now())
        await asyncio.sleep(0.4)
        self.assertIn("names nothing this gateway can start",
                      gateway.log_path(gw.name, self.logs).read_text())

    async def test_a_gateway_that_is_stopping_starts_nothing_further(self):
        """R-GW-6, R-SCH-2"""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, self._writes())
        gw.ask_to_stop()
        gw._fire(self.schedule, __import__("datetime").datetime.now())
        await asyncio.sleep(0.4)
        self.assertFalse(self.told.exists(), "a gateway on its way out started new work")


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
        self.assertFalse((where / "twice.json").exists(), "it left its record behind")
        self.assertFalse(gateway.standing("twice", where).running)

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
            stderr=subprocess.PIPE, text=True, args=[
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
        served.kill()
        self.fail(
            "the gateway never came up holding what it was meant to hold — it said: "
            + (served.stderr.read() or "(nothing)")
        )

    def _in_flight(self, name: str) -> bool:
        try:
            said = json.loads((self.where / f"{name}.json").read_text())
        except (OSError, ValueError):
            return False
        return bool(said.get("working"))

    def test_a_gateway_stops_when_the_machine_asks_it_to(self):
        """R-GW-6, R-GW-12"""
        served = subprocess.Popen(
            stderr=subprocess.PIPE, text=True, args=[
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
        self.assertFalse((self.where / "real.json").exists(), "it left its record behind")


if __name__ == "__main__":
    unittest.main()
