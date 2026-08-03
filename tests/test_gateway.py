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
import io
import json
import logging
import os
import pathlib
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import activity, config, gateway, process, recovery, schedule, store  # noqa: E402
from rundesk import role_run as role_runs  # noqa: E402

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
        # An install of its own, and an empty one: claiming a name asks whether this
        # install fits the Python running it, and a gateway built without a root asks
        # that of the developer's real checkout. With dependencies declared, they live
        # only in the install's virtualenv — so every one of these cases refused to
        # start on the machine of anyone who had run the installer, and passed in CI,
        # which never has one. Nothing here is about fitness; `WhatItIsMadeOf` is,
        # and builds the installs it needs.
        self.root = Path(tempfile.mkdtemp(prefix="rundesk-root-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        # What this gateway's agent keeps. Handed over already opened, the way `cmd_serve`
        # hands one over: a gateway reads rows out of it and never asks whose they are.
        self.records = self.some_records()
        self.addCleanup(setattr, gateway, "STOP_SECONDS", gateway.STOP_SECONDS)
        gateway.STOP_SECONDS = 2.0
        self.addCleanup(setattr, process, "GRACE_SECONDS", process.GRACE_SECONDS)
        process.GRACE_SECONDS = 0.5

    def some_records(self):
        """One agent's records, in a directory of their own. One per agent is the whole of
        the isolation now: a gateway has no way to name another's schedules because it is
        handed the only store it can reach."""
        at = Path(tempfile.mkdtemp(prefix="rundesk-records-"))
        self.addCleanup(shutil.rmtree, at, True)
        kept = store.Store(store.path_for(at))
        kept.made()
        return kept

    def made(self, name: str = gateway.DEFAULT_NAME, records=False,
             **more) -> gateway.Gateway:
        """A gateway in this case's own directories. Anything else a case needs to hand it
        goes through `**more`, so a new collaborator does not mean a new fixture."""
        gw = gateway.Gateway(name, where=self.where, logs=self.logs, root=self.root,
                             records=self.records if records is False else records,
                             **more)
        self.addCleanup(gw.release)
        return gw

    def schedules_for(self, name: str, *written, records=None) -> None:
        """Schedules, as the rows an agent keeps. `name` is the gateway they belong to,
        which is now the store they are in rather than a file named for it.

        Takes what a schedules file used to hold, so a case still reads as the thing it is
        about: `when` is the cron and `run` is the program. A row that names nothing is
        `command` of `[]` — the database refuses a schedule that is neither a program nor a
        prompt, and an empty program is how "names nothing this gateway can start" is still
        reachable.
        """
        kept = records if records is not None else self.records
        for one in written:
            # `at` is the other way of saying when — the one moment this runs. Never both,
            # which is what the records themselves insist on.
            moment = one.get("at")
            kept.remember_schedule(
                one["name"], None if moment else one.get("when", ""), store.stamped(),
                at=moment,
                command=one.get("run") if one.get("run") is not None else [],
                enabled=one.get("enabled", True))

    def what_each_schedule_last_did(self, records=None) -> dict:
        """What each of this gateway's schedules last did, by name — the reader a case uses
        where it used to read a file beside the schedules."""
        kept = records if records is not None else self.records
        return {row["name"]: row for row in kept.schedules()}

    def scratch(self) -> Path:
        made = Path(tempfile.mkdtemp(prefix="rundesk-scratch-"))
        self.addCleanup(shutil.rmtree, made, True)
        return made

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
        # Leave enough room between the observation wait and the stale threshold for a
        # loaded older interpreter to schedule the heartbeat task.
        gateway.BEAT_SECONDS = 0.2
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
        # The root it defaults from as well, or this asserts wherever the suite happens to
        # have pointed the data directory rather than what an owner with nothing set gets.
        pointed = os.environ.pop("RUNDESK_DATA_DIR", None)
        if pointed is not None:
            self.addCleanup(os.environ.__setitem__, "RUNDESK_DATA_DIR", pointed)
        self.assertEqual(Path.home() / ".rundesk" / "data" / "run", gateway.home())

    def test_what_it_writes_goes_beside_the_run_directory_by_default(self):
        """R-GW-18 — history and state are kept apart, so giving a name back cannot take
        the record of what happened with it."""
        self.addCleanup(os.environ.__setitem__, "RUNDESK_LOG_DIR", os.environ["RUNDESK_LOG_DIR"])
        del os.environ["RUNDESK_LOG_DIR"]
        # The root it defaults from as well, or this asserts wherever the suite happens to
        # have pointed the data directory rather than what an owner with nothing set gets.
        pointed = os.environ.pop("RUNDESK_DATA_DIR", None)
        if pointed is not None:
            self.addCleanup(os.environ.__setitem__, "RUNDESK_DATA_DIR", pointed)
        self.assertEqual(Path.home() / ".rundesk" / "data" / "logs", gateway.logs_home())
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
        """R-GW-15 — the guard is on the same work, never on there being work.

        Process creation is delayed on purpose. `running` is populated before `Program.start`
        finishes, so counting its entries used to call `end_all` while every program still had
        `_proc=None`; the no-op stop was followed by three processes starting and the test
        waiting on them forever. A loaded macOS runner made that race repeatable.
        """
        starts = process.Program.start

        async def slowly(program):
            await asyncio.sleep(0.1)
            await starts(program)

        self.addCleanup(setattr, process.Program, "start", starts)
        process.Program.start = slowly
        gw = self.made()
        gw.claim()
        running = [
            asyncio.ensure_future(gw.start(FOREVER, as_name=f"conversation-{i}", silence=None))
            for i in range(3)
        ]
        await self._holding(gw)
        self.assertEqual(3, len(gw.running))
        await process.end_all(list(gw.running.values()))
        await asyncio.wait_for(asyncio.gather(*running), 10)

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
        await self._holding(gw)
        self.assertEqual(3, len(gw.running))
        await process.end_all(list(gw.running.values()))
        await asyncio.wait_for(asyncio.gather(*running), 10)



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
        deadline = time.monotonic() + 5
        record = self.where / f"{gw.name}.json"
        said = json.loads(record.read_text())
        while "a-conversation" not in said["working"] and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
            said = json.loads(record.read_text())
        self.assertIn("a-conversation", said["working"])
        self.assertEqual(
            next(iter(gw.running.values())).pid, said["working"]["a-conversation"]["pgid"]
        )
        await process.end_all(list(gw.running.values()))
        await running
        after = json.loads(record.read_text())
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
        await self._holding(gw)
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

    def test_a_machine_that_will_not_say_when_a_group_started_keeps_the_record(self):
        """R-GW-16, R-GW-26 — asked and not told is not "it is a stranger". `started_at`
        answers None for a `ps` that timed out or a fork that failed, and a loaded machine
        at boot is both when that happens and when work gets left behind.

        Read as a mismatch it took the branch below: the group left running *and* the only
        record naming it dropped, so nothing could ever find it again — the loss
        `_anything_left` refuses one function up. Kept, exactly as a record carrying no
        fingerprint at all is kept."""
        asked = []
        became = gateway._end_left_running(
            "a-conversation", {"pgid": 4242, "since": "when ours started"},
            self.made("orphaned").log,
            present=lambda pgid: True,
            started=lambda pgid: None,          # the machine would not answer
            ask=lambda pgid, sig: asked.append((pgid, sig)) or True,
            gone_within=lambda pgid, patience: False,
        )
        self.assertTrue(became.keep, "it dropped the only record naming live work")
        self.assertFalse(became.swept)
        self.assertEqual([], asked, "it signalled a group it could not prove was ours")

    def test_a_group_the_machine_says_began_elsewhere_is_not_kept(self):
        """R-GW-16 — the other half, so the fix above cannot swallow it: a real, different
        answer still proves the number came round again, and naming a stranger in our
        record is how the next start comes to aim at it."""
        asked = []
        became = gateway._end_left_running(
            "a-conversation", {"pgid": 4242, "since": "when ours started"},
            self.made("orphaned").log,
            present=lambda pgid: True,
            started=lambda pgid: "when a stranger started",
            ask=lambda pgid, sig: asked.append((pgid, sig)) or True,
            gone_within=lambda pgid, patience: False,
        )
        self.assertFalse(became.keep)
        self.assertEqual([], asked, "it signalled a stranger's process group")

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
        from rundesk import schedule
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

        self.records.schedule_fired = cannot_write
        gw._fire(self.schedule, datetime(2026, 3, 1, 9, 30))
        await asyncio.sleep(0.2)
        self.assertEqual({}, gw.running, "it started work it could not record having started")

    async def test_what_a_schedule_last_did_never_moves_backwards(self):
        """R-SCH-9 — a long run finishing after a later occurrence was already recorded put
        the earlier minute back, and a gateway reading that took the later minute for one
        that had never fired."""
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, {"name": "nightly", "when": "0 9 * * *", "run": ["/bin/true"]})
        gw._remember_firing("nightly", datetime(2026, 3, 1, 9, 0))
        gw._remember_firing("nightly", datetime(2026, 3, 1, 9, 5))
        gw._remember_firing("nightly", datetime(2026, 3, 1, 9, 0))   # the late arrival
        said = self.what_each_schedule_last_did()
        self.assertEqual("2026-03-01 09:05", said["nightly"]["last_auto_run_at"],
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
            said = self.what_each_schedule_last_did()
            self.assertIn("slow", said, "nothing was written down until the run finished")
            self.assertEqual("2026-03-01 09:30", said["slow"]["last_auto_run_at"])
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
            if self.what_each_schedule_last_did().get("named", {}).get(
                    "last_outcome") == "could not start":
                break
            await asyncio.sleep(0.05)
        said = self.what_each_schedule_last_did()
        self.assertEqual("could not start", said.get("named", {}).get("last_outcome"),
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
        said = self.what_each_schedule_last_did()
        self.assertEqual("interrupted", said["long"]["last_outcome"],
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
        schedules that agent's alone. True by construction now rather than by guarding: a
        gateway is handed the only store it can reach, so there is no directory to name
        another's schedules in and no name to name them by."""
        theirs = self.some_records()
        self.schedules_for("someone-else", self._writes(), records=theirs)
        gw = self.made("mine")
        gw.claim()
        gw._fire(self.schedule, __import__("datetime").datetime.now())
        await asyncio.sleep(0.5)
        self.assertFalse(self.told.exists(), "a gateway ran another gateway's schedule")
        self.assertEqual([], self.records.schedules(), "it read schedules that were not its")
        self.assertEqual(["ran"], [row["name"] for row in theirs.schedules()],
                         "the other agent's schedule was not left where it was")

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


class AProgramTheGatewayStartsReadsWhatTheGatewayReads(WithARunDirectory):
    """R-SCH-27 — the regression check that keeps one split from coming back. A gateway is
    told where agents are kept and its children were not, so `rundesk schedules ava run
    nightly` started `rundesk ask ava` and the child answered NO SUCH AGENT while the
    gateway that started it was running ava. The environment a gateway builds for a program
    is deliberately bare — a gateway must not hand every secret it holds to everything it
    runs — so the fix is to put this there on purpose, not to start inheriting.

    Proved with the repository's own command rather than a stand-in that prints a variable:
    what has to hold is that a real `rundesk` resolves a real agent, and a stand-in cannot
    be wrong about the thing this exists to catch.
    """

    #: The command an installed rundesk is, by where it actually is. A schedule may name it
    #: and `CLI.md` says to; nothing else here would notice if it stopped working.
    RUNDESK = Path(__file__).resolve().parent.parent / "rundesk"

    def setUp(self):
        super().setUp()
        from rundesk import agent
        # Two roots, and the ambient one is *not* the gateway's. Pointed at the same place
        # the case proves nothing: the child would find the agent by falling back, which is
        # exactly the accident this guards against.
        self.elsewhere = Path(tempfile.mkdtemp(prefix="rundesk-elsewhere-"))
        self.addCleanup(shutil.rmtree, self.elsewhere, True)
        self.addCleanup(os.environ.pop, "RUNDESK_AGENTS_DIR", None)
        os.environ["RUNDESK_AGENTS_DIR"] = str(self.elsewhere)
        self.data_at = Path(tempfile.mkdtemp(prefix="rundesk-data-"))
        self.addCleanup(shutil.rmtree, self.data_at, True)
        self.addCleanup(os.environ.pop, "RUNDESK_DATA_DIR", None)
        os.environ["RUNDESK_DATA_DIR"] = str(self.data_at)
        config.ensure(self.data_at)
        self.agents = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.agents, True)
        agent.add("probe", self.agents)

    def served(self, name: str = gateway.DEFAULT_NAME) -> gateway.Gateway:
        gw = gateway.Gateway(name, where=self.where, logs=self.logs, root=self.root,
                             agents=self.agents)
        self.addCleanup(gw.release)
        return gw

    async def test_a_program_the_gateway_starts_finds_the_agents_the_gateway_is_running(self):
        """R-SCH-27 — the whole of finding 22, in the one command that reproduced it."""
        gw = self.served()
        gw.claim()
        outcome = await gw.start([str(self.RUNDESK), "agents"])
        self.assertTrue(outcome.ok, f"the command failed: {outcome.reason}: {outcome.output}")
        self.assertIn("probe", outcome.output,
                      "a program the gateway started looked somewhere else for agents")

    async def test_a_gateway_told_nothing_hands_on_what_it_was_told_itself(self):
        """R-SCH-27 — a gateway built without one is not a gateway whose children guess:
        it passes on the root this process was given, which is the same answer."""
        os.environ["RUNDESK_AGENTS_DIR"] = str(self.agents)
        gw = self.made()
        gw.claim()
        outcome = await gw.start([str(self.RUNDESK), "agents"])
        self.assertIn("probe", outcome.output, f"{outcome.reason}: {outcome.output}")


class WhatEveryAdapterOfOneGatewayIsTold(WithARunDirectory):
    """R-DIS-15 — adapters share one lifetime, and a successor gets another."""

    class Surface:
        env = {"SOMETHING": "kept"}
        #: What this surface reads its own credential from, which the install's values are
        #: never given to it under. Empty here, and named in the case that proves it.
        channel_secrets = frozenset()

    def made(self, name="gateway", **more):
        """A gateway whose values are produced by a stand-in, never by this machine's own.

        The whole point of the collaborator: these cases run with no store, no keeper and
        nothing of the owner's, on a machine that may have all three.
        """
        async def kept(exclude=()):
            from rundesk import secret

            return secret.Resolved(values={one: value for one, value
                                           in getattr(self, "keeping", {}).items()
                                           if one not in set(exclude)})

        return super().made(name, secrets_resolving=kept, **more)

    async def test_the_gateway_lifetime_is_shared_only_by_its_own_adapters(self):
        first = self.made()
        successor = self.made("successor")
        one = await first._for_a_channel(self.Surface())
        two = await first._for_a_channel(self.Surface())
        later = await successor._for_a_channel(self.Surface())

        self.assertEqual(one["RUNDESK_GATEWAY"], two["RUNDESK_GATEWAY"])
        self.assertNotEqual(one["RUNDESK_GATEWAY"], later["RUNDESK_GATEWAY"])
        self.assertEqual("kept", one["SOMETHING"],
                         "naming the gateway dropped what the adapter was already told")

    async def test_every_adapter_is_told_the_version_that_actually_came_up(self):
        """R-UPD-46 — a surface reporting a version it asked a forge for would name the
        newest *published* release rather than the one it is running, and one reading an
        updater transcript would have nothing to read after an unattended update."""
        from rundesk import __version__, updater
        told = await self.made()._for_a_channel(self.Surface())
        self.assertEqual(__version__, told["RUNDESK_VERSION"])
        self.assertEqual(updater.release_url(__version__), told["RUNDESK_RELEASE_URL"])

    async def test_every_adapter_is_given_the_values_this_install_keeps(self):
        """R-SEC-1 — a channel adapter is a program rundesk starts like any other, so an
        integration command it runs finds the same credential a brain's would."""
        self.keeping = {"GITHUB_TOKEN": "gh-x"}

        told = await self.made()._for_a_channel(self.Surface())

        self.assertEqual("gh-x", told["GITHUB_TOKEN"])

    async def test_a_surface_is_never_given_the_value_it_reads_its_own_credential_from(self):
        """R-SEC-29 — the adapter reads its variable before the file beside it, and two
        agents may hold two different bots. One install-wide value would make them the same
        bot, silently, with each agent's record still naming a file nobody read."""
        self.keeping = {"DISCORD_TOKEN": "one-bot", "GITHUB_TOKEN": "gh-x"}

        class Discord(self.Surface):
            channel_secrets = frozenset({"DISCORD_TOKEN"})

        told = await self.made()._for_a_channel(Discord())

        self.assertNotIn("DISCORD_TOKEN", told)
        self.assertEqual("gh-x", told["GITHUB_TOKEN"],
                         "excluding one name excluded the rest with it")

    async def test_what_a_gateway_already_decided_survives_a_value_claiming_its_name(self):
        """R-SEC-14 — the merge is never over what rundesk built, at this layer too."""
        self.keeping = {"RUNDESK_GATEWAY": "taken", "SOMETHING": "taken"}

        told = await self.made()._for_a_channel(self.Surface())

        self.assertNotEqual("taken", told["RUNDESK_GATEWAY"])
        self.assertEqual("kept", told["SOMETHING"])


class TheClockIsLookedAtAsSoonAsThereIsAGatewayToLookAtIt(WithARunDirectory):
    """R-SCH-26 — the tick slept before its first look, so a gateway examined nothing for
    twenty seconds after claiming its name. A schedule is due only in its stated minute, so
    a gateway the machine started or recovered in the last twenty seconds of that minute
    lost the occurrence outright — and nothing else covers it: what fell due while nothing
    was running is reported and deliberately not run late (R-SCH-4), and that runs during
    `claim`, before this gap begins.
    """

    def setUp(self):
        super().setUp()
        from rundesk import schedule
        self.schedule = schedule
        self.told = self.scratch() / "it-ran"

    def _appends(self, name="ran"):
        """A schedule whose program can be run twice and say so. Counting is the point
        here: an immediate look plus an ordinary tick must still be one firing."""
        return {"name": name, "when": "* * * * *",
                "run": [PY, "-c",
                        f"import pathlib; p = pathlib.Path({str(self.told)!r}); "
                        f"p.write_text((p.read_text() if p.exists() else '') + 'x')"]}

    def _ran(self) -> int:
        return len(self.told.read_text()) if self.told.exists() else 0

    async def _ran_within(self, seconds: float) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self._ran():
                return True
            await asyncio.sleep(0.02)
        return False

    async def test_a_gateway_looks_at_the_clock_as_soon_as_it_has_its_name(self):
        """R-SCH-26 — with the interval set far longer than the case waits, anything that
        runs at all ran because the first look does not wait for it."""
        self.addCleanup(setattr, gateway, "TICK_SECONDS", gateway.TICK_SECONDS)
        gateway.TICK_SECONDS = 600.0
        gw = self.made()
        self.schedules_for(gw.name, self._appends())
        serving = asyncio.ensure_future(gw.serve())
        await self._up(gw)
        # Generous, and it costs nothing when it works: this waits for a real subprocess to
        # be spawned and finish, and the whole suite behind it has just loaded the machine.
        # What makes the case decisive is the interval above, not this window.
        started = await self._ran_within(30.0)
        gw.ask_to_stop()
        await asyncio.wait_for(serving, 10)
        self.assertTrue(started, "nothing due was started until a whole interval had passed")

    async def test_the_first_look_and_the_ordinary_tick_do_not_start_one_minute_twice(self):
        """R-SCH-9, R-SCH-26 — the durable per-minute guard is what makes looking early
        safe, and it is the thing an extra look would have broken.

        **The whole window has to sit inside one minute**, and that is arranged rather than
        hoped for. The schedule is due every minute against the wall clock, so a window
        that crosses a boundary sees a *second* firing that is entirely correct — and this
        case then fails saying a minute was started twice, which is not what happened. It
        failed exactly that way once on a loaded CI runner and passes on every unloaded
        machine, which is the signature.
        """
        self.addCleanup(setattr, gateway, "TICK_SECONDS", gateway.TICK_SECONDS)
        gateway.TICK_SECONDS = 0.05
        # Start early in a minute, so the first firing and the second of ticking after it
        # cannot land either side of a boundary. Waiting is cheap and only ever happens in
        # the last quarter of a minute.
        while datetime.now().second > 45:
            await asyncio.sleep(0.5)
        gw = self.made()
        self.schedules_for(gw.name, self._appends())
        began = datetime.now().minute
        serving = asyncio.ensure_future(gw.serve())
        await self._up(gw)
        self.assertTrue(await self._ran_within(30.0), "nothing due was started at all")
        # Long enough for many more ticks than the one that has already happened.
        await asyncio.sleep(1.0)
        gw.ask_to_stop()
        await asyncio.wait_for(serving, 10)
        if datetime.now().minute != began:
            # Alignment above makes this effectively unreachable, and if a machine is slow
            # enough to reach it anyway then a second firing is the right answer and this
            # case has measured nothing. Said out loud rather than passed quietly.
            self.skipTest("the window crossed a minute, so a second firing is correct here")
        self.assertEqual(1, self._ran(), "one minute was started more than once")

    async def test_a_stop_asked_for_while_it_takes_hold_starts_nothing(self):
        """R-GW-6, R-SCH-26 — the immediate look happens after `claim`, which is inside the
        window a supervisor may ask a gateway to stop in. Looking at once must not be a way
        to start work a shutdown had already refused."""
        self.addCleanup(setattr, gateway, "TICK_SECONDS", gateway.TICK_SECONDS)
        gateway.TICK_SECONDS = 0.05
        gw = self.made()
        self.schedules_for(gw.name, self._appends())
        gw.ask_to_stop()
        self.assertEqual(0, await asyncio.wait_for(gw.serve(), 10))
        self.assertEqual(0, self._ran(), "a gateway on its way out started work at once")

    async def test_the_beat_still_waits_before_saying_anything(self):
        """R-SCH-26 — `at_once` is asked for rather than assumed, because the two callers of
        the loop want opposite things: the beat has nothing to report until there is
        something to report about, and a beat before the record exists is a beat about
        nothing."""
        gw = self.made()
        looked = []
        held = asyncio.ensure_future(gw._over_and_over(60.0, lambda: looked.append(1), "%s"))
        await asyncio.sleep(0.1)
        held.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await held
        self.assertEqual([], looked, "the loop looked before waiting without being asked to")


class WhatCarriesAcrossARestart(WithARunDirectory):
    """Cycling a gateway is the most ordinary thing that happens to one, and two things
    were lost every time it did."""

    def setUp(self):
        super().setUp()
        from rundesk import schedule
        self.schedule = schedule
        self.told = self.scratch() / "it-ran"

    def _writes(self):
        return {"name": "ran", "when": "* * * * *",
                "run": [PY, "-c", f"import pathlib; pathlib.Path({str(self.told)!r}).write_text('yes')"]}

    def _writes_once(self, at: str):
        """The same program, on a schedule that states one moment rather than a repetition."""
        return {"name": "ran", "at": at,
                "run": [PY, "-c",
                        f"import pathlib; pathlib.Path({str(self.told)!r}).write_text('yes')"]}

    async def _ran(self, gw, moment) -> bool:
        gw._fire(self.schedule, moment)
        deadline = time.time() + 10
        while not self.told.exists() and time.time() < deadline:
            await asyncio.sleep(0.05)
        return self.told.exists()

    async def test_a_schedule_stating_one_moment_runs_when_the_clock_reaches_it(self):
        """R-SCH-2 — the clock is what starts it, and this is the only thing that ever does.
        A moment that never fires at all would make every claim below vacuously true."""
        from datetime import datetime
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, self._writes_once("2026-07-25 09:00"))
        self.assertTrue(await self._ran(gw, datetime(2026, 7, 25, 9, 0)),
                        "the moment came and nothing started")
        self.assertEqual("2026-07-25 09:00",
                         self.what_each_schedule_last_did()["ran"]["last_auto_run_at"])

    async def test_a_schedule_that_has_run_its_one_moment_can_never_be_due_again(self):
        """R-SCH-37 — through a gateway restart, a clock put back, and a second gateway
        starting. Not by trusting a flag: what refuses it is the record of the firing, which
        is durable, is written before the work begins, and reads the same to all three."""
        from datetime import datetime
        moment = datetime(2026, 7, 25, 9, 0)
        first = self.made()
        first.claim()
        self.schedules_for(first.name, self._writes_once("2026-07-25 09:00"))
        self.assertTrue(await self._ran(first, moment))
        first.release()
        self.told.unlink()

        # a gateway that has just come up, holding nothing in memory about what has run
        again = self.made()
        again.claim()
        again._fire(self.schedule, moment)
        await asyncio.sleep(0.5)
        self.assertFalse(self.told.exists(), "a restart ran a moment that was already spent")

        # the clock stepped backwards, to before the moment — where a flag saying "in the
        # past" would say this is waiting to happen
        again._fire(self.schedule, datetime(2026, 7, 25, 8, 0))
        await asyncio.sleep(0.5)
        self.assertFalse(self.told.exists(), "a clock put back brought a spent moment round")

        # and its own minute again, from a third gateway of the same name
        again.release()
        third = self.made()
        third.claim()
        third._fire(self.schedule, moment)
        await asyncio.sleep(0.5)
        self.assertFalse(self.told.exists(), "a second gateway ran a moment that was spent")

    async def test_a_moment_whose_firing_cannot_be_read_back_as_a_time_is_still_spent(self):
        """R-SCH-37 — and the hole the older guard leaves. What has run is picked up on the
        way up by *parsing* each minute, and a row it cannot parse is silently passed over, so
        that schedule reads as never having run. For a repeating one that costs a single
        early firing; for a moment it runs work a second time that was only ever to happen
        once. What refuses it here asks whether anything is written, never what it says."""
        from datetime import datetime
        moment = datetime(2026, 7, 25, 9, 0)
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, self._writes_once("2026-07-25 09:00"))
        self.assertTrue(await self._ran(gw, moment))
        gw.release()
        self.told.unlink()
        self.records.schedule_fired("ran", "whenever it was", "finished")

        again = self.made()
        again.claim()
        self.assertNotIn("ran", again._ran,
                         "the case is arranging nothing — the minute parsed after all")
        again._fire(self.schedule, moment)
        await asyncio.sleep(0.5)
        self.assertFalse(self.told.exists(),
                         "a firing nobody could read was taken as never having happened")

    async def test_a_moment_that_passed_while_nothing_ran_is_not_run_late(self):
        """R-SCH-4 — and it is the whole of why a moment is due in its own minute and in no
        other. Nothing suppresses this: there is simply no later minute in which it is due."""
        from datetime import datetime
        gw = self.made()
        gw.claim()
        self.schedules_for(gw.name, self._writes_once("2026-07-25 09:00"))
        gw._fire(self.schedule, datetime(2026, 7, 25, 9, 1))
        gw._fire(self.schedule, datetime(2026, 7, 26, 9, 0))
        await asyncio.sleep(0.5)
        self.assertFalse(self.told.exists(), "a moment that had passed was run late")
        # and nothing durable says it ever ran, which is what tells the two kinds of over
        # apart afterwards (R-SCH-40)
        self.assertIsNone(self.what_each_schedule_last_did()["ran"]["last_auto_run_at"])

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
        first._remember_outcome("quick", "finished")
        self.assertIn("quick", self.what_each_schedule_last_did())
        first.release()

        again = self.made()
        again.claim()
        carried = self.what_each_schedule_last_did()
        self.assertIn("quick", carried, "restarting wiped what the schedules had done")
        self.assertEqual("finished", carried["quick"]["last_outcome"])

    def _last_up(self, seconds_ago: float) -> None:
        """Say when a gateway of this name was last known to be going round.

        Written through the store's own stamp rather than formatted here: what it holds is
        UTC and a schedule is stated in local time, and a case that wrote the string itself
        would be the second copy of that format the seam exists to prevent."""
        self.records.seen(store.stamped(lambda: time.time() - seconds_ago))

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
        self.assertIsNotNone(self.records.last_seen(),
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
                "from rundesk import gateway\n"
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
                "from rundesk import gateway\n"
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
        like work that said nothing at all, which is the one reading that misleads.

        A receiver that never recovers loses the record, so the outcome says so: an
        account with holes in it is not one anything downstream can act on, whoever is at
        fault for the holes. A receiver that fails and then recovers is the other case,
        and it is `refused` alone with the outcome left intact."""
        gw = self.made()
        gw.claim()

        def refuses(_record):
            raise RuntimeError("this receiver is broken")

        outcome = await asyncio.wait_for(gw.start(
            [PY, "-c", "import sys; sys.stdout.write('{\"a\":1}\\n'); sys.stdout.flush()"],
            as_name="refused", silence=None, sink=refuses,
        ), 20)
        self.assertEqual(1, outcome.undelivered, "the record it never took was written off")
        self.assertFalse(outcome.ok, "a run whose only record was lost reported success")
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
        said = recovery.what_was_interrupted("gateway", self.logs)
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
        said = recovery.what_was_interrupted("gateway", self.logs)
        self.assertFalse(said["turn"]["ended"], "something still running was called gone")
        self.assertIn("ours", said["turn"]["why"])

    async def test_a_record_that_does_not_say_what_was_running_is_still_answered_for(self):
        """R-GW-23 — the least we know is still more than silence."""
        (self.where / "gateway.json").write_text(json.dumps(
            {"name": "gateway", "working": {"turn": {"since": "x"}}}))
        gw = self.made()
        gw.claim()
        said = recovery.what_was_interrupted("gateway", self.logs)
        self.assertIn("turn", said)
        self.assertIsNone(said["turn"]["pgid"])

    async def test_work_left_under_a_name_nobody_uses_is_answered_for_under_that_name(self):
        """R-GW-21, R-GW-23 — swept by whichever gateway happens to start, but recorded
        against the gateway it belonged to, which is where anything asking would look."""
        self._left_behind(name="abandoned", work="its-turn")
        gw = self.made("mine")
        gw.claim()
        self.assertIn("its-turn", recovery.what_was_interrupted("abandoned", self.logs))
        self.assertEqual({}, recovery.what_was_interrupted("mine", self.logs),
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
        said = recovery.what_was_interrupted(gw.name, self.logs)
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
        self.assertIn("turn", recovery.what_was_interrupted("gateway", self.logs))

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
        self.addCleanup(setattr, recovery, "KEPT_INTERRUPTIONS", recovery.KEPT_INTERRUPTIONS)
        recovery.KEPT_INTERRUPTIONS = 3
        for n in range(10):
            recovery.note_interrupted("gateway", self.logs, f"turn-{n}", "because")
        said = recovery.what_was_interrupted("gateway", self.logs)
        self.assertEqual(3, len(said), "it kept every interruption there had ever been")
        self.assertIn("turn-9", said, "it kept the oldest and threw away the newest")

    async def test_one_gateway_noting_an_interruption_does_not_erase_anothers(self):
        """R-GW-23 — a gateway sweeping an abandoned name writes into *that* name's file,
        so two writers working from their own snapshots is a real shape here."""
        recovery.note_interrupted("shared", self.logs, "first", "because")
        recovery.note_interrupted("shared", self.logs, "second", "because")
        said = recovery.what_was_interrupted("shared", self.logs)
        self.assertEqual({"first", "second"}, set(said), "one write erased the other")


def ended(child) -> None:
    """See this child off, however it got there.

    Killed rather than only waited on: one that never noticed it was asked to stop would
    otherwise fail the *cleanup*, which reports the wrong case and leaves the process
    behind anyway. And both halves are suppressed — these cases run inside async tests,
    where asyncio's child watcher may have reaped it first, and reaping twice raises.
    """
    with contextlib.suppress(ProcessLookupError, OSError):
        child.kill()
    with contextlib.suppress(subprocess.TimeoutExpired, ChildProcessError):
        child.wait(timeout=30)


#: A gateway of this name, holding it and running something, for as long as it is left to.
#: Its own process so the lock is genuinely another process's — a lock taken twice in one
#: process is granted, which is the one thing this must not accidentally prove.
HOLDS_ITS_NAME = """
import json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from rundesk import gateway

where, name, ready, stop = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5])
mine = gateway.Gateway(name, where=where, logs=Path(sys.argv[6]), root=Path(sys.argv[7]))
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
        # Bounded, and tolerant of having been reaped by somebody else. These cases run
        # inside an async test, where asyncio's child watcher may collect any child before
        # `wait` sees it — and an unbounded `wait` on a pid another reaper already took
        # never returns at all. It is the group being gone that this needs, not the exit
        # status, so that is what it waits for and what it asserts.
        with contextlib.suppress(subprocess.TimeoutExpired, ChildProcessError):
            went.wait(timeout=30)
        deadline = time.time() + 30
        while gateway._still_there(went.pid) and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(gateway._still_there(went.pid), "the process never went")

        self.assertTrue(gateway._ask_group(went.pid, signal.SIGTERM),
                        "a group that had already gone was read as the machine refusing")

    def test_a_machine_that_refuses_the_signal_is_told_from_one_that_granted_it(self):
        """R-GW-28 — the distinction the whole decision rests on, at its own level.

        **No real group is named here, and none ever should be.** `killpg` is only defined
        as "that group" for a group id above one; at one and at zero it degenerates, and on
        Linux group one means *every process this user may signal*. An earlier version of
        this case asked group one to die and took the whole machine's session with it —
        which on a runner is the job, the shell and the agent reporting the result, so the
        step hung forever with an empty log. Group zero is the caller's own, which is no
        better.

        The refusal is the machine's answer, so the machine's answer is what is replaced.
        """
        refused = []

        def would_not(pgid, sig):
            refused.append((pgid, sig))
            raise PermissionError("not yours to signal")

        self.addCleanup(setattr, os, "killpg", os.killpg)
        os.killpg = would_not

        self.assertFalse(gateway._ask_group(4242, signal.SIGKILL),
                         "a refused signal was reported as sent")
        self.assertEqual([(4242, signal.SIGKILL)], refused, "it never asked at all")


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
             str(told), str(stop), str(self.logs), str(self.root)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(ended, child)
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

        swept = gateway._sweep_strays(self.where, "mine", self.made("mine").log, self.logs)

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
            args=(self.where, "mine", self.made("mine").log, self.logs), daemon=True)
        sweeping.start()
        self.addCleanup(sweeping.join, 30)
        self.addCleanup(carry_on.touch)
        deadline = time.time() + 15
        while not inside.exists() and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(inside.exists(), "the sweep never got as far as reckoning")

        claiming = gateway.Gateway("target", where=self.where, logs=self.logs,
                                   root=self.root)
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

        swept = gateway._sweep_strays(self.where, "mine", self.made("mine").log, self.logs)

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
from rundesk import recovery

