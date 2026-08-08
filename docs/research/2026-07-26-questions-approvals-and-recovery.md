# Research: What a brain can do when nobody is watching the turn

> **Carried across on 2026-08-04, intact, from the previous build's research directory** — a
> gitignored, reference-only tree that is expected to be deleted. Nothing here has been rewritten:
> the wording, the dates, the labels and the measurements are that build's. Two session identifiers
> captured from real accounts were shortened and nothing else was changed. Its internal citations
> name files in trees that are going away, so treat a `(internal)` source as provenance rather than
> as something you can open.
>
> **What is still true.** The limits table and every scenario behind it, measured on one day against
> three real accounts. It is the document that corrects the earlier doc-derived claims, so where it
> disagrees with [`2026-07-25-provider-cli-discord-interaction.md`](2026-07-25-provider-cli-discord-interaction.md)
> it wins. **What is not.** Its `ROADMAP` phase numbers and its shipped-adapter defect reports belong
> to the previous build; the review ledger it names has already been retired.


**Last updated:** 2026-07-26
**Question it answers:** Driving command-line programs rather than APIs, what can and cannot be built for a turn nobody is watching — can a brain ask, can an answer get back, can an approval gate exist, and what survives a restart?

## What they do

Everything here was measured on 2026-07-26 by [`../scripts/probe-asking`](../scripts/probe-asking),
against the versions installed that day:[1]

| brain | version | how it is driven here |
|---|---|---|
| `codex` | codex-cli **0.145.0** | `codex app-server`, the bidirectional stdio protocol the shipped adapter uses |
| `claude` | **2.1.220** | `claude -p --output-format stream-json`, prompt on stdin |
| `grok` | **0.2.111** | `grok -p --output-format streaming-json --no-memory`, and `grok agent stdio` |

Two labels are used and never blurred. **Measured** means a scenario ran against a real account
and its output was kept. **Unmeasured** means the cost was not worth it or the shape was not
reached, and it is an allowed answer — a guess dressed as a finding is the thing this note exists
to avoid. The prior art it re-proves is the Node build's, captured 2026-07-24 against
`claude 2.1.219` and `codex-cli 0.144.6`, which never covered grok and never covered
`app-server`.[2]

### The limits table

Verdicts: **works** · **works differently** · **does not exist** · **unmeasured**.

| What a turn needs to do | codex (`app-server` 0.145.0) | claude 2.1.220 | grok 0.2.111 |
|---|---|---|---|
| Ask a question at all, headless | **works** — prose, and the turn ends | **works** — prose, and the turn ends | **works** — prose, and the turn ends |
| Ask it as a *tool call* | **does not exist** | **does not exist** | **does not exist** |
| Ask it as *structured output* | **works** — `outputSchema` on `turn/start`, and the turn still streams | **works differently** — only under `--output-format json`, never under the `stream-json` rundesk streams with | **works** — `--json-schema` under `streaming-json` |
| Offer a **multiple choice** — labelled options a surface could render as buttons | **works** — 3 labelled options | **works** — 4 labelled options | **works** — 4 labelled options |
| A *native* multiple-choice request, raised by the brain itself | **unmeasured** — `item/tool/requestUserInput` is defined and never fired | **does not exist** | **does not exist** |
| End the turn when it asks (not hang) | **works** | **works** | **works** |
| Route an answer back by resuming | **works** — across a fresh process | **works** — control must stand elsewhere, see below | **works** — with `--no-memory` |
| Take input **mid-turn** | **works** — `turn/steer`, one turn | **does not exist** — `--input-format stream-json` queues a *second* turn | **unmeasured** — no steering surface found on either shape |
| An approval that **waits** for a decision | **works** — `item/fileChange/requestApproval`, and `decline` held | **works** — `--permission-prompt-tool` + `--permission-mode manual`, and deny held | **does not exist** — never asked, on either surface |
| Nobody answers that approval | **works differently** — the turn hangs, with no deadline of its own | **unmeasured** — the brokered request holds the turn open; how long was not measured | not applicable |
| Plan mode as an approval point | not applicable | **does not exist** — it terminates, and emits no `ExitPlanMode` | **does not exist** |
| A posture that actually holds | **works** — both spellings enforce read-only | **works differently** — the allowlist holds for tools and *not* for the memory write | **does not exist** — the tool list only[3] |
| Resuming a session that is gone | **works** — a protocol error naming the reason | **works differently** — the reason is on **stderr only** | **works** — refuses, exit 1 |
| Brain gone between question and answer | **works** — the thread resumed and the answer landed | **unmeasured** | **unmeasured** |

### 1. Every brain asks in prose, and every brain ends the turn

