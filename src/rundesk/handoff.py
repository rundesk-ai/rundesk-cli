"""What is the same about handing work off, whichever kind of work it is.

Two things in this product hand a bounded task to somebody else and hear back about it in a
later turn: a **role run**, where the agent works in a mode with its identity withheld, and a
**delegation**, where another named agent answers as itself. They are different features and
stay in different modules — but four decisions are not about which of the two it is, and were
written twice:

- how long to leave a failed attempt alone before trying it again, and whether that time has
  passed;
- how often work still in flight says so where somebody asked for it;
- what a task may be called where other people are reading.

None of them can read anything about a role or about an agent, which is what makes them
belong here rather than in either. A list written twice is a list that disagrees with itself,
and these had already drifted by a word or two apiece before they were brought together.

Imports `store` only for reading a written moment back, which is the same dependency both
callers already had. Knows nothing of gateways, agents, roles or turns.
"""

from __future__ import annotations

import time

from rundesk import store

#: How long after a throw the same work is left alone. Doubled per attempt, so three
#: attempts are spread over minutes rather than over the fifteen seconds a five-second look
#: would otherwise take — a ceiling on attempts is only a ceiling on cost if something puts
#: time between them.
CARRY_BACKOFF_SECONDS = 60.0

#: How often work still in flight says so where it was asked for. Twenty minutes: long
#: enough that an hour's job is three lines rather than forty, short enough that somebody who
#: came back to the room can tell work that is going from work that is gone. Counted from
#: admission, which is what both listings already report as `elapsed`, so a line in a room and
#: a listing in a terminal cannot disagree about how long it has been.
CHECK_IN_SECONDS = 1200.0

#: How long a label may be where other people read it, and which characters may be in one.
#: Bounded because it goes in a thread title and a listing line; narrowed because everything
#: outside this set is either markup somebody else's client will act on or a path separator.
LABEL_CHARS = 60
LABEL_KEEPS = " -_.,'()"


def safe_label(said: str | None, fallback: str) -> str:
    """A short task label safe to show where other people are reading (R-ROL-17, R-DEL-15).

    Never a person's words verbatim and never markup: this is written into a thread title and
    into a listing, and a label carrying a private directory has published one.

    **A known limit, unchanged by being moved here.** This removes a path's separators rather
    than its components, so `/Users/somebody/secret/exporter` comes back as one long word with
    every component still readable — the same trap `_plain_name` sets in the Discord adapter.
    What actually drops components is the adapter's own `_helper_name`. Anything relying on a
    path *disappearing* here is relying on something this has never done.
    """
    text = " ".join(str(said or "").split())
    kept = "".join(ch for ch in text if ch.isalnum() or ch in LABEL_KEEPS)
    kept = " ".join(kept.split())[:LABEL_CHARS].strip()
    return kept or fallback


def check_in_due(elapsed: float, told: int = 0) -> int:
    """Which check-in this work has reached, or 0 when it owes none.

    A bucket number rather than a timestamp, so a gateway that restarted mid-run resumes the
    cadence from where the clock is rather than immediately saying something — and so two
    looks a second apart cannot produce two lines.
    """
    reached = int(max(0.0, float(elapsed)) // CHECK_IN_SECONDS)
    return reached if reached > max(0, int(told)) else 0


def backoff_seconds(attempts: int) -> float:
    """How long to leave this work alone after that many failed attempts at carrying it."""
    return CARRY_BACKOFF_SECONDS * (2 ** max(0, int(attempts) - 1))


def ready_to_carry(row: dict, now=None) -> bool:
    """Whether enough time has passed since this work's latest failed carry.

    Wall time on both sides, and deliberately: the gateway deciding this is usually not the
    gateway that failed, so there is no monotonic clock the two share — the same reason a
    retention window is a durable stamp rather than an elapsed count.

    Reads two fields and knows nothing else about the row it is handed, which is what lets one
    function answer for a role run's record in a store and a delegation's record in a file.
    """
    stumbled = store.moment(row.get("carry_failed_at"))
    if stumbled is None:
        return True
    waited = backoff_seconds(row.get("carry_attempts") or 0)
    return (now or time.time)() - stumbled.timestamp() >= waited
