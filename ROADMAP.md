# Roadmap — Agent Profiles to Provider-Controlled Channels

**Planning baseline:** `8be7470` on 2026-07-25  
**Status:** Direction, not a ratified product contract

This roadmap gets Rundesk from a proven process/gateway/schedule substrate to named agent profiles that
can be reached through Discord, Slack, schedules and the terminal. It deliberately advances one
testable concept at a time. The Node Rundesk is evidence and prior art; it is not the architecture to
port.

## Direction

Build **agent profiles before Discord**, after restoring a trustworthy runtime baseline.

Profiles come first because a channel needs a stable identity, workspace and knowledge boundary to route
to. Discord should not be used to discover whether profile isolation, provider invocation or session
continuation works. Those are cheaper and more deterministic to prove locally.

The first useful vertical slice is:

```text
one profile -> one resolved binding -> one provider turn -> the terminal
```

Then prove the same path from a schedule and a fake channel before adding the Discord network boundary.
Do not build all providers, channels, tools and approval paths together.

## The Small Model

Four concepts are enough:

| Concept | Owns | Does not own |
|---|---|---|
| **Profile** | Name, gateway, profile home, workspace, knowledge, skills and tool grants | A permanent provider, model or channel |
| **Binding** | One entry point's profile, provider, model and permission policy | Profile knowledge or provider session history |
| **Conversation** | One external thread or terminal conversation and its provider-native session handle | Global profile configuration |
| **Run** | One admitted occurrence, immutable resolved settings, native events and outcome | Future changes to its binding |

A gateway belongs to a profile, but it may own multiple provider processes or turns selected by different
bindings. The provider CLI remains the agent brain.

For example, all four bindings below use the same profile knowledge:

| Entry point | Profile | Provider | Model |
|---|---|---|---|
| Discord `#operations` | `ava` | Claude | model selected for Discord |
| Slack `#planning` | `ava` | Codex | model selected for Slack |
| Schedule `morning-review` | `ava` | Codex | lower-cost scheduled model |
| Schedule `weekly-research` | `ava` | Grok | research model |

Provider and model are resolved when a run is admitted and written into that run's record. Changing a
binding affects new work. It must not silently change an active conversation or resume a session through
a different provider. A provider change starts a new provider session unless a future, explicitly tested
migration says otherwise.

Profile defaults may be a convenience fallback, but provider and model are not intrinsic profile
identity. An inbound chat message cannot change them; only an authorized binding/configuration change or
an authorized local invocation can.

## Boundaries to Keep

- Keep the provider's native conversation, context, tools, permissions and session loop intact. Rundesk
  invokes it, supplies its isolated environment, streams its native events, sends supported input and
  records outcomes. It does not reconstruct an agent loop.
- Preserve the native event record. Add only the small Rundesk envelope needed to correlate profile,
  binding, conversation, run and delivery. Do not invent a large common event vocabulary before two real
  consumers prove it is needed.
- Keep channel presentation out of provider adapters. A fake channel and Discord should consume the same
  provider/run surface.
- Keep provider installations, adapters and private runtime homes outside the profile home. Rundesk may
  associate an isolated runtime home with a profile/provider pair, but that managed state is not profile
  knowledge and does not make the provider part of the profile.
- Define profile isolation narrowly in the first release: separate automatic context/skill discovery,
  configuration, session history and default cwd. It is not an OS filesystem sandbox. A provider's native
  file or shell tools may reach sibling or owner paths unless a later phase adds and proves an enforcement
  boundary; remote access must never be described as filesystem containment.
- Keep schedule time arithmetic unchanged. A schedule can eventually name a binding or run request
  because its current payload is intentionally opaque to the scheduler.
- Keep persistence small and file-based until measured behavior requires something else. A run ID and
  minimal routing/session records do not require a database.
- Treat component ontology, persisted schemas and migrations as owner decisions before implementation.
  This roadmap does not add or ratify `agent-`, `provider-` or `channel-` components.

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

## Phase 0 — Restore a Trustworthy Gate and Declare the Surface

