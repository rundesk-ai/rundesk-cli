"""Everything one agent keeps, and the only way in to it — every claim `store.py` makes.

Nothing here reaches the network, starts a gateway, runs a program or goes near the
machine's own `~/.rundesk`: a `Store` is built with a path, so each case gives it a
directory of its own. Every connection a case opens itself is closed — a leaked one holds
the WAL read lock on newer Pythons and not on the floor version, so the leak is invisible
exactly where CI would catch it.

Run: python3 tests/test_store.py
"""

from __future__ import annotations

import contextlib
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import migration, store  # noqa: E402

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
        settled = dict(source="channel", provider="codex", posture="safe",
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
        self.assertTrue(kept.display_name())
        self.assertIsNone(kept.last_seen())

    def test_an_agents_display_name_is_kept_without_changing_its_brain(self):
        """R-AGT-39 — the human spelling is durable state beside, not inside, the slug."""
        kept = self.built()
        kept.remember_display_name("iOS Helper")
        self.assertEqual("iOS Helper", kept.display_name())
        self.assertEqual({"provider": None, "model": None, "instructions": None,
                          "settings": {}}, kept.agent())

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

    def test_records_that_are_not_there_are_the_seams_own_answer(self):
        """R-STO-16 — nothing of the database's leaves this module, exceptions included. A
        caller that handles a shape this rundesk will not read would otherwise meet a raw
        `unable to open database file` and let it out — which, at the one caller the machine
        invokes, is a gateway restarted every ten seconds for as long as the machine is up."""
        with self.assertRaises(store.Unreadable) as refused:
            store.Store(self.at).understood()
        self.assertIn("has no records yet", str(refused.exception))

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


class WhenTwoOfThemArriveAtOnce(WithAnAgentsOwnRecords):
    """Making a database is a read, a decision and a write, and they belong under one hold.

    Two commands can reach for one agent's records at the same moment — a gateway starting
    while something is typed at it. Both looking before either acts is how one of them ends up
    reporting that a perfectly healthy database failed to be built.
    """

    def test_two_of_them_building_one_fresh_database_both_succeed(self):
        trouble, done = [], []

        def build():
            try:
                made = store.Store(self.at)
                made.made()
                done.append(made.version())
            except BaseException as raised:      # noqa: BLE001 — the case is what escapes
                trouble.append(repr(raised))

        pair = [threading.Thread(target=build) for _ in range(2)]
        for one in pair:
            one.start()
        for one in pair:
            one.join()

        self.assertEqual([], trouble, "one of them was told a healthy database had failed")
        self.assertEqual([store.VERSION, store.VERSION], done)
        # and what they built is real, not merely unraised-against
        back = store.Store(self.at)
        self.assertEqual({"provider": None, "model": None, "instructions": None,
                          "settings": {}}, back.agent())

    def test_a_build_landing_between_the_two_looks_is_never_seen_half_way(self):
        """The same race, made to happen rather than waited for (#278).

        The case above is the real shape, and 300 rounds of it on this machine tripped it
        none — a case that reports a fix it cannot tell from luck. Here the second command is
        stopped between its version read and its table read, and the other command's whole
        build — the tables and the version stamp that goes with them — is committed while it
        stands there. Two unheld reads see version 0 *and* the tables, and `_refused` calls
        that written partway; one hold sees neither half, because the build cannot land.

        Nothing in `src/` is reached into: the stop is a subclass, and what tells the two
        outcomes apart is the write lock answering rather than a clock. `timeout=0` is what
        makes "somebody is holding it" an answer instead of a wait, so the held path costs
        nothing and neither path sleeps.
        """
        bound = 10.0
        looking, landed = threading.Event(), threading.Event()

        class Held(store.Store):
            """Stopped once, between the two reads `made` decides on."""

            def _anything(self, conn):
                if not looking.is_set():
                    looking.set()
                    landed.wait(bound)
                return store.Store._anything(conn)

        trouble = []

        def build():
            try:
                Held(self.at).made()
            except BaseException as raised:      # noqa: BLE001 — the case is what escapes
                trouble.append(repr(raised))

        second = threading.Thread(target=build)
        second.start()
        self.addCleanup(second.join, bound)
        self.assertTrue(looking.wait(bound), "the second command never took its first look")

        arranged = sqlite3.connect(str(self.at), isolation_level=None, timeout=0)
        try:
            arranged.execute("BEGIN IMMEDIATE")
            arranged.execute("CREATE TABLE agent (id INTEGER PRIMARY KEY)")
            arranged.execute(f"PRAGMA user_version = {store.VERSION}")
            arranged.execute("COMMIT")
        except sqlite3.OperationalError:
            # The write lock is held across both looks, so this build has nowhere to land —
            # which is the whole of the fix, said by the database rather than by a timer.
            with contextlib.suppress(sqlite3.OperationalError):
                arranged.execute("ROLLBACK")
        finally:
            arranged.close()
            landed.set()
        second.join(bound)

        self.assertFalse(second.is_alive(), "the second command never finished")
        self.assertEqual([], trouble, "a build landing mid-look was read as tables at "
                                      "version 0 and refused as written partway")
        back = store.Store(self.at)
        self.assertEqual(store.VERSION, back.version())
        self.assertEqual({"provider": None, "model": None, "instructions": None,
                          "settings": {}}, back.agent())


class WhenTheRecordsAreNotADatabaseAtAll(WithAnAgentsOwnRecords):
    """R-STO-13 — a stalled volume, a truncated restore, a half-copied file. The driver says
    "file is not a database", and left to escape that reached callers which already handle
    every shape they will not read and handled this one by tracebacking. Nothing of the
    database's leaves this module, exceptions included."""

    GARBLED = "this is not a database, and everything the owner wrote is still in here"

    def garbled(self):
        self.at.parent.mkdir(parents=True, exist_ok=True)
        self.at.write_text(self.GARBLED)

    def test_records_that_cannot_be_read_are_refused_in_this_seams_own_words(self):
        """R-STO-13 — both ways in answer the same thing the same way, because a caller
        that only reads and one that may write both meet it."""
        for opening in ("made", "understood"):
            with self.subTest(opening=opening):
                self.garbled()
                with self.assertRaises(store.Unreadable):
                    getattr(store.Store(self.at), opening)()

    def test_records_that_cannot_be_read_are_left_exactly_as_they_are(self):
        """R-STO-13 — they still hold everything the owner ever wrote, so the one thing
        that must not happen is writing over them to make the error go away."""
        self.garbled()
        with self.assertRaises(store.Unreadable):
            store.Store(self.at).made()
        self.assertEqual(self.GARBLED, self.at.read_text())

    def test_records_that_cannot_be_read_say_so_in_the_agents_own_log(self):
        """R-STO-20 — the one account that outlives whatever was asking."""
        self.garbled()
        with self.assertRaises(store.Unreadable):
            store.Store(self.at).understood()
        self.assertIn("could not be read at all",
                      (self.at.parent / "logs" / "gateway.log").read_text())


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
        return kept

    def test_a_shape_this_rundesk_has_moved_past_is_refused_until_it_is_brought_forward(self):
        self.older()
        with self.assertRaises(store.Behind) as refused:
            store.Store(self.at, version=store.VERSION + 1).made()
        self.assertEqual(store.VERSION, refused.exception.found)
        self.assertEqual(store.VERSION + 1, refused.exception.understood)

    def test_an_older_shape_is_left_exactly_as_it_was_when_it_is_refused(self):
        """Refusing must cost nothing. A reader that repaired what it could not read would
        be the one thing standing between an owner and a migration that still works."""
        self.older()
        with self.assertRaises(store.Behind):
            store.Store(self.at, version=store.VERSION + 1).made()
        arranged = self.raw()
        self.assertEqual(store.VERSION,
                         arranged.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual(1, arranged.execute("SELECT count(*) FROM channel").fetchone()[0])
        self.assertEqual("what about the parser",
                         arranged.execute("SELECT text FROM message").fetchone()[0])

    def test_a_shape_that_says_it_is_here_and_is_not_is_refused_rather_than_read(self):
        """A version says which shape this is meant to be, never that the shape is there.

        The header survives a truncated restore where the pages holding the tables do not, so
        a database can claim the current version and hold nothing. The mirror case — tables
        with no version — was guarded and this one was not, and this is the one that reads as
        healthy right up until the first real question.
        """
        self.built()
        arranged = self.raw()
        for table in ("record", "message", "run", "session", "conversation",
                      "schedule", "channel", "gateway", "agent"):
            arranged.execute(f"DROP TABLE IF EXISTS {table}")
        self.assertEqual(store.VERSION,
                         arranged.execute("PRAGMA user_version").fetchone()[0])
        arranged.close()
        with self.assertRaises(store.Unreadable):
            store.Store(self.at).made()

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
        with self.assertRaises(migration.Failed):
            store.Store(at, version=1).made()
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
        self.assertEqual(store.moment(AT), kept.last_seen())

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

    def test_replacing_a_brain_clears_only_its_provider_specific_defaults(self):
        """R-AGT-31, R-AGT-33 — one row changes atomically; the agent remains itself."""
        kept = self.built()
        kept.remember_agent(provider="codex", model="o3", instructions="be brief",
                            settings={"effort": "high"})
        kept.remember_agent(provider="claude", replace_brain=True)
        self.assertEqual({
            "provider": "claude", "model": None, "instructions": "be brief", "settings": {},
        }, kept.agent())

    def test_naming_the_current_brain_does_not_clear_newer_defaults(self):
        """R-AGT-31 — replacement is decided under the store's write transaction."""
        kept = self.built()
        kept.remember_agent(provider="claude", model="opus",
                            settings={"effort": "low"})
        kept.remember_agent(provider="claude", replace_brain=True)
        self.assertEqual("opus", kept.agent()["model"])
        self.assertEqual({"effort": "low"}, kept.agent()["settings"])

    def test_provider_and_conversation_sessions_change_in_one_transaction(self):
        """R-CH-26 — a failed session reset rolls the provider change back too."""
        kept = self.built()
        kept.remember_agent(provider="codex", model="o3",
                            settings={"effort": "high"})
        kept.opened("c1", "discord", "discord", "thread", AT)
        kept.remember_session("c1", "codex", "old-codex")
        kept.remember_session("c1", "claude", "old-claude")
        with kept._writing() as conn:
            conn.execute(
                "CREATE TRIGGER refuse_session_reset BEFORE DELETE ON session "
                "BEGIN SELECT RAISE(FAIL, 'session reset refused'); END")

        with self.assertRaises(sqlite3.IntegrityError):
            kept.remember_agent(
                provider="claude", replace_brain=True, forget_conversation="c1")

        self.assertEqual({
            "provider": "codex", "model": "o3", "instructions": None,
            "settings": {"effort": "high"},
        }, kept.agent())
        self.assertEqual("old-codex", kept.session("c1", "codex"))
        self.assertEqual("old-claude", kept.session("c1", "claude"))

    def test_when_a_gateway_was_last_up_outlives_the_gateway_that_wrote_it(self):
        """It is read by the *next* gateway, working out how long it was down."""
        kept = self.built()
        kept.seen(AT)
        self.assertEqual(store.moment(AT), kept.last_seen())
        kept.seen(LATER)
        self.assertEqual(store.moment(LATER), store.Store(self.at).last_seen())

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
             "secret": None, "settings": {"prefix": "!"}, "describes": None, "fills": [],
             "activity": True, "created_at": AT},
            kept.channel("discord"))

    def test_what_a_surface_said_about_itself_is_kept_where_the_surface_is(self):
        """What the adapter said this kind of place is like, and which parts of it it can
        fill in — kept so a `{where.something}` an owner writes later is checked against
        what will actually be there rather than against a guess."""
        kept = self.built()
        kept.remember_channel("rooms", "discord", ["amy"], AT,
                              describes="a room other people read",
                              fills=["channel", "server"])
        self.assertEqual("a room other people read", kept.channel("rooms")["describes"])
        self.assertEqual(["channel", "server"], kept.channel("rooms")["fills"])

    def test_a_surface_is_shown_what_the_agent_is_doing_unless_it_is_told_not_to_be(self):
        """R-CH-6 — on unless an owner says otherwise. A room that goes quiet for four
        minutes and then answers looks broken; a room where that is noise is one where the
        owner says so once, rather than rundesk guessing per message."""
        kept = self.built()
        kept.remember_channel("rooms", "discord", ["amy"], AT)
        self.assertTrue(kept.channel("rooms")["activity"])

        kept.remember_channel("quiet", "discord", ["amy"], AT, activity=False)
        self.assertFalse(kept.channel("quiet")["activity"])
        self.assertTrue(kept.channel("rooms")["activity"], "one surface answered for both")

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

    def test_who_a_surface_allows_is_changed_without_rewriting_the_rest_of_it(self):
        """R-CAD-19 — the people responsible for an agent change over its life, and saying
        so must not throw away its instructions, its settings or what the adapter kept."""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT, instructions="be brief",
                              settings={"prefix": "!"}, describes="a room")
        self.assertEqual(["amy", "zoe"], kept.allow_channel("discord", add=["zoe"]))
        again = kept.channel("discord")
        self.assertEqual(["amy", "zoe"], again["allow"])
        self.assertEqual("be brief", again["instructions"])
        self.assertEqual({"prefix": "!"}, again["settings"])
        self.assertEqual("a room", again["describes"])

    def test_one_person_is_replaced_by_another_under_one_hold(self):
        """R-CAD-19 — asked for as *what to change*, so two owners changing the list at
        once cannot each read the same one and lose the other's half."""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT)
        self.assertEqual(["zoe"],
                         kept.allow_channel("discord", add=["zoe"], remove=["amy"]))
        self.assertEqual(["zoe"], kept.channel("discord")["allow"])

    def test_a_surface_cannot_be_changed_down_to_nobody(self):
        """R-CAD-10, R-CAD-19 — the answer adding one refuses to write, said again at the
        point it would be acted on."""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT)
        with self.assertRaises(ValueError):
            kept.allow_channel("discord", remove=["amy"])
        self.assertEqual(["amy"], kept.channel("discord")["allow"])

    def test_taking_off_somebody_a_surface_never_allowed_is_refused(self):
        """R-CAD-19 — a mistyped id that quietly succeeds leaves the person somebody meant
        to take off still allowed, and says the opposite."""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT)
        with self.assertRaises(ValueError):
            kept.allow_channel("discord", remove=["zoe"])
        self.assertEqual(["amy"], kept.channel("discord")["allow"])

    def test_a_user_id_with_nothing_in_it_allows_and_removes_nobody(self):
        """R-CAD-10, R-CAD-19"""
        kept = self.built()
        kept.remember_channel("discord", "discord", ["amy"], AT)
        for nobody in ("", "   "):
            with self.assertRaises(ValueError):
                kept.allow_channel("discord", add=[nobody])
        self.assertEqual(["amy"], kept.channel("discord")["allow"])

    def test_changing_who_a_surface_that_is_not_there_allows_is_refused(self):
        """R-CAD-19 — never written as a side effect, the way `remember_channel` would."""
        kept = self.built()
        with self.assertRaises(ValueError):
            kept.allow_channel("discord", add=["amy"])
        self.assertEqual([], kept.channels())

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
        kept.remember_schedule("nightly", "0 3 * * *", AT, command=["ls", "-l"])
        kept.remember_schedule("standup", "0 9 * * 1", AT, prompt="how are we",
                               provider="codex", model="gpt-5", instructions="be brief")
        self.assertEqual(["nightly", "standup"], [one["name"] for one in kept.schedules()])
        nightly = kept.schedule("nightly")
        self.assertEqual(["ls", "-l"], nightly["command"])
        self.assertIsNone(nightly["prompt"])
        standup = kept.schedule("standup")
        self.assertEqual("how are we", standup["prompt"])
        self.assertIsNone(standup["command"])
        self.assertEqual("gpt-5", standup["model"])

    def test_a_schedule_states_a_repeating_time_or_one_moment_and_never_both_or_neither(self):
        """R-SCH-36 — said by the records rather than trusted to whoever writes them, the same
        way a program and a prompt already are. Cron has no year, so a single occurrence
        cannot be said in one at all, and a row naming both would leave rundesk choosing."""
        kept = self.built()
        for cron, moment in (("0 3 * * *", "2026-07-28 09:00"), (None, None)):
            with self.assertRaises(ValueError):
                kept.remember_schedule("tidy-up", cron, AT, at=moment, command=["ls"])
        self.assertEqual([], kept.schedules())

        kept.remember_schedule("tidy-up", None, AT, at="2026-07-28 09:00", command=["ls"])
        kept.remember_schedule("nightly", "0 3 * * *", AT, command=["ls"])
        once = kept.schedule("tidy-up")
        self.assertEqual("2026-07-28 09:00", once["at"])
        self.assertIsNone(once["cron"])
        self.assertIsNone(kept.schedule("nightly")["at"])

    def test_the_records_themselves_refuse_a_schedule_saying_when_two_ways(self):
        """The rule above, reached around: whatever writes a row, the shape refuses it. A
        check only the one writer makes is a check that ends the day there are two."""
        kept = self.built()
        with self.assertRaises(sqlite3.IntegrityError):
            self.raw().execute(
                "INSERT INTO schedule (name, cron, at, command, created_at)"
                " VALUES ('tidy-up', '0 3 * * *', '2026-07-28 09:00', '[]', ?)", (AT,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.raw().execute(
                "INSERT INTO schedule (name, command, created_at) VALUES ('tidy-up', '[]', ?)",
                (AT,))
        self.assertEqual([], kept.schedules())

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
)

    def test_the_clock_starting_a_schedule_moves_when_it_last_ran_on_its_own(self):
        self.kept.schedule_fired("nightly", LATER, "started")
        fired = self.kept.schedule("nightly")
        self.assertEqual(LATER, fired["last_auto_run_at"])
        self.assertEqual("started", fired["last_outcome"])

    def test_running_a_schedule_by_hand_leaves_both_of_its_times_where_they_were(self):
        """Only the clock moves these. A hand-run that moved them would push out the next
        automatic firing, so asking for something now would quietly cancel tonight."""
        self.kept.schedule_fired("nightly", AT, "started")
        by_hand = self.a_run(self.kept, source="schedule",
                             schedule_id=self.kept.schedule("nightly")["id"])
        self.kept.recorded(by_hand, 1, LATER, "done", event={"ok": True})
        self.kept.ended(by_hand, LATER, "done", exit_code=0)
        after = self.kept.schedule("nightly")
        self.assertEqual(AT, after["last_auto_run_at"], "a hand-run moved when it last ran")
        self.assertEqual([by_hand],
                         [one["id"] for one in self.kept.runs(schedule_id=after["id"])])

    def test_what_a_schedule_last_did_never_moves_backwards(self):
        """R-SCH-9 — a long run finishing after a later occurrence was already written
        would put the earlier minute back, and a gateway reading it on the way up would
        take that later minute for one that had never fired, and run it again."""
        self.kept.schedule_fired("nightly", LATER, "started")
        self.kept.schedule_fired("nightly", AT, "started")     # an earlier one, finishing late
        self.assertEqual(LATER, self.kept.schedule("nightly")["last_auto_run_at"])

    def test_what_the_work_a_schedule_started_became_leaves_the_minute_alone(self):
        """R-SCH-9 — the minute is the one it *fell due*, and moving it to the moment a
        run finished is how a gateway restarting reads a later minute as the last."""
        self.kept.schedule_fired("nightly", AT, "started")
        self.kept.schedule_became("nightly", "finished")
        after = self.kept.schedule("nightly")
        self.assertEqual((AT, "finished"), (after["last_auto_run_at"], after["last_outcome"]))

    def test_a_name_that_is_already_a_schedules_is_refused_rather_than_replaced(self):
        """The name is claimed by *writing* it, not by asking first and then writing: two
        `schedules add` of one name both found it absent, both reported ADDED, and the second
        silently replaced the first — taking its account of what it last did with it."""
        self.kept.schedule_fired("nightly", AT, "started")
        with self.assertRaises(store.Taken):
            self.kept.remember_schedule("nightly", "0 4 * * *", LATER, command=["ls", "-l"])
        after = self.kept.schedule("nightly")
        self.assertEqual("0 3 * * *", after["cron"], "the schedule that was there was replaced")
        self.assertEqual(AT, after["last_auto_run_at"], "it forgot when it last ran")

    def test_two_writers_claiming_one_name_cannot_both_believe_they_got_it(self):
        """The teeth on the above, and the fault as it actually happened: a check followed by a
        write is two decisions with a gap, and both callers reported success."""
        made = []
        for _ in range(2):
            try:
                self.kept.remember_schedule("once", "0 5 * * *", AT, command=["/bin/true"])
                made.append("claimed")
            except store.Taken:
                made.append("refused")
        self.assertEqual(["claimed", "refused"], made)
        self.assertEqual(1, len([one for one in self.kept.schedules() if one["name"] == "once"]))

    def test_turning_a_schedule_off_and_on_does_not_forget_when_it_last_ran(self):
        """The path a change actually takes now that a name cannot be re-written: it must not
        make the gateway think every firing since the schedule was made has been missed."""
        self.kept.schedule_fired("nightly", AT, "started")
        self.kept.enable_schedule("nightly", False)
        self.kept.enable_schedule("nightly", True)
        after = self.kept.schedule("nightly")
        self.assertEqual(AT, after["last_auto_run_at"])
        self.assertIs(True, after["enabled"])

    def test_a_schedule_reporting_to_a_channel_that_is_not_there_is_refused(self):
        """A reference is what stops a schedule outliving the surface it reported to, and it
        refuses at the moment of writing rather than at three in the morning."""
        with self.assertRaises(store.Refused):
            self.kept.remember_schedule("weekly", "0 9 * * 1", AT, prompt="anything?",
                                        channel="nowhere")
        self.assertEqual([], [one for one in self.kept.schedules() if one["name"] == "weekly"])


class WhenAScheduleIsChanged(WithAnAgentsOwnRecords):
    def setUp(self):
        super().setUp()
        self.kept = self.built()
        self.kept.remember_schedule("nightly", "0 3 * * *", AT, prompt="what changed?",
                                    instructions="be brief", provider="claude")

    def test_only_what_is_named_moves(self):
        """The whole difference between changing a schedule and removing it to add it
        again: everything not named stays exactly as it was, rather than being written back
        from a caller's idea of what the row held."""
        self.assertTrue(self.kept.change_schedule("nightly", prompt="what broke?"))
        after = self.kept.schedule("nightly")
        self.assertEqual("what broke?", after["prompt"])
        self.assertEqual(("0 3 * * *", "be brief", "claude"),
                         (after["cron"], after["instructions"], after["provider"]))

    def test_a_change_keeps_every_record_of_what_the_schedule_has_already_done(self):
        """What removing and adding again destroys, and the reason this exists."""
        self.kept.schedule_fired("nightly", AT, "started")
        self.kept.schedule_became("nightly", "finished")
        made = self.kept.schedule("nightly")["created_at"]
        self.kept.change_schedule("nightly", cron="30 6 * * *")
        after = self.kept.schedule("nightly")
        self.assertEqual((AT, "finished", made),
                         (after["last_auto_run_at"], after["last_outcome"], after["created_at"]))

    def test_setting_one_of_a_pair_clears_the_other(self):
        """Both pairs the table insists on. A row holding a repeating time and a single
        moment is one the database refuses, so a caller stating one is stating that the
        other has gone — the alternative is an integrity error where an owner asked for a
        change."""
        self.kept.change_schedule("nightly", at="2099-01-01 09:00")
        moved = self.kept.schedule("nightly")
        self.assertEqual("2099-01-01 09:00", moved["at"])
        self.assertIsNone(moved["cron"])
        self.kept.change_schedule("nightly", command=["/bin/echo", "hi"])
        became = self.kept.schedule("nightly")
        self.assertEqual(["/bin/echo", "hi"], became["command"])
        self.assertIsNone(became["prompt"])

    def test_nothing_is_given_as_empty_and_left_alone_by_being_absent(self):
        """The two instructions a caller has to be able to tell apart — leave it, and take
        it off — which one default would make one keystroke."""
        self.kept.change_schedule("nightly", instructions="")
        self.assertIsNone(self.kept.schedule("nightly")["instructions"])
        self.kept.change_schedule("nightly", provider="grok")
        self.assertIsNone(self.kept.schedule("nightly")["instructions"],
                          "a field nobody named was written anyway")

    def test_a_change_that_would_leave_neither_of_a_pair_is_refused(self):
        """Checked against the row after the change rather than against what was passed in:
        only that knows which of the two this ends up being."""
        with self.assertRaises(ValueError):
            self.kept.change_schedule("nightly", prompt="")
        self.assertEqual("what changed?", self.kept.schedule("nightly")["prompt"],
                         "the refused change was written anyway")

    def test_a_schedule_that_is_not_there_is_said_rather_than_reported_as_changed(self):
        """Including one taken away between being read and being written: a change that did
        nothing must say so rather than report a success nobody can find afterwards."""
        self.assertFalse(self.kept.change_schedule("gone", prompt="anything?"))

    def test_a_change_naming_a_channel_that_is_not_there_is_refused(self):
        """The same reference that stops a schedule outliving the surface it reports to,
        holding on the way through an edit as well as on the way in."""
        with self.assertRaises(store.Refused):
            self.kept.change_schedule("nightly", channel="nowhere")

    def test_a_column_that_is_not_a_schedules_to_change_is_refused(self):
        """`enabled` has two verbs of its own, and what a schedule has already done is not
        an owner's to rewrite — so neither is reachable from here."""
        for named in ({"enabled": 0}, {"last_outcome": "finished"},
                      {"last_auto_run_at": AT}, {"created_at": AT}):
            with self.assertRaises(ValueError):
                self.kept.change_schedule("nightly", **named)
        # A schedule's name is what its runs are recorded against, so it is not among them
        # either — and it cannot be, being the one thing this is asked by.
        self.assertNotIn("name", store.Store.CHANGEABLE)


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
                               thread="t-1", parent_id="c1")
        self.assertEqual("c2", branched["id"])
        self.assertEqual("c1", branched["parent_id"])
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


