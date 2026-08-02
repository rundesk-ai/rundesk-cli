#!/usr/bin/env python3
"""The update worker: which gateways it may take down, and what it puts back.

Kept apart from `test_cli.py` deliberately. These cases drive the machine-wide stand-down
and the recovery a successor worker performs — the highest-consequence path in the product
— and they reach it directly rather than through `cli.main`, so nothing here depends on the
command surface's fixture, on an argparse grammar, or on which verb happens to call it.

Every collaborator is a stand-in written here: no gateway is started, no supervisor is
asked, and nothing outside a temporary directory is touched.

Run: python3 tests/test_update_worker.py
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import standing  # noqa: E402
from rundesk import update_request  # noqa: E402
from rundesk import update_worker  # noqa: E402


class Agents:
    """The agent module, as far as the update worker is concerned.

    It asks three things and never writes: which agents there are, where one keeps what it
    is running, and — for the origin of a request — what a run recorded. A gateway's run
    directory is the only one of those the stand-down path actually reads.
    """

    def known(self):
        return []

    def resolved(self, name):
        return type("Where", (), {"run": None})()

    def reading(self, name):
        raise AssertionError("the stand-down path does not read an agent's records")


class WhatEveryGatewayIsWorkingOn(unittest.TestCase):
    """R-UPD-23 — what the worker must wait for before it replaces anything."""

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

            def what_is_working(self, name, where=None):
                return {"alpha": ["turn-1", "turn-2"], "beta": ["turn-3"],
                        "gamma": ["stale"]}[name]

            def what_is_turning(self, name, where=None):
                return []

        self.assertEqual(
            ["alpha/turn-1", "alpha/turn-2", "beta/turn-3"],
            update_worker._in_flight(Gateways(), Agents()),
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

        self.assertEqual([], update_worker._in_flight(Gateways(), Agents()))


class StoppingWhatAnUpdateWouldReplace(unittest.TestCase):
    """R-UPD-21, R-UPD-22 — which gateways an update may take down, and which it may not."""

    class Standing:
        def __init__(self, name, running=True, pid=1, version="0.1.0"):
            self.name, self.running, self.pid, self.version = name, running, pid, version

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run_home = pathlib.Path(self.temporary.name)

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

            def described(self, root=None):
                return []

            def stop(self, name, root=None):
                Machine.asked.append(("stop", name))
                Machine.roots.append(("stop", name, root))
                return type("Spoke", (), {"ok": stops})()

            def start(self, name, root=None):
                Machine.asked.append(("start", name))
                Machine.roots.append(("start", name, root))
                return type("Spoke", (), {"ok": True})()

        Machine.asked = []
        Machine.roots = []
        return Machine()

    def _gateways(self, standing, gone_after_stop=True, comes_up=True, working=()):
        outer = self
        #: How many times each has been asked after. The first answer is what it was doing
        #: before anything was asked of it, and the ones after are whether it has gone —
        #: the same gateway, asked twice, which is what the real one does.
        asked = {}

        class Gateways:
            def home(self):
                return outer.run_home

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

            def what_is_working(self, name, where=None):
                return {one: {"pgid": 1} for one in working}

            def what_is_turning(self, name, where=None):
                return []

            def fitness(self, root=None):
                return None
        return Gateways()

    def test_an_update_stops_every_supervised_gateway_that_is_running(self):
        """R-UPD-21"""
        up = [self.Standing("alpha"), self.Standing("beta"), self.Standing("idle", running=False)]
        machine = self._machine(loaded=("alpha", "beta"))
        stopped, refused = update_worker._stand_all_down(self._gateways(up), machine, Agents())
        self.assertIsNone(refused)
        self.assertEqual(["alpha", "beta"], stopped)
        self.assertEqual([("stop", "alpha"), ("stop", "beta")], machine.asked,
                         "it stopped a gateway that was not running")

    def test_an_update_marks_maintenance_until_the_gateway_is_back(self):
        """R-UPD-43"""
        machine = self._machine(loaded=("alpha",))
        agents = Agents()
        stopped, refused = update_worker._stand_all_down(
            self._gateways([self.Standing("alpha")]), machine, agents
        )
        self.assertEqual((["alpha"], None), (stopped, refused))
        self.assertTrue(
            update_request.maintaining("alpha", self.run_home),
            "the shutdown looked like an unexplained outage",
        )

        update_worker._bring_all_back(
            ["alpha"], self._gateways([self.Standing("alpha")]), machine, agents
        )
        self.assertTrue(
            update_request.maintaining("alpha", self.run_home),
            "the returning channel lost the marker before it could report completion",
        )

    def test_a_gateway_the_update_could_not_stop_is_not_left_in_maintenance(self):
        """R-UPD-43"""
        machine = self._machine(loaded=("alpha",), stops=False)
        update_worker._stand_all_down(
            self._gateways([self.Standing("alpha")]), machine, Agents()
        )
        self.assertFalse(update_request.maintaining("alpha", self.run_home))

    def test_a_successor_worker_restores_only_a_gateway_marked_for_maintenance(self):
        """R-UPD-44"""
        outer = self

        class Gateways:
            asked = 0

            def home(self):
                return outer.run_home

            def every(self):
                return []

            def remembered(self):
                return []

            def fitness(self, root=None):
                return None

            def standing(self, name, where=None):
                self.asked += 1
                return outer.Standing(name, running=self.asked > 1)

        machine = self._machine(loaded=("alpha", "deliberately-stopped"))
        machine.described = lambda root=None: ["alpha", "deliberately-stopped"]
        update_request.begin_maintenance("alpha", self.run_home)

        self.assertEqual(
            [], update_worker._recover_update_gateways(Gateways(), machine, Agents())
        )
        self.assertIn(("start", "alpha"), machine.asked)
        self.assertNotIn(("start", "deliberately-stopped"), machine.asked)
        self.assertTrue(update_request.maintaining("alpha", self.run_home))

    def test_a_successor_worker_never_starts_a_gateway_on_an_unfit_release(self):
        """R-UPD-44"""
        gateways = self._gateways([self.Standing("alpha", running=False)])
        gateways.fitness = lambda root=None: "dependencies are incomplete"
        machine = self._machine(loaded=("alpha",))
        machine.described = lambda root=None: ["alpha"]
        update_request.begin_maintenance("alpha", self.run_home)

        self.assertEqual(
            ["alpha"],
            update_worker._recover_update_gateways(gateways, machine, Agents()),
        )
        self.assertNotIn(("start", "alpha"), machine.asked)

    def test_an_external_update_acts_on_jobs_owned_by_the_target_install(self):
        """R-UPD-21 — the worker runs from the release checkout while the supervised
        jobs belong to the older install it is replacing."""
        target = Path("/target-install")
        machine = self._machine(loaded=("alpha",))
        stopped, refused = update_worker._stand_all_down(
            self._gateways([self.Standing("alpha")]), machine, Agents(), target
        )
        self.assertEqual((["alpha"], None), (stopped, refused))
        self.assertEqual([("stop", "alpha", target)], machine.roots)

        update_worker._bring_all_back(
            ["alpha"], self._gateways([self.Standing("alpha")]),
            machine, Agents(), target,
        )
        self.assertIn(("start", "alpha", target), machine.roots)

    def test_an_update_refuses_rather_than_taking_down_what_it_cannot_start_again(self):
        """R-UPD-21 — launchctl has no handle on a process it never started, and nothing
        records the terminal a hand-started gateway came from."""
        machine = self._machine(loaded=())     # running, but the machine holds no job
        stopped, refused = update_worker._stand_all_down(self._gateways([self.Standing("scratch", pid=8812)]), machine, Agents())
        self.assertEqual([], stopped)
        self.assertIn("unsupervised", refused)
        self.assertIn("rundesk start scratch", refused)
        self.assertEqual([], machine.asked, "it tried to stop one it could not start again")

    def test_an_update_on_a_machine_with_no_supervisor_stops_nothing(self):
        """R-UPD-21 — nothing to hand a gateway to means nothing to take one from."""
        stopped, refused = update_worker._stand_all_down(self._gateways([self.Standing("alpha")]), self._machine(available=False), Agents())
        self.assertEqual(([], None), (stopped, refused))

    def test_a_gateway_that_will_not_stop_leaves_the_install_untouched(self):
        """R-UPD-21 — replacing files under something that refused to go is the failure
        this whole sequence exists to avoid."""
        machine = self._machine(loaded=("alpha",), stops=False)
        stopped, refused = update_worker._stand_all_down(self._gateways([self.Standing("alpha")]), machine, Agents())
        self.assertEqual([], stopped)
        self.assertIn("would not stop", refused)

    def test_work_begun_while_the_update_was_starting_is_not_taken_down(self):
        """R-UPD-23 — what is in flight is asked once, before any of this. A turn that
        began between that answer and this moment would be killed by the very stop that
        exists to protect it, so it is asked again with nothing left in between."""
        machine = self._machine(loaded=("alpha",))
        stopped, refused = update_worker._stand_all_down(self._gateways([self.Standing("alpha")], working=("a-turn",)), machine, Agents())
        self.assertEqual([], stopped)
        self.assertIn("began work", refused)
        self.assertEqual([], machine.asked, "it stopped a gateway that had just taken work")

    def test_a_connected_channel_adapter_does_not_block_an_idle_update(self):
        """R-UPD-39"""
        machine = self._machine(loaded=("alpha",))
        stopped, refused = update_worker._stand_all_down(
            self._gateways(
                [self.Standing("alpha")], working=("channel:discord-dms",)
            ),
            machine, Agents(),
        )
        self.assertIsNone(refused)
        self.assertEqual(["alpha"], stopped)

    def test_a_gateway_that_does_not_come_back_is_reported_rather_than_passed_over(self):
        """R-UPD-22 — a release needing something this install does not have starts a
        gateway that ends *well* so as not to be restarted forever, and the machine calls
        that a job accepted. Only asking the gateway itself catches it."""
        self.addCleanup(setattr, standing, "START_PATIENCE", standing.START_PATIENCE)
        standing.START_PATIENCE = 0.1
        machine = self._machine(loaded=("alpha",))
        never = self._gateways([self.Standing("alpha", running=False)], gone_after_stop=False)
        self.assertEqual(["alpha"], update_worker._bring_all_back(["alpha"], never, machine, Agents()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
