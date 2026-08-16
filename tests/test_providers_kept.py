"""What an agent's records hold about its turns, and finding what was said.

Every case builds a real agent in a scratch root and writes to its real records. Nothing is mocked:
the guarantees here are about constraints, transactions and a full-text index, and none of those is
provable against a stand-in.

Run directly: `python3 tests/test_providers_kept.py`
"""

import datetime
import json
import unittest

import support
from rundesk.agents import directory, migration, records
from rundesk.channels import arriving
from rundesk.providers import kept, protocol
from rundesk.schedules import kept as schedules_kept
from rundesk.utils import scripts

#: Older than anything a sweep keeps, so a case does not have to wait a fortnight.
LONG_AGO = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)


def the_step(wanted: str = "carry"):
    """Something out of step 0004, loaded the way the runner loads one — by file, never by name."""
    found = [one for one in migration.found() if one.id.startswith("0004")]
    return scripts.carrying(found[0], "a_step_under_test", wanted=wanted)


def _without_search(agent: str) -> None:
    """An agent as it stands on a machine whose SQLite has no full-text module.

    The table **and** its triggers, because a trigger left behind by a table that is gone fires on
    every message and refers to something that is not there — which is a broken agent rather than one
    without a search, and the two prove different things.
    """
    with records.writing(directory.records(agent)) as conn:
        for one in ("conversation_messages_after_insert", "conversation_messages_after_delete",
                    "conversation_messages_after_update"):
            conn.execute(f"DROP TRIGGER IF EXISTS {one}")
        conn.execute("DROP TABLE IF EXISTS conversation_messages_fts")


class WithAnAgent(support.Isolated):
    def setUp(self):
        super().setUp()
        directory.made("ava", "a-stand-in")

    def a_conversation(self, place: str = "1180", channel: str = "discord") -> int:
        """One exchange, made the way the channel layer makes one."""
        return arriving.recorded("ava", channel, place, "2207", "what changed today?").conversation

    def a_turn(self, conversation=None, **also) -> int:
        given = {"conversation_id": conversation if conversation is not None
                 else self.a_conversation(),
                 "provider_name": "a-stand-in", "access_mode": protocol.ACCESS_WORK}
        given.update(also)
        return kept.add_turn("ava", given)

    def assertPlanned(self, sql: str, values: tuple, index: str) -> None:
        """Fail unless SQLite answers this by seeking `index` rather than reading the table.

        **Asked of the planner rather than timed.** A timing on a table with three rows in it proves
        nothing at all, and one big enough to time is a suite nobody runs; `EXPLAIN QUERY PLAN` is
        SQLite's own answer to which index it will use, and it is the thing that regresses when
        somebody trims an index that looked unused.

        **A `SCAN … USING INDEX` is a pass, and that is not a loophole.** Walking a *partial* index
        end to end is the whole point of one — `idx_turns_working` holds only the turns nothing has
        settled, so reading all of it reads a handful however long the ledger gets. What fails is a
        step that reads a table with no index at all, which is what `SCAN` on its own means.
        """
        with records.reading(directory.records("ava")) as conn:
            steps = [str(row[-1]) for row
                     in conn.execute("EXPLAIN QUERY PLAN " + sql, values)]
        plan = " / ".join(steps)
        self.assertIn(index, plan, f"expected {index} to answer this; SQLite said: {plan}")
        read_whole = [one for one in steps if one.startswith("SCAN") and "USING" not in one]
        self.assertEqual(read_whole, [], f"this reads a table with no index; SQLite said: {plan}")


