"""The two models a turn knows apart, the word it could not say, and who keeps the counters.

Three defects in the permanent ledger, and one shape fixes them: a column may hold one fact, and the
thing that causes a number is the thing that moves it.

## One model column held two facts and lost whichever arrived second

`model_name` was written at admission from the model *asked for* and overwritten at settlement by the
model the brain *reported*. An ordinary turn on an agent's configured model wrote nothing at all, so
the ledger could not say which model an agent runs on; a turn that asked for one and was answered by
another kept only the answer. `admitted_model_name` and `reported_model_name` are those two facts,
each nullable and each written by the one thing that knows it.

**`model_name` is left exactly where it is**, as the best-known answer — what the brain reported when
it reported one, and what the turn was admitted with when it did not. Every surface reading it goes on
being right, and nothing has to be carried to keep it that way.

**Neither new column is backfilled, and that is the point.** On a row an older release wrote,
`model_name` is whichever of the two arrived last and nothing can say which — so both stay `NULL`,
which here means *the release that wrote this row did not keep these apart*. Copying the old value
across would turn something nobody can interpret into something that reads as though somebody had.

**`model_provenance_kept` is how a reader knows which kind of row it is holding, and it is a column
rather than an inference.** Absence of both models cannot answer it: a turn that selected no model
and was answered by a provider that reported none is empty in exactly the way a legacy row is, and
guessing would put an honest new row under a sentence about an older release. Every row admitted from
here on says `1`, every row already here says `0`, and nothing else may write it.

## A steering word rundesk could not deliver is not the adapter drifting

`lost_records` is how a vendor moving underneath rundesk becomes visible, and a word refused at the
end of a turn was counted into it — so an ordinary steering race read as provider protocol drift.
`unsent_records` is the other event, counted apart. Records already written keep their word and their
reason; only what is written from here on is separated.

## The insert keeps the count, because the writer that kept it was already gone

The counters were taken at settlement by counting rows, and the thread that appends those rows may
still be running: a word refused a second after the brain went quiet appended a record to a turn
whose summary was already final, and the detail is swept a fortnight later leaving the wrong
permanent number and nothing to recover it from. Measured — one `LOST` record and a permanent count
of zero, on a three-second delay and not on a one-second one.

So the count moves inside the insert's own transaction, in a trigger rather than in the writer, for
the reason `0004` gives about the search index: **a trigger cannot be forgotten by a future writer**,
and it is the same transaction by construction rather than by everybody remembering.

**It only counts up.** `turn_records` is swept and `turns` is kept for ever — a row going has to
leave the summary alone, so there is no delete trigger and there is not meant to be one.

## What the old counting got wrong is repaired only as far as the evidence goes

A turn settled by an earlier release may hold a summary lower than the records it still has, because
the count was taken before the last of them landed. Carrying raises each counter to the number of
retained records **of that kind, where that is higher, and never otherwise** — `max` and never
assignment. A turn whose detail has already been swept has no evidence left, so its summary is left
exactly as it is rather than reset to the zero rows a sweep leaves behind, and the repair may be run
again for the same reason: it can only ever agree with itself.

**An old `lost` record is never re-read as `unsent`.** Both were written under one word and the
reason is prose, so anything sorting them now would be guessing at history. Old counts stay where
they are and only what is written from here on is separated.

Imports nothing of rundesk's, never `executescript`, never ends the runner's transaction, and is safe
against an agent that does not need it.
"""

import sqlite3
from pathlib import Path
from typing import Iterator, List

#: What is added to `turns`. The two models are nullable because a turn may honestly have neither;
#: the marker beside them is what says whether that emptiness means anything, and it defaults to `0`
#: so every row already in the table answers *no* without being written to.
COLUMNS = (
    ("admitted_model_name", "TEXT"),
    ("reported_model_name", "TEXT"),
    ("unsent_records", "INTEGER NOT NULL DEFAULT 0"),
    ("model_provenance_kept",
     "INTEGER NOT NULL DEFAULT 0 CHECK (model_provenance_kept IN (0, 1))"),
)

#: The record kinds a turn keeps a permanent count of, and the column each one moves. Spelled here as
#: well as in `providers.kept` — a step may not import anything of rundesk's, and these words are the
#: schema's as much as the product's. Adding a fourth is a new step, never an edit to this one.
COUNTED = (("unknown", "unknown_records"), ("lost", "lost_records"),
           ("unsent", "unsent_records"))

#: Raise one counter to the records that are still there, where they are more than it says. `max` of
#: the two rather than the count alone, because a swept turn has no evidence left and its summary is
#: the only thing that remembers; narrowed to turns that have such a record at all, so an install
#: with a long ledger and a fortnight of detail pays for the fortnight.
RECONCILED = """
UPDATE turns SET {column} = max({column}, (
  SELECT count(*) FROM turn_records r
   WHERE r.turn_id = turns.id AND r.record_type = '{kind}'))
 WHERE id IN (SELECT turn_id FROM turn_records WHERE record_type = '{kind}');
"""

#: A comparison in SQLite is `1` or `0`, so the three additions are the branch: exactly one of them
#: moves, and the `WHEN` keeps every other record out of the table altogether.
COUNTING = """
CREATE TRIGGER IF NOT EXISTS turn_records_after_insert
AFTER INSERT ON turn_records
WHEN new.record_type IN ('unknown', 'lost', 'unsent') BEGIN
  UPDATE turns SET
    unknown_records = unknown_records + (new.record_type = 'unknown'),
    lost_records    = lost_records + (new.record_type = 'lost'),
    unsent_records  = unsent_records + (new.record_type = 'unsent')
  WHERE id = new.turn_id;
END;
"""


def carry(conn: sqlite3.Connection, where: Path) -> None:
    """Add the columns, have the insert keep the counters, and raise what the old counting missed.

    `where` is this agent's own directory. This step changes no files in it, and takes it because
    the contract every step is written to is the same one.
    """
    tables = set(_tables(conn))
    if "turns" not in tables:
        return
    present = set(_columns(conn, "turns"))
    for name, kind in COLUMNS:
        if name not in present:
            # Check, then act. `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS`, and a step has to be
            # safe against an agent that does not need it.
            conn.execute(f"ALTER TABLE turns ADD COLUMN {name} {kind}")
    if "turn_records" not in tables:
        return
    for statement in statements(COUNTING):
        conn.execute(statement)
    for kind, column in COUNTED:
        for statement in statements(RECONCILED.format(kind=kind, column=column)):
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
    anything of rundesk's — including another step. **Not `said.split(";")`**: the trigger body above
    ends a statement of its own, so the obvious replacement would hand SQLite half a trigger.
    """
    building = ""
    for line in said.splitlines(True):
        building += line
        if sqlite3.complete_statement(building):
            yield building
            building = ""
    if building.strip():
        raise ValueError(f"this step ends in a statement with no terminator: {building.strip()!r}")
