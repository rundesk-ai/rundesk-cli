"""Somewhere for a role run to keep who asked it to stop.

`stop_asked_at` said that somebody had asked and never which somebody, so a run the agent
itself ended on purpose and a run a person ended from a terminal settled identically — and
the notice a surface showed for either of them could only say the run had not finished,
which reads as a fault when it was a decision.

`stop_asked_by` is who asked, in the one word this install can actually tell apart:
`agent` where the ask came from inside a turn, `terminal` where it came from somebody
typing. Nothing finer is claimed, because nothing finer is known — `RUNDESK_RUN` is in
every program a gateway starts and in nothing a person types, and that is the whole of the
discrimination there is.

**Rows written before this step stay NULL, and NULL means what it is: nobody wrote down
who asked.** A run stopped by the release before this one is still inside its retention
window when this step runs, and back-filling it with either word would be inventing a fact
about somebody's work. What is shown for one names nobody rather than guessing.
"""


def up(conn, home):
    conn.execute("ALTER TABLE role_run ADD COLUMN stop_asked_by TEXT")
    return []
