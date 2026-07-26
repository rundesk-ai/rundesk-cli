---
name: write-a-provider-adapter
description: How to put your own brain, or your own conversational loop, behind a Rundesk agent — the whole contract, and a working adapter in twenty lines.
---

# Write a provider adapter

Rundesk does not run a conversation. It runs **your program**, gives it somewhere to work,
reads what you report, and ends it when the turn is over. That program is an adapter, and
this is everything it has to do.

It is a program and not a plugin on purpose: Rundesk never loads your code into the gateway
that runs every other agent, and you are not obliged to write Python. An adapter can be a
shell script.

Your adapter answers **two questions**. What you can do, and one turn.

## Question one: what can you do?

Run with `--capabilities`, print one JSON object, exit `0`:

```json
{"tools": true, "resume": true, "usage": true, "model": false}
```

| | |
|---|---|
| `tools` | you report what tools ran |
| `resume` | you can carry an earlier conversation on |
| `usage` | you report what a turn cost |
| `model` | you can name the model that actually answered |
| `steer` | you can be sent more words while a turn is still running |

Every field is `false` when you leave it out, so `{}` is a valid answer and a complete
adapter. **Rundesk asks rather than assuming**, and it never guesses from your name — so say
`false` and the work is simply absent, rather than expected and missing.

`--capabilities` is the only argument you are given, your stdin is closed, and nothing about
a particular run is set. If you do not recognise the flag and do something else entirely,
you can do nothing — which is a complete answer and never an error.

**A declaration stops rundesk asking; it does not stop you reporting.** Say `tools: false`
and emit a tool record anyway and the record is kept exactly as any other. Only `steer`
changes how your turn is *run* — everything else is a claim about what to expect, recorded
with the run so a turn that reported nothing and a brain that has nothing can be told
apart later.

This must not need an account, a network or a login, and it must be the same answer every
time. It is asked when a turn is admitted, and the answer is written into that run's
record — so a turn that reported no tools and a brain that has none can be told apart
afterwards. `rundesk doctor` does not ask it: diagnosing an agent starts nothing at all,
and it only checks that your program is there and can be run.

## Question two: carry one turn

**We run your program.** Its path is whatever the agent was given as its provider:

```sh
rundesk add ava --provider codex           # one that ships
rundesk add ava --provider /opt/my-brain   # yours
```

**You are told where to work, through the environment:**

| | |
|---|---|
| `RUNDESK_CWD` | the agent's own home — stand here, so what stands beside you is what your brain loads |
| `RUNDESK_PROVIDER_HOME` | yours alone, and it lasts: config, credentials, session files, anything you must remember between turns |
| `RUNDESK_MODEL` | the model asked for, or unset — a name you understand, not one we enumerate |
| `RUNDESK_RUN` | the id of this run, for correlating anything you keep |
| `RUNDESK_RESUME` | the handle you reported last time on this conversation, or unset for a new one |
| `RUNDESK_POSTURE` | `read` or `work` — how much of the machine this turn may touch |
| `RUNDESK_SETTINGS` | a JSON object of whatever the owner set, passed through unread |
| `RUNDESK_RAW` | somewhere to append everything your *brain* said, if you want to keep it |
| `RUNDESK_PREFACE` | standing instructions for this turn's situation, or unset — see below |

The first four are always set. `RUNDESK_MODEL`, `RUNDESK_RESUME` and `RUNDESK_SETTINGS` are
**absent** rather than empty when there is nothing to say, so `${RUNDESK_MODEL:-default}`
does what you would hope. `RUNDESK_PROVIDER_HOME` is made for you before you start, and is
yours to write in.

**`RUNDESK_PREFACE` is appended, never substituted — and this one will bite.** It is what
the owner has this agent told about the situation it is answering in, before it reads a
word of what anybody typed. Rundesk says what it means and stops there, because only you
know what your brain offers:

- **If your brain has a way to *add* to its instructions, use that.** `claude` has
  `--append-system-prompt`. `grok` has `--rules`, described in its own help as "extra rules
  to append to the system prompt". Codex has `developerInstructions`. That is the right
  home for this, and it costs nothing: standing instructions never take up a message, so
  they never accumulate in a conversation.
- **Never map it to anything that replaces the system prompt.** `claude --system-prompt`,
  `grok --system-prompt-override` and codex's `baseInstructions` all *substitute* for what
  the brain was built with — the instructions that tell it how to use its own tools. Send
  an owner's paragraph there and you have not added a paragraph, you have deleted the brain
  and left the paragraph. Rundesk cannot stop you doing this and will not know you did; the
  turn will simply behave strangely, and it will look like the model's fault.
