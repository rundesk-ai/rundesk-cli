# Research: The Grok CLI as an agent's brain

**Last updated:** 2026-07-26
**Question it answers:** What does the installed Grok CLI actually do when it is driven headlessly, and which of it has to be absorbed by an adapter?

## What they do

Everything here is true of `grok 0.2.111` (`grok-4.5-build`) on macOS 25.5.0 — the build every
capture below was driven against, recorded in `cli-versions.lock`.[9] Two labels are used and
never blurred. **Measured** means a probe ran against a real account and its output was kept; the
golden stream in `tests/samples/` is 79 lines of that output.[1] **Assumed** means it was read off
a flag surface, a help string or a vendor write-up and never exercised. Grok has more of the
second kind than either other brain, and where that is so it is said plainly rather than smoothed
over.

| Need | What `grok 0.2.111` does |
|---|---|
| Run one turn without a person | Measured: `grok -p "<prompt>" --output-format streaming-json`, JSONL on stdout. The prompt is the **value of a flag**, not a positional, so nothing can swallow it — and it is therefore visible in the process list.[1][3][10] |
| Say what happened as it works | Measured: three line kinds and no more — `thought`, `text`, `end`.[1] |
| Say what tools it ran | Measured: **nothing at all.** There are no tool events in this stream, in either output format. It runs a command and describes the result in prose.[2][6] |
| Say which conversation this was | Measured: `end.sessionId`. The golden was captured with no `--session-id` passed and came back with `019f95ad-a32b-7922-a669-e6e26f978901`, so the CLI mints one when the caller does not.[1][10] |
| Carry a conversation on | Assumed: `--resume <id>`, with `--session-id <uuid>` naming a *new* conversation. **The round trip has never been run** — see Open questions.[2] |
| Say what a turn cost | Measured field names, on the `end` line: `usage.{input_tokens, cache_read_input_tokens, output_tokens, reasoning_tokens, total_tokens}`, plus `total_cost_usd` and a `modelUsage` map. Whether they are per-turn or cumulative is **unmeasured** — one turn was ever captured.[1] |
| Say which model answered | Measured: the first key of `end.modelUsage` — `grok-4.5-build`, with `modelCalls: 1`.[1] |
| Keep one agent's sign-in from another's | Assumed: `GROK_HOME`. The shipped adapter sets it; the Node build's own roadmap carries it as **unproven** and no agent was ever configured with a private home.[3][7] |
| Choose how much of the machine it may touch | Measured: the `--tools` list, and only the `--tools` list. Two flags that look like they would help do not — see below.[4] |
| Be sent to mid-turn | Nothing measured. No steering surface is known, and there is no tool event to hang one off.[2] |

### Three line kinds, and one of them is the whole turn

Measured, counted off the golden's 79 lines.[1] The mapping column is the Node build's own,
recorded in `grok-events.json`.[2]

| Line | Lines in the golden | Maps to | Why, or why nothing exists |
|---|--:|---|---|
| `thought` | 41 | reasoning | `{"type":"thought","data":"<fragment>"}` — streamed a token at a time, and the **only** sign this brain gives that a turn is in progress, since it reports no tool work |
| `text` | 37 | the reply | `{"type":"text","data":"<fragment>"}` — identical shape to `thought`, one field apart |
| `end` | 1 | cost, then the end of the turn | `sessionId` is the resume handle; `stopReason === "EndTurn"` is the outcome |
| *(tool calls, tool results, todos, questions)* | 0 | — | **no source exists in this CLI** |

**Text arrives as fragments and never whole.** Measured: 37 `text` chunks concatenate to 215
characters, and nothing in the stream restates them.[1] There is no equivalent of Claude's whole
`assistant` block — so nothing is ever complete until the turn ends, and there is no double-count
to avoid either.

**`thought` and `text` are one field apart.** Measured: both are `{"type": …, "data": …}` on the
same shape, so anything scanning raw lines for `data` counts what the model merely thought
about as if it had said it.[5][6]

### No tool events at all — the finding, not a gap in the capture

