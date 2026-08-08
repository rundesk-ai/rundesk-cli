"""The channels one agent keeps: what is written, what is refused, and what two callers cannot lose.

Every case works on a real agent with real records, made the way the product makes one — so the
`channels` table under test is the one migration step `0003` laid down and not a fixture that agrees
with it.

**The refusals are most of the value**, and two of them are the whole reason this module exists
rather than callers writing SQL. Who may reach an agent is a list, so it is changed by what goes in
and out of it inside one transaction — handed to a caller to rewrite, two commands racing each other
lose one of the two changes. And which channel is told is a claim no two rows may hold, so it is
moved by one function that clears and sets together, rather than by a caller who might clear, fail,
and leave an agent that tells nobody anything.

Run directly: `python3 tests/test_channels_kept.py`
"""

import json
import sqlite3
import unittest

import support
from rundesk.agents import directory, records
from rundesk.channels import kept


class Channels(support.Isolated):
    """An agent with real records, and the channels it keeps in them."""

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")

    def given(self, kind="discord", allowed=("2207",), **also):
        values = dict({"describes": f"a bot on {kind}", "allowed": json.dumps(list(allowed))}, **also)
        kept.added(self.agent, kind, values)
        return kind

    def allowed_now(self, kind="discord"):
        return kept.who_may_reach(kept.one(self.agent, kind))


