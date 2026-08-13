"""What an agent's records hold about its turns, and finding what was said.

The mirror of `channels.kept` and `schedules.kept`, and the same shape: every read goes through
`records.reading`, every write through `records.writing`, no connection is ever held across a call,
and **there is no second way into an agent's database**.

Four things live here and they are read for different reasons.

**A turn** is one row: what it was admitted with, what it came to, and what it cost. Written at
admission and settled once, so a turn that died before it reached the brain still shows what somebody
asked for.

**A turn's records** are what it *did*, in order. The only table that grows with tool calls, and the
only one swept — `turn_records` is diagnostic and a conversation is history.

**A provider session** is where one conversation got to on one brain. Three columns, because a
session belongs to a conversation and a brain and not to a model, which can change under a resumed
session without invalidating it. Its current instruction boundary is the fingerprint on that
provider's latest turn; a changed fingerprint makes the opaque handle stale.

**The search** is over what was said, and it is the agent's own tool before it is the owner's: an
owner refers to work the agent has no record of, and the agent reads its own history back before
answering. That is why the default answer is bounded — every line it reads costs tokens.

May depend on `agents`, `core` and `utils`.
"""

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from rundesk.agents import directory, records
from rundesk.core import config
from rundesk.providers import adapters, protocol

#: The tables, named once each.
TURNS = "turns"
TURN_RECORDS = "turn_records"
SESSIONS = "provider_sessions"
MESSAGES = "conversation_messages"
SEARCH = "conversation_messages_fts"

#: What a turn is, from admission to settled. **`WORKING` means nothing has settled it, and never
#: that something is running** — whether a turn is running now is asked of the kernel through the
#: conversation's lock, exactly as a firing's record on disk means the work began and the lock says
#: whether it still is.
#:
#: The same four words the channel layer already renders, and `seen` is deliberately not among them:
#: that one belongs to a message arriving and needs no turn at all.
WORKING = "working"
DONE = "done"
STOPPED = "stopped"
FAILED = "failed"
TURN_STATUSES = (WORKING, DONE, STOPPED, FAILED)

#: What a turn may be given when it is admitted. Narrower than the table on purpose: `id` is
#: identity, `state` starts at `working` and is settled by `settled`, and everything about what a
#: turn *came to* is the records' own account — a caller that could set those could rewrite history
#: and then read it back as fact.
ADMITTED = ("conversation_id", "schedule_id", "schedule_name", "provider_name", "provider_alias",
            "model_name",
            "access_mode", "provider_capabilities", "session_resumed", "instructions_sha256",
            "instructions_bytes")

#: What may be written when a turn is settled, beside its state.
SETTLED = ("model_name", "exit_code", "failure_code", "failure_message", "usage_reported",
           "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
           "context_tokens", "unknown_records", "lost_records",
           "raw_offset_start", "raw_offset_end")

#: How many messages a search answers with unless somebody asks for more. Small, because **the agent
#: is the first caller and every line it reads costs tokens** — a search that answered with fifty
#: bodies would spend a turn's budget on finding out what the turn was about.
FOUND_AT_MOST = 20

#: How much of a message is shown around what matched, in words. What a person or an agent needs is
#: enough to recognise the exchange and go and read it, not the exchange itself.
AROUND_A_MATCH = 12

#: What escapes a wildcard in the fallback's `LIKE`. Named because it has to be spelled the same in
#: the pattern and in the `ESCAPE` clause, and escaping without the clause does nothing at all.
LIKE_ESCAPE = "\\"


class Refused(Exception):
    """Something that may not be written about a turn, named with why.

    A sentence rather than a code, because every caller has to tell somebody what happened — and the
    one most likely to meet this is a gateway writing a line at two in the morning.
    """


# -- one turn --------------------------------------------------------------------------


