"""A schedule may state a single moment rather than a repeating time.

`cron` was `NOT NULL`, which is the whole of why every schedule recurs: cron has no year,
so `0 9 28 7 *` says every 28 July for ever and there is no way to say one. This makes
`cron` optional, puts `at` beside it, and has the records themselves insist on exactly one
of the two — the idiom `001.py` already uses for a schedule that runs a program or asks a
turn and never both.

**Why the table is rebuilt rather than altered.** SQLite can neither drop a `NOT NULL` nor
add a `CHECK` through `ALTER TABLE`, so the only way to say either is a new table. That is
ordinary, and one thing about it here is not: `run.schedule_id` references this table
`ON DELETE SET NULL`, and with foreign keys on — which is how the runner opens every step —
`DROP TABLE` performs an implicit `DELETE FROM` that fires exactly that action. The rebuild
would then look perfect while every run had quietly stopped saying which schedule started
it, which is the one thing `001.py` added that clause to preserve. So the links are read
out first, put back after, and checked.

The step cannot turn foreign keys off to avoid it: `PRAGMA foreign_keys` is a no-op inside a
transaction, and the runner hands this a live `BEGIN IMMEDIATE`.

Every schedule that exists on any machine today is a cron schedule and stays exactly one:
`at` arrives NULL for all of them, and nothing else about a row changes.
"""

#: The shape a schedule takes from here. Every column and comment carried across from
#: `001.py` unchanged except the two lines this step is about, so the two files can be read
#: side by side and the difference is the whole difference.
SCHEDULE = """
CREATE TABLE schedule_rebuilt (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,
    enabled           INTEGER NOT NULL DEFAULT 1,
    -- When it runs, over and over. NULL where this schedule states a single moment
    -- instead — it was NOT NULL, and that was the whole of why every schedule recurred.
    cron              TEXT,
    -- The single moment it runs, once, after which it can never be due again. The
    -- machine's own local clock, to the minute, spelled the way `last_auto_run_at`
    -- beside it already is — a schedule is stated in local time and compared against
    -- local time, and a moment kept in a second clock face one column away would be
    -- wrong by an hour for part of the year and invisible for the rest of it.
    at                TEXT,
    command           TEXT,
    prompt            TEXT,
    -- Which provider answers work this schedule starts, and what it is told before it reads
    -- the prompt.
    provider          TEXT,
    model             TEXT,
    instructions      TEXT,
    -- Where what this came to is said, by the name the owner gave that surface. Nothing at
    -- three in the morning has a person at the other end, so the outcome has to reach where
    -- its owner already looks — and which place that is, is the owner's to choose rather than
    -- rundesk's to guess. A schedule naming none is not silence: the account and `schedules`
    -- say it either way, and referencing the channel is what stops one outliving the other.
    channel           TEXT REFERENCES channel(name),
    -- *Which place on it*, in the surface's own word for one — `#operations`, a room id,
    -- whatever that platform calls them. **Never parsed here**, the same rule
    -- `conversation.space` already holds to: the core does not know this platform has rooms,
    -- so it carries the word and the adapter resolves it. A schedule naming a channel but no
    -- place is not wrong; it follows the conversation, which is what a channel reaching one
    -- place already means.
    place             TEXT,
    -- That the clock started this, and what it came to. Together they are also what says a
    -- single moment has been used: one whose moment has passed with nothing written here
    -- never ran at all, which is a different fact from one that ran and failed.
    last_auto_run_at  TEXT,
    last_outcome      TEXT,
    created_at        TEXT NOT NULL,
    -- Exactly one of the two, said by the records rather than trusted to whoever writes
    -- them, the same way the pair below is.
    CHECK ((cron IS NULL) <> (at IS NULL)),
    CHECK ((command IS NULL) <> (prompt IS NULL))
) STRICT;
"""

#: What is carried across, in one order written once so the SELECT cannot drift from the
#: INSERT. `at` is not here: every existing schedule is a cron schedule and takes NULL.
CARRIED = (
    "id", "name", "enabled", "cron", "command", "prompt", "provider", "model",
    "instructions", "channel", "place", "last_auto_run_at", "last_outcome", "created_at",
)


def up(conn, home):
    """Rebuild `schedule`, inside the transaction the runner opened.

    Never commits and never deletes a file, so nothing is handed back. Statements go one at
    a time rather than through `executescript`, which issues an implicit COMMIT before it
    runs and would silently end the `BEGIN IMMEDIATE` above this.
    """
    # Read the links out before anything can take them. `DROP TABLE` below fires
    # `ON DELETE SET NULL` on every one of these, and a run that no longer says which
    # schedule started it is the one loss this whole step has to not cause.
    linked = conn.execute(
        "SELECT n, schedule_id FROM run WHERE schedule_id IS NOT NULL"
    ).fetchall()
    # And the id counter, which the drop takes with the table. Left to restart from the
    # highest id copied across, a schedule removed after the busiest one would let the next
    # schedule added take an id that has already been somebody's.
    counter = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'schedule'"
    ).fetchone()

    conn.execute(SCHEDULE.strip())
    columns = ", ".join(CARRIED)
    conn.execute(f"INSERT INTO schedule_rebuilt ({columns}) SELECT {columns} FROM schedule")
    conn.execute("DROP TABLE schedule")
    # After this the referencing clause in `run` names the rebuilt table, which is what
    # makes putting the links back below a write the database will accept.
    conn.execute("ALTER TABLE schedule_rebuilt RENAME TO schedule")

    for row in linked:
        conn.execute("UPDATE run SET schedule_id = ? WHERE n = ?", (row[1], row[0]))
    if counter is not None:
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'schedule'")
        conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('schedule', ?)",
                     (counter[0],))

    # Read and raised on by hand: this answers with rows rather than by failing, so a
    # rebuild that went wrong would otherwise commit. Raising here is what puts the records
    # back exactly as they were — the runner rolls the whole step back around this.
    broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    if broken:
        raise RuntimeError(
            "rebuilding the schedule table left references that do not resolve: "
            f"{broken!r}"
        )
    return []
