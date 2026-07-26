# Roadmap — Agents to Provider-Controlled Channels

**Planning baseline:** `1046f3f` on 2026-07-25  
**Status:** Direction, not a ratified product contract

**Starting implementation? Read in this order:** this file's Direction and **Phase 4**, which is next and
settles the design **and builds the seam it is all reached through**, while touching nothing anybody owns —
Phase 5 is what moves real data. Then walk what is actually
on disk before believing any description of it: `agents/<name>/` and `~/.rundesk/`, because two layouts
currently coexist and ending that is the first thing Phase 5 does. Then
[`CLI.md`](CLI.md) for every operation as it is typed, and
[`.knowledge/guides/the-command-surface.md`](.knowledge/guides/the-command-surface.md) for why the surface
is shaped that way. Phases 0 to 3 are done and their contracts are ratified in
[`.knowledge/prd/`](.knowledge/prd/README.md) — read the ones you are about to change the storage of:
`agent-home`, `agent-run`, `agent-usage`, `platform-schedule`, `channel-messaging`.

This roadmap gets Rundesk from a proven process/gateway/schedule substrate to named agents that can be
reached through Discord, Slack, schedules and the terminal. It deliberately advances one testable
concept at a time. The Node Rundesk is evidence and prior art; it is not the architecture to port.

**The noun is `agent`.** Earlier drafts of this roadmap said "profile"; the settled word for the thing a
person operates is the agent, and *its home* is the directory of rules, memory, workspace and skills it
loads. Where "profile" survives below, read "agent". `agent-` is a declared component sitting above
`platform-` — so an agent knows which gateway runs it, and a gateway knows nothing of whose work it
holds. Its drafts are `agent-home` (`R-AGT-n`) for what an agent is and loads, and `agent-gateway`
(`R-AGW-n`) for the one gateway it runs in.

## Direction

Build **agents first, then reach one through Discord**, and add skills and tools after that.

Agents come first because a channel needs a stable identity, workspace and knowledge boundary to route
to. Discord should not be used to discover whether agent isolation, provider invocation or session
continuation works — those are cheaper and more deterministic to prove locally.

The first useful vertical slice is:

```text
one agent -> one resolved binding -> one adapter -> one turn -> the terminal
```

The adapter in that line is a program Rundesk runs, not code it loads — which is what makes the same
line true when the brain is somebody's own CLI rather than one that ships here.

**Discord comes next, not last.** A remote channel is the thing this product is for, and until one
carries a real turn, everything before it is proved only against fakes and the owner's own terminal. So
the order is: the agent, the smallest resolution that lets a source pick a provider, one provider turn
to have a brain at all, and then Discord — with the fake channel as its offline half rather than as a
phase of its own.

**The seam is opened with the first brain, not after several.** A contract generalised out of one
vendor's adapter is shaped like that vendor; the way to avoid it is to write the contract first and let
the first shipped adapter be its first customer, with a stranger's adapter proving the claim in the same
phase. That is why Phase 2 does not end when one provider works.

**Skills and tools come after**, because they are additive: an agent that loads a skill is a better
agent, not a different one, and nothing about the channel, the turn or the run record changes when they
land. Building them earlier spends the risk budget on the part that can be added safely at any time.

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

**One agent has one gateway**, made with the agent and taken away with it. Everything that reaches that
agent runs inside it: its channels are held open there and its schedules fire there, though the gateway
may hold several provider processes or turns, each with its own provider and model. So what a person operates
is the agent, and the gateway is how it runs rather than a second thing to keep track of. The provider
CLI remains the agent brain.

For example, all four entry points below use the same agent's knowledge, inside that agent's one gateway:

| Entry point | Agent | Provider | Model |
|---|---|---|---|
| Discord `#operations` | `ava` | Claude | model selected for Discord |
| Slack `#planning` | `ava` | Codex | model selected for Slack |
| Schedule `morning-review` | `ava` | Codex | lower-cost scheduled model |
| Schedule `weekly-research` | `ava` | Grok | research model |

Provider and model are resolved when a run is admitted and written into that run's record. Changing a
binding affects new work. It must not silently change an active conversation or resume a session through
a different provider. A provider change starts a new provider session unless a future, explicitly tested
migration says otherwise.

Agent defaults may be a convenience fallback, but provider and model are not intrinsic agent identity.
An inbound chat message cannot change them; only an authorized binding/configuration change or an
authorized local invocation can.

## Boundaries to Keep

- Keep the provider's native conversation, context, tools, permissions and session loop intact. Rundesk
  invokes it, supplies its isolated environment, streams its native events, sends supported input and
  records outcomes. It does not reconstruct an agent loop.
- **The seam a brain is reached through is public, and an adapter is a program rather than a plugin.**
  Rundesk runs it and reads records from it; it never loads a stranger's code into the gateway that runs
  every other agent, and never requires an adapter to be written in Python. A brain nobody here has
  heard of — a self-hosted endpoint, somebody's own conversational CLI — is reached the same way a
  shipped one is, and is a first-class brain rather than a degraded one.
- Preserve the native event record. Add only the small Rundesk envelope needed to correlate agent,
  binding, conversation, run and delivery. Do not invent a large common event vocabulary before two real
  consumers prove it is needed.
- Keep channel presentation out of provider adapters. A fake channel and Discord should consume the same
  provider/run surface.
- Keep provider installations, adapters and private runtime homes outside an agent's home. Rundesk may
  associate an isolated runtime home with an agent/provider pair, but that managed state is not the agent's
  knowledge and does not make the provider part of the agent.
- Define agent isolation narrowly in the first release: separate automatic context/skill discovery,
  configuration, session history and default cwd. It is not an OS filesystem sandbox. A provider's native
  file or shell tools may reach sibling or owner paths unless a later phase adds and proves an enforcement
  boundary; remote access must never be described as filesystem containment.
- Keep schedule time arithmetic unchanged. A schedule can eventually name a binding or run request
  because its current payload is intentionally opaque to the scheduler.
- Keep persistence small and file-based until measured behavior requires something else. A run ID and
  minimal routing/session records do not require a database.
- Treat component ontology, persisted schemas and migrations as owner decisions before implementation.
  `agent-` and `channel-` are now declared; this roadmap does not add or ratify `provider-`.
- **A credential never arrives as a command-line argument, and never leaves in output.** Anything on a
  command line is readable through the process list and kept in shell history. A channel's token is read
  from an environment variable, from a file the owner already controls, or asked for on a terminal — and
  what shows a channel says a secret is present rather than what it is.

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
  samples. A provider version change reruns its probes before its conformance claim changes. Probe output
  is evidence, never a CI dependency.

Measure observable behavior. For example, prove two processes overlap by recording their start/end
intervals; do not infer concurrency from a quick elapsed time. Prove context loading with a canary and
token counts; do not ask a model what it believes was loaded.

## Phase 0 — Restore a Trustworthy Gate and Declare the Surface — **done**

**Outcome:** the substrate has one unambiguous green gate, and the owner has approved how the next
concepts appear in the product. No agent or channel behavior was added.

### 0A. Make the gate truthful — done

The gate meant three things. A `Gateway` built without a root asked whether the *developer's checkout*
fit the Python running it, so with `discord.py` declared, every case that claimed a name refused on any
machine that had run the installer — 8 failures and 88 errors — and passed in CI, which has no `.venv`.
The suites now decide fitness in their own scratch root, and CI creates an empty `.venv` so a runner is
the machine a developer has. `discord.py` stays declared and pinned: the channel needs a websocket
client the standard library does not have.

A second gap mattered more for consumers. Nobody runs rundesk under `.venv/bin/python`, which is all CI
ever checked — the command is `#!/usr/bin/env python3` and puts the virtualenv's packages on the path
itself. That hand-off was unproven, and breaking it would have refused every installed gateway while the
gate stayed green. CI now starts a real gateway through the installed command.

`.knowledge/scripts/gate` is the one command, and it **finds** the suites rather than listing them: four
ran in CI that the documented gate never named. It fails when the workflow does not name one too.

### 0B. Declare the concepts and their command surface — done

`agent-` is a declared component above `platform-`, and `.knowledge/prd-drafts/agent-home.md` states what
an agent is, what its home holds, how far apart two of them are kept, and what isolation deliberately is
not. Every operation the product will offer is registered and refuses truthfully — `add`, `agents`,
`ask`, `channels`, `doctor` and `runs`, each with its actions described where it is listed — and
[`CLI.md`](CLI.md) states every one of them, generated from the parser so it cannot describe a product
nobody has. There is no `bindings` verb: which provider answers is an option where the entry point is
made, so reaching an agent from Discord is one command and not two.

A planned command exited `2`, and so does a typo — two situations wanting opposite things done about
them. Planned now ends on `EX_UNAVAILABLE`, says which part of it is missing, and names a command that
works (R-CMD-8, R-CMD-9, R-CMD-10).

### Exit proof — met

- The documented local command and CI run the same list under the same assumptions, and pass from a clean
  checkout with or without a `.venv`.
- The owner-approved ontology, persisted boundaries and complete planned CLI surface are recorded.
- Existing process, gateway and schedule contracts remain green.

### Left open, deliberately

- Findings 32 and 33 — `stop`/`restart` fanning out with no scope, and `uninstall` being an instruction
  page that exits zero. Both change built verbs and were kept out of a declaration phase.
- Finding 31 — `schedules add --run` swallowing later options. Nothing new was added to that grammar
  because of it.

## Phase 1 — Make the Agent the Thing You Operate — **done**

**Outcome:** Rundesk creates, lists and diagnoses an isolated agent, and the command surface operates
agents rather than gateways — without a provider being run.

