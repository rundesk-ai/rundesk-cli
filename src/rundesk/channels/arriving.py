"""What came in through a channel, written where it can be read again.

One exchange out in the world is one conversation here, and that is the whole of what this module
has to get right. The build this replaces derived a conversation's identity by hashing what it came
from, which is what let two exchanges weeks apart, in different processes, land on one conversation
without either of them asking anything first. Here the uniqueness is stated in the table and the
lookup is `INSERT … ON CONFLICT DO NOTHING` followed by a read — so two gateways racing to record the
same arriving message end up with one conversation between them rather than two.

**A message that has already landed lands once.** The platform's own id for it is written down, and
the partial unique index behind that is what makes a redelivery — which every chat platform does,
and Slack does on a timer — cost nothing the second time. The previous build had that column, had
that index, and no adapter ever passed an id through the seam, so the guard was correct and
prevented nothing while the same build re-solved the problem in one adapter's memory, which did not
survive a restart.

**Nothing here decides whether somebody may be answered.** That is `kept.who_may_reach` and it is
asked before this is reached: a message from a stranger is never recorded, because a record of it is
a thing an agent could later be asked to read.

May depend on `agents`, `core` and `utils`.
"""

import secrets
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from rundesk.agents import directory, records
from rundesk.core import config

#: Where a conversation came from. The vocabulary the column holds is wider still, and step `0003`
#: says why it is stated in full rather than grown later.
FROM_CHANNEL = "channel"
FROM_SCHEDULE = "schedule"

#: Another named agent handed this agent a bounded task. A conversation of its own, never one a
#: person is typing into — `recorded_for_a_delegation` says why.
FROM_AGENT = "agent"

#: Somebody typing. One conversation per agent — asking again is carrying the same exchange on.
FROM_TERMINAL = "terminal"

#: Who said a thing. `rundesk` is the product speaking for itself — a gateway coming up, a schedule
#: that failed — and is deliberately neither the agent nor a person, because a reader of the history
#: has to be able to tell what the agent said from what was said on its behalf.
BY_AGENT = "agent"
BY_USER = "user"
BY_RUNDESK = "rundesk"

#: How much of one message is kept. Bounded because this is a stranger's text arriving on somebody
#: else's schedule, and an agent's records are not somewhere a chat platform gets to fill. Generous
#: enough that no ordinary message is touched.
BODY_AT_MOST = 64 * 1024

#: How many conversations a listing answers with unless somebody asks for more. Generous, because
#: this is a person looking at their own agent rather than a brain spending tokens — but a ceiling,
#: because a channel makes a conversation per room and per person for as long as the agent lives.
CONVERSATIONS_AT_MOST = 200

#: A pending message belongs only to the unresolved tail of its conversation. Once a later message
#: has been admitted, the exchange has moved past every older unclaimed row: replaying one after a
#: restart starts work the person has already continued beyond, and can answer an already-answered
#: retry a second time. Derived from the existing exact turn boundary rather than wall-clock age, so
#: a genuinely stranded latest message remains recoverable however long a gateway was unavailable.
NO_LATER_ADMITTED = (
    " AND NOT EXISTS (SELECT 1 FROM conversation_messages AS later"
    " WHERE later.conversation_id = m.conversation_id AND later.id > m.id"
    " AND later.turn_id IS NOT NULL)"
)


class Landed(NamedTuple):
    """What became of one arriving message.

    `fresh` is the field that matters: `False` means the platform sent it twice and this is the
    record that was already here. A caller that started a turn without asking would start a second
    one for a message somebody sent once.
    """

    conversation: int
    message: int
    fresh: bool


class Pending(NamedTuple):
    """One channel message recorded durably before any turn admitted it."""

    channel: str
    place: str
    author_id: str
    body: str
    external_id: Optional[str]
    landed: Landed


def recorded(agent: str, channel: str, place: str, author_id: str, body: str,
             external_id: Optional[str] = None, when: Optional[datetime] = None) -> Landed:
    """Write down one thing that arrived, making its conversation if this is the first of them.

    Both writes are in one transaction: a conversation with nothing in it is a row nothing would
    ever look at again, and a message whose conversation failed to land has nowhere to hang.
    """
    said = _bounded(body)
    now = _now(when)
    with records.writing(directory.records(agent)) as conn:
        conversation = _conversation(conn, agent, FROM_CHANNEL, place, channel, now)
        message, fresh = _message(conn, agent, conversation, BY_USER, author_id, said,
                                  external_id, now)
    return Landed(conversation, message, fresh)


