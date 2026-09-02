"""The channels one agent keeps, and the only way in to them.

Everything here goes through `agents.records` — its connections, its transactions, its busy timeout
and its four answers. There is no second way into an agent's database, and this module exists so
that there does not become one.

**A channel is found by its platform**, because a channel *is* its platform: one Discord connection
per agent, so `kind` is both the name somebody types and the row's identity. There is nothing to
invent and nothing to disambiguate.

## Two things a caller may not simply set

**`notified` is not in `SETTABLE`, and `telling` is the only way to move it.** At most one channel
may claim it, held by a partial unique index — so a caller setting it directly would have to clear
the previous one first, in the same transaction, and get the order right. Any caller that got that
wrong would be refused by the index, which is the good outcome; the bad one is the caller who clears
first, fails to set, and leaves an agent that tells nobody anything. `telling` does both under one
transaction and answers for it.

**`allowed` is a list, so it is changed by what goes in and out of it rather than by being replaced.**
`allowing` reads, decides and writes inside one transaction. Handing a caller the whole list to
rewrite is how two commands racing each other lose one of the two changes, and this is the list that
decides who may reach the agent.

Neither of those can reach zero or two: the records refuse an empty allow list and a second notified
channel, and this module refuses them earlier, in words about what somebody typed rather than about
a constraint they have never seen.

## What an entry in that list may name

**A bare entry is a sender id and always was**, so every list written before this paragraph existed
goes on meaning exactly what it meant. A typed entry says which kind of thing it names — `sender:`
for one person on that platform, `place:` for one place on it, where anybody the platform reports as
being there may reach the agent. There is no schema change and nothing to carry forward: the column
is a JSON array of strings either way, and `admitting` is the one place that reads what a string
means.

**The decision stays here and never moves to the adapter.** An adapter supplies the two stable
identifiers a platform knows — who spoke, and where — and `channels.hosting` asks this module
whether that pair is admitted. An adapter narrows first to avoid working for nothing; nothing it
sends is the decision.

May depend on `agents`, `core` and `utils`.
"""

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from rundesk.agents import directory, records
from rundesk.core import config

#: The table, named once.
TABLE = "channels"

#: What a caller may state through `added` and `changed`. Narrower than the table on purpose: `id`
#: and `kind` are the row's identity, `created_at` is the records' own account of themselves, and
#: `notified` has `telling` because it is the one column two rows may not agree about.
SETTABLE = ("describes", "notify_place", "secret_names", "settings", "allowed")

#: The two things an allow entry may name, and the separator that marks one as typed. **Closed, and
#: that is the whole of its value**: an entry whose prefix is anything else is a bare sender id, so a
#: platform whose ids happen to contain a colon keeps meaning what it meant. Written as words rather
#: than as letters because they are also what somebody types after `--allow`.
SENDER = "sender"
PLACE = "place"
TYPED = (SENDER, PLACE)
AS = ":"


class Admitting(NamedTuple):
    """Who a channel admits, and from where. Read once when an adapter starts, asked per message.

    Two tuples rather than two sets, because the order somebody typed is load-bearing on the way
    out: an adapter reports where unprompted things would land by opening a conversation with the
    **first** sender on the list, so a set would hand it a different owner between runs.
    """

    #: Every sender id this channel names, in the order the list holds them.
    senders: Tuple[str, ...]
    #: Every external place id this channel names, in the same order.
    places: Tuple[str, ...]

    def admits(self, sender: str, place: str = "") -> bool:
        """Whether this pair may reach the agent. **An unnamed sender is never one of them.**

        A place entry allows anybody the platform reports as being in that place, and *anybody* is
        still somebody: a record arriving with no sender at all is an event rather than a person —
        a bot, a join notice, a platform's own housekeeping — and admitting one because of where it
        happened would turn a place entry into a way in for anything that can post there.
        """
        if not sender:
            return False
        if sender in self.senders:
            return True
        return bool(place) and place in self.places


class Refused(Exception):
    """Something that may not be done to a channel, named with why.

    A sentence rather than a code, for the reason `directory.Refused` gives: every caller has to tell
    somebody what to type instead, and a caller left to invent that wording invents a different one.
    """


