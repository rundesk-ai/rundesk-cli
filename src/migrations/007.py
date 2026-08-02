"""Somewhere to count the times carrying a role run threw, so a fault ends rather than repeats.

Carrying one role run can fail before the work does: a provider that died, a network that
went, a target directory somebody moved. Whether that is a blip worth trying again or a
fault that will happen every time is not a question one attempt can answer — and the count
that would answer it lived nowhere, so it died with the gateway holding it, which is
exactly the moment it is needed.

`carry_attempts` is how many times carrying *this* run has thrown. `carry_failed_at` is
when the latest of those was, so the next attempt waits rather than following it a beat
later. Both belong to the run rather than to a process, because the gateway that tries
again is usually not the gateway that failed.

**Rows written before this step read as never having failed**, which is what they are: a
default of zero and no failure time is the truth about every run admitted until now, so
nothing has to be back-filled and a copy of rundesk from before this step reads every row
it wrote exactly as it did.
"""


def up(conn, home):
    # Two columns rather than one. The count alone says "try again" without saying "not
    # yet", so a gateway looking every five seconds would spend the whole ceiling inside
    # fifteen seconds — three attempts is a ceiling on cost only if something spreads them
    # out.
    conn.execute(
        "ALTER TABLE role_run ADD COLUMN carry_attempts INTEGER NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE role_run ADD COLUMN carry_failed_at TEXT")
    # Which turns carried a role run is now asked on a timer as well as for a handoff:
    # "has this run produced anything in six hours" reaches every record of every turn
    # carrying it, and without this it reaches them by walking every run the agent has
    # ever had.
    conn.execute("CREATE INDEX run_by_role ON run(role_run)")
    return []
