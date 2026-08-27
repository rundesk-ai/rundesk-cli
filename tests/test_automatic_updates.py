"""The daily coordinator: isolated identity, reconciliation, and safe admission."""

import datetime
import json
import os
import plistlib
import sys
import threading
from unittest import mock

import support
from rundesk.commands import automatic_updates, update
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job
from rundesk.providers import turns
from rundesk.utils import locking, programs

HOLD_LOCK = (
    "import fcntl,sys,time;"
    "f=open(sys.argv[1],'a');fcntl.flock(f,fcntl.LOCK_EX);time.sleep(30)"
)

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

    def a_queue_worker_holding_its_claim(self) -> int:
        at = automatic_updates.queue_lock_at(automatic_updates.coordinator())
        pid = programs.start(
            [sys.executable, "-c", HOLD_LOCK, str(at)], self.home / "queue-holder.log")
        self.addCleanup(lambda: programs.stop(pid, gently_for=0.1, firmly_for=1.0))
        self.assertTrue(waited_until(lambda: locking.is_held(at) is True, 2.0))
        return pid

    def write_coordinator(self, one: automatic_updates.Coordinator, *, aged: bool = False) -> None:
        one.into.mkdir(parents=True, exist_ok=True)
        definition = automatic_updates.plist_of(one)
        definition.write_bytes(
            plistlib.dumps(automatic_updates.document(one, "03:00")))
        if aged:
            old = automatic_updates.time.time() - automatic_updates.ORPHAN_GRACE_SECONDS - 1
            os.utime(definition, (old, old))

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

    def test_job_definition_does_not_depend_on_the_callers_path(self) -> None:
        supervisor = ASupervisor()
        with mock.patch.dict(os.environ, {"PATH": "/tmp/first"}):
            automatic_updates.reconcile(supervisor, self.into)
        supervisor.answers["print"] = ran(0)
        with mock.patch.dict(os.environ, {"PATH": "/tmp/second"}):
            answer = automatic_updates.status(supervisor, self.into)

        one = automatic_updates.coordinator(into=self.into)
        placed = plistlib.loads(automatic_updates.plist_of(one).read_bytes())
        self.assertEqual("scheduled daily at 03:00 local time", answer)
        self.assertEqual(":".join(job.LAUNCHD_PATH),
                         placed["EnvironmentVariables"]["PATH"])

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

    def test_reconciliation_removes_a_coordinator_whose_install_vanished(self) -> None:
        orphan = automatic_updates.coordinator(self.home / "vanished", self.into)
        self.write_coordinator(orphan, aged=True)
        supervisor = ASupervisor()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertFalse(automatic_updates.plist_of(orphan).exists())
        self.assertIn(("bootout", orphan.label), supervisor.asked)

    def test_reconciliation_preserves_another_functioning_install(self) -> None:
        other = automatic_updates.coordinator(self.home / "other", self.into)
        self.write_coordinator(other)
        automatic_updates.shim_of(other).parent.mkdir(parents=True)
        automatic_updates.shim_of(other).write_text("still installed\n")
        supervisor = ASupervisor()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertTrue(automatic_updates.plist_of(other).exists())
        self.assertNotIn(("bootout", other.label), supervisor.asked)

    def test_reconciliation_preserves_a_recently_absent_install(self) -> None:
        other = automatic_updates.coordinator(self.home / "recently-absent", self.into)
        self.write_coordinator(other)
        supervisor = ASupervisor()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertTrue(automatic_updates.plist_of(other).exists())
        self.assertNotIn(("bootout", other.label), supervisor.asked)

    def test_reconciliation_preserves_an_unavailable_parent(self) -> None:
        unavailable = self.home / "unavailable" / "install"
        other = automatic_updates.coordinator(unavailable, self.into)
        self.write_coordinator(other, aged=True)
        supervisor = ASupervisor()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertTrue(automatic_updates.plist_of(other).exists())
        self.assertNotIn(("bootout", other.label), supervisor.asked)

    def test_reconciliation_serializes_a_secondary_reinstall(self) -> None:
        other = automatic_updates.coordinator(self.home / "returning", self.into)
        self.write_coordinator(other, aged=True)
        supervisor = ASupervisor()
        attempted = threading.Event()
        answers = []
        taking = locking._taken

        def reconcile() -> None:
            answers.append(automatic_updates.reconcile(supervisor, self.into))

        def observed_take(*args, **kwargs):
            attempted.set()
            return taking(*args, **kwargs)

        current = automatic_updates.coordinator(into=self.into)
        with locking.only_one(automatic_updates.reconciliation_lock_at(current)):
            with mock.patch.object(locking, "_taken", side_effect=observed_take):
                worker = threading.Thread(target=reconcile)
                worker.start()
                self.assertTrue(attempted.wait(1.0))
                automatic_updates.shim_of(other).parent.mkdir(parents=True)
                automatic_updates.shim_of(other).write_text("installed again\n")
        worker.join(2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(job.PLACED, answers[0].how, answers[0].why)
        self.assertTrue(automatic_updates.plist_of(other).exists())
        self.assertNotIn(("bootout", other.label), supervisor.asked)

    def test_reconciliation_restores_a_secondary_reinstalled_by_an_older_release(self) -> None:
        other = automatic_updates.coordinator(self.home / "returning", self.into)
        self.write_coordinator(other, aged=True)
        case = self

        class OlderInstaller(ASupervisor):
            def take_back(self, label):
                automatic_updates.shim_of(other).parent.mkdir(parents=True, exist_ok=True)
                automatic_updates.shim_of(other).write_text("installed by an older release\n")
                case.write_coordinator(other)
                return super().take_back(label)

        supervisor = OlderInstaller()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertTrue(automatic_updates.plist_of(other).exists())
        self.assertTrue(automatic_updates.shim_of(other).exists())
        self.assertIn(("bootstrap", str(automatic_updates.plist_of(other))), supervisor.asked)
        self.assertFalse(automatic_updates._claim_of(
            automatic_updates.plist_of(other)).exists())

    def test_reconciliation_recovers_an_interrupted_orphan_claim(self) -> None:
        orphan = automatic_updates.coordinator(self.home / "vanished", self.into)
        self.write_coordinator(orphan, aged=True)
        claim = automatic_updates._claim_of(automatic_updates.plist_of(orphan))
        automatic_updates.plist_of(orphan).rename(claim)
        supervisor = ASupervisor()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertFalse(automatic_updates.plist_of(orphan).exists())
        self.assertFalse(claim.exists())
        self.assertIn(("bootout", orphan.label), supervisor.asked)

    def test_reconciliation_restores_a_root_returning_during_take_back(self) -> None:
        other = automatic_updates.coordinator(self.home / "returning", self.into)
        self.write_coordinator(other, aged=True)

        class ReturningRoot(ASupervisor):
            def take_back(self, label):
                automatic_updates.shim_of(other).parent.mkdir(parents=True, exist_ok=True)
                automatic_updates.shim_of(other).write_text("installed again\n")
                return super().take_back(label)

        supervisor = ReturningRoot()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertTrue(automatic_updates.plist_of(other).exists())
        self.assertIn(("bootstrap", str(automatic_updates.plist_of(other))), supervisor.asked)
        self.assertFalse(automatic_updates._claim_of(
            automatic_updates.plist_of(other)).exists())

    def test_reconciliation_recovers_a_claimed_functioning_install(self) -> None:
        other = automatic_updates.coordinator(self.home / "installed", self.into)
        self.write_coordinator(other)
        automatic_updates.shim_of(other).parent.mkdir(parents=True, exist_ok=True)
        automatic_updates.shim_of(other).write_text("installed\n")
        claim = automatic_updates._claim_of(automatic_updates.plist_of(other))
        automatic_updates.plist_of(other).rename(claim)
        supervisor = ASupervisor()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertTrue(automatic_updates.plist_of(other).exists())
        self.assertFalse(claim.exists())
        self.assertNotIn(("bootout", other.label), supervisor.asked)

    def test_reconciliation_preserves_an_identity_mismatched_definition(self) -> None:
        other = automatic_updates.coordinator(self.home / "gone", self.into)
        document = automatic_updates.document(other, "03:00")
        document["ProgramArguments"] = [str(self.home / "not-the-recorded-root" / "missing")]
        other.into.mkdir(parents=True, exist_ok=True)
        automatic_updates.plist_of(other).write_bytes(plistlib.dumps(document))
        supervisor = ASupervisor()

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.PLACED, answer.how, answer.why)
        self.assertTrue(automatic_updates.plist_of(other).exists())
        self.assertNotIn(("bootout", other.label), supervisor.asked)

    def test_reconciliation_reports_an_orphan_it_cannot_take_back(self) -> None:
        orphan = automatic_updates.coordinator(self.home / "vanished", self.into)
        self.write_coordinator(orphan, aged=True)
        supervisor = ASupervisor(bootout=ran(5, err="launchd refused"))

        answer = automatic_updates.reconcile(supervisor, self.into)

        self.assertEqual(job.CANNOT_TELL, answer.how)
        self.assertIn("take back orphaned automatic update", answer.why)
        self.assertTrue(automatic_updates.plist_of(orphan).exists())

    def test_embedded_removal_releases_its_reconciliation_lock(self) -> None:
        supervisor = ASupervisor()
        automatic_updates.reconcile(supervisor, self.into)

        answer = automatic_updates.remove(supervisor, self.into)

        self.assertEqual("", answer)
        self.assertFalse(self.into.exists())

    def test_embedded_removal_never_splits_the_lock_between_waiters(self) -> None:
        current = automatic_updates.coordinator(into=self.into)
        at = automatic_updates.reconciliation_lock_at(current)
        waiter_has_it = threading.Event()
        release_waiter = threading.Event()

        def wait_for_lock() -> None:
            with locking.only_one(at):
                waiter_has_it.set()
                release_waiter.wait(2.0)

        with locking.only_one(at):
            waiter = threading.Thread(target=wait_for_lock)
            waiter.start()
        self.assertTrue(waiter_has_it.wait(1.0))
        self.into.mkdir(parents=True)
        self.into.rmdir()

        with self.assertRaises(locking.Stuck):
            with locking.only_one(at, waiting=0):
                pass

        release_waiter.set()
        waiter.join(2.0)
        self.assertFalse(waiter.is_alive())

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
        called = mock.Mock(return_value=update.Attempt(OK, False))
        now = datetime.datetime(2026, 11, 1, 1, 30).astimezone()
        with mock.patch("rundesk.commands.update.attempt_update", called), \
                mock.patch.object(automatic_updates, "_busy_reason", return_value=""):
            first = automatic_updates.run(now)
            second = automatic_updates.run(now.replace(fold=1))

        self.assertEqual((first, second), (OK, OK))
        called.assert_called_once()
        self.assertEqual(automatic_updates._completed(automatic_updates.coordinator()), "2026-11-01")

    def test_busy_install_queues_after_releasing_the_daily_claim(self) -> None:
        called = mock.Mock(return_value=update.Attempt(OK, False))
        started = []

        def start(one):
            started.append((automatic_updates.request_at(one).is_file(),
                            locking.is_held(automatic_updates.queue_lock_at(one))))
            return 41

        with mock.patch("rundesk.commands.update.attempt_update", called), \
                mock.patch.object(automatic_updates, "_busy_reason",
                                  return_value="piper has an active provider turn"), \
                mock.patch.object(automatic_updates, "_start_queued_runner", side_effect=start):
            result = automatic_updates.run(datetime.datetime(2026, 8, 8, 3, 0).astimezone())

        self.assertEqual(result, OK)
        called.assert_not_called()
        self.assertEqual([(True, False)], started,
                         "the worker started before the daily coordinator released its claim")
        request = json.loads(automatic_updates.request_at(
            automatic_updates.coordinator()).read_text())
        self.assertEqual("piper has an active provider turn", request["reason"])
        state = automatic_updates.state_at(automatic_updates.coordinator()).read_text()
        self.assertIn('"outcome": "DEFERRED"', state)

    def test_a_busy_daily_attempt_does_not_replace_an_existing_manual_request(self) -> None:
        automatic_updates.queued("manual request", starting=lambda _one: 41, environ={})
        one = automatic_updates.coordinator()
        before = automatic_updates.request_at(one).stat()
        with mock.patch.object(automatic_updates, "_busy_reason", return_value="busy"), \
                mock.patch.object(automatic_updates, "_start_queued_runner", return_value=42):
            result = automatic_updates.run(
                datetime.datetime(2026, 8, 8, 3, 0).astimezone())

        after = automatic_updates.request_at(one).stat()
        request = json.loads(automatic_updates.request_at(one).read_text())
        self.assertEqual(OK, result)
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
        self.assertEqual("manual request", request["reason"])

    def test_a_daily_queue_start_failure_keeps_the_request_and_reports_failure(self) -> None:
        with mock.patch.object(automatic_updates, "_busy_reason", return_value="busy"), \
                mock.patch.object(automatic_updates, "_start_queued_runner",
                                  side_effect=OSError("could not spawn")):
            result = automatic_updates.run(
                datetime.datetime(2026, 8, 8, 3, 0).astimezone())

        one = automatic_updates.coordinator()
        self.assertEqual(FAILED, result)
        self.assertTrue(automatic_updates.request_at(one).is_file())
        self.assertIn('"outcome": "FAILED"', automatic_updates.state_at(one).read_text())

    def test_failed_update_is_not_reported_as_success(self) -> None:
        with mock.patch("rundesk.commands.update.attempt_update",
                        return_value=update.Attempt(FAILED, False)), \
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

    def test_manual_update_is_queued_durably_when_any_provider_turn_is_active(self) -> None:
        queueing = mock.Mock(return_value="update queued until current work finishes — busy")
        asking = mock.Mock()
        gateways = mock.Mock()
        fetching = mock.Mock()
        with mock.patch.object(automatic_updates, "_busy_reason",
                               return_value="winston has an active provider turn"), \
                mock.patch.object(automatic_updates, "queued", queueing):
            code = update.cmd_update(
                mock.Mock(), asking=asking, gateways=gateways, fetching=fetching)

        self.assertEqual(OK, code)
        queueing.assert_called_once_with("winston has an active provider turn")
        asking.assert_not_called()
        self.assertFalse(gateways.method_calls)
        fetching.assert_not_called()

    def test_an_update_waiting_behind_uninstall_cannot_put_the_removed_app_back(self) -> None:
        app = mock.Mock()
        app.is_dir.side_effect = [True, False]
        asking = mock.Mock()
        fetching = mock.Mock()
        with mock.patch.object(paths, "app", return_value=app):
            attempt = update.attempt_update(
                mock.Mock(), asking=asking, fetching=fetching, gateways=mock.Mock())

        self.assertEqual(update.Attempt(FAILED, False), attempt)
        asking.assert_not_called()
        fetching.assert_not_called()

    def test_queue_is_written_before_its_detached_runner_starts(self) -> None:
        seen = []

        def starting(one):
            seen.append(automatic_updates.request_at(one).is_file())
            return 41

        said = automatic_updates.queued(
            "winston has an active provider turn", starting=starting,
            environ={"RUNDESK_AGENT": "winston", "RUNDESK_RUN": "46"})
        one = automatic_updates.coordinator()
        request = json.loads(automatic_updates.request_at(one).read_text())

        self.assertEqual([True], seen)
        self.assertIn("queued until current work finishes", said)
        self.assertEqual(("winston", 46), (request["agent"], request["turn"]))
        self.assertEqual(0o600, automatic_updates.request_at(one).stat().st_mode & 0o777)

    def test_queued_runner_waits_for_quiet_then_updates_once_and_clears_the_request(self) -> None:
        automatic_updates.queued("busy", starting=lambda _one: 41, environ={})
        updating = mock.Mock(return_value=update.Attempt(OK, False))
        with mock.patch.object(automatic_updates, "_busy_reason",
                               side_effect=["busy", "", ""]), \
                mock.patch("rundesk.commands.update.attempt_update", updating):
            result = automatic_updates.run_queued(sleeping=lambda _seconds: None)

        self.assertEqual(OK, result)
        updating.assert_called_once()
        self.assertFalse(automatic_updates.request_at(automatic_updates.coordinator()).exists())

    def test_queued_runner_retries_a_failed_attempt_until_the_request_succeeds(self) -> None:
        automatic_updates.queued("busy", starting=lambda _one: 41, environ={})
        updating = mock.Mock(side_effect=[update.Attempt(FAILED, False),
                                         update.Attempt(OK, False)])
        slept = []
        with mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch("rundesk.commands.update.attempt_update", updating):
            result = automatic_updates.run_queued(sleeping=slept.append)

        self.assertEqual(OK, result)
        self.assertEqual(2, updating.call_count)
        self.assertTrue(slept, "a failed update was retried without any hold-off")
        self.assertFalse(automatic_updates.request_at(automatic_updates.coordinator()).exists())

    def test_queued_runner_never_deletes_a_newer_request_created_while_it_settles(self) -> None:
        automatic_updates.queued("earlier", starting=lambda _one: 41, environ={})

        def succeeded_after_a_new_request(_args):
            automatic_updates.queued("newer", starting=lambda _one: 42, environ={})
            return update.Attempt(OK, False)

        with mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch("rundesk.commands.update.attempt_update",
                           side_effect=succeeded_after_a_new_request):
            result = automatic_updates.run_queued(sleeping=lambda _seconds: None)

        self.assertEqual(OK, result)
        request = json.loads(automatic_updates.request_at(
            automatic_updates.coordinator()).read_text())
        self.assertEqual("newer", request["reason"])

    def test_daily_runner_never_deletes_a_newer_request_created_while_it_settles(self) -> None:
        automatic_updates.queued("earlier", starting=lambda _one: 41, environ={})

        def succeeded_after_a_new_request(_args, **_updating):
            automatic_updates.queued("newer", starting=lambda _one: 42, environ={})
            return update.Attempt(OK, False)

        with mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch("rundesk.commands.update.attempt_update",
                           side_effect=succeeded_after_a_new_request):
            result = automatic_updates.run(
                datetime.datetime(2026, 8, 8, 3, 0).astimezone())

        self.assertEqual(OK, result)
        request = json.loads(automatic_updates.request_at(
            automatic_updates.coordinator()).read_text())
        self.assertEqual("newer", request["reason"])

    def test_a_turn_winning_the_final_race_keeps_the_request_deferred(self) -> None:
        automatic_updates.queued("earlier work", starting=lambda _one: 41, environ={})
        started = []

        def start(one):
            started.append(locking.is_held(automatic_updates.queue_lock_at(one)))
            return 42

        with mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch("rundesk.commands.update.attempt_update",
                           return_value=update.Attempt(OK, True)), \
                mock.patch.object(automatic_updates, "_start_queued_runner", side_effect=start):
            result = automatic_updates.run(
                datetime.datetime(2026, 8, 8, 3, 0).astimezone())

        self.assertEqual(OK, result)
        self.assertEqual([False], started)
        self.assertTrue(automatic_updates.request_at(automatic_updates.coordinator()).is_file())
        self.assertIn('"outcome": "DEFERRED"',
                      automatic_updates.state_at(automatic_updates.coordinator()).read_text())

    def test_the_same_worker_keeps_waiting_when_a_turn_wins_its_final_race(self) -> None:
        automatic_updates.queued("busy", starting=lambda _one: 41, environ={})
        updating = mock.Mock(side_effect=[update.Attempt(OK, True),
                                         update.Attempt(OK, False)])
        with mock.patch.object(automatic_updates, "_busy_reason",
                               side_effect=["", "busy", ""]), \
                mock.patch("rundesk.commands.update.attempt_update", updating):
            result = automatic_updates.run_queued(sleeping=lambda _seconds: None)

        self.assertEqual(OK, result)
        self.assertEqual(2, updating.call_count)
        self.assertFalse(automatic_updates.request_at(automatic_updates.coordinator()).exists())

    def test_a_second_daily_runner_skips_while_the_queue_worker_owns_the_claim(self) -> None:
        updating = mock.Mock(return_value=update.Attempt(OK, False))
        self.a_queue_worker_holding_its_claim()
        with mock.patch("rundesk.commands.update.attempt_update", updating):
            result = automatic_updates.run(
                datetime.datetime(2026, 8, 8, 3, 0).astimezone())

        self.assertEqual(OK, result)
        updating.assert_not_called()

    def test_cancel_removes_the_request_but_refuses_while_its_worker_is_active(self) -> None:
        automatic_updates.queued("busy", starting=lambda _one: 41, environ={})
        self.a_queue_worker_holding_its_claim()
        trouble = automatic_updates.cancel_queued(waiting=0)

        self.assertTrue(trouble)
        self.assertFalse(automatic_updates.request_at(automatic_updates.coordinator()).exists())

    def test_uninstall_exclusion_holds_both_update_claims_for_its_whole_body(self) -> None:
        one = automatic_updates.coordinator()
        with automatic_updates.updates_stopped():
            self.assertTrue(locking.is_held(automatic_updates.queue_lock_at(one)))
            self.assertTrue(locking.is_held(paths.update_lock()))

    def test_an_uninstall_body_error_is_not_misreported_as_failure_to_stop_updates(self) -> None:
        with self.assertRaisesRegex(OSError, "removal body failed"):
            with automatic_updates.updates_stopped():
                raise OSError("removal body failed")

    def test_detached_runner_receives_no_conversation_or_delegation_context(self) -> None:
        with mock.patch.object(automatic_updates.programs, "start", return_value=41) as started:
            automatic_updates._start_queued_runner(automatic_updates.coordinator())

        environ = started.call_args.kwargs["env"]
        self.assertEqual("1", environ[automatic_updates.QUEUED])
        self.assertNotIn("RUNDESK_AGENT", environ)
        self.assertNotIn("RUNDESK_RUN", environ)
        self.assertNotIn("RUNDESK_DELEGATION", environ)


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
            ["uninstall", "--confirm", "--purge", "--root", str(paths.home())],
            supervising=supervisor)

        self.assertEqual(OK, code, err)
        self.assertIn("rundesk removed", out)
        self.assertIn(("bootout", one.label), supervisor.asked)
        self.assertFalse(paths.app().exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
