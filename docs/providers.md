# The provider layer, and writing a provider adapter

**This is what ships.** Every claim on this page was read out of the code as it stands: where it
states a field, a bound or an exit code, it is because `src/rundesk/providers/`, the working adapters
in `src/providers/`, and the suites in `tests/` say so.

**Three brains ship**, and each was driven against the version named in
[`cli-versions.lock`](../cli-versions.lock) rather than against notes about an older one:

| Adapter | Reaches it by | Can be steered |
|---|---|---|
| `codex` | `codex app-server`, JSON-RPC over a pipe | yes |
| `claude` | `claude -p`, streaming JSON both ways | yes |
| `grok` | `grok agent stdio`, the Agent Client Protocol | yes |

**Every turn runs with the whole machine available to it**, on all three. `RUNDESK_ACCESS_MODE` is
still carried and is still what this page says it is below — a request rather than containment, which
an adapter may map onto its brain or ignore — and all three ignore it. That is the owner's decision,
written here so that what is documented and what happens are the same thing.

A **provider** is a brain — a vendor's own command-line tool, driven headlessly. A **provider
adapter** is the program rundesk runs to reach one. Nothing under `src/rundesk/` names a vendor, and
`tests/test_providers_protocol.py` refuses the file if one appears there.

[`adapters.md`](adapters.md) is the other seam, for channels. [`gateways.md`](gateways.md) is what
hosts both, [`commands.md`](commands.md) is what a person types, and [`layout.md`](layout.md) is
where an install keeps things.

---

## Part one — what a turn is

### One turn, start to finish

```
somebody asks            the clock comes due          a message arrives on a channel
      │                          │                             │
   rundesk ask         rundesk providers run          the gateway's own loop
      └──────────────────────────┴─────────────────────────────┘
                                 │
                       providers.turns.run()
                                 │
   ┌─────────────────────────────┼──────────────────────────────┐
   │ 1  claim the conversation   │  a lock, taken once, never waited on
   │ 2  find the adapter         │  a name → a program
   │ 3  ask what it can do       │  --capabilities, offline
   │ 4  compose the instructions │  a pure function; a fingerprint is kept, not the words
   │ 5  write the turn down      │  one row, `working`
   │ 6  run the adapter          │  records in, records out, for as long as it takes
   │ 7  settle the turn          │  `done`, `stopped` or `failed` — exactly once
   └─────────────────────────────┴──────────────────────────────┘
```

**Every turn ends settled.** Step 7 is a context manager entered before anything can fail, so a turn
killed halfway is `stopped` and never left saying it is being worked on.

**Whether a turn is running now is the kernel's answer and never a row.** The conversation's lock
descriptor is passed to the adapter's child process, so the claim is held for exactly as long as the
adapter tree lives — through a `SIGKILL`, through a gateway that died without unwinding. There is no
pid written down anywhere, because a written-down pid gets reused and a reused pid gets signalled.

### The five callers, and why they are not one

| Caller | Runs the turn | Can steer | Conversation |
|---|---|---|---|
| `rundesk ask` | in the terminal's own process | yes — it reads later typed words | one per agent |
| a channel | on a thread of its own | yes — later messages prefer its active turn | one per place |
| a schedule (the gateway) | in a process of its own, `rundesk providers run` | no | one per schedule |
| a delegation (the gateway) | on a thread of its own | yes — durable `asked say` guidance is polled into its active turn | one per delegation |
| `rundesk providers run` | there | no | the schedule's |

A channel turn runs on a thread because the thread that reads a channel adapter **cannot fall
behind**: a turn takes minutes, and running one inline would stop that channel reading anything for
the length of it — including the next message and including a stop.

A scheduled turn is a *process* because that is how its claim survives the gateway that started it.

### What is written down

Four tables, in the agent's own `state.db`. Every column exists because a question is asked of it.

**`turns`** — one row per turn: which brain and which model *answered*, what the adapter said it
could do at the time, whether the session was resumed, what it came to, what it cost, and where its
slice of the raw stream sits.

- The four billed quantities are kept apart because they are billed at **three different rates**. A
  single total would be a number that is real and misleading.
- All five token columns are nullable, and **null means the brain did not report that quantity**. A
  cost nobody measured and a cost of nothing are different answers.
