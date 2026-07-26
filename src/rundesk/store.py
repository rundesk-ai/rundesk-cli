"""Everything one agent keeps, and the only way in to it.

One database per agent, never one shared: nothing is shared between two gateways, which is
what makes one restartable without disturbing the rest (see `gateway.Gateway`). A shared
database would put one agent's write lock in another's way and make one corrupt file
everybody's problem.

**A caller asks for what it wants by name.** No SQL exists outside this module and no
connection ever leaves it — the same rule the provider and channel seams already hold to,
where here the vendor is the database. A question asked in two places is asked through one
name, so when a column moves, what breaks is this file and it breaks visibly.

**Reading and writing are told apart at the connection.** A reader is opened read-only, so
it cannot begin a transaction that would make a turn wait — not by convention but because
the database refuses it. A writer takes its lock at `BEGIN IMMEDIATE` rather than at commit,
so contention surfaces at the start of an operation instead of at the end of one.

What is *not* here, and deliberately: what a brain printed and what it said went wrong stay
files, because `RUNDESK_RAW` is a path handed to a program that may be a shell script and
stderr is a pipe the operating system gives us. Those files may be destroyed to reclaim
space, so **nothing a run recorded is recoverable only from them** — every line an adapter
produced is a row here, understood or not.

Nothing in the product reads this module yet. It is built and proved first, and moved onto
second, so that what moves has somewhere already known to work.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import sqlite3
import time
from pathlib import Path

from rundesk import migration


def version_wanted() -> int:
    """The shape this code understands: how many steps forward there are to have taken.

    Read off the steps rather than written down beside them, so the number and the steps
    cannot disagree. Adding a migration is the whole of raising it.
    """
    steps = migration.found()
    return steps[-1].version if steps else 0


VERSION = version_wanted()

NAME = "state.db"

# Short, because waiting is handled here with jitter rather than inside SQLite. Its own busy
# handler backs off on a near-deterministic schedule, so concurrent writers re-collide in
# lockstep; a random wait breaks the convoy.
BUSY_SECONDS = 5.0
TRIES = 5
WAIT_LEAST = 0.02
WAIT_MOST = 0.15

# What a run is called. The number is the database's and is never reused; the tail is what
# keeps two agents' run names from looking interchangeable when they are read side by side.
MARK_FROM = "abcdefghijklmnopqrstuvwxyz0123456789"
MARK_LENGTH = 4

RECORD_KINDS = ("think", "tool", "result", "usage", "file", "done", "lost", "unknown")
AUTHORS = ("person", "agent", "rundesk")


class Unreadable(Exception):
    """There is something there and it could not be understood. Never treated as empty."""


class TooNew(Exception):
    """Written by a later rundesk than this one. Refused rather than read hopefully."""

    def __init__(self, found: int, understood: int):
        super().__init__(
            f"this data is version {found} and this rundesk understands {understood} — "
            "a newer version is refused rather than read"
        )
        self.found = found
        self.understood = understood


class Behind(Exception):
    """Written by an earlier rundesk, and not yet brought forward.

    Refused as firmly as a newer one, and for the same reason: reading an older shape as
    though it were this one is reading a partial truth and then writing over the rest. What
    resolves this is a migration, which runs while nothing is up — never a reader deciding
    on its own that the difference probably does not matter.
    """

    def __init__(self, found: int, understood: int):
        super().__init__(
            f"this data is version {found} and this rundesk expects {understood} — "
            "it has not been brought forward yet"
        )
        self.found = found
        self.understood = understood


class Unsearchable(Exception):
    """This machine's SQLite was built without FTS5. Said out loud, never returned as none."""


def path_for(directory) -> Path:
    """Where an agent's records stand, given the directory everything of its own is under."""
    return Path(directory) / NAME


def _plain(row) -> dict:
    """A row as an ordinary mapping. Nothing of the database's leaves this module."""
    return {key: row[key] for key in row.keys()}


def _marked(pick=None) -> str:
    chose = random.choice if pick is None else pick
    return "".join(chose(MARK_FROM) for _ in range(MARK_LENGTH))


