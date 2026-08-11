"""Lifecycle continuation is explicit at the CLI and survives the existing update queue."""

import json
import os
import unittest
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import arriving
from rundesk.commands import automatic_updates, update
from rundesk.exits import FAILED, OK, USAGE
from rundesk.gateways import job, standing
from rundesk.providers import continuations, kept, protocol, turns


class LifecycleCommands(support.Isolated):
    def setUp(self):
        super().setUp()
        self.agent = "ava"
        self.at = directory.made(self.agent, support.A_STAND_IN)
        landed = arriving.recorded(
            self.agent, "discord", "1180", "2207", "perform lifecycle work")
        self.conversation = landed.conversation
        self.message = landed.message
        self.turn = kept.add_turn(self.agent, {
            "conversation_id": self.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": protocol.ACCESS_WORK,
            "provider_capabilities": json.dumps({"resume": True}),
        })
        arriving.handled_by_turn(
            self.agent, self.conversation, (self.message,), self.turn)
        self.origin = {
            "RUNDESK_AGENT": self.agent, "RUNDESK_RUN": str(self.turn),
            "RUNDESK_CWD": str(directory.home(self.agent)),
        }

    def test_update_continue_records_before_the_existing_queue_worker_starts(self):
        observed = []

        def starting(_one):
            observed.append(continuations.for_turn(
                self.agent, self.turn, continuations.UPDATE) is not None)
            return 41

        with turns.claiming(self.agent, self.conversation), \
                mock.patch.dict(os.environ, self.origin), \
                mock.patch.object(automatic_updates, "_start_queued_runner", starting):
            code, out, err = support.run_with(
                ["update", "--continue"], asking=mock.Mock())

        self.assertEqual(OK, code, err)
        self.assertEqual([True], observed)
        self.assertIn("queued until current work finishes", out)
        request = json.loads(automatic_updates.request_at(
            automatic_updates.coordinator()).read_text())
        self.assertEqual({"agent": self.agent, "turn": self.turn,
                          "handoff": continuations.for_turn(
                              self.agent, self.turn, continuations.UPDATE).id},
                         request["continuation"])

    def test_update_without_opt_in_keeps_queue_behavior_but_no_handoff(self):
        with turns.claiming(self.agent, self.conversation), \
                mock.patch.dict(os.environ, self.origin), \
                mock.patch.object(automatic_updates, "_start_queued_runner", return_value=41):
            code, _, err = support.run_with(["update"], asking=mock.Mock())

        self.assertEqual(OK, code, err)
        self.assertIsNone(continuations.for_turn(
            self.agent, self.turn, continuations.UPDATE))
        request = json.loads(automatic_updates.request_at(
            automatic_updates.coordinator()).read_text())
        self.assertNotIn("continuation", request)

    def test_update_continue_refuses_terminal_origin_before_asking_or_queueing(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        asking = mock.Mock()
        with mock.patch.dict(os.environ, self.origin):
            code, out, err = support.run_with(
                ["update", "--continue"], asking=asking)

        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("active channel", err)
        asking.assert_not_called()
        self.assertFalse(automatic_updates.request_at(
            automatic_updates.coordinator()).exists())

    def test_later_unflagged_queue_request_cannot_erase_opted_in_provenance(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        automatic_updates.queued(
            "opted in", starting=lambda _one: 41,
            continuation=(self.agent, self.turn, handoff.id))
        automatic_updates.queued(
            "later ordinary request", starting=lambda _one: 42, environ={})

        request = json.loads(automatic_updates.request_at(
            automatic_updates.coordinator()).read_text())
        self.assertEqual("opted in", request["reason"])
        self.assertEqual(handoff.id, request["continuation"]["handoff"])

    def test_queued_opt_in_failure_is_terminal_and_does_not_retry_forever(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        automatic_updates.queued(
            "opted in", starting=lambda _one: 41,
            continuation=(self.agent, self.turn, handoff.id))
        sleeping = mock.Mock()
        with mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch.object(
                    update, "attempt_update", return_value=update.Attempt(FAILED, False)):
            code = automatic_updates.run_queued(sleeping=sleeping)

        got = continuations.for_turn(self.agent, self.turn, continuations.UPDATE)
        self.assertEqual(FAILED, code)
        self.assertEqual(continuations.FAILED, got.lifecycle_state)
        self.assertFalse(automatic_updates.request_at(
            automatic_updates.coordinator()).exists())
        sleeping.assert_not_called()

    def test_queued_opt_in_success_completes_the_exact_update_handoff(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        automatic_updates.queued(
            "opted in", starting=lambda _one: 41,
            continuation=(self.agent, self.turn, handoff.id))
        with mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch.object(
                    update, "attempt_update", return_value=update.Attempt(OK, False)):
            code = automatic_updates.run_queued()

        got = continuations.for_turn(self.agent, self.turn, continuations.UPDATE)
        self.assertEqual(OK, code)
        self.assertEqual(continuations.SUCCEEDED, got.lifecycle_state)
        self.assertFalse(automatic_updates.request_at(
            automatic_updates.coordinator()).exists())

    def test_queued_worker_does_not_apply_stale_turn_provenance_to_a_handoff(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        automatic_updates.queued(
            "opted in", starting=lambda _one: 41,
            continuation=(self.agent, self.turn, handoff.id))
        request_at = automatic_updates.request_at(automatic_updates.coordinator())
        request = json.loads(request_at.read_text())
        request["continuation"]["turn"] = self.turn + 100
        automatic_updates._written_privately(
            request_at, (json.dumps(request) + "\n").encode(), 0o600)
        attempting = mock.Mock(return_value=update.Attempt(OK, False))
        with mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch.object(update, "attempt_update", attempting):
            code = automatic_updates.run_queued()

        self.assertEqual(FAILED, code)
        attempting.assert_not_called()
        self.assertEqual(continuations.SUPPRESSED, continuations.one(
            self.agent, handoff.id).continuation_state)

    def test_queued_update_never_completes_a_gateway_restart_handoff(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.GATEWAY_RESTART, 41)
        automatic_updates.queued(
            "wrong operation", starting=lambda _one: 41,
            continuation=(self.agent, self.turn, handoff.id))
        attempting = mock.Mock(return_value=update.Attempt(OK, False))
        with mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch.object(update, "attempt_update", attempting):
            code = automatic_updates.run_queued()

        self.assertEqual(FAILED, code)
        attempting.assert_not_called()
        self.assertEqual(continuations.REQUESTED, continuations.one(
            self.agent, handoff.id).lifecycle_state)
        self.assertFalse(automatic_updates.request_at(
            automatic_updates.coordinator()).exists())

    def test_safe_self_gateway_restart_queues_without_touching_the_supervisor(self):
        by = support.ASupervisor()
        one = job.job(self.agent, self.at, self.home, self.home / "LaunchAgents")
        job.place(one, by)
        by.answers["print"] = support.ran(0)
        by.asked.clear()
        with standing.holding(self.at), turns.claiming(self.agent, self.conversation), \
                mock.patch.dict(os.environ, self.origin):
            standing.write_record(self.at, self.agent, "0.45.1")
            code, out, err = support.run_with(
                ["gateways", "restart", self.agent, "--continue"], supervising=by)

        self.assertEqual(OK, code, err)
        self.assertIn("queued", out)
        self.assertEqual([], [verb for verb in by.verbs()
                              if verb in ("bootout", "bootstrap")])

    def test_a_newer_gateway_stop_suppresses_a_queued_self_restart(self):
        by = support.ASupervisor()
        one = job.job(self.agent, self.at, self.home, self.home / "LaunchAgents")
        job.place(one, by)
        by.answers["print"] = support.ran(job.NOT_KNOWN)
        handoff = continuations.requested(
            self.agent, self.turn, self.message,
            continuations.GATEWAY_RESTART, 41)

        code, _, err = support.run_with(
            ["gateways", "stop", self.agent], supervising=by)

        self.assertEqual(OK, code, err)
        self.assertEqual(continuations.SUPPRESSED, continuations.one(
            self.agent, handoff.id).continuation_state)

    def test_restart_continue_refuses_other_agent_all_and_force(self):
        directory.made("other", support.A_STAND_IN)
        with turns.claiming(self.agent, self.conversation), \
                mock.patch.dict(os.environ, self.origin):
            another = support.run_with(
                ["gateways", "restart", "other", "--continue"])[0]
            every = support.run_with(
                ["gateways", "restart", "--all", "--continue"])[0]
            forced = support.run_with(
                ["gateways", "restart", self.agent, "--force", "--continue"])[0]

        self.assertEqual(FAILED, another)
        self.assertEqual((USAGE, USAGE), (every, forced))
        self.assertIsNone(continuations.for_turn(
            self.agent, self.turn, continuations.GATEWAY_RESTART))


if __name__ == "__main__":
    unittest.main()