Measured on all three, with the same deliberately under-specified rename request. None used a
tool to ask; each replied with the question as ordinary text and exited 0 — codex in 1 turn on
`app-server`, claude in 3.9s, grok in 7.7s with `stopReason: EndTurn`.[1] **No brain hung**, which
is the failure that would matter: a brain that asks and waits forever is a hung gateway, and none
of the three does that.

**Two of the three can be made to ask as a machine-readable object, and neither does it the same
way.** Grok's `--json-schema` constrains the reply under its ordinary streaming output —

```json
{"needs_answer":true,"question":"Which variable name should I use?","options":[]}
```

— while Claude's `--json-schema` was **silently ignored** under `--output-format stream-json` and
produced the same object only under `--output-format json`.[1] So on Claude a structured question
and a streamed turn are mutually exclusive on this version. Codex has it too and it was nearly
missed: `outputSchema` on `turn/start`, *"constrain the final assistant message for this turn"*.

**And all three can be made to ask a genuine multiple choice** — a question plus labelled options,
which is the shape a surface renders as buttons. Measured with a prompt that forces the brain to
enumerate its own alternatives:[1]

| | options offered | under |
|---|:--:|---|
| codex | 3 labelled | `outputSchema` on `turn/start`, and the turn still streamed normally |
| claude | 4 labelled | `--output-format json` only |
| grok | 4 labelled | `--json-schema` under ordinary `streaming-json` |

```json
{"needs_answer":true,"question":"Which caching approach should I use for this service?",
 "options":[{"label":"In-process cache","description":"…each instance has separate cache state…"},
            {"label":"Redis cache","description":"…works across instances, adds infrastructure…"}]}
```

**The first run of that probe measured nothing, and it is worth saying why.** It asked about "two
reasonable names" without ever saying what they were, so `options: []` came back — which was the
honest answer to the question asked, and looked exactly like a brain that cannot offer choices.
A multiple-choice probe has to give the brain something to enumerate.

**Codex's schema is stricter than the other two, and the difference costs a turn.** `outputSchema`
is rejected unless every object carries `additionalProperties: false`, and the rejection is not a
refused request — it is a **failed turn**, carrying a provider 400 (`invalid_json_schema`) inside
the turn error. The same schema is accepted unchanged by the other two.[1]

What none of them has is the brain *itself* raising a multiple choice as a first-class request.
Codex defines exactly that — `item/tool/requestUserInput`, carrying `{itemId, threadId, turnId, questions[{header, id, options[{label, description}]}], autoResolutionMs}` — and it never fired in
anything probed here, so it stays **unmeasured** rather than being written up from its schema.[1]
The difference matters: a schema-constrained answer is rundesk *asking the brain to ask in a
shape*, while `requestUserInput` would be the brain deciding on its own that it needs the user.

### 2. Resuming the session is still the whole of answer routing — but the Claude proof needed a new control

The check is mechanical: turn one offers two candidate words minted per run, turn two says only
*"the second one"*, naming neither. Measured on all three, each across a genuinely separate
process, and each with a fresh-session control that had to fail:[1]

| | turn 2 resolved it | control failed as it should |
|---|:--:|---|
| codex (`thread/start` → `thread/resume`, second process) | yes | yes — the fresh thread guessed at something else entirely |
| claude (`--session-id` → `--resume`) | yes | **only in a different working directory** |
| grok (`--session-id` → `--resume`, `--no-memory`) | yes | yes |

**Claude now contaminates its own control, and this is new.** A fresh session — no `--resume`, a
new `--session-id` — standing in the *same* working directory answered correctly, from a file the
turn before had written to `~/.claude/projects/<resolved cwd slug>/memory/`:[1]

```
description: "The single word the user asked me to remember — \"WALRUSPGHVAE\""
**How to apply:** If asked "what word am I remembering?" or similar, answer WALRUSPGHVAE.
```

Two consequences, and the second is not about probing. **The allowlist was `Read`, and the file
was written anyway** — so the one thing prior art measured to hold as containment on this brain
does not hold for the memory path. And memory is keyed by the **working directory**, which is
exactly what rundesk gives one agent for every one of its turns — so on Claude, every conversation
of one agent shares a memory namespace and can answer another's question. That is the grok
cross-session finding, on a second brain, arriving by a different route.[4]

### 3. Mid-turn input: one brain has it, and it is not the one with a flag that says so

Measured with the same task on both — count slowly to 40, then eight seconds in, *stop at 5 and
say HALTED*. Both printed a similar tail, so the text is not the discriminator; **the number of
turns is**:[1]