def _statements(script: str):
    """Split a script the way SQLite itself would, and never on the semicolons.

    A trigger body holds `BEGIN … END;` with semicolons inside it, so splitting on `;` cuts
    one statement into three that none of them parse. `complete_statement` is the same test
    the shell uses to decide a statement has ended, so a trigger survives it intact.
    """
    gathered = ""
    for line in script.splitlines(keepends=True):
        gathered += line
        if sqlite3.complete_statement(gathered):
            said = gathered.strip()
            if said and not said.startswith("--"):
                yield said
            gathered = ""
    if gathered.strip():
        raise ValueError(f"a statement was never finished: {gathered.strip()[:60]}…")


def _fts5(conn) -> bool:
    """Whether this machine's SQLite can search at all — asked by trying it, not by version."""
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.probing_fts5 USING fts5(x)")
    except sqlite3.OperationalError:
        return False
    conn.execute("DROP TABLE temp.probing_fts5")
    return True


def _journal(conn) -> str:
    """Ask for WAL, and take what the machine gives.

    WAL is what lets a reader carry on while a turn is writing. It is refused on some network
    filesystems, where the answer is an error rather than a slower mode — so the fallback is
    explicit and the mode actually in force is reported rather than assumed.
    """
    try:
        got = conn.execute("PRAGMA journal_mode=WAL").fetchone()
    except sqlite3.OperationalError:
        return str(conn.execute("PRAGMA journal_mode").fetchone()[0])
    return str(got[0])


