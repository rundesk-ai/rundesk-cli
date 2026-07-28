"""The one database this plugin keeps, and the two rules that make sharing it safe.

**Every agent on this machine reaches this same file.** Rundesk installs a plugin once and
puts its command on every agent's PATH, so two agents answering two people at the same
moment are two processes against one SQLite file. That is the whole reason this module
exists rather than a bare `sqlite3.connect` at the top of `example.py`.

**Rule one: WAL, with a timeout.** The default journal makes a reader block a writer and a
writer block everything; WAL lets readers carry on while one writer works. The busy timeout
is what turns the remaining collision from an immediate `database is locked` — which reaches
an agent as a traceback and a person as a failure — into a short wait.

**Rule two: refuse data this code does not understand.** If the version on disk is ahead of
what this release knows, the plugin was downgraded and going on would read columns that mean
something else now. If it is behind, migrations have not run. Both say so and stop, which is
the same posture rundesk's own `migration.py` takes: "data a copy of rundesk does not
understand keeps it down and says why."
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

#: What version of the records this release of the plugin expects. Bumped in the same commit
#: that adds `migrations/00N.py`, and never separately — the two disagreeing is the one
#: failure this check cannot catch.
EXPECTS = 1

#: How long to wait for whichever agent got there first, in milliseconds. Long enough to
#: outlast an ordinary write, short enough that a stuck one is reported rather than hung on.
BUSY_MS = 5000

RECORDS = "state.db"


class Unusable(Exception):
    """The records are not in a shape this release can read, and why."""


def open(state: Path, expects: int = EXPECTS) -> sqlite3.Connection:
    """The shared records, ready to use — or a refusal that names what to do about it."""
    state.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(state / RECORDS), timeout=BUSY_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    found = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if found > expects:
        conn.close()
        raise Unusable(
            f"these records are version {found} and this build reads version {expects} — "
            "a newer version of this plugin wrote them; reinstall the newer one"
        )
    if found < expects:
        conn.close()
        raise Unusable(
            f"these records are version {found} and this build expects {expects} — "
            "run: rundesk plugins update example"
        )
    return conn
