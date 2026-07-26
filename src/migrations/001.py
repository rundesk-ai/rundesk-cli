"""The shape an agent starts with — and the only definition of it there is.

Creating an agent runs this, rather than building the tables directly, so the migration path
is exercised every time anybody adds an agent. A step that has rotted is then found by the
next person who makes an agent, not months later by an owner in the middle of an update — and
a fresh install cannot drift from an upgraded one, because there is only one way to arrive.

Read the schema here. There is no second copy of it to disagree with.
"""

SCHEMA = """
CREATE TABLE agent (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    provider      TEXT,
    model         TEXT,
    -- What every turn for this agent is told before it reads a prompt, where neither the
    -- surface nor the schedule said. The fallback the other two inherit from; no command
    -- sets it yet, which is why a channel's are the only ones an owner can write today.
    instructions  TEXT,
    settings      TEXT NOT NULL DEFAULT '{}'
) STRICT;

CREATE TABLE gateway (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    last_seen_at  TEXT
) STRICT;

CREATE TABLE channel (
    name          TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    enabled       INTEGER NOT NULL DEFAULT 1,
    -- Which brain answers what arrives here, where the turn did not say. Part of the same
    -- fallback as the agent's; no option sets them yet.
    provider      TEXT,
    model         TEXT,
    instructions  TEXT,
    allow         TEXT NOT NULL,
    secret        TEXT,
    settings      TEXT NOT NULL DEFAULT '{}',
    describes     TEXT,
    fills         TEXT NOT NULL DEFAULT '[]',
    activity      INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
) STRICT;

CREATE TABLE schedule (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,
    enabled           INTEGER NOT NULL DEFAULT 1,
    cron              TEXT NOT NULL,
    command           TEXT,
    prompt            TEXT,
    -- Which brain answers work this schedule starts, and what it is told before it reads
    -- the prompt. Nothing sets them yet: a schedule that asks a turn rather than running a
    -- program is Phase 6, and `prompt` and the CHECK below are the shape it needs.
    provider          TEXT,
    model             TEXT,
    instructions      TEXT,
    last_auto_run_at  TEXT,
    last_outcome      TEXT,
    created_at        TEXT NOT NULL,
    CHECK ((command IS NULL) <> (prompt IS NULL))
) STRICT;

CREATE TABLE conversation (
    id         TEXT PRIMARY KEY,
    channel    TEXT NOT NULL,
    kind       TEXT NOT NULL,
    space      TEXT NOT NULL,
    thread     TEXT NOT NULL DEFAULT '',
    -- What this conversation branched from, where a surface has threads (R-STO-9). No
    -- adapter reports one yet, so nothing sets it; it is the shape the requirement names
    -- rather than a field waiting for a use to be found for it.
    parent_id  TEXT REFERENCES conversation(id),
    opened_at  TEXT NOT NULL,
    last_at    TEXT NOT NULL,
    UNIQUE (channel, space, thread)
) STRICT;

CREATE INDEX conversation_in_space ON conversation(channel, space, last_at);

CREATE TABLE session (
    conversation_id  TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    brain            TEXT NOT NULL,
    handle           TEXT NOT NULL,
    PRIMARY KEY (conversation_id, brain)
) STRICT;

CREATE TABLE run (
    n                   INTEGER PRIMARY KEY AUTOINCREMENT,
    id                  TEXT NOT NULL UNIQUE,
    conversation_id     TEXT REFERENCES conversation(id),
    schedule_id         INTEGER REFERENCES schedule(id),
    source              TEXT NOT NULL,
    trigger_message_id  INTEGER,
    provider            TEXT NOT NULL,
    brain               TEXT NOT NULL,
    model               TEXT,
    posture             TEXT NOT NULL,
    can                 TEXT NOT NULL DEFAULT '{}',
    settings            TEXT NOT NULL DEFAULT '{}',
    resumed             INTEGER NOT NULL DEFAULT 0,
    started_at          TEXT NOT NULL,
    ended_at            TEXT,
    outcome             TEXT,
    why                 TEXT,
    exit_code           INTEGER,
    tokens_in           INTEGER,
    tokens_out          INTEGER,
    tokens_cached       INTEGER,
    tokens_reported     INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE INDEX run_in_conversation ON run(conversation_id, n);
CREATE INDEX run_by_schedule     ON run(schedule_id, n);

CREATE TABLE message (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    run_id           TEXT REFERENCES run(id),
    -- The platform's own id for this message, which is what makes work arriving twice from
    -- one surface recorded once (R-STO-6) — enforced by `message_once` below rather than by
    -- anything remembering to check. No adapter passes one through the seam yet.
    external_id      TEXT,
    at               TEXT NOT NULL,
    author           TEXT NOT NULL,
    who              TEXT,
    text             TEXT NOT NULL
) STRICT;

CREATE INDEX message_in_conversation ON message(conversation_id, id);
CREATE INDEX message_by_time         ON message(at);

CREATE UNIQUE INDEX message_once ON message(conversation_id, external_id)
    WHERE external_id IS NOT NULL;

CREATE TABLE record (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  TEXT NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    seq     INTEGER NOT NULL,
    at      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    event   TEXT,
    raw     TEXT,
    UNIQUE (run_id, seq)
) STRICT;
"""

# Asked for, never assumed. FTS5 is a compile-time option rather than a guarantee, so a machine
# without it still lists, reads and queries every run — only searching by the words in something
# is missing, and `doctor` is what says so.
#
# External content: the index holds no copy of the text, only what is needed to find it. The
# three triggers keep it in step, including when a conversation goes and takes its messages with
# it — firing a delete for a row the index never held is the canonical way to corrupt an FTS5
# index, which is why these are created with the table and never after rows exist.
SEARCH = """
CREATE VIRTUAL TABLE message_fts USING fts5(
    text, content='message', content_rowid='id', tokenize='unicode61');

CREATE TRIGGER message_fts_insert AFTER INSERT ON message BEGIN
    INSERT INTO message_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER message_fts_delete AFTER DELETE ON message BEGIN
    INSERT INTO message_fts(message_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER message_fts_update AFTER UPDATE ON message BEGIN
    INSERT INTO message_fts(message_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO message_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


def _statements(script):
    """Split a script the way SQLite itself would, and never on the semicolons.

    Deliberately a copy rather than an import of the identical helper in `store.py`. A step
    describes a shape that existed at one moment, so it must not change meaning the day
    today's code does — and a ten-line splitter is a cheap price for a step that will still
    be correct in five years. See `README.md` here.
    """
    import sqlite3

    gathered = ""
    for line in script.splitlines(keepends=True):
        gathered += line
        if sqlite3.complete_statement(gathered):
            said = gathered.strip()
            if said and not said.startswith("--"):
                yield said
            gathered = ""


def _fts5(conn):
    """Whether this machine's SQLite can search. Asked by trying it, not by reading a version."""
    import sqlite3

    try:
        conn.execute("CREATE VIRTUAL TABLE temp.probing_fts5 USING fts5(x)")
    except sqlite3.OperationalError:
        return False
    conn.execute("DROP TABLE temp.probing_fts5")
    return True


def up(conn, home):
    """Build it, inside the transaction the runner opened. Never commit, never delete."""
    for statement in _statements(SCHEMA):
        conn.execute(statement)
    if _fts5(conn):
        for statement in _statements(SEARCH):
            conn.execute(statement)
    conn.execute("INSERT INTO agent (id) VALUES (1)")
    conn.execute("INSERT INTO gateway (id) VALUES (1)")
    return []
