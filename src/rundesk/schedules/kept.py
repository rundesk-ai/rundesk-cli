"""The schedules one agent keeps, and the only way in to them.

Everything here goes through `agents.records` — its connections, its transactions, its busy timeout
and its four answers. There is no second way into an agent's database, and this module exists so
that there does not become one: a schedules table read by two different sets of open-and-retry rules
is a table where a gateway and a command disagree about what "locked" means.

## The four answers it inherits, and the fifth it adds

`agents.records` already tells apart records that were read, records that are **not there**, records
that are **there and cannot be understood**, and records **carried further than this release ships**.
Every one of those reaches a caller unchanged, because collapsing any pair loses state — a caller
told "not there" makes a new one, and an agent's whole memory is what that overwrites.

The fifth is `NotThere` for **one schedule** rather than for the records: a change aimed at a
schedule that is not there alters nothing and says so. It is `records.NotThere` reused rather than a
second class of its own, because every caller has the same thing to do about both and a second name
would only be a second thing to catch.

## What is written for a machine and what is written for a person

`created_at` and `last_run_at` are records of something that happened: they are compared, they are
sorted, and they may be read on another machine after a restore. UTC, to the second, in
`core.config.MOMENT`, like every other record this product keeps.

`cron`, `run_at` and `expire_at` are the opposite — a statement about the future, on this machine's
own clock, kept exactly as the owner typed them. `due` says why at length.

`last_fired_for` is the odd one out and is local too, because it is compared against a minute the
cron fields produced and those are local. It is written **before** the work starts, and `claimed` is
the only thing that writes it.

May depend on `agents`, `core` and `utils`.
"""

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from rundesk.agents import directory, records
from rundesk.core import config
from rundesk.utils import files

#: The table, named once.
TABLE = "schedules"

#: What a firing came to, and the only three words this column may hold. `done` is the work ran and
#: said it was happy; `failed` is it ran and said it was not, or never started at all; and `stopped`
#: is that nobody can say, because whatever was watching went away first. The third is not a kind of
#: failure — a gateway killed mid-run leaves work that may well have finished, and calling that a
#: failure is a claim nothing here can back.
#:
#: **`done` rather than `completed`, and the word is not this module's to pick.** `seen`, `working`,
#: `done`, `stopped` and `failed` are the states an adapter renders, written down in `docs/adapters.md`
#: with the note that they are *not* `taken`, `running`, `finished` — a published vocabulary somebody
#: else's program is built against. `turns.turn_status` already speaks it. A firing's outcome never
#: leaves this machine, so nothing forced the two apart except that they were written months apart,
#: and one product saying `done` in one place and `completed` in another is one word too many.
DONE = "done"
FAILED = "failed"
STOPPED = "stopped"
OUTCOMES = (DONE, FAILED, STOPPED)

#: What a caller may set through `added` and `changed`, and nothing else. Narrower than the table on
#: purpose: `id` is the row's identity, `name` is how a schedule is found rather than something to
#: overwrite in place, and `created_at`, `last_outcome`, `last_run_at` and `last_fired_for` are the
#: records' own account of what has happened — a caller that could set those could rewrite history
#: and then read it back as fact.
SETTABLE = ("enabled", "cron", "run_at", "expire_at", "provider_name", "model_name",
            "prompt", "command", "channel", "channel_place_id")


class Refused(Exception):
    """Something that may not be done to a schedule, named with why.

    A sentence rather than a code, for the reason `directory.Refused` gives: every caller has to
    tell somebody what to type instead, and a caller left to invent that wording invents a different
    one.
    """


def name_trouble(said: str) -> str:
    """Why `said` may not be a schedule's name, or `""` when it may.

    `utils.files.name_trouble` is the whole of the general answer and is reused rather than
    reimplemented. It applies here for a concrete reason rather than by analogy: a schedule's name
    becomes `<name>.lock`, `<name>.json` and `<name>.out` inside the agent's `schedules/` directory,
    so a name a filesystem cannot hold is a schedule that can be added and can never be fired.

    Refused where it is typed, which is the only moment somebody can do anything about it.
    """
    return files.name_trouble(said)