This phase is **two halves that must land together**, because either alone leaves the product incoherent:
an agent nobody can start, or a gateway that still has to be managed by hand beside its agent.

### 1A. The agent and its home

`agents add` makes an agent's home; `agents`, `agents show` and `doctor` read it. Exact syntax and
persisted layout are decided in the draft PRD before implementation, and `.knowledge/prd-drafts/agent-home.md`
and `agent-gateway.md` are ratified as part of this phase rather than before it — their rows are what
these tests prove.

An agent's home should contain:

```text
<agent>/
  AGENTS.md
  CLAUDE.md
  SOUL.md
  USER.md
  MEMORY.md
  workspace/
  skills/
```

This is a conceptual layout, not a ratified path schema. `AGENTS.md` is the canonical rule router.
`CLAUDE.md` is a small provider bootstrap that routes Claude to the same rules; it is not a second set of
agent knowledge. `SOUL.md`, `USER.md` and `MEMORY.md` are loaded through that routing rather than
assuming each provider recognizes those filenames.

Rundesk-managed provider homes are outside an agent's home and isolated by agent/provider pair.
Authentication sharing or isolation is a separate, explicit decision: probes already show that
config/home variables affect discovery and credentials, so Rundesk must never accidentally expose the
owner's global skills or history through automatic discovery.

An agent's knowledge must also have an explicit lifecycle. It must live outside removable install files
or be preserved by ordinary uninstall, with deletion limited to a separately authorized purge. Agent
names must not collide with gateway history sidecars or reserved suffixes.

Before a supervised agent is considered isolated, local commands and its launchd job must resolve the
same authoritative state and agent directories. These entry risks are currently recorded by findings
18–19, 22 and 28; reproduce them on the implementation baseline rather than copying a suggested fix.

### 1B. The CLI operates agents, and gateways are how they run

Today the gateway is the subject of `start`, `stop`, `restart`, `remove`, `status`, `logs` and
`schedules --gateway`. It becomes the mechanism, and the agent becomes the subject.

**One rule: the verb says what, and the next word says whose.** A verb with only one possible object at
this level needs no noun in front of it — there is one thing to `add`, `remove`, `start` or `stop`, and
it is an agent. A nested `add` stays qualified by its group, so `schedules ava add` is a schedule.

```sh
rundesk add ava                    make ava, and the one gateway that runs it
rundesk remove ava                 take both away
rundesk agents                     every agent, and what each is doing
rundesk agents ava                 what ava is, and where it keeps things
rundesk doctor ava                 what stands between ava and a working turn

rundesk start ava                  already ships — subject becomes the agent
rundesk start ava --here           …in this terminal instead     (was: serve ava)
rundesk stop ava
rundesk restart ava
rundesk logs ava

rundesk ask ava "…"                one turn, streamed here
rundesk schedules ava              what ava runs on its own       (was --gateway ava)
rundesk schedules ava add tidy --when <cron> -- /bin/tidy
rundesk schedules ava remove tidy  take it away
rundesk schedules ava on|off tidy  keep it, but stop it running
rundesk schedules ava run tidy     run it now, due or not
rundesk channels ava               what ava is reachable on
rundesk channels ava add ops --kind discord --server <id> --provider claude
rundesk runs ava                   what ava has run
rundesk runs ava show <run> [--stream]
rundesk runs ava resume|stop <run>

rundesk status                     how rundesk itself is — not a list of agents
```

Every operation as it will be typed is in [`CLI.md`](CLI.md), generated from the parser. *Why* the
surface is shaped this way — and which overlaps were removed to get there — is
[`.knowledge/guides/the-command-surface.md`](.knowledge/guides/the-command-surface.md).

- `add` makes the agent **and its one gateway**; `remove` takes both. There is no separate step, and no
  way to end up with one without the other.
- `remove` stops being gateway-specific and becomes the agent's — the gateway goes because its agent did.
  The verb does not move, so nothing that ships today is renamed.
- **`remove` takes the agent's schedules and channels with it** (R-AGW-4). Otherwise adding the name back
  inherits work nobody asked for, from an agent that no longer exists. What the agent *did* is kept until
  a removal is explicitly asked to take that too (R-AGW-5), which is the `--purge` that already ships.
- `--gateway <name>` becomes a positional, which also takes it out of the option list that `--run`'s
  remainder currently swallows (finding 31).
- **A schedule can be run by hand** — `schedules <agent> run <schedule>` — whether or not it is due, and
  doing so does not move when it next falls due on its own (R-SCH-21, R-SCH-22).
- The default gateway that exists today under no agent's name is reconciled: either it gains an agent or
  it is named as legacy. **This is a persisted-state decision and an owner call before implementation.**
- `channels` stays **registered and refusing** through this phase. Its shape is settled in Phase 3, which
  is where a channel is worth having, and nothing here builds one.

The dependency runs **agents → gateways and never the reverse**: `cli` → `agent` → `gateway` → `process`.
An agent knows which gateway runs it; a gateway goes on knowing nothing of whose work it holds, which is
what keeps the two testable apart while the command surface operates them as one thing.

### Tests

- Refuse names and symlinks that escape where agents are kept.
- Refuse names that collide with reserved state or history filenames.
- Make the same agent twice without overwriting knowledge already edited in its home.
- Prove two agents have different workspace and provider-home paths.
- Prove an agent's gateway is made with it, and goes with it.
- Prove no command leaves an agent without its gateway, or a gateway without its agent.
- Prove a schedule run by hand runs, and leaves the time it next falls due where it was.
- Prove the gateway receives the same resolved agent paths when supervised as when run locally.
- Prove ordinary uninstall and update preserve an agent's knowledge, workspace, channels and history.
- Prove `doctor` detects missing files, broken links, unusable provider homes and an unfit runtime without
  starting a provider or changing state.
- Prove the gateway module still passes its own contract with no agent anywhere near it.
- Prove `status` answers for rundesk itself and lists no agents, and that `agents` lists them with state.
- Prove `start <agent> --here` runs it in this terminal, and that a job written before this still starts.
- Prove `schedules <agent>` reaches the same schedules `--gateway <agent>` used to, and that an option
  typed after the program is no longer swallowed by it.
- Prove `uninstall` removes rundesk and reports failure when it could not, rather than exiting zero.
- Prove every operation `CLI.md` lists is answered, and that `CLI.md` still matches the command.

### Order of work

Either half alone leaves the product incoherent, so both land together — but not in one commit:

1. The agent and its home, with no command touching it yet: the module, its paths, its refusals.
2. `add` and `remove`, which is the first point a gateway is made and taken away by an agent's name.
3. The gateway verbs change subject, one at a time, each with its own regression check.
4. `status` splits from `agents`; `serve` folds into `start --here`; `stop --remove` goes.
5. `schedules` moves its agent to a positional and gains `run`.
6. `uninstall` stops being an instruction page.
7. Ratify `agent-home.md` and `agent-gateway.md` into `prd/`, glyphs set by what now passes.

### What this closes

Findings **31** (`--run` swallowing later options, fixed by the positional), **33** (`uninstall`
exiting zero), and the parts of **18**, **19**, **22** and **28** that concern where an agent's things
live and whether a supervised one resolves them the same way. Finding **32** — a bare `stop` or
`restart` fanning out to everything — **is a decision this phase must make**: with agents, does a bare
`stop` mean every agent, or is it a usage error? The surface says a verb's next word says whose, and
leaving it out currently means all of them, silently.

### Exit proof — met

A fresh agent is created, inspected, started, stopped and diagnosed entirely offline, and every one of
those is typed against the agent's name rather than a gateway's. Agent management cannot resolve one
agent's owned paths as another's. Provider filesystem containment is explicitly deferred; this phase
proves only separate discovery, configuration, session and cwd defaults.

**What was decided, and what it cost.** Everything of one agent's lives in one directory — its home, the
private homes providers are given, and the three its gateway keeps things in. That ended finding 19 by
construction rather than by guarding against it: a name can no longer claim a file belonging to another,
because there is no shared directory to claim it in. The three directories from before agents are kept and
read, so a gateway running since then goes on working and is adopted only when its owner asks.

Finding 32 was answered as a usage error: a bare `stop` or `restart` refuses and touches nothing, and
`--all` is how the fan-out is asked for. Finding 31 was answered by the grammar — the agent is a
positional, so nothing can swallow it, and what to run is the words after `--`, so an option typed there
is refused rather than handed to the program. Finding 33 was answered by `uninstall` running the
installer's own removal and propagating what it returned.

`agent-home` and `agent-gateway` are ratified. Two rows in them are ❌ on purpose: an agent loading its own
home rather than its owner's cannot be shown without a provider, and channels do not exist yet. Both are
what the phases after this are for.

### Left open, deliberately

- Which files each provider actually loads is inherited from probes of the build this replaces, not
  re-proven against installed versions. Phase 2 re-probes before anything claims it.
- Finding 28's larger half — a command reading a supervised gateway's directories out of its own job —
  is not done. What this phase owed it is: the job carries the agent's directories, so the two agree.
- Running a schedule by hand happens in the terminal, not inside the agent's gateway. There is nothing to
  ask a running gateway with, and inventing one was not this phase's work.

## Phase 2 — Open the Provider Seam, and Put One Brain Behind It — **done**

**Outcome:** one agent completes and resumes a turn through an adapter — and a second adapter, written
by somebody who has never seen this code, does the same with nothing here changed.

**The seam is the deliverable. The adapter is the proof.** Building one provider and generalising later
is how a seam ends up shaped like whichever vendor happened to be first; every leaked flag, session file
and permission mode then has to be pulled back out of the core. So the contract is written first, the
shipped adapter is written against it, and the phase does not end until an adapter Rundesk has never
heard of carries a whole turn.

