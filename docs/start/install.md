---
title: Install
description: Install Rundesk with one command. It lives under ~/.rundesk and never edits your shell profile.
sidebar:
  order: 2
---

```sh
curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash
```

That installs the newest **published release** — not whatever is on the branch — and puts
the `rundesk` command on your `PATH` without editing your shell profile.

## Where things go

```text
~/.rundesk/
  app/          the installed Rundesk release
  data/         your agents, skills, scripts, history, and configuration
```

The split is the point. `app/` is Rundesk's; `data/` is yours.

- **Updates** replace `app/` and leave `data/` alone.
- **Uninstall** leaves `data/` alone unless you explicitly ask to purge it.
- **Removing an agent** preserves its home unless you explicitly ask to purge it.

## Check it answers

```sh
rundesk doctor
```

`doctor` runs the diagnostics that catch a broken install before it becomes an unattended
failure at three in the morning.

## Updates

Rundesk updates itself daily, defaulting to 03:00 in the machine's local time. To choose
another time, set it in `~/.rundesk/data/config.json` and apply the schedule:

```json
{"updates": {"at": "02:30"}}
```

```sh
rundesk update
```

When an update needs to migrate agent records, Rundesk first stops every gateway and keeps a
rollback copy of each database. If any migration fails it restores every agent's records and
keeps the previous release in place — a failed update leaves you where you started, not
half-way.

## Uninstall

```sh
curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash -s -- --uninstall
```

Add `--purge` to remove `data/` as well. Without it, your agents, history, and configuration
survive the uninstall and are picked up again by a later install.

Next: [create your first agent](/start/first-agent/).
