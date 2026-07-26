# Roadmap — Agents to Provider-Controlled Channels

**Revised:** 2026-07-26, against the ✅/❌ columns in [`.knowledge/prd/`](.knowledge/prd/README.md), the
code, and a green `python3 .knowledge/scripts/gate` — not against this document's own prose, which had
drifted in four places.
**Released:** `v0.5.1`. **Status:** direction, not a ratified product contract — the contracts are.

**Starting implementation? Read this file's Direction, then [What Remains, In Order](#what-remains-in-order),
then the phase at the top of that table.** Phases 0–5 are done and compressed into
[What Is Already Built](#what-is-already-built); their contracts are ratified and are the truth about them,
not the summaries here. Then [`CLI.md`](CLI.md) for every operation as it is typed, and
[`.knowledge/guides/the-command-surface.md`](.knowledge/guides/the-command-surface.md) for why the surface is
shaped that way.

**The numbers ascend in the order the work happens**, and there are no gaps in them. They were labels once,
with seven landing before six and thirteen running next; that cost every reader the same reconciliation, so
they were renumbered in one pass. Phase 6 is where work stands today.

This roadmap gets Rundesk from a proven process/gateway/schedule substrate to named agents reached through
Discord, Slack, schedules and the terminal. It deliberately advances one testable concept at a time. The Node
Rundesk is evidence and prior art; it is not the architecture to port.

**The noun is `agent`.** Earlier drafts said "profile"; the settled word for the thing a person operates is
the agent, and *its home* is the directory of rules, memory, workspace and skills it loads.

## Direction

Build **agents first, then reach one through Discord**, and add skills and tools after that.

Agents come first because a channel needs a stable identity, workspace and knowledge boundary to route to.
Discord should not be used to discover whether agent isolation, provider invocation or session continuation
works — those are cheaper and more deterministic to prove locally.

The first useful vertical slice is:

```text
one agent -> one resolved binding -> one adapter -> one turn -> the terminal
```

The adapter in that line is a program Rundesk runs, not code it loads — which is what makes the same line
true when the brain is somebody's own CLI rather than one that ships here.

**The seam is opened with the first brain, not after several.** A contract generalised out of one vendor's
adapter is shaped like that vendor; the way to avoid it is to write the contract first and let the first
shipped adapter be its first customer, with a stranger's adapter proving the claim in the same phase.

**Skills, tools and customization come after**, because they are additive: an agent that loads a skill is a
better agent, not a different one, and nothing about the channel, the turn or the run record changes when
they land. Building them earlier spends the risk budget on the part that can be added safely at any time.

Do not build all providers, channels, tools and approval paths together.

## The Small Model

Five concepts are enough:

| Concept | Owns | Does not own |
|---|---|---|
| **Agent** | Name, its one gateway, its home, workspace, knowledge, skills and tool grants | A permanent provider, model or channel |
| **Binding** | One entry point's agent, provider, model and permission policy | Agent knowledge or provider session history |
| **Conversation** | One external thread or terminal conversation and its provider-native session handle | Global agent configuration |
| **Run** | One admitted occurrence, immutable resolved settings, native events and outcome | Future changes to its binding |
| **Adapter** | Running a brain and reporting what it did, in words no brain owns | The agent, the run, or anything about whose turn it is |

**One agent has one gateway**, made with the agent and taken away with it. Everything that reaches that agent
runs inside it: its channels are held open there and its schedules fire there, though the gateway may hold
several provider processes or turns, each with its own provider and model. So what a person operates is the
agent, and the gateway is how it runs rather than a second thing to keep track of.

For example, all four entry points below use the same agent's knowledge, inside that agent's one gateway:

| Entry point | Agent | Provider | Model |
|---|---|---|---|
| Discord `#operations` | `ava` | Claude | model selected for Discord |
| Slack `#planning` | `ava` | Codex | model selected for Slack |
| Schedule `morning-review` | `ava` | Codex | lower-cost scheduled model |
| Schedule `weekly-research` | `ava` | Grok | research model |

Provider and model are resolved when a run is admitted and written into that run's record. Changing a binding
affects new work. It must not silently change an active conversation or resume a session through a different
provider. Agent defaults may be a convenience fallback, but provider and model are not intrinsic agent
identity: an inbound chat message cannot change them, and only an authorized configuration change or an
authorized local invocation can.

## Boundaries to Keep

- Keep the provider's native conversation, context, tools, permissions and session loop intact. Rundesk
  invokes it, supplies its isolated environment, streams its native events, sends supported input and records
  outcomes. It does not reconstruct an agent loop.
- **Both seams are public, and an adapter is a program rather than a plugin.** Rundesk runs it and reads
  records from it; it never loads a stranger's code into the gateway that runs every other agent, and never
  requires an adapter to be written in Python. A brain or a surface nobody here has heard of is first-class
  rather than degraded.
- Preserve the native event record. Add only the small Rundesk envelope needed to correlate agent, binding,
  conversation, run and delivery. Do not invent a large common event vocabulary before two real consumers
  prove it is needed.
- Keep channel presentation out of provider adapters. A fake channel and Discord consume the same surface.
- Keep provider installations, adapters and private runtime homes outside an agent's home.
- Define agent isolation narrowly: separate automatic context/skill discovery, configuration, session history
  and default cwd. It is **not** an OS filesystem sandbox, and remote access must never be described as
  filesystem containment.
- Keep schedule time arithmetic unchanged. A schedule can name a binding or run request because its payload is
  intentionally opaque to the scheduler.
- Treat component ontology, persisted schemas and migrations as owner decisions before implementation.
- **A credential never arrives as a command-line argument, and never leaves in output.** Anything on a command
  line is readable through the process list and kept in shell history. A channel's token is read from an
  environment variable, from a file the owner already controls, or asked for on a terminal — and what shows a
  channel says a secret is present rather than what it is.
- **What an owner wrote is the owner's.** An update replaces what rundesk is made of and never what a person
  authored. Phase 9 is where that stops being true only by accident.

## How Every Phase Is Proved

Each phase ends with all of the following:

1. A narrow demo of only that phase's outcome.
2. Offline `unittest` coverage, including its failure paths.
3. Any new guaranteed behavior ratified in the appropriate PRD and tied to real tests.
4. Documentation, evidence checks and the repository gate green in the same supported environment.
5. Unknowns either answered by evidence or explicitly left outside the next phase's promise.

Provider and channel behavior need two separate test tracks:

- **Offline gate:** fake executables record `argv`, environment, cwd and stdin; saved native JSONL samples
  drive parser and replay tests; fake clocks and fake channels exercise routing and failure handling. No
  network and no provider login.
- **Manual probes:** small, rerunnable scripts exercise installed provider CLI versions and save sanitized
  samples. A provider version change reruns its probes before its conformance claim changes. Probe output is
  evidence, never a CI dependency.

Measure observable behavior. Prove two processes overlap by recording their start/end intervals; do not infer
concurrency from a quick elapsed time. Prove context loading with a canary and token counts; do not ask a
model what it believes was loaded.

**A ✅ is a claim about a test, not about the code.** `check-evidence` proves every ✅ names a test that
exists; it cannot prove that test fails when the code breaks. Break the code and watch the case fail, or the
row is unearned — this has cost this repository twice.

---

# What Is Already Built

Six phases are done. Each is one block here; the contracts are the truth about them, and
[`.knowledge/CODEMAP.md`](.knowledge/CODEMAP.md) is where the code is.

### 0 · A trustworthy gate, and the surface declared — **done**

One unambiguous green gate, and every operation the finished product will offer registered from the outset.

- The gate **finds** its suites rather than listing them, and fails when `build.yml` does not name one too —
  four ran in CI that the documented gate never named.
- A `Gateway` built without a root asked whether the *developer's checkout* fit the Python running it, which
  refused every named gateway on any machine that had run the installer while passing in CI. Suites now decide
  fitness in their own scratch root, and CI creates an empty `.venv`.
- Nobody runs rundesk under `.venv/bin/python`, which was all CI checked. CI now starts a real gateway through
  the installed command.
- A planned command exited `2`, and so does a typo. Planned now ends on `EX_UNAVAILABLE` and names a command
  that works (R-CMD-8, R-CMD-9, R-CMD-10).

**Contract:** [`command-surface`](.knowledge/prd/command-surface.md) — 10 ✅, 0 ❌.

### 1 · The agent is the thing you operate — **done**

`add` makes an agent and its one gateway; `remove` takes both. The gateway verbs changed subject from the
gateway to the agent, and `agents`, `agents show`, `doctor` and `status` read what an agent is.

**What was decided, and what it cost.** Everything of one agent's lives in **one directory** — its home, the
private homes providers are given, and the three its gateway keeps things in. That ended finding 19 by
construction rather than by guarding against it: a name can no longer claim a file belonging to another,
because there is no shared directory to claim it in.

- Finding 32 was answered as a usage error: a bare `stop` or `restart` refuses and touches nothing, and
  `--all` is how the fan-out is asked for.
- Finding 31 was answered by the grammar — the agent is a positional, and what to run is the words after `--`.
- Finding 33 was answered by `uninstall` running the installer's own removal and propagating what it returned.
- A schedule can be run by hand without moving when it next falls due (R-SCH-21, R-SCH-22).

**Contracts:** [`agent-home`](.knowledge/prd/agent-home.md) — 14 ✅, 1 ❌ ·
[`agent-gateway`](.knowledge/prd/agent-gateway.md) — 9 ✅, 2 ❌.

**Left open, deliberately:** running a schedule by hand happens in the terminal, not inside the agent's
gateway — there is still nothing to ask a running gateway with. Finding 28's larger half (a command reading a
supervised gateway's directories out of its own job) is not done; what this phase owed it is that the job
carries the agent's directories, so the two agree.

### 2 · The provider seam, and one brain behind it — **done**

**The seam is the deliverable. The adapter is the proof.** The contract was written first, the shipped adapter
was its first customer, and the phase did not end until an adapter Rundesk has never heard of carried a whole
turn.

```text
we run:     <provider>                      whatever the agent named — a shipped one, or a path
we set:     RUNDESK_CWD, RUNDESK_PROVIDER_HOME, RUNDESK_MODEL, RUNDESK_RUN
we send:    the prompt, on stdin
we read:    one JSON record per line on stdout — text · think · tool · result · usage · done
            anything else is kept in the run record, shown to nobody, and breaks nothing
we keep:    stderr, apart, as what went wrong rather than what happened
we end:     the adapter and everything it started
```

The vocabulary is closed. A seventh record is a contract change, deliberately — an open one puts every
vendor's words into every channel and every reader, which is the thing the seam exists to prevent. Being
closed is also what lets an adapter be ahead of us: an unknown record is preserved rather than refused.

**Three things, three lifetimes:** a run id is ours, a session handle is the provider's and opaque here, and
the resume ledger is keyed by **conversation and provider together** — keyed by conversation alone, changing
an agent's provider hands Claude's session to Codex, which is how the Node build's is keyed.

**The transcript is the data this is all for.** Every run writes what happened, append-only, ordered by a
monotonic sequence rather than a clock. Normalise once and keep the raw, so an upstream format change is
visible drift rather than a silent gap. **Nothing is sent that the transcript does not show** — injecting text
a human never wrote and leaving it out of the audit makes the audit a lie.

**What proves the seam open rather than merely designed open:** `tests/strangers/driftwood-adapter` was
written from [the guide](.knowledge/guides/write-a-provider-adapter.md) by an agent given the guide's text and
nothing else, is committed exactly as handed over, and passes the same conformance suite unchanged. That is
`R-PRV-2` — the one row that could not have been ticked from the inside. The claim was tested a second way by
accident: the shipped adapter was rewritten from `codex exec` to `codex app-server`, a different protocol, and
**one file changed**.

**Contract:** [`provider-adapter`](.knowledge/prd/provider-adapter.md) — 21 ✅, 2 ❌. Also delivered:
`rundesk ask <agent> "…"` streamed to the terminal, and `--steer`, which was not planned and is proved against
a real brain mid-turn.

### 3 · The channel seam, and Discord behind it — **done**

The same shape as Phase 2, deliberately — two swappable edges and one core that knows neither:

```text
  CHANNEL ADAPTERS                                    PROVIDER ADAPTERS
  discord  ─┐                                      ┌─ codex
  slack    ─┼──▶   the gateway  ──▶  a turn  ──▶───┤─ claude
  imessage ─┘      (knows neither edge)            └─ your own brain
```

- **The system decides the turn's lifecycle; an adapter only says how its platform shows it.** Seen, running,
  finished, stopped, failed. An adapter working that out for itself would be re-implementing the turn, and two
  adapters would disagree.
- **Work goes out early; prose does not.** What the agent *did* is shown as it happens; what it *says* is held
  and posted whole, because a reply that rewrites itself in place is unreadable. The line between them is
  whole records, never part-written ones — a rule of the seam, not of Discord.
- **A channel is held open by the agent's gateway**, not started per turn, and ends with it.
- **Adding a channel tests itself**: it connects, authenticates, verifies it can see what it was pointed at,
  and writes nothing if it cannot.
- **At least one allowed user is required, never defaulted.** An agent that answers whoever speaks to it, on a
  machine where it can run tools, is a misconfiguration and not a mode.
- **A channel is presentation and authorisation, and nothing else.** The phase needed a brain to be told where
  it was answering — a *provider* question — and the answer went into the provider seam as `RUNDESK_PREFACE`,
  not into Discord as a special case.

`tests/strangers/semaphore-channel` is the mirror of `driftwood`: written from
[the guide](.knowledge/guides/write-a-channel-adapter.md) alone and passing the conformance suite unchanged.
That is `R-CAD-2`.

**Contracts:** [`channel-adapter`](.knowledge/prd/channel-adapter.md) — 13 ✅, 2 ❌ ·
[`channel-messaging`](.knowledge/prd/channel-messaging.md) — 19 ✅, 3 ❌ ·
[`channel-discord`](.knowledge/prd/channel-discord.md) — 12 ✅, 9 ❌. The fourteen ❌ are honest and are
catalogued [below](#what-those-phases-left--on-purpose).

**Left open, deliberately:** the gateway announces itself once *per channel*, so two channels mean two notices
to the same person — the notice is about the gateway and wants deciding where it belongs. A second platform is
Phase 15, and reviewing for it surfaced four owner questions: what `direct` means where there is no such
thing, whether an adapter filters un-addressed messages in a busy room, how a conversation maps to a Slack
thread, and what dialect prose is in. Hermes ships a per-platform hint describing the medium itself; ours makes
the owner write both that and their own instructions.

### 4 · The shape of what is kept, and the way in — **done**

The one phase that could not discover its design while building it: the moment a release lands, the shape is on
somebody's disk and every mistake becomes a migration.

**Group by lifetime, not by kind** — that is the whole answer to the scatter:

| | Lives until | Who owns it | Cleared when an agent stops? |
|---|---|---|---|
| **the person's** | they delete it | the owner | never — `--purge` only |
| **records** | the agent is removed | rundesk | no — this is what migrates |
| **history** | retention says otherwise | rundesk | no — it must outlive the gateway |
| **running** | the agent stops | rundesk | **yes, always** |

- **One database per agent, never one shared.** Every agent has its own gateway process; a shared database
  puts one agent's write lock in another's way and makes one corrupt file everybody's problem.
- **One version per agent, and nothing at the top.** There is no install-wide state: the list of agents is the
  directories, found rather than listed. The version lives in `PRAGMA user_version` inside each `state.db`.
- **The line is who writes it, not how big it is.** Rundesk's records are rows; what the *brain* printed and
  what it said went wrong are files, because `RUNDESK_RAW` is a path handed to a program that may be a shell
  script, and you cannot hand `bash` a database handle.
- **The database is the history; the files are diagnostics and may be destroyed.** So the account must stand
  on its own — a run whose account says "see the raw file" is a run that will one day say nothing.
- **Searchable is a requirement, not a side effect** — FTS5 where the machine has it, `doctor` saying so where
  it does not, and the history still queryable by agent, conversation, run and time without it.
- **The migration is walked through on paper against a real install**, item for item. That walk found what the
  design had missed: a conversation key that is a *session handle* somebody passed to `--conversation`, which
  no migration written from the documentation would have expected.

**Contracts:** [`agent-store`](.knowledge/prd/agent-store.md) — 23 ✅, 1 ❌ ·
[`lifecycle-migration`](.knowledge/prd/lifecycle-migration.md) — 18 ✅, 0 ❌ ·
[`agent-run`](.knowledge/prd/agent-run.md) · [`agent-usage`](.knowledge/prd/agent-usage.md). The map from every
old reader to its replacement is [`moving-onto-the-store`](.knowledge/guides/moving-onto-the-store.md).

**What building rather than drawing found:** records older than the installed shape were read silently rather
than refused, and building a database released the lock between reading the version and acting on it, so two
commands arriving together told one that a healthy database had failed. Both only appear once something runs.

### 5 · Two more brains behind the seam — **done**

Claude Code and Grok each carry a whole turn, and **nothing in `src/rundesk/` changed to accommodate either**.
That was the point: a brain is a program, so adding one touches `src/providers/`, `tests/` and `.knowledge/`,
reads no durable state, and ran beside the storage move without waiting on it.

The closed vocabularies were enough — seven records, six verbs, five capabilities, two postures — and the two
brains land at opposite ends of the contract: claude answers `true` to four capabilities, grok to three, and a
turn on either is complete. Both pass `tests/test_provider.py --adapter src/providers/<brain>` unchanged, with
`--home` omitted entirely. Every case was proved by breaking the code and watching it fail — 24 probes.

**The design this phase got wrong first.** The adapters were built to relocate each brain's home onto
`RUNDESK_PROVIDER_HOME`, on the reading that a private home is what separates one agent from another. **It is
not, and forcing it broke Claude outright.** Both brains already file conversations under *the directory a turn
was run in*, and rundesk already stands every turn in its own agent's home — so the separation is had for free.
And `CLAUDE_CONFIG_DIR` does not *redirect* a login, it *removes* one. No shipped adapter relocates a brain's
home now, and a fresh agent answers on first ask with no sign-in step.

**Deliberately short:** `R-PRV-20` stays ❌. Grok reports no tool events at all, and the 184 captured lines of
claude contain no file-making tool, so the field a `Write` names its path in is unmeasured. Guessing a vendor's
field name is already in `MEMORY.md` as costing a whole feature silently.

### What those phases left ❌ on purpose

Twenty-eight rows across the contracts are ❌, and every one is honest. Grouped by what would earn it — which
is also the list of what the phases below have to pick up:

| Why it is ❌ | Rows | Earned by |
|---|---|---|
| Only a person watching a real platform can settle it | R-DIS-5, -6, -11, -12, -14, -15, -16, -18, -19; R-CH-16 | `.knowledge/scripts/probe-discord` says what to do and what to look for on each. Not ticked on a script's say-so |
| Needs a real connection held open and dropped at a chosen moment | R-AGW-3, R-CAD-6, R-CAD-7, R-CH-11 | Phase 11 |
| Nothing can prove what cannot be written | R-CH-2, R-RUN-13, R-RUN-15, R-USE-11, R-STO-19 | A case that *adds* the forbidden thing and watches it fail — see `MEMORY.md` on the guard that passed green through the commit that broke it |
| Waits on money, which nothing computes | R-USE-5, R-USE-8 | Nothing works a cost out from prices yet |
| Waits on a brain making a file, which nobody has captured | R-PRV-20 | Phase 10 |
| Waits on recovery, which is not built | R-GW-22, R-GW-24, R-SCH-20 | Phase 14 |
| Waits on a provider and a credential the suite has neither of | R-AGT-10 | Phase 12's canary |
| Inherited from what runs a program at all; no test of its own | R-PRV-13 | Phase 10 |
| **Possibly earnable today, and worth checking first** | R-AGW-9 | Channels are rows in `state.db` now and removing an agent takes its directory, so the behaviour may already be there with no row turned. Both `agent-gateway` rows carry no evidence at all |

---

# What Remains, In Order

| | Phase | What lands |
|---|---|---|
| **6** | Let the clock start work | The end-to-end proof: a schedule fires a *turn*, not just a program, and its outcome reaches a channel |
| **7** | Move everything onto it | The gateway's own three directories — the last readers of `~/.rundesk/{run,logs,schedules}` — carried by `002.py` |
| **8** | Updates an owner can trust | Dependencies move with the records, `update --check` says what it would do, and where every agent stands is a question with an answer |
| **9** | Templates an owner can make their own | The files a new agent is copied from become the owner's to override, one at a time, and survive an update |
| **10** | Provider adapters — audit the seam | A generic endpoint adapter, the decoupling test, and the contradictions settled |
| **11** | Channel adapters — audit the seam | The same, on the surfaces side |
| **12** | Skills a brain loads by itself | One skill, written once, discovered natively by every brain that has discovery — and a live probe proving each one sees it |
| **13** | Know what an agent was granted | Inventory, search and explain: what each brain reports it has, and what this agent has actually run |
| **14** | Questions, approvals, recovery | A brain pausing mid-turn for an answer, and surviving a restart while it waits |
| **15** | Channel breadth | Slack, needing no provider or agent change |

**Why this order.**

**Six proves the chain, so it goes first.** Fixing the clock exercises everything in one line — clock,
gateway, turn, brain, account, channel — so anything the storage move broke shows up there rather than later
and further from its cause.

**Seven finishes the oldest debt, and needs nothing built first.** The gateway move is the one change to the
on-disk shape that arrives *after* a release, so it is `002.py` rather than a free edit — but the machinery
that carries a step is already built and wired into the update (`cli.py:489`, R-MIG-1, R-MIG-6). It does not
wait on Phase 8: what Phase 8 adds is *dependency* movement, and moving the gateway's three directories adds
no dependency. It goes before everything after it because two coexisting layouts is the condition every later
phase would otherwise be built on top of.

**Eight comes next because releases are real now.** `v0.5.0` and `v0.5.1` are out, so there are installed
agents — and an update still replaces the source without touching what the source is made of. Until that is
fixed, every phase after it ships changes an owner cannot safely take.

**Nine comes straight after eight**, because its whole promise is that what an owner wrote survives an update.
Proving that before eight would be proving it against the mechanism eight is changing.

**Ten and eleven are audits, and they are phases** because three shipped adapters plus a stranger's is the
first point either seam can be judged rather than described. Their shared claim decides whether anybody else
can build here: **a feature is written against the contract, never against the adapter that shipped first.**
The test is the poorest possible adapter — declaring nothing, doing nothing — still getting every feature that
does not strictly require what it lacks.

**A resolver phase used to sit at step 3 and no longer does.** With no `bindings` verb there was no object
anyone creates, and its one durable artefact — the ledger saying which conversation continues which session —
cannot be built before a provider has reported a session handle. Its two real parts are now where they can be
proved: what a turn resolves is Phase 2, and four entry points reaching one agent is Phase 3.

---

## Phase 6 — Let the Clock Start Work

**Outcome:** an agent does work because the time came, through the same resolver, run record and provider
adapter that Discord and the terminal already use.

**This is the end-to-end proof, which is why it comes first.** A schedule already runs a *program*. What it
cannot do is run a *turn* — and making it work exercises the whole chain in one line: the clock fires, a
gateway admits a turn, a brain answers, the account records it, and the outcome reaches a channel. Anything
broken anywhere along that chain shows up here.

Most of the mechanism is already here: a schedule carries what it names without reading it (R-SCH-3), so a
schedule whose program is `rundesk ask ava "…"` is a scheduled turn — no new schema, no binding, nothing to
migrate. `ask --says` already exists so a scheduled turn can be given its own standing instructions.

### Where it stands

**Done.** Finding 22 is closed in the code: a gateway is handed where agents are kept and passes it on, so a
program it starts resolves the same root it does (`R-SCH-27`, `process.py:1136-1149`). The narrowing is
deliberate and worth recording — **only `RUNDESK_AGENTS_DIR` is passed, not the run, log and schedule
directories**, because everything of an agent's derives from that one root and the other three are on their
way out with Phase 7. Schedules are also examined as soon as a gateway has its name rather than an interval
later (`R-SCH-26`), and the ways work is admitted are a closed set of three — `terminal`, `channel`,
`schedule` — refused rather than written as free text (`store.py:85`).

**Not done.** Nothing can yet record a run as scheduled. `turn.py:187-188` sets a run's source to
`"channel" if asked_by else "terminal"` and never passes `schedule_id`, so a scheduled turn is
indistinguishable from one typed by hand, and the `schedule` source the store now declares is written by
nothing. Until that closes, deliverables 3 and 4 have nothing to assert, and finding 22 cannot honestly be
marked closed in [`SUGGESTIONS.md`](SUGGESTIONS.md) — it still reads **Open**.

### Deliverables

1. ~~`process.environment()` passes what a program needs to find the agents the gateway is running.~~ — done.
2. ~~A regression case: a program the gateway starts reads the same places the gateway does.~~ — done,
   `R-SCH-27`.
3. **A scheduled `rundesk ask <agent> "…"` that completes, records a run *as scheduled*, and can be read
   back** — the run carrying its `source` and its `schedule_id`, so `runs` can answer "what did the clock do
   last night" without inferring it from a timestamp.
4. **The outcome of a scheduled turn reaching the agent's channel where it has one.**
5. `R-SCH` rows for both, and the finding-22 entry closed in `SUGGESTIONS.md`.

### Nobody is watching, so the outcome has to go somewhere

This is the first trigger with no person at the other end, and Phase 3 is what makes that survivable: an agent
now has channels. A scheduled turn that failed at three in the morning should be readable where its owner
already looks, rather than only in a log nobody opens.

What that must not become is a channel deciding anything about schedules — a schedule that fires with no
channel configured still runs, still records, and is still reported through `schedules`.

### Tests

- `schedule A` and `schedule B` share one agent but resolve different provider/model selections.
- Existing never-late and never-overlap rules still hold.
- An interactive request in an autonomous schedule becomes a clear outcome instead of waiting forever.
- A schedule whose provider fails leaves one durable outcome that `schedules` reports, not silence.
- A scheduled turn's run says the clock started it, and names the schedule that did.
- A scheduled turn's outcome reaches the agent's channel where it has one.
- A scheduled turn on an agent with no channel still runs, records, and is reported by `schedules`.
- A scheduled turn is never the only thing that knew what happened.

### Exit proof

One scheduled run passes through the same resolver, run record and provider adapter that Discord and the
terminal already used — and its outcome is readable the next morning without a terminal having been open.

## Phase 7 — Move Everything Onto It

**Outcome:** what Phase 4 designed is what is on disk, and everything reads it through one seam.

This phase writes no new design and builds no new seam. Where the design turns out to be wrong, that is a
finding and the drafts move first, because the whole point of the phase before was that this one does not
improvise. Read [`moving-onto-the-store`](.knowledge/guides/moving-onto-the-store.md) first: it holds the map
from every remaining reader to the call that replaces it, and the traps already paid for.

### Where it stands

**Done.** Every JSON file an *agent* kept is gone and is rows: `agent.json`, `channels.json`, `sessions.json`
(and `session.py` with it), `runs/<run>.jsonl`, `.raw` and `allocating.json`. A run is numbered inside the
transaction that writes it. `transcript.py` is down to the two things that cannot be rows — what the brain
printed and what it said went wrong — and both stand under `logs/`, so deleting that directory costs an owner
nothing an account needed. `runs`, `usage` and `search` are built. The migration runner is wired into the
update, in the window `R-UPD-21` already opens. R-MIG-1, R-MIG-6, R-MIG-17 and R-MIG-18 are green; R-AGW-5 is
reversed, and removing an agent takes everything of its own.

**Not done — one move, not four.** The gateway still keeps what it is doing, what it wrote and what it is
scheduled to do in `run/`, `logs/` and `schedules/`. `gateway.py:162`, `:264` and `:354` each fall back to
`~/.rundesk/{logs,run,schedules}`, and `agent.resolved()` returns `Where(None, None, None)` for a name that is
not an agent (`agent.py:240-241`) — which is what silently sends every unknown name there. A gateway reading
its schedules from one place and its record from another is half-moved, so the four go together or not at all.

### What is left, in the order it is forced into

1. **`migrations/002.py`, written as a step.** `001.py` was edited freely while nothing was released; `v0.5.0`
   ended that, and an installed agent claims version 1. The gateway move is the first change to the shape that
   needs a step after it — and the first real customer of a runner that has so far only carried steps a test
   wrote.
2. **Move the gateway's three readers over**, together, with a regression check each.
3. **Delete the old layout and the code that defaulted to it**, including `agent.resolved()`'s empty answer.
4. **Prove it against a scratch install built for the purpose**, not the owner's own — by hand as well as by
   the suite. Driving it by hand is what found the two defects a green suite did not.

### The decision this phase still carries out

**Cross-agent stray sweeping is already dead, and this makes it permanent.** `_sweep_strays()` globs a
directory that holds exactly one record (`gateway.py:781`), so the loop body never runs for a per-agent
gateway. `R-GW-21` and `R-GW-23` are ✅ only because their tests share one `where`. Narrow both rows and stop
the tests sharing it, in the commit that deletes the shared directory. The cost is real and is accepted: work
left by an agent removed mid-run is never ended by anything.

### Tests

- Stopping an agent takes `gateway.json` and `gateway.lock` and touches nothing in `home/`, `logs/` or
  `state.db`.
- Nothing reads or writes `~/.rundesk/run`, `logs` or `schedules` any more, and a name that is not an agent
  gets an error rather than the old layout.
- No lock file sits anywhere a record does, and the ones a transaction replaced are gone rather than unused.
- A gateway's own log and what the machine caught before its logger existed are one file, and rotating it
  never leaves the machine writing into the rotated copy.
- Two agents' gateways writing at once never wait on each other.
- One kind of thing has exactly one home; the older layout is gone rather than merely unused.
- Data written by `v0.5.1` is readable by this one after an update, and says the new version.
- A migration runs once; an update that stopped halfway does not run it again; one that fails leaves every
  gateway down, the reason said, and the data as it was.
- No SQL appears outside the one module that owns it.

### Exit proof

`~/.rundesk/{run,logs,schedules}` is gone rather than merely unused, and one agent's log tells the whole story
of that agent. A phase that has moved the data but left one reader on the old layout has not moved the data.

**Retention is still unanswered**, and it is the other thing between this and done — how long an account is
kept, and whether an owner or a size decides. Phase 8 is where it is answered, because a copy kept until a
move is proved is the same question.

## Phase 8 — Updates an Owner Can Trust

**Outcome:** an owner on any released version can reach any later one and know, before they start, what it
will change and what it will move — and afterwards, that it moved. What an install is *made of* and what an
agent *keeps* both come forward, or neither does and nothing comes back up.

**Why it is a phase.** Phase 7 built one half and proved it: records move in the window an update already
stands every gateway down for, and a step that fails leaves them down and says which and why (R-MIG-1,
R-MIG-6). The other half is missing entirely, and the same window is where it belongs — `updater.py` contains
no mention of `pip`, `.venv` or `requirements`, so **an update replaces the source and never touches what it
is made of.**

Three things that costs today, in order of how quietly they happen:

| a release that | happens now |
|---|---|
| **adds** a dependency | it is not installed. `gateway.fitness()` catches it, so every gateway refuses to start — ending *well*, so nothing loops — with "what rundesk needs is not all there". An update that leaves every agent down until somebody notices and re-runs the installer |
| **bumps** a version | it is not upgraded, and `fitness()` asks only whether the name *imports*. A release needing a newer one runs against the old one and fails wherever the difference bites. **Nothing catches this** |
| **removes** one | it stays in the virtualenv for ever, and only removing rundesk clears it |

### Deliverables

1. **What an install is made of comes forward in the same window the records do.** Requirements are
   reinstalled after the files are replaced and before the first agent is brought back, with `pip check`
   after — installed is not the same as usable, and the installer already knows that (`install.sh:304`). A
   failure leaves every agent down and says so, exactly as a failed step does.
2. **Fitness asks what was declared, not only whether a name loads.** A version too old to satisfy
   `requirements.txt` is an install that does not fit, and today it reads as one that does.
3. **`update --check` says what it would do before it does it** — the version, the steps that would run
   against each agent, and what would be installed or upgraded. This answers
   [`lifecycle-migration`](.knowledge/prd/lifecycle-migration.md)'s open question about whether an owner may
   ask what a step would do before it does it.
4. **A full view of where every agent stands.** One command saying, per agent, the shape on disk, the shape
   installed, and what sits between them — so "which of my agents is behind" is a question with an answer
   rather than a database to open.
5. **What ran is readable after the fact.** Each agent's own log has it (R-STO-20, R-MIG-7); a command should
   say it, because an owner reading three logs to find out whether last night's update finished is an owner
   who will not.
6. **An update part-way through is resumable, and that is written down.** R-MIG-4 already makes running again
   safe; whether it may be *resumed* or must be re-run from the version on disk is answered rather than left.
7. **A copy of what was there, kept until the move is proved.** A step that fails leaves the data as it was
   (R-MIG-5), but a step that *succeeds* and is wrong has no way back, because going backwards is refusing to
   go forwards. **This is where retention meets it** — how long a copy is kept is the same question as how
   long an account is kept, and answering one settles the other.

### Tests

- A release that adds a dependency is installable and every gateway comes back.
- A release that bumps one leaves the install running the version it declared, not the one it had.
- An install whose virtualenv no longer satisfies what is declared does not fit, and says which.
- `update --check` names every step it would run and installs nothing.
- An update that cannot install what a release needs leaves every agent down and says why.
- An update interrupted between replacing the files and installing what they need is recoverable by running
  it again, and says what it found.
- Where every agent stands is answered without opening a database.
- A copy taken before records are moved is found afterwards, and something says when it may go.

### Exit proof

An install of `v0.5.1`, with agents, schedules, channels and history, reaches this one in one command: what it
is made of and what its agents keep both move, every gateway comes back, and the command said beforehand what
both of those would be. The same update run twice changes nothing the second time. An update made to fail at
each of its three points — the download, the dependencies, a step — leaves the agents down, the data as it
was, and a sentence naming which point and why.

## Phase 9 — Templates an Owner Can Make Their Own

**Outcome:** the files a new agent's home is copied from are the owner's to override — one at a time, any or
all — and what they wrote survives an update.

**Why it is a phase and not a flag.** Today the only place to customise what a new agent starts as is
`src/templates/agent/` (`agent.py:32`), which is **inside the install** — the directory an update replaces. So
the one place an owner can edit is the one place that does not survive. Editing an agent's own home afterwards
is a different thing entirely: it changes one agent, after the fact, and the next agent still starts from the
shipped words.

**What ships stays the factory set.** Five ordinary Markdown files — `AGENTS.md`, `CLAUDE.md`, `SOUL.md`,
`USER.md`, `MEMORY.md` — copied with one substitution (`{{name}}`, `agent.py:35`) and never text built in
code, because they are what an owner reads first and edits next. This phase does not change that; it puts a
second directory in front of it.

### What it must settle

**An override is per file, not per set.** An owner who wants their own `SOUL.md` and nothing else writes one
file, and the other four stay whatever the install ships — including whatever a later release improves them
into. Taking on all five means never getting an improvement to any of them, which is a choice worth being able
to avoid.

```text
~/.rundesk/templates/agent/
  SOUL.md              the owner's — used instead of the shipped one
  (nothing else)       the other four come from the install, and keep improving
```

**Where they live is the owner's tier**, above agents rather than inside any of them: they belong to the
person, are never touched by an update, and are not one agent's. That places them outside everything Phase 4
settled — there is deliberately no install-wide *records* state, and this is not records. **How it is
resolved is an owner decision**: derived from where agents are kept, or its own variable. `RUNDESK_HOME` is
not it — `MEMORY.md` already records that it does not redirect where agents live, and a second name that
half-works is worse than none.

**Does an override only replace, or may it add a file the install does not ship?** This is the decision the
phase turns on, and the recommendation is **replace only, at first**. What an agent's home holds is read off
the template directory rather than listed in code (`agent.py:41-50`), and the same list is what `doctor`
checks every agent against (`agent.py:531-533`). So a *new* name appearing in an override directory would
instantly report every agent ever made as "missing one of the files it loads" — a customization that
retroactively breaks the diagnosis of things it never touched. Adding is a second, explicit decision with its
own answer to that, not a side effect of allowing overrides.

**An override changes new agents, never existing ones.** `add` writes a page only when it is not already there
(`agent.py:303-304`), which is what makes running it again a repair rather than a reset. That stays true: an
owner who overrides a template and wants an existing agent to have it edits that agent's home, and rundesk
never rewrites words a person may have changed.

**`doctor` says where each file came from.** "Why does my new agent not have my rules" must be answerable
without reading source — per file, shipped or the owner's, and the path of the one that was used.

**An override that ignores `{{name}}` is still valid.** The substitution is the whole contract an override has
to honour, and honouring it is optional: a template with no placeholder is a template every agent gets
verbatim, which is a legitimate thing to want.

### Deliverables

1. Override resolution: per file, owner's directory first, install second, with the shipped set unchanged.
2. A way to start from the shipped words rather than from nothing — writing the factory set into the
   override directory to be edited, refusing to clobber what is already there.
3. `doctor` reporting, per file, whether it came from the install or the owner, and from where.
4. `R-AGT-n` rows in [`agent-home`](.knowledge/prd/agent-home.md) for override resolution and survival across
   an update; a [`command-surface`](.knowledge/prd/command-surface.md) row if a new verb lands, with `CLI.md`
   regenerated from the parser.
5. The owner's decisions recorded rather than assumed: where the directory lives and how it resolves; whether
   an override may add a name the install does not ship; and whether `install.sh --uninstall --purge` takes
   it — it is the person's, so the default answer is no.

### Tests

- A home made with no overrides is byte-for-byte what the install ships.
- One overridden file is the owner's and the rest are shipped, in the same home.
- An override that never writes `{{name}}` still makes a working agent.
- An override directory that is empty, unreadable, or holds a name the install does not ship is reported
  truthfully and never leaves a half-made agent.
- An update replaces the shipped templates and leaves every override untouched — the claim the phase exists
  for, and the reason it follows 13.
- An override added after an agent exists changes nothing in that agent's home.
- Making the same agent twice does not overwrite knowledge already edited in its home, with or without
  overrides.
- `doctor` names, per file, where it came from.
- **No suite reads the owner's real override directory.** This is a new external surface, and `MEMORY.md`
  already records what the same mistake one level down cost: a scratch run that redirected five variables
  still wrote real agents into `~/.rundesk/agents`, and reported success while doing it.

### Exit proof

An owner overrides one of the five files, makes an agent, and finds their words and four shipped ones in its
home. They update to a later release; their file is untouched and the other four are the new release's.
`doctor` says which is which without being asked twice.

## Phase 10 — Provider Adapters: Audit the Seam

**Outcome:** somebody who has never seen this code can write a brain — or point at an endpoint — and have it
work with every feature, and what rundesk keeps about a brain is stable enough to build on.

**Why an audit is a phase.** Three shipped adapters and a stranger's is the first point the seam can be judged
honestly rather than from one example. It is also the point where the promises made early are checked against
what shipped.

### Deliverables

1. **`src/providers/api`** — a generic endpoint adapter, so pointing rundesk at an OpenAI-compatible or custom
   HTTP brain is **configuration rather than code**. The roadmap already promises a self-hosted endpoint is
   reached the same way a shipped one is; today that is only true if you write a program.
2. **The decoupling test**: the poorest adapter imaginable — declaring `{}`, no tools, no usage, no model, no
   steering — still gets schedules, channels, history, search and `doctor`. Every feature works against the
   contract or degrades honestly, never against a shipped adapter.
3. **A live defect fixed**: `make` is a legal verb in `provider.DID` and in the guide, and the conformance
   suite's assertion omits it — so an adapter that emits it fails a suite it passes.
4. **Two contradictions settled**: the shipped Codex adapter ignores `RUNDESK_PROVIDER_HOME` against the
   guide's own advice, on measured grounds — either the guide moves or the adapter does. And a brain's
   identity is a fingerprint of its *file path*, so moving your program orphans its sessions.
5. `R-PRV-13`, `-20`, `-22` closed or narrowed to what is true. `R-PRV-20` needs a capture of a brain making a
   file — a live turn nobody has bought yet.
6. **A new stranger's adapter**, written from the guide alone by someone without the code — the same bar Phase
   2 set, re-run against a guide that has since changed.
7. `doctor` and `agents` show what each brain declared it can do, without starting one.
8. The guide's dead link fixed, and what an author is guaranteed across versions written down. In particular
   **what `RUNDESK_PROVIDER_HOME` is actually for**, now that no shipped adapter uses it for credentials while
   the guide still describes it as "config, credentials, session files".
9. **Something drives a shipped adapter into a `state.db` from a test.** All three were driven by hand and
   their accounts inspected — runs, records, usage, session handles and resume all correct — but the suite
   proves the seam-to-store path with stand-ins only.

## Phase 11 — Channel Adapters: Audit the Seam

**Outcome:** the same, on the other edge — a new surface hooks into every existing feature without touching
one of them.

### Deliverables

1. **The decoupling test**: the poorest surface there is — no threads, no reactions, no typing, no edits —
   carries a whole turn, and every feature either works on it or degrades honestly. Correctness never
   degrades; only fidelity does.
2. `R-AGW-3`, `R-CAD-6`, `R-CAD-7` and `R-CH-11` turned ✅ — held open by the gateway, reconnecting without a
   turn noticing, and leaving nothing running afterwards. All are proved by hand today and by nothing
   repeatable, and all need a real connection dropped at a chosen moment.
3. **A new stranger's channel adapter**, written from the guide alone.
4. What is kept for a channel audited and written down: the opaque adapter blob, the credential held as a
   *name* and never a value, and the per-channel directory an adapter owns.
5. A capability-versus-feature matrix in the contract, so an author knows what declaring nothing costs them.
6. **The gateway's announcement decided.** It fires once per channel, so two channels mean two notices to the
   same person. The notice is about the gateway; it wants a home rather than papering over.

## Phase 12 — Skills a Brain Loads by Itself

**Outcome:** an owner writes a skill once, in one format, and **every brain that agent reaches picks it up on
its own** — discovered natively by the provider rather than pasted into a prompt by rundesk — with a probe
proving each one actually sees it.

**One skill, written once. Provider-centric delivery.** The skill is universal: one `SKILL.md`, in the agent's
own `skills/`, with no vendor in it. What is *not* universal is where a brain looks, and no amount of wishing
makes it so — **no provider discovers a bare `skills/` directory** (`agent.py:141-151`). Probes of the
installed CLIs found each reads a directory of its own: `.claude/skills`, `.agents/skills`, `.grok/skills`.
So the same skill is *presented* to each brain where that brain already looks. One source, several
placements, and the owner writes one file.

**Auto-loading is the requirement, not a convenience.** Rundesk must not read a skill and inject its text
into the prompt. That would make every skill cost tokens on every turn whether or not it was relevant, put
rundesk in the business of deciding what is relevant, and — worst — make the audit lie, because `R-PRV-5`
requires everything added to a turn to appear in its account. The brain's own discovery is what this phase
delivers; if a brain has none, it has none, and that is reported rather than worked around.

### The seam question this phase must answer first

**A vendor's directory name may not appear above `src/providers/`.** That rule is what Phases 2, 5 and 10
exist to hold, so `.claude/skills` cannot be written into `src/rundesk/`. Making skills provider-centric
therefore requires the provider seam to carry *something* about them, which is a
[`provider-adapter`](.knowledge/prd/provider-adapter.md) contract change and an owner decision:

- **Recommended:** a `RUNDESK_SKILLS` variable pointing at the agent's `skills/`, handed over like
  `RUNDESK_CWD` and `RUNDESK_PREFACE` already are, with **the adapter** placing or linking them where its own
  brain looks. Every vendor path stays in the one file that already knows that vendor, a stranger's adapter
  gets skills the day it reads one variable, and rundesk learns nothing about anybody's layout.
- **The alternative** — an adapter *declaring* its discovery directory and rundesk doing the placement — puts
  the mechanism in the core and gives the core a per-vendor path to hold. Cheaper to write, and it is the
  shape the seam was built to prevent.

Either way it is a new row in the contract and a new line in
[`write-a-provider-adapter.md`](.knowledge/guides/write-a-provider-adapter.md), and the closed vocabularies
are not reopened: a skill is not a record, a verb or a capability.

### What is built

- **One `SKILL.md` format**, and a template an owner starts from. What a skill is, what it may assume, and
  what it may never contain — no credentials, no vendor flags.
- **One canonical place per agent**: `home/skills/`, which already exists and is already the agent's own.
- **Presentation to each shipped brain**, through whatever the seam decision above settles, for `codex`,
  `claude` and `grok` — and honestly absent for a brain that discovers nothing.
- **An agent does not inherit its owner's skills.** Rundesk-managed configuration must not turn on automatic
  discovery of ungranted owner-level skills; that is the isolation `R-AGT-8` and the Boundaries section
  already promise, one directory further in.
- **`doctor` says, per brain, whether skills are discoverable, not discoverable, or unproven on this version.**

### Probing — the part that decides whether any of this is true

**Nothing here is claimed from file presence.** A linked directory is evidence that a link exists, not that a
model read it. Each shipped brain gets a probe following `probe-codex`'s shape — an `--offline` half that
costs nothing, a live half, and a named verdict rather than numbers to squint at — and the probe is what
turns a row ✅.

The traps are already paid for and are in `.knowledge/MEMORY.md`; re-read them before writing one:

- **Do not test with a question the conversation can already answer.** A first attempt at a codex probe asked
  for a codename the thread had been asked for before, and the model answered from its own earlier reply. Use
  a fact only the skill can supply, and **run the control**: prove the same brain does *not* answer it when
  the skill is absent.
- **Make the canary unguessable per run.** Grok reads its other sessions — a probe passed once on
  cross-session recall alone, with the model saying so. Pass `--no-memory` and suffix the canary with a uuid,
  or a re-run reads the previous run's sessions.
- **A signed-in machine is required, and isolating a home logs the brain out.** `CLAUDE_CONFIG_DIR` does not
  redirect a login, it removes one, and claude reports `loggedIn: false` when `USER` is unset. A skills probe
  that quietly runs unauthenticated proves nothing.
- **Re-probe the installed versions.** Node-era findings suggested `.claude/skills/` and `.agents/skills/`;
  they are prior art, not a guarantee, and a version bump reruns the probe before the claim changes.

### Tests and probes

- Offline: scaffolding a skill twice changes nothing the second time; placement resolves to the right path
  per brain; an agent's skills are never another agent's.
- Offline: an adapter that discovers nothing still completes a turn, with the skill simply absent — the same
  claim Phase 10's decoupling test makes.
- Rundesk-managed config does not automatically discover ungranted owner-level skills.
- **A canary skill is read by each shipped brain**, proved live, with the control proving it is not read when
  absent — and saved, sanitized output recording provider version, invocation and result.
- A canary agent proves each provider follows `AGENTS.md` to `SOUL.md`, `USER.md` and `MEMORY.md` — which is
  `R-AGT-10`, ❌ today because a case needs a real provider and a credential the suite has neither of. This
  phase is where that row is earned or explicitly left.
- No vendor's skills directory appears outside its own adapter.

### Exit proof

One skill, written once by an owner, is picked up by every shipped brain that has discovery — proved by a
live canary and its control, not by a link existing. Each supported provider has a current row marked proven,
unsupported or unknown against a recorded version. **Rundesk does not claim that a provider loaded a rule or
a skill based only on file presence**, and a brain that discovers nothing is reported as such rather than
quietly given the text in its prompt.

## Phase 13 — Know What an Agent Was Granted

**Outcome:** an owner can see what tools an agent's brains actually have, and what this agent was granted,
without rundesk becoming a tool engine.

**Split from skills on purpose.** A skill is content an owner authors and a brain reads; a tool is a
capability the brain already has and a permission question about it. They travel together in most products
and share nothing here: skills need discovery probes, tools need the provider's own inventory, and merging
them is how a project ends up with a tool-execution loop nobody asked for.

**Inventory, search and explain. Nothing else.** The first kit does not duplicate provider-native file or
shell tools, does not dynamically load plugins, and does not execute arbitrary new actions. Rundesk does not
run tools — the brain does, inside its own permission model, which the Boundaries section requires be kept
intact.

What already exists to build on: an adapter declares what it can do, `tools` among them, and a turn's record
carries every `tool` and `result` the brain reported. So "what did this agent actually use" is a query
against the store rather than anything new to capture.

### Deliverables

1. **What each brain reports it has**, read through the seam and shown by `agents` and `doctor` without
   starting a turn.
2. **What this agent was granted**, if grants are to exist at all — and that is an owner decision, because a
   grant is persisted state and a permission claim rundesk cannot enforce. A posture is carried to the
   adapter today and no tool list is believed in; adding one that *looks* enforced would be worse than none.
3. **What an agent has actually run**, from the account: which tools, how often, in which runs.
4. A row saying plainly what a grant does and does not guarantee — it is not filesystem containment, and a
   provider's native tools may reach sibling paths unless a later phase adds and proves an enforcement
   boundary.

### Exit proof

An owner asks what a brain can do and what this agent has done with it, and gets an answer that came from the
adapter and the account rather than from a list rundesk keeps. Nothing claims a tool was prevented that was
not.

## Phase 14 — Questions, Approvals and Recovery

**Outcome:** a supported provider can pause for remote input without weakening its native permission model,
and Rundesk can recover truthfully after a gateway/channel restart.

Add one interaction type at a time: question, allow once, deny and cancel. Each pending interaction is a
single-use capability bound to the authorized user, provider request, conversation, run and expiry. Mismatches
and expiry deny by default.

Provider behavior is allowed to differ:

- a bidirectional protocol may stay live and receive the answer;
- a headless provider may defer, exit and resume its native session;
- an unsupported request must be reported as unsupported, never converted to blanket permission bypass.

`codex exec` cannot answer one mid-turn and `app-server` can; nothing uses that yet, and this is where it
belongs. **Steering is not an approval** — it already exists at the seam, and a brain declaring `steer: true`
taking words mid-turn says nothing about its permission model.

### Tests

- Duplicate, stale, wrong-user and wrong-conversation responses cannot act.
- Channel or gateway restart preserves enough correlation to answer or safely deny the pending request.
- A provider crash while waiting produces one durable outcome and does not restart the turn from scratch.
- Discord delivery failure does not lose the local pending/outcome record.
- Raw tool arguments/results remain local unless an explicit redaction/presentation rule allows them.

### Exit proof

A manual canary completes one question and one approval through Discord, then repeats each across the
supported restart boundary. The public always-online claim waits until interrupted work can resume rather than
restart and repeated crashes stop looping — `R-GW-22` and `R-GW-24`, both ❌ today because nothing records
where a piece of work had got to.

## Phase 15 — Add Channel Breadth One Adapter at a Time

**Outcome:** a second real surface — Slack — reuses the channel contract without changing the agent, the seam
or any provider.

The brains were done in Phase 5. This is the other edge, and the same claim: adding a surface is writing a
program against a published contract rather than extending a core. A Slack channel selects its provider and
model exactly as Discord and a schedule do; it does not add Slack fields to the agent.

Four questions Phase 3 surfaced and left for the owner are answered here: what `direct` means where there is
no such thing, whether an adapter should filter un-addressed messages in a busy room, how a conversation maps
to a Slack thread, and what dialect prose is in.

If adding one needs a change inside Rundesk, that is the finding — the seam was not open, and the change
belongs in the contract rather than in a special case for whichever platform exposed it.

### Exit proof

- One agent is exercised through at least two channels and two schedules with different provider and model
  selections, and unchanged agent knowledge.
- Adding the second real channel requires a wire and presentation adapter, and no provider or agent change at
  all.

## Explicitly Deferred

- Distributed workers or a general queue service.
- Dynamic provider/channel plugin loading.
- A Rundesk-built conversational or tool-execution loop.
- Automatic cross-provider conversation migration.
- A rich common event taxonomy before real adapters require it.
- Arbitrary remote changes to provider, model, permissions or tool grants.
- Executing every discovered tool before inventory, grants and one provider turn are proven.
- A budget that throttles or stops an agent that has cost too much. Recording comes first, so a cap is set
  against history rather than a guess — and a wrong reading stops a working agent.
- Reading a run back from the command line beyond `runs`, `usage` and `search`.

## Evidence Used

- The command as it stands and as it will be typed: [`CLI.md`](CLI.md), generated from the parser, and
  [`.knowledge/guides/the-command-surface.md`](.knowledge/guides/the-command-surface.md) for the rules it
  obeys and the overlaps already removed from it.
- Live Python contracts and structure: [`.knowledge/BRIEF.md`](.knowledge/BRIEF.md),
  [`.knowledge/CODEMAP.md`](.knowledge/CODEMAP.md), and [`.knowledge/prd/`](.knowledge/prd/README.md) — the
  ✅/❌ columns there, not the prose here, are the truth about what is proved.
- Current review ledger: [`SUGGESTIONS.md`](SUGGESTIONS.md)
- Current provider/channel research:
  [`.knowledge/research/2026-07-25-provider-cli-discord-interaction.md`](.knowledge/research/2026-07-25-provider-cli-discord-interaction.md)
- Node reference evidence: `../rundesk/docs/`, `../rundesk/probes/` and `../rundesk/test/`