**An adapter is a program, not a plugin.** Rundesk runs it, tells it where to work through the
environment, reads whole records from its stdout, and ends it. It never loads a stranger's code into the
gateway that runs every other agent, and an adapter can be written in any language — a shell script is
enough. This is what "Rundesk is a process hub" means concretely: the conversational loop is the
adapter's, always, including for the ones that ship here.

The contract is drafted in `provider-adapter` (`R-PRV-n`) and written for a stranger in
[`.knowledge/guides/write-a-provider-adapter.md`](.knowledge/guides/write-a-provider-adapter.md).
Its shape:

```text
we run:     <provider>                      whatever the agent named — a shipped one, or a path
we set:     RUNDESK_CWD, RUNDESK_PROVIDER_HOME, RUNDESK_MODEL, RUNDESK_RUN
we send:    the prompt, on stdin
we read:    one JSON record per line on stdout —
              text · think · tool · result · usage · done
            anything else is kept in the run record, shown to nobody, and breaks nothing
we keep:    stderr, apart, as what went wrong rather than what happened
we end:     the adapter and everything it started
```

The vocabulary is closed at those six. A seventh is a contract change, deliberately — an open one puts
every vendor's words into every channel and every reader, which is the thing the seam exists to prevent.
Being closed is also what lets an adapter be ahead of us: an unknown record is preserved rather than
refused, so a provider can grow without waiting for a release here.

**A brain with no loop of its own is a first-class brain**, not a degraded one. An adapter that runs no
tools reports none — a complete, honest turn. That is what makes a custom conversational CLI, or a plain
HTTP endpoint, swappable in without pretending to capabilities it has not got.

### What a turn resolves, and what it remembers

There is no binding to create and no resolver phase of its own: what a turn needs is worked out when it
is admitted, and only two things are written down. **The resolver enumerates nothing** — no list of
providers, no list of models. A provider is a name carried through, a shipped adapter or a path to a
program somebody wrote, so one Rundesk does not recognise is the ordinary case rather than an error; the
only failure is nothing runnable being there. A model is a word the adapter understands and nothing here
reads. How much of the machine a turn may touch is a posture carried to the adapter, never a tool list
Rundesk believes in.

**Three things, three lifetimes, and they are not one thing:**

```text
run id            one turn                     ours — what correlates a transcript, a cost, an outcome
session handle    the provider's own token     theirs — opaque here, never interpreted
resume ledger     (conversation, provider)     ours — the only working state that outlives the process
                     -> session handle
```

The ledger is keyed by **conversation and provider together**. Keyed by conversation alone, changing an
agent's provider hands Claude's session to Codex — the Node build's ledger is keyed that way and this one
must not be. Losing the ledger costs the next turn its context and nothing else, which is why it is a
plain file rather than anything larger.

Do not choose the first shipped adapter because the Node build chose it. Probe the installed Claude,
Codex and Grok CLIs against the same minimum contract:

- select model, cwd and private provider home;
- start and stop a turn safely;
- stream structured native output with stderr kept separate;
- identify completion, failure, session and usage;
- resume a completed/interrupted native session;
- state truthfully whether mid-turn input, tool events, questions and approvals are supported.

Before that live turn, close only the process/runtime risks it exercises: serialized writes; bounded,
truthful receiver delivery; safe uncertain liveness and process identity; shutdown within the supervisor
budget; ownership committed before spawn; and a small admission bound. These are the current findings
6, 8–10, 12, 16, 23 and 30. Reproduce each on the implementation baseline and use its failure-injection
criteria; finding numbers are review evidence, not architecture.

Choose the smallest currently documented surface that passes every required item above. Implement that
adapter, a stand-in adapter the suite drives, and `rundesk ask <agent> "..."` to the terminal. Mid-turn
send is not promised until a real probe proves it; some headless providers turn questions into final
prose or require stop/resume.

**One suite, every adapter.** The conformance suite is what a shipped adapter and a stranger's both
pass, and it takes the adapter as an argument so an author can run it against theirs:

```sh
python3 tests/test_provider.py --adapter /opt/my-brain
```

It needs no account, token or network, because the adapters it drives are themselves small programs —
the same thing any real adapter is.

### The transcript — the data this is all for

Every run writes what happened, append-only, one record to a line, and it is never rewritten. This is
the thing worth having: an agent that worked all night is only useful if what it did can be read back.

```text
one file per run          agents/<agent>/runs/<run>.jsonl
five fields to a line     run · agent · seq · at · event
seq is monotonic          a total order that does not depend on a clock, so concatenating
                          two files or rotating one keeps the order it happened in
```

Two rules make it worth trusting:

- **Normalise once, keep the raw.** The record carries our event *and* the provider's own line beside
  it. An upstream format change then shows up as visible drift rather than a silent gap, and a record we
  did not understand is still there to be read later (R-PRV-5).
- **Nothing is sent that the transcript does not show.** Anything Rundesk adds to a turn — standing
  instructions, a continuation, anything at all — is in the record and charged to the run's usage. The
  Node build's note on this is worth keeping: injecting text a human never wrote and leaving it out of
  the audit makes the audit a lie, and it is invisible precisely because it is the audit.

**What is deliberately not copied:** the provider's own session files. Those stay in its home and are
referenced by session handle, because copying them duplicates credentials and vendor config into our
record. **The consequence is honest and should be stated:** if that home is purged, what the vendor kept
goes with it — our transcript is what survives, so it has to be sufficient on its own.

**Usage is captured here, because here is where the stream first exists.** Every provider reports it and
each reports it differently, and the Node build already proved the two traps: Codex's
`turn.completed.usage` is the running total for the whole *conversation*, not the turn — three one-word
replies reported 5, 10, 15 — so a turn's own share is the difference from the last one, and a gateway
restart loses that running total; and Claude bills cache *creation* as fresh input, above the standard
rate, so it cannot be folded in with cache reads. What is drafted is `agent-usage` (`R-USE-n`), beside `agent-run` (`R-RUN-n`) for the account itself, and its
hardest rule is that a cost worked out from prices never reads like one a provider measured.

Nothing here asks a provider what a plan has left. That is the provider's question, needs auth and a
network call, and could not be proved by an offline gate.

### Tests

- Replay captured native streams, including malformed, duplicate, oversized and partial records.
- Prove model/home/cwd arguments through a stand-in executable.
- Prove native events retain their original record plus Rundesk correlation metadata.
- Prove stop ends the provider and its tool descendants.
- Prove secrets and raw tool payloads are not printed to a remote-safe presentation by default.
- Prove a restart either resumes the same recorded run or reports a durable terminal interruption; it
  never silently starts the turn again.
- Prove a conversation's second turn is charged its own tokens, not the conversation's running total.
- Prove a run whose usage never arrived says so, rather than recording a cost of nothing.
- Prove a cost worked out from prices is marked apart from one a provider measured.
- Prove a transcript is readable after the gateway that wrote it has gone.
- Prove two runs of one conversation concatenate into the order they happened in.
- Prove a record Rundesk did not understand is still in the transcript afterwards.
- Prove a second turn resumes the conversation's session, and that changing provider does not.
- Prove anything Rundesk added to a turn appears in that turn's transcript.
- **An adapter this code has never seen carries a whole turn**, written against the guide alone and
  living outside the tree — the claim the whole seam rests on.
- An adapter that runs no tools produces a complete turn, with that work simply absent.
- An adapter emitting a record we do not know keeps it in the run, shows it to nobody, and finishes.
- An adapter that names no model leaves none claimed, rather than the one that was asked for.
- Ending a turn ends the adapter and every process it started.
- One adapter cannot reach another agent's workspace or provider home.
- No vendor's flag, session file or permission mode appears outside its own adapter.

### Exit proof — met

A manual canary completed one local turn, resumed it, and correlated its native stream, transcript,
session and outcome by one run ID. `rundesk ask ava "…"` answered, a second `ask` on the same
conversation remembered what the first had said, and the same question after `--fresh` did not.

**And the seam is proved open, not just designed open.** `tests/strangers/driftwood-adapter` was written
from [the guide](.knowledge/guides/write-a-provider-adapter.md) by an agent given the guide's text and
nothing else — no repository, no source, no tests — and is committed exactly as it was handed over. It
passes the same conformance suite the shipped adapter passes, unchanged, and nothing in Rundesk was
changed to accommodate it. That is `R-PRV-2`, and it is the one row here that could not have been ticked
from the inside.

The claim was tested a second way by accident. The shipped adapter was written against `codex exec`,
then rewritten against `codex app-server` — a different surface, a different protocol, and a capability
gained — and **one file changed**. Nothing outside `adapters/codex` knew either surface existed.

### What this closes

  - the contract, written before any adapter and rewritten twice by what strangers found missing in it;
  - `provider.py` — a seam with no vendor name and no list of providers or models in it;
  - `tests/test_provider.py --adapter <anything>`, which is what makes the seam a claim rather than a hope;
  - one shipped adapter, on the hardest of the three installed CLIs;
  - the transcript: one account per run, appended and never rewritten, ordered without a clock, beside
    verbatim files holding everything the brain itself said;
  - the resume ledger, keyed so that handing one brain's session to another is not expressible;
  - `rundesk ask <agent> "…"`, streamed to the terminal — and `--steer`, which was not planned and is
    now proved against a real brain mid-turn.