class AdmittingATurn(WithAnAgent):
    def test_a_turn_is_written_before_the_brain_starts_and_says_what_it_was_admitted_with(self):
        turn = self.a_turn(model_name="m-1", session_resumed=1)
        got = kept.get_turn("ava", turn)
        self.assertEqual(got["provider_name"], "a-stand-in")
        self.assertEqual(got["model_name"], "m-1")
        self.assertEqual(got["session_resumed"], 1)
        self.assertEqual(got["turn_status"], kept.WORKING)

    def test_working_means_nothing_has_settled_it_and_never_that_it_is_running(self):
        """Whether a turn is running now is the conversation lock's answer, never a column's."""
        self.a_turn()
        self.assertEqual([one["turn_status"] for one in kept.list_unfinished_turns("ava")],
                         [kept.WORKING])

    def test_a_turn_that_died_before_the_brain_still_shows_what_was_asked(self):
        conversation = self.a_conversation()
        self.a_turn(conversation)
        said = arriving.messages("ava", conversation)
        self.assertEqual(said[0]["body"], "what changed today?")

    def test_a_column_a_caller_may_not_set_is_refused_before_anything_is_written(self):
        for name in ("turn_status", "ended_at", "exit_code", "input_tokens"):
            with self.subTest(name=name):
                with self.assertRaises(kept.Refused):
                    self.a_turn(**{name: "anything"})

    def test_a_column_these_records_do_not_have_is_refused(self):
        with self.assertRaises(kept.Refused):
            kept.add_turn("ava", {"conversation_id": 1, "provider_name": "x",
                                  "access_mode": "work", "invented": "yes"})

    def test_an_access_mode_the_records_will_not_hold_is_a_refusal(self):
        """A constraint violation is a caller handing a bad value, not records nobody can read."""
        with self.assertRaises(kept.Refused):
            self.a_turn(access_mode="anything-else")


class SettlingATurn(WithAnAgent):
    def test_what_it_came_to_is_written_once(self):
        turn = self.a_turn()
        kept.finish_turn("ava", turn, kept.DONE,
                         {"exit_code": 0, "usage_reported": 1, "input_tokens": 20,
                          "output_tokens": 1510, "cache_read_tokens": 302567,
                          "cache_write_tokens": 17453, "context_tokens": 9200})
        got = kept.get_turn("ava", turn)
        self.assertEqual(got["turn_status"], kept.DONE)
        self.assertEqual((got["input_tokens"], got["cache_read_tokens"]), (20, 302567))
        self.assertTrue(got["ended_at"])

    def test_the_four_billed_quantities_stay_apart(self):
        turn = self.a_turn()
        kept.finish_turn("ava", turn, kept.DONE,
                         {"input_tokens": 1, "output_tokens": 2,
                          "cache_read_tokens": 3, "cache_write_tokens": 4})
        got = kept.get_turn("ava", turn)
        self.assertEqual([got["input_tokens"], got["output_tokens"],
                          got["cache_read_tokens"], got["cache_write_tokens"]], [1, 2, 3, 4])

    def test_a_cost_nobody_reported_is_not_a_cost_of_nothing(self):
        turn = self.a_turn()
        kept.finish_turn("ava", turn, kept.DONE, {})
        got = kept.get_turn("ava", turn)
        self.assertEqual(got["usage_reported"], 0)
        self.assertIsNone(got["input_tokens"])

    def test_a_word_that_is_not_a_turn_status_is_refused_in_a_sentence(self):
        """The caller is a gateway logging at two in the morning, and a constraint violation is not a
        sentence anybody can act on."""
        turn = self.a_turn()
        with self.assertRaises(kept.Refused) as refused:
            kept.finish_turn("ava", turn, "finished")
        self.assertIn("done", str(refused.exception))

    def test_a_turn_may_not_be_settled_as_still_working(self):
        turn = self.a_turn()
        with self.assertRaises(kept.Refused):
            kept.finish_turn("ava", turn, kept.WORKING)

    def test_every_failure_this_release_knows_is_accepted(self):
        for code in protocol.FAILURE_CODES:
            with self.subTest(code=code):
                turn = self.a_turn()
                kept.finish_turn("ava", turn, kept.FAILED, {"failure_code": code})
                self.assertEqual(kept.get_turn("ava", turn)["failure_code"], code)

    def test_a_failure_this_release_does_not_know_is_refused_before_the_write(self):
        """The column has no CHECK on purpose — this vocabulary grows with every vendor — so the
        refusal has to happen here or an unknown word sits silently in the column for ever."""
        turn = self.a_turn()
        with self.assertRaises(kept.Refused):
            kept.finish_turn("ava", turn, kept.FAILED, {"failure_code": "quantum_flux"})
        self.assertEqual(kept.get_turn("ava", turn)["turn_status"], kept.WORKING)

    def test_the_brains_prose_and_the_closed_word_are_kept_apart(self):
        turn = self.a_turn()
        kept.finish_turn("ava", turn, kept.FAILED,
                         {"failure_code": protocol.SIGNED_OUT,
                          "failure_message": "Not logged in - please run the login command"})
        got = kept.get_turn("ava", turn)
        self.assertEqual(got["failure_code"], protocol.SIGNED_OUT)
        self.assertIn("login", got["failure_message"])

    def test_a_settled_turn_is_no_longer_unfinished(self):
        turn = self.a_turn()
        kept.finish_turn("ava", turn, kept.STOPPED)
        self.assertEqual(kept.list_unfinished_turns("ava"), [])


