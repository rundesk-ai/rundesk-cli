"""One turn, start to settled.

Every case drives the real path against `tests/samples/a-stand-in`, which is a whole adapter written
to the same contract a vendor's is — it simply has no vendor behind it, so nothing here needs an
account, a token or a network. What it does is set by `RUNDESK_SETTINGS`, so one program covers every
shape a turn has to survive.

Run directly: `python3 tests/test_providers_turns.py`
"""

import contextlib
import json
import threading
import time
import unittest
from unittest import mock

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.commands import automatic_updates
from rundesk.core import paths
from rundesk.providers import adapters, instructions, kept, protocol, turns
from rundesk.utils import locking

PATIENCE = 15.0


class WithAnAgent(support.Isolated):
    def setUp(self):
        super().setUp()
        self.agent = "ava"
        directory.made(self.agent, support.A_STAND_IN)

    def asking(self, said: str = "what changed today?", **also) -> turns.Request:
        landed = arriving.recorded("ava", "discord", "ops", "2207", said)
        return turns.Request(agent="ava", prompt=said, conversation=landed.conversation,
                             source=arriving.FROM_CHANNEL, place="ops", **also)

    def run_turn(self, request=None, **also):
        return turns.run(request or self.asking(), **also)


class ATurnThatAnswers(WithAnAgent):
    def test_it_is_recorded_as_done_and_says_what_the_brain_said(self):
        got = self.run_turn()
        self.assertEqual(got.turn_status, kept.DONE)
        self.assertTrue(got.worked)
        self.assertIn("what changed today?", got.reply)

    def test_what_it_did_is_written_in_the_order_it_happened(self):
        got = self.run_turn()
        said = [one["record_type"] for one in kept.list_turn_records("ava", got.turn)]
        self.assertEqual(said, ["instructions", "sent", "think", "tool", "result", "limit",
                                "usage", "done"])

    def test_what_it_said_is_one_message_and_never_one_record_per_fragment(self):
        """A row per fragment is a history nobody can read back and a search matching half a
        sentence."""
        got = self.run_turn()
        self.assertNotIn("text", [one["record_type"]
                                  for one in kept.list_turn_records("ava", got.turn)])
        said = arriving.messages("ava", 1)
        answers = [one for one in said if one["author"] == arriving.BY_AGENT]
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["turn_id"], got.turn)

    def test_an_unattended_turn_delivers_only_its_last_complete_response(self):
        """Activity may exist in the stream, but it is not the schedule or caller's report."""
        for situation in (instructions.SCHEDULE_TO_AGENT, instructions.AGENT_TO_AGENT):
            with self.subTest(situation=situation[:24]):
                self.a_stand_in_told(self.agent, remarks=["checking the fixture"],
                                     also_did="read")
                got = self.run_turn(self.asking(situation=situation))
                self.assertNotIn("checking the fixture", got.reply)
                self.assertIn("You asked:", got.reply)

    def test_unattended_activity_without_a_final_report_is_not_success(self):
        self.a_stand_in_told(self.agent, remarks=["checking the fixture"], also_did="read",
                             omit_final_response=True)
        got = self.run_turn(self.asking(situation=instructions.SCHEDULE_TO_AGENT))
        self.assertEqual(kept.FAILED, got.turn_status)
        self.assertEqual("", got.reply)
        self.assertEqual(turns.NOTHING_SAID, got.failure_message)

    def test_an_unattended_file_without_a_final_report_is_not_success(self):
        for situation in (instructions.SCHEDULE_TO_AGENT, instructions.AGENT_TO_AGENT):
            with self.subTest(situation=situation[:24]):
                self.a_stand_in_told(self.agent, made_a_file_and_said_nothing=True)
                got = self.run_turn(self.asking(situation=situation))
                self.assertEqual(kept.FAILED, got.turn_status)
                self.assertEqual("", got.reply)
                self.assertEqual(turns.NOTHING_SAID, got.failure_message)

    def test_a_person_facing_file_without_text_remains_an_answer(self):
        self.a_stand_in_told(self.agent, made_a_file_and_said_nothing=True)
        got = self.run_turn()
        self.assertEqual(kept.DONE, got.turn_status)
        self.assertTrue(got.files)

    def test_a_person_facing_turn_keeps_its_interactive_answer_text(self):
        self.a_stand_in_told(self.agent, remarks=["checking the fixture"], also_did="read")
        got = self.run_turn()
        self.assertIn("checking the fixture", got.reply)

    def test_the_four_billed_quantities_are_written_apart(self):
        row = kept.get_turn("ava", self.run_turn().turn)
        self.assertEqual([row["input_tokens"], row["output_tokens"],
                          row["cache_read_tokens"], row["cache_write_tokens"]],
                         [20, 1510, 302567, 17453])
        self.assertEqual(row["usage_reported"], 1)

    def test_the_model_that_actually_answered_is_recorded_and_not_the_one_asked_for(self):
        got = self.run_turn()
        self.assertEqual(got.usage.model_name, "a-stand-in-1")

    def test_the_model_that_answered_reaches_the_records_and_not_only_the_outcome(self):
        """Read back a month later off the row, which is where anybody looks.

        The column was written once, at admission, from the model *asked for* — so a turn that
        asked for nothing and was answered by a real model recorded no model at all, and `rundesk
        turns` showed a dash on a turn whose usage record named one.
        """
        row = kept.get_turn("ava", self.run_turn().turn)
        self.assertEqual(row["model_name"], "a-stand-in-1")

    def test_a_brain_that_names_no_model_does_not_erase_the_one_that_was_asked_for(self):
        """A quiet brain must not take the record of what was asked for away with it."""
        self.a_stand_in_told(self.agent, say_nothing_and_finish=True)
        got = self.run_turn(self.asking(model_name="something-particular"))
        self.assertEqual(kept.get_turn("ava", got.turn)["model_name"], "something-particular")

    def test_a_prompt_too_long_to_keep_is_cut_and_marked_like_any_other_record(self):
        """**A prompt is not smaller for being rundesk's own.** Every record read off the brain is
        bounded; the two rundesk writes itself were not, so a schedule with a long one wrote an
        unbounded row every time the clock reached it."""
        got = self.run_turn(self.asking("x" * 20000))
        sent = [one for one in kept.list_turn_records(self.agent, got.turn)
                if one["record_type"] == "sent"]
        self.assertLess(len(sent[0]["event_data"]), 4100)
        self.assertIn("truncated", sent[0]["event_data"])

    def test_what_became_of_the_program_is_kept_apart_from_what_the_brain_said(self):
        self.assertEqual(kept.get_turn("ava", self.run_turn().turn)["exit_code"], 0)

    def test_a_watcher_sees_every_record_including_the_ones_not_written_as_records(self):
        seen = []
        self.run_turn(watching=seen.append)
        kinds = [one["type"] for one in seen]
        self.assertIn("text", kinds)
        self.assertIn("tool", kinds)
        self.assertIn("done", kinds)

    def test_a_watcher_that_raises_is_its_own_problem_and_never_the_turns(self):
        def refuses(_one):
            raise RuntimeError("this watcher is broken")

        self.assertEqual(self.run_turn(watching=refuses).turn_status, kept.DONE)

    def test_agent_records_stay_reachable_while_the_provider_process_runs(self):
        """A provider tool may invoke `rundesk messages` during its turn.

        SQLite WAL readers need the shared-memory sidecar. Some provider sandboxes may read the
        agent directory but not create that sibling, so the gateway keeps one read connection open
        while the provider runs rather than leaving the documented history command unusable.
        """
        opened = 0
        reading = turns.records.reading
        talking = turns.adapters.talking_to

        @contextlib.contextmanager
        def tracked(at):
            nonlocal opened
            with reading(at) as conn:
                opened += 1
                try:
                    yield conn
                finally:
                    opened -= 1

        def while_reachable(*args, **kwargs):
            self.assertGreater(opened, 0, "provider started without reachable WAL sidecars")
            return talking(*args, **kwargs)

        with mock.patch.object(turns.records, "reading", tracked), \
                mock.patch.object(turns.adapters, "talking_to", side_effect=while_reachable):
            got = self.run_turn()

        self.assertEqual(kept.DONE, got.turn_status)
        self.assertEqual(0, opened)


