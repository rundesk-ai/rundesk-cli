"""What an adapter may say, and what a turn's records add up to.

Every case is a list of dicts. Nothing here starts a program, opens a file or needs a brain — which
is the point: these readings are where the previous build's plausible-looking simpler versions were
wrong, and each one is now provable in a millisecond.

Run directly: `python3 tests/test_providers_protocol.py`
"""

import json
import unittest

import support
from rundesk.providers import protocol

#: Brains the seam must never learn. Spelled here rather than imported from anywhere, because a list
#: the code under test could supply is a list that agrees with a mistake in it.
VENDORS = ("claude", "anthropic", "codex", "openai", "grok", "gemini", "antigravity", "copilot")


def done(**also):
    return dict({"type": "done", "ok": True}, **also)


def text(said, whole=False):
    one = {"type": "text", "text": said}
    if whole:
        one["whole"] = True
    return one


class TheSeamNamesNoVendor(support.Isolated):
    """The rule the whole design rests on, checked rather than remembered."""

    def test_no_module_in_providers_names_a_brand(self):
        """A vendor's name in this package means the seam has already failed.

        Read off the files rather than off an import, so a module that would not import is a failure
        of this case too rather than a silent pass.
        """
        where = support.CHECKOUT / "src" / "rundesk" / "providers"
        for module in sorted(where.glob("*.py")):
            said = module.read_text(encoding="utf-8").lower()
            for vendor in VENDORS:
                with self.subTest(module=module.name, vendor=vendor):
                    self.assertNotIn(vendor, said,
                                     f"{module.name} names {vendor}; every fact about one brain "
                                     "belongs in that brain's own adapter")


class ReadingOneLine(support.Isolated):
    """Nothing an adapter emits may break a turn, and nothing unknown may be shown to anybody."""

    def test_a_record_this_release_knows_comes_back(self):
        self.assertEqual(protocol.understood('{"type": "done", "ok": true}'),
                         {"type": "done", "ok": True})

    def test_a_line_that_is_not_json_is_kept_and_shown_to_nobody(self):
        self.assertIsNone(protocol.understood("this is not a record"))

    def test_a_line_that_is_json_but_not_an_object_is_not_a_record(self):
        for said in ("[1, 2, 3]", '"a string"', "42", "null"):
            with self.subTest(said=said):
                self.assertIsNone(protocol.understood(said))

    def test_a_kind_this_release_has_never_heard_of_is_not_a_record(self):
        """An adapter may be ahead of this release, and must not have to wait for one."""
        self.assertIsNone(protocol.understood('{"type": "telepathy", "text": "hello"}'))

    def test_a_record_with_no_kind_at_all_is_not_one(self):
        self.assertIsNone(protocol.understood('{"text": "hello"}'))

    def test_nothing_it_is_given_raises(self):
        for said in ("", "   ", "{", "{}", '{"type": null}', "\x00"):
            with self.subTest(said=said):
                protocol.understood(said)


class SayingSomethingToARunningBrain(support.Isolated):
    def test_it_is_one_line_however_many_the_text_has(self):
        said = protocol.spoken("first\nsecond\nthird")
        self.assertEqual(said.count("\n"), 1)
        self.assertTrue(said.endswith("\n"))

    def test_the_text_survives_the_encoding(self):
        self.assertEqual(json.loads(protocol.spoken("first\nsecond"))["text"], "first\nsecond")

    def test_rundesks_own_context_is_carried_apart_from_the_persons_words(self):
        """Concatenating them would alter what the person is recorded as having said."""
        record = json.loads(protocol.spoken("stop at five", protocol.STEERING_CONTEXT))
        self.assertEqual(record["text"], "stop at five")
        self.assertEqual(record["context"], protocol.STEERING_CONTEXT)

    def test_no_context_leaves_the_field_out_rather_than_empty(self):
        self.assertNotIn("context", json.loads(protocol.spoken("stop at five")))