def said_by_rundesk(agent: str, channel: str, place: str, body: str,
                    external_id: Optional[str] = None,
                    when: Optional[datetime] = None) -> Landed:
    """Write down something rundesk said on its own behalf, in the place it said it.

    Kept beside what people said rather than in a log of its own, because somebody reading a
    conversation back needs the gateway notice that interrupted it in the same order it arrived.
    """
    now = _now(when)
    with records.writing(directory.records(agent)) as conn:
        conversation = _conversation(conn, agent, FROM_CHANNEL, place, channel, now)
        message, fresh = _message(conn, agent, conversation, BY_RUNDESK, "rundesk",
                                  _bounded(body), external_id, now)
    return Landed(conversation, message, fresh)


def asked_at_a_terminal(agent: str, body: str, when: Optional[datetime] = None) -> Landed:
    """Write down something somebody typed at a terminal, in this agent's terminal conversation.

    **One conversation per agent, not one per command.** Asking again at a terminal is carrying the
    same exchange on — which is what a person means by asking again — so the place is the agent's own
    name and the same row is found every time.

    No `external_id`: a terminal has no message ids of its own, and two identical questions typed
    twice are two questions rather than one asked twice.
    """
    now = _now(when)
    with records.writing(directory.records(agent)) as conn:
        conversation = _conversation(conn, agent, FROM_TERMINAL, agent, None, now)
        message, fresh = _message(conn, agent, conversation, BY_USER, FROM_TERMINAL,
                                  _bounded(body), None, now)
    return Landed(conversation, message, fresh)


def recorded_for_a_schedule(agent: str, schedule: str, body: str,
                            when: Optional[datetime] = None,
                            invocation: Optional[str] = None) -> Landed:
    """Write down what one schedule invocation asked, in a fresh conversation.

    **One conversation per invocation, and never the one a person types into.** The schedule name
    remains the prefix so a later delegated result can recover which unattended situation it is
    resuming, while the random suffix prevents tonight from inheriting last night's provider
    session.

    Written as `rundesk` rather than as a person, because nobody asked: the clock did.
    """
    now = _now(when)
    source_id = f"{schedule}/{invocation or secrets.token_hex(16)}"
    with records.writing(directory.records(agent)) as conn:
        conversation = _conversation(conn, agent, FROM_SCHEDULE, source_id, None, now)
        message, fresh = _message(conn, agent, conversation, BY_RUNDESK, FROM_SCHEDULE,
                                  _bounded(body), None, now)
    return Landed(conversation, message, fresh)


def said_by_rundesk_into(agent: str, conversation: int, body: str,
                          when: Optional[datetime] = None,
                          external_id: Optional[str] = None) -> Landed:
    """Write down something rundesk said, in a conversation already known by its id.

    The sibling of `said_by_rundesk`, which finds the conversation from a channel and a place. This
    one is handed the conversation, because what puts a delegated answer in front of an agent knows
    exactly which exchange it belongs to and has no channel to name.

    `BY_RUNDESK` and never `BY_AGENT`: what another agent said is not this agent's own words, and a
    reader of the history has to be able to tell the two apart.
    """
    now = _now(when)
    with records.writing(directory.records(agent)) as conn:
        message, fresh = _message(conn, agent, conversation, BY_RUNDESK, "rundesk",
                                  _bounded(body), external_id, now)
    return Landed(conversation, message, fresh)