### Left open, deliberately

  - **Money.** Nothing works a cost out from prices, so `R-USE-5` has nothing yet to be honest about.
  - **`runs` and `usage` as verbs.** The contracts graduated on module-level evidence; reading a run
    back from the command line is a listing, and listings are cheap to add once a channel wants one.
  - **Approvals and questions.** `codex exec` cannot answer one mid-turn and `app-server` can; nothing
    here uses that yet, and Phase 8 — questions and approvals — is where it belongs.
  - **A gateway you can ask for something.** `ask` runs in the terminal that typed it, exactly as a
    schedule run by hand does. Phase 3 is what forces the question.

## Phase 3 — Open the Channel Seam, and Put Discord Behind It — **done**

**Outcome:** one authorized Discord channel, thread or DM reaches an agent and watches it work — through
a seam a second channel could be written against without changing anything here. Approvals and provider
questions stay explicitly unsupported; steering a running turn is neither, and works exactly as far as
the adapter behind that agent declared it does.

**The same shape as Phase 2, deliberately.** A channel adapter is a program Rundesk runs, not code it
loads: it connects to whatever platform it speaks for, reports what arrives in words no platform owns,
and is told what happened in the same six records a brain reports. Discord is the first one and is
first-class — every Discord-shaped thing lives inside it — but iMessage, Slack or a webhook is one more
program, not a change here. Two swappable edges, one core that knows neither:

```text
  CHANNEL ADAPTERS                                    PROVIDER ADAPTERS
  discord  ─┐                                      ┌─ codex
  slack    ─┼──▶   the gateway  ──▶  a turn  ──▶───┤─ claude
  imessage ─┘      (knows neither edge)            └─ your own brain
```

The seam itself is drafted in `channel-adapter` (`R-CAD-n`), what any channel does with a turn in
`channel-messaging` (`R-CH-n`), and what Discord does with both in `channel-discord` (`R-DIS-n`) — the
last two carried over from the Node build, which had all of this working:
threads opened on being named, reactions marking a turn seen, finished, stopped or failed, and steering
through Discord's own commands rather than words typed into the chat.

### It runs in the gateway, and it stays connected

A channel is not started per turn. The agent's gateway holds the connection open for as long as it is
up, because a message has to be picked up the moment it arrives — a poll, or a process started per
message, is a reply that lands late enough for someone to have asked again. This is what the gateway was
built to own: it already keeps a long-lived thing alive, ends everything it started, and comes back when
the machine takes it away.

The consequences to design for rather than discover: an agent that is stopped is not reachable, and that
must be visible rather than silent; the connection is one more thing a gateway ends when it goes; and a
channel that drops must reconnect without the agent's turns noticing.

### What the system does, and what an adapter does

The lifecycle of a turn is the same on every surface, so the **system** decides when a turn is seen,
running, finished, stopped or failed, and the adapter only says how its platform shows that. An adapter
that had to work out for itself when to mark something seen would be re-implementing the turn, and two
adapters would disagree.

| The system says | Discord shows | A surface with none of that |
|---|---|---|
| taken up | 👀 on the message, and starts typing | says it is working |
| still running | keeps typing alive | — |
| finished | ✅, and the answer posted whole | posts the answer |
| stopped | ✋ | says it stopped |
| failed | ⚠️, and why | says what failed |

**Work goes out early; prose does not.** What the agent *did* — a tool it ran, a thought it closed — is
worth watching as it happens and is shown during the turn. What it *says* is held and posted whole at
the end, because a reply that rewrites itself in place is unreadable. The line between them is whole
records, never part-written ones. This is a rule of the seam, not of Discord: every surface renders what
it can and skips what it cannot, and correctness never degrades — only fidelity.

### Setting one up, and proving it before it is trusted

Adding a channel **tests itself**. `channels add` connects, authenticates, verifies it can see what it
was pointed at, and refuses to write anything if it cannot — an agent whose channel is misconfigured
must find out at setup, not at three in the morning when somebody asks it something.

Discord needs, and is asked for:

```text
--kind discord
--bot <application id>      which bot this is
--allow <user id> …         who may reach the agent through it — at least one, always
--server <id> --channel <id>   where it listens, or a DM
token                       read from the environment or a file, never an argument
```

**At least one allowed user is required, not defaulted.** An unset owner means the agent answers whoever
speaks to it, on a machine where it can run tools — a misconfiguration, never a mode. The Node build
refused to start without one, and that refusal is worth keeping.

`channels ava show ops` then says what it is, who may use it, and that a secret is present — never what
the secret is.

Build the Discord wire against a fake brain first, then attach it to the Phase 2 adapter. The already
pinned `discord.py` dependency must earn its place through the same install and test path as the product;
do not add a second Discord stack.

**What Phase 2 changed, and this phase must use rather than rebuild:**

- **Adapters declare what they can do**, so a channel asks rather than assumes. `steer`, `resume`,
  `tools`, `usage` and `model` are answered per adapter and written into the run's record. A channel
  that offers to interrupt a brain that declared `steer: false` is offering something that cannot
  happen — read the capability, and show what is possible.
- **Steering exists at the seam.** A brain that declared `steer: true` takes words mid-turn. That is
  not the same as an approval, and it does not make questions supported — it means a second Discord
  message during a running turn has somewhere real to go rather than needing to queue.
- **Every turn already writes a transcript**, keyed by run id, ordered by sequence rather than clock.
  A channel adds delivery on top; it does not add a second record, and it must not become the only
  place something was written down.
- **A run already carries its own cost and outcome.** Discord reports them; it does not compute them.

The rule that follows: **a channel is presentation and authorisation, and nothing else.** If this phase
needs a change inside the seam or the turn, that is the finding — the boundary was wrong, and the change
belongs there rather than as a Discord-shaped special case.

**The fake channel is this phase's offline half, not a phase of its own.** Every routing and failure case
— disconnect, slow delivery, retry exhaustion, reconnecting to an existing conversation — is proved
against it before a real token is used, so a Discord failure is never confused with a routing one. What
the fake cannot prove is Discord's own limits, and that is what the canary at the end is for.

### What `channels add` takes

A channel is **named the way a schedule is** — you give it a name to refer to it by later, and what it
is comes from `--kind`. Each kind then needs different things, and those are its own options:

```text
rundesk channels ava add ops   --kind discord --bot <id> --server <id> --channel <id> --allow <user> …
rundesk channels ava add dms   --kind discord --bot <id> --dm --allow <user>
rundesk channels ava add plans --kind slack   --workspace <id> --channel <id> --allow <user>
```

Exact field names are settled **here**, against the installed Discord API rather than from a
specification read early. Until this phase, `channels` is registered and refuses truthfully. What was
decided in advance is only the shape, and these rules:

- **A secret is never an argument.** A bot token on a command line is readable by anything on the machine
  through the process list and is written into shell history. Tokens are read from an environment
  variable or a file the owner already controls, or asked for on a terminal — never `--token <value>`,
  and never stored anywhere Rundesk would print.
- Who may use a channel is part of adding it, not a later step, and **at least one allowed user is
  required rather than defaulted** — an agent that answers whoever speaks to it, on a machine where it
  can run tools, is a misconfiguration and never a mode.
- **Adding a channel proves it works before it is written down.** It connects, authenticates and checks
  it can see what it was pointed at; if it cannot, nothing is saved and the reason is said.
- `channels ava show <channel>` says what a channel is and who may reach the agent through it, with the
  secret named as present rather than shown.

Before reconnectable channel delivery, interruption history must resist lost updates, logs must
have one bounded source, and stale or interrupted runs must be readable and reconciled. These are
the current findings 11, 17 and 26–27 — just-in-time gates for this phase, and not blockers for the
offline agent work before it.

The first slice needs:

- explicit Discord channel/thread to binding lookup;
- authorized user/server/channel checks before run admission;
- a thread opened on being named, and answered in without being named again (R-DIS-1, R-DIS-3);
- the turn marked as it goes — seen, then how it ended (R-DIS-5, R-DIS-7, R-DIS-8);
- stopping and forgetting a conversation, offered as Discord's own commands (R-CH-9, R-CH-10, R-DIS-10);
- prompt acknowledgement within Discord's limit;
- coalesced text edits and bounded/safe handling of long output;
- an asynchronous delivery queue whose failure cannot kill provider work;
- local retention of the final run outcome when Discord is unavailable.

**Stopping and forgetting are not approvals.** They are gestures aimed at the conversation, not at the
provider's permission model, so they belong here while questions and approvals wait for Phase 8. What a
control *did* arrives as the turn's own outcome, never as the command's answer — acknowledging a control
with a lifecycle signal is what made resetting mid-turn publish the running turn's half-written output in
the Node build (R-DIS-12).

### Tests

- Fake-channel disconnect, slow delivery and retry exhaustion do not end the provider turn.
- Reconnecting the fake channel identifies the existing conversation/run instead of duplicating it.
- An unauthorized user, server or channel is refused before a run is admitted, not after.
- A message naming a provider, model or permission policy changes none of them.
- Output too long for one message is bounded and split or attached, never truncated in silence.
- A stop ends the turn running in that conversation and nothing else.
- Forgetting a conversation means the next message starts a new session, not a resumed one.
- A control raised mid-turn does not publish the running turn's half-written output as its answer.
- **A channel adapter this code has never seen carries a whole conversation** — the claim the seam rests
  on, and the same one Phase 2 makes of a brain.
- The poorest surface there is — no reactions, no typing, no edits — still carries a turn from arrival to
  answer, because correctness never degrades and only fidelity does.
- The system decides a turn is seen, running, finished, stopped or failed; no adapter works that out.
- Adding a channel that cannot connect writes nothing and says why.
- Adding a channel with nobody allowed is refused.
- A channel is held open by the gateway, comes back by itself after a drop, and goes when the gateway does.
- An agent that is stopped is reported as unreachable rather than silently missing messages.
- Work is shown while the turn runs; the answer arrives whole, and never part-written.
- No Discord concept — a snowflake, an intent, a gateway opcode — appears outside the Discord adapter.