schedules, mine, how_many, start = Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), Path(sys.argv[5])
while not start.exists():          # all of them held here, then let go together
    time.sleep(0.002)
for n in range(how_many):
    recovery.note_interrupted("shared", schedules, f"{mine}-{n}", "because")
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
                [PY, "-c", NOTES_INTERRUPTIONS, str(ROOT / "src"), str(self.logs),
                 f"writer{n}", str(self.EACH), str(start)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            for n in range(self.WRITERS)
        ]
        # Seen off whatever happens below. A writer left behind by a failing assertion
        # keeps the file's lock and its own pipe, and the next case then waits on both.
        for one in running:
            self.addCleanup(ended, one)
        time.sleep(0.3)   # every one of them up and waiting before any of them writes
        start.touch()
        for one in running:
            _, went_wrong = one.communicate(timeout=60)
            self.assertEqual(0, one.returncode, went_wrong)

        said = recovery.what_was_interrupted("shared", self.logs)
        wanted = {f"writer{n}-{m}" for n in range(self.WRITERS) for m in range(self.EACH)}
        self.assertLessEqual(len(wanted), recovery.KEPT_INTERRUPTIONS,
                             "the case is only about lost writes, so it stays under the cap")
        self.assertEqual(wanted, set(said),
                         f"{len(wanted) - len(said)} of {len(wanted)} interruptions were lost")

    def test_a_writer_that_cannot_read_the_file_changes_nothing_and_does_not_stop_a_start(self):
        """R-GW-27, R-SCH-17 — the history is worth less than the gateway. It is not worth
        so little that a file nobody can read is replaced with one entry."""
        target = recovery.interrupted_path("shared", self.logs)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"turn": {"at": "2026-07-25 09:00",,}}')
        recovery.note_interrupted("shared", self.logs, "new", "because")
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

        recovery.note_interrupted("shared", self.logs, "turn", "because")
        self.assertTrue(asked, "what has already happened was written without waiting for it")

        asked.clear()
        gateway.write_whole(self.where / "beat.json", "{}")
        self.assertEqual([], asked, "the beat pays for a durability it does not need")


