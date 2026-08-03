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

### Where what an install keeps is decided (8 places)

An install's own directories are not mapped here — this is the source tree, and a layout written down
twice is a layout that disagrees with itself. Each of these files *is* the answer for one part of it, and
none of them is a copy of another:

| Decided in | What it settles |
|---|---|
| `src/rundesk/__init__.py` — `data_home()`, `scripts_home()`, `skills_home()` | **the program and the data are two directories**: `app/` is what an update replaces and an uninstall takes whole, while owner commands, skills, and catalogs resolve below the data it never touches (R-INS-13, R-RM-8, R-PROC-22) |
| `src/rundesk/agent.py` — `agents_home()`, `directory()`, `paths()` | every directory that is one agent's own, off one list that making and diagnosing both read |
| `src/rundesk/agent.py` — `templates_home()`, `sourced()` | where an owner's own templates stand and which file each page really comes from. **Below `agents_home()`**, so whatever redirects where agents live redirects it too, and outside anything a release ships, which is the whole of why an update cannot reach it (R-AGT-23) |
| `src/rundesk/dependencies.py` — `wanted_at()`, `site_packages()` | what this install is made of and where it is kept, asked the same way by the installer, an update and a gateway |
| `src/migrations/` | **the shape of everything an agent keeps**, and the only description of it there is. `001.py` is the shape an agent starts from and every step after it is one change to that shape, so what the records are today is the steps read in order — never a second description kept beside them |
| `src/rundesk/store.py` | the only way in to it, and what may be asked of it |
| `src/rundesk/supervisor.py` — `describe()` | what the machine's own job carries, so a gateway resolves what the command that made it resolved (R-AGT-9) |
| `src/rundesk/secret.py` — `home()` | **the one thing an install keeps that stands outside `data_home()`** — the values every program it starts is given. Outside on purpose: `backup.py` copies `data_home()` and nothing else, so a copy of an install is structurally incapable of holding a credential rather than careful not to (R-SEC-26) |

**Everything that is one agent's lives in one directory**, so an agent is one thing to look at, copy or
take away, and no name can claim a file belonging to another. What is *not* in its records is deliberate
and short: what a brain printed and what it said went wrong stay files, because the path is handed to a
program that may be a shell script and stderr is a pipe the operating system gives us — so those may be
destroyed to reclaim space, and nothing a run recorded is recoverable only from them (R-STO-5).

Anything still kept as a small JSON file is written whole and renamed into place, and `durable.changing()`
holds the read, the decision and the write under one `flock`. Those are what remain to move (see
[`guides/moving-onto-the-store.md`](guides/moving-onto-the-store.md)); each one that goes takes its lock
file with it.

## Backend / Services (src/rundesk/ — 36 modules)

- `src/rundesk/cli.py` — the command surface: every verb the finished product will have, registered
  from the outset. What the gateway verbs act on is passed in rather than imported, so the surface knows
  the verbs and nothing of locks, records or process groups. `PLANNED` is the table of every operation
  registered and not built, each with the actions under it; every one answers and exits `NOT_AVAILABLE`
  rather than reporting a success it did not earn, and rather than argparse's usage code, which would
  make a missing command indistinguishable from a typo. An entry graduates out of that table into a real
  command as it lands.
- `src/rundesk/commands/` — **one command group per module, and the only layer that may know
  argparse.** A group takes a `Namespace` and hands back an exit code; what it acts on — the
  gateways, the machine, the agents, the skills — arrives as an argument from `cli.main`, so every
  verb is exercised with none of them near it. `cli.py` keeps the parser and the dispatch and imports
  each handler **by name**, which is why the dispatch chain reads the same as it did when all of it
  lived in one file — and is not an accident of style: a module alias would collide with `main`'s own
  `agents` and `skills` parameters and with cli.py's existing `backups`, `schedules` and `config`
  aliases. `__init__.py` holds what more than one group needs and nothing below wants: how a table is
  printed, how a change reaches an agent's log, how a call that may block inside the operating
  system is given up on, and how a long command says where it has got to. A group may also call
  another group — `update` refreshes skill catalogs, which is the skills group's job and prints
  like one — but only one way, never in a cycle.
