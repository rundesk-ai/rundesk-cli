---
id: CAD
name: The seam a surface is reached through
---

## What this is

A channel adapter is a program that speaks one messaging platform and reports what arrives in words no
platform owns. Rundesk holds it open inside the agent's gateway, hands it what a turn is doing, and ends
it — it never loads an adapter's code, and it never lets a platform's vocabulary past the seam. Discord
is the first one and is first-class; a second is one more program rather than a change here.

## Why it exists

- An owner can reach an agent from whatever they already use, including something nobody here wrote.
- A surface with almost nothing — no reactions, no typing, no edits — still carries a whole turn.
- What a turn is doing is decided once, so two surfaces can never disagree about it.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-CAD-1 | A channel adapter is a program Rundesk runs, never code it loads | — |
| ❌ | R-CAD-2 | A channel adapter Rundesk has never heard of carries a whole conversation | — |
| ❌ | R-CAD-3 | Rundesk decides whether a turn is taken up, running, finished, stopped or failed | — |
| ❌ | R-CAD-4 | An adapter is told how a turn stands, and decides only how its platform shows it | — |
| ❌ | R-CAD-5 | A surface that cannot show something still carries the turn through to an answer | — |
| ❌ | R-CAD-6 | An agent's channels are held open by the gateway that runs it | — |
| ❌ | R-CAD-7 | A channel that drops its connection returns without a turn noticing | — |
| ❌ | R-CAD-8 | An agent that is not running is reported as out of reach rather than silently missing what arrives | — |
| ❌ | R-CAD-9 | Adding a channel proves it can connect before anything about it is written down | — |
| ❌ | R-CAD-10 | A channel that nobody is allowed to use is refused rather than defaulted | — |
| ❌ | R-CAD-11 | A credential a channel needs is read from where the owner keeps it, never from a command | — |
| ❌ | R-CAD-12 | What shows a channel says a credential is present rather than what it is | — |
| ❌ | R-CAD-13 | No word belonging to one platform appears outside the adapter that speaks it | — |
| ❌ | R-CAD-14 | An adapter decides the shape of what Rundesk keeps for it, and Rundesk reads none of it | — |

## Open questions

- Whether an adapter is told which of its abilities Rundesk will use, the way a brain is asked.
- Whether one agent may be reached on two surfaces at once, and what that does to a conversation.
- Whether a surface may refuse a turn outright, and what an owner sees when it does.
- Where an adapter that is not on the machine is reported — by `doctor`, at setup, or both.
