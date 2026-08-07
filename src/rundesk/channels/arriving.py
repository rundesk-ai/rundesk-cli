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

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, NamedTuple, Optional

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


class Landed(NamedTuple):
    """What became of one arriving message.

    `fresh` is the field that matters: `False` means the platform sent it twice and this is the
    record that was already here. A caller that started a turn without asking would start a second
    one for a message somebody sent once.
    """

    conversation: int
    message: int
    fresh: bool


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
                            when: Optional[datetime] = None) -> Landed:
    """Write down what a schedule asked, in that schedule's own conversation.

    **One conversation per schedule, and never the one a person types into.** In the build this
    replaces a scheduled turn resumed the owner's own session and left its prompt and its answer in
    the middle of it — so a run at three in the morning appeared as though somebody had asked.

    Written as `rundesk` rather than as a person, because nobody asked: the clock did.
    """
    now = _now(when)
    with records.writing(directory.records(agent)) as conn:
        conversation = _conversation(conn, agent, FROM_SCHEDULE, schedule, None, now)
        message, fresh = _message(conn, agent, conversation, BY_RUNDESK, FROM_SCHEDULE,
                                  _bounded(body), None, now)
    return Landed(conversation, message, fresh)


def said_by_rundesk_into(agent: str, conversation: int, body: str,
                          when: Optional[datetime] = None) -> Landed:
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
                                  _bounded(body), None, now)
    return Landed(conversation, message, fresh)


def recorded_for_a_delegation(agent: str, delegator: str, parent_turn: int, body: str,
                              when: Optional[datetime] = None) -> Landed:
    """Write down what another agent asked, in a conversation of its own.

    **This is the one place a gateway writes an agent's store that is not its own**, and it is a
    *delivery* rather than bookkeeping — the same act the Discord adapter performs when a message
    arrives. What stays the answering agent's own is everything downstream: it makes the turn, it
    records it, and it holds no account of somebody else's delegation.

    **Keyed by who asked and which of their turns**, so two delegations from one turn share a
    conversation and therefore a provider session, and one from a later turn starts its own. That
    key is constructed by `delegations.kept.source_id_for` and never stored, because a stored id
    would point into a database the delegator may not follow it into.

    **Never the conversation a person is typing into**, which is what `FROM_AGENT` buys: an answer
    to another agent turning up in the middle of somebody's exchange is the fault the schedules got
    a conversation of their own to avoid.

    Written as `BY_AGENT` under the *delegator's* name rather than the answering agent's, so reading
    the history back tells a colleague's request apart from this agent's own words by a column
    rather than by a prefix somebody has to parse.
    """
    now = _now(when)
    with records.writing(directory.records(agent)) as conn:
        conversation = _conversation(conn, agent, FROM_AGENT, f"{delegator}/{parent_turn}",
                                     None, now)
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


def last_answer(agent: str, source: str, place: str, after: str = "") -> str:
    """The last thing the agent itself said in one conversation. `""` where it has said nothing.

    **What a scheduled run came to, read back by the layer that reports it.** A schedule's turn runs
    in a process of its own, which holds no channel and cannot post anything; the gateway that
    reaped it holds the channels and never saw a word of the answer. This is where the two meet —
    the answer is already written down, keyed by the conversation the run had.

    **Only what the agent said**, never what rundesk said on its behalf: the schedule's own prompt is
    written into the same conversation as `rundesk`, and a report that posted that back would be
    quoting the question as though it were the answer.

    **`after` is what makes this *this run's* answer, and leaving it out is a real defect rather than
    a loose end.** Every firing of one schedule shares a single conversation — it is keyed by the
    schedule's name and nothing else — and a turn writes a message only when it actually produced
    words. So a schedule that answered on Monday and failed on Tuesday without saying anything has,
    on Tuesday, exactly one agent message in its conversation: Monday's. Read without a bound, that
    is posted under Tuesday's notice as though it were Tuesday's report, and the failure is never
    mentioned at all — an answer nobody earned, reported as fact, which is the failure this product
    is built around refusing. Bounded by the moment the firing began, only what was said after the
    run started can be the run's.

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
