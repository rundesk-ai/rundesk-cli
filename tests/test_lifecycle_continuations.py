"""Opt-in lifecycle handoffs preserve one exact conversation and wake it at most once."""

import json
import os
import shutil
import sqlite3
import unittest
from unittest import mock

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving, hosting
from rundesk.core import config, paths
from rundesk.gateways import host
from rundesk.lifecycle import backups
from rundesk.providers import answering, continuations, instructions, kept, protocol, turns


class LifecycleContinuations(support.Isolated):
    def setUp(self):
        super().setUp()
        self.agent = "ava"
        self.at = directory.made(self.agent, support.A_STAND_IN)
        landed = arriving.recorded(
            self.agent, "discord", "1180", "2207", "update safely and continue")
        self.conversation = landed.conversation
        self.message = landed.message
        self.turn = kept.add_turn(self.agent, {
            "conversation_id": self.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": protocol.ACCESS_WORK,
            "provider_capabilities": json.dumps({"resume": True}),
        })
        origin_request = turns.Request(
            agent=self.agent, prompt="", conversation=self.conversation,
            source=arriving.FROM_CHANNEL, place="1180")
        origin_prompt = instructions.build(
            situation=instructions.USER_TO_AGENT,
            variables=turns._about(origin_request, support.A_STAND_IN),
            team=turns.team.for_agent(self.agent))
        with records.writing(directory.records(self.agent)) as conn:
            conn.execute(
                "UPDATE turns SET instructions_sha256 = ? WHERE id = ?",
                (origin_prompt.sha256, self.turn))
        arriving.handled_by_turn(
            self.agent, self.conversation, (self.message,), self.turn)
        self.origin = {
            "RUNDESK_AGENT": self.agent, "RUNDESK_RUN": str(self.turn),
            "RUNDESK_CWD": str(directory.home(self.agent)),
        }

    def row(self):
        with records.reading(directory.records(self.agent)) as conn:
            found = conn.execute(
                "SELECT * FROM lifecycle_continuations WHERE origin_turn_id = ?",
                (self.turn,),
            ).fetchone()
        return dict(found)

    def test_only_an_active_channel_turn_with_an_exact_owner_origin_is_accepted(self):
        with turns.claiming(self.agent, self.conversation), \
                mock.patch.dict(os.environ, self.origin):
            got = continuations.origin()
        self.assertEqual((self.agent, self.turn, self.conversation, self.message), got)

        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        with mock.patch.dict(os.environ, self.origin):
            with self.assertRaisesRegex(continuations.NoOrigin, "active channel"):
                continuations.origin()

    def test_mid_turn_owner_guidance_becomes_the_exact_continuation_origin(self):
        guidance = arriving.recorded(
            self.agent, "discord", "1180", "2207", "finish the update and continue")
        arriving.handled_by_turn(
            self.agent, self.conversation, (guidance.message,), self.turn)

        with turns.claiming(self.agent, self.conversation), \
                mock.patch.dict(os.environ, self.origin):
            got = continuations.origin()

        self.assertEqual(
            (self.agent, self.turn, self.conversation, guidance.message), got)

    def test_terminal_and_ambiguous_callers_write_nothing(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        with mock.patch.dict(os.environ, self.origin):
            with self.assertRaises(continuations.NoOrigin):
                continuations.requested_from_origin(continuations.UPDATE)
        with records.reading(directory.records(self.agent)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM lifecycle_continuations").fetchone()[0]
        self.assertEqual(0, count)

    def test_another_agents_home_cannot_be_mistaken_for_the_active_origin(self):
        other = "bea"
        directory.made(other, support.A_STAND_IN)
        claimed = dict(self.origin, RUNDESK_CWD=str(directory.home(other)))
        with turns.claiming(self.agent, self.conversation), mock.patch.dict(os.environ, claimed):
            with self.assertRaisesRegex(continuations.NoOrigin, "agent and home"):
                continuations.requested_from_origin(continuations.UPDATE)
        with records.reading(directory.records(self.agent)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM lifecycle_continuations").fetchone()[0]
        self.assertEqual(0, count)

    def test_one_turn_can_request_one_operation_once_without_private_payload(self):
        with turns.claiming(self.agent, self.conversation), \
                mock.patch.dict(os.environ, self.origin):
            first = continuations.requested_from_origin(continuations.UPDATE, 41)
            duplicate = continuations.requested_from_origin(continuations.UPDATE, 99)

        self.assertEqual(first.id, duplicate.id)
        self.assertEqual(41, self.row()["requested_pid"])
        serialized = " ".join(str(value) for value in self.row().values() if value is not None)
        for private in (self.agent, "discord", "1180", "2207",
                        "update safely and continue"):
            self.assertNotIn(private, serialized)

    def test_unsupported_resume_still_records_the_requested_wake(self):
        with records.writing(directory.records(self.agent)) as conn:
            conn.execute(
                "UPDATE turns SET provider_capabilities = '{}' WHERE id = ?", (self.turn,))
        with turns.claiming(self.agent, self.conversation), \
                mock.patch.dict(os.environ, self.origin):
            got = continuations.requested_from_origin(continuations.UPDATE, 41)
        self.assertEqual(continuations.REQUESTED, got.continuation_state)

    def test_newer_owner_input_suppresses_before_the_once_only_claim(self):
        kept.save_session(self.agent, self.conversation, support.A_STAND_IN, "session-9")
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="updated")
        arriving.recorded(self.agent, "discord", "1180", "2207", "I already continued")

        self.assertIsNone(continuations.claim(self.agent, handoff.id))
        self.assertEqual(continuations.SUPPRESSED, self.row()["continuation_state"])

    def test_crash_claim_is_at_most_once_and_a_delivered_turn_is_terminal(self):
        kept.save_session(self.agent, self.conversation, support.A_STAND_IN, "session-9")
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        continuations.finished(self.agent, handoff.id, succeeded=False, outcome="rolled back")

        first = continuations.claim(self.agent, handoff.id)
        second = continuations.claim(self.agent, handoff.id)
        continuations.delivered(self.agent, handoff.id, "continuation turn delivered")

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertIsNone(continuations.claim(self.agent, handoff.id))
        self.assertEqual(continuations.DELIVERED, self.row()["continuation_state"])

    def test_restart_requires_changed_pid_and_exact_channel_health(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message,
            continuations.GATEWAY_RESTART, 41)
        continuations.running(self.agent, handoff.id)
        watching = hosting.Watching({}, {}, {})
        with mock.patch.object(host.os, "getpid", return_value=41), \
                mock.patch.object(hosting, "connected", return_value=True):
            host._finished_lifecycle_restart(self.agent, watching)
        self.assertEqual(continuations.RUNNING, self.row()["lifecycle_state"])

        with mock.patch.object(host.os, "getpid", return_value=52), \
                mock.patch.object(hosting, "connected", return_value=True):
            host._finished_lifecycle_restart(self.agent, watching)
        self.assertEqual(continuations.SUCCEEDED, self.row()["lifecycle_state"])

    def test_already_current_update_can_resume_on_the_same_healthy_gateway_pid(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="already current")
        answerer = mock.Mock()
        watching = hosting.Watching({}, {}, {})
        with mock.patch.object(hosting, "connected", return_value=True):
            host._resumed_lifecycle(self.agent, watching, answerer)

        answerer.resume.assert_called_once_with(self.agent, handoff.id)
        got = continuations.one(self.agent, handoff.id)
        self.assertEqual(os.getpid(), got.observed_pid)
        self.assertEqual(host.__version__, got.observed_version)

    def test_self_restart_waits_for_the_origin_turn_then_uses_gateway_exit(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message,
            continuations.GATEWAY_RESTART, os.getpid())
        asked_for = []
        with mock.patch.object(host.os, "kill") as killed:
            with turns.claiming(self.agent, self.conversation):
                host._requested_lifecycle_restart(self.agent, asked_for)
            killed.assert_not_called()
            self.assertEqual([], asked_for)

            host._requested_lifecycle_restart(self.agent, asked_for)

        self.assertEqual([host.LIFECYCLE_RESTART], asked_for)
        self.assertEqual(continuations.RUNNING,
                         continuations.one(self.agent, handoff.id).lifecycle_state)

    def test_direct_continuation_adds_one_turn_and_no_owner_message_or_delegation(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        kept.save_session(self.agent, self.conversation, support.A_STAND_IN, "session-9")
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="already current")
        before_turns = kept.turns_in_conversation(self.agent, self.conversation)
        before_users = [one for one in arriving.messages(self.agent, self.conversation)
                        if one["author"] == arriving.BY_USER]
        answerer = __import__(
            "rundesk.providers.answering", fromlist=["OnAContinuation"]
        ).OnAContinuation(directory.logs(self.agent), lambda: hosting.Watching({}, {}, {}))

        with mock.patch.object(answerer, "_delivered", return_value=""):
            answerer._resumed(self.agent, handoff.id)

        after_turns = kept.turns_in_conversation(self.agent, self.conversation)
        after_users = [one for one in arriving.messages(self.agent, self.conversation)
                       if one["author"] == arriving.BY_USER]
        self.assertEqual(len(before_turns) + 1, len(after_turns))
        self.assertEqual(len(before_users), len(after_users))
        self.assertEqual(1, after_turns[-1]["session_resumed"])
        instruction_records = [
            json.loads(one["event_data"]) for one in kept.list_turn_records(
                self.agent, int(after_turns[-1]["id"]))
            if one["record_type"] == turns.INSTRUCTIONS]
        self.assertEqual("", instruction_records[0]["team"])
        with records.reading(directory.records(self.agent)) as conn:
            delegations = conn.execute("SELECT COUNT(*) FROM delegations").fetchone()[0]
        self.assertEqual(0, delegations)
        self.assertEqual(continuations.DELIVERED,
                         continuations.one(self.agent, handoff.id).continuation_state)

    def test_an_admitted_continuation_starts_and_ends_the_channel_state(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="updated")
        answerer = answering.OnAContinuation(
            directory.logs(self.agent), lambda: hosting.Watching({}, {}, {}))

        with mock.patch.object(answerer, "_delivered", return_value=""), \
                mock.patch.object(hosting, "marked", return_value=True) as marked:
            answerer._resumed(self.agent, handoff.id)

        self.assertEqual(
            [mock.call(self.agent, directory.logs(self.agent), mock.ANY,
                       "discord", "1180", answering.WORKING),
             mock.call(self.agent, directory.logs(self.agent), mock.ANY,
                       "discord", "1180", answering.DONE)],
            marked.call_args_list)

    def test_an_admitted_continuation_failure_stops_the_channel_state(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="updated")
        answerer = answering.OnAContinuation(
            directory.logs(self.agent), lambda: hosting.Watching({}, {}, {}))

        def failed(_request, admitting, watching=None, admitted=None):
            self.assertTrue(admitting())
            admitted()
            raise RuntimeError("provider fell over")

        with mock.patch.object(turns, "run_if", side_effect=failed), \
                mock.patch.object(hosting, "marked", return_value=True) as marked:
            answerer._resumed(self.agent, handoff.id)

        self.assertEqual(
            [answering.WORKING, answering.FAILED],
            [one.args[-1] for one in marked.call_args_list])

    def test_a_suppressed_continuation_never_starts_channel_state(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="updated")
        arriving.recorded(self.agent, "discord", "1180", "2207", "I already continued")
        answerer = answering.OnAContinuation(
            directory.logs(self.agent), lambda: hosting.Watching({}, {}, {}))

        with mock.patch.object(hosting, "marked", return_value=True) as marked:
            answerer._resumed(self.agent, handoff.id)

        marked.assert_not_called()
        self.assertEqual(
            continuations.SUPPRESSED,
            continuations.one(self.agent, handoff.id).continuation_state)

    def test_missing_session_wakes_once_in_a_fresh_session(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="updated")
        before = len(kept.turns_in_conversation(self.agent, self.conversation))
        answerer = __import__(
            "rundesk.providers.answering", fromlist=["OnAContinuation"]
        ).OnAContinuation(directory.logs(self.agent), lambda: hosting.Watching({}, {}, {}))

        answerer._resumed(self.agent, handoff.id)

        after = kept.turns_in_conversation(self.agent, self.conversation)
        self.assertEqual(before + 1, len(after))
        self.assertEqual(0, after[-1]["session_resumed"])
        self.assertEqual(continuations.DELIVERED,
                         continuations.one(self.agent, handoff.id).continuation_state)

    def test_changed_instructions_wake_fresh_without_resuming_stale_authority(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        kept.save_session(self.agent, self.conversation, support.A_STAND_IN, "session-9")
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="updated")
        before = len(kept.turns_in_conversation(self.agent, self.conversation))
        answerer = __import__(
            "rundesk.providers.answering", fromlist=["OnAContinuation"]
        ).OnAContinuation(directory.logs(self.agent), lambda: hosting.Watching({}, {}, {}))

        with mock.patch.object(turns.team, "for_agent", return_value="bea: newly eligible"):
            answerer._resumed(self.agent, handoff.id)

        after = kept.turns_in_conversation(self.agent, self.conversation)
        self.assertEqual(before + 1, len(after))
        self.assertEqual(0, after[-1]["session_resumed"])
        self.assertEqual(continuations.DELIVERED,
                         continuations.one(self.agent, handoff.id).continuation_state)

    def test_changed_provider_wakes_once_in_a_fresh_session(self):
        kept.finish_turn(self.agent, self.turn, kept.DONE, {})
        kept.save_session(self.agent, self.conversation, support.A_STAND_IN, "session-9")
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        continuations.finished(self.agent, handoff.id, succeeded=True, outcome="updated")
        changed = self.home / "changed-provider"
        shutil.copy2(support.A_STAND_IN, changed)
        changed.chmod(0o755)
        records.stated(directory.records(self.agent), {"provider_name": str(changed)})
        before = len(kept.turns_in_conversation(self.agent, self.conversation))
        answerer = __import__(
            "rundesk.providers.answering", fromlist=["OnAContinuation"]
        ).OnAContinuation(directory.logs(self.agent), lambda: hosting.Watching({}, {}, {}))

        with mock.patch.object(answerer, "_delivered", return_value=""):
            answerer._resumed(self.agent, handoff.id)

        after = kept.turns_in_conversation(self.agent, self.conversation)
        self.assertEqual(before + 1, len(after))
        self.assertEqual(0, after[-1]["session_resumed"])
        self.assertEqual(str(changed), after[-1]["provider_name"])
        self.assertEqual(continuations.DELIVERED,
                         continuations.one(self.agent, handoff.id).continuation_state)

    def test_recovery_prompt_names_the_exact_recorded_context_command(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, os.getpid())
        said = continuations.prompt(self.agent, handoff)
        self.assertIn(
            f'"$RUNDESK_COMMAND" messages {self.agent} --conversation {self.conversation}', said)

    def test_one_gateway_never_wakes_another_agents_terminal_handoff(self):
        other = "bea"
        directory.made(other, support.A_STAND_IN)
        landed = arriving.recorded(other, "discord", "900", "901", "continue mine")
        other_turn = kept.add_turn(other, {
            "conversation_id": landed.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": protocol.ACCESS_WORK,
            "provider_capabilities": json.dumps({"resume": True}),
        })
        arriving.handled_by_turn(other, landed.conversation, (landed.message,), other_turn)
        kept.save_session(other, landed.conversation, support.A_STAND_IN, "other-session")
        handoff = continuations.requested(
            other, other_turn, landed.message, continuations.UPDATE, 88)
        continuations.finished(other, handoff.id, succeeded=True, outcome="updated")
        answerer = mock.Mock()

        with mock.patch.object(hosting, "connected", return_value=True):
            host._resumed_lifecycle(
                self.agent, hosting.Watching({}, {}, {}), answerer)

        answerer.resume.assert_not_called()
        self.assertEqual(continuations.REQUESTED,
                         continuations.one(other, handoff.id).continuation_state)

    def test_a_backup_snapshot_suppresses_transient_handoffs_without_changing_live_state(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        live = directory.records(self.agent)
        copied = self.home / "copied-state.db"
        shutil.copy2(live, copied)

        backups._a_snapshot(live, copied, lambda _said: None)

        with records.reading(copied) as conn:
            copied_state = conn.execute(
                "SELECT continuation_state FROM lifecycle_continuations WHERE id = ?",
                (handoff.id,),
            ).fetchone()[0]
        self.assertEqual(continuations.SUPPRESSED, copied_state)
        self.assertEqual(continuations.REQUESTED,
                         continuations.one(self.agent, handoff.id).continuation_state)

    def test_restore_suppresses_a_raw_fallback_copy_before_gateways_can_return(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        config.fill_in(paths.data())
        name = "2026-08-10T00-00-00Z"
        copied = paths.backups() / name
        copied.parent.mkdir(parents=True)
        shutil.copytree(paths.data(), copied)

        restored = backups.restore(name, paths.data(), paths.backups())

        self.assertIsNone(restored.settled)
        self.assertEqual(continuations.SUPPRESSED,
                         continuations.one(self.agent, handoff.id).continuation_state)

    def test_restore_never_follows_agent_records_link_outside_the_restored_tree(self):
        handoff = continuations.requested(
            self.agent, self.turn, self.message, continuations.UPDATE, 41)
        config.fill_in(paths.data())
        outside = self.home / "outside-state.db"
        with records.reading(directory.records(self.agent)) as source, \
                sqlite3.connect(str(outside)) as target:
            source.backup(target)
        name = "2026-08-10T00-00-00Z"
        copied = paths.backups() / name
        copied.parent.mkdir(parents=True)
        shutil.copytree(paths.data(), copied)
        copied_records = copied / "agents" / self.agent / directory.RECORDS
        copied_records.unlink()
        copied_records.symlink_to(outside)

        with self.assertRaisesRegex(backups.Refused, "link"):
            backups.restore(name, paths.data(), paths.backups())

        with sqlite3.connect(str(outside)) as conn:
            state = conn.execute(
                "SELECT continuation_state FROM lifecycle_continuations WHERE id = ?",
                (handoff.id,),
            ).fetchone()[0]
        self.assertEqual(continuations.REQUESTED, state)


if __name__ == "__main__":
    unittest.main()