def recorded_for_a_delegation(agent: str, delegator: str, parent_turn: int, body: str,
                              when: Optional[datetime] = None,
                              delegation_id: Optional[str] = None,
                              legacy_fallback: bool = False) -> Landed:
    """Write down what another agent asked, in a conversation of its own.

    **This is the one place a gateway writes an agent's store that is not its own**, and it is a
    *delivery* rather than bookkeeping — the same act the Discord adapter performs when a message
    arrives. What stays the answering agent's own is everything downstream: it makes the turn, it
    records it, and it holds no account of somebody else's delegation.

    **Keyed by the delegation as well as who asked and which turn**, so two bounded tasks from one
    turn cannot share a provider session or answer. Guidance and resumed work carry the same id and
    therefore return to that delegation's session. Old callers with no id retain the earlier key so
    delegations written before this boundary remain readable.

    **The format is spelled here and in `delegations.kept.source_id_for`, and it has to stay the
    same in both.** This layer may not import that one, so the two cannot share a function;
    `tests/test_layers.py` compares them instead, the way it already compares the two spellings of a
    gateway's own files. Left to agree by hand they would eventually not, and the symptom is an
    answer written into a conversation nobody is reading.

    **Never the conversation a person is typing into**, which is what `FROM_AGENT` buys: an answer
    to another agent turning up in the middle of somebody's exchange is the fault the schedules got
    a conversation of their own to avoid.

    Written as `BY_AGENT` under the *delegator's* name rather than the answering agent's, so reading
    the history back tells a colleague's request apart from this agent's own words by a column
    rather than by a prefix somebody has to parse.
    """
    now = _now(when)
    legacy = f"{delegator}/{parent_turn}"
    source_id = f"{legacy}/{delegation_id}" if delegation_id else legacy
    with records.writing(directory.records(agent)) as conn:
        if delegation_id and legacy_fallback:
            current = _rows(
                conn, agent,
                "SELECT source_id FROM conversations WHERE source = ? AND source_id IN (?, ?)"
                " ORDER BY CASE source_id WHEN ? THEN 0 ELSE 1 END LIMIT 1",
                (FROM_AGENT, source_id, legacy, source_id)).fetchone()
            if current is not None:
                source_id = str(current["source_id"])
        conversation = _conversation(conn, agent, FROM_AGENT, source_id, None, now)
        message, fresh = _message(conn, agent, conversation, BY_AGENT, delegator,
                                  _bounded(body), None, now)
    return Landed(conversation, message, fresh)


def said_by_agent(agent: str, source: str, place: str, body: str, turn: Optional[int] = None,
                  external_id: Optional[str] = None,
                  when: Optional[datetime] = None) -> Landed:
    """Write down what the agent itself answered, in the conversation it answered in.

    The other half of `recorded`, and the one `BY_AGENT` was defined for. Kept beside what people
    said rather than in a log of its own, because a conversation read back has to read as a
    conversation — and because this is what a search over what was said actually searches.

    **One message for the whole answer, not one per fragment.** A brain writes its reply a piece at a
    time; a row per piece is a history nobody can read back and a search that matches half a
    sentence. Whoever calls this has already joined them.

    `turn` is the turn that produced it, so what a turn said and what it did are readable together.
    """
    now = _now(when)
    with records.writing(directory.records(agent)) as conn:
        conversation = _conversation(conn, agent, source, place,
                                     place if source == FROM_CHANNEL else None, now)
        message, fresh = _message(conn, agent, conversation, BY_AGENT, agent,
                                  _bounded(body), external_id, now, turn=turn)
    return Landed(conversation, message, fresh)


def said_by_agent_into(agent: str, conversation: int, body: str,
                       turn: Optional[int] = None, external_id: Optional[str] = None,
                       when: Optional[datetime] = None) -> Landed:
    """Write the agent's answer into the exact conversation its admitted turn belongs to."""
    now = _now(when)
    with records.writing(directory.records(agent)) as conn:
        message, fresh = _message(conn, agent, conversation, BY_AGENT, agent,
                                  _bounded(body), external_id, now, turn=turn)
    return Landed(conversation, message, fresh)


def schedule_name(source_id: str) -> str:
    """The schedule prefix in an invocation source id, including legacy unsuffixed ids."""
    return source_id.rsplit("/", 1)[0] if "/" in source_id else source_id


def where_it_stands(agent: str, conversation: int) -> Optional[Tuple[str, str]]:
    """The `source` and `source_id` this conversation was made under, or `None` if there is no such
    conversation.

    **What a turn has to be told so its answer lands where it was asked.** `said_by_agent` resolves
    the conversation to write into from `(source, place)` rather than from an id, so a caller that
    passed a plausible-looking pair instead of the real one gets a *new* conversation and an answer
    nobody is reading. Measured: a delegated turn answered into a conversation of its own six times
    over, while the one that asked sat unanswered and the gateway started a turn every beat.

    So a caller that already knows the conversation asks here rather than reconstructing the pair.
    """
    try:
        with records.reading(directory.records(agent)) as conn:
            row = _rows(conn, agent, "SELECT source, source_id FROM conversations WHERE id = ?",
                        (conversation,)).fetchone()
    except (records.NotThere, records.Unreadable, OSError):
        return None
    return (str(row["source"]), str(row["source_id"])) if row else None