class TakingAGatewayAway(WithARunDirectory):
    """What rundesk keeps for a gateway, once there is no gateway to keep it for."""

    def kept_for(self, name: str) -> dict:
        """Everything rundesk would have written for a gateway of this name."""
        made = {
            "record": self.where / f"{name}.json",
            "lock": self.where / f"{name}.lock",
            "log": self.logs / f"{name}.log",
            "interrupted": self.logs / f"{name}.interrupted.json",
        }
        for path in made.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}")
        return made

    def test_forgetting_a_gateway_keeps_what_it_wrote(self):
        """R-GW-31, R-GW-18 — an owner tidying a name out of their machine's background
        items has not asked to lose the account of what it did.

        What it was scheduled to do is not here to keep or take: that is a row its agent
        keeps, and removing the agent is what takes it (R-AGW-4)."""
        made = self.kept_for("test2")
        gateway.forget("test2", self.where, self.logs)
        for still in ("log", "interrupted"):
            self.assertTrue(made[still].exists(), f"removing a gateway took its {still}")
        self.assertFalse(made["record"].exists(), "it left behind what the gateway was doing")
        self.assertFalse(made["lock"].exists(), "it left the name looking as though it exists")

    def test_forgetting_a_gateway_with_its_history_takes_all_of_it(self):
        """R-GW-31 — the other half, so "keeps it" cannot pass by never removing anything."""
        made = self.kept_for("test2")
        gateway.forget("test2", self.where, self.logs, history=True)
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

        gateway.forget("busy", self.where, self.logs)

        self.assertTrue(made["lock"].exists(), "it took a name another process was holding")

    def test_holding_a_never_started_name_excludes_its_first_gateway_claim(self):
        """R-GW-29 — absence of yesterday's lock cannot open a race into a mutation."""
        lock = self.where / "first.lock"

        with gateway.holding("first", self.where) as held:
            self.assertTrue(held)
            contender = os.open(lock, os.O_RDWR)
            self.addCleanup(os.close, contender)
            with self.assertRaises(OSError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_forgetting_a_gateway_that_was_never_there_takes_nothing_and_says_so(self):
        """R-GW-31 — asked twice, or for a name that never existed, is not an error."""
        self.assertEqual([], gateway.forget("never-was", self.where, self.logs))

    def test_forgetting_a_gateway_leaves_every_other_gateway_alone(self):
        """R-GW-31 — one name's removal is one name's."""
        mine, theirs = self.kept_for("mine"), self.kept_for("theirs")
        gateway.forget("mine", self.where, self.logs, history=True)
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

    #: Records that are there and hold nothing anything can read. Not a missing file and not
    #: an empty one: this is what a stalled volume or a truncated write leaves behind, and it
    #: still holds everything the owner ever wrote.
    def garbled_for(self, records) -> Path:
        target = Path(records.at)
        target.write_text("this is not a database, and every schedule is still in here")
        return target

    def test_records_that_cannot_be_read_are_never_read_as_no_schedules(self):
        """R-SCH-17 — the one that mattered most replaced what it could not parse with an
        empty list and reported success, so a stray byte took every schedule the owner had
        ever written and said nothing. Refused instead, in rundesk's own words."""
        gw = self.made()
        target = self.garbled_for(self.records)
        before = target.read_text()
        with self.assertRaises(gateway.Unreadable):
            gw._schedules()
        self.assertEqual(before, target.read_text(), "reading them changed them")

    def test_records_that_are_not_there_are_told_from_records_that_cannot_be_read(self):
        """R-SCH-17 — absent and unreadable are distinguishable at the point of decision,
        which is the whole of the fix: one is an agent that has never been given a schedule,
        and the other is one whose schedules are all still there."""
        never = self.made("never-had-one")
        self.assertEqual([], never._schedules())
        self.garbled_for(self.records)
        with self.assertRaises(gateway.Unreadable):
            never._schedules()

    def test_a_change_that_did_change_something_is_written(self):
        """R-SCH-19 — the other half of "a change that changed nothing changes nothing", so
        it cannot pass by never writing at all."""
        gw = self.made()
        self.schedules_for(gw.name, {"name": "new", "when": "* * * * *", "run": ["/bin/echo"]})
        self.assertEqual(["new"], [row["name"] for row in gw._schedules()])
        self.records.enable_schedule("new", False)
        self.assertIs(False, gw._schedules()[0]["enabled"])

    def test_a_gateway_whose_schedules_cannot_be_read_still_starts_and_says_so(self):
        """R-SCH-17, R-SCH-18 — a command refuses, because it was asked to change them. A
        gateway that refused to start over it would take everything else it does down with
        the one thing that is broken."""
        self.garbled_for(self.records)
        gw = self.made()
        gw.claim()
        self.assertTrue(gateway.standing("gateway", self.where).running)
        self.assertIn("could not be read", gateway.log_path("gateway", self.logs).read_text())

    async def test_no_schedule_runs_while_the_schedules_cannot_be_read(self):
        """R-SCH-18 — and it is said once, not on every tick for as long as it is broken."""
        gw = self.made()
        gw.claim()
        self.garbled_for(self.records)
        gw._fire(schedule, datetime(2026, 7, 25, 9, 0))
        gw._fire(schedule, datetime(2026, 7, 25, 9, 1))
        await asyncio.sleep(0.2)
        self.assertEqual({}, gw.running, "it ran something out of records it could not read")
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
        swept = gateway._sweep_strays(self.where, "mine", self.made("mine").log, self.logs)
        self.assertEqual([], swept, "it claimed to have swept a record it could not read")
        self.assertTrue(record.exists(), "it deleted the only record naming abandoned work")

    #: A record that is there and holds nothing anything can parse — a truncated write, or a
    #: volume that stalled mid-flush. Not a missing record, which is a gateway that has
    #: simply not written one yet.
    def garbled_record_for(self, name: str = "gateway") -> Path:
        target = self.where / f"{name}.json"
        target.write_text('{"working": {"a-turn": {"pgid": 4242,,}}}')
        return target

    def test_a_record_that_cannot_be_read_is_not_reported_as_a_gateway_doing_nothing(self):
        """R-UPD-23 — five callers decide on this answer: a queued restart and an
        interactive one stop the gateway, an update replaces this install, and a restore
        swaps the owner's whole data tree. `read_json` cannot tell a record nobody wrote
        from one nobody could read, so an unreadable one answered "idle" and every one of
        those went ahead while work was genuinely in flight."""
        self.garbled_record_for()
        doing = gateway.what_is_working("gateway", self.where)
        self.assertNotEqual({}, doing, "an unreadable record was reported as an idle gateway")
        self.assertTrue(gateway.could_not_be_read(doing),
                        "it answered something, but not that it could not tell")

    def test_a_record_that_cannot_be_read_is_not_reported_as_nothing_running(self):
        """The same answer through the other reader, because `_in_flight` reaches both."""
        self.garbled_record_for()
        self.assertTrue(
            gateway.could_not_be_read(gateway.what_is_running("gateway", self.where)))

    def test_a_gateway_that_has_written_no_record_is_still_a_gateway_doing_nothing(self):
        """The other half, and the one that keeps the fix from swallowing the product: a
        record nobody has written yet is an idle gateway, not an unreadable one. Answering
        "I could not tell" here would refuse every update on a machine that is perfectly
        healthy — the same outage as the defect, arrived at from the other side."""
        self.assertEqual({}, gateway.what_is_working("never-wrote-one", self.where))
        self.assertFalse(gateway.could_not_be_read(
            gateway.what_is_running("never-wrote-one", self.where)))


class WhatAGatewaySaysAndWhereItLands(WithARunDirectory):
    """R-GW-35, R-GW-36 — one bounded account of a gateway, and all of it readable.

    Every line went to a rotated file *and* to stderr, which under the machine that keeps
    a gateway up is a file nothing rotates, nothing reads and no requirement mentions. So
    the log that exists to be bounded had an unbounded shadow — while the one thing that
    file is genuinely good for, a crash that never reached the logger at all, was
    unreachable through the command that a failed start tells the owner to run.
    """

    def test_what_a_gateway_writes_is_bounded_wherever_it_lands(self):
        """R-GW-35 — a gateway the machine is running writes its account once. `isatty`
        is what tells a person watching from a file collecting, and a captured stream is
        never a terminal."""
        gone = io.StringIO()          # a captured stream, which is what launchd hands it
        with contextlib.redirect_stderr(gone):
            log = gateway.recorder("gateway", self.logs)
            log.info("something happened")
        self.assertEqual("", gone.getvalue(),
                         "every line was copied into a second store nothing bounds")
        self.assertIn("something happened", (self.logs / "gateway.log").read_text(),
                      "it stopped saying it out loud and stopped writing it down too")

    def test_a_gateway_a_person_is_watching_still_shows_its_working(self):
        """R-GW-35 — bounding the copy must not silence `rundesk serve` in a terminal,
        which is the one place the second handler was ever for."""

        class Watched(io.StringIO):
            def isatty(self):
                return True

        watching = Watched()
        with contextlib.redirect_stderr(watching):
            gateway.recorder("gateway", self.logs).info("up")
        self.assertIn("up", watching.getvalue(),
                      "a gateway run by hand went quiet")

    def test_routine_channel_activity_is_logged_below_warning_severity(self):
        """R-GW-44 — a successful delivery is useful diagnostic context, not a reason
        for an owner to inspect the gateway."""

        class Log:
            def __init__(self):
                self.info_lines = []
                self.warning_lines = []

            def info(self, template, *values):
                self.info_lines.append(template % values)

            def warning(self, template, *values):
                self.warning_lines.append(template % values)

        log = Log()
        gateway.channel_note(log, "discord-dms", "INFO\twrote 262 chars and 0 files")
        self.assertEqual(
            ["channel 'discord-dms': wrote 262 chars and 0 files"],
            log.info_lines,
        )
        self.assertEqual([], log.warning_lines)

    def test_unclassified_channel_diagnostics_remain_warnings(self):
        """An older or third-party adapter has not classified its stderr. Preserve the
        attention-safe behavior instead of silently demoting a real failure."""

        class Log:
            def __init__(self):
                self.info_lines = []
                self.warning_lines = []

            def info(self, template, *values):
                self.info_lines.append(template % values)

            def warning(self, template, *values):
                self.warning_lines.append(template % values)

        log = Log()
        gateway.channel_note(log, "custom", "could not write")
        gateway.channel_note(log, "custom", "WARNING\tconnection refused")
        self.assertEqual([], log.info_lines)
        self.assertEqual(
            ["channel 'custom': could not write",
             "channel 'custom': connection refused"],
            log.warning_lines,
        )

    def test_a_stream_that_cannot_say_whether_it_is_a_terminal_is_not_one(self):
        """R-GW-35 — anything may be standing in for stderr, including something that
        raises when asked. The unbounded copy is the thing being prevented, so the answer
        it cannot give must be the one that does not make one."""

        class Refuses(io.StringIO):
            def isatty(self):
                raise ValueError("I/O operation on closed file")

        with contextlib.redirect_stderr(Refuses()):
            log = gateway.recorder("gateway", self.logs)
        self.assertEqual(1, len(log.handlers),
                         "a stream that would not answer was treated as a terminal")

    def test_a_gateways_whole_account_is_readable_however_it_was_rotated(self):
        """R-GW-36 — the line explaining the tail is as often in the rotation behind it,
        and reading only the last file is how the answer sat one filename away."""
        (self.logs / "gateway.log.2").write_text("oldest\n")
        (self.logs / "gateway.log.1").write_text("older\n")
        (self.logs / "gateway.log").write_text("newest\n")
        found = gateway.log_sources("gateway", self.logs, gateway.GATEWAY_LOG)
        self.assertEqual(["gateway.log.2", "gateway.log.1", "gateway.log"],
                         [path.name for _whose, path in found],
                         "one account cut up by rotation was not put back in order")

    def test_what_never_reached_the_logger_is_readable_too(self):
        """R-GW-36 — a traceback, a task nobody awaited, a refusal printed before there
        was a logger. None of it is in the gateway's own log, and it is the whole of the
        answer to why a gateway would not start."""
        (self.logs / "gateway.err").write_text("Traceback (most recent call last):\n")
        found = gateway.log_sources("gateway", self.logs)
        self.assertIn((gateway.MACHINE_LOG, self.logs / "gateway.err"), found,
                      "what the machine captured was unreachable")
        self.assertEqual([], gateway.log_sources("gateway", self.logs, gateway.GATEWAY_LOG),
                         "asking for one source answered with the other")

    def test_a_change_that_could_not_be_written_down_says_so(self):
        """R-GW-37 — it swallowed the error, so the first schedule added in a clean home
        printed ADDED, kept the change, and left no audit line anywhere."""
        nowhere = self.logs / "taken" / "gateway.log"
        nowhere.parent.write_text("this is a file, so nothing can be made inside it")
        self.assertIsNotNone(gateway.note("gateway", "a change", nowhere.parent),
                             "a log line that could not be written reported nothing")

    def test_the_first_line_written_in_a_clean_home_makes_somewhere_to_put_it(self):
        """R-GW-37 — the ordinary case, and the one that failed: nothing had written to
        this agent's logs before, so there was no directory yet."""
        fresh = self.logs / "never-written-in"
        self.assertIsNone(gateway.note("gateway", "a change", fresh),
                          "the first line in a clean home was refused")
        self.assertIn("a change", (fresh / "gateway.log").read_text())


class FindingAGatewayByWhatItLeftBehind(WithARunDirectory):
    """R-GW-38, R-GW-39, R-GW-40 — the store saying what never finished, made answerable.

    It had no reader anywhere in the product: "what did not finish" meant reading JSON
    out of a directory by hand, during an incident, having already guessed the name.
    """

    def test_a_gateway_that_survives_only_in_what_it_left_is_still_found(self):
        """R-GW-38 — its record was cleared when it stopped and its agent was taken away,
        so the one place it exists is the account of what it never finished. That is the name
        an owner wants after a crash, and every listing left it out.

        What it was *scheduled* to do no longer survives losing its agent: schedules are rows
        an agent keeps, so an agent that is gone takes them with it."""
        (self.logs / "vanished.interrupted.json").write_text('{"turn": {"ended": false}}')
        (self.logs / "also-here.interrupted.json").write_text("{}")
        self.assertEqual(["also-here", "vanished"], recovery.remembered(self.logs),
                         "a gateway with nothing left but its history was invisible")

    def test_a_name_nothing_of_ours_wrote_is_passed_over(self):
        """R-GW-38 — the directory may be overridden onto somewhere shared, and a name
        that could never be a gateway's is somebody else's file rather than a gateway."""
        (self.logs / "not a gateway name.json").write_text("{}")
        self.assertEqual([], recovery.remembered(self.logs),
                         "it read somebody else's file as a gateway")

    async def test_work_that_is_running_again_is_no_longer_unfinished(self):
        """R-GW-40 — entries were keyed by work and never cleared, so work interrupted
        once in March was still listed in July beside work interrupted a minute ago."""
        recovery.note_interrupted("gateway", self.logs, "schedule:nightly",
                                  "the gateway it was running under is gone", ended=True)
        gw = self.made()
        gw.claim()
        await gw.start([PY, "-c", "pass"], as_name="schedule:nightly")
        self.assertEqual({}, recovery.what_was_interrupted("gateway", self.logs),
                         "work that is running again was still reported as unfinished")

    async def test_other_work_that_never_finished_is_left_standing(self):
        """R-GW-40 — resolving one entry must not tidy away the rest, which is the whole
        of what anybody is asking this store."""
        for work in ("schedule:nightly", "schedule:weekly"):
            recovery.note_interrupted("gateway", self.logs, work, "gone", ended=True)
        gw = self.made()
        gw.claim()
        await gw.start([PY, "-c", "pass"], as_name="schedule:nightly")
        self.assertEqual(["schedule:weekly"],
                         sorted(recovery.what_was_interrupted("gateway", self.logs)),
                         "resolving one entry took another with it")


class ASchedulesOutcomeAfterACrash(WithARunDirectory):
    """R-SCH-23 — a firing is written down before the run begins, and nothing rewrote it.

    Two durable stores then described one event and disagreed: the outcome said `started`,
    indistinguishable from running right now, while the interruption beside it said the
    same work had ended.
    """

    def _died_mid_run(self, name="gateway", schedule_name="nightly", work=None):
        """A schedule left saying it started, and a record naming the work as in flight —
        which is exactly what a gateway that died between the two leaves behind."""
        self.schedules_for(name, {"name": schedule_name, "when": "0 3 * * *",
                                  "run": ["/bin/true"]})
        self.records.schedule_fired(schedule_name, "2026-07-25 03:00", gateway.STARTED)
        (self.where / f"{name}.json").write_text(json.dumps(
            {"name": name, "pid": 1,
             "working": {work or f"schedule:{schedule_name}": {"pgid": 999999, "since": "then"}}}))

    def test_a_schedule_left_saying_started_by_a_gone_gateway_is_reconciled(self):
        """R-SCH-23 — the first question asked after a crash, answered wrongly, while the
        right answer was already on disk one file away."""
        self._died_mid_run()
        self.made().claim()
        did = self.what_each_schedule_last_did()["nightly"]
        self.assertEqual(gateway.INTERRUPTED, did["last_outcome"],
                         "dead work was still presented as in flight")

    def test_reconciling_does_not_move_the_minute_it_fell_due(self):
        """R-SCH-23 — R-SCH-9 rests on that minute. Putting the moment of reconciling
        there reads as a later firing, and everything due in between is passed over."""
        self._died_mid_run()
        self.made().claim()
        self.assertEqual("2026-07-25 03:00",
                         self.what_each_schedule_last_did()["nightly"]["last_auto_run_at"],
                         "the minute a schedule fell due was moved")

    def test_work_the_sweep_found_still_running_is_left_alone(self):
        """R-SCH-23 — it is genuinely in flight, and calling it interrupted is the same
        lie the other way up. What the sweep handed over is what says so.

        The reconciliation is asked directly rather than through a real process group:
        naming one in a test is how this suite once killed its own runner, and what is
        being proved here is the decision, not the signalling that feeds it.
        """
        self._died_mid_run()
        gw = self.made()
        gw._inherited = {"schedule:nightly": {"pgid": 4242, "since": "then"}}
        gw._reconcile_what_never_finished()
        self.assertEqual(gateway.STARTED,
                         self.what_each_schedule_last_did()["nightly"]["last_outcome"],
                         "work that is genuinely running was written off as interrupted")

    def test_a_schedule_refused_by_a_shutdown_leaves_no_stale_start(self):
        """R-SCH-23 — the form no reconciliation on the way back up can reach: the firing
        is written, then shutdown refuses the wrapper, so no process ever exists for a
        sweep to find and reckon with."""

        self.schedules_for("gateway", {"name": "nightly", "when": "0 3 * * *",
                                       "run": ["/bin/true"]})
        self.records.schedule_fired("nightly", "2026-07-25 03:00", gateway.STARTED)

        async def refused():
            gw = self.made()
            gw.claim()
            gw._stopping = True
            one = schedule.Schedule("nightly", "0 3 * * *", ["/bin/true"])
            await gw._run_scheduled(one, datetime(2026, 7, 25, 3, 0))

        asyncio.run(refused())
        self.assertEqual(gateway.INTERRUPTED,
                         self.what_each_schedule_last_did()["nightly"]["last_outcome"],
                         "a schedule that never started was left saying it had")


#: A brain, as a program: answers, says what it cost, and says where the conversation got
#: to. The same shape `tests/test_turn.py` uses, and for the same reason — a stand-in more
#: generous than a real adapter hides whole features, so this is exactly the seam's surface.
A_BRAIN = r"""#!%s
import json, os, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"tools": True, "resume": True, "model": True, "usage": True}))
    sys.exit(0)
prompt = sys.stdin.read().strip()
say = lambda **it: (sys.stdout.write(json.dumps(it) + "\n"), sys.stdout.flush())
say(type="text", text="heard " + prompt)
say(type="usage", input=100, output=8, cached=40, session=148, model="stand-in-1")
say(type="done", ok=True, session=(os.environ.get("RUNDESK_RESUME") or "") + "s")
""" % PY

#: A brain that fails, so a schedule whose provider goes wrong leaves one durable outcome
#: rather than silence.
A_FAILING_BRAIN = r"""#!%s
import json, sys
if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)
sys.stdin.read()
sys.stdout.write(json.dumps({"type": "done", "ok": False, "why": "it would not answer"}) + "\n")
""" % PY


class ASurface:
    """A surface that is up, as far as the gateway is concerned.

    Exactly the one method the gateway calls on a live `Answering` and nothing else: what a
    remark looks like once it crosses the seam is `tests/test_answering.py`'s, and a stand-in
    here that knew more would let a case pass against a message nobody could read.
    """

    #: Where a notice goes, which a real surface resolves once and hands back so the report
    #: is delivered to the same conversation rather than to whichever is newest by then
    #: (R-SCH-46).
    NOTICE_WENT_TO = "the-room-the-notice-went-to"

    def __init__(self, refuses: bool = False, nowhere: bool = False):
        self.told: list = []
        #: The complete result handed to the surface, retained separately from the compact
        #: outcome assertions older schedule cases make (R-SCH-50).
        self.results: list = []
        self.started: list = []
        #: What each report was told to be delivered to, in order.
        self.delivered_to: list = []
        self.refuses = refuses
        #: A surface with nowhere to deliver, which is what `told_a_schedule_started` hands
        #: back when nothing has ever been said on it and no place was named (R-SCH-46).
        self.nowhere = nowhere

    async def told_what_a_schedule_did(self, named: str, result, where=None) -> None:
        if self.refuses:
            raise OSError("the platform would not take it")
        self.results.append(result)
        self.told.append((named, getattr(result, "became", result)))
        self.delivered_to.append(where)

    async def told_a_schedule_started(self, named: str):
        if self.refuses:
            raise OSError("the platform would not take it")
        if self.nowhere:
            return False, None
        self.started.append(named)
        return True, self.NOTICE_WENT_TO


class WhenTheClockAsksATurn(WithARunDirectory):
    """R-SCH-28 — a schedule that asks a turn rather than starting a program.

    The end of the chain this phase exists to prove: the clock fires, a gateway admits a turn,
    a brain answers, and the account records it. Offline throughout — the brain is a program
    this case writes, which is what any real adapter is.
    """

    def setUp(self):
        super().setUp()
        from rundesk import agent as agents
        self.agents_at = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.agents_at, True)
        self.addCleanup(os.environ.pop, "RUNDESK_AGENTS_DIR", None)
        os.environ["RUNDESK_AGENTS_DIR"] = str(self.agents_at)
        self.data_at = Path(tempfile.mkdtemp(prefix="rundesk-data-"))
        self.addCleanup(shutil.rmtree, self.data_at, True)
        self.addCleanup(os.environ.pop, "RUNDESK_DATA_DIR", None)
        os.environ["RUNDESK_DATA_DIR"] = str(self.data_at)
        config.ensure(self.data_at)
        self.agents = agents
        agents.add("ava", self.agents_at)
        self.records = agents.records("ava", self.agents_at)
        self.brains = Path(tempfile.mkdtemp(prefix="rundesk-brains-"))
        self.addCleanup(shutil.rmtree, self.brains, True)

    def brain(self, said: str = A_BRAIN, called: str = "stand-in") -> str:
        at = self.brains / called
        at.write_text(said, encoding="utf-8")
        at.chmod(at.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(at)

    def reachable_on(self, called: str = "ops") -> None:
        """A surface this agent is reachable on. Written down because a schedule referencing a
        channel that is not there is refused by the records themselves — which is what stops a
        schedule outliving the channel it reported to."""
        self.records.remember_channel(called, "somewhere", ["2207"], store.stamped())

    def asks(self, name="nightly", prompt="what changed?", **held) -> None:
        """A schedule that asks a turn, written the way the command writes one."""
        self.records.remember_schedule(name, held.pop("when", "* * * * *"), store.stamped(),
                                       prompt=prompt, **held)

    def made(self, name: str = "ava", **held) -> gateway.Gateway:
        held.setdefault("asking", self.agents.asking("ava", self.agents_at))
        gw = gateway.Gateway(name, where=self.where, logs=self.logs, root=self.root,
                             records=self.records, agents=self.agents_at, **held)
        self.addCleanup(gw.release)
        return gw

    async def _fired(self, gw, moment=None, seconds: float = 30.0) -> dict:
        """Fire the clock and wait for the run the turn wrote. Returns the run's row.

        The read is retried rather than trusted, and not for the usual reason. Reading these
        records can fail outright while another process is writing them — a WAL database whose
        `-shm` is not there cannot be opened read-only at all, and that is the state a clean
        close leaves behind. It is a real fault and it is recorded as one; a polling helper is
        not the place to prove it, so this waits it out.
        """
        gw._fire(schedule, moment or datetime.now())
        deadline = time.time() + seconds
        last = None
        while time.time() < deadline:
            try:
                runs = self.records.runs()
                if runs and runs[0].get("ended_at"):
                    return runs[0]
            except Exception as why:  # noqa: BLE001 — see the docstring
                last = why
            await asyncio.sleep(0.05)
        self.fail(f"no run was recorded (last read said {last!r})")

    async def test_a_schedule_that_asks_a_turn_completes_and_records_it(self):
        """R-SCH-28 — the whole line in one case: the time came, a brain answered, and what
        it said is readable afterwards by somebody who was not there."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks()
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        self.assertEqual("finished", run["outcome"], f"the turn did not finish: {run}")
        said = [one for one in self.records.messages(run["conversation_id"])
                if one["author"] == "agent"]
        self.assertEqual(["heard what changed?"], [one["text"] for one in said],
                         "what the brain answered is not readable afterwards")

    async def test_an_update_migration_runs_once_as_a_backend_scheduled_turn(self):
        """A release request is durable until the restarted gateway sees and completes it,
        and it is never posted to a channel. It uses a fresh scheduled
        conversation and remains expired after completion instead of running again."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        # The internal conversation and accounting must remain separate even when an owner
        # used the same display name for an ordinary schedule.
        self.records.remember_schedule(
            "migration-91", None, store.stamped(), at="2099-01-01 00:00",
            prompt="owner work",
        )
        with sqlite3.connect(str(self.records.at), isolation_level=None) as conn:
            conn.execute(
                "INSERT INTO update_turn (migration, prompt, instructions, bootstrap)"
                " VALUES (91, ?, ?, ?)",
                ("tighten this agent home", "this is an unattended update migration",
                 "# replaced bootstrap\n"),
            )
        gw = self.made()
        gw.claim()

        run = await self._fired(gw)
        gw._fire(schedule, datetime.now())
        await asyncio.sleep(0.1)

        self.assertEqual(("schedule", None), (run["source"], run["schedule_id"]))
        conversation = next(one for one in self.records.conversations()
                            if one["id"] == run["conversation_id"])
        self.assertEqual(("update", "migration-91"),
                         (conversation["channel"], conversation["space"]))
        owner = self.records.schedule("migration-91")
        self.assertIsNone(owner["last_outcome"])
        self.assertIsNone(owner["last_auto_run_at"])
        self.assertEqual(1, len(self.records.runs()), "the expired migration ran again")
        self.assertEqual([], self.records.pending_update_turns())
        with sqlite3.connect(str(self.records.at)) as conn:
            completed = conn.execute(
                "SELECT completed_at FROM update_turn WHERE migration = 91"
            ).fetchone()[0]
        self.assertIsNotNone(completed)
        self.assertEqual(
            "# replaced bootstrap\n",
            (self.agents.home("ava", self.agents_at) / "CLAUDE.md").read_text(),
        )

    async def test_a_returned_update_is_settled_without_replaying_after_a_write_failure(self):
        """The run is the durable proof across the narrow return/expire boundary. A failed
        completion write is retried from that proof, never by running the migration again."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        with sqlite3.connect(str(self.records.at), isolation_level=None) as conn:
            conn.execute(
                "INSERT INTO update_turn (migration, prompt, instructions, bootstrap)"
                " VALUES (96, 'migrate', 'backend only', '# bootstrap\\n')"
            )
        gw = self.made()
        gw.claim()

        with mock.patch.object(
                self.records, "complete_update_turn", side_effect=OSError("briefly locked")):
            await self._fired(gw)
            deadline = time.time() + 2
            while gw._update_turn_tasks and time.time() < deadline:
                await asyncio.sleep(0.01)

        self.assertEqual([96], [
            one["migration"] for one in self.records.pending_update_turns()
        ])
        gw._fire(schedule, datetime.now())
        await asyncio.sleep(0.1)

        self.assertEqual([], self.records.pending_update_turns())
        self.assertEqual(1, len(self.records.runs()), "the returned migration was replayed")

    async def test_a_stopped_update_run_is_not_mistaken_for_a_returned_migration(self):
        """Cancellation settles the run account as stopped, but not the migration request.
        A successor must still be allowed to finish the agent-home work."""
        conversation = "migration-98"
        identifier = store.conversation_id("update", conversation)
        self.records.opened(
            identifier, "update", "schedule", conversation, store.stamped())
        run = self.records.began(
            "schedule", "stand-in", "default", store.stamped(),
            conversation_id=identifier,
        )
        self.records.ended(run, store.stamped(), "stopped")

        self.assertFalse(self.records.update_turn_returned(conversation))

    async def test_pending_update_migrations_run_oldest_first(self):
        """Two release prompts may accumulate while an agent is unrunnable. They must never
        rewrite one home concurrently, and the later request must run after the first."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        with sqlite3.connect(str(self.records.at), isolation_level=None) as conn:
            for version in (94, 95):
                conn.execute(
                    "INSERT INTO update_turn (migration, prompt, instructions, bootstrap)"
                    " VALUES (?, 'migrate', 'backend only', '# bootstrap\\n')",
                    (version,),
                )
        gw = self.made()
        gw.claim()
        gw._fire(schedule, datetime.now())
        deadline = time.time() + 3
        while time.time() < deadline:
            if not gw._update_turn_tasks and [
                    one["migration"] for one in self.records.pending_update_turns()] == [95]:
                break
            await asyncio.sleep(0.01)

        self.assertEqual(1, len(self.records.runs()))
        self.assertEqual([95], [
            one["migration"] for one in self.records.pending_update_turns()
        ])
        gw._fire(schedule, datetime.now())
        deadline = time.time() + 3
        while time.time() < deadline:
            if not gw._update_turn_tasks and not self.records.pending_update_turns():
                break
            await asyncio.sleep(0.01)

        self.assertEqual([], self.records.pending_update_turns())
        runs = list(reversed(self.records.runs()))
        conversations = {
            one["id"]: one for one in self.records.conversations(channel="update")
        }
        self.assertEqual(
            ["migration-94", "migration-95"],
            [conversations[one["conversation_id"]]["space"] for one in runs],
        )

    async def test_bootstrap_replacement_failure_is_atomic_and_retried(self):
        """A failed script-owned replacement leaves the old bootstrap intact and the
        request pending; a later tick can perform the replacement and run exactly once."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        bootstrap = self.agents.home("ava", self.agents_at) / "CLAUDE.md"
        before = bootstrap.read_bytes()
        with sqlite3.connect(str(self.records.at), isolation_level=None) as conn:
            conn.execute(
                "INSERT INTO update_turn (migration, prompt, instructions, bootstrap)"
                " VALUES (99, 'migrate', 'backend only', ?)",
                ("# replacement\n",),
            )
        gw = self.made()
        gw.claim()

        with mock.patch.object(
                store.os, "replace", side_effect=OSError("replacement unavailable")):
            gw._fire(schedule, datetime.now())
            deadline = time.time() + 2
            while gw._update_turn_tasks and time.time() < deadline:
                await asyncio.sleep(0.01)

        self.assertEqual(before, bootstrap.read_bytes())
        self.assertFalse(
            bootstrap.with_name(".CLAUDE.md.update-99").exists(),
            "the failed atomic replacement left its temporary file behind",
        )
        self.assertEqual([99], [
            one["migration"] for one in self.records.pending_update_turns()
        ])
        self.assertEqual([], self.records.runs())

        await self._fired(gw)
        self.assertEqual(b"# replacement\n", bootstrap.read_bytes())
        self.assertEqual([], self.records.pending_update_turns())
        self.assertEqual(1, len(self.records.runs()))

    async def test_serve_cancels_and_awaits_a_backend_migration(self):
        """Production shutdown owns backend tasks rather than relying on loop teardown."""
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocked(_one):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with sqlite3.connect(str(self.records.at), isolation_level=None) as conn:
            conn.execute(
                "INSERT INTO update_turn (migration, prompt, instructions, bootstrap)"
                " VALUES (97, 'migrate', 'backend only', '# bootstrap\\n')"
            )
        gw = self.made(asking=blocked)
        serving = asyncio.ensure_future(gw.serve())
        while gw._stopped is None:
            await asyncio.sleep(0)
        gw._fire(schedule, datetime.now())
        await asyncio.wait_for(started.wait(), timeout=2)
        gw.ask_to_stop()

        await asyncio.wait_for(serving, timeout=5)
        self.assertTrue(cancelled.is_set())
        self.assertEqual({}, gw._update_turn_tasks)
        self.assertEqual([97], [
            one["migration"] for one in self.records.pending_update_turns()
        ])

    async def test_an_update_migration_that_cannot_start_remains_pending(self):
        """A claim is not completion. An agent with no configured brain may become runnable
        later, so the update request remains available rather than disappearing on the
        first gateway that could not start it."""
        with sqlite3.connect(str(self.records.at), isolation_level=None) as conn:
            conn.execute(
                "INSERT INTO update_turn (migration, prompt, instructions, bootstrap)"
                " VALUES (92, 'migrate', 'backend only', '# bootstrap\\n')"
            )
        gw = self.made()
        gw.claim()

        gw._fire(schedule, datetime.now())
        deadline = time.time() + 2
        while gw._update_turn_tasks and time.time() < deadline:
            await asyncio.sleep(0.01)

        self.assertEqual([92], [
            one["migration"] for one in self.records.pending_update_turns()
        ])
        self.assertEqual([], self.records.runs())

    async def test_an_interrupted_update_migration_runs_after_the_gateway_returns(self):
        """Shutdown may land after the backend task starts. Cancellation leaves the durable
        request pending, and a successor runs it once instead of losing it at the claim."""
        started = asyncio.Event()

        async def accounted(_name, prompt, provider, **held):
            """The turn seam with its real durable account, blocked after admission."""
            identifier = store.conversation_id(held["on"], held["conversation"])
            self.records.opened(
                identifier, held["on"], held["kind"], held["conversation"], store.stamped())
            asked = self.records.arrived(identifier, store.stamped(), prompt)
            run = self.records.began(
                held["source"], provider, "default", store.stamped(),
                conversation_id=identifier, schedule_id=held["schedule_id"],
                trigger_message_id=asked,
            )
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.records.interrupted(run, store.stamped(), "gateway stopped")

        self.agents.remember("ava", self.agents_at, provider="stand-in")
        with sqlite3.connect(str(self.records.at), isolation_level=None) as conn:
            conn.execute(
                "INSERT INTO update_turn (migration, prompt, instructions, bootstrap)"
                " VALUES (93, 'migrate', 'backend only', '# bootstrap\\n')"
            )
        first = self.made(asking=self.agents.asking(
            "ava", self.agents_at, carry=accounted))
        first.claim()
        first._fire(schedule, datetime.now())
        await asyncio.wait_for(started.wait(), timeout=2)
        runs = self.records.runs()
        self.assertTrue(runs and runs[0]["ended_at"] is None, "the real turn was not admitted")
        task = first._update_turn_tasks[93]
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
        interrupted = self.records.runs()[0]
        self.assertEqual("stopped", interrupted["outcome"])
        self.assertEqual([93], [
            one["migration"] for one in self.records.pending_update_turns()
        ])
        first.release()

        self.agents.remember("ava", self.agents_at, provider=self.brain())
        successor = self.made()
        successor.claim()
        successor._fire(schedule, datetime.now())
        deadline = time.time() + 3
        while time.time() < deadline:
            runs = self.records.runs()
            if len(runs) == 2 and runs[0]["ended_at"]:
                break
            await asyncio.sleep(0.01)
        run = self.records.runs()[0]

        self.assertEqual("finished", run["outcome"])
        self.assertEqual([], self.records.pending_update_turns())
        self.assertEqual(2, len(self.records.runs()))

    async def test_a_turn_the_clock_started_says_so_in_the_account(self):
        """R-RUN-16 — the column somebody reads at three in the morning to find out whether
        they asked for what happened. It said `terminal`, because nothing could tell it
        otherwise."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks()
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        self.assertEqual("schedule", run["source"])
        self.assertEqual(self.records.schedule("nightly")["id"], run["schedule_id"],
                         "the run does not name the schedule that started it")

    async def test_a_scheduled_turn_is_never_in_the_terminals_conversation(self):
        """R-SCH-29 — untouched, a run at three in the morning landed in the conversation its
        owner types into: it resumed that session and left its own prompt and answer in the
        middle of it. Its own place, named for the schedule."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks()
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        where_it_is = [one for one in self.records.conversations()
                       if one["id"] == run["conversation_id"]][0]
        self.assertEqual(("schedule", "nightly"), (where_it_is["channel"], where_it_is["space"]))
        self.assertNotEqual(store.conversation_id("terminal", "terminal"), run["conversation_id"])

    async def test_two_schedules_on_one_agent_are_two_conversations(self):
        """R-SCH-29 — one place each, so what one asked is never in the other's history."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks("nightly", "what changed?")
        self.asks("weekly", "what is worth knowing?")
        gw = self.made()
        gw.claim()
        await self._fired(gw)
        deadline = time.time() + 30
        while time.time() < deadline and len(self.records.runs()) < 2:
            await asyncio.sleep(0.05)
        places = {one["space"] for one in self.records.conversations()}
        self.assertEqual({"nightly", "weekly"}, places, "two schedules shared one conversation")

    async def test_each_firing_of_a_schedule_starts_fresh(self):
        """R-SCH-29 — a brain that binds its standing instructions when a conversation opens
        is told what its situation is once and never again, so every firing stands on its own.
        Proved by the handle: the stand-in appends to whatever it was resumed from, so a
        carried-on conversation would report `ss` on the second turn."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks()
        gw = self.made()
        gw.claim()
        await self._fired(gw, datetime(2026, 7, 26, 9, 0))
        await self._fired(gw, datetime(2026, 7, 26, 9, 1))
        deadline = time.time() + 30
        while time.time() < deadline and len(self.records.runs()) < 2:
            await asyncio.sleep(0.05)
        self.assertEqual([False, False], [bool(one["resumed"]) for one in self.records.runs()],
                         "a firing carried on from the one before it")

    async def test_a_turn_the_clock_started_is_told_nobody_is_watching(self):
        """R-SCH-30 — the first trigger with no person at the other end, and the whole reason
        the sentence exists. Read out of the account rather than out of the environment,
        because what the brain was told is exactly what the account has to show (R-RUN-9)."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks()
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        told = [one["text"] for one in self.records.messages(run["conversation_id"])
                if one["author"] == "rundesk"]
        self.assertEqual(1, len(told), f"what it was told is not in the account: {told}")
        self.assertIn("nightly", told[0])
        self.assertIn("Nothing will answer", told[0])

    async def test_what_a_schedule_was_told_to_say_is_added_to_rundesks_own(self):
        """R-SCH-30, R-AGT-16, R-AGT-17, R-AGT-34 — what the owner wrote is added to
        rundesk's own rather than replacing them: ours says what the agent is, how to find
        what it did and what the situation is, theirs says what to do about tonight, and an
        agent needs both."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks(instructions="Only look at the deploy log.")
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        told = [one["text"] for one in self.records.messages(run["conversation_id"])
                if one["author"] == "rundesk"]
        self.assertEqual(1, len(told))
        self.assertTrue(told[0].startswith(self.agents.standing("ava")))
        self.assertTrue(told[0].endswith("Only look at the deploy log."))

    async def test_a_schedule_told_what_to_do_is_still_told_nobody_is_watching(self):
        """R-AGT-34, R-SCH-30 — the regression this whole tier change exists for. Standing
        instructions as ordinary as one line about what to look at used to displace the only
        statement rundesk makes about a scheduled turn, and nothing anywhere said so."""
        self.agents.remember("ava", self.agents_at, provider=self.brain(),
                             instructions="You are ava, and you are always brief.")
        self.asks(instructions="Only look at the deploy log.")
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        told = [one["text"] for one in self.records.messages(run["conversation_id"])
                if one["author"] == "rundesk"][0]
        self.assertIn("nightly", told, "it never said which schedule started this")
        self.assertIn("Nothing will answer", told)
        self.assertIn("Write nothing until the work is finished", told)
        self.assertLess(told.index("Nothing will answer"),
                        told.index("Only look at the deploy log."),
                        "the owner's words came before rundesk's account of the situation")

    async def test_a_schedule_that_says_nothing_still_gets_what_the_agent_says(self):
        """R-AGT-16 — the tier in the middle, on the surface that has no other. Still
        reached now that rundesk's own line no longer waits for everyone else to be silent."""
        self.agents.remember("ava", self.agents_at, provider=self.brain(),
                             instructions="You are ava, and you are always brief.")
        self.asks()
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        told = [one["text"] for one in self.records.messages(run["conversation_id"])
                if one["author"] == "rundesk"]
        self.assertEqual(1, len(told))
        self.assertTrue(told[0].startswith(self.agents.standing("ava")))
        self.assertTrue(told[0].endswith("You are ava, and you are always brief."))

    async def test_a_schedule_names_the_brain_that_answers_it(self):
        """R-SCH-28 — two schedules on one agent, resolving different brains: which one
        answers is the schedule's where it says, and the agent's where it does not."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks("weekly", "what is worth knowing?", provider=self.brain(called="other"))
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        self.assertTrue(run["provider"].endswith("other"),
                        f"the schedule's own brain was passed over: {run['provider']}")

    async def test_what_a_schedule_came_to_is_said_on_the_surface_it_names(self):
        """R-SCH-31, R-SCH-50 — the gateway is the only thing that can say it: a channel
        is held open here, and it receives the complete turn result rather than losing the
        usage facts before the answer can be rendered."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made()
        gw._reached["ops"] = ASurface()
        gw.claim()
        await self._fired(gw)
        told = gw._reached["ops"].told
        self.assertEqual([("nightly", "finished")], told,
                         f"what the schedule came to never reached the surface: {told}")
        result = gw._reached["ops"].results[0]
        self.assertEqual((True, 8, 148), (result.tokens["reported"],
                                          result.tokens["output"],
                                          result.tokens["session"]))

    async def test_a_schedule_says_it_on_the_surface_it_names_and_no_other(self):
        """R-SCH-31 — it went to every surface the agent had, which is two notices about work
        that concerned one of them, and rundesk deciding for an owner where a night's work is
        discussed."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made()
        self.reachable_on("dms")
        gw._reached["ops"], gw._reached["dms"] = ASurface(), ASurface()
        gw.claim()
        await self._fired(gw)
        self.assertEqual([("nightly", "finished")], gw._reached["ops"].told)
        self.assertEqual([], gw._reached["dms"].told,
                         "a surface the schedule does not name was told anyway")

    async def test_a_schedule_naming_no_surface_still_runs_and_still_records(self):
        """R-SCH-31 — not silence: the account and `schedules` say it either way, and a
        schedule nobody asked to be told about in a chat is not a schedule that did nothing."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks()
        gw = self.made()
        gw._reached["ops"] = ASurface()
        gw.claim()
        run = await self._fired(gw)
        self.assertEqual("finished", run["outcome"])
        self.assertEqual("finished", self.records.schedule("nightly")["last_outcome"])
        self.assertEqual([], gw._reached["ops"].told,
                         "it said it somewhere the schedule never named")

    async def test_an_agent_with_no_channel_at_all_still_runs_and_still_records(self):
        """R-SCH-31 — the case that matters most: a channel decides nothing about schedules,
        so an agent that has none is an agent whose clock works exactly the same."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.asks(channel=None)
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        self.assertEqual("finished", run["outcome"])
        self.assertEqual("finished", self.records.schedule("nightly")["last_outcome"])

    async def test_a_surface_that_is_not_up_is_said_rather_than_passed_over(self):
        """R-SCH-31 — an owner who asked to be told and was not is owed the reason: a schedule
        reporting nowhere looks exactly like one that did not run."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made()
        gw.claim()
        await self._fired(gw)
        self.assertIn("that channel is not up", gateway.log_path("ava", self.logs).read_text())

    async def test_a_surface_that_will_not_take_it_changes_nothing_the_schedule_recorded(self):
        """R-SCH-31 — the work is over and its record is written before this is tried."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made()
        gw._reached["ops"] = ASurface(refuses=True)
        gw.claim()
        run = await self._fired(gw)
        self.assertEqual("finished", run["outcome"])
        self.assertEqual("finished", self.records.schedule("nightly")["last_outcome"],
                         "a surface refusing changed what the schedule recorded")
        self.assertIn("could not say what", gateway.log_path("ava", self.logs).read_text())

    async def _became(self, gw, named: str, seconds: float = 30.0) -> str:
        """Fire the clock and wait for this schedule to settle on a final outcome.

        `_fired` waits for a *run*, which a schedule that starts a program never writes and
        a firing that never reached a brain never writes either. What every one of them does
        write is the outcome on the schedule itself — and `started` is written before the
        work begins, so it is the one word that means this has not finished yet.

        Whatever is said on a surface is said after that write, so the settle below is not
        politeness: read straight off the outcome, a case about what reached the surface is
        reading it before anything could have.
        """
        gw._fire(schedule, datetime.now())
        deadline, became = time.time() + seconds, None
        while time.time() < deadline:
            with contextlib.suppress(Exception):
                became = (self.records.schedule(named) or {}).get("last_outcome")
                if became and became != "started":
                    break
            await asyncio.sleep(0.05)
        else:
            self.fail(f"schedule '{named}' never settled on an outcome (last said {became!r})")
        for _ in range(200):
            if not [one for one in asyncio.all_tasks() if one is not asyncio.current_task()]:
                break
            await asyncio.sleep(0.005)
        return became

    async def test_a_scheduled_run_says_it_started_before_it_says_what_it_found(self):
        """R-SCH-46 — an owner cannot otherwise tell a schedule is running: work starts at six,
        nothing is said for twenty minutes, and the report arrives beside answers to other
        questions with nothing tying the two together."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made()
        gw._reached["ops"] = ASurface()
        gw.claim()
        await self._fired(gw)
        self.assertEqual(["nightly"], gw._reached["ops"].started,
                         "nothing said the run had begun")
        self.assertEqual([("nightly", "finished")], gw._reached["ops"].told,
                         "what it found did not follow the notice that it had started")

    async def test_a_run_carries_where_its_notice_went_to_its_report(self):
        """R-SCH-46 — the gateway is what holds the two ends of a run together, so it is what
        carries where the notice went across to the report. Left for the report to work out
        again, the answer is whichever room somebody last spoke in — which a long run gives an
        owner every chance to change, leaving a promise standing in one room for ever and its
        outcome posted in another."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made()
        gw._reached["ops"] = ASurface()
        gw.claim()
        await self._fired(gw)
        self.assertEqual([ASurface.NOTICE_WENT_TO], gw._reached["ops"].delivered_to,
                         "the report was left to resolve where it goes all over again")
        self.assertEqual({}, gw._announced, "a notice already answered is still standing")

    async def test_a_report_for_a_run_nobody_announced_resolves_where_it_goes(self):
        """R-SCH-31, R-SCH-46 — a program schedule never announces, so there is nowhere carried
        to deliver to and the report goes where every report went before there were notices."""
        self.reachable_on("ops")
        self.records.remember_schedule("tidy", "* * * * *", store.stamped(),
                                       command=[PY, "-c", "pass"], channel="ops")
        gw = self.made()
        gw._reached["ops"] = ASurface()
        gw.claim()
        await self._became(gw, "tidy")
        self.assertEqual([None], gw._reached["ops"].delivered_to,
                         "a report nobody announced was pinned to a conversation anyway")

    async def test_a_schedule_that_starts_a_program_says_nothing_when_it_starts(self):
        """R-SCH-46 — a program has no report to anchor, so `Working on…` for one is a promise
        rundesk does not keep. What it *came to* is still said, exactly as it was (R-SCH-31)."""
        self.reachable_on("ops")
        self.records.remember_schedule("tidy", "* * * * *", store.stamped(),
                                       command=[PY, "-c", "pass"], channel="ops")
        gw = self.made()
        gw._reached["ops"] = ASurface()
        gw.claim()
        await self._became(gw, "tidy")
        self.assertEqual([], gw._reached["ops"].started,
                         "a program schedule promised a report it never delivers")
        self.assertEqual(["tidy"], [named for named, _became in gw._reached["ops"].told],
                         "a program schedule stopped saying what it came to")

    async def test_a_run_that_could_not_start_still_replies_to_its_notice(self):
        """R-SCH-46 — the notice must not be left standing with nothing under it. A brain that
        could not be reached is exactly the case an owner is waiting on, and a `Working on…`
        with no outcome beneath it reads as an agent that hung."""
        async def would_not(one):
            raise RuntimeError("the brain could not be reached")

        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made(asking=would_not)
        gw._reached["ops"] = ASurface()
        gw.claim()
        self.assertEqual("could not start", await self._became(gw, "nightly"))
        self.assertEqual(["nightly"], gw._reached["ops"].started)
        self.assertEqual([("nightly", "could not start")], gw._reached["ops"].told,
                         "the notice was left with no outcome under it")

    async def test_a_firing_refused_for_still_running_says_nothing_about_starting(self):
        """R-SCH-6, R-SCH-46 — announced before the overlap guard, this firing would have said
        work began that never did. And the notice standing on the surface belongs to the run
        still going, so answering it here would close off work that has not finished."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made()
        gw._reached["ops"] = ASurface()
        gw._asked_for.add(f"{gateway.SCHEDULED_AS}nightly")
        gw.claim()
        self.assertEqual("still running", await self._became(gw, "nightly"))
        self.assertEqual([], gw._reached["ops"].started, "it said a refused firing had begun")
        self.assertEqual([], gw._reached["ops"].told,
                         "it answered a notice belonging to the run still going")

    async def test_a_surface_with_nowhere_to_deliver_leaves_no_notice_to_answer(self):
        """R-SCH-46 — nowhere to say it is nowhere to say it started, and only what actually
        went out is owed a reply. A gateway that assumed the notice landed would post an
        outcome into a room that never saw the thing it is answering."""
        async def would_not(one):
            raise RuntimeError("the brain could not be reached")

        self.reachable_on("ops")
        self.asks(channel="ops")
        gw = self.made(asking=would_not)
        gw._reached["ops"] = ASurface(nowhere=True)
        gw.claim()
        await self._became(gw, "nightly")
        self.assertEqual([], gw._reached["ops"].told,
                         "it answered a notice that never went out")

    async def test_a_schedule_that_names_rundesk_ask_is_admitted_as_the_clocks_work(self):
        """R-RUN-16, R-SCH-27, R-SCH-29 — the other half of the phase, and the one a stand-in
        cannot prove: a schedule whose *program* is `rundesk ask` is still the clock's work, and
        the only thing that can tell it so is the one variable the gateway adds to its
        environment. Driven through the repository's own command, in a real subprocess, so a
        rename of that variable on either side fails here rather than silently reverting a
        scheduled turn to one somebody typed."""
        self.agents.remember("ava", self.agents_at, provider=self.brain())
        self.records.remember_schedule(
            "nightly", "* * * * *", store.stamped(),
            command=[str(ROOT / "rundesk"), "ask", "ava", "what changed?"])
        gw = self.made()
        gw.claim()
        run = await self._fired(gw)
        self.assertEqual("schedule", run["source"],
                         "a turn the clock started read back as one somebody typed")
        where_it_is = [one for one in self.records.conversations()
                       if one["id"] == run["conversation_id"]][0]
        self.assertEqual(("schedule", "nightly"),
                         (where_it_is["channel"], where_it_is["space"]),
                         "it landed somewhere other than the schedule's own conversation")

    async def test_a_gateway_going_while_a_turn_is_going_does_not_report_a_clean_stop(self):
        """R-GW-7 — a turn a schedule asked for is not a program this gateway started, so ending
        everything it *did* start reached none of it. Taking that for nothing left reported exit
        zero and "down" while a brain was still answering, and a supervisor reading zero has no
        way to know."""
        held = asyncio.Event()

        async def slowly(one):
            await held.wait()
            raise AssertionError("the turn was never let go")

        self.asks()
        gw = self.made(asking=slowly)
        gw.claim()
        gw._fire(schedule, datetime.now())
        for _ in range(200):
            if gw._asked_for:
                break
            await asyncio.sleep(0.02)
        self.assertEqual({"schedule:nightly"}, gw._asked_for, "no turn was in flight to test")

        drained = await gw._go()

        self.assertFalse(drained, "it reported a clean stop with a turn still going")
        said = gateway.log_path("ava", self.logs).read_text()
        self.assertIn("still out there", said)
        self.assertIn("with work still running", said)
        self.assertIn("schedule:nightly",
                      json.dumps(recovery.what_was_interrupted("ava", self.logs)),
                      "nothing durable named the turn that never finished")
        held.set()

    async def test_a_schedule_whose_brain_fails_leaves_one_durable_outcome(self):
        """R-SCH-8 — a schedule that fails in silence looks exactly like one that has never
        come due, and fails again every time it falls due."""
        self.agents.remember("ava", self.agents_at, provider=self.brain(A_FAILING_BRAIN, "sulky"))
        self.asks()
        gw = self.made()
        gw.claim()
        await self._fired(gw)
        self.assertEqual("failed", self.records.schedule("nightly")["last_outcome"])

    async def test_a_schedule_that_asks_a_turn_with_no_brain_anywhere_says_so(self):
        """R-SCH-8 — refused as an outcome rather than passed over. A minute that did nothing
        for a reason nobody wrote down is a schedule an owner cannot fix."""
        self.asks()
        gw = self.made()
        gw.claim()
        gw._fire(schedule, datetime.now())
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.records.schedule("nightly")["last_outcome"] not in (None, gateway.STARTED):
                break
            await asyncio.sleep(0.05)
        self.assertEqual("could not start", self.records.schedule("nightly")["last_outcome"])
        self.assertIn("names no brain", gateway.log_path("ava", self.logs).read_text())

    async def test_a_gateway_with_nothing_to_ask_a_turn_with_says_so(self):
        """R-SCH-8 — a gateway that is not an agent can start programs and not turns, and a
        schedule that asks one has to say why it did not run rather than doing nothing."""
        self.asks()
        gw = gateway.Gateway("ava", where=self.where, logs=self.logs, root=self.root,
                             records=self.records, agents=self.agents_at)
        self.addCleanup(gw.release)
        gw.claim()
        gw._fire(schedule, datetime.now())
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.records.schedule("nightly")["last_outcome"] not in (None, gateway.STARTED):
                break
            await asyncio.sleep(0.05)
        self.assertEqual("could not start", self.records.schedule("nightly")["last_outcome"])
        self.assertIn("nothing to ask one with", gateway.log_path("ava", self.logs).read_text())


class ARunTheGatewayNeverSettled(WithARunDirectory):
    """R-GW-23 — a run is marked running the moment it is admitted, and nothing rewrote
    that if the gateway holding it died, was stopped, or was replaced by an update.

    Reported (#105): one agent's `rundesk runs` still showed a turn in flight more than
    twenty-six hours after its transcript stopped being written, across three releases.
    The record is what answers "what is in flight" and "what did this cost"; a stranded
    row makes both untrue and its cost stays unreported for ever.
    """

    def _left_running(self, provider="codex"):
        """A run admitted and never ended — what a gateway that went mid-turn leaves."""
        return self.records.began("channel", provider, "read", "2026-07-27T18:31:18Z")

    def _row(self, run):
        return next(one for one in self.records.runs(limit=200) if one["id"] == run)

    def _turning(self, run, pid=None):
        """The activity record a live turn publishes for itself."""
        activity.began(self.where, {
            "run": run, "source": "channel", "surface": "discord",
            "conversation": "one", "pid": pid or os.getpid(), "since": 1,
        })

    def test_a_run_left_running_by_a_gone_gateway_is_settled_when_the_next_one_starts(self):
        run = self._left_running()
        self.made().claim()
        row = self._row(run)
        self.assertIsNotNone(row["ended_at"], "the run is still marked as running")
        self.assertEqual("stopped", row["outcome"])
        self.assertEqual(gateway.ABANDONED_WHY, row["why"])

    def test_a_turn_that_is_genuinely_still_turning_is_left_running(self):
        """Settling live work would be the same lie the other way up. What is turning
        says so for itself, and this gateway asks that rather than a process table."""
        run = self._left_running()
        self._turning(run)
        self.made().claim()
        self.assertIsNone(self._row(run)["ended_at"],
                          "a turn that is genuinely running was written off")

    def test_what_a_crashed_turn_left_behind_is_gone_once_a_gateway_claims_the_name(self):
        """R-GW-23 — the record a turn publishes for itself is removed by exactly one
        thing, the turn's own `finally`, and a gateway killed outright never reaches it.
        Nothing swept them afterwards: `release` takes the record file and `forget` takes
        the record, the lock and the log. So one file per crashed turn stood for the life
        of the install, cost a liveness check on every look at what an agent is doing, and
        kept `agent.forget` from ever removing the agent's own `run/` directory."""
        run = self._left_running()
        gone = subprocess.Popen([sys.executable, "-c", ""])
        gone.wait()
        self._turning(run, pid=gone.pid)
        self.assertEqual(1, len(list((self.where / "turns").glob("*.json"))))
        self.made().claim()
        self.assertEqual([], list((self.where / "turns").glob("*.json")),
                         "what a crashed turn left behind is still standing")
        self.assertIsNotNone(self._row(run)["ended_at"],
                             "and the run it named was left marked as running")

    def test_settling_one_stranded_run_does_not_touch_a_run_that_already_ended(self):
        """A settled run keeps what it was settled as — including what it cost."""
        done = self._left_running(provider="claude")
        self.records.ended(done, "2026-07-27T18:33:00Z", "finished",
                           tokens={"input": 12, "output": 3, "reported": True})
        stranded = self._left_running()
        self.made().claim()
        settled, kept = self._row(stranded), self._row(done)
        self.assertEqual("stopped", settled["outcome"])
        self.assertEqual("finished", kept["outcome"], "a finished run was overwritten")
        self.assertEqual("2026-07-27T18:33:00Z", kept["ended_at"])
        self.assertEqual(12, kept["tokens_in"])

    def test_a_gateway_whose_records_will_not_settle_still_comes_up(self):
        """A gateway that refused to start because it could not tidy the last one's
        records is a worse outage than the bad rows it was trying to fix."""
        class Refuses:
            def __getattr__(self, named):
                raise RuntimeError("records are unreadable")

        gw = self.made()
        gw.records = Refuses()
        gw._settle_runs_nothing_is_doing()          # says so in the log, and returns
        gw.claim()
        self.assertIsNotNone(gw._lock, "the gateway refused to start over old records")


class LifecycleOutcomesWaitForReachability(WithARunDirectory):
    """R-UPD-40, R-GW-43 — lifecycle outcomes wait for their channel to reconnect."""

    async def test_lifecycle_outcomes_are_not_offered_until_the_channel_is_ready(self):
        """A disconnected channel is an expected wait state, not a failed delivery."""
        class Surface:
            def __init__(self):
                self.connected = False
                self.update_calls = 0
                self.restart_calls = 0
                self.update_refused = False
                self.restart_refused = False

            async def told_update_finished(self, _conversation, _text):
                self.update_calls += 1
                if not self.connected:
                    raise RuntimeError("channel 'ops' is not connected")
                if not self.update_refused:
                    self.update_refused = True
                    raise OSError("the platform is busy")

            async def told_restart_finished(self, _conversation, _text):
                self.restart_calls += 1
                if not self.connected:
                    raise RuntimeError("channel 'ops' is not connected")
                if not self.restart_refused:
                    self.restart_refused = True
                    raise OSError("the platform is busy")

        update = {
            "id": "update-1",
            "origin": {"channel": "ops", "conversation": "one"},
        }
        restart = {
            "id": "restart-1",
            "origin": {"channel": "ops", "conversation": "one"},
        }
        surface = Surface()
        gw = self.made("ava")
        gw._reached["ops"] = surface
        sleeps = 0

        async def advance(_seconds):
            nonlocal sleeps
            sleeps += 1
            if sleeps == 30:
                self.assertEqual(0, surface.update_calls)
                self.assertEqual(0, surface.restart_calls)
                update_delivered.assert_not_called()
                restart_delivered.assert_not_called()
                self.assertEqual([], warning.call_args_list,
                                 "waiting for readiness wrote warning noise")
                surface.connected = True
            elif sleeps == 31:
                self.assertEqual((1, 1), (surface.update_calls, surface.restart_calls))
                update_delivered.assert_not_called()
                restart_delivered.assert_not_called()
            elif sleeps == 32:
                gw._stopping = True

        with (
            mock.patch.object(gateway.update_request, "deliverable", return_value=update),
            mock.patch.object(gateway.update_request, "summary", return_value="updated"),
            mock.patch.object(gateway.update_request, "delivered") as update_delivered,
            mock.patch.object(gateway.restart_request, "deliverable", return_value=restart),
            mock.patch.object(gateway.restart_request, "summary", return_value="restarted"),
            mock.patch.object(gateway.restart_request, "delivered") as restart_delivered,
            mock.patch.object(gateway.asyncio, "sleep", new=advance),
            mock.patch.object(gw.log, "warning") as warning,
        ):
            await gw._deliver_update_notices()

        self.assertEqual(2, surface.update_calls,
                         "the update did not retry exactly once after a ready failure")
        self.assertEqual(2, surface.restart_calls,
                         "the restart did not retry exactly once after a ready failure")
        update_delivered.assert_called_once_with("update-1")
        restart_delivered.assert_called_once_with("ava", "restart-1")
        warnings = [call.args[0] % call.args[1:] for call in warning.call_args_list]
        self.assertEqual(2, len(warnings), "a ready failure was not warned once per retry")
        self.assertFalse(any("not connected" in line for line in warnings),
                         "an expected wait state was logged as a delivery failure")


class Delegating:
    """What a gateway is handed to carry role runs with, as a stand-in.

    The real one is `agent.playing`, made where an agent is known. Every case here runs
    with no agent, no bundle and no brain anywhere near it, which is the whole point of
    the seam being an argument.
    """

    def __init__(self, waiting=(), owed=(), carried=None, quiet=()):
        self._waiting = list(waiting)
        self._owed = list(owed)
        self._quiet = list(quiet)
        self.carried = carried if carried is not None else []
        self.claimed: list = []
        self.settled: list = []
        self.reviewing_runs: list = []
        self.reviewed_runs: list = []
        self.given_up: list = []
        self.swept = 0
        #: Where each run this stand-in knows about is shown, and how long it has been.
        self.check_ins: dict = {}

    def waiting(self):
        return list(self._waiting)

    def seen(self, run_id):
        return {"channel": "ops", "conversation": "one", "label": "a task",
                "role": "development", "elapsed": 0}

    def checking_in(self, run_id, told=0):
        """Exactly what `agent.playing` answers, off the same arithmetic — a stand-in
        more generous than the real thing hides whole features."""
        where = self.check_ins.get(run_id)
        if where is None:
            return None
        due = role_runs.check_in_due(where["elapsed"], told)
        return None if not due else {**where, "due": due}

    def stopping(self):
        return [one for one in self._waiting if one.get("stop_asked_at")]

    def stopped(self, run_id):
        self.settled.append(run_id)
        self._waiting = [one for one in self._waiting if one["id"] != run_id]

    async def carry(self, run_id, watching=None, steering=None, admitted=None):
        self.carried.append(run_id)
        self._waiting = [one for one in self._waiting if one["id"] != run_id]
        return None

    def owed(self):
        return list(self._owed)

    def claiming(self, role_run):
        self.claimed.append(role_run)

    def reviewing(self, role_run, review_run):
        self.reviewing_runs.append((role_run, review_run))

    def reviewed(self, role_run):
        self.reviewed_runs.append(role_run)
        self._owed = [one for one in self._owed if one["role_run"] != role_run]

    def giving_up(self, role_run):
        """Exactly what `agent.playing` does — the same write `reviewed` makes, so it
        stops being offered."""
        self.given_up.append(role_run)
        self._owed = [one for one in self._owed if one["role_run"] != role_run]

    def sweep(self):
        self.swept += 1
        return []

    def quiet(self):
        gone, self._quiet = list(self._quiet), []
        self._waiting = [one for one in self._waiting if one["id"] not in gone]
        return gone


class Reached:
    """One surface, as far as delivering a role handoff is concerned."""

    def __init__(self, connected: bool = True, raises=None, busy: bool = False,
                 answers: bool = True, owner_raises=None):
        self.connected = connected
        self.told: list = []
        #: Every notice this surface was asked to put in front of the owner alone.
        self.owner_told: list = []
        self._raises = raises
        self._busy = busy
        #: Whether the review turn this admits goes on to answer. The real
        #: `told_role_finished` returns the moment the turn is admitted and settles the
        #: handoff only once it has actually said something — so a stand-in that always
        #: settled would agree with the code that lost a report for exactly that reason.
        self._answers = answers
        self._owner_raises = owner_raises

    def answering_somebody(self, conversation):
        return self._busy

    async def told_role_finished(self, conversation, handoff, reviewing=None,
                                 delivered=None):
        if self._raises is not None:
            raise self._raises
        if reviewing is not None:
            reviewing("11-rrrr")
        self.told.append((conversation, handoff))
        if delivered is not None and self._answers:
            delivered()

    async def told_the_owner(self, text):
        if self._owner_raises is not None:
            raise self._owner_raises
        self.owner_told.append(text)


class Shown(Reached):
    """One surface, as far as *showing* a role run is concerned."""

    def __init__(self):
        super().__init__()
        self.working: list = []
        self.checked_in: list = []
        self.settled: list = []

    def told_role_working(self, conversation, run, label, role="", elapsed=0):
        self.working.append((conversation, run, label, role, elapsed))

    def told_role_checking_in(self, conversation, run, label, role="", elapsed=0):
        self.checked_in.append((conversation, run, label, role, elapsed))

    def told_role_settled(self, conversation, run, ok, summary, role="", elapsed=0):
        self.settled.append((conversation, run, ok, summary, role, elapsed))


class CarryingWhatAnAgentHandedOn(WithARunDirectory):
    """R-ROL-15 — work admitted while nothing was up is still carried, and its parent
    is told exactly once."""

    def one(self, doing) -> gateway.Gateway:
        gw = gateway.Gateway("ava", where=self.where, logs=self.logs, root=self.root,
                             roles=doing)
        self.addCleanup(gw.release)
        return gw

    async def test_a_gateway_carries_every_admitted_role_run_it_finds(self):
        doing = Delegating(waiting=[{"id": "rol-1-aaaa"}, {"id": "rol-2-bbbb"}])
        gw = self.one(doing)

        gw._start_admitted_roles()
        await asyncio.gather(*tuple(gw._role_tasks.values()))

        self.assertEqual(["rol-1-aaaa", "rol-2-bbbb"], sorted(doing.carried))

    async def test_a_root_already_in_flight_is_never_started_a_second_time(self):
        """R-GW-15 — the same work started twice answers its parent twice."""
        held = asyncio.Event()
        doing = Delegating(waiting=[{"id": "rol-1-aaaa"}])

        async def carrying(run_id, **_given):
            doing.carried.append(run_id)
            await held.wait()

        doing.carry = carrying
        gw = self.one(doing)

        gw._start_admitted_roles()
        gw._start_admitted_roles()
        held.set()
        await asyncio.gather(*tuple(gw._role_tasks.values()))

        self.assertEqual(["rol-1-aaaa"], doing.carried)

    async def test_a_parent_is_told_once_and_the_review_stops_being_owed(self):
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "channel": "ops",
                                  "conversation": "one",
                                  "handoff": {"report": "done"}}])
        gw = self.one(doing)
        surface = Reached()
        gw._reached["ops"] = surface

        await gw._deliver_one_role_review()

        self.assertEqual([("one", {"report": "done"})], surface.told)
        self.assertEqual(["rol-1-aaaa"], doing.claimed)
        self.assertEqual([("rol-1-aaaa", "11-rrrr")], doing.reviewing_runs)
        self.assertEqual(["rol-1-aaaa"], doing.reviewed_runs)

    async def test_a_review_is_left_owing_while_the_surface_is_down(self):
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "channel": "ops",
                                  "conversation": "one", "handoff": {}}])
        gw = self.one(doing)
        gw._reached["ops"] = Reached(connected=False)

        await gw._deliver_one_role_review()

        self.assertEqual([], doing.reviewed_runs)
        self.assertEqual([], doing.claimed)

    async def test_a_review_the_surface_refused_is_left_owing_rather_than_lost(self):
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "channel": "ops",
                                  "conversation": "one", "handoff": {}}])
        gw = self.one(doing)
        gw._reached["ops"] = Reached(raises=RuntimeError("the room is busy"))

        with self.assertRaises(RuntimeError):
            await gw._deliver_one_role_review()

        self.assertEqual(["rol-1-aaaa"], doing.claimed)
        self.assertEqual([], doing.reviewed_runs)

    async def test_a_review_that_answered_nobody_leaves_the_handoff_owed(self):
        """R-ROL-15 — issue #282 part B. The review turn was admitted and answered
        nobody, which is what a stale provider session does, and the handoff was written
        off the instant it started. The work was done, the provider was paid for it, and
        the report was read by nobody — with nothing anywhere saying so."""
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "role": "development",
                                  "attempts": 1, "channel": "ops",
                                  "conversation": "one",
                                  "handoff": {"report": "done"}}])
        gw = self.one(doing)
        gw._reached["ops"] = Reached(answers=False)

        await gw._deliver_one_role_review()

        self.assertEqual(["rol-1-aaaa"], doing.claimed, "it was not even attempted")
        self.assertEqual([], doing.reviewed_runs,
                         "a review that answered nobody was written off as delivered")
        self.assertEqual(["rol-1-aaaa"], [one["role_run"] for one in doing.owed()],
                         "the handoff is not there to be offered again")

    async def test_a_handoff_under_the_ceiling_is_woken_for_again(self):
        """R-ROL-37 — two failed attempts is a blip, not a parent that cannot be woken."""
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "role": "development",
                                  "attempts": role_runs.REVIEW_CEILING - 1,
                                  "channel": "ops", "conversation": "one",
                                  "handoff": {"report": "done"}}])
        gw = self.one(doing)
        surface = Reached()
        gw._reached["ops"] = surface

        await gw._deliver_one_role_review()

        self.assertEqual([("one", {"report": "done"})], surface.told)
        self.assertEqual([], surface.owner_told, "the owner was told about a live handoff")
        self.assertEqual([], doing.given_up)

    async def test_a_handoff_at_the_ceiling_is_settled_once_and_the_owner_told(self):
        """R-ROL-37 — a parent that fails every time would otherwise be woken for the same
        report every few seconds for the whole retention window, and the one place nothing
        can be said about it is the conversation whose review turn is the thing failing."""
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "role": "development",
                                  "attempts": role_runs.REVIEW_CEILING,
                                  "channel": "ops", "conversation": "one",
                                  "handoff": {"report": "done"}}])
        gw = self.one(doing)
        surface = Reached()
        gw._reached["ops"] = surface

        await gw._deliver_one_role_review()
        await gw._deliver_one_role_review()

        self.assertEqual([], surface.told, "the parent was woken past the ceiling")
        self.assertEqual(1, len(surface.owner_told), "the owner was told twice or not at all")
        self.assertIn("rol-1-aaaa", surface.owner_told[0])
        self.assertIn("development", surface.owner_told[0])
        self.assertEqual(["rol-1-aaaa"], doing.given_up)
        self.assertEqual([], doing.owed(), "it is still there to be offered again")

    async def test_the_undeliverable_notice_repeats_no_word_of_the_unreviewed_report(self):
        """R-ROL-19 — the report has still been read by nobody, so putting any of it in
        front of the owner would publish unreviewed work by the one route built to stop
        exactly that. The run and the role are enough to go and ask for it."""
        report = "Landed the change; the suite passes."
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "role": "development",
                                  "attempts": role_runs.REVIEW_CEILING,
                                  "channel": "ops", "conversation": "one",
                                  "handoff": {"report": report, "target": "/tmp/checkout",
                                              "brief": "rewrite the exporter"}}])
        gw = self.one(doing)
        surface = Reached()
        gw._reached["ops"] = surface

        await gw._deliver_one_role_review()

        said = surface.owner_told[0]
        self.assertNotIn(report, said, "an unreviewed report reached a person")
        self.assertNotIn("/tmp/checkout", said)
        self.assertNotIn("rewrite the exporter", said)

    async def test_a_surface_that_could_not_tell_the_owner_leaves_the_handoff_owed(self):
        """R-ROL-37 — told first and written off second, so a notice that did not arrive
        is tried again rather than being the thing that was lost."""
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "role": "development",
                                  "attempts": role_runs.REVIEW_CEILING,
                                  "channel": "ops", "conversation": "one",
                                  "handoff": {"report": "done"}}])
        gw = self.one(doing)
        gw._reached["ops"] = Reached(owner_raises=RuntimeError("the platform refused it"))

        with self.assertRaises(RuntimeError):
            await gw._deliver_one_role_review()

        self.assertEqual([], doing.given_up)
        self.assertEqual(["rol-1-aaaa"], [one["role_run"] for one in doing.owed()])

    async def test_a_handoff_settled_undeliverable_never_holds_up_the_ones_behind(self):
        """R-ROL-15 — the same rule a channel the owner removed already obeys: one review
        that cannot be delivered must not sit at the head keeping every later one behind
        it, or work that was done is never reported and nothing says why."""
        doing = Delegating(owed=[
            {"role_run": "rol-1-aaaa", "role": "development",
             "attempts": role_runs.REVIEW_CEILING, "channel": "ops",
             "conversation": "one", "handoff": {"report": "the first"}},
            {"role_run": "rol-2-bbbb", "role": "development", "attempts": 0,
             "channel": "ops", "conversation": "two", "handoff": {"report": "the second"}},
        ])
        gw = self.one(doing)
        surface = Reached()
        gw._reached["ops"] = surface

        await gw._deliver_one_role_review()

        self.assertEqual(["rol-1-aaaa"], doing.given_up)
        self.assertEqual([("two", {"report": "the second"})], surface.told,
                         "the handoff behind an undeliverable one was never offered")

    async def test_handing_work_to_a_role_is_shown_where_it_was_asked_for(self):
        """R-ROL-27 — a role was invisible: the command admitting it showed as an ordinary
        shell run, the work said nothing, and the agent answered minutes later with no
        sign of where the answer came from."""
        doing = Delegating(waiting=[{"id": "rol-1-aaaa"}])
        gw = self.one(doing)
        surface = Shown()
        gw._reached["ops"] = surface

        gw._start_admitted_roles()
        await asyncio.gather(*tuple(gw._role_tasks.values()))

        self.assertEqual(
            [("one", "rol-1-aaaa", "a task", "development", 0)], surface.working,
            "nothing said the work had been handed on")
        self.assertEqual([("one", "rol-1-aaaa")],
                         [(one[0], one[1]) for one in surface.settled],
                         "nothing said what came of it")

    async def test_a_role_that_could_not_be_carried_still_says_how_it_went(self):
        """Work handed over and never heard of again reads as still running for ever."""
        doing = Delegating(waiting=[{"id": "rol-1-aaaa"}])

        async def broke(_run, **_given):
            raise RuntimeError("the bundle was not there")

        doing.carry = broke
        gw = self.one(doing)
        surface = Shown()
        gw._reached["ops"] = surface

        gw._start_admitted_roles()
        await asyncio.gather(*tuple(gw._role_tasks.values()))

        self.assertEqual(1, len(surface.working))
        self.assertEqual([False], [one[2] for one in surface.settled])

    async def test_a_run_still_working_says_so_once_per_window(self):
        """R-ROL-36 — a run somebody asked for goes quiet for an hour otherwise, and a
        room cannot tell that from a run that is gone."""
        doing = Delegating()
        gw = self.one(doing)
        surface = Shown()
        gw._reached["ops"] = surface
        gw._role_tasks["rol-1-aaaa"] = None
        doing.check_ins = {"rol-1-aaaa": {
            "channel": "ops", "conversation": "one", "label": "a task",
            "role": "development", "elapsed": 1300}}

        gw._check_in_on_roles()
        gw._check_in_on_roles()   # the same window, a second look

        self.assertEqual([("one", "rol-1-aaaa", "a task", "development", 1300)],
                         surface.checked_in,
                         "a run still working was said twice, or never")
        self.assertEqual({"rol-1-aaaa": 1}, gw._role_checked)

    async def test_a_run_inside_its_window_is_never_checked_in_on(self):
        doing = Delegating()
        gw = self.one(doing)
        surface = Shown()
        gw._reached["ops"] = surface
        gw._role_tasks["rol-1-aaaa"] = None
        doing.check_ins = {"rol-1-aaaa": {
            "channel": "ops", "conversation": "one", "label": "a task",
            "role": "development", "elapsed": 60}}

        gw._check_in_on_roles()

        self.assertEqual([], surface.checked_in)
        self.assertEqual({}, gw._role_checked)

    async def test_a_run_this_gateway_is_not_carrying_is_never_checked_in_on(self):
        """A check-in that outlived the work it describes is a room being told a run is
        going by the one process that would know it is not."""
        doing = Delegating()
        gw = self.one(doing)
        surface = Shown()
        gw._reached["ops"] = surface
        doing.check_ins = {"rol-1-aaaa": {
            "channel": "ops", "conversation": "one", "label": "a task",
            "role": "development", "elapsed": 1300}}

        gw._check_in_on_roles()

        self.assertEqual([], surface.checked_in)

    async def test_a_check_in_a_surface_cannot_take_is_never_said_again(self):
        """Set before the record is queued: a surface that throws costs one skipped line
        rather than a line every five seconds for the rest of the run."""
        doing = Delegating()
        gw = self.one(doing)

        class Refuses(Shown):
            def told_role_checking_in(self, *given, **also):
                raise RuntimeError("the platform would not take it")

        gw._reached["ops"] = Refuses()
        gw._role_tasks["rol-1-aaaa"] = None
        doing.check_ins = {"rol-1-aaaa": {
            "channel": "ops", "conversation": "one", "label": "a task",
            "role": "development", "elapsed": 1300}}

        with mock.patch.object(gw.log, "warning") as warned:
            gw._check_in_on_roles()
            gw._check_in_on_roles()

        self.assertEqual({"rol-1-aaaa": 1}, gw._role_checked)
        self.assertEqual(1, warned.call_count, "a refused check-in was retried every look")

    async def test_a_surface_that_is_down_is_skipped_without_raising(self):
        doing = Delegating()
        gw = self.one(doing)
        surface = Shown()
        surface.connected = False
        gw._reached["ops"] = surface
        gw._role_tasks["rol-1-aaaa"] = None
        gw._role_tasks["rol-2-bbbb"] = None
        doing.check_ins = {
            "rol-1-aaaa": {"channel": "ops", "conversation": "one", "label": "a task",
                           "role": "development", "elapsed": 1300},
            # A run whose parent conversation nothing ever recorded.
            "rol-2-bbbb": {"channel": "ops", "conversation": "", "label": "a task",
                           "role": "development", "elapsed": 1300},
        }

        gw._check_in_on_roles()

        self.assertEqual([], surface.checked_in)
        self.assertEqual({}, gw._role_checked,
                         "a run nothing was told about was written down as told")

    async def test_a_settled_run_stops_being_checked_in_on(self):
        """The bookkeeping goes with the work: a process that runs for weeks must not
        keep a number for every run it ever carried."""
        doing = Delegating(waiting=[{"id": "rol-1-aaaa"}])
        gw = self.one(doing)
        gw._reached["ops"] = Shown()
        gw._role_checked["rol-1-aaaa"] = 3

        gw._start_admitted_roles()
        await asyncio.gather(*tuple(gw._role_tasks.values()))

        self.assertEqual({}, gw._role_checked)

    async def test_a_surface_that_cannot_be_told_never_holds_up_the_work(self):
        doing = Delegating(waiting=[{"id": "rol-1-aaaa"}])
        gw = self.one(doing)   # nothing reached: no surface for 'ops' at all

        gw._start_admitted_roles()
        await asyncio.gather(*tuple(gw._role_tasks.values()))

        self.assertEqual(["rol-1-aaaa"], doing.carried)

    async def test_an_undeliverable_review_never_holds_up_the_ones_behind_it(self):
        """R-ROL-15 — a channel the owner has since removed never comes back, and the
        oldest handoff sitting at the head of the queue would keep every later one from
        ever being reported."""
        doing = Delegating(owed=[
            {"role_run": "rol-1-aaaa", "channel": "gone", "conversation": "one",
             "handoff": {}},
            {"role_run": "rol-2-bbbb", "channel": "ops", "conversation": "two",
             "handoff": {"report": "done"}},
        ])
        gw = self.one(doing)
        surface = Reached()
        gw._reached["ops"] = surface

        await gw._deliver_one_role_review()

        self.assertEqual([("two", {"report": "done"})], surface.told)
        self.assertEqual(["rol-2-bbbb"], doing.reviewed_runs)

    async def test_a_parent_mid_turn_adds_nothing_to_the_attempt_count(self):
        """R-ROL-32 — the handoff waiting for a busy parent is correct and is retried
        every five seconds, so counting each look put seven hundred attempts on an agent
        that was simply answering somebody. That count is the only thing an owner has for
        spotting a surface that is never coming back, and a busy parent looked identical
        to a dead channel."""
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "channel": "ops",
                                  "conversation": "one", "handoff": {"report": "done"}}])
        gw = self.one(doing)
        gw._reached["ops"] = Reached(busy=True)

        for _ in range(5):
            await gw._deliver_one_role_review()

        self.assertEqual([], doing.claimed, "a busy parent was counted as an attempt")
        self.assertEqual([], doing.reviewed_runs)

    async def test_the_handoff_still_arrives_once_the_busy_parent_goes_idle(self):
        """The other half: waiting is not losing it."""
        doing = Delegating(owed=[{"role_run": "rol-1-aaaa", "channel": "ops",
                                  "conversation": "one", "handoff": {"report": "done"}}])
        gw = self.one(doing)
        surface = Reached(busy=True)
        gw._reached["ops"] = surface

        await gw._deliver_one_role_review()
        surface._busy = False
        await gw._deliver_one_role_review()

        self.assertEqual([("one", {"report": "done"})], surface.told)
        self.assertEqual(["rol-1-aaaa"], doing.claimed)
        self.assertEqual(["rol-1-aaaa"], doing.reviewed_runs)

    async def test_a_busy_parent_never_holds_up_the_handoffs_behind_it(self):
        doing = Delegating(owed=[
            {"role_run": "rol-1-aaaa", "channel": "busy", "conversation": "one",
             "handoff": {}},
            {"role_run": "rol-2-bbbb", "channel": "ops", "conversation": "two",
             "handoff": {"report": "done"}},
        ])
        gw = self.one(doing)
        gw._reached["busy"] = Reached(busy=True)
        surface = Reached()
        gw._reached["ops"] = surface

        await gw._deliver_one_role_review()

        self.assertEqual([("two", {"report": "done"})], surface.told)
        self.assertEqual(["rol-2-bbbb"], doing.claimed)

    def test_a_run_that_went_quiet_is_settled_on_the_sweep(self):
        """R-ROL-30 — nothing checked for silence at all, so a wedged provider sat
        `working` until its retention window closed a fortnight later."""
        doing = Delegating(waiting=[{"id": "rol-1-aaaa"}], quiet=["rol-1-aaaa"])
        gw = self.one(doing)

        gw._sweep_roles()

        self.assertEqual([], doing.waiting())
        self.assertEqual(1, doing.swept, "the expiry sweep was skipped")

    async def test_settling_a_quiet_run_lets_go_of_what_was_carrying_it(self):
        """A run reported finished while a task here still awaits a wedged provider is a
        run somebody is still paying for."""
        held = asyncio.Event()
        doing = Delegating(waiting=[{"id": "rol-1-aaaa"}], quiet=["rol-1-aaaa"])

        async def carrying(run_id, **_given):
            doing.carried.append(run_id)
            await held.wait()

        doing.carry = carrying
        gw = self.one(doing)
        gw._start_admitted_roles()
        task = gw._role_tasks["rol-1-aaaa"]
        for _ in range(200):
            if doing.carried:
                break
            await asyncio.sleep(0.005)

        gw._sweep_roles()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        self.assertTrue(task.cancelled(), "the wedged turn was left running")
        held.set()

    def test_a_broken_configuration_never_stops_expired_bundles_being_cleared(self):
        """How long silence may last is the owner's to state, in a file they edit by hand.
        One they have broken must not also keep a fortnight of bundles on disk."""
        doing = Delegating()

        def unreadable():
            raise RuntimeError("config.json: 'roles.quiet_hours' is missing")

        doing.quiet = unreadable
        gw = self.one(doing)

        gw._sweep_roles()

        self.assertEqual(1, doing.swept)

    def test_a_gateway_with_no_agent_behind_it_carries_no_role_run_at_all(self):
        gw = gateway.Gateway("ava", where=self.where, logs=self.logs, root=self.root)
        self.addCleanup(gw.release)
        gw._sweep_roles()   # nothing to sweep, and nothing to raise
        self.assertEqual({}, gw._role_tasks)