class WhatWasSentIsProvableAfterwards(WithAnAgent):
    def test_the_instructions_are_fingerprinted_onto_the_turn_before_anything_starts(self):
        row = kept.get_turn("ava", self.run_turn().turn)
        self.assertEqual(len(row["instructions_sha256"]), 64)
        self.assertGreater(row["instructions_bytes"], 0)

    def test_the_layers_that_were_composed_are_in_the_account(self):
        got = self.run_turn()
        first = kept.list_turn_records("ava", got.turn)[0]
        self.assertEqual(first["record_type"], turns.INSTRUCTIONS)
        said = json.loads(first["event_data"])
        self.assertEqual([one["name"] for one in said["layers"]], ["core", "situation"])
        self.assertEqual("", said["team"])

    def test_team_state_is_not_read_when_a_named_handoff_cannot_be_used(self):
        requests = [
            self.asking(situation=instructions.AGENT_TO_AGENT, caller_agent="bob"),
            self.asking(access_mode=protocol.ACCESS_READ),
        ]
        for request in requests:
            with self.subTest(situation=request.situation[:20], access=request.access_mode):
                with mock.patch.object(turns.team, "for_agent",
                                       side_effect=AssertionError("team was inspected")):
                    got = self.run_turn(request)
                record = kept.list_turn_records("ava", got.turn)[0]
                said = json.loads(record["event_data"])
                self.assertNotIn("agents", [one["name"] for one in said["layers"]])
                self.assertEqual("", said["team"])

    def test_a_scheduled_work_turn_records_the_team_it_was_shown(self):
        listed = "- **bob** — verifies releases · skills: reviewing-code"
        with mock.patch.object(turns.team, "for_agent", return_value=listed) as looked:
            got = self.run_turn(self.asking(situation=instructions.SCHEDULE_TO_AGENT,
                                            schedule_name="nightly"))
        looked.assert_called_once_with("ava")
        record = kept.list_turn_records("ava", got.turn)[0]
        said = json.loads(record["event_data"])
        self.assertIn("agents", [one["name"] for one in said["layers"]])
        self.assertEqual(listed, said["team"])

    def test_a_person_facing_work_turn_records_the_team_it_was_shown(self):
        listed = "- **bob** — verifies releases · skills: reviewing-code"
        with mock.patch.object(turns.team, "for_agent", return_value=listed) as looked:
            got = self.run_turn()
        looked.assert_called_once_with("ava")
        record = kept.list_turn_records("ava", got.turn)[0]
        said = json.loads(record["event_data"])
        self.assertIn("agents", [one["name"] for one in said["layers"]])
        self.assertEqual(listed, said["team"])

    def test_what_was_asked_is_written_before_the_brain_is_started(self):
        got = self.run_turn()
        sent = [one for one in kept.list_turn_records("ava", got.turn)
                if one["record_type"] == turns.SENT]
        self.assertEqual(json.loads(sent[0]["event_data"])["text"], "what changed today?")

    def test_what_the_brain_itself_printed_is_kept_where_the_turn_says_it_is(self):
        """Without this, rundesk sees what the *adapter* reported and never what the brain said."""
        got = self.run_turn()
        row = kept.get_turn("ava", got.turn)
        raw = adapters.raw_of("ava", 1).read_text(encoding="utf-8")
        self.assertEqual(row["raw_offset_start"], 0)
        self.assertEqual(row["raw_offset_end"], len(raw.encode("utf-8")))
        self.assertIn("what changed today?", raw)


