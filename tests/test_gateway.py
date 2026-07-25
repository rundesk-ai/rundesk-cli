"""What rundesk guarantees about a gateway — the rows of platform-gateway.

Offline, and no provider. Where a real signal is the thing under test, a gateway is run
as a real process and really signalled; everything else drives the object directly.

The rows about staying up, coming back and surviving a reboot are the machine's
supervisor's, and are not here: they arrive with the job that describes one.
"""

import asyncio
import contextlib
import faulthandler
import fcntl
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk_cli import gateway, process  # noqa: E402

PY = sys.executable

#: Long enough for the slowest machine this runs on — about a minute in CI — and far short
#: of the hours a stuck job otherwise costs. This file deadlocked on Linux and ran until the
#: CI provider's own six-hour limit, three times over, with no output and nothing to read.
#: `exit=True` dumps every thread's stack and ends the process, which turns a day of
#: inference into one traceback naming the line.
SUITE_SECONDS = 300.0
faulthandler.dump_traceback_later(SUITE_SECONDS, exit=True)

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
        # An install of its own, and an empty one: claiming a name asks whether this
        # install fits the Python running it, and a gateway built without a root asks
        # that of the developer's real checkout. With dependencies declared, they live
        # only in the install's virtualenv — so every one of these cases refused to
        # start on the machine of anyone who had run the installer, and passed in CI,
        # which never has one. Nothing here is about fitness; `WhatItIsMadeOf` is,
        # and builds the installs it needs.
        self.root = Path(tempfile.mkdtemp(prefix="rundesk-root-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(setattr, gateway, "STOP_SECONDS", gateway.STOP_SECONDS)
        gateway.STOP_SECONDS = 2.0
        self.addCleanup(setattr, process, "GRACE_SECONDS", process.GRACE_SECONDS)
        process.GRACE_SECONDS = 0.5

    def made(self, name: str = gateway.DEFAULT_NAME) -> gateway.Gateway:
        gw = gateway.Gateway(name, where=self.where, logs=self.logs, schedules=self.schedules,
                             root=self.root)
        self.addCleanup(gw.release)
        return gw

    def scratch(self) -> Path:
        made = Path(tempfile.mkdtemp(prefix="rundesk-scratch-"))
        self.addCleanup(shutil.rmtree, made, True)
        return made

    def schedules_for(self, name: str, *written) -> None:
        """Write this gateway's schedules — and only this gateway's."""
        (self.schedules / f"{name}.json").write_text(json.dumps(list(written)))

    # -- waiting for something to be true, without stopping it becoming true -----------
    #
    # Every one of these yields between looks. Blocking the loop here starves the very
    # tasks being waited on: a program the gateway started is this process's own child,
    # and stays a zombie that `os.kill(pid, 0)` still finds until the `wait()` running on
    # this loop reaps it — so a helper that slept through would report every ended
    # program as still running, and pass only when the reaping happened to land first.

    async def _up(self, gw, seconds: float = 5.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if gateway.standing(gw.name, self.where).running:
                return
            await asyncio.sleep(0.02)
        self.fail(f"gateway '{gw.name}' never came up")

    async def _holding(self, gw, seconds: float = 5.0):
        """Wait until the gateway holds work that has really been started.

        Registered is not started: `start` puts work into `running` before it has a
        process, so a test that waited only for the name to appear could act on it while
        `pid` was still None — and while a shutdown sweeping what is alive would not see
        it at all.
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            if gw.running and all(p.alive for p in gw.running.values()):
                return
            await asyncio.sleep(0.02)
        self.fail(f"gateway '{gw.name}' never took hold of its program")

    async def _gone(self, pid: int, seconds: float = 10.0) -> bool:
        """Is this one process gone? Asked of the process, not of its group.

        Told apart from `_group_gone` because the two answer differently for anything
        that is not a group leader: `killpg` on a grandchild's number fails whether or
        not it is running, so asking that way reports every child of a child as gone and
        quietly passes every test about leaving one behind.
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                return True
            await asyncio.sleep(0.05)
        return False

    async def _group_gone(self, pgid: int, seconds: float = 10.0) -> bool:
        """Is everything in this process group gone? The number must be a group leader's."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            if not gateway._still_there(pgid):
                return True
            await asyncio.sleep(0.05)
        return False


class OnlyOneOfEachName(WithARunDirectory):
    async def test_only_one_gateway_of_a_name_runs_at_a_time(self):
        """R-GW-4"""
        first = self.made()
        first.claim()
        second = gateway.Gateway(gateway.DEFAULT_NAME, where=self.where, logs=self.logs, root=self.root)
        with self.assertRaises(gateway.AlreadyRunning):
            second.claim()

    async def test_a_refused_gateway_refuses_promptly_rather_than_waiting(self):
        """R-GW-5 — the refusal has to come back. Asking for the lock without saying
        'do not wait' turns a clean refusal into a hang that no test can see, because
        a suite that never finishes reads as a stuck machine and not as a failure."""
        self.made().claim()
        second = gateway.Gateway(gateway.DEFAULT_NAME, where=self.where, logs=self.logs, root=self.root)

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
            gateway.Gateway(gateway.DEFAULT_NAME, where=self.where, logs=self.logs, root=self.root).claim()
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
        first = gateway.Gateway("agent-one", where=self.where, logs=self.logs, root=self.root)
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



class GoingAway(WithARunDirectory):
    async def test_a_gateway_asked_to_stop_goes(self):
        """R-GW-12"""
        gw = self.made()
        serving = asyncio.ensure_future(gw.serve())
        await self._up(gw)
        gw.ask_to_stop()
        self.assertEqual(0, await asyncio.wait_for(serving, 10))
        self.assertFalse(gateway.standing(gw.name, self.where).running)

    async def test_a_gateway_can_be_asked_to_stop_from_the_moment_it_can_be_found(self):
        """R-GW-6, R-GW-12 — the window between being visible and being able to answer.

        A gateway becomes discoverable the moment it takes its name, and until its
        handlers are installed the system default for these signals is *terminate*. A
        supervisor asking it to stop inside that window killed it outright: the shutdown
        never ran, and the record it left behind was there for the next start to trip
        over. Asserted by when the handler was installed rather than by racing it, since
        the race is exactly what a test cannot be relied on to lose.
        """
        gw = self.made()
        taking_hold = {}
        took = gw.claim

        def claim():
            taking_hold["sigterm"] = signal.getsignal(signal.SIGTERM)
            return took()

        gw.claim = claim
        serving = asyncio.ensure_future(gw.serve())
        await self._up(gw)
        gw.ask_to_stop()
        self.assertEqual(0, await asyncio.wait_for(serving, 10))
        self.assertNotEqual(
            signal.SIG_DFL, taking_hold["sigterm"],
            "a stop arriving while it took its name would have killed it where it stood",
        )

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
        self.assertTrue(await self._gone(pid), "a program outlived the gateway running it")

    async def test_a_gateway_going_away_ends_what_the_work_left_running(self):
        """R-GW-8, R-PROC-11 — the leader having gone is not the tree having gone.

        A program that exits while something it started carries on is still draining, and
        stays in `running` — but `alive` asks after the one process we started, so a
        shutdown that ended only what was alive skipped it entirely, reported itself
        drained, and deleted the record naming the group. Nothing was left that could ever
        end it: not the successor either, since the pid it fingerprints has been reaped.
        """
        gw = self.made()
        gw.claim()
        # A long drain, so the tidying `wait()` does on its own way out cannot reach the
        # leftover during this test. That tidying is real, but it is not this guarantee:
        # once `serve` returns the gateway process exits, and a `wait()` still draining
        # goes with the loop it was running on. Whatever `_go` did not end is left for
        # good — so what `_go` alone achieves is what has to be asserted.
        self.addCleanup(setattr, process, "DRAIN_SECONDS", process.DRAIN_SECONDS)
        process.DRAIN_SECONDS = 30.0
        told = self.scratch() / "grandchild.pid"
        leaves_one = [
            PY, "-c",
            "import subprocess, pathlib, sys\n"
            f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
            f"pathlib.Path({str(told)!r}).write_text(str(child.pid))\n",
        ]
        running = asyncio.ensure_future(gw.start(leaves_one, as_name="leaky", silence=None))
        left = await self._said(told)
        self.assertIsNotNone(left, "the program never got as far as starting anything")
        # Its own leader is gone; what it started is not, and the gateway still holds it.
        self.assertTrue(await self._went(gw.running["leaky"]), "the leader never exited")
        self.assertIn("leaky", gw.running)
        drained = await asyncio.wait_for(gw._go(), 15)
        self.assertTrue(await self._gone(left, 5.0),
                        "the gateway left behind what its work started")
        self.assertTrue(drained, "it reported work still out there when it had ended all of it")
        running.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(running, 15)

    async def _said(self, told, seconds: float = 10.0):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if told.exists() and told.read_text().strip():
                return int(told.read_text().strip())
            await asyncio.sleep(0.05)
        return None

    async def _went(self, program, seconds: float = 10.0) -> bool:
        """Has the program's own leader exited, whatever it left running?"""
        deadline = time.time() + seconds
        while time.time() < deadline:
            if not program.alive:
                return True
            await asyncio.sleep(0.05)
        return not program.alive

    async def test_work_that_starts_as_the_gateway_goes_away_is_not_left_running(self):
        """R-GW-8 — the gap between taking work and having a process for it.

        `start` registers work before it has spawned anything, so a shutdown sweeping
        what is *alive* passes straight over work still being spawned: it is neither
        running to be ended nor stopped from starting. It then comes up moments after the
        gateway has gone, with `running` already cleared — an orphan nothing will ever
        end, under a name whose next start has no idea it is there.
        """
        gw = self.made()
        gw.claim()
        spawning, carry_on = asyncio.Event(), asyncio.Event()
        real = process.Program.start
        self.addCleanup(setattr, process.Program, "start", real)

        async def dawdle(program):
            spawning.set()
            await carry_on.wait()
            await real(program)

        process.Program.start = dawdle
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="late", silence=None))
        await asyncio.wait_for(spawning.wait(), 5)
        held = gw.running["late"]
        self.assertIsNone(held.pid, "the window this is about had already closed")
        await asyncio.wait_for(gw._go(), 10)  # finds nothing alive, and clears up
        carry_on.set()
        self.assertEqual(process.ENDED, (await asyncio.wait_for(running, 15)).reason)
        self.assertTrue(await self._gone(held.pid), "it outlived the gateway that started it")

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
        self.assertTrue(await self._group_gone(left.pid))

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
            gateway.Gateway("taken", where=self.where, logs=self.logs, root=self.root).claim()
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
        passerby = gateway.Gateway("shared", where=self.where, logs=self.logs, root=self.root)
        passerby.release()  # never claimed, so it must touch nothing
        third = gateway.Gateway("shared", where=self.where, logs=self.logs, root=self.root)
        with self.assertRaises(gateway.AlreadyRunning):
            third.claim()

    async def test_shutting_down_a_gateway_that_never_claimed_touches_nothing(self):
        """R-GW-4 — `_go()` releases unconditionally, and it must still be no-one else's
        name it gives back."""
        holder = self.made("shared")
        holder.claim()
        passerby = gateway.Gateway("shared", where=self.where, logs=self.logs, root=self.root)
        await passerby._go()
        self.assertTrue(gateway.standing("shared", self.where).running, "the holder lost its name")

    async def test_a_name_that_would_escape_its_directory_is_refused(self):
        """R-GW-20 — the name becomes the name of a lock, a record and a log."""
        for bad in ("../escape", "a/b", "", "..", "with space"):
            with self.assertRaises(gateway.NotAName, msg=f"accepted {bad!r}"):
                gateway.Gateway(bad, where=self.where, logs=self.logs, root=self.root)

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

    async def test_a_shutdown_that_could_not_end_something_says_so_without_running_out_of_time(self):
        """R-GW-17 — running out of time is not the only way to fail to end something.

        The other way is that both signals go out, the grace period passes, and the group
        is still there. `end` returned normally either way, so the shutdown saw no timeout,
        called itself drained, and deleted the record naming the survivors — leaving work
        no successor of this name would ever sweep, which is the one thing the record
        exists to prevent. Ending is quick here; only its answer is wrong.
        """
        gw = self.made()
        gw.claim()
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="unkillable", silence=None))
        await self._holding(gw)
        left = next(iter(gw.running.values()))
        stubborn = process.end_all

        async def would_not_go(_programs):
            return False

        self.addCleanup(setattr, process, "end_all", stubborn)
        process.end_all = would_not_go
        self.assertFalse(await asyncio.wait_for(gw._go(), 15),
                         "it could not end the work and reported a clean shutdown")
        said = json.loads((self.where / f"{gw.name}.json").read_text())
        self.assertIn("unkillable", said["working"], "it deleted the record naming what survived")
        process.end_all = stubborn
        await stubborn([left])
        await asyncio.wait_for(running, 15)

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
        self.assertTrue(await self._group_gone(left.pid), "work under a forgotten name outlived everything")
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

    async def test_a_schedule_whose_firing_cannot_be_written_down_does_not_start(self):
        """R-SCH-9 — writing it down first is the whole guard against running it twice, so
        starting anyway when the write failed is the guard doing nothing at all."""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, {"name": "nightly", "when": "* * * * *", "run": list(FOREVER)})

        def cannot_write(*_args, **_kw):
            raise OSError("the disk is full")

        self.addCleanup(setattr, gateway, "_written_whole", gateway._written_whole)
        gateway._written_whole = cannot_write
        gw._fire(self.schedule, datetime(2026, 3, 1, 9, 30))
        await asyncio.sleep(0.2)
        self.assertEqual({}, gw.running, "it started work it could not record having started")

    async def test_what_a_schedule_last_did_never_moves_backwards(self):
        """R-SCH-9 — a long run finishing after a later occurrence was already recorded put
        the earlier minute back, and a gateway reading that took the later minute for one
        that had never fired."""
        gw = self.made()
        gw.claim()
        gw._remember("nightly", "started", datetime(2026, 3, 1, 9, 0))
        gw._remember("nightly", "still running", datetime(2026, 3, 1, 9, 5))
        gw._remember("nightly", "finished", datetime(2026, 3, 1, 9, 0))   # the late arrival
        said = gateway.what_was_scheduled(gw.name, self.schedules)
        self.assertEqual("2026-03-01 09:05", said["nightly"]["at"],
                         "a late finish put the clock back and freed a minute to run again")

    async def test_that_a_schedule_fired_is_written_down_before_it_is_run(self):
        """R-SCH-9 — held only in memory, the fact that this minute had already fired
        died with the gateway. A crash between starting and finishing, and a supervisor
        that brings the gateway back within seconds, ran the same schedule twice over for
        the one minute it was due. Asserted while the run is still going, because after it
        finishes both a working version and a broken one have written the same thing."""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, {"name": "slow", "when": "* * * * *", "run": FOREVER})
        gw._fire(self.schedule, datetime(2026, 3, 1, 9, 30))
        try:
            said = gateway.what_was_scheduled(gw.name, self.schedules)
            self.assertIn("slow", said, "nothing was written down until the run finished")
            self.assertEqual("2026-03-01 09:30", said["slow"]["at"])
        finally:
            await process.end_all(list(gw.running.values()))

    async def test_a_gateway_coming_straight_back_does_not_run_the_same_minute_again(self):
        """R-SCH-9 — the point of writing it down: what a successor of this name reads is
        what stops it firing a minute its predecessor already fired."""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, {"name": "slow", "when": "* * * * *", "run": FOREVER})
        minute = datetime(2026, 3, 1, 9, 30)
        gw._fire(self.schedule, minute)
        await process.end_all(list(gw.running.values()))
        gw.release()

        successor = self.made()
        successor.claim()   # everything it knows, it read off the disk
        successor._fire(self.schedule, minute)
        self.assertEqual({}, successor.running, "it ran a minute its predecessor had already run")

    async def test_a_schedule_that_cannot_be_started_says_so_where_it_can_be_read(self):
        """R-SCH-8 — nobody awaits the task a schedule runs in, so anything raised in it
        is raised nowhere at all: asyncio reports it on stderr, which for a supervised
        gateway is a file rundesk does not read. The schedule sat at LAST RUN '-' forever,
        indistinguishable from one that has simply never come due — while failing again
        every single time it fell due."""
        gw = self.made()
        gw.claim()
        # A program named rather than located: exactly what `--run codex exec` writes, and
        # what the gateway's own environment cannot resolve.
        self.schedules_for(gw.name, {"name": "named", "when": "* * * * *", "run": ["python3", "-c", "pass"]})
        gw._fire(self.schedule, datetime(2026, 3, 1, 9, 30))
        for _ in range(100):
            if gateway.what_was_scheduled(gw.name, self.schedules).get("named", {}).get(
                    "outcome") == "could not start":
                break
            await asyncio.sleep(0.05)
        said = gateway.what_was_scheduled(gw.name, self.schedules)
        self.assertEqual("could not start", said.get("named", {}).get("outcome"),
                         "a schedule that could not start looks like one that never came due")
        self.assertIn("could not be started", gateway.log_path(gw.name, self.logs).read_text())

    async def test_a_run_cut_short_by_the_gateway_going_is_not_called_a_failure_to_start(self):
        """R-SCH-8, R-GW-18 — a catch-all that does not let cancellation past first.

        A run in flight when the gateway goes is cancelled by the loop that was running
        it. Swallowed by the handler written for a program that could not be started, it
        was written down as 'could not start' with no reason at all — one line after the
        log said it had started. A false line in the one account that outlives the gateway,
        in the file that exists to say truthfully what each schedule last did.
        """
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, {"name": "long", "when": "* * * * *", "run": FOREVER})
        fired = datetime(2026, 3, 1, 9, 30)
        gw._fire(self.schedule, fired)
        await self._holding(gw)
        # Cancelling the task the schedule runs in is exactly what the loop does to
        # whatever is left when `serve` returns and the gateway's process exits.
        running = next(
            (task for task in asyncio.all_tasks()
             if task is not asyncio.current_task() and "_run_scheduled" in repr(task)),
            None,
        )
        self.assertIsNotNone(running, "the schedule is not running in a task of its own")
        running.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(running, 15)
        said = gateway.what_was_scheduled(gw.name, self.schedules)
        self.assertEqual("interrupted", said["long"]["outcome"],
                         "a run cut short by the gateway going was called a failure to start")
        self.assertNotIn("could not be started", gateway.log_path(gw.name, self.logs).read_text())
        await process.end_all(list(gw.running.values()))

    async def test_a_gateway_can_start_work_with_no_ceiling_on_how_long_it_runs(self):
        """R-PROC-13 — a program may be allowed to run without any ceiling, and the
        gateway is the only thing that starts one. Unable to say so, everything it ran was
        nailed to the 48-hour backstop, and a session meant to be persistent would be
        ended on its second day."""
        gw = self.made()
        gw.claim()
        running = asyncio.ensure_future(
            gw.start(FOREVER, as_name="persistent", silence=None, ceiling=None)
        )
        await self._holding(gw)
        self.assertIsNone(gw.running["persistent"].ceiling, "it was held to the backstop anyway")
        await process.end_all(list(gw.running.values()))
        await asyncio.wait_for(running, 15)

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