- **Find out *when* your brain will read it, and do not guess.** Some take it every time
  they are run; some bind it when a conversation is created and silently ignore it after.
  Codex is the second kind — probed, because its schema says nothing about it: the same
  instruction was obeyed at `thread/start` and absent after `thread/resume`. So the shipped
  adapter sets it only where a conversation is opened, and deliberately strips it from a
  resume. **An argument that is accepted and then dropped is worse than one never sent**,
  because it reads like it works, and an owner rewording something would watch nothing
  happen with nothing to tell them why.
- **If your brain has no way to add to its instructions at all**, put it at the top of the
  turn as its own block, marked as rundesk's rather than the person's — and know what that
  costs: a block sent every turn accumulates in the conversation for the life of it. Worse
  than a real channel, and fine: correctness never degrades, only fidelity.
- **Ignoring it entirely is a whole adapter.** A brain with no notion of standing
  instructions is not a broken one.

It arrives already composed and already bounded, and it does not come through again with a
steer — a brain does not read its standing instructions twice in one turn.

**`RUNDESK_RAW` is worth using.** Rundesk sees what *you* report and never what your brain
said before you made records of it — so if your brain changes its output shape, that shows
up as records quietly going missing with nothing to compare against. Append your brain's own
stream to that file, verbatim, and the evidence is there.

Append only, and in whatever shape your brain speaks — **nothing reads it**, so there is no
format to match and nothing you can get wrong. Make it if it is not there. It is thrown away
with the rest of a run's raw when a retention policy takes them, and the account survives
without it. Ignore it and nothing breaks.

**The prompt arrives on stdin**, and how depends on the one capability that changes how a
turn is *run*:

- **You said `steer: false`** (or said nothing). The prompt is plain text and stdin closes
  straight after it. Read to the end and you have the whole of what was asked, with the
  newline that terminated it still on the end.
- **You said `steer: true`.** Stdin stays open for as long as the turn does, so nothing can
  mean "the prompt ended" any more. Everything arrives as one JSON record per line —
  `{"type":"say","text":"…"}` — the prompt first, and anything said later the same way.
  Read a line at a time and keep going until stdin closes.

Only ask for `steer: true` if your brain can really take a word mid-turn. Holding input
open for one that will never read again is a turn that never ends.

**You report on stdout, one JSON object per line**, flushed as it happens:

```json
{"type": "text",   "text": "Looking at the logs now.", "whole": true}
{"type": "think",  "text": "The error is in the parser."}
{"type": "tool",   "id": "1", "name": "Bash", "did": "run"}
{"type": "result", "id": "1", "ok": true, "summary": "3 files changed"}
{"type": "usage",  "input": 1200, "output": 340, "cached": 8000, "model": "…"}
{"type": "file",   "at": "/…/workspace/chart.png", "name": "chart.png"}
{"type": "done",   "ok": true, "session": "019f954d-ad60-7f91"}
```

**stderr is yours.** Say what went wrong there; it is kept, and it is never mistaken for what
you reported.

That is the contract. Seven kinds of record, and only `done` is required.

**What each record needs**, and nothing else is required of you:

| | must have | may have |
|---|---|---|
| `text` · `think` | `text` | `whole` |
| `tool` | `id` (a string) | `name` — your brain's own word · `did` |
| `result` | `id`, matching a `tool` you sent | `ok` · `summary` |
| `usage` | | `input` · `output` · `cached` · `model` |
| `file` | `at` (an absolute path) | `name` |
| `done` | `ok` | `session` · `why`, when it failed |

`input` is **fresh tokens only** — what `cached` counts is not in it. Send more than one
`usage` and they are added together, so report each as a share and never as a new total.

Leave a field out rather than guessing at it: an absent `cached` means *you could not tell*,
and is recorded differently from a `cached` of zero. If your brain gives you one input
number that silently includes an unknown amount of cache, report it as `input` and omit
`cached` — a total you cannot split is still the truth, and a split you invented is not. Order is yours — records are kept in
the order you send them. A line that is not JSON, or is a kind not listed here, is kept
verbatim and shown to nobody, so nothing you emit can break a turn.

## The rules that will bite you

**Say `whole` when what you just said is finished.** A brain that writes its reply a
fragment at a time says nothing complete until it stops, so nothing can be shown to
anybody until the turn ends — a reply that rewrites itself under a reader is unreadable.
A brain that says several complete things as it works — "I will look at the logs", and
then what it found — is writing the way a person does, and marking each one `whole` lets
a surface show it as it is said instead of delivering the lot at the end. The last one is
still the answer. Leave it out and you get the old behaviour, which is correct and
merely quieter.

