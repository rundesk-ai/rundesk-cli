# Schedules

A schedule belongs to one agent and starts either a program or an agent prompt when local time is
due. The gateway is the clock that fires it.

## Commands

| Command | Control |
|---|---|
| `schedules` or `schedules list [<agent>]` | List every schedule or one agent's. |
| `schedules add <agent> <schedule> (--when <cron> | --at <moment>) (--run <program> | --ask <prompt>) [--until <moment>] [--disabled]` | Create repeating or one-time work. |
| `schedules update <agent> <schedule> [--when <cron> | --at <moment>] [--run <program> | --ask <prompt>] [--until <moment>] [--enable | --disable]` | Change stated fields and keep execution history. |
| `schedules show <agent> <schedule>` | Show the complete definition and state. |
| `schedules run <agent> <schedule> [--wait <seconds>]` | Run now in this terminal; default wait is 3600 seconds. |
| `schedules remove <agent> <schedule>` | Remove the schedule. This has no confirmation preview. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Time and execution rules

- `--when` is five-field cron: `minute hour day month weekday`. `--at` is
  `YYYY-MM-DDTHH:MM`. Both use the machine's local clock; timezone suffixes and `Z` are refused.
- Use exactly one of `--when` or `--at`, and exactly one of `--run` or `--ask`.
- `--until` is the local moment after which the schedule never runs again.
- `--run` takes one quoted string, splits it into program arguments, and never invokes a shell. It
  does not expand variables, globs, pipes, redirects, `&&`, or `;`. Name an executable program.
- `--ask` uses a schedule-specific conversation, separate from the conversation used by `ask`.

## Operate and recover

1. Add disabled when rollout needs inspection, then `show` and `run` it manually.
2. Manual `run` takes the same durable claim as the gateway and refuses a duplicate. It records the
   result but does not consume or shift the next due time.
3. Enable only after the manual result is correct and the gateway is running.
4. Inspect `show`, `gateways logs <agent>`, and `turns <agent>` for failures.

Rundesk durably claims work before starting it and does not replay every minute missed while a
gateway was down. Disable a schedule to retain its definition without future firings. Because
`remove` acts immediately, verify agent and schedule names first and save a backup when the history
matters.