def on_which_channel(agent: str, conversation: int) -> Optional[str]:
    """Which channel adapter this conversation arrived on, or `None` where it arrived on none.

    **The kind, which `where_it_stands` cannot give.** That one answers `(source, place)`, and `place`
    is the platform's own name for a room — enough to write an answer back into the records and not
    enough to send one out, because sending needs the adapter that speaks to that platform. The
    column has held it since `0003`; nothing had asked for it, and a turn that wanted to answer where
    it was asked had no way to find out where that was.

    `None` for a schedule, a terminal or a delegation, and that is an ordinary answer rather than a
    hole: those conversations stand on no platform, and a caller told `None` is being told there is
    nobody out there to post to.
    """
    try:
        with records.reading(directory.records(agent)) as conn:
            row = _rows(conn, agent, "SELECT channel FROM conversations WHERE id = ?",
                        (conversation,)).fetchone()
    except (records.NotThere, records.Unreadable, OSError):
        return None
    return str(row["channel"]) if row and row["channel"] else None


def conversations(agent: str, most: int = CONVERSATIONS_AT_MOST) -> List[Dict[str, Any]]:
    """This agent's conversations, newest first.

    **Bounded, like every other read here.** A busy channel makes a conversation per room and per
    person indefinitely, so the unbounded form was one query that grew for the life of the agent
    while every read beside it had a ceiling. Newest first is what makes a default honest: the
    ceiling cuts off the oldest, which is the end nobody was looking for.
    """
    with records.reading(directory.records(agent)) as conn:
        return [dict(row) for row in _rows(
            conn, agent, "SELECT * FROM conversations ORDER BY id DESC LIMIT ?", (most,))]


def messages(agent: str, conversation: int, most: int = 50) -> List[Dict[str, Any]]:
    """The last `most` messages of one conversation, oldest first.

    Oldest first because that is the order somebody reads an exchange in, and the last `most`
    because the interesting end of a long one is the recent end.
    """
    with records.reading(directory.records(agent)) as conn:
        found = _rows(conn, agent,
                      "SELECT * FROM conversation_messages WHERE conversation_id = ?"
                      " ORDER BY id DESC LIMIT ?", (conversation, most)).fetchall()
    return [dict(row) for row in reversed(found)]


def pending_from(agent: str, conversation: int, author_id: str,
                 most: int) -> List[Tuple[int, str]]:
    """Pending inbound messages from one author, oldest first and bounded.

    A delegated turn calls this while it runs so guidance written by another process can enter the
    same provider turn. Reading does not claim anything: `handled_by_turn` makes the exact atomic
    claim only after the turn has proved it is still accepting input.
    """
    with records.reading(directory.records(agent)) as conn:
        found = _rows(
            conn, agent,
            "SELECT id, body FROM conversation_messages"
            " WHERE conversation_id = ? AND author_id = ? AND turn_id IS NULL"
            " ORDER BY id LIMIT ?", (conversation, author_id, most)).fetchall()
    return [(int(one["id"]), str(one["body"] or "")) for one in found]


def pending_on_channels(agent: str, most: int,
                        channels: Optional[Tuple[str, ...]] = None,
                        after: int = 0) -> List[Pending]:
    """Unclaimed user messages from channel conversations, oldest first and bounded.

    This is the restart boundary: a gateway may end after recording a platform message but before
    its answering thread acquires the provider claim. A fresh adapter will not necessarily receive
    that platform event again, so the durable row is what must wake the replacement gateway.

    Only the unresolved tail of a conversation may wake it. A later admitted message proves the
    exchange progressed after an older row failed admission; replaying that row after an unrelated
    restart is stale work, even when its platform id still makes the transport idempotent.
    """
    if channels is not None and not channels:
        return []
    channel_clause = ""
    parameters: Tuple[Any, ...] = (FROM_CHANNEL, BY_USER, after)
    if channels is not None:
        channel_clause = " AND c.channel IN (" + ",".join("?" for _one in channels) + ")"
        parameters += tuple(channels)
    parameters += (most,)
    with records.reading(directory.records(agent)) as conn:
        found = _rows(
            conn, agent,
            "SELECT m.id, m.conversation_id, m.author_id, m.body, m.external_id,"
            " c.channel, c.source_id FROM conversation_messages AS m"
            " JOIN conversations AS c ON c.id = m.conversation_id"
            " WHERE c.source = ? AND m.author = ? AND m.turn_id IS NULL"
            " AND m.external_id IS NOT NULL AND m.id > ?"
            + NO_LATER_ADMITTED
            + channel_clause +
            " ORDER BY m.id LIMIT ?", parameters).fetchall()
    return [Pending(
        channel=str(one["channel"] or ""), place=str(one["source_id"]),
        author_id=str(one["author_id"]), body=str(one["body"] or ""),
        external_id=(str(one["external_id"]) if one["external_id"] is not None else None),
        landed=Landed(int(one["conversation_id"]), int(one["id"]), True)) for one in found]


