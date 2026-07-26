"""Everything one agent keeps, and the only way in to it — every claim `store.py` makes.

Nothing here reaches the network, starts a gateway, runs a program or goes near the
machine's own `~/.rundesk`: a `Store` is built with a path, so each case gives it a
directory of its own. Every connection a case opens itself is closed — a leaked one holds
the WAL read lock on newer Pythons and not on the floor version, so the leak is invisible
exactly where CI would catch it.

Run: python3 tests/test_store.py
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import migration, store  # noqa: E402

AT = "2026-07-26T09:00:00Z"
LATER = "2026-07-26T10:00:00Z"


class WithAnAgentsOwnRecords(unittest.TestCase):
    """A database of this case's own, and nothing of the machine's within reach."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-store-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.at = store.path_for(self.where)

    def built(self, **held) -> store.Store:
        made = store.Store(self.at, **held)
        made.made()
        return made

    def raw(self):
        """A connection of the case's own, for arranging what no caller may ask for.

        Registered for closing the moment it exists: a connection left to the garbage
        collector keeps its lock, and closing twice is harmless.
        """
        conn = sqlite3.connect(str(self.at), isolation_level=None, timeout=5.0)
        self.addCleanup(conn.close)
        return conn

    def impatient(self) -> None:
        """Make SQLite's own busy handler give up at once, so a case about the retry
        in this module does not spend five seconds inside SQLite per attempt.

        `BUSY_SECONDS` is read in the body of `_open` rather than bound as a default,
        which is the only reason changing it here reaches anything.
        """
        self.addCleanup(setattr, store, "BUSY_SECONDS", store.BUSY_SECONDS)
        store.BUSY_SECONDS = 0.05

    def a_run(self, kept, **held) -> str:
        settled = dict(source="channel", provider="codex", brain="codex", posture="safe",
                       started_at=AT)
        settled.update(held)
        return kept.began(**settled)


class TheShapeOnDisk(WithAnAgentsOwnRecords):
    def test_a_fresh_database_is_stamped_with_the_shape_this_rundesk_understands(self):
        """First use and an upgrade converge on one shape, so a database made today
        needs no migration to be the same as one migrated to today."""
        kept = self.built()
        self.assertTrue(self.at.exists())
        self.assertEqual(store.VERSION, kept.version())
        self.assertEqual("wal", kept.journal())
        self.assertEqual({"provider": None, "model": None, "instructions": None,
                          "settings": {}}, kept.agent())
        self.assertIsNone(kept.last_seen())

    def test_making_a_database_that_is_already_there_keeps_everything_in_it(self):
        """`made()` is what every entry point calls before it does anything, so it runs
        far more often than once and must never be the thing that empties an agent."""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["u1"], AT)
        kept.made()
        kept.made()
        self.assertEqual(store.VERSION, kept.version())
        self.assertEqual(["discord"], [one["name"] for one in kept.channels()])

    def test_a_version_newer_than_this_code_understands_is_refused_rather_than_read(self):
        """Old code reading a newer shape is the dangerous direction: it does not know
        what it is missing, so it reads a partial truth and writes over the rest."""
        self.built()
        arranged = self.raw()
        arranged.execute(f"PRAGMA user_version = {store.VERSION + 1}")
        arranged.close()
        with self.assertRaises(store.TooNew) as refused:
            store.Store(self.at).made()
        self.assertEqual(store.VERSION + 1, refused.exception.found)
        self.assertEqual(store.VERSION, refused.exception.understood)

    def test_a_database_holding_tables_and_no_version_is_unreadable_rather_than_rebuilt(self):
        """It is one that died partway through being made. Building over it is writing an
        empty agent on top of whatever it did manage to keep."""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["u1"], AT)
        arranged = self.raw()
        arranged.execute("PRAGMA user_version = 0")
        arranged.close()
        with self.assertRaises(store.Unreadable):
            store.Store(self.at).made()
        self.assertEqual(["discord"], [one["name"] for one in kept.channels()],
                         "an unreadable database was built over rather than left alone")


