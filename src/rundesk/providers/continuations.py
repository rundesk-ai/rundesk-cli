"""One lifecycle result returned to its exact originating conversation at most once.

The durable row copies no prompt, provider handle, channel identity, person identity, agent name,
credential, or path. It keeps only local row ids and bounded product-authored outcomes. Claiming is
transactional and deliberately at-most-once after a crash: replaying a continuation can repeat tool
effects, while an interrupted ``resuming`` row remains an honest auditable outcome.
"""

import os
import sqlite3
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.core import config
from rundesk.providers import environment, kept, turns

UPDATE = "update"
GATEWAY_RESTART = "gateway-restart"

REQUESTED = "requested"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"

SUPPRESSED = "suppressed"
RESUMING = "resuming"
DELIVERED = "delivered"

OUTCOME_AT_MOST = 1000


class NoOrigin(Exception):
    """The opt-in flag was not invoked by one unambiguous active channel turn."""


class Handoff(NamedTuple):
    id: int
    operation: str
    origin_turn_id: int
    origin_message_id: int
    requested_pid: Optional[int]
    lifecycle_state: str
    lifecycle_outcome: str
    continuation_state: str
    continuation_outcome: str
    observed_version: Optional[str]
    observed_pid: Optional[int]
    conversation: int
    provider: str
    provider_alias: Optional[str]
    origin_instructions: str


def origin(environ: Optional[Dict[str, str]] = None) -> Tuple[str, int, int, int]:
    """The active channel-backed agent, turn, conversation, and owner message, or a refusal."""
    values = os.environ if environ is None else environ
    agent = str(values.get(environment.AGENT) or "")
    raw_turn = str(values.get(environment.RUN) or "")
    if not agent or not raw_turn.isdigit() or int(raw_turn) < 1:
        raise NoOrigin("--continue is available only from one active channel provider turn")
    origin_home = str(values.get(environment.CWD) or "")
    try:
        if not origin_home or Path(origin_home).resolve() != directory.home(agent).resolve():
            raise NoOrigin("--continue requires this turn's agent and home to agree")
    except (OSError, directory.Refused) as why:
        raise NoOrigin(f"the active channel origin could not be resolved ({why})") from why
    turn = int(raw_turn)
    try:
        with records.reading(directory.records(agent)) as conn:
            row = conn.execute(
                "SELECT t.conversation_id, t.turn_status, c.source "
                "FROM turns t JOIN conversations c ON c.id = t.conversation_id "
                "WHERE t.id = ?", (turn,),
            ).fetchone()
            messages = conn.execute(
                "SELECT id FROM conversation_messages WHERE conversation_id = ? "
                "AND turn_id = ? AND author = ? ORDER BY id",
                (int(row["conversation_id"]) if row is not None else 0,
                 turn, arriving.BY_USER),
            ).fetchall()
    except (OSError, records.NotThere, records.Unreadable) as why:
        raise NoOrigin(f"the active channel origin could not be read ({why})") from why
    if (row is None or row["turn_status"] != kept.WORKING
            or row["source"] != arriving.FROM_CHANNEL
            or len(messages) != 1):
        raise NoOrigin("--continue requires one unambiguous active channel owner turn")
    conversation = int(row["conversation_id"])
    if turns.standing(agent, conversation) is not True:
        raise NoOrigin("--continue requires the initiating channel turn to still be active")
    return agent, turn, conversation, int(messages[0]["id"])


def requested_from_origin(operation: str, pid: Optional[int] = None,
                          environ: Optional[Dict[str, str]] = None) -> Handoff:
    """Validate and record the current provider origin in one call."""
    agent, turn, _conversation, message = origin(environ)
    return requested(agent, turn, message, operation, pid)


def requested(agent: str, turn: int, message: int, operation: str,
              pid: Optional[int] = None) -> Handoff:
    """Record opt-in intent once for this exact turn/message and operation."""
    if operation not in (UPDATE, GATEWAY_RESTART):
        raise ValueError(f"{operation} is not a lifecycle continuation operation")
    with records.writing(directory.records(agent)) as conn:
        origin_row = _origin(conn, agent, turn, message)
        existing = _one(conn, turn=turn, operation=operation)
        if existing is not None:
            return existing
        made = conn.execute(
            "INSERT INTO lifecycle_continuations "
            "(operation, origin_turn_id, origin_message_id, requested_pid, requested_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (operation, turn, int(origin_row["message"]),
             pid if pid is not None and pid > 0 else None, config.moment_of()),
        )
        return _by_id(conn, agent, int(made.lastrowid))


def running(agent: str, handoff: int) -> Handoff:
    """Mark lifecycle work begun without reopening a terminal outcome."""
    with records.writing(directory.records(agent)) as conn:
        conn.execute(
            "UPDATE lifecycle_continuations SET lifecycle_state = ? "
            "WHERE id = ? AND lifecycle_state = ?", (RUNNING, handoff, REQUESTED))
        return _by_id(conn, agent, handoff)


