"""What a delegated turn is actually told, and what the gateway's sweep decides.

**The case that matters most here is the prompt one.** Every other suite that renders the
delegation layer hands `caller_agent` in by hand, so all of them passed while the real pipeline
never set it — a delegated brain was told `{caller_agent} reads it and comes back to you`, five
times over, and nothing went red. What is proved here is the wiring those suites step over:
`hosting` knows who asked, and the name survives every hop to the built prompt.

Run directly: `python3 tests/test_delegations_hosting.py`
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.core import config, paths
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


class StoppingWorkHandedHere(support.Isolated):
    """A durable stop reaches the gateway that owns the delegated provider turn."""

    def setUp(self):
        super().setUp()
        directory.made("ava", "a-stand-in")
        directory.made("bob", "a-stand-in")
        parent = arriving.asked_at_a_terminal("ava", "delegate the audit")
        with records.writing(directory.records("ava")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (parent.conversation, "a-stand-in", "work", "done",
                 "2026-08-10T00:00:00Z"))
            parent_turn = int(conn.execute("SELECT id FROM turns").fetchone()[0])
        self.delegation = "del-1-aabbcc"
        self.landed = arriving.recorded_for_a_delegation(
            "bob", "ava", parent_turn, "audit it", delegation_id=self.delegation)
        kept.made("ava", self.delegation, "bob", parent.conversation, parent_turn)
        kept.stop_asked("ava", self.delegation)

    def test_a_stop_is_routed_to_the_target_turn_and_never_starts_another(self):
        calls = []

        class Target:
            def stop_this(inner, *args):
                calls.append(("stop", args))
                return True

            def answer_this(inner, *args):
                calls.append(("answer", args))

        hosting._answered_what_was_handed_here("bob", directory.where("bob"), Target())

        self.assertEqual([("stop", ("bob", self.landed.conversation,
                                     self.delegation, "ava", None, None))], calls)

    def test_one_stop_failure_does_not_prevent_the_next_stop(self):
        second = "del-1-ddeeff"
        arriving.recorded_for_a_delegation(
            "bob", "ava", 1, "audit exports", delegation_id=second)
        kept.made("ava", second, "bob", 1, 1)
        kept.stop_asked("ava", second)
        calls = []

        class Target:
            def stop_this(inner, _agent, _conversation, delegation_id, _delegator,
                          _provider_name, _model_name):
                calls.append(delegation_id)
                if delegation_id == self.delegation:
                    raise RuntimeError("provider is leaving")
                return True

            def answer_this(inner, *args):
                raise AssertionError(f"stopped work was started: {args}")

        hosting._answered_what_was_handed_here("bob", directory.where("bob"), Target())

        self.assertEqual([self.delegation, second], calls)

    def test_a_replacement_gateway_receives_the_same_scoped_provider_and_model(self):
        with records.writing(directory.records("ava")) as conn:
            conn.execute(
                "UPDATE delegations SET stop_asked_at = NULL,"
                " provider_name = 'codex', model_name = 'asked-model'"
                " WHERE delegation_id = ?", (self.delegation,))
        calls = []

        class Target:
            def answer_this(inner, *args):
                calls.append(args)

            def stop_this(inner, *args):
                raise AssertionError(f"active work was stopped: {args}")

        hosting._answered_what_was_handed_here("bob", directory.where("bob"), Target())
        # A fresh tenant represents the replacement gateway: no process-local state is shared.
        hosting._answered_what_was_handed_here("bob", directory.where("bob"), Target())

        expected = ("bob", self.landed.conversation, self.delegation, "ava",
                    "codex", "asked-model")
        self.assertEqual([expected, expected], calls)


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

    def test_a_collected_answer_carries_its_terminal_status(self):
        self.answered_with("here is what I found", status=hosting.STOPPED)
        self.assertEqual(hosting.STOPPED, self.what().turn_status)

    def test_a_collected_answer_carries_the_provider_and_model_that_actually_answered(self):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, model_name, access_mode,"
                " turn_status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (self.landed.conversation, "codex", "effective-model", "work", "done",
                 "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn("bob", self.landed.conversation, (self.landed.message,), turn)
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", 12),
                               "here is what I found", turn=turn)

        answer = self.what()

        self.assertEqual(("codex", "effective-model"),
                         (answer.provider_name, answer.model_name))

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


class Showing:
    """A room that writes down what it was told, standing in for a channel that is not here.

    The sweep under test may not reach `channels` at all — what a room *is* belongs a layer away —
    so this is the published shape filled in, which is exactly what the gateway hands it.
    """

    def __init__(self):
        self.said = []

    def answer_this(self, *args, **more):
        raise AssertionError("this case is about what is shown, not about starting turns")

    def review_this(self, *args, **more):
        raise AssertionError("this case is about what is shown, not about delivering answers")

    def showed(self, agent, conversation, state, to_agent, delegation_id, seconds=None):
        self.said.append((state, to_agent, delegation_id, seconds))
        return True


class ARoomWatchingWorkHandedOver:
    """The fixture both halves of what a room is told are proved against: one agent, one real
    conversation, one real turn, and a seam that records what it was shown.

    **A mixin and not a case**, because a case that inherited another's fixture would inherit its
    tests as well and run every one of them a second time under whatever defaults the subclass
    changed — which is how this was written first, and six inherited cases went red for a reason
    that had nothing to do with them.
    """

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("ava", "a-stand-in")
        self.showing = Showing()
        self.carrying = hosting.settled("ava", directory.logs("ava"))
        # A real conversation and a real turn, because the row points at both and SQLite means it.
        self.conversation = arriving.asked_at_a_terminal("ava", "hand it to dev").conversation
        with records.writing(directory.records("ava")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.conversation, "a-stand-in", "work", "done", "2026-08-08T00:00:00Z"))
            self.turn = conn.execute(
                "SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]

    def handed(self, delegation_id="del-7-aabbcc", minutes_ago=0, to_agent="dev"):
        """One delegation this agent made, handed over that many minutes before now."""
        when = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        kept.made("ava", delegation_id, to_agent, self.conversation, self.turn, now=when)
        return delegation_id

    def moment(self, minutes_ago):
        return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)

    def guided(self, delegation_id="del-7-aabbcc", minutes_ago=0):
        """Words said into work still going, that many minutes before now."""
        self.assertTrue(kept.guided("ava", delegation_id, now=self.moment(minutes_ago)))
        return delegation_id

    def swept(self):
        hosting._showed_what_is_happening("ava", self.carrying, self.showing)
        return self.showing.said

    def states(self):
        return [one[0] for one in self.showing.said]


class WhatARoomIsToldAboutWorkHandedOver(ARoomWatchingWorkHandedOver, support.Isolated):
    """R-DEL-16: handing work over, it still being out, and it coming back, where the person asked.

    **Everything here is about a person watching a room**, which is the half a delegation had none
    of: the records were right the whole time and somebody staring at their own direct message saw
    an agent hand work over and then saw nothing ever again.
    """

    def test_work_that_has_just_gone_out_says_who_has_it_and_which_ask_it_is(self):
        at = config.moment_of()
        with mock.patch.object(config, "moment_of", return_value=at):
            self.handed()
            self.assertEqual([(hosting.HANDED_OVER, "dev", "del-7-aabbcc", 0)], self.swept())

    def test_it_is_said_once_however_often_the_beat_comes_round(self):
        """The beat is fifteen seconds. Anything said per pass would be said four times a minute."""
        self.handed()
        self.swept()
        self.swept()
        self.swept()
        self.assertEqual([hosting.HANDED_OVER], self.states())

    def test_work_still_out_after_the_window_says_so_and_says_how_long(self):
        self.handed(minutes_ago=21)
        state, who, _ask, seconds = self.swept()[0]
        self.assertEqual((hosting.STILL_WORKING, "dev"), (state, who))
        self.assertGreaterEqual(seconds, hosting.STILL_WORKING_EVERY)

    def test_work_that_finishes_inside_the_window_never_says_it_is_still_working(self):
        """A ninety-second delegation says it went and says it came back, and nothing between."""
        self.handed(minutes_ago=1)
        self.swept()
        kept.answered("ava", "del-7-aabbcc")
        self.swept()
        self.assertEqual([hosting.HANDED_OVER, hosting.CAME_BACK], self.states())

    def test_each_window_is_its_own_check_in_rather_than_one_for_ever(self):
        """Twenty minutes and forty minutes are different news, and the second must not be eaten by
        the first having already been said."""
        self.handed(minutes_ago=21)
        self.swept()
        self.carrying.said.clear()
        self.handed(delegation_id="del-8-bbccdd", minutes_ago=41)
        said = [one for one in self.swept() if one[2] == "del-8-bbccdd"]
        self.assertEqual(hosting.STILL_WORKING, said[0][0])
        self.assertGreaterEqual(said[0][3], 2 * hosting.STILL_WORKING_EVERY)

    def test_an_answer_that_came_back_says_so_and_how_long_it_took(self):
        self.handed(minutes_ago=5)
        self.swept()
        kept.answered("ava", "del-7-aabbcc")
        state, who, _ask, seconds = self.swept()[-1]
        self.assertEqual((hosting.CAME_BACK, "dev"), (state, who))
        self.assertGreaterEqual(seconds, 5 * 60)

    def test_an_answer_already_reported_is_never_reported_again(self):
        self.handed()
        kept.answered("ava", "del-7-aabbcc")
        self.swept()
        self.swept()
        self.assertEqual([hosting.CAME_BACK], self.states())

    def test_work_another_agent_handed_to_this_one_is_never_shown_here(self):
        """The other side of a delegation is somebody else's room. An agent that announced work it
        was merely doing would be posting another person's task into its own."""
        directory.made("bob", "a-stand-in")
        conversation = arriving.recorded_for_a_delegation(
            "bob", "ava", 9, "audit it", delegation_id="del-9-eeffaa").conversation
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation, "a-stand-in", "work", "done", "2026-08-08T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        kept.made("bob", "del-9-eeffaa", "ava", conversation, turn)
        self.assertEqual([], self.swept())

    def test_what_it_remembers_is_dropped_when_the_delegation_is(self):
        """A gateway runs for weeks; without this, `said` only ever grows and is keyed by something
        that stops existing."""
        self.handed()
        self.swept()
        self.assertIn("del-7-aabbcc", self.carrying.said)
        with records.writing(directory.records("ava")) as conn:
            conn.execute("DELETE FROM delegations")
        self.swept()
        self.assertEqual({}, self.carrying.said)

    def test_a_word_this_release_shows_is_one_the_seam_can_carry(self):
        """Six words in one vocabulary, of two kinds. A check-in is remembered per window and a
        thing that happened is remembered per moment, while what crosses the seam is the plain word
        — the elapsed time or the words that prompted it are which one it is."""
        self.assertEqual((hosting.HANDED_OVER, hosting.STILL_WORKING, hosting.CAME_BACK,
                          hosting.STOPPED),
                         hosting.STANDS)
        self.assertEqual((hosting.GUIDED, hosting.STOPPING, hosting.CARRIED_ON), hosting.HAPPENED)
        self.assertEqual(hosting.STANDS + hosting.HAPPENED, hosting.SHOWN)
        self.assertEqual(hosting.STILL_WORKING, hosting._as_shown(f"{hosting.STILL_WORKING}-3"))
        self.assertEqual(hosting.CAME_BACK, hosting._as_shown(hosting.CAME_BACK))
        self.assertEqual(hosting.GUIDED, hosting._as_shown(f"{hosting.GUIDED}@2026-08-08T10:00:00"))
        self.assertEqual(hosting.CARRIED_ON,
                         hosting._as_shown(f"{hosting.CARRIED_ON}@2026-08-08T10:00:00"))

    def test_a_moment_nobody_can_read_is_not_work_that_just_went_out(self):
        """Otherwise a row with an unreadable timestamp announces itself on every single beat."""
        self.handed()
        with records.writing(directory.records("ava")) as conn:
            # Both, because `working_since` is what the clock is read from now and `created_at` is
            # what "nobody has touched this" is judged against. A row with one of them unreadable is
            # a row this has nothing true to say about either.
            conn.execute("UPDATE delegations SET created_at = 'not a moment',"
                         " working_since = 'not a moment'")
        self.assertEqual([], self.swept())


