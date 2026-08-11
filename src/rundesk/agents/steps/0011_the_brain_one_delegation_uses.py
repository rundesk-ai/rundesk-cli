"""Keep the provider and optional model selected for one delegation.

A delegation-scoped provider is admission data, not agent configuration.  These nullable columns
keep what the delegator requested and what admission resolved without changing the target agent's
durable default.  ``NULL`` in every column is the compatible answer for work admitted without an
override: its turn continues to resolve the target agent's configuration when it starts, exactly as
it did before this step.

Imports nothing of rundesk's, never ends the runner's transaction, and is safe to run again.
"""

import sqlite3
from pathlib import Path
from typing import List

PROVENANCE = (
    ("requested_provider_name", "TEXT"),
    ("requested_model_name", "TEXT"),
    ("provider_name", "TEXT"),
    ("model_name", "TEXT"),
)


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Add nullable delegation provenance where the delegation table exists."""
    if "delegations" not in _tables(conn):
        return
    present = set(_columns(conn, "delegations"))
    for name, kind in PROVENANCE:
        if name not in present:
            conn.execute(f"ALTER TABLE delegations ADD COLUMN {name} {kind}")


def _tables(conn: sqlite3.Connection) -> List[str]:
    """Which tables this agent has now."""
    return [str(one[0]) for one in
            conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Which columns the literally named table has."""
    return [str(one[1]) for one in conn.execute(f"PRAGMA table_info({table})").fetchall()]
