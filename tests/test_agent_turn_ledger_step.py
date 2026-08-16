"""The two models a turn knows, and the counters it keeps — what `0013` adds to the ledger.

The ledger is permanent, so what it says about a turn taken before this step ran matters as much as
what it says about one taken after. Four things are proved here and nothing else can prove them.

**Nothing is invented for a row an older release wrote.** `model_name` on such a row is whichever of
*asked for* and *reported* arrived last, and there is no way to tell which — so both new columns stay
`NULL` on it, and `model_provenance_kept` stays `0` to say so out loud. Copying the old column across
would turn a value nobody can interpret into one that reads as though somebody had, and inferring the
answer from two empty columns would put an honest new row under the same sentence.

**What the old counting missed is repaired only as far as the evidence goes.** A summary below the
records a turn still has is raised to them; one above them is left alone, because a swept turn has no
evidence left and its summary is the only thing that remembers. `max` of the two, per kind, and never
an assignment — so carrying twice reaches the same numbers.

**The counters are the insert's own work.** They are maintained by a trigger rather than by the
writer, for the reason `0004` gives about the search index: a trigger cannot be forgotten by a future
writer, and the writer that forgot was settlement, which counted rows while the thread that appends
them was still running.

**It only ever counts up.** The detail is swept a fortnight later and the summary is permanent, so a
row going has to leave the count alone.

Run directly: `python3 tests/test_agent_turn_ledger_step.py`
"""

import sqlite3
import unittest

import support
from rundesk.agents import directory, migration, records
from rundesk.core import paths

#: The step this suite is about, by the name the runner records it under.
THE_STEP = "0013_the_models_a_turn_knows_and_the_counters_it_keeps"

#: What it adds to `turns`.
COLUMNS = ("admitted_model_name", "reported_model_name", "unsent_records",
           "model_provenance_kept")


class OneAgentsTurns(support.Isolated):
    """A real agent, made the way the product makes one — the schema is the shipped step's."""

    def setUp(self):
        super().setUp()
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("ava", "a-stand-in")
        self.at = directory.records("ava")

    def rows(self, sql, *values):
        with records.reading(self.at) as conn:
            return list(conn.execute(sql, values))

    def write(self, sql, *values):
        with records.writing(self.at) as conn:
            conn.execute(sql, values)

    def a_conversation(self):
        """One exchange. Named for how many there already are, because a source id is unique."""
        so_far = self.rows("SELECT count(*) FROM conversations")[0][0]
        self.write("INSERT INTO conversations (source, source_id, created_at)"
                   " VALUES ('terminal', ?, '2026-08-06T00:00:00Z')", f"one-{so_far}")
        return self.rows("SELECT id FROM conversations ORDER BY id DESC LIMIT 1")[0][0]

    def a_turn(self, **also):
        """One turn row, written straight into the table the way any release writes one."""
        said = {"conversation_id": self.a_conversation(), "provider_name": "a-stand-in",
                "access_mode": "work", "turn_status": "done",
                "created_at": "2026-08-06T00:00:00Z"}
        said.update(also)
        names = ", ".join(said)
        holes = ", ".join("?" for _ in said)
        self.write(f"INSERT INTO turns ({names}) VALUES ({holes})", *said.values())
        return self.rows("SELECT id FROM turns ORDER BY id DESC LIMIT 1")[0][0]

    def a_record(self, turn, kind):
        """One record, inserted with no help from rundesk — the counter is the table's own work."""
        self.write("INSERT INTO turn_records (turn_id, record_type, event_data, created_at)"
                   " VALUES (?, ?, '{}', '2026-08-06T00:00:00Z')", turn, kind)

    def counters(self, turn):
        return tuple(self.rows(
            "SELECT unknown_records, lost_records, unsent_records FROM turns WHERE id = ?",
            turn)[0])

    def back_to_before(self, step):
        """Unstamp this step and every one after it, the way a real older agent stands."""
        self.write("DELETE FROM migrations WHERE key >= ?", step)

    def as_an_older_release_left_it(self):
        """The whole pre-`0013` shape: no trigger, none of the columns, and the stamp gone.

        The trigger goes first — SQLite will not drop a column a trigger names.
        """
        self.write("DROP TRIGGER IF EXISTS turn_records_after_insert")
        for column in reversed(COLUMNS):
            self.write(f"ALTER TABLE turns DROP COLUMN {column}")
        self.back_to_before(THE_STEP)


