"""What a gateway never got to finish, and what a successor makes of it.

The interruption ledger: a gateway that dies leaves work nobody is coming back for, and this
is the only record that outlives the process. A successor claiming the name reads it, settles
what it can and says what was missed.

Kept beside the log rather than inside the run state it describes, for the reason the log is:
run state is cleared when a gateway goes, and this has to survive exactly that.

The `Gateway` methods that *act* on this — reconciling, settling, saying what was missed —
stay in the class. They are the second half of `claim()` and they write the clock's own
state; freeing them is a redesign rather than a move, and it is the neighbourhood three
recent defects came from.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rundesk import schedule
from rundesk.durable import Unreadable, changing, read_json
from rundesk.gateway_log import DEFAULT_NAME, NotAName, checked, logs_home


#: How many interruptions are kept for one gateway (R-GW-23). Bounded for the same reason
#: the log is: a machine left running for months must not grow a file nobody prunes. The
#: oldest go, because an interruption nobody has looked at in fifty incidents is history.
KEPT_INTERRUPTIONS = 50

def interrupted_path(name: str, logs: Path | None = None) -> Path:
    """Where work that never got to finish is written down (R-GW-23).

    With the log, which is the tier that outlives a gateway: stopping one clears what it is
    *doing* (R-GW-12), and this is the account of what it never finished — worth least at
    the moment it is written and most much later.

    It stood beside the schedules until those became rows. It is a file rather than a row
    because it describes work that has no run of its own — a channel held open, a program a
    predecessor left behind — and because the gateway that answers for it may be one whose
    agent no longer exists.
    """
    return (logs or logs_home()) / f"{checked(name)}.interrupted.json"


def what_was_interrupted(name: str = DEFAULT_NAME, logs: Path | None = None) -> dict:
    """What this gateway never got to finish, and why (R-GW-23).

    Read from a file rather than asked of anything, because whatever wants to know is a
    different process — and usually a later one, since the gateway that could have
    answered is the one that went.
    """
    said = read_json(interrupted_path(name, logs), {})
    return {work: how for work, how in said.items() if isinstance(how, dict)} \
        if isinstance(said, dict) else {}


def remembered(logs: Path | None = None) -> list[str]:
    """Every gateway name that left an account of work it never finished (R-GW-38).

    A gateway is discoverable from its run record, from an agent, or from a job the
    machine holds — and a name whose record has been cleared, whose agent has been taken
    away and whose job was never written survives only here. That is precisely the name an
    owner needs after a crash, and the one every listing left out: they had to already know
    it before they could ask about it.

    Read from where the logs are, because that is where the account now stands. What it was
    *scheduled* to do no longer survives a name losing its agent at all — schedules are rows
    an agent keeps, so an agent that is gone takes them with it.
    """
    where = logs or logs_home()
    if not where.is_dir():
        return []
    found = set()
    for beside in where.glob("*.interrupted.json"):
        plain = beside.name[: -len(".interrupted.json")]
        try:
            found.add(checked(plain))
        except NotAName:
            continue  # something else's file, in a directory that is not only ours
    return sorted(found)


def resolve_interruption(name: str, logs: Path | None, work: str) -> None:
    """Work that is running again is no longer work that never finished (R-GW-40).

    Entries were keyed by work name and never cleared, so a schedule interrupted once in
    March was still listed in July beside one interrupted a minute ago, with nothing
    telling outstanding from long since fine — which is a store nobody can act on. Work
    starting again is the one resolution that is actually knowable here: if it is
    interrupted a second time, that is a new entry rather than an unresolved old one.
    """
    try:
        with changing(interrupted_path(name, logs), {}, "interruptions", durable=True) as said:
            said.pop(work, None)
    except (OSError, Unreadable):
        pass  # tidying history is never worth refusing to start work over


def note_interrupted(name: str, logs: Path | None, work: str, why: str,
                      pgid: int | None = None, ended: bool = False) -> None:
    """Write down that a piece of work was interrupted (R-GW-23).

    Read, added to and written back under one hold (R-GW-27). The thing that writes here is
    not always the gateway whose file it is: a gateway sweeping what an abandoned name left
    behind writes into *that* name's file (R-GW-21), so two writers each working from their
    own snapshot is the ordinary case on a machine bringing several gateways up at once —
    and half of everything recorded was lost every time it happened. The hold is taken on
    the file being changed rather than on the gateway doing the changing, which is what
    makes it cover a sweeper racing the file's own owner as well as two sweepers racing.

    `ended` is the distinction worth keeping. Work rundesk ended and work it could not
    show was its to end are both interrupted, and only one of them is definitely gone.
    """
    from rundesk import schedule

    try:
        with changing(interrupted_path(name, logs), {}, "interruptions", durable=True) as said:
            said[work] = {
                "at": datetime.now().strftime(schedule.A_MINUTE), "why": why,
                "pgid": pgid, "ended": ended,
            }
            if len(said) > KEPT_INTERRUPTIONS:
                # An entry a hand edit left behind is not a record and has no time to sort
                # on. `what_was_interrupted` already passes over those, and the cap must
                # not be the one thing here that falls over on one.
                oldest = sorted(said, key=lambda one: said[one].get("at", "")
                                if isinstance(said[one], dict) else "")
                for one in oldest[: len(said) - KEPT_INTERRUPTIONS]:
                    said.pop(one, None)
    except (OSError, Unreadable):
        pass  # a gateway that cannot write this down still has to get on with starting
