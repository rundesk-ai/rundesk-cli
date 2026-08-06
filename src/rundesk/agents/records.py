"""The database one agent keeps, and the only way in to it.

One database per agent, never one shared between them. A shared file would put one agent's write
lock in another agent's way and make one corrupt file everybody's problem; this way an agent that
cannot be read is one agent that cannot be read.

## Four answers, never two

Asking an agent for its records can end four different ways, and every pair of them that gets
collapsed loses state:

| Answer | What it means | Named |
|---|---|---|
| it was read | there, understood, and here is the row | — |
| it is not there at all | nobody has made this agent, or its records have been taken away | `NotThere` |
| it is there and cannot be understood | a truncated copy, a file somebody put there, a database half-written by a disk that filled | `Unreadable` |
| it has been carried further than this release ships | a newer rundesk moved it forward | `migration.Ahead` |

The third is the one that costs something when it is collapsed into the second: a caller told
"not there" makes a new one, and what was in the old one is gone. `AGENTS.md` states the rule
under *Say which of the three it is*; here there are four.

## A reader is opened read-only, and it has to be asked for at open time

The build this replaces recorded the trap: **`BEGIN IMMEDIATE` succeeds on a read-only
connection.** So "this connection only reads" cannot be a thing a caller intends and then relies
on later — it is asked of SQLite at `sqlite3.connect`, through the `file:…?mode=ro` URI, and the
database itself refuses the write. **A read never creates the file**, which is what makes
`NotThere` an answer rather than a side effect.

## A busy timeout is necessary and not sufficient

A gateway reads an agent's records while a command writes to them, and that is the ordinary case
rather than the rare one. Without a busy timeout the second one back gets `database is locked`
immediately — not after waiting, immediately — so one is set explicitly on every connection.
Explicitly, because the five seconds the Python binding defaults to is an accident of the binding
rather than a decision anybody here made, and a default nobody chose is a default nobody can change
with confidence.

**And then the wait is tried again, with a random pause.** SQLite's own backoff is very nearly
deterministic, so two writers that collide once re-collide in lockstep and form a convoy: the
timeout expires for both and both report a database that is perfectly healthy. A random wait breaks
the convoy. The numbers below came from the build this replaces, which settled on them by measuring.

## WAL if this filesystem can, and the default journal if it cannot

`journal_mode=WAL` lets a reader and a writer stop taking turns, and it is asked for once, when the
database is made.

**Asked for, never assumed.** `RUNDESK_HOME` defaults under the owner's home directory, and a home
directory is not always a local disk: on iCloud Drive, Dropbox or an SMB share, WAL does not work at
all — SQLite answers with a locking-protocol error, and an agent's records become unusable on a
machine that was working a moment before. So the mode is asked for, **read back**, and left on the
default rollback journal when it did not take. Everything here works either way; only the taking of
turns changes. A suite that runs in `/tmp` can never see this, which is why it is written down here.

**Never live-downgraded either.** The mode is a property of the file that other processes may have
open, so a later connection reads it and does not touch it.

Transactions are explicit: `isolation_level=None` turns off the standard library's own idea of
when to begin one, so a writer takes its lock at `BEGIN IMMEDIATE` — at the start of the
operation, where contention can be reported — rather than at the commit at the end of it.

## Every connection is closed on every path, including the ones that fail

Not tidiness. A leaked reader holds the WAL read lock on Python 3.11 and later and does **not** on
3.9 — so the leak is invisible on the interpreter this project pins as its floor and is a hard error
on a current one, which is the worst possible way round. In a gateway that runs for days it finally
surfaces as `[Errno 24] Too many open files` in components with nothing to do with the database,
which is a diagnosis nobody makes quickly. `contextlib.closing`, every open, every path.
"""

import contextlib
import random
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List

#: How long a connection waits for another one to finish before saying the database is locked.
#:
#: Read at the moment of connecting rather than bound into a signature, so a suite can shorten the
#: ceiling and drive real contention in milliseconds. `sqlite3.connect`'s `timeout` argument and
#: SQLite's `busy_timeout` are one knob under two names; both are set from this, because the value
#: has to be a decision at the moment of connecting as well as afterwards.
BUSY_SECONDS = 5.0

#: How many times a writer asks for the lock before giving up, and the range of the random pause
#: between attempts. Above the busy timeout rather than instead of it — see the module docstring on
#: convoys. These are the numbers the build this replaces settled on by measuring; nothing here has
#: a reason to differ from them.
TRIES = 5
WAIT_LEAST = 0.02
WAIT_MOST = 0.15

