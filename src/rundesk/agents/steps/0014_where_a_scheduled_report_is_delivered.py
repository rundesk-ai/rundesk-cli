"""Who an agent is whatever it is called, and where one schedule's finished report is delivered.

A schedule may name another agent to hand its finished report to. Three things have to be durable
before that is safe, and all three are here because they are one change: **who the target is**,
**what one schedule was told**, and **what one finished run still owes**.

## An agent's name is not an identity, and a name-only reference is the bug

`config` held `agent_name` and nothing else that survives being renamed or re-made. A schedule that
carried only a name would follow that name to whoever holds it next: remove `bob`, make a new `bob`
next week for something else entirely, and last month's nightly report is delivered into a stranger
— silently, because every name involved still matches. `agent_identity` is minted once per agent and
never rewritten, so *the agent this schedule was pointed at* is a question with a durable answer.

**Minted here for every agent that already has a configuration row.** An agent being made this
minute has none yet — its row is written after the steps run — so `agents.directory` mints one in
the same write that names it. Two places, because there are two moments an agent comes into
existence, and neither may leave the column empty.

**Never rewritten, by anything.** `agents.records.stated` refuses to set it and the sweep below
reads it. A rewritten identity is the same silent redirection this column exists to prevent, aimed
at the other end.

## What a schedule was told is two columns, and the pair is held by the records

`deliver_to_agent` is the name, so a person can read it back and every message can say it out loud.
`deliver_to_identity` is who that was at the moment somebody typed it. Both or neither: a target
with no identity would be a name-only reference again, and an identity with no name is nothing
anybody could read.

**Only a schedule that asks an agent may carry one, and the records refuse the rest.** A schedule
that starts a program has no report — `docs/schedules.md` says the promise to report back is one
rundesk would not be keeping — so a delivery target on one is a promise nothing could keep. The
`CHECK` rides on the column rather than on the table because a table-level one cannot be added to a
table that already exists without rebuilding it, and it holds both directions: a target may not be
set on a schedule that names a program, and a schedule carrying a target may not be turned into one.

## What an invocation owes is frozen before work, because completion must survive a crash

`schedule_delivery_obligations` keeps the target pair and run key before the child starts. The
firing settles it before removing its recovery record. A gateway that stops between observing
success and writing the outbox therefore leaves both the exact outcome and an unresolved obligation
for its replacement to retry. The same obligation remains through a delegated review, whose final
turn may settle before the reporting thread can enqueue it.

`schedule_deliveries` is the source agent's own outbox. A run that completed writes one row and is
done with it; the recipient's gateway reads it out of this store, read-only, whenever it next comes
up. A recipient that is offline, busy, or has not existed for an hour costs the report nothing.

**`run_key` is `UNIQUE`, and that is the whole of the exactly-once guarantee.** It is the scheduled
invocation's own conversation id — one conversation per invocation, written before the work starts —
so a gateway that reports a run twice, one that adopts a firing another one started, and a restart
between the report and the write all insert the same key and the second one does nothing.

**`to_identity` is copied from the frozen obligation**, not reread from the schedule. Adding,
clearing, or changing a target while a run works affects the next invocation only.

`schedule_delivery_marks` is the other end of the same sweep: how far into one source's outbox this
agent has already read. Keyed by the source's **identity** and not its name — a source removed and
re-made under the same name starts its own row ids at one again, and a mark keyed by name would
swallow the new agent's first deliveries as though they had already been read.

Once the source sees that mark, it writes `acknowledged_at` on its own outbox row. The recipient's
mark may then disappear with that agent without turning an admitted report back into an unread one.

Imports nothing of rundesk's, never `executescript`, never ends the runner's transaction, and is
safe against an agent that does not need any of it.
"""

import secrets
import sqlite3
from pathlib import Path
from typing import Iterator, List

#: How long a minted identity is, in bytes of randomness. Sixteen is what this product already uses
#: for an invocation's own mark, and it is far past anything a machine full of agents could collide
#: on by accident.
IDENTITY_BYTES = 16

#: What is added to `schedules`, in this order — the second `CHECK` names the first column, so the
#: pair cannot be added the other way round.
#:
#: **A column `CHECK` and not a table one.** `ALTER TABLE … ADD COLUMN` is the only widening SQLite
#: offers a table that already exists, and a table-level constraint needs the twelve-step rebuild
#: `steps/__init__.py` says cannot be followed from inside a live transaction. A column constraint
#: may name other columns and is enforced on every later write, which is the guarantee wanted here.
COLUMNS = (
    ("deliver_to_agent",
     "TEXT CHECK (deliver_to_agent IS NULL OR prompt IS NOT NULL)"),
    ("deliver_to_identity",
     "TEXT CHECK ((deliver_to_identity IS NULL) = (deliver_to_agent IS NULL))"),
)

