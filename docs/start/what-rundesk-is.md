---
title: What Rundesk is
description: Rundesk runs the coding CLI you already use as a durable, named teammate with its own home, memory, schedules, and channels.
sidebar:
  order: 1
---

Rundesk is a **provider-agnostic multi-agent gateway** for your own machine. It keeps the
coding CLI you already use running with its own workspace, rules, memory, skills,
conversations, and history.

It does not replace Codex, Claude Code, Grok, or Google Antigravity. It gives those tools a
dependable home and a common operating layer.

## The problem it solves

A coding agent is excellent at a turn of work. Its native home, though, is usually one
terminal session — close the window and the identity, the context, and the accumulated
judgement go with it.

Rundesk adds the parts needed to operate an agent over time:

- a stable identity and workspace for each agent;
- an always-on gateway owned by the operating system;
- conversations that resume across turns and surfaces;
- schedules that run once, never overlap, and do not run late after downtime;
- access controls for chat channels;
- normalized history and usage across different provider CLIs; and
- updates, backups, diagnostics, and removal with explicit ownership boundaries.

## What it is not

- **Not a model.** Rundesk has no opinion about which brain answers. It runs the provider
  CLI you already installed and signed into.
- **Not a hosted service.** Everything runs on your machine. No Rundesk server is required
  and none is contacted to answer a turn.
- **Not a credential store.** Provider adapters use the login already established on your
  machine. Rundesk does not copy provider credentials.

## How the pieces fit

| Piece | What it is |
|---|---|
| **Agent** | A named teammate with its own home, memory, skills, and history |
| **Gateway** | The always-on process for one agent, owned by `launchd` |
| **Provider** | The brain — an executable adapter wrapping a coding CLI |
| **Channel** | A surface the agent is reachable on — the terminal, Discord, or one you wrote |
| **Schedule** | A cron or one-time trigger that starts a turn and records its outcome |
| **Skill** | A folder of instructions granted to an agent for a particular kind of work |

The provider and channel seams are **programs, not in-process plugins**. A custom adapter
can be written in any language and receives the same scheduling, lifecycle, history, and
channel behavior as a shipped one.

## One night, end to end

Nothing below needs you to be awake for it.

```text
  03:00                                                    07:40
    │                                                        │
    ▼                                                        ▼
┌────────────┐   ┌───────────────┐   ┌──────────────┐   ┌──────────┐
│  schedule  │──▶│    gateway    │──▶│   provider   │   │   you    │
│  is due    │   │  ava, always  │   │  codex, run  │   │ on your  │
│            │   │  on, launchd  │   │  as a program│   │  phone   │
└────────────┘   └───────┬───────┘   └──────┬───────┘   └────▲─────┘
                         │                  │                │
              never runs on top             │                │
              of itself; never              ▼                │
              fires late after     ┌──────────────────┐      │
              downtime             │  the turn, as a  │      │
                                   │  durable record  │      │
                                   │  messages, tools,│      │
                                   │  outcome, tokens │      │
                                   └────────┬─────────┘      │
                                            │                │
                                            └────────────────┘
                                              delivered to
                                              the channel it
                                              was told to use
```

In the morning `rundesk runs ava` says what happened, `rundesk usage ava` says what it cost,
and asking the agent about it on Discord continues the same conversation.

Next: [install it](/start/install/).
