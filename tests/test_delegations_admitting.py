"""Whether one agent may hand work to another, and what it is told when it may not.

Every case here is a refusal somebody reads. The guards are cheap and there are only two of them,
which is the point: the previous build walked an array of everyone the work had passed through,
because its depth rule was legal on one path and refused on the other. Held to uniformly, depth one
makes a cycle unconstructible and there is nothing to walk.

Run directly: `python3 tests/test_delegations_admitting.py`
"""

import unittest

import support
from rundesk.agents import directory, records
from rundesk.core import paths
from rundesk.delegations import admitting, kept

#: A turn of ava's, as the gateway would have described it to a brain.
AVAS_TURN = {admitting.AGENT: "ava", admitting.RUN: "12"}


class WhoIsAsking(support.Isolated):
    """Read off the environment, because a command run from inside a turn has nothing passed to it."""

    def test_an_agents_own_turn_is_one(self):
        asking = admitting.whoever_is_asking(AVAS_TURN)
        self.assertEqual(("ava", 12), (asking.agent, asking.run))
        self.assertTrue(asking.is_a_turn)

    def test_a_person_at_a_terminal_is_not(self):
        self.assertFalse(admitting.whoever_is_asking({}).is_a_turn)

    def test_an_agent_named_with_no_turn_is_not_a_turn(self):
        """`RUNDESK_AGENT` outlives a turn in a shell somebody left open; `RUNDESK_RUN` does not."""
        self.assertFalse(admitting.whoever_is_asking({admitting.AGENT: "ava"}).is_a_turn)

    def test_a_run_that_is_not_a_number_is_no_run_rather_than_a_crash(self):
        asking = admitting.whoever_is_asking({admitting.AGENT: "ava", admitting.RUN: "later"})
        self.assertIsNone(asking.run)
        self.assertFalse(asking.is_a_turn)


class WhatIsRefused(support.Isolated):

    def refusal(self, said=None, to_agent="bob", task="audit the exporter", **more):
        return admitting.refusal(admitting.whoever_is_asking(AVAS_TURN if said is None else said),
                                 to_agent, task, **more)

    def test_a_turn_of_this_agents_own_may_hand_work_over(self):
        self.assertEqual("", self.refusal())

    def test_a_person_at_a_terminal_may_not(self):
        """`rundesk ask bob` typed by somebody is an ordinary turn on bob, not a delegation."""
        said = self.refusal({})
        self.assertIn("only an agent's own turn", said)

    def test_an_agent_may_not_hand_work_to_itself(self):
        said = self.refusal(to_agent="ava")
        self.assertIn("cannot hand work to itself", said)
        self.assertIn("that is a turn", said)

    def test_a_turn_already_answering_a_delegation_may_not_hand_it_on(self):
        """Depth one. This is what makes a cycle unconstructible rather than merely refused."""
        said = self.refusal({**AVAS_TURN, admitting.ANSWERING: "del-1-aaaa"})
        self.assertIn("cannot be handed on again", said)

    def test_and_it_says_what_to_do_instead(self):
        said = self.refusal({**AVAS_TURN, admitting.ANSWERING: "del-1-aaaa"})
        self.assertIn("finish it here", said)

    def test_nothing_to_hand_over_is_refused(self):
        self.assertIn("nothing to hand over", self.refusal(task="   "))

    def test_a_task_longer_than_the_ceiling_names_the_ceiling_and_the_length(self):
        said = self.refusal(task="x" * (admitting.A_TASK_AT_MOST + 1))
        self.assertIn(str(admitting.A_TASK_AT_MOST), said)
        self.assertIn(str(admitting.A_TASK_AT_MOST + 1), said)


class WhetherAnythingWouldAnswer(support.Isolated):
    """A delegation to an agent nothing is running is work that waits for ever, and an agent that
    believes it handed work over is worse off than one told it could not."""

    def refusal(self, **more):
        return admitting.refusal(admitting.whoever_is_asking(AVAS_TURN), "bob", "audit it", **more)

    def test_a_gateway_that_is_definitely_offline_refuses_and_says_how_to_start_it(self):
        said = self.refusal(nothing_would_answer=True)
        self.assertIn("no gateway running", said)
        self.assertIn("rundesk gateways start bob", said)

    def test_a_gateway_that_is_online_is_admitted(self):
        self.assertEqual("", self.refusal(nothing_would_answer=False))

    def test_a_gateway_nobody_can_tell_about_is_admitted(self):
        """**Refusing on uncertainty is the worse of the two errors.** `standing` answers three
        things and the caller collapses only the definite one into a refusal."""
        self.assertEqual("", self.refusal())


class WritingItDown(support.Isolated):

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("ava", "a-stand-in")
        with records.writing(directory.records("ava")) as conn:
            conn.execute(
                "INSERT INTO conversations (source, source_id, created_at) VALUES (?, ?, ?)",
                ("terminal", "one", "2026-08-06T00:00:00Z"))
            self.conversation = conn.execute("SELECT id FROM conversations").fetchone()[0]
            conn.execute(
                "INSERT INTO turns (id, conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (12, ?, ?, ?, ?, ?)",
                (self.conversation, "a-stand-in", "work", "working", "2026-08-06T00:00:00Z"))

    def test_it_lands_in_the_asking_agents_own_store(self):
        admitting.admitted(admitting.whoever_is_asking(AVAS_TURN), "del-1-aaaa", "bob",
                           self.conversation)
        said = kept.one("ava", "del-1-aaaa")
        self.assertEqual(("bob", 12), (said.to_agent, said.parent_turn))

    def test_a_terminal_cannot_write_one_even_by_calling_this_directly(self):
        """`refusal` is what a command reads, and this is the floor under it — the two are not the
        same check, but the one that writes must not be the one that trusts."""
        with self.assertRaises(admitting.Refused):
            admitting.admitted(admitting.whoever_is_asking({}), "del-1-aaaa", "bob",
                               self.conversation)


if __name__ == "__main__":
    unittest.main()