def all(agent: str) -> List[Dict[str, Any]]:  # noqa: A001 — see the docstring
    """Every schedule this agent keeps, in name order.

    Named `all` because that is the question — every other name for it (`listed`, `known`, `every`)
    reads as a different one at the call site. It shadows the builtin only inside this module, which
    uses none of it, and it is always reached as `kept.all(...)`.

    No schedules is an answer rather than a failure: an agent nobody has scheduled anything for says
    so. Records that cannot be read are left to raise, because answering "none" would tell somebody
    their schedules are gone at the moment they are merely unreadable — and the next thing they do
    is add them again over the top.
    """
    with records.reading(directory.records(agent)) as conn:
        return [dict(row) for row in _rows(conn, agent, "SELECT * FROM schedules ORDER BY name")]


def one(agent: str, name: str) -> Dict[str, Any]:
    """One schedule, whole. `records.NotThere` when this agent has no schedule of that name."""
    with records.reading(directory.records(agent)) as conn:
        found = _rows(conn, agent, "SELECT * FROM schedules WHERE name = ?", (name,)).fetchone()
    if found is None:
        raise records.NotThere(f"{agent} has no schedule called {name}")
    return dict(found)


def added(agent: str, name: str, values: Dict[str, Any], when: Optional[datetime] = None) -> None:
    """Write down a new schedule. `Refused` when the name is taken or is not a name.

    **A name already there is refused rather than replaced.** Two people can reach for one name and
    the second must not silently take the first's schedule away — and the refusal is the `UNIQUE`
    constraint doing it inside the transaction, not a check-then-insert with a gap in the middle.

    Everything the records themselves refuse — when said two ways, a kind said two ways, an outcome
    that is not one of three — is refused by the `CHECK`s rather than re-asked here. What is asked
    here is only what the database cannot see: whether the name can be a file.
    """
    trouble = name_trouble(name)
    if trouble:
        raise Refused(f"{name} cannot be a schedule's name: {trouble}")
    unknown = [key for key in sorted(values) if key not in SETTABLE]
    if unknown:
        raise Refused(f"{unknown[0]} is not something a schedule is given")

    stated = dict(values, name=name, created_at=_now(when))
    named = sorted(stated)
    with records.writing(directory.records(agent)) as conn:
        _known(conn, agent, named)
        try:
            conn.execute(
                "INSERT INTO schedules (" + ", ".join(named) + ") "
                "VALUES (" + ", ".join("?" for _ in named) + ")",
                [stated[key] for key in named])
        except sqlite3.IntegrityError as why:
            raise Refused(_why_the_records_refused(agent, name, why)) from why


def changed(agent: str, name: str, values: Dict[str, Any]) -> None:
    """Change a schedule in place, keeping every record of what it has already done.

    **All of it or none of it.** Every name is checked against the live table before anything is
    written, the same rule and the same code `records.stated` uses: naming two columns and getting
    one wrong must change neither, because half of what was meant is not a smaller change — it is a
    different one nobody typed.

    **`records.NotThere` when nothing was changed**, asked of `rowcount` rather than of a read
    beforehand. A change aimed at a schedule that is not there alters nothing and says so, and
    asking first would leave a gap in which somebody removes it between the two statements.

    Nothing named is refused by the caller and not here: this is the layer that writes, and *"you
    named nothing"* is a sentence about a command line.
    """
    if not values:
        raise Refused(f"nothing was named to change about {name}")
    unknown = [key for key in sorted(values) if key not in SETTABLE]
    if unknown:
        raise Refused(f"{unknown[0]} is not something a schedule is given")

    named = sorted(values)
    with records.writing(directory.records(agent)) as conn:
        _known(conn, agent, named)
        try:
            moved = conn.execute(
                "UPDATE schedules SET " + ", ".join(f"{key} = ?" for key in named) +
                " WHERE name = ?", [values[key] for key in named] + [name]).rowcount
        except sqlite3.IntegrityError as why:
            raise Refused(_why_the_records_refused(agent, name, why)) from why
    if moved == 0:
        raise records.NotThere(f"{agent} has no schedule called {name}")


def forgotten(agent: str, name: str) -> None:
    """Take a schedule away. `records.NotThere` when there was none of that name.

    **A removal that did not happen is a failure**, which is why this reads `rowcount` rather than
    treating a delete that matched nothing as the state that was asked for. What the schedule has
    already done goes with it — there is no history table for a firing to outlive its schedule in,
    and what a firing wrote is in the agent's log, which this does not touch.
    """
    with records.writing(directory.records(agent)) as conn:
        gone = conn.execute("DELETE FROM schedules WHERE name = ?", (name,)).rowcount
    if gone == 0:
        raise records.NotThere(f"{agent} has no schedule called {name}")