- `src/rundesk/agent.py` — the named identity work is run for: its name, its home, and where
  everything of its own stands. Above the gateway and never beside it — it resolves an agent's three
  directories and hands them to a `Gateway`, which is why a gateway goes on knowing nothing of whose work it
  holds. A new agent's home is copied from `src/templates/agent/` — stubs an owner reads and edits, kept beside the package rather than inside it, and what a home holds is read off that
  directory rather than listed in code. What a name may be is stricter here than for a gateway: one path
  component, standing where agents are kept, and never a word a gateway writes beside some other name.
- `src/rundesk/instructions.py` — Rundesk's core and trigger instructions, their communication-agnostic
  variables, and the builder that composes them with adapter and owner additions.
- `src/rundesk/provider.py` — the seam a brain is reached through, and nothing about any
  particular brain. Resolves a provider — a shipped adapter, or a path to a program somebody wrote — into
  something runnable, builds the environment it is told everything through, asks what it can do, and reads
  one of its records. **Enumerates nothing**: no list of providers and no list of models, so one rundesk
  has never heard of is the ordinary case. A vendor name appearing in this file is the seam already failing.
- `src/providers/` — the brains that ship, one program each. Not modules: nothing imports them and they
  import nothing of Rundesk's, so a vendor's flags, system-prompt transport, stream shape, session file
  and usage arithmetic live in one file and reach no further. Four so far —
  `codex`, `claude`, `grok` and `antigravity` — and adding the
  latter three changed nothing above this line, which is the claim the seam was built to make. Each is
  driven offline by a suite of its own against real captured output in `tests/samples/`.
- `src/rundesk/channel.py` — the seam a surface is reached through, and nothing about any
  particular platform. The mirror of `provider.py`: resolves a channel — a shipped adapter, or a path to
  a program somebody wrote — builds the environment it is told everything through, asks whether it can
  reach what it was pointed at, and frames one record each way. What is *written down* about a channel is
  part of what its agent keeps and is asked for through `store.py`; a record is handed to this module
  rather than fetched by it. **Enumerates nothing**: no list of platforms and no list of what one needs, so whatever a
  surface calls its places arrives as options this file hands straight back unread. It also holds the two
  decisions a surface does not get to make — what state a turn is in, and that what a brain *says* is
  handed over once and whole. A platform's word appearing in this file is the seam already failing.
- `src/channels/` — the surfaces that ship, one program each. Not modules: nothing imports them and they
  import nothing of Rundesk's, so a platform's ids, prompt additions, intents and limits live in one file
  and reach no further.
- `src/rundesk/answering.py` — what arrives on a channel, carried through to an answer: the mirror of
  `turn.py`, and the only module that knows `channel`, `turn` and `agent` all exist. Two things
  live here and nowhere else, because two surfaces deciding either separately would eventually disagree
  about one run: **who may be answered**, checked against the record the owner wrote rather than trusted to
  an adapter, and **what state a turn is in**. Writes nothing down — the run's own account already records
  it, and a channel that kept a second copy would become the only place something existed.
- `src/rundesk/query.py` — the read-only answers a channel may ask for, composed for a surface to
  show: status, version, agents, skills, schedules, roles, help, and nothing that changes anything
  (R-CAD-17). Apart from `agent.py` because composing what somebody reads in a chat room is not what
  that module is for — its subject is a named identity, and none of `gateway`, `schedule`, `store`
  or `role_run` is needed to resolve one. It imports `agent`, so `agent` imports **it** lazily, from
  inside `_answering` where the `querying=` seam is built; a module-level import either way closes a
  cycle. Written for a narrow surface throughout: what is over gives way to what is happening.
- `src/rundesk/attachment.py` — what an answer declares for delivery, and whether it may be sent.
  A brain writes an absolute local Markdown link to mean "send this" (R-CH-31); this reads those out
  of what it wrote and decides, separately, whether one may leave the machine — that it stands where
  the agent works, that no component of the path is a link out of there, and that it is small enough
  (R-CH-18). Apart from `answering.py` because none of it is about who may be answered or what state
  a turn is in, which is that module's whole subject: this is a **security boundary** — containment,
  symlink refusal through held directory descriptors, and a size ceiling — and it is worth reading on
  its own. Holds no state and knows nothing of conversations, agents or turns.
