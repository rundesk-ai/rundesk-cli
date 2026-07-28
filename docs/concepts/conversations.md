---
title: Conversations and records
description: How a turn is recorded, and why the history is Rundesk's rather than the provider's.
sidebar:
  order: 3
---

A **turn** is one exchange: something asks, the agent answers. A **conversation** is a series
of turns that resume each other.

## Continuing and fresh

Conversations resume across turns *and across surfaces*. The same agent picks up where it
left off whether you reached it from the terminal, from Discord, or from a schedule — each
surface keeps its own thread of conversation with that agent.

```sh
rundesk ask ava "what did we decide about the release?"   # resumes
rundesk ask ava --fresh "unrelated question"              # starts over
```

## Postures

A turn runs read-only or working. Rundesk translates the posture into each provider's native
controls, so `--read-only` means the same thing to Codex and to Claude Code even though they
express it differently.

## What gets recorded

Per turn, durably:

- the messages, both directions
- tool activity
- the outcome, or the error
- token usage

This matters because it does not depend on a provider's private session format. You can
inspect what an agent did, filter messages, and run full-text search across an agent's
conversations without asking a vendor's CLI to explain itself — and the record survives that
vendor changing its storage tomorrow.

Usage is normalized across providers, so cost across a fleet of agents on different brains is
a question you can actually answer.