#: The one column added to `config`. Nullable, because an agent being made this minute has no
#: configuration row for this step to write into and `agents.directory` fills it a moment later.
IDENTITY_COLUMN = ("agent_identity", "TEXT")

#: What a completed run owes, and how far this agent has read of somebody else's owing.
#:
#: `report` is the finished report itself rather than a pointer into the source's conversations: the
#: recipient reads this store read-only and across a boundary, and a delivery that had to join two
#: tables of a store it does not own would break the day either of them is swept.
SCHEMA = """
CREATE TABLE IF NOT EXISTS schedule_deliveries (
  id            INTEGER PRIMARY KEY,
  schedule_name TEXT NOT NULL,
  run_key       TEXT NOT NULL UNIQUE,
  ran_at        TEXT NOT NULL,
  to_agent      TEXT NOT NULL,
  to_identity   TEXT NOT NULL,
  report        TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  acknowledged_at TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS idx_schedule_deliveries_addressed
  ON schedule_deliveries (to_agent, id);

CREATE TABLE IF NOT EXISTS schedule_delivery_obligations (
  run_key       TEXT PRIMARY KEY,
  schedule_name TEXT NOT NULL,
  began_at      TEXT NOT NULL,
  to_agent      TEXT NOT NULL,
  to_identity   TEXT NOT NULL,
  outcome       TEXT NOT NULL DEFAULT 'running'
                  CHECK (outcome IN ('running', 'done', 'failed', 'stopped')),
  settled_at    TEXT,
  resolved_at   TEXT,
  resolution    TEXT CHECK (resolution IN ('delivered', 'source')),
  CHECK ((resolved_at IS NULL) = (resolution IS NULL))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_schedule_delivery_obligations_pending
  ON schedule_delivery_obligations (outcome, resolved_at, began_at);

CREATE TABLE IF NOT EXISTS schedule_delivery_marks (
  from_identity TEXT PRIMARY KEY,
  from_agent    TEXT NOT NULL,
  last_id       INTEGER NOT NULL,
  updated_at    TEXT NOT NULL
) STRICT;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Give this agent an identity, let a schedule name where its report goes, and lay down the
    outbox both ends of a delivery read.

    `where` is this agent's own directory. This step changes no files in it, and takes it because
    the contract every step is written to is the same one.
    """
    tables = set(_tables(conn))
    if "config" in tables:
        if IDENTITY_COLUMN[0] not in _columns(conn, "config"):
            # Check, then act. `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS`.
            conn.execute(f"ALTER TABLE config ADD COLUMN {IDENTITY_COLUMN[0]} {IDENTITY_COLUMN[1]}")
        # Only where it is empty, and only for a row that is already there. Running twice must not
        # mint a second identity: the whole value of the column is that it never changes.
        conn.execute(
            "UPDATE config SET agent_identity = ?"
            " WHERE id = 1 AND (agent_identity IS NULL OR agent_identity = '')",
            (secrets.token_hex(IDENTITY_BYTES),))
    if "schedules" in tables:
        present = set(_columns(conn, "schedules"))
        for name, kind in COLUMNS:
            if name not in present:
                conn.execute(f"ALTER TABLE schedules ADD COLUMN {name} {kind}")
    for statement in statements(SCHEMA):
        conn.execute(statement)


def _tables(conn: sqlite3.Connection) -> List[str]:
    """Which tables this agent has now."""
    return [str(one[0]) for one in
            conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Which columns the literally named table has. `table` is never a caller's word."""
    return [str(one[1]) for one in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def statements(said: str) -> Iterator[str]:
    """Split SQL into statements the way SQLite itself would, one at a time.

    Written out here rather than imported from an earlier step, because a step may not import
    anything of rundesk's — including another step. **Not `said.split(";")`**: a trigger body ends a
    statement of its own, so the obvious replacement would hand SQLite half a trigger.
    """
    building = ""
    for line in said.splitlines(True):
        building += line
        if sqlite3.complete_statement(building):
            yield building
            building = ""
    if building.strip():
        raise ValueError(f"this step ends in a statement with no terminator: {building.strip()!r}")