class WhatAnAdapterSaysItCanDo(support.Isolated):
    def test_absent_is_no_for_every_one_of_them(self):
        self.assertEqual(protocol.claimed({}),
                         dict.fromkeys(protocol.CAPABILITIES, False))

    def test_an_answer_that_is_not_an_object_can_do_nothing(self):
        for said in (None, "yes", 7, ["tools"]):
            with self.subTest(said=said):
                self.assertEqual(protocol.claimed(said),
                                 dict.fromkeys(protocol.CAPABILITIES, False))

    def test_every_question_is_answered_even_when_only_some_were_asked(self):
        got = protocol.claimed({"tools": True, "steer": True})
        self.assertEqual(set(got), set(protocol.CAPABILITIES))
        self.assertTrue(got["tools"])
        self.assertFalse(got["resume"])

    def test_anything_else_it_said_is_ignored_rather_than_refused(self):
        """An adapter reporting its own vendor version is answering a question we did not ask."""
        got = protocol.claimed({"tools": True, "version": "1.2.3"})
        self.assertNotIn("version", got)


class WhyATurnStopped(support.Isolated):
    """Auth, allowance, rate, context, the vendor's own fault, and ours."""

    def test_a_word_this_release_knows_is_carried(self):
        for word in protocol.BECAUSE:
            with self.subTest(word=word):
                self.assertEqual(protocol.because([done(ok=False, because=word)]), word)

    def test_a_word_from_a_newer_release_is_dropped_rather_than_stored(self):
        """One unknown member sitting silently in the column takes away the whole value of a closed
        set, which is that a reader can exhaust it."""
        self.assertIsNone(protocol.because([done(ok=False, because="quantum_flux")]))

    def test_nothing_is_inferred_from_the_prose_beside_it(self):
        """A word guessed from a failure message is wrong on the first vendor that rewords one."""
        said = [done(ok=False, why="401 Unauthorized: please run the login command")]
        self.assertIsNone(protocol.because(said))
        self.assertIn("401", protocol.why(said))

    def test_the_words_rundesk_may_write_itself_are_only_about_what_it_saw(self):
        for word in protocol.OBSERVED_HERE:
            with self.subTest(word=word):
                self.assertIn(word, protocol.BECAUSE)
        self.assertNotIn(protocol.SIGNED_OUT, protocol.OBSERVED_HERE)
        self.assertNotIn(protocol.RATE_LIMITED, protocol.OBSERVED_HERE)

    def test_only_the_transient_ones_are_worth_trying_again(self):
        again = {protocol.RATE_LIMITED, protocol.UPSTREAM_ERROR,
                 protocol.OFFLINE, protocol.CRASHED}
        for word in protocol.BECAUSE:
            with self.subTest(word=word):
                self.assertEqual(protocol.worth_trying_again(word), word in again)

    def test_an_unknown_word_is_never_worth_trying_again(self):
        """The safe way round: it might mean the card was declined."""
        self.assertFalse(protocol.worth_trying_again("quantum_flux"))
        self.assertFalse(protocol.worth_trying_again(None))

    def test_the_ones_a_person_has_to_settle_are_named(self):
        for word in (protocol.SIGNED_OUT, protocol.NO_ACCESS, protocol.NO_CREDIT):
            with self.subTest(word=word):
                self.assertTrue(protocol.needs_a_person(word))
                self.assertFalse(protocol.worth_trying_again(word))

    def test_being_rate_limited_is_not_something_a_person_settles(self):
        self.assertFalse(protocol.needs_a_person(protocol.RATE_LIMITED))