**Say when your brain made something, or nobody will ever see it.** A brain that draws a
picture, renders a chart or writes a report can otherwise only mention it in a sentence —
and a surface showing that turn shows the sentence and not the picture. `file` is how you
say a thing exists: an absolute path, on this machine, that you really wrote.

Only say it about files you made. It is not read here and it is not opened here, but a
surface may send it to wherever somebody is reading, and where it may be sent from is
bounded — the agent's own workspace and home. Naming something outside that is not an
error and simply will not be sent, so there is nothing to be gained by trying.

**`did` is what the tool *did*, not what your brain calls it.** The same action is `Bash` on
one brain, `shell` on the next and `run_terminal_command` on a third. A channel that
recognised your vendor's names would be carrying your vocabulary forever, so it never sees
them.

The list is closed and short on purpose — `read`, `search`, `run`, `edit`, `list`, `make`.
If what your tool did is not one of those, **leave `did` out**: `name` still carries your own word
for it, and a reader that shows nothing is better than one taught to believe a word that
means something else here. Do not stretch one to fit; tell us instead, and the list can
grow by a release rather than by every adapter guessing differently.

**Report the turn's own tokens, not the conversation's.** If your brain hands you a running
total, subtract what you reported last time. Getting this wrong overstates every turn after
the first, and a spend limit built on it fires on how long a conversation is rather than on
what it cost.

Keep what you subtract from in `RUNDESK_PROVIDER_HOME`, keyed by your brain's own session
handle — that is the thing a running total is running against. Three cases worth deciding
before they happen: a handle you have never seen subtracts nothing, and that one turn reads
high; a total that came back *lower* than last time means the conversation was restarted
underneath you, so report it whole rather than a negative; and if you cannot tell at all,
report nothing rather than a guess.

**Keep cached tokens apart from fresh ones.** Re-reading a cached prompt is most of the
volume and a fraction of the price. Folding them together reports a number that is
technically real and practically a lie. If your brain folds cache reads *into* its input
count, subtract them back out before you report.

**`RUNDESK_POSTURE` is a request, and honouring it is yours.** `read` means the owner asked
this turn to look without changing anything; `work` is the ordinary case. Rundesk enforces
nothing — it has no way to, and pretending otherwise would be worse than saying so. Map it
onto whatever your brain really has: a sandbox, a tool list, a permission mode. If your
brain has nothing to map it onto, ignore it; that is honest, and it is why nothing here
describes a posture as containment.

**Say nothing you did not measure.** `model` is what actually answered — omit it if your
brain does not say, and nothing will be claimed. The same goes for tools: an adapter with no
loop reports no tools, which is a complete and honest turn, not a degraded one.

**The session handle is yours and opaque to us.** Report it on `done` and we hand it straight
back next time in `RUNDESK_RESUME`, for that conversation and that provider together. We
never read it, never parse it, and never give it to a different brain. Not reporting one
costs the next turn its context and nothing else.

**`RUNDESK_SETTINGS` is not ours to understand.** Whatever the owner set with `--set`
arrives as one JSON object. Both spellings merge into it, and a value that reads as JSON
arrives as JSON:

```sh
rundesk ask ava "…" --set effort=high --set '{"flags":["--no-color"],"retries":3}'
```
```json
{"effort": "high", "flags": ["--no-color"], "retries": 3}
```

There are no keys rundesk defines — `effort` and `flags` above are that owner's words for
that owner's brain. **You decide what you understand.** Map what you know onto your own
flags, ignore what you do not, and say on stderr when something recognised is malformed so
an owner who mistyped hears about it. A new option on your CLI is then theirs to reach
today, rather than after a Rundesk release.

**Never a credential — not in settings, and not on a command line.** What an owner set is
written into the run's record, so a token put there is a token in a file that outlives the
turn. Anything on a command line is readable through the process list and kept in a shell's
history. Read a secret from your own `RUNDESK_PROVIDER_HOME`, or from an environment
variable that never reaches an argument.

**Do not go looking for the owner's own configuration.** `RUNDESK_PROVIDER_HOME` is yours,
and it persists — what you leave there is there next turn. It is empty the *first* time an
agent reaches your brain, which for most brains means not signed in. Say so, and say what to
run — do not quietly copy or link somebody's credentials into it. Sharing one sign-in
between agents may well be what they want, and it is theirs to decide rather than yours to
arrange on their behalf.

**A record we do not recognise is kept, not refused.** Emit something new and it lands in the
run's record verbatim. It will not be shown and it will not break the turn — so you can be
ahead of us without waiting for us.

