"""When the phase of work a delegation is *currently* in began. 0.41.0.

`0005` gave a delegation one clock — `created_at`, the moment the work first went out — and every
elapsed time a room is shown was counted from it. That is right until work is **carried on**, and
then it is wrong in a way somebody watching a channel sees immediately:

> `rundesk asked elena resume del-7-aabbcc` — and the room said *"⏳ elena still working · 1h"*
> on the very next beat, before elena had done a second of the new work.

The resumed phase inherited the whole age of the original, so the first check-in was overdue the
instant it began, the number beside it described a stretch of time nobody was waiting through, and
the answer that eventually came back was reported as having taken an hour when it took four minutes.
Measured on a real Discord channel; this step is what makes the honest number storable.

## Why a column and not arithmetic

There is nothing already written down that answers it. `latest_at` moves for every steer and every
stop, so counting from it would restart the clock each time somebody said a word into work that is
running — which is the *opposite* of the rule the sweep is written to, and would have made a busy
delegation permanently look as though it had just begun. `answered_at` is cleared by the resume, so
the moment the answer landed is gone by the time anybody could subtract from it. The phase's own
start is a fact about the delegation that nothing else records, so it is recorded.

**`0005` is not touched.** It has shipped in 0.40.0, its id is how every install on every machine
knows it has run, and a step that needs changing is a new step. This one adds a column and rebuilds
nothing.

## Why it is nullable, and backfilled anyway

`ALTER TABLE ADD COLUMN` cannot add `NOT NULL` without a constant default, and the honest default
here is per-row: a delegation that has never been carried on began its only phase when it was
created. So the column is added nullable, filled from `created_at` for every row already there, and
read with the same fallback in `delegations.kept` — a row written by an older release and never
carried on answers exactly as it always did.

**Backfilling from `created_at` is not a guess.** Before this release nothing could carry work on and
have the clock notice, so every existing row is in its first phase by construction, and its first
phase began when it was made.

Imports nothing of rundesk's, never `executescript`, never ends the runner's transaction, and is safe
against an agent that does not need it.
"""

import sqlite3
from pathlib import Path
from typing import Iterator, List

#: When the phase of work this delegation is in began: the moment it was handed over, or the moment
#: it was last carried on.
#:
#: **Moved by `reopened` and by nothing else.** A steer and a stop request both move `latest_at` and
#: must leave this alone — somebody putting words into work that is running has not restarted that
#: work, and a person who has been waiting an hour has been waiting an hour whatever was said into
#: it meanwhile. Only carrying on begins a new stretch of waiting, because only carrying on is new
#: work.
WHEN_THIS_PHASE_BEGAN = """
ALTER TABLE delegations ADD COLUMN working_since TEXT;
"""

#: Every row already there is in its first phase, and its first phase began when it was made. Run
#: once, guarded by the column being absent, so an agent carried forward twice is not rewritten the
#: second time — and written as `IS NULL` as well, so a row inserted between the `ALTER` and this by
#: nothing at all is still covered.
FROM_WHEN_IT_WAS_MADE = """
UPDATE delegations SET working_since = created_at WHERE working_since IS NULL;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Give every delegation a phase start, where it has not got one.

    `where` is this agent's own directory. This step changes no files in it, and takes it because the
    contract every step is written to is the same one.

    Safe against an agent with no `delegations` table at all: that is an agent whose records predate
    `0005`, and the runner runs the steps in order, so by the time this one runs the table is there.
    Checked anyway rather than assumed — a step that raises on an install nobody anticipated is a
    carry that stops halfway.
    """
    if "delegations" not in _tables(conn):
        return
    if "working_since" in _columns(conn, "delegations"):
        return
    # Check, then act. `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS`, and a step has to be safe
    # against an agent that does not need it.
    for statement in statements(WHEN_THIS_PHASE_BEGAN):
        conn.execute(statement)
    for statement in statements(FROM_WHEN_IT_WAS_MADE):
        conn.execute(statement)


def _tables(conn: sqlite3.Connection) -> List[str]:
    """Which tables this agent has now."""
    return [str(one[0]) for one in
            conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Which columns a table has now. `table` is named literally here and is never a caller's word."""
    return [str(one[1]) for one in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def statements(said: str) -> Iterator[str]:
    """Split SQL into statements the way SQLite itself would, one at a time.

    Written out here rather than imported from an earlier step, because a step may not import
    anything of rundesk's — including another step. A step written today runs against an agent
    carried forward years from now, by a runner that loads it from a file, and the file beside it may
    have moved.
    """
    building = ""
    for line in said.splitlines(True):
        building += line
        if sqlite3.complete_statement(building):
            yield building
            building = ""
    if building.strip():
        raise ValueError(f"this step ends in a statement with no terminator: {building.strip()!r}")
