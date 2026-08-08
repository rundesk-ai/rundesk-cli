"""The macOS sleep assertion owned by each live gateway.

The suite never starts the machine's real ``caffeinate``. Its contract is split at the executable:
these cases prove the exact argv, lifetime, failure behavior and host wiring; a scratch runtime check
proves the system program publishes the expected assertion on a Mac.

Run directly: ``python3 tests/test_gateway_awake.py``
"""

import contextlib
import errno
import io
import os
import platform
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import hosting
from rundesk.exits import OK
from rundesk.gateways import awake, host, standing


class Child:
    """A controllable caffeinate process, with only the process methods this contract uses."""

    def __init__(self, code=None, stubborn=False):
        self.code = code
        self.stubborn = stubborn
        self.killed = 0
        self.waited = []

    def poll(self):
        return self.code

    def kill(self):
        self.killed += 1
        if not self.stubborn:
            self.code = -9

    def wait(self, timeout=None):
        self.waited.append(timeout)
        if self.code is None:
            raise subprocess.TimeoutExpired("caffeinate", timeout)
        return self.code


class StopsAfterFirstProof(Child):
    """Alive at acquisition, gone when the live gateway checks it after its first beat."""

    def __init__(self):
        super().__init__()
        self.polled = 0

    def poll(self):
        self.polled += 1
        if self.polled > 1:
            self.code = 9
        return self.code


def published(_guard):
    """The system-boundary answer for cases whose subject is everything around that boundary."""
    return True


