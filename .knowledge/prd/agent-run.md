---
id: RUN
name: A run, and the account it leaves behind
last_verified: 2026-07-26
---

## What this is

One occurrence of an agent doing work, and the record it writes while doing it. A run has an id of its
own, an account of everything that happened, and — where a conversation continues — the handle its brain
uses to pick that conversation back up. The account is the point: an agent that worked all night is only
worth having if what it did can be read back afterwards.

## Why it exists

- What an agent did is readable long after the gateway that ran it has gone.
- A conversation carries on where it left off, without Rundesk knowing what a session handle means.
- Nothing reaches a brain that the account does not also show.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-RUN-1 | Every run has an id of its own | `every run has an id of its own`, `every run is named once and no name is handed out twice`, `a runs name carries a mark of its own beside the number` |
| ✅ | R-RUN-2 | A run's id is what its account, its cost and its outcome are found by | `a runs account is found by the runs id`, `an agent is made with somewhere to keep what it did` |
| ✅ | R-RUN-3 | What a run resolved is written when it is admitted and never changed after | `what a run resolved is written when it is admitted`, `what a run resolved is never changed after`, `a brain named for one turn is used for that turn only` |
| ✅ | R-RUN-4 | A run's account records every event, in the order it happened | `a runs account records every event in the order it happened`, `a runs account is added to and never rewritten`, `a turn that failed is recorded as one` |
| ✅ | R-RUN-5 | A run's account is added to and never rewritten | `a runs account is added to and never rewritten`, `what a brain said can be thrown away while the account stands` |
| ✅ | R-RUN-6 | Each record carries what its brain reported alongside what Rundesk made of it | `everything a brain said is kept exactly as it said it`, `a record rundesk did not understand is still in the run afterwards` |
| ✅ | R-RUN-7 | The order of a run's account does not depend on a clock | `the order of a runs account does not depend on a clock`, `a runs place in the order does not depend on a clock` |
| ✅ | R-RUN-8 | Two accounts of one conversation read in the order the work happened | `two accounts of one conversation read in the order the work happened`, `runs are read back in the order they were admitted` |
| ✅ | R-RUN-9 | Anything Rundesk adds to a turn appears in that turn's account | `anything rundesk added to a turn appears in that turns account`, `what was sent is written down before the brain is started`, `everything said mid turn is in that turns account` |
| ✅ | R-RUN-10 | A run's account outlives the gateway that wrote it, and lasts as long as the agent (R-AGW-5) | `a runs account outlives the gateway that wrote it`, `where an agent keeps what it did is not where its gateway keeps what it is doing`, `taking an agent away takes what a run did` |
| ✅ | R-RUN-11 | A conversation continues from the handle its brain last reported | `a conversation continues from the handle its brain last reported`, `a second turn resumes the conversations session`, `asking the same agent again carries the conversation on` |
| ✅ | R-RUN-12 | A handle is kept for one conversation and one brain together, never for either alone | `a handle is kept for one conversation and one brain together`, `one brain is never handed another brains session`, `changing the brain does not hand over the other ones session`, `two conversations of one brain are carried on separately` |
| ❌ | R-RUN-13 | A brain's own session files are referenced rather than copied | src/rundesk/store.py — a handle is a string in a row and nothing copies what it names, so nothing proves it is not copied |
| ✅ | R-RUN-14 | Losing what a conversation was continuing costs the next turn its context and nothing else | `losing what a conversation was continuing costs the next turn its context`, `a conversation can be started fresh for one brain or for all of them`, `a turn asked to start fresh carries nothing on`, `asking for a fresh start carries nothing on` |
| ❌ | R-RUN-15 | No credential a brain was given appears in a run's account | src/rundesk/turn.py:118 — nothing puts one there; no test |
| ✅ | R-RUN-16 | A run says what admitted it, and it is one of the declared ways work is admitted | `every way work is admitted is named here`, `work admitted from somewhere nobody declared is refused`, `a run refused for its source is not written at all`, `a turn the clock started says so in the account` |

## Open questions

- How long an account is kept, and whether an owner or a size decides.
- Whether an account records what a brain was sent, or only what it reported back.
- What is read back when a brain's own session files are gone but our account remains.
- Whether a run interrupted by a restart is one run continued or two runs recorded.
- Where an account lives when the work was for no conversation at all.