def usage_of_turn(row: Dict[str, Any]) -> protocol.Usage:
    """What a settled turn cost, as the same object a running one reports.

    **The columns and the fields are the same words**, so this is a lift and never a translation —
    which is the point: a surface reading a row and a surface reading a live turn were formatting
    the cost independently, and the one reading the row had never picked up `context_tokens`. The
    ledger for a turn showed less than the line printed the moment that turn finished.
    """
    return protocol.Usage(
        usage_reported=bool(row["usage_reported"]),
        **{named: row[named] for named in
           ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
            "context_tokens", "model_name")})


def add_turn(agent: str, values: Dict[str, Any], when: Optional[datetime] = None) -> int:
    """Write down a turn that has been admitted, and hand back its id. **Before the brain starts.**

    The id is what the adapter is told as `RUNDESK_RUN`, so it has to exist before anything is
    started — and writing the turn first is what makes a turn that died on its way to the brain still
    show what somebody asked for.
    """
    _only(values, ADMITTED, "given to a turn")
    stated = dict(values, turn_status=WORKING, created_at=_now(when))
    named = sorted(stated)
    with records.writing(directory.records(agent)) as conn:
        _known(conn, agent, named, TURNS)
        got = _rows(conn, agent,
                    f"INSERT INTO {TURNS} ({', '.join(named)}) "
                    f"VALUES ({', '.join('?' for _ in named)})",
                    tuple(stated[one] for one in named))
        return int(got.lastrowid)


def finish_turn(agent: str, turn: int, turn_status: str,
                values: Optional[Dict[str, Any]] = None,
                when: Optional[datetime] = None) -> None:
    """Write down what a turn came to. **Refused if it is not one of the four words.**

    Refused here rather than left to the `CHECK`, for the reason `schedules.kept.became` gives: the
    caller is a gateway logging at two in the morning, and a constraint violation is not a sentence
    anybody can act on.

    A turn whose row has gone is passed over rather than raising — an agent removed from under a
    running turn is somebody's decision, and failing to write down what happened to a turn nobody
    kept is not a failure worth reporting.
    """
    if turn_status not in TURN_STATUSES or turn_status == WORKING:
        raise Refused(f"{turn_status} is not what a turn comes to — it is one of "
                      f"{', '.join(one for one in TURN_STATUSES if one != WORKING)}")
    given = dict(values or {})
    _only(given, SETTLED, "written down about a settled turn")
    if given.get("failure_code") is not None and not _a_known_failure(given["failure_code"]):
        raise Refused(f"{given['failure_code']} is not a failure this release knows")
    given.update(turn_status=turn_status, ended_at=_now(when))
    named = sorted(given)
    with records.writing(directory.records(agent)) as conn:
        _known(conn, agent, named, TURNS)
        _rows(conn, agent,
              f"UPDATE {TURNS} SET {', '.join(f'{one} = ?' for one in named)} WHERE id = ?",
              (*(given[one] for one in named), turn))


def get_turn(agent: str, turn: int) -> Dict[str, Any]:
    """One turn, whole. `records.NotThere` when there is no such turn."""
    with records.reading(directory.records(agent)) as conn:
        got = _rows(conn, agent, f"SELECT * FROM {TURNS} WHERE id = ?", (turn,)).fetchone()
    if got is None:
        raise records.NotThere(f"{agent} has no turn {turn}")
    return dict(got)


def list_turns(agent: str, most: int = FOUND_AT_MOST,
               conversation: Optional[int] = None) -> List[Dict[str, Any]]:
    """The most recent turns, newest first. None is an answer; unreadable records raise."""
    where = "WHERE conversation_id = ?" if conversation is not None else ""
    values = (conversation, most) if conversation is not None else (most,)
    with records.reading(directory.records(agent)) as conn:
        got = _rows(conn, agent, f"SELECT * FROM {TURNS} {where} ORDER BY id DESC LIMIT ?", values)
        return [dict(row) for row in got.fetchall()]


def turns_in_conversation(agent: str, conversation: int) -> List[Dict[str, Any]]:
    """Every turn in one conversation, oldest first.

    The ordinary listing stays bounded and newest first. A session-lineage query needs the other
    shape: a durable delegation may have originated before the listing bound, and a later fresh
    turn is the evidence that its delivery session was replaced.
    """
    with records.reading(directory.records(agent)) as conn:
        got = _rows(
            conn, agent,
            f"SELECT * FROM {TURNS} WHERE conversation_id = ? ORDER BY id",
            (conversation,),
        )
        return [dict(row) for row in got.fetchall()]


