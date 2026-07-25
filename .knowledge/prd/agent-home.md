---
id: AGT
name: An agent, and the home it loads from
last_verified: 2026-07-25
---

## What this is

An agent is a named identity rundesk runs work for, and its home is the directory holding the rules,
memory, workspace and skills it loads. Two agents are separate in what each discovers, how each is
configured, what each remembers, and where each works by default — but not by the operating system, so a
provider's own tools still reach whatever their owner reaches.

## Why it exists

- An owner runs several agents on one machine without one of them finding another's rules or history.
- What an owner writes for an agent outlives updating and removing rundesk itself.
- An agent that cannot do work says why before a provider is ever started.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-AGT-1 | Every agent has a name that is its own on a machine | `an agent is named by the one who made it`, `two agents never stand in one place` |
| ✅ | R-AGT-2 | An agent has a home holding the knowledge it loads | `an agent is made with the files it loads`, `what an agent loads holds nothing rundesk keeps`, `what a home holds is what there is a template for`, `a template is copied with the agents own name in it`, `the file every provider loads names the ones none of them do`, `what an agent loads is reached by being told rather than by a link`, `an agent is only one that has a home` |
| ✅ | R-AGT-3 | An agent's home outlives the copy of rundesk that created it | `removing rundesk keeps every agents home`, `purging takes every agents home as well` |
| ✅ | R-AGT-4 | Creating an agent that already exists leaves the knowledge edited in its home unchanged | `making an agent again leaves what was written in it`, `making an agent again puts back only what is missing`, `making an agent that exists leaves its home alone` |
| ✅ | R-AGT-5 | A name that would reach outside where agents are kept is refused | `a name that is a path is refused`, `a name that is no name at all is refused`, `a name standing on a link out of where agents are kept is refused`, `a name that cannot be an agents is refused before anything is made` |
| ✅ | R-AGT-6 | A name a gateway would take for something it wrote is refused | `a name a gateway would take for something it wrote is refused`, `a name that merely has a dot in it is still a name`, `what a gateway writes is asked of it rather than listed` |
| ✅ | R-AGT-7 | No two agents resolve to one workspace | `no two agents resolve to one workspace`, `two agents never stand in one place` |
| ✅ | R-AGT-8 | No two agents share the private home a provider is given | `no two agents share the private home a provider is given`, `one agent keeps two providers apart`, `the private home a provider is given stands outside what the agent loads` |
| ✅ | R-AGT-9 | An agent the machine keeps running resolves the home the command that made it resolved | `the job carries the directories it was given rather than its own`, `a verb asks where the agent it names keeps things`, `where an agent keeps things is its own`, `nothing is adopted while a gateway of that name is running`, `what a stopped gateway wrote is adopted once it lets the name go` |
| ❌ | R-AGT-10 | An agent loads what stands in its own home rather than what its owner keeps | — |
| ✅ | R-AGT-11 | An agent is diagnosed without a provider being started | `an agent that has everything is diagnosed with nothing`, `an agent missing what it loads says which file`, `an agent that was never made is said to be missing`, `an agent that cannot be written to says so`, `an install that does not fit stands between an agent and a turn`, `an install with nothing to make an agent from says so`, `an agent with nothing wrong is ready`, `an agent with something wrong says what and fails`, `diagnosing with no name asks after every agent`, `diagnosing where there are no agents says so`, `asking after an agent that is not there says so` |
| ✅ | R-AGT-12 | Diagnosing an agent changes nothing about it | `diagnosing an agent changes nothing about it`, `diagnosing an agent that is not there changes nothing` |
| ✅ | R-AGT-13 | A name that has no agent is reached where it always was | `a name with no agent keeps things where it always did`, `a name with no agent is asked after where it always was` |
| ✅ | R-AGT-14 | Every place an agent resolves is readable without opening the source | `one agent says every place it resolves` |

## Open questions

- Which of an agent's files each provider is proven to *load*, rather than merely to find. Probes of the
  build this replaces found that only the two named after a provider are picked up where they stand, that
  one of them expands an import and none follows a link, and that a bare skills directory is discovered by
  nobody. None of it is re-proven against the versions installed now, which is what R-AGT-10 waits on.
- Whether agents share the owner's provider sign-in or each holds its own. Redirecting a provider's home
  isolated its credentials too in that build, so two agents needed two sign-ins — a cost worth stating
  before it is chosen rather than discovered.
- Whether what a run recorded belongs with the agent or with the gateway that admitted it.
- Where rundesk's own account of itself stands, now that everything else belongs to an agent.
