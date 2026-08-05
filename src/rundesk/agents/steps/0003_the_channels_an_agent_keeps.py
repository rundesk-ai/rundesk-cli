"""The channels one agent keeps, and what was said through them. 0.38.0.

Three tables. `channels` is what an agent is reachable through; `conversations` and
`conversation_messages` are what came of it. They arrive together because a channel with nowhere to
record what arrives is a channel that can only be configured, and this release receives.

**`allowed` is the security boundary, and the `CHECK` is why it cannot be got wrong.** It holds a
JSON array of the platform ids that may reach this agent here, and an empty one authorises **nobody**
— never everybody. That is a rule other people have got backwards at real cost: a gateway shipped
with a default-allow fallback for an empty recipient set, and sent approval prompts to every client
connected to it. Written as a convention it survives exactly as long as everyone who touches the
column remembers it; written as a constraint it is not something a later caller can be careless
about. Note the failure is `OperationalError: malformed JSON` rather than a constraint failure when
the column is handed something that is not JSON at all, so the layer above still validates on the way
in — this is the floor, not the whole of it.

**At most one channel is the notified one**, and a partial unique index is what says so. Unprompted
things — a gateway came up, a schedule failed — have exactly one place to go, and *no* place is a
legitimate answer, so the index covers only the rows that claim it. Two channels both claiming it is
the state that has no meaning, and this is the only way to make writing it impossible rather than
merely unusual.

**`place_kind` says how many people are there, and that is deliberately not a chat word.** It holds
`dm` or `room`, and those are the two answers because they are the two the *core* behaves differently
about: one person, private, where a reply is flat and needs no mention; or several people, shared,
where a reply may thread and the asker has to be named. An adapter for something that is not a chat
platform maps onto the same distinction rather than needing a third word — one email address is `dm`
and a distribution list is `room`, one phone number is `dm` and a group message is `room`. A thread
is not a third kind: it is where a reply goes inside a `room`, not something a channel is configured
against. Written down here because the vocabulary is the part a later adapter author has to fit into,
and because widening a `CHECK` afterwards means the table rebuild this file's last paragraph is about.

**`conversations` carries `UNIQUE (source, source_id)` and that is the whole point of the table.**
The build this replaces derived a conversation's identity by hashing what it came from, which is
what let two exchanges weeks apart, in different processes, land on one conversation without either
of them asking anything first. An `INTEGER PRIMARY KEY` cannot do that on its own: the uniqueness has
to be stated over the thing that identifies an exchange out in the world, or two gateways racing to
record the same arriving message make two conversations for it.

**`channel` is text and deliberately not a foreign key.** Which channel an exchange arrived through
is a fact about the past. A foreign key would make removing a channel either refuse — because a
conversation still points at it — or quietly null the column under `ON DELETE SET NULL`, and both of
those lose history in order to keep a constraint tidy. The name is recorded and left alone.

**`external_id` is the platform's own id for a message, and it exists to be written.** The previous
build had this column and its unique index and no adapter ever passed one through the seam, so the
guard was correct, cost a column, and prevented nothing — while the same build re-solved duplicate
delivery inside one adapter's memory, which did not survive a restart. It is here on the condition
that the acknowledgement path fills it in.

**What is deliberately not here.** No per-channel provider, model or instructions: step `0002` carried
provider columns forward for schedules on the argument that a column added later is a migration for
every agent on every machine, and that argument does not transfer — a schedule already had a firing
path that handles that kind, and a channel has neither a path nor a provider to run. No `enabled`,
which the previous build never once wrote as anything but true. No `turn_id` on a message, which
would be a foreign key into a table no release ships. No full-text search tables, which are five
tables and three triggers serving a verb that does not exist.

**The `source` vocabulary is complete rather than only what is reachable**, and that is the one place
this file is deliberately ahead of the product. Widening a `CHECK` later means rebuilding the table,
and `steps/__init__.py` records that a rebuild here cannot follow SQLite's own documented procedure —
`PRAGMA foreign_keys=OFF` is a no-op inside the runner's transaction and still answers `1`. A
vocabulary is not an offer of a feature; it is the set of words a column may hold.

Imports nothing of rundesk's, and never `executescript`. Both are `steps/__init__.py`'s rules.
"""

import sqlite3
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  kind          TEXT NOT NULL,
  place_id      TEXT NOT NULL,
  place_kind    TEXT NOT NULL CHECK (place_kind IN ('dm', 'room')),
  describes     TEXT NOT NULL,
  notified      INTEGER NOT NULL DEFAULT 0 CHECK (notified IN (0, 1)),
  secret_names  TEXT NOT NULL DEFAULT '[]',
  settings      TEXT NOT NULL DEFAULT '{}',
  allowed       TEXT NOT NULL CHECK (json_array_length(allowed) > 0),
  created_at    TEXT NOT NULL,
  UNIQUE (kind, place_id)
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_notified
  ON channels (notified) WHERE notified = 1;

CREATE TABLE IF NOT EXISTS conversations (
  id          INTEGER PRIMARY KEY,
  source      TEXT NOT NULL CHECK (source IN ('channel', 'schedule', 'terminal', 'agent', 'role')),
  source_id   TEXT NOT NULL,
  channel     TEXT,
  created_at  TEXT NOT NULL,
  UNIQUE (source, source_id)
) STRICT;

CREATE TABLE IF NOT EXISTS conversation_messages (
  id               INTEGER PRIMARY KEY,
  conversation_id  INTEGER NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
  author           TEXT NOT NULL CHECK (author IN ('agent', 'user', 'rundesk')),
  author_id        TEXT NOT NULL,
  body             TEXT NOT NULL,
  external_id      TEXT,
  created_at       TEXT NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_messages_conversation
  ON conversation_messages (conversation_id, id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_external_id
  ON conversation_messages (conversation_id, external_id) WHERE external_id IS NOT NULL;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Lay down the three tables and their indexes, and leave any already there alone.

    `IF NOT EXISTS` on every one of them is the check-then-act this step needs, done by SQLite
    inside the statement so there is no window between the looking and the making.

    **The index on `conversation_messages (conversation_id, id)` is not an optimisation to be
    trimmed.** The foreign key above it carries `ON DELETE CASCADE`, and SQLite has to find a
    parent's children to obey that — with no index on the child's key it scans the whole table for
    every conversation removed. It is also the order every read of a conversation wants, so the one
    index answers both.

    `where` is this agent's own directory. This step changes no files in it — the directory a channel
    keeps its attachments in is made by the code that downloads one, because a step that made it
    would be making a directory for channels that may never be configured.
    """
    for statement in statements(SCHEMA):
        conn.execute(statement)


def statements(said: str) -> Iterator[str]:
    """Split SQL into statements the way SQLite itself would, one at a time.

    Written out here rather than imported from `0001` or `0002`, because a step may not import
    anything of rundesk's — including another step. A step written today runs against an agent
    carried forward years from now, by a runner that loads it from a file, and the file beside it may
    have moved.
    """
    building = ""
    for line in said.splitlines(True):
        building += line
        if sqlite3.complete_statement(building):
            yield building
            building = ""
    if building.strip():
        raise ValueError(f"this step ends in a statement with no terminator: {building.strip()!r}")
