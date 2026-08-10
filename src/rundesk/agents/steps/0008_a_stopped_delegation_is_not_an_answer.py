"""Give an owner-requested stop its own durable terminal outcome.

``answered_at`` means the result was returned for review.  A requested stop deliberately creates no
review turn, so writing that moment there makes listings and surfaces claim an answer came back.
This nullable column keeps the two terminal outcomes distinct without rewriting the shipped table.

Imports nothing of rundesk's, never ends the runner's transaction, and is safe to run again.
"""

import sqlite3
from pathlib import Path
from typing import List

STOPPED_OUTCOME = """
ALTER TABLE delegations ADD COLUMN stopped_at TEXT;
"""
WAITING_INDEX = """
CREATE INDEX idx_delegations_waiting ON delegations(to_agent)
WHERE answered_at IS NULL AND stopped_at IS NULL;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Add the stop outcome where the delegation table exists and does not already hold it."""
    if "delegations" not in _tables(conn):
        return
    if "stopped_at" not in _columns(conn, "delegations"):
        conn.execute(STOPPED_OUTCOME)
    conn.execute("DROP INDEX IF EXISTS idx_delegations_waiting")
    conn.execute(WAITING_INDEX)


def _tables(conn: sqlite3.Connection) -> List[str]:
    """Which tables this agent has now."""
    return [str(one[0]) for one in
            conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Which columns the literally named table has."""
    return [str(one[1]) for one in conn.execute(f"PRAGMA table_info({table})").fetchall()]
