# Research: The Grok CLI as an agent's brain

**Last updated:** 2026-08-02
**Question it answers:** What does the installed Grok CLI actually do when it is driven headlessly, and which of it has to be absorbed by an adapter?

## What they do

The golden and original probes use `grok 0.2.111` (`grok-4.5-build`) on macOS 25.5.0, recorded in
`cli-versions.lock`; the ACP probes use the installed 0.2.112 build.[9][14] Two labels are used and
never blurred. **Measured** means a probe ran against a real account and its output was kept; the
golden stream in `tests/samples/` is 79 lines of that output,[1] and `.knowledge/scripts/probe-grok`
is a re-runnable probe that settled four more things on 2026-07-26.[12] **Assumed** means it was
read off a flag surface, a help string or a vendor write-up and never exercised.

| Need | What the measured Grok builds do |
|---|---|
| Run one turn without a person | Measured: `grok -p "<prompt>" --output-format streaming-json`, JSONL on stdout. The prompt is the **value of a flag**, not a positional, so nothing can swallow it — and it is therefore visible in the process list.[1][3][10] Measured since: `--prompt-file <path>` carries a turn identically, so it need not be.[12] |
| Say what happened as it works | Measured: one-shot `streaming-json` has only `thought`, `text`, `end`; ACP adds message, thought, tool-call and tool-result events.[1][13][14] |
| Say what tools it ran | Measured: **not in one-shot output, but fully in ACP.** `tool_call` carries a stable id, name and input; `tool_call_update` carries the same id, status, output and locations.[13][14] |
| Say which conversation this was | Measured: `end.sessionId`. The golden was captured with no `--session-id` passed and came back with `019f95ad-a32b-7922-a669-e6e26f978901`, so the CLI mints one when the caller does not.[1][10] |
| Carry a conversation on | Measured: `--resume <id>` carries context in one-shot mode; ACP `session/load` carries the exact session into a new adapter process without replaying its history as new output.[12][14] |
| Say what a turn cost | Measured: on the `end` line, `usage.{input_tokens, cache_read_input_tokens, output_tokens, reasoning_tokens, total_tokens}` plus `total_cost_usd` and a `modelUsage` map — and **per turn, not cumulative**: three one-word replies on one session reported `output_tokens` of 31, 21 and 21.[1][12] |
| Say which model answered | Measured: the first key of `end.modelUsage` — `grok-4.5-build`, with `modelCalls: 1`.[1] |
| Keep one agent's sign-in from another's | Measured: `GROK_HOME`. A fresh directory fails the turn closed — exit 1, `Error: Not signed in`, naming `grok login --device-code` — and the CLI fills it with `config.toml`, `sessions/`, `logs/`, `agent_id` and its own lockfiles.[12] |
| Choose how much of the machine it may touch | **Depends entirely on the transport, and the two answers do not overlap.** One-shot: the `--tools` list, and only that list — with `--tools read_file,list_dir,grep` a turn could not create a file, with the fuller list it could, and with the flag left off entirely it could, so omitting it is how this CLI says every built-in.[4] ACP: **not `--tools` at all** — it is documented headless-only, and `agent stdio` accepts it in silence and hands the turn every built-in. What holds there is `session/new._meta.agentProfile`, measured 2026-08-02 on 0.2.112 and detailed below.[16] Two flags that merely look like they would help do neither — see below.[4] Note `-p/--single` is the single-turn form; piping a prompt on stdin fails with `Device not configured (os error 6)`. |
| Be sent to mid-turn | ACP keeps stdin open and supports a long-lived session, but sending another prompt during an active turn is not measured.[13] |

### The one-shot format has three line kinds

Measured, counted off the golden's 79 lines.[1] The mapping column is the Node build's own,
recorded in `grok-events.json`.[2]

| Line | Lines in the golden | Maps to | Why, or why nothing exists |
|---|--:|---|---|
| `thought` | 41 | reasoning | `{"type":"thought","data":"<fragment>"}` — streamed a token at a time, and the only progress signal in this one-shot format |
| `text` | 37 | the reply | `{"type":"text","data":"<fragment>"}` — identical shape to `thought`, one field apart |
| `end` | 1 | cost, then the end of the turn | `sessionId` is the resume handle; `stopReason === "EndTurn"` is the outcome |
| *(tool calls, tool results, todos, questions)* | 0 | — | **no source exists in this output format; ACP supplies tool calls and results** |