Measured at 0.2.111, and deliberately: read tools were granted, a file was planted, and the CLI
was asked to read it. **It reported the file's contents, with `num_turns: 2`, and the stream
carried only `text` and `thought`.**[2] The golden itself is a one-turn conceptual question
(`num_turns: 1`) that used no tools, so the golden shows the shape and this probe shows the
absence.

Its tool names, when it does run them, are its own and match no other provider's: `read_file`,
`list_dir`, `grep`, `run_terminal_command`, `ask_user_question`, `spawn_subagent`, `todo_write`,
`edit_file`, `create_file`.[2][3] `ask_user_question` is worth noticing precisely because it
exists in that vocabulary and would still produce no event.

### Usage: the split matches Claude's, and there is no cache-write figure

Measured — the golden's `end` line, in full:[1]

```json
{"type":"end","stopReason":"EndTurn","sessionId":"019f95ad-…","requestId":"f7fd1b19-…",
 "usage":{"input_tokens":13373,"cache_read_input_tokens":5248,"output_tokens":192,
          "reasoning_tokens":151,"total_tokens":18813},
 "num_turns":1,"total_cost_usd":0.0294724,"total_cost_usd_ticks":294724000,
 "modelUsage":{"grok-4.5-build":{"inputTokens":13373,"outputTokens":192,
               "cacheReadInputTokens":5248,"modelCalls":1,"costUSD":0.0294724}}}
```

Measured: **`input_tokens` excludes `cache_read_input_tokens`.** 13,373 + 5,248 + 192 = 18,813,
which is `total_tokens` exactly. So fresh and cached are already apart, as they are on Claude and
unlike Codex, where the cache is folded inside the input count.[1][2]

Measured: **there is no cache-*creation* field.** Grok reports what it read from cache and says
nothing about what it wrote into it — so on this brain the cache-write tier that costs above
standard input on the other two is simply not visible.[1]

Measured: `modelUsage` restates the same three numbers for the one model, and its `costUSD`
equals `total_cost_usd` exactly.[1] Unmeasured: whether `reasoning_tokens` (151) sits inside
`output_tokens` (192) or beside it — 151 is smaller than 192, which is suggestive and not
evidence.

