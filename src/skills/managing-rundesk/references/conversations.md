# Conversations and turns

Use `ask` to start attended work, `messages` to search what was said, and `turns` to inspect execution,
cost, tool records, and failure details.

## Commands

| Command | Control |
|---|---|
| `ask <agent> <prompt...>` | Ask in that agent's continuing terminal conversation. |
| `ask ... --fresh` | Start a new provider conversation. |
| `ask ... --read-only` | Request inspection without changes. |
| `ask ... --model <model>` | Pass a provider-specific model name. |
| `ask ... --thinking` | Show reasoning events as well as the answer. |
| `ask ... --quiet` | Show only the final answer. |
| `messages <agent> [--search <words>] [--channel <channel>] [--source <kind>] [--conversation <id>] [--since <YYYY-MM-DD>] [--limit <n>] [--full]` | Search message history. Filters compose; limit defaults to 20 and must be at least 1. |
| `turns <agent> [--limit <n>] [--conversation <id>]` | List recent turns and their status and cost. Limit defaults to 20 and must be at least 1. |
| `turns <agent> <turn>` | Show one turn, its request, records, usage, and failure. |

Prefix every command with `"$RUNDESK_COMMAND"`. Quote prompts so the shell passes them as intended.

## Choose the right view

- `messages` answers what the agent was told and said. Its default is intentionally one bounded line
  per message; use `--full` only after narrowing the result.
- `turns` answers what execution did and cost. Inspect one turn when an answer failed, a tool behaved
  unexpectedly, or usage needs explanation.
- Rising `UNKNOWN` means the provider emitted records Rundesk did not understand. Rising `LOST`
  means expected records never arrived. Either indicates adapter/provider drift worth investigating.
- `UNSENT` is not drift. It counts words Rundesk could not deliver into a running turn, usually a
  steer offered after the provider had already finished; those words stay durable for a later turn.
- One turn shows `model asked for` beside `model reported`. A turn recorded before Rundesk kept those
  apart shows a single `model` line saying the value may be either.
- `ask` is the attended caller and can accept steering while a turn runs. Channel and scheduled turns
  are unattended. A busy conversation refuses a second simultaneous turn instead of queuing it.
- `--read-only` is a request sent to the provider, not an operating-system sandbox. Keep task scope
  explicit and review what the turn actually did.