**Text arrives as fragments and never whole.** Measured: 37 `text` chunks concatenate to 215
characters, and nothing in the stream restates them.[1] There is no equivalent of Claude's whole
`assistant` block — so nothing is ever complete until the turn ends, and there is no double-count
to avoid either.

**`thought` and `text` are one field apart.** Measured: both are `{"type": …, "data": …}` on the
same shape, so anything scanning raw lines for `data` counts what the model merely thought
about as if it had said it.[5][6]

### One-shot output hides tools; ACP reports them

Measured at 0.2.111, and deliberately: read tools were granted, a file was planted, and the CLI
was asked to read it. **It reported the file's contents, with `num_turns: 2`, and the stream
carried only `text` and `thought`.**[2] The golden itself is a one-turn conceptual question
(`num_turns: 1`) that used no tools, so the golden shows the shape and this probe shows the
absence.

Its tool names, when it does run them, are its own and match no other provider's: `read_file`,
`list_dir`, `grep`, `run_terminal_command`, `ask_user_question`, `spawn_subagent`, `todo_write`,
`edit_file`, `create_file`.[2][3] `ask_user_question` is worth noticing precisely because it
exists in that vocabulary and would still produce no event.

Measured at 0.2.112: that absence belongs to the **one-shot output format**, not the agent.
`grok agent stdio` speaks the documented ACP JSON-RPC interface and streams
`agent_thought_chunk`, `agent_message_chunk`, `tool_call`, `tool_call_update` and a terminal
`turn_completed` update.[13][14] A controlled working turn created, read, edited and counted a
file; ACP named the tools `write`, `read_file`, `search_replace` and `run_terminal_command`, gave
each a stable `toolCallId`, then paired it with `status: completed` and `rawOutput` on the same
id.[14]

The intermediate tool update carries a broad `kind` and `locations`; the terminal update carries
the outcome. No path or command has to be parsed out of prose, and no post-turn Markdown export
has to be scraped.[14]

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

ACP labels the fields differently and includes cached reads inside `inputTokens`: a measured turn
reported 26,797 input, 24,448 cached and 81 output, with 26,878 total.[14] The adapter therefore
subtracts cached reads once to preserve the seam's fresh/cached split; applying the one-shot rule
to ACP would double-count 24,448 tokens.

Measured: `modelUsage` restates the same three numbers for the one model, and its `costUSD`
equals `total_cost_usd` exactly.[1] Unmeasured: whether `reasoning_tokens` (151) sits inside
`output_tokens` (192) or beside it — 151 is smaller than 192, which is suggestive and not
evidence.

**Per-turn, measured — the question Codex answered badly.** Three one-word replies on one
session, run twice:[12]

```text
turn 1: {"input_tokens": 11394, "cache_read_input_tokens":  5248, "output_tokens": 31}
turn 2: {"input_tokens":   304, "cache_read_input_tokens": 16640, "output_tokens": 21}
turn 3: {"input_tokens":   483, "cache_read_input_tokens": 34048, "output_tokens": 81}
```

Output did not climb, so nothing is accumulating and no subtraction is needed. What *does* grow
is `cache_read_input_tokens`, which is the conversation being re-read each turn — a real per-turn
cost and not a running total. `input_tokens` collapsing after turn one is the same thing seen from
the other side: almost all of the prompt is being served from cache by then.

Measured, and worth not tripping over: `end.usage.input_tokens` and
`end.modelUsage.<model>.inputTokens` disagree by about 20 tokens on the same turn (11,394 against
11,424).[12] Either is defensible; taking both from the same place every time is what matters.

### It answers from conversations it was never given

Measured, and found only because the resume probe carried a control.[12] A turn in a **fresh**
session — no `--resume`, no `--session-id` — was asked to pick "the second one" of two codewords
it had never been shown, and it produced the right one, saying so as it went:

> "No prior context in this session — checking recent sessions for what 'the second one' refers
> to."

