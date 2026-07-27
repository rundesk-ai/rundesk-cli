# migrations/ — one file per step forward

A step is **found here, not listed anywhere**. Its name is the version it brings data up to,
and nothing else — so there is one obvious way to add one, and no second place for the order to
be written down:

```
001.py   the shape an agent starts with
002.py
003.py
```

The number is the version and sorting the numbers is the whole of the ordering, so `010.py` runs
after `009.py` rather than after `001.py`. Two files claiming one number is refused rather than
resolved, because the order would otherwise be whatever the filesystem felt like.

**Why a sequence and not a date.** A version lives in the database header as a signed 32-bit
integer. `20260726` would fit; `20260726001`, or a date with a time on it, would not — and going
past the ceiling does not raise, it wraps to zero, which is the value that means "written partway
and cannot be read". Rails and Django can use timestamps because they keep a table of what has
run. A sequence needs no table, and the header is enough.

**`001.py` is the schema.** There is no second description of the tables kept beside the steps
to disagree with them: making an agent runs this path from nothing, so a step that has rotted is
found by whoever next adds an agent rather than by an owner mid-update, and a fresh install
cannot drift from an upgraded one.

## What a step looks like

```python
def up(conn, home):
    """`conn` is inside a transaction already. `home` is the agent's own directory."""
    conn.execute("ALTER TABLE run ADD COLUMN trigger_message_id INTEGER")
    return []                      # or paths that are safe to delete once the version commits
```

**A step has no kind, and the runner never asks what it is doing.** It is handed a connection
*and* a directory, so it may change tables, move files, rewrite a workspace, or do all of those
in one step — one thing has to run, and this is that thing. Nothing here classifies steps into
schema ones and file ones, because the moment it did, a step that needed to do both would have
nowhere to live and the order between two of them would stop being the order in this directory.

- **Do not open a connection and do not commit.** You are handed one, inside
  `BEGIN IMMEDIATE`, and the runner stamps the new version and commits — together with your
  work, so there is no moment where the change is present and the version is not. That is why
  there is no record of what has run: **the version is the record.**
- **Do not delete a file. Copy it, and hand back what is now spare**, as a list of paths. The
  runner removes them only once the version has committed, so a step that died halfway leaves
  both copies rather than neither, and running again is safe.
- **Do not import anything of rundesk's.** A step describes a shape that existed at one moment
  in the past. Calling today's code from it means it stops meaning that the day today's code
  changes, and a migration nobody can re-run is a migration nobody can trust.
- **Write it so running it twice would be harmless anyway.** It will not happen — the version
  gate sees to that — but a step that is safe on its own is one you can reason about alone.

## What there is not

No table recording what ran, no batches, and no way back. Going backwards is refusing to go
forwards: data a copy of rundesk does not understand keeps every agent down and says which
version it found, rather than being read by code that cannot know what it is missing.

The runner is [`../rundesk/migration.py`](../rundesk/migration.py); what it guarantees is
[`lifecycle-migration`](../../.knowledge/prd/lifecycle-migration.md).