#: What SQLite writes beside a database in WAL mode: the write-ahead log, and the shared-memory
#: index into it. Named rather than globbed — see `beside`.
SIBLINGS = ("-wal", "-shm")

#: The cheapest question that has to read the file header, so a file that is not a database says so
#: at the moment it is opened rather than three statements later inside somebody else's `try`.
READABLE = "PRAGMA schema_version"


class NotThere(Exception):
    """There are no records here. Nobody has made this agent, or they have been taken away."""


class Unreadable(Exception):
    """The records are there and cannot be understood, and nothing will be written over them.

    Deliberately not the same answer as `NotThere`. A caller told "not there" makes a new set, and
    an agent's whole memory is what that overwrites.
    """


class Refused(Exception):
    """A column that may not be set, named with why."""


def beside(at: Path) -> List[Path]:
    """The database and the two files SQLite keeps beside it, named one at a time.

    This exists so that removing an agent and rolling one back **name** these rather than globbing
    for them. The old build recorded why: a glob written as `state.db*` is easy to get subtly wrong
    and a glob written as `state.*` catches things that are not the database's at all, and either
    way what is left behind is a stale write-ahead log — which the next connection reads as the
    database's most recent truth.

    **Never assert that the siblings exist.** They are there only while a writer is live and are
    gone after a clean close, so a caller that checked would be checking the weather.
    """
    return [at] + [at.with_name(at.name + one) for one in SIBLINGS]


def _read_only(at: Path) -> str:
    """The URI that opens these records without the power to change them.

    Built with `as_uri()` rather than by pasting the path into an f-string, because SQLite reads
    everything after a `?` as its own parameters: an agent called `who?` would have its own name
    end the filename early, and the URI that resulted would open something else or nothing at all.
    """
    return f"{at.as_uri()}?mode=ro"


def _opened(where: str, uri: bool) -> sqlite3.Connection:
    """A connection with this product's settings on it, whichever way it was asked for.

    In one place so that a reader and a writer cannot come to disagree about the busy timeout or
    about who begins a transaction.

    The timeout is set twice on purpose and not by accident: once at `connect`, which is the only
    moment the argument can act on, and once as the pragma, which is the name somebody grepping for
    `busy_timeout` will look for. They are the same knob, and the point of setting it at all is that
    the binding's own five-second default is nobody's decision.
    """
    conn = sqlite3.connect(where, uri=uri, timeout=BUSY_SECONDS, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(BUSY_SECONDS * 1000)}")
    return conn


def _busy(why: sqlite3.OperationalError) -> bool:
    """Whether this is somebody else holding the lock, rather than something actually wrong.

    Asked of `sqlite_errorcode` where there is one — it arrived in Python 3.11 — and of the message
    otherwise, because this project's floor is 3.9 and the binding there carries no code at all.
    Reading the message is not something to be pleased about; it is the only answer 3.9 has.
    """
    code = getattr(why, "sqlite_errorcode", None)
    if code is not None:
        return code in (5, 6)                     # SQLITE_BUSY, SQLITE_LOCKED
    said = str(why).lower()
    return "locked" in said or "busy" in said


def _begun(conn: sqlite3.Connection) -> None:
    """Take the write lock, asking again after a random pause while something else holds it.

    **Above the busy timeout, not instead of it.** SQLite's own backoff is close enough to
    deterministic that two writers which collide once go on colliding in step, and both then run
    out of timeout and report a database that is perfectly healthy. The pause is random so the two
    stop arriving together.

    Anything that is not somebody else holding the lock is raised at once: waiting does not fix a
    database nobody may write to, and asking five times would only take five times as long to say
    the same thing.
    """
    for attempt in range(TRIES):
        try:
            conn.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as why:
            if not _busy(why) or attempt == TRIES - 1:
                raise
            time.sleep(random.uniform(WAIT_LEAST, WAIT_MOST))


def _journalled(conn: sqlite3.Connection) -> None:
    """Keep these records in WAL if this filesystem can, and in the default journal if it cannot.

    Called once, when the database is made, and never again — the mode belongs to the file and
    other processes may have it open, so a later connection reads it rather than changing it.

    **Read back rather than assumed.** A home directory can sit on iCloud Drive, Dropbox or an SMB
    share, where WAL does not work at all: SQLite answers with a locking-protocol error, and records
    left believing they were in WAL are records that cannot be opened on a machine that was working
    a moment before. When it did not take, the rollback journal is asked for by name, so what these
    records are kept in is something that was decided rather than whatever the failed attempt left.
    """
    with contextlib.suppress(sqlite3.DatabaseError):
        conn.execute("PRAGMA journal_mode=WAL")
    if str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() != "wal":
        with contextlib.suppress(sqlite3.DatabaseError):
            conn.execute("PRAGMA journal_mode=DELETE")


