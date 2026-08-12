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
from datetime import datetime, timedelta, timezone

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
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
        said = {"to_agent": "bob",
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

    def test_delegating_without_naming_an_agent_says_what_was_missing(self):
        """The table refuses it too. **The sentence is what this guard is for** — SQLite answers
        `NOT NULL constraint failed: delegations.to_agent`, naming a column and not the mistake."""
        with self.assertRaises(kept.Refused) as caught:
            self.ava_delegates(to_agent="")
        self.assertIn("has to name the agent it goes to", str(caught.exception))
        self.assertNotIn("constraint", str(caught.exception))

    def test_two_may_not_share_an_id(self):
        self.ava_delegates()
        with self.assertRaises(kept.Refused):
            self.ava_delegates()

    def test_one_nobody_made_is_not_there_rather_than_empty(self):
        with self.assertRaises(records.NotThere):
            kept.one("ava", "del-9-zzzz")

    def test_requested_and_effective_provider_model_round_trip_separately(self):
        kept.made(
            "ava", "del-1-aaaa", "bob", self.conversation, self.turn,
            requested_provider_name="./codex", requested_model_name="asked-model",
            provider_name="codex", model_name="asked-model")

        one = kept.one("ava", "del-1-aaaa")

        self.assertEqual(("./codex", "asked-model", "codex", "asked-model"),
                         (one.requested_provider_name, one.requested_model_name,
                          one.provider_name, one.model_name))

    def test_no_override_keeps_the_compatible_absent_provenance(self):
        self.ava_delegates()
        one = kept.one("ava", "del-1-aaaa")
        self.assertEqual((None, None, None, None),
                         (one.requested_provider_name, one.requested_model_name,
                          one.provider_name, one.model_name))


class FindingWorkToDo(TwoAgents):

    def test_an_answering_agent_finds_what_was_handed_to_it(self):
        self.ava_delegates("del-1-aaaa")
        self.ava_delegates("del-2-bbbb", to_agent="nina")
        waiting = kept.outstanding("ava", to_agent="bob")
        self.assertEqual(["del-1-aaaa"], [one.delegation_id for one in waiting])

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


class StoppingExactlyOnce(TwoAgents):
    """A requested stop is terminal without pretending an answer came back."""

    def test_stopped_work_is_terminal_and_distinct_from_answered_work(self):
        self.ava_delegates()

        self.assertTrue(kept.stopped("ava", "del-1-aaaa"))
        one = kept.one("ava", "del-1-aaaa")

        self.assertIsNotNone(one.stopped_at)
        self.assertIsNone(one.answered_at)
        self.assertEqual([], kept.outstanding("ava", to_agent="bob"))

    def test_only_the_first_gateway_pass_can_settle_the_stop(self):
        self.ava_delegates()
        self.assertTrue(kept.stopped("ava", "del-1-aaaa"))
        self.assertFalse(kept.stopped("ava", "del-1-aaaa"))


class WhenThePhaseOfWorkBegan(TwoAgents):
    """`working_since`, and the one verb that is allowed to move it.

    A resumed delegation is new work in an old row, and before this column existed there was nothing
    written down that said so: every elapsed time was counted from `created_at`, so a room watching
    an hour-old delegation get carried on was told *"still working · 1h"* on the next beat, before
    the agent had done a second of it.

    The rule has two halves and both are here, because a fix that only did the first would be worse
    than the defect — a clock that any steer restarted would make busy work look permanently new.
    """

    def moment(self, minutes_ago):
        return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)

    def test_a_delegation_begins_its_first_phase_when_it_is_made(self):
        self.ava_delegates()
        one = kept.one("ava", "del-1-aaaa")
        self.assertEqual(one.created_at, one.working_since)

    def test_carrying_work_on_begins_a_new_phase(self):
        self.ava_delegates(now=self.moment(60))
        began = kept.one("ava", "del-1-aaaa")
        kept.answered("ava", "del-1-aaaa", now=self.moment(55))
        self.assertTrue(kept.reopened("ava", "del-1-aaaa", now=self.moment(1)))

        carried = kept.one("ava", "del-1-aaaa")
        self.assertEqual(began.created_at, carried.created_at, "the original moment was rewritten")
        self.assertNotEqual(began.working_since, carried.working_since)
        self.assertEqual(carried.latest_at, carried.working_since,
                         "a resume has to leave both on the same moment — see `_what_just_happened`")

    def test_carrying_work_on_keeps_its_scoped_provider_and_model(self):
        kept.made(
            "ava", "del-1-aaaa", "bob", self.conversation, self.turn,
            provider_name="codex", model_name="asked-model")
        kept.answered("ava", "del-1-aaaa")
        self.assertTrue(kept.reopened("ava", "del-1-aaaa"))

        one = kept.one("ava", "del-1-aaaa")
        self.assertEqual(("codex", "asked-model"), (one.provider_name, one.model_name))

    def test_words_said_into_running_work_leave_the_phase_where_it_is(self):
        self.ava_delegates(now=self.moment(60))
        began = kept.one("ava", "del-1-aaaa").working_since
        self.assertTrue(kept.guided("ava", "del-1-aaaa"))

        one = kept.one("ava", "del-1-aaaa")
        self.assertEqual(began, one.working_since, "a steer restarted the clock the work is timed by")
        self.assertNotEqual(began, one.latest_at, "the steer moved nothing at all")

    def test_asking_running_work_to_stop_leaves_the_phase_where_it_is(self):
        self.ava_delegates(now=self.moment(60))
        began = kept.one("ava", "del-1-aaaa").working_since
        self.assertTrue(kept.stop_asked("ava", "del-1-aaaa"))

        one = kept.one("ava", "del-1-aaaa")
        self.assertEqual(began, one.working_since, "a stop restarted the clock the work is timed by")
        self.assertNotEqual(began, one.latest_at)

    def test_a_row_written_before_the_column_existed_reads_as_its_own_first_phase(self):
        """An agent carried forward from 0.40.0. Step `0006` backfills, and this is the reader's own
        half of the same answer — a `NULL` is never handed to anything that has to subtract from it.
        """
        self.ava_delegates()
        with records.writing(directory.records("ava")) as conn:
            conn.execute("UPDATE delegations SET working_since = NULL")
        one = kept.one("ava", "del-1-aaaa")
        self.assertEqual(one.created_at, one.working_since)


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


