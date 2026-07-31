---
title: When something breaks
description: What doctor tells you, where the logs are, and the failures that actually happen.
sidebar:
  order: 5
---

Start here, in this order. Most problems answer to the first two.

```sh
rundesk doctor          # what stands between every agent and a working turn
rundesk doctor ava      # the same, for one agent
rundesk status          # how Rundesk itself is on this machine
rundesk logs ava        # what that agent has been saying
```

## Reading an exit code

Scripts and schedules see these, so they are worth telling apart:

| Code | Means |
|---|---|
| `0` | It did the thing |
| `1` | It ran and failed, and said why |
| `2` | Typed wrongly — read the help |
| `69` | This Rundesk has not built that yet, and nothing changed |

`69` is deliberately not `2`. A script has to be able to tell "this version lacks the command"
from "the caller got it wrong", because the two want opposite things done about them.

## The gateway will not start, or will not come back

```sh
rundesk agents          # what each agent is doing
rundesk logs ava --source machine
```

`--source machine` is the important one here. It shows what the operating system caught that
never reached the gateway's own log — which is where a job that died before it could write
anything leaves its only trace.

`launchd` owns each gateway, so a gateway that keeps restarting is usually failing at startup
rather than crashing under load. The machine log says which.

## The agent answers `NOT CONFIGURED`, or a turn fails immediately

Run `rundesk doctor ava`. It checks that the agent's provider adapter can actually run, which
is the failure this is nearly always about.

The most common cause is that the provider CLI logged itself out. Rundesk uses the login
already on your machine and never copies it, so the fix is to sign in to that CLI directly and
run `doctor` again.

Run `doctor` when you create an agent and whenever you change its provider. An unattended
schedule is a bad place to discover a signed-out CLI.

## A scheduled turn did not happen

Two behaviours look like a bug and are not:

- **No overlap.** The same schedule never runs on top of itself. A nightly review that ran
  long does not get a second copy started underneath it.
- **No late execution after downtime.** If the machine was asleep at 03:00, the 03:00 run does
  not fire at 08:00 when you open the lid. A stale run reports on a world that has moved.

To see what actually happened, including the one-time schedules whose moment has passed:

```sh
rundesk runs ava
rundesk schedules ava --expired
```

To prove a schedule works without waiting for it:

```sh
rundesk schedules ava run nightly
```

## The Discord bot connects and stays silent

Check the allowlist first — this is the usual answer:

```sh
rundesk channels ava show discord-dms
```

Rundesk owns who may reach an agent, not Discord. A message from somebody not on the channel's
allowlist is admitted by the platform and refused here.

If the allowlist is right, check that nothing else is holding the same token. **A second
connection with the same bot token silently wins**, and neither side reports an error — so
running the adapter by hand to diagnose it, while the gateway is already serving that channel,
makes one of the two stop receiving. Stop the gateway first, or accept that what you are
watching is not what the gateway sees.

## A command works in your shell and not from a schedule

A gateway runs with a deliberately minimal environment — see
[what an agent can reach](/concepts/security/). Two consequences account for most of these:

- A scheduled **program must be given by full path**. A bare name is refused.
- `PATH` is the integration command library plus what the gateway inherited, which is not
  what your interactive shell has.

## After an update

An update that needs to migrate agent records stops every gateway first and keeps a rollback
copy of each database. If a migration fails, every agent's records are restored and the
previous release is kept — a failed update leaves you where you started rather than half-way.

To see where you are:

```sh
rundesk version --check
rundesk update --status
```

## Before anything destructive

```sh
rundesk backups add
```

It costs seconds. `restore` replaces everything this install keeps rather than merging into
it, so if you are unsure whether you need a restore or a narrower fix, the narrower fix is
almost always right. See [Back up and restore](/guides/backups/).

## Filing a bug

Rundesk ships a skill for this. Grant it and ask:

```sh
rundesk skills grant ava reporting-a-rundesk-bug
```

It collects durable evidence and leaves out anything sensitive. Failing that, the repository's
[issues](https://github.com/rundesk-ai/rundesk-cli/issues) want the output of `rundesk doctor`,
`rundesk status`, and the relevant `rundesk logs ava --source machine`.
