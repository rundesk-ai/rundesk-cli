"""Bring this plugin's shared records up to version 1.

**A step is found, not listed.** The number in the filename *is* the version it brings the
records to, and sorting the numbers is the whole of the ordering — there is no list kept
anywhere that could disagree with the directory.

**There is no record of what has run, because the version is the record.** Rundesk runs this
inside one transaction that also stamps `PRAGMA user_version`, so the schema change, the data
change and the version commit together. "Ran but was not recorded" is not a state that can
exist.

**A step may never delete.** Removing a file is not part of any transaction. Copy instead,
and hand back what is now spare: rundesk removes those only once the version has committed,
so a step that died halfway leaves both copies rather than neither, and running it again is
safe.

**One store, not one per agent.** Every agent shares these records, so this runs once — and
it runs inside rundesk's update window with every gateway stood down, which is why it need
not compete with a live agent for the write lock.
"""

from __future__ import annotations

from pathlib import Path


def up(conn, state: Path) -> list[Path]:
    """Make the shape this release reads. Return files now spare, or an empty list.

    `conn` is already inside `BEGIN IMMEDIATE`. Do not commit, roll back, or stamp the
    version — rundesk does all three, and a step that commits early breaks the promise
    that makes running it again safe.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item (
            ref      TEXT PRIMARY KEY,
            title    TEXT NOT NULL,
            seen_at  TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS item_seen ON item(seen_at DESC)")
    return []