class WhatCarriesAcrossARestart(WithARunDirectory):
    """Cycling a gateway is the most ordinary thing that happens to one, and two things
    were lost every time it did."""

    def setUp(self):
        super().setUp()
        from rundesk_cli import schedule
        self.schedule = schedule
        self.told = self.scratch() / "it-ran"

    def _writes(self):
        return {"name": "ran", "when": "* * * * *",
                "run": [PY, "-c", f"import pathlib; pathlib.Path({str(self.told)!r}).write_text('yes')"]}

    async def test_a_schedule_that_already_ran_this_minute_does_not_run_again_after_a_restart(self):
        """R-SCH-9 — what has run is held in memory, and a new gateway starts with none
        of it. A restart landing in the same minute ran everything a second time."""
        from datetime import datetime
        moment = datetime(2026, 7, 25, 9, 0)
        first = self.made()
        first.claim()
        self.schedules_for(first.name, self._writes())
        first._fire(self.schedule, moment)
        deadline = time.time() + 10
        while not self.told.exists() and time.time() < deadline:
            await asyncio.sleep(0.05)
        self.assertTrue(self.told.exists())
        first.release()
        self.told.unlink()

        again = self.made()
        again.claim()
        again._fire(self.schedule, moment)   # the same minute, a new gateway
        await asyncio.sleep(0.5)
        self.assertFalse(self.told.exists(), "a restart ran a schedule that had already run")

    async def test_what_each_schedule_last_did_survives_a_restart(self):
        """R-SCH-8 — the first record a fresh gateway writes wiped it, so cycling erased
        the only account of what the schedules had been doing."""
        first = self.made()
        first.claim()
        self.schedules_for(first.name, {"name": "quick", "when": "* * * * *", "run": [PY, "-c", "pass"]})
        await first.start([PY, "-c", "pass"], as_name="ignored")
        first._remember("quick", "finished")
        self.assertIn("quick", gateway.what_was_scheduled(first.name, self.schedules))
        first.release()

        again = self.made()
        again.claim()
        carried = gateway.what_was_scheduled(again.name, self.schedules)
        self.assertIn("quick", carried, "restarting wiped what the schedules had done")
        self.assertEqual("finished", carried["quick"]["outcome"])

    def _last_up(self, seconds_ago: float) -> None:
        """Say when a gateway of this name was last known to be going round."""
        gateway.seen_path("gateway", self.schedules).write_text(
            json.dumps({"at": time.time() - seconds_ago})
        )

    async def test_what_fell_due_while_nothing_ran_is_said(self):
        """R-SCH-5 — none of it is run, and saying nothing is the silence an owner
        cannot tell from a schedule that never worked."""
        self._last_up(3 * 60 * 60)   # nothing has run for three hours
        self.schedules_for("gateway", {"name": "hourly", "when": "0 * * * *", "run": [PY, "-c", "pass"]})
        gw = self.made()
        gw.claim()
        self.assertIn("fell due", gateway.log_path(gw.name, self.logs).read_text())
        self.assertIn("was not run late", gateway.log_path(gw.name, self.logs).read_text())

    async def test_what_fell_due_is_said_after_an_ordinary_stop_and_not_only_a_crash(self):
        """R-SCH-5, R-GW-12 — where the downtime checkpoint has to live.

        Read off the run record, this survived a crash and not an ordinary stop, because
        stopping deletes that record on purpose. So the gap an owner is most likely to
        have caused — stopping a gateway and starting it again later — was the one gap
        nobody was ever told about, which is the inverse of what is useful.
        """
        self.schedules_for("gateway", {"name": "hourly", "when": "0 * * * *", "run": [PY, "-c", "pass"]})
        first = self.made()
        first.claim()
        first._say()          # it was up, and said so
        first.release()       # ...and then stopped, cleanly: the record goes
        self.assertFalse((self.where / "gateway.json").exists(), "the record survived a clean stop")
        self._last_up(3 * 60 * 60)   # and it stayed down for three hours

        again = self.made()
        again.claim()
        said = gateway.log_path(again.name, self.logs).read_text()
        self.assertIn("fell due", said, "a clean stop left nothing to measure the gap against")

    async def test_being_up_leaves_something_a_later_gateway_can_measure_against(self):
        """R-SCH-5 — the other half: nothing writes the checkpoint, and the test above
        passes forever on a file the suite wrote itself."""
        gw = self.made()
        gw.claim()
        gw._say()
        self.assertIsNotNone(gateway.last_seen(gw.name, self.schedules),
                             "a running gateway left nothing to say it had been up")


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
        gw = gateway.Gateway("awkward", where=self.where, logs=self.logs, root=self.root)
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
        # An empty install of its own, for the same reason as `WithARunDirectory` — and
        # it has to reach the gateway these cases start in another process, so it goes
        # into the script rather than into an argument here.
        self.root = Path(tempfile.mkdtemp(prefix="rundesk-root-"))
        self.addCleanup(shutil.rmtree, self.root, True)

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
                f"gw = gateway.Gateway({name!r}, where=pathlib.Path({str(self.where)!r}), "
                f"root=pathlib.Path({str(self.root)!r}))\n"
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
                "import pathlib\n"
                f"gw = gateway.Gateway('real', where=pathlib.Path({str(self.where)!r}), "
                f"root=pathlib.Path({str(self.root)!r}))\n"
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


