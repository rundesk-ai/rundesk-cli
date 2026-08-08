# Designing the provider system: what is settled, what is open, and the route

**Written 2026-08-05**, before anything is built. This is a proposal page, not a description of anything
that runs — nothing in it is a guarantee and nothing in `docs/` should cite it.

It sits on four things established the same day or carried forward:

- [`the-adapter-contracts.md`](the-adapter-contracts.md) — the provider adapter contract as the previous
  build defined it, already distilled and treated here as **the contract of record**.
- [`2026-08-05-the-old-builds-provider-system.md`](2026-08-05-the-old-builds-provider-system.md) — what
  the previous build's six modules actually did, with the incidents attached.
- [`2026-08-05-how-other-gateways-run-a-provider.md`](2026-08-05-how-other-gateways-run-a-provider.md) —
  OpenClaw and Hermes, and the two shapes they chose instead.
- [`instruction-layers.md`](instruction-layers.md) and the four dated brain notes, which are the
  measurements everything below is bounded by.

---

## The finding that frames the work

**A provider contract already exists, it is largely right, and it has been proved once by accident.**
Codex was moved from `codex exec` to `codex app-server` — a different transport, and it *gained* the
`steer` capability doing it — and that change touched **one file**. Nothing in the core moved.

So this is not a design from nothing. It is a re-implementation of a working seam onto a synchronous,
one-root, stdlib codebase, with four things fixed that the previous build got wrong at the level of
structure rather than at the level of a bug.

| | Settled by the existing contract | What has to change |
|---|---|---|
| **The seam** | adapter is a program, never code; closed vocabularies; unknown records kept and shown to nobody; capabilities asked once per turn | nothing — carry it forward as it stands |
| **The process** | silence not duration; group signalling; bounded queue between reading and receiving; gaps reported in place | **asyncio comes out.** ~a third of the old module's scar tissue was asyncio-specific and this build is synchronous |
| **One turn at a time** | — | **three mechanisms became one.** A funnel inside the gateway, a queue in `answering.py`, and *nothing at all* for `rundesk ask` at a terminal — which could start a second turn in a conversation a gateway was already running. One lock per conversation, the way `schedules.firing` already does it |
| **The turn's shape** | the seven readings; nothing sent that the account does not show; a begun run is always settled | **`turn.carry` had thirty parameters.** Six of them were delegation and roles, which are not being built. A request object, and the unbuilt things simply absent |
| **Instructions** | one composer, a core carrying no identity, exactly one layer naming who asked | **it was scattered** — `instructions.py` composed, `channel.py` bounded and stacked owner text, `turn.py` wrote it into the account, `answering.py` chose the trigger. One owner, and a command that prints what a turn would be given |

---

## 1 · The decisions that are not open

These are settled by evidence already on the shelf. They are written here so nobody re-litigates them,
and each one names what would have to be true to reopen it.

### An adapter is a program, and never loaded code

The alternative shape exists and was read: OpenClaw declares a CLI backend as a ~40-field config table
plus six escape hatches. **Two fields in it are `jsonlDialect: "claude-stream-json" | "gemini-stream-json"`
and `liveSession: "claude-stdio"`** — vendor names in the core type of the mechanism built to keep vendor
names out of the core. The shapes that would not fit into data became enum members instead, so the design
pays both costs.

And the four things that actually differ between the measured brains cannot be expressed as configuration
at all: Claude's reply arriving three times with two copies byte-identical; Codex's usage being a running
total needing per-session subtraction against durable state; Grok's `--tools` being accepted in silence
and inert on ACP; Claude's steering needing an interrupt request, an acknowledgement drain, *then* the
message.

*Reopen if:* somebody demonstrates a vendor whose whole behaviour is a flag table. Nobody has.

### The core makes no decision on a vendor's name, and this is grep-checkable

A vendor name may appear in `src/rundesk/` in a docstring explaining why a rule exists, and in help-text
examples — which is exactly where the previous build's four appear. It may never be read, compared or
branched on. A test asserts it the way `tests/test_layers.py` asserts the import direction, because
*"written down is where a rule of this kind stops being true."*

The test has to be written against **code** rather than against the file's bytes, or the help examples
fail it and somebody deletes the test instead of the violation: parse with `ast`, ignore docstrings and
string constants that are only ever printed, and fail on a vendor name reaching a comparison, a dict key
or a branch.

### It is synchronous

Hermes drives `codex app-server` from a synchronous caller with reader threads and bounded queues, and
says why in its own docstring: *"layering asyncio just to drive a stdio child creates surprising interrupt
semantics."* This build is already synchronous everywhere — `utils/programs.py`, `gateways/host.py`,
`schedules/firing.py` — and the previous build's cancellation defects (a run left `running` for ever
because a cancellation unwound past the settle; a task whose exception nobody retrieved) are exactly the
class Hermes named.