### Order of work

Discord is the first phase where a mistake is visible to somebody who is not the owner, so the offline
half is finished before a token exists — and, as in Phase 2, the seam is written before the adapter that
proves it:

1. **The seam**: what a channel adapter is handed, what it reports, and what the system decides for it.
   Written before any Discord code exists, and written for a stranger.
2. **The channel record** — what `channels add` writes, where the token is read from rather than typed,
   and the check at setup that refuses to write it when the platform will not answer.
3. **A fake channel**, and every routing and failure case against it: unauthorized sender, disconnect,
   slow delivery, retry exhaustion, reconnection finding the conversation it already had.
4. **The turn's lifecycle as the system decides it** — seen, running, finished, stopped, failed — with
   the fake showing it, so the marks are proved before an emoji exists.
5. **Presentation**: what a turn's records look like as messages, work shown as it happens, the answer
   posted whole, and what a long one does.
6. **The Discord adapter**, behind that same fake-tested surface: threads, DMs, reactions, typing.
7. **Held open by the gateway**, reconnecting on its own, ending when the gateway ends.
8. **A private-server canary**, last, proving only what a fake cannot — Discord's own limits and timings.

### Exit proof — met

A fake channel proves every routing and failure case offline, and it is what the gate stands on: nothing
in the suite reaches Discord or needs a token. A real agent then carried whole conversations on a private
server, in direct messages and in a room, and the transcript of each run tells the same story the channel
told — because the channel wrote none of it.

**And the seam is proved open, not merely designed open.** `tests/strangers/semaphore-channel` was
written from [the guide](.knowledge/guides/write-a-channel-adapter.md) by an agent given the guide's text
and nothing else — no repository, no source, no tests — and is committed exactly as it was handed over.
It passes the same conformance suite the shipped adapter passes, unchanged, and nothing here was changed
to accommodate it. That is `R-CAD-2`, and it is the row that could not have been ticked from the inside.

The mirror held in the other direction too. The phase needed a brain to be told where it was answering,
which is a *provider* question — and the answer went into the provider seam as `RUNDESK_PREFACE`, not
into the channel as a Discord-shaped special case. Nothing outside `channels/discord` knows Discord
exists, and nothing outside `adapters/codex` knows what `developerInstructions` is.

### What this closes

  - the contract, written before any Discord code and rewritten by what the shipped adapter found
    missing in it;
  - `channel.py` — a seam with no platform name and no list of platforms or of the kinds of place any
    of them has;
  - `answering.py` — arrival to answer, and the only module that knows a turn and a surface both exist;
  - `tests/test_channel.py --adapter <anything>`, which is what makes the seam a claim rather than a hope;
  - one shipped adapter, and one written by a stranger from the guide alone;
  - channels held open by the agent's own gateway, swept and ended with it like any other work;
  - standing instructions an owner writes per channel, reaching a brain through whatever its adapter has
    for *adding* to its instructions and never through anything that replaces them;
  - a turn standing in the agent's own home, so the rules scaffolded for it are the rules it loads.

### Left open, deliberately

  - **Fourteen rows are still ❌**, and honestly so. Eleven are what a person sees and nothing else can
    settle — a mark appearing, an indicator running, a bot showing online — and
    `.knowledge/scripts/probe-discord` says what to do and what to look for on each. Three want a real
    connection dropped at a chosen moment. None is ticked on a script's say-so.
  - **The gateway announces itself once per channel.** Two channels, two notices, both to the same
    person. The notice is about the gateway, so it wants deciding where it belongs rather than papering
    over.
  - **A second platform.** The stranger's adapter proves one can be written; Telegram or Slack proves
    it is worth writing. Four questions were surfaced by reviewing for them and left for the owner:
    what `direct` means where there is no such thing, whether an adapter should filter un-addressed
    messages in a busy room, how a conversation maps to a Slack thread, and what dialect prose is in.
  - **What the medium is, as against what the owner says.** Hermes ships a hint per platform describing
    the medium itself — what markdown converts, how a file is sent — leaving an owner to write only what
    they alone know. Ours makes the owner write both.

## Phase 4 — Design the Shape of What Is Kept, and Build the Way In

**Outcome:** a settled, agreed design for how everything durable is organised, queried and carried
between versions — **and the seam it is all reached through, built and exercised against nothing that
matters yet.**

**Why this is its own phase.** Every other phase here could discover its design while building it, because
a wrong turn cost a rewrite of code nobody had yet. This one cannot: the moment a release lands, the shape
is on somebody's disk and every mistake becomes a migration. Discovering the design while implementing it
means discovering it in the one place where mistakes are permanent. So the design is finished, argued over
and written down first, and the phase after does exactly what was written.

**Nothing anybody owns is touched here.** No file is moved, nothing is migrated, and nothing yet reads
the new store — the old layout keeps working throughout, untouched, and could keep working if this phase
were abandoned. What *is* built is the way in: the schema and the one module every reader will go through.

**That is deliberate, and it is why this is not a paper phase.** A query seam designed on a page and never
run is a guess: whether a caller can actually ask for what it needs without SQL leaking out, whether a
migration can find every question, whether reading can be told from writing — none of that is knowable
until something has been built against a real database. So it is built here, where the only database it
touches is one made for a test, and the phase after moves real data onto something already proven to work.

### First, the shape of each part — with the owner, one at a time

**This is the phase's first task and it is not done alone.** Every one of these is persisted state, which
`AGENTS.md` makes a hard gate, and a schema settled by an agent on its own is a schema the owner has to
live with. So they are worked through together, in this order, each one finished before the next is opened.

What each holds *today* is listed so the conversation starts from what is true rather than from a proposal.
Read them off a real install first — these were read off one — and correct this list where it has drifted.

| | What it is | What it holds today |
|---|---|---|
| 1 | **the agent** | `{"provider": "…"}` on the install read here — but `agent.remember()` writes **three** fields: `provider`, `model` and `settings`. Design for three |
| 2 | **its channels** | one per surface: its kind, where it listens, who may use it, and what it is told about where it is (`channels says`). Its credential is *referenced*, never held — a token in the environment or a file in the channel's own directory. **Plus a directory per channel**, `channels/<name>/`, which is the adapter's own and holds that token file and anything it downloads |
| 3 | **its schedules** | `[{name, when, run: [program, args…], enabled}]` — a JSON list, at `schedules/<agent>.json` |
| 4 | **what each schedule last did** | **three sidecars, not one.** `<agent>.ran.json` is what each last did, rewritten whole and flushed to disk; `<agent>.seen.json` is a fifteen-second liveness beat that a *later* gateway reads to work out what it missed; `<agent>.interrupted.json` is work that never finished, capped and written under a lock |
| 5 | **its sessions** | `{brain-fingerprint: {conversation: handle}}` — keyed by the brain *and* the conversation, so changing provider cannot resume the wrong one. A conversation is `terminal` or `<channel>/<platform-id>`, and on the install read here one of them is a *session handle* somebody passed to `--conversation` |
| 6 | **its runs** | **nothing.** There is no run record today — no row, no index, no file. Every field below lives inside the `admitted` and `outcome` events of the account, and the only way to enumerate runs is to glob the directory, which nothing in the product does. The run is something this phase invents rather than moves |
| 7 | **the account of each run** | every record in order, with its sequence and time. Rundesk writes `admitted`, `sent`, `lost` and `outcome`; a brain's are `text`, `think`, `tool`, `result`, `usage`, `file` and `done`. **This is the searchable history**, and the largest thing here by far |
| 8 | **how a run is named, and what version the data is** | ids look like `1-co8m`, and the counter file is a *hint* — the id is claimed by creating its file exclusively, and on a collision the directory wins. Moving to a database moves where uniqueness is decided. The version has nowhere to live yet |

For each, the questions worth answering before it is a table: what identifies it, what may be absent versus
what may never be, what is one row versus many, what is asked of it often enough to be indexed, what is
allowed to be deleted, and **what a migration would have to do if this part changed shape**. That last one
is the point of asking now: a shape nobody can imagine migrating is a shape to change while it is free.

### What it must settle

Everything below is the current proposal, arrived at by walking what is actually on disk. It is where this
phase starts, not where it is obliged to end — and every part of it is the owner's to confirm, because all
of it is persisted state.

**Group by lifetime, not by kind.** That is the whole answer to the scatter. Today things are grouped by
what they *are* — logs here, schedules there, runs somewhere else — which is why the same agent's things
are in four places and why a name has to be repeated to tell them apart. What actually differs between
them is **how long each is meant to last and who owns it**, and that is what decides whether stopping an
agent may delete it, whether an update must migrate it, and whether removing an agent takes it.

Four lifetimes, and everything durable is exactly one of them:

| | Lives until | Who owns it | Cleared when an agent stops? |
|---|---|---|---|
| **the person's** | they delete it | the owner | never — `--purge` only |
| **records** | the agent is removed | rundesk | no — this is what migrates |
| **history** | retention says otherwise | rundesk | no — it must outlive the gateway |
| **running** | the agent stops | rundesk | **yes, always** |

Which gives one shape per agent, and nothing outside it:

```text
~/.rundesk/
  rundesk.json                  what shape this install's data is in. One number, and nothing else.
  agents/
    ava/
      state.db                  RECORDS — the agent, its channels, schedules and what each last
                                did, its sessions, every run, and the account of what happened
                                in each. One per agent, never one shared: see below.
      home/                     THE PERSON'S — never touched by anything but --purge
        AGENTS.md  CLAUDE.md  SOUL.md  USER.md  MEMORY.md
        workspace/
        skills/
      providers/<provider>/     a brain's own home, one per provider. Opaque to us.
      history/                  HISTORY — append-only, outlives the gateway
        gateway.log
        brains/<run>.raw        what the brain itself said — the *adapter* appends here
        brains/<run>.err        what it said went wrong
      running/                  RUNNING — what it is doing now, emptied when it stops
        gateway.lock
        gateway.json
        locks/                  every lock, together, and never among the records
```

