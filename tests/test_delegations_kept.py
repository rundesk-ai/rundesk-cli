"""The delegations one agent has made, and the rule about whose store they stand in.

Two guarantees here cost something the day they are wrong, and neither is visible from reading the
code. **Delivering once** is a `WHERE` clause rather than a decision, so two gateways looking at the
same settled work cannot both wake the delegator. And **a gateway reads another agent's store and
never writes it**, which SQLite enforces because the connection is opened read-only — a case proves
the refusal rather than trusting the mode string.

Run directly: `python3 tests/test_delegations_kept.py`
"""

import sqlite3
import unittest

import support
from rundesk.agents import directory, records
from rundesk.core import paths
from rundesk.delegations import kept


class TwoAgents(support.Isolated):
    """Ava delegates, bob answers — the shape every case here is about."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("ava", "a-stand-in")
        directory.made("bob", "a-stand-in")
        self.conversation, self.turn = self.a_turn_of("ava")

    def a_turn_of(self, agent):
        """A conversation and a turn in that agent's store, for a delegation to point at."""
        with records.writing(directory.records(agent)) as conn:
            conn.execute(
                "INSERT INTO conversations (source, source_id, created_at) VALUES (?, ?, ?)",
                ("terminal", "one", "2026-08-06T00:00:00Z"))
            conversation = conn.execute("SELECT id FROM conversations").fetchone()[0]
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation, "a-stand-in", "work", "working", "2026-08-06T00:00:00Z"))
            turn = conn.execute("SELECT id FROM turns").fetchone()[0]
        return conversation, turn

    def ava_delegates(self, delegation_id="del-1-aaaa", **more):
        said = {"kind": kept.AGENT, "to_agent": "bob",
                "parent_conversation": self.conversation, "parent_turn": self.turn}
        said.update(more)
        kept.made("ava", delegation_id, **said)
        return delegation_id


class WritingOneDown(TwoAgents):

    def test_it_stands_in_the_store_of_the_agent_that_made_it(self):
        self.ava_delegates()
        self.assertEqual(1, len(kept.every("ava")))
        # And in nobody else's. Bob holds no record of somebody else's bookkeeping.
        self.assertEqual([], kept.every("bob"))

    def test_a_kind_that_is_neither_is_refused_in_words_rather_than_by_the_table(self):
        with self.assertRaises(kept.Refused) as caught:
            self.ava_delegates(kind="schedule")
        self.assertIn("schedule", str(caught.exception))

    def test_delegating_to_an_agent_without_naming_one_says_what_was_missing(self):
        """The table refuses it too. **The sentence is what this guard is for** — SQLite answers
        `CHECK constraint failed: delegations`, which names the table and not the mistake."""
        with self.assertRaises(kept.Refused) as caught:
            self.ava_delegates(to_agent=None)
        self.assertIn("has to name the agent", str(caught.exception))
        self.assertNotIn("CHECK constraint", str(caught.exception))

    def test_a_role_run_without_naming_a_role_says_what_was_missing(self):
        with self.assertRaises(kept.Refused) as caught:
            self.ava_delegates(kind=kept.ROLE, to_agent=None)
        self.assertIn("has to name the role", str(caught.exception))
        self.assertNotIn("CHECK constraint", str(caught.exception))

    def test_a_role_run_names_the_role_and_the_revision_it_was_admitted_against(self):
        self.ava_delegates(kind=kept.ROLE, to_agent=None, role="review", revision="abc123")
        said = kept.one("ava", "del-1-aaaa")
        self.assertEqual(("review", "abc123"), (said.role, said.revision))
        self.assertEqual("review", said.handed_to)

    def test_two_may_not_share_an_id(self):
        self.ava_delegates()
        with self.assertRaises(kept.Refused):
            self.ava_delegates()

    def test_one_nobody_made_is_not_there_rather_than_empty(self):
        with self.assertRaises(records.NotThere):
            kept.one("ava", "del-9-zzzz")


class FindingWorkToDo(TwoAgents):

    def test_an_answering_agent_finds_what_was_handed_to_it(self):
        self.ava_delegates("del-1-aaaa")
        self.ava_delegates("del-2-bbbb", to_agent="nina")
        waiting = kept.outstanding("ava", to_agent="bob")
        self.assertEqual(["del-1-aaaa"], [one.delegation_id for one in waiting])

    def test_a_role_run_is_never_work_for_another_agent(self):
        """`to_agent` is null on a role run, and a query that matched it would hand one agent's
        private mode to somebody else's gateway."""
        self.ava_delegates(kind=kept.ROLE, to_agent=None, role="review")
        self.assertEqual([], kept.outstanding("ava", to_agent="bob"))
        self.assertEqual(1, len(kept.outstanding("ava")))

    def test_what_has_been_answered_is_no_longer_waiting(self):
        self.ava_delegates()
        kept.answered("ava", "del-1-aaaa")
        self.assertEqual([], kept.outstanding("ava", to_agent="bob"))

    def test_the_oldest_is_offered_first_so_nothing_waits_behind_what_came_later(self):
        for one in ("del-1-aaaa", "del-2-bbbb", "del-3-cccc"):
            self.ava_delegates(one)
        self.assertEqual(["del-1-aaaa", "del-2-bbbb", "del-3-cccc"],
                         [one.delegation_id for one in kept.outstanding("ava")])


