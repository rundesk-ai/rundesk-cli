---
title: Agents and gateways
description: What a Rundesk agent owns, and what its gateway does for it.
sidebar:
  order: 1
---

An **agent** is a named teammate. A **gateway** is the always-on process that keeps that
teammate reachable.

## What an agent owns

- An isolated home, workspace, rules, memory, and skills
- Its own conversations, tool activity, outcomes, and token usage
- Its own channels, schedules, and provider defaults
- A private provider home, when the provider supports one

Providers that use the native keyring or a machine-wide login keep their state under the
provider's own rules rather than in the agent's home. Rundesk does not fight them for it.

## What the gateway does

```sh
rundesk start ava
rundesk agents
rundesk logs ava
rundesk restart ava
rundesk stop ava
```

One gateway per agent, owned by macOS `launchd`. That ownership is what makes it durable —
the operating system brings it back after a crash, a reboot, or an automatic update, without
a supervisor process of Rundesk's own to also crash.

- **Agents are independent.** Restarting or stopping one does not disturb the others.
- **Stopping is complete.** Ending a gateway ends the provider and every child process it
  started.

## Diagnostics before failure

```sh
rundesk doctor ava
```

`doctor` checks that an agent's provider adapter can actually run. Run it when you create an
agent and when you change its provider — an unattended 3 a.m. schedule is the wrong place to
discover that a CLI logged itself out.

## Removal

Removing an agent preserves its home unless you explicitly ask to purge it — the identity
goes away, the record of what it did stays.