class WorkTheGatewayTalksTo(WithARunDirectory):
    """R-PROC-14 to R-PROC-18 reaching work through the gateway that owns it.

    Proven at the gateway rather than only on a program, because the gateway is the only
    thing that starts one — a policy it cannot pass on is a policy nothing can ask for.
    """

    ECHOES = [PY, "-c", "import sys\nfor line in sys.stdin:\n"
                        "    sys.stdout.write('heard ' + line); sys.stdout.flush()"]

    async def test_a_gateway_starts_work_it_can_write_to_and_read_records_from(self):
        """R-PROC-14, R-PROC-17 — the whole of what this is groundwork for: work that is
        still running, still being written to, and answering into a receiver."""
        gw = self.made()
        gw.claim()
        taken = []
        running = asyncio.ensure_future(gw.start(
            self.ECHOES, as_name="talks", silence=None, takes_input=True, sink=taken.append,
        ))
        await self._holding(gw)
        # By name, for as long as it runs: the gateway's own register is the handle.
        talking = gw.running["talks"]
        await talking.send(b'{"ask":1}')
        deadline = time.time() + 10
        while not taken and time.time() < deadline:
            await asyncio.sleep(0.02)
        self.assertEqual([b'heard {"ask":1}'], taken, "nothing came back while it was running")
        await process.end_all(list(gw.running.values()))
        await asyncio.wait_for(running, 15)

    async def test_what_work_said_went_wrong_is_written_down_rather_than_parsed(self):
        """R-PROC-15, R-GW-18 — kept out of what is meant to be parsed, and put where
        anything else worth explaining in the morning already goes."""
        gw = self.made()
        gw.claim()
        taken = []
        outcome = await asyncio.wait_for(gw.start(
            [PY, "-c", "import sys\n"
                       "sys.stderr.write('it went wrong\\n'); sys.stderr.flush()\n"
                       "sys.stdout.write('{\"real\":1}\\n'); sys.stdout.flush()"],
            as_name="noisy", silence=None, sink=taken.append,
        ), 20)
        self.assertEqual([b'{"real":1}'], taken, "what went wrong reached the receiver")
        self.assertTrue(outcome.ok)
        said = gateway.log_path(gw.name, self.logs).read_text()
        self.assertIn("it went wrong", said, "what it said went wrong was simply dropped")

    async def test_a_receiver_that_refuses_is_recorded_rather_than_lost(self):
        """R-PROC-17 — a receiver silently dropping everything it is handed looks exactly
        like work that said nothing at all, which is the one reading that misleads."""
        gw = self.made()
        gw.claim()

        def refuses(_record):
            raise RuntimeError("this receiver is broken")

        outcome = await asyncio.wait_for(gw.start(
            [PY, "-c", "import sys; sys.stdout.write('{\"a\":1}\\n'); sys.stdout.flush()"],
            as_name="refused", silence=None, sink=refuses,
        ), 20)
        self.assertTrue(outcome.ok, "the receiver failing was blamed on the work")
        said = gateway.log_path(gw.name, self.logs).read_text()
        self.assertIn("refused 1 record", said)

    async def test_a_gateway_starts_work_in_the_workspace_it_is_given(self):
        """R-PROC-19 — every agent brain works on a project, and the gateway is started by
        the machine in a directory nobody chose."""
        gw = self.made()
        gw.claim()
        workspace = Path(tempfile.mkdtemp(prefix="rundesk-work-"))
        self.addCleanup(shutil.rmtree, workspace, True)
        taken = []
        await asyncio.wait_for(gw.start(
            [PY, "-c", "import os, sys; sys.stdout.write(os.getcwd() + '\\n'); sys.stdout.flush()"],
            as_name="somewhere", silence=None, sink=taken.append, cwd=workspace,
        ), 20)
        self.assertEqual(workspace.resolve(), Path(taken[0].decode()).resolve())

    async def test_work_the_gateway_only_reads_is_given_no_input_and_one_stream(self):
        """R-PROC-14, R-PROC-15 — the guard: what the gateway has always started must go
        on being started exactly as it was."""
        gw = self.made()
        gw.claim()
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="ordinary", silence=None))
        await self._holding(gw)
        ordinary = gw.running["ordinary"]
        self.assertFalse(ordinary.takes_input)
        self.assertFalse(ordinary.errors_apart)
        await process.end_all(list(gw.running.values()))
        await asyncio.wait_for(running, 15)


