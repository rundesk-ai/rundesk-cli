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
- An agent is whole again from what it keeps, whatever was destroyed beside it.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-STO-1 | What an agent keeps is read without starting a gateway, a brain or the agent | `what an agent falls back to round trips` |
| ✅ | R-STO-2 | What one agent keeps is never in the way of what another agent keeps | `one agent writing never makes another agent wait` |
| ✅ | R-STO-3 | Reading what an agent keeps never delays work that agent is doing | `a question is answered while a turn holds the write lock` |
| ✅ | R-STO-4 | Two commands changing one agent's records at once cannot lose one another's change | `two writers at once cannot lose one anothers work` |
| ✅ | R-STO-5 | Nothing a run recorded is recoverable only from a file that may be destroyed (R-RUN-5, R-RUN-6) | `what a brain printed going costs the account nothing` |
| ✅ | R-STO-6 | Work arriving twice from one surface is recorded once | `a channel reconnecting cannot record one message twice` |
| ✅ | R-STO-7 | What was said is found by the words in it, whichever surface it arrived on | `a word is found wherever it was said and whoever said it` |
| ✅ | R-STO-8 | Searching where the machine cannot is reported as unavailable rather than as nothing found | `a machine that cannot search says so rather than answering nothing` |
| ✅ | R-STO-9 | A conversation says which surface it happened on and what it branched from | `a thread is a conversation of its own that knows what it came from` |
| ✅ | R-STO-10 | Every run says what caused it | `everything settled when a run was admitted is written down with it` |
| ✅ | R-STO-11 | What an agent keeps says which shape it is in | `a fresh database is stamped with the shape this rundesk understands` |
| ✅ | R-STO-12 | A shape this copy of rundesk does not understand is refused rather than read | `a version newer than this code understands is refused rather than read` |
| ✅ | R-STO-13 | Records that are there and cannot be understood are never treated as absent | `a database holding tables and no version is unreadable rather than rebuilt`, `diagnosing an agent never builds the records it reads` |
| ✅ | R-STO-14 | Taking an agent away leaves nothing of what it kept behind | `nothing of an agents records is left behind` |
| ✅ | R-STO-15 | What an agent keeps is reached only by asking for it by name | `no statement is written anywhere but the one module` |
| ✅ | R-STO-16 | Nothing a caller is handed can be used to ask a question of its own | `nothing a caller is handed is a connection` |
| ✅ | R-STO-17 | A run is named once, and no name is handed out twice | `every run is named once and no name is handed out twice` |
| ✅ | R-STO-18 | An agent is whole again from what it keeps, with everything raw beside it gone | `an agent is whole again from its records alone` |
| ❌ | R-STO-19 | What an agent's owner wrote is theirs, and is never reproduced from what rundesk keeps | — |
| ✅ | R-STO-20 | Records this rundesk refuses to read say why in the agent's own log | `records this rundesk will not read say why in the log` |
| ✅ | R-STO-21 | A write that gave up waiting says what was holding it | `a write that gave up waiting says what was holding it` |
| ✅ | R-STO-22 | Something the machine cannot do is said once rather than on every attempt | `a machine that cannot search says so once rather than every time` |
| ✅ | R-STO-23 | An ordinary read or write is not written to the agent's log | `an ordinary read and write says nothing at all` |
| ✅ | R-STO-24 | A run that failed says why, where the run is read | `a run that failed says why beside the run and not only in a file`, `a run that finished well says nothing about why` |

## Open questions

- How long an account is kept, and whether an owner or a size decides.
- Whether removing one schedule takes the runs it produced or leaves them as history.
- Whether a run that started no brain at all, such as a scheduled program, is recorded as a run.
- Whether the private home a brain is given belongs to the same lifetime as what an agent keeps.
- Whether a conversation may ever span two surfaces, and what joining two of them would mean.
- Whether what a brain printed is deleted on a schedule, on a size, or only when asked.
- What an agent has cost reads as nothing rather than as absent when it has run nothing at all.
- Whether a channel can be turned off and left in place, the way a schedule can. What is kept
  has somewhere to say so, and no command offers it.
- Whether what a person calls a conversation is worth keeping, given no surface reports one yet.
- When a run is ever taken away on its own, rather than with the agent that ran it.