- `src/rundesk/transcript.py` — the two files beside a run, and nothing else: what the brain itself
  printed (`logs/runs/<run>.jsonl`, whose path an adapter is handed, because you cannot give a shell script
  a database handle) and what it said went wrong (`.err`, an operating-system pipe). Both may be destroyed
  to reclaim space, so every line an adapter produced is a row as well — which is what makes deleting
  `logs/` cost an owner nothing they need.
- `src/rundesk/turn.py` — the only module that knows the three above exist: resolve, write down what was
  resolved, run the brain, write down what it said, keep where the conversation got to, write down how it
  ended. Nothing reaches a brain that the account does not show.
- `src/rundesk/activity.py` — atomic, runtime-only provider-turn identities. Keeps only source,
  conversation, PID, start time, and **the machine's own answer for when that process began**, so
  status and update safety can see work without seeing prompts. That last one is what makes a PID
  an identity: the machine reissues numbers, and reissues them from low ones first after a reboot,
  which is exactly when a record written before that reboot is read. Missing it keeps a row and
  mismatching it drops one, the same asymmetry `gateway._end_left_running` holds — and a probe that
  *could not answer* is neither, because `ps` reports nothing for a timeout or a failed fork.
  **A row this install could not fingerprint at all is kept for as long as its pid answers** — an
  accepted limit, not an oversight: such rows always have a live pid (a dead one is already taken by
  the liveness check), so dropping them deletes the record of a possibly-running turn rather than
  tidying up after a dead one. Sweeping them was tried and reverted; a provider orphaned by its
  gateway, and `rundesk ask` — which writes here from a standalone process holding no lock and having
  no gateway at all — both defeat any "the writer is proven gone" argument. The cost is that an
  update may wait on a turn that has ended. **`sweep()` is the only thing
  that removes what a killed turn left behind** — `ended` runs in the turn's own `finally`, which a
  SIGKILL never reaches — and a gateway calls it as it claims the name.
- `src/rundesk/skill.py` — the library of skills on this machine, and what makes one. Everything
  stands in `data/skills/`: required built-ins copied there by the install, catalog links, and an
  owner's own packages beside them. **A grant is a link in the agent's own `skills/`,
  not a record of one** — rundesk never loads a skill, so the only lever with force is what is
  standing there before the brain runs, and a rule in a config file would describe what rundesk
  placed while the brain read on. Knows nothing of any brain: where a skill is *presented* is each
  adapter's, told through `RUNDESK_SKILLS`.
- `src/rundesk/role.py` — a shared specialist definition an agent may hand work to, and what
  makes one usable. Two maintained files below `agents_home()/.roles/` — a description, a
  skill set, a posture and optionally the brain and model its runs use, plus the rules one
  execution follows — and everything else derived:
  the slug is the directory, the label is the slug read aloud, and the revision is a digest of
  the manifest, the rules and every resolved skill package, so nobody increments a version. A
  role naming no brain is absent from that digest rather than empty in it, so pinning one moves
  a revision and every role written before the field existed keeps the one it had. A
  shipped role is laid down where one is missing and **never over one that is there**: a
  role is what an owner writes their specialists as, not a thing a release keeps true.
- `src/rundesk/role_run.py` — one isolated specialist execution, from admission to expiry.
  Assembles a bundle of locked bytes under the agent's own directory and moves it into place
  whole, hands `turn.py` an execution context standing in the target project, and settles the
  root into exactly one review its named parent is owed. **Takes back what an adapter stood in
  that project on its way in**: every brain presents skills beside the directory it stands in,
  so a run that simply ended left a vendor directory in somebody's checkout holding links into
  a bundle swept a fortnight later. Vendor-neutral — it removes only a link resolving inside
  this run's own snapshot, and only a directory that removal emptied. **Knows nothing of channels or
  gateways**: what carries it and what tells its parent are `agent.playing`'s, handed to a
  gateway already made the way `agent.asking` already is. **Which brain carries it is settled
  when it is admitted** and written down, rather than resolved again by whatever picks it up:
  a run has to be able to say afterwards what it ran on, a role edited in between must not
  change that answer, and a resumption continues a provider session that is one brain's.
- `src/rundesk/catalog.py` — repository manifests, catalog provenance, and atomic installation,
  update, adoption, and removal below `data/catalogs/`. Exposes complete packages through links in
  the existing skill library; never imports or executes catalog content.
