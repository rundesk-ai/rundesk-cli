"""The delegations one agent has made, and the only way in to them.

Everything here goes through `agents.records` — its connections, its transactions, its busy timeout
and its four answers — for the reason `schedules.kept` gives: a table read by two different sets of
open-and-retry rules is a table where a gateway and a command disagree about what "locked" means.

## Why the row belongs to the agent that made it

A delegation spans two agents, and there is no cross-agent database. The row stands in the store of
the agent that **delegated**, because *"I handed this out and I am owed an answer"* is not a fact
about the agent doing the work — that one has an inbound message on a conversation and answers it,
exactly as it would one arriving from a channel.

So one rule holds everywhere, and `reading` is what enforces it rather than anybody's discipline:

    A gateway writes only its own agent's store. It reads other agents' stores read-only.

`records.reading` opens the file `mode=ro`, so SQLite itself refuses a write down that path. There
is no care to be taken and no reviewer who has to notice.

## What is not in this table

**Every column is a thing that is neither a turn nor a message**, and that is the membership rule
step `0005` was written to. The brief, the answer and every steer are `conversation_messages`; the
work is `turns`; its outcome is `turn_status`. There is no `state` column, because what state a
delegation is in is read off the work it delegated — `standing` is where that reading happens, and
it is the only place that knows how the two fit together.

## Finding the work without keeping a pointer to it

`conversations` has `UNIQUE (source, source_id)`, so the conversation a delegation's work happens in
is found by a key that is **constructed rather than stored**: `('agent', '<delegator>/<parent turn>')`
in the other agent's database, `('role', '<delegation id>')` in the delegator's own. A stored id
would be a second source of truth, and for the agent kind it would point into a database this one
may not follow it into.

May depend on `agents`, `core` and `utils`.
"""

import sqlite3
from datetime import datetime
from typing import Any, List, NamedTuple, Optional

from rundesk.agents import directory, records
from rundesk.core import config

#: The table, named once.
TABLE = "delegations"

#: What a delegation was handed to. `AGENT` is another named agent, answering as itself out of its
#: own home; `ROLE` is a specialist definition this agent puts on, with its identity withheld. The
#: words are `conversations.source`'s, which step `0003` wrote complete rather than grew.
AGENT = "agent"
ROLE = "role"
KINDS = (AGENT, ROLE)


#: How the conversation holding a delegation's work is keyed, per kind. Not stored anywhere — see
#: the module docstring. `source_id` is `TEXT`, and both of these are built into one.
def source_id_for(kind: str, delegator: str, parent_turn: int, delegation_id: str) -> str:
    """The `conversations.source_id` this delegation's work stands under.

    An agent's is keyed by **who asked and which turn of theirs**, so two delegations from one turn
    share a conversation and a provider session, and one from a later turn does not. A role's is
    keyed by the run, because a role has no identity to share a conversation with.
    """
    return f"{delegator}/{parent_turn}" if kind == AGENT else delegation_id


class Refused(Exception):
    """Something that may not be done to a delegation, named with why.

    A sentence rather than a code, for the reason `directory.Refused` gives: every caller has to
    tell somebody what to type instead, and a caller left to invent that wording invents a
    different one.
    """


class Delegation(NamedTuple):
    """One row, as everything above this reads it.

    A named shape rather than a dict, because four modules read these fields and a typo in a key is
    a `None` that reaches a person as a blank column rather than as a failure.
    """

    delegation_id: str
    kind: str
    to_agent: Optional[str]
    role: Optional[str]
    revision: Optional[str]
    parent_conversation: int
    parent_turn: int
    answered_at: Optional[str]
    stop_asked_at: Optional[str]
    carry_attempts: int
    created_at: str
    latest_at: str

    @property
    def handed_to(self) -> str:
        """Who or what this went to, for a listing that shows both kinds in one column."""
        return self.to_agent or self.role or ""


def made(agent: str, delegation_id: str, kind: str, parent_conversation: int, parent_turn: int,
         to_agent: Optional[str] = None, role: Optional[str] = None,
         revision: Optional[str] = None, now: Optional[datetime] = None) -> None:
    """Write down that this agent has handed work over. In the **delegator's** own store.

    Refuses rather than writes where the kind and what it names disagree — though the table refuses
    it too, and that is deliberate: the `CHECK` is the guarantee and this is the sentence, because
    `CHECK constraint failed: delegations` tells nobody what they did.
    """
    if kind not in KINDS:
        raise Refused(f"work is handed to one of {KINDS}, not {kind!r}")
    if kind == AGENT and not to_agent:
        raise Refused("a delegation to an agent has to name the agent")
    if kind == ROLE and not role:
        raise Refused("a role run has to name the role")

    at = config.moment_of(now)
    with records.writing(directory.records(agent)) as conn:
        try:
            conn.execute(
                f"INSERT INTO {TABLE} (delegation_id, kind, to_agent, role, revision,"
                " parent_conversation, parent_turn, created_at, latest_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (delegation_id, kind, to_agent, role, revision,
                 parent_conversation, parent_turn, at, at))
        except sqlite3.IntegrityError as why:
            raise Refused(f"{delegation_id} could not be written down: {why}") from why


