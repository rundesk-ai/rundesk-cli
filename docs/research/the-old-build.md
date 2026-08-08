# How the build this replaces did agents and gateways

Established 2026-08-04, by reading `src_old/`, `tests_old/`, `docs_old/`, `.knowledge_old/` and
`old/` — all gitignored, reference-only, and expected to be deleted. Everything here is read off that
code and its own notes. Where a line says a thing *happened*, that build recorded it happening; where
it says a thing was *designed*, the code says so and nobody claimed it was ever proven.

The point of this page is not nostalgia. It is that a rebuild repeats the failures it did not write
down, and most of what follows cost somebody a real machine.

---

## What an agent was

`~/.rundesk/data/agents/<slug>/`, and **an agent was a directory containing `home/`**. That is what
let `.templates/` and `.roles/` sit among the agents without being listed as agents.

```
<slug>/
  home/                 everything the agent LOADS — the only thing an uninstall preserved
    AGENTS.md  CLAUDE.md  MEMORY.md  SOUL.md
    workspace/plans/    the cwd a turn ran in
    skills/             each grant a SYMLINK into the shared library, never a record
  providers/<key>/      per (agent, provider) credentials and sessions
  channels/<name>/      per (agent, channel) surface state
  run/                  <name>.lock, <name>.json, turns/<sha>.json — cleared when the gateway went
  logs/                 <name>.log[.1-3], <name>.out, <name>.err, runs/<run>.jsonl
  state.db              sqlite, one per agent, never shared
```

**One directory per agent was itself a lesson.** Before agents existed, what a gateway kept was
sharded by *kind* — a run directory, a log directory, a schedules directory — with the gateway's name
as a filename prefix inside each. Which is why a gateway named `foo.log` and one named `foo` wanted
one file between them, and why that build carried a whole `reserved_suffixes` / `_claimed_stems`
machinery: it probed its own path helpers with the name `"0"` and read off what got appended, to
work out which names an agent could not have. A directory each ends that entire class of collision.
Its own store guide says the machinery "disappears entirely once the files become `gateway.json` /
`gateway.lock` at the agent root", which is what this build does.

**Provider homes sat outside `home/` on purpose** — "a provider reading the agent's rules would be
reading its own state."

### A provider was a program, never code

Nothing was enumerated. A bare name resolved inside `src/providers/`; anything containing a path
separator was used as a path. It had to exist and be executable, or `NotRunnable`. Shipped adapters
were `claude`, `codex`, `grok`, `antigravity` — executables with no `.py`, importing nothing of the
product's. Everything was told to them through the environment (`RUNDESK_CWD`, `RUNDESK_PROVIDER_HOME`,
`RUNDESK_SKILLS`, `RUNDESK_POSTURE`, `RUNDESK_RESUME` and a dozen more), and they answered with a
newline-delimited record stream (`text`, `think`, `tool`, `result`, `usage`, `file`, `limit`, `done`).

**An agent with no provider was refused at creation.** Its own diagnosis code says why: "a brain
nobody named is what stands between this agent and every turn — and this said READY, which is a
diagnosis claiming a success it had not earned."

---

## The database

One sqlite `state.db` per agent, never one shared, "so a turn's write is never in another agent's
way". Per-agent configuration had *been* JSON (`agent.json`, `channels.json`, `sessions.json`,
`schedules/`) and was moved into the database; what deliberately stayed a file was the lock, the
liveness record, the log, and the per-run transcripts.

**There was no migrations table — the version *was* the record.** `PRAGMA user_version`, stamped
inside the same transaction as the step's work. The schema was `001.py` and nothing else described
it. Steps were found, not listed; duplicate numbers refused; a step returned the paths it had made
spare and the runner removed them only after the version committed; a step imported nothing of the
product's, so `001.py` carried its own copy of the statement splitter and the FTS5 probe.

