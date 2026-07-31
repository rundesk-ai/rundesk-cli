---
title: Back up and restore
description: Taking a copy is cheap. Putting one back replaces everything this install keeps.
sidebar:
  order: 3
---

Rundesk keeps copies of everything an owner has — agents, homes, memory, conversations,
schedules, channels, and configuration.

```sh
rundesk backups            # what copies exist
rundesk backups add        # take one now
rundesk backups on         # have the machine take one every day
rundesk backups off        # stop that
```

Daily backups are the default posture. Take a manual one before anything destructive — it
costs seconds, and it is the only thing that makes a bad decision reversible.

## Restore replaces everything

```sh
rundesk backups restore <backup>
```

:::danger
`restore` puts a backup back **replacing everything this install keeps** — not merging into
it. Every agent, conversation, schedule, and channel returns to its state at the moment the
copy was taken, and anything that happened since is gone.
:::

This is the asymmetry to hold onto: taking a copy is cheap and putting one back is not. If
you are unsure whether you need a restore or a narrower fix, the narrower fix is almost
always right.

Removing a single copy is separate, and only touches that one:

```sh
rundesk backups remove <backup>
```

Both `restore` and `remove` ask for confirmation. `--yes` skips the prompt, for scripts.

## Where copies live

The backup location is configurable. Program and owner data are kept in separate directories
by design — `~/.rundesk/app/` is Rundesk's and `~/.rundesk/data/` is yours — so a backup is a
copy of `data/`, and reinstalling Rundesk is never the thing that loses it.
