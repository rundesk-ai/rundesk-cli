"""The two tables every agent has: what it is configured with, and how far it has been carried.

The first release to ship agents. This is the step that makes a directory an agent — before it has
run there is a directory, and after it has run there are records.

Both tables are `STRICT`, so a column that says `TEXT` holds text and nothing else. Without it
SQLite stores whatever it is handed under whatever affinity it feels like, and a setting written as
a number comes back as one, so the code that reads it grows a conversion nobody can later remove
because some machine somewhere has the other type on disk.

`config` is held to a single row by `CHECK (id = 1)` rather than by everyone agreeing to write only
one: an agent has exactly one configuration, and a second row is not extra information — it is two
answers to a question with one.

Imports nothing of rundesk's, and never `executescript`. Both are `steps/__init__.py`'s rules and
both matter here: this file runs inside a transaction the runner opened, and it runs on machines
whose rundesk has moved on years past the release that wrote it.
"""

import sqlite3
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
  id                  INTEGER PRIMARY KEY CHECK (id = 1),
  agent_name          TEXT NOT NULL,
  agent_provider      TEXT NOT NULL,
  agent_model         TEXT,
  agent_instructions  TEXT,
  agent_settings      TEXT NOT NULL DEFAULT '{}',
  owner_name          TEXT,
  last_seen_at        TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS migrations (
  key           TEXT PRIMARY KEY,
  completed_at  TEXT NOT NULL
) STRICT;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Lay down `config` and `migrations`, and leave anything already there alone.

    `IF NOT EXISTS` is the check-then-act this step needs, done by SQLite in the same statement so
    there is no window between the looking and the making. An agent that already has these tables —
    a run interrupted after the first `CREATE` and before the commit could not leave one, but a
    hand-repaired database could — is left exactly as it is.

    `where` is this agent's own directory. This step changes no files in it, and takes it anyway
    because the contract every step is written to is the same one.
    """
    for statement in statements(SCHEMA):
        conn.execute(statement)


def statements(said: str) -> Iterator[str]:
    """Split SQL into statements the way SQLite itself would, one at a time.

    **Not `executescript`**, which issues an implicit `COMMIT` before it runs and so silently drops
    the transaction the runner opened around this step. And **not `said.split(";")`**, which is the
    obvious replacement and is wrong for a reason that only shows up later: a trigger body contains
    semicolons of its own, so the first step that adds one would be handed half a trigger and a
    syntax error — and this build grows triggers the moment there is full-text search over what an
    agent has said.

    `sqlite3.complete_statement` is the parser's own answer to "is this a whole statement yet", so
    the split is SQLite's rather than a guess about its grammar.
    """
    building = ""
    for line in said.splitlines(True):
        building += line
        if sqlite3.complete_statement(building):
            yield building
            building = ""
    if building.strip():
        raise ValueError(f"this step ends in a statement with no terminator: {building.strip()!r}")