class WhatATurnDid(WithAnAgent):
    def test_records_come_back_in_the_order_they_happened(self):
        turn = self.a_turn()
        for each in ("tool", "result", "usage", "done"):
            kept.add_turn_record("ava", turn, each)
        self.assertEqual([one["record_type"] for one in kept.list_turn_records("ava", turn)],
                         ["tool", "result", "usage", "done"])

    def test_the_raw_line_is_kept_only_for_something_that_was_not_understood(self):
        turn = self.a_turn()
        kept.add_turn_record("ava", turn, "tool", {"id": "1", "did": "read"})
        kept.add_turn_record("ava", turn, "unknown", {}, raw_line='{"type": "telepathy"}')
        got = kept.list_turn_records("ava", turn)
        self.assertIsNone(got[0]["raw_line"])
        self.assertIn("telepathy", got[1]["raw_line"])

    def test_a_records_event_survives_as_it_was_given(self):
        turn = self.a_turn()
        kept.add_turn_record("ava", turn, "result", {"id": "1", "ok": True, "summary": "3 files"})
        got = json.loads(kept.list_turn_records("ava", turn)[0]["event_data"])
        self.assertEqual(got["summary"], "3 files")

    def test_a_turns_records_go_when_its_conversation_does(self):
        conversation = self.a_conversation()
        turn = self.a_turn(conversation)
        kept.add_turn_record("ava", turn, "tool")
        with records.writing(directory.records("ava")) as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation,))
        self.assertEqual(kept.list_turn_records("ava", turn), [])


class TheSummaryATurnKeepsForEver(WithAnAgent):
    """**What a turn kept for ever has to be what its records say, whenever they were written.**

    The three counters were taken at settlement, by counting rows, and the thread that writes them
    can still be running then: a word refused a second after the brain went quiet appended its
    record to a turn whose summary had already been finalised. The detail is swept a fortnight
    later and the wrong permanent number is what is left.

    So the count is maintained by the write that causes it, inside the same transaction — a record
    the records did not accept is still not one this number claims.
    """

    def test_each_counted_kind_moves_its_own_column_and_no_other(self):
        turn = self.a_turn()
        for kind in (kept.UNKNOWN, kept.LOST, kept.UNSENT):
            kept.add_turn_record("ava", turn, kind)
        got = kept.get_turn("ava", turn)
        self.assertEqual((1, 1, 1),
                         (got["unknown_records"], got["lost_records"], got["unsent_records"]))

    def test_an_ordinary_record_counts_towards_nothing(self):
        turn = self.a_turn()
        for kind in ("tool", "result", "sent", "done"):
            kept.add_turn_record("ava", turn, kind)
        got = kept.get_turn("ava", turn)
        self.assertEqual((0, 0, 0),
                         (got["unknown_records"], got["lost_records"], got["unsent_records"]))

    def test_a_record_written_after_the_turn_settled_still_reaches_the_summary(self):
        turn = self.a_turn()
        kept.add_turn_record("ava", turn, kept.LOST, {"lost_count": 1})
        kept.finish_turn("ava", turn, kept.DONE)

        kept.add_turn_record("ava", turn, kept.LOST, {"lost_count": 1})

        self.assertEqual(2, kept.get_turn("ava", turn)["lost_records"])

    def test_the_summary_survives_the_sweep_that_takes_the_detail_away(self):
        """The detail is diagnostic and goes; the ledger is permanent and must still be right."""
        turn = self.a_turn()
        kept.add_turn_record("ava", turn, kept.LOST, when=LONG_AGO)
        kept.finish_turn("ava", turn, kept.DONE)

        self.assertEqual(1, kept.sweep_turn_records("ava", 14))

        self.assertEqual([], kept.list_turn_records("ava", turn))
        self.assertEqual(1, kept.get_turn("ava", turn)["lost_records"])

    def test_settling_a_turn_may_not_write_a_counter_of_its_own(self):
        """Settlement counting rows is the defect. A caller that could still set these could
        overwrite a count that is already right."""
        turn = self.a_turn()
        for named in ("unknown_records", "lost_records", "unsent_records"):
            with self.subTest(named=named):
                with self.assertRaises(kept.Refused):
                    kept.finish_turn("ava", turn, kept.DONE, {named: 0})


