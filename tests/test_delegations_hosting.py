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
from rundesk.providers import answering, instructions, turns
from rundesk.providers import kept as provider_kept


class WhatADelegatedTurnIsTold(support.Isolated):
    """The prompt, built the way a real turn builds it rather than with the variables filled by
    hand — which is the whole point, since filling them by hand is what hid the defect."""

    def built(self, **more):
        request = turns.Request(agent="bob", prompt="audit it", conversation=1,
                                situation=instructions.AGENT_TO_AGENT, **more)
        return instructions.build(situation=request.situation,
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


class WhatADelegatedTurnIsAsked(support.Isolated):
    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("bob", "a-stand-in")
        self.landed = arriving.recorded_for_a_delegation("bob", "ava", 12, "audit it")

    def prompt(self):
        return answering._delegated_prompt("bob", self.landed.conversation, "ava")

    def test_guidance_before_the_first_turn_augments_the_original_brief(self):
        more = arriving.recorded_for_a_delegation("bob", "ava", 12, "also check retention")
        body, messages = self.prompt()
        self.assertEqual("audit it\n\nalso check retention", body)
        self.assertEqual((self.landed.message, more.message), messages)

    def test_more_than_the_history_display_limit_stays_oldest_first(self):
        guidance = [arriving.recorded_for_a_delegation(
            "bob", "ava", 12, f"guidance {number}") for number in range(60)]
        body, messages = self.prompt()
        self.assertEqual("audit it", body.split("\n\n")[0])
        self.assertEqual("guidance 59", body.split("\n\n")[-1])
        self.assertEqual((self.landed.message, *(one.message for one in guidance)), messages)

    def test_more_tiny_messages_than_one_claim_can_hold_are_left_for_the_next_turn(self):
        guidance = [arriving.recorded_for_a_delegation(
            "bob", "ava", 12, f"g{number}")
                    for number in range(answering.DELEGATED_MESSAGES_AT_MOST + 20)]
        body, messages = self.prompt()
        self.assertEqual(answering.DELEGATED_MESSAGES_AT_MOST, len(messages))
        self.assertEqual("audit it", body.split("\n\n")[0])
        self.assertEqual(
            f"g{answering.DELEGATED_MESSAGES_AT_MOST - 2}", body.split("\n\n")[-1])
        self.assertNotIn(guidance[-1].message, messages)

    def test_guidance_after_an_answer_is_the_next_turns_prompt(self):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, "a-stand-in", "work", "done",
                 "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn("bob", self.landed.conversation, (self.landed.message,), turn)
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", 12),
                               "review complete", turn=turn)
        more = arriving.recorded_for_a_delegation("bob", "ava", 12, "also check retention")
        self.assertEqual(("also check retention", (more.message,)), self.prompt())

    def test_a_partial_message_claim_is_rolled_back_whole(self):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, "a-stand-in", "work", "working",
                 "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        with self.assertRaises(records.Unreadable):
            arriving.handled_by_turn(
                "bob", self.landed.conversation, (self.landed.message, 999999), turn)
        with records.reading(directory.records("bob")) as conn:
            claimed = conn.execute(
                "SELECT turn_id FROM conversation_messages WHERE id = ?",
                (self.landed.message,)).fetchone()[0]
        self.assertIsNone(claimed)


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
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn("bob", self.landed.conversation, (self.landed.message,), turn)
        return turn

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
        self.landed = arriving.recorded_for_a_delegation("bob", "ava", 12, "audit it")

    def answered_with(self, said, status="done", message=None):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (1, ?, ?, ?, ?)",
                ("a-stand-in", "work", status, "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn(
            "bob", self.landed.conversation,
            (self.landed.message if message is None else message,), turn)
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", 12),
                               said, turn=turn)
        return turn

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

    def test_guidance_arriving_during_a_turn_requires_a_later_turn(self):
        turn = self.answered_with("first report", status=hosting.WORKING)
        guidance = arriving.recorded_for_a_delegation(
            "bob", "ava", 12, "include GUIDANCE=EMBER-284")
        with records.writing(directory.records("bob")) as conn:
            conn.execute("UPDATE turns SET turn_status = 'done' WHERE id = ?", (turn,))

        self.assertIsNone(self.what())
        self.assertTrue(hosting._is_waiting_on_us("bob", self.landed.conversation, "ava"))
        self.assertEqual(("include GUIDANCE=EMBER-284", (guidance.message,)),
                         answering._delegated_prompt("bob", self.landed.conversation, "ava"))

        self.answered_with("complete report with GUIDANCE=EMBER-284", message=guidance.message)
        self.assertEqual("complete report with GUIDANCE=EMBER-284", self.what())

    def test_a_turn_that_said_nothing_answers_a_sentence_rather_than_silence(self):
        """Silence delivered as an answer reads as an answer."""
        self.answered_with("   ", status="failed")
        self.assertIn("without saying anything", self.what() or "")

    def test_a_terminal_turn_with_no_agent_message_still_answers(self):
        """A provider can fail before writing any message at all. Claiming the brief must not
        leave that delegation permanently neither waiting nor collectable."""
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, "a-stand-in", "work", "failed",
                 "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn("bob", self.landed.conversation,
                                 (self.landed.message,), turn)

        self.assertIn("without saying anything (failed)", self.what() or "")

    def test_a_pre_boundary_terminal_answer_is_collected_without_rerunning_its_brief(self):
        """Older releases left a delegated brief's turn id empty even after its turn answered."""
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, "a-stand-in", "work", "done",
                 "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        provider_kept.add_turn_record("bob", turn, "sent", {"text": "audit it"})
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", 12),
                               "legacy report", turn=turn)

        self.assertFalse(hosting._is_waiting_on_us(
            "bob", self.landed.conversation, "ava"))
        self.assertEqual("legacy report", self.what())

    def test_guidance_an_old_running_turn_never_saw_remains_for_a_later_turn(self):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, "a-stand-in", "work", "working",
                 "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        provider_kept.add_turn_record("bob", turn, "sent", {"text": "audit it"})
        guidance = arriving.recorded_for_a_delegation(
            "bob", "ava", 12, "include GUIDANCE=EMBER-284")
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", 12),
                               "old report", turn=turn)
        with records.writing(directory.records("bob")) as conn:
            conn.execute("UPDATE turns SET turn_status = 'done' WHERE id = ?", (turn,))

        self.assertIsNone(self.what())
        self.assertTrue(hosting._is_waiting_on_us(
            "bob", self.landed.conversation, "ava"))
        self.assertIn(guidance.message, answering._delegated_prompt(
            "bob", self.landed.conversation, "ava")[1])


