"""Somewhere for a role run to keep the brain it was admitted to run on.

A role run used to be carried on whatever brain its parent turn happened to resolve, read
again every time something picked the run up. That answer lived nowhere, so it could not
be asked for afterwards — and it could change underneath a run: an agent reconfigured, or
a role edited, between admission and the first carry gave the work a different brain than
the one it was admitted with, and nothing anywhere recorded that it had.

`provider` is the brain this run was admitted to run on, resolved once from the flag, the
role and the parent turn in that order. `model` is the model on it, resolved at the same
moment and by the same rule. Both are settled when the run is admitted and neither changes
after — the same as which role, which revision and which skills, and for the same reason:
a run resumed on day fourteen resumes on the brain it started on, because its provider
session is that brain's and there is no other one to carry it.

**Rows written before this step stay NULL, and NULL means what it always meant**: carry
this on whatever the parent turn resolved. A run admitted by the release before this one
is still in its retention window when this step runs, and it must go on being carried
exactly as it was rather than being back-filled with a brain nobody resolved for it. A
copy of rundesk from before this step reads every row it wrote exactly as it did.
"""


def up(conn, home):
    # Two columns rather than one settled string. What a turn is told the brain is and
    # what it is told the model is are two arguments at the seam that runs one, and a
    # single column holding both would be a place to parse them apart again.
    conn.execute("ALTER TABLE role_run ADD COLUMN provider TEXT")
    conn.execute("ALTER TABLE role_run ADD COLUMN model TEXT")
    return []