class SweepingWhatTurnsDid(WithAnAgent):
    def test_only_what_a_turn_did_is_swept_and_never_the_turn_or_the_conversation(self):
        """A turn's own row is the ledger and what was said is the owner's history. This is the one
        table that grows with tool calls."""
        conversation = self.a_conversation()
        turn = self.a_turn(conversation)
        kept.add_turn_record("ava", turn, "tool", when=LONG_AGO)
        went = kept.sweep_turn_records("ava", keeping_days=14)
        self.assertEqual(went, 1)
        self.assertEqual(kept.list_turn_records("ava", turn), [])
        self.assertEqual(kept.get_turn("ava", turn)["id"], turn)
        self.assertTrue(arriving.messages("ava", conversation))

    def test_recent_records_are_left_alone(self):
        turn = self.a_turn()
        kept.add_turn_record("ava", turn, "tool")
        self.assertEqual(kept.sweep_turn_records("ava", keeping_days=14), 0)

    def test_keeping_nothing_removes_nothing_rather_than_everything(self):
        """The safe way round for a number that arrives from a configuration file."""
        turn = self.a_turn()
        kept.add_turn_record("ava", turn, "tool", when=LONG_AGO)
        self.assertEqual(kept.sweep_turn_records("ava", keeping_days=0), 0)
        self.assertEqual(len(kept.list_turn_records("ava", turn)), 1)

    def test_the_sweep_seeks_rather_than_scanning_the_largest_table_an_agent_has(self):
        """`turn_records` is the one table that grows with tool calls, and the sweep is a range over
        `created_at`. Without an index on it this reads every row an agent has ever written."""
        self.assertPlanned("DELETE FROM turn_records WHERE created_at < ?",
                           ("2026-01-01T00:00:00Z",), "idx_turn_records_created")


class WhatAGatewayAsksForWhenItComesUp(WithAnAgent):
    def test_the_turns_nothing_settled_are_sought_and_never_scanned(self):
        """`turns` is kept for ever, so the index that answers this must hold only the handful
        nothing has settled rather than growing with the whole ledger."""
        self.assertPlanned("SELECT * FROM turns WHERE turn_status = ? ORDER BY id",
                           (kept.WORKING,), "idx_turns_working")

    def test_it_still_finds_only_the_unfinished_ones(self):
        working = self.a_turn()
        settled = self.a_turn()
        kept.finish_turn("ava", settled, kept.DONE)
        self.assertEqual([one["id"] for one in kept.list_unfinished_turns("ava")], [working])


class WhichScheduleRanATurn(WithAnAgent):
    """The ledger has to go on saying who spent the cost after somebody tidies up.

    `schedule_id` is `ON DELETE SET NULL`, so on its own it forgets — which is exactly what `0003`
    refused for `conversations.channel`.
    """

    def a_schedule(self, name: str = "nightly") -> int:
        schedules_kept.added("ava", name, {"cron": "0 3 * * *", "command": "echo hi"})
        return int(schedules_kept.one("ava", name)["id"])

    def test_a_turn_keeps_the_name_of_the_schedule_that_ran_it(self):
        turn = self.a_turn(schedule_id=self.a_schedule(), schedule_name="nightly")
        self.assertEqual(kept.get_turn("ava", turn)["schedule_name"], "nightly")

    def test_the_name_outlives_the_schedule_and_the_id_does_not(self):
        turn = self.a_turn(schedule_id=self.a_schedule(), schedule_name="nightly")
        schedules_kept.forgotten("ava", "nightly")
        row = kept.get_turn("ava", turn)
        self.assertIsNone(row["schedule_id"], "the foreign key is ON DELETE SET NULL")
        self.assertEqual(row["schedule_name"], "nightly",
                         "the ledger forgot which schedule spent the cost")

    def test_a_turn_nobody_scheduled_says_so_rather_than_naming_something(self):
        self.assertIsNone(kept.get_turn("ava", self.a_turn())["schedule_name"])