class WhenTheShapeOnDiskIsNotThisOne(WithAnAgentsOwnRecords):
    """Both directions are refused, and the symmetry is the point.

    A newer shape is dangerous because this code does not know what it is missing. An older
    one is dangerous because this code assumes something that is not there yet. Guarding only
    the first leaves the second silently reading a partial truth and writing over the rest.
    """

    def older(self):
        """A database this rundesk has moved on from, with something in it worth keeping."""
        kept = self.built()
        kept.remember_channel("ops", "discord", ["u1"], AT)
        kept.opened("c1", "ops", "thread", "99123", AT, thread="4456")
        kept.arrived("c1", AT, "what about the parser")
        self.addCleanup(setattr, store, "VERSION", store.VERSION)
        store.VERSION += 1
        return kept

    def test_a_shape_this_rundesk_has_moved_past_is_refused_until_it_is_brought_forward(self):
        self.older()
        with self.assertRaises(store.Behind) as refused:
            store.Store(self.at).made()
        self.assertEqual(store.VERSION - 1, refused.exception.found)
        self.assertEqual(store.VERSION, refused.exception.understood)

    def test_an_older_shape_is_left_exactly_as_it_was_when_it_is_refused(self):
        """Refusing must cost nothing. A reader that repaired what it could not read would
        be the one thing standing between an owner and a migration that still works."""
        self.older()
        with self.assertRaises(store.Behind):
            store.Store(self.at).made()
        arranged = self.raw()
        self.assertEqual(store.VERSION - 1,
                         arranged.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual(1, arranged.execute("SELECT count(*) FROM channel").fetchone()[0])
        self.assertEqual("what about the parser",
                         arranged.execute("SELECT text FROM message").fetchone()[0])

    def test_a_database_half_built_is_not_a_state_that_can_exist(self):
        """The tables, the first rows and the stamp all move together.

        SQLite keeps DDL inside a transaction, so a build that dies partway leaves nothing
        rather than a shape nobody can name — and it is the same property that lets a
        migration carry its own version stamp instead of inventing a record of what ran.
        """
        broken = Path(tempfile.mkdtemp(prefix="rundesk-store-"))
        self.addCleanup(shutil.rmtree, broken, True)
        at = store.path_for(broken)
        # A step that does real work and then fails — what a build dying partway actually
        # looks like, rather than one nobody could parse in the first place.
        steps = Path(tempfile.mkdtemp(prefix="rundesk-steps-"))
        self.addCleanup(shutil.rmtree, steps, True)
        (steps / "001.py").write_text(
            "def up(conn, home):\n"
            "    conn.execute('CREATE TABLE agent (id INTEGER PRIMARY KEY)')\n"
            "    conn.execute('INSERT INTO agent (id) VALUES (1)')\n"
            "    raise RuntimeError('the machine went away')\n"
        )
        self.addCleanup(setattr, migration, "STEPS", migration.STEPS)
        migration.STEPS = steps
        self.addCleanup(setattr, store, "VERSION", store.VERSION)
        store.VERSION = 1
        with self.assertRaises(migration.Failed):
            store.Store(at).made()
        arranged = sqlite3.connect(str(at))
        self.addCleanup(arranged.close)
        self.assertEqual(0, arranged.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual(
            [], arranged.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='agent'"
            ).fetchall(),
            "a failed build left tables behind with no version to name them")


class TellingReadingAndWritingApart(WithAnAgentsOwnRecords):
    def test_a_reader_cannot_write_because_the_database_refuses_it(self):
        """The claim the whole module rests on: a reader is opened `mode=ro`, so it can
        never begin the work that would make a turn wait.

        Proven at the write and not at `BEGIN IMMEDIATE`, which succeeds on a read-only
        connection — SQLite defers taking the lock until something actually writes, so a
        case asserting on the `BEGIN` would be asserting on nothing.
        """
        kept = self.built()
        kept.remember_agent(model="what was really there")
        with kept._reading() as reader:
            reader.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError) as refused:
                reader.execute("UPDATE agent SET model = 'from a reader' WHERE id = 1")
        self.assertIn("readonly", str(refused.exception).lower())
        self.assertEqual("what was really there", kept.agent()["model"])

    def test_a_question_is_answered_while_a_turn_holds_the_write_lock(self):
        """The other half of the same claim, and the reason the journal is asked for
        rather than assumed: a listing during a long turn answers instead of waiting."""
        kept = self.built()
        kept.remember_agent(model="what was really there")
        held = self.raw()
        held.execute("BEGIN IMMEDIATE")
        held.execute("UPDATE agent SET model = 'not committed' WHERE id = 1")
        self.assertEqual("wal", kept.journal())
        self.assertEqual("what was really there", kept.agent()["model"])
        held.execute("ROLLBACK")
        held.close()

    def test_a_writer_that_finds_the_lock_taken_waits_and_takes_it_once_it_is_free(self):
        """Contention surfaces at `BEGIN IMMEDIATE`, before any of the work is done, so
        the boundary is the only thing ever issued twice."""
        self.impatient()
        kept = self.built()
        held = self.raw()
        held.execute("BEGIN IMMEDIATE")
        held.execute("UPDATE gateway SET last_seen_at = 'not committed' WHERE id = 1")
        waited = []

        def let_go(seconds):
            waited.append(seconds)
            if len(waited) == 1:
                held.execute("ROLLBACK")

        store.Store(self.at, wait=let_go).seen(AT)
        self.assertEqual(1, len(waited), "the boundary retry never fired")
        self.assertLessEqual(store.WAIT_LEAST, waited[0])
        self.assertLessEqual(waited[0], store.WAIT_MOST)
        self.assertEqual(AT, kept.last_seen())

    def test_a_writer_that_never_gets_the_lock_gives_up_rather_than_waiting_forever(self):
        """A turn blocked on a lock nobody will release has to end in something a caller
        can report, and the number of attempts is fixed rather than open-ended."""
        self.impatient()
        kept = self.built()
        held = self.raw()
        held.execute("BEGIN IMMEDIATE")
        held.execute("UPDATE gateway SET last_seen_at = 'not committed' WHERE id = 1")
        waited = []
        with self.assertRaises(sqlite3.OperationalError) as gave_up:
            store.Store(self.at, wait=waited.append).seen(AT)
        self.assertIn("lock", str(gave_up.exception).lower())
        self.assertEqual(store.TRIES - 1, len(waited), "it waited an unbounded number of times")
        held.execute("ROLLBACK")
        held.close()
        self.assertIsNone(kept.last_seen())

    def test_two_writers_at_once_cannot_lose_one_anothers_work(self):
        """Admitting a run reads the highest number and writes the next one. Two of them
        under a lock taken at commit would agree on the same number, and one run would
        either overwrite the other or be refused — so both take it at the start."""
        kept = self.built()
        trouble = []

        def admitting():
            try:
                mine = store.Store(self.at)
                for _ in range(15):
                    self.a_run(mine)
            except BaseException as went_wrong:  # reported, never swallowed
                trouble.append(repr(went_wrong))

        both = [threading.Thread(target=admitting) for _ in range(2)]
        for one in both:
            one.start()
        for one in both:
            one.join(60)
        self.assertEqual([], trouble)
        admitted = kept.runs(limit=100)
        self.assertEqual(30, len(admitted), "one writer's work was lost")
        self.assertEqual(30, len({one["id"] for one in admitted}), "two runs share one name")
        self.assertEqual(list(range(30, 0, -1)), [one["n"] for one in admitted])

    def test_two_writers_opening_one_conversation_make_one_room_between_them(self):
        """Two messages arriving at once on a surface nobody has spoken on yet is the
        ordinary case, not the rare one."""
        kept = self.built()
        found, trouble = [], []

        def opening(name):
            try:
                found.append(store.Store(self.at).opened(
                    name, "discord", "discord", "general", AT)["id"])
            except BaseException as went_wrong:
                trouble.append(repr(went_wrong))

        both = [threading.Thread(target=opening, args=(name,)) for name in ("c1", "c2")]
        for one in both:
            one.start()
        for one in both:
            one.join(60)
        self.assertEqual([], trouble)
        self.assertEqual(1, len(set(found)), "one place became two conversations")
        self.assertEqual(1, len(kept.conversations()))


