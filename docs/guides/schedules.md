---
title: Schedule work
description: Recurring cron turns and one-time runs, with outcomes recorded and delivered to a channel.
sidebar:
  order: 2
---

A schedule starts a turn without you. Rundesk records the outcome either way.

## Recurring

Standard five-field cron:

```sh
rundesk schedules ava add nightly \
  --when "0 3 * * *" \
  --ask "review today's changes and report anything risky"
```

## Once, at an exact time

```sh
rundesk schedules ava add release-check \
  --at "2026-07-29T09:00" \
  --ask "verify the release and summarize the result" \
  --to discord-dms
```

`--to` delivers the outcome to an existing channel, so a scheduled turn reaches you rather
than sitting in a log you have to remember to read.

One-time schedules are also the right tool for a safety net: a check that needs to happen
after something finishes, when that something may outlive the session that started it.

## Two guarantees worth relying on

- **No overlap.** The same schedule never runs on top of itself. A nightly review that takes
  longer than usual does not get a second copy started underneath it.
- **No late execution after downtime.** If the machine was asleep at 03:00, the 03:00 run
  does not fire at 08:00 when you open the lid. A stale run is worse than a missed one — it
  reports on a world that has moved.

## Turns or executables

A schedule can start an agent turn or **an executable by full path**. The outcome is recorded
the same way for both, which makes Rundesk a reasonable place to put ordinary automation you
want a durable record of.

## Per-schedule overrides

Provider, model, instructions, and delivery channel can all be set per schedule. A nightly
review can run on a cheaper brain than the one you talk to during the day, without changing
the agent's default.
