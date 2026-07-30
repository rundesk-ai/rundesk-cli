# Research: The Codex CLI as an agent's brain

**Last updated:** 2026-07-26
**Question it answers:** What does the installed Codex CLI actually do when it is driven headlessly, and which of it has to be absorbed by an adapter?

## What they do

| Need | What `codex-cli 0.145.0` does |
|---|---|
| Run one turn without a person | `codex exec --json` streams JSONL on stdout and takes the prompt as a positional or, with `-`, on stdin.[1] Measured: a whole turn is `thread.started`, `turn.started`, `item.completed`, `turn.completed`.[4] |
| Say which conversation this was | `thread.started` carries `thread_id`, on the first line and nowhere else. It is minted by the provider, so it does not exist until a turn has started.[4] |
| Carry a conversation on | `codex exec … resume <id>` — but **every global flag is rejected after `resume`**, measured: `--sandbox` placed after it is `error: unexpected argument '--sandbox' found`.[2][4] |
| Say what a turn cost | Through `codex exec`, `turn.completed.usage` is the **thread's running total rather than the turn's** — measured: three one-word replies reported `output_tokens` of 5, 10 and 15.[4] Through `app-server` there is no such trap: `thread/tokenUsage/updated` carries `last` beside `total`, so this turn's own share is reported as such.[4] |
| Keep one agent's sign-in from another's | `CODEX_HOME`. Measured: pointed at an empty directory, every request is `401 Unauthorized … Missing bearer or basic authentication`.[4] |
| Choose how much of the machine it may touch | `--sandbox` with `read-only`, `workspace-write` or `danger-full-access`; a process-level sandbox rather than a tool list.[1] |
| Say which model answered | Nothing in the stream names one.[4] |
| Be sent to mid-turn | **Not through `codex exec`**, which reads its prompt and runs to the end. Through `codex app-server` it is a first-class request: `turn/steer` takes the thread, the id of the turn it expects to still be running, and more input.[4] |

**Usage is cumulative, and this is the finding that matters most.** Three turns on one
thread, each asking for a single word:

```text
turn 1: {"input_tokens": 17401, "cached_input_tokens": 13056, "output_tokens":  5}
turn 2: {"input_tokens": 34821, "cached_input_tokens": 30208, "output_tokens": 10}
turn 3: {"input_tokens": 52260, "cached_input_tokens": 47360, "output_tokens": 15}
```

Three one-word replies cannot legitimately grow, so the field is the thread's running
total. Reported as a turn's cost it overstates every turn after the first, and a spend
limit reading it would fire on how long a conversation is rather than on what it cost.
This reproduces the same finding the previous build recorded against an earlier version,
down to the same three numbers, so it is behaviour rather than a bug that happened to be
present once.[3]

**The cache is folded inside the input count.** `input_tokens` contains
`cached_input_tokens`, so reporting it whole prices most of the volume at the fresh rate.
0.145.0 also reports `cache_write_input_tokens` separately, which is the tokens written
*into* the cache and billed above the standard rate. Codex's own conversion fixture proves
both are subdivisions of input: 100 input and 10 output total 110 while the input details
name 40 cached and 60 written.[5]

**A private home isolates the sign-in, and sharing it is one file.** Codex keeps its
credentials in `auth.json` inside the home it is given — a plain file, not a keychain — so
a fresh home is logged out. Measured: a home holding nothing gets `401 Unauthorized` on
every request; a home holding a *copy* of the owner's `auth.json` completes a turn; and a
home holding a *symlink* to it completes a turn and stays a symlink, so a refreshed token
goes on being shared rather than going stale.

That answers an open question on `agent-home`, and the answer is "either, and it is the
owner's call". Everything else — sessions, caches, skills, state and configuration — is
made fresh in the new home, so the isolation that was wanted is real whichever way the
sign-in goes.

**Rundesk does not make that call and does not touch the file.** An adapter that copied or
linked somebody's credentials would be sharing them between agents without anyone having
said so, and copying one in particular goes stale the moment the token refreshes. The
adapter recognises what Codex says when a home is logged out, and says what to run.

## What we can borrow

- Everything above belongs in the adapter and nowhere else. Rundesk's own modules must not
  learn any of it: the flags, the ordering, the stream shape, the arithmetic and the
  environment variable are all one file's business.
- The subtraction that turns a running total into a turn's share is the **adapter's**, and
  what it subtracts from belongs in the adapter's own private home. The previous build kept
  it in a gateway's memory and lost it on every restart, over-reporting the first turn of
  every existing thread afterwards.
- Give the prompt on stdin with `-` rather than as a positional. What somebody asks their
  agent is readable through the process list and kept in a shell's history otherwise.
- `--skip-git-repo-check` is needed: an agent's workspace is a directory, not necessarily a
  repository, and Codex otherwise refuses to start outside one.
- Claim no model. Nothing in the stream names one, and a model that was merely asked for is
  a request rather than a measurement.

## What to avoid

- Do not append global flags to a resume command line. Build the whole line in one place, in
  one order, and let nothing add to it afterwards.
