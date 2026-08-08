"""The daily coordinator: isolated identity, reconciliation, and safe admission."""

import datetime
import plistlib
import threading
from unittest import mock

import support
from rundesk.commands import automatic_updates, update
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job
from rundesk.providers import turns
from rundesk.utils import locking

ASupervisor = support.ASupervisor
Isolated = support.Isolated
ran = support.ran
waited_until = support.waited_until


class AutomaticUpdates(Isolated):
    def setUp(self) -> None:
        super().setUp()
        config.write_fresh(paths.data())
        paths.app().mkdir(parents=True)
        self.into = self.home / "LaunchAgents"

    def test_job_is_root_specific_and_uses_a_local_calendar(self) -> None:
        one = automatic_updates.coordinator(into=self.into)
        other = automatic_updates.coordinator(self.home / "other", self.into)
        document = automatic_updates.document(one, "03:17")

        self.assertNotEqual(one.label, other.label)
        self.assertEqual(document["StartCalendarInterval"], {"Hour": 3, "Minute": 17})
        self.assertNotIn("RunAtLoad", document)
        self.assertNotIn("KeepAlive", document)
        self.assertEqual(document["EnvironmentVariables"][paths.HOME_IS], str(self.home))
        self.assertNotIn("SECRET", repr(document))

    def test_enabled_job_is_placed_once_and_files_are_private(self) -> None:
        supervisor = ASupervisor()
        first = automatic_updates.reconcile(supervisor, self.into)
        supervisor.answers["print"] = ran(0)
        second = automatic_updates.reconcile(supervisor, self.into)
        one = automatic_updates.coordinator(into=self.into)

        self.assertEqual((first.how, second.how), (job.PLACED, job.PLACED))
        self.assertEqual(supervisor.verbs().count("bootstrap"), 1)
        self.assertEqual(automatic_updates.plist_of(one).stat().st_mode & 0o777, 0o600)
        self.assertEqual(automatic_updates.shim_of(one).stat().st_mode & 0o777, 0o700)
        self.assertEqual(plistlib.loads(automatic_updates.plist_of(one).read_bytes())["Label"],
                         one.label)

    def test_time_change_replaces_the_loaded_definition(self) -> None:
        supervisor = ASupervisor()
        automatic_updates.reconcile(supervisor, self.into)
        config.stated_all({"update_time": "08:45"}, paths.data())
        automatic_updates.reconcile(supervisor, self.into)
        one = automatic_updates.coordinator(into=self.into)

        document = plistlib.loads(automatic_updates.plist_of(one).read_bytes())
        self.assertEqual(document["StartCalendarInterval"], {"Hour": 8, "Minute": 45})
        self.assertEqual(supervisor.verbs().count("bootstrap"), 2)

    def test_failed_bootstrap_is_retried_even_when_files_already_match(self) -> None:
        supervisor = ASupervisor(bootstrap=ran(5))
        first = automatic_updates.reconcile(supervisor, self.into)
        supervisor.answers["bootstrap"] = ran(0)
        second = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(first.how, job.CANNOT_TELL)
        self.assertEqual(second.how, job.PLACED)
        self.assertEqual(supervisor.verbs().count("bootstrap"), 2)
        self.assertTrue(automatic_updates.receipt_at(
            automatic_updates.coordinator(into=self.into)).is_file())

    def test_disable_takes_back_and_removes_both_files_idempotently(self) -> None:
        supervisor = ASupervisor()
        automatic_updates.reconcile(supervisor, self.into)
        config.stated_all({"update_enabled": False}, paths.data())
        first = automatic_updates.reconcile(supervisor, self.into)
        second = automatic_updates.reconcile(supervisor, self.into)
        one = automatic_updates.coordinator(into=self.into)

        self.assertEqual((first.how, second.how), (job.NOT_PLACED, job.NOT_PLACED))
        self.assertFalse(automatic_updates.plist_of(one).exists())
        self.assertFalse(automatic_updates.shim_of(one).exists())

    def test_one_successful_attempt_per_local_day(self) -> None:
        called = mock.Mock(return_value=OK)
        now = datetime.datetime(2026, 11, 1, 1, 30).astimezone()
        with mock.patch("rundesk.commands.update.cmd_update", called), \
                mock.patch.object(automatic_updates, "_busy_reason", return_value=""):
            first = automatic_updates.run(now)
            second = automatic_updates.run(now.replace(fold=1))

        self.assertEqual((first, second), (OK, OK))
        called.assert_called_once()
        self.assertEqual(automatic_updates._completed(automatic_updates.coordinator()), "2026-11-01")

    def test_busy_install_defers_without_invoking_the_updater(self) -> None:
        called = mock.Mock(return_value=OK)
        with mock.patch("rundesk.commands.update.cmd_update", called), \
                mock.patch.object(automatic_updates, "_busy_reason",
                                  return_value="piper has an active provider turn"):
            result = automatic_updates.run(datetime.datetime(2026, 8, 8, 3, 0).astimezone())

        self.assertEqual(result, OK)
        called.assert_not_called()
        state = automatic_updates.state_at(automatic_updates.coordinator()).read_text()
        self.assertIn('"outcome": "DEFERRED"', state)

    def test_failed_update_is_not_reported_as_success(self) -> None:
        with mock.patch("rundesk.commands.update.cmd_update", return_value=FAILED), \
                mock.patch.object(automatic_updates, "_busy_reason", return_value=""):
            result = automatic_updates.run(datetime.datetime(2026, 8, 8, 3, 0).astimezone())
        self.assertEqual(result, FAILED)
        self.assertIn('"outcome": "FAILED"',
                      automatic_updates.state_at(automatic_updates.coordinator()).read_text())

    def test_admission_barrier_closes_the_busy_check_start_gap(self) -> None:
        entered = threading.Event()
        released = threading.Event()

        def start_turn() -> None:
            with turns.claiming("piper", 1):
                entered.set()
            released.set()

        with locking.only_one(paths.work_admission_lock(), guarding="test race"):
            thread = threading.Thread(target=start_turn)
            thread.start()
            self.assertFalse(waited_until(entered.is_set, 0.1))
        self.assertTrue(waited_until(entered.is_set, 1.0))
        self.assertTrue(waited_until(released.is_set, 1.0))
        thread.join()


