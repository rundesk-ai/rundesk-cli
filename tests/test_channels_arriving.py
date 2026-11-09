"""What came in, written where it can be read again — and written once however often it arrives.

Two guarantees carry this suite. One exchange out in the world is one conversation here, whichever
process records it first; and a message the platform has already delivered lands once. The second is
not hypothetical: every chat platform redelivers, and the build this replaces solved it inside one
adapter's memory, which did not survive a restart.

Run directly: `python3 tests/test_channels_arriving.py`
"""

import datetime
import unittest
from unittest import mock

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.core import config
from rundesk.providers import kept as turns_kept


class Arriving(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")

    def arrived(self, body="what changed today?", place="1180", external_id=None, who="2207"):
        return arriving.recorded(self.agent, "discord", place, who, body, external_id)


class OneExchangeIsOneConversation(Arriving):

    def test_the_first_message_makes_the_conversation(self):
        landed = self.arrived()
        self.assertTrue(landed.fresh)
        self.assertEqual(1, len(arriving.conversations(self.agent)))

    def test_the_second_message_joins_the_first(self):
        first = self.arrived("one")
        second = self.arrived("two")
        self.assertEqual(first.conversation, second.conversation)
        self.assertEqual(1, len(arriving.conversations(self.agent)))

    def test_another_place_is_another_conversation(self):
        # A room and a private message on the same channel, with nothing configured for either.
        self.arrived(place="1180")
        self.arrived(place="9930")
        self.assertEqual(2, len(arriving.conversations(self.agent)))

    def test_a_conversation_remembers_which_channel_it_came_through(self):
        self.arrived()
        self.assertEqual("discord", arriving.conversations(self.agent)[0]["channel"])

    def test_two_recordings_racing_for_one_exchange_make_one_conversation(self):
        # The shape rather than the timing: `INSERT … ON CONFLICT DO NOTHING` then read means the
        # decision is the constraint's, so the read-look-insert gap that would make two does not
        # exist to be raced through.
        for _ in range(5):
            self.arrived(place="1180")
        self.assertEqual(1, len(arriving.conversations(self.agent)))


class AMessageLandsOnce(Arriving):

    def test_the_same_platform_message_twice_is_recorded_once(self):
        first = self.arrived("hello", external_id="8841")
        again = self.arrived("hello", external_id="8841")
        self.assertTrue(first.fresh)
        self.assertFalse(again.fresh, "a redelivery was taken for a new message")
        self.assertEqual(first.message, again.message)
        self.assertEqual(1, len(arriving.messages(self.agent, first.conversation)))

    def test_two_messages_nobody_gave_an_id_are_two_messages(self):
        # Two identical lines are two things somebody said, not one said twice.
        landed = self.arrived("ok")
        self.arrived("ok")
        self.assertEqual(2, len(arriving.messages(self.agent, landed.conversation)))

    def test_the_same_id_in_a_different_conversation_is_a_different_message(self):
        self.arrived("hello", place="1180", external_id="8841")
        landed = self.arrived("hello", place="9930", external_id="8841")
        self.assertTrue(landed.fresh)


class MessagesAReplacementGatewayCanRecover(Arriving):

    def admitted(self, landed):
        turn = turns_kept.add_turn(self.agent, {
            "conversation_id": landed.conversation,
            "provider_name": "stand-in",
            "access_mode": "work",
        })
        arriving.handled_by_turn(
            self.agent, landed.conversation, (landed.message,), turn)
        turns_kept.finish_turn(self.agent, turn, turns_kept.DONE)
        return turn

    def test_an_unclaimed_platform_message_is_returned_with_everything_needed_to_answer(self):
        landed = self.arrived("please continue", external_id="8841")

        self.assertEqual([
            arriving.Pending("discord", "1180", "2207", "please continue", "8841", landed)
        ], arriving.pending_on_channels(self.agent, 4))

    def test_a_message_without_a_platform_id_is_not_replayed_after_restart(self):
        """Only a platform identity makes replay idempotent. A legacy/id-less row could be an old
        unanswered record and must never become a surprise new turn merely because a gateway rose."""
        self.arrived("old message without an id")

        self.assertEqual([], arriving.pending_on_channels(self.agent, 4))

    def test_an_older_unclaimed_message_is_not_replayed_after_the_conversation_moved_on(self):
        self.arrived("why no eyes?", external_id="8841")
        later = self.arrived("please update", external_id="8842")
        self.admitted(later)

        self.assertEqual([], arriving.pending_on_channels(self.agent, 4))

    def test_an_answered_retry_supersedes_the_original_duplicate(self):
        self.arrived("are you organized?", external_id="8841")
        retry = self.arrived("are you organized?", external_id="8842")
        self.admitted(retry)

        self.assertEqual([], arriving.pending_on_channels(self.agent, 4))

    def test_the_unclaimed_tail_after_the_last_admitted_turn_is_still_recoverable(self):
        answered = self.arrived("first question", external_id="8841")
        self.admitted(answered)
        latest = self.arrived("please continue", external_id="8842")

        self.assertEqual([
            arriving.Pending("discord", "1180", "2207", "please continue", "8842", latest)
        ], arriving.pending_on_channels(self.agent, 4))


class WhatIsWrittenDown(Arriving):

    def test_a_message_reads_back_whole(self):
        landed = self.arrived("what changed today?", who="2207", external_id="8841")
        said = arriving.messages(self.agent, landed.conversation)[0]
        self.assertEqual("what changed today?", said["body"])
        self.assertEqual("2207", said["author_id"])
        self.assertEqual(arriving.BY_USER, said["author"])
        self.assertEqual("8841", said["external_id"])

    def test_what_rundesk_says_for_itself_is_neither_the_agent_nor_a_person(self):
        # A reader of the history has to tell what the agent said from what was said on its behalf.
        landed = arriving.said_by_rundesk(self.agent, "discord", "1180", "gateway up")
        said = arriving.messages(self.agent, landed.conversation)[0]
        self.assertEqual(arriving.BY_RUNDESK, said["author"])

    def test_a_notice_joins_the_conversation_it_interrupted(self):
        first = self.arrived("hello", place="1180")
        notice = arriving.said_by_rundesk(self.agent, "discord", "1180", "gateway up")
        self.assertEqual(first.conversation, notice.conversation)

    def test_messages_come_back_in_the_order_they_were_said(self):
        landed = self.arrived("first")
        self.arrived("second")
        self.arrived("third")
        self.assertEqual(["first", "second", "third"],
                         [one["body"] for one in arriving.messages(self.agent, landed.conversation)])

    def test_only_the_recent_end_of_a_long_exchange_comes_back(self):
        landed = self.arrived("first")
        for nth in range(10):
            self.arrived(f"line {nth}")
        said = arriving.messages(self.agent, landed.conversation, most=3)
        self.assertEqual(["line 7", "line 8", "line 9"], [one["body"] for one in said])

    def test_a_message_too_long_to_keep_whole_is_clipped_rather_than_dropped(self):
        # The readable part of an over-long message is still what somebody sent.
        landed = self.arrived("x" * (arriving.BODY_AT_MOST + 500))
        self.assertEqual(arriving.BODY_AT_MOST,
                         len(arriving.messages(self.agent, landed.conversation)[0]["body"]))

    def test_when_it_arrived_is_written_for_a_machine_to_compare(self):
        landed = self.arrived()
        self.assertRegex(arriving.messages(self.agent, landed.conversation)[0]["created_at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class DelegatedResultsNoTurnHasTaken(Arriving):
    """A delegated answer is written into the asking agent's own conversation before any turn
    exists to read it, so the row is what a later pass finds the unread ones by."""

    def setUp(self):
        super().setUp()
        self.conversation = arriving.asked_at_a_terminal(self.agent, "hand it over").conversation

    def result(self, delegation_id, answer_id="7", body="the report"):
        return arriving.said_by_rundesk_into(
            self.agent, self.conversation, body,
            external_id=f"{arriving.A_DELEGATION_RESULT}{delegation_id}:{answer_id}")

    def claimed(self, landed):
        turn = turns_kept.add_turn(self.agent, {
            "conversation_id": landed.conversation,
            "provider_name": "stand-in",
            "access_mode": "work",
        })
        arriving.handled_by_turn(
            self.agent, landed.conversation, (landed.message,), turn)
        return turn

    def owed(self, after=0, most=32):
        return [one.delegation_id
                for one in arriving.pending_delegation_results(self.agent, after, most).owed]

    def test_a_recorded_result_nobody_claimed_is_found_with_its_conversation(self):
        landed = self.result("del-1-aabbcc")

        self.assertEqual(
            [arriving.Owed("del-1-aabbcc", self.conversation, landed.message)],
            list(arriving.pending_delegation_results(self.agent).owed))

    def test_a_result_a_turn_has_taken_is_not_owed_one(self):
        self.claimed(self.result("del-1-aabbcc"))

        self.assertEqual([], self.owed())

    def test_anything_else_rundesk_said_is_not_a_delegated_result(self):
        arriving.said_by_rundesk_into(self.agent, self.conversation, "the gateway came up")

        self.assertEqual([], self.owed())

    def test_two_phases_of_one_delegation_ask_for_one_review(self):
        """And it is the newer phase: the older one is what the agent has already been told."""
        self.result("del-1-aabbcc", answer_id="7")
        newer = self.result("del-1-aabbcc", answer_id="9", body="the second report")
        self.result("del-2-ddeeff", answer_id="4")

        window = arriving.pending_delegation_results(self.agent)

        self.assertEqual(["del-1-aabbcc", "del-2-ddeeff"],
                         [one.delegation_id for one in window.owed])
        self.assertEqual(newer.message, window.owed[0].message)

    def test_an_older_phase_a_reviewed_result_left_behind_asks_for_nothing(self):
        """The shape that would otherwise hold a pass for ever: the delegation is answered and its
        current result has been read, and the row an earlier phase left is unclaimed for good."""
        self.result("del-1-aabbcc", answer_id="7")
        self.claimed(self.result("del-1-aabbcc", answer_id="9", body="the second report"))

        self.assertEqual([], self.owed())

    def test_a_delegation_id_holding_a_colon_is_still_read_whole(self):
        self.result("del-1:aabbcc")

        self.assertEqual(["del-1:aabbcc"], self.owed())

    def test_a_neighbouring_delegation_is_not_read_as_a_later_phase(self):
        """The prefix range one delegation's ids occupy stops at that delegation, and `:` is not
        the only character an id can be followed by."""
        older = self.result("del-1", answer_id="7")
        self.result("del-12", answer_id="9")
        self.result("del-1X", answer_id="9")

        window = arriving.pending_delegation_results(self.agent)

        self.assertEqual(["del-1", "del-12", "del-1X"],
                         [one.delegation_id for one in window.owed])
        self.assertEqual(older.message, window.owed[0].message)

    def test_an_id_with_no_answer_part_names_no_delegation(self):
        arriving.said_by_rundesk_into(
            self.agent, self.conversation, "half an id",
            external_id=f"{arriving.A_DELEGATION_RESULT}del-1-aabbcc")

        self.assertEqual([], self.owed())

    def test_the_answer_is_oldest_first(self):
        for number in range(4):
            self.result(f"del-{number}-aabbcc")

        self.assertEqual(
            ["del-0-aabbcc", "del-1-aabbcc", "del-2-aabbcc", "del-3-aabbcc"], self.owed())

    def test_one_delegations_rows_cannot_crowd_out_another(self):
        """The rows a carried-on delegation leaves behind are the oldest there are, and only the
        last of them is news — so they are one entry between them and not four."""
        for answer_id in ("3", "5", "7", "9"):
            self.result("del-1-aabbcc", answer_id=answer_id)
        self.result("del-2-ddeeff", answer_id="4")

        self.assertEqual(["del-1-aabbcc", "del-2-ddeeff"], self.owed())

    def test_a_look_stops_at_the_room_it_was_given_and_says_where_it_got_to(self):
        rows = [self.result(f"del-{number}-aabbcc") for number in range(5)]

        window = arriving.pending_delegation_results(self.agent, most=2)

        self.assertEqual(["del-0-aabbcc", "del-1-aabbcc"],
                         [one.delegation_id for one in window.owed])
        self.assertEqual(rows[1].message, window.reached)

    def test_a_look_that_reads_nothing_after_the_position_stays_where_it_was(self):
        """The only thing that means *there is nothing after here*. A look that read rows and found
        none of them owed has moved, and saying otherwise sends the next one back to the head."""
        last = self.result("del-0-aabbcc")

        self.assertEqual(last.message,
                         arriving.pending_delegation_results(self.agent, most=2).reached)
        self.assertEqual(last.message, arriving.pending_delegation_results(
            self.agent, last.message, most=2).reached)

    def test_continuing_a_look_walks_every_row_and_then_finds_nothing_after_it(self):
        """What makes a bounded look fair rather than a bounded look at the same two rows."""
        for number in range(5):
            self.result(f"del-{number}-aabbcc")

        seen, after, rounds = [], 0, 0
        while rounds < 10:
            rounds += 1
            window = arriving.pending_delegation_results(self.agent, after, most=2)
            seen.extend(one.delegation_id for one in window.owed)
            if window.reached == after:
                break
            after = window.reached

        self.assertEqual([f"del-{number}-aabbcc" for number in range(5)], seen)
        self.assertEqual(4, rounds, "the walk did not finish in the rounds the window needs")

    def test_a_look_past_rows_nothing_will_ever_review_still_moves_on(self):
        """The rows a carried-on delegation left are owed nothing and must not hold the position."""
        for answer_id in ("1", "2", "3"):
            self.result("del-stale-aabbcc", answer_id=answer_id)
        valid = self.result("del-owed-ddeeff", answer_id="4")

        first = arriving.pending_delegation_results(self.agent, most=2)
        second = arriving.pending_delegation_results(self.agent, first.reached, most=2)

        self.assertEqual([], [one.delegation_id for one in first.owed])
        self.assertEqual(["del-stale-aabbcc", "del-owed-ddeeff"],
                         [one.delegation_id for one in second.owed])
        self.assertEqual(valid.message, second.owed[-1].message)

    def test_a_look_is_a_seek_into_the_index_and_never_a_walk_through_the_history(self):
        """The other structural half, and the reason the window names its index.

        The plan is asked of the statement the function actually ran rather than of a copy of it
        here, so a second spelling cannot pass this while the shipped one scans. Left to choose,
        SQLite reads the window as a walk forward from the position through every message in the
        way — which is an agent's whole history on the beat that can least afford it.
        """
        for number in range(4):
            self.result(f"del-{number}-aabbcc")
        with mock.patch.object(arriving, "_rows", wraps=arriving._rows) as asked:
            arriving.pending_delegation_results(self.agent, most=2)

        with records.reading(directory.records(self.agent)) as conn:
            for call, index in ((asked.call_args_list[0], "idx_messages_turn"),
                                (asked.call_args_list[1], "idx_messages_external_id")):
                _conn, _agent, sql, values = call[0]
                plan = [str(row[-1]) for row
                        in conn.execute("EXPLAIN QUERY PLAN " + sql, values).fetchall()]
                self.assertTrue(any(index in one for one in plan), plan)
                self.assertFalse(any(one.startswith("SCAN") for one in plan), plan)

    def test_what_one_look_costs_does_not_grow_with_what_the_store_holds(self):
        """The structural half of the measurement: a look is one read of the window plus one read
        of each named delegation's own results, whatever else has accumulated.

        This is the guard on the shape the first correction had, where every candidate was matched
        against every later row in the store — quadratic, and seconds of a beat on a store that had
        merely been busy for a while."""
        for number in range(200):
            landed = self.result(f"del-{number}-aabbcc")
            if number % 2:
                self.claimed(landed)

        with mock.patch.object(arriving, "_rows", wraps=arriving._rows) as asked:
            window = arriving.pending_delegation_results(self.agent, most=8)

        self.assertEqual(8, len(window.owed))
        self.assertLessEqual(asked.call_count, 1 + 8)


class WhenTheRecordsCannotAnswer(Arriving):

    def test_an_agent_that_is_not_there_says_so_rather_than_answering_none(self):
        with self.assertRaises(records.NotThere):
            arriving.recorded("nobody", "discord", "1180", "2207", "hello")

    def test_an_agent_with_no_conversations_says_so(self):
        self.assertEqual([], arriving.conversations(self.agent))


class WhatOneRunAnswered(Arriving):
    """What a scheduled run came to, read back by the layer that reports it.

    A schedule's turn runs in a process of its own that holds no channel; the gateway that reaps it
    holds the channels and never saw a word of the answer. This is where the two meet.
    """

    def test_the_last_thing_the_agent_said_in_that_schedules_conversation(self):
        arriving.recorded_for_a_schedule(self.agent, "nightly", "run the backup")
        arriving.said_by_agent(self.agent, arriving.FROM_SCHEDULE, "nightly", "an early thought")
        arriving.said_by_agent(self.agent, arriving.FROM_SCHEDULE, "nightly", "Backup done, 4.2GB.")
        self.assertEqual("Backup done, 4.2GB.",
                         arriving.last_answer(self.agent, arriving.FROM_SCHEDULE, "nightly"))

    def test_what_rundesk_said_on_its_behalf_is_never_read_back_as_the_answer(self):
        """The schedule's own prompt is written into the same conversation as `rundesk`, and a report
        that posted that back would be quoting the question as though it were the answer."""
        arriving.recorded_for_a_schedule(self.agent, "nightly", "run the backup")
        self.assertEqual("", arriving.last_answer(self.agent, arriving.FROM_SCHEDULE, "nightly"))

    def test_one_schedules_answer_is_never_another_schedules(self):
        arriving.said_by_agent(self.agent, arriving.FROM_SCHEDULE, "nightly", "Backup done.")
        arriving.said_by_agent(self.agent, arriving.FROM_SCHEDULE, "review", "Queue is clear.")
        self.assertEqual("Backup done.",
                         arriving.last_answer(self.agent, arriving.FROM_SCHEDULE, "nightly"))

    def test_a_run_that_produced_nothing_answers_with_nothing_rather_than_raising(self):
        """An ordinary answer: a turn that failed on its way to the brain has an outcome worth
        reporting and no words of its own, and the caller says what happened instead."""
        self.assertEqual("", arriving.last_answer(self.agent, arriving.FROM_SCHEDULE, "nothing"))

    def test_yesterdays_answer_is_never_read_back_as_todays(self):
        """**The one this exists to refuse.** Every firing of a schedule shares one conversation, and
        a turn writes a message only when it really produced words — so a schedule that answered on
        Monday and failed on Tuesday saying nothing has exactly one agent message in it, Monday's.
        Unbounded, that is posted under Tuesday's notice as Tuesday's report and the failure is never
        mentioned: an answer nobody earned, reported as fact."""
        monday = datetime.datetime(2026, 8, 3, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(self.agent, arriving.FROM_SCHEDULE, "nightly",
                               "Monday's report: all clear.", when=monday)
        tuesday = config.moment_of(datetime.datetime(2026, 8, 4, 9, 0,
                                                     tzinfo=datetime.timezone.utc))
        self.assertEqual("", arriving.last_answer(self.agent, arriving.FROM_SCHEDULE, "nightly",
                                                  after=tuesday))

    def test_the_answer_this_run_really_gave_is_still_found(self):
        """The bound may not be so tight that a run's own answer falls outside it."""
        began = config.moment_of(datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc))
        arriving.said_by_agent(self.agent, arriving.FROM_SCHEDULE, "nightly", "Tuesday's report.",
                               when=datetime.datetime(2026, 8, 4, 9, 5,
                                                      tzinfo=datetime.timezone.utc))
        self.assertEqual("Tuesday's report.",
                         arriving.last_answer(self.agent, arriving.FROM_SCHEDULE, "nightly",
                                              after=began))

    def test_an_answer_written_in_the_very_moment_the_run_began_counts_as_its_own(self):
        """`>=` and never `>`: these moments are recorded to the second, and a run that answered
        inside the same second it started would otherwise report as having said nothing."""
        at = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(self.agent, arriving.FROM_SCHEDULE, "nightly", "quick.", when=at)
        self.assertEqual("quick.", arriving.last_answer(self.agent, arriving.FROM_SCHEDULE,
                                                        "nightly", after=config.moment_of(at)))


if __name__ == "__main__":
    unittest.main()
