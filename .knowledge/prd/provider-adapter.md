---
id: PRV
name: The seam a brain is reached through
last_verified: 2026-07-26
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
| ✅ | R-PRV-1 | An adapter is a program Rundesk runs, never code it loads | `a brain this rundesk has never heard of is the ordinary case`, `a shipped adapter is found by looking rather than by being listed`, `no vendor variable is put in front of an adapter` |
| ✅ | R-PRV-2 | An adapter Rundesk has never heard of carries a whole turn, with nothing here changed | `an adapter this code has never seen carries a whole turn` |
| ✅ | R-PRV-3 | An adapter is told the agent's working directory and its own private home | `an adapter is told where to work and where its own things go`, `what was not asked for is left unset rather than set to nothing`, `a turn works in its own agents workspace`, `a brain is told where its own things would go but given no home` |
| ✅ | R-PRV-4 | An adapter reports what happened as whole records, one to a line | `an adapter carries a whole turn`, `what an adapter reports is whole records one to a line`, `the prompt arrives on the stream meant for it`, `a turn that failed says so rather than going quiet` |
| ✅ | R-PRV-5 | A record of a kind Rundesk does not know is kept rather than refused | `a record of a kind we do not know is kept rather than refused`, `a line that is not a record at all is understood as nothing`, `a record rundesk did not understand is still in the run afterwards`, `a record rundesk did not understand is kept and shown to nobody` |
| ✅ | R-PRV-6 | What an adapter says went wrong is kept apart from what it reports | `what an adapter says went wrong is kept off what it reports`, `what an adapter said went wrong is kept and kept apart`, `what a brain said went wrong is kept and kept out of the account`, `what a brain said went wrong is kept apart from what it reported` |
| ✅ | R-PRV-7 | An adapter that runs no tools reports none, rather than appearing to have run some | `an adapter that runs no tools carries a whole turn`, `an adapter that says it can do nothing is believed` |
| ✅ | R-PRV-8 | An adapter says what a tool did in words no brain owns | `an adapter says what a tool did in words no brain owns` |
| ✅ | R-PRV-9 | An adapter names the model that answered, and none is claimed when it does not | `an adapter naming no model leaves none claimed`, `a brain that names no model leaves none claimed` |
| ✅ | R-PRV-10 | Rundesk never sends a brain anything the run's record does not also show | `anything rundesk added to a turn appears in that turns account`, `what was sent is written down before the brain is started`, `everything said mid turn is in that turns account` |
| ✅ | R-PRV-11 | Ending a turn ends the adapter and everything it started | `ending a turn ends the adapter and everything it started` |
| ✅ | R-PRV-12 | An adapter that cannot run says why before a turn is admitted | `the only failure is nothing runnable being there`, `an adapter that cannot run says why before a turn is admitted`, `an agent that reaches for no brain says so rather than guessing` |
| ❌ | R-PRV-13 | An adapter that stops reporting is ended on silence rather than on a deadline | src/rundesk_cli/turn.py:151 — inherited from what runs a program at all; no test of its own here |
| ✅ | R-PRV-14 | What one adapter does cannot reach another agent's working directory or home | `an adapter works where it is told and not where it pleases`, `a turn works in its own agents workspace` |
| ✅ | R-PRV-15 | An adapter says what it can do before a turn is admitted, and nothing else is assumed of it | `an adapter says what it can do without carrying a turn`, `an adapter that says it can do nothing is believed`, `an adapter that cannot answer the question can do nothing`, `what a brain says it can do is recorded with the run`, `a brain that cannot carry a conversation on is not asked to` |
| ✅ | R-PRV-16 | What an owner set for a brain reaches it unread and unchanged | `what an owner set reaches the brain unread and unchanged`, `what an owner set reaches the brain and is written down` |
| ✅ | R-PRV-17 | An adapter is handed the handle it last reported for that conversation, and never another conversation's | `an adapter is handed back the handle it reported`, `a second turn resumes the conversations session`, `changing the brain does not hand over the other ones session` |
| ✅ | R-PRV-18 | An adapter is told how much of the machine a turn may touch, in words no brain owns | `an adapter is told how much of the machine a turn may touch`, `a turn asked to only look says so to the brain` |
| ✅ | R-PRV-19 | A brain that says it can be sent to mid-turn is, and the turn carries on rather than starting again | `a brain that can be steered hears a word said mid turn`, `a brain that cannot be steered is not left waiting for more`, `an adapter can be steered exactly as much as it said it could` |

## Open questions

- What a turn does when a word said into it arrives after it has already finished.
- What a turn does when an adapter reports a record whose shape is known but whose content is not.
- What happens when what an adapter says it can do and what it then reports disagree.
- Whether an adapter that cannot carry a conversation on should be given one at all.
- How a brain that has drifted from what was last measured is noticed before a turn fails on it.