class Store:
    """One agent's records, and every question anybody may ask of them.

    Built with a path and nothing else, so a test gives it a temporary directory and no
    gateway, no agent and no process is anywhere near it.
    """

    def __init__(self, at, wait=None, version=None, clock=None):
        self.at = Path(at)
        self._clock = clock
        # Which shape this is expected to be. Left unresolved here and asked for in the body
        # of `made`, so it is read off the steps that actually ship at the moment it matters —
        # rather than frozen when this file was first imported, which would leave every caller
        # sharing one mutable number and every test having to put it back.
        self._version = version
        # Resolved in the body rather than bound as a default, so a test can shorten the wait
        # without the value having been fixed when this file was first read.
        self._wait = time.sleep if wait is None else wait
        self._searchable = None
        self._grumbled = set()

    def _noted(self, line: str, level: str = "INFO") -> None:
        """Into the agent's own log, which is where somebody looks when this agent is wrong.

        Only what an owner would need to explain a failure: a refusal, a write that gave up, a
        machine that cannot do what was asked of it. Never an ordinary read or write — a log
        nobody can skim is a log nobody reads.
        """
        migration.logged(self.at.parent, line, level, clock=self._clock)

    def _once(self, key: str, line: str, level: str) -> None:
        """Said the first time it is true, and not on every call afterwards."""
        if key not in self._grumbled:
            self._grumbled.add(key)
            self._noted(line, level)

    # ── opening ───────────────────────────────────────────────────────────────────────────

    def _open(self, writing: bool):
        if writing:
            conn = sqlite3.connect(str(self.at), timeout=BUSY_SECONDS, isolation_level=None)
        else:
            # Read-only at the connection, so a reader *cannot* begin a transaction that
            # would make a writer wait. A rule the database enforces beats one a reviewer has
            # to notice.
            conn = sqlite3.connect(
                f"file:{self.at}?mode=ro", uri=True, timeout=BUSY_SECONDS, isolation_level=None
            )
        conn.row_factory = sqlite3.Row
        if writing:
            mode = _journal(conn)
            if mode.lower() != "wal":
                self._once("journal", f"this machine would not keep these records in wal — "
                                      f"it is using {mode}, so a reader waits on a writer",
                           "WARNING")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextlib.contextmanager
    def _reading(self):
        """A read. No transaction is ever begun, and the connection is always closed.

        `with conn:` commits and rolls back — it does **not** close. A connection left to the
        garbage collector keeps its read lock on newer Pythons and not on the oldest, so a
        leak is invisible on the version CI pins and an error on the machine you are using.
        """
        conn = self._open(writing=False)
        try:
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def _writing(self):
        """One write, alone and whole.

        `BEGIN IMMEDIATE` takes the write lock at the start rather than at commit, so two
        writers find out about each other before either has done its work. The retry is on
        the boundary statements only — both are safe to issue again, and nothing in the body
        is ever replayed.
        """
        conn = self._open(writing=True)
        try:
            self._boundary(conn, "BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                with contextlib.suppress(sqlite3.OperationalError):
                    conn.execute("ROLLBACK")
                raise
            self._boundary(conn, "COMMIT")
        finally:
            conn.close()

    def _boundary(self, conn, statement: str) -> None:
        for attempt in range(TRIES):
            try:
                conn.execute(statement)
                return
            except sqlite3.OperationalError as trouble:
                said = str(trouble).lower()
                if "locked" not in said and "busy" not in said:
                    raise
                if attempt == TRIES - 1:
                    self._noted(f"gave up waiting to write after {TRIES} tries — something "
                               f"else is holding these records: {trouble}", "ERROR")
                    raise
                self._wait(random.uniform(WAIT_LEAST, WAIT_MOST))

    # ── the shape on disk ─────────────────────────────────────────────────────────────────

    def made(self) -> None:
        """Bring this database into being, or check the one already there is one we know.

        A fresh one is stamped with the current version and needs no migration, so first use
        and an upgrade converge on the same shape.
        """
        want = version_wanted() if self._version is None else self._version
        self.at.parent.mkdir(parents=True, exist_ok=True)
        conn = self._open(writing=True)
        try:
            found = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if found == 0 and not self._anything(conn):
                conn.close()
                conn = None
                # Built by walking the same steps an update walks, rather than by a second
                # description of the shape kept beside them. A step that has rotted is then
                # found by whoever next makes an agent, and a fresh install cannot drift from
                # an upgraded one, because there is only one way to arrive.
                found = migration.carry(self.at, self.at.parent, want=want)
                conn = self._open(writing=True)
            self._refused(conn, found, want)
            self._searchable = self._has_search(conn)
        finally:
            if conn is not None:
                conn.close()

    def understood(self) -> None:
        """Check the records already there are ones we know, and never build any.

        The same question `made` asks, asked by whoever may only read. Opening a writer to
        find out would leave the two files SQLite keeps beside a database standing after a
        command that promised to change nothing — `doctor` is exactly that command
        (R-AGT-12), and it is also the one an owner runs when something is already wrong.
        """
        want = version_wanted() if self._version is None else self._version
        with self._reading() as conn:
            found = int(conn.execute("PRAGMA user_version").fetchone()[0])
            self._refused(conn, found, want)
            self._searchable = self._has_search(conn)

    def _refused(self, conn, found: int, want: int) -> None:
        """Whether this shape may be read at all — one decision, said the same to everyone.

        Both directions are refused, and that symmetry is the point. A newer shape is
        dangerous because this code does not know what it is missing; an older one is
        dangerous because this code assumes something that is not there yet. Neither is a
        reader's decision — what resolves the second is a migration, run while nothing is up.
        """
        if found > want:
            self._noted(f"refusing these records: they are version {found} and this "
                       f"rundesk understands {want}", "ERROR")
            raise TooNew(found, want)
        if found == 0:
            self._noted("these records hold tables but say no version — they were "
                       "written partway and are left exactly as they are", "ERROR")
            raise Unreadable(
                f"{self.at} holds tables but says no version — it was written partway"
            )
        if found < want:
            self._noted(f"refusing these records: they are version {found} and this "
                       f"rundesk expects {want} — they have not been brought forward",
                       "ERROR")
            raise Behind(found, want)
        # A version says which shape this is meant to be, not that the shape is there. A
        # header survives a truncated restore and a dropped table where the pages holding
        # them do not, so a database can claim the current version and hold nothing. Asked
        # every time rather than only when the version is zero: the mirror case was
        # guarded and this one was not, and it is the one that reads as healthy.
        if not self._anything(conn):
            self._noted(f"these records say they are version {found} and hold none of it",
                       "ERROR")
            raise Unreadable(f"{self.at} says it is version {found} and holds none of it")

    @staticmethod
    def _anything(conn) -> bool:
        row = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'agent'"
        ).fetchone()
        return bool(row[0])

    @staticmethod
    def _has_search(conn) -> bool:
        row = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE name = 'message_fts'"
        ).fetchone()
        return bool(row[0])

    def version(self) -> int:
        with self._reading() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def searchable(self) -> bool:
        """Whether searching by the words in something works here. Asked, never assumed."""
        if self._searchable is None:
            with self._reading() as conn:
                self._searchable = self._has_search(conn)
        return self._searchable

    def journal(self) -> str:
        with self._reading() as conn:
            return str(conn.execute("PRAGMA journal_mode").fetchone()[0])

    # ── the agent, and its gateway's one durable fact ─────────────────────────────────────

    def agent(self) -> dict:
        with self._reading() as conn:
            row = conn.execute(
                "SELECT provider, model, instructions, settings FROM agent WHERE id = 1"
            ).fetchone()
        kept = _plain(row)
        kept["settings"] = json.loads(kept["settings"])
        return kept

    def remember_agent(self, provider=None, model=None, instructions=None, settings=None):
        """Change what an entry point falls back to when it names no brain of its own.

        Only what is named is changed, so setting a model does not quietly clear a provider.
        """
        sets, values = [], []
        for column, given in (
            ("provider", provider),
            ("model", model),
            ("instructions", instructions),
        ):
            if given is not None:
                sets.append(f"{column} = ?")
                values.append(given)
        if settings is not None:
            sets.append("settings = ?")
            values.append(json.dumps(settings, sort_keys=True))
        if not sets:
            return
        with self._writing() as conn:
            conn.execute(f"UPDATE agent SET {', '.join(sets)} WHERE id = 1", values)

    def seen(self, at: str) -> None:
        """That a gateway of this name was up at this moment, so a later one can measure.

        Durable rather than swept with what a stop clears: the gateway that reads this is the
        *next* one, working out how long it was down and which firings it missed.
        """
        with self._writing() as conn:
            conn.execute("UPDATE gateway SET last_seen_at = ? WHERE id = 1", (at,))

    def last_seen(self):
        with self._reading() as conn:
            return conn.execute("SELECT last_seen_at FROM gateway WHERE id = 1").fetchone()[0]

    # ── channels ──────────────────────────────────────────────────────────────────────────

    def channels(self, enabled_only: bool = False) -> list:
        where = " WHERE enabled = 1" if enabled_only else ""
        with self._reading() as conn:
            rows = conn.execute(f"SELECT * FROM channel{where} ORDER BY name").fetchall()
        return [self._channel(row) for row in rows]

    def channel(self, name: str):
        with self._reading() as conn:
            row = conn.execute("SELECT * FROM channel WHERE name = ?", (name,)).fetchone()
        return self._channel(row) if row else None

    @staticmethod
    def _channel(row) -> dict:
        kept = _plain(row)
        kept["allow"] = json.loads(kept["allow"])
        kept["settings"] = json.loads(kept["settings"])
        kept["fills"] = json.loads(kept["fills"])
        kept["activity"] = bool(kept["activity"])
        kept["secret"] = json.loads(kept["secret"]) if kept["secret"] else None
        kept["enabled"] = bool(kept["enabled"])
        return kept

    def remember_channel(self, name, kind, allow, created_at, provider=None, model=None,
                         instructions=None, secret=None, settings=None, describes=None,
                         fills=None, activity=True, enabled=True):
        """Write down a surface an agent is reachable on, replacing one of the same name.

        `allow` is who may reach the agent through it and is never empty — a channel nobody
        may use answers whoever speaks to it, which is a misconfiguration and never a mode.
        `secret` holds the *names* of the places a credential is read from, never a credential.

        `describes` and `fills` are what the adapter said about the kind of place this is
        and which parts of it it can fill in, so a `{where.something}` an owner writes later
        is checked against what will actually be there rather than against a guess.

        `activity` is whether this surface is shown what the agent is *doing* while it
        works, as against what it finally says. On unless an owner says otherwise: a room
        that goes quiet for four minutes and then answers looks broken, and the fix for a
        room where that is noise is to say so once rather than to guess per message.
        """
        if not allow:
            raise ValueError("a channel nobody may use is refused rather than defaulted")
        with self._writing() as conn:
            conn.execute(
                "INSERT INTO channel (name, kind, enabled, provider, model, instructions,"
                " allow, secret, settings, describes, fills, activity, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET"
                " kind=excluded.kind, enabled=excluded.enabled, provider=excluded.provider,"
                " model=excluded.model, instructions=excluded.instructions,"
                " allow=excluded.allow, secret=excluded.secret, settings=excluded.settings,"
                " describes=excluded.describes, fills=excluded.fills,"
                " activity=excluded.activity",
                (
                    name, kind, 1 if enabled else 0, provider, model, instructions,
                    json.dumps(sorted(set(allow))),
                    json.dumps(secret, sort_keys=True) if secret else None,
                    json.dumps(settings or {}, sort_keys=True),
                    describes, json.dumps(list(fills or [])), 1 if activity else 0,
                    created_at,
                ),
            )

    def tell_channel(self, name: str, instructions) -> None:
        """What the agent is told about being here. Empty takes it off rather than storing it."""
        with self._writing() as conn:
            conn.execute(
                "UPDATE channel SET instructions = ? WHERE name = ?",
                (instructions or None, name),
            )

    def forget_channel(self, name: str) -> None:
        with self._writing() as conn:
            conn.execute("DELETE FROM channel WHERE name = ?", (name,))

    # ── schedules ─────────────────────────────────────────────────────────────────────────

    def schedules(self) -> list:
        with self._reading() as conn:
            rows = conn.execute("SELECT * FROM schedule ORDER BY name").fetchall()
        return [self._schedule(row) for row in rows]

    def schedule(self, name: str):
        with self._reading() as conn:
            row = conn.execute("SELECT * FROM schedule WHERE name = ?", (name,)).fetchone()
        return self._schedule(row) if row else None

    @staticmethod
    def _schedule(row) -> dict:
        kept = _plain(row)
        kept["command"] = json.loads(kept["command"]) if kept["command"] else None
        kept["enabled"] = bool(kept["enabled"])
        return kept

    def remember_schedule(self, name, cron, created_at, command=None, prompt=None,
                          provider=None, model=None, instructions=None, enabled=True,
                          next_auto_run_at=None):
        """Work an agent does because the time came — either a program, or a turn.

        Exactly one of `command` and `prompt`, which the database enforces rather than trusts.
        `next_auto_run_at` is reported rather than authoritative: the cron is the only thing
        that decides when work is due, and this is recomputed whenever the cron changes so a
        listing can show it without working it out again.
        """
        if (command is None) == (prompt is None):
            raise ValueError("a schedule runs a command or asks a turn, never both or neither")
        with self._writing() as conn:
            conn.execute(
                "INSERT INTO schedule (name, enabled, cron, command, prompt, provider, model,"
                " instructions, next_auto_run_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET"
                " enabled=excluded.enabled, cron=excluded.cron, command=excluded.command,"
                " prompt=excluded.prompt, provider=excluded.provider, model=excluded.model,"
                " instructions=excluded.instructions,"
                " next_auto_run_at=excluded.next_auto_run_at",
                (
                    name, 1 if enabled else 0, cron,
                    json.dumps(command) if command is not None else None,
                    prompt, provider, model, instructions, next_auto_run_at, created_at,
                ),
            )

    def enable_schedule(self, name: str, on: bool) -> None:
        """Keep a schedule and what it did, but stop it running."""
        with self._writing() as conn:
            conn.execute(
                "UPDATE schedule SET enabled = ? WHERE name = ?", (1 if on else 0, name)
            )

    def schedule_fired(self, name: str, at: str, next_at=None) -> None:
        """That the clock started this, written before it runs.

        Only the clock moves this. Running one by hand leaves both times where they were,
        which is what keeps a hand-run from moving when it next falls due on its own.
        """
        with self._writing() as conn:
            conn.execute(
                "UPDATE schedule SET last_auto_run_at = ?,"
                " next_auto_run_at = COALESCE(?, next_auto_run_at) WHERE name = ?",
                (at, next_at, name),
            )

    def forget_schedule(self, name: str) -> None:
        with self._writing() as conn:
            conn.execute("DELETE FROM schedule WHERE name = ?", (name,))

    # ── conversations, and the brain's own token for each ─────────────────────────────────

    def conversation(self, channel: str, space: str, thread: str = ""):
        with self._reading() as conn:
            row = conn.execute(
                "SELECT * FROM conversation WHERE channel = ? AND space = ? AND thread = ?",
                (channel, space, thread),
            ).fetchone()
        return _plain(row) if row else None

    def conversations(self, channel=None, space=None, limit: int = 50) -> list:
        where, values = [], []
        if channel is not None:
            where.append("channel = ?")
            values.append(channel)
        if space is not None:
            where.append("space = ?")
            values.append(space)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._reading() as conn:
            rows = conn.execute(
                f"SELECT * FROM conversation{clause} ORDER BY last_at DESC, id LIMIT ?",
                values + [limit],
            ).fetchall()
        return [_plain(row) for row in rows]

    def opened(self, conversation_id, channel, kind, space, at, thread="", parent_id=None,
               title=None) -> dict:
        """Find where this is happening, or begin knowing about it.

        `space` and `thread` are the platform's own words and are never parsed here — a
        Discord channel and thread, a Telegram chat and topic, a Slack channel and timestamp.
        A surface nobody has written yet needs no change to this.
        """
        with self._writing() as conn:
            row = conn.execute(
                "SELECT * FROM conversation WHERE channel = ? AND space = ? AND thread = ?",
                (channel, space, thread),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE conversation SET last_at = ? WHERE id = ?", (at, row["id"])
                )
                found = _plain(row)
                found["last_at"] = at
                return found
            conn.execute(
                "INSERT INTO conversation (id, channel, kind, space, thread, parent_id,"
                " title, opened_at, last_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (conversation_id, channel, kind, space, thread, parent_id, title, at, at),
            )
            made = conn.execute(
                "SELECT * FROM conversation WHERE id = ?", (conversation_id,)
            ).fetchone()
            return _plain(made)

    def session(self, conversation_id: str, brain: str):
        """What this conversation was continuing, for this brain and no other.

        Kept for a conversation and a brain together, never for either alone: keyed by the
        conversation only, changing which brain answers would hand one vendor's session to
        another, and that must not be expressible.
        """
        with self._reading() as conn:
            row = conn.execute(
                "SELECT handle FROM session WHERE conversation_id = ? AND brain = ?",
                (conversation_id, brain),
            ).fetchone()
        return row["handle"] if row else None

    def remember_session(self, conversation_id: str, brain: str, handle: str) -> None:
        with self._writing() as conn:
            conn.execute(
                "INSERT INTO session (conversation_id, brain, handle) VALUES (?,?,?)"
                " ON CONFLICT(conversation_id, brain) DO UPDATE SET handle = excluded.handle",
                (conversation_id, brain, handle),
            )

    def forget_session(self, conversation_id: str, brain=None) -> None:
        """So the next message starts a new one rather than resuming."""
        with self._writing() as conn:
            if brain is None:
                conn.execute(
                    "DELETE FROM session WHERE conversation_id = ?", (conversation_id,)
                )
            else:
                conn.execute(
                    "DELETE FROM session WHERE conversation_id = ? AND brain = ?",
                    (conversation_id, brain),
                )

    # ── what was said: the searchable history ─────────────────────────────────────────────

    def arrived(self, conversation_id, at, text, author="person", who=None, who_label=None,
                external_id=None, reply_to_id=None):
        """Something a person said. Returns what it is known by, so a run can name its cause.

        A platform's own id makes this the same message however often a channel reconnects —
        recording it twice is refused by the database rather than guarded against here.
        """
        return self._said(conversation_id, at, text, author, who, who_label, external_id,
                          reply_to_id, None)

    def answered(self, conversation_id, run_id, at, text, external_id=None, reply_to_id=None):
        """What the agent said, and which run produced it."""
        return self._said(conversation_id, at, text, "agent", None, None, external_id,
                          reply_to_id, run_id)

    def _said(self, conversation_id, at, text, author, who, who_label, external_id,
              reply_to_id, run_id):
        if author not in AUTHORS:
            raise ValueError(f"an author is one of {AUTHORS}, not {author!r}")
        with self._writing() as conn:
            cursor = conn.execute(
                "INSERT INTO message (conversation_id, run_id, external_id, reply_to_id,"
                " at, author, who, who_label, text) VALUES (?,?,?,?,?,?,?,?,?)",
                (conversation_id, run_id, external_id, reply_to_id, at, author, who,
                 who_label, text),
            )
            conn.execute(
                "UPDATE conversation SET last_at = ? WHERE id = ? AND last_at < ?",
                (at, conversation_id, at),
            )
            return int(cursor.lastrowid)

    def messages(self, conversation_id: str, limit: int = 200) -> list:
        """One conversation's whole history, in the order it happened."""
        with self._reading() as conn:
            rows = conn.execute(
                "SELECT * FROM message WHERE conversation_id = ? ORDER BY id LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [_plain(row) for row in rows]

    def search(self, words: str, limit: int = 50) -> list:
        """What was said about something, wherever it was said and whoever said it.

        Refuses out loud where this machine's SQLite cannot search, rather than returning
        nothing — an empty answer and an impossible question must not look the same.
        """
        if not self.searchable():
            self._once("search", "this machine's sqlite cannot search, so searching by the "
                                 "words in something is unavailable here", "WARNING")
            raise Unsearchable(
                "this machine's SQLite was built without FTS5, so searching by the words in "
                "something is unavailable — every run is still listed, read and queried"
            )
        with self._reading() as conn:
            rows = conn.execute(
                "SELECT m.*, c.channel AS channel, c.space AS space, c.thread AS thread"
                " FROM message_fts f"
                " JOIN message m ON m.id = f.rowid"
                " JOIN conversation c ON c.id = m.conversation_id"
                " WHERE message_fts MATCH ? ORDER BY rank LIMIT ?",
                (words, limit),
            ).fetchall()
        return [_plain(row) for row in rows]

    # ── runs, and the account of each ─────────────────────────────────────────────────────

    def began(self, source, provider, brain, posture, started_at, conversation_id=None,
              schedule_id=None, trigger_message_id=None, model=None, can=None,
              settings=None, resumed=False, pick=None) -> str:
        """Admit one occurrence of work, and name it. Everything resolved here is final.

        The number is the database's and is never handed out twice — allocated inside the
        same transaction that writes the row, so the counter and what it counts cannot
        disagree the way a file beside a directory can.

        `settings` is what the brain was told to run with, carried unread. It is part of
        what the run resolved rather than of what it did, so it belongs here and is never
        changed afterwards (R-RUN-3).
        """
        with self._writing() as conn:
            row = conn.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM run").fetchone()
            number = int(row[0])
            named = f"{number}-{_marked(pick)}"
            conn.execute(
                "INSERT INTO run (n, id, conversation_id, schedule_id, source,"
                " trigger_message_id, provider, brain, model, posture, can, settings,"
                " resumed, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (number, named, conversation_id, schedule_id, source, trigger_message_id,
                 provider, brain, model, posture, json.dumps(can or {}, sort_keys=True),
                 json.dumps(settings or {}, sort_keys=True),
                 1 if resumed else 0, started_at),
            )
            return named

    def ended(self, run_id, ended_at, outcome, exit_code=None, why=None,
              tokens=None) -> None:
        """How it finished, and what it cost. Written once, at the end.

        A cost that never arrived is left absent rather than recorded as nothing: a run that
        cost an unknown amount and one that cost zero are different facts.

        `why` is the one actionable line about a run that failed, kept beside the run rather
        than only in what the brain printed — because a turn that failed with its reason
        filed where nobody looks is a turn somebody is stuck on, and a run that never
        reached a brain has nothing printed at all.
        """
        tokens = tokens or {}
        with self._writing() as conn:
            conn.execute(
                "UPDATE run SET ended_at = ?, outcome = ?, exit_code = ?, why = ?,"
                " tokens_in = ?, tokens_out = ?, tokens_cached = ?, tokens_written = ?,"
                " tokens_reported = ? WHERE id = ?",
                (
                    ended_at, outcome, exit_code, why,
                    tokens.get("input"), tokens.get("output"),
                    tokens.get("cached"), tokens.get("written"),
                    1 if tokens.get("reported") else 0,
                    run_id,
                ),
            )

    def run(self, run_id: str):
        with self._reading() as conn:
            row = conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def runs(self, conversation_id=None, schedule_id=None, limit: int = 50) -> list:
        """What an agent has run, newest first — or one conversation's, in the order it went."""
        where, values = [], []
        if conversation_id is not None:
            where.append("conversation_id = ?")
            values.append(conversation_id)
        if schedule_id is not None:
            where.append("schedule_id = ?")
            values.append(schedule_id)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._reading() as conn:
            rows = conn.execute(
                f"SELECT * FROM run{clause} ORDER BY n DESC LIMIT ?", values + [limit]
            ).fetchall()
        return [self._run(row) for row in rows]

    @staticmethod
    def _run(row) -> dict:
        kept = _plain(row)
        kept["can"] = json.loads(kept["can"])
        kept["settings"] = json.loads(kept["settings"])
        kept["resumed"] = bool(kept["resumed"])
        kept["tokens_reported"] = bool(kept["tokens_reported"])
        return kept

    def usage(self) -> dict:
        """What this agent has cost, without a provider being started to ask.

        Runs whose usage never arrived are counted apart rather than folded in as zero, so a
        total never quietly claims to know more than it does.
        """
        with self._reading() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS runs,"
                " SUM(tokens_reported) AS reported,"
                " SUM(COALESCE(tokens_in, 0)) AS input,"
                " SUM(COALESCE(tokens_out, 0)) AS output,"
                " SUM(COALESCE(tokens_cached, 0)) AS cached,"
                " SUM(COALESCE(tokens_written, 0)) AS written FROM run"
            ).fetchone()
        kept = _plain(row)
        kept["reported"] = int(kept["reported"] or 0)
        kept["unreported"] = int(kept["runs"]) - kept["reported"]
        return kept

    def recorded(self, run_id, seq, at, kind, event=None, raw=None) -> None:
        """One line of what happened, added and never rewritten.

        `seq` is a total order that does not depend on a clock, so two accounts concatenate
        into the order the work happened in. A line the seam did not understand is kept as
        `unknown` with its own words beside it, because a record nobody could read today is
        still there to be read later.
        """
        if kind not in RECORD_KINDS:
            raise ValueError(f"a record is one of {RECORD_KINDS}, not {kind!r}")
        with self._writing() as conn:
            conn.execute(
                "INSERT INTO record (run_id, seq, at, kind, event, raw) VALUES (?,?,?,?,?,?)",
                (run_id, seq, at, kind,
                 json.dumps(event, sort_keys=True) if event is not None else None, raw),
            )

    def records(self, run_id: str) -> list:
        with self._reading() as conn:
            rows = conn.execute(
                "SELECT * FROM record WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        kept = []
        for row in rows:
            one = _plain(row)
            one["event"] = json.loads(one["event"]) if one["event"] else None
            kept.append(one)
        return kept



def removes(directory) -> list:
    """Every file taking this agent's records away has to take.

    A database is three files while it is in WAL, and the two beside it are the database's
    rather than ours — leaving them behind leaves a record of what was deleted.
    """
    at = path_for(directory)
    return [at, Path(str(at) + "-wal"), Path(str(at) + "-shm")]


def gone(directory) -> None:
    for one in removes(directory):
        with contextlib.suppress(OSError):
            os.remove(one)