class WhatAnAgentIsConfiguredWith(WithAnAgentsOwnRecords):
    def test_what_an_agent_falls_back_to_round_trips(self):
        kept = self.built()
        kept.remember_agent(provider="codex", model="gpt-5", instructions="be brief",
                            settings={"posture": "safe"})
        self.assertEqual({"provider": "codex", "model": "gpt-5", "instructions": "be brief",
                          "settings": {"posture": "safe"}}, kept.agent())

    def test_naming_one_thing_about_an_agent_does_not_clear_the_others(self):
        """Setting a model through a partial update is the commonest thing an owner does,
        and quietly dropping the provider with it would take the agent off the air."""
        kept = self.built()
        kept.remember_agent(provider="codex", model="gpt-5", instructions="be brief")
        kept.remember_agent(model="gpt-5-mini")
        self.assertEqual({"provider": "codex", "model": "gpt-5-mini",
                          "instructions": "be brief", "settings": {}}, kept.agent())
        kept.remember_agent()
        self.assertEqual("codex", kept.agent()["provider"])

    def test_when_a_gateway_was_last_up_outlives_the_gateway_that_wrote_it(self):
        """It is read by the *next* gateway, working out how long it was down."""
        kept = self.built()
        kept.seen(AT)
        self.assertEqual(AT, kept.last_seen())
        kept.seen(LATER)
        self.assertEqual(LATER, store.Store(self.at).last_seen())

    def test_a_surface_is_written_down_with_who_may_reach_the_agent_through_it(self):
        """Who may use it is sorted and said once: a listing that depends on the order
        two names were typed in is a listing that differs between two machines."""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["zoe", "amy", "zoe"], AT,
                              provider="codex", model="gpt-5", instructions="be brief",
                              settings={"prefix": "!"})
        self.assertEqual(
            {"name": "discord", "kind": "discord", "enabled": True, "provider": "codex",
             "model": "gpt-5", "instructions": "be brief", "allow": ["amy", "zoe"],
             "secret": None, "settings": {"prefix": "!"}, "created_at": AT},
            kept.channel("discord"))

    def test_a_channel_nobody_may_use_is_refused_rather_than_defaulted(self):
        """A surface with an empty allow answers whoever speaks to it. That is a
        misconfiguration and never a mode, so it is not writable at all."""
        kept = self.built()
        for nobody in ([], (), None):
            with self.assertRaises(ValueError):
                kept.remember_channel("discord", "discord", nobody, AT)
        self.assertEqual([], kept.channels())

    def test_a_channel_keeps_the_names_a_credential_is_read_from_and_never_one(self):
        """`secret` says *where* a token is read from. The token itself never reaches a
        file that gets copied off a machine when somebody asks for a database."""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT,
                              secret={"token": "RUNDESK_DISCORD_TOKEN"})
        self.assertEqual({"token": "RUNDESK_DISCORD_TOKEN"}, kept.channel("discord")["secret"])

    def test_a_surface_written_down_twice_replaces_itself_rather_than_doubling(self):
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT, model="gpt-5")
        kept.remember_channel("discord", "discord", ["zoe"], LATER, enabled=False)
        self.assertEqual(1, len(kept.channels()))
        again = kept.channel("discord")
        self.assertEqual(["zoe"], again["allow"])
        self.assertFalse(again["enabled"])
        self.assertIsNone(again["model"])
        self.assertEqual(AT, again["created_at"], "a rewrite forgot when it was first made")
        self.assertEqual([], kept.channels(enabled_only=True))

    def test_what_the_agent_is_told_about_being_somewhere_can_be_taken_off_again(self):
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT, instructions="be brief")
        kept.tell_channel("discord", "be briefer")
        self.assertEqual("be briefer", kept.channel("discord")["instructions"])
        kept.tell_channel("discord", "")
        self.assertIsNone(kept.channel("discord")["instructions"],
                          "an empty instruction was stored rather than taken off")

    def test_a_surface_is_forgotten_when_it_is_asked_to_be(self):
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT)
        kept.remember_channel("terminal", "terminal", ["amy"], AT)
        kept.forget_channel("discord")
        self.assertEqual(["terminal"], [one["name"] for one in kept.channels()])
        self.assertIsNone(kept.channel("discord"))

    def test_a_schedule_runs_a_command_or_asks_a_turn_and_never_both_or_neither(self):
        """The database enforces it as well, so the rule cannot be reached around."""
        kept = self.built()
        with self.assertRaises(ValueError):
            kept.remember_schedule("nightly", "0 3 * * *", AT)
        with self.assertRaises(ValueError):
            kept.remember_schedule("nightly", "0 3 * * *", AT, command=["ls"], prompt="how are we")
        self.assertEqual([], kept.schedules())
        kept.remember_schedule("nightly", "0 3 * * *", AT, command=["ls", "-l"],
                               next_auto_run_at=LATER)
        kept.remember_schedule("standup", "0 9 * * 1", AT, prompt="how are we",
                               provider="codex", model="gpt-5", instructions="be brief")
        self.assertEqual(["nightly", "standup"], [one["name"] for one in kept.schedules()])
        nightly = kept.schedule("nightly")
        self.assertEqual(["ls", "-l"], nightly["command"])
        self.assertIsNone(nightly["prompt"])
        self.assertEqual(LATER, nightly["next_auto_run_at"])
        standup = kept.schedule("standup")
        self.assertEqual("how are we", standup["prompt"])
        self.assertIsNone(standup["command"])
        self.assertEqual("gpt-5", standup["model"])

    def test_a_schedule_turned_off_keeps_its_row_and_everything_it_did(self):
        """Off is not gone: an owner turning something off for a week still wants to see
        it, and turning it back on must not need it typing again."""
        kept = self.built()
        kept.remember_schedule("nightly", "0 3 * * *", AT, command=["ls"])
        kept.schedule_fired("nightly", AT, LATER)
        kept.enable_schedule("nightly", False)
        off = kept.schedule("nightly")
        self.assertFalse(off["enabled"])
        self.assertEqual("0 3 * * *", off["cron"])
        self.assertEqual(AT, off["last_auto_run_at"])
        kept.enable_schedule("nightly", True)
        self.assertTrue(kept.schedule("nightly")["enabled"])
        kept.forget_schedule("nightly")
        self.assertIsNone(kept.schedule("nightly"))