**Take as long as you need, but keep talking.** Nothing bounds how long a turn may run —
an agent that thinks for an hour is working. What is bounded is how long you may say
*nothing at all*: half an hour on either stream, and anything you write to stderr counts.
If your brain goes quiet for longer than that while it is genuinely busy, say something.

**Exit when the turn is done**, and take your children with you. When a turn is stopped you
get a `SIGTERM` to your whole process group and a few seconds to leave before a `SIGKILL`;
a `done` record on the way out is welcome and not required.

**Both your exit code and your `done` matter, and they mean different things.** `done.ok`
is what *your brain* made of the turn; the exit code is what became of *your program*. A
turn is only recorded as having worked when both say so, so a brain that answered fine
inside an adapter that then crashed reads as the failure it was.

A brain that simply said no is not your program failing — `done ok:false` and exit `0` is
the exact answer. Exiting non-zero as well is allowed and says nothing extra. What you must
not do is exit without any `done` at all: that is a turn that never said it finished, and
nothing downstream can tell it from one still running.

**When a turn is stopped**, exit however you like — nothing reads the code of a program that
was told to stop. A parting `done` is welcome and never required.

## A working adapter

Answers once and stops. Twenty lines, no dependencies:

```sh
#!/usr/bin/env bash
# my-brain — the smallest adapter that is not a lie.
set -euo pipefail

[ "$*" = "--capabilities" ] && { printf '{}\n'; exit 0; }

json() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'; }
say()  { printf '%s\n' "$1"; }

cd "$RUNDESK_CWD"                   # work where the agent works

# The turn arrives on stdin and goes to your brain the same way. Never as an argument:
# what somebody asks their agent is readable through the process list otherwise.
answer=$(your-cli --model "${RUNDESK_MODEL:-default}" --read-prompt-from-stdin) || {
  say '{"type":"done","ok":false,"why":"your-cli would not answer"}'
  exit 1
}

say "$(printf '{"type":"text","text":%s}' "$(printf '%s' "$answer" | json)")"
say '{"type":"done","ok":true}'
```

If your brain will only take a prompt as an argument, that is its limit rather than yours —
pass it, and know that it is visible in the process list while it runs.

Point an agent at it and it is a first-class brain:

```sh
rundesk add ava --provider /opt/my-brain
rundesk ask ava "what changed today?"
```

Give it whatever your CLI takes, without anything changing here:

```sh
rundesk ask ava "…" --set effort=high --set '{"flags":["--no-color"]}'
```

## Steering, if your brain can take it

Only if you said `steer: true`. Your stdin stays open, and every line is a record:

```json
{"type":"say","text":"count from one to ten"}      <- the prompt
{"type":"say","text":"actually, stop at three"}    <- eight seconds later
```

Read a line, act on it, keep reading. Everything that arrives goes to the turn that is
*already running* — it is not a new turn, and the old one is not thrown away.

**The turn ends when your brain is finished, not when your stdin closes.** Say `done` and
exit the moment the work is over, whatever your input is doing. Rundesk may hold it open
long after — a person typing at a terminal has not closed anything just because they have
stopped typing — so an adapter that waited for the close would be waiting on somebody who
is waiting on it. A close is a promise that nothing more is coming, and nothing else.

Rundesk writes every one of these into the run's record as it sends it, so a word put into
a turn is never a word the account cannot show.

## Proving it

The same suite every shipped adapter passes is the one yours passes — that is what makes "a
brain Rundesk has never heard of" a claim rather than a hope. It checks that a whole turn
completes, that a brain reporting no tools still produces a well-formed turn, that an
unknown record survives, that a running total is reported as this turn's share, that
stopping ends everything, and that one adapter cannot reach another agent's workspace.

Run it against yours:

```sh
git clone https://github.com/rundesk-ai/rundesk-cli && cd rundesk-cli
python3 tests/test_provider.py --adapter /opt/my-brain
python3 tests/test_provider.py --adapter /opt/my-brain --home ~/.my-brain   # if it signs in
```

Run bare it needs no account, no token and no network — the adapters it drives are then
small programs, which is the same thing yours is. Pointed at yours it really runs your
brain, which is what you want it to do; and if your brain needs a sign-in, `--home` is the
private home to hand it, because it will not find one in an empty directory.

**If your adapter follows this page and the suite still fails it, this page is wrong** — it
is the contract, and the code is what has to move.

---
*This page is the contract — if your adapter follows it and the suite still fails, this page
is what moves. [`../prd-drafts/provider-adapter.md`](../prd-drafts/provider-adapter.md) is
the list of requirements it is held to, and which test proves each; it describes this page
rather than the other way round.*