*Reopen if:* one gateway has to host many concurrent turns and threads prove insufficient. Not today: one
agent, one gateway, and turns are minutes long.

### The vendor's own CLI, signed in by the owner, through its published headless interface

This is the terms-of-service position and it is a design invariant, not a policy note. It gets its own
section below.

### Delegation, roles, channels, approvals and questions are not being built

They are understood — [`the-adapter-contracts.md`](the-adapter-contracts.md) has the channel contract,
[`2026-07-26-questions-approvals-and-recovery.md`](2026-07-26-questions-approvals-and-recovery.md) has the
measurements — and they are what the provider layer must not make harder. What that costs now is three
things kept in view rather than built:

- **an instruction layer per trigger**, so `AGENT_TO_AGENT` and `AGENT_TO_ROLE` land beside the two that
  do exist rather than being retrofitted into a composer built for one;
- **a `watching` sink on a turn** — records handed on as they arrive — because that is how a channel shows
  work as it happens, and a turn that only returns an outcome cannot grow one;
- **`turn_records` and `conversations` as tables from the first migration step**, because a channel adds
  delivery on top of the account and *must never become the only place something was written*.

Everything else waits.

---

## 2 · Where it goes

Seven packages become eight. `providers` sits beside `schedules`, and `gateways` reaches it:

```
commands  →  lifecycle  ─┐
          →  gateways   ─┤ →  providers ─┐
          →  skills     ─┤ →  schedules ─┴→  agents  →  core  →  utils
          →  providers  ─┘
```

```python
"providers": ("agents", "core", "utils"),
"gateways":  ("providers", "schedules", "agents", "core", "utils"),
"commands":  ("skills", "providers", "schedules", "gateways", "lifecycle", "agents", "core", "utils"),
```

**`schedules` may not reach `providers`, and that is the direction that matters.** `firing.Starting` is
already a protocol handed in, and `firing.looked(..., asking=None)` is already the seam a provider process
arrives at — written that way months before there was one. The gateway supplies the provider-backed
`Starting`; the schedule layer stays answerable by a case with no brain, no adapter and no subprocess
anywhere near it.

**`commands` reaches `providers` directly**, because `rundesk ask` typed at a terminal runs a turn without
a gateway.

### The modules, and why each is separable

| Module | Owns | Testable with |
|---|---|---|
| `utils/framing.py` | bytes off a pipe → whole records, or a gap saying what was lost and where | a bytes literal. No process |
| `utils/programs.py` **(+ a third shape)** | a program you hold a conversation with: read framed records, write records, bound the silence, signal the group | fixture programs (`python3 -c …`) |
| `providers/seam.py` | the closed vocabularies, `understood`, `spoken`, `claimed` | dicts and strings. No I/O at all |
| `providers/adapters.py` | which program is this provider, and what it says it can do | fixture adapters, as shell scripts |
| `providers/briefing.py` | everything an adapter is told — the whole environment | a dict comparison |
| `providers/instructions.py` | what a brain reads before the task | a string comparison |
| `providers/kept.py` | conversations, turns, records and sessions in the agent's own `state.db` | a scratch database |
| `providers/turns.py` | one turn: resolve → record → run → record → settle | all of the above, with a fixture adapter |

Two of those are new departures from the previous build and both are deliberate.

**`framing` is separate from `programs`.** The previous build's `_Lines` and `_Records` were inner classes
of a 1207-line module, so the bounds could only be tested by running a program that emitted a five-megabyte
line. They are the single most defect-prone thing in the set — evicting by hand rather than by `maxlen`,
bytes not characters, gaps folded rather than piled up, `\r` stripped exactly once and only at the end —
and every one of those is provable against a bytes literal in a millisecond.

**`briefing` is separate from `adapters`.** What a turn *tells* its brain is a pure function of the turn,
and it is the thing that grows: the previous build's `environment()` took fourteen arguments by the end. A
module that returns a dict and never touches a file is one whose growth is visible.

---

## 3 · The three things being fixed structurally

### One turn per conversation, held by a lock

