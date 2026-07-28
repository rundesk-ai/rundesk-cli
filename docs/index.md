---
title: Rundesk documentation
description: Documentation for the Rundesk CLI — running AI coding agents as durable, named teammates on your own Mac.
tableOfContents: false
---

Documentation for **Rundesk**, the provider-agnostic multi-agent gateway that runs on your
own machine. It keeps the coding CLI you already use — Codex, Claude Code, Grok, Google
Antigravity — running with its own workspace, rules, memory, skills, conversations, and
history.

New here? [What Rundesk is](/start/what-rundesk-is/) explains the model in about two minutes,
then [Install](/start/install/) and [Your first agent](/start/first-agent/) get you to a
working teammate.

In a hurry:

```sh
curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash
rundesk add ava --provider codex
rundesk ask ava "review this repository and tell me the highest-risk open issue"
```

## Browse the docs

### Start here

| Page | What it covers |
|---|---|
| [What Rundesk is](/start/what-rundesk-is/) | The model, what it is not, and the pieces that make it up |
| [Install](/start/install/) | One command, where things go, updates, and uninstall |
| [Your first agent](/start/first-agent/) | Create an agent, ask it something, give it a gateway |

### Concepts

| Page | What it covers |
|---|---|
| [Agents and gateways](/concepts/agents/) | What an agent owns, and what `launchd` does for it |
| [The agent home](/concepts/agent-home/) | The four markdown files that decide who an agent is |
| [Conversations and records](/concepts/conversations/) | How a turn is recorded, and why the history is yours |
| [Skills](/concepts/skills/) | Folders of instructions, granted per agent from a shared library |

### Guides

| Page | What it covers |
|---|---|
| [Put an agent on Discord](/guides/discord/) | Allowlists, threads, and separate instructions for public rooms |
| [Schedule work](/guides/schedules/) | Cron and one-time runs, with outcomes delivered to a channel |
| [Back up and restore](/guides/backups/) | Daily copies, and what putting one back really does |

### Reference

| Page | What it covers |
|---|---|
| [Providers](/reference/providers/) | The four shipped adapters, and pointing Rundesk at your own |
| [CLI reference](/reference/cli/) | Every command and argument, generated from the parser |

### Extend

| Page | What it covers |
|---|---|
| [Provider adapters](/extend/provider-adapters/) | Put another brain behind an agent |
| [Channel adapters](/extend/channel-adapters/) | Reach an agent from another platform |
| [Integration CLIs](/extend/integration-clis/) | Give every agent a custom command |

## Requirements

- macOS
- Python 3.9 or newer
- At least one [supported provider CLI](/reference/providers/), installed and signed in

## Elsewhere

- [`rundesk-ai/rundesk-cli`](https://github.com/rundesk-ai/rundesk-cli) — the source, issues, and releases
- [Tested contracts](https://github.com/rundesk-ai/rundesk-cli/blob/main/.knowledge/prd/README.md) — every guarantee and the test that proves it
- [Roadmap](https://github.com/rundesk-ai/rundesk-cli/blob/main/ROADMAP.md) — what is built, what is next, and why
- Rundesk is [MIT licensed](https://github.com/rundesk-ai/rundesk-cli/blob/main/LICENSE)
