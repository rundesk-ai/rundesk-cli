# Research: The Claude Code CLI as an agent's brain

**Last updated:** 2026-07-26
**Question it answers:** What does the installed Claude Code CLI actually do when it is driven headlessly, and which of it has to be absorbed by an adapter?

## What they do

Everything here is true of `claude 2.1.219` on macOS 25.5.0 unless a line says otherwise — the
build every capture below was driven against, recorded in `cli-versions.lock`.[10] Two rows were
measured later against **2.1.220**, which is what the machine now has; both say so, and neither
contradicted the capture. Two labels are used and never blurred. **Measured** means a probe ran
against a real account and its output was kept; the golden stream in `tests/samples/` is 184 lines
of that output,[1] and `.knowledge/scripts/probe-claude` is a re-runnable probe beside it.[12]
**Assumed** means it was read off a flag surface, a help string or a vendor write-up and never
exercised. Where a doc-derived claim was later contradicted by a probe, it is marked **Refuted**
and both halves are given.

| Need | What `claude 2.1.219` does |
|---|---|
| Run one turn without a person | Measured: `claude -p --output-format stream-json --verbose --include-partial-messages`, prompt on **stdin**, JSONL on stdout.[1][2] |
| Say which conversation this was | Measured: `--session-id <uuid>` names a *new* conversation with an id the caller mints, so the handle exists before the first byte; `--resume <id>` continues it. Every line of the stream carries `session_id`.[1][4] |
| Carry a conversation on | Measured: a value stated in turn 1 was recalled in turn 2 across two separate processes, and `session_id` stayed stable.[4] Measured again in a harder form: turn 2's entire input was *"the second one"*, naming neither candidate word, and the answer resolved correctly.[5] |
| Say what a turn cost | Measured: `result.usage` is **per turn, not cumulative** — two one-word replies on one session reported `output` of 3 and 3, against Codex's 5/10/15 on the same shape of test.[8] |
| Say which model answered | Measured: `system/init.model` is `claude-opus-5[1m]`, and `result.modelUsage` keys name every model that did work in the turn.[1] |
| Keep one agent's sign-in from another's | Measured: `CLAUDE_CONFIG_DIR`. A fresh directory answers `{"is_error": true, "result": "Not logged in · Please run /login"}` and fills with `.claude.json`, `sessions/`, `projects/<cwd-slug>/` and `backups/`; nothing is inherited from `~/.claude`.[4] |
| Choose how much of the machine it may touch | Measured: the **allowlist**, and only the allowlist. `--permission-mode` is not a posture — see below.[5] |
| Be sent to mid-turn | Measured: no. `claude -p` reads its prompt and runs to the end; the shipped adapter's `interrupt()` is `child.kill('SIGINT')`, after which the session survives on disk and the next `--resume` picks it up.[3] |

### The stream: sixteen line kinds, and what each is for

Measured, counted off the golden's 184 lines.[1] The mapping column and every "why" is the Node
build's own, recorded line kind by line kind in `claude-events.json`.[2]

| Line | Lines in the golden | Maps to | Why, or why it is dropped |
|---|--:|---|---|
| `system/init` | 1 | nothing directly | the only carrier of `session_id` and `model`; its `tools`, `cwd`, `skills`, `plugins`, `agents` and `mcp_servers` lists are the machine's configuration, not turn activity |
| `system/status` | 10 | — | `requesting`/`idle` churn: ops noise, not audit |
| `system/thinking_tokens` | 4 | — | a reasoning meter (`estimated_tokens`, `estimated_tokens_delta`); usage is taken once, from `result` |
| `rate_limit_event` | 1 | — | account state (`five_hour` window, `resetsAt`), not this turn |
| `stream_event/message_start` | 10 | — | framing — **and it carries a full `usage` block**; counting it as well as `result` double-counts the cost |
| `stream_event/content_block_start` | 18 | — | framing |
| `content_block_delta` + `text_delta` | 10 | the reply | the live stream |
| `content_block_delta` + `thinking_delta` | 2 | reasoning | shape proven, content not: every captured delta carries an empty string |
| `content_block_delta` + `signature_delta` | 2 | — | the signature over redacted thinking; not text anyone reads |
| `content_block_delta` + `input_json_delta` | 56 | — | half-parsed tool arguments; the whole input arrives on the following `assistant` line |
| `stream_event/content_block_stop` | 18 | — | framing |
| `stream_event/message_delta` | 10 | — | framing — **and it carries a partial `usage` delta**; same double-count |
| `stream_event/message_stop` | 10 | — | framing |
| `assistant` | 18 | tool calls | `tool_use` blocks carry `id`/`name`/`input`; **`text` blocks are dropped — they repeat what already streamed** |
| `user` | 13 | tool results | `tool_result` carries `tool_use_id`, `content`, `is_error` |
| `result` | 1 | cost, then the end of the turn | the only line whose `usage` is counted; `is_error` decides the outcome |

