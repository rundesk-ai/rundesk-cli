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
| `gateways restart <agent> [--force]` | Stop and start one gateway. |
| `gateways restart --all [--force]` | Restart every gateway. |
| `gateways logs <agent> [-n <lines>]` | Read gateway and supervisor logs; default is 20 lines. |
| `gateways run <agent>` | Run the gateway in the current terminal instead of as a login job. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Diagnose before cycling

1. Run `status`, `gateways`, and `gateways logs <agent> -n 100`.
2. Run `channels doctor <agent>`, `skills doctor <agent>`, and `providers check <provider>` when the
   log points at one of those seams.
3. Start a stopped gateway. Restart only when the process is running but unhealthy.
4. Use `--force` only when an ordinary stop cannot finish. It kills in-flight work where it stands.

## State and recovery

- Never stop your own gateway. Restarting it is allowed: Rundesk queues the restart until the active
  turn finishes, then brings the gateway back online under supervision.
- A placed launchd job, a running process, and a healthy gateway are distinct states. Trust the
  listing's words; do not reduce them to one boolean.
- `start` earns success only after the process proves it is up. Read the failure and logs if it does
  not.
- `run` is useful for an agent whose name cannot be a launchd label or for attended diagnosis. It
  occupies the terminal until stopped and is not a second gateway beside a running job.
- `run` is the launchd entry point and may exit `0` after a deliberate refusal so launchd does not
  thrash. For diagnosis, trust its words and gateway state as well as the code.
- Normal stop allows work to finish. If it refuses because a turn or schedule is active, wait or
  inspect that work with `turns`; forced stop may leave the work failed but must not leave the
  gateway permanently locked out of starting.
