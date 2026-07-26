# Moving onto the store — what Phase 7 did, and what is left

Phase 4 built [`store.py`](../../src/rundesk/store.py) and
[`migration.py`](../../src/rundesk/migration.py) and pointed nothing at them. This is the
page that says how everything is pointed at them without improvising.

**If the design turns out to be wrong, the contract moves first.** The whole point of the phase
before was that this one does not discover its design while building it. A surprise is a finding
against [`agent-store`](../prd/agent-store.md) or
[`lifecycle-migration`](../prd/lifecycle-migration.md), not a special case in the code. Several
were found, each recorded in the roadmap's Phase 7 with what was decided about it.

**There is no migration `002`.** Nothing is released, so there is no data on any machine to
carry: `001.py` is the whole shape, and everything the move proved missing went into it —
`run.why`, `run.settings`, `channel.describes`, `channel.fills`, `channel.activity` and
`schedule.last_outcome`, each of which the shipped code already wrote and the drawn shape had
nowhere for. The runner is wired to the update and proved anyway, because the version that *does*
have data to carry must not be the one that discovers the wiring.

## What has moved

| was | is |
|---|---|
| `agent.json` | `store.agent()` · `remember_agent()`, reached through `agent.records()` for a caller that may write and `agent.reading()` for one that may only ask — `doctor` must not be able to repair what it was asked to inspect |
| `channels.json` | `store.channels()` · `channel()` · `remember_channel()` · `tell_channel()` · `forget_channel()`. `channel.py` is now only the seam a *surface* is reached through; a record is handed to it rather than fetched by it |
| `sessions.json`, and `session.py` with it | `store.session()` · `remember_session()` · `forget_session()` over `store.opened()`. A conversation is a *place* — `store.conversation_id(channel, space, thread)` — rather than a string two callers built to different recipes |
| `runs/<run>.jsonl` · `.raw` · `allocating.json` | `store.began()` · `recorded()` · `arrived()` · `answered()` · `ended()`. The run number is the database's, allocated inside the transaction that writes the row |
| `runs/<run>.brain` · `.err` | `logs/runs/<run>.jsonl` · `.err` — all that is left of `transcript.py` |
| nothing; new surface | `runs`, `usage` and `search`, which is what makes any of the above readable by an owner rather than by a test |

## What is left, and why it is one move

**The gateway's own three directories.** `run/`, `logs/` and `schedules/` are where they were, and
`Gateway` still takes them as three arguments. What goes with them:

- `changing_schedules()` · `written_schedules()` · `scheduled()` → `store.schedules()` and the
  four writers beside it. **`schedule.read()` parses `{name, when, run}` and a row is
  `{name, cron, command}`** — that mapping is the only real design work left in the phase.
- `what_was_scheduled()` · `Gateway._remember()` → `store.schedule_fired()` ·
  `schedule_became()`, which exist and are proved.
- `last_seen()` · `Gateway._say()` → `store.last_seen()` · `seen()`. **Mind the units:** the file
  held `time.time()` as a float and the store holds an ISO string, so `_say_what_was_missed`
  changes with it — and AGENTS.md forbids comparing the two kinds of clock.
- `what_was_interrupted()` · `_note_interrupted()` → `store.runs()` filtered on outcome ·
  `store.ended(outcome="interrupted")`. `_sweep_strays()` is deleted; R-GW-21 and R-GW-23 narrow,
  and their tests stop sharing one `where`.
- `run/<name>.json` and `.lock` → `gateway.json` and `gateway.lock` at the agent root. **No file
  a gateway writes carries a name any more**, so `reserved_suffixes()` and the whole class of
  collision R-AGT-6 guards against go away with it.
- `every()` and `remembered()` walk files to find gateways. The agents directory is that list now,
  so both move above the gateway rather than being rewritten inside it.
- Last, and only once every reader above has moved: `gateway.home()`, `logs_home()`,
  `schedules_home()`, the `RUNDESK_{RUN,LOG,SCHEDULES}_DIR` variables `supervisor.describe()`
  bakes into the job, `agent.resolved()` returning `Where(None, None, None)`, `agent.adopt()` and
  `standing_before()` with it, and `logs` and `schedules` off `install.sh`'s keep-list.

**It is one move rather than four** because a `Gateway` reading its schedules from one place and
its record from another is half-moved, and the constructor that decides both would otherwise be
changed four times. The seam it turns on is `Gateway(name, at=<the agent's directory>)`, resolving
its own store, log and record from that one argument — which is also what makes a gateway stop
needing to know that names and files were ever related.

## What already reports, and what still has to

`store.py` and `migration.py` write into the agent's own log — a refused version, records that
cannot be understood, a write that gave up, a machine with no WAL or no search, and every
migration step that ran or failed. An ordinary read or write writes nothing, deliberately.

**Nothing else does yet.** As each reader moves onto the store, whatever it used to report has
to keep being reported — a schedule that could not fire, a channel that could not connect, a
turn whose account could not be written. The rule to hold: after Phase 7, one agent's log tells
the whole story of that agent, and no part of that story is only in a caller's return value.

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
[`migrations/README.md`](../../src/migrations/README.md) — you are handed a
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