**Per-turn or cumulative is the single biggest hole.** One turn was captured, `num_turns: 1`, so
the question Codex answered badly (a running total for the whole thread) and Claude answered well
(the turn's own share) has never been asked of this brain at all.

### Two flags that read like containment and are not

Measured by giving the CLI the invocation under test in a throwaway directory and looking at what
happened **on disk**, not at what the CLI reported.[4]

| Flag | What it reads like | What it does |
|---|---|---|
| `--permission-mode dontAsk` | deny anything without an explicit allow | **accepted and silently ignored** — the session keeps the default prompting policy |
| `--sandbox read-only` / `strict` | kernel-enforced filesystem limits | **no-op headless** |

**`--permission-mode dontAsk` was a live shipped bug, and its failure mode is the worst kind.**
The adapter passed it for both postures, so an agent configured for full access was given every
write tool and then denied all of them: headless, a call that would prompt is cancelled and
reported to the model. Asked to create a file, the agent wrote nothing and said so in prose —

> "I wasn't able to create the file — file-write and shell tools are currently blocked by the
> prompt policy in this session."

— **while the turn itself reported success.** Nothing in the test suite could see it: the flag was
present, the argv looked deliberate, and the write tools genuinely were named. Only
`bypassPermissions` and `default` are applied by this flag; the same word set through
`defaultMode` in a settings file does work. Re-running with `bypassPermissions` created the
file.[2][4][6]

**`--sandbox` is worse than useless, because it reads like a guarantee.** Under
`--sandbox read-only` the CLI created a file both through its own `create_file` tool *and* through
a shell redirect. Under `--sandbox strict`, documented as limiting reads to the working directory
and system paths, it read a planted marker well outside that directory and reported the
contents.[4]

Measured consequence: **what scopes this brain is the tool list, and only the tool list.** A tool
never granted cannot be called. Read-only on the shipped adapter is
`--tools read_file,list_dir,grep` with no mode at all.[3]

Measured consequence of that: **a read-only Grok agent has no shell.** `run_terminal_command` is
the only shell this CLI offers and it cannot be scoped to a command prefix the way another brain
scopes `Bash(ls:*)`, so it is not granted — and because the sandbox does not hold, there is no
safe way to hand one over either.[4]

Assumed, and worth flagging about the golden itself: it was captured with `--permission-mode plan`,
annotated in the probe as "read-only for a probe".[10] Since only `bypassPermissions` and
`default` are applied by that flag, the capture almost certainly ran under the default policy
rather than the one its comment claims. It made no tool calls, so nothing in the golden turns on
it.

### The system prompt, and which flag does what

Assumed, from the CLI's own help string and never exercised: `--rules` is described as "extra
rules to append to the system prompt" and therefore **appends**, while
`--system-prompt-override` **replaces** what the brain was built with. The shipped adapter passes
`--rules` only.[2][3] Neither has been probed — not whether `--rules` actually lands, and not
whether it is re-read on a resume or bound once when a conversation is created (Codex was measured
to be the second kind and to drop it silently afterwards).

### Isolation is the one thing every other brain proved and this one did not

Assumed, sourced to vendor write-ups rather than a probe: `GROK_HOME` defaults to `~/.grok` and
covers "config, auth, sessions, skills, plugins, logs" — a direct analogue of the variable that
was measured to isolate Codex.[8] The doc that made the claim flagged it for a Phase-0 probe in
the same breath; the probe was never run.[7][8]

Measured, by absence: the isolation probe that settled `CLAUDE_CONFIG_DIR` and `CODEX_HOME`
covered those two only, and the Node build's roadmap carries `GROK_HOME` isolation as an open
unknown, with no agent ever configured with a private home because isolating an agent into a home
it has no login for breaks it.[7]

Also assumed, from the same write-up: headless runs need a cached subscription token or
`XAI_API_KEY`, and long-running subscription-token refresh behaviour is undocumented.[8]

### Context files: it reads both, from its own directory only, and a git init fences it

Measured with an unguessable marker planted in every candidate file and a referenced-by-nothing
`UNSEEN.md` as the control, reproduced identically on three consecutive runs.[5]

| File, relative to the agent's own directory | grok |
|---|:--:|
| `CLAUDE.md` — in the agent's own directory | **loaded** |
| `AGENTS.md` — in the agent's own directory | **loaded** |
| `CLAUDE.md` — one directory up | not loaded |
| `AGENTS.md` — one directory up | not loaded |
| `SOUL.md` — pulled in by an `@SOUL.md` import | not loaded |
| `USER.md` — referenced by a Markdown link | not loaded |
| `UNSEEN.md` — referenced by nothing *(control)* | not loaded |

Grok is the only one of the three that reads **both** context-file names, and it does not expand
an `@import` — so identity held in a separate file costs it a tool call, or must be inlined.[5]

Measured: **a git boundary does fence it.** An agent directory inside the project inherited that
project's `AGENTS.md` at a cost of **+2,729 tokens every turn**; `git init` in the agent's own
directory took that to **−57**, which is noise. One `git init` per agent directory is the fence
for this brain, where it is not for Claude.[5]

Measured baseline, for scale: the same trivial ask cost **5,842** prompt tokens outside any
repository, against Codex's 17,047 and Claude's 24,252. Grok is by a wide margin the cheapest
brain measured to start a turn.[5]

### Skills: it reads every vendor's directory

Measured, one skill planted per candidate directory each declaring its own unguessable code, **no
file-reading tool granted**, with `nowhere/skills/` as the control: Grok discovers
`.grok/skills/`, `.agents/skills/` **and** `.claude/skills/` — its own place and both other
vendors' — and it documents that it deduplicates by name, so a skill reached through more than one
is indexed once. A bare `skills/` is discovered by nobody.[4]

### Questions, approvals, mid-turn input

Nothing measured. The clarify probe that established how a headless question arrives, and that an
answer lands by resuming, covered Claude and Codex only.[11] For Grok the equivalent behaviour is
unknown, and `ask_user_question` being in its tool vocabulary is not evidence of anything, since
no tool it calls appears in the stream.

### Flag traps

- Measured: **`--allow` takes one rule per flag and rejects a space-separated list** —
  `unknown tool prefix: …`. Use `--tools`, which takes a comma-separated list of built-in tool
  names.[2][6]
- Measured: `--permission-mode dontAsk` and `--sandbox` are the two above, and both fail silently.
- Measured, once: Grok inside a freshly `git init`-ed directory exceeded a 120-second deadline,
  then behaved normally on the following runs.[5]
- Measured: macOS has no `timeout`, so anything driving this CLI with a deadline needs
  `perl -e 'alarm shift; exec @ARGV' <secs> …` or a kill timer of its own.[6]

## What we can borrow

- **A brain that reports nothing about its tools is a whole brain, not a broken one.** Grok is the
  proof case for that claim in the contract — three of the seven record kinds are all it can
  honestly produce, and the surface simply shows less. Nothing should be invented to fill the gap.
- **Report `input_tokens` as fresh and `cache_read_input_tokens` as cached, unchanged.** The split
  already matches the shape our seam asks for; no subtraction is needed, and none should be
  invented until per-turn-vs-cumulative is settled.
- **Omit `cached` rather than guessing it, if the field is ever missing.** An absent value means
  *could not tell*, which is different from zero — and on this brain the cache-write side genuinely
  cannot be told at all.
- **Take the model from `modelUsage`, which is reported rather than requested.** A silent model
  substitution would show up there and nowhere else.
- **Pass the tool list and nothing that implies a limit we do not have.** No `--sandbox`, no
  `--permission-mode` outside the one value that is applied.
- **`git init` in an agent's own directory, for this brain, is worth 2,729 tokens a turn.**
- **Grok is the cheap brain.** At 5,842 tokens of baseline against Claude's 24,252, it is the one
  to reach for when a turn is small and its lack of tool visibility does not matter.

## What to avoid

- Never trust a flag this CLI accepted. Two of the three that look like containment are accepted
  and do nothing, and one of them shipped a bug where an agent with full access could write
  nothing while its turn reported success. On this brain, "the argv looked deliberate" is not
  evidence of anything.
- Do not report a posture as containment. The tool list is what holds; say that, and nothing more.
- Do not grant `run_terminal_command` to a read-only agent. It is the only shell offered and it
  cannot be scoped by prefix, so there is no partial version of it to grant.
- Do not scan raw lines for `data`. `thought` and `text` differ by one field, and counting both
  publishes what the model merely considered.
- Do not report a `cached` figure this brain did not give, and do not infer a cache-write number
  from the absence of one.
- Do not build a spend limit on this brain's usage until per-turn-vs-cumulative is measured. If it
  turns out cumulative, the limit fires on how long a conversation is rather than on what it cost —
  the exact trap Codex set.
- Do not claim `resume: true` for it on the strength of a flag existing. Reporting a capability
  that is not there costs the next turn its context, silently.
- Do not put a private `GROK_HOME` in front of an agent and call it isolation. It is untested, and
  an agent isolated into a home it has no login for is an agent that cannot work at all.
- Do not put a secret on this command line. The prompt is already a flag value and therefore in
  the process list; nothing else should join it there.
- Do not make any of this a test dependency. The golden stream is committed so the suite never
  needs an account, a token or a network.

## Verdict for us

**Grok is the honest floor, and that is its whole value to the seam.** It is the brain that proves
the contract in [`../guides/write-a-provider-adapter.md`](../guides/write-a-provider-adapter.md)
degrades rather than breaks: `tools: false`, `steer: false`, `usage: true`, `model: true`, and
`resume` claimed only once the round trip has actually been run. A turn on it is a stream of
fragments and a cost, and that is a complete turn.

**We take the invocation, the three line kinds and the usage split as settled, and nothing else.**
Everything about how this CLI is *governed* — isolation, resume, standing instructions, whether
the cost figure is a turn's or a thread's — is either unproven or read off a flag. Those are not
details; each of them is a way for a Python adapter to look correct and be wrong, which is exactly
the failure `--permission-mode dontAsk` already produced once in the Node build.

**The `dontAsk` bug is the lesson we carry over, not the flag.** A vendor CLI accepted an argument,
ignored it, and let the turn report success. Nothing in a test suite could see it because the
adapter did everything right on its own terms. The defence is that a posture is only ever claimed
on measured behaviour, and `AGENTS.md`'s "never let a command report success it did not earn"
extends to what an adapter says a brain is doing.

This feeds a `provider-` component that is not declared yet — adding one is the owner's call
(`AGENTS.md`, the component ontology) — and it is held to
[`../prd/provider-adapter.md`](../prd/provider-adapter.md), where `R-PRV-7` (an adapter that runs
no tools reports none), `R-PRV-9`, `R-PRV-15` and `R-PRV-18` are the rows this brain exercises
hardest. Re-drive the capture and update `tests/samples/cli-versions.lock` in the same change when
the version moves.

## Open questions

**These four are the shopping list for the next live probe, in the order they matter.**

- **The resume round trip.** `--session-id` minting a new conversation and `--resume` continuing it
  is recorded but never exercised end to end — write a value on turn 1, ask for it on turn 2 in a
  separate process, and see whether it comes back. Until then `resume` cannot honestly be claimed.
- **Per-turn or cumulative usage.** Three one-word replies on one session, the same test that
  caught Codex. If the numbers grow, the adapter needs the subtraction and a place to keep what it
  subtracts from; if they do not, it needs neither.
- **`GROK_HOME` isolation.** Point it at an empty directory and see whether the run fails closed
  the way a fresh `CODEX_HOME` and a fresh `CLAUDE_CONFIG_DIR` both did — and see what the CLI
  actually writes into it.
- **`--system-prompt-override` and `--rules`.** Whether `--rules` lands at all, whether it is
  re-read on a resume or bound at conversation creation, and what `--system-prompt-override`
  really substitutes. An argument accepted and then dropped reads like it works.

Beyond those:

- Whether `reasoning_tokens` is inside `output_tokens` or beside it.
- Whether this brain can be asked a question or sent to mid-turn at all, and what a headless
  question looks like when it arrives — the clarify probe never covered it.
- What `--permission-mode plan` does headless, given the same flag ignores `dontAsk`.
- Whether a cached subscription token survives a long-running headless agent, or whether
  `XAI_API_KEY` is mandatory for anything always-on.
- Whether the tool list is stable across machines and configurations the way the golden's is
  assumed to be — the equivalent list on another brain was measured to vary run to run.
- What this CLI's own baseline prompt is made of, since at 5,842 tokens it is a third of Codex's
  and a quarter of Claude's and nothing has explained the gap.

## Sources

1. `tests/samples/grok-stream.jsonl` — the golden stream, 79 lines, `grok 0.2.111`, captured 2026-07-24 — (internal)
2. `../rundesk/src/contracts/grok-events.json` — vocabulary, quirks, and the no-tool-events finding — (internal)
3. `../rundesk/src/adapters/grok.ts` — the shipped Node adapter — (internal)
4. `../rundesk/docs/tools-and-skills.md` — the two flags that do not scope it, and skill discovery, probed 2026-07-24 — (internal)
5. `../rundesk/docs/context-files.md` — what it auto-loads, the git fence, and the baseline token counts — (internal)
6. `../rundesk/.knowledge/MEMORY.md` — the Node build's friction log — (internal)
7. `../rundesk/docs/ROADMAP.md` — U-3, `GROK_HOME` isolation carried as unproven — (internal)
8. `../rundesk/.knowledge/research/provider-clis-and-tos.md` — the doc-derived `GROK_HOME` and auth claims, with their own verify-in-Phase-0 caveat — (internal)
9. `tests/samples/cli-versions.lock` — the CLI versions every capture here is true of — (internal)
10. `../rundesk/probes/capture.ts` — the exact invocation the golden was captured with — (internal)
11. `../rundesk/docs/clarify.md` — the headless-question probe, which covered Claude and Codex only — (internal)
