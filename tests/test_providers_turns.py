"""One turn, start to settled.

Every case drives the real path against `tests/samples/a-stand-in`, which is a whole adapter written
to the same contract a vendor's is — it simply has no vendor behind it, so nothing here needs an
account, a token or a network. What it does is set by `RUNDESK_SETTINGS`, so one program covers every
shape a turn has to survive.

Run directly: `python3 tests/test_providers_turns.py`
"""

import json
import threading
import time
import unittest

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.providers import adapters, kept, protocol, turns

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


if __name__ == "__main__":
    unittest.main()
