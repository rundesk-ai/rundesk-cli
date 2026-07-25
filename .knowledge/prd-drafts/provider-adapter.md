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

An adapter answers two questions: what it can do, and one turn. Both are asked of the adapter rather
than worked out from its name, so a brain that runs no tools, keeps no conversation or reports no cost
is a whole brain with that work absent, rather than a broken one.

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
| ❌ | R-PRV-15 | An adapter says what it can do before a turn is admitted, and nothing else is assumed of it | — |
| ❌ | R-PRV-16 | What an owner set for a brain reaches it unread and unchanged | — |
| ❌ | R-PRV-17 | An adapter is handed the handle it last reported for that conversation, and never another conversation's | — |
| ❌ | R-PRV-18 | An adapter is told how much of the machine a turn may touch, in words no brain owns | — |

## Open questions

- What a turn does when an adapter reports a record whose shape is known but whose content is not.
- What happens when what an adapter says it can do and what it then reports disagree.
- Whether an adapter that cannot carry a conversation on should be given one at all.
- Whether being sent to mid-turn belongs in this seam, and what would prove a brain supports it.
- How a brain that has drifted from what was last measured is noticed before a turn fails on it.