A child that exits with **no `result` line at all** produces nothing an adapter can end a turn on;
the Node build synthesises one, because without it the daemon waits forever.[2]

### The reply arrives three times, and two of them are byte-identical

Measured, on the golden.[1] Concatenating the ten `text_delta` fragments gives **574 characters**.
Concatenating the three `assistant` text blocks gives the **same 574 characters** — identical,
byte for byte. An adapter that reports both reports every answer twice. Then `result.result`
carries a **third** copy of the final block alone (440 characters, equal to the last `assistant`
text block and not to the three joined).

So text arrives as **fragments**, and the whole of each thought arrives separately when that
thought is over: three `assistant` text blocks against ten delta fragments, in a turn that also
made 13 tool calls between them.[1]

### Usage: the field names, and the case that makes summing them a lie

Measured — the golden's `result.usage`, in full:[1]

```json
{"input_tokens": 20, "cache_creation_input_tokens": 17453, "cache_read_input_tokens": 302567,
 "output_tokens": 1510, "cache_creation": {"ephemeral_1h_input_tokens": 17453,
 "ephemeral_5m_input_tokens": 0}, "service_tier": "standard", "iterations": [...]}
```

**20 fresh tokens against 302,567 cache reads.** Cache *creation* is billed above standard input
and cache *reads* at a fraction of it, so the two cannot be added: summing them reports 320,020
tokens at one price, which is a number that is real and misleading. Reporting `input_tokens`
alone is no better — it drops the 17,453 that genuinely were new and charged at the higher
rate.[2]

Measured, and not previously written down anywhere: **the top-level `usage` block does not
account for every model that worked on the turn.** `modelUsage` names two —

```text
claude-opus-5[1m]            in     20   out 1510   cache-read 302567   cache-write 17453   $0.3636635
claude-haiku-4-5-20251001    in    563   out   15   cache-read      0   cache-write     0   $0.0006380
```

— and the top-level block is *exactly* the Opus row. Haiku's 563 in and 15 out appear nowhere in
it, while `total_cost_usd` (0.3643015) is the exact sum of both rows' `costUSD`. So the turn's
own usage block under-reports by one model's worth of tokens, and the money says so.[1]

Measured: the cache creation was **entirely the 1-hour tier** (17,453) with the 5-minute tier at
zero.[1] Assumed: those two tiers are priced differently, since a vendor that reports them apart
is unlikely to charge them the same — nothing here measured it.

### Tools: the vendor's own names, paired ids, and a list that is not constant

Measured, on the golden: 13 `tool_use` blocks with ids of the form `toolu_011WKukECbctmzqtWUjDo9CF`,
and 13 `tool_result` blocks whose `tool_use_id` matches — every call paired, none orphaned. The
names used were `TaskUpdate` (6), `TaskCreate` (3), `ToolSearch` (2), `Bash` (1) and `Read` (1).[1]
Its full vocabulary in the Node build's mapping is `Read`, `NotebookRead`, `WebFetch`, `Glob`,
`LS`, `Grep`, `WebSearch`, `ToolSearch`, `Bash`, `BashOutput`, `Task`, `Edit`, `Write`,
`NotebookEdit`.[3]

**The offered tool list is not a constant, and it is the owner's machine talking.** Measured: the
golden's `system/init` names **31** tools including `Glob` and `Grep`; the clarify probe's run
listed **29**, without them.[1][5] `TodoWrite` is absent from both — and the agent said so itself
in the golden, unprompted: *"TodoWrite isn't available in this session — the equivalent here is
TaskCreate/TaskUpdate."*[1] The same `init` line also enumerates the machine's plugins, subagents,
skills, slash commands and MCP servers, which is where the variation comes from.[1]

