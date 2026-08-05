"""What came in, written where it can be read again — and written once however often it arrives.

Two guarantees carry this suite. One exchange out in the world is one conversation here, whichever
process records it first; and a message the platform has already delivered lands once. The second is
not hypothetical: every chat platform redelivers, and the build this replaces solved it inside one
adapter's memory, which did not survive a restart.

Run directly: `python3 tests/test_channels_arriving.py`
"""

import unittest

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving


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


class WhenTheRecordsCannotAnswer(Arriving):

    def test_an_agent_that_is_not_there_says_so_rather_than_answering_none(self):
        with self.assertRaises(records.NotThere):
            arriving.recorded("nobody", "discord", "1180", "2207", "hello")

    def test_an_agent_with_no_conversations_says_so(self):
        self.assertEqual([], arriving.conversations(self.agent))


if __name__ == "__main__":
    unittest.main()
