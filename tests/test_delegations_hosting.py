"""What a delegated turn is actually told, and what the gateway's sweep decides.

**The case that matters most here is the prompt one.** Every other suite that renders the
delegation layer hands `caller_agent` in by hand, so all of them passed while the real pipeline
never set it — a delegated brain was told `{caller_agent} reads it and comes back to you`, five
times over, and nothing went red. What is proved here is the wiring those suites step over:
`hosting` knows who asked, and the name survives every hop to the built prompt.

Run directly: `python3 tests/test_delegations_hosting.py`
"""

import unittest

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.core import paths
from rundesk.delegations import hosting, kept
from rundesk.providers import instructions, turns


class WhatADelegatedTurnIsTold(support.Isolated):
    """The prompt, built the way a real turn builds it rather than with the variables filled by
    hand — which is the whole point, since filling them by hand is what hid the defect."""

    def built(self, **more):
        request = turns.Request(agent="bob", prompt="audit it", conversation=1,
                                trigger=instructions.ANOTHER_AGENT_ASKED, **more)
        return instructions.build(trigger=request.trigger,
                                  variables=turns._about(request, "a-stand-in"))

    def test_the_agent_that_asked_is_named(self):
        self.assertIn("ava, an agent on your team, handed you this task",
                      self.built(caller_agent="ava").text)

    def test_no_placeholder_survives_into_what_the_brain_reads(self):
        self.assertNotIn("{caller_agent}", self.built(caller_agent="ava").text)

    def test_a_turn_nobody_named_a_caller_for_shows_the_hole_rather_than_hiding_it(self):
        """`_filled` leaves an unmatched placeholder standing on purpose. That is what made the
        defect visible once anybody looked at a real prompt — and this case is what makes the
        wiring above provable rather than assumed."""
        self.assertIn("{caller_agent}", self.built().text)


class WhetherWorkIsWaitingOnUs(support.Isolated):
    """Read off the conversation rather than remembered. The gateway used to keep a list of ids it
    had already started, which meant a delegation carried on with more work was one it would never
    look at again."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("bob", "a-stand-in")
        self.landed = arriving.recorded_for_a_delegation("bob", "ava", 12, "audit it")

    def a_turn(self, status):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, "a-stand-in", "work", status, "2026-08-06T00:00:00Z"))
            return conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]

    def waiting(self):
        return hosting._is_waiting_on_us("bob", self.landed.conversation, "ava")

    def test_a_brief_nobody_has_answered_is_waiting(self):
        self.assertTrue(self.waiting())

    def test_work_already_going_is_not_waiting(self):
        """Otherwise the next beat starts a second turn for the same work — measured, one
        delegation and two turns, the second resuming the first's session and answering again."""
        self.a_turn(hosting.WORKING)
        self.assertFalse(self.waiting())

    def test_an_answer_already_given_is_not_waiting(self):
        turn = self.a_turn("done")
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", 12),
                               "here is what I found", turn=turn)
        self.assertFalse(self.waiting())

    def test_and_more_work_after_that_answer_is_waiting_again(self):
        """What `resume` does. The delegation is the same one, so a gateway that remembered having
        started it would never pick this up."""
        turn = self.a_turn("done")
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", 12),
                               "here is what I found", turn=turn)
        arriving.recorded_for_a_delegation("bob", "ava", 12, "also check retention")
        self.assertTrue(self.waiting())

    def test_a_conversation_that_is_not_there_is_not_waiting_rather_than_raising(self):
        self.assertFalse(hosting._is_waiting_on_us("bob", 999, "ava"))


class WhatCountsAsTheAnswer(support.Isolated):
    """Only a reply newer than the ask. Without that clause a carried-on delegation is answered
    instantly with the reply to the previous task — measured, and it left the further work
    untouched while the row read as collected."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("bob", "a-stand-in")
        arriving.recorded_for_a_delegation("bob", "ava", 12, "audit it")

    def answered_with(self, said, status="done"):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (1, ?, ?, ?, ?)",
                ("a-stand-in", "work", status, "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", 12),
                               said, turn=turn)

    def what(self):
        return hosting._what_they_answered("bob", "ava", 12)

    def test_nothing_before_it_has_answered(self):
        self.assertIsNone(self.what())

    def test_the_reply_once_the_turn_is_terminal(self):
        self.answered_with("here is what I found")
        self.assertEqual("here is what I found", self.what())

    def test_nothing_while_the_turn_is_still_going(self):
        self.answered_with("half a thought", status=hosting.WORKING)
        self.assertIsNone(self.what())

    def test_a_reply_older_than_the_newest_ask_is_not_an_answer_to_it(self):
        self.answered_with("here is what I found")
        arriving.recorded_for_a_delegation("bob", "ava", 12, "also check retention")
        self.assertIsNone(self.what())

    def test_a_turn_that_said_nothing_answers_a_sentence_rather_than_silence(self):
        """Silence delivered as an answer reads as an answer."""
        self.answered_with("   ", status="failed")
        self.assertIn("without saying anything", self.what() or "")


if __name__ == "__main__":
    unittest.main()
