---
title: Configuration
description: The two sections of config.json, what each key accepts, and the default that applies when it is absent.
sidebar:
  order: 2
---

Everything Rundesk remembers about an *agent* is a record that agent keeps. Decisions about
the **install itself** live in one file instead:

```text
~/.rundesk/data/config.json
```

It stands under `data/`, so an ordinary uninstall keeps it, `--purge` takes it, and a backup
contains it.

You write this file by hand. Rundesk reads it and never writes it back, so comments and
formatting you add survive.

## The file

Two sections, both optional, and the file itself is optional:

```json
{
  "backups": {
    "at": "04:00",
    "keep_days": 30
  },
  "updates": {
    "at": "03:00"
  }
}
```

### `backups`

| Key | Accepts | Default |
|---|---|---|
| `at` | A time of day as `HH:MM`, on the machine's own clock | `04:00` |
| `keep_days` | A whole number of days, at least 1 | `30` |

`keep_days` is how long a copy survives before a later backup prunes it. Zero and negative
numbers are refused rather than clamped, because either reading of them destroys something:
treated as the default they keep every backup forever, treated literally they delete your
history.

### `updates`

| Key | Accepts | Default |
|---|---|---|
| `at` | A time of day as `HH:MM`, on the machine's own clock | `03:00` |

The default is early enough to be finished before a working day and late enough to miss the
nightly schedules an agent is likely to have.

After changing it, apply the schedule:

```sh
rundesk update
```

## Missing and unreadable are different

No file means you never wrote one, and every default above applies.

A file that exists and cannot be understood is **refused and reported** — Rundesk does not
fall back to defaults. A malformed file treated as absent is how an install runs on settings
its owner believes they overrode, and they find out when a backup they thought was kept for a
year has gone.

The same applies within a section. `keep_days: "thirty"` is refused and named, rather than
silently becoming 30.

## What is not in here

Anything belonging to one agent — its provider, model, instructions, channels, schedules, and
granted skills — is that agent's own and is changed through the command:

```sh
rundesk configure ava --provider claude --model opus
```

See [`rundesk configure`](/reference/cli/#rundesk-configure).