def all(agent: str) -> List[Dict[str, Any]]:  # noqa: A001 — the same reason `schedules.kept.all` has
    """Every channel this agent keeps, in platform order.

    No channels is an answer rather than a failure. Records that cannot be read are left to raise,
    because answering "none" would tell somebody their channels are gone at the moment they are
    merely unreadable — and the next thing they do is configure them again over the top.
    """
    with records.reading(directory.records(agent)) as conn:
        return [dict(row) for row in _rows(conn, agent, "SELECT * FROM channels ORDER BY kind")]


def one(agent: str, kind: str) -> Dict[str, Any]:
    """One channel, whole. `records.NotThere` when this agent is not connected to that platform."""
    with records.reading(directory.records(agent)) as conn:
        found = _rows(conn, agent, "SELECT * FROM channels WHERE kind = ?", (kind,)).fetchone()
    if found is None:
        raise records.NotThere(f"{agent} has no {kind} channel")
    return dict(found)


def told(agent: str) -> Optional[Dict[str, Any]]:
    """The channel unprompted things go to, or `None` when this agent tells nobody anything.

    `None` is an ordinary answer and never a failure: an agent nobody has asked to be told about is
    an agent that says nothing, which is what somebody who configured no channel asked for.
    """
    with records.reading(directory.records(agent)) as conn:
        found = _rows(conn, agent, "SELECT * FROM channels WHERE notified = 1").fetchone()
    return dict(found) if found else None


def added(agent: str, kind: str, values: Dict[str, Any],
          when: Optional[datetime] = None) -> None:
    """Write down a new channel. `Refused` when the platform is already connected.

    **A platform already there is refused rather than replaced**, and the refusal is the `UNIQUE`
    constraint doing it inside the transaction rather than a check-then-insert with a gap in the
    middle. Reconnecting is `changed`, which keeps what the channel already knows.
    """
    stated = dict(values, kind=kind, created_at=_now(when))
    _only_settable(sorted(values))
    _a_list(stated.get("allowed"), "allowed")
    named = sorted(stated)
    with records.writing(directory.records(agent)) as conn:
        _known(conn, agent, named)
        try:
            conn.execute(
                "INSERT INTO channels (" + ", ".join(named) + ") "
                "VALUES (" + ", ".join("?" for _ in named) + ")",
                [stated[key] for key in named])
        except sqlite3.IntegrityError as why:
            raise Refused(_why_the_records_refused(agent, kind, why)) from why


def changed(agent: str, kind: str, values: Dict[str, Any]) -> None:
    """Change a channel in place, keeping everything else it holds.

    **All of it or none of it** — every name is checked against the live table before anything is
    written, the same rule `records.stated` keeps: naming two columns and getting one wrong must
    change neither, because half of what was meant is not a smaller change but a different one
    nobody typed.
    """
    if not values:
        raise Refused(f"nothing was named to change about {agent}'s {kind} channel")
    _only_settable(sorted(values))
    if "allowed" in values:
        _a_list(values["allowed"], "allowed")

    named = sorted(values)
    with records.writing(directory.records(agent)) as conn:
        _known(conn, agent, named)
        try:
            moved = conn.execute(
                "UPDATE channels SET " + ", ".join(f"{key} = ?" for key in named) +
                " WHERE kind = ?", [values[key] for key in named] + [kind]).rowcount
        except sqlite3.IntegrityError as why:
            raise Refused(_why_the_records_refused(agent, kind, why)) from why
    if moved == 0:
        raise records.NotThere(f"{agent} has no {kind} channel")


def allowing(agent: str, kind: str, add: Sequence[str] = (),
             remove: Sequence[str] = ()) -> List[str]:
    """Change who may reach this agent here. Hands back the list as it now stands.

    **Read, decided and written inside one transaction.** Handing the whole list to a caller to
    rewrite is how two commands racing each other lose one of the two changes, and this is the list
    that decides who may reach the agent.

    An id already there is not added twice and an id that was never there is refused rather than
    passed over: *"remove 2207"* aimed at a list that never held `2207` is somebody typing the wrong
    id, and answering "done" leaves them believing they have taken away access they have not.

    **It may not reach zero.** The records refuse an empty list, and it is refused here too, in a
    sentence about what taking the last one away would mean rather than about a constraint.
    """
    with records.writing(directory.records(agent)) as conn:
        found = _rows(conn, agent, "SELECT allowed FROM channels WHERE kind = ?", (kind,)).fetchone()
        if found is None:
            raise records.NotThere(f"{agent} has no {kind} channel")
        standing = _read_list(found[0], f"{agent}'s {kind} channel")

        missing = [one for one in remove if one not in standing]
        if missing:
            raise Refused(f"{missing[0]} is not somebody who may reach {agent} on {kind}")
        wanted = [one for one in standing if one not in remove]
        wanted += [one for one in add if one not in wanted]
        if not wanted:
            raise Refused(
                f"that would leave nobody able to reach {agent} on {kind} — a channel with an empty "
                "list answers nobody, so take the channel away instead")
        conn.execute("UPDATE channels SET allowed = ? WHERE kind = ?",
                     (json.dumps(wanted), kind))
    return wanted


