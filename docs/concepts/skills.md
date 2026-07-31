---
title: Skills
description: Folders of instructions for a particular kind of work, granted per agent from a shared library.
sidebar:
  order: 4
---

A **skill** is a folder of instructions for a particular kind of work. It exists because
somebody decided this work should be done a particular way here — ignoring it and improvising
is how that decision gets quietly lost.

Skills live in a shared library and are granted per agent.

```sh
rundesk skills
```

That says what exists on the machine and which of it an agent has.

## Two kinds

- **Built-in skills** ship with Rundesk and update with it.
- **Owner-created skills** are yours and do not get overwritten by an update.

An update replaces what Rundesk laid down and nothing else, so your own skills survive it.

## What ships

| Skill | Covers |
|---|---|
| `using-rundesk` | Operating Rundesk itself — history, schedules, channels, runs, costs |
| `writing-skills` | How to write a skill, and where to put it so it can be granted |
| `building-a-provider-adapter` | Putting another brain behind an agent |
| `building-a-channel-adapter` | Reaching an agent from another platform |
| `building-integration-clis` | Giving every agent a custom command |
| `managing-backups` | Taking copies, and what restoring one really does |
| `reporting-a-rundesk-bug` | Filing a defect with durable evidence and nothing sensitive |
| `writing-pull-requests` | Making the case for a change rather than listing the diff |

## Integration CLIs

Alongside skills, Rundesk keeps a shared **executable** library placed on every agent's
`PATH`. A skill tells an agent *how* to think about a job; an integration CLI gives it the
command to actually do it — a guarded, offline-testable wrapper around a service API.

The pair is the unit that makes a capability reusable: write it once, grant it to every
agent. See [Integration CLIs](/extend/integration-clis/).

## Self-improving by design

Agents can turn repeated work into new skills and integration CLIs themselves. A capability
developed once by one agent can then be granted to all of them.
