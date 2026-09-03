"""The schedules one agent keeps: what it starts, when, and what became of it last time. 0.38.0.

**Why the records refuse rather than trust.** Four of the columns below come in pairs where exactly
one of the pair must say something, and the build this replaces asked that question in the reader
instead — so a row written by a half-finished command, a hand-edited database or a future column
default was found broken at the moment the clock reached it, in a gateway, at two in the morning.
The two `CHECK`s make such a row impossible to write, which means nothing downstream has to re-ask:
`due.understood` still refuses one, because a row is still a person's typing on the way in, but it
is refusing what could not have got here rather than what routinely does.

**`last_fired_for` is why this table can be trusted through a restart.** It is the local minute a
firing was claimed for, written *before* the work starts. Held only in memory — which is where the
old build held it — the fact that a minute had already fired died with the gateway, and a crash
between starting and finishing plus a supervisor that brings the gateway back within seconds ran the
same schedule twice for the one minute it was due. It is compared with a strict `>` and never `!=`,
because a wall clock does not only stand still, it goes backwards: an autumn hour repeats every year
and `!=` lets every minute of it through.

**Local, not UTC, and only these three.** `cron`, `run_at` and `expire_at` are what somebody typed
and are matched against this machine's own clock, so they are kept exactly as typed —
`docs/concepts/time.md`'s rule is about a *record*, and these are a statement about the future. `last_run_at`
and `created_at` are records of something that happened, are compared and sorted, and are UTC in
`core.config.MOMENT` like every other record this product keeps. `last_fired_for` is the odd one and
deliberately so: it is compared against a minute the cron fields produced, and those are local.

**The provider columns are what a schedule asks an agent**, and they are named for the thing rather
than for who reads them: `provider_name` and `model_name` are the same fact `config` and `turns`
keep, and one fact spelled three ways is three things to grep for. They were carried here before
anything wrote them, on the argument that a column added later is a second migration for every agent
on every machine — and the release that runs a provider has since arrived and writes them.

**`last_outcome` speaks the states an adapter renders.** `done`, not `completed`: `docs/extending/adapters.md`
publishes `seen`, `working`, `done`, `stopped`, `failed` and says plainly that they are not `taken`,
`running`, `finished`. `turns.turn_status` already speaks it, and a firing's outcome is the same
question asked of a different kind of work.
"""

import sqlite3
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
  id               INTEGER PRIMARY KEY,
  name             TEXT NOT NULL UNIQUE,
  enabled          INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  cron             TEXT,
  run_at           TEXT,
  expire_at        TEXT,
  provider_name   TEXT,
  model_name      TEXT,
  prompt     TEXT,
  command          TEXT,
  channel          TEXT,
  channel_place_id TEXT,
  last_outcome     TEXT CHECK (last_outcome IS NULL OR
                               last_outcome IN ('stopped', 'failed', 'done')),
  last_run_at      TEXT,
  last_fired_for   TEXT,
  created_at       TEXT NOT NULL,
  CHECK ((cron IS NULL) <> (run_at IS NULL)),
  CHECK ((command IS NULL) <> (prompt IS NULL))
) STRICT;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Lay down `schedules`, and leave one that is already there alone."""
    for statement in statements(SCHEMA):
        conn.execute(statement)


def statements(said: str) -> Iterator[str]:
    """Split SQL into statements the way SQLite itself would, one at a time.

    Written out here rather than imported from `0001`, because a step may not import anything of
    rundesk's — including another step. A step written today runs against an agent carried forward
    years from now, by a runner that loads it from a file, and the file beside it may have moved.
    """
    building = ""
    for line in said.splitlines(True):
        building += line
        if sqlite3.complete_statement(building):
            yield building
            building = ""
    if building.strip():
        raise ValueError(f"this step ends in a statement with no terminator: {building.strip()!r}")