class WorkThatNeverGotToFinish(WithARunDirectory):
    """R-GW-23 — work in flight when a gateway goes, answered for rather than dropped.

    The log already tells a person. What none of this told anything else is which work
    never finished, and whether it is definitely gone — which is what a provider adapter
    coming back after a restart has to know before it decides what to say.
    """

    def _left_behind(self, name="gateway", work="turn", pgid=999999, since="some time"):
        """A record of the shape a gateway that died would have left."""
        (self.where / f"{name}.json").write_text(json.dumps(
            {"name": name, "pid": 1, "working": {work: {"pgid": pgid, "since": since}}}))

    async def test_work_a_dead_gateway_left_is_written_down_for_something_to_read(self):
        """R-GW-23 — the ordinary case: the work went when its gateway did, and until now
        the only trace was a line nothing but a person could read."""
        self._left_behind()
        gw = self.made()
        gw.claim()
        said = gateway.what_was_interrupted("gateway", self.schedules)
        self.assertIn("turn", said, "work that never finished was dropped in silence")
        self.assertTrue(said["turn"]["ended"], "it is gone, and was not said to be")
        self.assertIn("gone", said["turn"]["why"])

    async def test_work_that_could_not_be_shown_to_be_ours_is_told_apart(self):
        """R-GW-23, R-GW-19 — ended and could-not-prove-it-was-ours are both interrupted,
        and only one of them is definitely gone. Answering both the same way would have an
        adapter treat a program that is still running as finished."""
        # Our own process group: genuinely alive, so the sweep reaches the branch where
        # it cannot prove the group is ours. A bare pid is not a group and would look gone.
        self._left_behind(pgid=os.getpgrp(), since=None)
        gw = self.made()
        gw.claim()
        said = gateway.what_was_interrupted("gateway", self.schedules)
        self.assertFalse(said["turn"]["ended"], "something still running was called gone")
        self.assertIn("ours", said["turn"]["why"])

    async def test_a_record_that_does_not_say_what_was_running_is_still_answered_for(self):
        """R-GW-23 — the least we know is still more than silence."""
        (self.where / "gateway.json").write_text(json.dumps(
            {"name": "gateway", "working": {"turn": {"since": "x"}}}))
        gw = self.made()
        gw.claim()
        said = gateway.what_was_interrupted("gateway", self.schedules)
        self.assertIn("turn", said)
        self.assertIsNone(said["turn"]["pgid"])

    async def test_work_left_under_a_name_nobody_uses_is_answered_for_under_that_name(self):
        """R-GW-21, R-GW-23 — swept by whichever gateway happens to start, but recorded
        against the gateway it belonged to, which is where anything asking would look."""
        self._left_behind(name="abandoned", work="its-turn")
        gw = self.made("mine")
        gw.claim()
        self.assertIn("its-turn", gateway.what_was_interrupted("abandoned", self.schedules))
        self.assertEqual({}, gateway.what_was_interrupted("mine", self.schedules),
                         "another gateway's interruption was filed under ours")

    async def test_work_a_shutdown_could_not_end_is_answered_for(self):
        """R-GW-23 — the other moment: not a successor finding leftovers, but a gateway
        going away that could not take its work with it."""
        gw = self.made()
        gw.claim()
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="stubborn", silence=None))
        await self._holding(gw)
        left = next(iter(gw.running.values()))
        stubborn = process.end_all

        async def would_not_go(_programs):
            return False

        self.addCleanup(setattr, process, "end_all", stubborn)
        process.end_all = would_not_go
        self.assertFalse(await asyncio.wait_for(gw._go(), 15))
        said = gateway.what_was_interrupted(gw.name, self.schedules)
        self.assertIn("stubborn", said, "it went with work running and told nothing")
        self.assertFalse(said["stubborn"]["ended"])
        process.end_all = stubborn
        await stubborn([left])
        await asyncio.wait_for(running, 15)

    async def test_what_never_finished_outlives_the_gateway_that_never_finished_it(self):
        """R-GW-23, R-GW-12 — kept where history is kept, so an ordinary stop does not
        erase the one account of what was interrupted."""
        self._left_behind()
        gw = self.made()
        gw.claim()
        gw.release()
        self.assertFalse((self.where / "gateway.json").exists())
        self.assertIn("turn", gateway.what_was_interrupted("gateway", self.schedules))

    async def test_work_a_successor_could_not_end_is_still_named_in_its_record(self):
        """R-GW-16, R-GW-23 — refusing to *claim* it was ended is only half of it.

        The successor writes its own record straight over the predecessor's, and the
        stray sweep skips its own name — so a group nothing could end was named nowhere
        the moment the new gateway came up, and no later start would ever look for it
        again. One log line, and then permanently invisible.
        """
        # A group that is genuinely alive and that we cannot prove is ours, so the sweep
        # leaves it — the shape of a leftover that will not go.
        self._left_behind(pgid=os.getpgrp(), since=None)
        gw = self.made()
        gw.claim()
        said = json.loads((self.where / "gateway.json").read_text())
        self.assertIn("turn", said["working"],
                      "the successor wrote over the only thing naming a live group")
        self.assertEqual(os.getpgrp(), said["working"]["turn"]["pgid"])

    async def test_what_a_successor_did_end_is_not_carried_forward(self):
        """R-GW-16 — carrying it forever would have every gateway inherit a list of work
        that finished years ago, and a sweep chasing groups that are long gone."""
        self._left_behind()          # a pgid that is not there
        gw = self.made()
        gw.claim()
        said = json.loads((self.where / "gateway.json").read_text())
        self.assertEqual({}, said["working"], "it inherited work that had already gone")

    async def test_interruptions_do_not_pile_up_without_end(self):
        """R-GW-23 — a machine left running for months must not grow a file nobody prunes,
        and the ones worth keeping are the ones that just happened."""
        self.addCleanup(setattr, gateway, "KEPT_INTERRUPTIONS", gateway.KEPT_INTERRUPTIONS)
        gateway.KEPT_INTERRUPTIONS = 3
        for n in range(10):
            gateway._note_interrupted("gateway", self.schedules, f"turn-{n}", "because")
        said = gateway.what_was_interrupted("gateway", self.schedules)
        self.assertEqual(3, len(said), "it kept every interruption there had ever been")
        self.assertIn("turn-9", said, "it kept the oldest and threw away the newest")

    async def test_one_gateway_noting_an_interruption_does_not_erase_anothers(self):
        """R-GW-23 — a gateway sweeping an abandoned name writes into *that* name's file,
        so two writers working from their own snapshots is a real shape here."""
        gateway._note_interrupted("shared", self.schedules, "first", "because")
        gateway._note_interrupted("shared", self.schedules, "second", "because")
        said = gateway.what_was_interrupted("shared", self.schedules)
        self.assertEqual({"first", "second"}, set(said), "one write erased the other")