class OneTurnAtATimeInOneConversation(WithAnAgent):
    def test_an_update_sees_the_kernel_claim_before_the_unfinished_row_exists(self):
        """Deterministically occupy run's claim-to-row gap and make the updater inspect it."""
        request = self.asking()
        before_row = threading.Event()
        let_the_row_land = threading.Event()
        answered = []
        adding = turns.kept.add_turn

        def paused(*args, **kwargs):
            before_row.set()
            let_the_row_land.wait(PATIENCE)
            return adding(*args, **kwargs)

        reason = ""
        running = None
        try:
            with mock.patch.object(turns.kept, "add_turn", side_effect=paused):
                running = threading.Thread(
                    target=lambda: answered.append(turns.run(request)), daemon=True)
                running.start()
                self.assertTrue(before_row.wait(PATIENCE), "the turn never reached the row gap")
                self.assertEqual([], kept.list_unfinished_turns(self.agent))
                with locking.only_one(paths.work_admission_lock(), waiting=0):
                    reason = automatic_updates._busy_reason()
        finally:
            let_the_row_land.set()
            if running is not None:
                running.join(PATIENCE)
        self.assertIn("active provider turn", reason)
        self.assertFalse(running.is_alive(), "the turn did not finish after the row gap was released")
        self.assertEqual(1, len(answered))

    def test_the_claim_is_held_while_a_turn_runs(self):
        request = self.asking()
        holding = threading.Event()
        answered = []

        def slowly(_one):
            holding.set()
            time.sleep(0.4)

        running = threading.Thread(
            target=lambda: answered.append(turns.run(request, watching=slowly)), daemon=True)
        running.start()
        self.assertTrue(holding.wait(PATIENCE))
        self.assertTrue(turns.busy("ava", request.conversation))
        running.join(PATIENCE)
        self.assertEqual(answered[0].turn_status, kept.DONE)

    def test_a_second_turn_in_a_busy_conversation_is_refused_and_never_queued(self):
        request = self.asking()
        with turns.claiming("ava", request.conversation):
            with self.assertRaises(turns.Busy):
                turns.run(request)

    def test_a_conversation_nothing_has_ever_answered_in_is_not_busy(self):
        self.assertFalse(turns.busy("ava", 99))

    def test_asking_whether_it_is_busy_does_not_make_the_lock(self):
        """A question that writes is a question that fails on a read-only disk."""
        turns.busy("ava", 99)
        self.assertFalse(adapters.lock_of("ava", 99).exists())

    def test_two_conversations_run_at_once(self):
        one = self.asking("first")
        two = turns.Request(agent="ava", prompt="second",
                            conversation=arriving.recorded(
                                "ava", "discord", "other", "2207", "second").conversation,
                            source=arriving.FROM_CHANNEL, place="other")
        with turns.claiming("ava", one.conversation):
            self.assertEqual(turns.run(two).turn_status, kept.DONE)


