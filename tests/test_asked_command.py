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
from rundesk.providers import answering, turns
from rundesk.providers import kept as provider_kept


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

    def guide(self):
        return self.rundesk("asked", "--agent", "ava", "say", self.delegation,
                            "include GUIDANCE=EMBER-284")

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
        guidance_done = threading.Event()
        results = []
        reviews = []
        original = hosting._what_they_answered

        def held(*values):
            entered.set()
            self.assertTrue(release.wait(2))
            return original(*values)

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

        with mock.patch.object(hosting, "_what_they_answered", side_effect=held):
            collecting = threading.Thread(target=collect)
            collecting.start()
            self.assertTrue(entered.wait(2))
            guiding = threading.Thread(target=guide)
            guiding.start()
            self.assertFalse(guidance_done.wait(0.05))
            release.set()
            collecting.join(2)
            guiding.join(2)

        self.assertEqual([FAILED], results)
        self.assertEqual(["finished report"], [one[2] for one in reviews])
        self.assertEqual(["audit it", "finished report"], [
            one["body"] for one in arriving.messages("bob", self.landed.conversation)])

    def test_an_external_parent_keeps_the_result_owed_until_a_review_turn_is_admitted(self):
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
            self.assertIsNone(kept.one("ava", self.delegation).answered_at)
            result = [one for one in arriving.messages("ava", self.parent.conversation)
                      if one["author"] == arriving.BY_RUNDESK]
            self.assertEqual(1, len(result))
            self.assertIsNone(result[0]["turn_id"])

        hosting._collected_what_came_back("ava", directory.where("ava"), reviews)

        self.assertTrue(support.waited_until(
            lambda: bool(provider_kept.list_turns("ava")
                         and provider_kept.list_turns("ava")[0]["ended_at"]), 15))
        self.assertIsNotNone(kept.one("ava", self.delegation).answered_at)
        result = [one for one in arriving.messages("ava", self.parent.conversation)
                  if one["author"] == arriving.BY_RUNDESK]
        self.assertEqual(1, len(result))
        self.assertIsNotNone(result[0]["turn_id"])

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


if __name__ == "__main__":
    unittest.main()
