# Research: how other gateways run a provider process

**Established 2026-08-05**, by reading two comparable products at local checkouts and comparing them
against the previous rundesk build. Everything here is **read off source**, not measured and not
documented behaviour — where a claim is a line of code it is cited by path, and where it is an inference
it says so.

| | Checkout | Upstream |
|---|---|---|
| **OpenClaw** | `0920946f835` (2026-08-05) | https://github.com/openclaw/openclaw |
| **Hermes Agent** | `a61183b56` (2026-08-05) | https://github.com/NousResearch/hermes-agent |
| **rundesk (previous build)** | `src_old/` | [`2026-08-05-the-old-builds-provider-system.md`](2026-08-05-the-old-builds-provider-system.md) |

[`2026-07-29-what-a-gateway-tells-its-agent.md`](2026-07-29-what-a-gateway-tells-its-agent.md) already
compares what these two put *in front of* an agent. This page is the other half: what they do to **run
one** — the process, the seam, the failure handling and the money.

---

## The short version

**The most important finding is structural, and it is about what a "provider" even is.**

|  | What a provider *is* | Where vendor knowledge lives |
|---|---|---|
| **OpenClaw** | an **HTTP API** it calls itself, running its own agent loop — *plus* a second, bolted-on notion of an external **CLI backend** | `packages/ai/src/providers/*` for the API path; a ~40-field declarative config table for the CLI path |
| **Hermes** | an **HTTP API** it calls itself, running its own agent loop — *plus* per-CLI hand-written stdio clients | a `ProviderProfile` dataclass with override hooks, discovered as plugins; and one bespoke module per CLI |
| **rundesk** | a **program it runs** | one executable file per vendor, importing nothing |

Both of the others are *inference hosts*. They own the loop, the tool calls, the context window and the
bill. rundesk owns none of that by design — it runs the vendor's own CLI, which owns its own loop, and
rundesk keeps the process, the records and the money-shaped facts the CLI reports.

**That difference makes most of their provider code inapplicable and their process code directly
applicable.** Everything below is filtered on that basis.

**The three things worth taking:**

1. OpenClaw's **supervisor** shape — `spawn(input) → ManagedRun`, a run registry with an explicit state
   machine, a `scopeKey` that can displace a previous run, and a `TerminationReason` enum that says *which*
   of six ways a run ended.
2. Hermes's **deliberate rejection of asyncio** for driving a stdio child, written down with the reason —
   which independently agrees with this build already being synchronous.
3. Hermes's **wedge watchdog** and **restart-loop breaker**, both of which exist because a supervised
   process that is alive-but-stuck is invisible to `KeepAlive`.

**And the two to refuse outright:**

1. OpenClaw's **declarative CLI-backend config table** — the alternative shape to adapter-as-program, and
   a live demonstration of why it does not hold.
2. OpenClaw's **vendor impersonation on subscription credentials** — the clearest terms-of-service line in
   either codebase, and it is on the wrong side of it.

---

## OpenClaw

### 1 · The supervisor is a real abstraction, and it is the best thing here

`src/process/supervisor/types.ts` is 120 lines and defines the whole surface:

```ts
export interface ProcessSupervisor {
  spawn(input: SpawnInput): Promise<ManagedRun>;
  cancel(runId: string, reason?: TerminationReason): void;
  cancelScope(scopeKey: string, reason?: TerminationReason): void;
  getRecord(runId: string): RunRecord | undefined;
}
```

Four things in it are worth carrying, and three of them the previous rundesk build did not have.

**A run has a state machine, and it is written down.**

```ts
type RunState = "starting" | "running" | "exiting" | "exited";
type TerminationReason =
  | "manual-cancel" | "overall-timeout" | "no-output-timeout"
  | "spawn-error" | "signal" | "exit";
```

rundesk's `process.Result` carried five reasons — `finished`, `failed`, `ended`, `silent`, `overran` — but
had no *state*, so "starting" and "running" were not distinguishable from outside and nothing could ask
about a run except the thing awaiting it. `RunRecord` also carries `startedAtMs`, `lastOutputAtMs`,
`createdAtMs`, `updatedAtMs`, `pid` and `processGroupId` — enough for a third party to report on a run it
does not own.

**`scopeKey` with `replaceExistingScope` is the missing primitive.** A scope is a name a run claims; asking
for a run under a scope that is occupied can *displace* the occupant. That is exactly the shape rundesk
needs — one turn per conversation, where a new message either queues or replaces — and the previous build
solved it three separate ways: a funnel keyed by name inside the gateway, a per-conversation `WAITING`
queue in `answering.py`, and nothing at all for `rundesk ask` typed at a terminal, *which could therefore
start a second turn in a conversation a gateway was already running.*