What that fixes, item for item:

- **The two layouts become one.** `~/.rundesk/{run,logs,schedules}` stop existing; `gateway.py` reads the
  agent's own directories like everything else does.
- **A name is said once.** `history/gateway.log`, not `logs/ava.log` inside `agents/ava/`.
- **Locks are not data.** They are all in `running/locks/`, so they are never mistaken for records and
  are cleared by the same sweep that clears everything else a stop clears.
- **The two words are not the same word.** `state.db` is what an agent *is* and keeps; `running/` is what
  it is *doing right now*. Naming both "state" would put the schedules, sessions and run index of an agent
  in the one directory a stop is supposed to empty — which is the worst mistake available here, and is why
  the tier a stop clears is named for what it holds rather than for how long it lasts.
- **A run is one thing.** One row, with what its brain said beside it in a file only because a stranger's
  program is what appends there — and both forgotten together.
- **A counter is not a record.** Allocating a run id is the database's, in a transaction, not a JSON file
  among the runs it numbers.
- **Removing an agent is one directory**, and `--purge` versus not is the difference between taking
  `home/` and leaving it.

**One database per agent, not one for the install.** `gateway.py` already states the principle this rests
on — *"Nothing is shared between two gateways: that is what makes one restartable without disturbing the
rest"* — and every agent has its own gateway process. A shared database puts one agent's write lock in
another's way and makes one corrupt file everybody's problem, which is the coupling that sentence exists
to prevent. `usage` across every agent is then several small queries rather than one, on a machine that
has a handful of agents, which is a price worth paying for keeping an agent self-contained enough to copy
elsewhere.

**One version number, at the top.** `rundesk.json` says what shape the data is in, and a migration is a
step from one number to the next that may move files, change a schema, or both — because moving
`logs/ava.log` to `history/gateway.log` is a migration too, and a schema version inside a database cannot
describe it. Each `state.db` mirrors that number in `PRAGMA user_version` so a database found on its own
still says what it is.

**Where SQLite earns its place, and where it does not.** It is in the standard library, so it costs no
dependency, and `PRAGMA user_version` is a schema version designed for exactly this. The split worth
making:

**The line is who writes it, not how big it is.** That is the one place the split cannot be argued with:

| | Where it goes | Why |
|---|---|---|
| the agent, its sessions, its channels, its schedules and what each last did, every run — and **the account of what happened in each** | **`state.db`, one per agent** | Rundesk writes all of it, from records an adapter reported. Small, structured, and the thing anyone would want to ask a question of. Today it is eight JSON files with four lock files beside them; one transaction replaces a `flock`, `user_version` gives migrations somewhere to live, and `runs` and `usage` become queries rather than directory walks |
| what the brain itself said, and what it said went wrong | **files, and they have no choice** | `RUNDESK_RAW` is a **path handed to the adapter**, and an adapter is a program in any language — the contract says a shell script is enough. You cannot hand `bash` a database handle. The same goes for stderr, which is a pipe the operating system gives us. Referenced from `state.db` by run id |
| the gateway's log | **a file** | rotated, tailed, and read by a person while something is going wrong |

**The database is the history; the files are diagnostics, and may be destroyed.** That is the split's
point, and it has one consequence that must be designed for rather than discovered: **the account has to
stand on its own.** If what a brain said can be deleted to reclaim space — and it can, and should be —
then nothing may be recoverable only from there. The same rule already applies one level out, where a
provider's own session files are referenced and never copied: our record is what survives, so it has to be
enough. A run whose account says "see the raw file" is a run that will one day say nothing.

**What this actually unlocks: one history across every surface.** The account already records both sides
of a turn — `sent` is what the person asked, `text` is what the agent answered — and `admitted` carries
the conversation it happened in. Nothing new has to be captured; it is captured today and thrown into a
file per run with no way to ask it anything. As rows, with the conversation as the key that ties runs
together, the same store answers all of these:

```text
everything ava has ever been asked, wherever it was asked
one Discord thread's whole history — across a dozen runs, in order
what was said about the parser, on any surface, by any agent
what an agent was told on Tuesday, and what it did about it
the same conversation continued from the terminal and then from Discord
```

That last one is the point of doing it once rather than per channel: a surface is where a message arrived,
not where it lives. Discord, a schedule and the terminal all dispatch into the same account, so history is
not something each channel keeps its own version of — which is exactly what would have happened if each
adapter had been left to record what it saw.

**Searchable is a requirement, not a side effect.** The reason the history goes in the database is to be
able to ask it something later — what did ava say about the parser, which run mentioned that file, what
was I told last Tuesday. SQLite has `FTS5` for exactly this and it is present in every Python checked here
(3.11, 3.13, 3.14, SQLite 3.53). But **it is a compile-time option, not a guarantee**, and the floor is
the oldest Python a fresh macOS ships, on Linux as well as macOS. So it is asked for rather than assumed:
searching works where it is there, `doctor` says so where it is not, and the history is still readable and
still queryable by agent, conversation, run and time without it. A feature that silently needs a build
option nobody checked is how an install works on one machine and not the next.

That split is the recommendation, not a foregone conclusion — **it is an owner decision and a persisted
schema change, so it is confirmed before anything is written.** What must not happen is a live event
stream moving into a transaction per record, or a legible transcript becoming a table nobody can read
with the tools they already have.

### 4B. A migration that runs on update, before anything comes back up

An update already stands every gateway down and brings it back — `R-UPD-21`, and it already refuses
rather than replacing files under something it could not stop. **The window this needs already exists and
is already tested**, which is most of why this half is small: migrations run inside it, after the files
are replaced and before the first agent is started again.

```text
update:  check what is published
         refuse if work is in flight
         stand every gateway down          ← already built
         replace the files
         MIGRATE what is on disk           ← this half
         bring every gateway back          ← already built
```

How it behaves, which is the part worth arguing about now rather than during an incident:

- **A migration is found, not listed.** Each is a file named for the version it brings data up to, and
  what runs is whatever sits between the version on disk and the version now installed.
- **In order, once each, recorded.** What has run is written down, so an update that stops halfway does
  not run half of it again.
- **A migration that fails stops the update, and the agents stay down.** Bringing an agent back onto data
  half-moved is worse than leaving it off and saying so. The owner is told which migration, and what was
  reached.
- **Backwards is a real case.** A consumer who hits a bad release wants the previous one, and old code
  reading a newer shape is the dangerous direction, because it does not know what it is missing. A version
  it does not recognise is refused outright rather than read hopefully.
- **Nothing is migrated in place until it has somewhere to fall back to.** What was there is kept until
  the new shape is written and readable.
- **A fresh install runs no migrations** and is stamped with the current version, so first use and
  upgrade converge on the same shape.

### One way in, and no SQL anywhere else

**A reusable query seam is part of this phase, not a tidy-up afterwards.** Raw SQL at eight call sites is
`~/.rundesk/{run,logs,schedules}` again one level up: the same question asked three slightly different ways,
and every migration having to find them all. This codebase already has the pattern to follow — one reader
and one writer serve every file today, and `gateway.changing()` holds a read, a decision and a write under
one lock.

So: one module opens `state.db`, one place begins and commits, and **a caller asks for what it wants rather
than saying how to get it**. What that must give, whatever its shape ends up being:

- **Named questions, not strings at call sites.** `runs`, `usage`, `agents`, `schedules` and searching all
  ask the same seam. A question asked in two places is asked through one name.
- **A migration can find every question.** When a column moves, what breaks is one module, and it breaks
  visibly rather than at the one call site nobody grepped for.
- **Nothing outside it knows SQL exists.** The same rule the provider and channel seams already hold to:
  no vendor concept crosses the line, and here the vendor is the database.
- **Read and write are told apart**, so a reader can never quietly begin a transaction that blocks a turn.
- **It is testable without a gateway**, like everything else here — a database in a temporary directory,
  and no process anywhere near it.

### What it produces

Four things, and the phase is not finished until all four exist:

1. **The schema, and the one module every reader goes through** — built, tested, and used by nothing yet.
   With it, a draft contract for what it guarantees, so what the next phase moves onto is a promise rather
   than an implementation detail.
2. **A research note** in `.knowledge/research/`, following `guides/docs-research.md`, on how the world
   already solves this — how migration systems are ordered and recorded elsewhere, what they do about a
   failure halfway and about going backwards, what practice says about SQLite for this shape, and what a
   query seam usually looks like. Reporting, sourced, and separate from what we decide.
3. **A draft contract for the shape**, in `.knowledge/prd-drafts/` — what is kept, where, under which
   lifetime, what carries a version, and what may be destroyed.
4. **A draft contract for moving between versions** — how a migration is found, ordered, recorded, and
   what happens when one fails or when data is newer than the rundesk reading it.
5. **The owner's decisions, recorded rather than assumed.** Each of these is a hard gate under `AGENTS.md`
   and none may be settled by an agent alone:
   - the layout, and that `~/.rundesk/{run,logs,schedules}` stops existing;
   - SQLite at all, and one database per agent named `state.db`;
   - which things become rows and which stay files;
   - that the raw stream a brain produced may be destroyed;
   - the retention of everything else — the open question `agent-run` already carries;
   - how a conversation is keyed, given one history now spans every surface.

### How it is proved

