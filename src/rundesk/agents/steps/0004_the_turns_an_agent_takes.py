"""The turns one agent has taken, what each did, and finding what was said. 0.39.0.

The release that runs a provider. `0003` laid down conversations and the messages in them and said
what it was deliberately leaving out: *"No `turn_id` on a message, which would be a foreign key into
a table no release ships. No full-text search tables, which are five tables and three triggers
serving a verb that does not exist."* Both verbs exist now, so both land here.

## Three tables, one column, and an index

**`turns`** is one row per turn: what it was admitted with, what it came to, and what it cost. It is
kept for ever — a couple of hundred bytes each, and a cost nobody can look back at is not a ledger.

**`turn_records`** is what a turn *did*, in order. The only table that grows with tool calls, and the
only one swept.

**`provider_sessions`** is where each conversation got to on each brain, which is the whole of how a
turn carries on from the last one.

**`conversation_messages.turn_id`** is the column `0003` would not pre-carry, added now that there is
a table for it to point at. `NULL` is meaningful: a message that arrived and was never answered,
which is a real state today.

## What decides whether something is a `CHECK` or a column

**Widening a `CHECK` needs the full table rebuild `steps/__init__.py` records as dangerous here —
`PRAGMA foreign_keys=OFF` is a no-op inside the runner's transaction and still answers `1`. Adding a
nullable column does not: it is one `ALTER TABLE`.**

So a `CHECK` names every value the design already knows is coming, and a column is never pre-carried
for a feature that is not built. `access_mode` and `turn_status` are complete vocabularies and are checked.
`failure_code` is **not**, and that is the one deliberate exception: it grows every time a vendor
invents a new way to fail, so `providers.kept` refuses an unknown word before the write instead.

## The search, and the one thing it may not do

Full text over an **external-content** table, so a message body is indexed once and not stored twice.
Three triggers keep it in step rather than a manual insert at each write, because `channels.arriving`
already writes messages without knowing this exists and a trigger cannot be forgotten by a future
writer. This is the case `0001` predicted when it refused `said.split(";")`: a trigger body contains
semicolons of its own.

**FTS5 is asked for read-only and never by attempting the statement.** A `CREATE VIRTUAL TABLE` that
fails inside the runner's transaction rolls the whole agent back through `migration._could_not` — so
an agent on a Python whose SQLite was built without the module would fail to carry at all, over a
verb it can live without. Asked of `pragma_compile_options`, an absent module means no table, no
triggers, and a search that falls back to a scan and says so.

Imports nothing of rundesk's, never `executescript`, never ends the runner's transaction, and is safe
against an agent that does not need it.
"""

import sqlite3
from pathlib import Path
from typing import Iterator, List

#: The tables and their indexes. Every one `STRICT`, so a column that says `TEXT` holds text — without
#: it SQLite stores whatever it is handed under whatever affinity it feels like, and a number written
#: into a text column comes back as one for ever.
SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
  id                  INTEGER PRIMARY KEY,
  conversation_id     INTEGER NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
  schedule_id         INTEGER REFERENCES schedules (id) ON DELETE SET NULL,
  provider_name       TEXT NOT NULL,
  model_name          TEXT,
  access_mode         TEXT NOT NULL CHECK (access_mode IN ('read', 'work')),
  provider_capabilities TEXT NOT NULL DEFAULT '{}',
  session_resumed     INTEGER NOT NULL DEFAULT 0 CHECK (session_resumed IN (0, 1)),
  instructions_sha256 TEXT,
  instructions_bytes  INTEGER,
  turn_status         TEXT NOT NULL
                        CHECK (turn_status IN ('working', 'done', 'stopped', 'failed')),
  exit_code           INTEGER,
  failure_code        TEXT,
  failure_message     TEXT,
  usage_reported      INTEGER NOT NULL DEFAULT 0 CHECK (usage_reported IN (0, 1)),
  input_tokens        INTEGER,
  output_tokens       INTEGER,
  cache_read_tokens   INTEGER,
  cache_write_tokens  INTEGER,
  context_tokens      INTEGER,
  unknown_records     INTEGER NOT NULL DEFAULT 0,
  lost_records        INTEGER NOT NULL DEFAULT 0,
  raw_offset_start    INTEGER,
  raw_offset_end      INTEGER,
  created_at          TEXT NOT NULL,
  ended_at            TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS idx_turns_conversation ON turns (conversation_id, id);

