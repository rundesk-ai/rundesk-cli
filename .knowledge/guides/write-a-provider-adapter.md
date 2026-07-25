---
name: write-a-provider-adapter
description: How to put your own brain, or your own conversational loop, behind a Rundesk agent — the whole contract, and a working adapter in twenty lines.
---

# Write a provider adapter

Rundesk does not run a conversation. It runs **your program**, gives it somewhere to work, reads what
you report, and ends it when the turn is over. That program is an adapter, and this is everything it
has to do.

It is a program and not a plugin on purpose: Rundesk never loads your code into the gateway that runs
every other agent, and you are not obliged to write Python. An adapter can be a shell script.

## The whole contract

**We run your program.** Its path is whatever the agent was given as its provider:

```sh
rundesk add ava --provider claude          # one that ships
rundesk add ava --provider /opt/my-brain   # yours
```

**You are told where to work, through the environment:**

| | |
|---|---|
| `RUNDESK_CWD` | the agent's workspace — work here |
| `RUNDESK_PROVIDER_HOME` | yours alone, for config, credentials and session files |
| `RUNDESK_MODEL` | the model asked for, or unset — a name you understand, not one we enumerate |
| `RUNDESK_RUN` | the id of this run, for correlating anything you keep |

The prompt arrives on **stdin**.

**You report on stdout, one JSON object per line**, flushed as it happens:

```json
{"type": "text",   "text": "Looking at the logs now."}
{"type": "think",  "text": "The error is in the parser."}
{"type": "tool",   "id": "1", "name": "Bash", "did": "run"}
{"type": "result", "id": "1", "ok": true, "summary": "3 files changed"}
{"type": "usage",  "input": 1200, "output": 340, "cached": 8000, "model": "…"}
{"type": "done",   "ok": true}
```

**stderr is yours.** Say what went wrong there; it is kept, and it is never mistaken for what you
reported.

That is the contract. Six kinds of record, and only `done` is required.

## The rules that will bite you

**`did` is what the tool *did*, not what your brain calls it.** The same action is `Bash` on one brain,
`shell` on the next and `run_terminal_command` on a third. Say one of `read`, `search`, `run`, `edit`,
`list` — or leave it out. A channel that recognised your vendor's names would be carrying your
vocabulary forever, so it never sees them.

**Report the turn's own tokens, not the conversation's.** If your brain hands you a running total,
subtract what you reported last time. Getting this wrong overstates every turn after the first, and a
spend limit built on it fires on how long a conversation is rather than what it cost.

**Keep cached tokens apart from fresh ones.** Re-reading a cached prompt is most of the volume and a
fraction of the price. Folding them together reports a number that is technically real and practically
a lie.

**Say nothing you did not measure.** `model` is what actually answered — omit it if your brain does not
say, and nothing will be claimed. The same goes for tools: an adapter with no loop reports no tools,
which is a complete and honest turn, not a degraded one.

**A record we do not recognise is kept, not refused.** Emit something new and it lands in the run's
record verbatim. It will not be shown and it will not break the turn — so you can be ahead of us
without waiting for us.

**Exit when the turn is done**, and take your children with you. Rundesk ends your process group, but a
turn that never ends is ended on silence rather than on a clock, because real work can legitimately take
hours.

## A working adapter

Answers once and stops. Twenty lines, no dependencies:

```sh
#!/usr/bin/env bash
# my-brain — the smallest adapter that is not a lie.
set -euo pipefail

prompt=$(cat)                       # the turn arrives on stdin
cd "$RUNDESK_CWD"                   # work where the agent works

say() { printf '%s\n' "$1"; }       # one record, one line, flushed

answer=$(your-cli --model "${RUNDESK_MODEL:-default}" --prompt "$prompt") || {
  say '{"type":"done","ok":false}'  # a turn that failed says so
  exit 1
}

say "$(printf '{"type":"text","text":%s}' "$(printf '%s' "$answer" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")"
say '{"type":"done","ok":true}'
```

Point an agent at it and it is a first-class brain:

```sh
rundesk add ava --provider /opt/my-brain
rundesk ask ava "what changed today?"
```

## Proving it

The same suite every shipped adapter passes is the one yours passes — that is what makes "a brain
Rundesk has never heard of" a claim rather than a hope. It checks that a whole turn completes, that a
brain reporting no tools still produces a well-formed turn, that an unknown record survives, that
stopping ends everything, and that one adapter cannot reach another agent's workspace.

Run it against yours:

```sh
python3 tests/test_provider.py --adapter /opt/my-brain
```

Nothing in it needs an account, a token or a network: the suite drives adapters that are themselves
small programs, which is the same thing your adapter is.

---
*This is a project how-to. The contract it describes is [`../prd-drafts/provider-adapter.md`](../prd-drafts/provider-adapter.md).*
