# Codemap — rundesk-cli

The always-loaded structural map: *where things are*, layer by layer. Keep it current — when you move
or restructure files, update this in the same task.

**Stay high-level.** List entry points, layers, and where each *kind* of thing lives — not every file.
A map that mirrors the whole tree rots on the next commit; one that names the landmarks stays true.

## Entry Points

- `rundesk` — the executable the installer symlinks onto a PATH. It resolves its own location, puts
  `src/` on the path and hands off to `cli.main`. It owns no logic, so everything below is importable
  and testable without it.
- The machine's own supervisor, running `rundesk serve <name>` from a job `supervisor.py` wrote. The
  second way in, and the one nobody types: it is how a gateway is still there tomorrow.

## Domain / Data

- `src/rundesk/__init__.py` — **`__version__`, the one source of what version this is.** The command
  reports it, the updater compares against it, and a release tag is expected to match it. Nothing else
  holds a copy. `ROOT` is the same idea for *where* this install is, resolved rather than assumed.

### What is written down, and where (5 directories)

**What the product runs on today is below; what it is moving to is `store.py`, and nothing reads that
yet.** Everything the shipped code persists is a small JSON file written whole and renamed into place,
so a reader
arriving mid-write finds the old one rather than half of the new one. Each directory is overridable by an
environment variable, and every one of them is carried in the launchd job — a gateway reading somewhere
other than the command that configured it is the fault that makes a schedule silently never run.

One reader and one writer serve all of them: `gateway._read()` says which of missing, unreadable or
written a file turned out to be — the two absences being opposite decisions — and `gateway.changing()`
holds the read, the decision and the write under one `flock`, asking the machine to put what records
what has *already happened* onto the disk before saying it is there.

**Everything that is one agent's lives in one directory.** `~/.rundesk/agents/<agent>/` holds its `home/`
(what it loads), the private homes providers are given, the account of every turn it has taken, and the
three its gateway uses — so an agent is one
thing to look at, copy or take away, and no name can claim a file belonging to another. The three
directories below the agents one hold what rundesk wrote *before there were agents to own it*: a gateway
still running from then goes on reading them, and rundesk writes nothing new there. Every schedule, log and
lock in the finished product belongs to an agent.