| | turns started | what happened |
|---|:--:|---|
| codex `turn/steer` | **1** | the steer returned the *same* `turnId`, and the later words reached the running turn |
| claude `--input-format stream-json` | **2** | it finished counting to 40, emitted a `result`, then answered the second message as a new turn |

So Claude's "realtime streaming input" is a **persistent multi-turn process**, not steering, and
`steer: false` on the shipped Claude adapter is correct — now measured against the streaming-input
surface rather than assumed from `-p`. **Grok's is unmeasured**: nothing in its flag surface or in
its ACP handshake named a way to add to a running turn, and no probe was built to look for one, so
the honest answer is that it was not tested rather than that it is absent.

**What a brain declaring `steer: false` does when sent input anyway is rundesk's own question, not
a vendor one** — the seam closes the input rather than passing it on, and `test_provider.py` covers
it. Nothing was bought to re-establish that.

### 4. An approval gate can be built — on two of the three brains

This is the finding that moves the most, and both halves carried controls.

**Codex.** With `approvalPolicy: "untrusted"` and `approvalsReviewer: "user"` on `thread/start`,
a read-only turn asked to write a file raised `item/fileChange/requestApproval` to the client. A
client answering `{"decision": "decline"}` produced `patch rejected by user` on stderr, no file,
and a turn that completed normally.[1] The decision vocabularies are closed and generated by the
CLI itself: `accept` · `acceptForSession` · `decline` · `cancel`, and `ReviewDecision` adds
`timed_out`.[1] **Nothing sets that policy today**, which is why it had never been seen — the first
run of this probe reported "never fires" about a policy nothing had turned on.

**Claude.** `--permission-prompt-tool` is **absent from 2.1.220's `--help` and still accepted by
the parser** — established for nothing, because an invented flag dies with `error: unknown option`
before a turn starts.[1] Pointed at a throwaway stdio MCP server, under `--permission-mode manual`
and with **no tool allowlisted**, the decision really was routed out:

```json
{"name": "approve", "arguments": {"tool_name": "Write",
 "input": {"file_path": ".../TOUCHED.txt", "content": "HELLO\n"}, "tool_use_id": "..."}}
```

The broker denied it, no file was written, and Claude reported the refusal verbatim — *"The write
was denied by a permission hook (message: "denied by the probe, deliberately")"*.[1] Three controls
make that readable: the broker was reported `connected` in `system/init.mcp_servers`; the same turn
with `Write` allowlisted wrote the file; and the same turn with no broker at all was refused
without anybody being asked. **The first attempt at this probe allowlisted the very tool it was
testing and reported that no gate existed** — a permitted tool never prompts.

**Grok asks nobody anything.** Headless, with `create_file` granted, it wrote the file and said so.
Its ACP surface — `grok agent stdio`, which speaks a real protocol and advertises
`"x.ai/hooks":{"blockingEvents":["pre_tool_use"],"decisions":["deny","block"]}` in its handshake —
drove a whole session that wrote the file with **no permission request of any kind**.[1] Judged on
the file, never on the handshake, which is how this brain has to be judged.[3]

**Plan mode is not the answer on either brain that has it.** Claude's terminated in 25.2s and
emitted no `ExitPlanMode`; grok's terminated in 40.6s and this brain reports no tool events at all,
so there is nothing to capture even in principle.[1]

### 5. What it costs to leave a question open

**Turn-shaped asking costs nothing to leave open.** All three end the turn when they ask, so
there is no process holding anything: what remains is a session file on disk and a handle in the
account. Nothing expires inside the horizon of this probe, and **whether a session expires over
days is unmeasured** — it cannot be bought inside one task.

**Protocol-shaped asking is the opposite, and it is measured.** With an approval policy set and a
client that never answers, the codex turn **did not complete inside 120 seconds** and had to be
killed.[1] That is precisely what the shipped adapter does: `_listen` routes anything with an `id`
and a `method` into `_heard`, which knows only notifications, so a server-initiated request is
dropped in silence.

### 6. Failure and recovery

Measured, one scenario each:[1]

- **Claude, resuming a session that never existed.** The reason is still on **stderr only** —
  `No conversation found with session ID: …` — while the stream carries `subtype: "error_during_execution"` and says nothing about why. The prior finding stands unchanged at 2.1.220.
- **Codex, resuming a thread that never existed.** A clean protocol error naming the reason:
  `{"code": -32600, "message": "no rollout found for thread id …"}`.
- **Grok, resuming a session that never existed.** Exit 1, and it first tries to fetch the session
  **from a remote registry** — *"Session … not found locally, restoring from remote…"* — before
  failing. A grok session handle is not purely local state.
