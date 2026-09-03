"""The one destination a schedule reports to, when it is not the agent's notified channel.

`schedules` already carried `channel` and `channel_place_id`, written by nothing: step `0002` put
them there on the argument that a column added later is a migration for every agent on every
machine, and the verb that would write them had not been asked for yet. It has been. What those two
could not say is the other kind of destination — **one person's direct message** — because a place
id and a sender id are different facts about a platform and a column that held either would be a
column no reader could interpret.

So `channel_sender_id` joins them, and the three are read as a closed tri-state:

| `channel` | `channel_place_id` | `channel_sender_id` | What it means |
|---|---|---|---|
| `NULL` | `NULL` | `NULL` | no destination of its own — the agent's notified channel, as before |
| set | set | `NULL` | that place on that channel |
| set | `NULL` | set | that person's direct message on that channel |

**Every row already on disk is the first line of that table**, so nothing is back-filled and nothing
has to be: no release before this one wrote either of the two columns it already had, and *both
empty* is exactly what *no destination* means. A default would have been the one way to get this
wrong — a column defaulting to the notified channel would turn *nobody chose* into *somebody chose
this*, and the two have to stay apart because only one of them is a thing an owner can be shown.

**The pair is refused by the records rather than trusted**, which is step `0002`'s own argument about
the two `CHECK`s it wrote: a row naming a place *and* a person names two destinations and one report
cannot go to both, and a reader finding one at two in the morning has no honest way to pick. The
constraint arrives with the column, so it is satisfied by every row already here — nothing has ever
written `channel_sender_id`, so `channel_sender_id IS NULL` holds throughout.

**What that costs is stated rather than hidden.** A cross-column `CHECK` added by `ALTER TABLE` can
only be taken off again by rebuilding the table, and this package's own notes say a rebuild here
cannot follow SQLite's documented procedure. So a future release that wants one schedule to report
to a place *and* a direct message pays for it. That is the right way round: the invariant is true
today, a row that breaks it is unreadable rather than merely odd, and the alternative is every
reader re-asking a question the table could have answered.

The remaining half of the tri-state — that `channel` and exactly one id stand or fall together — is
not expressible here without disturbing what the two older columns are already allowed to hold, and
is refused by `schedules.kept` before anything is written.

Imports nothing of rundesk's, never `executescript`, never ends the runner's transaction, and is
safe against an agent that does not need it.
"""

import sqlite3
from pathlib import Path
from typing import List

#: What is added to `schedules`, and the one thing the records refuse. Nullable because *no
#: destination* is the ordinary answer and has to stay tellable from a destination that is a place.
COLUMN = ("channel_sender_id",
          "TEXT CHECK (channel_sender_id IS NULL OR channel_place_id IS NULL)")


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Give `schedules` the direct message one may report to. Leaves an agent without that table.

    `where` is this agent's own directory. This step changes no files in it, and takes it because
    the contract every step is written to is the same one.
    """
    if "schedules" not in _tables(conn):
        # Unreachable in the ordinary order, where `0002` has already laid the table down — and
        # checked anyway, because rule 5 is that a step never assumes the shape it starts from.
        return
    if COLUMN[0] in _columns(conn, "schedules"):
        # Check, then act. `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS`, and a step has to be
        # safe against an agent that does not need it.
        return
    conn.execute(f"ALTER TABLE schedules ADD COLUMN {COLUMN[0]} {COLUMN[1]}")


def _tables(conn: sqlite3.Connection) -> List[str]:
    """Which tables this agent has now."""
    return [str(one[0]) for one in
            conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Which columns the literally named table has. `table` is never a caller's word."""
    return [str(one[1]) for one in conn.execute(f"PRAGMA table_info({table})").fetchall()]