def turn_for_message(agent: str, conversation: int, message: int) -> Optional[int]:
    """The turn that admitted one exact message, or `None` while it remains pending."""
    with records.reading(directory.records(agent)) as conn:
        found = _rows(
            conn, agent,
            "SELECT turn_id FROM conversation_messages WHERE conversation_id = ? AND id = ?",
            (conversation, message)).fetchone()
    if found is None:
        raise records.NotThere(f"message {message} is not in conversation {conversation}")
    return int(found["turn_id"]) if found["turn_id"] is not None else None


def delegation_brief(agent: str, delegator: str, parent_turn: int,
                     delegation_id: str) -> str:
    """The first task message for one delegation, or ``""`` when it cannot be found.

    The query surface uses only a bounded identity made from this body. Keeping the read here means
    the conversation store still owns how modern and pre-boundary delegation keys are reconciled;
    a gateway does not gain a second spelling of that durable identity.
    """
    modern = f"{delegator}/{parent_turn}/{delegation_id}"
    legacy = f"{delegator}/{parent_turn}"
    with records.reading(directory.records(agent)) as conn:
        found = _rows(
            conn, agent,
            "SELECT m.body FROM conversation_messages AS m"
            " JOIN conversations AS c ON c.id = m.conversation_id"
            " WHERE c.source = ? AND c.source_id IN (?, ?) AND m.author = ?"
            " AND m.author_id = ?"
            " ORDER BY CASE c.source_id WHEN ? THEN 0 ELSE 1 END, m.id LIMIT 1",
            (FROM_AGENT, modern, legacy, BY_AGENT, delegator, modern),
        ).fetchone()
    return str(found["body"] or "") if found is not None else ""


def delegation_review_turn(agent: str, conversation: int,
                           delegation_id: str) -> Optional[int]:
    """The turn handling this delegation's latest returned result, or ``None`` while unclaimed.

    Result bodies are deliberately not selected. A state query needs only the durable association,
    and selecting less makes exposing a specialist's full result through this seam impossible by
    accident.
    """
    prefix = f"delegation-result:{delegation_id}:"
    with records.reading(directory.records(agent)) as conn:
        found = _rows(
            conn, agent,
            "SELECT turn_id FROM conversation_messages"
            " WHERE conversation_id = ? AND external_id IS NOT NULL"
            " AND substr(external_id, 1, length(?)) = ? ORDER BY id DESC LIMIT 1",
            (conversation, prefix, prefix),
        ).fetchone()
    if found is None or found["turn_id"] is None:
        return None
    return int(found["turn_id"])


def handled_by_turn(agent: str, conversation: int, messages: tuple, turn: int) -> None:
    """Associate pending inbound `messages` with the turn that received them.

    Delegation guidance can arrive while an earlier turn runs. Leaving every inbound message's
    `turn_id` empty makes that earlier reply look like it answered later guidance merely because it
    was written afterward. Exact ids make the boundary durable and race-free.
    """
    ids = tuple(dict.fromkeys(int(one) for one in messages))
    if not ids:
        return
    marks = ", ".join("?" for _one in ids)
    with records.writing(directory.records(agent)) as conn:
        changed = _rows(
            conn, agent,
            f"UPDATE conversation_messages SET turn_id = ? WHERE conversation_id = ?"
            f" AND turn_id IS NULL AND id IN ({marks})",
            (turn, conversation, *ids)).rowcount
        if changed != len(ids):
            # Inside the transaction so one valid id beside one stale id claims neither. A partial
            # claim would split one provider prompt across two future turns.
            raise records.Unreadable(
                f"{agent} could not associate every inbound message with turn {turn}")


