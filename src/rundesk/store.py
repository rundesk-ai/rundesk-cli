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

**Nothing of the database's leaves this module, exceptions included.** A caller that handles
every shape it will not read would otherwise meet a raw `file is not a database` and let it
past, so what cannot be read is refused in this seam's own words wherever it is opened.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
import sqlite3
import time
from datetime import datetime, timezone
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

#: Read off the runner rather than written here: it opens a database before there is a store
#: to ask, so the name is its, and two spellings of it would leave an update walking every
#: agent, finding nothing, and reporting that everything moved.
NAME = migration.RECORDS

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

# `limit` is account state a brain volunteered rather than this turn's activity — how much of
# an allowance is left, and when the window resets. It is non-fatal: a turn carrying one may
# still have succeeded, which is what makes it a record of its own rather than a failure.
RECORD_KINDS = ("think", "tool", "result", "usage", "file", "limit", "done", "lost",
                "unknown")
AUTHORS = ("user", "agent", "rundesk")

# Appended to a stopped run's account rather than added to the schema. Recovery is lifecycle
# bookkeeping, not a new shape of owner data, and these exact private records make claiming
# one interrupted turn atomic without rewriting the account it already left (R-GW-22).
RECOVERABLE = "rundesk:recovery:available"
RECOVERY_CLAIMED = "rundesk:recovery:claimed"
RECOVERED_BY = "rundesk:recovery:run:"

#: Every way work is admitted for an agent, and the whole of it. Three, because there are
#: three things that start one: somebody at a terminal, somebody on a surface the agent is
#: reachable on, and the clock.
#:
#: **Declared and refused rather than written as free text.** This is the only record of how
#: a run came about, and until it was a set the column took whatever a caller passed —
#: `"hand"` existed in a test and in nothing else, which is what a fourth word arriving by
#: typo looks like from the outside. A word nobody can read back is a run whose origin is
#: lost, and this is the column somebody reads at three in the morning to find out whether
#: they asked for what happened.
SOURCES = ("terminal", "channel", "schedule")


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


class Taken(Exception):
    """This name is already a schedule's, so nothing was written.

    Its own type because the caller has something useful to say about it and nothing useful to
    say about the driver's words. Raised by the write rather than decided by a read before one:
    asking and then writing is two decisions with a gap, and two commands adding the same name
    both found it absent and both reported success while one of them was silently replaced.
    """


class Refused(Exception):
    """The records would not take this, because something it names is not there.

    A schedule reporting to a channel that has gone is the case: the reference is what stops one
    outliving the other, and it refuses at the moment of writing rather than at three in the
    morning.
    """


class Unsearchable(Exception):
    """This machine's SQLite was built without FTS5. Said out loud, never returned as none."""


def path_for(directory) -> Path:
    """Where an agent's records stand, given the directory everything of its own is under."""
    return Path(directory) / NAME


#: How a durable moment is written down, and read back by `moment`. One spelling, because
#: a writer and a reader that disagreed about it would fall to the reader's `except` and
#: quietly answer "nothing was ever written".
STAMPED_AS = "%Y-%m-%dT%H:%M:%SZ"


def stamped(now=None) -> str:
    """Now, as what is written down beside a record.

    Wall time, and deliberately: these are calendar facts somebody reads back months later,
    never durations — nothing here measures how long anything took, so nothing compares one
    of these with a monotonic clock. In UTC and to the second, so two agents' records sort
    against each other whatever machine wrote them.

    One of these, not one per caller, and it takes the clock: a second copy that read the
    clock for itself would be a durable fact no case could fix, and two formats for one kind
    of fact the day either changed.
    """
    return time.strftime(STAMPED_AS, time.gmtime((now or time.time)()))