So this CLI reads its own past sessions by default. Two consequences, and the first is why this
paragraph exists at all: **a resume probe without a control reports success when nothing was
resumed** — the naive version of this probe did exactly that, and would have had an adapter claim
`resume` on cross-session recall. Re-run with `--no-memory` on every turn and candidates minted
per run, the control failed as it should (*"I don't have prior context for which codewords you
mean"*) and the resumed turn answered — which is the measurement in the table above.

The second consequence is the seam's: one conversation reading another's contents is exactly what
a private home and a per-conversation handle exist to prevent, and `GROK_HOME` does not stop it
because both conversations live in the same home.

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
never granted cannot be called. On the one-shot transport that list is `--tools`; on ACP it is
`_meta.agentProfile`, and the flag is one more thing accepted that enforces nothing.[3][16]

Measured consequence of that: **a read-only Grok agent has no shell.** `run_terminal_command` is
the only shell this CLI offers and it cannot be scoped to a command prefix the way another brain
scopes `Bash(ls:*)`, so it is not granted — and because the sandbox does not hold, there is no
safe way to hand one over either.[4]

Assumed, and worth flagging about the golden itself: it was captured with `--permission-mode plan`,
annotated in the probe as "read-only for a probe".[10] Since only `bypassPermissions` and
`default` are applied by that flag, the capture almost certainly ran under the default policy
rather than the one its comment claims. It made no tool calls, so nothing in the golden turns on
it.

### The system prompt, and which transport actually applies it

Measured on 0.2.112: root `--rules` appends in one-shot mode but is silently ignored by
`grok agent stdio`. ACP exposes the equivalent as `_meta.rules` on `session/new`; a live turn
returned an unguessable marker supplied only there, then an indirect “send me the file” turn emitted
Rundesk's exact attachment declaration. The installed official guide names this field “Extra rules
appended to the system prompt.” `systemPromptOverride` replaces the prompt and is never used.[15]

Rules bind when an ACP conversation is created. The adapter sends `_meta.rules` on `session/new`
and nothing on `session/load`, matching the conversation-bound behavior measured for Codex.[15]

### What scopes an ACP turn's tools, and the three things that do not

Measured 2026-08-02 against 0.2.112, one live turn per row, each asked to name its tools and then
to call `run_terminal_command` with `pwd`. What is believed is the recorded `tool_call` updates.[16]

| Session opened as | Tools the turn reported | Ran `pwd` |
|---|---|:--:|
| root `--tools read_file,list_dir,grep` | all 31 built-ins | **yes** |
| root `--deny Bash --deny Edit --deny Write --deny WebFetch --deny WebSearch --deny MCPTool` | all 31 built-ins | **yes** |
| `_meta.agentProfile` with `injectDefaultTools: false`, `tools: [read_file, list_dir, grep]` | those three, plus `search_tool` and `use_tool` | no |
| the same, plus `disallowedTools: [search_tool, use_tool]` | exactly those three | no |
| nothing | all 31 built-ins | **yes** |

So **the root command line does not reach an ACP turn's tool set at all** — neither the allowlist
nor the permission rules, both of which the vendor's own help calls headless-only or describes as
working "in both modes" meaning TUI and headless. This is the `dontAsk` trap a third time: accepted,
silent, enforcing nothing.

`_meta.agentProfile` takes an agent definition — the same shape as a `.grok/agents/*.md`
frontmatter, in camelCase — and its `tools` is an allowlist only when `injectDefaultTools` is
`false`; the vendor documents a stock profile as injecting its optional tools *before* the
allowlist applies. `search_tool` and `use_tool` are documented as always-on MCP meta-tools and
survive `tools`; they are removed by name through `disallowedTools`, which the vendor documents as
winning over the allowlist. Naming the `MCPTool` permission class instead does nothing, because
permission rules are the row above.

Two things it does that `_meta.rules` does not:

- **It binds on `session/load` too.** A conversation created with no profile at all came back, when
  loaded with the read profile attached, naming exactly the three read tools and unable to run a
  shell command. So a resumed turn is narrowed by the posture the owner holds *now*, and an agent
  moved to `read` after a working conversation was opened does not keep that conversation's tools.
- **A profile it cannot parse is not refused.** `session/new` succeeds and the conversation quietly
  gets the default agent, which is every tool there is. The only thing said is on stderr:
  `ERROR Failed to parse _meta.agentProfile JSON object, falling back to default agent`. That line
  is the whole drift signal, and it is why this has to be re-probed when the version moves rather
  than assumed from the schema.

Read posture bounds **tools, not paths**: the live read turn read `~/.grok/docs/user-guide/*.md`
and `~/.grok/README.md` while hunting for a shell, which is the same finding as `--sandbox`
enforcing nothing. A posture is a tool boundary on this brain and must never be described as
containment.

### Isolation: the one thing every other brain proved, now proved here too

Measured, and it was the last of the three to be asked.[12] `GROK_HOME` pointed at an empty
directory fails the turn closed:

```text
exit 1
Error: Not signed in. To authenticate without a browser, run:
  grok login --device-code
Alternatively, set the XAI_API_KEY environment variable or run `grok login` on a machine
with a browser.
```

and the CLI fills that directory with `config.toml`, `sessions/`, `logs/`, `docs/`, `agent_id`,
`active_sessions.json` and its own lockfiles. So the variable covers the sign-in and not only the
configuration, exactly as `CODEX_HOME` and `CLAUDE_CONFIG_DIR` do — an agent's private home is
empty the first time it reaches this brain, which for this brain means not signed in, and the
error names the command to fix it.

The claim being replaced was assumed rather than probed: a vendor write-up said `GROK_HOME`
defaults to `~/.grok` and covers "config, auth, sessions, skills, plugins, logs", and flagged
itself for a Phase-0 probe that was never run.[7][8] It was right.

Still assumed, from that same write-up: headless runs need a cached subscription token or
`XAI_API_KEY`, and long-running subscription-token refresh behaviour is undocumented.[8]

### Conversations are filed by the directory a turn was run in

Measured: this brain keeps its sessions at `~/.grok/sessions/<url-encoded working directory>` —
one directory per place a turn was run, holding that place's conversations and nothing else.[12]
Claude does the same thing under another name, filing at `~/.claude/projects/<cwd slug>/`, with
the session id that a resume handle names as a `.jsonl` inside it.[12]

So **standing a turn in the agent's own directory is what separates one agent's conversations
from another's**, and it happens whether or not anything relocates the brain's home. That is the
same isolation a person gets by `cd`-ing into a project and running the CLI, and it is already
what rundesk does for every turn.

What relocating `GROK_HOME` adds on top is a second login to create and nothing else, which is
why the shipped adapter stopped doing it. What it would still buy, for an owner who wants it, is
a genuinely *separate account* — and that is a thing to ask for rather than a default to impose.

### The prompt does not have to be on the command line

Measured: `--prompt-file <path>` is on this build's help, appears in none of the carried-over
evidence, and carries a whole turn — the same trivial ask answered `ORANGE` through a file as it
does through `-p`.[12] ACP goes further: `session/prompt` sends the prompt as JSON-RPC over stdin,
so no prompt value or temporary prompt file is needed.[13][14]

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

ACP is a long-lived bidirectional connection, and `--always-approve` completed controlled file and
terminal calls without stopping for a person.[13][14] What remains unmeasured is whether a
headless `ask_user_question` arrives as an ACP interaction, and whether a second prompt can steer
an active turn. The earlier headless-question probe covered Claude and Codex, not Grok; a tool
existing in Grok's vocabulary is not evidence of either.[11]

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

- **Choose the integration stream that preserves what happened.** Grok's one-shot JSONL hides
  tools that ACP reports with stable ids and terminal outcomes; an adapter must not call the
  lossy stream the whole truth.[13][14]
- **Report `input_tokens` as fresh and `cache_read_input_tokens` as cached, unchanged.** The split
  already matches the shape our seam asks for, and the counts are now measured to be a turn's own,
  so no subtraction is needed and none should be invented.
- **Close the cross-session door explicitly.** `--no-memory` on every turn is what makes a resume
  handle mean what it says. Without it this CLI answers from conversations it was never handed,
  and the failure is invisible: the turn is right, and it is right for the wrong reason.
- **Separate agents by where they stand, not by relocating the brain's home.** Both this CLI and
  Claude file conversations under the working directory, so standing a turn in its own agent's
  home already separates them — and it costs nothing, needs no second login, and is what a person
  does by hand. Moving the home is for a different *account*, which is a thing to be asked for.
- **Send the prompt over ACP stdin.** What somebody asked their agent never has to appear in the
  process list or a temporary file.[13][14]
- **Omit `cached` rather than guessing it, if the field is ever missing.** An absent value means
  *could not tell*, which is different from zero — and on this brain the cache-write side genuinely
  cannot be told at all.
- **Take the model from `modelUsage`, which is reported rather than requested.** A silent model
  substitution would show up there and nowhere else.
- **Pass the tool list where the transport reads it, and nothing that implies a limit we do not
  have.** On ACP that is `_meta.agentProfile`; the root `--tools` and `--deny` flags belong to the
  one-shot transport and are silently inert here. No `--sandbox`, and no `--permission-mode` outside
  the one value that is applied.
- **`git init` in an agent's own directory, for this brain, is worth 2,729 tokens a turn.**
- **Grok is the cheap brain.** At 5,842 tokens of baseline against Claude's 24,252, it is the one
  to reach for when a turn is small; ACP no longer trades away tool visibility.

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
- Do not read a resume as proven without a control turn. This CLI answers from its other
  sessions, so the obvious probe passes whether or not anything was resumed, and an adapter would
  claim a capability on recall.
- Do not leave cross-session memory open on an agent's turn. Two conversations in one private home
  can see each other, which is the thing a per-conversation handle exists to prevent.
- Do not copy or link a login into a private `GROK_HOME`. An empty one is logged out by design and
  that is the isolation working; the CLI's own error names the command, so say that instead.
- Do not put a secret on this command line. The prompt is already a flag value and therefore in
  the process list; nothing else should join it there.
- Do not make any of this a test dependency. The golden stream is committed so the suite never
  needs an account, a token or a network.

## Verdict for us

**Grok now uses the full provider seam its ACP stream can prove.** The adapter reports
`tools: true`, `resume: true`, `usage: true`, `model: true` and `steer: false`: calls and terminal
results come from structured ACP updates, while steering remains unmeasured.[13][14] The one-shot
format is still a useful proof that a lossy vendor stream must not be mistaken for the agent's
whole activity.

**We take the ACP invocation, update mapping, usage split, resume handle, private home, standing
instruction transport and tool scoping as settled.** Root `--rules` is not an ACP transport;
`_meta.rules` on `session/new` is. Root `--tools` and the root permission rules are not either;
`_meta.agentProfile` on both `session/new` and `session/load` is, and a read posture built on it
came back naming exactly `read_file, list_dir, grep`.[15][16]

**Two transport choices are non-negotiable on every turn, for opposite reasons.** `--no-memory`, because
without it a conversation reads conversations it was never given and a resume handle stops meaning
anything. And ACP stdin, because the prompt otherwise sits in the process list for the life of the
turn.

**The `dontAsk` bug is the lesson we carry over, not the flag.** A vendor CLI accepted an argument,
ignored it, and let the turn report success. Nothing in a test suite could see it because the
adapter did everything right on its own terms. The defence is that a posture is only ever claimed
on measured behaviour, and `AGENTS.md`'s "never let a command report success it did not earn"
extends to what an adapter says a brain is doing.

This feeds a `provider-` component that is not declared yet — adding one is the owner's call
(`AGENTS.md`, the component ontology) — and it is held to
[`../prd/provider-adapter.md`](../prd/provider-adapter.md), where `R-PRV-7` (an adapter that runs
no tools reports none), `R-PRV-8`, `R-PRV-9`, `R-PRV-15` and `R-PRV-18` are the rows this brain exercises
hardest. Re-drive the capture and update `tests/samples/cli-versions.lock` in the same change when
the version moves.

## Open questions

The original transport questions are answered: resume carries context, usage is a turn's own,
`GROK_HOME` isolates login, prompts need not enter the process list, ACP standing rules append
at conversation creation, and an ACP session is scoped by its agent profile.[12][15][16] What
remains:

- **Whether an agent profile can be confirmed rather than only sent.** `session/new` reports the
  session's model, working directory and available commands, and nothing about which agent
  resolved — so a profile this vendor stops being able to parse reopens the whole tool set with
  only a stderr line to say so.[16]
- **What else reaches across sessions, and whether `--no-memory` closes all of it.** The control
  turn named "recent sessions" specifically; whether that is the documented cross-session memory,
  a tool, or something else was not established, and only the observable symptom was tested.

Beyond those:

- Whether `reasoning_tokens` is inside `output_tokens` or beside it.
- Whether this brain can ask a headless question or be steered during an active ACP turn, and what
  either interaction looks like.
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
12. `.knowledge/scripts/probe-grok` against `grok 0.2.111` on macOS 25.5.0, 2026-07-26 — (internal)
13. SpaceXAI, “Headless & Scripting” — https://docs.x.ai/build/cli/headless-scripting
14. Controlled ACP tool and resume probes against `grok 0.2.112`, 2026-07-27 — (internal)
15. Installed official `docs/user-guide/15-agent-mode.md` plus controlled ACP rule, posture and attachment probes against `grok 0.2.112`, 2026-08-01 — (internal)
16. `.knowledge/scripts/probe-grok --acp-tools` against `grok 0.2.112`, 2026-08-02, plus the installed official `docs/user-guide/14-headless-mode.md`, `16-subagents.md` and `22-permissions-and-safety.md` — (internal)