def _pushed_as_hard_as_this_journal_needs(conn: sqlite3.Connection) -> None:
    """How hard a commit is pushed at the disk, **decided from the journal this file is really in**.

    The one connection setting this module had never chosen, which meant it inherited SQLite's
    `FULL` — and a default nobody chose is a default nobody can change with confidence, which is the
    same argument the busy timeout above is set explicitly for.

    It is not one answer, and that is why it is asked here rather than written into `_opened`.
    **`NORMAL` cannot corrupt a database under WAL** — a power cut loses transactions committed
    since the last checkpoint and nothing more — and it is the setting that makes WAL worth having,
    because every commit otherwise waits for the platter. **Under the rollback journal the same
    setting risks the file itself**, so anywhere WAL did not take keeps `FULL`.

    `_journalled` already had to read the mode back rather than assume it, because a home directory
    on iCloud Drive or an SMB share refuses WAL outright. This reads the same answer for the same
    reason: what is safe here is a fact about the filesystem underneath, not about what was asked
    for.
    """
    in_wal = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
    conn.execute(f"PRAGMA synchronous = {'NORMAL' if in_wal else 'FULL'}")


def _left_tidy(conn: sqlite3.Connection) -> None:
    """Let SQLite keep its own statistics fresh, after the work and never during it.

    Without statistics the planner guesses, and it guesses about tables that grow without bound —
    `turn_records` with a tool call in every row, `conversation_messages` with everything anybody
    has said. `PRAGMA optimize` is the documented habit for exactly this: it looks at what has
    changed and does the little that is worth doing, which is usually nothing at all.

    **After the commit, and never inside the transaction.** It may run `ANALYZE`, which writes — so
    inside the block it would be part of somebody's write, and on the failure path it would run
    against changes that are about to be rolled back.

    Suppressed rather than raised, and that is the whole of its contract: this is a tidy-up after
    work that has *already committed*, and a caller told their write failed because the statistics
    could not be refreshed would be told something untrue about the thing they asked for.
    """
    with contextlib.suppress(sqlite3.DatabaseError):
        conn.execute("PRAGMA optimize")


def _understood(conn: sqlite3.Connection, at: Path) -> None:
    """Ask the file whether it is a database at all, and say so in this module's words if not.

    Asked at open time and once. Left to the first real statement, `file is not a database` would
    surface from wherever that statement happened to be, wearing a name from `sqlite3` that no
    caller of this module should have to catch.
    """
    try:
        conn.execute(READABLE)
    except sqlite3.DatabaseError as why:
        raise Unreadable(f"{at} is there and cannot be read as an agent's records: {why}") from why


@contextlib.contextmanager
def reading(at: Path) -> Iterator[sqlite3.Connection]:
    """A connection that cannot write, for the length of the block.

    `NotThere` when there is nothing there — asked before connecting, because a `mode=ro` URI is
    also the thing that makes a missing file an error rather than a new empty database, and this
    way the answer is this module's word rather than SQLite's.
    """
    if not at.is_file():
        raise NotThere(f"{at} is not there")
    with contextlib.closing(_opened(_read_only(at), uri=True)) as conn:
        _understood(conn, at)
        yield conn


@contextlib.contextmanager
def writing(at: Path, making: bool = False) -> Iterator[sqlite3.Connection]:
    """A connection inside `BEGIN IMMEDIATE`, committed on the way out and rolled back on the way down.

    `making` is whether these records may be brought into existence: `False` is the ordinary case
    and answers `NotThere` rather than quietly creating an empty database where an agent's memory
    used to be. `True` is for the migration runner, which is the one thing that builds a set of
    records from nothing.

    **The lock is taken at `BEGIN IMMEDIATE`**, at the start of the operation, so two writers
    contend where it can be reported rather than at the commit at the end of one.

    The journal mode is decided only when the database is made — see `_journalled`. It is a
    property of the file that other processes may have open, so a later connection reads it and
    never changes it.

    `foreign_keys` is set **before** the transaction is begun, and that is not a stylistic
    ordering: the pragma is a no-op inside one, and answers as though it had worked.
    """
    fresh = not at.is_file()
    if fresh:
        if not making:
            raise NotThere(f"{at} is not there")
        # The directory is somebody else's to make. Creating it here would mean that carrying an
        # agent nobody has ever made *makes* one — a whole directory and a database, from a typo.
        if not at.parent.is_dir():
            raise NotThere(f"{at.parent} is not there, so there are no records to make in it")
    with contextlib.closing(_opened(str(at), uri=False)) as conn:
        _understood(conn, at)
        if fresh:
            _journalled(conn)
        conn.execute("PRAGMA foreign_keys=ON")
        _pushed_as_hard_as_this_journal_needs(conn)
        _begun(conn)
        try:
            yield conn
        except BaseException:
            # Rolled back on anything at all, including a `KeyboardInterrupt`: a step that was
            # stopped halfway leaves the same half-changed database as one that raised.
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        _left_tidy(conn)