class HowWorkCameToBeAdmitted(WithAnAgentsOwnRecords):
    """R-RUN-16 — the only record of how a run came about. Free text until now: `"hand"`
    existed in this suite and in nothing else, which is exactly what a fourth word arriving
    by typo looks like from outside. A word nothing can read back is a run whose origin is
    lost, and this is the column somebody reads at three in the morning to find out whether
    they asked for what happened."""

    def test_every_way_work_is_admitted_is_named_here(self):
        """R-RUN-16 — three, because there are three things that start work: somebody at a
        terminal, somebody on a surface the agent is reachable on, and the clock."""
        kept = self.built()
        for source in store.SOURCES:
            with self.subTest(source=source):
                run = self.a_run(kept, source=source)
                self.assertEqual(source, kept.run(run)["source"])

    def test_work_admitted_from_somewhere_nobody_declared_is_refused(self):
        """R-RUN-16 — refused where an author and a record kind already are, so the set is
        one thing to keep true rather than a convention nothing enforces."""
        kept = self.built()
        for said in ("hand", "cron", "", None, "Terminal"):
            with self.subTest(source=said):
                with self.assertRaises(ValueError, msg=f"admitted {said!r}"):
                    self.a_run(kept, source=said)

    def test_a_run_refused_for_its_source_is_not_written_at_all(self):
        """R-RUN-16 — refused before the transaction, so a rejected admission does not
        consume a run number that then has a hole where it should be."""
        kept = self.built()
        first = self.a_run(kept)
        with self.assertRaises(ValueError):
            self.a_run(kept, source="nowhere")
        second = self.a_run(kept)
        self.assertEqual([1, 2], sorted(one["n"] for one in kept.runs(limit=50)))
        self.assertNotEqual(first, second)


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
        named = kept.began("channel", "/opt/my-brain", "safe", AT,
                           conversation_id="c1", trigger_message_id=said, model="gpt-5",
                           can={"steer": True}, settings={"effort": "high"}, resumed=True,
                           pick=lambda _: "a")
        self.assertEqual(
            {"n": 1, "id": named, "conversation_id": "c1", "schedule_id": None,
             "source": "channel", "trigger_message_id": said,
             "provider": "/opt/my-brain", "model": "gpt-5", "posture": "safe",
             "can": {"steer": True}, "settings": {"effort": "high"}, "resumed": True,
             "started_at": AT, "ended_at": None, "outcome": None, "why": None,
             "exit_code": None, "tokens_in": None, "tokens_out": None,
             "tokens_cached": None, "tokens_written": None, "tokens_reported": False,
             "because": None, "role_run": None},
            kept.run(named))
        self.assertEqual([named], [one["id"] for one in kept.runs(conversation_id="c1")])
        self.assertIsNone(kept.run("404-zzzz"))

    def test_how_a_run_finished_and_what_it_cost_is_written_at_the_end(self):
        kept = self.built()
        named = self.a_run(kept)
        kept.ended(named, LATER, "done", exit_code=0,
                   tokens={"input": 120, "output": 30, "cached": 10, "reported": True})
        finished = kept.run(named)
        self.assertEqual(LATER, finished["ended_at"])
        self.assertEqual("done", finished["outcome"])
        self.assertEqual(0, finished["exit_code"])
        self.assertEqual((120, 30, 10),
                         (finished["tokens_in"], finished["tokens_out"],
                          finished["tokens_cached"]))
        self.assertTrue(finished["tokens_reported"])

    def test_a_run_that_failed_says_why_beside_the_run_and_not_only_in_a_file(self):
        """The one actionable line, kept where the run is read. A run that never reached a
        brain printed nothing at all, so a reason filed only in what the brain printed is a
        reason nobody has — which is exactly the run somebody is stuck on."""
        kept = self.built()
        named = self.a_run(kept)
        kept.ended(named, LATER, "failed", exit_code=1,
                   why="unexpected status 401 Unauthorized")
        self.assertEqual("unexpected status 401 Unauthorized", kept.run(named)["why"])
        self.assertEqual([], kept.records(named), "nothing was printed, and why survives")

    def test_an_interrupted_channel_turn_is_claimed_for_recovery_once(self):
        """R-GW-22 — two successor starts cannot continue one interrupted turn twice."""
        kept = self.built()
        kept.opened("c1", "ops", "somewhere", "one", AT)
        asked = kept.arrived("c1", AT, "finish the release", who="2207")
        named = kept.began(
            "channel", "a-brain", "safe", AT, conversation_id="c1",
            trigger_message_id=asked, settings={"effort": "high"}, pick=lambda _: "a",
        )
        kept.interrupted(named, LATER, "the gateway stopped", recoverable=True)

        found = kept.recoverable("ops")
        self.assertEqual([named], [one["id"] for one in found])
        self.assertEqual(("one", "2207", {"effort": "high"}),
                         (found[0]["conversation"], found[0]["user"], found[0]["settings"]))
        self.assertTrue(kept.claim_recovery(named, LATER))
        self.assertFalse(kept.claim_recovery(named, LATER),
                         "a second successor claimed the same interrupted turn")
        self.assertEqual([], kept.recoverable("ops"))

    def test_an_explicitly_stopped_turn_is_not_offered_for_recovery(self):
        """R-GW-22 — only gateway loss is continued; a person's stop remains stopped."""
        kept = self.built()
        kept.opened("c1", "ops", "somewhere", "one", AT)
        asked = kept.arrived("c1", AT, "stop here", who="2207")
        named = kept.began(
            "channel", "a-brain", "safe", AT, conversation_id="c1",
            trigger_message_id=asked, pick=lambda _: "a",
        )
        kept.interrupted(named, LATER, "stopped by the person", recoverable=False)
        self.assertEqual([], kept.recoverable("ops"))

    def test_a_run_that_finished_well_says_nothing_about_why(self):
        """Absent rather than empty, so `why` reads as a reason and never as a field."""
        kept = self.built()
        named = self.a_run(kept)
        kept.ended(named, LATER, "done", exit_code=0)
        self.assertIsNone(kept.run(named)["why"])

    def test_a_run_whose_cost_never_arrived_is_left_absent_rather_than_written_as_nothing(self):
        """A run that cost an unknown amount and one that cost zero are different facts,
        and writing the first as the second is the way a total starts lying."""
        kept = self.built()
        named = self.a_run(kept)
        kept.ended(named, LATER, "lost", exit_code=1)
        silent = kept.run(named)
        for column in ("tokens_in", "tokens_out", "tokens_cached"):
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
        self.assertEqual([None] * 3, [nothing_yet[word] for word
                                      in ("input", "output", "cached")])
        silent = self.a_run(kept)
        kept.ended(silent, LATER, "done")
        told = self.a_run(kept)
        kept.ended(told, LATER, "done",
                   tokens={"input": 120, "output": 30, "cached": 10, "reported": True})
        # `written` totals 0 rather than being absent: neither run reported the split, and
        # a SUM over rows that all said nothing is a floor of nothing. What must not become
        # zero is the *per-run* value, which stays NULL — see test_migration.
        self.assertEqual({"runs": 2, "reported": 1, "unreported": 1, "input": 120,
                          "output": 30, "cached": 10, "written": 0}, kept.usage())

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