def moment(said) -> "datetime | None":
    """A moment these records hold, read back — or None where there is nothing to read.

    The inverse of `stamped`, and here rather than beside its caller for the same reason
    `stamped` is here: one format, written once. A second copy of it is a durable fact no
    case could fix the day either changed.

    **Aware, and deliberately.** What is written down is UTC so two agents' records sort
    against each other whatever machine wrote them, and a schedule is stated in the machine's
    own local time. Handing back something that does not say which would let a caller compare
    the two clock faces directly — an error invisible for most of the year and wrong by an
    hour for the rest of it. The caller converts, and cannot forget to.
    """
    if not isinstance(said, str) or not said:
        return None
    try:
        return datetime.strptime(said, STAMPED_AS).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def conversation_id(channel: str, space: str, thread: str = "") -> str:
    """What one conversation is called, worked out the same way every time it is opened.

    Derived rather than handed out, because the three that identify a conversation are
    already unique together and a name minted afresh each time would need somewhere to be
    remembered — which is the row it is the name of. So two turns arriving in one Discord
    room, weeks apart and from different processes, land on one conversation without
    either having asked anything first.

    Hashed rather than joined, because a separator is only unambiguous until one of the
    three contains it: a platform's own words are its own, and `a` in `b:c` must never be
    the same conversation as `a:b` in `c`.
    """
    said = "\x00".join((channel, space, thread)).encode("utf-8")
    return hashlib.sha256(said).hexdigest()[:16]


