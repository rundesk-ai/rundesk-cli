# Moving onto the store — what Phase 5 does, and in what order

Phase 4 built [`store.py`](../../src/rundesk_cli/store.py) and
[`migration.py`](../../src/rundesk_cli/migration.py) and pointed nothing at them. This is the
page that says how to point everything at them without improvising.

**If the design turns out to be wrong, the drafts move first.** The whole point of the phase
before was that this one does not discover its design while building it. A surprise is a finding
against [`platform-store`](../prd-drafts/platform-store.md) or
[`lifecycle-migration`](../prd-drafts/lifecycle-migration.md), not a special case in the code.

## Order of work

1. **Write migration `002`.** One step, bringing today's layout to the new one. Nothing reads
   the store yet, so this can land and be re-run against copies of a real install until it is
   right.
2. **Move readers and writers over, one at a time**, each with its own regression check. The map
   below is the whole list — every place that touches durable state today.
3. **Delete the old layout and the code that defaulted to it**, including
   `agent.resolved()` returning `Where(None, None, None)` for a name that is not an agent, which
   is what silently sends every unknown name to `~/.rundesk/{run,logs,schedules}`.
4. **Migrate the owner's own install**, with a copy kept until it is proved.

## Every place that touches durable state today

Read off the source at `1046f3f`. When one of these moves, the row moves with it.

### Configuration

| today | becomes |
|---|---|
| `agent.chosen()` `agent.py:441` | `store.agent()` |
| `agent.remember()` `agent.py:456` | `store.remember_agent()` |
| `channel.known()` `channel.py:631` · `channel.of()` `:648` | `store.channels()` · `store.channel(name)` |
| `channel.remember()` `channel.py:653` | `store.remember_channel()` |
| `channel.tell()` `channel.py:696` | `store.tell_channel()` |
| `channel.forget()` `channel.py:723` | `store.forget_channel()` |
| `gateway.written_schedules()` `gateway.py:164` · `gateway.scheduled()` `:409` | `store.schedules()` |
| `gateway.changing_schedules()` `gateway.py:141` | `store.remember_schedule()` · `enable_schedule()` · `forget_schedule()` |

### History

| today | becomes |
|---|---|
| `session.of()` `session.py:38` | `store.session(conversation_id, brain)` |
| `session.remember()` `session.py:48` · `forget()` `:76` | `store.remember_session()` · `forget_session()` |
| `transcript.allocate()` `transcript.py:75` | `store.began()` — the number is the database's, and `runs/allocating.json` stops existing |
| `transcript.Writer.add()` `transcript.py:127` | `store.recorded()`, and the brain's own stream stays a file at `logs/runs/<run>.jsonl` |
| `transcript.Writer.went_wrong()` `transcript.py:138` | `logs/runs/<run>.err`, unchanged |
| `transcript.read()` / `events()` / `known()` `transcript.py:168+` | `store.records()` · `store.runs()` — these have **no product caller today**, so `runs` and `usage` are new surface rather than moved surface |
| `gateway.what_was_scheduled()` `gateway.py:1026` | `store.schedules()`, reading `last_auto_run_at` |
| `Gateway._remember()` `gateway.py:1834` | `store.schedule_fired()` |
| `gateway.last_seen()` `gateway.py:402` · `Gateway._say()` `:1864` | `store.last_seen()` · `store.seen()` |
| `gateway.what_was_interrupted()` `gateway.py:584` · `_note_interrupted()` `:635` | `store.runs()` filtered on outcome · `store.ended(outcome="interrupted")` — an interruption is how a run ended, not a thing of its own |

### Staying as files

`logs/gateway.log` (both writers, one inode, never renamed — see the roadmap on why),
`logs/runs/<run>.jsonl` (the adapter appends there through `RUNDESK_RAW`; you cannot hand a
shell script a database handle), `logs/runs/<run>.err`, `gateway.json`, `gateway.lock`,
`home/`, `providers/<p>/`, `channels/<c>/`.

## What migration `002` has to do

Walked against a real install in the roadmap's Phase 4; this is the mechanical form. Follow
[`migrations/README.md`](../../src/rundesk_cli/migrations/README.md) — you are handed a
connection inside a transaction, you never commit, and you never delete.

1. Read `agent.json` → one `UPDATE agent`.
2. Read `channels.json` → one row per channel.
3. Read `schedules/<agent>.json` → one row per schedule, with `command` set and `prompt` null.
4. Read `schedules/<agent>.ran.json` → `last_auto_run_at` on each schedule.
5. Read `schedules/<agent>.seen.json` → `gateway.last_seen_at`.
6. Read `schedules/<agent>.interrupted.json` → these describe work with no run row. **Decide
   before writing code**: a synthetic run per interruption, or dropped with a line saying so.
   This is the one item the walk could not settle from the data.
7. Read every `runs/<run>.jsonl`, in the order of the number in the name:
   - `admitted` → the `run` row and its `conversation`
   - `sent` → a `message` with `author='person'`, and `run.trigger_message_id`
   - `text` → a `message` with `author='agent'` and `run_id`
   - everything else → a `record`, `seq` preserved exactly
   - `outcome` → the run's `ended_at`, `outcome`, `exit_code` and token columns
8. `runs/<run>.raw` → the matching `record.raw`, matched by position in the file.
9. **Copy** `runs/<run>.brain` → `logs/runs/<run>.jsonl` and `runs/<run>.err` →
   `logs/runs/<run>.err`, and hand both originals back for the runner to remove after commit.
10. Hand back `agent.json`, `sessions.json`, `channels.json`, `runs/allocating.json` and every
    `.changing` file, so they go once the version has moved and not before.

### Two things the real install proves you must handle

- **A conversation key may be a session handle.** On the owner's install, `sessions.json` holds
  `{"codex": {"terminal": "019f9c43…", "019f9c43…": "019f9c45…"}}` — somebody passed
  `--conversation` a handle. Mint one conversation per distinct key and **never merge**: nothing
  in the data can prove two keys were one conversation, and guessing silently joins two
  histories.
- **The legacy layout is two files, not three directories.** `~/.rundesk/run` and
  `~/.rundesk/logs` do not exist; `~/.rundesk/schedules/` holds `twice.seen.json` and
  `twice.interrupted.changing`, sidecars of a gateway with no agent. Delete them and say so.

## Traps already paid for

- **`executescript()` commits before it runs.** It will silently end the transaction you were
  given. Execute statements one at a time — `store._statements()` splits a script the way
  SQLite does, which matters because a trigger body contains semicolons.
- **A reader that leaks its connection holds the WAL read lock on Python 3.11+ and not on 3.9**,
  so the leak is invisible on the version CI pins and an error on the machine you are using.
  Close every connection.
- **`agent.forget()` deletes by glob** — `*.json` and `*.changing` (`agent.py:408`) — so
  `state.db` is not caught by removal at all. Name it, and its `-wal` and `-shm`:
  `store.removes()` already returns all three.
- **Removing an agent now takes its account.** That contradicts ratified `R-AGW-5` and the
  `runs_home()` docstring at `agent.py:180`. The owner decided it; the row and the docstring
  change in the same commit as the behaviour.
- **Cross-agent stray sweeping is already dead** in the per-agent layout — `_sweep_strays()`
  globs a directory holding exactly one record (`gateway.py:820`). `R-GW-21` and `R-GW-23` are
  ✅ only because their tests share one `where`. Narrow the rows and stop the tests sharing it,
  in the commit that deletes the shared directory.
