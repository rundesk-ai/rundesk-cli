---
id: STO
name: What an agent keeps
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
| ❌ | R-STO-1 | What an agent keeps is read without starting a gateway, a brain or the agent | src/rundesk_cli/store.py:317 — no test |
| ❌ | R-STO-2 | What one agent keeps is never in the way of what another agent keeps | src/rundesk_cli/store.py:21 — no test |
| ❌ | R-STO-3 | Reading what an agent keeps never delays work that agent is doing | src/rundesk_cli/store.py:341 — no test |
| ❌ | R-STO-4 | Two commands changing one agent's records at once cannot lose one another's change | src/rundesk_cli/store.py:356 — no test |
| ❌ | R-STO-5 | A run's account is added to and never rewritten | src/rundesk_cli/store.py:806 — no test |
| ❌ | R-STO-6 | The order of a run's account does not depend on a clock | src/rundesk_cli/store.py:806 — no test |
| ❌ | R-STO-7 | A line a brain produced that nobody understood is kept rather than dropped | src/rundesk_cli/store.py:806 — no test |
| ❌ | R-STO-8 | Nothing a run recorded is recoverable only from a file that may be destroyed | src/rundesk_cli/store.py:26 — no test |
| ❌ | R-STO-9 | What a run cost is recorded as absent rather than as nothing when it never arrived | src/rundesk_cli/store.py:768 — no test |
| ❌ | R-STO-10 | A session is kept for one conversation and one brain together, never for either alone | src/rundesk_cli/store.py:601 — no test |
| ❌ | R-STO-11 | Work arriving twice from one surface is recorded once | src/rundesk_cli/store.py:646 — no test |
| ❌ | R-STO-12 | What was said is found by the words in it, whichever surface it arrived on | src/rundesk_cli/store.py:697 — no test |
| ❌ | R-STO-13 | Searching where the machine cannot is reported as unavailable rather than as nothing found | src/rundesk_cli/store.py:697 — no test |
| ❌ | R-STO-14 | A conversation says which surface it happened on and what it branched from | src/rundesk_cli/store.py:566 — no test |
| ❌ | R-STO-15 | Every run says what caused it | src/rundesk_cli/store.py:735 — no test |
| ❌ | R-STO-16 | What an agent keeps says which shape it is in | src/rundesk_cli/store.py:277 — no test |
| ❌ | R-STO-17 | A shape this copy of rundesk does not understand is refused rather than read | src/rundesk_cli/store.py:277 — no test |
| ❌ | R-STO-18 | Records that are there and cannot be understood are never treated as absent | src/rundesk_cli/store.py:277 — no test |
| ❌ | R-STO-19 | Taking an agent away leaves nothing of what it kept behind | src/rundesk_cli/store.py:836 — no test |
| ❌ | R-STO-20 | A name a caller asks by is the only way what an agent keeps is reached | src/rundesk_cli/store.py:14 — no test |

## Open questions

- How long an account is kept, and whether an owner or a size decides.
- Whether removing one schedule takes the runs it produced or leaves them as history.
- Whether a run that started no brain at all, such as a scheduled program, is recorded as a run.
- Whether the private home a brain is given belongs to the same lifetime as what an agent keeps.
- Whether a conversation may ever span two surfaces, and what joining two of them would mean.
- Whether what a brain printed is deleted on a schedule, on a size, or only when asked.
