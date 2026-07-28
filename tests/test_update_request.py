"""Durable self-update requests survive processes and never overlap."""

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import cli, update_request  # noqa: E402


class DurableRequests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(os.environ.pop, "RUNDESK_DATA_DIR", None)
        os.environ["RUNDESK_DATA_DIR"] = self.temporary.name

    def test_duplicate_requests_share_one_pending_update(self):
        """R-UPD-37"""
        first, created = update_request.queue({"agent": "ava", "run": "one"})
        second, created_again = update_request.queue({"agent": "ava", "run": "two"})
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])

    def test_pending_running_and_final_outcomes_are_durable(self):
        """R-UPD-36"""
        queued, _ = update_request.queue({"agent": "ava", "run": "one"})
        self.assertEqual("pending", update_request.read()["state"])
        self.assertEqual("running", update_request.claim()["state"])
        update_request.finish(queued["id"], "succeeded", "updated", "rundesk 0.9.7")
        self.assertEqual("succeeded", update_request.read()["state"])

    def test_final_outcome_waits_for_its_origin_agent_and_is_delivered_once(self):
        """R-UPD-40"""
        queued, _ = update_request.queue({
            "agent": "ava", "run": "one", "channel": "discord",
            "conversation": "room-7",
        })
        update_request.claim()
        update_request.finish(queued["id"], "succeeded", "updated", "rundesk 0.9.7")
        self.assertIsNone(update_request.deliverable("bo"))
        self.assertEqual(queued["id"], update_request.deliverable("ava")["id"])
        update_request.delivered(queued["id"])
        self.assertIsNone(update_request.deliverable("ava"))

    def test_only_safe_origin_identity_is_kept(self):
        queued, _ = update_request.queue({
            "agent": "ava", "run": "one", "channel": "discord",
            "conversation": "room-7", "prompt": "private", "token": "secret",
        })
        self.assertEqual(
            {"agent", "run", "channel", "conversation"}, set(queued["origin"])
        )

    def test_unreadable_request_is_never_replaced_as_empty(self):
        update_request.path().write_text("{broken", encoding="utf-8")
        with self.assertRaises(update_request.Unreadable):
            update_request.queue({"agent": "ava", "run": "one"})
        self.assertEqual("{broken", update_request.path().read_text(encoding="utf-8"))

    def test_external_worker_waits_for_active_work_then_runs_the_guarded_update(self):
        """R-UPD-38"""
        queued, _ = update_request.queue({"agent": "ava", "run": "one"})
        completed = [
            mock.Mock(returncode=0, stdout="updated safely\n", stderr=""),
            mock.Mock(returncode=0, stdout="rundesk 0.9.7\n", stderr=""),
        ]
        with mock.patch.object(cli, "_in_flight", side_effect=[["ava/turn:one"], []]), \
                mock.patch.object(cli.time, "sleep"), \
                mock.patch.object(cli, "_recover_update_gateways", return_value=[]), \
                mock.patch.object(cli, "_install_automatic_updates", return_value=0), \
                mock.patch.object(cli.subprocess, "run", side_effect=completed) as ran:
            code = cli._run_update_worker(mock.Mock(), mock.Mock(), mock.Mock())
        self.assertEqual(0, code)
        self.assertEqual(2, ran.call_count)
        final = update_request.read()
        self.assertEqual(queued["id"], final["id"])
        self.assertEqual("succeeded", final["state"])

    def test_external_worker_waits_for_the_origin_run_record_to_finish(self):
        """R-UPD-38"""
        update_request.queue({"agent": "ava", "run": "one"})

        class Agents:
            def __init__(self):
                self.runs = iter([
                    {"id": "one", "ended_at": None},
                    {"id": "one", "ended_at": "2026-07-27T23:30:00Z"},
                ])

            def reading(self, name):
                self.name = name
                return self

            def run(self, run_id):
                self.run_id = run_id
                return next(self.runs)

        completed = [
            mock.Mock(returncode=0, stdout="updated safely\n", stderr=""),
            mock.Mock(returncode=0, stdout="rundesk 0.9.9\n", stderr=""),
        ]
        agents = Agents()
        with mock.patch.object(cli, "_in_flight", side_effect=lambda *_: []), \
                mock.patch.object(cli.time, "sleep") as slept, \
                mock.patch.object(cli, "_recover_update_gateways", return_value=[]), \
                mock.patch.object(cli, "_install_automatic_updates", return_value=0), \
                mock.patch.object(cli.subprocess, "run", side_effect=completed):
            self.assertEqual(0, cli._run_update_worker(
                mock.Mock(), mock.Mock(), agents
            ))
        slept.assert_called_once()
        self.assertEqual("ava", agents.name)
        self.assertEqual("one", agents.run_id)

    def test_external_worker_can_update_a_separate_installed_root(self):
        update_request.queue({"agent": "ava", "run": "one"})
        target = pathlib.Path(self.temporary.name) / "installed"
        os.environ["RUNDESK_UPDATE_ROOT"] = str(target)
        self.addCleanup(os.environ.pop, "RUNDESK_UPDATE_ROOT", None)
        completed = [
            mock.Mock(returncode=0, stdout="rundesk 0.9.6\n", stderr=""),
            mock.Mock(returncode=0, stdout="updated safely\n", stderr=""),
            mock.Mock(returncode=0, stdout="rundesk 0.9.7\n", stderr=""),
        ]
        with mock.patch.object(cli, "_in_flight", return_value=[]), \
                mock.patch.object(cli, "_recover_update_gateways", return_value=[]), \
                mock.patch.object(cli, "_install_automatic_updates", return_value=0), \
                mock.patch.object(cli.subprocess, "run", side_effect=completed) as ran:
            self.assertEqual(0, cli._run_update_worker(
                mock.Mock(), mock.Mock(), mock.Mock()
            ))
        update = ran.call_args_list[1]
        self.assertEqual(str(cli.REPO_ROOT / "rundesk"), update.args[0][0])
        self.assertEqual(str(target), update.kwargs["env"]["RUNDESK_UPDATE_ROOT"])
        self.assertEqual("0.9.6", update.kwargs["env"]["RUNDESK_UPDATE_VERSION"])

    def test_an_interrupted_update_stays_active_for_the_supervisor_to_retry(self):
        """R-UPD-44"""
        update_request.queue({})
        with mock.patch.object(cli, "_in_flight", return_value=[]), \
                mock.patch.object(
                    cli.subprocess, "run",
                    side_effect=cli.subprocess.TimeoutExpired(["rundesk", "update"], 1),
                ):
            self.assertEqual(1, cli._run_update_worker(
                mock.Mock(), mock.Mock(), mock.Mock()
            ))
        self.assertEqual("running", update_request.read()["state"])

    def test_bootstrap_child_drives_the_old_target_with_its_new_update_logic(self):
        target = pathlib.Path(self.temporary.name) / "installed"
        args = mock.Mock(
            after_replacing=None, worker=False, status=False, check=False
        )
        with mock.patch.dict(os.environ, {
                    "RUNDESK_UPDATE_ROOT": str(target),
                    "RUNDESK_UPDATE_VERSION": "0.9.6",
                }, clear=True), \
                mock.patch.object(cli.updater, "run", return_value=0) as ran:
            self.assertEqual(0, cli.cmd_update(
                args, mock.Mock(), mock.Mock(), mock.Mock()
            ))
        self.assertEqual(target, ran.call_args.args[0])
        self.assertEqual("0.9.6", ran.call_args.args[1])

    def test_agent_initiation_queues_the_external_worker_and_returns(self):
        """R-UPD-35, R-UPD-36"""
        class Machine:
            class Unsure(Exception):
                pass

            def available(self):
                return True

            def loaded(self, name):
                return name == "ava"

            def update_worker_loaded(self):
                return False

            def install_update_worker(self):
                return mock.Mock(ok=True, said="")

        code = cli._queue_update(Machine(), {
            "agent": "ava", "run": "one", "channel": "discord",
            "conversation": "room-7",
        })
        self.assertEqual(0, code)
        self.assertEqual("pending", update_request.read()["state"])

    def test_duplicate_agent_initiation_does_not_restart_the_worker(self):
        """R-UPD-37"""
        class Machine:
            class Unsure(Exception):
                pass

            installed = 0

            def available(self):
                return True

            def loaded(self, name):
                return True

            def update_worker_loaded(self):
                return self.installed > 0

            def install_update_worker(self):
                self.installed += 1
                return mock.Mock(ok=True, said="")

        machine = Machine()
        origin = {"agent": "ava", "run": "one"}
        self.assertEqual(0, cli._queue_update(machine, origin))
        self.assertEqual(0, cli._queue_update(machine, origin))
        self.assertEqual(1, machine.installed)

    def test_duplicate_agent_initiation_recovers_a_missing_worker(self):
        """R-UPD-35, R-UPD-36, R-UPD-37"""
        class Machine:
            class Unsure(Exception):
                pass

            installed = 0

            def available(self):
                return True

            def loaded(self, name):
                return True

            def update_worker_loaded(self):
                return False

            def install_update_worker(self):
                self.installed += 1
                return mock.Mock(ok=True, said="")

        machine = Machine()
        update_request.queue({"agent": "ava", "run": "one"})
        update_request.claim()
        self.assertEqual(0, cli._queue_update(machine, {"agent": "ava", "run": "two"}))
        self.assertEqual(1, machine.installed)
        self.assertEqual("running", update_request.read()["state"])

    def test_the_daily_trigger_queues_the_crash_recoverable_worker(self):
        """R-UPD-42"""
        class Machine:
            class Unsure(Exception):
                pass

            def available(self):
                return True

            def install_update_worker(self):
                self.installed = True
                return mock.Mock(ok=True, said="")

        machine = Machine()
        self.assertEqual(0, cli._queue_automatic_update(machine))
        self.assertTrue(machine.installed)
        self.assertEqual("pending", update_request.read()["state"])
        self.assertEqual({}, update_request.read()["origin"])

    def test_a_successful_manual_update_installs_the_daily_trigger(self):
        """R-UPD-42"""
        args = mock.Mock(
            after_replacing=None, worker=False, automatic=False,
            status=False, check=False,
        )

        class Machine:
            class NoSupervisor(Exception):
                pass

            class NotOurs(Exception):
                pass

            def available(self):
                return True

            def install_automatic_update(self):
                self.installed = True
                return mock.Mock(ok=True, said="")

        machine = Machine()
        with mock.patch.dict(os.environ, {"RUNDESK_RUN": ""}, clear=False), \
                mock.patch.object(cli.updater, "run", return_value=0):
            self.assertEqual(0, cli.cmd_update(
                args, mock.Mock(), machine, mock.Mock()
            ))
        self.assertTrue(machine.installed)

    def test_a_second_daily_trigger_does_not_overlap_an_active_update(self):
        """R-UPD-37, R-UPD-42"""
        class Machine:
            class Unsure(Exception):
                pass

            installed = 0

            def available(self):
                return True

            def update_worker_loaded(self):
                return True

            def install_update_worker(self):
                self.installed += 1
                return mock.Mock(ok=True, said="")

        machine = Machine()
        update_request.queue({})
        self.assertEqual(0, cli._queue_automatic_update(machine))
        self.assertEqual(0, machine.installed)

    def test_maintenance_markers_survive_a_worker_and_clear_only_after_recovery(self):
        """R-UPD-43"""
        run_home = pathlib.Path(self.temporary.name) / "run"
        marker = update_request.begin_maintenance("ava", run_home)
        self.assertTrue(marker.is_file())
        self.assertTrue(update_request.maintaining("ava", run_home))
        update_request.finish_maintenance("ava", run_home)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