`carry_every` walked agents in name order and **stopped at the first failure**, and
`carry_every_or_put_back` copied each `state.db` aside under the agents root first — deliberately
under the agents root, so redirecting agents redirected the rollback too.

### SQLite facts that were learned the hard way

Every one of these is from that build's own notes.

- **A migration numbered with a date-and-time silently destroys `user_version`.** It is a signed
  32-bit value; a number like `20260804_1200` wraps, and `0` is the "written partway" sentinel.
- **`Connection.executescript()` issues an implicit `COMMIT` before it runs**, so a step called
  inside a `BEGIN IMMEDIATE` quietly loses the transaction it was supposed to be in.
- **`BEGIN IMMEDIATE` succeeds on a read-only connection.** Read-only has to be asked for when the
  connection is opened, not relied on afterwards.
- **`DROP TABLE` fires the foreign-key actions pointing *at* it**, so rebuilding a table with
  children needs the children considered first.
- **`PRAGMA foreign_keys=OFF` is a no-op inside a transaction, and still answers `1` when asked.**
- **Never assert that `state.db-wal` and `state.db-shm` exist.** They are there only while a writer
  is live. They must still be *named* explicitly by anything that copies or removes the database,
  because a glob for `state.db*` is exactly what people write and it is not what they mean.
- A `NOT NULL` on `run.provider` meant a turn with no provider could not be written at all — which
  was the intended guarantee, discovered by something failing to write one.
- `ON DELETE SET NULL` on a schedule's foreign key was load-bearing: without it, a schedule that had
  ever fired could not be deleted, and since nothing edited one, a schedule became permanent the
  first time the clock reached it.

---

## Gateways

**The product supervised nothing.** One launchd job per gateway in `~/Library/LaunchAgents`, label
`ai.rundesk.<agent>`, domain `gui/<uid>`. Install-level jobs were namespaced with a *hyphen* —
`ai.rundesk-backup`, `ai.rundesk-update` — so the glob that found gateways could not match them.

The plist:

```python
{
  "Label": label(name),
  "ProgramArguments": [str(root / "rundesk"), "serve", name],
  "WorkingDirectory": str(root),
  "EnvironmentVariables": _environment(logs, run, agents),   # nine RUNDESK_*_DIR variables
  "RunAtLoad": True,
  "KeepAlive": {"SuccessfulExit": False},
  "ThrottleInterval": 10,
  "StandardOutPath": str(logs / f"{name}.out"),
  "StandardErrorPath": str(logs / f"{name}.err"),
}
```

### Liveness was asked of the kernel

A gateway held an exclusive `flock` on `run/<name>.lock` for as long as it ran, and the kernel
released it however the process died. So "is it running" was answered by trying to take the lock,
and **a record left behind by a gateway that was killed outright could not make a dead gateway look
alive**. The record beside it (`<name>.json`) held pid, version, start time, a beat, and
`time.monotonic()` — monotonic on purpose, because the wall clock moves in both directions on wake
and on NTP. Nothing in the record was trusted unless the lock said running: "a pid read off a record
whose process is gone is a pid that now belongs to something else."

**The lock file was never unlinked while released.** A lock lives on the inode, not the path, so
unlinking it while another gateway holds it hands the name away: the next claim makes a fresh inode
and locks that one, and two gateways answer as one identity.

Three orthogonal facts were reported separately, and that was deliberate: the **gateway process**
(the lock), the **launchd job** (`launchctl print` — and *silence was `Unknown`, never `no`*), and
the **version the running process was actually on** (from the record, marked `(old)` when it differed
from the installed one).

Wedged was `time.monotonic() - since_boot > BEAT_SECONDS * 3`, with a 15-second beat.

**There were no ports and no sockets.** Nothing bound, nothing listened. All coordination was flock,
atomically-renamed JSON, sqlite, and launchd. Channel adapters were subprocesses speaking
newline-delimited JSON over pipes.

### What the running process did

