---
name: managing-rundesk
description: Use when inspecting, configuring, operating, troubleshooting, or recovering the Rundesk install that owns this agent. It supplies verified commands, workflows, and safety rules for agents, gateways, conversations, channels, schedules, providers, skills, backups, configuration, credentials, and the Rundesk lifecycle. Do not use for ordinary project work or for deciding, performing, or reviewing delegation.
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

## Common entry points

| Priority | Need | Command |
|---|---|---|
| 1 | Prove which install this is and whether it is healthy | `"$RUNDESK_COMMAND" status` |
| 2 | See the agents and their providers | `"$RUNDESK_COMMAND" agents` |
| 3 | See whether gateways are running | `"$RUNDESK_COMMAND" gateways` |
| 4 | Explain gateway trouble | `"$RUNDESK_COMMAND" gateways logs <agent>` |
| 5 | Check provider, channel, and skill readiness | `"$RUNDESK_COMMAND" providers check <provider>` · `"$RUNDESK_COMMAND" channels doctor <agent>` · `"$RUNDESK_COMMAND" skills doctor <agent>` |
| 6 | Protect approved risky work | `"$RUNDESK_COMMAND" backups save` |

Choose the narrowest command that answers the request. Before a mutation, inspect only enough state
to identify the exact target and consequence. Most groups list when called with no subcommand.

## Safety boundaries

- Never open or edit Rundesk databases, conversation records, or lock files directly. If a command
  fails, use documented read-only surfaces or report it; do not bypass the command with file tools.
- Never stop your own gateway. Restarting it is allowed: Rundesk queues the restart until the active
  turn finishes, then brings the gateway back online.
- Require an explicit request for agent removal, schedule removal, backup restore, uninstall, purge,
  or forced gateway shutdown. Name the exact target.
- Run a guarded command without `--confirm` first when it offers a preview. Add `--confirm` only
  after the preview matches the request.
- Save a backup before an approved destructive change. A backup contains the sealed credential store
  and its key, so protect its location as credential-bearing data.
- Never ask for a credential in chat or pass one as an argument. Tell the owner to run
  `"$RUNDESK_COMMAND" env set <NAME>` in their own terminal.
- Prefer diagnosis before restart: inspect status, listings, logs, and the relevant `doctor` or
  `check` command.

## Read only the reference you need

| Area | Read for |
|---|---|
| [Agents](references/agents.md) | Add, describe, reassign, or remove agents |
| [Agent instructions](references/agent-instructions.md) | Design or change persistent agent behavior |
| [Gateways](references/gateways.md) | Start, stop, restart, run, inspect, or recover gateways |
| [Conversations](references/conversations.md) | Ask agents; inspect messages, turns, usage, and failures |
| [Backups](references/backups.md) | Save, locate, move, or restore copies |
| [Schedules](references/schedules.md) | Create timed work and proactive verification check-ins |
| [Channels](references/channels.md) | Connect adapters, access lists, notifications, and diagnosis |
| [Providers](references/providers.md) | Discover, check, or inspect provider execution |
| [Skills](references/skills.md) | Catalogs, grants, profiles, values, and skill diagnosis |
| [Maintenance](references/maintenance.md) | Focused upkeep of this agent's memory, indexes, and home workspace |
| [Retrospective](references/retrospective.md) | Write the bounded usage-cycle diary from evidence and compare prior improvements |
| [Self-improvement](references/self-improvement.md) | Review proven friction, continuity, capability gaps, and skills |
| [Configuration](references/configuration.md) | Status, version, install settings, and secret values |
| [OAuth login](references/oauth-login.md) | Configure an installed provider; connect, select, extend, or recover accounts |
| [Lifecycle](references/lifecycle.md) | Install, update, uninstall, and purge |

Use `"$RUNDESK_COMMAND" <group> --help` when exact help and a reference disagree. Report the command's
answer, including uncertainty or refusal, without translating it into a success it did not earn.
