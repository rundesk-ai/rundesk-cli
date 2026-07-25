# Roadmap — Agents to Provider-Controlled Channels

**Planning baseline:** `1046f3f` on 2026-07-25  
**Status:** Direction, not a ratified product contract

**Starting implementation? Read in this order:** this file's Direction and Phase 1; then
[`CLI.md`](CLI.md) for every operation as it will be typed;
[`.knowledge/guides/the-command-surface.md`](.knowledge/guides/the-command-surface.md) for why the
surface is shaped that way and which overlaps were already removed; then the two drafts Phase 1
ratifies, `.knowledge/prd-drafts/agent-home.md` and `agent-gateway.md`.

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
phase. That is why Phase 3 does not end when one provider works.

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
- `channels` stays **registered and refusing** through this phase. Its shape is settled in Phase 4, which
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
  re-proven against installed versions. Phase 3 re-probes before anything claims it.
- Finding 28's larger half — a command reading a supervised gateway's directories out of its own job —
  is not done. What this phase owed it is: the job carries the agent's directories, so the two agree.
- Running a schedule by hand happens in the terminal, not inside the agent's gateway. There is nothing to
  ask a running gateway with, and inventing one was not this phase's work.

## Phase 2 — Resolve a Binding Without a Provider Anywhere Near It

**Outcome:** terminal, schedule and future channel sources can select different providers/models for the
same agent through one pure resolver.

**A binding is resolved, never maintained.** There is no `bindings` verb and no object a consumer
creates: which provider and model answer is an option where the entry point is made — on a channel, on a
schedule, on `ask` — and the agent supplies whatever was left out. What this phase builds is the
resolver that turns those into one immutable record per run, and nothing a person types.

**The resolver enumerates nothing.** It never holds a list of providers, and never a list of models. A
provider is a name it carries through: one of the shipped adapters, or a path to a program somebody
wrote. So "a provider Rundesk does not recognise" is not an error condition — it is the ordinary case
the seam exists for, and the only failure is nothing runnable being there. A model is likewise a word
the adapter understands and the resolver does not read; validating it here would mean tracking every
vendor's catalogue forever, and refusing a model that shipped this morning.

The same goes for how much of the machine a turn may touch: every brain scopes capability its own way,
so what is resolved is a posture carried to the adapter, never a tool list Rundesk believes in.

Define the smallest binding record that can answer:

- which agent receives this source;
- which provider and optional model are selected;
- which permission policy applies;
- which external conversation key, if any, owns continuation.

Resolution produces an immutable run specification containing at least `run_id`, agent, binding,
source/conversation, provider, model, cwd and provider home. Provider session handles belong to the
conversation and provider combination; they are never reused across providers.

Do this first with stand-in adapters — small programs, which is what every adapter is, so the fake and
the real differ in what they run and in nothing else. Do not add Discord or invoke a real provider CLI.

The `run_id` must also become the durable correlation key in live state, history and related logs before a
channel can attach a question, answer or outcome to it. This is the narrow change described by finding 29;
it does not require a new persistence engine.

### Tests

- Discord, Slack and two schedules resolve to the same agent cwd/knowledge but different requested
  provider/model combinations.
- Binding selection does not copy or fork an agent's knowledge.
- An unknown **agent** or source fails before anything is started.
- A provider that is a path to a program resolves, and one that is nothing runnable fails before a
  process is created — the only two outcomes, because there is no list of providers to be absent from.
- A model Rundesk has never heard of resolves and is carried through unread.
- A binding edit does not mutate an already admitted run.
- A provider change cannot resume the old provider's session.
- Untrusted message text cannot override provider, model or permission policy.
- Nothing in the resolver names a vendor, so a new adapter needs no change here at all.

### Exit proof

One table-driven offline test demonstrates the four-entry-point example above, including exact resolved
`argv`, environment, cwd and session key through stand-in executables.

## Phase 3 — Open the Provider Seam, and Put One Brain Behind It

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

**Usage is captured here, because here is where the stream first exists.** Every provider reports it and
each reports it differently, and the Node build already proved the two traps: Codex's
`turn.completed.usage` is the running total for the whole *conversation*, not the turn — three one-word
replies reported 5, 10, 15 — so a turn's own share is the difference from the last one, and a gateway
restart loses that running total; and Claude bills cache *creation* as fresh input, above the standard
rate, so it cannot be folded in with cache reads. What is drafted is `agent-usage` (`R-USE-n`), and its
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
- **An adapter this code has never seen carries a whole turn**, written against the guide alone and
  living outside the tree — the claim the whole seam rests on.
- An adapter that runs no tools produces a complete turn, with that work simply absent.
- An adapter emitting a record we do not know keeps it in the run, shows it to nobody, and finishes.
- An adapter that names no model leaves none claimed, rather than the one that was asked for.
- Ending a turn ends the adapter and every process it started.
- One adapter cannot reach another agent's workspace or provider home.
- No vendor's flag, session file or permission mode appears outside its own adapter.

### Exit proof

A manual canary completes one local turn, resumes it, and correlates its native stream, transcript,
session and outcome by one run ID. The same sanitized stream passes offline replay.