def schedule_turn_after(agent: str, schedule: str, after: str) -> Optional[Dict[str, Any]]:
    """The first turn one schedule invocation admitted at or after `after`."""
    with records.reading(directory.records(agent)) as conn:
        got = _rows(
            conn, agent,
            f"SELECT * FROM {TURNS} WHERE schedule_name = ? AND created_at >= ?"
            " ORDER BY id LIMIT 1", (schedule, after)).fetchone()
    return dict(got) if got is not None else None


def list_unfinished_turns(agent: str) -> List[Dict[str, Any]]:
    """Every turn nothing has settled, oldest first.

    **What a gateway reads when it comes up.** A turn left `working` is one whose process is gone or
    still going, and which of those it is is the conversation lock's answer and never this one's.
    """
    with records.reading(directory.records(agent)) as conn:
        got = _rows(conn, agent, f"SELECT * FROM {TURNS} WHERE turn_status = ? ORDER BY id", (WORKING,))
        return [dict(row) for row in got.fetchall()]


# -- what a turn did -------------------------------------------------------------------


def add_turn_record(agent: str, turn: int, record_type: str,
                    event_data: Optional[Dict[str, Any]] = None,
                    raw_line: Optional[str] = None,
                    when: Optional[datetime] = None) -> None:
    """One thing that happened in a turn, added and never rewritten.

    `raw` is written **only for something this release did not understand**. For a record it did, the
    parsed event *is* the line, and storing both doubles the table for nothing — and this is the
    column drift is read from, so what is in it means something.
    """
    with records.writing(directory.records(agent)) as conn:
        _rows(conn, agent,
              f"INSERT INTO {TURN_RECORDS} "
              "(turn_id, record_type, event_data, raw_line, created_at) VALUES (?, ?, ?, ?, ?)",
              (turn, record_type, json.dumps(event_data or {}, sort_keys=True), raw_line,
               _now(when)))


def list_turn_records(agent: str, turn: int) -> List[Dict[str, Any]]:
    """Everything a turn did, in the order it happened.

    Ordered by `id`, which is a total order that does not depend on a clock — one turn is one process
    is one writer, so the order rows were inserted in is the order things happened in, on a machine
    whose clock went backwards mid-turn.
    """
    with records.reading(directory.records(agent)) as conn:
        got = _rows(conn, agent, f"SELECT * FROM {TURN_RECORDS} WHERE turn_id = ? ORDER BY id",
                    (turn,))
        return [dict(row) for row in got.fetchall()]


def sweep_turn_records(agent: str, keeping_days: int,
                       when: Optional[datetime] = None) -> int:
    """Remove what turns did more than `keeping_days` ago. Hands back how many rows went.

    **Only `turn_records`.** A turn's own row is a couple of hundred bytes and is the ledger; what
    was said is the owner's history and is what they search. This is the one table that grows with
    tool calls, and it is diagnostic — a fortnight after the fact, what a turn *did* has been read if
    it was ever going to be.

    `keeping_days` below one removes nothing rather than everything, which is the safe way round for
    a number that arrives from a configuration file.
    """
    if keeping_days < 1:
        return 0
    before = _now(when, days_ago=keeping_days)
    with records.writing(directory.records(agent)) as conn:
        got = _rows(conn, agent, f"DELETE FROM {TURN_RECORDS} WHERE created_at < ?", (before,))
        return int(got.rowcount or 0)


# -- where a conversation got to -------------------------------------------------------


def get_session(agent: str, conversation: int, provider_name: str,
                provider_alias: Optional[str] = None) -> Optional[str]:
    """The handle this conversation got to on this brain, or `None` for a fresh one."""
    provider_name = _session_provider(provider_name, provider_alias)
    with records.reading(directory.records(agent)) as conn:
        got = _rows(conn, agent,
                    f"SELECT session_id FROM {SESSIONS} WHERE conversation_id = ? "
                    "AND provider_name = ? AND provider_alias = ?",
                    (conversation, provider_name, provider_alias or "")).fetchone()
    return str(got["session_id"]) if got is not None else None