**The no-output timeout is separate from the overall timeout, and both are per-run.**
`resolveElapsedTimeoutReason` reads two deadlines and reports which one elapsed. rundesk had the same two
numbers as module constants; OpenClaw makes them arguments, and its CLI-backend config tunes them
**differently for fresh and resumed runs** — `reliability.watchdog.{fresh,resume}` with a ratio, a floor
and a ceiling each. That distinction is real: a resumed session's first token arrives much sooner than a
fresh one's, so one window fits both badly.

**Captured output is bounded with a visible marker.** `appendCapturedOutput` writes
`[openclaw: captured stdout truncated to last N chars]` into the retained text. rundesk bounds the same way
and says nothing in the retained tail — the loss is only in `Gap` records on the parsed stream, so a
*person* reading the diagnosis tail cannot tell it was clipped.

`GRACEFUL_CANCEL_TIMEOUT_MS = 5000` matches rundesk's `GRACE_SECONDS = 5.0` exactly, arrived at
independently.

### 2 · Work admission is a first-class concept, and rundesk has nothing like it

`src/process/gateway-work-admission.ts` holds a process-wide admission gate with a `GatewayDrainingError`,
reference-counted active root work, drain waiters, and a `suspendPhase` of `accepting | preparing |
prepared`. Restart and suspend both *close admission first*, drain, then act.

`src/process/lanes.ts` names seven queues that must not interleave — `main`, `system-agent`, `cron`,
`cron-nested`, `subagent`, `nested`, `skill-workshop-review`.

The previous rundesk build's shutdown was: cancel every task, look again three times (`_UNWINDING = 3`) for
work that appeared while cancelling, then exit. It had no way to *stop accepting* — which is why the
"look again" loop exists at all, and why `turn._settled_whatever_happens` had to be written: work could
still be admitted during the shutdown that was trying to end it.

**This is the cleanest answer found anywhere to a question that is already live in this build.** The
gateway's `ExitTimeOut` is 25 seconds and `STOPPING_WITHIN` is 20; a provider turn takes minutes. Closing
admission before draining is what makes the difference between a shutdown that is bounded and one that
merely hopes.

### 3 · The CLI-backend config table — the alternative shape, and why it fails

`src/plugins/cli-backend.types.ts` is the direct competitor to adapter-as-program. A CLI backend is
declared as **data**, not code:

```ts
type CliBackendConfig = {
  command: string;  args?: string[];
  output?: "json" | "text" | "jsonl";
  resumeOutput?: "json" | "text" | "jsonl";
  jsonlDialect?: "claude-stream-json" | "gemini-stream-json";
  liveSession?: "claude-stdio";
  input?: "arg" | "stdin";  maxPromptArgChars?: number;
  modelArg?: string;  modelAliases?: Record<string, string>;
  sessionArgs?: string[];  resumeArgs?: string[];  forkArg?: string;
  sessionMode?: "always" | "existing" | "none";  sessionIdFields?: string[];
  systemPromptArg?: string;  systemPromptFileArg?: string;
  systemPromptFileConfigArg?: string;  systemPromptFileConfigKey?: string;
  systemPromptMode?: "append" | "replace";  systemPromptWhen?: "first" | "always" | "never";
  imageArg?: string;  imageMode?: "repeat" | "list";  imagePathScope?: "temp" | "workspace";
  serialize?: boolean;  env?: …;  clearEnv?: string[];  reliability?: …;
};
```

Forty-odd fields, and then escape hatches on top of them: `normalizeConfig`, `transformSystemPrompt`,
`resolveExecutionArgs`, `prepareExecution`, `textTransforms`, `bundleMcpMode`. The whole `CliBackendPlugin`
type is 320 lines.

**Two lines in it are the verdict on the approach.** `jsonlDialect: "claude-stream-json" |
"gemini-stream-json"` and `liveSession: "claude-stdio"` are **vendor names in the core type**. The config
table was supposed to keep vendor knowledge out; the stream shapes and the long-lived-process behaviour
would not fit into data, so they became enum members instead. The result is *both* costs at once — a
40-knob configuration surface **and** vendor names in the core, plus a generic runner that has to interpret
every combination of knobs.

The declarative-adapter shape also cannot express the things that actually differ between the four brains
rundesk measured:

- Claude's reply arriving three times with two copies byte-identical (a dedupe decision, not a flag);
- Codex's usage being a **running total** that must be subtracted against per-session state the adapter
  keeps in its own home (arithmetic and durable state, not a flag);