class WhenTheClockStartsWork(WithAnAgentsOwnRecords):
    def setUp(self):
        super().setUp()
        self.kept = self.built()
        self.kept.remember_schedule("nightly", "0 3 * * *", AT, command=["ls"],
                                    next_auto_run_at=LATER)

    def test_the_clock_starting_a_schedule_moves_when_it_last_ran_on_its_own(self):
        self.kept.schedule_fired("nightly", LATER, "2026-07-27T10:00:00Z")
        fired = self.kept.schedule("nightly")
        self.assertEqual(LATER, fired["last_auto_run_at"])
        self.assertEqual("2026-07-27T10:00:00Z", fired["next_auto_run_at"])

    def test_a_firing_that_says_nothing_about_the_next_one_leaves_it_where_it_was(self):
        self.kept.schedule_fired("nightly", LATER)
        self.assertEqual(LATER, self.kept.schedule("nightly")["last_auto_run_at"])
        self.assertEqual(LATER, self.kept.schedule("nightly")["next_auto_run_at"])

    def test_running_a_schedule_by_hand_leaves_both_of_its_times_where_they_were(self):
        """Only the clock moves these. A hand-run that moved them would push out the next
        automatic firing, so asking for something now would quietly cancel tonight."""
        self.kept.schedule_fired("nightly", AT, LATER)
        by_hand = self.a_run(self.kept, source="hand",
                             schedule_id=self.kept.schedule("nightly")["id"])
        self.kept.recorded(by_hand, 1, LATER, "done", event={"ok": True})
        self.kept.ended(by_hand, LATER, "done", exit_code=0)
        after = self.kept.schedule("nightly")
        self.assertEqual(AT, after["last_auto_run_at"], "a hand-run moved when it last ran")
        self.assertEqual(LATER, after["next_auto_run_at"], "a hand-run moved when it is next due")
        self.assertEqual([by_hand],
                         [one["id"] for one in self.kept.runs(schedule_id=after["id"])])

    def test_writing_a_schedule_down_again_does_not_forget_when_it_last_ran(self):
        """Editing a cron is an ordinary thing to do, and it must not make the gateway
        think every firing since the schedule was made has been missed."""
        self.kept.schedule_fired("nightly", AT, LATER)
        self.kept.remember_schedule("nightly", "0 4 * * *", LATER, command=["ls", "-l"])
        after = self.kept.schedule("nightly")
        self.assertEqual("0 4 * * *", after["cron"])
        self.assertEqual(AT, after["last_auto_run_at"])


class WhereAConversationIsHappening(WithAnAgentsOwnRecords):
    def test_the_same_place_is_the_same_conversation_however_often_it_is_opened(self):
        """Every message that arrives asks this, so it is asked far more often than a
        conversation is begun — and answering it twice would split a room in half."""
        kept = self.built()
        first = kept.opened("c1", "discord", "discord", "general", AT)
        again = kept.opened("c2", "discord", "discord", "general", LATER)
        self.assertEqual("c1", again["id"], "one place became two conversations")
        self.assertEqual(AT, again["opened_at"])
        self.assertEqual(LATER, again["last_at"], "the room did not notice it was used")
        self.assertEqual(first["opened_at"], again["opened_at"])
        self.assertEqual(1, len(kept.conversations()))

    def test_a_conversation_with_no_thread_cannot_be_opened_into_a_second_room(self):
        """An absent thread is the empty one and never a value of its own: were it NULL
        the uniqueness would not hold, and every message on the main surface would make a
        new conversation."""
        kept = self.built()
        kept.opened("c1", "discord", "discord", "general", AT)
        self.assertEqual("c1", kept.opened("c2", "discord", "discord", "general", LATER,
                                           thread="")["id"])
        self.assertEqual(1, len(kept.conversations(channel="discord", space="general")))
        self.assertEqual("c1", kept.conversation("discord", "general")["id"])

    def test_a_thread_is_a_conversation_of_its_own_that_knows_what_it_came_from(self):
        kept = self.built()
        kept.opened("c1", "discord", "discord", "general", AT)
        branched = kept.opened("c2", "discord", "discord", "general", LATER,
                               thread="t-1", parent_id="c1", title="about orion")
        self.assertEqual("c2", branched["id"])
        self.assertEqual("c1", branched["parent_id"])
        self.assertEqual("about orion", branched["title"])
        self.assertEqual(2, len(kept.conversations()))
        self.assertIsNone(kept.conversation("discord", "general")["parent_id"])

    def test_a_conversation_somewhere_else_is_not_this_one(self):
        kept = self.built()
        kept.opened("c1", "discord", "discord", "general", AT)
        kept.opened("c2", "terminal", "terminal", "general", AT)
        self.assertEqual("c2", kept.conversation("terminal", "general")["id"])
        self.assertEqual(["c1"], [one["id"] for one in kept.conversations(channel="discord")])


class WhichBrainAConversationIsCarriedOnBy(WithAnAgentsOwnRecords):
    def setUp(self):
        super().setUp()
        self.kept = self.built()
        self.kept.opened("c1", "discord", "discord", "general", AT)
        self.kept.opened("c2", "terminal", "terminal", "here", AT)

    def test_a_conversation_continues_from_the_handle_its_brain_last_reported(self):
        self.assertIsNone(self.kept.session("c1", "codex"))
        self.kept.remember_session("c1", "codex", "thread-019f")
        self.assertEqual("thread-019f", self.kept.session("c1", "codex"))
        self.kept.remember_session("c1", "codex", "thread-02aa")
        self.assertEqual("thread-02aa", self.kept.session("c1", "codex"),
                         "a conversation kept two places it had got to")

    def test_one_brain_is_never_handed_another_brains_session(self):
        """Keyed by the conversation alone, changing which brain answers would hand one
        vendor's token to another, and there is no shape here in which that is sayable."""
        self.kept.remember_session("c1", "codex", "thread-019f")
        self.assertIsNone(self.kept.session("c1", "claude"),
                          "one brain was handed another brain's session")
        self.assertIsNone(self.kept.session("c2", "codex"),
                          "one conversation was handed another conversation's session")
        self.kept.remember_session("c1", "claude", "conv-771")
        self.assertEqual("thread-019f", self.kept.session("c1", "codex"))
        self.assertEqual("conv-771", self.kept.session("c1", "claude"))

    def test_a_conversation_can_be_started_fresh_for_one_brain_or_for_all_of_them(self):
        self.kept.remember_session("c1", "codex", "thread-019f")
        self.kept.remember_session("c1", "claude", "conv-771")
        self.kept.forget_session("c1", "codex")
        self.assertIsNone(self.kept.session("c1", "codex"))
        self.assertEqual("conv-771", self.kept.session("c1", "claude"))
        self.kept.forget_session("c1")
        self.assertIsNone(self.kept.session("c1", "claude"))