def latest_instructions(agent: str, conversation: int,
                        provider_name: str,
                        provider_alias: Optional[str] = None) -> Optional[str]:
    """The instruction fingerprint on this brain's latest turn in the conversation.

    A session handle does not carry that fingerprint itself, so the turn that last used the
    conversation is the durable boundary. Some brains bind instructions when a session is created
    and silently ignore replacements on resume; a missing or different fingerprint therefore means
    the saved handle is not safe to carry into the next turn.
    """
    with records.reading(directory.records(agent)) as conn:
        rows = _rows(
            conn, agent,
            f"SELECT provider_name, instructions_sha256 FROM {TURNS} "
            "WHERE conversation_id = ? AND provider_alias IS ? ORDER BY id DESC",
            (conversation, provider_alias),
        ).fetchall()
    wanted = _session_provider(provider_name, provider_alias)
    for got in rows:
        if _session_provider(str(got["provider_name"]), provider_alias) != wanted:
            continue
        if got["instructions_sha256"] is None:
            return None
        return str(got["instructions_sha256"])
    return None


def save_session(agent: str, conversation: int, provider_name: str, session_id: str,
                 provider_alias: Optional[str] = None) -> None:
    """Keep where this conversation got to, replacing whatever was there.

    An upsert rather than a delete and an insert: two statements would leave a moment with no handle
    at all, and a turn admitted in that moment would start a fresh conversation and throw away
    everything the last one had.
    """
    provider_name = _session_provider(provider_name, provider_alias)
    with records.writing(directory.records(agent)) as conn:
        _rows(conn, agent,
              f"INSERT INTO {SESSIONS} (conversation_id, provider_name, provider_alias, session_id) "
              "VALUES (?, ?, ?, ?) ON CONFLICT (conversation_id, provider_name, provider_alias) "
              "DO UPDATE SET session_id = excluded.session_id",
              (conversation, provider_name, provider_alias or "", session_id))


def delete_session(agent: str, conversation: int, provider_name: str,
                   provider_alias: Optional[str] = None) -> None:
    """Throw away where this conversation got to, so the next turn starts fresh.

    A row that was not there is not a failure: starting fresh is what was asked for either way.
    """
    provider_name = _session_provider(provider_name, provider_alias)
    with records.writing(directory.records(agent)) as conn:
        _rows(conn, agent,
              f"DELETE FROM {SESSIONS} WHERE conversation_id = ? AND provider_name = ? "
              "AND provider_alias = ?",
              (conversation, provider_name, provider_alias or ""))


def _session_provider(provider_name: str, provider_alias: Optional[str]) -> str:
    """Session identity for an alias, without changing ordinary default-account behaviour."""
    return adapters.canonical(provider_name) if provider_alias is not None else provider_name


def forget_sessions(agent: str, conversation: int) -> int:
    """Throw away where this conversation got to **on every brain**. Hands back how many went.

    Every brain rather than the one configured now, because *start fresh* is a thing somebody asks
    of the conversation and not of a provider: an agent whose brain was changed last week still has
    the old one's handle sitting here, and leaving it would have a conversation somebody was told
    was fresh resume the moment its provider was changed back.
    """
    with records.writing(directory.records(agent)) as conn:
        gone = _rows(conn, agent, f"DELETE FROM {SESSIONS} WHERE conversation_id = ?",
                     (conversation,))
        return int(gone.rowcount if gone.rowcount and gone.rowcount > 0 else 0)


# -- finding what was said -------------------------------------------------------------


class Found(Dict[str, Any]):
    """One message a search matched, with where it was said carried alongside it."""


