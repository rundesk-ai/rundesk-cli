"""What one agent handed to somebody else, and what it is still owed. 0.40.0.

The release that lets an agent delegate — to another named agent, or to a role it puts on. `0003`
reserved the two words this needs (`conversations.source` already accepts `'agent'` and `'role'`)
and said why the vocabulary was written complete rather than grown: *"Widening a `CHECK` later means
rebuilding the table, and a rebuild here cannot follow SQLite's own documented procedure."* So this
step adds a table and a column, and rebuilds nothing.

## One table, and the test it keeps passing

**Every column here is a thing that is neither a turn nor a message.** That is the membership rule,
and it is the whole reason this table is thirteen columns rather than thirty. Delegating decomposes
almost entirely into what already exists:

- the brief, the answer, and every steer are `conversation_messages`;
- the work is `turns`, and its outcome is `turn_status` — `working`, `done`, `stopped`, `failed`;
- who triggered the work is `conversations.source` and `source_id`;
- how much of the machine it could touch is `turns.access_mode`;
- whether its brain could be steered is `turns.provider_capabilities`;
- when it started and ended is `turns.created_at` and `ended_at`.

The previous build carried all of those a second time, in a record of its own, plus a seven-state
machine that duplicated `turn_status` outright — it had `working` beside `working` and `stopped`
beside `stopped`. None of that is here. **There is no `state` column**: what state a delegation is in
is read off the work it delegated, and the one derived value kept is `answered_at`, because that is
what makes delivering exactly once a `WHERE` clause instead of a scan of somebody else's database.

## Why the row belongs to the agent that made it

A delegation spans two agents and there is no cross-agent database. The row stands in the store of
the agent that **delegated**, because that is whose business it is — *"I handed this out and I am
owed an answer"* is not a fact about the agent doing the work. The one doing the work has an inbound
message on a conversation and answers it, exactly as it would one arriving from a channel.

That is also what keeps both foreign keys inside one database. The previous build's equivalent of
`parent_conversation` pointed across stores and could not be a foreign key at all; here it is one,
with a cascade, so a swept conversation cannot leave a delegation behind pointing at nothing.

**Finding the work stores no id.** `conversations` already has `UNIQUE (source, source_id)`, and the
key is one the delegator can construct rather than keep: `('agent', '<me>/<parent_turn>')` in the
other agent's database, `('role', '<delegation_id>')` in its own.

## The two kinds, in one table

`kind` is `'agent'` or `'role'`, and the two `CHECK`s tie the nullable columns to it so neither
kind's fields can be set on the other. The overlap between them is near-total and there are two of
them, which is the size at which one table with a constraint beats a table each.

`revision` is a snapshot of what the role was when the run was admitted, and it is deliberately not a
live lookup — the same denormalization `turns.schedule_name` already is, and for the same reason. A
role is replaced wholesale on every update, so a run that resumed against whatever the library holds
today would be a different run from the one that was admitted.

Imports nothing of rundesk's, never `executescript`, never ends the runner's transaction, and is safe
against an agent that does not need it.
"""

import sqlite3
from pathlib import Path
from typing import Iterator, List

#: The table, and the three indexes that answer the three questions anything asks of it: what is
#: waiting for me, what of mine is still out, and what belongs to this conversation.
#:
#: Every index is **partial**, over the rows that are still outstanding. A delegation is answered
#: once and then read rarely, so an index over all of them would grow for ever while the queries that
#: matter only ever look at the few that are open.
#:
#: Both foreign keys are indexed on the child side, because SQLite does not do it and an unindexed
#: one turns a parent delete into a scan — and a parent delete here is the retention sweep, which is
#: the one thing that touches many rows at once.
SCHEMA = """
CREATE TABLE IF NOT EXISTS delegations (
  id                  INTEGER PRIMARY KEY,
  delegation_id       TEXT NOT NULL UNIQUE,
  kind                TEXT NOT NULL CHECK (kind IN ('agent', 'role')),
  to_agent            TEXT,
  role                TEXT,
  revision            TEXT,
  parent_conversation INTEGER NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
  parent_turn         INTEGER NOT NULL REFERENCES turns (id) ON DELETE CASCADE,
  answered_at         TEXT,
  stop_asked_at       TEXT,
  carry_attempts      INTEGER NOT NULL DEFAULT 0,
  created_at          TEXT NOT NULL,
  latest_at           TEXT NOT NULL,
  CHECK ((kind = 'agent') = (to_agent IS NOT NULL)),
  CHECK ((kind = 'role') = (role IS NOT NULL)),
  CHECK ((kind = 'role') OR revision IS NULL)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_delegations_waiting
  ON delegations (to_agent) WHERE answered_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_delegations_mine
  ON delegations (kind, id) WHERE answered_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_delegations_parent
  ON delegations (parent_conversation, id);

CREATE INDEX IF NOT EXISTS idx_delegations_turn
  ON delegations (parent_turn);
"""

#: What an agent is for, in one sentence, so another agent can decide whether to delegate to it.
#:
#: **The gap this closes is the one that made the previous build's delegation close to unusable**: an
#: agent had no description the way a role did, so — in that build's own words — it *"learned the verb
#: from the help output and the names from nowhere."* A team it cannot see is a team it cannot use.
#:
#: Apart from `SCHEMA` because it is an `ALTER` rather than a `CREATE IF NOT EXISTS`: SQLite refuses
#: to add a column that is already there, so this one is asked about first — check, then act. Nullable
#: because every agent that already exists has no answer for it, and a made-up one would be worse than
#: the absence: it would read as something its owner wrote.
WHAT_AN_AGENT_IS_FOR = """
ALTER TABLE config ADD COLUMN describes TEXT;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Lay down the delegations and, where it is not already there, what an agent is for.

    `where` is this agent's own directory. This step changes no files in it, and takes it because the
    contract every step is written to is the same one.
    """
    for statement in statements(SCHEMA):
        conn.execute(statement)

    if "describes" not in _columns(conn, "config"):
        # Check, then act. `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS`, and a step has to be safe
        # against an agent that does not need it.
        for statement in statements(WHAT_AN_AGENT_IS_FOR):
            conn.execute(statement)


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
