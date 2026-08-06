"""The channels one agent keeps, and what was said through them. 0.38.0.

Three tables. `channels` is what an agent is reachable through; `conversations` and
`conversation_messages` are what came of it. They arrive together because a channel with nowhere to
record what arrives is a channel that can only be configured, and this release receives.

**A channel is a connection, not a place, and `kind` being unique is the whole of that.** One
Discord bot per agent, reaching private messages and every room it has been invited to, with nothing
per-place written down anywhere. The build this replaces did the opposite — one `add` wrote a channel
per *kind of place*, private messages and rooms as separate rows with separate lists of who may use
them — and that shape exists to govern a public room full of strangers who are not the people allowed
to send a private message. Nothing here governs strangers: one list of ids says who may reach this
agent, and it says so wherever they say it.

What that removes is the point. There is no name to invent, because the channel is its platform.
There is no place to look up and paste, because a room is discovered when somebody speaks in it. And
there is no second `add`, because there is nothing a second one would say.

**Where a reply goes is never configured**, because it is wherever the message came from.
`notify_place` is the one exception and the reason it is a column: a gateway that has just come up is
answering nobody, so it has no conversation to reply into, and something has to say where that lands.
The `CHECK` holds the pair together — a channel that is the notified one and has nowhere to notify is
a row that would be found broken at the moment it was needed, which for a gateway notice is the
moment somebody's agent has stopped.

**`allowed` is the security boundary, and the `CHECK` is why it cannot be got wrong.** It holds a
JSON array of the platform ids that may reach this agent, and an empty one authorises **nobody** —
never everybody. That is a rule other people have got backwards at real cost: a gateway shipped with
a default-allow fallback for an empty recipient set, and sent approval prompts to every client
connected to it. Written as a convention it survives exactly as long as everyone who touches the
column remembers it. Note the failure is `OperationalError: malformed JSON` rather than a constraint
failure when the column is handed something that is not JSON at all, so the layer above still
validates on the way in — this is the floor, not the whole of it.

**And the floor is laid under every JSON column here, not only that one.** `secret_names` and
`settings` hold JSON in a `TEXT` column exactly as `allowed` does, and a column that is only JSON by
convention is JSON for as long as everybody who writes it remembers — which is the same argument
`allowed` already makes, applied where it was not. `json_valid` is the cheap half of it; what the
shape *means* is still the layer above's to check.

**At most one channel is the notified one**, and a partial unique index says so. Unprompted things
have exactly one place to go, and *no* place is a legitimate answer, so the index covers only the
rows that claim it.

**`conversations` carries `UNIQUE (source, source_id)` and that is the whole point of the table.**
The build this replaces derived a conversation's identity by hashing what it came from, which is what
let two exchanges weeks apart, in different processes, land on one conversation without either of
them asking anything first. An `INTEGER PRIMARY KEY` cannot do that on its own: the uniqueness has to
be stated over the thing that identifies an exchange out in the world, or two gateways racing to
record the same arriving message make two conversations for it.

**`channel` is text and deliberately not a foreign key.** Which channel an exchange arrived through
is a fact about the past. A foreign key would make removing a channel either refuse — because a
conversation still points at it — or quietly null the column under `ON DELETE SET NULL`, and both
lose history in order to keep a constraint tidy.

**`external_id` is the platform's own id for a message, and it exists to be written.** The previous
build had this column and its unique index and no adapter ever passed one through the seam, so the
guard was correct, cost a column, and prevented nothing — while the same build re-solved duplicate
delivery inside one adapter's memory, which did not survive a restart.

**What is deliberately not here.** No per-channel provider, model or instructions: step `0002`
carried provider columns forward for schedules on the argument that a column added later is a
migration for every agent on every machine, and that argument does not transfer — a schedule already
had a firing path that handles that kind, and a channel has neither a path nor a provider to run. No
`enabled`, which the previous build never once wrote as anything but true. No `turn_id` on a message,
which would be a foreign key into a table no release ships. No full-text search tables, which are
five tables and three triggers serving a verb that does not exist.

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
  kind          TEXT NOT NULL UNIQUE,
  describes     TEXT NOT NULL,
  notified      INTEGER NOT NULL DEFAULT 0 CHECK (notified IN (0, 1)),
  notify_place  TEXT,
  secret_names  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(secret_names)),
  settings      TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(settings)),
  allowed       TEXT NOT NULL CHECK (json_array_length(allowed) > 0),
  created_at    TEXT NOT NULL,
  CHECK (notified = 0 OR notify_place IS NOT NULL)
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