def has_search_index(agent: str) -> bool:
    """Whether this agent's records have a full-text index at all.

    Asked of the records rather than remembered, so there is no state to go stale — and asked at all
    because SQLite is not always built with the module, and an agent without it must still work.

    **Asked by using it, not by looking for it.** A row in `sqlite_master` says the table was created
    once, on some machine, by some Python — it does not say this one can open it. An install whose
    interpreter was upgraded to a build without the module has the table in the file and cannot read
    a word of it, and a search that trusted the row would raise on every query instead of falling
    back. One trivial query costs nothing and answers the question that was actually asked.
    """
    try:
        with records.reading(directory.records(agent)) as conn:
            conn.execute(f"SELECT rowid FROM {SEARCH} LIMIT 1").fetchone()
        return True
    except (records.NotThere, records.Unreadable, sqlite3.DatabaseError):
        return False


def search_messages(agent: str, saying: str = "", channel: Optional[str] = None,
           source: Optional[str] = None, conversation: Optional[int] = None,
           since: Optional[str] = None, most: int = FOUND_AT_MOST) -> List[Found]:
    """Messages matching these words, narrowed by where and when they were said.

    Every filter is optional and every one of them joins through a primary key, so narrowing costs
    nothing. With no words at all this is the conversation read back, newest first, which is what
    `--conversation` on its own means.

    **Falls back to a scan where there is no index**, and the caller is expected to say so: a scan
    has no stemming, no phrase and no ranking, and it finds different things. It is bounded by the
    same limit, so the fallback is slower and never unbounded.

    **What somebody typed is words, never a query.** Both branches take it as words — see
    `_as_words` and `_as_a_pattern` — so the two find the same things and neither can be made to
    mean something by what a person happened to type.
    """
    narrowing, values = _narrowed(channel, source, conversation, since)
    if not saying.strip():
        sql = (f"SELECT m.*, c.source, c.channel, c.source_id FROM {MESSAGES} m "
               f"JOIN conversations c ON c.id = m.conversation_id {narrowing} "
               "ORDER BY m.id DESC LIMIT ?")
        return _found(agent, sql, (*values, most))
    if has_search_index(agent):
        sql = (f"SELECT m.*, c.source, c.channel, c.source_id, "
               f"snippet({SEARCH}, 0, '[', ']', '…', {AROUND_A_MATCH}) AS excerpt "
               f"FROM {SEARCH} f JOIN {MESSAGES} m ON m.id = f.rowid "
               f"JOIN conversations c ON c.id = m.conversation_id "
               f"WHERE {SEARCH} MATCH ? {_and(narrowing)} ORDER BY rank LIMIT ?")
        return _found(agent, sql, (_as_words(saying), *values, most))
    sql = (f"SELECT m.*, c.source, c.channel, c.source_id FROM {MESSAGES} m "
           f"JOIN conversations c ON c.id = m.conversation_id "
           f"WHERE m.body LIKE ? ESCAPE '{LIKE_ESCAPE}' {_and(narrowing)} "
           "ORDER BY m.id DESC LIMIT ?")
    return _found(agent, sql, (_as_a_pattern(saying), *values, most))


def _as_words(saying: str) -> str:
    """What somebody typed, as words for the index rather than as a query language.

    **FTS5's `MATCH` takes a query, not a string, and that is the whole of this.** Handed what a
    person typed, `C++` is a syntax error near `+`, `it's fine` is one near `'`, and an unbalanced
    `"` is an unterminated string — none of which is a search that found nothing. Worse, every one
    of them arrived here as `OperationalError`, which `_rows` reads as records that cannot be read:
    somebody searching for `C++` was told their agent's memory was unreadable.

    So each word becomes a quoted phrase, with any `"` doubled the way FTS5 escapes its own. The
    tokenizer then throws away what is not a token, so `+++` finds nothing rather than raising.
    Several words are still several phrases, which FTS5 requires all of — the same *and* the
    unquoted form meant.

    **This spends the operators to buy the apostrophe**, deliberately: `--search <words>` is
    documented as words, and `parser OR lunch` was never something the surface offered. A bare
    apostrophe is what people actually type.
    """
    return " ".join('"{}"'.format(one.replace('"', '""')) for one in saying.split())