- Do not treat everything on stdout as a record. `Reading additional input from stdin…` and
  other prose arrive there too; what does not parse is not ours.
- Do not report a negative cost. A thread reporting less than last time has been restarted
  underneath us rather than gone backwards.
- Do not publish a tool's output. `command_execution` carries `aggregated_output`, which can
  hold file contents, credentials and private paths — what a channel shows is not the
  adapter's decision to make.
- Do not make any of this a test dependency. It needs an account and a network, and a suite
  that reached for either would fail on somebody else's uptime rather than on this code.
- Do not copy, link or read a credential on an owner's behalf, and never carry one in what
  an owner set — that is written into the run's record, so a token put there outlives the
  turn in a file.
- Do not assume `codex` is on the path. A gateway is started by the machine's supervisor
  with a bare environment, so a name that resolves in a shell may resolve to nothing there.
  Check for it and say what to do, rather than keeping a list of the places it might be
  installed — such a list is wrong on the first machine that did something else.

**Steering exists, and it is on the other surface.** `codex exec` cannot be sent to once
it has started; that is what makes the shipped adapter say it cannot be steered. But
`codex app-server` — a bidirectional stdio protocol on the same binary — has it, and the
protocol can be read offline without an account:

```sh
codex app-server generate-json-schema --out <dir>
```

Three shapes the schema does *not* give you, each of which cost an attempt:

```text
sandbox on thread/start   {"read-only": {}}     externally tagged, kebab-case
                          — NOT {"mode": …}, NOT {"type": …}, NOT a bare string
SandboxPolicy elsewhere   {"type": "readOnly"}  internally tagged, camelCase
                          — the same idea, spelled two ways in one protocol
usage                     arrives as a notification, not on the completed turn:
                          thread/tokenUsage/updated {tokenUsage: {last, total}}
```

The posture is set once, when the conversation is opened; a turn inside it does not
restate it.

Measured end to end: a turn counting to thirty took a change of plan eight seconds in and
finished on the new instruction, in the same run, without being interrupted and started
again. What that schema says, at 0.145.0:[4]

```text
turn/steer         {threadId, expectedTurnId, input: [UserInput], clientUserMessageId?}
                   -> {turnId}
                   expectedTurnId is a precondition: the request fails when the turn it
                   names is no longer the running one, so a word cannot land in a turn
                   the sender did not mean.
turn/interrupt     the other thing — stopping, rather than adding to, a running turn.
thread/injectItems raw items appended to what the model can see.
```

Only two kinds of turn refuse to be steered — `review` and `compact`. An ordinary one
takes it. So a Codex adapter built on `app-server` rather than `exec` would report
`steer` and carry a word said mid-turn; the shipped one is built on `exec`, reports that
it cannot, and is honest about it. That is the seam working as intended — what a brain can
do is asked rather than assumed, and a brain gaining a capability is one adapter's change.

## Verdict for us

**Use `app-server`, not `exec`.** The shipped adapter does. `exec` is the simpler surface
and it costs three real things: a turn cannot be added to once it starts, the only usage
figure is a running total every adapter then has to remember and subtract across restarts,
and its session handle appears on one line and is lost if anything goes wrong before it.
`app-server` has none of those problems — steering is a first-class request, `last` is the
turn's own cost, and the thread id comes back from opening the conversation.

What it costs instead: it is a protocol with a lifecycle rather than one command, and it is
marked experimental at 0.145.0. That is a real risk and the reason the probe exists — when
the version moves, rerun it before trusting any of this.

Codex was worth taking first for a reason that survives the change of surface: it is the
**hardest** of the three installed CLIs on the things the seam most needs to get right, and
an adapter absorbing them proves the seam can. It also proved the seam's central claim by
accident — moving this brain from one surface to a completely different one, and gaining a
capability doing it, changed exactly one file and nothing else.

Rerun `.knowledge/scripts/probe-codex` when the version moves, and write what changed here.

## Open questions

- Whether an owner sharing one sign-in across agents wants that arranged for them, and by
  what — nothing does it today, deliberately.
- What an adapter on `app-server` costs to keep: it is a protocol with a lifecycle rather
  than one command, and the surface is still marked experimental on this version.
- Whether a thread whose total went backwards has really been restarted, or whether the
  count can legitimately fall for a reason not yet seen.
- Which of its item kinds carry an id that is stable between `item.started` and
  `item.completed`, since a tool and its result are correlated by one.

## Sources

1. OpenAI, Codex non-interactive mode — https://developers.openai.com/codex/noninteractive/
2. OpenAI, Codex App Server — https://developers.openai.com/codex/app-server/
3. The build this replaces, `probes/codex-usage.ts` — (internal)
4. `.knowledge/scripts/probe-codex` against `codex-cli 0.145.0` on macOS, 2026-07-26 — (internal)
5. Codex cache-write conversion fixture — https://github.com/openai/codex/blob/3d805abdf09093bfa806f359a5adc6514766c420/codex-rs/codex-api/src/sse/responses.rs#L810-L833
