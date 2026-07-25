---
id: AGT
name: An agent, and the home it loads from
---

## What this is

An agent is a named identity rundesk runs work for, and its home is the directory holding the rules,
memory, workspace and skills it loads. One agent runs in one gateway, made with it and taken away with
it, and everything that reaches that agent runs inside it. Two agents are separate in what each
discovers, how each is configured, what each remembers, and where each works by default — but not by
the operating system, so a provider's own tools still reach whatever their owner reaches.

## Why it exists

- An owner runs several agents on one machine without one of them finding another's rules or history.
- What an owner writes for an agent outlives updating and removing rundesk itself.
- An owner operates agents, and never has to keep track of what each one runs inside.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-AGT-1 | Every agent has a name that is its own on a machine | — |
| ❌ | R-AGT-2 | An agent has a home holding the knowledge it loads | — |
| ❌ | R-AGT-3 | An agent's home outlives the copy of rundesk that created it | — |
| ❌ | R-AGT-4 | Creating an agent that already exists leaves the knowledge edited in its home unchanged | — |
| ❌ | R-AGT-5 | A name that would reach outside where agents are kept is refused | — |
| ❌ | R-AGT-6 | A name a gateway would take for something it wrote is refused | — |
| ❌ | R-AGT-7 | No two agents resolve to one workspace | — |
| ❌ | R-AGT-8 | No two agents share the private home a provider is given | — |
| ❌ | R-AGT-9 | An agent the machine keeps running resolves the home the command that made it resolved | — |
| ❌ | R-AGT-10 | An agent loads what stands in its own home rather than what its owner keeps | — |
| ❌ | R-AGT-11 | An agent is diagnosed without a provider being started | — |
| ❌ | R-AGT-12 | Diagnosing an agent changes nothing about it | — |
| ❌ | R-AGT-13 | Making an agent makes the one gateway that runs it | — |
| ❌ | R-AGT-14 | Taking an agent away takes away the gateway that ran it | — |
| ❌ | R-AGT-15 | Every channel an agent is reachable on is held open by the gateway that runs it | — |

## Open questions

- Where an agent's home stands, relative to this copy of rundesk and to what a gateway writes beside it.
- Whether agents share the owner's provider sign-in or each holds its own.
- Which of an agent's files each provider is proven to load, rather than merely to find.
- Whether what a run recorded belongs with the agent or with the gateway that admitted it.
- Which contract owns keeping an agent's home through a removal — this one, or the one removal owns.
- What becomes of the gateway that exists today under no agent's name, once every gateway has one.
- Whether a gateway can be stood down while its agent stays, or whether standing one down is the agent's.