class WhereAConversationGotTo(WithAnAgent):
    def test_a_fresh_conversation_has_no_handle(self):
        self.assertIsNone(kept.get_session("ava", self.a_conversation(), "a-stand-in"))

    def test_a_handle_is_kept_and_read_back(self):
        conversation = self.a_conversation()
        kept.save_session("ava", conversation, "a-stand-in", "thread-9")
        self.assertEqual(kept.get_session("ava", conversation, "a-stand-in"), "thread-9")

    def test_keeping_it_again_replaces_it_without_a_moment_of_having_none(self):
        conversation = self.a_conversation()
        kept.save_session("ava", conversation, "a-stand-in", "thread-9")
        kept.save_session("ava", conversation, "a-stand-in", "thread-10")
        self.assertEqual(kept.get_session("ava", conversation, "a-stand-in"), "thread-10")

    def test_two_brains_in_one_conversation_are_two_handles(self):
        conversation = self.a_conversation()
        kept.save_session("ava", conversation, "one", "a")
        kept.save_session("ava", conversation, "two", "b")
        self.assertEqual(kept.get_session("ava", conversation, "one"), "a")
        self.assertEqual(kept.get_session("ava", conversation, "two"), "b")

    def test_forgetting_one_that_was_never_there_is_not_a_failure(self):
        kept.delete_session("ava", self.a_conversation(), "a-stand-in")

    def test_forgetting_it_makes_the_next_turn_start_fresh(self):
        conversation = self.a_conversation()
        kept.save_session("ava", conversation, "a-stand-in", "thread-9")
        kept.delete_session("ava", conversation, "a-stand-in")
        self.assertIsNone(kept.get_session("ava", conversation, "a-stand-in"))


class FindingWhatWasSaid(WithAnAgent):
    def setUp(self):
        super().setUp()
        self.ops = arriving.recorded(
            "ava", "discord", "ops", "2207", "the invoice bug is in the parser").conversation
        self.other = arriving.recorded(
            "ava", "slack", "random", "2207", "the invoice bug came back").conversation
        arriving.recorded("ava", "discord", "ops", "2207", "unrelated chatter about lunch")

    def test_this_install_can_search(self):
        """Every case below is about the index; this one says whether there is one at all."""
        self.assertTrue(kept.has_search_index("ava"),
                        "this SQLite has no FTS5, so the cases below prove the fallback instead")

    def test_a_phrase_is_found(self):
        got = kept.search_messages("ava", "invoice")
        self.assertEqual(len(got), 2)

    def test_it_is_narrowed_by_the_channel_it_was_said_on(self):
        got = kept.search_messages("ava", "invoice", channel="discord")
        self.assertEqual([one["conversation_id"] for one in got], [self.ops])

    def test_a_channel_it_was_not_said_on_finds_nothing(self):
        self.assertEqual(kept.search_messages("ava", "invoice", channel="nowhere"), [])

    def test_it_is_narrowed_by_the_conversation(self):
        got = kept.search_messages("ava", "invoice", conversation=self.other)
        self.assertEqual(len(got), 1)

    def test_where_it_was_said_comes_back_with_it(self):
        got = kept.search_messages("ava", "invoice", channel="discord")[0]
        self.assertEqual(got["channel"], "discord")
        self.assertEqual(got["source"], arriving.FROM_CHANNEL)

    def test_what_matched_is_shown_in_a_bounded_excerpt(self):
        """The agent is the first caller and every line it reads costs tokens."""
        got = kept.search_messages("ava", "invoice")[0]
        self.assertIn("[invoice]", got["excerpt"])

    def test_no_words_at_all_is_the_conversation_read_back_newest_first(self):
        got = kept.search_messages("ava", conversation=self.ops)
        self.assertEqual(got[0]["body"], "unrelated chatter about lunch")

    def test_an_answer_is_bounded_unless_more_is_asked_for(self):
        for n in range(30):
            arriving.recorded("ava", "discord", "ops", "2207", f"invoice note {n}")
        self.assertEqual(len(kept.search_messages("ava", "invoice")), kept.FOUND_AT_MOST)
        self.assertEqual(len(kept.search_messages("ava", "invoice", most=5)), 5)

    def test_the_index_follows_a_message_that_is_removed(self):
        """An external-content index cannot find the old row by itself, so the trigger has to hand it
        the values that were indexed — or the next search matches a message that is gone."""
        with records.writing(directory.records("ava")) as conn:
            conn.execute("DELETE FROM conversation_messages WHERE body LIKE '%parser%'")
        self.assertEqual(len(kept.search_messages("ava", "invoice")), 1)

    def test_the_index_follows_a_message_that_is_rewritten(self):
        with records.writing(directory.records("ava")) as conn:
            conn.execute("UPDATE conversation_messages SET body = ? WHERE body LIKE '%parser%'",
                         ("nothing to do with billing",))
        self.assertEqual(len(kept.search_messages("ava", "invoice")), 1)
        self.assertEqual(len(kept.search_messages("ava", "billing")), 1)

    def test_what_was_said_before_the_index_existed_is_still_found(self):
        """An agent carrying forward has a conversation behind it, and a search that could only find
        what was said after the upgrade is one somebody stops trusting on their first try."""
        _without_search("ava")
        self.assertFalse(kept.has_search_index("ava"))
        migration.carry_one("ava")
        self.assertEqual(len(kept.search_messages("ava", "invoice")), 2)