**And the seam is proved open, not just designed open:** a second adapter, written from
[the guide](.knowledge/guides/write-a-provider-adapter.md) by someone who has not read this codebase,
runs a whole turn with nothing in Rundesk changed to accommodate it — and passes the same conformance
suite the shipped one does. Until that has happened, the seam is a hope.

## Phase 4 — Add Basic Discord Communication

**Outcome:** one authorized Discord channel/thread can send text to one proven provider binding and receive
streamed results. Approvals and provider questions remain explicitly unsupported in this phase.

What a channel must do is drafted in `channel-messaging` (`R-CH-n`) and what Discord does with it in
`channel-discord` (`R-DIS-n`), both carried over from the Node build, which had all of this working:
threads opened on being named, reactions marking a turn seen, finished, stopped or failed, and steering
through Discord's own commands rather than words typed into the chat.

Build the Discord wire against a fake brain first, then attach it to the Phase 3 adapter. The already
pinned `discord.py` dependency must earn its place through the same install and test path as the product;
do not add a second Discord stack.

**The fake channel is this phase's offline half, not a phase of its own.** Every routing and failure case
— disconnect, slow delivery, retry exhaustion, reconnecting to an existing conversation — is proved
against it before a real token is used, so a Discord failure is never confused with a routing one. What
the fake cannot prove is Discord's own limits, and that is what the canary at the end is for.

### What `channels add` takes

A channel is **named the way a schedule is** — you give it a name to refer to it by later, and what it
is comes from `--kind`. Each kind then needs different things, and those are its own options:

```text
rundesk channels ava add ops   --kind discord --server <id> --channel <id> --allow <user> …
rundesk channels ava add plans --kind slack   --workspace <id> --channel <id> --allow <user>
```

Exact field names are settled **here**, against the installed Discord API rather than from a
specification read early. Until this phase, `channels` is registered and refuses truthfully. What was
decided in advance is only the shape, and one hard rule:

- **A secret is never an argument.** A bot token on a command line is readable by anything on the machine
  through the process list and is written into shell history. Tokens are read from an environment
  variable or a file the owner already controls, or asked for on a terminal — never `--token <value>`,
  and never stored anywhere Rundesk would print.
- Who may use a channel is part of adding it, not a later step. A channel authorized for nobody reaches
  nobody, which is the safe direction to fail in.
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
provider's permission model, so they belong here while questions and approvals wait for Phase 7. What a
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

### Exit proof

A fake Discord integration proves all routing and failure cases offline. A manual private-server canary
then sends one message, observes streamed progress and receives one final answer correlated to the same
run ID.

## Phase 5 — Let the Clock Start Work

**Outcome:** an agent does work because the time came, through the same resolver, run record and
provider adapter that Discord and the terminal already use.

One schedule names a binding and runs the proven provider under an autonomous permission policy. The
fake channel was Phase 4's offline half, so what is left here is the trigger that has no one watching
it — which is the one that must never fail silently.

Any change to existing schedule files is a persisted-schema decision and requires owner approval plus a
tested migration or an additive format that keeps old schedules truthful.

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

### Exit proof

One scheduled run passes through the same resolver, run record and provider adapter that Discord and the
terminal already used — and its outcome is readable the next morning without a terminal having been open.

## Phase 6 — Bootstrap Knowledge, Skills and Tool Discovery

**Outcome:** every provider can be given the same agent's knowledge and a basic skill without Rundesk
becoming a second skills or tools engine.

**This is additive, which is why it waits.** An agent that loads a skill is a better agent, not a
different one: nothing about the channel, the turn, the run record or the resolver changes when this
lands. Everything before it was work that could not be added later without redoing it, and this is not.
The corollary is a real constraint — if a change here forces a change in Phase 3 or 4, it is not a skill
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

## Phase 7 — Questions, Approvals and Recovery

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

## Phase 8 — Add Provider and Channel Breadth One Adapter at a Time

**Outcome:** Claude, Codex and Grok can each be selected where an entry point is made, and a second
channel can reuse the same channel contract without changing the agent.

Add the remaining providers one at a time behind the Phase 3 conformance suite — which by now a
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

Phases 0 and 1 are done, so Rundesk is ready to **resolve a binding**. It is not ready to begin Discord or
a live provider adapter.

The next implementation sequence should be:

1. ~~Make the dependency/test gate truthful and declare the approved product/CLI surface.~~ **Done.**
2. ~~Build the agent and its home, and refactor the command surface so agents are what a person operates
   and gateways are how they run.~~ **Done.**
3. Prove binding and run-ID resolution with fakes — the smallest thing that lets a source pick a provider.
4. Close the provider-facing runtime risks, then take one provider turn to the terminal.
5. **Reach that agent through Discord**, so the product is tested where it is actually used.
6. Add skills and tool discovery, which are additive and change nothing already proven.

That sequence exposes agent and routing mistakes locally, keeps the provider CLIs native, and gets to a
real remote turn in four moves instead of six — while leaving the additive work until after the risky
part has been proved.

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