The seam is proved the way everything here is — offline, against a database in a temporary directory, with
no gateway and no agent anywhere near it:

- Every question a caller can ask is answered, and asking the same thing twice goes through one name.
- No SQL exists outside the module that owns it, proved by looking rather than by intention.
- A reader cannot begin a transaction that would make a writer wait.
- Two writers to one database cannot lose one another's change.
- A schema at a version this code does not know is refused rather than read.
- Searching works where the machine can, and its absence is reported rather than returning nothing.

The design cannot be proved by tests, so it is proved by three other things, and dishonesty here is the
only real risk:

- **Every decision above is written down where decisions live**, not in a conversation that scrolls away.
- **The design accounts for what is on disk today**, item by item — including the two coexisting layouts,
  the four lock files, the four files per run, and the counter among the runs. A design that does not
  mention something that exists has not been checked against reality.
- **The migration is walked through against the owner's own install** on paper, naming what moves where.
  If that walk cannot be written, the design is not finished — and it is far cheaper to find that out here.

### The walk, against the install that exists

Read off `~/.rundesk` on 2026-07-26. It is one agent, `john`, with four runs, no channels and no
launchd job — and `~/.rundesk` is itself the install directory, so `agents/` sits inside the tree an
update replaces. Every item is named, including the ones that turned out not to be there.

| on disk today | becomes | note |
|---|---|---|
| `agents/john/agent.json` → `{"provider":"codex"}` | one row in `agent` | `model` and `settings` are writable today and unset here, so the row is mostly empty and that is correct |
| `agents/john/agent.changing` | **deleted** | a lock, not data |
| `agents/john/sessions.json` | rows in `conversation` and `session` | see below — this one is not a straight copy |
| `agents/john/sessions.changing` | **deleted** | |
| `agents/john/runs/allocating.json` → `{"last": 4}` | **deleted** | the run number becomes the database's, and the count is checked against the rows rather than carried |
| `agents/john/runs/allocating.changing` | **deleted** | |
| `agents/john/runs/<run>.jsonl` ×4 | rows in `run`, `record` and `message` | the `admitted` and `outcome` events become the run's columns; `sent` and `text` become messages; the rest become records |
| `agents/john/runs/<run>.raw` ×4 | `record.raw` | folded in, then the file goes |
| `agents/john/runs/<run>.brain` ×4 | `logs/runs/<run>.jsonl` | renamed to what it is; still a file, still destroyable |
| `agents/john/runs/<run>.err` ×4 | `logs/runs/<run>.err` | moved, unchanged |
| `agents/john/logs/` — **empty** | `logs/` | nothing to move |
| `agents/john/run/` — **empty** | `gateway.json`, `gateway.lock` at the agent root | nothing to move; the agent is not running |
| `agents/john/schedules/` — **empty** | rows in `schedule` | john has none |
| `agents/john/home/` | `home/`, untouched | the person's. only `--purge` may take it |
| `agents/john/providers/codex/` | unchanged, in place | the brain's own home, opaque. It holds Codex's own `goals_1.sqlite` — never walked, never copied |
| `~/.rundesk/schedules/twice.seen.json` | **deleted, and said** | a sidecar of a gateway named `twice` that has no agent and never will |
| `~/.rundesk/schedules/twice.interrupted.changing` | **deleted** | a lock belonging to the same orphan |
| `~/.rundesk/{run,logs}` | — | **do not exist.** The legacy layout is two files, not three directories |
| `~/.rundesk/.update.lock` | unchanged | install-level, not an agent's |
| `~/Library/LaunchAgents/ai.rundesk.*` | — | **none present.** A machine with one gains `logs/gateway.log` as both its capture paths |
| — | `~/.rundesk/rundesk.json` | **new.** The layout version, one number |

**The one row that is not a copy.** `sessions.json` reads:

```json
{"codex": {"terminal":                              "019f9c43-4c96-7ce1-ba75-384223458dd6",
           "019f9c43-4c96-7ce1-ba75-384223458dd6":  "019f9c45-6fa2-7f72-96db-79812a22c65b"}}
```

Two conversations under one brain, and the second is *named after the first's session handle* —
somebody passed `--conversation` a handle. The shape has no conversation to attach to, so the
migration **mints one per distinct key**: `('terminal', 'terminal', '')` and
`('terminal', '019f9c43…', '')`, each with a `session` row keyed to brain `codex`. Nothing is
merged, because nothing here can prove those two were the same conversation — and guessing would
silently join two histories. This is exactly the case that would have been discovered in Phase 5
against real data, which is why the walk exists.

**What the walk found that the design had missed:** the `.brain` file is the adapter's and the
`.raw` file is rundesk's, so only one of them is forced to stay a file; `~/.rundesk/run` and
`logs` do not exist at all, so the legacy layout is far smaller than assumed; and a conversation
key can be a session handle, which no migration written from the documentation would have expected.

### Exit proof

The owner has agreed the layout, the split between rows and files, retention, and the migration mechanism,
and each is written where the next phase can build from it without asking again — a second person could
carry it out from what is written. The seam exists, is tested, and is reached by nothing: the old layout is
still what runs, and deleting the new module would leave the product exactly as it was. Nothing on the
owner's disk has changed.

## Phase 5 — Move Everything Onto It

**Outcome:** what Phase 4 designed is what is on disk, everything reads it through one seam, and an update
carries a previous version's data into the new shape before any agent comes back up.

This phase writes no new design and builds no new seam — Phase 4 built that, and this is what it was for.
Where the design turns out to be wrong, that is a finding and the drafts move first, because the whole
point of the phase before was that this one does not improvise.

### Order of work

1. The migration runner, with one migration: the one that brings today's layout to the new one.
2. Move readers and writers over to the seam Phase 4 built, one at a time, each with its own regression
   check.
3. Delete the old layout, and the code that defaulted to it.
4. Migrate the owner's own install, with a copy kept until it is proved.

### Tests

- Stopping an agent empties `running/` and touches nothing in `home/`, `history/` or `state.db`.
- Removing an agent takes one directory; `--purge` is the only thing that takes `home/`.
- No lock file sits anywhere a record does.
- Forgetting a run takes its row and the brain's own files with it, and nothing of another run's.
- Nothing reads or writes `~/.rundesk/run`, `logs` or `schedules` any more.
- Two agents' gateways writing at once never wait on each other.
- Every durable thing carries a version, and something that does not is refused rather than guessed at.
- One kind of thing has exactly one home; the older layout is gone rather than merely unused.
- Data written by the previous release is readable by this one after an update, and says the new version.
- A migration runs once, and an update that stopped halfway does not run it again.
- A migration that fails leaves every gateway down, the reason said, and the data as it was.
- A version newer than this rundesk understands is refused rather than read.
- A fresh install needs no migration and is stamped current.
- Two commands changing one agent's records at once cannot lose one another's change.
- An account of a run is readable without the gateway that wrote it, and after it has gone.
- A turn writing its account does not hold up another command reading a schedule.
- What a brain said is kept where a shell-script adapter can append to it.
- Deleting what a brain said leaves the account of that run whole and still readable.
- Nothing a run recorded is recoverable only from a file that may be destroyed.
- What an agent has been told and has said is searchable by words in it, where the machine can.
- One conversation's whole history reads back in order, across every run it took.
- A conversation carried on from a second surface is one history, not two.
- What arrived on one surface is found by a search that names no surface at all.
- A machine whose SQLite cannot search still lists, reads and queries every run.
- `doctor` says when searching is unavailable rather than searching returning nothing.
- Nothing an update touches loses a transcript, a log, or what a schedule last did.
- No SQL appears outside the one module that owns it.

### Exit proof

An install of the previous release, with agents, schedules, channels, sessions and history on disk, is
updated to this one: the migration runs in the window where nothing is up, every agent comes back, and
everything that was there is readable in the new shape. The same update run twice migrates once. A
migration made to fail leaves the agents down and says which one and why. And the owner's own install —
the one with real history in it — is carried across, with what it looked like before kept until it is
proved.

## Phase 6 — Let the Clock Start Work

**Outcome:** an agent does work because the time came, through the same resolver, run record and
provider adapter that Discord and the terminal already use.

**Most of the mechanism is already here, and one thing blocks it.** A schedule carries what it names
without reading it (R-SCH-3), so a schedule whose program is `rundesk ask ava "…"` is a scheduled turn —
no new schema, no binding, nothing to migrate. `ask --says` already exists so a scheduled turn can be
given its own standing instructions.

What stops it today is **finding 22**, and it reproduces in one command:

```text
rundesk schedules ava run nightly
  → rundesk ask ava "what changed?"
  → ava: NO SUCH AGENT — nothing of that name has been made
```

`process.environment()` builds a deliberately bare environment — right, because a gateway must not hand
every secret it holds to every program it runs — but it passes `RUNDESK_HOME` and not the state
directories. `supervisor.describe()` carries all of them *into* the gateway, with a comment recording
that leaving one out "silently split the machine in two"; the same split is reintroduced one level down
for any scheduled program that is itself `rundesk`. **Close that first, and most of this phase is
already standing.**

Any change to existing schedule files is a persisted-schema decision and requires owner approval plus a
tested migration or an additive format that keeps old schedules truthful — but on the evidence above,
none is needed.

### Nobody is watching, so the outcome has to go somewhere

This is the first trigger with no person at the other end, and Phase 3 is what makes that survivable: an
agent now has channels. A scheduled turn that failed at three in the morning should be readable where its
owner already looks, rather than only in a log nobody opens.

What that means, and what it must not become: the outcome of a scheduled turn reaches the agent's channel
when it has one, and a scheduled turn is never *only* recorded where nothing will surface it. What it must
not become is a channel deciding anything about schedules — a schedule that fires with no channel
configured still runs, still records, and still reports through `schedules`.

