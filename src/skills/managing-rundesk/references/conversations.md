# Conversations, search, and turns

Use `ask` to start attended work, `messages` to search what this agent was told and said, `search` to
ask the platforms it is connected to what anybody said there, and `turns` to inspect execution, cost,
tool records, and failure details.

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
| `search <agent> <words...>` | Search every platform this agent has a channel on. |
| `search ... --channel <channel>` | Only that channel. |
| `search ... --place <id>` | Only that room or private conversation, using an id a result printed. |
| `search ... --from <id>` | Only messages that sender said. |
| `search ... --since <YYYY-MM-DD> --until <YYYY-MM-DD>` | Only that window of days. |
| `search ... --limit <n>` | How many each channel answers with. Defaults to 20, at most 100. |
| `search ... --full` | Whole messages with links, instead of one line each. |
| `search <agent> --fetch <ref> --channel <channel>` | Bring one result's attachments onto this machine. |
| `turns <agent> [--limit <n>] [--conversation <id>]` | List recent turns and their status and cost. Limit defaults to 20 and must be at least 1. |
| `turns <agent> <turn>` | Show one turn, its request, records, usage, and failure. |

Prefix every command with `"$RUNDESK_COMMAND"`. Quote prompts so the shell passes them as intended.

## Choose the right view

- `messages` answers what the agent was told and said. Its default is intentionally one bounded line
  per message; use `--full` only after narrowing the result.
- `search` answers what was said on the platform, by anybody, whether the agent was there or not. It
  is the same shape on every platform, so there is nothing per-platform to learn, and an agent with
  no channels has no search.
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

## Read a search answer correctly

Search has four answers and three of them look similar. Read the count line before the rows.

| It printed | It means |
|---|---|
| `3 found on <channel>` | it looked everywhere it was asked to and found these |
| `nothing found on <channel>` | it looked everywhere it was asked to and matched nothing |
| `nothing found yet` or `N found so far`, with a `NOT THE WHOLE ANSWER` line | **it stopped before it had finished** |
| a reason on stderr, and a non-zero exit | it could not look at all |

**Never read `NOT THE WHOLE ANSWER` as an absence.** A search that ran out of budget and a search
that found nothing print the same empty table, and the warning line is the only thing that tells
them apart. When you see it, narrow the search — a place, a sender, a window of days — and ask again
rather than concluding the thing was never discussed.

The exit code says whether anything was looked through, not whether anything was found.

## What a search can and cannot see

A search sees what this agent's **bot** was admitted to: rooms it was invited to and private
conversations it is part of. It does not see a person's own private messages with other people, or
rooms the bot was never invited to. Say that plainly when it matters to an answer rather than
reporting an absence of results as an absence of conversation.

Results are handed back and never written into the agent's records. Narrowing a question over several
searches leaves nothing behind, so search as often as the question needs.

## Bring in a file a search found

Each result prints a `REF`. Pass it back with the channel that found it:

```sh
"$RUNDESK_COMMAND" search ava --fetch 'C0OPS/1725026531.000200' --channel slack
```

The files land under that channel's dated incoming directory, exactly where a file somebody sent the
agent would have landed, and the command prints each path. Fetch only what the answer needs — this
downloads, where the search only read.