- `src/rundesk/script.py` — the owner's shared integration commands. Resolves the script
  library below the install's data and lists only runnable top-level entries; `process.py`
  puts that directory first on every program's `PATH`.
- `src/rundesk/backup.py` — copies of everything the owner keeps, and putting one back. Knows
  nothing of gateways or of the machine's supervisor: what must be true before a restore may
  proceed arrives as callables, the way `updater.run` already takes them. What goes into one is
  `data_home()` and nothing else — the program is what a release publishes, so a copy of it is a
  copy of something already downloadable. **Never copies a database**; it asks `store` for a
  consistent one, because a file copied under a live writer opens, looks healthy and is wrong.
- `src/rundesk/secret.py` — the values this install keeps, and hands to every program it
  starts. **One set for the whole install — there is no whose**, which is what makes an
  integration command find its credential without an owner having exported anything in a
  shell a gateway will never see. Two ways one is kept and it knows no others: **held**
  here in a file only its owner can read, or **fetched** by a command somebody else wrote,
  whose words are kept and run again each spawn so the value is never on this disk at all.
  Knows nothing of gateways, agents or channels: what a caller already has its own answer
  for arrives as `exclude`, and what runs a fetching command arrives as an argument, so the
  whole module is exercised with no vault and no keeper installed. **Nothing it exposes
  gives a whole value back** — a masked hint and a mark taken with a key of this install's
  answer "which one is this" and "did it change", and answer nothing else (R-SEC-4).
- `src/rundesk/config.py` — how this install is configured, as opposed to how any one agent is.
  One file under `data_home()`, sections at the top level, and the source of every effective
  install-wide value. The install writes it complete; an update adds values an older release
  never wrote without changing anything already stated. `skills.granted` is the required
  baseline reconciled onto every new and existing agent and protected from revocation while
  configured.
  Distinct from `settings`, which already means what one agent or channel was told.
- `src/rundesk/store.py` — everything one agent keeps, and **the only way in to it**. One database per
  agent, never one shared, so a turn's write is never in another agent's way. Reading and writing are told
  apart at the connection: a reader is opened read-only, so it cannot begin work that would make a turn
  wait — refused by the database rather than by convention. No statement is written anywhere else and no
  connection ever leaves the module, both proved by looking. Agent, gateway, turn, answering, backup and
  command paths all use this seam; none reaches around it to the database.
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
- `src/migrations/` — **the schema, and the only description of it there is.** `001.py` is the shape an
  agent starts from; every step after it changes that shape, and reading them in order is what the records
  are today. Making an agent runs the whole path from nothing rather than building tables directly, so it is
  exercised every time anybody adds an agent and a fresh install cannot drift from an upgraded one. A step
  that rebuilds a table something else references puts those references back itself: the runner opens every
  step with foreign keys on and cannot turn them off inside its own transaction, so dropping a table fires
  the actions pointing at it.
- `src/rundesk/updater.py` — where this install stands against what is published, and moving between
  them. Every network call is behind an argument, so the whole module is exercised offline. An update
  is **two tiers**: what rundesk is made of and what its agents keep both come forward, in that order,
  and either failing puts the release back and the records with it. What was replaced is kept aside
  until the whole thing is proved, which is the only way back there is. Once the files land the rest
  of the window is handed to the release that just landed, because a step is found on disk and would
  otherwise be run by the runner it replaced.
- `src/rundesk/update_worker.py` — the process **no gateway owns**, which is the only thing that may
  stop every gateway on a machine. Claims a durable request, waits for every turn to finish, stands the
  supervised gateways down, lets `updater.py` replace the files, and puts them back — plus the recovery
  a successor performs when one died mid-window, off the maintenance marker rather than off a guess.
  Entered as `rundesk update --worker` from the job `supervisor.describe_update_worker` writes; the
  surface only adapts what was typed and calls in here. Every collaborator is an argument, so the
  highest-consequence path in the product is exercised with no gateway and no supervisor near it.
- `src/rundesk/update_request.py` — the durable handoff from an agent turn to the
  supervisor-owned update worker: one request, its origin, lifecycle, final outcome, and delivery state,
  all changed under one lock and atomically replaced.
- `src/rundesk/restart_request.py` — one durable restart request per gateway: its safe
  origin, readiness, lifecycle, final outcome, and delivery state, owned outside the gateway it may cycle.
