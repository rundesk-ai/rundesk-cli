---
id: STO
name: What an agent keeps
last_verified: 2026-07-26
---

## What this is

Everything one agent keeps that outlives the moment: what it is configured to do, and what it
has done. Each agent keeps its own, so nothing one agent holds is ever in another's way.

## Why it exists

- What an agent was told and what it answered can be read back long afterwards, and searched.
- One agent is restartable, movable and removable without disturbing any other.
- What a run recorded survives losing everything a brain itself printed.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-STO-1 | What an agent keeps is read without starting a gateway, a brain or the agent | `what an agent falls back to round trips` |
| ✅ | R-STO-2 | What one agent keeps is never in the way of what another agent keeps | `one agent writing never makes another agent wait` |
| ✅ | R-STO-3 | Reading what an agent keeps never delays work that agent is doing | `a question is answered while a turn holds the write lock` |
| ✅ | R-STO-4 | Two commands changing one agent's records at once cannot lose one another's change | `two writers at once cannot lose one anothers work` |
| ✅ | R-STO-5 | A run's account is added to and never rewritten | `a runs account is added to and never rewritten` |
| ✅ | R-STO-6 | The order of a run's account does not depend on a clock | `a runs account is read back in the order the work happened` |
| ✅ | R-STO-7 | A line a brain produced that nobody understood is kept rather than dropped | `a line rundesk did not understand is kept with what it actually said` |
| ✅ | R-STO-8 | Nothing a run recorded is recoverable only from a file that may be destroyed | `what a brain printed going costs the account nothing` |
| ✅ | R-STO-9 | What a run cost is recorded as absent rather than as nothing when it never arrived | `a run whose cost never arrived is left absent rather than written as nothing` |
| ✅ | R-STO-10 | A session is kept for one conversation and one brain together, never for either alone | `one brain is never handed another brains session` |
| ✅ | R-STO-11 | Work arriving twice from one surface is recorded once | `a channel reconnecting cannot record one message twice` |
| ✅ | R-STO-12 | What was said is found by the words in it, whichever surface it arrived on | `a word is found wherever it was said and whoever said it` |
| ✅ | R-STO-13 | Searching where the machine cannot is reported as unavailable rather than as nothing found | `a machine that cannot search says so rather than answering nothing` |
| ✅ | R-STO-14 | A conversation says which surface it happened on and what it branched from | `a thread is a conversation of its own that knows what it came from` |
| ✅ | R-STO-15 | Every run says what caused it | `everything settled when a run was admitted is written down with it` |
| ✅ | R-STO-16 | What an agent keeps says which shape it is in | `a fresh database is stamped with the shape this rundesk understands` |
| ✅ | R-STO-17 | A shape this copy of rundesk does not understand is refused rather than read | `a version newer than this code understands is refused rather than read` |
| ✅ | R-STO-18 | Records that are there and cannot be understood are never treated as absent | `a database holding tables and no version is unreadable rather than rebuilt` |
| ✅ | R-STO-19 | Taking an agent away leaves nothing of what it kept behind | `nothing of an agents records is left behind` |
| ✅ | R-STO-20 | What an agent keeps is reached only by asking for it by name | `no statement is written anywhere but the one module` |
| ✅ | R-STO-21 | Nothing a caller is handed can be used to ask a question of its own | `nothing a caller is handed is a connection` |
| ✅ | R-STO-22 | A run is named once, and no name is handed out twice | `every run is named once and no name is handed out twice` |
| ✅ | R-STO-23 | An agent is whole again from what it keeps, with everything raw beside it gone | `an agent is whole again from its records alone` |
| ❌ | R-STO-24 | What an agent's owner wrote is theirs, and is never reproduced from what rundesk keeps | — |

## Open questions

- How long an account is kept, and whether an owner or a size decides.
- Whether removing one schedule takes the runs it produced or leaves them as history.
- Whether a run that started no brain at all, such as a scheduled program, is recorded as a run.
- Whether the private home a brain is given belongs to the same lifetime as what an agent keeps.
- Whether a conversation may ever span two surfaces, and what joining two of them would mean.
- Whether what a brain printed is deleted on a schedule, on a size, or only when asked.
- What an agent has cost reads as nothing rather than as absent when it has run nothing at all.