CREATE INDEX IF NOT EXISTS idx_turns_schedule ON turns (schedule_id);

CREATE TABLE IF NOT EXISTS turn_records (
  id          INTEGER PRIMARY KEY,
  turn_id     INTEGER NOT NULL REFERENCES turns (id) ON DELETE CASCADE,
  record_type TEXT NOT NULL,
  event_data  TEXT NOT NULL DEFAULT '{}',
  raw_line    TEXT,
  created_at  TEXT NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_turn_records_turn ON turn_records (turn_id, id);

CREATE TABLE IF NOT EXISTS provider_sessions (
  conversation_id  INTEGER NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
  provider_name    TEXT NOT NULL,
  session_id       TEXT NOT NULL,
  PRIMARY KEY (conversation_id, provider_name)
) STRICT;
"""

#: The column `0003` deliberately did not pre-carry, and its index. Apart from `SCHEMA` because it is
#: an `ALTER` rather than a `CREATE IF NOT EXISTS`: SQLite refuses to add a column that is already
#: there, so this one is asked about first — check, then act.
#:
#: `ON DELETE SET NULL` rather than `CASCADE`: a conversation going takes its turns and its messages
#: with it, and a message pointing at a turn that is being deleted in the same sweep must not stand
#: in the way of it.
TURN_ON_A_MESSAGE = """
ALTER TABLE conversation_messages
  ADD COLUMN turn_id INTEGER REFERENCES turns (id) ON DELETE SET NULL;
"""

INDEX_ON_THAT_COLUMN = """
CREATE INDEX IF NOT EXISTS idx_messages_turn ON conversation_messages (turn_id);
"""

#: The search, and the three triggers that keep it true. `content=` makes this an **external content**
#: table: the body is indexed here and stored only in `conversation_messages`, so nothing is held
#: twice. `content_rowid=` is what ties a row in the index back to the message it came from.
#:
#: The `'delete'` command form on the two that remove is FTS5's own, and it is not optional: an
#: external-content index cannot find the old row by itself, so it has to be handed the values that
#: were indexed or the entry is orphaned and the next search matches a message that is gone.
SEARCH = """
CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_fts USING fts5(
  body,
  content='conversation_messages',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS conversation_messages_after_insert
AFTER INSERT ON conversation_messages BEGIN
  INSERT INTO conversation_messages_fts (rowid, body) VALUES (new.id, new.body);
END;

CREATE TRIGGER IF NOT EXISTS conversation_messages_after_delete
AFTER DELETE ON conversation_messages BEGIN
  INSERT INTO conversation_messages_fts (conversation_messages_fts, rowid, body)
    VALUES ('delete', old.id, old.body);
END;

CREATE TRIGGER IF NOT EXISTS conversation_messages_after_update
AFTER UPDATE ON conversation_messages BEGIN
  INSERT INTO conversation_messages_fts (conversation_messages_fts, rowid, body)
    VALUES ('delete', old.id, old.body);
  INSERT INTO conversation_messages_fts (rowid, body) VALUES (new.id, new.body);
END;
"""

#: What every message already written has to be put into the index, once, when it is first built. An
#: agent carrying forward has a conversation behind it, and a search that could only find what was
#: said after the upgrade would be a search somebody stops trusting on their first try.
BACKFILL = """
INSERT INTO conversation_messages_fts (rowid, body)
  SELECT id, body FROM conversation_messages;
"""

#: The three triggers by name, for taking them away again.
#:
#: **A trigger that outlives its table is worse than no search at all.** It fires on every insert into
#: `conversation_messages` and refers to a table that is not there, so the write fails — and the write
#: it fails is a message arriving on a channel. The agent stops being able to record anything anybody
#: says to it, which is a far larger failure than the search it was meant to serve.
#:
#: Nothing in rundesk drops that table, so the state this guards against comes from a repair, a hand
#: edit, or a restore from a backup taken on a machine whose SQLite had the module when this one does
#: not. A step is written to be safe against an agent that does not need it, and healing this is what
#: that means here.
TRIGGERS = ("conversation_messages_after_insert", "conversation_messages_after_delete",
            "conversation_messages_after_update")


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Lay down the turns, the records, the sessions, the column and — where it is possible — the
    search. Leaves anything already there alone.

    `where` is this agent's own directory. This step changes no files in it, and takes it because the
    contract every step is written to is the same one.
    """
    for statement in statements(SCHEMA):
        conn.execute(statement)

    if "turn_id" not in _columns(conn, "conversation_messages"):
        # Check, then act. `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS`, and a step has to be safe
        # against an agent that does not need it.
        for statement in statements(TURN_ON_A_MESSAGE):
            conn.execute(statement)
    for statement in statements(INDEX_ON_THAT_COLUMN):
        conn.execute(statement)

    if not _already_indexed(conn):
        # **Before anything else, and whatever happens next.** A trigger left behind by a table that
        # is gone breaks every message this agent would ever record — see `TRIGGERS`.
        _without_the_triggers(conn)

    if not _can_search(conn):
        # No index, no triggers, and an agent that carries perfectly well. Searching then falls back
        # to a scan, and says that it did — see `providers.kept.search_messages`.
        return
    already = _already_indexed(conn)
    for statement in statements(SEARCH):
        conn.execute(statement)
    if not already:
        for statement in statements(BACKFILL):
            conn.execute(statement)


def _without_the_triggers(conn: sqlite3.Connection) -> None:
    """Take away any trigger whose table is not there. See `TRIGGERS` for what this prevents."""
    for one in TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {one}")


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Which columns a table has now. `table` is named literally here and is never a caller's word."""
    return [str(one[1]) for one in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _can_search(conn: sqlite3.Connection) -> bool:
    """Whether this SQLite was built with full-text search. **Asked, never attempted.**

    A `CREATE VIRTUAL TABLE` for a module that is not there raises inside the transaction the runner
    opened, which rolls the whole agent back — so an agent on a Python whose SQLite lacks the module
    would refuse to carry at all, over a verb it can live without.

    `pragma_compile_options` is a table-valued function rather than a statement with side effects, so
    asking costs nothing and cannot poison anything. An older SQLite that does not have the function
    answers by raising, and that is read as *no*: the honest answer when the question cannot be put.
    """
    try:
        asked = conn.execute(
            "SELECT 1 FROM pragma_compile_options WHERE compile_options = 'ENABLE_FTS5'")
        return asked.fetchone() is not None
    except sqlite3.DatabaseError:
        return False


def _already_indexed(conn: sqlite3.Connection) -> bool:
    """Whether the index is already there, so a re-run does not put every message in it twice."""
    asked = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("conversation_messages_fts",))
    return asked.fetchone() is not None


def statements(said: str) -> Iterator[str]:
    """Split SQL into statements the way SQLite itself would, one at a time.

    Written out here rather than imported from `0001`, `0002` or `0003`, because a step may not
    import anything of rundesk's — including another step. A step written today runs against an agent
    carried forward years from now, by a runner that loads it from a file, and the file beside it may
    have moved.

    **Not `said.split(";")`**, and this is the step that proves why: a trigger body above contains
    semicolons of its own, so the obvious replacement would hand SQLite half a trigger.
    """
    building = ""
    for line in said.splitlines(True):
        building += line
        if sqlite3.complete_statement(building):
            yield building
            building = ""
    if building.strip():
        raise ValueError(f"this step ends in a statement with no terminator: {building.strip()!r}")