class CommandWiring(Isolated):
    def setUp(self) -> None:
        super().setUp()
        config.write_fresh(paths.data())
        paths.app().mkdir(parents=True)

    def test_configure_reconciles_a_changed_update_time(self) -> None:
        supervisor = ASupervisor()
        code, out, err = support.run_with(
            ["configure", "--update-time", "07:25"], supervising=supervisor)
        one = automatic_updates.coordinator(into=self.home / "LaunchAgents")

        self.assertEqual(OK, code, err)
        self.assertIn("update_time is now 07:25", out)
        self.assertIn("bootstrap", supervisor.verbs())
        self.assertEqual(
            {"Hour": 7, "Minute": 25},
            plistlib.loads(automatic_updates.plist_of(one).read_bytes())[
                "StartCalendarInterval"])

    def test_status_reports_the_reconciled_schedule(self) -> None:
        supervisor = ASupervisor()
        code, _, err = support.run_with(
            ["configure", "--update-time", "06:40"], supervising=supervisor)
        self.assertEqual(OK, code, err)
        supervisor.answers["print"] = ran(0)

        code, out, err = support.run_with(["status"], supervising=supervisor)

        self.assertEqual(OK, code, err)
        self.assertIn("automatic update", out)
        self.assertIn("scheduled daily at 06:40 local time", out)

    def test_checkout_status_does_not_ask_the_host_supervisor(self) -> None:
        paths.app().rmdir()
        supervisor = ASupervisor()

        answer = automatic_updates.status(
            supervisor, into=self.home / "LaunchAgents")

        self.assertEqual("not scheduled — this root is running from a checkout", answer)
        self.assertEqual([], supervisor.asked)

    def test_update_settlement_fails_when_reconciliation_does_not_finish(self) -> None:
        outcome = automatic_updates.Reconciled(job.CANNOT_TELL, "launchd stayed unavailable")
        with mock.patch.object(automatic_updates, "reconcile", return_value=outcome) as reconciled:
            code = update.settle()

        self.assertEqual(FAILED, code)
        reconciled.assert_called_once_with()

    def test_uninstall_takes_back_a_loaded_job_even_when_both_artifacts_are_missing(self) -> None:
        supervisor = ASupervisor(print=ran(0), bootout=ran(0))
        one = automatic_updates.coordinator(into=self.home / "LaunchAgents")
        self.assertFalse(automatic_updates.plist_of(one).exists())
        self.assertFalse(automatic_updates.shim_of(one).exists())

        code, out, err = support.run_with(
            ["uninstall", "--confirm", "--purge"], supervising=supervisor)

        self.assertEqual(OK, code, err)
        self.assertIn("rundesk removed", out)
        self.assertIn(("bootout", one.label), supervisor.asked)
        self.assertFalse(paths.app().exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