def telling(agent: str, kind: str, place: Optional[str] = None) -> None:
    """Make this the channel unprompted things go to, and no other. `place` is where they land.

    **Both writes in one transaction, the clearing first.** At most one channel may claim this, held
    by a partial unique index, so setting the new one before clearing the old is refused by the
    index — which is the good outcome. The bad one is the caller who clears, then fails to set, and
    leaves an agent that tells nobody anything.

    `place` is required by the records whenever a channel is the notified one, and is left as it
    stands when nothing is said: re-marking a channel that already knows where to write does not
    make somebody name the place again.
    """
    with records.writing(directory.records(agent)) as conn:
        found = _rows(conn, agent, "SELECT notify_place FROM channels WHERE kind = ?",
                      (kind,)).fetchone()
        if found is None:
            raise records.NotThere(f"{agent} has no {kind} channel")
        landing = place if place is not None else found[0]
        if not landing:
            raise Refused(
                f"nothing said where {agent} should write on {kind} when nobody has asked — a "
                "gateway coming up is answering no one, so it has no conversation to reply into")
        conn.execute("UPDATE channels SET notified = 0 WHERE notified = 1")
        conn.execute("UPDATE channels SET notified = 1, notify_place = ? WHERE kind = ?",
                     (landing, kind))


def forgotten(agent: str, kind: str) -> None:
    """Take a channel away. `records.NotThere` when there was none for that platform.

    **A removal that did not happen is a failure**, which is why this reads `rowcount` rather than
    treating a delete that matched nothing as the state that was asked for.

    What was said through it stays. `conversations.channel` is deliberately not a foreign key, so
    the history keeps saying where it came from after the connection is gone — see step `0003`.
    """
    with records.writing(directory.records(agent)) as conn:
        gone = conn.execute("DELETE FROM channels WHERE kind = ?", (kind,)).rowcount
    if gone == 0:
        raise records.NotThere(f"{agent} has no {kind} channel")


def who_may_reach(row: Dict[str, Any]) -> List[str]:
    """The ids a channel row allows, read back as a list.

    Here rather than at each call site because a row read from the database holds text, and every
    caller that parsed it itself would be a caller that could parse it differently.
    """
    return _read_list(row.get("allowed"), f"the {row.get('kind')} channel")


def admitting(row: Dict[str, Any]) -> Admitting:
    """What a channel's allow list admits, sorted into the two things an entry may name.

    Here rather than at each call site for the reason `who_may_reach` is: the column holds text, and
    every caller that decided for itself what one of those strings meant would be a caller that could
    decide differently — which for this column is two answers to *who may reach this agent*.

    **Raises rather than answering empty**, exactly as `who_may_reach` does. An `Admitting` with
    nothing in it admits nobody, so a list that merely could not be read must never look like one.
    """
    return admitted_by(who_may_reach(row))


def admitted_by(entries: Sequence[str]) -> Admitting:
    """The same reading, of a list already in hand — what `RUNDESK_ALLOW` is built from.

    **A prefix that is not one of the two closed words is not a prefix**, it is the start of an id.
    That is what keeps a list written before typed entries existed meaning exactly what it meant, and
    it is why the words are matched whole rather than split on the first colon and hoped about.

    **A typed entry naming nothing is dropped.** `sender:` with nothing after it is not an id, and
    the two directions are not equally safe: kept as the literal text it would sit in the list
    matching a sender nobody can be, and read as *any sender* it would open the channel to everybody.
    Dropped, it admits nobody, which is what an entry that names nobody should do. `channels add`
    refuses one before it is ever written.
    """
    senders: List[str] = []
    places: List[str] = []
    for entry in entries:
        kind, marked, named = str(entry).partition(AS)
        if marked and kind in TYPED:
            if named:
                (senders if kind == SENDER else places).append(named)
        elif entry:
            senders.append(str(entry))
    return Admitting(_once(senders), _once(places))


