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

Every field is `false` when you leave it out, so `{}` is a valid answer and a complete
adapter. **Rundesk asks rather than assuming**, and it never guesses from your name — so say
`false` and the work is simply absent, rather than expected and missing.

This must not need an account, a network or a login. It is asked by `rundesk doctor`, before
any turn, and it must be the same answer every time.

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

The prompt arrives on **stdin**.

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

**A record we do not recognise is kept, not refused.** Emit something new and it lands in the
run's record verbatim. It will not be shown and it will not break the turn — so you can be
ahead of us without waiting for us.

**Exit when the turn is done**, and take your children with you. Rundesk ends your process
group, but a turn that never ends is ended on silence rather than on a clock, because real
work can legitimately take hours.

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

Run it against yours:

```sh
python3 tests/test_provider.py --adapter /opt/my-brain
```

Nothing in it needs an account, a token or a network: the suite drives adapters that are
themselves small programs, which is the same thing your adapter is.

**If your adapter follows this page and the suite still fails it, this page is wrong** — it
is the contract, and the code is what has to move.

---
*This is a project how-to. The contract it describes is [`../prd-drafts/provider-adapter.md`](../prd-drafts/provider-adapter.md).*
