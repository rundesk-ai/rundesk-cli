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

import json
import unittest

import support
from rundesk.agents import directory, records
from rundesk.exits import FAILED, OK, USAGE
from rundesk.providers import kept

STAND_IN = str(support.CHECKOUT / "tests" / "samples" / "a-stand-in")


class Turns(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, STAND_IN)

    def a_stand_in_that(self, **how):
        records.stated(directory.records(self.agent), {"agent_settings": json.dumps(how)})

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
        self.a_stand_in_that(crash_without_finishing=True)
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
        self.a_stand_in_that(fail_with="signed_out")
        self.a_turn()
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertIn("did not answer", out)
        self.assertIn("will not clear on its own", out)

    def test_a_retryable_failure_says_the_other_thing(self):
        self.a_stand_in_that(fail_with="rate_limited")
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
        self.assertEqual((0, 0), self._counters(1))

    def test_a_record_this_release_never_heard_of_is_counted_and_kept(self):
        """**Kept, and shown to nobody.** A line this release cannot read must not vanish quietly —
        that is the difference between visible drift and records silently going missing."""
        self.a_stand_in_that(say_something_unknown=True)
        self.a_turn()
        self.assertGreater(self._counters(1)[0], 0)
        code, out, _err = self.rundesk("turns", self.agent, "1")
        self.assertEqual(OK, code)
        self.assertIn("unknown", out)

    def _counters(self, turn):
        row = kept.get_turn(self.agent, turn)
        return row["unknown_records"], row["lost_records"]


if __name__ == "__main__":
    unittest.main()