def _once(named: List[str]) -> Tuple[str, ...]:
    """The same ids, each kept the first time it is seen. One id said twice is one id."""
    kept: List[str] = []
    for one in named:
        if one not in kept:
            kept.append(one)
    return tuple(kept)


def _read_list(said: Any, whose: str) -> List[str]:
    """A JSON array of ids, or `Unreadable` — never a silently empty list.

    An empty list authorises nobody, so a column that could not be read must never *look* like one:
    that would turn a database somebody could still repair into a channel that quietly stopped
    answering the person who owns it.
    """
    try:
        held = json.loads(said)
    except (TypeError, ValueError) as why:
        raise records.Unreadable(f"{whose} does not say who may reach this agent: {why}") from why
    if not isinstance(held, list):
        raise records.Unreadable(f"{whose} does not say who may reach this agent")
    return [str(one) for one in held]


def _a_list(said: Any, called: str) -> None:
    """Refuse a column that has to be a JSON array before SQLite refuses it less helpfully.

    The `CHECK` behind this answers `OperationalError: malformed JSON`, which names neither the
    column nor the caller's mistake.
    """
    if said is None:
        return
    try:
        held = json.loads(said)
    except (TypeError, ValueError) as why:
        raise Refused(f"{called} has to be a list of ids, written as JSON ({why})") from why
    if not isinstance(held, list):
        raise Refused(f"{called} has to be a list of ids, written as JSON")
    if not held:
        raise Refused(f"an empty {called} authorises nobody, so a channel with one answers nobody")


def _only_settable(named: List[str]) -> None:
    """Refuse a column a caller may not state, before anything is written."""
    unknown = [key for key in named if key not in SETTABLE]
    if unknown:
        if unknown[0] == "notified":
            raise Refused("which channel is told is set with `telling`, so that no two claim it")
        raise Refused(f"{unknown[0]} is not something a channel is given")


def _rows(conn: sqlite3.Connection, agent: str, sql: str, values: tuple = ()) -> sqlite3.Cursor:
    """Ask the channels table, saying which agent it was when it cannot answer.

    Records holding no `channels` table are `Unreadable` rather than an empty listing, for the same
    reason `records.read` refuses a missing configuration row: an agent carried no further than
    `0002` has channels nobody has read, not no channels.
    """
    try:
        return conn.execute(sql, values)
    except sqlite3.DatabaseError as why:
        raise records.Unreadable(f"{agent} does not hold channels that can be read: {why}") from why


def _known(conn: sqlite3.Connection, agent: str, named: List[str]) -> None:
    """Refuse before writing anything if one of these is not a column the table has.

    Asked of `PRAGMA table_info` through `records.columns_of` rather than against `SETTABLE` alone,
    because the two answer different questions: `SETTABLE` is what a caller is *allowed* to state,
    and this is what the records in front of us actually hold. It is also what makes the statements
    above safe to build by hand — the only names that reach them are ones SQLite has just supplied.
    """
    columns = records.columns_of(conn, directory.records(agent), TABLE)
    unknown = [key for key in named if key not in columns]
    if unknown:
        raise Refused(f"{unknown[0]} is not something {agent}'s channels hold")


def _why_the_records_refused(agent: str, kind: str, why: sqlite3.IntegrityError) -> str:
    """What the database just refused, said as the thing somebody did.

    SQLite names the constraint and not the mistake. Every one of these is something a person typed,
    so every one gets the sentence for what they typed.
    """
    said = str(why).lower()
    if "channels.kind" in said or ("unique" in said and "notified" not in said):
        return (f"{agent} is already connected to {kind} — a channel is a connection rather than a "
                f"place, so there is one of them and it reaches every room the bot is in")
    if "notified" in said:
        return f"another channel is already the one {agent} writes to when nobody has asked"
    if "notify_place" in said:
        return f"nothing said where {agent} should write on {kind} when nobody has asked"
    return f"{agent}'s records refused that channel ({why})"


def _now(when: Optional[datetime] = None) -> str:
    """A moment this product keeps for a machine to compare, in the one shape it keeps them in."""
    return config.moment_of(when)