class WhetherTheTurnWorked(support.Isolated):
    def test_no_done_record_at_all_is_a_third_answer(self):
        """The shape a killed adapter leaves. Nothing may declare such a turn over on its behalf."""
        self.assertIsNone(protocol.finished([text("half a thought")]))

    def test_a_brain_that_said_no_is_told_apart_from_one_that_said_nothing(self):
        self.assertIs(protocol.finished([done(ok=False)]), False)
        self.assertIs(protocol.finished([done(ok=True)]), True)

    def test_a_turn_that_said_nothing_at_all_answered_nobody(self):
        """Measured on a live gateway: `done ok:true`, four zero counters, fourteen milliseconds,
        and nothing said — recorded as finished, and the question was consumed."""
        self.assertFalse(protocol.answered([done(), {"type": "usage", "input": 0, "output": 0}]))

    def test_whitespace_is_not_an_answer(self):
        self.assertFalse(protocol.answered([text("   \n  "), done()]))

    def test_a_file_is_an_answer_even_with_nothing_typed_about_it(self):
        self.assertTrue(protocol.answered([{"type": "file", "at": "/tmp/chart.png"}, done()]))

    def test_a_tool_call_is_not_an_answer(self):
        """Reading a file and thinking about it is work nobody receives."""
        self.assertFalse(protocol.answered([{"type": "tool", "id": "1", "did": "read"}, done()]))


class WhereTheConversationGotTo(support.Isolated):
    def test_the_handle_comes_off_the_record_that_ends_the_turn(self):
        self.assertEqual(protocol.resume_handle([done(session="thread-9")]), "thread-9")

    def test_an_empty_handle_is_no_handle(self):
        self.assertIsNone(protocol.resume_handle([done(session="")]))

    def test_a_handle_that_is_not_text_is_no_handle(self):
        self.assertIsNone(protocol.resume_handle([done(session=17)]))


class WhatATurnCost(support.Isolated):
    def test_no_usage_record_is_not_a_cost_of_nothing(self):
        """Zero and unknown are different answers, and a spend limit reading the first for the
        second would never fire."""
        cost = protocol.cost([done()])
        self.assertFalse(cost.reported)
        self.assertIsNone(cost.fresh)
        self.assertIsNone(cost.output)

    def test_a_usage_record_with_no_numbers_still_counts_as_reported(self):
        cost = protocol.cost([{"type": "usage"}, done()])
        self.assertTrue(cost.reported)
        self.assertIsNone(cost.fresh)

    def test_a_quantity_the_brain_could_not_tell_stays_unknown(self):
        """Summing an absent cached figure into zero says it read nothing from the cache."""
        cost = protocol.cost([{"type": "usage", "input": 20, "output": 5}, done()])
        self.assertEqual(cost.fresh, 20)
        self.assertIsNone(cost.cache_read)
        self.assertIsNone(cost.cache_write)

    def test_the_four_billed_quantities_are_never_folded_together(self):
        cost = protocol.cost([{"type": "usage", "input": 20, "output": 1510,
                               "cached": 302567, "written": 17453}, done()])
        self.assertEqual((cost.fresh, cost.output, cost.cache_read, cost.cache_write),
                         (20, 1510, 302567, 17453))

    def test_quantities_from_several_records_are_summed(self):
        cost = protocol.cost([{"type": "usage", "input": 10, "output": 1},
                              {"type": "usage", "input": 20, "output": 2}, done()])
        self.assertEqual((cost.fresh, cost.output), (30, 3))

    def test_how_big_the_conversation_is_takes_the_last_and_never_the_sum(self):
        """A level, not a quantity — it goes *down* when a conversation is compacted, which no
        running total can, so adding snapshots would invent a number nothing measured."""
        cost = protocol.cost([{"type": "usage", "session": 9200},
                              {"type": "usage", "session": 4100}, done()])
        self.assertEqual(cost.context, 4100)

    def test_a_boolean_is_not_a_count(self):
        cost = protocol.cost([{"type": "usage", "input": True, "output": 5}, done()])
        self.assertIsNone(cost.fresh)
        self.assertEqual(cost.output, 5)

    def test_only_a_model_that_answered_is_claimed(self):
        """A model requested is not a model measured."""
        self.assertIsNone(protocol.cost([{"type": "usage", "input": 1}, done()]).model)
        self.assertEqual(protocol.cost([{"type": "usage", "model": "m-1"}, done()]).model, "m-1")