def released_by_turn(agent: str, conversation: int, messages: tuple, turn: int) -> None:
    """Return exact inbound messages to pending when a provider refused their live steer.

    A durable delegation word is claimed before it enters the active turn's in-memory queue. If the
    provider has already stopped accepting input, that claim must be undone or the word belongs to
    a turn that never read it and no later turn can recover it. Exact ids and the exact former turn
    make this the inverse of `handled_by_turn`, not a broad reset of conversation history.
    """
    ids = tuple(dict.fromkeys(int(one) for one in messages))
    if not ids:
        return
    marks = ", ".join("?" for _one in ids)
    with records.writing(directory.records(agent)) as conn:
        changed = _rows(
            conn, agent,
            f"UPDATE conversation_messages SET turn_id = NULL WHERE conversation_id = ?"
            f" AND turn_id = ? AND id IN ({marks})",
            (conversation, turn, *ids)).rowcount
        if changed != len(ids):
            raise records.Unreadable(
                f"{agent} could not release every inbound message from turn {turn}")


def last_answer(agent: str, source: str, place: str, after: str = "") -> str:
    """The last thing the agent itself said in one conversation. `""` where it has said nothing.

    **What a scheduled run came to, read back by the layer that reports it.** A schedule's turn runs
    in a process of its own, which holds no channel and cannot post anything; the gateway that
    reaped it holds the channels and never saw a word of the answer. This is where the two meet —
    the answer is already written down, keyed by the conversation the run had.

    **Only what the agent said**, never what rundesk said on its behalf: the schedule's own prompt is
    written into the same conversation as `rundesk`, and a report that posted that back would be
    quoting the question as though it were the answer.

    **`after` is what makes this *this run's* answer.** It protects legacy shared schedule
    conversations and any caller looking across several runs from attributing yesterday's answer to
    today's failed run.

    A moment in `core.config.MOMENT`, which is what these records keep and why a plain string
    comparison is the whole of the test. `""` means unbounded and is for a caller that genuinely
    wants the latest, whatever run it came from.

    `""` for a run that produced nothing is an ordinary answer and not a failure — a turn that failed
    on its way to the brain has an outcome worth reporting and no words of its own. The caller says
    what happened instead of falling silent.
    """
    since = " AND m.created_at >= ?" if after else ""
    values = (source, place, BY_AGENT) + ((after,) if after else ())
    with records.reading(directory.records(agent)) as conn:
        found = _rows(conn, agent,
                      "SELECT m.body FROM conversation_messages m"
                      " JOIN conversations c ON c.id = m.conversation_id"
                      " WHERE c.source = ? AND c.source_id = ? AND m.author = ?"
                      f"{since}"
                      " ORDER BY m.id DESC LIMIT 1",
                      values).fetchone()
    return str(found[0]) if found is not None else ""


def last_schedule_answer(agent: str, schedule: str, after: str = "") -> str:
    """The last answer from this schedule's turns, across invocation conversations."""
    since = " AND m.created_at >= ?" if after else ""
    values = (schedule, BY_AGENT) + ((after,) if after else ())
    with records.reading(directory.records(agent)) as conn:
        found = _rows(
            conn, agent,
            "SELECT m.body FROM conversation_messages m"
            " JOIN turns t ON t.id = m.turn_id"
            " WHERE t.schedule_name = ? AND m.author = ?"
            f"{since} ORDER BY m.id DESC LIMIT 1", values).fetchone()
    return str(found[0]) if found is not None else ""


def delegation_result_reached_turn(agent: str, turn: int) -> bool:
    """Whether a returned delegation was admitted into this still-running parent turn."""
    with records.reading(directory.records(agent)) as conn:
        found = _rows(
            conn, agent,
            "SELECT 1 FROM conversation_messages"
            " WHERE turn_id = ? AND external_id LIKE 'delegation-result:%' LIMIT 1",
            (turn,)).fetchone()
    return found is not None