- **Codex, brain gone between the question and the answer.** The process was killed after the
  question and a *new* process resumed the thread; the answer landed correctly. What is proven is
  the gateway-restart case, not a turn interrupted halfway — the short question had already
  completed when the kill arrived, and the probe says so.

### The posture question, settled for codex

Measured because the shipped adapter and the generated schema disagree: 0.145.0 types `sandbox` on
`thread/start` as a plain `SandboxMode` string, while the adapter sends the externally-tagged
`{"read-only": {}}`. **Both are accepted and both hold** — under either spelling the write was
refused and the model said the workspace was read-only.[1] No defect, and it is written down so
nobody re-derives it.

### Corrections to the prior art, line by line

The Node build's four recorded findings,[2] each re-run against the installed versions:

| What it said | Now | What replaced it |
|---|---|---|
| "Neither brain asks with a tool — both ask in prose and end the turn" | **still holds** | And it now holds on grok too, and on `app-server` rather than `exec`. `AskUserQuestion` is still absent from the headless tool list. |
| "End-turn then resume carries the question, proved on both" | **still holds** | On all three brains, and on `app-server`. But the *proof* needed rebuilding on Claude: its control must now stand in a different working directory, or its auto-memory answers for it. |
| "Plan mode is not usable headless — it did not terminate inside 120 seconds" | **half refuted** | The hang is gone: 2.1.220 terminated in 25.2s, exit 0. The conclusion survives on the other half — no `ExitPlanMode`, so still no capture point there. |
| "`--permission-mode` is not a read-only posture — the allowlist is" | **narrowed** | The allowlist is not sufficient either: with `Read` alone allowlisted, Claude still wrote a memory file. |

And one from this repo's own notes: the 2026-07-25 note's Claude approval route — `--permission-prompt-tool`, sending native permission prompts to a named MCP tool — was written from vendor documentation and never exercised.[5] It is **confirmed working** at 2.1.220, with the caveat that the flag no longer appears in `--help`. The same note's `PreToolUse` defer/resume route was not probed and stays unmeasured.

## What we can borrow

- **The turn-shaped ask is the honest shape, and it is free.** All three brains ask in prose and
  end the turn, so a question costs a session file and nothing running. Design for that first;
  everything richer is a per-brain extra.
- **Resuming the session is still the whole of answer routing.** A pending-ask record is not needed
  to make an answer *land* — the session does that on all three brains.
- **A control belongs in every resume probe, and it has to stand somewhere the brain's memory does
  not reach.** Two of three brains now answer from state that no handle was given.
- **Approvals are a per-brain capability to declare, not a feature to assume.** Two brains have a
  real one and they are shaped differently: codex routes a decision inside its own protocol, Claude
  routes it out to an MCP tool the host runs. Both are honest `allow`/`deny` points that hold.
- **The canary is the cheap half of every approval probe.** `system/init.mcp_servers` on Claude and
  the `turn/started` count on codex each turn an ambiguous result into a readable one.
- **Judge grok on effects.** It reports no tool events, and its ACP handshake advertised a blocking
  permission hook that never fired. The file on disk is the only evidence this brain gives.
- **Take the offline half seriously.** `codex app-server generate-json-schema` and one control
  against an invented flag answered two structural questions for nothing at all.

## What to avoid

- **Do not allowlist the tool whose permission you are testing.** A permitted tool never prompts,
  and the run reports that no gate exists.
- **Do not read "no approval fired" as "no approval exists"** until `approvalPolicy` has been set.
  Codex's default is not to ask, and the shipped adapter never sets it.
- **Do not conclude a flag is gone because `--help` stopped listing it.** The parser is strict, so
  an invented flag is refused for nothing while a real one is silently accepted.
- **Do not treat an allowlist as containment on Claude.** It held for every tool and did not stop
  the memory write.
- **Do not leave a server-initiated request unanswered.** Codex waits, with no deadline of its own,
  and the turn never ends.
- **Do not isolate a brain's home to keep a probe clean.** All three carry the sign-in there, so it
  logs the brain out; every probe run necessarily leaves directories in the owner's real
  `~/.claude/projects/`, `~/.grok/sessions/` and `~/.codex/sessions/`. Name scratch directories so
  the litter is identifiable, and leave removing it to whoever owns the machine.
- **Do not ask a brain something the conversation, its memory, or its other sessions can already
  answer.** Two of three brains would have made a resume probe pass without resuming anything.
- **Do not promise a structured question on Claude while streaming.** The two flags do not compose
  on this version, and the schema is dropped in silence.