- `src/rundesk/dependencies.py` — what this install is made of beyond the standard library, and putting
  it there. One place decides what `requirements.txt` declares, what the virtualenv actually holds and
  how the second is made to satisfy the first — `install.sh` asked in shell and `gateway.fitness` asked
  in Python, and neither could see a version. **Imports nothing of rundesk's**: the installer calls it
  through a bare `python3` before there is a virtualenv, and an update calls it part-way through
  replacing every other module here. What runs a program is an argument, so pip never runs in the suite.
- `src/rundesk/process.py` — a program rundesk runs, and how it keeps hold of it: its own session so
  ending it ends the whole tree, silence rather than duration as the failure, output streamed and never
  accumulated. Knows nothing of gateways or agents, and holds no state of its own, so any number of
  programs run at once. Two ways of reading one, sharing every rule about when to stop: output **meant to
  be read** goes line by line to the caller as it always has, and output **meant to be parsed** goes as
  whole records through what is held for a receiver — kept apart from what the program says went wrong,
  written back to while it runs, and never split, so that a slow or failing receiver can neither hold up
  the program nor end it.
- `src/rundesk/durable.py` — a small file written whole, and changed under a lock nobody else holds.
  The primitive everything durable here is built on: a value renamed into place so a reader never sees
  half of one, and `changing()` holding the read, the decision and the write under one `flock`. **What
  cannot be read is not empty** — a missing file and an unreadable one are different answers, and
  writing an empty value back over the second is how state is lost. Imports nothing of rundesk's.
- `src/rundesk/welcome.py` — who a channel has already introduced this agent to, and who is still
  owed one (R-CH-33). One file in the channel's own home, and four questions asked of it. Apart from
  the gateway because none of it is a gateway's: the record belongs to a channel, and the command
  that adds or removes one writes here while nothing is running — which is why `commands/channels.py`
  was reaching through the gateway collaborator for it. **A mapping and not a list is the whole
  feature**: `changing` hands back the empty value for a file nobody wrote, so an empty list would
  make "this channel is new, greet everybody" and "this channel has greeted everybody" the same
  answer. A missing key is the third: a channel from before any of this, whose people must never be
  greeted. The gateway keeps the loop that walks its live surfaces and asks for the turn — that is
  gateway work and stays there; what is written down is here.
- `src/rundesk/gateway_log.py` — what a gateway is called, and the account it writes under that name.
  One concern rather than two: a name becomes the name of its lock, its record **and** its log, so what
  a name may be and where the writing lands are the same decision. History is kept apart from run
  state, which is cleared when a gateway goes (R-GW-18). **Everything written about an agent goes
  through `note()`** — a migration and the store included, which used to spell a filename of their
  own and so put every line about an agent's records where `rundesk logs <agent>` structurally
  could not reach it, and where nothing rotated it (R-STO-20). It also reads back what those
  releases left behind, from an agent's own log directory and never from the shared one, where
  that same name is the default gateway's own current account.
- `src/rundesk/recovery.py` — what a gateway never got to finish, left for whoever claims the name
  next. The only record that outlives the process, so it is kept beside the log rather than inside the
  run state it describes. The `Gateway` methods that *act* on it stay in that class: they are the
  second half of `claim()` and they write the clock's own state.
- `src/rundesk/gateway.py` — the part that stays running. One per name from the outset, since a
  gateway per agent is how one agent is cycled without disturbing the rest. Owns every program started
  through it, and proves it is alive with a lock the kernel drops when the process dies. Writes what
  happened to its own log, kept apart from its run state because history has to outlive the gateway.
- `src/rundesk/standing.py` — how a gateway stands, asked from above it: what one is doing, what
  gateways there are at all, and waiting for one to come up or go. Above the gateway rather than in it,
  because answering means putting a gateway together with the agent whose run directory it keeps, and a
  gateway never reaches for an agent. Below the surface rather than in it, because the update worker
  that stands every gateway on the machine down asks the same four questions. Every collaborator is an
  argument, so all four are exercised with no gateway and no supervisor near them.
- `src/rundesk/schedule.py` — work that starts itself: what a schedule is, when one is next due, and
  which are due now. Knows nothing of gateways or processes, and what a schedule names is carried without
  ever being read — so the day it names an agent rather than a command, nothing here changes. The time is
  an argument, so a year of firings is decided in a millisecond.