#: A gateway of this name, holding it and running something, for as long as it is left to.
#: Its own process so the lock is genuinely another process's — a lock taken twice in one
#: process is granted, which is the one thing this must not accidentally prove.
HOLDS_ITS_NAME = """
import json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from rundesk_cli import gateway

where, name, ready, stop = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5])
mine = gateway.Gateway(name, where=where, logs=Path(sys.argv[6]), schedules=Path(sys.argv[7]),
                       root=Path(sys.argv[8]))
mine.claim()
work = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"],
                        start_new_session=True)
(where / f"{name}.json").write_text(json.dumps({
    "name": name, "pid": os.getpid(),
    "working": {"turn": {"pgid": work.pid, "since": gateway.started_at(work.pid)}},
}))
ready.write_text(str(work.pid))
while not stop.exists():
    time.sleep(0.01)
work.kill()
"""


class TheDecisionToEndSomebodysWork(WithARunDirectory):
    """The whole table, without a real process anywhere near it.

    What this code can do when it is wrong is kill a provider's entire process tree, or
    throw away the only record that would ever find one. The cases that matter are the ones
    a real process cannot be made to produce on demand — a signal the machine refuses, an
    identity that changes between two looks — so every question it asks of the live world
    arrives as an operation it is handed.
    """

    def setUp(self):
        super().setUp()
        self.log = logging.Logger("reckoning")
        self.said = []
        self.log.addHandler(logging.NullHandler())
        self.log.error = lambda msg, *a: self.said.append(msg % a if a else msg)
        self.log.warning = lambda msg, *a: self.said.append(msg % a if a else msg)

    def reckon(self, was, **how):
        """One entry, decided with the world answering exactly as told."""
        answers = {"present": lambda _pgid: True,
                   "started": lambda _pgid: "when it started",
                   "ask": lambda _pgid, _sig: True,
                   "gone_within": lambda _pgid, _patience: True}
        answers.update(how)
        return gateway._end_left_running("turn", was, self.log, **answers)

    OURS = {"pgid": 4242, "since": "when it started"}

    def test_work_the_machine_refused_to_signal_is_not_reported_as_ended(self):
        """R-GW-28 — every path appended the entry to what had been swept, including the
        one where the first signal was refused and the second was never sent. The sweep
        then said it had ended work left behind, and the record naming a live process
        tree was the thing it went on to delete."""
        became = self.reckon(self.OURS, ask=lambda _pgid, _sig: False,
                             gone_within=lambda _pgid, _p: False)
        self.assertFalse(became.swept, "it counted work it never signalled as dealt with")
        self.assertFalse(became.ended, "it called work it never signalled ended")
        self.assertTrue(became.keep, "it dropped the only record naming a live group")

    def test_an_escalation_that_stopped_after_the_polite_signal_is_not_reported_as_ended(self):
        """R-GW-28 — refused on the second signal is as short of the end as refused on the
        first, and the group is still there either way."""
        asked = []

        def refuses_the_second(_pgid, sig):
            asked.append(sig)
            return len(asked) == 1

        became = self.reckon(self.OURS, ask=refuses_the_second,
                             gone_within=lambda _pgid, _p: False)
        self.assertEqual(2, len(asked), "it never tried to insist")
        self.assertFalse(became.swept, "an escalation that stopped short was called complete")
        self.assertTrue(became.keep)

    def test_work_that_goes_on_the_polite_signal_is_ended_without_being_killed(self):
        """R-GW-16"""
        asked = []
        became = self.reckon(self.OURS,
                             ask=lambda _pgid, sig: asked.append(sig) or True,
                             gone_within=lambda _pgid, _p: True)
        self.assertEqual([signal.SIGTERM], asked, "it killed something that was going anyway")
        self.assertTrue(became.swept)
        self.assertTrue(became.ended)

    def test_work_that_ignores_the_polite_signal_is_killed_and_then_ended(self):
        """R-GW-16"""
        asked, went = [], []

        def then_gone(_pgid, _patience):
            went.append(1)
            return len(went) > 1        # still there after TERM, gone after KILL

        became = self.reckon(self.OURS,
                             ask=lambda _pgid, sig: asked.append(sig) or True,
                             gone_within=then_gone)
        self.assertEqual([signal.SIGTERM, signal.SIGKILL], asked)
        self.assertTrue(became.swept)
        self.assertTrue(became.ended)

    def test_work_that_outlives_both_signals_is_swept_and_said_not_to_have_gone(self):
        """R-GW-17 — everything that can be done to it has been done, and it is still
        answering. Both facts are reported, because they are different facts."""
        became = self.reckon(self.OURS, gone_within=lambda _pgid, _p: False,
                             present=lambda _pgid: True)
        self.assertTrue(became.swept, "it left work nothing more can be done to")
        self.assertFalse(became.ended, "it said work that still answers had gone")
        self.assertTrue(any("still answers" in one for one in self.said))

    def test_a_group_whose_identity_changed_between_two_looks_is_left_alone(self):
        """R-GW-19 — a tree-kill aimed at a stranger because a number came round again is
        very much worse than a stray program, and it is never kept in our record either:
        naming a stranger is how the next start comes to aim at it."""
        became = self.reckon(self.OURS, started=lambda _pgid: "some other moment")
        self.assertFalse(became.swept)
        self.assertFalse(became.keep, "it took a stranger's group into its own record")
        self.assertIn("not ours", became.why)

    def test_a_record_that_cannot_prove_the_work_was_ours_leaves_it_and_keeps_naming_it(self):
        """R-GW-19, R-GW-23 — nothing may be signalled on the strength of a number alone,
        and the record we are about to write is the only thing naming it."""
        became = self.reckon({"pgid": 4242}, started=lambda _pgid: "when it started")
        self.assertFalse(became.swept)
        self.assertTrue(became.keep)

    def test_a_record_that_does_not_say_what_was_running_is_still_answered_for(self):
        """R-GW-23"""
        became = self.reckon({"pgid": "not a number"})
        self.assertFalse(became.swept)
        self.assertFalse(became.keep)
        self.assertIn("does not say", became.why)

    def test_work_that_had_already_gone_is_not_counted_as_something_we_ended(self):
        """R-GW-23 — interrupted, definitely gone, and nothing rundesk did."""
        became = self.reckon(self.OURS, present=lambda _pgid: False)
        self.assertFalse(became.swept, "it took credit for work that went with its gateway")
        self.assertTrue(became.ended)

    def test_asking_a_group_that_has_already_gone_counts_as_the_ask_getting_through(self):
        """R-GW-28 — the ask is granted by the very thing it asked for. Read as a refusal,
        work that had gone would be left unswept for the one reason that means it worked."""
        went = subprocess.Popen([PY, "-c", "pass"], start_new_session=True)
        went.wait()
        self.assertTrue(gateway._ask_group(went.pid, signal.SIGTERM),
                        "a group that had already gone was read as the machine refusing")

    @unittest.skipIf(os.geteuid() == 0, "root is refused nothing, so there is no refusal to see")
    def test_a_machine_that_refuses_the_signal_is_told_from_one_that_granted_it(self):
        """R-GW-28 — the distinction the whole decision rests on, at its own level.

        Group one is the machine's own, which nobody but root may signal. **Never group
        zero**: that is the caller's own group, and asking it to die kills the test run,
        the shell around it and everything else sharing the group.
        """
        self.assertFalse(gateway._ask_group(1, signal.SIGKILL),
                         "a refused signal was reported as sent")