def claimed(agent: str, name: str, minute: str) -> None:
    """Write down that the clock has taken this schedule for this minute. **Before the work starts.**

    This is the whole of the guarantee that a schedule runs once for the minute it is due. Held only
    in memory — which is where the build this replaces held it — the fact that a minute had already
    fired died with the gateway: a crash between starting and finishing, and a supervisor that
    brings the gateway back within seconds, ran the same schedule twice for the one minute it was
    due.

    **And the work starts only if this landed.** A caller that started anyway would leave work which
    has visibly happened with nothing durable saying it did, so the same side-effecting run repeats
    on the way back up — which is the very thing writing it first is for. This raises rather than
    answering, so a caller cannot reach the spawn by ignoring a return value.
    """
    with records.writing(directory.records(agent)) as conn:
        moved = conn.execute("UPDATE schedules SET last_fired_for = ? WHERE name = ?",
                             (minute, name)).rowcount
    if moved == 0:
        raise records.NotThere(f"{agent} has no schedule called {name}")


def became(agent: str, name: str, outcome: str, when: Optional[datetime] = None) -> None:
    """Write down what a firing came to, and when it was over.

    Refused for a word that is not one of the three, here rather than only at the `CHECK`: the
    constraint would raise `IntegrityError` naming a constraint, and the caller of this is a gateway
    writing into a log somebody reads at two in the morning.

    A schedule that has been taken away while its firing was running is not an error — the removal
    is what somebody asked for and the child is being stopped along with it — so a row that is no
    longer there is passed over rather than raised about.
    """
    if outcome not in OUTCOMES:
        raise Refused(f"{outcome} is not what a firing comes to — it is one of {', '.join(OUTCOMES)}")
    with records.writing(directory.records(agent)) as conn:
        conn.execute("UPDATE schedules SET last_outcome = ?, last_run_at = ? WHERE name = ?",
                     (outcome, _now(when), name))


def _rows(conn: sqlite3.Connection, agent: str, sql: str, values: tuple = ()) -> sqlite3.Cursor:
    """Ask the schedules table, saying which agent it was when it cannot answer.

    Records that are there and hold no `schedules` table are `Unreadable` rather than an empty
    listing, for the same reason `records.read` refuses a missing configuration row: an agent
    carried no further than `0001` has schedules nobody has read, not no schedules, and a caller
    told "none" would go on to write over whatever is really in there.
    """
    try:
        return conn.execute(sql, values)
    except sqlite3.DatabaseError as why:
        raise records.Unreadable(f"{agent} does not hold schedules that can be read: {why}") from why


def _known(conn: sqlite3.Connection, agent: str, named: List[str]) -> None:
    """Refuse before writing anything if one of these is not a column the table has.

    Asked of `PRAGMA table_info` through `records.columns_of` rather than against `SETTABLE` alone,
    because the two answer different questions: `SETTABLE` is what a caller is *allowed* to state,
    and this is what the records in front of us actually hold. An agent carried only as far as
    `0001` passes the first and fails this, which is the honest answer.

    It is also what makes the statements above safe to build by hand: the only column names that
    reach them are ones SQLite has just said the table has.
    """
    columns = records.columns_of(conn, directory.records(agent), TABLE)
    unknown = [key for key in named if key not in columns]
    if unknown:
        raise Refused(f"{unknown[0]} is not something {agent}'s schedules hold")


def _why_the_records_refused(agent: str, name: str, why: sqlite3.IntegrityError) -> str:
    """What the database just refused, said as the thing somebody did.

    SQLite names the constraint and not the mistake — `CHECK constraint failed: schedules` tells
    nobody which of the two `CHECK`s it was, and `UNIQUE constraint failed: schedules.name` reads
    like an internal detail of a table the person has never seen. Every one of these is something a
    person typed, so every one of them gets the sentence for what they typed.
    """
    said = str(why).lower()
    if "unique" in said:
        return (f"{agent} already has a schedule called {name} — change that one, or take it away "
                "first")
    return (f"a schedule says when it runs over and over or the one moment it runs, and starts a "
            f"program or asks an agent — never both of a pair and never neither ({why})")


def _now(when: Optional[datetime] = None) -> str:
    """A moment this product keeps for a machine to compare, in the one shape it keeps them in.

    UTC through `core.config.MOMENT`, the same constant the install's own records and an agent's
    `migrations` rows use — the same constant rather than the same literal typed again, which is
    what `agents.migration._now` says about its own.
    """
    return config.moment_of(when)
