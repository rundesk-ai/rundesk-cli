---
title: Your first agent
description: Create a named agent, ask it something, and keep it available after the terminal closes.
sidebar:
  order: 3
---

Three commands to a working teammate.

```sh
rundesk add ava --provider codex
rundesk doctor ava
rundesk ask ava "summarize what changed in this repository today"
```

`add` creates the agent and its home. `doctor` proves the provider adapter can actually run
before you depend on it. `ask` starts a conversation — the answer streams to your terminal.

## The conversation continues

The next `ask` resumes the same terminal conversation. The agent remembers what you were
talking about.

```sh
rundesk ask ava "now check whether any of that is covered by a test"
```

Useful modifiers:

| Flag | Effect |
|---|---|
| `--fresh` | Start a new conversation instead of resuming |
| `--read-only` | A constrained turn — the agent looks, but does not change anything |
| `--steer` | Add instructions while a turn is already running (Codex) |

## Keep it available

So far the agent only exists while you are sitting in front of it. Give it a gateway:

```sh
rundesk start ava
rundesk agents
rundesk logs ava
```

`start` hands the agent to macOS `launchd`, which keeps it running and brings it back after a
crash, reboot, or automatic update.

Each agent has **its own** gateway. Restarting or stopping one does not disturb the others,
and stopping a gateway ends the provider and every child process it started — no orphans.

## Change its mind, keep its identity

`configure` changes an agent's defaults without replacing its home, memory, conversations,
channels, schedules, or history:

```sh
rundesk configure ava --provider claude
rundesk configure ava --model opus
rundesk configure ava --set effort=high
rundesk configure ava --instructions "Keep answers concise."
```

Rundesk checks the new adapter can run **before** it changes anything, then switches
atomically. A turn already underway finishes on the provider it started with.

:::note
Models and settings are provider-specific, so switching providers clears the old values
unless you supply replacements with `--model` and `--set`.
:::

## Where next

- [Put the agent on Discord](/guides/discord/) so you can reach it from your phone
- [Give it a schedule](/guides/schedules/) so it works while you sleep
- [Understand its home](/concepts/agent-home/) — the files that make it *this* agent