class ATriggerThatOutlivedItsTable(WithAnAgent):
    """The worst state this schema can be in, and the one a step has to heal.

    A trigger fires on every insert into `conversation_messages` and refers to a table that is not
    there, so **the agent stops being able to record anything anybody says to it** — a far larger
    failure than the search it was meant to serve.
    """

    def a_broken_agent(self):
        """The table gone and its triggers left, which is what an outside repair leaves behind."""
        with records.writing(directory.records("ava")) as conn:
            conn.execute("DROP TABLE conversation_messages_fts")

    def test_the_state_really_does_break_recording_a_message(self):
        """Proved first, so the case below is healing something rather than nothing."""
        self.a_broken_agent()
        with self.assertRaises(records.Unreadable):
            arriving.recorded("ava", "discord", "ops", "2207", "anything at all")

    def test_carrying_the_agent_again_heals_it(self):
        self.a_broken_agent()
        with records.writing(directory.records("ava")) as conn:
            the_step()(conn, directory.where("ava"))
        arriving.recorded("ava", "discord", "ops", "2207", "and now it lands")
        self.assertEqual(len(kept.search_messages("ava", "lands")), 1)

    def test_healing_it_leaves_the_search_working(self):
        self.a_broken_agent()
        with records.writing(directory.records("ava")) as conn:
            the_step()(conn, directory.where("ava"))
        self.assertTrue(kept.has_search_index("ava"))

    def test_the_triggers_are_taken_away_where_there_is_no_table_to_rebuild(self):
        """The half this machine cannot reach through `carry`.

        Here, FTS5 is available, so `carry` heals the broken state by rebuilding the table and the
        trigger-drop never has to fire. On a machine whose SQLite has no full-text module there is
        nothing to rebuild, and taking the triggers away is the *only* thing standing between the
        agent and being unable to record a word. So it is asked of directly.
        """
        self.a_broken_agent()
        with records.writing(directory.records("ava")) as conn:
            the_step("_without_the_triggers")(conn)
        arriving.recorded("ava", "discord", "ops", "2207", "and now it lands")
        self.assertFalse(kept.has_search_index("ava"))
        self.assertEqual(len(kept.search_messages("ava", "lands")), 1,
                         "the fallback did not find what the index no longer holds")


class AnIndexThisSqliteCannotOpen(WithAnAgent):
    """A row in `sqlite_master` says the table was created once, on some machine, by some Python.

    It does not say *this* one can read it. An install whose interpreter was upgraded to a build
    without the full-text module has the table in the file and cannot read a word of it, and a check
    that trusted the row would raise on every query instead of falling back.

    That exact state cannot be built portably — the newer SQLite lets its shadow tables be emptied
    and the older one refuses — so what stands in for it is a table of the same name that is present
    and will not answer the query. The property under test is the same one: **asked by using it, not
    by looking for it.**
    """

    def test_a_table_that_will_not_answer_is_not_a_search_index(self):
        with records.writing(directory.records("ava")) as conn:
            for one in ("conversation_messages_after_insert", "conversation_messages_after_delete",
                        "conversation_messages_after_update"):
                conn.execute(f"DROP TRIGGER IF EXISTS {one}")
            conn.execute("DROP TABLE conversation_messages_fts")
            conn.execute("CREATE TABLE conversation_messages_fts (body TEXT PRIMARY KEY) "
                         "WITHOUT ROWID")
        self.assertFalse(kept.has_search_index("ava"),
                         "a table that cannot answer the query was reported as a working index")

    def test_and_the_search_still_finds_what_was_said(self):
        arriving.recorded("ava", "discord", "ops", "2207", "the invoice bug is in the parser")
        with records.writing(directory.records("ava")) as conn:
            for one in ("conversation_messages_after_insert", "conversation_messages_after_delete",
                        "conversation_messages_after_update"):
                conn.execute(f"DROP TRIGGER IF EXISTS {one}")
            conn.execute("DROP TABLE conversation_messages_fts")
            conn.execute("CREATE TABLE conversation_messages_fts (body TEXT PRIMARY KEY) "
                         "WITHOUT ROWID")
        self.assertEqual(len(kept.search_messages("ava", "invoice")), 1)