- `unknown_records` and `lost_records` are the drift counters. Both zero on a healthy turn; both
  climbing means an adapter and its brain have drifted apart, and nothing else in the product will
  tell you before somebody notices an agent behaving oddly.
- `instructions_sha256` and `instructions_bytes` are kept **instead of** the prompt. See
  [re-composing a past turn](#re-composing-what-a-turn-was-sent).

**`turn_records`** — one row per thing that happened, in the order it happened. Swept at
`turn_records_days` (default 14) because it is diagnostic and it is the only table that grows with
tool calls. The sweep runs once a day inside a gateway, on the same pass that sweeps the day files
and what arrived through a channel, and it says in the log how many rows went. What an agent *said*
is not in here — see below.

**`provider_sessions`** — where a conversation got to on a brain, keyed by `(conversation,
provider)`. Opaque to rundesk and never parsed.

A saved handle is resumed only when this provider's latest turn has the same instruction
fingerprint as the prompt being composed now. A changed access mode, operating rule, owner addition,
or eligible-team snapshot starts a fresh provider session and discards the stale handle. This is
required for brains that bind instructions when the session is created and silently ignore a
replacement on resume.

**`conversation_messages`** — what was said, kept for ever, with a full-text index over it.

#### One source of truth per fact

| Fact | Lives in | Nowhere else |
|---|---|---|
| what was said | `conversation_messages` + its index | not in `turn_records`, not in a log |
| what a turn did | `turn_records` | not in the messages, not in a log |
| what a turn cost and became | `turns` columns | not in a record, not in a log |
| where a conversation got to on a brain | `provider_sessions` | not in `turns`, not in a file |
| **whether a turn is running now** | the kernel, via the conversation's lock | never a row, never a pid |
| what the brain printed verbatim | `conversations/<id>/raw.jsonl` + two offsets | not in the database |
| what rundesk said to the brain | a fingerprint, re-composed on demand | not a file, not a message |

**`text` records are never rows.** They are gathered and written as **one message**, because a row
per fragment is a history nobody can read back and a search that matches half a sentence.

### On disk

```
data/agents/alan/
  home/                        every turn stands here — the brain finds AGENTS.md by being in it
  state.db                     turns, turn_records, provider_sessions, messages, the search index
  providers/<provider>/        the adapter's own; rundesk never writes here
  conversations/<id>/
    lock                       the claim, held by the kernel
    raw.jsonl                  what the brain said, appended across turns, rotated at 256 KB × 3
    stderr.log                 the adapter's own errors, same
```

**Three files per conversation, and conversations are bounded** — a terminal, a few channels, a
handful of schedules. It does not grow with turns, with time, or with how busy the agent is. A
per-turn layout would leave an agent taking fifty turns a day some seventy thousand files a year.

### Re-composing what a turn was sent

Nothing stores the prompt. The composer is a pure function of its inputs and every one of those is on
the turn, so `rundesk providers instructions <agent> --turn <n>` re-derives the words and compares
the fingerprint. It prints them when they still match, and says

> this release composes a different prompt for these inputs (b71c… against the recorded a3f9…)

when they do not. That is a **better** audit than a stored blob — it detects the change rather than
merely surviving it — and it costs forty bytes instead of five kilobytes a turn.

### Reading it back

```console
$ rundesk turns ava              # the ledger: what each turn cost and became
$ rundesk turns ava 7            # one turn whole, every record in order
$ rundesk messages ava --search "the release" --channel discord
$ rundesk providers instructions ava --turn 7
```

`rundesk messages` is what was *said*; `rundesk turns` is what it *cost*. Two questions, kept apart
because they are read for different reasons.

---

## Part two — the contract

### An adapter is a program, never a plugin

**Rundesk does not load somebody else's code into the gateway hosting every other agent.** One
provider that raised on import would take an agent's whole gateway with it. The seam is a pipe
carrying newline-delimited JSON, so an adapter may be written in anything — and a vendor library
lives on the far side of it and never enters the gateway, which is how a product whose own code
imports nothing outside the standard library reaches one that needs a websocket.

#### Where one stands

| Where | Whose it is |
|---|---|
| `paths.code()/providers/<name>` — an install's `app/src/providers/` | part of the release, replaced whole by an update |
| `data/providers/<name>` | this install's own; never touched by an update |
| any path with a separator in it | yours, right now, wherever you are writing it |

A bare name resolves among the shipped ones first and then among the given ones, so an install
cannot quietly shadow a release's own. **Providers and channels do not share a namespace** — a
channel called `discord` and a provider called `discord` are different programs.

### The two invocations

#### `--capabilities`

Print one JSON object and exit `0`. **No account, no network, the same answer every time.** Your
stdin is closed and nothing about a particular run is set.

```json
{"tools": true, "resume": true, "model": true, "usage": true, "steer": true}
```

| | |
|---|---|
| `tools` | you report what tools ran |
| `resume` | you can carry an earlier conversation on |
| `model` | you can name the model that actually answered |
| `usage` | you report what a turn cost |
| `steer` | you can be sent more words while a turn is still running |

**Absent means no**, so `{}` is a complete and honest answer and a plain conversational CLI is first
class rather than degraded. Anything else you put in the object is kept beside the turn and shown
under *"it also said, and rundesk did not ask"* — a version is the most useful thing to put there,
because it is what explains a turn six months later.

**Only `steer` changes how your turn is run.** Declare it and your input is held open for the length
of the turn and you are given records; leave it out and you are given the prompt and told there is no
more. Everything else is a claim about what to expect, recorded with the turn so that *reported no
tools* and *has no tools* stay distinguishable afterwards.

Answering must be quick: rundesk gives it **60 seconds** and this is the one place it runs an
unvetted program before a turn has been admitted.

#### One turn

Run with no arguments. The prompt arrives on your stdin, records come back on your stdout, and
whatever you write to stderr is appended to the conversation's `stderr.log`.

**If you declared `steer`**, everything on your stdin is a record:

```json
{"type": "say", "text": "what changed today?"}
{"type": "say", "text": "stop at five", "context": "This is mid-turn guidance within the original request. …"}
```

The first is the prompt; anything after it arrived while you were working. `context` is rundesk's own
words, carried **apart from** the person's text so you can apply it without altering what they
actually said — and so your brain is told this is genuine mid-turn guidance. A bare line appended to
a running turn is refused by real brains as suspected prompt injection.

Your input stays open for the whole turn, so **nothing means "the prompt ended" any more**. A brain
that reads to the end of its input would wait for an end that is not coming.

**If you did not**, your stdin is the prompt as plain text and it is closed after it.

### What you say back

One JSON object per line, flushed. Eight kinds and no ninth.

```json
{"type": "text",   "text": "Nothing urgent — three merged pull requests.", "whole": true}
{"type": "think",  "text": "**Checking the queue first**", "whole": true}
{"type": "tool",   "id": "1", "name": "sed -n '1,40p' note.txt", "did": "read"}
{"type": "result", "id": "1", "ok": true, "summary": "exit 0: the answer is 41"}
{"type": "usage",  "input_tokens": 30709, "output_tokens": 123, "cache_read_tokens": 22016,
                   "cache_write_tokens": 0, "context_tokens": 15428, "model_name": "gpt-5.6-sol"}
{"type": "limit",  "percent_left": 73, "resets_at": "2026-08-08T03:33:24Z"}
{"type": "file",   "at": "/…/home/chart.png", "name": "chart.png"}
{"type": "done",   "ok": true, "session_id": "019fd763-7c7a-7521-bcc9-1b560b60709d"}
```

**A field is named for what it holds, and the wire name is the column name.** `failure_code`,
`session_id`, `input_tokens`, `context_tokens` — the words you write are the words `turns` stores, so
nothing translates between them.

| Kind | What it is |
|---|---|
| `text` | what the agent said. `whole: true` means *this is finished*, which is what lets a surface show it while the turn runs; absent means a fragment, and fragments are only shown at the end |
| `think` | the same, for reasoning. One record per finished thought, never one per fragment |
| `tool` | a tool starting. `id` is yours and pairs it with its result; `name` is for a person to read; `did` is one of ten words below |
| `result` | what that tool came to |
| `usage` | what the turn cost. **Only what you actually measured** — a brain that cannot tell fresh tokens from cached ones leaves the cached field out, because summing that into zero says it read nothing from the cache |
| `limit` | account state. **News about the account, never about the work**: a turn carrying one may have succeeded |
| `file` | something the brain *made*, for a person. Not every file it touched — this is what gets attached to a message on a channel |
| `done` | the turn ended. **Exactly one, and always one** |

`context_tokens` is a **level, not a quantity**: how big the conversation is now. It goes *down* when
one is compacted, so rundesk takes the last and never the sum.

#### What a tool did

`read` · `search` · `run` · `edit` · `list` · `make` · `delegate` · `memory` · `rules` · `identity`

Closed and short on purpose: the same act is `Bash` on one brain, `shell` on the next and
`run_terminal_command` on a third, and a surface that recognised any of them would carry that
vendor's vocabulary for ever.

**A brain that did something outside this list leaves the word out** rather than stretching one to
fit. A reader shown nothing is better off than one taught to believe a word that means something else
here. The last three are the same act as `edit` and are told apart deliberately: what an agent keeps
of its own is what it *is* between turns, and a file it lives by being changed is not the same news
as a working file being changed. **A file's name is not the test** — every checkout on the machine
has an `AGENTS.md`, and an agent editing one in a repository has not rewritten its own rules. What
qualifies is a path standing directly in `RUNDESK_CWD`.

#### Why a turn stopped

On the `done` record, when `ok` is false:

```json
{"type": "done", "ok": false, "failure_code": "usage_exhausted",
 "failure_message": "your weekly limit is spent; it resets on Friday"}
```

| Word | Waiting helps? |
|---|---|
| `signed_out` — no usable credential | no, a person runs the login command |
| `no_access` — signed in and not entitled to this model | no |
| `no_credit` — the account cannot pay | no |
| `usage_exhausted` — the plan's allowance is spent | no, not until its window resets |
| `context_exceeded` — the conversation is too big to continue | no |
| `refused` — the brain declined the work | no, it is a decision |
| `rate_limited` — too fast, right now | **yes** |
| `upstream_error` — the vendor's own fault | **yes** |
| `offline` — this machine could not reach the vendor | **yes** |
| `crashed` — the adapter or its brain fell over | **yes** |

Three more — `cancelled`, `timed_out`, `crashed` — rundesk writes on its own account, because they
are about what *rundesk* did or saw. **You classify your own failure and rundesk never infers one
from your prose**: a word guessed from a message is a word that is wrong on the first vendor that
rewords one. A word rundesk does not know is dropped rather than stored, and the message is kept
either way.

`failure_message` is the prose a person reads. Say the actionable thing in it.

### The environment

Built from nothing rather than inherited, so nothing of the gateway's own leaks into a brain. **What
is left out is unset, never empty** — `${RUNDESK_MODEL:-default}` is written expecting that.

| | |
|---|---|
| `RUNDESK_CWD` | where the turn stands: the agent's own home. The brain finds the files it lives by **because it is in the directory** |
| `RUNDESK_PROVIDER_HOME` | yours, for what you must remember between turns. Named, never made |
| `RUNDESK_AGENT`, `RUNDESK_RUN` | which agent, and which turn |
| `RUNDESK_ACCESS_MODE` | `read` or `work`. **A request, not containment** — rundesk enforces nothing and has no way to |
| `RUNDESK_HOME` | which install this turn belongs to. Every `rundesk` command the agent runs reads it |
| `RUNDESK_COMMAND` | the whole path to *this* install's `rundesk`. What works when `PATH` does not |
| `RUNDESK_SKILLS` | where this agent's skills stand. Presenting them is yours |
| `RUNDESK_CONTINUITY` | `AGENTS.md=rules,MEMORY.md=memory,SOUL.md=identity` — which files the agent lives by, and what changing one is called |
| `RUNDESK_RAW` | somewhere to append everything the brain said, verbatim. Offered, never required |
| `RUNDESK_MODEL` | a model name your brain understands, or unset |
| `RUNDESK_RESUME` | the handle this conversation got to last time, or unset for a new one |
| `RUNDESK_SETTINGS` | whatever the owner set, as one JSON object, sorted |
| `RUNDESK_PREFACE` | what rundesk wants said before the brain reads a word of the task |

**`RUNDESK_PREFACE` is appended to your brain's instructions and never mapped onto the flag that
replaces its system prompt.** Measured on one brain, the replacing flag takes about 6,100 tokens of
that brain's own instructions with it, nothing reports it, the tools keep working, and the turn
merely behaves differently — which is the failure mode that gets blamed on the model.

Find out *when* your brain reads it, and do not guess. Codex binds it when a thread is created and
**ignores it on a resume** — probed three ways — so the shipped adapter sends it at `thread/start`
and deliberately strips it from a resume. **An argument accepted and then dropped is worse than one
never sent**, because it reads like it works.

**`RUNDESK_RAW` is worth using.** Rundesk sees what *you* reported and never what your brain said, so
a vendor changing its output shape otherwise shows up as records quietly going missing with nothing
at all to compare against.

**An agent runs `rundesk` from inside its own turn**, and two things make that reach *this* install
rather than another one — or none.

`PATH` carries this install's own command directory in front, which is enough for a brain that hands
its shell the environment it was given. `RUNDESK_COMMAND` carries the whole path, which is what works
when a brain does not: one measured brain rebuilds its shell's `PATH` from the owner's login profile
before the agent types anything, so the directory in front is gone and a bare `rundesk` exits 127 on
a perfectly healthy install — while the variables it was handed arrive intact. Both are set, and the
shipped `managing-rundesk` skill tells an agent to prefer `"$RUNDESK_COMMAND"`.

`RUNDESK_HOME` is what makes the command answer about the right install once it has been found.
Without it, `rundesk` resolves the default `~/.rundesk`: measured, a turn ran `rundesk messages` and
was told the agent that was speaking is not an agent on this install. It is **derived from the
resolved root, never inherited** — this process may have the variable unset and still resolve one —
the same way `schedules.firing` builds a schedule's environment and `gateways.job` writes a plist.

One consequence worth stating: a value the owner keeps under either of those two names no longer
reaches a brain, because a name rundesk decides is a name an owner's value may not take. What it did
before was point an agent's own `rundesk` at a different install, which is the defect this closes.

**A provider is handed every value this install keeps**, merged in after the above and **never over
a name rundesk decided**. Not scoped per agent, and that is a decision rather than an oversight: a
channel adapter names the secrets it may have because it is a program reaching one platform on the
owner's behalf, while a brain running under `work` access already reads the owner's files and runs
their shell. An allowlist in front of it would be a boundary that is not one — the brain could read
the same values off disk a moment later — so rundesk says plainly what it does instead of implying a
containment it cannot keep.

What follows from that is worth being clear about: **an agent's brain can see every credential this
install holds**, including ones belonging to channels and to other providers. Run a brain you are
willing to trust with them, and keep out of `rundesk env` anything you are not.

### The bounds

| | | |
|---|---|---|
| a line | 1 MB | longer is read to its end, discarded whole, and reported as a gap in the place it happened |
| held records | 4096 | a receiver that falls behind loses records and the loss is counted, rather than the adapter blocking |
| silence | 1800 s | measured across **both** streams. Not a duration — a brain may work for hours, and this is how long it may say nothing |
| a turn | 48 h | the ceiling, whatever it is saying |
| `--capabilities` | 60 s | |
| draining after a stop | 2 s | |
| an event stored | 4 KB | a `result` can carry a whole file, a credential or a private path |
| `raw.jsonl`, `stderr.log` | 256 KB × 3 | rotated |

**Half a record is not a smaller record, it is a corrupt one.** An over-long line is never handed on
in pieces, because nothing downstream could tell that apart from your brain talking nonsense.

### The rules that will bite

**Say `done` whatever happens.** Rundesk reading no `done` at all is a turn nobody can explain — the
one exception is a process killed outright, which is rundesk's to classify and the only case it can
classify correctly.

**Your exit code says what became of the *program*, and never what became of the turn.** Rundesk
decides that from your `done` record, records your code beside it, and the two are kept apart on
purpose: a brain that failed cleanly and an adapter that fell over are different news. So exit
non-zero when *you* went wrong, not because the brain reported a failure you relayed correctly.

**Exiting zero having said nothing is not a turn that worked.** It is the failure that looks most
like a success, and rundesk refuses it.

**End your brain yourself.** A brain left running is a brain nobody will reap.

**Flush every record.** A record held in a buffer is a record nobody saw, and a surface watching a
turn go past shows nothing at all.

**Do not put a prompt or a secret on a command line.** Every process on the machine can read one.

### Terms of service — a design invariant

rundesk runs the vendor's own published CLI, as the owner, signed in the way the vendor intends,
through the headless interface the vendor documents. An adapter that ships here follows the same
rules:

- **Never impersonate a first-party client.** Say who you are. The shipped codex adapter sends
  `clientInfo: rundesk` and `threadSource: rundesk`, so the owner's own thread list shows where a
  thread came from.
- **Never move a subscription credential onto an API path it was not issued for.**
- **Never copy, link or read an owner's credential.** Say the brain is not signed in
  (`signed_out`) and say what to run.
- **Drive only documented headless surfaces**, and never defeat a rate limit.
- **Never let a test reach a vendor.** Capture a real stream, commit it, and replay it — see
  `tests/samples/codex-app-server-0.146.0.jsonl`, `tests/samples/claude-2.1.223.jsonl`,
  `tests/samples/grok-acp-0.2.118.jsonl` and `cli-versions.lock`.

---

## Part three — writing one

### The smallest adapter that is not a lie

```sh
#!/bin/sh
# echo — answers with what it was asked, and is honest that it can do nothing else.
if [ "$1" = "--capabilities" ]; then
  printf '%s\n' '{}'
  exit 0
fi
asked=$(cat)
printf '%s\n' "{\"type\": \"text\", \"text\": $(printf '%s' "$asked" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'), \"whole\": true}"
printf '%s\n' '{"type": "done", "ok": true}'
```

It declares nothing, so its stdin is the prompt and is closed after it. It is a whole adapter: rundesk
records the turn, keeps the answer as a message, and reports that this brain measured no cost rather
than that it cost nothing.

### The order to build one in

1. **`--capabilities` first, answering `{}`.** `rundesk providers check <name>` must print five
   *no*s before anything else is worth trying.
2. **A turn that answers with one `text` and one `done`.** `rundesk ask <agent> "hello"`.
3. **`usage`.** Find out whether your brain reports a turn or a running total — and if it is a
   total, work out the turn's share without keeping state that can go stale. The shipped codex
   adapter recovers its baseline from the turn's own first report.
4. **`tool` and `result`.** Map your brain's tool names onto the ten words, and leave the word out
   where nothing fits.
5. **`resume`.** Keep the handle on `done`; read `RUNDESK_RESUME` on the way in. Then prove it: turn
   two must answer something only turn one could know, **in a fresh process**, and a `--fresh`
   control must fail — or the resume proved nothing.
6. **`steer`.** Last, because declaring it changes how the turn is run.

### Proving it without a vendor

Capture what your brain really said during one turn, scrub out anything naming a machine or an owner,
commit it, and replay it through your adapter. `tests/test_providers_codex.py` is the worked example.

**Three stand-ins ship, and which one fits is decided by how your brain is spoken to** rather than by
which vendor it is. Reuse one where it fits and write a fourth where none does — a shared fixture
that has to branch on vendor is worse than two that do not.

| Stand-in | For a brain that | Releases a capture |
|---|---|---|
| `a-captured-brain` | answers requests, and whose notifications follow the request that caused them | on each reply, everything since the last one |
| `an-acp-brain` | answers requests, and whose notifications are caused by a *later* request than the reply they sit behind | only once the request that causes them arrives |
| `a-streaming-brain` | is told things and answers, with no request ids at all | one turn per thing it is told |

The difference between the first two is not cosmetic. Releasing a run of notifications before the
request that caused it is an ordering no real server produces, and a fixture that produces one
teaches an adapter to survive something that never happens — or hides something that does. It hid
exactly one: an adapter deciding what belonged to its turn on a different thread from the one reading
had a race, and only the early release made it visible.

**A brain that can be steered does not end on its own.** Its input is held open for the whole turn,
which is what steering *is*, so it waits for another word after it has answered while your reader
waits for a stream that will not close. Close its input when the turn ends, or the turn hangs until
rundesk's silence window ends it half an hour later with nothing written down.

**A capture of a turn that started from nothing cannot prove usage arithmetic** — a turn that begins
at zero reports the same numbers whether a baseline is subtracted or ignored. Capture a second turn
on the same conversation, or the case that would over-report every resumed conversation goes green.

Record which version you captured in `cli-versions.lock`. The day the vendor changes its stream, the
suite goes red with the reading that broke and that file says what to compare against.

### How to check yours

```console
$ rundesk providers                      # is it found at all?
$ rundesk providers check <name>         # what does it say it can do?
$ rundesk agents add ava --provider <name>
$ rundesk ask ava "say the single word: pong"
$ rundesk turns ava 1                    # every record, in order, with what it cost
```

Read `rundesk turns` rather than the screen. `UNKNOWN` above zero means you sent something this
release does not understand; `LOST` above zero means records did not arrive.