- Grok's `--tools` being **accepted in silence and inert** on the ACP transport (a fact you have to know,
  not a value to pass);
- Claude's `steer` needing an `interrupt` control request, an acknowledgement drain, *then* the message
  (a protocol exchange, not an argument).

**Verdict: adapter-as-program is the right shape and this is the evidence.** OpenClaw's table is what
happens when the seam is data instead of a process boundary.

### 4 · What OpenClaw does about a mid-turn interrupt

`packages/agent-core/src/turn-interruption.ts`. An aborted turn appends a custom message into the
transcript:

```
<turn_aborted>
The previous turn was interrupted. Any running background processes may still be active.
If any tools or commands were aborted, they may have partially executed.
</turn_aborted>
```

with an explicit carve-out — `isTurnHandoffAbort` — so a *deliberate* stop does not get the warning,
because *"the next turn would otherwise be told tools may have partially executed after a clean,
deliberate stop."*

**This is the piece the previous rundesk build did not have and needed.** Its recovery prompt said
`CONTINUE = "Continue the interrupted work from where the previous gateway stopped. Do not repeat actions
already completed."` — which is the same idea, but delivered as *the turn's prompt* rather than as a
message in the transcript. That is what forced `stands_alone` to exist: a recovery prompt is not a
question, so it must never be retried on a fresh session, and the code had to grow a flag to say so.

### 5 · Vendor impersonation — the terms-of-service line

`packages/ai/src/providers/anthropic.ts`. On `sk-ant-oat…` subscription credentials the transport
prepends `You are Claude Code, Anthropic's official CLI for Claude.` plus a billing header, sets
`user-agent: claude-cli/2.1.75`, and renames tools through `toClaudeCodeName`, under a source comment
reading `// Stealth mode: Mimic Claude Code's tool naming exactly`.

That is a third-party client presenting itself as a vendor's first-party CLI in order to use subscription
credentials on an API path. It is written down here because **it is precisely the thing rundesk's
architecture makes unnecessary**: rundesk runs the vendor's own CLI, signed in by the owner, through the
vendor's own published headless interface. Nothing is impersonated because nothing is substituted.

The [companion note on this already flagged it](2026-07-29-what-a-gateway-tells-its-agent.md) under *what
to avoid*. It is repeated here because the provider layer is where it would be reachable.

---

## Hermes Agent

### 1 · The provider profile — declarative, plugin-discovered, and about APIs

`providers/base.py` + `providers/__init__.py`. One `ProviderProfile` dataclass per inference provider,
holding auth type, base URL, model catalog, header quirks and five override hooks
(`prepare_messages`, `build_extra_body`, `build_api_kwargs_extras`, `fetch_models`, `get_hostname`).
Profiles live as plugins under `plugins/model-providers/<name>/` and under
`$HERMES_HOME/plugins/model-providers/<name>/`, discovered lazily on first access.

Its own README states the design rule plainly: *"Provider profiles are DECLARATIVE — they describe the
provider's behavior. They do NOT own client construction, credential rotation, or streaming."*

**Two things transfer and the rest does not.** The transferable half is **a per-user plugin directory
searched beside the bundled one**, which is how a third party ships a provider without touching the
product — rundesk's equivalent is already the path branch in `provider.program()`, and a per-install
adapters directory under `RUNDESK_HOME` would complete it. The non-transferable half is everything else:
these are HTTP endpoints, not processes.

The README also documents the cost of the approach honestly — nine named downstream consumers each read
the registry (`auth.py`, `models.py`, `doctor.py`, `config.py`, `runtime_provider.py`,
`model_metadata.py`, `auxiliary_client.py`, `transports/chat_completions.py`, `run_agent.py`). **A
declarative provider table becomes a dependency of every layer that touches providers.** An executable
adapter has exactly one consumer.

### 2 · Driving a CLI: synchronous, with reader threads, and the reason is written down

`agent/transports/codex_app_server.py` is the closest thing in either product to what rundesk does — a
JSON-RPC 2.0 client over NDJSON on a spawned `codex app-server` stdio child. Its threading model:

> - Spawning thread (caller) drives request/response pairs synchronously.
> - One reader thread parses stdout, dispatches replies to the right pending future, and routes
>   notifications + server-initiated requests to bounded queues that the caller drains on their own cadence.
> - One reader thread captures stderr for diagnostics.
>
> **Intentionally NOT async.** AIAgent.run_conversation() is synchronous and runs on the main thread;
> layering asyncio just to drive a stdio child creates surprising interrupt semantics. We use blocking
> queues with timeouts and rely on `turn/interrupt` for cancellation.