def one(agent: str, delegation_id: str) -> Delegation:
    """One delegation this agent made. `records.NotThere` when it made no such thing."""
    with records.reading(directory.records(agent)) as conn:
        row = _asked(conn, agent, f"SELECT * FROM {TABLE} WHERE delegation_id = ?",
                     (delegation_id,)).fetchone()
    if row is None:
        raise records.NotThere(f"{agent} has handed nothing over under {delegation_id}")
    return _read(row)


def every(agent: str) -> List[Delegation]:
    """Everything this agent has handed over, newest first."""
    with records.reading(directory.records(agent)) as conn:
        rows = _asked(conn, agent, f"SELECT * FROM {TABLE} ORDER BY id DESC", ()).fetchall()
    return [_read(row) for row in rows]


def outstanding(agent: str, to_agent: Optional[str] = None) -> List[Delegation]:
    """What has not been answered yet — everything, or only what was handed to one agent.

    **Read out of somebody else's store as readily as out of one's own**, which is the whole of how
    an answering gateway finds work: it asks each agent on the install what it has outstanding for
    *it*, over a read-only connection. Oldest first, so nothing waits behind work that arrived
    later.
    """
    sql = f"SELECT * FROM {TABLE} WHERE answered_at IS NULL"
    values: tuple = ()
    if to_agent is not None:
        sql += " AND kind = ? AND to_agent = ?"
        values = (AGENT, to_agent)
    with records.reading(directory.records(agent)) as conn:
        rows = _asked(conn, agent, sql + " ORDER BY id", values).fetchall()
    return [_read(row) for row in rows]


def answered(agent: str, delegation_id: str, now: Optional[datetime] = None) -> bool:
    """Mark one delivered, and say whether this call was the one that did it.

    **The deliver-once guarantee, and it is a `WHERE` clause rather than a decision.** Two gateways
    looking at the same settled work would both see an answer owed; the one whose `UPDATE` matches
    a row still holding `answered_at IS NULL` is the one that delivers it, and the other is told
    `False` and does nothing. Anything that read first and wrote after would deliver twice.
    """
    at = config.moment_of(now)
    with records.writing(directory.records(agent)) as conn:
        moved = conn.execute(
            f"UPDATE {TABLE} SET answered_at = ?, latest_at = ?"
            " WHERE delegation_id = ? AND answered_at IS NULL",
            (at, at, delegation_id))
        return bool(moved.rowcount)


def stop_asked(agent: str, delegation_id: str, now: Optional[datetime] = None) -> bool:
    """Ask for one to end. **A request, and never an outcome** — what came of it is the turn's.

    Answers `False` where there was nothing to stop, so a caller can say *"that is already over"*
    rather than reporting a stop it did not cause.
    """
    at = config.moment_of(now)
    with records.writing(directory.records(agent)) as conn:
        moved = conn.execute(
            f"UPDATE {TABLE} SET stop_asked_at = ?, latest_at = ?"
            " WHERE delegation_id = ? AND answered_at IS NULL AND stop_asked_at IS NULL",
            (at, at, delegation_id))
        return bool(moved.rowcount)


def tried(agent: str, delegation_id: str, now: Optional[datetime] = None) -> int:
    """Count one more attempt at starting this work, and hand back the count.

    **A failed start produces no turn**, which is exactly why this cannot be counted off `turns` and
    has a column of its own. It is a wedge-stop rather than a retry policy: something that cannot be
    started must not be picked up for ever, and a bounded count is what says when to give up.
    """
    at = config.moment_of(now)
    with records.writing(directory.records(agent)) as conn:
        conn.execute(
            f"UPDATE {TABLE} SET carry_attempts = carry_attempts + 1, latest_at = ?"
            " WHERE delegation_id = ?", (at, delegation_id))
        row = conn.execute(
            f"SELECT carry_attempts FROM {TABLE} WHERE delegation_id = ?",
            (delegation_id,)).fetchone()
    return int(row[0]) if row else 0


def _read(row: Any) -> Delegation:
    """One row as a `Delegation`, naming every field rather than trusting column order."""
    return Delegation(
        delegation_id=str(row["delegation_id"]), kind=str(row["kind"]),
        to_agent=row["to_agent"], role=row["role"], revision=row["revision"],
        parent_conversation=int(row["parent_conversation"]),
        parent_turn=int(row["parent_turn"]),
        answered_at=row["answered_at"], stop_asked_at=row["stop_asked_at"],
        carry_attempts=int(row["carry_attempts"]),
        created_at=str(row["created_at"]), latest_at=str(row["latest_at"]))


def _asked(conn: sqlite3.Connection, agent: str, sql: str,
           values: tuple) -> sqlite3.Cursor:
    """Ask, and turn records holding no such table into `Unreadable` rather than an empty answer.

    An agent carried no further than `0004` has delegations nobody has read, not no delegations,
    and a caller told "none" would go on believing this agent has handed nothing over.
    """
    try:
        return conn.execute(sql, values)
    except sqlite3.DatabaseError as why:
        raise records.Unreadable(
            f"{agent} does not hold delegations that can be read: {why}") from why