Before enabling provider-backed schedules, the scheduler must prove that it examines work immediately
after gateway start, agrees on cron next-time and firing semantics, reconciles a stale `started` outcome
after a crash, and cannot confuse Rundesk options with provider arguments. These are the current risks
recorded as findings 24–26 and 31.

### Tests

- `schedule A` and `schedule B` share one agent but resolve different provider/model selections.
- Existing never-late and never-overlap rules still hold.
- An interactive request in an autonomous schedule becomes a clear outcome instead of waiting forever.
- A schedule run by hand runs, and leaves the time it next falls due where it was (R-SCH-21, R-SCH-22).
- A schedule whose provider fails leaves one durable outcome that `schedules` reports, not silence.
- **A program the gateway starts reads the same places the gateway does** — the regression check for
  finding 22, and the one that makes a scheduled `rundesk ask` find its agent at all.
- A scheduled turn's outcome reaches the agent's channel where it has one.
- A scheduled turn on an agent with no channel still runs, records, and is reported by `schedules`.
- A scheduled turn is never the only thing that knew what happened.

### Exit proof

One scheduled run passes through the same resolver, run record and provider adapter that Discord and the
terminal already used — and its outcome is readable the next morning without a terminal having been open.

## Phase 7 — Bootstrap Knowledge, Skills and Tool Discovery

**Outcome:** every provider can be given the same agent's knowledge and a basic skill without Rundesk
becoming a second skills or tools engine.

**This is additive, which is why it waits.** An agent that loads a skill is a better agent, not a
different one: nothing about the channel, the turn, the run record or the resolver changes when this
lands. Everything before it was work that could not be added later without redoing it, and this is not.
The corollary is a real constraint — if a change here forces a change in Phase 2 or 3, it is not a skill
concern and belongs in the phase it disturbed.

Add one basic `SKILL.md` template, one canonical agent-visible skills library and only the provider
discovery links that live probes prove. Current Node probes suggest `.claude/skills/` and
`.agents/skills/` links, while a bare `skills/` directory is not enough; re-probe current CLI versions
before making that a guarantee.

The first tool discovery kit should only inventory, search and explain granted tools. It should not
duplicate provider-native file/shell tools, dynamically load plugins or execute arbitrary new actions.
Tool execution and richer grants wait until one provider turn is proven — which by now it is.

### Tests and probes

- Offline tests prove scaffold idempotency, link resolution and agent-specific grants.
- Rundesk-managed config does not automatically discover ungranted owner-level skills.
- A canary agent proves each provider follows `AGENTS.md` to `SOUL.md`, `USER.md` and `MEMORY.md`.
- A basic skill canary proves actual provider discovery from the agent's workspace.
- Saved, sanitized probe output records provider version, invocation and result.

### Exit proof

Each supported provider has a current capability row marked proven, unsupported or unknown. Rundesk does
not claim that a provider loaded a rule or skill based only on file presence.

## Phase 8 — Questions, Approvals and Recovery

**Outcome:** a supported provider can pause for remote input without weakening its native permission
model, and Rundesk can recover truthfully after a gateway/channel restart.

Add one interaction type at a time: question, allow once, deny and cancel. Each pending interaction is a
single-use capability bound to the authorized user, provider request, conversation, run and expiry.
Mismatches and expiry deny by default.

Provider behavior is allowed to differ:

- a bidirectional protocol may stay live and receive the answer;
- a headless provider may defer, exit and resume its native session;
- an unsupported request must be reported as unsupported, never converted to blanket permission bypass.

### Tests

- Duplicate, stale, wrong-user and wrong-conversation responses cannot act.
- Channel or gateway restart preserves enough correlation to answer or safely deny the pending request.
- A provider crash while waiting produces one durable outcome and does not restart the turn from scratch.
- Discord delivery failure does not lose the local pending/outcome record.
- Raw tool arguments/results remain local unless an explicit redaction/presentation rule allows them.

### Exit proof

A manual canary completes one question and one approval through Discord, then repeats each across the
supported restart boundary. The public always-online claim waits until interrupted work can resume rather
than restart and repeated crashes stop looping (the currently unproven R-GW-22 and R-GW-24).

## Phase 9 — Add Provider and Channel Breadth One Adapter at a Time

**Outcome:** Claude, Codex and Grok can each be selected where an entry point is made, and a second
channel can reuse the same channel contract without changing the agent.

Add the remaining providers one at a time behind the Phase 2 conformance suite — which by now a
stranger's adapter has already passed, so adding one is writing a program against a published contract
rather than extending a core. Preserve real differences: do not synthesize tool events a provider does
not emit, claim interactive input a protocol cannot accept or hide cumulative usage behind guessed
per-turn numbers.

If adding one of these needs a change inside Rundesk, that is the finding — the seam was not open, and
the change belongs in the contract rather than in a special case for whichever vendor exposed it.

Only after Discord and the fake channel share a proven surface should Slack be added. A Slack binding
selects its provider/model exactly as Discord and schedules do; it does not add Slack fields to the
agent.

### Exit proof

- Each provider passes the supported subset of the same invocation/replay/recovery suite.
- `doctor` reports installed version and proven/unsupported capabilities for each provider.
- One agent is exercised through at least two channels and two schedules with different provider/model
  selections and unchanged agent knowledge.
- Adding the second real channel requires a wire/presentation adapter, not provider or agent changes.

## Explicitly Deferred

- A database, distributed workers or a general queue service.
- Dynamic provider/channel plugin loading.
- A Rundesk-built conversational or tool-execution loop.
- Automatic cross-provider conversation migration.
- A rich common event taxonomy before real adapters require it.
- Arbitrary remote changes to provider, model, permissions or tool grants.
- Executing every discovered tool before inventory, grants and one provider turn are proven.
- A budget that throttles or stops an agent that has cost too much. Recording comes first, so a cap is
  set against history rather than a guess — and a wrong reading stops a working agent.

## Ready-for-Next-Phase Verdict

Phases 0 to 3 are done. Agents exist and are operated by name; a brain is reached through a seam a
stranger has already written against; Discord is one channel adapter of several possible ones. **Next is
the shape of what is kept** — because a consumer's data begins existing at the first release, and a record
written without a version can never afterwards be read with certainty.

The next implementation sequence should be:

1. ~~Make the dependency/test gate truthful and declare the approved product/CLI surface.~~ **Done.**
2. ~~Build the agent and its home, and refactor the command surface so agents are what a person operates
   and gateways are how they run.~~ **Done.**
3. ~~Open the provider seam and put one brain behind it — the contract first, a shipped adapter as its
   first customer, a stranger's adapter as the proof, and the transcript that makes any of it worth
   having.~~ **Done.**
4. ~~Reach that agent through Discord.~~ **Done** — the channel seam, with Discord as its first adapter
   and a stranger's channel adapter proving it open.
5. **Design the shape of what is kept, and build the way in.** The design settled and agreed — one home
   per kind, a version on everything, what may be destroyed — and the schema and query seam built and
   exercised against nothing that matters yet. **This is next, and it is next because it is the only work
   here with a deadline** — the shape stops being cheap to change the day somebody installs.
6. **Move everything onto it**, exactly as designed: the migration runner, every reader moved across to
   that seam, the old layout deleted, and the owner's own install carried over.
7. Let the clock start work, which is the trigger nobody is watching.
8. Add skills and tool discovery, which are additive and change nothing already proven.

**A resolver phase used to sit at step 3 and no longer does.** With no `bindings` verb there was no
object anyone creates, and its one durable artefact — the ledger that says which conversation is
continuing which session — cannot be built before a provider has reported a session handle. It would
have been a ledger with nothing to put in it. Its two real parts are now where they can be proved: what
a turn resolves is decided in Phase 2, and the claim that four entry points reach one agent with
different providers is proved in Phase 3, where the entry points exist.

That sequence exposes agent and routing mistakes locally, keeps the provider CLIs native, and reaches a
real remote turn in **one** move from here — while leaving the additive work until after the risky part
is proved.

**What Phase 2 settled that Phase 3 can now lean on.** A channel does not need to know what a brain is:
it hands a turn a prompt and a conversation name, and reads the account afterwards. Which brain answers,
what it cost, whether it can be steered and where the conversation got to are all decided and recorded
below the channel. So Discord's work is delivery and presentation, and none of it is provider work.

**What Phase 2 leaves for Phase 3 to force.** `ask` runs the turn in the terminal that typed it, because
there is still nothing to ask a running gateway with. A channel is held open *by* the gateway, so Phase 3
is the first thing that cannot avoid the question — and it should answer it as a gateway surface rather
than by having a channel start turns of its own outside the thing that owns them.

## Evidence Used

- The command as it stands and as it will be typed: [`CLI.md`](CLI.md), generated from the parser, and
  [`.knowledge/guides/the-command-surface.md`](.knowledge/guides/the-command-surface.md) for the rules it
  obeys and the overlaps already removed from it.
- Live Python contracts and structure: [`.knowledge/BRIEF.md`](.knowledge/BRIEF.md),
  [`.knowledge/CODEMAP.md`](.knowledge/CODEMAP.md), and
  [`.knowledge/prd/`](.knowledge/prd/README.md)
- Current review ledger: [`SUGGESTIONS.md`](SUGGESTIONS.md)
- Current provider/channel research:
  [`.knowledge/research/2026-07-25-provider-cli-discord-interaction.md`](.knowledge/research/2026-07-25-provider-cli-discord-interaction.md)
- Node reference evidence: `../rundesk/docs/`, `../rundesk/probes/` and `../rundesk/test/`