class TellsTheOwnerWhatItsAgentMayDo(WithARunDirectory):
    """R-CH-32 — an agent gaining or losing a skill reaches its owner."""

    class Surface:
        """One channel, as the gateway reaches it."""

        def __init__(self, connected: bool = True, refuses: bool = False):
            self.connected = connected
            self.refuses = refuses
            self.told: list = []

        async def told_the_owner(self, text):
            if self.refuses:
                raise OSError("the platform is busy")
            self.told.append(text)

    def watching(self, *granted, reachable=("ops",), name="ava"):
        """A gateway holding one agent whose grants a case moves under it."""
        gw = self.made(name)
        gw.reachable = list(reachable)
        self.grants = list(granted)
        gw.granted = lambda: list(self.grants)
        return gw

    def look(self, gw):
        """One pass of the loop, without its wait."""
        gw._look_at_skills()
        return gw._say_skill_changes()

    async def test_a_first_look_says_nothing_and_writes_down_what_is_there(self):
        """An install where this never ran holds skills that were never newly granted."""
        gw = self.watching("alpha", "beta")
        surface = self.Surface()
        gw._reached["ops"] = surface
        await self.look(gw)
        self.assertEqual([], surface.told, "grants already held were announced as new")
        self.assertEqual(("alpha", "beta"), gw._skills_seen())

    async def test_a_skill_the_agent_gained_is_told_to_its_owner(self):
        gw = self.watching("alpha")
        surface = self.Surface()
        gw._reached["ops"] = surface
        await self.look(gw)
        self.grants.append("beta")
        await self.look(gw)
        self.assertEqual(["🧩 **Skill added** — `beta`"], surface.told)

    async def test_a_skill_the_agent_lost_is_told_to_its_owner(self):
        gw = self.watching("alpha", "beta")
        surface = self.Surface()
        gw._reached["ops"] = surface
        await self.look(gw)
        self.grants.remove("alpha")
        await self.look(gw)
        self.assertEqual(["🗑️ **Skill removed** — `alpha`"], surface.told)

    async def test_several_changes_at_once_are_one_message(self):
        """A catalog brings several skills and takes several away in one go, and an owner
        reading a phone wants one notice rather than a page of them."""
        gw = self.watching("alpha", "beta")
        surface = self.Surface()
        gw._reached["ops"] = surface
        await self.look(gw)
        self.grants = ["beta", "gamma", "delta"]
        await self.look(gw)
        self.assertEqual(
            ["🧩 **Skill added** — `gamma`\n"
             "🧩 **Skill added** — `delta`\n"
             "🗑️ **Skill removed** — `alpha`"],
            surface.told)

    async def test_a_change_is_told_once_however_often_it_is_looked_at(self):
        gw = self.watching("alpha")
        surface = self.Surface()
        gw._reached["ops"] = surface
        await self.look(gw)
        self.grants.append("beta")
        await self.look(gw)
        await self.look(gw)
        await self.look(gw)
        self.assertEqual(1, len(surface.told), "the same change was told more than once")

    async def test_an_agent_reached_on_two_surfaces_is_told_on_one(self):
        """Two surfaces are one owner, and the same news twice reads as two changes."""
        gw = self.watching("alpha", reachable=("ops", "away"))
        first, second = self.Surface(), self.Surface()
        gw._reached["away"], gw._reached["ops"] = first, second
        await self.look(gw)
        self.grants.append("beta")
        await self.look(gw)
        self.assertEqual(1, len(first.told), "the first surface by name was not the one told")
        self.assertEqual([], second.told, "one change was told on two surfaces")

    async def test_a_change_waits_for_a_surface_rather_than_being_lost(self):
        gw = self.watching("alpha")
        surface = self.Surface(connected=False)
        gw._reached["ops"] = surface
        await self.look(gw)
        self.grants.append("beta")
        await self.look(gw)
        self.assertEqual([], surface.told)
        surface.connected = True
        await self.look(gw)
        self.assertEqual(["🧩 **Skill added** — `beta`"], surface.told)

    async def test_a_change_a_surface_refused_is_told_again(self):
        """A delivery that failed is not a delivery, so nothing is written down for it."""
        gw = self.watching("alpha")
        surface = self.Surface(refuses=True)
        gw._reached["ops"] = surface
        await self.look(gw)
        self.grants.append("beta")
        await self.look(gw)
        surface.refuses = False
        await self.look(gw)
        self.assertEqual(["🧩 **Skill added** — `beta`"], surface.told)

    async def test_a_change_made_while_the_agent_was_stopped_is_still_told(self):
        """Taking a skill away is exactly what an owner does with the gateway down."""
        gw = self.watching("alpha", "beta")
        await self.look(gw)                       # what it could do when it last ran
        after = self.watching("alpha", name="ava")
        surface = self.Surface()
        after._reached["ops"] = surface
        await self.look(after)
        self.assertEqual(["🗑️ **Skill removed** — `beta`"], surface.told)

    async def test_an_agent_reached_on_nothing_is_owed_no_notice(self):
        """Otherwise an owner adding their first channel months later is greeted by every
        grant they ever made."""
        gw = self.watching("alpha", reachable=())
        await self.look(gw)
        self.grants.append("beta")
        await self.look(gw)
        self.assertEqual(("alpha", "beta"), gw._skills_seen())
        self.assertIsNone(gw._skills_owed)

    async def test_a_name_that_is_not_an_agent_is_not_watched(self):
        """A gateway of a name nothing was made for holds no grants, and still runs."""
        gw = self.made("ava")
        gw._stopping = True
        await gw._tell_about_skills()             # returns rather than asking None()

    async def test_grants_that_cannot_be_read_are_said_once(self):
        gw = self.watching("alpha")
        gw.granted = mock.Mock(side_effect=OSError("no such directory"))
        gw._stopping = False
        rounds = 0

        async def advance(_seconds):
            nonlocal rounds
            rounds += 1
            if rounds == 3:
                gw._stopping = True

        with (mock.patch.object(gateway.asyncio, "sleep", new=advance),
              mock.patch.object(gw.log, "warning") as warning):
            await gw._tell_about_skills()
        self.assertEqual(3, gw.granted.call_count)
        self.assertEqual(1, warning.call_count,
                         "an unreadable grant directory was said on every look")