def finished(agent: str, handoff: int, *, succeeded: bool, outcome: str,
             version: Optional[str] = None, pid: Optional[int] = None) -> Handoff:
    """Keep one truthful terminal lifecycle result and its observed health facts."""
    state = SUCCEEDED if succeeded else FAILED
    with records.writing(directory.records(agent)) as conn:
        conn.execute(
            "UPDATE lifecycle_continuations SET lifecycle_state = ?, lifecycle_outcome = ?, "
            "observed_version = ?, observed_pid = ?, finished_at = ? "
            "WHERE id = ? AND lifecycle_state IN (?, ?)",
            (state, _bounded(outcome), version, pid if pid and pid > 0 else None,
             config.moment_of(), handoff, REQUESTED, RUNNING),
        )
        return _by_id(conn, agent, handoff)


def observed(agent: str, handoff: int, *, version: str, pid: int) -> Handoff:
    """Attach healthy-gateway facts to a terminal lifecycle result."""
    with records.writing(directory.records(agent)) as conn:
        conn.execute(
            "UPDATE lifecycle_continuations SET observed_version = ?, observed_pid = ? "
            "WHERE id = ? AND lifecycle_state IN (?, ?)",
            (version, pid if pid > 0 else None, handoff, SUCCEEDED, FAILED),
        )
        return _by_id(conn, agent, handoff)


def claim(agent: str, handoff: int) -> Optional[Handoff]:
    """Claim once, suppressing only an origin overtaken by owner input or another turn."""
    with records.writing(directory.records(agent)) as conn:
        row = _by_id(conn, agent, handoff)
        if (row.lifecycle_state not in (SUCCEEDED, FAILED)
                or row.continuation_state != REQUESTED):
            return None
        newer_message = conn.execute(
            "SELECT 1 FROM conversation_messages WHERE conversation_id = ? "
            "AND author = ? AND id > ? LIMIT 1",
            (row.conversation, arriving.BY_USER, row.origin_message_id),
        ).fetchone()
        if newer_message is not None:
            _suppress(conn, handoff, "newer owner input reached the originating conversation")
            return None
        newer_turn = conn.execute(
            "SELECT 1 FROM turns WHERE conversation_id = ? AND id > ? LIMIT 1",
            (row.conversation, row.origin_turn_id),
        ).fetchone()
        if newer_turn is not None:
            _suppress(conn, handoff, "a newer turn already resumed the originating conversation")
            return None
        changed = conn.execute(
            "UPDATE lifecycle_continuations SET continuation_state = ?, resumed_at = ? "
            "WHERE id = ? AND continuation_state = ?",
            (RESUMING, config.moment_of(), handoff, REQUESTED),
        ).rowcount
        return _by_id(conn, agent, handoff) if changed == 1 else None


def delivered(agent: str, handoff: int, outcome: str) -> Handoff:
    """Record the continuation turn's terminal delivery without reopening it."""
    with records.writing(directory.records(agent)) as conn:
        conn.execute(
            "UPDATE lifecycle_continuations SET continuation_state = ?, "
            "continuation_outcome = ? WHERE id = ? AND continuation_state = ?",
            (DELIVERED, _bounded(outcome), handoff, RESUMING),
        )
        return _by_id(conn, agent, handoff)


def suppressed(agent: str, handoff: int, outcome: str) -> Handoff:
    """End an unadmitted continuation without making it eligible for replay."""
    with records.writing(directory.records(agent)) as conn:
        conn.execute(
            "UPDATE lifecycle_continuations SET continuation_state = ?, "
            "continuation_outcome = ? WHERE id = ? AND continuation_state IN (?, ?)",
            (SUPPRESSED, _bounded(outcome), handoff, REQUESTED, RESUMING),
        )
        return _by_id(conn, agent, handoff)


def superseded(agent: str, operation: str, outcome: str) -> int:
    """Make every not-yet-delivered request for one operation inert after a newer control."""
    with records.writing(directory.records(agent)) as conn:
        changed = conn.execute(
            "UPDATE lifecycle_continuations SET continuation_state = ?, "
            "continuation_outcome = ? WHERE operation = ? AND continuation_state = ?",
            (SUPPRESSED, _bounded(outcome), operation, REQUESTED),
        ).rowcount
    return int(changed or 0)


def prompt(agent: str, handoff: Handoff) -> str:
    """A product-authored recovery prompt containing facts but no replayed owner words."""
    if handoff.lifecycle_state == SUCCEEDED:
        subject = "update" if handoff.operation == UPDATE else "gateway restart"
        fact = f"The requested {subject} reached a successful terminal outcome"
    else:
        fact = ("The requested lifecycle operation reached a failed or rolled-back terminal "
                f"outcome: {handoff.lifecycle_outcome or 'it did not complete'}")
    recover = (f'"$RUNDESK_COMMAND" messages {agent} '
               f"--conversation {handoff.conversation}")
    return (f"{fact}. The gateway is healthy on Rundesk "
            f"{handoff.observed_version or 'the running release'} and the originating channel is "
            f"connected. If this is a fresh provider session, run `{recover}` to recover the "
            "recorded request and progress. Verify the lifecycle outcome, then continue from the "
            "first unfinished objective. Do not repeat completed actions or claim what the "
            "observations do not prove.")