class TheAccountOfARun(WithAnAgentsOwnRecords):
    def test_every_run_is_named_once_and_no_name_is_handed_out_twice(self):
        """The mark is fixed here on purpose: left random it hides the thing under test,
        because two runs given the same number would still get different names."""
        kept = self.built()
        same = lambda _: "a"  # noqa: E731 — so only the number can keep two names apart
        named = [self.a_run(kept, pick=same) for _ in range(20)]
        self.assertEqual(20, len(set(named)), "two runs were given one name")
        self.assertEqual([str(n) for n in range(1, 21)],
                         [one.partition("-")[0] for one in named])
        self.assertEqual(list(range(1, 21)), sorted(one["n"] for one in kept.runs(limit=50)))

    def test_a_runs_name_carries_a_mark_of_its_own_beside_the_number(self):
        """So two agents' runs never look interchangeable read side by side."""
        kept = self.built()
        mark = self.a_run(kept).partition("-")[2]
        self.assertEqual(store.MARK_LENGTH, len(mark))
        self.assertEqual(set(), set(mark) - set(store.MARK_FROM))

    def test_everything_settled_when_a_run_was_admitted_is_written_down_with_it(self):
        """Resolved once, at admission — a run that read its brain back out of the agent
        afterwards would report a model the work was never done with."""
        kept = self.built()
        kept.opened("c1", "discord", "discord", "general", AT)
        said = kept.arrived("c1", AT, "how are we")
        named = kept.began("channel", "codex", "/opt/my-brain", "safe", AT,
                           conversation_id="c1", trigger_message_id=said, model="gpt-5",
                           can={"steer": True}, resumed=True, pick=lambda _: "a")
        self.assertEqual(
            {"n": 1, "id": named, "conversation_id": "c1", "schedule_id": None,
             "source": "channel", "trigger_message_id": said, "provider": "codex",
             "brain": "/opt/my-brain", "model": "gpt-5", "posture": "safe",
             "can": {"steer": True}, "resumed": True, "started_at": AT, "ended_at": None,
             "outcome": None, "exit_code": None, "tokens_in": None, "tokens_out": None,
             "tokens_cached": None, "tokens_written": None, "tokens_reported": False},
            kept.run(named))
        self.assertEqual([named], [one["id"] for one in kept.runs(conversation_id="c1")])
        self.assertIsNone(kept.run("404-zzzz"))

    def test_how_a_run_finished_and_what_it_cost_is_written_at_the_end(self):
        kept = self.built()
        named = self.a_run(kept)
        kept.ended(named, LATER, "done", exit_code=0,
                   tokens={"input": 120, "output": 30, "cached": 10, "written": 5,
                           "reported": True})
        finished = kept.run(named)
        self.assertEqual(LATER, finished["ended_at"])
        self.assertEqual("done", finished["outcome"])
        self.assertEqual(0, finished["exit_code"])
        self.assertEqual((120, 30, 10, 5),
                         (finished["tokens_in"], finished["tokens_out"],
                          finished["tokens_cached"], finished["tokens_written"]))
        self.assertTrue(finished["tokens_reported"])

    def test_a_run_whose_cost_never_arrived_is_left_absent_rather_than_written_as_nothing(self):
        """A run that cost an unknown amount and one that cost zero are different facts,
        and writing the first as the second is the way a total starts lying."""
        kept = self.built()
        named = self.a_run(kept)
        kept.ended(named, LATER, "lost", exit_code=1)
        silent = kept.run(named)
        for column in ("tokens_in", "tokens_out", "tokens_cached", "tokens_written"):
            self.assertIsNone(silent[column], f"{column} was written as nothing")
        self.assertFalse(silent["tokens_reported"])

    def test_what_an_agent_cost_counts_a_run_it_cannot_account_for_apart(self):
        """So a total never quietly claims to know more than it does."""
        kept = self.built()
        # An agent that has run nothing has no totals to give, and says so: absent rather
        # than zero, which is the same distinction a run's own missing usage keeps.
        nothing_yet = kept.usage()
        self.assertEqual({"runs": 0, "reported": 0, "unreported": 0},
                         {word: nothing_yet[word]
                          for word in ("runs", "reported", "unreported")})
        self.assertEqual([None] * 4, [nothing_yet[word] for word
                                      in ("input", "output", "cached", "written")])
        silent = self.a_run(kept)
        kept.ended(silent, LATER, "done")
        told = self.a_run(kept)
        kept.ended(told, LATER, "done",
                   tokens={"input": 120, "output": 30, "cached": 10, "written": 5,
                           "reported": True})
        self.assertEqual({"runs": 2, "reported": 1, "unreported": 1, "input": 120,
                          "output": 30, "cached": 10, "written": 5}, kept.usage())

    def test_a_runs_account_is_read_back_in_the_order_the_work_happened(self):
        """`seq` is the order and a clock is not, so an account written by a machine whose
        clock went backwards still reads in the order the work was done."""
        kept = self.built()
        named = self.a_run(kept)
        going_back = ["2026-07-26T09:00:03Z", "2026-07-26T09:00:02Z", "2026-07-26T09:00:01Z"]
        for seq, at in zip((3, 2, 1), going_back):
            kept.recorded(named, seq, at, "think", event={"text": f"n{seq}"})
        said = kept.records(named)
        self.assertEqual([1, 2, 3], [one["seq"] for one in said])
        self.assertEqual(["n1", "n2", "n3"], [one["event"]["text"] for one in said])

    def test_a_runs_account_is_added_to_and_never_rewritten(self):
        """One place in the order is one line, and a second line claiming it is refused
        rather than replacing what is already there."""
        kept = self.built()
        named = self.a_run(kept)
        kept.recorded(named, 1, AT, "think", event={"text": "first"})
        with self.assertRaises(sqlite3.IntegrityError):
            kept.recorded(named, 1, LATER, "think", event={"text": "instead of the first"})
        self.assertEqual([{"text": "first"}], [one["event"] for one in kept.records(named)])

    def test_a_line_rundesk_did_not_understand_is_kept_with_what_it_actually_said(self):
        """A brain that can only grow when we release is one we have made slower than we
        are: its place in the order is kept and its own words are there to be read."""
        kept = self.built()
        named = self.a_run(kept)
        kept.recorded(named, 1, AT, "unknown", raw='{"type":"constellation"}')
        kept.recorded(named, 2, AT, "done", event={"ok": True})
        said = kept.records(named)
        self.assertEqual(["unknown", "done"], [one["kind"] for one in said])
        self.assertIsNone(said[0]["event"], "it passed off a record it does not understand")
        self.assertEqual('{"type":"constellation"}', said[0]["raw"])
        self.assertEqual({"ok": True}, said[1]["event"])

    def test_a_record_of_a_kind_that_does_not_exist_is_refused(self):
        """`unknown` is the shape a surprise takes, so a kind nobody defined is a mistake
        in this codebase rather than news from a brain."""
        kept = self.built()
        named = self.a_run(kept)
        with self.assertRaises(ValueError):
            kept.recorded(named, 1, AT, "constellation")
        self.assertEqual([], kept.records(named))

    def test_taking_a_run_away_takes_its_account_and_leaves_what_was_said(self):
        """What a person said is theirs and outlives the run that answered it; the answer
        stays too, no longer claiming a run that is gone."""
        kept = self.built()
        kept.opened("c1", "discord", "discord", "general", AT)
        named = self.a_run(kept, conversation_id="c1")
        kept.recorded(named, 1, AT, "done", event={"ok": True})
        kept.arrived("c1", AT, "how are we")
        kept.answered("c1", named, LATER, "we are well")
        kept.forget_run(named)
        self.assertIsNone(kept.run(named))
        self.assertEqual([], kept.records(named))
        self.assertEqual(["how are we", "we are well"],
                         [one["text"] for one in kept.messages("c1")])
        self.assertEqual([None, None], [one["run_id"] for one in kept.messages("c1")])