class WhatWasSaid(WithAnAgentsOwnRecords):
    def setUp(self):
        super().setUp()
        self.kept = self.built()
        self.kept.opened("c1", "discord", "discord", "general", AT)

    def test_a_conversation_is_read_back_in_the_order_it_happened(self):
        named = self.a_run(self.kept, conversation_id="c1")
        self.kept.arrived("c1", AT, "how are we", who="u-1", external_id="d-1")
        self.kept.answered("c1", named, LATER, "we are well", external_id="d-2")
        self.kept.arrived("c1", LATER, "good", who="u-1")
        said = self.kept.messages("c1")
        self.assertEqual(["how are we", "we are well", "good"],
                         [one["text"] for one in said])
        self.assertEqual(["user", "agent", "user"], [one["author"] for one in said])
        self.assertEqual("u-1", said[0]["who"])
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
        self.assertEqual({"user", "agent"}, {one["author"] for one in found})
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
        # What is left is the log, which is not a record and is not this call's to take —
        # building the records wrote a line saying so, and that outlives them on purpose.
        self.assertEqual(["logs"], sorted(one.name for one in self.where.iterdir()))
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

        self.assertEqual(store.moment(LATER), theirs.last_seen())
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
        # Nothing but the database's own files is left. Which of the three are actually there
        # is not ours to say: the two beside it exist only while a connection is open or after
        # one closed badly, so a case demanding all three passes on one Python and fails on
        # the next. What matters is that nothing else survived.
        left = sorted(one.name for one in self.where.iterdir())
        self.assertEqual([], [one for one in left
                              if one not in {x.name for x in store.removes(self.where)}])
        self.assertIn(store.NAME, left)

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
        self.assertEqual([("user", "what about the parser"),
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


class WhatTheAgentsOwnLogSays(WithAnAgentsOwnRecords):
    """When this agent is wrong, its own log is where somebody looks — so it has to say why.

    Not a diary of every read and write: a log nobody can skim is a log nobody reads. What is
    written down is what an owner would need to explain a failure — a refusal, a write that
    gave up, a machine that cannot do what was asked of it.
    """

    WHEN = "2026-07-26 03:00:00"

    def told(self) -> str:
        at = self.where / migration.LOG
        return at.read_text() if at.exists() else ""

    def test_records_this_rundesk_will_not_read_say_why_in_the_log(self):
        self.built()
        arranged = self.raw()
        arranged.execute(f"PRAGMA user_version = {store.VERSION + 1}")
        arranged.close()
        with self.assertRaises(store.TooNew):
            store.Store(self.at, clock=lambda: self.WHEN).made()
        self.assertIn("ERROR", self.told())
        self.assertIn(f"they are version {store.VERSION + 1}", self.told())
        self.assertIn(self.WHEN, self.told())

    def test_records_not_yet_brought_forward_say_so_in_the_log(self):
        self.built()
        with self.assertRaises(store.Behind):
            store.Store(self.at, version=store.VERSION + 1, clock=lambda: self.WHEN).made()
        self.assertIn("have not been brought forward", self.told())

    def test_records_that_cannot_be_understood_say_so_in_the_log(self):
        self.built()
        arranged = self.raw()
        for table in ("record", "message", "run", "session", "conversation",
                      "schedule", "channel", "gateway", "agent"):
            arranged.execute(f"DROP TABLE IF EXISTS {table}")
        arranged.close()
        with self.assertRaises(store.Unreadable):
            store.Store(self.at, clock=lambda: self.WHEN).made()
        self.assertIn("hold none of it", self.told())
        self.assertIn("ERROR", self.told())

    def test_a_write_that_gave_up_waiting_says_what_was_holding_it(self):
        """A turn that could not record what it did is the worst kind of silence."""
        self.impatient()
        kept = self.built(wait=lambda seconds: None, clock=lambda: self.WHEN)
        held = self.raw()
        held.execute("BEGIN IMMEDIATE")
        held.execute("UPDATE gateway SET last_seen_at = 'held' WHERE id = 1")
        with self.assertRaises(sqlite3.OperationalError):
            kept.seen(AT)
        held.execute("ROLLBACK")
        held.close()
        self.assertIn("gave up waiting to write", self.told())
        self.assertIn("ERROR", self.told())

    def test_a_machine_that_cannot_search_says_so_once_rather_than_every_time(self):
        kept = self.built(clock=lambda: self.WHEN)
        arranged = self.raw()
        for gone in ("message_fts_insert", "message_fts_delete", "message_fts_update"):
            arranged.execute(f"DROP TRIGGER {gone}")
        arranged.execute("DROP TABLE message_fts")
        arranged.close()
        kept._searchable = None
        for _ in range(3):
            with self.assertRaises(store.Unsearchable):
                kept.search("parser")
        self.assertEqual(1, self.told().count("cannot search"),
                         "the same complaint was written down every time it was asked")

    def test_an_ordinary_read_and_write_says_nothing_at_all(self):
        """The reason any of the above is findable. A log full of what went right is a log
        somebody stops opening, and then the one line that mattered is not read either."""
        kept = self.built(clock=lambda: self.WHEN)
        before = self.told()
        kept.remember_agent(provider="codex")
        kept.remember_channel("ops", "discord", ["u1"], AT)
        kept.opened("c1", "ops", "thread", "99123", AT, thread="4456")
        kept.arrived("c1", AT, "anything at all")
        named = self.a_run(kept, conversation_id="c1")
        kept.recorded(named, 1, AT, "done", event={"ok": True})
        kept.ended(named, LATER, "finished")
        kept.channels(), kept.runs(), kept.messages("c1"), kept.usage()
        self.assertEqual(before, self.told(), "an ordinary turn wrote to the log")



class WhenAGatewayWasLastUpIsAMomentNotAString(WithAnAgentsOwnRecords):
    """R-SCH-15 — whoever asks this is comparing it against a clock stated in local time, and
    what is kept is UTC. Handing back the string made the caller decode this module's own format
    to do that, which is the caller knowing what holds its records — `gateway.py` had to import
    `store` for it, crossing the one dependency direction the project has ratified."""

    def test_it_comes_back_as_a_moment_that_says_which_clock_it_is_on(self):
        """R-SCH-15 — aware, so the two clock faces cannot be compared without converting: an
        error invisible for most of the year and wrong by an hour for the rest of it."""
        kept = self.built()
        kept.seen(AT)
        when = kept.last_seen()
        self.assertEqual(store.moment(AT), when)
        self.assertIsNotNone(when.tzinfo, "it came back not saying which clock it is on")

    def test_a_gateway_that_was_never_up_is_nothing_rather_than_a_guess(self):
        """R-SCH-5 — there is nothing to measure a gap against, and saying so is the answer."""
        self.assertIsNone(self.built().last_seen())


class HowWorkIsAdmittedIsSpelledOneWay(unittest.TestCase):
    """R-RUN-16 — `store.began` refuses a word that is not one of `SOURCES`, and `turn.py`
    names all three so a caller has something to pass. Two spellings of one set is two too
    many: they would agree until one of them did not, and the way that fails is a turn refused
    at the moment it is admitted — the one place a refusal costs the work."""

    def test_the_words_a_turn_names_are_the_words_the_records_declare(self):
        """R-RUN-16 — asked of both rather than written down here, so a fourth one added to
        either side has to be added to the other in the same commit."""
        from rundesk import turn

        self.assertEqual(
            set(store.SOURCES),
            {turn.TERMINAL, turn.CHANNEL, turn.SCHEDULE, turn.ROLE},
        )


class TheOnlyWayIn(unittest.TestCase):
    """Nothing outside this module knows a database is there.

    The same rule the provider and channel seams hold to, where here the vendor is the
    database. Proved by looking rather than by intention: a sibling project confined every
    statement to four modules and still leaked, because one of them exposed its connection
    and six call sites reached through it. Every one began as a single read.
    """

    SOURCE = Path(__file__).resolve().parent.parent / "src" / "rundesk"

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

    #: How a module in this package actually reaches another one. The case this replaced
    #: looked for `from store import` and a line beginning `import`, and nothing here is
    #: written either way — so it passed for a phase after the thing it guarded was over.
    IMPORTS = re.compile(r"^\s*(?:from\s+rundesk\s+import\s+[^\n]*\bstore\b"
                         r"|from\s+rundesk\.store\s+import\b"
                         r"|import\s+rundesk\.store\b)", re.MULTILINE)

    def test_the_product_reaches_what_an_agent_keeps(self):
        """The opposite of what this case used to assert, and deliberately.

        While nothing read the store, deleting it left the product exactly as it was — which
        is what made building it before moving onto it safe. That is over: an agent is made
        with its records and taken away with them, so a store nothing reached would now be an
        agent with nowhere to keep anything.
        """
        reaching = [path.name for path in self.elsewhere()
                    if self.IMPORTS.search(path.read_text())]
        self.assertIn("agent.py", reaching, "an agent is made with nowhere to keep anything")

    def test_only_the_seam_is_reached_for_a_connection(self):
        """Reaching the store is not the same as reaching a database. Everything above asks
        for what it wants by name, and the two files that may open one are named."""
        opening = [path.name for path in self.elsewhere()
                   if re.search(r"^\s*(?:import\s+sqlite3|from\s+sqlite3\s+import)",
                                path.read_text(), re.MULTILINE)]
        self.assertEqual([], opening)


class TakingAScheduleAway(WithAnAgentsOwnRecords):
    """R-SCH-35 — a schedule that has run is still one an owner can be rid of."""

    def test_a_schedule_that_has_run_can_still_be_taken_away(self):
        """The clock reaching a schedule must not make it permanent. There is no verb that
        edits one, so a schedule that could not be removed could never be changed either —
        an owner wanting a report an hour later would have to take the whole agent away."""
        kept = self.built()
        kept.remember_schedule("nightly", "0 3 * * *", AT, prompt="what changed?")
        row = kept.schedule("nightly")
        kept.began("schedule", "codex", "safe", AT, schedule_id=row["id"])
        kept.forget_schedule("nightly")
        self.assertIsNone(kept.schedule("nightly"))

    def test_a_run_outlives_the_schedule_that_started_it(self):
        """What it cost: which schedule is lost, and that it was one is not. A listing still
        tells an owner the clock started it rather than a person."""
        kept = self.built()
        kept.remember_schedule("nightly", "0 3 * * *", AT, prompt="what changed?")
        row = kept.schedule("nightly")
        named = kept.began("schedule", "codex", "safe", AT, schedule_id=row["id"])
        kept.forget_schedule("nightly")
        ran = kept.run(named)
        self.assertIsNotNone(ran, "the run went with the schedule")
        self.assertEqual("schedule", ran["source"])
        self.assertIsNone(ran["schedule_id"])


class ReadingBackWhatWasSaid(WithAnAgentsOwnRecords):
    """R-STO-25, R-STO-26 — the listing an agent reads about itself.

    Searching needs a word, and the case this exists for is the one where nobody gave you
    one: "nice work" about a turn that ran in another conversation entirely.
    """

    def furnished(self):
        """Two surfaces, four messages, and a run under each — enough to narrow."""
        kept = self.built()
        kept.opened("c-term", "terminal", "terminal", "terminal", AT)
        kept.opened("c-ops", "ops", "room", "general", AT)
        said = {}
        said["asked"] = kept.arrived("c-term", AT, "look at the parser")
        named = kept.began("terminal", "codex", "safe", AT, conversation_id="c-term",
                           trigger_message_id=said["asked"])
        said["answered"] = kept.answered("c-term", named, AT, "three issues found")
        said["nightly"] = kept.arrived("c-ops", LATER, "nice work!", who="U1")
        by_clock = kept.began("schedule", "codex", "safe", LATER, conversation_id="c-ops")
        said["clock"] = kept.answered("c-ops", by_clock, LATER, "the nightly review ran")
        return kept, said

    def test_what_was_said_reads_back_newest_first(self):
        """Newest first, because the question is "what has just happened" — a listing that
        began at the beginning would make an agent page through its whole life to answer it."""
        kept, said = self.furnished()
        found = kept.latest()
        self.assertEqual([one["id"] for one in found],
                         sorted((one["id"] for one in found), reverse=True))
        self.assertEqual(said["clock"], found[0]["id"])

    def test_what_was_said_on_every_surface_reads_back_together(self):
        """Where something was said is not how anybody looks for it. One listing spans the
        terminal and a room, and says which each was."""
        kept, _ = self.furnished()
        found = kept.latest()
        self.assertEqual({"terminal", "ops"}, {one["channel"] for one in found})
        self.assertEqual(4, len(found))

    def test_only_what_was_said_after_a_given_one_is_read_back(self):
        """A cursor rather than an offset: `id` is `AUTOINCREMENT`, so it stays put while new
        messages land beside it, which is what makes "what is new since I looked" answerable."""
        kept, said = self.furnished()
        found = kept.latest(since=said["answered"])
        self.assertEqual([said["clock"], said["nightly"]], [one["id"] for one in found])

    def test_what_a_listing_shows_can_be_narrowed_to_one_channel(self):
        kept, said = self.furnished()
        found = kept.latest(channel="ops")
        self.assertEqual([said["clock"], said["nightly"]], [one["id"] for one in found])

    def test_what_a_listing_shows_can_be_narrowed_to_one_kind_of_author(self):
        kept, said = self.furnished()
        found = kept.latest(author="user")
        self.assertEqual([said["nightly"], said["asked"]], [one["id"] for one in found])

    def test_what_a_listing_shows_can_be_narrowed_to_how_the_work_was_admitted(self):
        """The one an agent actually reaches for: what did the clock do, as against what a
        person asked me. It reaches a run two ways — an answer carries `run_id`, and what a
        person said is what a run points back at — so both sides of a turn are found."""
        kept, said = self.furnished()
        self.assertEqual([said["clock"]], [one["id"] for one in kept.latest(source="schedule")])
        self.assertEqual([said["answered"], said["asked"]],
                         [one["id"] for one in kept.latest(source="terminal")])

    def test_what_a_listing_shows_can_be_narrowed_to_one_place_on_a_surface(self):
        """Two direct messages are two conversations on one channel, and an agent standing in
        one of them wants that one. Narrowing by the channel would hand it both."""
        kept = self.built()
        kept.opened("dm-tim", "dms", "dms", "482910337", AT)
        kept.opened("dm-sam", "dms", "dms", "913774028", AT)
        tim = kept.arrived("dm-tim", AT, "nice work!", who="tim")
        kept.arrived("dm-sam", LATER, "did you finish?", who="sam")
        found = kept.latest(conversation="482910337")
        self.assertEqual([tim], [one["id"] for one in found])
        self.assertEqual(["tim"], [one["who"] for one in found])

    def test_a_place_is_narrowed_to_by_the_name_the_listing_prints_for_it(self):
        """R-STO-28 — reported (#103): the `WHERE` column prints `<channel>/<space>` and the
        filter matched the bare space alone, so the one identifier an agent can see and copy
        back matched nothing at all — and the empty listing that came back reads as "this
        conversation is empty", which is the single wrong answer `messages` exists to stop."""
        kept = self.built()
        kept.opened("dm-tim", "discord-dms", "dms", "482910337", AT)
        kept.opened("dm-sam", "discord-dms", "dms", "913774028", AT)
        tim = kept.arrived("dm-tim", AT, "nice work!", who="tim")
        kept.arrived("dm-sam", LATER, "did you finish?", who="sam")
        printed = kept.latest(conversation="482910337")[0]
        qualified = f"{printed['channel']}/{printed['space']}"
        self.assertEqual([tim], [one["id"] for one in kept.latest(conversation=qualified)],
                         "the identifier the listing prints is not the one its filter takes")

    def test_a_place_named_on_the_wrong_channel_is_not_narrowed_to(self):
        """The qualified form is both halves or it is worth nothing: a space id that exists on
        one channel must not answer for a channel it was never on."""
        kept = self.built()
        kept.opened("dm-tim", "discord-dms", "dms", "482910337", AT)
        kept.arrived("dm-tim", AT, "nice work!", who="tim")
        self.assertEqual([], kept.latest(conversation="discord-rooms/482910337"))

    def test_a_place_whose_own_name_holds_a_slash_is_still_narrowed_to(self):
        """A platform's own word for a place is the platform's own. Splitting the qualified
        form on the last slash must not stop a bare value that contains one from matching."""
        kept = self.built()
        kept.opened("c-repo", "github", "room", "rundesk-ai/rundesk-cli", AT)
        said = kept.arrived("c-repo", AT, "the gate is green")
        self.assertEqual([said],
                         [one["id"] for one in kept.latest(conversation="rundesk-ai/rundesk-cli")])

    def test_a_place_that_exists_is_told_apart_from_one_that_does_not(self):
        """R-STO-28 — "there is no such conversation" and "that conversation is empty" send a
        reader somewhere completely different, and one empty list answered both."""
        kept = self.built()
        kept.opened("dm-tim", "discord-dms", "dms", "482910337", AT)
        self.assertTrue(kept.has_conversation("482910337"))
        self.assertTrue(kept.has_conversation("discord-dms/482910337"))
        self.assertFalse(kept.has_conversation("no-such-place"))
        self.assertFalse(kept.has_conversation("discord-rooms/482910337"))

    def test_two_people_on_one_channel_are_kept_apart_by_where_they_said_it(self):
        """The column an agent reads to know who it is talking to. Both are `user`, and what
        tells them apart is the place and the name their surface gave."""
        kept = self.built()
        kept.opened("dm-tim", "dms", "dms", "482910337", AT)
        kept.opened("dm-sam", "dms", "dms", "913774028", AT)
        kept.arrived("dm-tim", AT, "nice work!", who="tim")
        kept.arrived("dm-sam", LATER, "did you finish?", who="sam")
        found = kept.latest(channel="dms")
        self.assertEqual({"tim", "sam"}, {one["who"] for one in found})
        self.assertEqual({"user"}, {one["author"] for one in found})
        self.assertEqual(2, len({one["space"] for one in found}))

    def test_what_a_listing_shows_can_be_narrowed_to_one_person(self):
        """R-STO-27 — reported (#106): `--author` filters on author *kind* while the WHO
        column shows identity, so `--author user` returned rows displaying a platform id
        and neither could answer "what did this one person say". Kind and identity are two
        questions, and each now has its own way of being asked."""
        kept = self.built()
        kept.opened("room", "rooms", "rooms", "88213", AT)
        tim = kept.arrived("room", AT, "ship it", who="tim")
        kept.arrived("room", LATER, "not yet", who="sam")
        kept.arrived("room", LATER, "standing instructions", author="rundesk")
        found = kept.latest(who="tim")
        self.assertEqual([tim], [one["id"] for one in found])
        self.assertEqual(["user"], [one["author"] for one in found],
                         "narrowing by identity changed what kind of author came back")

    def test_narrowing_by_a_person_nobody_has_been_is_empty_rather_than_refused(self):
        """Unlike `author` and `source`, this is not a closed set: it is whatever a surface
        calls one person. Refusing an unknown one would mean keeping a list of everyone who
        has ever spoken to this agent, and an id nobody has matching nothing is a true
        answer to a question with no rows in it."""
        kept, _ = self.furnished()
        self.assertEqual([], kept.latest(who="nobody-by-that-name"))

    def test_a_narrowing_that_matches_nothing_is_empty_rather_than_everything(self):
        """The edge that turns a filter into a lie. A place nobody has spoken in must not
        fall back to the whole listing, which is how a scoped question answers a broad one."""
        kept, _ = self.furnished()
        self.assertEqual([], kept.latest(conversation="no-such-place"))
        self.assertEqual([], kept.latest(channel="no-such-channel"))
        self.assertEqual([], kept.latest(since=10_000))

    def test_narrowings_asked_together_all_hold_rather_than_the_last_one_winning(self):
        """Four filters at once, and each one still applies — a listing that quietly dropped
        all but the last would answer a question nobody asked."""
        kept, said = self.furnished()
        self.assertEqual(
            [said["asked"]],
            [one["id"] for one in kept.latest(channel="terminal", author="user",
                                              source="terminal", conversation="terminal")])

    def test_a_narrowing_by_an_author_nobody_could_be_is_refused(self):
        """Refused rather than ignored. A filter nobody can spell that is quietly dropped is
        a listing answering a different question than the one it was asked."""
        kept, _ = self.furnished()
        with self.assertRaises(ValueError):
            kept.latest(author="everyone")

    def test_a_narrowing_by_a_source_nothing_is_admitted_from_is_refused(self):
        kept, _ = self.furnished()
        with self.assertRaises(ValueError):
            kept.latest(source="hand")


if __name__ == "__main__":
    unittest.main(verbosity=2)