class TheAssertionItHolds(unittest.TestCase):
    def test_a_mac_prevents_idle_system_sleep_for_this_process(self):
        child = Child()
        asked = []

        with awake.while_running(
                system="Darwin", starting=lambda argv: asked.append(tuple(argv)) or child,
                proving=published) as guard:
            self.assertIs(child, guard)
            self.assertEqual([(awake.CAFFEINATE, "-i", "-w", str(os.getpid()))], asked)
            self.assertEqual(0, child.killed, "the assertion ended while the gateway was live")

        self.assertEqual(1, child.killed)
        self.assertEqual(-9, child.code)
        self.assertEqual([awake.REAP_WITHIN], child.waited)

    def test_the_display_is_not_forced_to_stay_awake(self):
        asked = []
        with awake.while_running(
                system="Darwin", starting=lambda argv: asked.append(tuple(argv)) or Child(),
                proving=published):
            pass
        self.assertNotIn("-d", asked[0])

    def test_the_real_start_has_no_shell_pipe_or_shared_process_group(self):
        child = Child()
        with mock.patch.object(subprocess, "Popen", return_value=child) as starting:
            self.assertIs(child, awake._started((awake.CAFFEINATE, "-i", "-w", "123")))
        starting.assert_called_once_with(
            [awake.CAFFEINATE, "-i", "-w", "123"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, start_new_session=True)

    def test_other_platforms_start_nothing(self):
        def must_not_start(_argv):
            self.fail("a non-macOS gateway tried to start caffeinate")

        with awake.while_running(system="Linux", starting=must_not_start) as guard:
            self.assertIsNone(guard)
            awake.proved(guard)

    def test_each_gateway_owns_an_independent_assertion(self):
        children = []

        def started(_argv):
            children.append(Child())
            return children[-1]

        with awake.while_running(system="Darwin", starting=started, proving=published):
            with awake.while_running(system="Darwin", starting=started, proving=published):
                self.assertEqual(2, len(children))
                self.assertEqual([0, 0], [one.killed for one in children])
            self.assertEqual([0, 1], [one.killed for one in children])
        self.assertEqual([1, 1], [one.killed for one in children])

    def test_a_helper_that_exited_at_start_establishes_no_assertion(self):
        with self.assertRaisesRegex(awake.NotPreventingSleep, "exited with status 3"):
            with awake.while_running(system="Darwin", starting=lambda _argv: Child(code=3),
                                     proving=published):
                self.fail("a dead helper was accepted")

    def test_a_helper_lost_later_is_a_fault(self):
        child = Child()
        with awake.while_running(system="Darwin", starting=lambda _argv: child,
                                 proving=published) as guard:
            child.code = 9
            with self.assertRaisesRegex(awake.NotPreventingSleep, "exited with status 9"):
                awake.proved(guard)

    def test_a_helper_that_cannot_start_says_which_program_failed(self):
        def failed(_argv):
            raise FileNotFoundError(errno.ENOENT, "not there")

        with self.assertRaisesRegex(awake.NotPreventingSleep,
                                    "/usr/bin/caffeinate did not start:.*not there"):
            with awake.while_running(system="Darwin", starting=failed, proving=published):
                self.fail("a failed start yielded a live assertion")

    def test_a_temporary_process_ceiling_is_a_fault_launchd_may_retry(self):
        def full(_argv):
            raise OSError(errno.EAGAIN, "try again")

        with self.assertRaisesRegex(awake.TryAgain, "/usr/bin/caffeinate did not start"):
            with awake.while_running(system="Darwin", starting=full, proving=published):
                self.fail("a transient start failure yielded a live assertion")

    def test_cleanup_never_hides_the_gateways_own_outcome(self):
        child = Child(stubborn=True)
        with awake.while_running(system="Darwin", starting=lambda _argv: child,
                                 proving=published):
            pass
        self.assertEqual(1, child.killed)
        self.assertEqual([awake.REAP_WITHIN], child.waited)

    def test_it_does_not_yield_until_the_assertion_is_published(self):
        answers = iter((False, False, True))
        asked = []
        with mock.patch.object(awake.time, "sleep") as waited:
            with awake.while_running(system="Darwin", starting=lambda _argv: Child(),
                                     proving=lambda _guard: asked.append(1) or next(answers)):
                self.assertEqual(3, len(asked))
        self.assertEqual(2, waited.call_count)

    def test_an_assertion_that_never_appears_fails_within_a_bound_and_cleans_up(self):
        child = Child()
        with mock.patch.object(awake.time, "monotonic", side_effect=(10.0, 16.0)), \
                mock.patch.object(awake.time, "sleep") as waited, \
                self.assertRaisesRegex(awake.TryAgain, "did not publish.*within 5 seconds"):
            with awake.while_running(system="Darwin", starting=lambda _argv: child,
                                     proving=lambda _guard: False):
                self.fail("an unpublished assertion was allowed to become LIVE")

        waited.assert_not_called()
        self.assertEqual(1, child.killed)
        self.assertEqual([awake.REAP_WITHIN], child.waited)


class TheGatewayOwnsIt(support.Isolated):
    def setUp(self):
        super().setUp()
        self.name = "cole"
        self.at = directory.made(self.name, "claude")

    def test_it_is_established_before_live_and_released_after_serving(self):
        events = []

        @contextlib.contextmanager
        def protected():
            self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)
            events.append("awake")
            try:
                yield None
            finally:
                events.append("released")

        def served(_name, _at, _held, _asked_for, _sleep_prevented):
            self.assertEqual(standing.ONLINE, standing.standing(self.at).how)
            events.append("serving")
            return OK

        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(awake, "while_running", protected), \
                mock.patch.object(host, "_serving", side_effect=served):
            self.assertEqual(OK, host.run(self.name))

        self.assertEqual(["awake", "serving", "released"], events)
        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)

    def test_it_refuses_cleanly_if_the_mac_cannot_be_kept_awake(self):
        @contextlib.contextmanager
        def failed():
            raise awake.NotPreventingSleep("the assertion was refused")
            yield None

        said = io.StringIO()
        with contextlib.redirect_stdout(said), \
                mock.patch.object(awake, "while_running", failed), \
                mock.patch.object(host, "_serving") as served:
            self.assertEqual(OK, host.run(self.name))

        served.assert_not_called()
        self.assertIn("could not keep this Mac awake", said.getvalue())
        self.assertIn("the assertion was refused", said.getvalue())
        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)

    def test_a_temporary_assertion_failure_asks_launchd_to_try_again(self):
        @contextlib.contextmanager
        def retry():
            raise awake.TryAgain("the process ceiling was full")
            yield None

        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(awake, "while_running", retry), \
                mock.patch.object(host, "_serving") as served, \
                self.assertRaisesRegex(awake.TryAgain, "process ceiling"):
            host.run(self.name)

        served.assert_not_called()
        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)

    def test_an_unexpected_assertion_bug_is_not_misreported_as_a_permanent_refusal(self):
        @contextlib.contextmanager
        def broken():
            raise ValueError("the assertion code is broken")
            yield None

        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(awake, "while_running", broken), \
                self.assertRaisesRegex(ValueError, "assertion code is broken"):
            host.run(self.name)

        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)

    def test_losing_the_assertion_in_the_live_loop_is_a_crash(self):
        child = StopsAfterFirstProof()
        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(awake.platform, "system", return_value="Darwin"), \
                mock.patch.object(awake, "_started", return_value=child), \
                mock.patch.object(awake, "_published", side_effect=published), \
                mock.patch.object(host, "_stop_politely"), \
                mock.patch.object(host.time, "sleep"), \
                self.assertRaisesRegex(awake.TryAgain, "exited with status 9"):
            host.run(self.name)

        self.assertGreaterEqual(child.polled, 2, "the assertion was never checked after startup")
        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)

    def test_a_claim_refusal_releases_the_assertion(self):
        events = []

        @contextlib.contextmanager
        def protected():
            events.append("awake")
            try:
                yield None
            finally:
                events.append("released")

        with standing.holding(self.at):
            with contextlib.redirect_stdout(io.StringIO()), \
                    mock.patch.object(awake, "while_running", protected):
                self.assertEqual(OK, host.run(self.name))

        self.assertEqual(["awake", "released"], events)

    def test_a_self_restart_releases_the_old_assertion_before_exec(self):
        events = []

        @contextlib.contextmanager
        def protected():
            events.append("awake")
            try:
                yield None
            finally:
                events.append("released")

        def served(_name, _at, _held, asked_for, _sleep_prevented):
            events.append("serving")
            asked_for.append(hosting.RESTART)
            return host.COME_BACK

        def restarted(_name, _where):
            events.append("exec")

        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(awake, "while_running", protected), \
                mock.patch.object(host, "_serving", side_effect=served), \
                mock.patch.object(host, "_again", side_effect=restarted):
            self.assertEqual(host.COME_BACK, host.run(self.name))

        self.assertEqual(["awake", "serving", "released", "exec"], events)