- `src/rundesk/supervisor.py` — handing a gateway to the machine that keeps it running: one job per
  gateway, and never one this install did not write. Every call out to the machine is an argument, so it
  is exercised on a machine with no supervisor at all.

## Frontend / UI

- No UI. The command line is the whole surface.

## Tests (tests/ — 33 files, ~2100 cases)

`unittest`, run directly (`python3 tests/test_cli.py`), never touching the network and never running a
provider. One file per contract, named for it:

| File | Cases | Covers |
|---|---|---|
| `test_gateway.py` | 264 | `platform-gateway` — real processes, real signals, waits turned down |
| `test_agent.py` | 142 | `agent-home` + `agent-gateway` — one scratch machine per case, no provider |
| `test_cli.py` | 325 | `command-surface` — walks every verb off the parser without reaching the owner's backups or uninstall, so one wired nowhere is caught |
| `test_catalog.py` | 27 | `lifecycle-skill-catalog` — manifests, provenance, default seeding, inert integration packages, lifecycle refresh, ownership, atomic updates, drift replacement, removal, and unsafe archives, all offline |
| `test_process.py` | 101 | `platform-process` — real process groups, grandchildren, drains and ceilings |
| `test_updater.py` | 81 | `lifecycle-update` — behind, current, could-not-ask; and an archive that cannot escape |
| `test_update_request.py` | 26 | `lifecycle-update` + queued restarts — durable external handoff, duplicate requests, safety waits, and outcome delivery |
| `test_update_worker.py` | 14 | `lifecycle-update` — the machine-wide stand-down and what a successor worker puts back, driven **without `cli.main`**: no surface fixture, no argparse, every collaborator a stand-in |
| `test_dependencies.py` | 28 | `lifecycle-update` — what the install is made of: what is declared, what the virtualenv holds, and building one **without pip ever running** |
| `test_install.py` | 82 | `lifecycle-install` — drives the real `install.sh` in a **copy** of the checkout, so the gate can be run twice |
| `test_supervisor.py` | 78 | the launchd job — a fake `launchctl`, so it runs where there is none |
| `test_schedule.py` | 49 | `platform-schedule` — pure time arithmetic, the clock passed in |
| `test_provider.py` | 41 | `provider-adapter` — **takes the adapter as an argument**; stand-ins it writes itself, so the gate needs no account, and one adapter in `strangers/` that this code never saw being written |
| `test_claude.py` | 65 | `provider-adapter` — the arithmetic and the postures one shipped brain decides on its own, driven against 184 captured lines rather than an account |
| `test_grok.py` | 35 | `provider-adapter` — a brain that reports no tools, and the two flags of its that are accepted and enforce nothing |
| `test_antigravity.py` | 18 | `provider-adapter` — piped prompt privacy, stream mapping, cumulative-resume usage, posture, skills and native-keyring environment, all offline |
| `test_turn.py` | 113 | `agent-run` — one whole turn, and `rundesk ask` end to end |
| `test_activity.py` | 3 | live-turn concurrency, safe persisted fields, and update visibility |
| `test_transcript.py` | 28 | `agent-run` — the account: append-only, clock-free, and what survives a pruning |
| `test_store.py` | 136 | `agent-store` — a database in a temp directory and nothing else: a reader that cannot write, two writers that cannot lose a change, two agents that never wait on each other, and the proof that no statement or connection escapes the one module |
| `test_channel.py` | 77 | `channel-adapter` — **takes the adapter as an argument**; stand-ins it writes itself, so the gate reaches no platform and needs no token, and one adapter in `strangers/` that this code never saw being written |
| `test_answering.py` | 146 | `channel-messaging` — both edges are arguments, so a routing failure and a platform failure can never be confused |
| `test_discord.py` | 208 | `channel-discord` — the policy and never the wire: who it answers, what a mark means, how a long answer is broken up, and which single message of a turn mentions anybody |
| `test_instructions.py` | 29 | Rundesk's core and trigger prompts, standard variables, the additive builder, the roles layer, and the separate role floor |
| `test_role.py` | 51 | `agent-role` — what a role is, what makes one usable, what its revision is computed from, and how the install's roles are offered, against a scratch library |
| `test_role_run.py` | 128 | `agent-role` — **takes the turn as an argument**, so what an execution is told, where it stands and what it is presented are asserted with no brain anywhere near it |
| `test_secret.py` | 39 | `platform-secrets` — what an install keeps for every program it starts: the refusals that are the boundary, the three answers a fetching command can give, and a scratch root that proves nothing reaches the owner's own |
| `test_ci.py` | 17 | the build topology — one PR run, bounded local and CI discovery, retained timeout diagnostics, process-tree cleanup, deterministic install catalogs, and the supported matrix |

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

