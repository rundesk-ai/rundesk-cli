---
title: Read what happened
description: Search an agent's conversations, filter what was said, see what it ran, and what it cost.
sidebar:
  order: 3
---

Every turn is recorded in Rundesk's own form rather than a provider's private session format,
which is what makes these four commands possible at all. They work the same whether the turn
came from your terminal, from Discord, or from a schedule.

## Search what was said

```sh
rundesk search ava "release checklist"
rundesk search ava --most 50 "auth guard"
```

Full text, across that agent's conversations, newest first.

## Filter what was said

`search` is by words. `messages` is by everything else:

```sh
rundesk messages ava                              # the last 20, newest first
rundesk messages ava --most 100
rundesk messages ava --source schedule            # only unattended work
rundesk messages ava --channel discord-rooms      # only one channel
rundesk messages ava --author agent               # only what the agent said
rundesk messages ava --since 4812                 # only after this message
```

| Filter | Narrows to |
|---|---|
| `--source` | Work admitted one way — `terminal`, `channel`, or `schedule` |
| `--channel` | One channel, by the name it was added under |
| `--conversation` | One place on that channel — a room or a direct message |
| `--author` | One kind of author — `user`, `agent`, or `rundesk` |
| `--since` | Everything after a message, by the id shown beside it |
| `--most` | How many to show (default 20) |

`--since` is the one to build on. It gives you a stable place to resume from, so a script that
watches an agent does not have to re-read what it has already seen.

## See what it ran

```sh
rundesk runs ava
rundesk runs ava --most 100
```

One line per run with what became of it. This covers scheduled turns and scheduled programs
alike — the outcome is recorded the same way for both, which is what makes a schedule a
reasonable place to put ordinary automation you want a durable record of.

## See what it cost

```sh
rundesk usage           # every agent
rundesk usage ava       # one of them
```

Token usage is normalized across providers, so the cost of a fleet running on different brains
is a question with an answer.

### Absent is not zero

An agent that has run nothing reports its input, output, and cached token counts as **absent**,
not as `0`. A run Rundesk could not account for is counted separately from a run that used
nothing — absent and zero are different claims.

## What the gateway itself said

The commands above read the agent's records. The gateway's own log is separate:

```sh
rundesk logs ava
rundesk logs ava -n 200
rundesk logs ava --source machine
```

`--source machine` shows what the operating system caught that never reached the gateway's own
log. That is where a process that died before it could write anything leaves its only trace —
see [when something breaks](/guides/troubleshooting/).
