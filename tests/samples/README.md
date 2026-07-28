# samples/ — what a brain really said, captured once

Real output from real CLIs, driven against real accounts. **It cost money to produce and it cannot
be re-derived by reading anything** — which is why it is committed rather than regenerated, and why
a test that drives it needs no account, no token and no network.

Carried over from the Node build (`../../../rundesk/probes/samples/`, `src/contracts/`), which
drove all three CLIs on 2026-07-24. What each fact is true *of* is the whole point:

| | version |
|---|---|
| `cli-versions.lock` | the exact builds every file here was captured against — `claude 2.1.219`, `codex-cli 0.144.6`, `grok 0.2.111`, `agy 1.1.8` |

## The golden streams

| | |
|---|---|
| `claude-stream.jsonl` | 184 lines. Sixteen distinct line kinds, a `result` line carrying 302,567 cache reads against 20 fresh tokens, whole `tool_use`/`tool_result` pairs, and thinking and signature deltas. |
| `grok-stream.jsonl` | 79 lines, and only three kinds — `thought`, `text`, `end`. **No tool events at all**, which is the finding rather than a gap in the capture. |
| `antigravity-stream.jsonl` | 9 sanitized lines from a real 1.1.8 turn: `init`, streamed reply fragments, paired tool steps, per-step usage, and terminal `result`. Paths, ids and tool output were replaced while event structure and numeric relationships were retained. |

## The mapping decisions

`claude-events.json`, `grok-events.json` and `codex-events.json` record, line kind by line kind,
what each maps to **and the reason one is dropped**. Those reasons are the expensive part:

- Claude sends its reply **twice** — as `text_delta` fragments and again whole on the `assistant`
  line. Reading both double-counts every answer.
- Claude's `message_start` and `message_delta` each carry a full `usage` block. Counting them as
  well as the `result` line double-counts the cost.
- Claude reports `cache_creation_input_tokens` separately from `cache_read_input_tokens` because
  creation is billed above input. Summing them gives a number that is real and misleading.
- Codex's `turn.completed.usage` is the running total for the **whole thread**, not the turn.
  Claude's and Grok's are per turn. That is why the adapters converge on a split rather than
  copying whichever field is nearest.
- Antigravity's `result.usage` is per turn when fresh but a running conversation total after
  `--conversation`; summing the new invocation's `step_update.usage` blocks yields the turn.
- Antigravity repeats streamed reply text in `result.response`; the adapter uses the terminal
  copy only when no delta arrived.

## Using them

A capture is a fixture, not a claim about today. When a CLI version moves, re-drive it, compare,
and write what changed into a dated note in [`../../.knowledge/research/`](../../.knowledge/research/)
— then update `cli-versions.lock` in the same change, or nothing here says what it is true of any
more.