class WhatProvesWorkIsOurs(WithARunDirectory):
    """A process number alone proves nothing; a number and a start time prove ownership.

    That proof was re-derived on every beat, from a subprocess with a five-second budget,
    on exactly the loaded machine where work gets left behind. One unanswered look wrote
    `null` over an answer that was correct, and from then on every gateway refused to touch
    the group — a provider CLI and everything under it, held until the machine reboots.
    """

    async def test_a_look_that_the_machine_did_not_answer_never_erases_what_is_held(self):
        """R-GW-30 — a start time cannot change, so asking again can only make it worse."""
        gw = self.made()
        gw.claim()
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="turn"))
        deadline = time.time() + 15
        while "turn" not in gw.running and time.time() < deadline:
            await asyncio.sleep(0.02)
        while not gw._known_since.get("turn") and time.time() < deadline:
            await asyncio.sleep(0.02)
        first = json.loads((self.where / "gateway.json").read_text())["working"]["turn"]
        self.assertTrue(first["since"], "the work was recorded without anything proving it ours")

        self.addCleanup(setattr, gateway, "started_at", gateway.started_at)
        gateway.started_at = lambda _pid: None      # the machine, not answering
        gw._say()

        after = json.loads((self.where / "gateway.json").read_text())["working"]["turn"]
        self.assertEqual(first["since"], after["since"],
                         "one unanswered look erased the only proof the work was ours")
        await process.end_all(list(gw.running.values()))
        await asyncio.wait_for(running, 15)

    async def test_a_beat_does_not_ask_the_machine_anything(self):
        """R-GW-30 — it was a blocking subprocess per running program per beat, on the
        loop that reads everything those programs are saying."""
        gw = self.made()
        gw.claim()
        running = asyncio.ensure_future(gw.start(FOREVER, as_name="turn"))
        deadline = time.time() + 15
        while not gw._known_since.get("turn") and time.time() < deadline:
            await asyncio.sleep(0.02)

        asked = []
        self.addCleanup(setattr, gateway, "started_at", gateway.started_at)
        gateway.started_at = lambda pid: asked.append(pid)
        gw._say()
        gw._say()

        self.assertEqual([], asked, "a beat shelled out once per running program")
        await process.end_all(list(gw.running.values()))
        await asyncio.wait_for(running, 15)


