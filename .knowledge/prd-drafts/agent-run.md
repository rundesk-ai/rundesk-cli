---
id: RUN
name: A run, and the account it leaves behind
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
| ❌ | R-RUN-1 | Every run has an id of its own | — |
| ❌ | R-RUN-2 | A run's id is what its account, its cost and its outcome are found by | — |
| ❌ | R-RUN-3 | What a run resolved is written when it is admitted and never changed after | — |
| ❌ | R-RUN-4 | A run's account records every event, in the order it happened | — |
| ❌ | R-RUN-5 | A run's account is added to and never rewritten | — |
| ❌ | R-RUN-6 | Each record carries what its brain reported alongside what Rundesk made of it | — |
| ❌ | R-RUN-7 | The order of a run's account does not depend on a clock | — |
| ❌ | R-RUN-8 | Two accounts of one conversation read in the order the work happened | — |
| ❌ | R-RUN-9 | Anything Rundesk adds to a turn appears in that turn's account | — |
| ❌ | R-RUN-10 | A run's account outlives the gateway that wrote it | — |
| ❌ | R-RUN-11 | A conversation continues from the handle its brain last reported | — |
| ❌ | R-RUN-12 | A handle is kept for one conversation and one brain together, never for either alone | — |
| ❌ | R-RUN-13 | A brain's own session files are referenced rather than copied | — |
| ❌ | R-RUN-14 | Losing what a conversation was continuing costs the next turn its context and nothing else | — |
| ❌ | R-RUN-15 | No credential a brain was given appears in a run's account | — |

## Open questions

- How long an account is kept, and whether an owner or a size decides.
- Whether an account records what a brain was sent, or only what it reported back.
- What is read back when a brain's own session files are gone but our account remains.
- Whether a run interrupted by a restart is one run continued or two runs recorded.
- Where an account lives when the work was for no conversation at all.