Consequence recorded by the Node build: three tools its allowlist named — `Glob`, `Grep`,
`TodoWrite` — did not exist in the build that ran, so `todo_update` had no live producer.[5]

### Questions, approvals and plan mode: nothing is capturable headless

Measured, three separate findings:[5]

- **`AskUserQuestion` is not offered headless, and allowlisting it changes nothing.** The probe
  printed the offered list and `AskUserQuestion offered: NO`, `ExitPlanMode offered: NO`,
  `TodoWrite offered: NO`. Asked something genuinely ambiguous *with `AskUserQuestion` explicitly
  allowlisted*, the CLI used no tool at all and ended the turn (exit 0) with the question as
  ordinary assistant text.
- **`--permission-mode plan` never returns.** It did not emit `ExitPlanMode`, said so itself —
  *"ExitPlanMode isn't available in this session, so here's the plan for review directly"* — and
  then did not terminate inside a 120-second deadline. Any probe touching plan mode needs its own
  kill timer.[8]
- **`--permission-mode` is not a read-only posture.** Under `plan`, with no `--allowedTools`, the
  CLI still reached for `Write` and `Bash` and wrote a file outside the repository. What holds is
  the allowlist.

What does work is the boring path: **end the turn, then resume with the answer.** Measured on both
Claude and Codex, and it is the whole of the answer-routing mechanism — no pending-ask record is
needed to make an answer land.[5]

**Refuted.** The Node build's design doc `harness-loop-and-steering.md` §1 carried a capability
table built from vendor documentation and stamped "verified against `code.claude.com/docs`". It
said Claude Code *alone* among the three had a clean cooperative interrupt —
`ClaudeSDKClient.interrupt()`, drain the buffered output, continue the same session — and that
`AskUserQuestion` and `ExitPlanMode` were capture points a daemon could render as buttons.[9]
Both halves fell to probes: no question or plan is capturable headless at all,[5] and the shipped
adapter's `interrupt()` is a `SIGINT` to the child, exactly the kill-and-resume every other brain
gets.[3] No installed CLI, on this evidence, has a cooperative headless interrupt.

Unexamined, and sitting in plain sight in the golden: `system/init` advertises
`"capabilities": ["interrupt_receipt_v1", "interrupt_cancel_queued_v1", "msg_lifecycle_v1"]`.[1]
Nothing in the Node build ever asked what those are.

### A private home isolates the login too

Measured: pointing `CLAUDE_CONFIG_DIR` at a fresh directory produces `Not logged in · Please run
/login`, and everything the CLI owns lands inside it.[4]

**Refuted.** A prior research doc predicted that the per-user Keychain item
`Claude Code-credentials` would leak one login across every config dir. The item does exist and is
per-user — but 2.1.219 does **not** authenticate a session from it when `CLAUDE_CONFIG_DIR` points
elsewhere. The config dir gates it, so two agents need two `claude /login` runs.[4]

Not re-tested: whether two agents with different homes running *simultaneously* stay independent,
and whether a Keychain-write race appears under load.[4]

### The system prompt, and which flag does what

**Measured, and the answer has a shape nobody predicted.**[12] Three runs of one ask — *run
`echo ZEPHYR` and tell me what it printed* — with a rule the conversation cannot supply
(*end every reply with the word PINEAPPLE*), and the whole of it settled on what happened rather
than on how a reply read. Reproduced twice:

```text
                        prompt tokens        the rule landed   it still used Bash
no flag (the control)          48,268                     NO                  YES
--append-system-prompt         48,333  (+65)             YES                  YES
--system-prompt                42,139  (−6,129)          YES                  YES
```

**`--system-prompt` replaces, and the size of the prompt is what says so.** A flag that only added
words could not make a turn *smaller*; this one takes about 6,100 tokens of the default system
prompt away with it — 6,489 on the first run, 6,129 on the second — against 65 for the append form,
which is the rule itself and nothing more.

**And the tool instructions survive it.** The same ask reached for a shell under all three forms,
so what `--system-prompt` substitutes is the prose above the tools rather than everything the CLI
was built with. That is a *narrower* replacement than codex's `baseInstructions`, which takes the
tool instructions too — and it is still the flag never to map standing instructions onto, because
6,100 tokens of a brain's own instructions going missing is not something an owner asked for when
they typed a paragraph.