class WhatWasSaid(WithAnAgentsOwnRecords):
    def setUp(self):
        super().setUp()
        self.kept = self.built()
        self.kept.opened("c1", "discord", "discord", "general", AT)

    def test_a_conversation_is_read_back_in_the_order_it_happened(self):
        named = self.a_run(self.kept, conversation_id="c1")
        self.kept.arrived("c1", AT, "how are we", who="u-1", who_label="amy",
                          external_id="d-1")
        self.kept.answered("c1", named, LATER, "we are well", external_id="d-2")
        self.kept.arrived("c1", LATER, "good", who="u-1")
        said = self.kept.messages("c1")
        self.assertEqual(["how are we", "we are well", "good"],
                         [one["text"] for one in said])
        self.assertEqual(["person", "agent", "person"], [one["author"] for one in said])
        self.assertEqual("amy", said[0]["who_label"])
        self.assertEqual(named, said[1]["run_id"])
        self.assertEqual(LATER, self.kept.conversation("discord", "general")["last_at"])

    def test_something_said_by_nobody_this_agent_knows_of_is_refused(self):
        with self.assertRaises(ValueError):
            self.kept.arrived("c1", AT, "how are we", author="martian")
        self.assertEqual([], self.kept.messages("c1"))

    def test_a_channel_reconnecting_cannot_record_one_message_twice(self):
        """A reconnect replays what a surface already delivered. The platform's own id
        makes that the same message, refused by the database rather than guarded here."""
        self.kept.arrived("c1", AT, "how are we", external_id="d-1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.kept.arrived("c1", LATER, "how are we", external_id="d-1")
        self.assertEqual(1, len(self.kept.messages("c1")))

    def test_the_same_id_on_another_surface_is_another_message(self):
        """Two platforms number their own messages, and one is not the other's."""
        self.kept.opened("c2", "terminal", "terminal", "here", AT)
        self.kept.arrived("c1", AT, "how are we", external_id="1")
        self.kept.arrived("c2", AT, "how are we", external_id="1")
        self.assertEqual(1, len(self.kept.messages("c1")))
        self.assertEqual(1, len(self.kept.messages("c2")))

    def test_a_conversation_going_takes_what_was_said_in_it(self):
        """Nothing in this module deletes a conversation; the cascade is the schema's, and
        it is what keeps messages from outliving the room they were said in."""
        self.kept.arrived("c1", AT, "how are we")
        self.kept.arrived("c1", LATER, "still here")
        taking = self.raw()
        taking.execute("PRAGMA foreign_keys=ON")
        taking.execute("DELETE FROM conversation WHERE id = 'c1'")
        taking.close()
        self.assertEqual([], self.kept.messages("c1"))
        self.assertIsNone(self.kept.conversation("discord", "general"))


class FindingWhatWasSaidAboutSomething(WithAnAgentsOwnRecords):
    def said_everywhere(self, kept) -> None:
        kept.opened("c1", "discord", "discord", "general", AT)
        kept.opened("c2", "terminal", "terminal", "here", AT)
        named = self.a_run(kept, conversation_id="c2")
        kept.arrived("c1", AT, "the orion release is out")
        kept.answered("c2", named, LATER, "orion shipped this morning")
        kept.arrived("c1", LATER, "nothing whatever to do with it")

    def test_a_word_is_found_wherever_it_was_said_and_whoever_said_it(self):
        kept = self.built()
        if not kept.searchable():
            self.skipTest("this machine's SQLite was built without FTS5")
        self.said_everywhere(kept)
        found = kept.search("orion")
        self.assertEqual(2, len(found))
        self.assertEqual({"discord", "terminal"}, {one["channel"] for one in found})
        self.assertEqual({"general", "here"}, {one["space"] for one in found})
        self.assertEqual({"person", "agent"}, {one["author"] for one in found})
        self.assertEqual([], kept.search("constellation"))

    def test_a_machine_that_cannot_search_says_so_rather_than_answering_nothing(self):
        """FTS5 is a compile-time option and not a guarantee. An empty answer and an
        impossible question must not look the same — everything else still answers, so
        what is lost is searching and never the records."""
        kept = self.built()
        # A machine whose SQLite has no FTS5 builds everything except the index and its
        # triggers, which is exactly this state. Reached by taking them away rather than by
        # patching the step that builds them, so the case is about what a caller then sees.
        arranged = self.raw()
        arranged.execute("DROP TRIGGER message_fts_insert")
        arranged.execute("DROP TRIGGER message_fts_delete")
        arranged.execute("DROP TRIGGER message_fts_update")
        arranged.execute("DROP TABLE message_fts")
        arranged.close()
        kept._searchable = None
        self.assertFalse(kept.searchable())
        self.assertFalse(store.Store(self.at).searchable(),
                         "a fresh Store believed a search index that is not there")
        self.said_everywhere(kept)
        named = kept.runs()[0]["id"]
        kept.recorded(named, 1, AT, "done", event={"ok": True})
        with self.assertRaises(store.Unsearchable):
            kept.search("orion")
        self.assertEqual(2, len(kept.messages("c1")))
        self.assertEqual(1, len(kept.messages("c2")))
        self.assertEqual(1, len(kept.runs()))
        self.assertEqual(1, len(kept.records(named)))
        self.assertEqual(store.VERSION, kept.version())


class TakingAnAgentsRecordsAway(WithAnAgentsOwnRecords):
    def test_taking_the_records_away_names_the_two_files_beside_the_database(self):
        """A database in WAL is three files, and the two beside it are the database's
        rather than ours — left behind, they are a record of what was deleted."""
        named = store.removes(self.where)
        self.assertEqual([self.at, Path(str(self.at) + "-wal"), Path(str(self.at) + "-shm")],
                         named)

    def test_nothing_of_an_agents_records_is_left_behind(self):
        kept = self.built()
        kept.opened("c1", "discord", "discord", "general", AT)
        kept.arrived("c1", AT, "how are we")
        # SQLite leaves the two beside the database whenever the last connection to close
        # was a reader, which cannot check the WAL back in. Made certain here, so the case
        # is about `gone()` and not about which connection happened to close last.
        for beside in store.removes(self.where)[1:]:
            beside.touch()
        store.gone(self.where)
        for one in store.removes(self.where):
            self.assertFalse(one.exists(), f"{one.name} was left behind")
        self.assertEqual([], sorted(self.where.iterdir()))
        store.gone(self.where)  # asking twice is not an error


class OneAgentIsNeverInAnothersWay(WithAnAgentsOwnRecords):
    """The reason there is one database per agent rather than one for the install.

    A shared one would put a turn's write lock in another agent's way and make one corrupt
    file everybody's problem — the coupling that keeps one gateway restartable without
    disturbing the rest exists precisely to prevent this.
    """

    def test_one_agent_writing_never_makes_another_agent_wait(self):
        self.impatient()
        mine = self.built()
        elsewhere = Path(tempfile.mkdtemp(prefix="rundesk-store-"))
        self.addCleanup(shutil.rmtree, elsewhere, True)
        theirs = store.Store(store.path_for(elsewhere))
        theirs.made()

        held = self.raw()
        held.execute("BEGIN IMMEDIATE")
        held.execute("UPDATE gateway SET last_seen_at = 'mine, uncommitted' WHERE id = 1")
        try:
            # No wait is given, so a single blocked attempt would raise rather than sleep.
            theirs.seen(LATER)
            theirs.remember_channel("ops", "discord", ["u1"], AT)
        finally:
            held.execute("ROLLBACK")
            held.close()

        self.assertEqual(LATER, theirs.last_seen())
        self.assertEqual(["ops"], [one["name"] for one in theirs.channels()])
        self.assertIsNone(mine.last_seen(), "one agent's write reached another's records")
        self.assertEqual([], mine.channels())


class WhatSurvivesLosingEverythingElse(WithAnAgentsOwnRecords):
    """The purpose of the split, stated as a case rather than as a paragraph.

    What an agent **is and keeps** — how it is configured, and everything it has been told and
    has said — is in one file. What is beside it is raw: what a brain printed, what went wrong,
    what the gateway said while it was happening. Those are diagnostics and may be destroyed to
    reclaim space, so nothing an agent needs may live only there.

    Copy the one file somewhere else and the agent is whole. That is what makes it worth having.
    """

    def furnished(self) -> str:
        """An agent with configuration and history, and raw files beside it."""
        kept = self.built()
        kept.remember_agent(provider="codex", instructions="be terse")
        kept.remember_channel("ops", "discord", ["u1"], AT, provider="codex")
        kept.remember_schedule("nightly", "0 3 * * *", AT, prompt="what changed?")
        kept.opened("c1", "ops", "thread", "99123", AT, thread="4456")
        asked = kept.arrived("c1", AT, "what about the parser", who="u1")
        named = self.a_run(kept, conversation_id="c1", trigger_message_id=asked)
        kept.recorded(named, 1, AT, "tool", event={"name": "grep"}, raw='{"type":"tool"}')
        kept.answered("c1", named, LATER, "the parser was rewritten")
        kept.ended(named, LATER, "finished", tokens={"input": 10, "output": 5, "reported": True})
        kept.remember_session("c1", "codex", "sess-abc")
        for raw in ("logs/gateway.log", "logs/runs/1-x.jsonl", "logs/runs/1-x.err",
                    "home/AGENTS.md", "providers/codex/config.toml", "channels/ops/token",
                    "gateway.json", "gateway.lock"):
            beside = self.where / raw
            beside.parent.mkdir(parents=True, exist_ok=True)
            beside.write_text("raw, and destroyable")
        return named

    def cleared(self) -> None:
        """Everything gone but the database and the two SQLite keeps beside it."""
        keeping = {one.name for one in store.removes(self.where)}
        for child in list(self.where.iterdir()):
            if child.name in keeping:
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()

    def test_an_agent_is_whole_again_from_its_records_alone(self):
        named = self.furnished()
        self.cleared()
        self.assertEqual(sorted(one.name for one in self.where.iterdir()),
                         sorted(one.name for one in store.removes(self.where)))

        back = store.Store(self.at)
        back.made()
        self.assertEqual(store.VERSION, back.version())
        # what it is configured to do
        self.assertEqual("codex", back.agent()["provider"])
        self.assertEqual("be terse", back.agent()["instructions"])
        self.assertEqual(["ops"], [one["name"] for one in back.channels()])
        self.assertEqual(["nightly"], [one["name"] for one in back.schedules()])
        # where it got to
        self.assertEqual("sess-abc", back.session("c1", "codex"))
        self.assertEqual("c1", back.conversation("ops", "99123", "4456")["id"])
        # everything it was told and said
        self.assertEqual([("person", "what about the parser"),
                          ("agent", "the parser was rewritten")],
                         [(one["author"], one["text"]) for one in back.messages("c1")])
        self.assertEqual(["finished"], [one["outcome"] for one in back.runs()])
        self.assertEqual(10, back.runs()[0]["tokens_in"])
        self.assertEqual([(1, "tool")], [(one["seq"], one["kind"]) for one in back.records(named)])
        self.assertEqual(2, len(back.search("parser")))

    def test_what_a_brain_printed_going_costs_the_account_nothing(self):
        """The reason those files may be destroyed at all: every line an adapter produced is
        already a row, so a run whose raw file is gone still says what happened."""
        named = self.furnished()
        shutil.rmtree(self.where / "logs")
        back = store.Store(self.at)
        self.assertEqual('{"type":"tool"}', back.records(named)[0]["raw"],
                         "what the adapter said was recoverable only from a file")
        self.assertEqual("finished", back.run(named)["outcome"])


class TheOnlyWayIn(unittest.TestCase):
    """Nothing outside this module knows a database is there.

    The same rule the provider and channel seams hold to, where here the vendor is the
    database. Proved by looking rather than by intention: a sibling project confined every
    statement to four modules and still leaked, because one of them exposed its connection
    and six call sites reached through it. Every one began as a single read.
    """

    SOURCE = Path(__file__).resolve().parent.parent / "src" / "rundesk_cli"

    # The seam, named rather than assumed. `store.py` is every question a caller may ask;
    # `migration.py` opens a database only to move it forward; a step under `migrations/` IS a
    # description of a schema, which is its whole job. Nothing else may know a database exists,
    # and this list is what would have to grow before that stopped being true.
    SEAM = ("store.py", "migration.py")

    def elsewhere(self):
        """Every source file that is not part of the seam."""
        return [path for path in sorted(self.SOURCE.rglob("*.py"))
                if path.name not in self.SEAM
                and "__pycache__" not in path.parts
                and "migrations" not in path.parts]

    def test_no_statement_is_written_anywhere_but_the_one_module(self):
        said = re.compile(r"\b(SELECT\s|INSERT\s+INTO\b|UPDATE\s+\w+\s+SET\b|DELETE\s+FROM\b"
                          r"|CREATE\s+(TABLE|INDEX|TRIGGER|VIRTUAL)\b|BEGIN\s+IMMEDIATE\b)",
                          re.IGNORECASE)
        leaked = [f"{path.name}:{n}" for path in self.elsewhere()
                  for n, line in enumerate(path.read_text().splitlines(), 1)
                  if said.search(line)]
        self.assertEqual([], leaked, "a statement was written outside the module that owns it")

    def test_no_other_module_reaches_the_database_for_itself(self):
        imported = [path.name for path in self.elsewhere()
                    if re.search(r"^\s*(import\s+sqlite3|from\s+sqlite3\s+import)",
                                 path.read_text(), re.MULTILINE)]
        self.assertEqual([], imported, "a module opened the database without going through the seam")

    def test_nothing_a_caller_is_handed_is_a_connection(self):
        """A caller that can reach the connection will eventually use it.

        Every public name on the store is checked, because the leak that matters is not a
        method returning one — it is an attribute somebody notices and reads.
        """
        where = Path(tempfile.mkdtemp(prefix="rundesk-store-"))
        self.addCleanup(shutil.rmtree, where, True)
        kept = store.Store(store.path_for(where))
        kept.made()
        kept.opened("c1", "terminal", "terminal", "terminal", AT)
        kept.arrived("c1", AT, "anything at all")
        handed = [kept.agent(), kept.channels(), kept.schedules(), kept.conversations(),
                  kept.messages("c1"), kept.runs(), kept.usage(),
                  kept.conversation("terminal", "terminal")]
        for one in handed:
            for value in (one.values() if isinstance(one, dict) else one):
                self.assertNotIsInstance(value, sqlite3.Connection)
                self.assertNotIsInstance(value, sqlite3.Cursor)
                self.assertNotIsInstance(value, sqlite3.Row)
        held = [name for name in vars(kept)
                if isinstance(getattr(kept, name), (sqlite3.Connection, sqlite3.Cursor))]
        self.assertEqual([], held, "the store kept a connection where a caller could reach it")

    def test_the_product_does_not_reach_the_new_store_yet(self):
        """Deleting this module must leave the product exactly as it was.

        The whole safety of building it before anything moves onto it. One reader changed to
        use it and that is no longer true — which is the next phase, not this one.
        """
        importing = [path.name for path in self.elsewhere()
                     if re.search(r"^\s*(from\s+\.?\s*store\s+import|import\s+.*\bstore\b)",
                                  path.read_text(), re.MULTILINE)]
        self.assertEqual([], importing, "something already reads the store — that is the next phase")


if __name__ == "__main__":
    unittest.main(verbosity=2)
