"""`rundesk turns` — the ledger, and one turn read whole.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case.

`rundesk messages` is what was *said*; this is what it *cost* and what became of it. The two are kept
apart because they are read for different reasons, and what this file protects is mostly the
difference between a number that is real and a number that is merely printed:

**A dash is not a zero.** A cost nobody measured and a cost of nothing are different answers, and a
ledger that showed them alike would not be a ledger.

**The four billed quantities stay apart.** They are billed at three different rates, so one total
would be a number that is true and misleading.

**The drift counters are the early warning.** `unknown` and `lost` are how a vendor moving under you
becomes visible before somebody notices an agent behaving oddly.

Run directly: `python3 tests/test_turns_command.py`
"""

import unittest

import support
from rundesk.agents import directory, records
from rundesk.exits import FAILED, OK, USAGE
from rundesk.providers import kept


class Turns(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, support.A_STAND_IN)

    def a_turn(self, asked="what changed today?", *more):
        code, _out, err = self.rundesk("ask", self.agent, asked, *more)
        return code, err


class Listing(Turns):

    def test_an_agent_that_has_taken_none_says_so_and_says_what_to_type(self):
        code, out, _err = self.rundesk("turns", self.agent)
        self.assertEqual(OK, code)
        self.assertIn("no turns yet", out)
        self.assertIn(f"rundesk ask {self.agent}", out)

    def test_each_turn_is_shown_newest_first_with_what_it_came_to(self):
        self.a_turn("the first")
        self.a_turn("the second")
        code, out, _err = self.rundesk("turns", self.agent)
        self.assertEqual(OK, code)
        self.assertLess(out.index("2"), out.index("1"))
        self.assertIn("done", out)

    def test_the_four_billed_quantities_are_shown_apart_and_never_summed(self):
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent)
        self.assertEqual(OK, code)
        for said in ("20in", "1510out", "302567cr", "17453cw"):
            self.assertIn(said, out)

    def test_a_turn_nobody_measured_shows_a_dash_and_never_a_zero(self):
        """A cost nobody reported and a cost of nothing are different answers."""
        self.a_stand_in_told(self.agent, crash_without_finishing=True)
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent)
        self.assertEqual(OK, code)
        self.assertIn("—", out)

    def test_it_can_be_narrowed_to_one_exchange(self):
        self.a_turn("the first")
        code, out, _err = self.rundesk("turns", self.agent, "--conversation", "9")
        self.assertEqual(OK, code)
        self.assertIn("no turns yet", out)

    def test_a_limit_that_is_not_a_count_is_the_command_line_being_wrong(self):
        code, _out, err = self.rundesk("turns", self.agent, "--limit", "0")
        self.assertEqual(USAGE, code)
        self.assertIn("at least 1", err)

    def test_an_agent_that_is_not_there_says_what_to_type(self):
        code, _out, err = self.rundesk("turns", "nobody")
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk agents", err)


class OneTurnWhole(Turns):

    def test_it_shows_what_the_turn_was_admitted_with(self):
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        for said in ("provider", "access", "resumed", "instructions"):
            self.assertIn(said, out)

    def test_it_shows_what_the_adapter_said_it_could_do_when_the_turn_ran(self):
        """Kept per turn, so *reported no tools* and *has no tools* stay distinguishable a month
        later — a distinction nothing can recover afterwards."""
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertIn("brain said", out)
        self.assertIn("tools", out)

    def test_it_says_which_model_was_asked_for_and_which_one_answered(self):
        """Two facts, and a ledger showing one of them could not say which it had."""
        self.a_stand_in_told(self.agent, model="the-one-that-ran")
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertEqual("provider default", self._said(out, "model asked for"))
        self.assertEqual("the-one-that-ran", self._said(out, "model reported"))

    def test_a_provider_that_reported_none_is_not_a_provider_that_was_given_none(self):
        """A provider choosing for itself and a provider that reported nothing are not one answer."""
        self.a_stand_in_told(self.agent, say_nothing_and_finish=True)
        self.a_turn("what changed today?", "--model", "asked-for-this")
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertEqual("asked-for-this", self._said(out, "model asked for"))
        self.assertEqual("—", self._said(out, "model reported"))

    def test_a_turn_that_chose_nothing_and_was_told_nothing_is_not_read_as_an_older_row(self):
        """**The marker decides, not the emptiness.** Both are blank here in exactly the way an
        older row is blank, and the honest answer is two of them rather than a sentence about a
        release that did not write this."""
        self.a_stand_in_told(self.agent, say_nothing_and_finish=True)
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertEqual("provider default", self._said(out, "model asked for"))
        self.assertEqual("—", self._said(out, "model reported"))
        self.assertNotIn("older release", out)

    def test_a_turn_an_older_release_wrote_is_shown_as_the_one_answer_it_has(self):
        """**Old rows are not reinterpreted.** One column held whichever of the two arrived last,
        and a surface that labelled it as either would be claiming something nobody recorded."""
        self.a_turn()
        with records.writing(directory.records(self.agent)) as conn:
            conn.execute("UPDATE turns SET model_name = 'either-of-them',"
                         " admitted_model_name = NULL, reported_model_name = NULL,"
                         " model_provenance_kept = 0 WHERE id = 1")

        code, out, _err = self.rundesk("turns", self.agent, "1")

        self.assertEqual(OK, code)
        self.assertNotIn("model asked for", out)
        self.assertIn("either-of-them", self._said(out, "model"))
        self.assertIn("older release", self._said(out, "model"))

    def _said(self, out, about):
        """What one line of the single-turn view answers, by the label in front of it."""
        line = next(one for one in out.splitlines() if one.startswith(about))
        return line[len(about):].strip()

    def test_every_record_is_shown_in_the_order_it_happened(self):
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        did = [line.split()[1] for line in out.splitlines()
               if line.startswith("2026-") and len(line.split()) > 1]
        self.assertEqual(["instructions", "sent", "think", "tool", "result", "limit",
                          "usage", "done"], did)

    def test_it_says_where_the_brains_own_words_are_and_which_bytes_are_this_turns(self):
        """Two integers instead of a file per turn. Without them the slice cannot be found again."""
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertIn("raw.jsonl", out)
        self.assertIn("bytes", out)

    def test_a_turn_that_failed_says_why_and_whether_waiting_will_help(self):
        self.a_stand_in_told(self.agent, fail_with="signed_out")
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertIn("did not answer", out)
        self.assertIn("will not clear on its own", out)

    def test_a_retryable_failure_says_the_other_thing(self):
        self.a_stand_in_told(self.agent, fail_with="rate_limited")
        self.a_turn()
        _code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertIn("later may work", out)

    def test_a_turn_that_is_not_there_fails_rather_than_printing_an_empty_shape(self):
        code, _out, err = self.rundesk("turns", self.agent, "9")
        self.assertEqual(FAILED, code)
        self.assertTrue(err.strip())


