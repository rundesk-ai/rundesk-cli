"""Give every agent an explicit operating role.

Domain is the compatible default: every agent created before roles existed owned its ongoing work,
and carrying it forward must not silently turn it into a bounded specialist. The database constraint
keeps the public vocabulary exact rather than relying on every writer to agree.

Imports nothing of rundesk's, never ends the runner's transaction, and is safe to run again.
"""

import sqlite3
from pathlib import Path
from typing import List

ROLE = """
ALTER TABLE config ADD COLUMN role TEXT NOT NULL DEFAULT 'domain'
  CHECK (role IN ('domain', 'specialist'));
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Add the domain-default role where it is absent."""
    if "role" not in _columns(conn, "config"):
        conn.execute(ROLE)


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Which columns the literally named table has."""
    return [str(one[1]) for one in conn.execute(f"PRAGMA table_info({table})").fetchall()]