The control is what makes any of this readable. The no-flag run proves the ask itself works and
the rule is genuinely absent without one, so "it ignored the rule" and "it ignores that kind of
rule" cannot be confused — the mistake this repo already made once and wrote down.[8]

The claim being replaced was assumed, from the flag surface and the Node build's own choice, and
never exercised. The shipped adapter passes the append form only.[3] `probes/overhead.ts` was written to measure
exactly what appending costs — a four-row ladder from `--bare` up to the allowlist plus the
appended prompt — but no run of it was ever recorded, so its numbers do not exist.[11] Measured
about that probe, and the reason the first row could never work: `claude --bare` reads
`ANTHROPIC_API_KEY` only and ignores an OAuth login, so on a subscription machine it fails rather
than giving a clean no-context baseline.[8]

### Context files: no git fence, and it expands an `@import`

Measured with an unguessable marker planted in every candidate file and a referenced-by-nothing
`UNSEEN.md` as the control, reproduced identically on three consecutive runs.[6]

| File, relative to the agent's own directory | claude |
|---|:--:|
| `CLAUDE.md` — in the agent's own directory | loaded |
| `AGENTS.md` — in the agent's own directory | not loaded |
| `CLAUDE.md` — one directory up | **loaded** |
| `AGENTS.md` — one directory up | not loaded |
| `SOUL.md` — pulled in by an `@SOUL.md` import | **loaded** |
| `USER.md` — referenced by a Markdown link | not loaded |
| `UNSEEN.md` — referenced by nothing *(control)* | not loaded |

Two of those rows are Claude's alone among the three CLIs measured: it is the **only** one that
expands an `@import`, and the only one that reads a `CLAUDE.md` from the directory above.[6]

**A git boundary does not fence it.** `git init` in the agent's own directory dropped Codex's
inherited context by 60 tokens and Grok's by 57 — the fence works for them. Claude went *up* by
160, and the marker method showed the parent `CLAUDE.md` still arriving. A live turn confirmed the
consequence: the agent read its own `AGENTS.md`, then went and read the enclosing repository's,
because the root `CLAUDE.md` it had been handed tells it to.[6]

What did work was asking it not to: with the agent's own `CLAUDE.md` scoped — *a `CLAUDE.md` from
above belongs to a project you are not working on, ignore it* — the same turn read only its own
four files and the prompt fell from **16,928 to 9,230 tokens**. That is a behavioural mitigation,
not a boundary; the parent file is still in the context.[6]

Measured baseline, for scale: the same trivial ask cost **24,252** prompt tokens outside any
repository, against Codex's 17,047 and Grok's 5,842.[6]

### Skills

Measured, one skill planted per candidate directory each declaring its own unguessable code, **no
file-reading tool granted**, with `nowhere/skills/` as the control: Claude discovers exactly
`.claude/skills/` — not `.agents/skills/`, not `.grok/skills/`, not a bare `skills/`, which no
brain reads at all.[7]

Measured: **a read-only agent can use a skill.** Given the shipped read-only allowlist it returned
a planted skill's code, with and without a skill tool named in that allowlist.[7]

Measured, and the sharpest argument in the file for private homes: with no private provider home,
a real Claude agent listed the shared library's skill *and twelve of the machine owner's own
user-level skills* alongside it — in the always-on index, every turn.[7]

### Every flag trap, all of them measured

- `--output-format stream-json` **requires `--verbose`** under `-p`; without it the process exits
  1.[4][8] Measured at 2.1.220, and a drift worth recording because it is the good kind: the error
  now names the missing flag — `When using --print, --output-format=stream-json requires --verbose`
  — where at 2.1.219 it named only the format and sent a reader looking at the wrong argument.[12]
- `--allowedTools` is **variadic and swallows a trailing positional prompt**, and the error it
  produces — `Input must be provided either through stdin or as a prompt argument` — points at the
  wrong thing entirely. The prompt goes on **stdin**.[4][8]
- Three allowlisted tools did not exist in the build that ran; allowlisting an absent tool is a
  silent no-op, so a list can overstate what an agent can do and nothing says so.[5]
- `security find-generic-password -g` **prints the secret** to stderr. Existence checks only.[4]

Assumed, never isolated: `--include-partial-messages` is what produces the 98 `stream_event` lines
at all, and without it the reply would arrive only whole on the `assistant` line.[1]

## What we can borrow