def _as_a_pattern(saying: str) -> str:
    """What somebody typed, as a `LIKE` pattern that means only itself.

    `%` and `_` are wildcards, so a search for `50%` matched every message ever written and one for
    `a_b` matched `axb`. Escaped here, and the `ESCAPE` clause is spelled at the statement —
    escaping without it does nothing, which is the way this is usually got wrong.

    The escape character is escaped first, or escaping the wildcards would escape it again.
    """
    for one in (LIKE_ESCAPE, "%", "_"):
        saying = saying.replace(one, LIKE_ESCAPE + one)
    return f"%{saying}%"


def _narrowed(channel, source, conversation, since):
    """The `WHERE` every search shares, and the values that go with it, in one place.

    Built rather than interpolated: the shape of the clause is this module's and the values are
    always bound, so nothing a person or an agent typed reaches the statement.
    """
    each, values = [], []
    for column, given in (("c.channel", channel), ("c.source", source),
                          ("c.id", conversation), ("m.created_at", since)):
        if given is not None:
            each.append(f"{column} >= ?" if column == "m.created_at" else f"{column} = ?")
            values.append(given)
    return ("WHERE " + " AND ".join(each) if each else ""), tuple(values)


def _and(narrowing: str) -> str:
    """The shared clause, joined onto a `WHERE` that is already there."""
    return narrowing.replace("WHERE ", "AND ", 1) if narrowing else ""


def _found(agent: str, sql: str, values: tuple) -> List[Found]:
    with records.reading(directory.records(agent)) as conn:
        return [Found(row) for row in _rows(conn, agent, sql, values).fetchall()]


# -- the shape every one of these shares -----------------------------------------------


def _rows(conn: sqlite3.Connection, agent: str, sql: str, values: tuple = ()) -> sqlite3.Cursor:
    """Every statement goes through this, so an agent that cannot be read says so once.

    An agent carried only as far as `0003` has turns nobody can read, not no turns, and the two lead
    somewhere completely different.
    """
    try:
        return conn.execute(sql, values)
    except sqlite3.IntegrityError as why:
        # **A constraint is a refusal, not an unreadable set of records.** The two lead somewhere
        # completely different: one means a caller handed a value the records will not hold, and the
        # other means the records themselves cannot be read. Folded together, a turn admitted with a
        # bad access mode reported that the agent's records were broken.
        raise Refused(f"{agent}'s records would not hold that: {why}") from why
    except sqlite3.DatabaseError as why:
        raise records.Unreadable(f"{agent} does not hold turns that can be read: {why}") from why


def _known(conn: sqlite3.Connection, agent: str, named: List[str], table: str) -> None:
    """Refuse a column these records do not have, **before anything is written**.

    Both checks are deliberate and they are not the same one: the tuple above is what a caller may
    state, and this is what the records in front of us actually hold. It is also what makes the
    hand-built column lists safe — only names SQLite has just reported reach the statement.
    """
    there = records.columns_of(conn, directory.records(agent), table)
    unknown = [one for one in named if one not in there and one != "id"]
    if unknown:
        raise Refused(f"{unknown[0]} is not something {agent}'s turns hold")


def _only(values: Dict[str, Any], allowed: tuple, called: str) -> None:
    """Refuse a name that is not the caller's to set."""
    unknown = sorted(one for one in values if one not in allowed)
    if unknown:
        raise Refused(f"{unknown[0]} is not something {called}")


def _a_known_failure(said: Any) -> bool:
    """Whether this is a word for stopping that this release knows.

    Asked here rather than by a `CHECK`, and that is the one deliberate exception in the schema: this
    vocabulary grows every time a vendor invents a new way to fail, and widening a `CHECK` costs a
    full table rebuild — so the words live in `protocol`, which is where every other reader of them
    looks, and the refusal happens before the write.
    """
    return isinstance(said, str) and said in protocol.FAILURE_CODES


def _now(when: Optional[datetime] = None, days_ago: int = 0) -> str:
    """One moment, as these records write them."""
    return config.moment_of(when, days_ago=days_ago)