class DeliveringExactlyOnce(TwoAgents):
    """The guarantee that stops a delegator being woken twice for one answer."""

    def test_the_first_call_delivers_and_the_second_does_not(self):
        self.ava_delegates()
        self.assertTrue(kept.answered("ava", "del-1-aaaa"))
        self.assertFalse(kept.answered("ava", "del-1-aaaa"))

    def test_it_is_the_row_that_decides_rather_than_the_caller(self):
        """Two gateways both seeing settled work is the real case, and neither reads before it
        writes — whichever `UPDATE` matches a row still owing an answer is the one that delivers."""
        self.ava_delegates()
        answered = [kept.answered("ava", "del-1-aaaa") for _ in range(5)]
        self.assertEqual(1, answered.count(True))

    def test_delivering_one_nobody_made_says_so_rather_than_claiming_it_did(self):
        self.assertFalse(kept.answered("ava", "del-9-zzzz"))


class AskingOneToStop(TwoAgents):

    def test_a_stop_is_recorded_for_whatever_carries_the_work(self):
        self.ava_delegates()
        self.assertTrue(kept.stop_asked("ava", "del-1-aaaa"))
        self.assertIsNotNone(kept.one("ava", "del-1-aaaa").stop_asked_at)

    def test_asking_twice_says_the_second_changed_nothing(self):
        self.ava_delegates()
        kept.stop_asked("ava", "del-1-aaaa")
        self.assertFalse(kept.stop_asked("ava", "del-1-aaaa"))

    def test_stopping_one_that_is_already_over_says_so(self):
        self.ava_delegates()
        kept.answered("ava", "del-1-aaaa")
        self.assertFalse(kept.stop_asked("ava", "del-1-aaaa"))


class CountingAttemptsAtStartingIt(TwoAgents):
    """A failed start produces no turn, which is exactly why this cannot be counted off `turns`."""

    def test_each_attempt_counts_and_the_count_comes_back(self):
        self.ava_delegates()
        self.assertEqual([1, 2, 3], [kept.tried("ava", "del-1-aaaa") for _ in range(3)])

    def test_counting_one_nobody_made_answers_none_rather_than_raising(self):
        self.assertEqual(0, kept.tried("ava", "del-9-zzzz"))


class WhereTheWorkStands(support.Isolated):
    """The key is constructed rather than stored, so nothing can point at the wrong database."""

    def test_a_delegation_to_an_agent_is_keyed_by_who_asked_and_which_turn(self):
        self.assertEqual("ava/12", kept.source_id_for(kept.AGENT, "ava", 12, "del-1-aaaa"))

    def test_two_delegations_from_one_turn_share_a_conversation(self):
        """So they share a provider session, and the answering agent is not made to start again."""
        self.assertEqual(kept.source_id_for(kept.AGENT, "ava", 12, "del-1-aaaa"),
                         kept.source_id_for(kept.AGENT, "ava", 12, "del-2-bbbb"))

    def test_one_from_a_later_turn_does_not(self):
        self.assertNotEqual(kept.source_id_for(kept.AGENT, "ava", 12, "del-1-aaaa"),
                            kept.source_id_for(kept.AGENT, "ava", 13, "del-2-bbbb"))

    def test_a_role_run_is_keyed_by_the_run_because_it_has_no_identity_to_share_one_with(self):
        self.assertEqual("rol-1-aaaa", kept.source_id_for(kept.ROLE, "ava", 12, "rol-1-aaaa"))


class ReadingSomebodyElsesStore(TwoAgents):
    """The ownership rule, and SQLite is what keeps it rather than anybody's care."""

    def test_another_agents_delegations_are_readable(self):
        self.ava_delegates()
        self.assertEqual(1, len(kept.outstanding("ava", to_agent="bob")))

    def test_and_the_connection_that_reads_them_cannot_write(self):
        with records.reading(directory.records("ava")) as conn:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                conn.execute("UPDATE delegations SET to_agent = 'nina'")
        self.assertIn("readonly", str(caught.exception).lower())


class RecordsThatCannotAnswer(TwoAgents):

    def test_an_agent_carried_no_further_than_the_turns_is_unreadable_rather_than_empty(self):
        """Told "none", a caller goes on believing this agent has handed nothing over."""
        with records.writing(directory.records("ava")) as conn:
            conn.execute("DROP TABLE delegations")
        with self.assertRaises(records.Unreadable):
            kept.every("ava")


if __name__ == "__main__":
    unittest.main()