- **Read one copy of the text and pick which.** Both copies are byte-identical, so the choice is
  free and the cost of getting it wrong is every answer reported twice. The deltas give a live
  stream; the `assistant` block gives a finished thought. Our seam has a word for exactly that
  distinction — `whole` — so an adapter can take the deltas as fragments and mark `whole` when
  the matching `assistant` block lands, and get both properties from one brain.
- **Take usage from `result` and from nowhere else.** Three lines carry a `usage` block —
  `message_start`, `message_delta` and `result` — and only the last is the turn.
- **Report `input_tokens + cache_creation_input_tokens` as fresh, and `cache_read_input_tokens` as
  cached, separately.** Creation is new content being written and is billed above standard input,
  so it belongs with fresh; reads are the cheap volume and belong on their own.
- **Cross-check the usage block against `modelUsage` before trusting it.** The measured turn's
  block silently omitted a second model's 578 tokens, and only the cost figure gave it away.
- **Mint the session id rather than waiting for one.** `--session-id` accepts an id we generate,
  so unlike Codex the handle exists before the first byte and cannot be lost by a crash mid-stream.
- **Ask the brain what it may do, never a mode.** The allowlist is the only thing measured to hold.
- **Take the model from `system/init`, which really does name one.** Claude can honestly answer
  `model: true` where Codex cannot.
- **Give the agent both `CLAUDE.md` and `AGENTS.md`, and scope the first.** One file cannot serve
  three brains, and the scoping sentence is worth 7,698 tokens a turn on the measured tree.

## What to avoid

- Do not read both copies of the reply. It is the single most expensive mistake this stream
  invites, and it is invisible — the turn looks right and says everything twice.
- Do not sum `cache_creation_input_tokens` and `cache_read_input_tokens`. On the measured turn
  that is 320,020 tokens priced as one thing when 302,567 of them cost a fraction of the rest.
- Do not treat `--permission-mode` as containment. It is a prompting policy; under `plan` with no
  allowlist this CLI wrote a file outside the repository.
- Do not send standing instructions through `--system-prompt`. Measured: it takes about 6,100
  tokens of the brain's own instructions with it. Nothing reports that, the tools keep working, and
  the turn merely behaves differently — which is the failure mode that gets blamed on the model.
- Do not touch plan mode from anything that has to finish. It never returned.
- Do not build a question or approval flow on `AskUserQuestion` or `ExitPlanMode`. Neither is
  offered headless, allowlisting does not change that, and a design that assumed otherwise is
  already in the record as refuted.
- Do not put the prompt on the command line. `--allowedTools` will eat it, and what somebody asks
  their agent is readable through the process list and kept in a shell's history anyway.
- Do not hardcode the tool list. It varies with the machine's plugins, skills and MCP servers —
  29 tools on one run and 31 on another, against the same binary.
- Do not let an adapter finish without a `done`. A child that dies before `result` produces
  nothing terminal, and whatever is waiting waits forever.
- Do not publish a tool's output. `tool_result.content` can hold file contents, credentials and
  private paths; what a surface shows is not the adapter's call to make.
- Do not copy or link an owner's credential into an agent's home. A fresh `CLAUDE_CONFIG_DIR` is
  logged out by design, and that is the isolation working — say what to run instead.
- Do not assume `claude` is on the PATH. A gateway started by the machine's supervisor gets a bare
  environment, and a name that resolves in a shell resolves to nothing there.
- Do not make any of this a test dependency. It needs an account and a network; the golden stream
  is committed precisely so the suite never does.

## Verdict for us

**Claude is the brain that most rewards the seam and least stresses it.** Everything the contract
in [`../guides/write-a-provider-adapter.md`](../guides/write-a-provider-adapter.md) asks for is
available honestly: `tools`, `resume`, `usage` and `model` are all `true`, tool calls come with
paired ids, the model is named rather than requested, and usage is already the turn's own — so
none of the running-total arithmetic Codex forced on us is needed here. `steer` is `false`, and
that is measured rather than conceded.

Three things must live inside the adapter and reach nothing else: the dedupe (deltas, not
`assistant` text), the usage split (`input + cache_creation` fresh, `cache_read` cached, and only
from `result`), and the fact that read-only is an allowlist. Every one of them is a number or a
posture that reads plausible when wrong.