| Where | Override | Holds | Lifetime |
|---|---|---|---|
| `~/.rundesk/agents/<agent>/home/` | `RUNDESK_AGENTS_DIR` | `AGENTS.md` · `CLAUDE.md` · `SOUL.md` · `USER.md` · `MEMORY.md` · `workspace/` · `skills/` | **The owner's** — kept by an ordinary uninstall, taken only by `--purge` (R-AGT-3) |
| `~/.rundesk/agents/<agent>/providers/<provider>/` | `RUNDESK_AGENTS_DIR` | the private home a provider is given, per agent and provider pair | Rundesk's state about a pair, never the agent's knowledge (R-AGT-8) |
| `~/.rundesk/agents/<agent>/run/` · `logs/` · `schedules/` | `RUNDESK_AGENTS_DIR` | what that agent's gateway keeps — the same files as below, in the agent's own place | As below, per agent |
| `~/.rundesk/agents/<agent>/runs/` | `RUNDESK_AGENTS_DIR` | one run each: `<run>.jsonl` (the account, in words no brain owns) · `<run>.raw` and `<run>.err` (everything the brain said, and said went wrong, verbatim) · `allocating.json` (the count of runs, a hint — the directory is the truth) | **History** — goes when the agent does (R-AGW-5). The two raw files are separate so a retention policy can one day take them and leave the account (R-RUN-5) |
| `~/.rundesk/agents/<agent>/state.db` | `RUNDESK_AGENTS_DIR` | **everything the agent keeps**, and the only way in is [`store.py`](../src/rundesk/store.py). Which brain it reaches for is here now; where each conversation got to and the surfaces it is reachable on are still `sessions.json` and `channels.json` beside it, and move next | Goes when the agent does (R-AGW-5, R-STO-14) |
| `~/.rundesk/agents/<agent>/sessions.json` · `channels.json` | `RUNDESK_AGENTS_DIR` | where each conversation got to — keyed by brain *and* conversation together — and the surfaces it is reachable on, each holding who may use it and the *name* of the variable its credential is read from, never the credential | Rundesk's working state about the agent; goes when the agent does (R-RUN-12, R-RUN-14, R-CAD-12) |
| `~/.rundesk/agents/<agent>/channels/<channel>/` | `RUNDESK_AGENTS_DIR` | the private home a channel is given, per agent and channel pair | Rundesk's state about a pair, never the agent's knowledge |
| `~/.rundesk/run/` | `RUNDESK_RUN_DIR` | `<name>.lock` (liveness, held open) · `<name>.json` (what a gateway is doing now) | **State** — cleared when a gateway stops (R-GW-12) |
| `~/.rundesk/logs/` | `RUNDESK_LOG_DIR` | `<name>.log` (rotated) | **History** — outlives the gateway (R-GW-18) |
| `~/.rundesk/schedules/` | `RUNDESK_SCHEDULES_DIR` | `<name>.json` (what is scheduled) · `<name>.ran.json` (when each last fired and what became of it) · `<name>.seen.json` (when a gateway of this name was last up) · `<name>.interrupted.json` (work that never got to finish, and whether it is definitely gone) · `<name>.changing` and `<name>.interrupted.changing` (held across a read-and-write, so two writers cannot lose one another's change) | **History**, beside what it describes |
| `~/Library/LaunchAgents/` | `RUNDESK_JOBS_DIR` | `ai.rundesk.<name>.plist` | The machine's, written by `supervisor.py` |

The split is the point: stopping a gateway must clear what it is *doing* without clearing what it *did*.
Putting the schedule history with the run state erased it on every ordinary restart. `run/` and `runs/`
are one letter apart and opposite for the same reason — the first is emptied when a gateway stops, and the
second is what an owner still has in the morning.

A run's account is the one thing here that is **appended** rather than written whole, because it is
written while the thing it accounts for is still happening and has to be readable throughout. Nothing
rewrites it; a retention policy takes whole files.

## Backend / Services (src/rundesk/ — 16 modules)

- `src/rundesk/cli.py` — the command surface: every verb the finished product will have, registered
  from the outset. What the gateway verbs act on is passed in rather than imported, so the surface knows
  the verbs and nothing of locks, records or process groups. `PLANNED` is the table of every operation
  registered and not built, each with the actions under it; every one answers and exits `NOT_AVAILABLE`
  rather than reporting a success it did not earn, and rather than argparse's usage code, which would
  make a missing command indistinguishable from a typo. An entry graduates out of that table into a real
  command as it lands.
- `src/rundesk/agent.py` — the named identity work is run for: its name, its home, and where
  everything of its own stands. Above the gateway and never beside it — it resolves an agent's three
  directories and hands them to a `Gateway`, which is why a gateway goes on knowing nothing of whose work it
  holds. A new agent's home is copied from `src/templates/agent/` — stubs an owner reads and edits, kept beside the package rather than inside it, and what a home holds is read off that
  directory rather than listed in code. What a name may be is stricter here than for a gateway: one path
  component, standing where agents are kept, and never a word a gateway writes beside some other name.
- `src/rundesk/provider.py` — the seam a brain is reached through, and nothing about any
  particular brain. Resolves a provider — a shipped adapter, or a path to a program somebody wrote — into
  something runnable, builds the environment it is told everything through, asks what it can do, and reads
  one of its records. **Enumerates nothing**: no list of providers and no list of models, so one rundesk
  has never heard of is the ordinary case. A vendor name appearing in this file is the seam already failing.
- `src/providers/` — the brains that ship, one program each. Not modules: nothing imports them
  and they import nothing of ours, so a vendor's flags, stream shape, session file and usage arithmetic
  live in one file and reach no further. `adapters/codex` is the first.
- `src/rundesk/channel.py` — the seam a surface is reached through, and nothing about any
  particular platform. The mirror of `provider.py`: resolves a channel — a shipped adapter, or a path to
  a program somebody wrote — builds the environment it is told everything through, asks whether it can
  reach what it was pointed at, frames one record each way, and holds what is written down about a
  channel. **Enumerates nothing**: no list of platforms and no list of what one needs, so whatever a
  surface calls its places arrives as options this file hands straight back unread. It also holds the two
  decisions a surface does not get to make — what state a turn is in, and that what a brain *says* is
  handed over once and whole. A platform's word appearing in this file is the seam already failing.
- `src/channels/` — the surfaces that ship, one program each. Not modules: nothing imports
  them and they import nothing of ours, so a platform's ids, intents and limits live in one file and
  reach no further.
- `src/rundesk/answering.py` — what arrives on a channel, carried through to an answer: the mirror of
  `turn.py`, and the only module that knows `channel`, `turn`, `session` and `agent` all exist. Two things
  live here and nowhere else, because two surfaces deciding either separately would eventually disagree
  about one run: **who may be answered**, checked against the record the owner wrote rather than trusted to
  an adapter, and **what state a turn is in**. Writes nothing down — the run's own account already records
  it, and a channel that kept a second copy would become the only place something existed.
- `src/rundesk/transcript.py` — what a run did, written while it did it. Three files per run: the
  account, in words no brain owns, added to and never rewritten; and beside it, verbatim, everything the
  brain said and everything it said went wrong. Separate so a retention policy can one day take the raw and
  leave the account standing. Ordered by a count rather than a clock, so two runs of one conversation read
  in the order the work happened whatever the machine's clock did.
- `src/rundesk/session.py` — where a conversation got to, kept for a conversation and a brain
  **together**. The brain is the outer key, so handing one brain's session to another is not expressible.
- `src/rundesk/turn.py` — the only module that knows the four above exist: resolve, write down what was
  resolved, run the brain, write down what it said, keep where the conversation got to, write down how it
  ended. Nothing reaches a brain that the account does not show.
- `src/rundesk/store.py` — everything one agent keeps, and **the only way in to it**. One database per
  agent, never one shared, so a turn's write is never in another agent's way. Reading and writing are told
  apart at the connection: a reader is opened read-only, so it cannot begin work that would make a turn
  wait — refused by the database rather than by convention. No statement is written anywhere else and no
  connection ever leaves the module, both proved by looking. **Nothing reads it yet**; it is built and
  proved before anything moves onto it, so deleting it would leave the product exactly as it is.
- `src/rundesk/migration.py` — moving what is already on a machine into the shape a newer rundesk
  expects. **A step is found, not listed**: each is `migrations/<version>.py`, ordered by that number, and
  what runs is whatever sits between the version on disk and the version installed. There is no table of
  what has run because **the version is the record** — SQLite keeps DDL inside a transaction, so a step's
  schema change, its data change and its version stamp commit together. A step may copy a file and never
  delete one; the runner removes what it hands back only once the version has committed, so a step that
  died halfway leaves both copies rather than neither. Going backwards is refusing to go forwards.
  `carry_every()` walks every agent in turn and stops at the first that cannot be moved, and every step
  that ran or failed is written into that agent's own log — an update that went wrong overnight is read
  afterwards rather than watched.
- `src/migrations/001.py` — **the schema, and the only description of it there is.** Making an
  agent runs the migration path from nothing rather than building tables directly, so the path is exercised
  every time anybody adds an agent and a fresh install cannot drift from an upgraded one.
- `src/rundesk/updater.py` — where this install stands against what is published, and moving between
  them. Every network call is behind an argument, so the whole module is exercised offline.
- `src/rundesk/process.py` — a program rundesk runs, and how it keeps hold of it: its own session so
  ending it ends the whole tree, silence rather than duration as the failure, output streamed and never
  accumulated. Knows nothing of gateways or agents, and holds no state of its own, so any number of
  programs run at once. Two ways of reading one, sharing every rule about when to stop: output **meant to
  be read** goes line by line to the caller as it always has, and output **meant to be parsed** goes as
  whole records through what is held for a receiver — kept apart from what the program says went wrong,
  written back to while it runs, and never split, so that a slow or failing receiver can neither hold up
  the program nor end it.
- `src/rundesk/gateway.py` — the part that stays running. One per name from the outset, since a
  gateway per agent is how one agent is cycled without disturbing the rest. Owns every program started
  through it, and proves it is alive with a lock the kernel drops when the process dies. Writes what
  happened to its own log, kept apart from its run state because history has to outlive the gateway.
- `src/rundesk/schedule.py` — work that starts itself: what a schedule is, when one is next due, and
  which are due now. Knows nothing of gateways or processes, and what a schedule names is carried without
  ever being read — so the day it names an agent rather than a command, nothing here changes. The time is
  an argument, so a year of firings is decided in a millisecond.
- `src/rundesk/supervisor.py` — handing a gateway to the machine that keeps it running: one job per
  gateway, and never one this install did not write. Every call out to the machine is an argument, so it
  is exercised on a machine with no supervisor at all.

## Frontend / UI

- No UI. The command line is the whole surface.

## Tests (tests/ — 15 files, ~790 cases)

`unittest`, run directly (`python3 tests/test_cli.py`), never touching the network and never running a
provider. One file per contract, named for it:

| File | Cases | Covers |
|---|---|---|
| `test_gateway.py` | 139 | `platform-gateway` — real processes, real signals, waits turned down |
| `test_agent.py` | 41 | `agent-home` + `agent-gateway` — one scratch machine per case, no provider |
| `test_cli.py` | 86 | `command-surface` — walks every verb off the parser, so one wired nowhere is caught |
| `test_process.py` | 87 | `platform-process` — real process groups, grandchildren, drains and ceilings |
| `test_updater.py` | 55 | `lifecycle-update` — behind, current, could-not-ask; and an archive that cannot escape |
| `test_install.py` | 41 | `lifecycle-install` — drives the real `install.sh` in a **copy** of the checkout, so the gate can be run twice |
| `test_supervisor.py` | 38 | the launchd job — a fake `launchctl`, so it runs where there is none |
| `test_schedule.py` | 28 | `platform-schedule` — pure time arithmetic, the clock passed in |
| `test_provider.py` | 31 | `provider-adapter` — **takes the adapter as an argument**; stand-ins it writes itself, so the gate needs no account, and one adapter in `strangers/` that this code never saw being written |
| `test_turn.py` | 39 | `agent-run` — one whole turn, and `rundesk ask` end to end |
| `test_transcript.py` | 20 | `agent-run` — the account: append-only, clock-free, and what survives a pruning |
| `test_session.py` | 9 | `agent-run` — a handle kept for a conversation and a brain together |
| `test_store.py` | 57 | `agent-store` — a database in a temp directory and nothing else: a reader that cannot write, two writers that cannot lose a change, two agents that never wait on each other, and the proof that no statement or connection escapes the one module |
| `test_channel.py` | 42 | `channel-adapter` — **takes the adapter as an argument**; stand-ins it writes itself, so the gate reaches no platform and needs no token, and one adapter in `strangers/` that this code never saw being written |
| `test_answering.py` | 36 | `channel-messaging` — both edges are arguments, so a routing failure and a platform failure can never be confused |
| `test_discord.py` | 37 | `channel-discord` — the policy and never the wire: who it answers, what a mark means, how a long answer is broken up |

Counts drift; what must not is one file per contract. Every `prd/` row names the tests that prove it, and
`.knowledge/scripts/check-evidence` fails the build when a row names one that does not exist.

## The layers, and which way they point

`cli` → `gateway` → `process`, and `supervisor` → `gateway`. `process` has never heard of a gateway,
which is what lets any number of programs run at once without coordinating. The command surface takes
what the gateway verbs act on as an argument rather than importing it, so the surface knows the verbs
and nothing of locks, records or process groups — and every one of them is tested with no gateway and
no supervisor anywhere near it.

The agent sits **above** the gateway, never beside it: `cli` → `agent` → `gateway` → `process`. One agent
has one gateway, made with it and taken away with it — the gateway *is* the agent's name, so there is no
record of the pairing that could disagree with itself. `agent` resolves the three directories and hands
them to `Gateway`, which already took them as arguments, so a gateway goes on knowing nothing of whose work
it is holding. That is what keeps the two testable apart while the command surface operates them as one
thing, and it is the direction to keep: never a gateway that reaches for an agent.

## Scripts And Commands

- `install.sh` — puts `rundesk` on a PATH and takes it off again (`--uninstall [--purge]`). Installs
  into `~/.rundesk`, one directory under the person's home holding rundesk and its `.venv`; from a
  checkout it symlinks that checkout instead, so development and installed use share one layout.
  Removing takes the install directory entry by entry rather than whole, so an ordinary uninstall
  keeps `logs/` and `schedules/` and only `--purge` takes them. It changes nothing else a person owns — a `PATH` that does not reach the command is reported, never
  edited — and refuses to claim success until the installed command answers.
- `CLI.md` — every operation the command offers, how each is typed, and what each argument means.
  **Generated** by `.knowledge/scripts/cli-reference` from the parser, so it cannot describe a product
  nobody has; the gate fails when it and the command disagree.
- `.knowledge/scripts/gate` — everything that has to be true before work here is finished, in one
  command. The suites are **found**, not listed, and it fails when the workflow does not name one of
  them, so the local gate and CI cannot come apart. Runs everything rather than stopping at the first
  failure, and says what it did not cover: the real `./install.sh` and `--uninstall`.
- `.github/workflows/build.yml` — the gate, in four named jobs so a red X says what broke: the knowledge
  base (docs, contracts, evidence); the tests, one step per contract, across macOS and Ubuntu on Python
  3.9 (the oldest a fresh macOS ships) and 3.13, with an empty `.venv` put beside the checkout so a
  runner is the machine a developer has; installing this checkout, using it — including starting a real
  gateway through the installed command, which is the only thing that exercises how the launcher reaches
  what was installed — and removing it; and installing the published release on a bare machine.
- `.github/workflows/release.yml` — a `vX.Y.Z` tag publishes the release that `rundesk update` finds.

## Integrations / Jobs

- `GitHub Releases` — the only thing this reaches out to: the newest published tag, and the archive an
  update is fetched from.

## Docs

- `.knowledge/` — the knowledge system (prd/, prd-drafts/, research/, references/, guides/). See `.knowledge/README.md`.

---
*Editing this file? Follow the standard first: [`guides/docs-codemap.md`](./guides/docs-codemap.md).*