The previous build had three mechanisms and a hole. This build already has the right pattern, written for
schedules: **`flock` on a file in the agent's own directory, the descriptor passed to the child, the kernel
dropping it however the child tree ends.** `schedules/firing.py::claiming` is the code, and its docstring
already names the defect being avoided — *"the old build funnelled by name inside the gateway, so `rundesk
schedules run` typed at a terminal knew nothing about it and could start a second copy of the same work."*

A conversation gets the same treatment: `conversations/<key>.lock` under the agent. Then:

- **the claim is the check** — there is no version that asks and then acts;
- `rundesk ask` and the gateway compete for the same lock, correctly, with no coordination between them;
- a turn's liveness is asked of the kernel, so a gateway killed outright never leaves a conversation
  looking busy;
- a gateway that comes up after the one that started a turn can *see* the turn is running, adopt it, and
  say `stopped` when the lock drops — because it cannot reap a child it did not start.

**And it means a turn is a detached child holding a lock, not a child of the gateway's own lifetime.**
That is what `firing` already chose, for the reason `gateways/host.py` states: a child in its own group is
outside the gateway's group, so launchd's cleanup cannot reach it either, and the fresh gateway must not
host the same agent beside it.

*This is the single largest simplification available.* It deletes the funnel, the per-conversation waiting
queue and the in-memory conversation cache in one move, and it makes the terminal path and the gateway
path the same path.

### A turn is asked for with an object, not thirty arguments

```python
@dataclass(frozen=True)
class Asked:
    agent: str
    prompt: str
    conversation: Where           # surface, kind, key — what makes one conversation one conversation
    trigger: str                  # which instruction layer names who asked
    posture: str = WORK
    model: str | None = None
    fresh: bool = False
    preface: str = ""
    stands_alone: bool = False    # is this prompt worth asking a fresh session again?
```

Everything the previous build's `carry()` took as a keyword and threaded through — `role_run`,
`delegation`, `recovery_of`, `resume_required`, `schedule_id`, `asked_by`, `prompt_author`,
`stopped_by_owner`, `secrets_resolving`, `clock`, `pick` — is either an unbuilt feature, a test seam, or a
thing that belongs on the result. The unbuilt ones stay unbuilt; the test seams stay arguments resolved in
the body (`AGENTS.md`'s own rule); the rest move.

`stands_alone` is kept despite looking like a wart, because the incident behind it is real: a resumed
session that hands a turn straight back is worth asking once more **only** if the prompt is a question
somebody asked. Retrying a continuation prompt on a fresh session answers about nothing, records
`finished`, and **replaces the interrupted conversation's handle — which is the work itself going.**

### The instruction system has one owner and is inspectable

The previous build's prompt was assembled across four modules. This build:

- **`providers/instructions.py` composes, and nothing else does.** Core → exactly one layer naming who
  asked → appends in the order supplied.
- **The core carries no identity**, and it is proved by *searching the built string* for every forbidden
  thing (a home path, a memory file, a channel, a schedule, a product command), never by reading the
  composition back.
- **Each externally supplied layer is bounded at ingestion; the finished stack is never clipped**, because
  clipping the whole silently drops whichever later layers fell past the boundary.
- **Substitution is `str.replace`, never `str.format`**, because owner text arrives with braces in it
  eventually and `str.format` raises mid-turn when it does.
- **A named cache boundary is a first-class concept.** Both comparable products let prefix-cache economics
  decide physical ordering and one keeps a literal marker naming the line. Which tier a fragment belongs to
  should be a decision the code records rather than one each new fragment re-litigates.
- **`rundesk agents instructions <agent>` prints the assembled prompt with a byte breakdown by tier** —
  the one idea worth taking wholesale from Hermes (`hermes prompt-size`). Prompt budget becomes inspectable
  rather than estimated, and it is the cheapest possible way to notice that a layer doubled.

Two tests, and neither is optional:

1. **Prove what did not change.** A captured file holding every preface the composer builds, captured once
   and never regenerated from the code it guards. A test that rebuilds its own expectation agrees with any
   change at all.
2. **Prove the leak cannot come back.** The role-execution search above, plus an assertion that no
   substitution placeholder of any kind survives in the core.

---

## 4 · Staying inside the vendors' terms

**The architecture is the compliance position, and it is worth stating as one.** rundesk runs the vendor's
own published CLI, as the owner, signed in the way the vendor intends, through the headless interface the
vendor documents. It substitutes nothing, re-implements nothing, and sends nothing to a vendor endpoint
itself.

Seven rules follow, and each has a failure behind it in one of the codebases read:

1. **Never impersonate a first-party client.** No borrowed user agent, no vendor system-prompt preamble, no
   tool renaming to match a vendor's own. OpenClaw's transport does all three on subscription credentials
   under a comment reading `// Stealth mode`. rundesk has no reason to: it *is* running the first-party
   client.
2. **Never take a subscription credential onto an API path it was not issued for.** This is the same rule
   from the other side and it is the one that actually matters — the terms distinguish a plan sold for
   interactive CLI use from metered API access, and moving a token between them is the violation.