class TheModelsATurnKnows(OneAgentsTurns):

    def test_a_made_agent_has_run_it(self):
        self.assertIn(THE_STEP, [one[0] for one in self.rows("SELECT key FROM migrations")])
        columns = [one[1] for one in self.rows("PRAGMA table_info(turns)")]
        self.assertTrue(all(column in columns for column in COLUMNS))

    def test_a_row_nothing_has_said_anything_about_says_neither(self):
        turn = self.a_turn()
        self.assertEqual([(None, None)], [tuple(one) for one in self.rows(
            "SELECT admitted_model_name, reported_model_name FROM turns WHERE id = ?", turn)])

    def test_an_agent_carried_forward_keeps_its_turns_and_invents_no_provenance(self):
        """The one column an older release wrote is left exactly as it is, and unexplained."""
        self.a_turn(model_name="whichever-of-the-two-this-was")
        self.as_an_older_release_left_it()

        self.assertIsNone(migration.carry_one("ava"))

        columns = [one[1] for one in self.rows("PRAGMA table_info(turns)")]
        self.assertTrue(all(column in columns for column in COLUMNS))
        self.assertEqual([("whichever-of-the-two-this-was", None, None, 0, 0)],
                         [tuple(one) for one in self.rows(
                             "SELECT model_name, admitted_model_name, reported_model_name,"
                             " unsent_records, model_provenance_kept FROM turns")])

    def test_a_row_carried_forward_is_marked_as_one_that_did_not_keep_them_apart(self):
        """**The marker is the discriminator and the emptiness is not.** A turn that selected no
        model and was answered by a provider that reported none is empty in the same way."""
        self.a_turn()
        self.as_an_older_release_left_it()

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([(0,)], [tuple(one) for one in
                                  self.rows("SELECT model_provenance_kept FROM turns")])

    def test_the_marker_holds_nothing_but_the_two_answers(self):
        turn = self.a_turn()
        with self.assertRaises(sqlite3.IntegrityError):
            self.write("UPDATE turns SET model_provenance_kept = 2 WHERE id = ?", turn)

    def test_running_it_twice_preserves_what_a_turn_recorded(self):
        turn = self.a_turn(model_name="what-answered")
        self.write("UPDATE turns SET admitted_model_name = 'what-was-asked-for',"
                   " reported_model_name = 'what-answered', unsent_records = 2,"
                   " model_provenance_kept = 1 WHERE id = ?", turn)
        self.back_to_before(THE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([("what-answered", "what-was-asked-for", "what-answered", 2, 1)],
                         [tuple(one) for one in self.rows(
                             "SELECT model_name, admitted_model_name, reported_model_name,"
                             " unsent_records, model_provenance_kept FROM turns")])


class TheCountersATurnKeeps(OneAgentsTurns):

    def test_each_counted_record_moves_its_own_column_as_it_is_written(self):
        turn = self.a_turn()
        for kind in ("unknown", "lost", "unsent"):
            self.a_record(turn, kind)
        self.assertEqual((1, 1, 1), self.counters(turn))

    def test_an_ordinary_record_counts_towards_nothing(self):
        turn = self.a_turn()
        for kind in ("sent", "tool", "result", "done"):
            self.a_record(turn, kind)
        self.assertEqual((0, 0, 0), self.counters(turn))

    def test_a_record_written_for_one_turn_never_counts_against_another(self):
        first, second = self.a_turn(), self.a_turn()
        self.a_record(second, "lost")
        self.assertEqual((0, 0, 0), self.counters(first))
        self.assertEqual((0, 1, 0), self.counters(second))

    def test_the_sweep_that_takes_the_detail_away_leaves_the_summary_alone(self):
        """The detail is diagnostic and goes; the ledger is permanent and it is what is left."""
        turn = self.a_turn()
        self.a_record(turn, "lost")

        self.write("DELETE FROM turn_records WHERE turn_id = ?", turn)

        self.assertEqual((0, 1, 0), self.counters(turn))

    def test_an_agent_carried_forward_gains_the_counting_without_its_old_counts_moving(self):
        turn = self.a_turn(lost_records=3)
        self.write("DROP TRIGGER IF EXISTS turn_records_after_insert")
        self.back_to_before(THE_STEP)

        self.assertIsNone(migration.carry_one("ava"))

        self.a_record(turn, "lost")
        self.assertEqual((0, 4, 0), self.counters(turn))


class ReconcilingWhatTheOldCountingMissed(OneAgentsTurns):
    """**A summary lower than the records it still has is a number that was taken too early.**

    Settlement counted rows while the thread that appends them could still be running, so a turn can
    stand with one `LOST` record and a permanent zero. Carrying raises each counter to the retained
    records of that kind where they are more — `max` and never assignment, so a turn whose detail has
    already been swept keeps the only number that still remembers it.
    """

    def undercounted(self, kind, retained, summary):
        """A turn as the old counting could leave it: records kept, and a summary below them."""
        turn = self.a_turn()
        for _ in range(retained):
            self.a_record(turn, kind)
        column = {"unknown": "unknown_records", "lost": "lost_records"}[kind]
        self.write(f"UPDATE turns SET {column} = ? WHERE id = ?", summary, turn)
        return turn

    def test_a_summary_below_the_records_it_kept_is_raised_to_them(self):
        for kind, at in (("lost", 1), ("unknown", 2)):
            with self.subTest(kind=kind):
                turn = self.undercounted(kind, retained=at, summary=0)
                self.as_an_older_release_left_it()

                self.assertIsNone(migration.carry_one("ava"))

                self.assertEqual(at, self.counters(turn)[0 if kind == "unknown" else 1])

    def test_a_summary_already_higher_than_its_records_is_left_alone(self):
        """It counts up and never down: what is above the detail is a turn that has been swept
        since, and the summary is the only thing that still remembers those records."""
        turn = self.undercounted("lost", retained=1, summary=5)
        self.as_an_older_release_left_it()

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual(5, self.counters(turn)[1])

    def test_a_turn_whose_detail_was_swept_keeps_the_summary_it_has(self):
        turn = self.undercounted("lost", retained=2, summary=2)
        self.write("DELETE FROM turn_records WHERE turn_id = ?", turn)
        self.as_an_older_release_left_it()

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual([], self.rows("SELECT id FROM turn_records WHERE turn_id = ?", turn))
        self.assertEqual(2, self.counters(turn)[1])

    def test_carrying_again_reaches_the_same_numbers(self):
        turn = self.undercounted("lost", retained=3, summary=1)
        self.as_an_older_release_left_it()
        self.assertIsNone(migration.carry_one("ava"))
        first = self.counters(turn)

        self.back_to_before(THE_STEP)
        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual((0, 3, 0), first)
        self.assertEqual(first, self.counters(turn))

    def test_a_word_an_older_release_recorded_as_lost_is_never_re_read_as_unsent(self):
        """Both wore one word and the reason is prose. Sorting them now would be guessing."""
        turn = self.a_turn()
        self.write("INSERT INTO turn_records (turn_id, record_type, event_data, created_at)"
                   " VALUES (?, 'lost', ?, '2026-08-06T00:00:00Z')",
                   turn, '{"lost_count": 1, "reason": "it had already finished"}')
        self.write("UPDATE turns SET lost_records = 0 WHERE id = ?", turn)
        self.as_an_older_release_left_it()

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual((0, 1, 0), self.counters(turn))
        self.assertEqual([("lost",)], [tuple(one) for one in self.rows(
            "SELECT record_type FROM turn_records WHERE turn_id = ?", turn)])

    def test_a_turn_with_no_records_of_a_kind_is_not_written_to_at_all(self):
        """Narrowed to the turns that have such a record, so a long ledger pays for its detail."""
        turn = self.a_turn()
        self.write("UPDATE turns SET lost_records = 4 WHERE id = ?", turn)
        self.as_an_older_release_left_it()

        self.assertIsNone(migration.carry_one("ava"))

        self.assertEqual((0, 4, 0), self.counters(turn))


if __name__ == "__main__":
    unittest.main()
