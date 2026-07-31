---
title: Integration CLIs
description: Give every agent a custom command — a guarded, offline-testable wrapper around a service API.
sidebar:
  order: 3
---

Rundesk keeps a shared executable library on **every agent's `PATH`**. An integration CLI is
how an agent actually reaches a service — Jira, Sentry, a calendar, your own API — rather
than being told to imagine it can.

A skill tells an agent *how* to think about a job. An integration CLI gives it the command to
do the job. Written as a pair, a capability developed once can be granted to every agent.

## What a good one looks like

- **Guarded.** Reads are free; mutations require explicit authorization for that exact change
  and a confirmation flag. An agent should not be able to send, delete, or charge by accident.
- **Offline-testable.** The network is an argument, not an import. The test suite proves the
  decisions without reaching anybody's uptime.
- **Credential-safe.** The CLI loads its own credentials and never prints them. Skills
  reference secrets by name; values stay in the environment.
- **Honest about failure.** A command that cannot do the thing says so and exits non-zero. A
  script that reads `0` believes the work happened.

## Building one

The full guide ships as a skill:

→ **[The integration CLI guide](https://github.com/rundesk-ai/rundesk-cli/blob/main/src/templates/skills/building-integration-clis/SKILL.md)**

Grant an agent the `building-integration-clis` skill and ask it to build the wrapper you
need — it will follow the guard and testing conventions rather than inventing its own.

## Why this beats an in-process plugin

The same reason provider and channel seams are programs: an executable can be written in any
language, tested on its own, versioned on its own, and swapped without a Rundesk release.
