---
title: What an agent can reach
description: The boundaries Rundesk actually enforces, the environment it builds for a provider, and the ones it does not pretend to enforce.
sidebar:
  order: 5
---

Rundesk runs coding agents on your own machine, unattended, and reachable from chat. That is
worth being precise about. This page says what Rundesk enforces and — just as importantly —
what it does not.

## The honest summary

**An agent has whatever access its provider CLI has.** Rundesk does not sandbox a brain, and
it is not a security boundary between a coding agent and your filesystem. Codex, Claude Code,
Grok, and Antigravity each have their own approval and permission model; Rundesk runs them
and records what happened.

What Rundesk does own is narrower and worth knowing exactly:

- who is allowed to send an agent work
- what environment the provider is started in
- whether a given turn is allowed to change anything
- where credentials live, and where they do not

## Nothing leaves the machine

No Rundesk server exists and none is contacted to answer a turn. Everything — agent homes,
conversations, records, usage, configuration — is on your disk under `~/.rundesk`.

The only outbound requests Rundesk itself makes are the update check against the release
feed, and whatever the provider CLI does on its own account.

## The environment a provider is given

The environment is **built, not inherited** (`R-PROC-1`). A gateway does not hand a program
the variables it was started with; it hands it exactly this:

| Variable | Set to |
|---|---|
| `HOME` | Your home directory |
| `PATH` | The integration command library, then the inherited `PATH` |
| `TERM` | `dumb` — nobody is watching, so providers should not render as if somebody is |
| `LANG` | `en_US.UTF-8` |
| `RUNDESK_HOME` | The agent's own home |
| `RUNDESK_SCRIPTS` | The shared integration command directory |
| `RUNDESK_SKILL_LIBRARY` | The shared skill library |

Anything not on that list is a thing Rundesk has decided its programs do not see. A gateway
holds credentials for every channel an agent is on, and it does not pass them to every
program it starts.

Two consequences:

- **`HOME` is your real home.** The agent is not chrooted. It can read what you can read.
- **A scheduled program must be given by full path.** A bare name is refused, because a
  gateway runs with almost none of the `PATH` your shell has.

## Credentials

Rundesk does not copy, store, or proxy provider credentials. A provider adapter uses the
login already established on your machine — a keychain entry, or that CLI's own config
directory — under that provider's rules.

Channel credentials are different, because Rundesk has to hold them to connect. A bot token
is read from standard input rather than from your shell history:

```sh
rundesk channels ava add discord --kind discord --allow <your-user-id> --token-stdin
```

Left out, `--token-stdin` is asked for at the terminal. The command **proves the connection
before saving anything**, so a token that does not work does not get written down.

## Who may talk to an agent

Access control is Rundesk's, not the platform's. Every channel carries an explicit allowlist
and **at least one `--allow` is always required** — there is no "add a channel and sort out
who can use it later".

```sh
rundesk channels ava show discord-dms
```

Two behaviours worth knowing:

- **Direct messages and rooms are separate channels** with separate allowlists and separate
  instructions, so an agent can be told to behave differently where other people are reading.
- **A shared channel cannot change the agent's brain.** `/provider` works on a single-user
  channel only. One person in a room should not be able to re-brain a teammate everybody else
  is using.

## Read-only turns

A turn runs in one of two postures, and Rundesk translates the posture into each provider's
native controls — so `--read-only` means the same thing to Codex and to Claude Code even
though they express it differently:

```sh
rundesk ask ava --read-only "what looks risky in this repository?"
```

This is a real constraint passed to the provider, not a prompt asking it nicely. It is still
the provider that enforces it.

## What a record contains

Every turn is recorded: the messages both ways, tool activity, the outcome or the error, and
token usage. That record is on your disk and is not sent anywhere.

It does mean a conversation containing something sensitive is written down. `rundesk backups`
copies it, and a backup is an ordinary directory — treat it the way you would treat any copy
of your shell history.

## Uninstalling

Removing Rundesk leaves `data/` alone unless you ask for `--purge`. Agents, history, and
configuration survive, and a later install picks them up again.

Caches created by installing dependencies — under `~/.cache`, `~/Library/Caches` — are not
Rundesk's and are not removed. What an uninstall takes is what Rundesk is made of.