class WhereTheWorkStands(support.Isolated):
    """The key is constructed rather than stored, so nothing can point at the wrong database."""

    def test_it_is_keyed_by_who_asked_and_which_turn(self):
        self.assertEqual("ava/12", kept.source_id_for("ava", 12))

    def test_two_delegations_from_one_turn_share_a_conversation(self):
        """So they share a provider session, and the answering agent is not made to start again."""
        self.assertEqual(kept.source_id_for("ava", 12), kept.source_id_for("ava", 12))

    def test_one_from_a_later_turn_does_not(self):
        self.assertNotEqual(kept.source_id_for("ava", 12), kept.source_id_for("ava", 13))


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


class DeliveringTheBriefIntoTheOtherAgentsStore(TwoAgents):
    """The one write a gateway makes to a store that is not its own — and it is a delivery."""

    def test_the_brief_lands_as_a_message_in_a_conversation_of_its_own(self):
        landed = arriving.recorded_for_a_delegation("bob", "ava", self.turn, "audit the exporter")
        with records.reading(directory.records("bob")) as conn:
            said = conn.execute(
                "SELECT c.source, c.source_id, m.author, m.author_id, m.body"
                " FROM conversation_messages m JOIN conversations c ON c.id = m.conversation_id"
                " WHERE m.id = ?", (landed.message,)).fetchone()
        self.assertEqual(("agent", f"ava/{self.turn}", "agent", "ava", "audit the exporter"),
                         tuple(said))

    def test_the_key_is_the_one_the_delegator_constructs(self):
        """Whoever delivers and whoever looks it up later have to agree without keeping a pointer."""
        landed = arriving.recorded_for_a_delegation("bob", "ava", self.turn, "one")
        with records.reading(directory.records("bob")) as conn:
            source_id = conn.execute("SELECT source_id FROM conversations WHERE id = ?",
                                     (landed.conversation,)).fetchone()[0]
        self.assertEqual(kept.source_id_for("ava", self.turn), source_id)

    def test_two_briefs_from_one_turn_share_a_conversation(self):
        one = arriving.recorded_for_a_delegation("bob", "ava", self.turn, "one")
        two = arriving.recorded_for_a_delegation("bob", "ava", self.turn, "two")
        self.assertEqual(one.conversation, two.conversation)

    def test_one_from_a_later_turn_does_not(self):
        one = arriving.recorded_for_a_delegation("bob", "ava", self.turn, "one")
        two = arriving.recorded_for_a_delegation("bob", "ava", self.turn + 1, "two")
        self.assertNotEqual(one.conversation, two.conversation)

    def test_it_is_never_the_conversation_a_person_is_typing_into(self):
        typed = arriving.asked_at_a_terminal("bob", "hello")
        delegated = arriving.recorded_for_a_delegation("bob", "ava", self.turn, "audit it")
        self.assertNotEqual(typed.conversation, delegated.conversation)

    def test_the_delegator_holds_no_conversation_for_it(self):
        """Bob's work is bob's. Ava keeps the one row saying she is owed an answer, and no more."""
        arriving.recorded_for_a_delegation("bob", "ava", self.turn, "audit it")
        with records.reading(directory.records("ava")) as conn:
            self.assertEqual([], list(conn.execute(
                "SELECT 1 FROM conversations WHERE source = 'agent'")))


if __name__ == "__main__":
    unittest.main()