def for_turn(agent: str, turn: int, operation: str) -> Optional[Handoff]:
    """The handoff one origin turn requested for one operation, if any."""
    with records.reading(directory.records(agent)) as conn:
        return _one(conn, turn=turn, operation=operation)


def one(agent: str, handoff: int) -> Handoff:
    """One handoff by its agent-local id."""
    with records.reading(directory.records(agent)) as conn:
        return _by_id(conn, agent, handoff)


def waiting(agent: str, operation: Optional[str] = None) -> List[Handoff]:
    """Actionable lifecycle requests, oldest first."""
    parameters: List[object] = [REQUESTED, REQUESTED]
    narrowed = ""
    if operation is not None:
        narrowed = " AND lc.operation = ?"
        parameters.append(operation)
    with records.reading(directory.records(agent)) as conn:
        rows = conn.execute(
            _SELECT + " WHERE lc.lifecycle_state = ? AND lc.continuation_state = ?"
            + narrowed + " ORDER BY lc.id", tuple(parameters),
        ).fetchall()
    return [_as_handoff(row) for row in rows]


def in_state(agent: str, operation: str, lifecycle_state: str) -> List[Handoff]:
    """One operation's actionable lifecycle rows in an exact state."""
    with records.reading(directory.records(agent)) as conn:
        rows = conn.execute(
            _SELECT + " WHERE lc.operation = ? AND lc.lifecycle_state = ? "
            "AND lc.continuation_state = ? ORDER BY lc.id",
            (operation, lifecycle_state, REQUESTED),
        ).fetchall()
    return [_as_handoff(row) for row in rows]


def terminal(agent: str) -> List[Handoff]:
    """Terminal outcomes still eligible to wake this agent's originating conversation."""
    with records.reading(directory.records(agent)) as conn:
        rows = conn.execute(
            _SELECT + " WHERE lc.lifecycle_state IN (?, ?) "
            "AND lc.continuation_state = ? ORDER BY lc.id",
            (SUCCEEDED, FAILED, REQUESTED),
        ).fetchall()
    return [_as_handoff(row) for row in rows]


_SELECT = (
    "SELECT lc.*, t.conversation_id AS conversation, t.provider_name AS provider, "
    "t.provider_alias AS provider_alias, "
    "t.instructions_sha256 AS origin_instructions "
    "FROM lifecycle_continuations lc JOIN turns t ON t.id = lc.origin_turn_id"
)


def _one(conn: sqlite3.Connection, *, turn: int, operation: str) -> Optional[Handoff]:
    found = conn.execute(
        _SELECT + " WHERE lc.origin_turn_id = ? AND lc.operation = ?", (turn, operation)
    ).fetchone()
    return _as_handoff(found) if found is not None else None


def _by_id(conn: sqlite3.Connection, agent: str, handoff: int) -> Handoff:
    found = conn.execute(_SELECT + " WHERE lc.id = ?", (handoff,)).fetchone()
    if found is None:
        raise records.NotThere(f"{agent} has no lifecycle continuation {handoff}")
    return _as_handoff(found)


def _origin(conn: sqlite3.Connection, agent: str, turn: int, message: int) -> sqlite3.Row:
    found = conn.execute(
        "SELECT t.conversation_id, m.id AS message FROM turns t "
        "JOIN conversation_messages m ON m.conversation_id = t.conversation_id "
        "WHERE t.id = ? AND m.id = ? AND m.turn_id = t.id AND m.author = ?",
        (turn, message, arriving.BY_USER),
    ).fetchone()
    if found is None:
        raise records.NotThere(f"{agent} has no matching lifecycle origin")
    return found


def _suppress(conn: sqlite3.Connection, handoff: int, why: str) -> None:
    conn.execute(
        "UPDATE lifecycle_continuations SET continuation_state = ?, continuation_outcome = ? "
        "WHERE id = ? AND continuation_state = ?",
        (SUPPRESSED, _bounded(why), handoff, REQUESTED),
    )


def _as_handoff(row: sqlite3.Row) -> Handoff:
    return Handoff(
        id=int(row["id"]), operation=str(row["operation"]),
        origin_turn_id=int(row["origin_turn_id"]),
        origin_message_id=int(row["origin_message_id"]),
        requested_pid=(int(row["requested_pid"]) if row["requested_pid"] is not None else None),
        lifecycle_state=str(row["lifecycle_state"]),
        lifecycle_outcome=str(row["lifecycle_outcome"]),
        continuation_state=str(row["continuation_state"]),
        continuation_outcome=str(row["continuation_outcome"]),
        observed_version=(str(row["observed_version"])
                          if row["observed_version"] is not None else None),
        observed_pid=(int(row["observed_pid"]) if row["observed_pid"] is not None else None),
        conversation=int(row["conversation"]), provider=str(row["provider"]),
        provider_alias=row["provider_alias"],
        origin_instructions=str(row["origin_instructions"] or ""),
    )


def _bounded(said: str) -> str:
    return " ".join(str(said).split())[:OUTCOME_AT_MOST]