@unittest.skipUnless(platform.system() == "Darwin" and Path(awake.CAFFEINATE).is_file(),
                     "macOS provides the assertion being proved")
class WhatMacOSActuallyHolds(support.Isolated):
    """One bounded real-system check, rather than one helper in every gateway host case."""

    PATIENCE = 10.0
    PMSET = "/usr/bin/pmset"

    def assertions(self):
        read = subprocess.run([self.PMSET, "-g", "assertions"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              timeout=self.PATIENCE, check=False)
        self.assertEqual(0, read.returncode, read.stderr)
        return read.stdout

    def held(self, pid):
        return any(f"pid {pid}(caffeinate)" in line and "PreventUserIdleSystemSleep" in line
                   for line in self.assertions().splitlines())

    def test_two_gateways_hold_independent_aggregated_assertions(self):
        with awake.while_running() as first:
            self.assertTrue(self.held(first.pid), "the context yielded before macOS held it")
            with awake.while_running() as second:
                self.assertTrue(self.held(second.pid), "the context yielded before macOS held it")
            self.assertTrue(support.waited_until(lambda: not self.held(second.pid), self.PATIENCE))
            self.assertTrue(self.held(first.pid), "stopping one gateway dropped the other's guard")
        self.assertTrue(support.waited_until(lambda: not self.held(first.pid), self.PATIENCE))

    def test_waiting_on_the_pid_releases_after_an_owner_is_killed(self):
        owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        self.addCleanup(self.stopped, owner)
        guard = awake._started((awake.CAFFEINATE, "-i", "-w", str(owner.pid)))
        # This test owns both wrappers. Cleanup may act on them without ever consulting a recorded
        # pid that could have been reused by an unrelated process.
        self.addCleanup(self.stopped, guard)
        self.assertTrue(support.waited_until(lambda: awake._published(guard), self.PATIENCE))

        os.kill(owner.pid, signal.SIGKILL)
        owner.wait(timeout=self.PATIENCE)

        self.assertTrue(support.waited_until(lambda: guard.poll() is not None, self.PATIENCE),
                        "caffeinate outlived the process its -w argument named")
        self.assertFalse(self.held(guard.pid), "the killed gateway's assertion remained active")

    def stopped(self, child):
        if child.poll() is None:
            child.kill()
            child.wait(timeout=self.PATIENCE)


if __name__ == "__main__":
    unittest.main()
