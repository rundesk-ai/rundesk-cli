"""Somewhere to keep what a profile run is, and the one callback that wakes its parent.

A named agent may hand one bounded task to an isolated profile run — a fresh specialist
execution acting on that agent's behalf, with the agent's identity, memory, history and
operational rules deliberately absent from it. Two facts about such a run have to outlive
the gateway that started it, and neither had anywhere to go:

**What the run was admitted with.** Which profile, which exact revision of it, which
skills, whose run asked, which conversation the answer is owed to, and how long the
execution context stays resumable. All of it is settled when the run is admitted and none
of it changes after, exactly as what an ordinary run resolved does not change after.

Beside it, a digest of every part of the locked bundle — the rules, the manifest, and each
skill package on its own. Kept per part rather than only as the profile's aggregate
revision, because the bundle is writable by the very execution it governs: a worker that
rewrote its own rules and was resumed would run under rules it wrote for itself while the
record still asserted the original revision. "These are the bytes that ran" has to be
checkable against what is on disk a fortnight later, one part at a time.

**That its parent still has to be told.** A profile run finishes while nobody is waiting
on it: the turn that admitted it ended with an acknowledgment, and the named agent is
woken afterwards to review the handoff. A gateway that died between the two would
otherwise lose the result silently — the work is done, the record says so, and nobody is
ever told. So the wake-up is a durable row with a delivery mark on it, claimed and marked
delivered separately, which is what makes it survivable at every crash point and
deliverable exactly once.

**Rows written before this step are left alone and stay NULL.** An ordinary run is not
part of a profile execution and never was; `profile_run` is absent on it rather than
filled with anything, because a run that belongs to no profile and one whose profile was
forgotten are different facts. A copy of rundesk from before this step reads every row it
wrote exactly as it did.
"""


def up(conn, home):
    # **The admission, not the execution.** One profile run may be carried by more than
    # one provider turn — an interrupted one is resumed within its retention window — so
    # what was admitted is its own row and each turn points back at it. The alternative,
    # hanging the profile's identity off whichever run happened to start first, loses the
    # link the moment that run is not the one that finished.
    conn.execute(
        """
        CREATE TABLE profile_run (
            n                   INTEGER PRIMARY KEY AUTOINCREMENT,
            id                  TEXT NOT NULL UNIQUE,
            profile             TEXT NOT NULL,
            revision            TEXT NOT NULL,
            skills              TEXT NOT NULL DEFAULT '[]',
            locked              TEXT NOT NULL DEFAULT '{}',
            label               TEXT NOT NULL,
            posture             TEXT NOT NULL,
            parent_run          TEXT NOT NULL,
            parent_conversation TEXT NOT NULL REFERENCES conversation(id),
            target              TEXT,
            admitted_at         TEXT NOT NULL,
            latest_at           TEXT NOT NULL,
            retained_until      TEXT NOT NULL,
            state               TEXT NOT NULL,
            outcome             TEXT,
            report              TEXT,
            reviewed_at         TEXT
        ) STRICT
        """
    )
    conn.execute("CREATE INDEX profile_run_by_parent ON profile_run(parent_run, n)")
    conn.execute("CREATE INDEX profile_run_by_state ON profile_run(state, n)")
    # **One row per profile run, and the primary key is what says so.** A terminal outcome
    # may be reached more than once by a retrying gateway; a second insert is refused by
    # the key rather than by a check somebody has to remember to write, so the parent is
    # woken exactly once however many times the outcome is offered.
    #
    # `review_run` is which named-agent turn was woken to read the handoff. Kept because
    # it is the durable answer to "was this turn created by a completion callback" — a
    # review may discuss or correct the run it is reviewing, and may not fan out into
    # another profile, and a question that important is not answered from an environment
    # variable the turn itself could unset.
    conn.execute(
        """
        CREATE TABLE profile_callback (
            profile_run   TEXT PRIMARY KEY REFERENCES profile_run(id) ON DELETE CASCADE,
            conversation  TEXT NOT NULL,
            queued_at     TEXT NOT NULL,
            attempts      INTEGER NOT NULL DEFAULT 0,
            claimed_at    TEXT,
            delivered_at  TEXT,
            review_run    TEXT
        ) STRICT
        """
    )
    # Which profile execution this turn was carrying, where it was carrying one. Nullable
    # with no default: every run written before this step belongs to no profile, and so
    # does every ordinary turn written after it.
    conn.execute("ALTER TABLE run ADD COLUMN profile_run TEXT")
    return []