3. **Never copy, link, or read an owner's credential on their behalf.** Measured: Claude's config
   directory *removes* the login rather than redirecting it, and there is nothing to copy; Codex keeps a
   plain `auth.json` that *can* be copied or symlinked; Grok fails closed and names the command to run.
   The honest behaviour is identical in all three cases — **say the brain is not signed in and say what to
   run.** Sharing one sign-in between agents may well be what an owner wants, and it is theirs to arrange.
4. **Never put a prompt or a secret on a command line.** It is readable through the process list and kept
   in a shell's history. The prompt goes on stdin. Grok is the exception the contract already names — its
   prompt *is* a flag value — and `--prompt-file` exists for exactly that.
5. **Drive only documented headless surfaces.** `-p`/`exec`/`app-server`/`agent stdio` are published
   interfaces. Scraping an interactive TUI, reverse-engineering a private endpoint, or automating a browser
   session to obtain a token are all outside this.
6. **Never defeat a rate limit.** A `limit` record is a thing to *report*, not a thing to route around.
   Multiple agents on one machine are multiple sign-ins the owner arranged, not a way to multiply an
   allowance.
7. **Never let a test reach a vendor.** Already an `AGENTS.md` rule, and it is a terms rule too: a suite
   that authenticated against somebody's account would be running unattended traffic nobody consented to.
   Golden streams are committed; probes are scripts a person runs deliberately.

**A per-adapter statement in the contract.** An adapter author is the one who knows their vendor's terms,
so the contract should ask for one line saying which published interface the adapter drives and how the
brain is signed in. It costs nothing and it makes rule 5 checkable by reading.

---

## 5 · The route

Nine phases. The rule underneath the ordering: **every phase is provable by breaking the code and watching
a test go red, and no phase depends on a vendor being installed.** The wrappers come last, and by the time
they arrive there is nothing left for them to do but absorb one vendor each.

### Phase 1 — the wire, with no process anywhere near it

`utils/framing.py` and `providers/seam.py`.

Bytes in, whole records or gaps out. The closed vocabularies. `understood`, `spoken`, `claimed`. Bounds in
bytes, eviction by hand, gaps folded by kind, `\r` stripped exactly once and only at the end.

*Done when:* a five-megabyte record is dropped with a gap in its place and the **framing survives**; an
unterminated tail is reported as a gap and never delivered as a record; a record of an unknown kind is
kept with its raw line and shown to nobody; the byte bound holds when the item count is small and the count
bound holds when the items are tiny.

*Why first:* it is where the previous build got things wrong most often, it needs nothing to test, and
everything else stands on it.

### Phase 2 — a program you can hold a conversation with

`utils/programs.py` gains a third shape beside `run` (answers and stops) and `start` (long-lived, output to
a file): **long-lived, output framed and read, written to.** Synchronous, with a reader thread and a
bounded queue.

Silence as the failure and a ceiling as the backstop. `SIGTERM` then `SIGKILL` to the **group**.
`PermissionError` is *still there and still ours*, never *gone*. stderr drained unconditionally and kept
apart. The drain a deadline, not a per-read timeout. A slow receiver bounded by its own patience, not the
drain's.

*Done when:* a program that spawns a talkative child and exits is reaped in seconds rather than at the
ceiling; a program that ignores `SIGTERM` is killed and reported as killed; a receiver that raises on every
record neither stops nor ends the program; a receiver that sleeps a fifth of a second per record still
receives everything it was owed.

*Fixtures, not vendors:* every case above is `python3 -c` in the test file.

### Phase 3 — the adapter seam

`providers/adapters.py` and `providers/briefing.py`.

Name → program, by looking rather than by a table. `--capabilities` with its own silence window and its own
ceiling. The environment built from nothing, sorted, with the owner's own values unable to take a name
rundesk decided.

*Done when:* an adapter that does not understand `--capabilities` can do nothing and that is not an error;
one that is not there raises `NotRunnable` **before anything is written down**; a chatty adapter cannot
hang the ask; and the environment contains no vendor variable, asserted by name.

*Fixtures:* three shell-script adapters in `tests/` — one that answers `{}`, one that answers everything,
one that never terminates.

### Phase 4 — where a turn is written down

Agent migration step `0003`: `conversations`, `conversation_messages` (+ FTS), `turns`, `turn_records`,
`provider_sessions`. Plus `providers/kept.py`, the way `schedules/kept.py` already reads and writes rows.

Persistence *before* orchestration, because writing things down is the orchestration's whole job.