Ten concurrent tasks: a 15-second beat rewriting the record; a 20-second schedule tick (with the
first look **immediately**, not one interval later — a gateway that waited lost every occurrence due
in the last twenty seconds of the minute it started in, which is exactly the moment a machine
restarts one); one task per channel holding an adapter open and restarting it ten seconds after it
exited; role runs; delegations; skill-grant notices; and two hourly sweeps.

Everything it ran went through one funnel keyed by name, so the same work could never start twice,
registered *before* the spawn rather than after.

`claim()` in order: check fitness, take the lock, pick up where schedules got to, say what firings
were missed while down, sweep the predecessor's leftovers, sweep strays, reconcile unfinished work,
write the record, log "up".

Shutdown ended the whole process *group* — SIGTERM then SIGKILL — bounded well under launchd's own
patience, "because being killed is how children get left behind". If anything survived, or if a turn
it had merely *asked for* was still going, it wrote interrupted records, kept the liveness record,
and exited non-zero.

### The exit-code contract with launchd

This is the part worth carrying forward verbatim. With `KeepAlive: {SuccessfulExit: False}`:

> A gateway that is *refusing* to run — its virtualenv does not fit, or another already holds its
> name — must end **well**. Ending badly would have it started again ten seconds later, forever.

So the serve command returned **0** on already-running, unfit, bad name, and unreadable/behind/too-new
records, printing `NOT STARTED — <why>` and where to look. Non-zero meant "bring me back", and
`ask_to_stop(come_back=True)` exited 1 deliberately, because `KeepAlive` was the only way a gateway
could restart itself.

### Logs

`RotatingFileHandler`, 2 MB, 3 kept, `logs/<name>.log`. Plus `.out` and `.err`, which were what
launchd captured and **the only place a start that died before the logger existed said anything**.
The logger was built directly rather than fetched from the registry, because two gateways in one
process would otherwise share a name; and a stderr handler was added only when stderr was a tty,
because a supervised gateway that also wrote to stderr duplicated every line into an unrotated `.out`
shadow that nothing rotated.

---

## Every incident it recorded

These are the ones with a cost attached. A rebuild that only reads the code repeats all of them.

### Locations

- **Three real agents were created in the owner's live install** by a scratch run that redirected
  `RUNDESK_HOME`, `RUNDESK_RUN_DIR`, `RUNDESK_LOG_DIR` and `RUNDESK_JOBS_DIR` — which looks
  exhaustive — and missed `RUNDESK_AGENTS_DIR`, whose own value beat `RUNDESK_DATA_DIR`. `rundesk
  add` reported success each time. They had to be removed by hand.
- **`RUNDESK_DATA_DIR` did not isolate a scratch install when an agent was doing the work**, because
  a gateway exported `RUNDESK_AGENTS_DIR` into every turn and it won.
- **A suite left nine log files in the owner's home** by building a gateway without *both*
  `RUNDESK_RUN_DIR` and `RUNDESK_LOG_DIR` at scratch.
- **`./install.sh --uninstall --purge` deleted the owner's live `~/.config/rundesk`** because
  `RUNDESK_SECRETS_DIR` was not redirected — and backups deliberately did not copy secrets, so there
  was no restore.
- **Adding a new `RUNDESK_*_DIR` was caught by a test that greps four named modules' source.** A
  fifth module (`secret.py`) was added and the test stayed green while a supervised gateway would
  have resolved a different directory from the command that wrote its job — the exact failure the
  test existed to prevent.

The whole class is why this build has **one** variable and derives everything from it.

### launchd

- **A second install's uninstall booted out `ai.rundesk-automatic-update` — the live install's job**
  — and left its own plist on disk looking well. A label belongs to the *person*, not to a directory,
  so no amount of redirecting isolates one.
- **Taking a job away returns before the machine has finished doing it.** Offering a replacement
  into that gap fails with an input/output error that says nothing about timing, leaving no job at
  all — so the next attempt succeeds and the one after that fails, alternately, forever.
