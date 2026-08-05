"""What an agent's channel records refuse, asked of the tables themselves.

Every case works on a real agent made the way the product makes one, so the tables under test are
the ones migration step `0003` laid down and not a fixture that agrees with them.

**This suite is about the constraints and nothing else.** There is no channel layer yet, so the rows
go in through `records.writing` — which is the point: these guarantees have to hold against whatever
writes them, including a later caller who has not read the step. A rule that only holds while every
caller remembers it is a rule that lasts until the second caller.

The two worth naming: **an empty allow list authorises nobody**, never everybody — a gateway
elsewhere shipped a default-allow fallback for an empty recipient set and sent approval prompts to
every client connected to it. And **at most one channel is the notified one**, because unprompted
things need exactly one place to go and two claims is a state with no meaning.

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

    def add(self, name="dm", place="1180", notified=0, allowed='["2207"]', place_kind="dm"):
        """One channel row, written through nothing, so the table is what refuses it."""
        with records.writing(self.at()) as conn:
            conn.execute(
                "INSERT INTO channels (name, kind, place_id, place_kind, describes, notified,"
                " allowed, created_at) VALUES (?, 'discord', ?, ?, 'somewhere', ?, ?, '2026-08-05')",
                (name, place, place_kind, notified, allowed))

    def conversation(self, source="channel", source_id="1180", channel="dm"):
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
        self.add(allowed='["2207", "4418", "9930"]')
        with records.reading(self.at()) as conn:
            self.assertEqual('["2207", "4418", "9930"]',
                             conn.execute("SELECT allowed FROM channels").fetchone()[0])


class WhichOneIsTold(Channels):

    def test_two_channels_cannot_both_be_the_notified_one(self):
        self.add("dm", place="1180", notified=1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("ops", place="9930", notified=1)
        self.assertEqual(1, self.counted("channels"))

    def test_any_number_of_channels_may_be_told_nothing(self):
        self.add("dm", place="1180")
        self.add("ops", place="9930")
        self.add("alerts", place="4418")
        self.assertEqual(3, self.counted("channels"))

    def test_no_channel_being_told_is_a_state_the_records_allow(self):
        self.add("ops", place="9930")
        with records.reading(self.at()) as conn:
            self.assertIsNone(
                conn.execute("SELECT id FROM channels WHERE notified = 1").fetchone())


class WhatAChannelReaches(Channels):

    def test_two_channels_cannot_name_the_same_place(self):
        self.add("dm", place="1180")
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("again", place="1180")

    def test_the_same_place_id_on_another_platform_is_a_different_place(self):
        self.add("dm", place="1180")
        with records.writing(self.at()) as conn:
            conn.execute(
                "INSERT INTO channels (name, kind, place_id, place_kind, describes, allowed,"
                " created_at) VALUES ('slack-dm', 'slack', '1180', 'dm', 'x', '[\"u\"]', 'now')")
        self.assertEqual(2, self.counted("channels"))

    def test_a_place_is_a_direct_message_or_a_room_and_nothing_else(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.add(place_kind="group")

    def test_two_channels_cannot_share_a_name(self):
        self.add("dm", place="1180")
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("dm", place="9930")


class WhatCameOfIt(Channels):

    def test_one_exchange_is_one_conversation_however_often_it_is_recorded(self):
        self.conversation(source_id="1180")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conversation(source_id="1180")
        self.assertEqual(1, self.counted("conversations"))

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
        self.add("ops", place="9930")
        self.conversation(channel="ops")
        with records.writing(self.at()) as conn:
            conn.execute("DELETE FROM channels WHERE name = 'ops'")
        with records.reading(self.at()) as conn:
            self.assertEqual("ops",
                             conn.execute("SELECT channel FROM conversations").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