class WhatARoomIsToldWhenSomebodyReachesIntoTheWork(ARoomWatchingWorkHandedOver, support.Isolated):
    """R-DEL-23: steering a delegation, stopping one and carrying one on are each shown where the
    person asked.

    **The half that was missing.** Where the work stands was already told correctly; what somebody
    *did* to it was told nowhere at all — an owner watching their agent steer a colleague for forty
    minutes saw one line saying the work had gone out and nothing after it.
    """

    #: Every moment here is passed in rather than taken, because a stored moment is UTC **to the
    #: second** and this whole case is about telling one movement of a row from the next. Left to
    #: the clock, a hand-over and the steer after it land in the same second, the row reads as one
    #: nobody has touched, and every case below passes or fails on how fast the machine is.
    def handed(self, delegation_id="del-7-aabbcc", minutes_ago=5, to_agent="dev"):
        """Handed over a few minutes back by default, so anything done to it comes after it."""
        return super().handed(delegation_id, minutes_ago, to_agent)

    def aged(self, minutes, delegation_id="del-7-aabbcc"):
        """Move when this phase of the work began, so a check-in window can be crossed in a test.

        **Both columns, because they answer different questions and a case wants the clock moved.**
        `working_since` is what a check-in counts from; `created_at` moves with it so a delegation
        nobody has carried on still reads as one phase, which is what these cases are about.
        """
        when = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        with records.writing(directory.records("ava")) as conn:
            conn.execute("UPDATE delegations SET created_at = ?, working_since = ?"
                         " WHERE delegation_id = ?",
                         (when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                          when.strftime("%Y-%m-%dT%H:%M:%SZ"), delegation_id))

    def test_words_said_into_work_still_going_are_shown_where_the_person_asked(self):
        self.handed()
        self.swept()
        self.showing.said.clear()
        self.guided()
        self.assertEqual([(hosting.GUIDED, "dev", "del-7-aabbcc", None)], self.swept())

    def test_a_steer_never_repeats_what_was_said(self):
        """The words are between two agents, and the seam has nowhere to put them by design —
        proved here rather than assumed, because a field added later would be added silently."""
        self.handed()
        self.guided("del-7-aabbcc")
        state, who, ask, seconds = self.swept()[-1]
        self.assertEqual((hosting.GUIDED, "dev", "del-7-aabbcc", None), (state, who, ask, seconds))

    def test_a_steer_carries_no_elapsed_clause(self):
        """How long the work has been out is news about the work. Beside `updated dev` it reads as
        how long the steering took."""
        self.handed(minutes_ago=41)
        self.guided()
        self.assertIsNone(self.swept()[-1][3])

    def test_a_second_steer_is_its_own_news_and_not_the_first_still_standing(self):
        self.handed()
        self.guided(minutes_ago=2)
        self.swept()
        self.showing.said.clear()
        self.guided()
        self.swept()
        self.assertEqual([hosting.GUIDED], self.states())

    def test_a_steer_is_said_once_however_often_the_beat_comes_round(self):
        self.handed()
        self.guided()
        self.swept()
        self.swept()
        self.swept()
        self.assertEqual(1, self.states().count(hosting.GUIDED))

    def test_work_steered_is_never_announced_as_newly_handed_over_afterwards(self):
        """The trap this structure exists for. Where the work stands and what was just done to it
        are two different memories; one dictionary would have `handed` overwritten by `guided`, and
        the beat after the steer would say the work had just gone out — a second time."""
        self.handed()
        self.swept()
        self.guided()
        self.swept()
        self.showing.said.clear()
        self.swept()
        self.assertEqual([], self.swept())

    def test_a_steer_that_displaced_a_check_in_does_not_make_it_arrive_late(self):
        """One piece of news per beat, and the steer is the one somebody could not have worked out.
        The check-in it displaced is counted as said, so the room hears the next one and not that
        one a beat afterwards."""
        self.handed(minutes_ago=21)
        self.guided()
        self.swept()
        self.assertEqual([hosting.GUIDED], self.states())
        self.showing.said.clear()
        self.assertEqual([], self.swept())

    def test_a_stop_asked_for_is_shown_where_the_person_asked(self):
        self.handed()
        self.swept()
        self.showing.said.clear()
        kept.stop_asked("ava", "del-7-aabbcc")
        self.assertEqual([(hosting.STOPPING, "dev", "del-7-aabbcc", None)], self.swept())

    def test_a_completed_requested_stop_is_shown_as_stopped_and_never_as_answered(self):
        now = datetime.now(timezone.utc)
        kept.made("ava", "del-7-aabbcc", "dev", self.conversation, self.turn,
                  now=now - timedelta(minutes=5))
        self.swept()
        self.showing.said.clear()
        kept.stop_asked("ava", "del-7-aabbcc", now=now)
        kept.stopped("ava", "del-7-aabbcc", now=now)

        self.assertEqual([(hosting.STOPPED, "dev", "del-7-aabbcc", 5 * 60)], self.swept())
        self.assertNotIn(hosting.CAME_BACK, self.states())

    def test_a_stop_nothing_has_honoured_yet_does_not_silence_the_check_ins(self):
        """A stop is a request. Work that goes on regardless has to go on saying so, or the room's
        last word on a wedged delegation is that somebody asked it to end."""
        self.handed(minutes_ago=21)
        self.swept()
        kept.stop_asked("ava", "del-7-aabbcc")
        self.swept()
        self.showing.said.clear()
        self.aged(41)
        self.swept()
        self.assertEqual([hosting.STILL_WORKING], self.states())

    def test_words_said_after_a_stop_was_asked_for_are_still_shown(self):
        """The stop is named by its own moment, so it stops being the latest thing that happened
        the moment somebody says something else."""
        self.handed()
        kept.stop_asked("ava", "del-7-aabbcc", now=self.moment(2))
        self.swept()
        self.showing.said.clear()
        self.guided()
        self.swept()
        self.assertEqual([hosting.GUIDED], self.states())

    def test_work_carried_on_says_so_rather_than_looking_like_a_new_delegation(self):
        """The whole difference between resuming and asking again. Before this the sweep read the
        reopened row off `created_at` alone and announced a second hand-over, or — where the ask was
        old enough — a check-in counting from a clock that was not measuring the new work."""
        self.handed()
        self.swept()
        kept.answered("ava", "del-7-aabbcc", now=self.moment(3))
        self.swept()
        self.showing.said.clear()
        kept.reopened("ava", "del-7-aabbcc", now=self.moment(1))
        self.assertEqual([(hosting.CARRIED_ON, "dev", "del-7-aabbcc", None)], self.swept())

    def test_carrying_on_is_told_from_steering_by_the_moment_the_phase_began(self):
        """A resume is the only verb that moves `working_since`, so the two are told apart off the
        record — see `_what_just_happened`."""
        self.handed()
        self.swept()
        kept.answered("ava", "del-7-aabbcc", now=self.moment(3))
        self.swept()
        kept.reopened("ava", "del-7-aabbcc", now=self.moment(2))
        self.swept()
        self.showing.said.clear()
        self.guided()
        self.swept()
        self.assertEqual([hosting.GUIDED], self.states())

    def test_a_gateway_restart_treats_retained_delegations_as_its_baseline(self):
        """Restarting is not a new delegation event. A gateway must describe only changes that
        happen after it starts, rather than replaying every retained answer or resume as fresh."""
        self.handed()
        kept.answered("ava", "del-7-aabbcc", now=self.moment(3))
        kept.reopened("ava", "del-7-aabbcc", now=self.moment(1))

        self.carrying = hosting.settled("ava", None)     # a gateway with no memory at all
        self.assertEqual([], self.swept())

    def test_nothing_is_remembered_about_a_delegation_that_is_no_longer_there(self):
        """Both dictionaries, not only the one that existed before this."""
        self.handed()
        self.guided()
        self.swept()
        self.assertIn("del-7-aabbcc", self.carrying.marked)
        with records.writing(directory.records("ava")) as conn:
            conn.execute("DELETE FROM delegations")
        self.swept()
        self.assertEqual(({}, {}), (self.carrying.said, self.carrying.marked))