def read(at: Path) -> Dict[str, Any]:
    """The one configuration row this agent keeps.

    `Unreadable` when the row is not there. A set of records with no configuration row is not an
    agent with no settings — it is a database that was never finished, and answering with an empty
    mapping would let a caller write its defaults over whatever survived.
    """
    with reading(at) as conn:
        try:
            row = conn.execute("SELECT * FROM config WHERE id = 1").fetchone()
        except sqlite3.DatabaseError as why:
            raise Unreadable(f"{at} does not hold an agent's configuration: {why}") from why
    if row is None:
        raise Unreadable(f"{at} holds no configuration row, so it is not an agent's records")
    return dict(row)


def stated(at: Path, values: Dict[str, Any]) -> None:
    """Set one or more configuration columns in one write, leaving every other as it was.

    **Every name is checked against the table before anything is written.** The same reasoning as
    `core.config.stated_all`: naming two columns and getting one wrong must change neither, because
    half of what was meant is not a smaller change — it is a different one nobody typed. The names
    are checked against `PRAGMA table_info` rather than against a list kept here, so a column a
    later step adds is settable the day it lands and a list cannot go stale.

    That check is also what makes the statement safe to build by hand: the only column names that
    reach it are ones SQLite has just said the table has.

    **A row that is not there yet is written by the same call**, because `CHECK (id = 1)` means
    there is exactly one configuration and its absence is not a different question from its
    contents — the first thing said about an agent is what brings its row into being. Tried as an
    update and then as an insert rather than as one `INSERT … ON CONFLICT DO UPDATE`: SQLite checks
    the insert's `NOT NULL` columns *before* it resolves the conflict, so the upsert form fails on
    a row that is already there whenever it names fewer columns than the table requires — measured
    on both this repo's 3.9 floor and on 3.14.
    """
    if not values:
        return
    named = sorted(values)
    said = [values[one] for one in named]
    with writing(at) as conn:
        columns = columns_of(conn, at, "config")
        unknown = [one for one in named if one not in columns]
        if unknown:
            raise Refused(f"{unknown[0]} is not something an agent's configuration holds")
        changed = conn.execute(
            "UPDATE config SET " + ", ".join(f"{one} = ?" for one in named) + " WHERE id = 1",
            said).rowcount
        if changed == 0:
            conn.execute(
                "INSERT INTO config (id, " + ", ".join(named) + ") "
                "VALUES (1, " + ", ".join("?" for _ in named) + ")", said)


def columns_of(conn: sqlite3.Connection, at: Path, table: str) -> List[str]:
    """What one of an agent's tables actually has, asked of the table itself.

    **Asked of SQLite rather than kept as a list here**, so a column a later step adds is settable
    the day it lands and a list cannot go stale. That is also what makes a statement built by hand
    from these names safe: the only names that reach it are ones SQLite has just said the table has.

    `id` is left out of every answer. In `config` it is how the table is kept to one row; in
    `schedules` it is the row's own identity, which nothing states and nothing changes. Either way a
    caller that set it would be refused by a constraint, in a sentence about the constraint rather
    than about what they did.

    `table` is interpolated, and it is never a caller's word — every call site in this product names
    a table literally. A public function taking a name from somewhere else would need quoting rules
    of its own, and there is no such caller to write them for.
    """
    try:
        there = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    except sqlite3.DatabaseError as why:
        raise Unreadable(f"{at} does not hold an agent's {table} table: {why}") from why
    if not there:
        raise Unreadable(
            f"{at} has no {table} table, so it is not an agent's records as this release keeps them")
    return [one for one in there if one != "id"]
