"""Carry the optional additional account through config, turns, delegations, and sessions.

``NULL`` remains the provider's ordinary account everywhere provenance is recorded. Sessions need a
non-null primary-key member, so only that table normalizes the same answer to ``''``. Existing rows
are copied into that default partition. Imports nothing of rundesk, never ends the runner's
transaction, and is safe to run again.
"""

import sqlite3
from pathlib import Path
from typing import List

ALIASES = (
    ("config", "provider_alias"),
    ("turns", "provider_alias"),
    ("delegations", "requested_provider_alias"),
    ("delegations", "provider_alias"),
)

SESSION_SCHEMA = """
CREATE TABLE new_provider_sessions (
  conversation_id  INTEGER NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
  provider_name    TEXT NOT NULL,
  provider_alias   TEXT NOT NULL DEFAULT ''
                     CHECK (provider_alias = '' OR lower(provider_alias) <> 'default'),
  session_id       TEXT NOT NULL,
  PRIMARY KEY (conversation_id, provider_name, provider_alias)
) STRICT;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Add nullable provenance and rebuild the session identity only where needed."""
    tables = set(_tables(conn))
    for table, column in ALIASES:
        if table in tables and column not in _columns(conn, table):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} TEXT "
                f"CHECK ({column} IS NULL OR ({column} <> '' AND lower({column}) <> 'default'))"
            )
    if "provider_sessions" not in tables:
        return
    if "provider_alias" in _columns(conn, "provider_sessions"):
        return
    conn.execute(SESSION_SCHEMA)
    conn.execute(
        "INSERT INTO new_provider_sessions "
        "(conversation_id, provider_name, provider_alias, session_id) "
        "SELECT conversation_id, provider_name, '', session_id FROM provider_sessions"
    )
    conn.execute("DROP TABLE provider_sessions")
    conn.execute("ALTER TABLE new_provider_sessions RENAME TO provider_sessions")


def _tables(conn: sqlite3.Connection) -> List[str]:
    return [str(row[0]) for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
