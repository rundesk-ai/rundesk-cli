---
name: managing-rundesk
description: Operate, inspect, or troubleshoot the Rundesk install running this agent. Use for agents, gateways, conversations, backups, schedules, channels, providers, skills, configuration, credentials, updates, paths, or anything on this machine that Rundesk may control.
---

# Manage Rundesk

Use Rundesk's commands to answer questions about this install. Do not guess at its state or paths.

## Use the right install

Run `"$RUNDESK_COMMAND"`, never bare `rundesk`. It is the absolute command for the install running
this turn. `$RUNDESK_HOME` already points to that install; do not change it or introduce another
location.

```sh
"$RUNDESK_COMMAND" status
"$RUNDESK_COMMAND" --help
```

Treat generated help as authoritative. If a verb is absent, Rundesk cannot perform it. A command
exits `0` when it answered or completed, `1` when understood but not completed, and `2` for invalid
command syntax. Never report success from wording alone; read the exit code and result.

## Start with the essentials

| Priority | Need | Command |
|---|---|---|
| 1 | Prove which install this is and whether it is healthy | `"$RUNDESK_COMMAND" status` |
| 2 | See the agents and their providers | `"$RUNDESK_COMMAND" agents` |
| 3 | See whether gateways are running | `"$RUNDESK_COMMAND" gateways` |
| 4 | Explain gateway trouble | `"$RUNDESK_COMMAND" gateways logs <agent>` |
| 5 | Ask an agent from this terminal | `"$RUNDESK_COMMAND" ask <agent> '<prompt>'` |
| 6 | Check provider, channel, and skill readiness | `"$RUNDESK_COMMAND" providers check <provider>` · `"$RUNDESK_COMMAND" channels doctor <agent>` · `"$RUNDESK_COMMAND" skills doctor <agent>` |
| 7 | Protect approved risky work | `"$RUNDESK_COMMAND" backups save` |

Use listing commands before mutations. Most groups list when called with no subcommand. Their output
also identifies the root or records being inspected.

## Safety boundaries

- Never stop your own gateway. Restarting it is allowed: Rundesk queues the restart until the active
  turn finishes, then brings the gateway back online.
- Require an explicit request for agent removal, schedule removal, backup restore, uninstall, purge,
  or forced gateway shutdown. Name the exact target.
- Run a guarded command without `--confirm` first when it offers a preview. Add `--confirm` only
  after the preview matches the request.
- Save a backup before an approved destructive change. A backup excludes credentials, so it cannot
  recover a lost secret.
- Never ask for a credential in chat or pass one as an argument. Tell the owner to run
  `"$RUNDESK_COMMAND" env set <NAME>` in their own terminal.
- Prefer diagnosis before restart: inspect status, listings, logs, and the relevant `doctor` or
  `check` command.

## Read only the reference you need

| Area | Read for |
|---|---|
| [Agents](references/agents.md) | Add, describe, reassign, or remove agents |
| [Gateways](references/gateways.md) | Start, stop, restart, run, inspect, or recover gateways |
| [Conversations](references/conversations.md) | Ask agents; inspect messages, turns, usage, and failures |
| [Backups](references/backups.md) | Save, locate, move, or restore copies |
| [Schedules](references/schedules.md) | Create and control timed programs or agent prompts |
| [Channels](references/channels.md) | Connect adapters, access lists, notifications, and diagnosis |
| [Providers](references/providers.md) | Discover, check, or inspect provider execution |
| [Skills](references/skills.md) | Catalogs, grants, profiles, values, and skill diagnosis |
| [Configuration](references/configuration.md) | Status, version, install settings, and secret values |
| [Lifecycle](references/lifecycle.md) | Install, update, uninstall, and purge |

## Write or publish a skill

Use [Writing skills](../writing-skills/SKILL.md) to create, revise, review, debug, or publish one.

- Read its [integration guidance](../writing-skills/references/integrations.md) only when a skill
  needs values or external commands.
- Read its [publishing guidance](../writing-skills/references/publishing.md) only when other installs
  must be able to install the skill.

Use `"$RUNDESK_COMMAND" <group> --help` when exact help and a reference disagree. Report the command's
answer, including uncertainty or refusal, without translating it into a success it did not earn.