class IntroducesTheAgentToSomebodyNewlyAllowed(WithARunDirectory):
    """R-CH-33 — a person newly allowed to reach an agent is greeted, once, by the agent.

    Every other private notice here has a fixed wording rundesk wrote. This one is a whole
    turn against the agent's own brain, so what it costs and how often it is attempted are
    part of the contract rather than details.
    """

    class Surface:
        """One channel, as the gateway reaches it: what it allows, and who it greeted."""

        def __init__(self, allow=("2207",), connected: bool = True, refuses: bool = False):
            self.connected = connected
            self.refuses = refuses
            self.record = {"allow": list(allow)}
            self.greeted: list = []

        async def welcomed(self, user):
            if self.refuses:
                raise OSError("the platform is busy")
            self.greeted.append(user)

    class Reached:
        """What `agent.reachable` hands a gateway, as far as this loop is concerned."""

        def __init__(self, name, home):
            self.name, self.home = name, home

    def setUp(self):
        super().setUp()
        # Channel homes stand under the agent, never in the run directory: the run
        # directory's `*.json` entries are the list of gateways there are.
        self.homes = Path(tempfile.mkdtemp(prefix="rundesk-channels-"))
        self.addCleanup(shutil.rmtree, self.homes, True)

    def greeting(self, *channels, name="ava"):
        """A gateway holding channels a case can move who they allow under it."""
        gw = self.made(name)
        gw.reachable = list(channels)
        return gw

    def channel(self, named, allow=("2207",), connected=True, refuses=False, new=True):
        """One reachable channel with a home of its own, and the surface holding it."""
        home = self.homes / named
        home.mkdir(parents=True, exist_ok=True)
        if new:
            gateway.remember_no_one_welcomed(home)
        return (self.Reached(named, home),
                self.Surface(allow=allow, connected=connected, refuses=refuses))

    def welcomed_in(self, one) -> list:
        return json.loads(
            gateway.welcomed_path(one.home).read_text(encoding="utf-8"))["welcomed"]

    async def test_somebody_newly_allowed_is_greeted_and_written_down(self):
        """R-CH-33"""
        one, surface = self.channel("ops")
        gw = self.greeting(one)
        gw._reached["ops"] = surface
        await gw._welcome_anyone_owed()
        self.assertEqual(["2207"], surface.greeted)
        self.assertEqual(["2207"], self.welcomed_in(one))

    async def test_somebody_already_greeted_is_not_greeted_again(self):
        """R-CH-33 — a reconnect, a restart and an update all come back through here."""
        one, surface = self.channel("ops")
        gw = self.greeting(one)
        gw._reached["ops"] = surface
        await gw._welcome_anyone_owed()
        after = self.greeting(one, name="ava")          # the gateway that comes back
        after._reached["ops"] = surface
        await after._welcome_anyone_owed()
        self.assertEqual(["2207"], surface.greeted, "the same person was greeted twice")

    async def test_a_channel_from_before_this_existed_greets_nobody(self):
        """R-CH-33 — updating rundesk must not greet people who have been reaching the
        agent for months. A channel with no record at all is one an older release wrote."""
        one, surface = self.channel("ops", new=False)
        gw = self.greeting(one)
        gw._reached["ops"] = surface
        await gw._welcome_anyone_owed()
        self.assertEqual([], surface.greeted)
        self.assertEqual(["2207"], self.welcomed_in(one),
                         "who is already there was not written down as known")

    async def test_only_the_person_newly_added_is_greeted(self):
        """R-CH-33 — adding a second owner, and replacing one with another, both reach
        exactly the person who has just arrived."""
        one, surface = self.channel("ops")
        gw = self.greeting(one)
        gw._reached["ops"] = surface
        await gw._welcome_anyone_owed()
        surface.record["allow"] = ["2207", "1180"]
        after = self.greeting(one, name="ava")
        after._reached["ops"] = surface
        await after._welcome_anyone_owed()
        self.assertEqual(["2207", "1180"], surface.greeted)

    async def test_somebody_taken_off_and_added_again_is_greeted_again(self):
        """R-CH-33 — a new membership is a new introduction."""
        one, surface = self.channel("ops")
        gw = self.greeting(one)
        gw._reached["ops"] = surface
        await gw._welcome_anyone_owed()
        surface.record["allow"] = ["1180"]              # 2207 taken off
        gw = self.greeting(one, name="ava")
        gw._reached["ops"] = surface
        await gw._welcome_anyone_owed()
        surface.record["allow"] = ["1180", "2207"]      # and put back
        gw = self.greeting(one, name="ava")
        gw._reached["ops"] = surface
        await gw._welcome_anyone_owed()
        self.assertEqual(["2207", "1180", "2207"], surface.greeted)

    async def test_an_agent_reached_on_two_channels_greets_one_person_once(self):
        """R-CH-33 — two surfaces are one agent, and two hellos a minute apart read as
        two agents."""
        first, first_surface = self.channel("away")
        second, second_surface = self.channel("ops")
        gw = self.greeting(first, second)
        gw._reached["away"], gw._reached["ops"] = first_surface, second_surface
        await gw._welcome_anyone_owed()
        self.assertEqual(["2207"], first_surface.greeted,
                         "the first channel by name was not the one that greeted them")
        self.assertEqual([], second_surface.greeted, "one person was greeted twice")
        self.assertEqual(["2207"], self.welcomed_in(second),
                         "the other channel still owes a greeting already delivered")

    async def test_a_greeting_waits_for_a_surface_rather_than_being_lost(self):
        """R-CH-33"""
        one, surface = self.channel("ops", connected=False)
        gw = self.greeting(one)
        gw._reached["ops"] = surface
        await gw._welcome_anyone_owed()
        self.assertEqual([], surface.greeted)
        surface.connected = True
        await gw._welcome_anyone_owed()
        self.assertEqual(["2207"], surface.greeted)

    async def test_a_greeting_that_failed_is_not_written_down_as_delivered(self):
        """R-CH-33 — and is tried again by the next gateway that comes up well, rather
        than every ten seconds against a brain that cannot run."""
        one, surface = self.channel("ops", refuses=True)
        gw = self.greeting(one)
        gw._reached["ops"] = surface
        with mock.patch.object(gw.log, "warning") as warning:
            await gw._welcome_anyone_owed()
            await gw._welcome_anyone_owed()
        self.assertEqual([], self.welcomed_in(one))
        self.assertEqual(1, warning.call_count,
                         "a whole turn was asked for again inside one gateway's life")
        surface.refuses = False
        after = self.greeting(one, name="ava")
        after._reached["ops"] = surface
        await after._welcome_anyone_owed()
        self.assertEqual(["2207"], surface.greeted)

    async def test_a_channel_that_is_not_up_greets_nobody(self):
        """R-CH-33 — a record with nobody holding it open is not a surface."""
        one, _surface = self.channel("ops")
        gw = self.greeting(one)
        await gw._welcome_anyone_owed()
        self.assertEqual([], self.welcomed_in(one))

    async def test_a_gateway_with_no_channels_watches_nothing(self):
        """R-CH-33 — including a gateway of a name nothing was made for."""
        gw = self.made("ava")
        gw._stopping = True
        await gw._welcome_new_owners()               # returns rather than reaching for one


