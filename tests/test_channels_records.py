"""What an agent's channel records refuse, asked of the tables themselves.

Every case works on a real agent made the way the product makes one, so the tables under test are
the ones migration step `0003` laid down and not a fixture that agrees with them.

**This suite is about the constraints and nothing else.** There is no channel layer yet, so the rows
go in through `records.writing` — which is the point: these guarantees have to hold against whatever
writes them, including a later caller who has not read the step. A rule that only holds while every
caller remembers it is a rule that lasts until the second caller.

Three are worth naming. **An empty allow list authorises nobody**, never everybody — a gateway
elsewhere shipped a default-allow fallback for an empty recipient set and sent approval prompts to
every client connected to it. **At most one channel is the notified one**, because unprompted things
need exactly one place to go. And **a channel is a connection rather than a place**, so one platform
is one row: there is no name to invent and no room to configure.

Run directly: `python3 tests/test_channels_records.py`
"""

import sqlite3
import unittest

import support
from rundesk.agents import directory, records


class Channels(support.Isolated):
    """An agent with real records, and rows written straight into them."""

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")

    def at(self):
        return directory.records(self.agent)

    def add(self, kind="discord", notified=0, notify_place="1180", allowed='["2207"]'):
        """One channel row, written through nothing, so the table is what refuses it."""
        with records.writing(self.at()) as conn:
            conn.execute(
                "INSERT INTO channels (kind, describes, notified, notify_place, allowed,"
                " created_at) VALUES (?, 'somewhere', ?, ?, ?, '2026-08-05')",
                (kind, notified, notify_place, allowed))

    def conversation(self, source="channel", source_id="1180", channel="discord"):
        with records.writing(self.at()) as conn:
            conn.execute(
                "INSERT INTO conversations (source, source_id, channel, created_at)"
                " VALUES (?, ?, ?, '2026-08-05')", (source, source_id, channel))

    def message(self, external_id=None, body="hello"):
        with records.writing(self.at()) as conn:
            conn.execute(
                "INSERT INTO conversation_messages (conversation_id, author, author_id, body,"
                " external_id, created_at) VALUES (1, 'user', '2207', ?, ?, '2026-08-05')",
                (body, external_id))

    def counted(self, table):
        with records.reading(self.at()) as conn:
            return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


class WhatIsThereAtAll(Channels):

    def test_making_an_agent_lays_down_all_three_tables(self):
        for table in ("channels", "conversations", "conversation_messages"):
            with self.subTest(table=table):
                self.assertEqual(0, self.counted(table))


class WhoMayReachTheAgent(Channels):
    """`allowed` is the security boundary, so the table refuses rather than the caller remembering."""

    def test_an_allow_list_with_nobody_in_it_cannot_be_written(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.add(allowed="[]")
        self.assertEqual(0, self.counted("channels"))

    def test_an_allow_list_that_is_not_a_list_at_all_cannot_be_written(self):
        # A different exception from the one above, and deliberately not smoothed over: the layer
        # above still validates on the way in, and this is the floor rather than the whole of it.
        with self.assertRaises(sqlite3.OperationalError):
            self.add(allowed="whoever")
        self.assertEqual(0, self.counted("channels"))

    def test_more_than_one_id_may_reach_one_channel(self):
        # One list governs a private message and a room alike, because a channel is a connection
        # rather than a place — so several ids is the ordinary case and not a special one.
        self.add(allowed='["2207", "4418", "9930"]')
        with records.reading(self.at()) as conn:
            self.assertEqual('["2207", "4418", "9930"]',
                             conn.execute("SELECT allowed FROM channels").fetchone()[0])


class OneConnectionPerPlatform(Channels):
    """A channel is its platform. There is no name to invent and no second one to add."""

    def test_a_platform_cannot_be_connected_twice(self):
        self.add("discord")
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("discord")
        self.assertEqual(1, self.counted("channels"))

    def test_two_platforms_are_two_channels(self):
        self.add("discord")
        self.add("slack")
        self.assertEqual(2, self.counted("channels"))


class WhichOneIsTold(Channels):

    def test_two_channels_cannot_both_be_the_notified_one(self):
        self.add("discord", notified=1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("slack", notified=1)
        self.assertEqual(1, self.counted("channels"))

    def test_any_number_of_channels_may_be_told_nothing(self):
        self.add("discord")
        self.add("slack")
        self.add("email")
        self.assertEqual(3, self.counted("channels"))

    def test_no_channel_being_told_is_a_state_the_records_allow(self):
        self.add("discord")
        with records.reading(self.at()) as conn:
            self.assertIsNone(
                conn.execute("SELECT id FROM channels WHERE notified = 1").fetchone())

    def test_the_notified_channel_must_say_where_that_lands(self):
        # A gateway that has just come up is answering nobody, so there is no conversation to reply
        # into. Left nullable, this row would be found broken at the moment it was needed — which
        # for a gateway notice is the moment somebody's agent has stopped.
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("discord", notified=1, notify_place=None)
        self.assertEqual(0, self.counted("channels"))

    def test_a_channel_nobody_is_told_through_needs_no_such_place(self):
        self.add("discord", notified=0, notify_place=None)
        self.assertEqual(1, self.counted("channels"))


class WhatCameOfIt(Channels):

    def test_one_exchange_is_one_conversation_however_often_it_is_recorded(self):
        self.conversation(source_id="1180")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conversation(source_id="1180")
        self.assertEqual(1, self.counted("conversations"))

    def test_a_room_and_a_private_message_are_two_conversations_on_one_channel(self):
        # The place is a fact about the exchange, never about the connection: rooms are discovered
        # when somebody speaks in one, and nothing had to be configured for this to be two.
        self.conversation(source_id="1180", channel="discord")
        self.conversation(source_id="9930", channel="discord")
        self.assertEqual(2, self.counted("conversations"))

    def test_the_same_id_from_a_different_kind_of_source_is_a_different_conversation(self):
        self.conversation(source="channel", source_id="1180")
        self.conversation(source="schedule", source_id="1180", channel=None)
        self.assertEqual(2, self.counted("conversations"))

    def test_a_message_the_platform_has_already_delivered_lands_once(self):
        self.conversation()
        self.message(external_id="8841")
        with self.assertRaises(sqlite3.IntegrityError):
            self.message(external_id="8841")
        self.assertEqual(1, self.counted("conversation_messages"))

    def test_messages_with_nothing_to_deduplicate_on_are_not_deduplicated(self):
        # Two identical lines nobody gave an id are two things somebody said, not one said twice.
        self.conversation()
        self.message(body="hello")
        self.message(body="hello")
        self.assertEqual(2, self.counted("conversation_messages"))

    def test_a_conversation_taken_away_takes_what_was_said_in_it(self):
        self.conversation()
        self.message(external_id="8841")
        with records.writing(self.at()) as conn:
            conn.execute("DELETE FROM conversations WHERE id = 1")
        self.assertEqual(0, self.counted("conversation_messages"))

    def test_which_channel_an_exchange_arrived_through_outlives_that_channel(self):
        # Deliberately not a foreign key. Where something came from is a fact about the past, and a
        # constraint that tidied it away on removal would lose history to stay consistent.
        self.add("discord")
        self.conversation(channel="discord")
        with records.writing(self.at()) as conn:
            conn.execute("DELETE FROM channels WHERE kind = 'discord'")
        with records.reading(self.at()) as conn:
            self.assertEqual("discord",
                             conn.execute("SELECT channel FROM conversations").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