class WhenTheBrainDoesNotAnswer(WithAnAgent):
    def test_a_turn_that_produced_nothing_is_not_a_turn_that_worked(self):
        """Measured on a live gateway: `done ok:true`, four zero counters, fourteen milliseconds and
        nothing said — recorded as finished, and the question that caused it consumed."""
        self.a_stand_in_told(self.agent, say_nothing_and_finish=True)
        got = self.run_turn()
        self.assertEqual(got.turn_status, kept.FAILED)
        self.assertEqual(got.failure_message, turns.NOTHING_SAID)

    def test_a_brain_that_classified_its_own_failure_has_that_word_recorded(self):
        self.a_stand_in_told(self.agent, fail_with=protocol.SIGNED_OUT)
        got = self.run_turn()
        self.assertEqual(got.turn_status, kept.FAILED)
        self.assertEqual(got.failure_code, protocol.SIGNED_OUT)
        self.assertEqual(kept.get_turn("ava", got.turn)["failure_code"], protocol.SIGNED_OUT)

    def test_a_signed_out_brain_is_not_something_to_try_again(self):
        self.a_stand_in_told(self.agent, fail_with=protocol.SIGNED_OUT)
        got = self.run_turn()
        self.assertFalse(protocol.is_retryable(got.failure_code))
        self.assertTrue(protocol.needs_human_action(got.failure_code))

    def test_a_vendor_that_fell_over_is_something_to_try_again(self):
        self.a_stand_in_told(self.agent, fail_with=protocol.UPSTREAM_ERROR)
        self.assertTrue(protocol.is_retryable(self.run_turn().failure_code))

    def test_a_brain_that_stopped_without_saying_it_had_finished_is_stopped_and_not_done(self):
        """No `done` at all is the shape a killed adapter leaves, and nothing may declare such a turn
        over on the brain's behalf."""
        self.a_stand_in_told(self.agent, crash_without_finishing=True)
        got = self.run_turn()
        self.assertEqual(got.turn_status, kept.STOPPED)
        self.assertEqual(got.failure_code, protocol.CRASHED)

    def test_what_it_said_went_wrong_reaches_the_turn(self):
        self.a_stand_in_told(self.agent, crash_without_finishing=True)
        self.assertIn("fell over", self.run_turn().failure_message)

    def test_an_adapter_that_will_not_start_is_a_failure_and_not_a_traceback(self):
        self.a_stand_in_told(self.agent, refuse_to_start=True)
        got = self.run_turn()
        self.assertIn(got.turn_status, (kept.FAILED, kept.STOPPED))

    def test_a_provider_nothing_stands_behind_is_refused_before_anything_is_written(self):
        records.stated(directory.records("ava"), {"provider_name": "nothing-here"})
        with self.assertRaises(turns.NotRunnable):
            self.run_turn()
        self.assertEqual(kept.list_turns("ava"), [])


class WhatThisReleaseDidNotUnderstand(WithAnAgent):
    def test_it_is_kept_with_its_own_words_and_counted(self):
        """An adapter may be ahead of rundesk, and a vendor's change has to show as visible drift."""
        self.a_stand_in_told(self.agent, say_something_unknown=True)
        got = self.run_turn()
        unknown = [one for one in kept.list_turn_records("ava", got.turn)
                   if one["record_type"] == turns.UNKNOWN]
        self.assertEqual(len(unknown), 2)
        self.assertTrue(any("telepathy" in one["raw_line"] for one in unknown))
        self.assertEqual(kept.get_turn("ava", got.turn)["unknown_records"], 2)

    def test_a_turn_that_understood_everything_counts_none(self):
        self.assertEqual(kept.get_turn("ava", self.run_turn().turn)["unknown_records"], 0)


class CarryingAConversationOn(WithAnAgent):
    def test_the_handle_is_kept_and_the_next_turn_is_told_it(self):
        first = self.run_turn()
        self.assertEqual(kept.get_turn("ava", first.turn)["session_resumed"], 0)
        again = turns.run(turns.Request(agent="ava", prompt="and now?", conversation=1,
                                        source=arriving.FROM_CHANNEL, place="ops"))
        self.assertEqual(kept.get_turn("ava", again.turn)["session_resumed"], 1)

    def test_asking_for_a_fresh_one_does_not_carry_it(self):
        self.run_turn()
        again = turns.run(turns.Request(agent="ava", prompt="and now?", conversation=1,
                                        fresh=True, source=arriving.FROM_CHANNEL, place="ops"))
        self.assertEqual(kept.get_turn("ava", again.turn)["session_resumed"], 0)

    def test_changed_instructions_start_fresh_and_the_same_instructions_resume(self):
        first = self.asking(additions=(("owner", "first rule"),))
        self.run_turn(first)
        changed = self.asking(additions=(("owner", "different rule"),))
        fresh = self.run_turn(changed)
        same = self.run_turn(self.asking(additions=(("owner", "different rule"),)))
        self.assertEqual(kept.get_turn("ava", fresh.turn)["session_resumed"], 0)
        self.assertEqual(kept.get_turn("ava", same.turn)["session_resumed"], 1)

    def test_a_stale_handle_does_not_return_after_a_changed_instruction_turn_failed(self):
        self.run_turn(self.asking(additions=(("owner", "first rule"),)))
        self.a_stand_in_told(self.agent, crash_without_finishing=True)
        failed = self.run_turn(self.asking(additions=(("owner", "different rule"),)))
        self.a_stand_in_told(self.agent)
        after = self.run_turn(self.asking(additions=(("owner", "different rule"),)))
        self.assertEqual(kept.get_turn("ava", failed.turn)["session_resumed"], 0)
        self.assertEqual(kept.get_turn("ava", after.turn)["session_resumed"], 0)