class ANameIsTakenNotAskedAbout(WithARunDirectory):
    """A gateway can claim its name in the instant between being asked about and being
    signalled. The answer stops being true the moment after it is given, so the sweep takes
    the name instead and keeps it for the whole reckoning."""

    def running_gateway(self, name: str):
        """A gateway of this name in a process of its own, holding it and running work."""
        ready = self.scratch()
        stop, told = ready / "stop", ready / "ready"
        child = subprocess.Popen(
            [PY, "-c", HOLDS_ITS_NAME, str(ROOT / "src"), str(self.where), name,
             str(told), str(stop), str(self.logs), str(self.schedules), str(self.root)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(child.wait, 30)
        self.addCleanup(stop.touch)
        deadline = time.time() + 30
        while not told.exists() and time.time() < deadline:
            if child.poll() is not None:
                self.fail(f"the gateway never came up: {child.communicate()[1]}")
            time.sleep(0.02)
        self.assertTrue(told.exists(), "the gateway never said it was up")
        return int(told.read_text())

    def test_a_gateway_that_holds_its_name_keeps_its_work_and_its_record(self):
        """R-GW-29 — the destructive half. A start that swept here ended a live agent's
        whole process tree, and the agent went on holding its name throughout."""
        working = self.running_gateway("busy")

        swept = gateway._sweep_strays(self.where, "mine", self.made("mine").log, self.schedules)

        self.assertEqual([], swept, "an ordinary start swept a gateway that is up")
        self.assertTrue((self.where / "busy.json").exists(),
                        "it deleted a live gateway's record")
        self.assertTrue(gateway._still_there(working),
                        "it ended the work of a gateway that holds its name")

    def test_a_gateway_cannot_claim_its_name_while_a_sweep_is_reckoning_with_it(self):
        """R-GW-29 — the window itself, and the reason one more liveness check was never
        enough. The old code asked whether the name was held and then let go of the answer;
        a gateway could claim in the instant that followed, and the sweep already under way
        went on to signal the process group that gateway had just started.

        A lock belongs to the open file, not to the process, so a second `open` here
        contends exactly as another process would — which is what `_held` itself relies on.
        """
        (self.where / "target.json").write_text(json.dumps({"working": {}}))
        (self.where / "target.lock").touch()
        inside, carry_on = self.scratch() / "inside", self.scratch() / "carry-on"

        def waits_while_holding_the_name(record, log, *_args, **_kw):
            inside.touch()
            deadline = time.time() + 15
            while not carry_on.exists() and time.time() < deadline:
                time.sleep(0.01)
            return []

        self.addCleanup(setattr, gateway, "_sweep_predecessor", gateway._sweep_predecessor)
        gateway._sweep_predecessor = waits_while_holding_the_name
        sweeping = threading.Thread(
            target=gateway._sweep_strays,
            args=(self.where, "mine", self.made("mine").log, self.schedules), daemon=True)
        sweeping.start()
        self.addCleanup(sweeping.join, 30)
        self.addCleanup(carry_on.touch)
        deadline = time.time() + 15
        while not inside.exists() and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(inside.exists(), "the sweep never got as far as reckoning")

        claiming = gateway.Gateway("target", where=self.where, logs=self.logs,
                                   schedules=self.schedules, root=self.root)
        self.addCleanup(claiming.release)
        with self.assertRaises(gateway.AlreadyRunning):
            claiming.claim()

    def test_a_name_that_cannot_be_asked_about_is_left_alone(self):
        """R-GW-29 — unknown is not free. `standing()` may answer "not running" when it
        cannot tell, because being wrong there costs a misleading line. Being wrong here
        ends somebody else's session."""
        (self.where / "guarded.json").write_text(json.dumps(
            {"working": {"turn": {"pgid": 999999, "since": "then"}}}))
        lock = self.where / "guarded.lock"
        lock.touch()
        lock.chmod(0o000)
        self.addCleanup(lock.chmod, 0o600)

        swept = gateway._sweep_strays(self.where, "mine", self.made("mine").log, self.schedules)

        self.assertEqual([], swept, "it acted on a name it could not ask about")
        self.assertTrue((self.where / "guarded.json").exists(),
                        "it deleted the record of a gateway it could not ask about")


#: One writer of the interruption history, as a program of its own. Two of these racing is
#: not a contrived shape: every gateway that starts writes into every abandoned name's file,
#: so a machine bringing several up at once does exactly this.
NOTES_INTERRUPTIONS = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from rundesk_cli import gateway

schedules, mine, how_many, start = Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), Path(sys.argv[5])
while not start.exists():          # all of them held here, then let go together
    time.sleep(0.002)
for n in range(how_many):
    gateway._note_interrupted("shared", schedules, f"{mine}-{n}", "because")
"""


class WhatTwoWritersDoToOneFile(WithARunDirectory):
    """Read, change, write back — by more than one process, which is the ordinary case.

    Every gateway that starts writes into every abandoned name's interruption file, so a
    reboot bringing several gateways up together has several writers on one file as a
    matter of course. Each read its own snapshot and wrote it back whole, and half of
    everything recorded was lost.
    """

    WRITERS = 4
    EACH = 10

    def test_gateways_noting_interruptions_at_once_lose_none_of_them(self):
        """R-GW-27 — real concurrent processes. Two sequential calls in one process pass
        against a file with no lock at all, which is what the case this replaces did."""
        start = self.scratch() / "go"
        running = [
            subprocess.Popen(
                [PY, "-c", NOTES_INTERRUPTIONS, str(ROOT / "src"), str(self.schedules),
                 f"writer{n}", str(self.EACH), str(start)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            for n in range(self.WRITERS)
        ]
        time.sleep(0.3)   # every one of them up and waiting before any of them writes
        start.touch()
        for one in running:
            _, went_wrong = one.communicate(timeout=60)
            self.assertEqual(0, one.returncode, went_wrong)

        said = gateway.what_was_interrupted("shared", self.schedules)
        wanted = {f"writer{n}-{m}" for n in range(self.WRITERS) for m in range(self.EACH)}
        self.assertLessEqual(len(wanted), gateway.KEPT_INTERRUPTIONS,
                             "the case is only about lost writes, so it stays under the cap")
        self.assertEqual(wanted, set(said),
                         f"{len(wanted) - len(said)} of {len(wanted)} interruptions were lost")

    def test_a_writer_that_cannot_read_the_file_changes_nothing_and_does_not_stop_a_start(self):
        """R-GW-27, R-SCH-17 — the history is worth less than the gateway. It is not worth
        so little that a file nobody can read is replaced with one entry."""
        target = gateway.interrupted_path("shared", self.schedules)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"turn": {"at": "2026-07-25 09:00",,}}')
        gateway._note_interrupted("shared", self.schedules, "new", "because")
        self.assertEqual('{"turn": {"at": "2026-07-25 09:00",,}}', target.read_text(),
                         "it wrote one entry over a file it could not read")

    def test_what_records_what_already_happened_is_asked_to_reach_the_disk(self):
        """The guarantee itself — that a run which already happened is not repeated after
        power loss — cannot be tested here, and R-SCH-20 says so. This proves only that the
        ask is made, so that a later change cannot drop it in silence."""
        asked = []
        self.addCleanup(setattr, os, "fsync", os.fsync)
        real_fsync = os.fsync
        os.fsync = lambda fd: (asked.append(fd), real_fsync(fd))[1]

        gateway._note_interrupted("shared", self.schedules, "turn", "because")
        self.assertTrue(asked, "what has already happened was written without waiting for it")

        asked.clear()
        gateway._written_whole(self.where / "beat.json", "{}")
        self.assertEqual([], asked, "the beat pays for a durability it does not need")


class TakingAGatewayAway(WithARunDirectory):
    """What rundesk keeps for a gateway, once there is no gateway to keep it for."""

    def kept_for(self, name: str) -> dict:
        """Everything rundesk would have written for a gateway of this name."""
        made = {
            "record": self.where / f"{name}.json",
            "lock": self.where / f"{name}.lock",
            "log": self.logs / f"{name}.log",
            "schedules": self.schedules / f"{name}.json",
            "ran": self.schedules / f"{name}.ran.json",
            "seen": self.schedules / f"{name}.seen.json",
            "interrupted": self.schedules / f"{name}.interrupted.json",
        }
        for path in made.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}")
        return made

    def test_forgetting_a_gateway_keeps_what_it_wrote_and_what_was_scheduled(self):
        """R-GW-31, R-GW-18 — an owner tidying a name out of their machine's background
        items has not asked to lose the account of what it did."""
        made = self.kept_for("test2")
        gateway.forget("test2", self.where, self.schedules, self.logs)
        for still in ("log", "schedules", "ran", "interrupted"):
            self.assertTrue(made[still].exists(), f"removing a gateway took its {still}")
        self.assertFalse(made["record"].exists(), "it left behind what the gateway was doing")
        self.assertFalse(made["lock"].exists(), "it left the name looking as though it exists")
        self.assertFalse(made["seen"].exists(),
                         "it left a checkpoint that would report schedules missed while "
                         "the gateway did not exist")

    def test_forgetting_a_gateway_with_its_history_takes_all_of_it(self):
        """R-GW-31 — the other half, so "keeps it" cannot pass by never removing anything."""
        made = self.kept_for("test2")
        gateway.forget("test2", self.where, self.schedules, self.logs, history=True)
        for path in made.values():
            self.assertFalse(path.exists(), f"--purge left {path.name} behind")

    def test_forgetting_a_gateway_never_unlinks_a_lock_something_else_is_holding(self):
        """R-GW-31 — a lock lives on the inode, not the path, so unlinking one another
        process holds hands the name away: the next claim makes a fresh inode, locks that,
        and two gateways answer as one identity. Holding it first is what makes removing
        it safe, and a name that cannot be held is one something is still using."""
        made = self.kept_for("busy")
        holding = os.open(made["lock"], os.O_RDWR)
        self.addCleanup(os.close, holding)
        fcntl.flock(holding, fcntl.LOCK_EX | fcntl.LOCK_NB)

        gateway.forget("busy", self.where, self.schedules, self.logs)

        self.assertTrue(made["lock"].exists(), "it took a name another process was holding")

    def test_forgetting_a_gateway_that_was_never_there_takes_nothing_and_says_so(self):
        """R-GW-31 — asked twice, or for a name that never existed, is not an error."""
        self.assertEqual([], gateway.forget("never-was", self.where, self.schedules, self.logs))

    def test_forgetting_a_gateway_leaves_every_other_gateway_alone(self):
        """R-GW-31 — one name's removal is one name's."""
        mine, theirs = self.kept_for("mine"), self.kept_for("theirs")
        gateway.forget("mine", self.where, self.schedules, self.logs, history=True)
        for path in theirs.values():
            self.assertTrue(path.exists(), f"removing one gateway took another's {path.name}")
        self.assertFalse(mine["record"].exists())


class WhatCannotBeReadIsNotEmpty(WithARunDirectory):
    """A file rundesk keeps is either not there or unreadable, and the two are opposites.

    Every reader worked it out for itself and they disagreed. The one that mattered most
    replaced a file it could not parse with an empty list and reported success — so a
    stray character in a schedules file, or a stalled volume for one moment, took every
    schedule the owner had ever written and said nothing.
    """

    GARBLED = '[{"name": "nightly", "when": "0 4 * * *", "run": ["/bin/echo", "x"]},,]'

    def garbled_for(self, name: str) -> Path:
        target = self.schedules / f"{name}.json"
        target.write_text(self.GARBLED)
        return target

    def test_a_schedules_file_that_cannot_be_read_is_never_written_over(self):
        """R-SCH-17 — the file still holds every schedule as recoverable text."""
        target = self.garbled_for("gateway")
        with self.assertRaises(gateway.Unreadable):
            with gateway.changing_schedules("gateway", self.schedules) as keeping:
                keeping.append({"name": "new", "when": "* * * * *", "run": ["/bin/echo"]})
        self.assertEqual(self.GARBLED, target.read_text(),
                         "it wrote over a file it could not read")

    def test_a_schedules_file_that_is_valid_json_but_not_schedules_is_not_read_as_none(self):
        """R-SCH-17 — parsing is not understanding: a file that reads back as an object
        holds something, and replacing it with an empty list loses it just the same."""
        target = self.schedules / "gateway.json"
        target.write_text('{"nightly": {"when": "0 4 * * *"}}')
        with self.assertRaises(gateway.Unreadable):
            gateway.written_schedules("gateway", self.schedules)
        self.assertEqual('{"nightly": {"when": "0 4 * * *"}}', target.read_text())

    def test_a_schedules_file_that_is_not_there_is_told_from_one_that_cannot_be_read(self):
        """R-SCH-17 — absent and unreadable are distinguishable at the point of decision,
        which is the whole of the fix: one is a gateway that has never been given a
        schedule, and the other is one whose schedules are all still there."""
        self.assertEqual([], gateway.written_schedules("never-had-one", self.schedules))
        self.garbled_for("had-some")
        with self.assertRaises(gateway.Unreadable):
            gateway.written_schedules("had-some", self.schedules)

    def test_a_change_that_changed_nothing_does_not_rewrite_the_file(self):
        """R-SCH-18 — a command that decided to do nothing writes nothing. Rewriting an
        unchanged file puts every schedule at the mercy of a failure nobody asked to
        risk, and `remove` on a name that is not there took that risk every time."""
        target = self.schedules / "gateway.json"
        # Written by hand, with spacing rundesk would not produce: an untouched file has
        # to come back byte for byte, not merely mean the same thing.
        original = '[{"name":   "nightly", "when": "0 4 * * *", "run": ["/bin/echo", "x"]}]'
        target.write_text(original)
        with gateway.changing_schedules("gateway", self.schedules) as keeping:
            self.assertEqual(1, len(keeping), "it did not read what was there")
        self.assertEqual(original, target.read_text(), "it rewrote a file nothing changed")

    def test_a_change_that_did_change_something_is_written(self):
        """R-SCH-18 — the other half, so "never rewrite" cannot pass by never writing."""
        with gateway.changing_schedules("gateway", self.schedules) as keeping:
            keeping.append({"name": "new", "when": "* * * * *", "run": ["/bin/echo"]})
        self.assertEqual(["new"], [one["name"] for one
                                   in gateway.written_schedules("gateway", self.schedules)])

    def test_a_gateway_whose_schedules_cannot_be_read_still_starts_and_says_so(self):
        """R-SCH-17 — a command refuses, because it was asked to change the file. A
        gateway that refused to start over it would take everything else it does down
        with the one thing that is broken."""
        self.garbled_for("gateway")
        gateway.seen_path("gateway", self.schedules).write_text(json.dumps({"at": time.time()}))
        gw = self.made()
        gw.claim()
        self.assertTrue(gateway.standing("gateway", self.where).running)
        self.assertIn("could not be read", gateway.log_path("gateway", self.logs).read_text())

    async def test_no_schedule_runs_while_the_file_cannot_be_read(self):
        """R-SCH-17 — and it is said once, not on every tick for as long as it is broken."""
        from rundesk_cli import schedule as schedules_module
        self.garbled_for("gateway")
        gw = self.made()
        gw.claim()
        from datetime import datetime
        gw._fire(schedules_module, datetime(2026, 7, 25, 9, 0))
        gw._fire(schedules_module, datetime(2026, 7, 25, 9, 1))
        await asyncio.sleep(0.2)
        self.assertEqual({}, gw.running, "it ran something out of a file it could not read")
        said = gateway.log_path("gateway", self.logs).read_text()
        self.assertEqual(1, said.count("no schedule can run"),
                         "it complained again on the next tick")

    def test_a_record_that_cannot_be_read_is_kept_rather_than_removed(self):
        """R-GW-26 — the record is the only thing naming a process group nobody owns.
        Reading "I could not tell" as "there is nothing left" throws away the sole means
        of ever finding it again, and reports having tidied up."""
        record = self.where / "abandoned.json"
        record.write_text('{"working": {"turn": {"pgid": 4242,,}}}')
        (self.where / "abandoned.lock").touch()
        swept = gateway._sweep_strays(self.where, "mine", self.made("mine").log, self.schedules)
        self.assertEqual([], swept, "it claimed to have swept a record it could not read")
        self.assertTrue(record.exists(), "it deleted the only record naming abandoned work")


if __name__ == "__main__":
    unittest.main()
