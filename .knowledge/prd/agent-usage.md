---
id: USE
name: What an agent's work cost
last_verified: 2026-07-26
---

## What this is

What every run of an agent cost, taken from what its provider streamed rather than asked for
separately. Tokens are the measurement; money is derived from them and is only ever as good as the
prices it was derived with, so a figure says which of the two it is. Nothing here reaches a provider's
account: how much of a plan is left is that provider's question, not this one's.

## Why it exists

- An owner can see what an agent costs before the bill rather than after it.
- A run that cost nothing and a run whose cost never arrived are told apart.
- A number that was estimated never reads as one that was measured.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-USE-1 | Every run records what it cost in tokens | `every run records what it cost in tokens` |
| ✅ | R-USE-2 | Tokens are recorded as the provider reported them, and not adjusted | `tokens are recorded as the brain reported them` |
| ✅ | R-USE-3 | A provider reporting a conversation's running total has only that turn's share recorded | `a brain reporting a running total reports only this turns share`, `what a brain remembers between turns survives the process` |
| ✅ | R-USE-4 | Tokens written into a provider's cache are recorded apart from tokens read from it | `tokens written into a cache are recorded apart from ones read from it` |
| ❌ | R-USE-5 | A cost in money says whether it was measured, worked out from prices, or unknown | src/rundesk/turn.py:236 — nothing works a cost out from prices, so nothing says which it is |
| ✅ | R-USE-6 | A cost that could not be established is never recorded as nothing | `a run whose usage never arrived says so`, `a turn whose cost was never reported says that rather than nothing` |
| ✅ | R-USE-7 | A run whose usage never arrived says so rather than reporting a cost of nothing | `a run whose usage never arrived says so`, `a turn whose cost was never reported says that rather than nothing`, `a total says how many runs it could not account for`, `an agent that has run nothing has no totals to give` |
| ❌ | R-USE-8 | What anything added to a turn cost is charged to that turn | src/rundesk/turn.py:118 — what is added to a turn is in the prompt the brain counts; no test tells its share apart |
| ✅ | R-USE-9 | What an agent has cost outlives the gateway that recorded it | `what an agent has cost outlives the gateway that recorded it` |
| ✅ | R-USE-10 | What an agent has cost is read without a provider being started | `what an agent has cost is read without a brain being started`, `what an agent has run is listed with what became of each` |
| ❌ | R-USE-11 | Nothing about a provider's plan or remaining allowance is claimed | src/rundesk/turn.py:236 — nothing asks a brain about a plan, so nothing proves it is not asked |
| ✅ | R-USE-12 | What one run cost names the cached input its provider reported, apart from fresh input | `a runs listing shows the cached input a provider reported`, `a run whose provider reported no cache at all claims none` |
| ✅ | R-USE-13 | Tokens written into a provider's cache are recorded apart from fresh input, and are absent where the provider does not report the split | `four billed quantities are reported in four slots`, `a brain that does not report cache writes claims none`, `what one run cost names the cache writes its provider reported`, `a total sums the cache writes that were reported`, `rows written before there was a column for cache writes stay unknown` |
| ✅ | R-USE-14 | A turn's input is the size it ended at, never the same prompt counted once per request | `the input side is where the turn ended not every request added up`, `a subagents own conversation is not where this turn ended`, `what a turn cost is reported once and never added up` |
| ✅ | R-USE-15 | A turn reports how big the conversation it ended on was, as a level and never as a total added across the requests it made | `a turn says how big the conversation it ended on was`, `a turn making several requests reports the level it ended at and not the sum`, `a compacted conversation is reported smaller than the one before it`, `how big the conversation is reaches a surface with what it cost`, `a turn records the final conversation size without adding snapshots` |
| ✅ | R-USE-16 | A turn whose provider reports none of the pieces its prompt is split into reports no conversation size at all | `a brain that reports none of the pieces of a prompt claims no size for the conversation`, `a brain that does not report a conversation size gets the footer it always got` |

## Open questions

- What a turn's share is after a restart loses the running total a provider was reporting against.
- Where prices come from, and what a cost says when the model that ran has no price on record.
- Whether usage belongs beside the run that produced it, beside the agent, or in both.
- Whether a provider that names no model leaves the run's cost attributable at all.
- Whether an owner should be able to stop an agent that has cost too much, and what decides too much.