class SayingSomethingIntoARunningTurn(WithAnAgent):
    def test_a_word_reaches_a_brain_that_said_it_can_be_steered(self):
        self.a_stand_in_told(self.agent, steer=True)
        got = self.run_turn(saying=["stop at five"])
        self.assertIn("heard stop at five", got.reply)

    def test_what_was_said_mid_turn_is_written_down_before_it_is_sent(self):
        self.a_stand_in_told(self.agent, steer=True)
        got = self.run_turn(saying=["stop at five"])
        sent = [json.loads(one["event_data"]) for one in kept.list_turn_records("ava", got.turn)
                if one["record_type"] == turns.SENT]
        self.assertTrue(any(one.get("mid_turn") and one["text"] == "stop at five" for one in sent))

    def test_a_brain_that_cannot_be_steered_still_answers(self):
        got = self.run_turn(saying=["this will not reach it"])
        self.assertEqual(got.turn_status, kept.DONE)

    def test_an_attended_iterator_left_open_does_not_block_provider_settlement(self):
        """The terminal owns this iterator, so the provider ending cannot wait for its next word."""
        self.a_stand_in_told(self.agent, steer=True, say_nothing_and_finish=True)
        released = threading.Event()

        def still_open():
            released.wait(PATIENCE)
            if False:
                yield "never"

        began = time.monotonic()
        try:
            got = self.run_turn(saying=still_open())
        finally:
            released.set()

        self.assertLess(time.monotonic() - began, 3.0)
        self.assertEqual(kept.FAILED, got.turn_status)