def standing_in(agent: str, place: str) -> Optional[int]:
    """The conversation a place already has, or `None` where nothing has been said in it yet.

    **A read that never writes**, which is what tells it apart from `_conversation` below. A gesture
    is not something said — somebody asking to start fresh in a room nobody has ever spoken in has
    nothing to forget, and making a conversation to answer that would put a row in the records for an
    exchange that never happened.

    Keyed exactly as `recorded` keys it, on the place alone: which channel it arrived through is a
    column beside it rather than part of its name, and a lookup that spelled the key differently
    would answer `None` for every conversation that exists.
    """
    with records.reading(directory.records(agent)) as conn:
        found = _rows(conn, agent,
                      "SELECT id FROM conversations WHERE source = ? AND source_id = ?",
                      (FROM_CHANNEL, place)).fetchone()
    return int(found[0]) if found is not None else None


def _conversation(conn: sqlite3.Connection, agent: str, source: str, source_id: str,
                  channel: Optional[str], now: str) -> int:
    """The id of the conversation this belongs to, making it if this is the first thing in it.

    **Insert-then-read rather than read-then-insert.** The read-first shape has a gap in it: two
    gateways that both look, both find nothing, and both insert would make two conversations for one
    exchange — and only one of them would then hold the history. `ON CONFLICT DO NOTHING` moves the
    decision into the statement, where the `UNIQUE (source, source_id)` behind it settles it.
    """
    _rows(conn, agent,
          "INSERT INTO conversations (source, source_id, channel, created_at)"
          " VALUES (?, ?, ?, ?) ON CONFLICT (source, source_id) DO NOTHING",
          (source, source_id, channel, now))
    found = _rows(conn, agent,
                  "SELECT id FROM conversations WHERE source = ? AND source_id = ?",
                  (source, source_id)).fetchone()
    if found is None:
        raise records.Unreadable(f"{agent} could not record where a message came from")
    return int(found[0])


def _message(conn: sqlite3.Connection, agent: str, conversation: int, author: str,
             author_id: str, body: str, external_id: Optional[str], now: str,
             turn: Optional[int] = None) -> tuple:
    """Write one message down, or find the one already there. Hands back `(id, fresh)`.

    The same insert-then-read shape and for the same reason, with one difference worth naming: a
    message with no `external_id` is **always** fresh. Two identical lines nobody gave an id to are
    two things somebody said, not one said twice, and the partial index behind this agrees — it
    covers only the rows that have one.
    """
    said = _rows(conn, agent,
                 "INSERT INTO conversation_messages (conversation_id, author, author_id, body,"
                 " external_id, created_at, turn_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
                 # **The `WHERE` is not optional and is not decoration.** The index behind this is
                 # partial, and SQLite matches an `ON CONFLICT` target to an index by its columns
                 # *and* its predicate — without it the statement is refused outright with "does not
                 # match any PRIMARY KEY or UNIQUE constraint", which is what happened here first.
                 # It also says the thing that is true: a row with no id is covered by no index and
                 # therefore conflicts with nothing, which is why every such message is fresh.
                 " ON CONFLICT (conversation_id, external_id) WHERE external_id IS NOT NULL"
                 " DO NOTHING",
                 (conversation, author, author_id, body, external_id, now, turn))
    if said.rowcount:
        return int(said.lastrowid), True
    found = _rows(conn, agent,
                  "SELECT id FROM conversation_messages WHERE conversation_id = ?"
                  " AND external_id = ?", (conversation, external_id)).fetchone()
    if found is None:
        raise records.Unreadable(f"{agent} could not record what arrived")
    return int(found[0]), False


def _bounded(said: str) -> str:
    """One message, clipped to what an agent's records will hold of it.

    Clipped rather than refused: a message too long to keep whole is still a message somebody sent,
    and dropping it entirely would lose the part that was readable along with the part that was not.
    """
    return said if len(said) <= BODY_AT_MOST else said[:BODY_AT_MOST]


def _rows(conn: sqlite3.Connection, agent: str, sql: str, values: tuple = ()) -> sqlite3.Cursor:
    """Ask, saying which agent it was when the records cannot answer."""
    try:
        return conn.execute(sql, values)
    except sqlite3.DatabaseError as why:
        raise records.Unreadable(
            f"{agent} does not hold conversations that can be read: {why}") from why


def _now(when: Optional[datetime] = None) -> str:
    """A moment this product keeps for a machine to compare, in the one shape it keeps them in."""
    return config.moment_of(when)