def _one_conversation(named: str, of: str = "") -> tuple:
    """Match one conversation by either name it goes by, as a clause and its values.

    **The identifier a listing prints is the identifier its filter takes (R-STO-28).**
    `messages` shows `<channel>/<space>` in its `WHERE` column while the filter matched
    the bare space alone, so the one value an agent can see and copy back matched nothing
    — and an empty listing reads as "this conversation is empty", which is the single
    wrong answer `messages` exists to prevent.

    Both forms, rather than the qualified one replacing the bare: a platform's own word
    for a place may itself contain a slash, and splitting on the last one would then
    quietly stop matching a value that used to work.
    """
    named = str(named)
    channel, slash, space = named.rpartition("/")
    if not slash:
        return f"{of}space = ?", [named]
    return (f"({of}space = ? OR ({of}channel = ? AND {of}space = ?))",
            [named, channel, space])


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
        try:
            self._made(want)
        except sqlite3.DatabaseError as why:
            # Records that are there and are not a database at all — see `understood`, which
            # answers the same thing the same way. Nothing of the database's leaves here.
            self._noted(f"these records could not be read at all: {why}", "ERROR")
            raise Unreadable(f"{self.at} could not be read: {why}") from why

    def _made(self, want: int) -> None:
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
            elif 0 < found < want:
                found = self._settled(conn, found, want)
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
        if not self.at.exists():
            # Records that have never been made are the seam's own answer, not the
            # database driver's: a caller that already handles a shape it will not read
            # would otherwise meet a raw `unable to open database file` from here and let
            # it out. **Nothing of the database's leaves this module, exceptions included.**
            self._noted("these records have not been made yet", "ERROR")
            raise Unreadable(f"{self.at} is not there — this agent has no records yet")
        try:
            with self._reading() as conn:
                found = int(conn.execute("PRAGMA user_version").fetchone()[0])
                self._refused(conn, found, want)
                self._searchable = self._has_search(conn)
        except sqlite3.DatabaseError as why:
            # **Records that are there and are not a database at all.** A stalled volume, a
            # truncated restore, a half-copied file: the driver says "file is not a
            # database" and, left to escape, that reached a caller which already handles
            # every shape it will not read and handles this one by tracebacking. Said in the
            # seam's own words for the same reason the missing case above is — nothing of
            # the database's leaves this module, exceptions included.
            #
            # Never treated as empty. What is there still holds everything the owner wrote.
            self._noted(f"these records could not be read at all: {why}", "ERROR")
            raise Unreadable(f"{self.at} could not be read: {why}") from why

    def _settled(self, conn, found: int, want: int) -> int:
        """What version these records are really on, once whoever is moving them has stopped.

        Records behind the installed shape are refused rather than moved forward by whatever
        opened them (R-MIG-10) — but **a fresh database somebody else is still building is
        behind too**, for as long as its steps take, and a single read cannot tell the two
        apart. What tells them apart is movement: a build is a version going up, and records
        that are genuinely behind read the same however often they are asked.

        Unreachable while one step shipped — a builder went from nothing to the installed
        shape in one transaction, so there was no half-built state to look at. The moment a
        second step landed, two commands reaching for one new agent at the same time left one
        of them refusing a database that was healthy a millisecond later.

        The write lock is taken before each look, so nothing is being read mid-step: a builder
        holds it for the whole of one. Bounded rather than endless — a build that died halfway
        leaves the version standing still, which is exactly the answer this then gives.
        """
        for _ in range(TRIES):
            # Waited *before* the first look, never after it. The version read on the way in
            # here was taken without the lock and a builder may simply not have reached its
            # next step yet, so concluding from it that nothing is moving is concluding from
            # no evidence at all.
            self._wait(random.uniform(WAIT_LEAST, WAIT_MOST))
            self._boundary(conn, "BEGIN IMMEDIATE")
            moved = int(conn.execute("PRAGMA user_version").fetchone()[0])
            self._boundary(conn, "COMMIT")
            if moved >= want or moved == found:
                return moved
            found = moved
        return found

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

    def remember_agent(self, provider=None, model=None, instructions=None, settings=None,
                       replace_brain=False, forget_conversation=None):
        """Change what an entry point falls back to when it names no brain of its own.

        Only what is named is changed, so setting a model does not quietly clear a provider.
        Replacing the brain is one atomic write of its provider-specific values: a model or
        setting understood by the old provider must not silently reach the new one
        (R-AGT-33).
        """
        with self._writing() as conn:
            # Compare under the same write lock as the update. Two simultaneous configure
            # commands must be ordered writes, not stale decisions that can erase the
            # model or settings the later command just kept (R-AGT-31, R-AGT-33).
            current = conn.execute(
                "SELECT provider FROM agent WHERE id = 1"
            ).fetchone()[0]
            replacing = bool(replace_brain and provider != current)
            sets, values = [], []
            for column, given in (("provider", provider), ("model", model)):
                if replacing:
                    sets.append(f"{column} = ?")
                    values.append(given)
                elif given is not None:
                    sets.append(f"{column} = ?")
                    values.append(given)
            if instructions is not None:
                sets.append("instructions = ?")
                values.append(instructions)
            if replacing or settings is not None:
                sets.append("settings = ?")
                values.append(json.dumps(settings or {}, sort_keys=True))
            if not sets:
                if forget_conversation is None:
                    return
            else:
                conn.execute(f"UPDATE agent SET {', '.join(sets)} WHERE id = 1", values)
            if forget_conversation is not None:
                conn.execute(
                    "DELETE FROM session WHERE conversation_id = ?",
                    (forget_conversation,))

    def seen(self, at: str | None = None) -> None:
        """That a gateway of this name was up at this moment, so a later one can measure.

        Durable rather than swept with what a stop clears: the gateway that reads this is the
        *next* one, working out how long it was down and which firings it missed.
        """
        with self._writing() as conn:
            conn.execute("UPDATE gateway SET last_seen_at = ? WHERE id = 1",
                         (at if at is not None else stamped(self._clock),))

    def last_seen(self):
        """When a gateway of this name was last up, or None if never.

        **A moment rather than the string one is written as**, and aware. What is kept is UTC so
        two agents' records sort against each other whatever machine wrote them, and whoever asks
        this is comparing it against a clock stated in local time — handing back the string made
        the caller decode this module's own format to do that, which is the caller knowing what
        holds its records. Aware, so the two clock faces cannot be compared without converting.
        """
        with self._reading() as conn:
            said = conn.execute("SELECT last_seen_at FROM gateway WHERE id = 1").fetchone()[0]
        return moment(said)

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

        `activity` is whether this surface is shown the turn while it runs — what the agent
        is doing and what it says on the way — as against only its answer (R-CH-6, R-CH-27).
        On unless an owner says otherwise: a room that goes quiet for four minutes and then
        answers looks broken, and the fix for a room where that is noise is to say so once
        rather than to guess per message.
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

    def remember_schedule(self, name, cron=None, created_at=None, command=None, prompt=None,
                          provider=None, model=None, instructions=None, enabled=True,
                          channel=None, place=None, at=None):
        """Work an agent does because the time came — either a program, or a turn.

        Exactly one of `command` and `prompt`, which the database enforces rather than trusts.

        **Exactly one of `cron` and `at`** (R-SCH-36), enforced the same way. `cron` is a
        repeating time;
        `at` is the single moment this runs, after which it can never be due again. Cron has
        no year, so one cannot say the other — and a row naming both would leave rundesk
        choosing which, with the choice invisible in the listing.

        `at` is the machine's own local clock, to the minute, spelled the way `last_auto_run_at`
        beside it is: a schedule is stated in local time and compared against a local clock,
        and the two sitting one column apart in different zones would be wrong by an hour for
        part of the year. Never `stamped()`, which is UTC because a run is a durable fact two
        agents' records have to sort against each other.

        Refused rather than replacing: `Taken` where the name is already a schedule's, `Refused`
        where it names a channel that is not there.

        `channel` is where what this came to is said, by the name the owner gave that surface —
        and none is not silence: the account and `schedules` say it either way, and a schedule
        that named no surface is one nobody asked to be told about in a chat.

        `place` is *which place on it*, in the surface's own word for one, and is carried
        without ever being read: a channel reaching a whole server has many rooms and the one
        an owner meant is not rundesk's to guess. Naming none follows the conversation, which
        is the older behaviour and still the right one for a channel that reaches one place.

        **When it is next due is not kept.** The cron is the only thing that decides that, so
        a column holding it would be a second answer to one question — stale the moment an
        owner edits the cron, and read in preference to the thing that is actually true.
        Whoever wants it works it out from the cron and the clock.
        """
        if (command is None) == (prompt is None):
            raise ValueError("a schedule runs a command or asks a turn, never both or neither")
        if (cron is None) == (at is None):
            raise ValueError(
                "a schedule states a repeating time or a single moment, never both or neither"
            )
        # **A plain insert, so the name is claimed by writing it.** It was an upsert, and a
        # caller that asked whether the name was free and then wrote was two decisions with a
        # gap in the middle: two `schedules add` of one name both found it absent, both reported
        # ADDED, and the second silently replaced the first — taking its account of what it last
        # did with it. The unique constraint is what closes that, because it is the write.
        try:
            with self._writing() as conn:
                conn.execute(
                    "INSERT INTO schedule (name, enabled, cron, at, command, prompt,"
                    " provider, model, instructions, channel, place, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        name, 1 if enabled else 0, cron, at,
                        json.dumps(command) if command is not None else None,
                        prompt, provider, model, instructions, channel, place, created_at,
                    ),
                )
        except sqlite3.IntegrityError as clash:
            # Two things the database refuses here and the caller answers differently: a name
            # that is already a schedule's, and a channel that is not there to report to. Told
            # apart by asking which, rather than by reading the driver's words.
            if self.schedule(name) is not None:
                raise Taken(f"a schedule called '{name}' is already there") from clash
            raise Refused(f"'{name}' names something this agent has not got: {clash}") from clash

    def enable_schedule(self, name: str, on: bool) -> None:
        """Keep a schedule and what it did, but stop it running."""
        with self._writing() as conn:
            conn.execute(
                "UPDATE schedule SET enabled = ? WHERE name = ?", (1 if on else 0, name)
            )

    def schedule_fired(self, name: str, at: str, outcome: str) -> None:
        """That the clock started this, written before it runs.

        Only the clock moves this. Running one by hand leaves both times where they were,
        which is what keeps a hand-run from moving when it next falls due on its own.

        **Never backwards.** A long run finishing after a later occurrence was already
        written would put the earlier minute back, and a gateway reading it on the way up
        would take the later minute for one that had never fired — and run it again
        (R-SCH-9). So the minute only ever moves forward, and the outcome follows it.
        """
        with self._writing() as conn:
            conn.execute(
                "UPDATE schedule SET last_auto_run_at = MAX(COALESCE(last_auto_run_at, ''), ?),"
                " last_outcome = ? WHERE name = ?",
                (at, outcome, name),
            )

    def schedule_became(self, name: str, outcome: str) -> None:
        """What the work a schedule started turned out to be, once it is over.

        The minute is left exactly where it was: it is the minute the schedule *fell due*,
        and moving it to the moment a run finished is how a gateway restarting comes to
        read a later minute as the last one to have fired.
        """
        with self._writing() as conn:
            conn.execute("UPDATE schedule SET last_outcome = ? WHERE name = ?",
                         (outcome, name))

    def forget_schedule(self, name: str) -> None:
        with self._writing() as conn:
            conn.execute("DELETE FROM schedule WHERE name = ?", (name,))

    # ── conversations, and the provider's own token for each ──────────────────────────────

    def conversation(self, channel: str, space: str, thread: str = ""):
        with self._reading() as conn:
            row = conn.execute(
                "SELECT * FROM conversation WHERE channel = ? AND space = ? AND thread = ?",
                (channel, space, thread),
            ).fetchone()
        return _plain(row) if row else None

    def has_conversation(self, named: str) -> bool:
        """Is there a conversation of this name, by either way of naming one?

        Asked so that a narrowed listing can tell "there is no such conversation" from
        "that conversation has nothing in it" — two sentences an agent acts on completely
        differently, and which returning an empty list for both made indistinguishable
        (R-STO-28).
        """
        clause_for, held = _one_conversation(named)
        with self._reading() as conn:
            row = conn.execute(
                f"SELECT 1 FROM conversation WHERE {clause_for} LIMIT 1", held
            ).fetchone()
        return row is not None

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

    def opened(self, conversation_id, channel, kind, space, at, thread="",
               parent_id=None) -> dict:
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
                " opened_at, last_at) VALUES (?,?,?,?,?,?,?,?)",
                (conversation_id, channel, kind, space, thread, parent_id, at, at),
            )
            made = conn.execute(
                "SELECT * FROM conversation WHERE id = ?", (conversation_id,)
            ).fetchone()
            return _plain(made)

    def session(self, conversation_id: str, provider: str):
        """What this conversation was continuing, for this provider and no other.

        Kept for a conversation and a provider together, never for either alone: keyed by
        the conversation only, changing which provider answers would hand one vendor's
        session to another, and that must not be expressible.

        `provider` here is the settled form — `provider.key()` of what an owner named — so
        one adapter typed two ways is one conversation carried on rather than two started.
        """
        with self._reading() as conn:
            row = conn.execute(
                "SELECT handle FROM session WHERE conversation_id = ? AND provider = ?",
                (conversation_id, provider),
            ).fetchone()
        return row["handle"] if row else None

    def remember_session(self, conversation_id: str, provider: str, handle: str) -> None:
        with self._writing() as conn:
            conn.execute(
                "INSERT INTO session (conversation_id, provider, handle) VALUES (?,?,?)"
                " ON CONFLICT(conversation_id, provider) DO UPDATE SET"
                " handle = excluded.handle",
                (conversation_id, provider, handle),
            )

    def forget_session(self, conversation_id: str, provider=None) -> None:
        """So the next message starts a new one rather than resuming.

        Every provider the conversation has had, unless one is named: an agent whose
        provider changed has a session under each, and leaving one behind means the next
        message carrying on from something somebody just asked to be rid of.
        """
        with self._writing() as conn:
            if provider is None:
                conn.execute(
                    "DELETE FROM session WHERE conversation_id = ?", (conversation_id,)
                )
            else:
                conn.execute(
                    "DELETE FROM session WHERE conversation_id = ? AND provider = ?",
                    (conversation_id, provider),
                )

    # ── what was said: the searchable history ─────────────────────────────────────────────

    def arrived(self, conversation_id, at, text, author="user", who=None,
                external_id=None):
        """Something a person said. Returns what it is known by, so a run can name its cause.

        A platform's own id makes this the same message however often a channel reconnects —
        recording it twice is refused by the database rather than guarded against here.
        """
        return self._said(conversation_id, at, text, author, who, external_id, None)

    def answered(self, conversation_id, run_id, at, text, external_id=None):
        """What the agent said, and which run produced it."""
        return self._said(conversation_id, at, text, "agent", None, external_id, run_id)

    def _said(self, conversation_id, at, text, author, who, external_id, run_id):
        if author not in AUTHORS:
            raise ValueError(f"an author is one of {AUTHORS}, not {author!r}")
        with self._writing() as conn:
            cursor = conn.execute(
                "INSERT INTO message (conversation_id, run_id, external_id,"
                " at, author, who, text) VALUES (?,?,?,?,?,?,?)",
                (conversation_id, run_id, external_id, at, author, who, text),
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

    def latest(self, limit: int = 50, since=None, channel=None, author=None,
               source=None, conversation=None, who=None) -> list:
        """The newest things said, across every conversation this agent has had.

        **The question `search` cannot answer.** Searching needs a word, and the case this
        exists for is the one where nobody gave you one: an agent is told "nice work" about
        a scheduled turn that ran in a different conversation, under a session that is not
        this one, and has no idea what is meant. Reading its own record newest-first is how
        it finds out, and `runs` is no help — a listing of ids, times and outcomes says that
        work happened and never what was said in it.

        Newest first and across every surface, because where something was said is not how
        anybody looks for it. `since` is a message id and nothing after it is returned twice,
        which is how a caller asks what is new rather than paging back through what it has
        already read — `id` is `AUTOINCREMENT`, so it is a cursor that stays put while new
        messages land beside it, which an offset is not.

        The narrowing arguments are refused rather than ignored when they are not one of the
        words that exist (R-STO-26). A filter nobody can spell is a listing that silently
        answers a different question than the one asked.
        """
        if author is not None and author not in AUTHORS:
            raise ValueError(f"an author is one of {AUTHORS}, not {author!r}")
        if source is not None and source not in SOURCES:
            raise ValueError(f"work is admitted from one of {SOURCES}, not {source!r}")
        where, values = [], []
        if since is not None:
            where.append("m.id > ?")
            values.append(int(since))
        if channel is not None:
            where.append("c.channel = ?")
            values.append(channel)
        if conversation is not None:
            # Either way of naming one place: the platform's own word for it, or the
            # qualified form the listing prints beside every row (R-STO-28).
            clause_for, held = _one_conversation(conversation, "c.")
            where.append(clause_for)
            values.extend(held)
        if author is not None:
            where.append("m.author = ?")
            values.append(author)
        if who is not None:
            # Identity, not kind. `author` says *what sort of* speaker this was and is one
            # of a closed set; this is the surface's own name for one person, so it is not
            # checked against anything — an id nobody has simply matches nothing, which is
            # a true answer, and refusing it would mean keeping a list of everyone who has
            # ever spoken to this agent (R-STO-27).
            where.append("m.who = ?")
            values.append(str(who))
        if source is not None:
            # Asked of the run this message belongs to, which it reaches two ways: an
            # agent's answer carries `run_id`, and what a person said is what a run points
            # back at. `EXISTS` rather than a join, so a message whose id matches more than
            # one run is still one row rather than several.
            where.append("EXISTS (SELECT 1 FROM run r WHERE (r.id = m.run_id"
                         " OR r.trigger_message_id = m.id) AND r.source = ?)")
            values.append(source)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._reading() as conn:
            rows = conn.execute(
                "SELECT m.*, c.channel AS channel, c.kind AS kind, c.space AS space,"
                " c.thread AS thread FROM message m"
                " JOIN conversation c ON c.id = m.conversation_id"
                f"{clause} ORDER BY m.id DESC LIMIT ?",
                values + [limit],
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

    def began(self, source, provider, posture, started_at, conversation_id=None,
              schedule_id=None, trigger_message_id=None, model=None, can=None,
              settings=None, resumed=False, pick=None) -> str:
        """Admit one occurrence of work, and name it. Everything resolved here is final.

        The number is the database's and is never handed out twice — allocated inside the
        same transaction that writes the row, so the counter and what it counts cannot
        disagree the way a file beside a directory can.

        `settings` is what the brain was told to run with, carried unread. It is part of
        what the run resolved rather than of what it did, so it belongs here and is never
        changed afterwards (R-RUN-3).

        `provider` is the adapter as the owner named it. Its settled form — what names its
        private directory and what `session` keys on — is `provider.key()` of that, derived,
        so it is not kept here as well.

        `source` is one of `SOURCES` and refused otherwise, the way an author and a record
        kind already are: it is the only thing that says how this run came about, and a word
        nothing can read back is a run whose origin is lost rather than one described oddly.
        """
        if source not in SOURCES:
            raise ValueError(f"work is admitted from one of {SOURCES}, not {source!r}")
        with self._writing() as conn:
            row = conn.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM run").fetchone()
            number = int(row[0])
            named = f"{number}-{_marked(pick)}"
            conn.execute(
                "INSERT INTO run (n, id, conversation_id, schedule_id, source,"
                " trigger_message_id, provider, model, posture, can, settings,"
                " resumed, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (number, named, conversation_id, schedule_id, source, trigger_message_id,
                 provider, model, posture, json.dumps(can or {}, sort_keys=True),
                 json.dumps(settings or {}, sort_keys=True),
                 1 if resumed else 0, started_at),
            )
            return named

    def ended(self, run_id, ended_at, outcome, exit_code=None, why=None,
              tokens=None, because=None) -> None:
        """How it finished, and what it cost. Written once, at the end.

        A cost that never arrived is left absent rather than recorded as nothing: a run that
        cost an unknown amount and one that cost zero are different facts.

        `why` is the one actionable line about a run that failed, kept beside the run rather
        than only in what the brain printed — because a turn that failed with its reason
        filed where nobody looks is a turn somebody is stuck on, and a run that never
        reached a brain has nothing printed at all.

        `because` is the closed word for the same failure and never a replacement for that
        sentence (R-RUN-19): prose says what this brain said, and the word is what anything
        else can count, branch on or phrase well. An adapter that cannot classify a failure
        leaves it absent, which is what every run written before there was a column for it
        already is — nothing infers one from `why` afterwards, because reading a word out of
        prose is guessing and a guessed reason inside a total cannot be seen.
        """
        tokens = tokens or {}
        with self._writing() as conn:
            conn.execute(
                "UPDATE run SET ended_at = ?, outcome = ?, exit_code = ?, why = ?,"
                " because = ?, tokens_in = ?, tokens_out = ?, tokens_cached = ?,"
                " tokens_written = ?, tokens_reported = ? WHERE id = ?",
                (
                    ended_at, outcome, exit_code, why, because,
                    tokens.get("input"), tokens.get("output"), tokens.get("cached"),
                    tokens.get("written"),
                    1 if tokens.get("reported") else 0,
                    run_id,
                ),
            )

    def interrupted(self, run_id: str, ended_at: str, why: str,
                    recoverable: bool = False) -> None:
        """Settle a cancelled run and, where safe, leave one durable recovery claim.

        The marker is appended in the same write as the outcome. A successor can therefore
        never see a run as recoverable before the interrupted execution is settled, or see
        a settled recoverable run without the marker that makes its claim single-use.
        """
        with self._writing() as conn:
            conn.execute(
                "UPDATE run SET ended_at = ?, outcome = ?, why = ? WHERE id = ?",
                (ended_at, "stopped", why, run_id),
            )
            if recoverable:
                self._mark(conn, run_id, ended_at, RECOVERABLE)

    def abandoned(self, ended_at: str, why: str, keep=()) -> int:
        """Settle every run still marked as running that nothing is doing (R-GW-23).

        A run is marked running when it starts, and a gateway that dies, is stopped or is
        replaced by an update never gets to write the end of it — so the row stayed
        `running` for ever. `rundesk runs` went on reporting a turn in flight more than a
        day after its transcript stopped being written, and its cost stayed `not reported`,
        which quietly undercounts every total read off it.

        `keep` is what is genuinely still in flight, named by the caller because only it
        can tell: this asks nothing about processes. Everything else is settled as
        `stopped` rather than `failed` — the turn ended without saying so, which is the
        same news `interrupted` already writes and not evidence that anything broke.

        Returns how many were settled, so a caller can say so once rather than per row.
        """
        kept = tuple(str(one) for one in keep)
        holes = ",".join("?" for _ in kept)
        with self._writing() as conn:
            done = conn.execute(
                "UPDATE run SET ended_at = ?, outcome = ?, why = ?"
                " WHERE ended_at IS NULL"
                + (f" AND id NOT IN ({holes})" if kept else ""),
                (ended_at, "stopped", why, *kept),
            )
            return int(done.rowcount or 0)

    def recoverable(self, channel: str) -> list:
        """Interrupted channel runs this surface may claim, oldest first (R-GW-22)."""
        with self._reading() as conn:
            rows = conn.execute(
                "SELECT r.*, c.space AS conversation, c.kind AS channel_kind,"
                " m.who AS user"
                " FROM run r"
                " JOIN conversation c ON c.id = r.conversation_id"
                " LEFT JOIN message m ON m.id = r.trigger_message_id"
                " WHERE r.source = 'channel' AND c.channel = ?"
                " AND EXISTS (SELECT 1 FROM record a WHERE a.run_id = r.id"
                "             AND a.kind = 'unknown' AND a.raw = ?)"
                " AND NOT EXISTS (SELECT 1 FROM record z WHERE z.run_id = r.id"
                "                 AND z.kind = 'unknown' AND z.raw = ?)"
                " ORDER BY r.n",
                (channel, RECOVERABLE, RECOVERY_CLAIMED),
            ).fetchall()
        return [self._run(row) for row in rows]

    def claim_recovery(self, run_id: str, at: str) -> bool:
        """Claim an interrupted run once, under the store's one writer lock."""
        with self._writing() as conn:
            available = conn.execute(
                "SELECT 1 FROM record WHERE run_id = ? AND kind = 'unknown' AND raw = ?",
                (run_id, RECOVERABLE),
            ).fetchone()
            claimed = conn.execute(
                "SELECT 1 FROM record WHERE run_id = ? AND kind = 'unknown' AND raw = ?",
                (run_id, RECOVERY_CLAIMED),
            ).fetchone()
            if available is None or claimed is not None:
                return False
            self._mark(conn, run_id, at, RECOVERY_CLAIMED)
            return True

    def recovery_began(self, interrupted_run: str, recovery_run: str, at: str) -> None:
        """Link the interrupted execution to the one continuing its provider session."""
        with self._writing() as conn:
            self._mark(conn, interrupted_run, at, RECOVERED_BY + recovery_run)

    @staticmethod
    def _mark(conn, run_id: str, at: str, marker: str) -> None:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM record WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO record (run_id, seq, at, kind, raw) VALUES (?,?,?,?,?)",
            (run_id, int(row[0]), at, "unknown", marker),
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
                # Summed the same way as the three beside it, so a total is what was
                # reported and nothing else. Rows from before the column, and every brain
                # that does not report the split, contribute nothing rather than a guess —
                # `written` is one place where the sum is knowingly a floor.
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


def snapshot(records: Path, into: Path) -> None:
    """A consistent copy of these records, taken while they may be being written to.

    **Here rather than beside whatever wants a copy**, because a copy of a database is a
    database operation: this module is the only one that opens one, and a backup reaching
    past it with `sqlite3.connect` is exactly the leak `R-STO-15` exists to prevent.

    **Why not a file copy.** `state.db` in WAL mode is three files, and the most recent
    truth may be in the one beside it rather than in the one somebody thought to copy. So a
    plain copy taken while a gateway is writing produces a database that opens, reports the
    right version, and is missing whatever had not been checkpointed — a failure discovered
    at the moment it is put back, which is the worst moment there is. Two ways to do it
    honestly, and this uses both.

    `VACUUM INTO` is preferred only because it compacts as it writes, which matters on an
    agent with a long history. It wants a SQLite newer than the floor this runs on is
    guaranteed to have, so where it is not there the standard library's own online backup
    does the same job without the compaction. Neither is `cp`.

    Opened read-only, so taking a copy can never be the thing that makes a turn wait.
    """
    conn = sqlite3.connect(f"file:{records}?mode=ro", uri=True, timeout=BUSY_SECONDS)
    try:
        try:
            conn.execute("VACUUM INTO ?", (str(into),))
            return
        except sqlite3.Error:
            # An older SQLite has no `VACUUM INTO`. Not a failure and not worth a word to an
            # owner: what follows is as consistent, and the only difference is its size. The
            # part-written file it may have left is removed first, because the backup below
            # opens its destination rather than replacing it.
            with contextlib.suppress(OSError):
                os.remove(into)
        second = sqlite3.connect(str(into))
        try:
            conn.backup(second)
        finally:
            second.close()
    finally:
        conn.close()