class DurableGuidanceIntoARunningTurn(WithAnAgent):
    class Stream:
        def __init__(self, accepts=True, raises=False):
            self.accepts = accepts
            self.raises = raises
            self.lines = []

        def say(self, line):
            self.lines.append(line)
            if self.raises:
                raise OSError("the provider pipe closed")
            if isinstance(self.accepts, list):
                return self.accepts.pop(0)
            return self.accepts

        def no_more(self):
            pass

        def records(self):
            return iter(())

        def stop(self):
            pass

    def admitted(self):
        landed = arriving.recorded_for_a_delegation("ava", "bob", 12, "audit it")
        turn = kept.add_turn("ava", {
            "conversation_id": landed.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": protocol.ACCESS_WORK,
        })
        arriving.handled_by_turn("ava", landed.conversation, (landed.message,), turn)
        return landed, turn

    def guidance(self, body="GUIDANCE=EMBER-284"):
        return arriving.recorded_for_a_delegation("ava", "bob", 12, body)

    def test_a_delegated_provider_turn_incorporates_guidance_written_while_it_runs(self):
        self.a_stand_in_told(self.agent, steer=True, finish_after_steers=1)
        brief = arriving.recorded_for_a_delegation("ava", "bob", 12, "audit it")
        request = turns.Request(
            agent="ava", prompt="audit it", conversation=brief.conversation,
            situation=instructions.AGENT_TO_AGENT, caller_agent="bob",
            source=arriving.FROM_AGENT, place="bob/12",
            inbound_messages=(brief.message,))
        answered = []
        running = threading.Thread(
            target=lambda: answered.append(turns.run(request)), daemon=True)
        running.start()
        self.assertTrue(support.waited_until(
            lambda: turns.busy("ava", brief.conversation), PATIENCE))

        guidance = self.guidance()

        running.join(PATIENCE)
        self.assertFalse(running.is_alive(), "the delegated turn did not settle after its steer")
        self.assertEqual(1, len(kept.list_turns("ava")))
        self.assertIn("GUIDANCE=EMBER-284", answered[0].reply)
        self.assertEqual(
            answered[0].turn,
            next(one for one in arriving.messages("ava", brief.conversation)
                 if one["id"] == guidance.message)["turn_id"])

    def test_a_durable_words_feeder_is_a_required_settlement_barrier(self):
        landed, turn = self.admitted()
        words = turns.Words("ava", landed.conversation, turn, caller_agent="bob")
        stream = self.Stream()

        class Feeder:
            joined = None

            def join(inner, *args, **kwargs):
                inner.joined = (args, kwargs)

        feeder = Feeder()
        with mock.patch.object(turns.adapters, "talking_to", return_value=stream), \
                mock.patch.object(turns, "_speaking", return_value=feeder):
            turns._the_brain(
                turns.Request(agent="ava", prompt="audit it", conversation=landed.conversation),
                support.A_STAND_IN, {}, turn, 0, {"steer": True}, None, words.each(), words)

        self.assertEqual(((), {}), feeder.joined)

    def test_pending_guidance_is_picked_up_by_the_active_turn_without_a_gateway_sweep(self):
        landed, turn = self.admitted()
        words = turns.Words("ava", landed.conversation, turn, caller_agent="bob")
        received = []
        speaking = threading.Thread(target=lambda: received.append(next(words.each())), daemon=True)
        speaking.start()

        guidance = self.guidance()

        speaking.join(2)
        words.close()
        self.assertFalse(speaking.is_alive(), "the active turn never noticed durable guidance")
        self.assertEqual("GUIDANCE=EMBER-284", received[0].text)
        self.assertEqual((guidance.message,), received[0].messages)
        self.assertEqual(turn, arriving.messages("ava", landed.conversation)[-1]["turn_id"])

    def test_multiple_pending_messages_are_claimed_oldest_first_in_one_bounded_pickup(self):
        landed, turn = self.admitted()
        first = self.guidance("first blast")
        second = self.guidance("second blast")
        words = turns.Words("ava", landed.conversation, turn, caller_agent="bob")

        guidance = next(words.each())

        words.close()
        self.assertEqual("first blast\n\nsecond blast", guidance.text)
        self.assertEqual((first.message, second.message), guidance.messages)

    def test_guidance_is_claimed_by_the_active_turn_before_it_is_queued(self):
        landed, turn = self.admitted()
        guidance = self.guidance()
        words = turns.Words("ava", landed.conversation, turn)
        with turns._reachable("ava", landed.conversation, words):
            self.assertTrue(turns.also_say(
                "ava", landed.conversation, "GUIDANCE=EMBER-284", (guidance.message,)))
        self.assertEqual(
            turn, arriving.messages("ava", landed.conversation)[-1]["turn_id"])

    def test_a_provider_refusal_or_exception_releases_every_claimed_unsent_batch(self):
        for failing in (self.Stream(False), self.Stream(raises=True)):
            with self.subTest(raises=failing.raises):
                landed, turn = self.admitted()
                first = self.guidance("first blast")
                second = self.guidance("second blast")
                words = turns.Words("ava", landed.conversation, turn)
                self.assertTrue(words.say("first blast", (first.message,)))
                self.assertTrue(words.say("second blast", (second.message,)))

                speaking = turns._speaking(
                    "ava", turn, failing, words.each(), reachable=words)
                speaking.join(2)

                pending = arriving.messages("ava", landed.conversation)[-2:]
                self.assertEqual([None, None], [one["turn_id"] for one in pending])
                self.assertFalse(words.open)
                lost = [one for one in kept.list_turn_records("ava", turn)
                        if one["record_type"] == turns.LOST]
                self.assertEqual(1, len(lost))

    def test_a_duplicate_claim_is_refused_without_queueing_the_message_twice(self):
        landed, turn = self.admitted()
        guidance = self.guidance()
        words = turns.Words("ava", landed.conversation, turn)
        self.assertTrue(words.say("GUIDANCE=EMBER-284", (guidance.message,)))
        with self.assertRaises(records.Unreadable):
            words.say("GUIDANCE=EMBER-284", (guidance.message,))
        self.assertEqual(1, len(words.words))

    def test_a_later_refusal_does_not_release_a_batch_the_provider_already_accepted(self):
        landed, turn = self.admitted()
        first = self.guidance("first blast")
        second = self.guidance("second blast")
        words = turns.Words("ava", landed.conversation, turn)
        self.assertTrue(words.say("first blast", (first.message,)))
        self.assertTrue(words.say("second blast", (second.message,)))

        speaking = turns._speaking(
            "ava", turn, self.Stream([True, False]), words.each(), reachable=words)
        speaking.join(2)

        messages = arriving.messages("ava", landed.conversation)[-2:]
        self.assertEqual([turn, None], [one["turn_id"] for one in messages])

    def test_guidance_that_missed_the_active_turn_stays_pending(self):
        landed, turn = self.admitted()
        guidance = self.guidance()
        words = turns.Words("ava", landed.conversation, turn)
        with turns._reachable("ava", landed.conversation, words):
            words.close()
            self.assertFalse(turns.also_say(
                "ava", landed.conversation, "GUIDANCE=EMBER-284", (guidance.message,)))
        self.assertIsNone(arriving.messages("ava", landed.conversation)[-1]["turn_id"])