class WhatARoomIsToldAfterWorkIsCarriedOn(ARoomWatchingWorkHandedOver, support.Isolated):
    """The clock a resumed phase is measured by.

    **Measured on a real Discord channel, and it is why `working_since` exists.** An hour-old
    delegation was resumed and the room said *"⏳ forge still working · 1h"* on the very next beat —
    before the agent had done a second of the new work. Counted from `created_at`, the resumed phase
    inherited the whole age of the original: the first check-in was overdue the instant it began, so
    the twenty minutes of silence a person reads as *"nothing to report yet"* never happened, and the
    answer that followed was reported as having taken an hour when it took minutes.

    Every case here starts from a delegation that is already old, because that is the only shape in
    which the defect shows.
    """

    def an_old_delegation_carried_on(self, was_out_for=60, resumed_ago=0):
        """An hour of work, answered, and then carried on — the exact live shape."""
        self.handed(minutes_ago=was_out_for)
        self.swept()
        kept.answered("ava", "del-7-aabbcc", now=self.moment(was_out_for - 5))
        self.swept()
        self.showing.said.clear()
        kept.reopened("ava", "del-7-aabbcc", now=self.moment(resumed_ago))

    def test_the_resumed_phase_does_not_inherit_the_age_of_the_original(self):
        # The regression itself. `1h` beside a resume that happened a moment ago is the sentence
        # somebody read in a real room.
        self.an_old_delegation_carried_on()
        self.swept()
        self.showing.said.clear()

        self.swept()
        self.assertEqual([], self.swept(), "the resumed phase announced something on its own")
        standing, since = hosting._how_it_stands(kept.one("ava", "del-7-aabbcc"))
        self.assertEqual(hosting.HANDED_OVER, standing)
        self.assertLess(since, 60, f"the resumed phase began {since}s old")

    def test_carrying_on_is_said_once_and_not_again_on_every_beat(self):
        self.an_old_delegation_carried_on()
        self.assertEqual([(hosting.CARRIED_ON, "dev", "del-7-aabbcc", None)], self.swept())
        self.showing.said.clear()

        self.swept()
        self.swept()
        self.assertEqual([], self.showing.said)

    def test_no_check_in_lands_before_the_resumed_phase_is_twenty_minutes_old(self):
        # Nineteen minutes into the new phase, an hour and nineteen into the delegation. Counted
        # from `created_at` this is the fourth check-in and long overdue; counted from the phase it
        # is silence, which is what a person watching should see.
        self.an_old_delegation_carried_on(resumed_ago=19)
        self.assertEqual([(hosting.CARRIED_ON, "dev", "del-7-aabbcc", None)], self.swept())
        self.showing.said.clear()

        self.swept()
        self.assertEqual([], self.showing.said, "a check-in landed inside the first window")

    def test_the_check_in_that_follows_a_resume_is_timed_from_the_resume(self):
        # **Time is moved rather than the row rewritten.** A fixture that aged the phase by editing
        # `working_since` would also move the moment the resume happened at, and the sweep would
        # announce the carry-on a second time — an artefact of the fixture and not of the product.
        # Moving what `now` means is what really happens between two beats.
        self.an_old_delegation_carried_on()
        self.swept()
        self.showing.said.clear()

        with self.at_minute(19):
            self.assertEqual([], self.swept(), "a check-in landed before the phase was 20m old")
        with self.at_minute(21):
            self.assertEqual([(hosting.STILL_WORKING, "dev", "del-7-aabbcc", 21 * 60)],
                             self.swept())

    def test_the_answer_to_resumed_work_is_timed_from_the_resume(self):
        # What the room is told the work took. An hour is the age of the whole delegation and
        # nobody waited it — the person who asked for more waited four minutes.
        self.an_old_delegation_carried_on()
        self.swept()
        self.showing.said.clear()

        answered = kept.one("ava", "del-7-aabbcc").working_since
        kept.answered("ava", "del-7-aabbcc",
                      now=datetime.strptime(answered, "%Y-%m-%dT%H:%M:%SZ").replace(
                          tzinfo=timezone.utc) + timedelta(minutes=4))
        self.assertEqual([(hosting.CAME_BACK, "dev", "del-7-aabbcc", 4 * 60)], self.swept())

    def test_steering_and_stopping_the_resumed_work_do_not_restart_its_clock(self):
        # The other half of the rule, and the one a "fix" would break: only carrying on begins a new
        # stretch of waiting. Somebody saying a word into running work has not restarted it.
        # Resumed a minute ago rather than this instant, so the steer that follows lands on a
        # later recorded moment than the resume did. Two writes inside one second are one moment to
        # the store, and a case that raced them would be measuring the clock rather than the rule.
        self.an_old_delegation_carried_on(resumed_ago=1)
        self.swept()
        began = kept.one("ava", "del-7-aabbcc").working_since

        self.guided()
        kept.stop_asked("ava", "del-7-aabbcc")

        after = kept.one("ava", "del-7-aabbcc")
        self.assertEqual(began, after.working_since,
                         "a steer or a stop moved the clock the work is measured by")
        self.assertNotEqual(began, after.latest_at, "neither verb moved the delegation at all")
        with self.at_minute(21):
            self.assertEqual((f"{hosting.STILL_WORKING}-1", 21 * 60),
                             hosting._how_it_stands(kept.one("ava", "del-7-aabbcc")))

    def test_the_delegation_keeps_its_identity_and_its_conversation(self):
        # Resuming is not asking again: the answering agent picks up the session it already had,
        # which is only true while the id, the conversation and the parent turn are untouched.
        self.handed(minutes_ago=60)
        before = kept.one("ava", "del-7-aabbcc")
        kept.answered("ava", "del-7-aabbcc", now=self.moment(55))
        kept.reopened("ava", "del-7-aabbcc", now=self.moment(1))
        after = kept.one("ava", "del-7-aabbcc")

        self.assertEqual((before.delegation_id, before.parent_conversation, before.parent_turn,
                          before.created_at),
                         (after.delegation_id, after.parent_conversation, after.parent_turn,
                          after.created_at))
        self.assertNotEqual(before.working_since, after.working_since)
        self.assertEqual(kept.source_id_for("ava", before.parent_turn, before.delegation_id),
                         kept.source_id_for("ava", after.parent_turn, after.delegation_id))

    def at_minute(self, minutes, delegation_id="del-7-aabbcc"):
        """Read the sweep as it would run that many minutes after this phase began.

        **`now` moves and the row does not.** Every moment in the record stays exactly where the
        product wrote it, so what is being measured is the arithmetic rather than a fixture's idea
        of it — and nothing here can accidentally restamp the resume and make the sweep re-announce
        it. Patched on `config`, which is the one place a moment is taken.
        """
        began = kept.one("ava", delegation_id).working_since
        at = (datetime.strptime(began, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
              + timedelta(minutes=minutes))
        real = config.moment_of
        return mock.patch.object(
            config, "moment_of",
            side_effect=lambda when=None, days_ago=0: (
                real(at, days_ago) if when is None else real(when, days_ago)))


class WhatMovesADelegationsLatestMoment(support.Isolated):
    """`kept.guided`: the one column every verb that reaches into a delegation moves, and what the
    sweep and the retention window both read."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("ava", "a-stand-in")
        self.conversation = arriving.asked_at_a_terminal("ava", "hand it to dev").conversation
        with records.writing(directory.records("ava")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.conversation, "a-stand-in", "work", "done", "2026-08-08T00:00:00Z"))
            self.turn = conn.execute(
                "SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        kept.made("ava", "del-7-aabbcc", "dev", self.conversation, self.turn,
                  now=datetime.now(timezone.utc) - timedelta(hours=2))

    def test_words_said_into_work_move_the_moment_it_was_last_touched(self):
        """Before this a delegation somebody steered for an hour aged as though nobody had been
        near it, and the retention window is counted from here (R-DEL-21)."""
        before = kept.one("ava", "del-7-aabbcc")
        self.assertEqual(before.created_at, before.latest_at)
        self.assertTrue(kept.guided("ava", "del-7-aabbcc"))
        after = kept.one("ava", "del-7-aabbcc")
        self.assertNotEqual(after.created_at, after.latest_at)
        self.assertGreater(after.latest_at, after.created_at)

    def test_work_that_has_been_answered_is_not_work_there_was_anything_to_say_into(self):
        """`False` rather than a stamp, so a row settled by collection between the caller's read and
        this write is not moved underneath it."""
        kept.answered("ava", "del-7-aabbcc")
        settled = kept.one("ava", "del-7-aabbcc")
        self.assertFalse(kept.guided("ava", "del-7-aabbcc"))
        self.assertEqual(settled.latest_at, kept.one("ava", "del-7-aabbcc").latest_at)

    def test_nothing_of_what_was_said_is_written_into_the_delegation(self):
        """The words are a message in the answering agent's store; this row is what is neither a
        turn nor a message, and the membership rule step 0005 was written to is kept."""
        kept.guided("ava", "del-7-aabbcc")
        with records.reading(directory.records("ava")) as conn:
            row = conn.execute(
                "SELECT * FROM delegations WHERE delegation_id = 'del-7-aabbcc'").fetchone()
        # `working_since` is a moment like the three beside it, and is in this list for the same
        # reason they are: what is being refused here is *words*, not columns.
        self.assertEqual(
            {"id", "delegation_id", "to_agent", "parent_conversation", "parent_turn",
             "answered_at", "stopped_at", "stop_asked_at", "created_at", "latest_at",
             "working_since", "provider_name", "model_name"},
            set(row.keys()))


if __name__ == "__main__":
    unittest.main()