- **Do not send codex the same schema the other two took.** `outputSchema` needs
  `additionalProperties: false` on every object, and the rejection arrives as a *failed turn*
  carrying a provider 400 rather than as a refused request — so getting it wrong costs a turn and
  looks like the brain failing.
- **Do not ask a brain to offer options without giving it something to enumerate.** An empty
  `options` is the honest answer to an under-specified question and is indistinguishable from a
  brain that cannot offer choices at all.

## Verdict for us

**The headline changes: an approval gate is buildable, on two of the three brains.** The ROADMAP's
Phase 14 opens by carrying in the Node build's conclusion that no capturable approve/edit/reject
point exists. That conclusion was drawn from the two paths that are now the least likely places to
look — Claude's plan mode, and `codex exec`, which this repo no longer uses. On the surfaces
rundesk actually drives, a decision can be routed out, held, and refused, and the refusal is
obeyed.

**What Phase 14 can promise.** A question, on all three brains, as the turn-shaped thing it
already is — asked in prose, the turn ending, the answer arriving as the next turn on the same
session. **A multiple choice with labelled options, on all three**, which is what a surface needs
to render buttons — obtained by constraining the reply, and paid for on Claude by giving up
streaming for that turn. And an approval that genuinely waits, on **codex and claude**, as a
declared per-brain capability with its own shape behind the seam.

**What Phase 14 must not promise.** An approval on **grok**, which asks nothing on either surface.
Mid-turn input on **claude**, which queues a second turn instead. A question or a choice raised as
a *tool call* by the brain's own decision, anywhere — every structured ask measured here happened
because rundesk asked for that shape, which means something has to decide a turn *might* need a
question before it starts. Anything at all built on plan mode. And a structured question on Claude
while a turn is streaming.

**The pending-ask record shrinks but does not vanish.** Routing an answer needs only the session,
as prior art said. What still needs a durable record is the **approval** case, because that one has
a live process waiting on it and a `tool_use_id` or `turnId` to match — and single-use, bound to
user, conversation and expiry is exactly right there, and ceremony on the question path.

**One defect and one boundary follow from this and are recorded rather than fixed here** — the
shipped codex adapter drops server-initiated requests, which is a hung turn the day an approval
policy is set; and Claude's memory crossing conversations in one agent's directory is a real
isolation limit. Both were recorded in the review ledger of the day, `SUGGESTIONS.md`, which has
since been retired.

This informs Phase 14 and is held to nothing: it is input to a draft, never a requirement. The
component it would feed is a `provider-` one that is not declared yet, which is the owner's call.
Re-run [`../scripts/probe-asking`](../scripts/probe-asking) when any of the three versions moves,
and write what changed here.

## Open questions

- **Whether `item/tool/requestUserInput` can be turned on**, and what an experimental-feature
  opt-in costs — it is fully defined, including an `autoResolutionMs` that would answer the
  nobody-answers case by itself, and it never fired.
- **How long a brokered Claude permission request holds a turn open**, and what happens at whatever
  deadline the CLI keeps for it.
- **Whether a session expires or becomes unresumable over days or weeks**, on any of the three.
- **Whether grok's advertised `pre_tool_use` blocking hook can be made to fire** through a client
  capability, a plugin directory or a config this probe did not reach.
- **Whether Claude's auto-memory can be turned off per turn**, which decides whether one agent's
  conversations can be kept apart on that brain at all.
- **What a genuinely mid-turn kill costs**, as opposed to one between the question and the answer.
- **Whether `--permission-prompt-tool` being undocumented means it is being withdrawn** — an
  approval gate built on a flag its vendor no longer lists is a gate with a shelf life.
- **What the other two brains do when an approval is left unanswered**, which was only measured on
  codex.

## Sources

1. [`../scripts/probe-asking`](../scripts/probe-asking) — the probe every measurement here comes from, run 2026-07-26 against `codex-cli 0.145.0`, `claude 2.1.220` and `grok 0.2.111` on macOS 25.5.0 — (internal)
2. `../rundesk/docs/clarify.md` — the Node build's recorded verdict, captured 2026-07-24 against `claude 2.1.219` and `codex-cli 0.144.6` — (internal)
3. [The Grok CLI as an agent's brain](./2026-07-26-grok-cli-as-a-brain.md) — the two flags this brain accepts and does not honour, and why it is judged on effects — (internal)
4. [The Claude Code CLI as an agent's brain](./2026-07-26-claude-cli-as-a-brain.md) — the allowlist-is-the-only-containment finding this note narrows — (internal)
5. [Provider CLI events and Discord interaction](./2026-07-25-provider-cli-discord-interaction.md) — the doc-derived Claude approval routes, one of which this note confirms — (internal)