class AReasonForFailingOnATurnThatWorked(WithAnAgent):
    """**The brain is the one thing that knows whether its turn worked.**

    `failure_code` belongs on a `done` that says `ok: false`; a word arriving beside `ok: true` is
    an adapter breaking the contract. Read as a failure it inverts the answer — measured against a
    real adapter, an owner was told `FAILED — it did not answer` on the line directly above the
    answer it had given, and the ledger said `failed` for a turn that was delivered.
    """

    def setUp(self):
        support.Isolated.setUp(self)
        self.agent = "ava"
        brain = self.home / "a-turn-that-worked-oddly"
        brain.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "if '--capabilities' in sys.argv[1:]:\n"
            "    print(json.dumps({'tools': True})); raise SystemExit(0)\n"
            "sys.stdin.read()\n"
            "for one in ({'type': 'text', 'text': 'the answer is 41', 'whole': True},\n"
            "            {'type': 'done', 'ok': True, 'failure_code': 'upstream_error',\n"
            "             'failure_message': 'the vendor said no'}):\n"
            "    sys.stdout.write(json.dumps(one) + '\\n'); sys.stdout.flush()\n",
            encoding="utf-8")
        brain.chmod(0o755)
        directory.made(self.agent, str(brain))

    def test_the_turn_is_recorded_as_done(self):
        got = self.run_turn()
        self.assertEqual(kept.DONE, got.turn_status,
                         "a turn the brain said worked was recorded as failed")
        self.assertTrue(got.worked)

    def test_the_word_is_dropped_rather_than_acted_on(self):
        """Kept on the row it would read as a failure from, which is what `ask` and a channel
        both decide from."""
        got = self.run_turn()
        self.assertIsNone(got.failure_code)
        self.assertIn("the answer is 41", got.reply)

    def test_a_reason_in_prose_alone_is_dropped_too(self):
        """**Both fields, not only the word.** `protocol.failure_code` answers `None` for a word
        this release does not know as well as for one never sent, so an adapter contradicting itself
        in prose alone — or with a word rundesk dropped — would otherwise leave a reason for failing
        sitting on a turn recorded as done, which is what every surface reads."""
        brain = self.home / "a-turn-that-worked-and-complained"
        brain.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "if '--capabilities' in sys.argv[1:]:\n"
            "    print(json.dumps({'tools': True})); raise SystemExit(0)\n"
            "sys.stdin.read()\n"
            "for one in ({'type': 'text', 'text': 'the answer is 41', 'whole': True},\n"
            "            {'type': 'done', 'ok': True,\n"
            "             'failure_code': 'a-word-nobody-here-knows',\n"
            "             'failure_message': 'something went wrong'}):\n"
            "    sys.stdout.write(json.dumps(one) + '\\n'); sys.stdout.flush()\n",
            encoding="utf-8")
        brain.chmod(0o755)
        directory.made("cole", str(brain))
        landed = arriving.recorded("cole", "discord", "ops", "2207", "what changed today?")
        got = turns.run(turns.Request(agent="cole", prompt="what changed today?",
                                      conversation=landed.conversation,
                                      source=arriving.FROM_CHANNEL, place="ops"))
        self.assertEqual(kept.DONE, got.turn_status)
        self.assertIsNone(got.failure_code)
        self.assertIsNone(got.failure_message)


class WhenADiagnosticRowCannotBeKept(WithAnAgent):
    """**The cheapest thing in the turn is the thing that gives way.**

    `kept.add_turn_record` opens a write transaction of its own for every record off the brain, so a
    store that will not take one threw straight out of the loop reading the stream — and what that
    cost was never the row it failed on. Measured, on a store made unwritable mid-stream: the
    brain's finished answer was never written, the turn settled as `stopped`, and on a channel the
    person was told "I could not answer that" for a turn that had worked.
    """

    def refusing(self, kind: str):
        """The store taking every record except one, which is what contention looks like."""
        keeping = kept.add_turn_record

        def one_it_will_not_take(agent, turn, record_type, *args, **also):
            if record_type == kind:
                raise records.Unreadable("the store went away mid-stream")
            return keeping(agent, turn, record_type, *args, **also)

        return mock.patch.object(turns.kept, "add_turn_record",
                                 side_effect=one_it_will_not_take)

    def test_the_answer_is_still_kept_and_the_turn_still_settles(self):
        with self.refusing("tool"):
            got = self.run_turn()
        self.assertEqual(got.turn_status, kept.DONE)
        self.assertIn("what changed today?", got.reply)
        self.assertEqual(kept.list_unfinished_turns("ava"), [],
                         "a row nobody could keep left the turn recorded as still working")

    def test_what_the_brain_said_reaches_the_conversation(self):
        """The half that is invisible from the ledger: a channel reads this, not the turn row."""
        with self.refusing("tool"):
            self.run_turn()
        said = [one["body"] for one in arriving.messages("ava", 1) if one["author"] == "agent"]
        self.assertTrue(said, "the brain answered and nothing was written down")

    def test_only_the_row_that_could_not_be_kept_is_missing(self):
        """Not a licence to lose the rest: every other record is still written in order."""
        with self.refusing("tool"):
            got = self.run_turn()
        keeping = [one["record_type"] for one in kept.list_turn_records("ava", got.turn)]
        self.assertNotIn("tool", keeping)
        self.assertEqual(keeping, ["instructions", "sent", "think", "result", "limit",
                                   "usage", "done"])


