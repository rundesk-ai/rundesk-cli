"""Keep an opted-in lifecycle handoff beside the exact turn that requested it. 0.46.0.

The row contains only local database identities, bounded product outcomes, and observed process
facts. Prompts, provider handles, channel/person identifiers, agent names, credentials, and paths
remain in the records that already own them.

Lifecycle and continuation have separate states. A claim moves atomically to ``resuming`` before a
provider is started, so a crash may leave an auditable at-most-once outcome but can never replay a
turn with side effects.

Imports nothing of rundesk's, never ends the runner's transaction, and is safe to run again.
"""

import sqlite3
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS lifecycle_continuations (
  id                    INTEGER PRIMARY KEY,
  operation             TEXT NOT NULL CHECK (operation IN ('update', 'gateway-restart')),
  origin_turn_id        INTEGER NOT NULL REFERENCES turns (id) ON DELETE CASCADE,
  origin_message_id     INTEGER NOT NULL REFERENCES conversation_messages (id),
  requested_pid         INTEGER,
  lifecycle_state       TEXT NOT NULL DEFAULT 'requested'
                          CHECK (lifecycle_state IN
                            ('requested', 'running', 'succeeded', 'failed')),
  lifecycle_outcome     TEXT NOT NULL DEFAULT '',
  continuation_state    TEXT NOT NULL DEFAULT 'requested'
                          CHECK (continuation_state IN
                            ('requested', 'suppressed', 'resuming', 'delivered')),
  continuation_outcome  TEXT NOT NULL DEFAULT '',
  observed_version      TEXT,
  observed_pid          INTEGER,
  requested_at          TEXT NOT NULL,
  finished_at           TEXT,
  resumed_at            TEXT,
  UNIQUE (origin_turn_id, operation)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_lifecycle_continuations_actionable
  ON lifecycle_continuations (lifecycle_state, continuation_state, id);
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Lay down the handoff ledger, leaving an existing one untouched."""
    for statement in statements(SCHEMA):
        conn.execute(statement)


def statements(said: str) -> Iterator[str]:
    """Split SQL into complete statements without ending the runner's transaction."""
    building = ""
    for line in said.splitlines(True):
        building += line
        if sqlite3.complete_statement(building):
            yield building
            building = ""
    if building.strip():
        raise ValueError(f"this step ends in a statement with no terminator: {building.strip()!r}")
