"""Keep the exact agents this agent may delegate to.

``NULL`` preserves the historical default of every other agent.  A JSON array is an explicit
allowlist, including the empty array for an inbound-only agent.  Imports nothing of rundesk's and
is safe to run again against an agent that already has the column.
"""

import sqlite3
from pathlib import Path
from typing import List

DELEGATION_SCOPE = """
ALTER TABLE config ADD COLUMN delegates_to TEXT
  CHECK (delegates_to IS NULL OR
         (json_valid(delegates_to) AND json_type(delegates_to) = 'array'));
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Add the nullable policy column where it is absent."""
    if "delegates_to" not in _columns(conn, "config"):
        conn.execute(DELEGATION_SCOPE)


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Which columns the literally named table has."""
    return [str(one[1]) for one in conn.execute(f"PRAGMA table_info({table})").fetchall()]
