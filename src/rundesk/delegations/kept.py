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
delegation is in is read off the work it delegated: no terminal turn yet means it is still being
answered, and `turn_status` says how it went.

There is no attempt counter either, and that is worth saying because its absence looks like an
oversight. `providers.turns` writes the turn row before the work starts and settles it in a `finally`
that survives the process being taken down, so a provider that cannot start still leaves a turn that
reached a terminal status. Work that was admitted and then vanished is not a state this can be in.

## Finding the work without keeping a pointer to it

`conversations` has `UNIQUE (source, source_id)`, so the conversation a delegation's work happens in
is found by a key that is **constructed rather than stored** —
`('agent', '<delegator>/<parent turn>/<delegation>')` in the answering agent's database. A stored id
would be a second source of truth, and it would point into a database this one may not follow it into.

May depend on `agents`, `core` and `utils`.
"""

import sqlite3
from datetime import datetime
from typing import Any, List, NamedTuple, Optional

from rundesk.agents import directory, records
from rundesk.core import config

#: The table, named once.
TABLE = "delegations"

#: Where a delegated turn's conversation comes from, in `conversations.source`. Step `0003` wrote
#: that vocabulary complete rather than growing it, which is why this word was already legal.
FROM_AGENT = "agent"


def source_id_for(delegator: str, parent_turn: int,
                  delegation_id: Optional[str] = None) -> str:
    """The `conversations.source_id` this delegation's work stands under.

    Keyed by **the delegation as well as who asked and which turn of theirs**. This keeps two asks
    from one turn from sharing an answer while `resume` still returns to the one session it names.
    With no delegation id it spells the legacy key, so work admitted before ids joined the
    conversation boundary remains readable.

    Constructed rather than stored — see the module docstring. Whoever delivers the brief and
    whoever looks the work up later both build it, so there is no pointer to keep true, and none
    that could point into a database this agent may not follow it into.
    """
    legacy = f"{delegator}/{parent_turn}"
    return f"{legacy}/{delegation_id}" if delegation_id else legacy


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
    to_agent: str
    parent_conversation: int
    parent_turn: int
    answered_at: Optional[str]
    stop_asked_at: Optional[str]
    created_at: str
    latest_at: str


def made(agent: str, delegation_id: str, to_agent: str, parent_conversation: int,
         parent_turn: int, now: Optional[datetime] = None) -> None:
    """Write down that this agent has handed work over. In the **delegator's** own store.

    The table refuses a missing `to_agent` too, and the guard here is deliberate rather than
    duplication: the `NOT NULL` is the guarantee and this is the sentence, because SQLite answers
    `NOT NULL constraint failed: delegations.to_agent`, which names a column and not the mistake.
    """
    if not to_agent:
        raise Refused("a delegation has to name the agent it goes to")

    at = config.moment_of(now)
    with records.writing(directory.records(agent)) as conn:
        try:
            conn.execute(
                f"INSERT INTO {TABLE} (delegation_id, to_agent,"
                " parent_conversation, parent_turn, created_at, latest_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (delegation_id, to_agent, parent_conversation, parent_turn, at, at))
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
        sql += " AND to_agent = ?"
        values = (to_agent,)
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


def reopened(agent: str, delegation_id: str, now: Optional[datetime] = None) -> bool:
    """Owe an answer again, so work already settled can be carried on. `False` if it was not settled.

    **Carrying on is not asking again.** The conversation is the same one, so the answering agent
    picks up the provider session it already had rather than starting over — which is the whole
    point of resuming rather than handing over a second task that repeats the first.

    Clearing `answered_at` is what puts it back in front of the answering gateway: that column is
    the only thing marking it done, so taking it away is the same thing as never having been.
    """
    at = config.moment_of(now)
    with records.writing(directory.records(agent)) as conn:
        moved = conn.execute(
            f"UPDATE {TABLE} SET answered_at = NULL, stop_asked_at = NULL, latest_at = ?"
            " WHERE delegation_id = ? AND answered_at IS NOT NULL",
            (at, delegation_id))
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


def _read(row: Any) -> Delegation:
    """One row as a `Delegation`, naming every field rather than trusting column order."""
    return Delegation(
        delegation_id=str(row["delegation_id"]), to_agent=str(row["to_agent"]),
        parent_conversation=int(row["parent_conversation"]),
        parent_turn=int(row["parent_turn"]),
        answered_at=row["answered_at"], stop_asked_at=row["stop_asked_at"],
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