class TheDriftCounters(Turns):
    """How a vendor moving under you becomes visible."""

    def test_a_healthy_turn_reports_nothing_unknown_and_nothing_lost(self):
        self.a_turn()
        self.assertEqual((0, 0, 0), self._counters(1))

    def test_a_record_this_release_never_heard_of_is_counted_and_kept(self):
        """**Kept, and shown to nobody.** A line this release cannot read must not vanish quietly —
        that is the difference between visible drift and records silently going missing."""
        self.a_stand_in_told(self.agent, say_something_unknown=True)
        self.a_turn()
        self.assertGreater(self._counters(1)[0], 0)
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertIn("unknown", out)

    def test_a_word_rundesk_could_not_deliver_is_shown_apart_from_adapter_drift(self):
        """`LOST` is the adapter moving underneath rundesk. A steering word the provider would not
        take is rundesk's own trouble, and counting it as drift sends somebody after a vendor."""
        self.a_turn()
        kept.add_turn_record(self.agent, 1, kept.UNSENT,
                             {"unsent_count": 1, "reason": "it had already finished"})

        code, out, _err = self.rundesk("turns", self.agent)

        self.assertEqual(OK, code)
        self.assertIn("UNSENT", out)
        counters = next(one for one in out.splitlines() if one.startswith("1 ")).split()[-3:]
        self.assertEqual(["0", "0", "1"], counters)
        self.assertEqual((0, 0, 1), self._counters(1))

    def _counters(self, turn):
        row = kept.get_turn(self.agent, turn)
        return row["unknown_records"], row["lost_records"], row["unsent_records"]


class AnAgentWhoseCarryDidNotReachTheseColumns(Turns):
    """**A ledger is most worth reading on the agent whose migration went wrong.**

    One agent that cannot be carried does not stop the others, so an install can stand with an agent
    whose `turns` has none of `0013`'s columns. Reaching for one by name would take the whole listing
    down with a `KeyError` on exactly the agent somebody is trying to look into.
    """

    def as_an_older_release_left_it(self):
        with records.writing(directory.records(self.agent)) as conn:
            conn.execute("DROP TRIGGER IF EXISTS turn_records_after_insert")
            for column in ("model_provenance_kept", "unsent_records",
                           "reported_model_name", "admitted_model_name"):
                conn.execute(f"ALTER TABLE turns DROP COLUMN {column}")

    def test_the_listing_answers_and_says_it_has_no_count_rather_than_a_zero(self):
        self.a_turn()
        self.as_an_older_release_left_it()

        code, out, err = self.rundesk("turns", self.agent)

        self.assertEqual(OK, code, err)
        self.assertIn("UNSENT", out)
        counters = next(one for one in out.splitlines() if one.startswith("1 ")).split()[-3:]
        self.assertEqual(["0", "0", "—"], counters)

    def test_one_turn_whole_answers_with_the_one_model_column_it_has(self):
        self.a_turn()
        self.as_an_older_release_left_it()

        code, out, err = self.rundesk("turns", self.agent, "1")

        self.assertEqual(OK, code, err)
        self.assertIn("a-stand-in-1", out)
        self.assertNotIn("model asked for", out)


if __name__ == "__main__":
    unittest.main()