class TwoDelegationsFromOneTurn(support.Isolated):
    """Distinct bounded tasks from one parent turn must never share a target session or answer."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("bob", "a-stand-in")
        self.first_id = "del-12-aabbcc"
        self.second_id = "del-12-ddeeff"
        self.first = arriving.recorded_for_a_delegation(
            "bob", "ava", 12, "audit retention", delegation_id=self.first_id)
        self.second = arriving.recorded_for_a_delegation(
            "bob", "ava", 12, "audit exports", delegation_id=self.second_id)

    def answer(self, landed, delegation_id, body):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (landed.conversation, "a-stand-in", "work", "done",
                 "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn("bob", landed.conversation, (landed.message,), turn)
        arriving.said_by_agent(
            "bob", kept.FROM_AGENT, kept.source_id_for("ava", 12, delegation_id), body, turn=turn)

    def test_each_task_has_its_own_conversation_and_answer(self):
        self.assertNotEqual(self.first.conversation, self.second.conversation)
        self.answer(self.first, self.first_id, "retention is sound")
        self.answer(self.second, self.second_id, "exports need a fix")

        self.assertEqual(
            "retention is sound",
            hosting._what_they_answered("bob", "ava", 12, self.first_id))
        self.assertEqual(
            "exports need a fix",
            hosting._what_they_answered("bob", "ava", 12, self.second_id))


if __name__ == "__main__":
    unittest.main()