**This is an independent arrival at the choice this build has already made.** `utils/programs.py` and
`gateways/host.py` are synchronous; the previous rundesk build was 1207 lines of asyncio and roughly a
third of its scar tissue was asyncio-specific. Hermes reached the same conclusion from the other end and
named the cost — *surprising interrupt semantics* — which is exactly what
`turn._settled_whatever_happens` was written to survive.

Three details worth copying from the same file:

- **Bounded queues between the reader thread and the caller**, drained on the caller's own cadence — the
  same shape as rundesk's `Held`, reached without asyncio.
- **stderr captured separately for diagnostics**, and a tail of it (`_STDERR_TAIL_LINES = 12`) attached to a
  user-facing error when nothing more specific classified the failure. rundesk kept 20
  (`TROUBLE_KEPT`) for the same purpose.
- **A minimum vendor version is a constant** — `MIN_CODEX_VERSION = (0, 125, 0)` — checked at install
  time. rundesk kept `cli-versions.lock` beside its golden streams and never checked one at runtime.

### 3 · The spawn environment — deny-list, and the incident behind it

`tools/environments/local.py::hermes_subprocess_env(*, inherit_credentials=False)`. It starts from
`os.environ.copy()` and strips in two tiers: Tier 1 always (gateway bot tokens, GitHub auth, remote-compute
secrets), Tier 2 unless the caller opts in (LLM provider keys and tool secrets). Plus a prefix sweep and an
`_is_hermes_internal_secret` predicate for dynamic names.

The comment at the codex spawn site records the incident:

> the previous `os.environ.copy()` also handed it every Tier-1 Hermes secret — gateway bot tokens, GitHub
> auth, Modal/Daytona infra tokens, the dashboard session token, `AUXILIARY_*` side-LLM keys,
> `GATEWAY_RELAY_*` auth — none of which a coding subprocess has any use for.

**rundesk already answered this the other way round and the other way round is right.**
`process.environment()` **builds** the environment from nothing — `HOME`, `PATH`, `RUNDESK_HOME`,
`TERM=dumb`, `LANG`, and whatever the owner deliberately set through `rundesk env` — so there is no
blocklist to keep true and nothing can leak by being newly added somewhere else. Hermes's own mitigation
proves the cost of the inherit-then-strip shape: the audit mechanism is
`grep -rn 'inherit_credentials=True'`, which is a grep standing in for a boundary.

One thing Hermes has that rundesk should keep: **the flag is grep-able on purpose.** A deliberate,
countable list of spawn sites that receive credentials is worth having even when the default is build-not-
inherit.

### 4 · Steering needed a trust marker, and the failure is the interesting part

`agent/prompt_builder.py:632` records that a plain `User guidance:` line appended to a tool result *"gets
refused as suspected prompt injection (observed in the wild)"*. Genuine mid-turn owner input is therefore
delivered inside a bounded `[OUT-OF-BAND USER MESSAGE — …]` marker, and `STEER_CHANNEL_NOTE` tells the
model to trust that form **and only that form**.

The previous rundesk build carried `STEERING_CONTEXT` beside the person's text for a *different* reason —
so the person's recorded words stay unaltered — and got the trust property for free. **Both properties are
wanted and they are not the same property**, which is worth stating before the two get merged: one is about
the account being honest, the other is about the brain not refusing real guidance.

### 5 · A wedged process is invisible to `KeepAlive`, and this is the answer

`gateway/shutdown_watchdog.py` opens with the clearest statement of the problem found anywhere:

> When the asyncio loop freezes mid-drain, every asyncio-based recovery path is structurally unable to
> fire: the drain deadline, status rewrites, and forensics all need the same loop that is stuck.
> launchd/systemd KeepAlive only restarts a *dead* process, so a wedged-but-alive gateway sits as a zombie
> until manual SIGKILL.

Two mechanisms:

1. **A plain OS-thread watchdog** armed at `stop()`. If shutdown has not completed within
   `restart_drain_timeout + grace` it dumps all-thread stacks with `faulthandler`, writes a metadata
   snapshot, then `os._exit` so the service manager can revive the process.
2. **A liveness heartbeat file** at `<HERMES_HOME>/state/gateway.heartbeat`, separate from the state file,
   *because the state file only rewrites on transitions and turns* — so it cannot distinguish "process
   alive" from "loop frozen".

**rundesk's beat already answers half of this and the halves are worth telling apart.** `standing`'s
15-second beat with a `time.monotonic()` reading *is* the heartbeat, and staleness is judged from outside.
What rundesk has no answer for is the second half: nothing inside a wedged gateway takes it out. That
matters more once a gateway hosts provider turns than it does today, because a stuck turn is the likeliest
way to wedge one.

