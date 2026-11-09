"""`rundesk asked`: public guidance controls for work one agent handed over.

Run directly: `python3 tests/test_asked_command.py`
"""

import os
import threading
import time
import unittest
from unittest import mock

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.channels import hosting as channels_hosting
from rundesk.commands import asked
from rundesk.delegations import admitting, hosting, kept
from rundesk.exits import FAILED, OK
from rundesk.providers import answering, instructions, turns
from rundesk.providers import kept as provider_kept


def _said(out: str, about: str) -> str:
    """What one line of `asked show` answers, by the label in front of it."""
    line = next(one for one in out.splitlines() if one.strip().startswith(about))
    return line.strip()[len(about):].strip()


def _reaching_no_channel() -> channels_hosting.Watching:
    """A gateway watching nothing, for a tenant whose conversations stand on no platform.

    Every conversation here is a delegation or a terminal one, so nothing is ever sent through this
    — but it is handed in rather than left out, because a tenant with nowhere to send an answer is
    the defect these cases exist alongside, not a shape a case should be able to construct.
    """
    return channels_hosting.Watching({}, {}, {})


class GuidingWorkingDelegation(support.Isolated):
    def setUp(self):
        super().setUp()
        directory.made("ava", support.A_STAND_IN)
        directory.made("bob", support.A_STAND_IN)
        parent = arriving.asked_at_a_terminal("ava", "delegate the audit")
        self.parent = parent
        with records.writing(directory.records("ava")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (parent.conversation, support.A_STAND_IN, "work", "done",
                 "2026-08-07T00:00:00Z"))
            self.turn = conn.execute("SELECT id FROM turns").fetchone()[0]
        self.delegation = "del-1-aabbcc"
        self.landed = arriving.recorded_for_a_delegation(
            "bob", "ava", self.turn, "audit it")
        kept.made("ava", self.delegation, "bob", parent.conversation, self.turn)

    def completed_answer(self, body="finished report"):
        """A terminal target turn and the answer the delegator's collector will find."""
        target_turn = provider_kept.add_turn("bob", {
            "conversation_id": self.landed.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": "work",
        })
        arriving.handled_by_turn(
            "bob", self.landed.conversation, (self.landed.message,), target_turn)
        arriving.said_by_agent(
            "bob", kept.FROM_AGENT, kept.source_id_for("ava", self.turn), body,
            turn=target_turn)
        provider_kept.finish_turn("bob", target_turn, provider_kept.DONE)
        return hosting._what_they_answered(
            "bob", "ava", self.turn, self.delegation)

    def claimed_review_result(self, answer, status, admitted=False):
        """A durable result claimed by one parent turn before its provider write."""
        said = answering.REVIEW.format(
            agent="bob", answer=answer,
            provenance=answering._delegation_provenance(answer))
        landed = arriving.said_by_rundesk_into(
            "ava", self.parent.conversation, said,
            external_id=f"delegation-result:{self.delegation}:{answer.answer_id}")
        owner = provider_kept.add_turn("ava", {
            "conversation_id": self.parent.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": "work",
        })
        arriving.handled_by_turn(
            "ava", self.parent.conversation, (landed.message,), owner)
        if admitted:
            provider_kept.add_turn_record(
                "ava", owner, turns.ADMITTED, {"messages": [landed.message]})
        if status != provider_kept.WORKING:
            provider_kept.finish_turn("ava", owner, status)
        return landed, owner

    def guide(self):
        return self.rundesk("asked", "--agent", "ava", "say", self.delegation,
                            "include GUIDANCE=EMBER-284")

    def test_show_distinguishes_requested_effective_and_terminal_provenance(self):
        with records.writing(directory.records("ava")) as conn:
            conn.execute(
                "UPDATE delegations SET requested_provider_name = './codex',"
                " requested_model_name = 'asked-model', provider_name = '/opt/codex',"
                " model_name = 'asked-model'"
                " WHERE delegation_id = ?",
                (self.delegation,))
        turn = provider_kept.add_turn("bob", {
            "conversation_id": self.landed.conversation,
            "provider_name": "/opt/codex",
            "model_name": "asked-model",
            "admitted_model_name": "asked-model",
            "access_mode": "work",
        })
        arriving.handled_by_turn(
            "bob", self.landed.conversation, (self.landed.message,), turn)
        # The brain names the model that ran, at settlement, which is the only moment anything can.
        provider_kept.finish_turn("bob", turn, provider_kept.DONE,
                                  {"model_name": "actual-model",
                                   "reported_model_name": "actual-model"})

        code, out, err = self.rundesk(
            "asked", "--agent", "ava", "show", self.delegation)

        self.assertEqual(OK, code, err)
        for value in ("requested provider", "requested model", "./codex", "asked-model",
                      "effective provider", "effective model", "/opt/codex",
                      "terminal provider", "terminal model", "actual-model"):
            self.assertIn(value, out)
        self.assertEqual("actual-model", _said(out, "terminal model"))

    def test_show_will_not_name_a_configured_model_the_provider_never_reported(self):
        """**A model that was asked for is not evidence of the model that ran**, and `terminal` is
        the column that claims it did.

        Driven end to end: bob is configured with a model, answers a real delegated turn on an
        adapter that reports none back — the shape `antigravity` ships today — and the row it leaves
        is the row this surface reads. Before the two were kept apart, the configured model was
        written at admission, survived a settlement that had nothing to replace it with, and was
        then printed here as the model that had answered.
        """
        records.stated(directory.records("bob"), {"model_name": "configured-model"})
        self.a_stand_in_told("bob", omit_model=True)
        self.a_delegated_turn_bob_answers()

        code, out, err = self.rundesk(
            "asked", "--agent", "ava", "show", self.delegation)

        self.assertEqual(OK, code, err)
        self.assertEqual("provider did not report one", _said(out, "terminal model"))
        self.assertNotIn("configured-model", out)

    def test_show_names_the_model_a_provider_did_report(self):
        """The other half of the same run, so the surface is not merely always saying nothing."""
        records.stated(directory.records("bob"), {"model_name": "configured-model"})
        self.a_delegated_turn_bob_answers()

        code, out, err = self.rundesk(
            "asked", "--agent", "ava", "show", self.delegation)

        self.assertEqual(OK, code, err)
        self.assertEqual("a-stand-in-1", _said(out, "terminal model"))

    def test_show_still_reads_the_one_column_a_turn_from_an_older_release_has(self):
        """Nothing is reinterpreted: that value is the best there is, and it is what is shown."""
        turn = provider_kept.add_turn("bob", {
            "conversation_id": self.landed.conversation,
            "provider_name": support.A_STAND_IN,
            "model_name": "either-of-them",
            "access_mode": "work",
        })
        arriving.handled_by_turn(
            "bob", self.landed.conversation, (self.landed.message,), turn)
        provider_kept.finish_turn("bob", turn, provider_kept.DONE)
        with records.writing(directory.records("bob")) as conn:
            conn.execute("UPDATE turns SET model_provenance_kept = 0,"
                         " admitted_model_name = NULL WHERE id = ?", (turn,))

        code, out, err = self.rundesk(
            "asked", "--agent", "ava", "show", self.delegation)

        self.assertEqual(OK, code, err)
        self.assertEqual("either-of-them", _said(out, "terminal model"))

    def a_delegated_turn_bob_answers(self):
        """One real turn on the answering side, admitted and settled the way a gateway runs one."""
        return turns.run(turns.Request(
            agent="bob", prompt="audit it", conversation=self.landed.conversation,
            situation=instructions.AGENT_TO_AGENT, caller_agent="ava",
            source=arriving.FROM_AGENT, place=f"ava/{self.turn}",
            inbound_messages=(self.landed.message,)))

    def test_show_identifies_a_legacy_late_bound_row(self):
        code, out, err = self.rundesk(
            "asked", "--agent", "ava", "show", self.delegation)
        self.assertEqual(OK, code, err)
        self.assertIn("not requested", out)
        self.assertIn("legacy target default at claim", out)
        self.assertIn("provider default", out)

    def test_resume_exposes_no_provider_or_model_override_flags(self):
        code, out, err = self.rundesk("asked", "resume", "--help")
        self.assertEqual(OK, code, err)
        self.assertNotIn("--provider", out)
        self.assertNotIn("--model", out)

    def test_say_records_guidance_for_the_active_turn_with_a_next_turn_fallback(self):
        code, out, err = self.guide()
        self.assertEqual(OK, code, err)
        self.assertIn("active-first", out)
        self.assertIn("offers it now", out)
        self.assertIn("next turn", out)
        said = arriving.messages("bob", 1)
        self.assertEqual(["audit it", "include GUIDANCE=EMBER-284"],
                         [one["body"] for one in said])

    def test_an_agents_own_turn_guides_and_carries_on_without_naming_itself(self):
        """**The verbs an agent actually reaches for, asked the way an agent asks them.**

        Every other case here passes `--agent`, which is the shape a person at a terminal uses — so
        all of them would pass with the environment ignored, and an agent following the instruction
        layer's own words would be told there is no turn here. Which agent it is comes from
        `RUNDESK_AGENT`, exactly as `ask` reads it, and an agent naming an agent is refused by not
        being possible: there is nothing on this parser to name somebody else with.
        """
        with mock.patch.dict(os.environ, {admitting.AGENT: "ava",
                                          admitting.RUN: str(self.turn)}):
            code, out, err = self.rundesk(
                "asked", "say", self.delegation, "include GUIDANCE=EMBER-284")
            self.assertEqual(OK, code, err)
            self.assertIn("include GUIDANCE=EMBER-284",
                          [one["body"] for one in arriving.messages("bob", 1)])

            kept.answered("ava", self.delegation)
            code, out, err = self.rundesk(
                "asked", "resume", self.delegation, "now check exports")
            self.assertEqual(OK, code, err)
            self.assertIn("carried on", out)

        # Carried on in the session it already had, and owed again — which is what puts it back in
        # front of the answering gateway rather than starting a second task that repeats the first.
        self.assertIsNone(kept.one("ava", self.delegation).answered_at)
        self.assertEqual([self.landed.conversation],
                         [one["id"] for one in arriving.conversations("bob")])
        self.assertEqual(["audit it", "include GUIDANCE=EMBER-284", "now check exports"],
                         [one["body"] for one in arriving.messages("bob", 1)])

    def test_say_moves_the_moment_the_delegation_was_last_touched(self):
        """R-DEL-23: what makes the steer visible at all. The asking agent's gateway has no way to
        know words were said into work it handed out — the guidance is a message in *bob's* store —
        so this row moving is the whole of the signal, and it is what the room's `updated bob` line
        and the retention window (R-DEL-21) are both read off.

        Handed over a few minutes back because a stored moment is UTC to the second: created and
        steered inside one second, the row reads as one nobody has been near.
        """
        with records.writing(directory.records("ava")) as conn:
            conn.execute("UPDATE delegations SET created_at = ?, latest_at = ?"
                         " WHERE delegation_id = ?",
                         ("2026-08-07T00:05:00Z", "2026-08-07T00:05:00Z", self.delegation))
        self.assertEqual(OK, self.guide()[0])
        moved = kept.one("ava", self.delegation)
        self.assertEqual("2026-08-07T00:05:00Z", moved.created_at)
        self.assertGreater(moved.latest_at, moved.created_at)

    def test_say_refuses_answered_work_and_points_to_resume(self):
        kept.answered("ava", self.delegation)
        code, _out, err = self.guide()
        self.assertEqual(FAILED, code)
        self.assertIn("already answered", err)
        self.assertIn("asked resume", err)

    def test_resume_keeps_a_pre_upgrade_delegations_original_conversation(self):
        kept.answered("ava", self.delegation)
        code, out, err = self.rundesk(
            "asked", "--agent", "ava", "resume", self.delegation, "check exports too")
        self.assertEqual(OK, code, err)
        self.assertIn("carried on", out)
        self.assertIsNone(kept.one("ava", self.delegation).answered_at)
        conversations = arriving.conversations("bob")
        self.assertEqual([self.landed.conversation], [one["id"] for one in conversations])
        self.assertEqual(
            ["audit it", "check exports too"],
            [one["body"] for one in arriving.messages("bob", self.landed.conversation)])

    def test_stopped_work_cannot_be_resumed(self):
        kept.stopped("ava", self.delegation)

        code, _out, err = self.rundesk(
            "asked", "--agent", "ava", "resume", self.delegation, "check exports too")

        self.assertEqual(FAILED, code)
        self.assertIn("was stopped and cannot be carried on", err)
        self.assertIsNotNone(kept.one("ava", self.delegation).stopped_at)
        self.assertEqual(["audit it"], [
            one["body"] for one in arriving.messages("bob", self.landed.conversation)])

    def test_say_reaches_active_polling_on_the_modern_delegation_conversation(self):
        modern = arriving.recorded_for_a_delegation(
            "bob", "ava", self.turn, "modern audit", delegation_id=self.delegation)
        active = provider_kept.add_turn("bob", {
            "conversation_id": modern.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": "work",
        })
        arriving.handled_by_turn("bob", modern.conversation, (modern.message,), active)
        words = turns.Words("bob", modern.conversation, active, caller_agent="ava")

        code, _out, err = self.guide()
        guidance = next(words.each())
        words.close()

        self.assertEqual(OK, code, err)
        self.assertEqual("include GUIDANCE=EMBER-284", guidance.text)
        self.assertEqual(modern.conversation, guidance.conversation)
        self.assertEqual(active, arriving.turn_for_message(
            "bob", modern.conversation, guidance.messages[0]))

    def test_guidance_cannot_land_behind_collection_that_already_settled_the_work(self):
        """The two store transition is ordered by milestones, never by an elapsed sleep.

        This used to give the collector two seconds to be released and assume that 50ms was enough
        for the guidance thread to reach the lock. A loaded CI runner can suspend either thread
        across those bounds, turning a correct lock into an intermittent green or red result.
        """
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, support.A_STAND_IN, "work", "done",
                 "2026-08-07T00:00:01Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn("bob", self.landed.conversation, (self.landed.message,), turn)
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", self.turn),
                               "finished report", turn=turn)

        entered = threading.Event()
        release = threading.Event()
        guidance_reached_lock = threading.Event()
        guidance_done = threading.Event()
        results = []
        reviews = []
        original = hosting._what_they_answered
        original_taken = asked.locking._taken

        def held(*values):
            entered.set()
            release.wait()
            return original(*values)

        def observed_taken(*values):
            if threading.current_thread() is guiding:
                guidance_reached_lock.set()
            return original_taken(*values)

        class Reviewed(hosting.Answering):
            def review_this(inner, agent, conversation, answer, from_agent, delegation_id,
                            answer_id):
                reviews.append((agent, conversation, answer, from_agent))
                return True

        def collect():
            hosting._collected_what_came_back(
                "ava", directory.where("ava"), Reviewed())

        def guide():
            results.append(asked._said_into(
                "ava", self.delegation, "include GUIDANCE=EMBER-284"))
            guidance_done.set()

        with mock.patch.object(hosting, "_what_they_answered", side_effect=held), \
                mock.patch.object(asked.locking, "_taken", side_effect=observed_taken):
            collecting = threading.Thread(target=collect)
            guiding = threading.Thread(target=guide)
            collecting.start()
            try:
                self.assertTrue(entered.wait(10), "collection did not reach the held answer")
                guiding.start()
                self.assertTrue(
                    guidance_reached_lock.wait(10), "guidance did not reach the shared lock")
                self.assertFalse(guidance_done.is_set(), "guidance walked through a held lock")
            finally:
                release.set()
            collecting.join(10)
            if guiding.ident is not None:
                guiding.join(10)

        self.assertFalse(collecting.is_alive(), "collection did not finish")
        self.assertIsNotNone(guiding.ident, "guidance did not start")
        self.assertFalse(guiding.is_alive(), "guidance did not finish")

        self.assertEqual([FAILED], results)
        self.assertEqual(["finished report"], [one[2] for one in reviews])
        self.assertEqual(["audit it", "finished report"], [
            one["body"] for one in arriving.messages("bob", self.landed.conversation)])

    def test_an_external_parent_is_answered_at_once_and_owes_the_review_to_a_later_pass(self):
        """A parent holding a claim this process cannot speak to is busy, not unanswered.

        The delegation settles on the durable record, because the alternative is a delegation that
        stands `working` for as long as somebody else's turn runs. What is still owed is the review,
        and the next pass is what offers it.
        """
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, support.A_STAND_IN, "work", "done",
                 "2026-08-07T00:00:01Z"))
            turn = conn.execute("SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn("bob", self.landed.conversation, (self.landed.message,), turn)
        arriving.said_by_agent("bob", kept.FROM_AGENT, kept.source_id_for("ava", self.turn),
                               "finished report", turn=turn)
        reviews = answering.OnADelegation(directory.logs("ava"), _reaching_no_channel)

        with turns.claiming("ava", self.parent.conversation):
            hosting._collected_what_came_back("ava", directory.where("ava"), reviews)
            self.assertIsNotNone(kept.one("ava", self.delegation).answered_at)
            result = [one for one in arriving.messages("ava", self.parent.conversation)
                      if one["author"] == arriving.BY_RUNDESK]
            self.assertEqual(1, len(result))
            self.assertIsNone(result[0]["turn_id"])

        hosting._reviewed_what_was_recorded("ava", directory.where("ava"), reviews)

        self.assertTrue(support.waited_until(
            lambda: bool(provider_kept.list_turns("ava")
                         and provider_kept.list_turns("ava")[0]["ended_at"]), 15))
        self.assertIsNotNone(kept.one("ava", self.delegation).answered_at)
        result = [one for one in arriving.messages("ava", self.parent.conversation)
                  if one["author"] == arriving.BY_RUNDESK]
        self.assertEqual(1, len(result))
        self.assertIsNotNone(result[0]["turn_id"])

    def test_a_terminal_unadmitted_result_claim_is_reoffered_and_settled_once(self):
        answer = self.completed_answer()
        stranded, old_turn = self.claimed_review_result(
            answer, provider_kept.STOPPED)
        reviews = answering.OnADelegation(directory.logs("ava"), _reaching_no_channel)

        hosting._collected_what_came_back("ava", directory.where("ava"), reviews)

        self.assertTrue(support.waited_until(
            lambda: kept.one("ava", self.delegation).answered_at is not None
            and provider_kept.list_turns("ava")[0]["ended_at"], 15))
        result = [one for one in arriving.messages("ava", self.parent.conversation)
                  if one["author"] == arriving.BY_RUNDESK]
        self.assertEqual(1, len(result))
        self.assertEqual(stranded.message, result[0]["id"])
        self.assertNotEqual(old_turn, result[0]["turn_id"])
        after = len(provider_kept.list_turns("ava"))

        hosting._collected_what_came_back("ava", directory.where("ava"), reviews)

        self.assertEqual(after, len(provider_kept.list_turns("ava")))
        self.assertEqual(1, len([
            one for one in arriving.messages("ava", self.parent.conversation)
            if one["author"] == arriving.BY_RUNDESK]))

    def test_a_working_turn_keeps_its_unadmitted_result_claim(self):
        answer = self.completed_answer()
        landed, working_turn = self.claimed_review_result(
            answer, provider_kept.WORKING)
        reviews = answering.OnADelegation(directory.logs("ava"), _reaching_no_channel)
        before = len(provider_kept.list_turns("ava"))

        hosting._collected_what_came_back("ava", directory.where("ava"), reviews)

        self.assertIsNone(kept.one("ava", self.delegation).answered_at)
        self.assertEqual(working_turn, arriving.turn_for_message(
            "ava", self.parent.conversation, landed.message))
        self.assertEqual(before, len(provider_kept.list_turns("ava")))

    def test_a_terminal_admitted_result_claim_is_not_reoffered(self):
        answer = self.completed_answer()
        landed, admitted_turn = self.claimed_review_result(
            answer, provider_kept.DONE, admitted=True)
        reviews = answering.OnADelegation(directory.logs("ava"), _reaching_no_channel)
        before = len(provider_kept.list_turns("ava"))

        hosting._collected_what_came_back("ava", directory.where("ava"), reviews)

        self.assertIsNotNone(kept.one("ava", self.delegation).answered_at)
        self.assertEqual(admitted_turn, arriving.turn_for_message(
            "ava", self.parent.conversation, landed.message))
        self.assertEqual(before, len(provider_kept.list_turns("ava")))

    def test_a_requested_stop_settles_without_a_review_or_response_turn(self):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, support.A_STAND_IN, "work", hosting.STOPPED,
                 "2026-08-10T00:00:01Z"))
            target_turn = conn.execute(
                "SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn(
            "bob", self.landed.conversation, (self.landed.message,), target_turn)
        kept.stop_asked("ava", self.delegation)

        class NoReview(hosting.Answering):
            def review_this(inner, *args, **kwargs):
                raise AssertionError(f"a stopped delegation was reviewed: {args} {kwargs}")

        before = len(provider_kept.list_turns("ava"))
        hosting._collected_what_came_back(
            "ava", directory.where("ava"), NoReview())

        settled = kept.one("ava", self.delegation)
        self.assertIsNone(settled.answered_at)
        self.assertIsNotNone(settled.stopped_at)
        self.assertEqual(before, len(provider_kept.list_turns("ava")))
        self.assertFalse(any(
            one["author"] == arriving.BY_RUNDESK
            for one in arriving.messages("ava", self.parent.conversation)))

        code, out, err = self.rundesk("asked", "--agent", "ava")
        self.assertEqual(OK, code, err)
        self.assertIn("stopped", out)
        self.assertNotIn("answered", out)

    def test_a_resumed_delegation_delivers_its_second_result_once(self):
        def answered(message, body):
            with records.writing(directory.records("bob")) as conn:
                conn.execute(
                    "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                    " created_at) VALUES (?, ?, ?, ?, ?)",
                    (self.landed.conversation, support.A_STAND_IN, "work", "done",
                     "2026-08-07T00:00:01Z"))
                turn = conn.execute(
                    "SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
            arriving.handled_by_turn("bob", self.landed.conversation, (message,), turn)
            arriving.said_by_agent(
                "bob", kept.FROM_AGENT, kept.source_id_for("ava", self.turn), body, turn=turn)

        reviews = answering.OnADelegation(directory.logs("ava"), _reaching_no_channel)
        answered(self.landed.message, "first result")
        hosting._collected_what_came_back("ava", directory.where("ava"), reviews)
        self.assertTrue(support.waited_until(
            lambda: bool(provider_kept.list_turns("ava")
                         and provider_kept.list_turns("ava")[0]["ended_at"]), 15))
        after_first = len(provider_kept.list_turns("ava"))

        code, _out, err = self.rundesk(
            "asked", "--agent", "ava", "resume", self.delegation, "check again")
        self.assertEqual(OK, code, err)
        resumed = arriving.messages("bob", self.landed.conversation)[-1]
        answered(resumed["id"], "different second result")
        hosting._collected_what_came_back("ava", directory.where("ava"), reviews)

        self.assertTrue(support.waited_until(
            lambda: len(provider_kept.list_turns("ava")) == after_first + 1
            and provider_kept.list_turns("ava")[0]["ended_at"], 15))
        results = [one for one in arriving.messages("ava", self.parent.conversation)
                   if one["author"] == arriving.BY_RUNDESK]
        self.assertEqual(1, sum("first result" in one["body"] for one in results))
        self.assertEqual(1, sum("different second result" in one["body"] for one in results))
        self.assertEqual(2, len(results))

    def test_a_pre_send_claim_is_not_collected_as_provider_admission(self):
        with records.writing(directory.records("bob")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (self.landed.conversation, support.A_STAND_IN, "work", "done",
                 "2026-08-07T00:00:01Z"))
            target_turn = conn.execute(
                "SELECT id FROM turns ORDER BY id DESC LIMIT 1").fetchone()[0]
        arriving.handled_by_turn(
            "bob", self.landed.conversation, (self.landed.message,), target_turn)
        arriving.said_by_agent(
            "bob", kept.FROM_AGENT, kept.source_id_for("ava", self.turn),
            "slow result", turn=target_turn)
        active = provider_kept.add_turn("ava", {
            "conversation_id": self.parent.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": "work",
        })
        words = turns.Words("ava", self.parent.conversation, active)
        release = threading.Event()

        class SlowRefusal:
            def say(inner, _line):
                self.assertTrue(release.wait(5))
                return False

            def no_more(inner):
                pass

        feeder = turns._speaking(
            "ava", active, SlowRefusal(), words.each(), reachable=words)
        reviews = answering.OnADelegation(directory.logs("ava"), _reaching_no_channel)
        with turns.claiming("ava", self.parent.conversation), \
                turns._reachable("ava", self.parent.conversation, words):
            began = time.monotonic()
            hosting._collected_what_came_back("ava", directory.where("ava"), reviews)
            self.assertGreaterEqual(time.monotonic() - began, answering.REVIEW_ADMITTED_WITHIN)
            self.assertIsNone(kept.one("ava", self.delegation).answered_at)
            hosting._collected_what_came_back("ava", directory.where("ava"), reviews)
            self.assertIsNone(kept.one("ava", self.delegation).answered_at)
            release.set()
            feeder.join(5)
            self.assertFalse(feeder.is_alive(), "the refusing feeder did not release its claim")
        provider_kept.finish_turn("ava", active, provider_kept.STOPPED)

        # **A pass that loses the admission race leaves the row owed on purpose, and the next
        # gateway beat is what collects it.** `review_this` waits `REVIEW_ADMITTED_WITHIN` — two
        # seconds — for its worker to prove it owns the durable result, and on a loaded machine the
        # worker takes longer than that: the turn still runs and still finishes, and the delegation
        # is deliberately left outstanding rather than marked on a claim that was never proven.
        # `_collected_what_came_back` says so where it declines to mark one.
        #
        # So the beat is modelled here rather than assumed away. One pass winning a two-second race
        # is a property of the machine this runs on, and asserting it made this the suite's most
        # frequent failure on a loaded runner — for a design that was working exactly as written.
        # The retry duplicates nothing: the answer carries a `delegation-result` external id, so the
        # second pass finds the message already written, and asks the turn that owns it instead of
        # starting another. The assertions below are what hold that to account.
        for _ in range(20):
            hosting._collected_what_came_back("ava", directory.where("ava"), reviews)
            if kept.one("ava", self.delegation).answered_at is not None:
                break
            time.sleep(0.1)

        self.assertTrue(support.waited_until(
            lambda: kept.one("ava", self.delegation).answered_at is not None
            and provider_kept.list_turns("ava")[0]["id"] != active
            and provider_kept.list_turns("ava")[0]["ended_at"]
            and not any(one.name == "review-bob" and one.is_alive()
                        for one in threading.enumerate()), 30))
        result = [one for one in arriving.messages("ava", self.parent.conversation)
                  if one["author"] == arriving.BY_RUNDESK]
        self.assertEqual(1, len(result))
        self.assertNotEqual(active, result[0]["turn_id"])


class _RefusingToOffer(answering.OnADelegation):
    """The real tenant seam, with the review of named delegations refused however often it is asked.

    A subclass rather than a patch, so the walk, the window and the busy question are the shipped
    ones and only the thing being reproduced is different.
    """

    def __init__(self, where, hosted, refusing):
        super().__init__(where, hosted)
        self.refusing = refusing

    def review_this(self, agent, conversation, answer, from_agent,
                    delegation_id="", answer_id=""):
        if delegation_id in self.refusing:
            raise records.Unreadable(f"{delegation_id} cannot be offered")
        return super().review_this(
            agent, conversation, answer, from_agent, delegation_id, answer_id)


class AnsweringAnUnattendedParentThatIsStillWorking(support.Isolated):
    """The shape that stranded a scheduled run: the parent handed work over from a turn of its own
    that is still going, and nothing in this process can speak to it.

    A scheduled turn runs in a process of its own, so the registry a steer needs is not this one's
    and the answer cannot be said into it. The target finished, its answer is durably recorded, and
    what has to be true is that the delegation says so — a parent waiting on a delegation it is
    itself blocking is a deadlock with no beat that ends it.
    """

    def setUp(self):
        super().setUp()
        directory.made("ava", support.A_STAND_IN)
        directory.made("bob", support.A_STAND_IN)
        self.parent = arriving.recorded_for_a_schedule("ava", "nightly", "review the exports")
        self.turn = provider_kept.add_turn("ava", {
            "conversation_id": self.parent.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": "work",
            "schedule_name": "nightly",
        })
        self.delegation = "del-9-ffeedd"
        self.landed = arriving.recorded_for_a_delegation(
            "bob", "ava", self.turn, "audit the exports", delegation_id=self.delegation)
        kept.made("ava", self.delegation, "bob", self.parent.conversation, self.turn)
        target = provider_kept.add_turn("bob", {
            "conversation_id": self.landed.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": "work",
        })
        arriving.handled_by_turn(
            "bob", self.landed.conversation, (self.landed.message,), target)
        arriving.said_by_agent(
            "bob", kept.FROM_AGENT, kept.source_id_for("ava", self.turn, self.delegation),
            "the exports reconcile", turn=target)
        provider_kept.finish_turn("bob", target, provider_kept.DONE)
        self.reviews = answering.OnADelegation(directory.logs("ava"), _reaching_no_channel)

    def results(self, delegation=None):
        """The recorded results of one delegation, which is never another's."""
        named = f"{arriving.A_DELEGATION_RESULT}{delegation or self.delegation}:"
        return [one for one in arriving.messages("ava", self.parent.conversation)
                if one["author"] == arriving.BY_RUNDESK
                and str(one["external_id"] or "").startswith(named)]

    def test_a_busy_parent_is_answered_and_still_gets_exactly_one_review(self):
        """No steering and no resume: the target answered once, and the parent never went idle.

        Before this, every pass recorded the same answer, found the parent busy, and left the row
        `working` — the delegation stayed active for as long as the parent turn did, which was
        until somebody stopped it by hand.
        """
        with turns.claiming("ava", self.parent.conversation):
            hosting._collected_what_came_back("ava", directory.where("ava"), self.reviews)
            hosting._collected_what_came_back("ava", directory.where("ava"), self.reviews)

            settled = kept.one("ava", self.delegation)
            self.assertIsNotNone(settled.answered_at, "the recorded answer did not settle")
            self.assertIsNone(settled.stopped_at)
            self.assertEqual(1, len(self.results()))
            self.assertIn("the exports reconcile", self.results()[0]["body"])
            self.assertIsNone(self.results()[0]["turn_id"], "a busy parent took a turn")
            self.assertEqual(
                [self.turn], [one["id"] for one in provider_kept.list_turns("ava")])

            code, out, err = self.rundesk("asked", "--agent", "ava", "show", self.delegation)
            self.assertEqual(OK, code, err)
            self.assertEqual("answered", _said(out, "state"))
            self.assertNotEqual("not yet", _said(out, "answered at"))

        hosting._reviewed_what_was_recorded("ava", directory.where("ava"), self.reviews)
        self.assertTrue(support.waited_until(
            lambda: len(provider_kept.list_turns("ava")) == 2
            and provider_kept.list_turns("ava")[0]["ended_at"], 15))
        review = provider_kept.list_turns("ava")[0]["id"]

        hosting._reviewed_what_was_recorded("ava", directory.where("ava"), self.reviews)
        hosting._collected_what_came_back("ava", directory.where("ava"), self.reviews)

        self.assertEqual([review, self.turn],
                         [one["id"] for one in provider_kept.list_turns("ava")])
        self.assertEqual(1, len(self.results()))
        self.assertEqual(review, self.results()[0]["turn_id"])

    def another_ask(self, delegation_id, answer="another report"):
        """A second ask from the same parent turn, answered and terminal in the target's store."""
        landed = arriving.recorded_for_a_delegation(
            "bob", "ava", self.turn, f"audit for {delegation_id}", delegation_id=delegation_id)
        kept.made("ava", delegation_id, "bob", self.parent.conversation, self.turn)
        target = provider_kept.add_turn("bob", {
            "conversation_id": landed.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": "work",
        })
        arriving.handled_by_turn("bob", landed.conversation, (landed.message,), target)
        arriving.said_by_agent(
            "bob", kept.FROM_AGENT, kept.source_id_for("ava", self.turn, delegation_id),
            answer, turn=target)
        provider_kept.finish_turn("bob", target, provider_kept.DONE)
        return target

    def a_recorded_result(self, delegation_id, answer_id, reviewed=False):
        """One result in the parent's conversation, optionally one a turn has already read."""
        landed = arriving.said_by_rundesk_into(
            "ava", self.parent.conversation, f"{delegation_id} answered in phase {answer_id}",
            external_id=f"{arriving.A_DELEGATION_RESULT}{delegation_id}:{answer_id}")
        if reviewed:
            owner = provider_kept.add_turn("ava", {
                "conversation_id": self.parent.conversation,
                "provider_name": support.A_STAND_IN,
                "access_mode": "work",
            })
            arriving.handled_by_turn(
                "ava", self.parent.conversation, (landed.message,), owner)
            provider_kept.add_turn_record(
                "ava", owner, turns.ADMITTED, {"messages": [landed.message]})
            provider_kept.finish_turn("ava", owner, provider_kept.DONE)
        return landed

    def carried_on(self, delegation_id):
        """Answered, then carried on: working again, with the result of its first phase unread.

        The further task is written into the target's conversation as `asked resume` writes it, so
        the target owes an answer it has not given and this delegation is genuinely working — not
        merely a row with a timestamp cleared.
        """
        self.another_ask(delegation_id)
        kept.answered("ava", delegation_id)
        stale = self.a_recorded_result(delegation_id, "1")
        kept.reopened("ava", delegation_id)
        arriving.recorded_for_a_delegation(
            "bob", "ava", self.turn, "and check retention", delegation_id=delegation_id)
        return stale

    def already_read(self, delegation_id):
        """Answered and reviewed, with the row an earlier phase left behind still unclaimed."""
        target = self.another_ask(delegation_id)
        stale = self.a_recorded_result(delegation_id, "1")
        self.a_recorded_result(delegation_id, str(target), reviewed=True)
        kept.answered("ava", delegation_id)
        return stale

    def forgotten(self, delegation_id):
        """A recorded result whose delegation this store no longer holds at all."""
        return self.a_recorded_result(delegation_id, "1")

    def the_answered_one_is_reviewed_once(self, stale):
        """Record this delegation's answer behind `stale`, sweep, and say what became of both.

        **The passes are counted rather than repeated until it works.** A pass may look at two
        candidates, so an answer behind `n` of them is reached on the pass that reaches it and not
        before: asserting the number is what keeps a walk that stopped walking visible.
        """
        with turns.claiming("ava", self.parent.conversation):
            hosting._collected_what_came_back("ava", directory.where("ava"), self.reviews)
        self.assertIsNotNone(kept.one("ava", self.delegation).answered_at)
        before = {one["id"] for one in provider_kept.list_turns("ava")}
        # Counted off the rows themselves: a shape whose result is superseded is not a candidate at
        # all, so what decides the number of passes is what a look would hand back and not what the
        # case wrote down.
        waiting = len(arriving.pending_delegation_results(
            "ava", 0, hosting.INSPECTED_AT_MOST).owed)
        needed = -(-waiting // hosting.REVIEWED_AT_MOST)

        for passes in range(1, needed + 1):
            hosting._reviewed_what_was_recorded("ava", directory.where("ava"), self.reviews)
            self.assertTrue(support.waited_until(
                lambda: not any(one.name.startswith("review-") and one.is_alive()
                                for one in threading.enumerate()), 15))
            self.assertEqual(
                passes == needed, self.results()[0]["turn_id"] is not None,
                f"pass {passes} of the {needed} this walk needs did not leave what it should")

        review = self.results()[0]["turn_id"]
        self.assertNotIn(review, before, "no new turn read the answered result")
        self.assertEqual(1, len(self.results()), "the answer was recorded twice")
        self.assertEqual(
            [review], [one["id"] for one in provider_kept.list_turns("ava")
                       if one["id"] not in before],
            "a pass started a turn for work nothing owes a review")
        self.assertEqual([None] * len(stale), [
            one["turn_id"] for one in arriving.messages("ava", self.parent.conversation)
            if one["id"] in {landed.message for landed in stale}],
            "a result nothing owes a review was read")

    def test_carried_on_delegations_cannot_starve_an_answered_one(self):
        """Their rows are the oldest there are, and their delegations are working rather than
        answered — so a pass that spent its bound on candidates spent it here for ever."""
        self.the_answered_one_is_reviewed_once(
            [self.carried_on("del-a-ccbbaa"), self.carried_on("del-b-ccbbaa")])

    def test_already_read_delegations_older_phases_cannot_starve_an_answered_one(self):
        """The delegation is answered and its current result has been read; what is left unclaimed
        is an earlier phase nothing will ever be woken for."""
        self.the_answered_one_is_reviewed_once(
            [self.already_read("del-c-ccbbaa"), self.already_read("del-d-ccbbaa")])

    def test_forgotten_delegations_cannot_starve_an_answered_one(self):
        """The message outlives the row, and the history keeps it: there is nothing to look up and
        nothing that will ever make these reviewable."""
        self.the_answered_one_is_reviewed_once(
            [self.forgotten("del-e-ccbbaa"), self.forgotten("del-f-ccbbaa")])

    def test_repeated_passes_over_every_stale_shape_still_reach_the_answered_one(self):
        """All three together, and more of them than one pass may ever offer, swept three times."""
        self.the_answered_one_is_reviewed_once([
            self.carried_on("del-a-ccbbaa"), self.carried_on("del-b-ccbbaa"),
            self.already_read("del-c-ccbbaa"), self.already_read("del-d-ccbbaa"),
            self.forgotten("del-e-ccbbaa"), self.forgotten("del-f-ccbbaa"),
        ])

    def unreadable_target(self, delegation_id):
        """Answered, owed a review, and handed to an agent whose records are not there.

        Its row passes every check this sweep makes; what fails is the read of the other store, and
        it fails the same way on every pass for as long as the row and the message are there.
        """
        kept.made("ava", delegation_id, "nowhere", self.parent.conversation, self.turn)
        kept.answered("ava", delegation_id)
        return self.a_recorded_result(delegation_id, "1")

    def owed_and_refused(self, delegation_id):
        """Answered, owed a review, readable — and a review that will not start."""
        self.another_ask(delegation_id)
        kept.answered("ava", delegation_id)
        return self.a_recorded_result(delegation_id, "1")

    def beats(self, how_many):
        """Run the sweep like the gateway does, and say what each pass spent."""
        spent = []
        for _ in range(how_many):
            lines = self.logged()
            with mock.patch.object(hosting.kept, "one", wraps=kept.one) as rows, \
                    mock.patch.object(hosting, "_what_they_answered",
                                      wraps=hosting._what_they_answered) as reads, \
                    mock.patch.object(type(self.reviews), "review_this",
                                      autospec=True,
                                      side_effect=type(self.reviews).review_this) as offers:
                hosting._reviewed_what_was_recorded(
                    "ava", directory.where("ava"), self.reviews)
                spent.append((rows.call_count, reads.call_count, offers.call_count,
                              self.logged() - lines))
            self.assertTrue(support.waited_until(
                lambda: not any(one.name.startswith("review-") and one.is_alive()
                                for one in threading.enumerate()), 15))
        return spent

    def logged(self):
        return sum("could not be reviewed" in line
                   for path in sorted(directory.logs("ava").glob("*"))
                   for line in path.read_text(encoding="utf-8").splitlines())

    def the_third_one_is_reviewed_once(self, spent):
        """Every pass inside its bounds, and the answer behind the two reached all the same."""
        for rows, reads, offers, lines in spent:
            self.assertLessEqual(rows, hosting.REVIEWED_AT_MOST, "too many rows read in one pass")
            self.assertLessEqual(reads, hosting.REVIEWED_AT_MOST, "too many other stores read")
            self.assertLessEqual(offers, hosting.REVIEWED_AT_MOST, "too many reviews started")
            self.assertLessEqual(lines, hosting.REVIEWED_AT_MOST, "too much said about one pass")
        self.assertEqual(1, len(self.results()))
        review = self.results()[0]["turn_id"]
        self.assertIsNotNone(review, "the answered result was never reached")
        self.assertEqual(
            [self.results()[0]["id"]],
            [one["id"] for one in arriving.messages("ava", self.parent.conversation)
             if one["turn_id"] == review
             and str(one["external_id"] or "").startswith(arriving.A_DELEGATION_RESULT)],
            "the review turn took a result it was not owed")

    def test_answers_whose_target_cannot_be_read_do_not_hold_the_pass_for_ever(self):
        """Piper's first shape, and the whole of what a bound alone does not fix: two candidates
        that are eligible, are read, and fail — with fewer rows in the store than one look holds, so
        every pass sees the same window."""
        stale = [self.unreadable_target("del-x-ccbbaa"), self.unreadable_target("del-y-ccbbaa")]
        with turns.claiming("ava", self.parent.conversation):
            hosting._collected_what_came_back("ava", directory.where("ava"), self.reviews)
        self.assertIsNotNone(kept.one("ava", self.delegation).answered_at)

        spent = self.beats(4)

        self.the_third_one_is_reviewed_once(spent)
        self.assertEqual([None, None], [
            one["turn_id"] for one in arriving.messages("ava", self.parent.conversation)
            if one["id"] in {landed.message for landed in stale}])

    def test_answers_whose_review_will_not_start_do_not_hold_the_pass_for_ever(self):
        """Piper's second shape. The same two candidates reach the offer and it raises every time,
        which before this correction was two log lines a beat for ever and no third review."""
        refusing = ["del-p-ccbbaa", "del-q-ccbbaa"]
        stale = [self.owed_and_refused(one) for one in refusing]
        self.reviews = _RefusingToOffer(
            directory.logs("ava"), _reaching_no_channel, tuple(refusing))
        with turns.claiming("ava", self.parent.conversation):
            hosting._collected_what_came_back("ava", directory.where("ava"), self.reviews)
        self.assertIsNotNone(kept.one("ava", self.delegation).answered_at)

        spent = self.beats(4)

        self.the_third_one_is_reviewed_once(spent)
        self.assertEqual([None, None], [
            one["turn_id"] for one in arriving.messages("ava", self.parent.conversation)
            if one["id"] in {landed.message for landed in stale}])
        self.assertLessEqual(self.logged(), 2 * hosting.REVIEWED_AT_MOST,
                             "the log grew with the passes rather than with the failures")

    def test_more_stale_results_than_one_pass_looks_at_still_reach_the_answered_one(self):
        """The bound is on the look as well as the offer, so the look has to move.

        Six recorded results, five of them owed to nothing, and a pass that may look at two: a look
        that started at the head every time would read the same two for ever. What is proved here is
        both halves — every pass stays inside its bounds, and the answer is still reached.
        """
        for number in range(5):
            self.forgotten(f"del-{number}-ccbbaa")
        with turns.claiming("ava", self.parent.conversation):
            hosting._collected_what_came_back("ava", directory.where("ava"), self.reviews)
        self.assertIsNotNone(kept.one("ava", self.delegation).answered_at)

        passes = 0
        with mock.patch.object(hosting, "INSPECTED_AT_MOST", 2):
            while passes < 6 and self.results()[0]["turn_id"] is None:
                passes += 1
                with mock.patch.object(hosting.kept, "one", wraps=kept.one) as rows, \
                        mock.patch.object(hosting, "_what_they_answered",
                                          wraps=hosting._what_they_answered) as reads:
                    hosting._reviewed_what_was_recorded(
                        "ava", directory.where("ava"), self.reviews)
                    self.assertLessEqual(rows.call_count, 2, "one pass looked past its window")
                    self.assertLessEqual(reads.call_count, hosting.REVIEWED_AT_MOST,
                                         "one pass read another store more often than it may")
                self.assertTrue(support.waited_until(
                    lambda: not any(one.name.startswith("review-") and one.is_alive()
                                    for one in threading.enumerate()), 15))

        self.assertEqual(3, passes, "the walk took more passes than its window needs")
        self.assertIsNotNone(self.results()[0]["turn_id"], "the answered result was never reached")

    def test_a_replacement_gateway_begins_the_walk_again_rather_than_losing_it(self):
        """Where the walk has got to is this process's. A gateway that went down restarts it at the
        oldest end, which delays a pass and loses nothing: every row is still read."""
        for number in range(4):
            self.forgotten(f"del-{number}-ccbbaa")

        walked = self.reviews.recorded_reviews("ava", 2, 2)
        carried_on = self.reviews.recorded_reviews("ava", 2, 2)
        replacement = answering.OnADelegation(directory.logs("ava"), _reaching_no_channel)

        self.assertEqual(("del-0-ccbbaa", "del-1-ccbbaa"), walked)
        self.assertEqual(("del-2-ccbbaa", "del-3-ccbbaa"), carried_on)
        self.assertEqual(walked, replacement.recorded_reviews("ava", 2, 2))

    def test_a_recorded_answer_is_offered_again_only_where_a_turn_could_start(self):
        """And a busy one is passed over rather than pinned to: the walk moves past it, so two of
        them in a room that never goes quiet cannot hold everything behind them."""
        def owed():
            return self.reviews.recorded_reviews(
                "ava", hosting.REVIEWED_AT_MOST, hosting.INSPECTED_AT_MOST)

        with turns.claiming("ava", self.parent.conversation):
            hosting._collected_what_came_back("ava", directory.where("ava"), self.reviews)

            self.assertEqual((), owed())
        self.assertEqual((), owed(), "the look after a busy one did not reach the end")
        self.assertEqual((self.delegation,), owed())


if __name__ == "__main__":
    unittest.main()
