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
| ❌ | R-USE-5 | A cost in money says whether it was measured, worked out from prices, or unknown | src/rundesk_cli/turn.py:236 — nothing works a cost out from prices, so nothing says which it is |
| ✅ | R-USE-6 | A cost that could not be established is never recorded as nothing | `a run whose usage never arrived says so`, `a turn whose cost was never reported says that rather than nothing` |
| ✅ | R-USE-7 | A run whose usage never arrived says so rather than reporting a cost of nothing | `a run whose usage never arrived says so`, `a turn whose cost was never reported says that rather than nothing` |
| ❌ | R-USE-8 | What anything added to a turn cost is charged to that turn | src/rundesk_cli/turn.py:118 — what is added to a turn is in the prompt the brain counts; no test tells its share apart |
| ✅ | R-USE-9 | What an agent has cost outlives the gateway that recorded it | `what an agent has cost outlives the gateway that recorded it` |
| ✅ | R-USE-10 | What an agent has cost is read without a provider being started | `what an agent has cost is read without a brain being started` |
| ❌ | R-USE-11 | Nothing about a provider's plan or remaining allowance is claimed | src/rundesk_cli/turn.py:236 — nothing asks a brain about a plan, so nothing proves it is not asked |

## Open questions

- What a turn's share is after a restart loses the running total a provider was reporting against.
- Where prices come from, and what a cost says when the model that ran has no price on record.
- Whether usage belongs beside the run that produced it, beside the agent, or in both.
- Whether a provider that names no model leaves the run's cost attributable at all.
- Whether an owner should be able to stop an agent that has cost too much, and what decides too much.