The synchronous design makes the OS-thread requirement lighter — a signal handler that raises already ends
a `time.sleep` — but not zero: a gateway blocked inside a subprocess wait cannot be reached by anything on
its own thread.

### 6 · The restart-loop breaker

`gateway/restart_loop_guard.py`, and the incident is a provider-layer incident:

> an agent running a raw `terminal("launchctl kickstart -k gui/<uid>/ai.hermes.gateway")`, an external
> monitor with a bad trigger, or any other repeated crash can still drive the supervisor
> (launchd `KeepAlive` / systemd `Restart=`) into a tight respawn loop. On each boot the gateway
> auto-resumes the restart-interrupted session, whose next turn re-runs the offending logic — SIGTERM
> every ~10 seconds until manually broken.

The breaker records a timestamp each boot that finds restart-interrupted sessions pending, keeps a rolling
window persisted across processes (*"each boot is a fresh process, so in-memory state is useless"*), and
once tripped **skips auto-resume for that boot** — the gateway still starts and serves real inbound
messages, it just stops replaying the session that keeps killing it. Defaults: 3 restarts in 60 seconds.
It **fails open** on any read/write error, *"because a broken breaker must never wedge a healthy gateway."*

**This is a direct hazard for rundesk's recovery path.** The previous build resumed interrupted turns on
gateway startup, and an agent has a shell. A turn that crashes the gateway and is resumed on the next boot
is a loop, and `KeepAlive` is what makes it tight. This is on the open-questions list already —
*"whether a program the gateway was running is started again when it fails, given that repeating a turn
repeats whatever that turn already did to the machine"* — and Hermes has both the failure and a shipped
answer to it.

---

## What each got wrong, side by side

| | OpenClaw | Hermes | rundesk (previous) |
|---|---|---|---|
| **vendor knowledge in the core** | leaked back in as enum members (`jsonlDialect`, `liveSession`) after a config table was built to prevent it | one profile per API provider *plus* a bespoke module per CLI — two mechanisms for one job | kept out, and proved by moving Codex to a different transport in one file |
| **spawn environment** | per-backend `env`/`clearEnv` on the config | inherit-then-strip, two tiers, audited by grep, after a real leak | built from nothing — no blocklist to keep true |
| **admission during shutdown** | first-class: close, drain, act | drain control plus an out-of-loop watchdog | none — cancel, look again three times, hope |
| **a wedged-but-alive process** | not addressed in what was read | `faulthandler` dump + `os._exit`, plus a heartbeat file | a beat judged from outside; nothing takes it out from within |
| **restart loops** | not addressed in what was read | persisted rolling-window breaker that fails open | not addressed |
| **one turn per conversation** | `scopeKey` + `replaceExistingScope` in the supervisor | serialized per session | three separate mechanisms, and `rundesk ask` at a terminal bypassed all of them |
| **subscription credentials** | impersonates the vendor's first-party CLI | uses the vendor's CLI as the user | uses the vendor's CLI as the user |

---

## What a stdlib-only synchronous Python port cannot take

- **OpenClaw's `AsyncLocalStorage` admission tracking.** There is no equivalent; the same guarantee has to
  come from an explicit registry of in-flight work rather than from ambient context.
- **`faulthandler.dump_traceback` across threads is available**, and is the one piece of Hermes's watchdog
  that ports directly. `os._exit` after it does too.
- **Hermes's plugin discovery by import** is exactly what rundesk's architecture forbids — a third-party
  adapter must stay a program.
- **Anything that assumes a persistent in-process agent loop.** Both products keep conversation state in
  memory across turns; rundesk keeps it in the CLI's own session file and in `state.db`, and the process
  is gone between turns. Every "just hold it in the session object" answer in either codebase is
  unavailable here — and that is the property that makes a gateway restart cheap.

---

## Open questions this leaves

- **Whether a provider turn should be a child of the gateway at all**, or a detached process holding a lock
  the way `schedules.firing` already does. Hermes's restart-loop incident and rundesk's own *"a gateway
  killed outright cannot take its children with it"* both point at the second, and the second is what this
  build already chose for schedules.
- **Whether the no-output window should differ for a fresh turn and a resumed one**, as OpenClaw's config
  allows. Nobody measured whether it matters.
- **What closes admission**, given that `rundesk ask` at a terminal is a separate process from the gateway
  and cannot be told anything. A lock per conversation answers it the way `firing.claiming` answers it for
  schedules; nothing else read here does.
- **Whether a wedge watchdog belongs in this build at all before there is a turn to wedge on**, and what it
  would dump given the process is synchronous and single-threaded.
