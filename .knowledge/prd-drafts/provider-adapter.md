---
id: PRV
name: The seam a brain is reached through
---

## What this is

An adapter is a program that runs a brain and reports what it did in words Rundesk understands. Rundesk
starts it, gives it the agent's working directory and private home, reads whole records from it, and
ends it — it never loads an adapter's code, and never runs a conversation itself. That the adapter is a
program rather than a plugin is the whole point: it can be written in anything, and a brain nobody here
has heard of is reached by the same seam as a shipped one.

## Why it exists

- An owner can put their own brain, or their own conversational loop, behind any agent.
- The loop that moves fastest stays the vendor's to maintain, and never becomes ours.
- What a brain reports is the same handful of things whichever brain it was.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-PRV-1 | An adapter is a program Rundesk runs, never code it loads | — |
| ❌ | R-PRV-2 | An adapter Rundesk has never heard of carries a whole turn, with nothing here changed | — |
| ❌ | R-PRV-3 | An adapter is told the agent's working directory and its own private home | — |
| ❌ | R-PRV-4 | An adapter reports what happened as whole records, one to a line | — |
| ❌ | R-PRV-5 | A record of a kind Rundesk does not know is kept rather than refused | — |
| ❌ | R-PRV-6 | What an adapter says went wrong is kept apart from what it reports | — |
| ❌ | R-PRV-7 | An adapter that runs no tools reports none, rather than appearing to have run some | — |
| ❌ | R-PRV-8 | An adapter says what a tool did in words no brain owns | — |
| ❌ | R-PRV-9 | An adapter names the model that answered, and none is claimed when it does not | — |
| ❌ | R-PRV-10 | Rundesk never sends a brain anything the run's record does not also show | — |
| ❌ | R-PRV-11 | Ending a turn ends the adapter and everything it started | — |
| ❌ | R-PRV-12 | An adapter that cannot run says why before a turn is admitted | — |
| ❌ | R-PRV-13 | An adapter that stops reporting is ended on silence rather than on a deadline | — |
| ❌ | R-PRV-14 | What one adapter does cannot reach another agent's working directory or home | — |

## Open questions

- Whether an adapter is told how much of the machine it may touch, or is left to its own posture.
- What a turn does when an adapter reports a record whose shape is known but whose content is not.
- Whether continuing an earlier conversation is the adapter's to arrange or Rundesk's to ask for.
- Whether a shipped adapter and a stranger's are held to the same suite, or the stranger's to less.
- Where an adapter that is not on the machine is reported — by `doctor`, at admission, or both.
