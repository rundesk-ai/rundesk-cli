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
| `RUNDESK_CWD` | the agent's workspace — work here |
| `RUNDESK_PROVIDER_HOME` | yours alone, for config, credentials, session files and anything you need to remember between turns |
| `RUNDESK_MODEL` | the model asked for, or unset — a name you understand, not one we enumerate |
| `RUNDESK_RUN` | the id of this run, for correlating anything you keep |
| `RUNDESK_RESUME` | the handle you reported last time on this conversation, or unset for a new one |
| `RUNDESK_POSTURE` | `read` or `work` — how much of the machine this turn may touch |
| `RUNDESK_SETTINGS` | a JSON object of whatever the owner set, passed through unread |

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
{"type": "text",   "text": "Looking at the logs now."}
{"type": "think",  "text": "The error is in the parser."}
{"type": "tool",   "id": "1", "name": "Bash", "did": "run"}
{"type": "result", "id": "1", "ok": true, "summary": "3 files changed"}
{"type": "usage",  "input": 1200, "output": 340, "cached": 8000, "model": "…"}
{"type": "done",   "ok": true, "session": "019f954d-ad60-7f91"}
```

**stderr is yours.** Say what went wrong there; it is kept, and it is never mistaken for what
you reported.

That is the contract. Six kinds of record, and only `done` is required.

**What each record needs**, and nothing else is required of you:

| | must have | may have |
|---|---|---|
| `text` · `think` | `text` | |
| `tool` | `id` (a string) | `name` — your brain's own word · `did` |
| `result` | `id`, matching a `tool` you sent | `ok` · `summary` |
| `usage` | | `input` · `output` · `cached` · `model` |
| `done` | `ok` | `session` · `why`, when it failed |

Leave a field out rather than guessing at it: an absent `cached` means *you could not tell*,
and is recorded differently from a `cached` of zero. Order is yours — records are kept in
the order you send them. A line that is not JSON, or is a kind not listed here, is kept
verbatim and shown to nobody, so nothing you emit can break a turn.

## The rules that will bite you

**`did` is what the tool *did*, not what your brain calls it.** The same action is `Bash` on
one brain, `shell` on the next and `run_terminal_command` on a third. Say one of `read`,
`search`, `run`, `edit`, `list` — or leave it out. A channel that recognised your vendor's
names would be carrying your vocabulary forever, so it never sees them.

**Report the turn's own tokens, not the conversation's.** If your brain hands you a running
total, subtract what you reported last time — keep it in `RUNDESK_PROVIDER_HOME`, which is
yours and outlives the turn. Getting this wrong overstates every turn after the first, and a
spend limit built on it fires on how long a conversation is rather than what it cost.

**Keep cached tokens apart from fresh ones.** Re-reading a cached prompt is most of the
volume and a fraction of the price. Folding them together reports a number that is
technically real and practically a lie. If your brain folds cache reads *into* its input
count, subtract them back out before you report.

**Say nothing you did not measure.** `model` is what actually answered — omit it if your
brain does not say, and nothing will be claimed. The same goes for tools: an adapter with no
loop reports no tools, which is a complete and honest turn, not a degraded one.

**The session handle is yours and opaque to us.** Report it on `done` and we hand it straight
back next time in `RUNDESK_RESUME`, for that conversation and that provider together. We
never read it, never parse it, and never give it to a different brain. Not reporting one
costs the next turn its context and nothing else.

**`RUNDESK_SETTINGS` is not ours to understand.** Whatever the owner set with `--set` arrives
as JSON exactly as they wrote it. Map it onto your own flags however you like, ignore what
you do not recognise, and fail loudly on stderr if something is wrong — that way a new flag
on your CLI is something an owner can reach today, not after a Rundesk release.

**Never a credential — not in settings, and not on a command line.** What an owner set is
written into the run's record, so a token put there is a token in a file that outlives the
turn. Anything on a command line is readable through the process list and kept in a shell's
history. Read a secret from your own `RUNDESK_PROVIDER_HOME`, or from an environment
variable that never reaches an argument.

**Do not go looking for the owner's own configuration.** `RUNDESK_PROVIDER_HOME` is yours
and it starts out empty, which for most brains means not signed in. Say so, and say what to
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
inside an adapter that then crashed reads as the failure it was. Exiting without any `done`
at all is a turn that never said it finished.

## A working adapter

Answers once and stops. Twenty lines, no dependencies:

```sh
#!/usr/bin/env bash
# my-brain — the smallest adapter that is not a lie.
set -euo pipefail

[ "${1:-}" = "--capabilities" ] && { printf '{"resume":false}\n'; exit 0; }

json() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'; }
say()  { printf '%s\n' "$1"; }

prompt=$(cat)                       # the turn arrives on stdin
cd "$RUNDESK_CWD"                   # work where the agent works

answer=$(your-cli --model "${RUNDESK_MODEL:-default}" --prompt "$prompt") || {
  say '{"type":"done","ok":false}'  # a turn that failed says so
  exit 1
}

say "$(printf '{"type":"text","text":%s}' "$(printf '%s' "$answer" | json)")"
say '{"type":"done","ok":true}'
```

Point an agent at it and it is a first-class brain:

```sh
rundesk add ava --provider /opt/my-brain
rundesk ask ava "what changed today?"
```

Give it whatever your CLI takes, without anything changing here:

```sh
rundesk ask ava "…" --set effort=high --set '{"flags":["--no-color"]}'
```

## Proving it

The same suite every shipped adapter passes is the one yours passes — that is what makes "a
brain Rundesk has never heard of" a claim rather than a hope. It checks that a whole turn
completes, that a brain reporting no tools still produces a well-formed turn, that an unknown
record survives, that a running total is reported as this turn's share, that stopping ends
everything, and that one adapter cannot reach another agent's workspace.

## Steering, if your brain can take it

Only if you said `steer: true`. Your stdin stays open for as long as the turn runs, and
every line is a record:

```json
{"type":"say","text":"count from one to ten"}      <- the prompt
{"type":"say","text":"actually, stop at three"}    <- eight seconds later
```

Read a line, act on it, keep reading. Everything that arrives goes to the turn that is
*already running* — it is not a new turn and the old one is not thrown away. When rundesk
has nothing more to say it closes your stdin, which is your signal that no more is coming.

Rundesk writes every one of these into the run's record as it sends it, so a word put into
a turn is never a word the account cannot show.

## Proving it

Run it against yours:

```sh
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
*This is a project how-to. The contract it describes is [`../prd-drafts/provider-adapter.md`](../prd-drafts/provider-adapter.md).*