- `install.sh` — puts `rundesk` on a PATH and takes it off again (`--uninstall [--purge]`). Installs into
  one directory holding rundesk and its `.venv`; from a checkout it symlinks that checkout instead, so
  development and installed use share one layout. Removing takes that directory entry by entry rather than
  whole, keeping what an owner made unless `--purge` asks for it. It changes nothing else a person owns —
  a `PATH` that does not reach the command is reported, never edited — and refuses to claim success until
  the installed command answers.
- `CLI.md` — every operation the command offers, how each is typed, and what each argument means.
  **Generated** by `.knowledge/scripts/cli-reference` from the parser, so it cannot describe a product
  nobody has; the gate fails when it and the command disagree.
- `src/templates/roles/` — **the roles this release ships.** Two files each, laid down where
  one of that name is missing and never over one an owner has: unlike a built-in skill, a role is
  what somebody writes their specialists as, and bringing one "forward" would rewrite what every future
  run of an edited role is allowed to do (R-ROL-18). Six so far, each for work heavy enough that
  an isolated run earns its cost: `development` implements a bounded change, `review` audits one
  it did not write, `testing` proves behaviour with production code read-only, `migration` sweeps
  one pattern across many sites, `research` answers a bounded question and `planning` returns an
  executable plan — the last two under a `read` posture, which on some brains has no shell in it
  at all. Each opens by naming the weight of work it is for, and all six use one section skeleton
  ending in a numbered definition of done, because that is what a parent reviews an unchecked
  report against (R-ROL-38). `managing-rundesk` carries how to write one.
- `src/templates/skills/` — **the required and remaining release-owned skills.** Copied into the
  owner's library by the install and brought forward by an update, so a built-in is always the version installed
  (R-AGT-30). `managing-rundesk` is how to operate rundesk, written for **an agent running inside
  it** — it was a document at the repository root that an agent had to be told to go and read,
  and the pointer named a path that existed on neither kind of install. As a skill it is handed
  to the agent instead. The operating baseline in `config.RUNDESK_REQUIRED_GRANTS` reaches every
  new and existing agent and cannot be configured away or revoked (R-AGT-36, R-AGT-37).
- `docs/extending/` — the adapter and integration guides, including `integration-clis/`, which
  is where building one is documented rather than in a skill every agent carries. They were built-in skills, laid down in
  every owner's library and granted to every agent, for a task almost none of them will ever do.
  A person building an adapter reads these against the repository; an agent does not need them in
  front of it on every turn (#95).
- `.knowledge/scripts/gate` — everything that has to be true before work here is finished, in one
  command. The suites are **found**, not listed, and it fails when CI stops delegating to the same
  discovery rule, so the local gate and CI cannot come apart. Runs everything rather than stopping at the first
  failure, and says what it did not cover: the real `./install.sh` and `--uninstall`.
- `.knowledge/scripts/ci-suites` — discovers every suite, balances six isolated shards from measured
  suite costs, and keeps one bounded log per suite so a timeout or failure still names what broke.
- `.github/workflows/build.yml` — one run per PR, with the full tests across macOS and Ubuntu on Python
  3.9 and 3.13, real checkout installs on both systems, the knowledge gate, retained suite logs, and one
  stable required check. Scheduled, release-tag, and manually requested canaries use separate concurrency.
- `.github/workflows/release.yml` — a `vX.Y.Z` tag publishes the release that `rundesk update` finds.

## Integrations / Jobs

- `GitHub Releases` — the only thing this reaches out to: the newest published tag, and the archive an
  update is fetched from.

## Docs

- `.knowledge/` — the knowledge system (prd/, prd-drafts/, research/, references/, guides/). See `.knowledge/README.md`.

---
*Editing this file? Follow the standard first: [`guides/docs-codemap.md`](./guides/docs-codemap.md).*
