# Gateways

A gateway is the supervised background process hosting one agent's channels, schedules, and turns.
One agent has one launchd job and one gateway.

## Commands

| Command | Control |
|---|---|
| `gateways` or `gateways list` | List every agent's gateway, job, and observed state. |
| `gateways start <agent>` | Place and start the job, then prove the gateway came up. |
| `gateways stop <agent> [--force]` | Ask one gateway to finish and remove its job. |
| `gateways stop --all [--force]` | Stop every gateway in this install. |
| `gateways restart <agent> [--force] [--continue]` | Refuse active work, then stop and start one gateway; `--continue` is the safe active-turn self-restart form and cannot combine with `--force`. |
| `gateways restart --all [--force]` | Atomically refuse if any gateway has active or unreadable work; otherwise restart every gateway. |
| `gateways logs <agent> [-n <lines>]` | Read gateway and supervisor logs; default is 20 lines. |
| `gateways run <agent>` | Run the gateway in the current terminal instead of as a login job. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Diagnose before cycling

1. Run `status`, `gateways`, and `gateways logs <agent> -n 100`.
2. Run `channels doctor <agent>`, `skills doctor <agent>`, and `providers check <provider>` when the
   log points at one of those seams.
3. Start a stopped gateway. Restart only when the process is running but unhealthy.
4. Wait when a normal restart reports active work. Use `--force` only when intentionally taking
   that work away because an ordinary stop cannot finish.

## State and recovery

- Never stop your own gateway. Restarting it is allowed: Rundesk queues the restart until the active
  turn finishes, then brings the gateway back online under supervision.
- From an active channel turn, `restart <self> --continue` durably requests one continuation after
  the replacement pid, running version, and exact origin channel are healthy. It refuses another
  agent, `--all`, `--force`, terminal/ambiguous callers, and unsupervised gateways. It resumes the
  exact provider session when safe and otherwise wakes a fresh session in the same conversation.
- A placed launchd job, a running process, and a healthy gateway are distinct states. Trust the
  listing's words; do not reduce them to one boolean.
- `start` earns success only after the process proves it is up. Read the failure and logs if it does
  not.
- `run` is useful for an agent whose name cannot be a launchd label or for attended diagnosis. It
  occupies the terminal until stopped and is not a second gateway beside a running job.
- `run` is the launchd entry point and may exit `0` after a deliberate refusal so launchd does not
  thrash. For diagnosis, trust its words and gateway state as well as the code.
- Normal restart refuses while a selected gateway has an active turn or schedule, and `--all`
  refuses before stopping any gateway. Wait or inspect the work with `turns`; forced restart may
  leave it failed.
- Normal stop asks active work to settle within the gateway shutdown window. It is an explicit
  cancellation and does not promise that work completes.