*Carry the SQLite lessons forward verbatim* — they are in
[`2026-07-26-sqlite-store-and-migrations.md`](2026-07-26-sqlite-store-and-migrations.md) and
[`the-old-build.md`](the-old-build.md): never `executescript` inside a step; `STRICT` tables; a `NOT NULL`
on a turn's provider is a guarantee, not an inconvenience; `ON DELETE SET NULL` on a schedule's key is
load-bearing.

*Done when:* a turn that died before reaching the brain still shows what somebody asked for; `seq` orders
an account correctly with a clock that went backwards mid-run; a record of an unknown kind lands as
`unknown` with its own words beside it.

### Phase 5 — the instruction system

`providers/instructions.py`, plus `rundesk agents instructions <agent>`.

*Done when:* the captured-preface file is byte-identical to what the composer builds; the core contains no
placeholder and names nothing identity-bearing; owner text containing `{` does not raise; a layer bounded
at ingestion does not clip the finished stack.

*Placed here deliberately:* before the turn, so a turn is handed a finished string and never composes one.

### Phase 6 — one turn

`providers/turns.py`. The seven readings. Records written before the brain starts. A begun run settled
whatever happens. The retry-once rule, gated on `stands_alone`. The `watching` sink, so a caller can be
handed records as they arrive.

*Done when:* an adapter that exits zero having said nothing is **not** a turn that worked; an adapter
saying `steer: false` has its input closed after the prompt and one saying `steer: true` does not; a turn
killed mid-flight is settled as `stopped` and not left `running`; nothing reaches the adapter that the
account does not show, asserted by comparing the two.

### Phase 7 — the gateway hosts it

The conversation lock. The turn as a detached child. `firing`'s `asking` seam filled in, so a schedule that
names an agent runs. Reconciliation at gateway startup for turns a previous gateway left. Admission closed
before the drain, so a shutdown is bounded rather than hopeful.

*Done when:* `rundesk ask` and a gateway cannot both run a turn in one conversation; a gateway killed
outright leaves a turn that the next gateway can *see*, refuses to duplicate, and settles honestly as
`stopped`; `NOT_PROVEN` comes out of `schedules/firing.py`.

*The restart-loop question is settled here, not later.* Hermes's incident is directly reachable: a turn
that crashes the gateway, resumed on the next boot, with `KeepAlive` making the cycle tight. Either
recovery is off by default, or there is a persisted rolling-window breaker that **fails open**.

### Phase 8 — the command surface

`rundesk ask`, `rundesk messages`, and whatever `rundesk gateways logs` needs to explain a turn. Only after
the layer works, and each verb only when it does.

### Phase 9 — the wrappers, one at a time

Each is one executable file, importing nothing, with a **committed golden stream** captured against a
stated version, driven offline.

**Claude first.** Best measured, most capable, honest about all five capabilities, and the golden already
exists. What it proves: the whole-versus-fragment distinction, the usage split, `steer` through a control
protocol.

**Codex second, because it is the hardest.** Cumulative usage needing per-session subtraction against
durable state in the adapter's own home; a JSON-RPC lifecycle rather than one command; `expectedTurnId` as
a steering precondition; and no model name at all, so it must honestly claim `model: false`. An adapter
that absorbs Codex proves the seam.

**Grok third**, for the ACP transport and the `--no-memory` cross-session lesson. **Antigravity fourth**,
for the two failures nobody else has: an unknown resume id that silently starts a new conversation, and a
soft-denied write that exits zero.

*Each wrapper is done when:* its golden replays offline to the exact records expected, its capability
declaration matches what it actually does, and it is driven once for real against a scratch `RUNDESK_HOME`.

---

## 6 · What this deliberately does not answer

- **Whether the no-output window should differ for a fresh turn and a resumed one.** OpenClaw's config
  allows it; nobody measured whether it matters. One window until something says otherwise.
- **How long an account is kept, and whether an owner or a size decides.** Asked three times in the
  previous build's own contracts and never answered once.
- **What a turn's share of a running total is after a restart lost the total it was reporting against.**
  The contract says what an *adapter* should do; nothing says what the *record* should say.
- **Whether a wedge watchdog belongs here.** Hermes has one because an asyncio loop can freeze; a
  synchronous gateway blocked in a subprocess wait is a smaller target but not a null one. Not before there
  is a turn to wedge on.
- **Where prices come from**, and whether a provider that names no model leaves a run's cost attributable
  at all. Codex names none.
- **Whether an owner may stop an agent that has cost too much**, and what decides "too much".

Every one of these is on [`open-questions.md`](open-questions.md) already. They are repeated here so that
reaching one during the work is recognised rather than discovered.