class WhatAChannelHasWrittenDownAboutWhoItGreeted(WithARunDirectory):
    """R-CH-33 — the file itself: three answers, and the difference is the feature."""

    def home(self):
        at = self.where / "channels" / "ops"
        at.mkdir(parents=True, exist_ok=True)
        return at

    def test_nothing_written_owes_nobody_and_writes_down_who_is_there(self):
        at = self.home()
        self.assertEqual([], gateway.owed_a_welcome(at, ["2207", "1180"]))
        self.assertEqual(["1180", "2207"],
                         json.loads(gateway.welcomed_path(at).read_text())["welcomed"])

    def test_a_channel_just_added_owes_everybody_it_allows(self):
        at = self.home()
        gateway.remember_no_one_welcomed(at)
        self.assertEqual(["2207", "1180"], gateway.owed_a_welcome(at, ["2207", "1180"]))

    def test_somebody_no_longer_allowed_is_dropped_rather_than_kept(self):
        at = self.home()
        gateway.remember_no_one_welcomed(at)
        gateway.remember_welcomed(at, "2207")
        self.assertEqual(["1180"], gateway.owed_a_welcome(at, ["1180"]))
        self.assertEqual([], json.loads(
            gateway.welcomed_path(at).read_text())["welcomed"])

    def test_somebody_forgotten_by_hand_is_owed_a_greeting_again(self):
        at = self.home()
        gateway.remember_no_one_welcomed(at)
        gateway.remember_welcomed(at, "2207")
        gateway.forget_welcomed(at, ["2207"])
        self.assertEqual(["2207"], gateway.owed_a_welcome(at, ["2207"]))

    def test_forgetting_writes_no_record_where_there_was_none(self):
        """A channel an older release wrote must not be turned into a new one by somebody
        being taken off it."""
        at = self.home()
        gateway.forget_welcomed(at, ["2207"])
        self.assertFalse(gateway.welcomed_path(at).exists())

    def test_writing_down_a_greeting_starts_no_record_of_its_own(self):
        """Same trap from the other side: a greeting delivered on one channel is written
        against every channel of that agent, and a channel from before this existed must
        not become a new one — everybody else on it would then be greeted too."""
        at = self.home()
        gateway.remember_welcomed(at, "2207")
        self.assertFalse(gateway.welcomed_path(at).exists())
        self.assertEqual([], gateway.owed_a_welcome(at, ["2207", "1180"]))


if __name__ == "__main__":
    unittest.main()