class AccountStateIsNotAnOutcome(support.Isolated):
    def test_a_limit_is_carried_without_failing_the_turn(self):
        """A turn carrying one of these may have succeeded — it is news about the account."""
        said = [{"type": "limit", "left": 12, "resets_at": "2026-08-06T00:00:00Z"}, done()]
        self.assertEqual(len(protocol.limits(said)), 1)
        self.assertIs(protocol.finished(said), True)
        self.assertIsNone(protocol.because(said))


class SplittingWhatTheBrainSaid(support.Isolated):
    def test_fragments_join_with_nothing_between_them(self):
        said = [text("Look"), text("ing at the logs.")]
        self.assertEqual(protocol.thoughts(said), ["Looking at the logs."])

    def test_a_finished_thought_stands_alone(self):
        said = [text("I will look at the logs.", whole=True), text("Three files changed.",
                                                                  whole=True)]
        self.assertEqual(protocol.thoughts(said),
                         ["I will look at the logs.", "Three files changed."])

    def test_two_finished_thoughts_do_not_run_together(self):
        """An account read back `caught it running.The worker` before this existed."""
        said = [text("caught it running.", whole=True), text("The worker is fine.", whole=True)]
        self.assertEqual(protocol.reply(said), "caught it running.\n\nThe worker is fine.")

    def test_going_to_work_ends_a_thought_for_a_brain_that_marks_nothing(self):
        """`whole` is not a seam every adapter has: one shipped brain writes a token at a time and
        nothing in its stream ever restates it."""
        said = [text("Looking at the logs."), {"type": "tool", "id": "1", "did": "read"},
                {"type": "result", "id": "1", "ok": True}, text("Three files changed.")]
        self.assertEqual(protocol.thoughts(said),
                         ["Looking at the logs.", "Three files changed."])

    def test_a_result_alone_still_ends_a_thought(self):
        """A tool already over when this process heard of it arrives as a result with no call."""
        said = [text("one"), {"type": "result", "id": "1", "ok": True}, text("two")]
        self.assertEqual(protocol.thoughts(said), ["one", "two"])

    def test_a_brain_that_never_went_to_work_said_one_thing(self):
        said = [text("a"), text("b"), text("c")]
        self.assertEqual(protocol.thoughts(said), ["abc"])

    def test_the_closing_thought_is_the_last_one_and_not_the_whole_turn(self):
        said = [text("Looking at the logs."), {"type": "tool", "id": "1", "did": "read"},
                text("Three files changed.")]
        self.assertEqual(protocol.closing(said), "Three files changed.")

    def test_a_turn_that_said_nothing_closes_on_nothing(self):
        self.assertEqual(protocol.closing([done()]), "")

    def test_blank_lines_inside_a_thought_are_the_brains_and_are_kept(self):
        said = [text("first para\n\nsecond para", whole=True)]
        self.assertEqual(protocol.thoughts(said), ["first para\n\nsecond para"])

    def test_reasoning_is_split_by_the_same_rule_and_kept_apart_from_the_reply(self):
        said = [{"type": "think", "text": "the error is in the parser", "whole": True},
                text("It is the parser.", whole=True)]
        self.assertEqual(protocol.thoughts(said, kind="think"), ["the error is in the parser"])
        self.assertEqual(protocol.thoughts(said), ["It is the parser."])


class WhatTheBrainMade(support.Isolated):
    def test_only_what_it_said_it_made(self):
        """What a tool printed is not a promise that a file exists."""
        said = [{"type": "tool", "id": "1", "did": "make"},
                {"type": "file", "at": "/tmp/chart.png", "name": "chart.png"}, done()]
        self.assertEqual([one["name"] for one in protocol.files(said)], ["chart.png"])


class TheReadingsTakeAnyIterable(support.Isolated):
    def test_a_generator_does_not_raise_on_the_readings_that_look_backwards(self):
        """Reversing a generator raises, and it would raise only on the path where a turn had
        already gone wrong."""
        for reading in (protocol.finished, protocol.because, protocol.why,
                        protocol.resume_handle):
            with self.subTest(reading=reading.__name__):
                reading(one for one in [done(ok=False, because=protocol.CRASHED, why="fell over")])


if __name__ == "__main__":
    unittest.main()