**Outcome:** the current substrate has one unambiguous green gate, and the owner has approved how the next
concepts appear in the product. No profile or channel behavior is added.

### 0A. Make the gate truthful

At this baseline, `requirements.txt` declares `discord.py==2.7.1`, the repository `.venv` can run the
gateway suite, but the CI test matrix runs plain Python without installing declared requirements. A clean
plain-Python gateway test therefore fails its runtime fitness check. Decide and prove the one supported
test environment before treating any later result as green. Do not remove or move the dependency merely
for cleanliness.

### 0B. Declare the concepts and their command surface

The owner must approve the component ontology and persisted-state boundaries before implementation.
R-CMD-1 and R-CMD-2 also require every future operation to be listed and described by the command from
the outset. Decide whether the existing planned verbs will manage each operation or whether additional
planned verbs are needed for:

- profile creation, listing, inspection and diagnosis;
- binding creation, provider/model selection and removal;
- channel authorization and channel-to-binding management;
- schedule-to-binding management;
- run inspection, continuation and replay.

The roadmap does not choose names for undeclared operations. Their approved syntax is registered as
truthfully unavailable before the first implementation phase relies on a hidden configuration path.

### Exit proof

- The documented local and CI commands use the same dependency assumptions and pass from a clean checkout.
- The owner-approved ontology, persisted boundaries and complete planned CLI surface are recorded.
- Existing process, gateway and schedule contracts remain green.

## Phase 1 — Create the Profile Boundary

**Outcome:** Rundesk can create, list and diagnose an isolated profile without running a provider.

Start with the already-declared `new`, `agents` and `doctor` command intentions. Exact syntax and persisted
layout are decided in the draft PRD before implementation.

A profile scaffold should contain:

