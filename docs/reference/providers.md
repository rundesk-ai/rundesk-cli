---
title: Providers
description: The four shipped provider adapters, what each supports, and how to point Rundesk at your own.
sidebar:
  order: 1
---

Rundesk ships four first-class provider adapters. Each uses the provider CLI and login
**already established on your machine** — Rundesk does not copy provider credentials.

| Provider CLI | `--provider` | First-class support |
|---|---|---|
| [OpenAI Codex CLI](https://learn.chatgpt.com/docs/codex/cli) | `codex` | Continuing conversations, model selection, tool activity, per-turn usage, and live steering |
| [Anthropic Claude Code](https://code.claude.com/docs/en/overview) | `claude` | Continuing conversations, model selection, tool activity, and per-turn usage |
| [xAI Grok CLI](https://docs.x.ai/build/cli/headless-scripting) | `grok` | Continuing conversations, model selection, tool activity, and per-turn usage |
| [Google Antigravity CLI](https://antigravity.google/docs/cli/install) | `antigravity` | Continuing conversations, model selection, tool activity, and per-turn usage |

## Choosing one

At creation:

```sh
rundesk add ava --provider codex
rundesk add claude-agent --provider claude
rundesk add grok-agent --provider grok
rundesk add antigravity-agent --provider antigravity
```

On an existing agent, without replacing its identity, home, memory, conversations, channels,
schedules, or history:

```sh
rundesk configure ava --provider claude
```

Rundesk checks the new adapter can run first, then changes the default atomically.

:::caution
Models and settings are provider-specific. Switching providers clears the old values unless
you supply replacements with `--model` and `--set`.
:::

A turn already underway finishes with the provider it started with; subsequent turns use the
new default.

## Per-turn and per-schedule

You can choose a different provider or model for **one turn or one schedule** without
changing the agent's default at all. A nightly review does not have to run on the brain you
use for conversation.

## Custom providers are first-class

```sh
rundesk add ava --provider /opt/my-provider --model fast-1 --set effort=high
```

A provider adapter is an executable that exchanges newline-delimited JSON records with
Rundesk. It can be a Python program, a compiled binary, or a shell script. Custom providers
get the same agent homes, schedules, channels, turn records, usage reporting, and lifecycle
as the shipped adapters — there is no second-class path.

→ [Write a provider adapter](/extend/provider-adapters/)