class ATurnIsAlwaysSettled(WithAnAgent):
    def test_nothing_is_left_recorded_as_still_working(self):
        self.run_turn()
        self.assertEqual(kept.list_unfinished_turns("ava"), [])

    def test_a_turn_taken_down_mid_flight_is_settled_as_stopped(self):
        """The path this exists for cannot be caught by the body it wraps: a gateway standing down
        takes the process with it, and a turn left `working` in an owner's records for ever is one
        `rundesk turns` goes on showing as in flight with nothing doing it."""
        request = self.asking()

        def stop_it(_one):
            raise KeyboardInterrupt("a gateway standing down")

        with self.assertRaises(KeyboardInterrupt):
            turns.run(request, watching=stop_it)
        self.assertEqual(kept.list_unfinished_turns("ava"), [],
                         "a turn was left recorded as still working with nothing doing it")
        self.assertEqual(kept.list_turns("ava")[0]["turn_status"], kept.STOPPED)

    def test_a_gateway_settles_an_abandoned_working_row_once_its_claim_is_free(self):
        conversation = self.asking().conversation
        turn = kept.add_turn(self.agent, {
            "conversation_id": conversation, "schedule_id": None, "schedule_name": None,
            "provider_name": support.A_STAND_IN, "model_name": None, "access_mode": "work",
            "provider_capabilities": "{}", "session_resumed": 0,
            "instructions_sha256": None, "instructions_bytes": None})

        self.assertEqual(1, turns.settle_abandoned(self.agent))
        self.assertEqual(kept.STOPPED, kept.get_turn(self.agent, turn)["turn_status"])

    def test_a_gateway_never_settles_a_working_row_while_its_kernel_claim_is_held(self):
        conversation = self.asking().conversation
        turn = kept.add_turn(self.agent, {
            "conversation_id": conversation, "schedule_id": None, "schedule_name": None,
            "provider_name": support.A_STAND_IN, "model_name": None, "access_mode": "work",
            "provider_capabilities": "{}", "session_resumed": 0,
            "instructions_sha256": None, "instructions_bytes": None})

        with turns.claiming(self.agent, conversation):
            self.assertEqual(0, turns.settle_abandoned(self.agent))
        self.assertEqual(kept.WORKING, kept.get_turn(self.agent, turn)["turn_status"])

    def test_gateway_shutdown_stops_and_waits_for_the_turns_this_process_owns(self):
        entered = threading.Event()

        def running():
            with turns._stoppable(self.agent, 1) as ours:
                entered.set()
                self.assertTrue(support.waited_until(lambda: ours.asked, PATIENCE))

        thread = threading.Thread(target=running)
        thread.start()
        self.assertTrue(entered.wait(PATIENCE))
        turns.stopping(self.agent, PATIENCE)
        thread.join(PATIENCE)
        self.assertFalse(thread.is_alive())

    def test_new_cannot_land_between_the_forget_check_and_session_save(self):
        request = self.asking()
        turn = kept.add_turn(self.agent, {
            "conversation_id": request.conversation, "schedule_id": None,
            "schedule_name": None, "provider_name": support.A_STAND_IN,
            "model_name": None, "access_mode": "work", "provider_capabilities": "{}",
            "session_resumed": 0, "instructions_sha256": None,
            "instructions_bytes": None})
        entered_save = threading.Event()
        release_save = threading.Event()
        real_save = kept.save_session

        def paused_save(*args):
            entered_save.set()
            self.assertTrue(release_save.wait(PATIENCE))
            real_save(*args)

        stream = mock.Mock(stop_reason="", stop_code=None)
        stream.outcome.return_value = mock.Mock(code=0)
        with turns._stoppable(self.agent, request.conversation) as ours, \
                mock.patch.object(kept, "save_session", side_effect=paused_save):
            settling = threading.Thread(target=lambda: turns._became(
                request, turn,
                [{"type": "done", "ok": True, "session_id": "late-session"}],
                stream, {"resume": True}, support.A_STAND_IN, 0, 0, ours=ours))
            settling.start()
            self.assertTrue(entered_save.wait(PATIENCE))
            forgetting = threading.Thread(target=lambda: turns.forget_when_done(
                self.agent, request.conversation))
            forgetting.start()
            release_save.set()
            settling.join(PATIENCE)
            forgetting.join(PATIENCE)

        self.assertFalse(settling.is_alive())
        self.assertFalse(forgetting.is_alive())
        self.assertIsNone(kept.get_session(
            self.agent, request.conversation, support.A_STAND_IN))


if __name__ == "__main__":
    unittest.main()