```text
<profile>/
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
profile knowledge. `SOUL.md`, `USER.md` and `MEMORY.md` are loaded through that routing rather than
assuming each provider recognizes those filenames.

Rundesk-managed provider homes are outside this profile scaffold and isolated by profile/provider pair.
Authentication sharing or isolation is a separate, explicit decision: probes already show that
config/home variables affect discovery and credentials, so Rundesk must never accidentally expose the
owner's global skills or history through automatic discovery.

Profile-owned knowledge must also have an explicit lifecycle. It must live outside removable install
files or be preserved by ordinary uninstall, with deletion limited to a separately authorized purge.
Profile names must not collide with gateway history sidecars or reserved suffixes.

Before a supervised profile is considered isolated, local commands and its launchd job must resolve the
same authoritative state/profile directories. These profile-entry risks are currently recorded by
findings 18–19, 22 and 28; reproduce them on the implementation baseline rather than copying a suggested
fix.

### Tests

- Refuse names and symlinks that escape the profile root.
- Refuse names that collide with reserved state/history filenames.
- Create the same profile idempotently without overwriting edited knowledge.
- Prove two profiles have different workspace and provider-home paths.
- Prove the gateway receives the same resolved profile paths when supervised as when run locally.
- Prove ordinary uninstall/update preserves profile knowledge, workspace, bindings and history.
- Prove `doctor` detects missing files, broken links, unusable provider homes and an unfit runtime without
  starting a provider or changing state.

### Exit proof

A fresh profile can be created, inspected and diagnosed entirely offline. Profile management operations
cannot resolve one profile's owned paths as another's. Provider filesystem containment is explicitly
deferred; this phase proves only separate discovery, configuration, session and cwd defaults.

## Phase 2 — Resolve Bindings Independently of Providers

**Outcome:** terminal, schedule and future channel sources can select different providers/models for the
same profile through one pure resolver.

Define the smallest binding record that can answer:

- which profile receives this source;
- which provider and optional model are selected;
- which permission policy applies;
- which external conversation key, if any, owns continuation.

Resolution produces an immutable run specification containing at least `run_id`, profile, binding,
source/conversation, provider, model, cwd and provider home. Provider session handles belong to the
conversation and provider combination; they are never reused across providers.

Do this first with fake providers. Do not add Discord or invoke a real CLI.

The `run_id` must also become the durable correlation key in live state, history and related logs before a
channel can attach a question, answer or outcome to it. This is the narrow change described by finding 29;
it does not require a new persistence engine.

### Tests

- Discord, Slack and two schedules resolve to the same profile cwd/knowledge but different requested
  provider/model combinations.
- Binding selection does not copy or fork profile knowledge.
- An unknown provider, model, profile or source fails before process creation.
- A binding edit does not mutate an already admitted run.
- A provider change cannot resume the old provider's session.
- Untrusted message text cannot override provider, model or permission policy.

### Exit proof

One table-driven offline test demonstrates the four-entry-point example above, including exact resolved
`argv`, environment, cwd and session key through stand-in executables.

## Phase 3 — Bootstrap Knowledge, Skills and Tool Discovery

**Outcome:** every provider can be given the same profile knowledge and a basic skill without Rundesk
becoming a second skills or tools engine.

Add one basic `SKILL.md` template, one canonical profile-visible skills library and only the provider
discovery links that live probes prove. Current Node probes suggest `.claude/skills/` and
`.agents/skills/` links, while a bare `skills/` directory is not enough; re-probe current CLI versions
before making that a guarantee.

The first tool discovery kit should only inventory, search and explain granted tools. It should not
duplicate provider-native file/shell tools, dynamically load plugins or execute arbitrary new actions.
Tool execution and richer grants wait until one provider turn is proven.

### Tests and probes

- Offline tests prove scaffold idempotency, link resolution and profile-specific grants.
- Rundesk-managed config does not automatically discover ungranted owner-level skills.
- A canary profile proves each provider follows `AGENTS.md` to `SOUL.md`, `USER.md` and `MEMORY.md`.
- A basic skill canary proves actual provider discovery from the profile workspace.
- Saved, sanitized probe output records provider version, invocation and result.

### Exit proof

Each supported provider has a current capability row marked proven, unsupported or unknown. Rundesk does
not claim that a provider loaded a rule or skill based only on file presence.

## Phase 4 — Control One Provider Through the Terminal

**Outcome:** one profile can complete and resume one provider-native turn while Rundesk streams and
correlates its events.

Do not choose the first adapter because the Node build chose it. Probe the installed Claude, Codex and
Grok CLIs against the same minimum contract:

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

Choose the smallest currently documented surface that passes every required item above. Implement only
that adapter and `rundesk run <profile> ...` to the terminal. Mid-turn send is not promised until a real
probe proves it; some headless providers turn questions into final prose or require stop/resume.

### Tests

- Replay captured native streams, including malformed, duplicate, oversized and partial records.
- Prove model/home/cwd arguments through a stand-in executable.
- Prove native events retain their original record plus Rundesk correlation metadata.
- Prove stop ends the provider and its tool descendants.
- Prove secrets and raw tool payloads are not printed to a remote-safe presentation by default.
- Prove a restart either resumes the same recorded run or reports a durable terminal interruption; it
  never silently starts the turn again.

### Exit proof

A manual canary completes one local turn, resumes it, and correlates its native stream, transcript,
session and outcome by one run ID. The same sanitized stream passes offline replay.

## Phase 5 — Exercise Two Trigger Types Without a Network

**Outcome:** the resolved run path works from a schedule and a fake channel, not only from the CLI.

First let one schedule name a binding and run the proven provider under an autonomous permission policy.
Then connect a fake channel to a fake or replayed provider. This separates routing and delivery failures
from Discord failures.

Any change to existing schedule files is a persisted-schema decision and requires owner approval plus a
tested migration or an additive format that keeps old schedules truthful.

Before reconnectable channel delivery, interruption history must resist lost updates, logs must have one
bounded source, and stale/interrupted runs must be readable and reconciled. These are the current findings
11, 17 and 26–27; they are just-in-time gates for this phase rather than blockers for the offline profile
scaffold.

Before enabling provider-backed schedules, the scheduler must also prove that it examines work
immediately after gateway start, agrees on cron next-time and firing semantics, reconciles a stale
`started` outcome after a crash, and cannot confuse Rundesk options with provider arguments. These are
the current risks recorded as findings 24–26 and 31.

### Tests

- `schedule A` and `schedule B` share one profile but resolve different provider/model selections.
- Existing never-late and never-overlap rules still hold.
- An interactive request in an autonomous schedule becomes a clear outcome instead of waiting forever.
- Fake-channel disconnect, slow delivery and retry exhaustion do not end the provider turn.
- Reconnecting the fake channel identifies the existing conversation/run instead of duplicating it.

### Exit proof

One schedule run and one fake-channel conversation pass through the same resolver, run record and provider
adapter used by the terminal.

## Phase 6 — Add Basic Discord Communication

**Outcome:** one authorized Discord channel/thread can send text to one proven provider binding and receive
streamed results. Approvals and provider questions remain explicitly unsupported in this phase.

Build the Discord wire against a fake brain first, then attach it to the Phase 4 adapter. The already
pinned `discord.py` dependency must earn its place through the same install and test path as the product;
do not add a second Discord stack.

The first slice needs:

- explicit Discord channel/thread to binding lookup;
- authorized user/server/channel checks before run admission;
- prompt acknowledgement within Discord's limit;
- coalesced text edits and bounded/safe handling of long output;
- an asynchronous delivery queue whose failure cannot kill provider work;
- local retention of the final run outcome when Discord is unavailable.

### Exit proof

A fake Discord integration proves all routing and failure cases offline. A manual private-server canary
then sends one message, observes streamed progress and receives one final answer correlated to the same
run ID.

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

**Outcome:** Claude, Codex and Grok can each be selected by bindings, and a second channel can reuse the
same channel contract without profile changes.

Add the remaining providers one at a time behind the Phase 4 conformance suite. Preserve real differences:
do not synthesize tool events a provider does not emit, claim interactive input a protocol cannot accept
or hide cumulative usage behind guessed per-turn numbers.

Only after Discord and the fake channel share a proven surface should Slack be added. A Slack binding
selects its provider/model exactly as Discord and schedules do; it does not add Slack fields to the
profile.

### Exit proof

- Each provider passes the supported subset of the same invocation/replay/recovery suite.
- `doctor` reports installed version and proven/unsupported capabilities for each provider.
- One profile is exercised through at least two channels and two schedules with different provider/model
  selections and unchanged profile knowledge.
- Adding the second real channel requires a wire/presentation adapter, not provider or profile changes.

## Explicitly Deferred

- A database, distributed workers or a general queue service.
- Dynamic provider/channel plugin loading.
- A Rundesk-built conversational or tool-execution loop.
- Automatic cross-provider conversation migration.
- A rich common event taxonomy before real adapters require it.
- Arbitrary remote changes to provider, model, permissions or tool grants.
- Executing every discovered tool before inventory, grants and one provider turn are proven.

## Ready-for-Next-Phase Verdict

Rundesk is ready to **plan and begin the foundation/profile work**, but it is not ready to begin Discord
or a live provider adapter on the current baseline.

The next implementation sequence should be:

1. Make the dependency/test gate truthful and declare the approved product/CLI surface.
2. Ratify and build the profile scaffold with discovery/config/session isolation.
3. Prove binding and run-ID resolution with fakes.
4. Close the provider-facing runtime risks immediately before the first live provider turn.

That sequence exposes profile and routing mistakes locally, keeps the provider CLIs native, and reaches
Discord through small demonstrations instead of one large integration.

## Evidence Used

- Live Python contracts and structure: [`.knowledge/BRIEF.md`](.knowledge/BRIEF.md),
  [`.knowledge/CODEMAP.md`](.knowledge/CODEMAP.md), and
  [`.knowledge/prd/`](.knowledge/prd/README.md)
- Current review ledger: [`SUGGESTIONS.md`](SUGGESTIONS.md)
- Current provider/channel research:
  [`.knowledge/research/2026-07-25-provider-cli-discord-interaction.md`](.knowledge/research/2026-07-25-provider-cli-discord-interaction.md)
- Node reference evidence: `../rundesk/docs/`, `../rundesk/probes/` and `../rundesk/test/`