**We adopt the golden stream as the fixture and never the account.** `tests/samples/claude-stream.jsonl`
is 184 lines of real output that cost real money and cannot be re-derived by reading anything; a
Python adapter's tests drive it offline, which is the only way this stays inside the "never let a
test reach the network" rule.

**We do not build questions, approvals or plan mode on this brain.** The capture points do not
exist headless. A question arrives as ordinary text, the turn ends, and the answer lands by
resuming — which is already correct behaviour with no machinery at all.

This feeds a `provider-` component that is not declared yet — adding one is the owner's call
(`AGENTS.md`, the component ontology) — and it is held to
[`../prd/provider-adapter.md`](../prd/provider-adapter.md), whose `R-PRV-9`, `R-PRV-17`, `R-PRV-18`
and `R-PRV-23` are each a row this note supplies the evidence for. Re-drive the capture and update
`tests/samples/cli-versions.lock` in the same change when the version moves; a fixture that does
not say what it is true of is not a fixture.

## Open questions

- **What the 6,100 tokens `--system-prompt` removes actually were.** It is measured that they go
  and that the tool instructions are not among them; what *is* in them was never enumerated, so
  "it replaces the prose above the tools" is a reading of one number and not an inventory.
- **Whether `--append-system-prompt` is read every turn or bound when a conversation is created.**
  Codex was measured to be the second kind and silently ignores it on resume; Claude was never
  asked, and an argument accepted and then dropped is worse than one never sent.
- **The `overhead.ts` numbers are lost.** The probe exists and was never recorded, so what the
  CLI's own baggage costs, and what standing instructions add on top of it, is unknown for this
  brain — while the same question has a hard answer for Codex (a 17.4k floor).[8]
- **`interrupt_receipt_v1`, `interrupt_cancel_queued_v1` and `msg_lifecycle_v1`** are advertised in
  every `system/init` line and were never investigated. If any of them is a cooperative interrupt
  or a mid-turn message path, the `steer: false` above is wrong.
- **The cache tiers were never reasoned about.** All 17,453 created tokens landed in
  `ephemeral_1h_input_tokens` with the 5-minute tier at zero; whether they price differently, and
  whether a resumed conversation keeps hitting the 1-hour tier, decides whether resume is as cheap
  as the whole design assumes.
- **Whether a second model's tokens should be added back.** The measured turn's usage block omitted
  563 in and 15 out that the cost figure charged for; reading `modelUsage` instead would fix it and
  would also change the meaning of `model` on the record.
- **Whether `--include-partial-messages` is really what produces the deltas**, and what the stream
  looks like without it.
- **Whether two agents with different `CLAUDE_CONFIG_DIR`s stay independent under concurrent load**,
  and whether a Keychain-write race appears then.
- **How a build that has drifted from 2.1.219 is noticed** before a turn fails on it — the tool
  list already varies between runs of the same binary, so a diff of the golden is a blunt signal.

## Sources

1. `tests/samples/claude-stream.jsonl` — the golden stream, 184 lines, `claude 2.1.219`, captured 2026-07-24 — (internal)
2. `../rundesk/src/contracts/claude-events.json` — line-kind vocabulary and the reason each drop — (internal)
3. `../rundesk/src/adapters/claude.ts` — the shipped Node adapter — (internal)
4. `../rundesk/docs/isolation.md` — `CLAUDE_CONFIG_DIR`, resume and flag traps, probed 2026-07-24 — (internal)
5. `../rundesk/docs/clarify.md` — headless questions, plan mode and allowlist-vs-mode, probed 2026-07-24 — (internal)
6. `../rundesk/docs/context-files.md` — what each brain auto-loads, marker method with a control — (internal)
7. `../rundesk/docs/tools-and-skills.md` — skill discovery and postures, probed 2026-07-24 — (internal)
8. `../rundesk/.knowledge/MEMORY.md` — the Node build's friction log — (internal)
9. `../rundesk/docs/design/harness-loop-and-steering.md` — the doc-derived capability table the probes refuted — (internal)
10. `tests/samples/cli-versions.lock` — the CLI versions every capture here is true of — (internal)
11. `../rundesk/probes/overhead.ts` — the prompt-overhead ladder, written and never recorded — (internal)
12. `.knowledge/scripts/probe-claude` against `claude 2.1.220` on macOS 25.5.0, 2026-07-26 — (internal)