class WhatIsWrittenDown(Channels):

    def test_a_channel_reads_back_everything_it_was_given(self):
        self.given("discord", allowed=("2207", "4418"), notify_place="1180",
                   secret_names='["DISCORD_BOT_TOKEN"]', settings='{"guild": "9930"}')
        one = kept.one(self.agent, "discord")
        self.assertEqual("discord", one["kind"])
        self.assertEqual("a bot on discord", one["describes"])
        self.assertEqual("1180", one["notify_place"])
        self.assertEqual('["DISCORD_BOT_TOKEN"]', one["secret_names"])
        self.assertEqual('{"guild": "9930"}', one["settings"])
        self.assertEqual(["2207", "4418"], kept.who_may_reach(one))

    def test_when_it_was_made_is_written_for_a_machine_to_compare(self):
        self.given()
        self.assertRegex(kept.one(self.agent, "discord")["created_at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_an_agent_with_no_channels_says_so_rather_than_failing(self):
        self.assertEqual([], kept.all(self.agent))

    def test_channels_come_back_in_platform_order(self):
        for kind in ("slack", "discord", "email"):
            self.given(kind)
        self.assertEqual(["discord", "email", "slack"], [one["kind"] for one in kept.all(self.agent)])

    def test_a_channel_nobody_configured_is_not_there_rather_than_empty(self):
        with self.assertRaises(records.NotThere):
            kept.one(self.agent, "discord")


class WhatTheStoreRefuses(Channels):

    def test_a_platform_already_connected_is_refused_rather_than_replaced(self):
        self.given("discord", allowed=("2207",))
        with self.assertRaises(kept.Refused) as refused:
            self.given("discord", allowed=("9999",))
        self.assertIn("already connected", str(refused.exception))
        self.assertEqual(["2207"], self.allowed_now())

    def test_the_refusal_says_a_channel_is_a_connection_rather_than_a_place(self):
        # The sentence matters: somebody adding Discord twice is somebody expecting to configure a
        # second room, and the answer is that they do not have to.
        self.given("discord")
        with self.assertRaises(kept.Refused) as refused:
            self.given("discord")
        self.assertIn("every room the bot is in", str(refused.exception))

    def test_an_empty_allow_list_is_refused_in_words_rather_than_by_a_constraint(self):
        with self.assertRaises(kept.Refused) as refused:
            self.given(allowed=())
        self.assertIn("authorises nobody", str(refused.exception))

    def test_an_allow_list_that_is_not_json_is_refused_before_sqlite_sees_it(self):
        with self.assertRaises(kept.Refused) as refused:
            kept.added(self.agent, "discord", {"describes": "x", "allowed": "whoever"})
        self.assertIn("list of ids", str(refused.exception))

    def test_a_column_that_is_not_a_channels_is_refused(self):
        with self.assertRaises(kept.Refused):
            kept.added(self.agent, "discord", {"describes": "x", "allowed": '["1"]', "colour": "red"})

    def test_which_channel_is_told_is_not_something_a_caller_may_simply_set(self):
        self.given()
        with self.assertRaises(kept.Refused) as refused:
            kept.changed(self.agent, "discord", {"notified": 1})
        self.assertIn("telling", str(refused.exception))


class ChangingOneInPlace(Channels):

    def test_only_what_is_named_moves(self):
        self.given("discord", notify_place="1180")
        kept.changed(self.agent, "discord", {"describes": "somewhere else"})
        one = kept.one(self.agent, "discord")
        self.assertEqual("somewhere else", one["describes"])
        self.assertEqual("1180", one["notify_place"])

    def test_naming_two_columns_and_getting_one_wrong_changes_neither(self):
        self.given("discord")
        with self.assertRaises(kept.Refused):
            kept.changed(self.agent, "discord", {"describes": "moved", "colour": "red"})
        self.assertEqual("a bot on discord", kept.one(self.agent, "discord")["describes"])

    def test_changing_a_channel_that_is_not_there_says_so_and_alters_nothing(self):
        with self.assertRaises(records.NotThere):
            kept.changed(self.agent, "discord", {"describes": "x"})

    def test_a_change_naming_nothing_is_said_rather_than_reported_as_done(self):
        self.given()
        with self.assertRaises(kept.Refused):
            kept.changed(self.agent, "discord", {})


class WhoMayReachTheAgent(Channels):
    """One list, read decided and written inside one transaction."""

    def test_somebody_is_added_and_the_others_stay(self):
        self.given(allowed=("2207",))
        self.assertEqual(["2207", "4418"], kept.allowing(self.agent, "discord", add=["4418"]))
        self.assertEqual(["2207", "4418"], self.allowed_now())

    def test_somebody_already_there_is_not_added_twice(self):
        self.given(allowed=("2207",))
        self.assertEqual(["2207"], kept.allowing(self.agent, "discord", add=["2207"]))

    def test_somebody_is_taken_away(self):
        self.given(allowed=("2207", "4418"))
        self.assertEqual(["2207"], kept.allowing(self.agent, "discord", remove=["4418"]))

    def test_taking_away_somebody_who_was_never_there_is_refused(self):
        # Answering "done" leaves somebody believing they have taken away access they have not.
        self.given(allowed=("2207",))
        with self.assertRaises(kept.Refused) as refused:
            kept.allowing(self.agent, "discord", remove=["9999"])
        self.assertIn("9999", str(refused.exception))
        self.assertEqual(["2207"], self.allowed_now())

    def test_the_list_may_not_be_emptied(self):
        self.given(allowed=("2207",))
        with self.assertRaises(kept.Refused) as refused:
            kept.allowing(self.agent, "discord", remove=["2207"])
        self.assertIn("take the channel away instead", str(refused.exception))
        self.assertEqual(["2207"], self.allowed_now())

    def test_one_call_may_both_add_and_take_away(self):
        self.given(allowed=("2207",))
        self.assertEqual(["4418"], kept.allowing(self.agent, "discord",
                                                 add=["4418"], remove=["2207"]))

    def test_a_channel_that_is_not_there_says_so(self):
        with self.assertRaises(records.NotThere):
            kept.allowing(self.agent, "discord", add=["2207"])

    def test_the_records_will_not_even_hold_a_list_that_cannot_be_read(self):
        # Worth pinning as its own case: the `CHECK` behind this column refuses malformed JSON
        # outright, so the unreadable state cannot be reached through the database at all. What it
        # answers with is `OperationalError` rather than a constraint failure, which is why the
        # layer says it in words on the way in.
        self.given()
        with self.assertRaises(sqlite3.OperationalError):
            with records.writing(directory.records(self.agent)) as conn:
                conn.execute("UPDATE channels SET allowed = 'not json' WHERE kind = 'discord'")
        self.assertEqual(["2207"], self.allowed_now())

    def test_a_row_that_does_not_say_who_may_reach_is_never_read_as_nobody(self):
        # `who_may_reach` takes a row rather than an agent, so it is reachable with something no
        # database produced. An empty list authorises nobody, so a row that could not be read must
        # never *look* like one — that is the difference between a fault somebody can see and a
        # channel that quietly stops answering its owner.
        for said in ("not json at all", None, '{"who": "me"}'):
            with self.subTest(said=said):
                with self.assertRaises(records.Unreadable):
                    kept.who_may_reach({"kind": "discord", "allowed": said})


class WhichChannelIsTold(Channels):

    def test_marking_one_moves_it_from_the_other(self):
        self.given("discord")
        self.given("slack")
        kept.telling(self.agent, "discord", "1180")
        self.assertEqual("discord", kept.told(self.agent)["kind"])
        kept.telling(self.agent, "slack", "C123")
        self.assertEqual("slack", kept.told(self.agent)["kind"])
        self.assertEqual(0, kept.one(self.agent, "discord")["notified"])

    def test_an_agent_that_tells_nobody_anything_says_so_rather_than_failing(self):
        self.given()
        self.assertIsNone(kept.told(self.agent))

    def test_marking_one_with_nowhere_to_write_is_refused(self):
        self.given()
        with self.assertRaises(kept.Refused) as refused:
            kept.telling(self.agent, "discord")
        self.assertIn("answering no one", str(refused.exception))
        self.assertIsNone(kept.told(self.agent))

    def test_marking_one_again_keeps_the_place_it_already_had(self):
        self.given("discord")
        kept.telling(self.agent, "discord", "1180")
        kept.telling(self.agent, "discord")
        self.assertEqual("1180", kept.told(self.agent)["notify_place"])

    def test_marking_a_channel_that_is_not_there_says_so(self):
        with self.assertRaises(records.NotThere):
            kept.telling(self.agent, "discord", "1180")


class TakingOneAway(Channels):

    def test_a_channel_is_taken_away(self):
        self.given()
        kept.forgotten(self.agent, "discord")
        self.assertEqual([], kept.all(self.agent))

    def test_a_removal_that_did_not_happen_is_a_failure(self):
        with self.assertRaises(records.NotThere):
            kept.forgotten(self.agent, "discord")

    def test_taking_one_away_leaves_the_others(self):
        self.given("discord")
        self.given("slack")
        kept.forgotten(self.agent, "discord")
        self.assertEqual(["slack"], [one["kind"] for one in kept.all(self.agent)])


if __name__ == "__main__":
    unittest.main()