- **Two parties have to let go, and both must be asked.** Judging a name released on the gateway
  process alone reported it taken back while the machine was still refusing to release its job — so
  an uninstall deleted the install and left the machine trying to start a command that was no longer
  there, every few seconds and again at every login.
- **`~/.local/bin` missing from the job's PATH cost a working provider.** A fresh machine reported
  the CLI "not on this machine's path" while `which` in the owner's shell answered perfectly well:
  the product had installed itself into a directory it then refused to look in.
- **A fifth environment variable left out of the plist split the machine in two.** A schedule could
  be added, listed and shown as due by the command line while the gateway keeping the machine knew
  nothing of it.

### Processes

- **`_held()` answers about the moment it was called.** Between that answer and a signal, a gateway
  of that name can claim the name and start work — so an ordinary `start` ended a live agent's whole
  process tree. Fixed by holding the name across the decision rather than asking and then acting.
- **A leftover process group was only ever killed if `ps` said its start time still matched** the
  recorded fingerprint. "Asked, and not told" (ps would not answer) was treated as *leave it alone
  and keep the record* — not as "it is a stranger". Naming a stranger in the record is how the next
  start comes to aim at it.
- **Never name a real process group in a test.** `killpg` degenerates at `0` — the caller's own
  group, which killed the test run and its shell — and at `1`, which on Linux is
  `kill(-1, …)`, *every process this user may signal*, and took the CI runner's own agent with it.
- **A turn a schedule asked for is not in `running`.** Taking that for "nothing left" reported a
  clean stop, exit zero and "down", while a brain was still working.
- **A gateway holds the module it imported when it started.** Editing a module and restarting the
  *adapter* is not enough — the adapter is a fresh process each time and the gateway is not. An
  attachment downloaded correctly by a new adapter was dropped by an old seam, which reads exactly
  like the adapter being broken.

### Reporting

- **`rundesk restart` with no name meant every gateway**, silently. It read as "the one you have",
  and it took down every agent somebody had. `--all` became required.
- **A failed restart fell into the block written for `stop`** and came out as `ALREADY STOPPED` with
  a success exit — a true sentence and a completely wrong one.
- **A shared `logs/gateway.log`** was where the one explanation of why an agent's records could not
  be read was written, and `rundesk logs <agent>` read `<agent>.log` — so for every agent not itself
  called `gateway`, the answer sat in the very directory the command read and could not be reached
  from it. Nothing rotated it either.
- **Markers were never put in the name column of a table.** Anything reading the table by name stops
  finding one, "which is exactly how CI came to report a running gateway as never started."
- **`rundesk agents <agent>` and subcommands under `agents` cannot both exist** — an optional
  positional and a sub-parser compete for the same word. This build takes the verb-first spelling
  for that reason.

### Removal

Removing an agent used to keep its history behind a second flag. It was reversed, and the reason is
worth keeping: "an account nobody can name an agent for is an account nobody reads, and what it left
behind was inherited by whoever took the name next." It mattered most for channels — an agent added
back under a name that was on somebody's server would be on it again, answering whoever was allowed
then, without anybody having asked for either.

---

## What was worth keeping, and what was not

**Kept, and cheap to keep:** flock-as-liveness with no pid file; one directory per agent; the schema
being the first migration step rather than a separate description; migrations that copy-then-return-
spare rather than delete; baking every redirectable path into the plist; ending *well* when refusing
to run; `Unsure` as a third answer distinct from `no`; `--all` required rather than implied; a
diagnosis that always says what to type.

**Not kept, because each cost a real incident:** the `run/*.json` glob doubling as the registry of
gateways; nine `RUNDESK_*_DIR` variables that had to be redirected together, enforced by a test that
grepped four named modules; labels that no directory redirect could isolate; `<name>.<suffix>`
sidecars and the reserved-suffix machinery they forced; and stopping a whole sweep at the first agent
that failed.