class WhenThereIsNoIndex(WithAnAgent):
    """SQLite is not always built with the module, and an agent without it must still work."""

    def setUp(self):
        super().setUp()
        arriving.recorded("ava", "discord", "ops", "2207", "the invoice bug is in the parser")
        _without_search("ava")

    def test_the_records_say_there_is_none(self):
        self.assertFalse(kept.has_search_index("ava"))

    def test_a_search_still_finds_what_was_said(self):
        got = kept.search_messages("ava", "invoice")
        self.assertEqual(len(got), 1)

    def test_the_fallback_is_bounded_like_the_index_is(self):
        for n in range(30):
            arriving.recorded("ava", "discord", "ops", "2207", f"invoice note {n}")
        self.assertEqual(len(kept.search_messages("ava", "invoice")), kept.FOUND_AT_MOST)

    def test_a_wildcard_somebody_typed_is_a_character_and_not_a_wildcard(self):
        """`%` and `_` are `LIKE`'s own, so unescaped they match everything ever said.

        `setUp` leaves one message with no `%` in it, so a `%` that is still a wildcard finds both
        and a `%` that is a character finds the one that has one.
        """
        arriving.recorded("ava", "discord", "ops", "2207", "the rollout is 50% done")
        self.assertEqual([one["body"] for one in kept.search_messages("ava", "50%")],
                         ["the rollout is 50% done"])
        self.assertEqual([one["body"] for one in kept.search_messages("ava", "%")],
                         ["the rollout is 50% done"])
        self.assertEqual(kept.search_messages("ava", "in_oice"), [])


class WhatSomebodyTypedIsWordsAndNeverAQuery(WithAnAgent):
    """The one place a person's own text reaches the records, and it used to raise.

    `MATCH` takes a query language rather than a string: `C++` is a syntax error near `+`, an
    apostrophe is one near `'`, and an unbalanced `"` is an unterminated string. Every one of them
    surfaced as `OperationalError`, which `_rows` reads as records that cannot be read — so
    searching for `C++` told somebody their agent's whole memory was unreadable.
    """

    #: Each of these raised before the terms were quoted. None of them is an unusual thing to type.
    TYPED = ("C++", "it's fine", 'what about the "cache', "deploy AND", "deploy)", "-- x", "*", "")

    def setUp(self):
        super().setUp()
        arriving.recorded("ava", "discord", "ops", "2207", "the deploy is 50% done in C++")

    def test_none_of_it_is_reported_as_records_that_cannot_be_read(self):
        for typed in self.TYPED:
            with self.subTest(typed=typed):
                kept.search_messages("ava", typed)

    def test_the_words_still_find_the_message(self):
        self.assertEqual(len(kept.search_messages("ava", "C++")), 1)
        self.assertEqual(len(kept.search_messages("ava", "deploy")), 1)

    def test_several_words_still_mean_all_of_them(self):
        self.assertEqual(len(kept.search_messages("ava", "deploy C++")), 1)
        self.assertEqual(len(kept.search_messages("ava", "deploy lunch")), 0)

    def test_a_word_that_is_only_punctuation_finds_nothing_rather_than_raising(self):
        self.assertEqual(kept.search_messages("ava", "+++"), [])

    def test_the_two_branches_agree_about_what_was_typed(self):
        """The fallback is slower and finds different things; it must not find *wrong* things."""
        with_index = [one["id"] for one in kept.search_messages("ava", "C++")]
        _without_search("ava")
        self.assertFalse(kept.has_search_index("ava"))
        self.assertEqual([one["id"] for one in kept.search_messages("ava", "C++")], with_index)


if __name__ == "__main__":
    unittest.main()
