---
title: Configuration
description: The three sections of config.json, what each key accepts, and what writes the file.
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

## What is in force

```sh
rundesk config
```

That reports every value governing this install and where each came from — including anything
written in the file that nothing reads, which is reported here and nowhere else.

## The file

Three sections. The install writes it with every effective value, so a fresh install has:

```json
{
  "backups": {
    "at": "04:00",
    "keep_days": 30
  },
  "updates": {
    "at": "03:00"
  },
  "skills": {
    "granted": [
      "managing-rundesk",
      "managing-rundesk-schedules",
      "managing-rundesk-backups",
      "filing-github-issues",
      "filing-rundesk-issues",
      "writing-github-pull-requests",
      "writing-rundesk-pull-requests"
    ]
  }
}
```

### `backups`

| Key | Accepts |
|---|---|
| `at` | A time of day as `HH:MM`, on the machine's own clock |
| `keep_days` | A whole number of days, at least 1 |

`keep_days` is how long a copy survives before a later backup prunes it. Zero and negative
numbers are refused rather than clamped, because either reading of them destroys something:
treated as a default they keep every backup forever, treated literally they delete your
history.

### `updates`

| Key | Accepts |
|---|---|
| `at` | A time of day as `HH:MM`, on the machine's own clock |

The shipped `03:00` is early enough to finish before a working day and late enough to miss the
nightly schedules an agent is likely to have. After changing it, apply the schedule with
`rundesk update`.

### `skills`

| Key | Accepts |
|---|---|
| `granted` | A list of skill names every agent is required to hold |

This is the install-wide baseline, not every skill the release ships. A new agent receives each
one. Add your own skills here to have them granted to every agent automatically.

`filing-rundesk-issues` is Rundesk's own floor rather than a baseline you chose. It is kept in
the file visibly, cannot be configured away, and the command refuses to revoke it.

## The file is the source of truth

**Runtime readers require the values to be in the file.** They do not fall back to a value
inside Python when a key is missing. A missing or unreadable owner value is refused and said
out loud, rather than silently supplied — because reaching around the file makes `config.json`
untrue about what governs the install.

**Missing and unreadable are different.** No file at all is an install that has not written one
yet. A file that exists and cannot be understood is refused and named — never treated as
absent, and never quietly replaced by defaults. The same applies within a section:
`keep_days: "thirty"` is refused and named rather than becoming 30.

## What writes it

You are expected to open and edit this file, which is why it is JSON in the open rather than a
row in a database. No reader ever writes it back, so your formatting and ordering survive.

Exactly two things write:

- **`ensure`**, run by the install and again by an update, adds sections and keys a release did
  not know about, so a file written by an older Rundesk grows into the current shape. Values
  you have stated are left alone.
- **`take_back`**, run by an uninstall, removes the configuration *only if it is byte-for-byte
  what the install wrote*. Any difference — including a key Rundesk does not recognise — makes
  the file yours, and it stays.

## What is not in here

Anything belonging to one agent — its provider, model, instructions, channels, schedules, and
its own granted skills — is that agent's own and is changed through the command:

```sh
rundesk configure ava --provider claude --model opus
```

See [`rundesk configure`](/reference/cli/#rundesk-configure) and
[`rundesk config`](/reference/cli/#rundesk-config).
