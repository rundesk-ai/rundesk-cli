---
id: AGW
name: An agent, and the one gateway it runs in
last_verified: 2026-07-25
---

## What this is

Every agent runs in one gateway of its own, made when the agent is made and taken away when the agent
is. Everything that reaches that agent runs inside it: the channels it answers on are held open there,
and the schedules that are its own fire there. So the agent is what a person operates, and the gateway
is how it runs rather than a second thing to keep.

## Why it exists

- No command leaves an agent with nothing running it, or something running nothing.
- Starting and stopping are said of the agent, so nobody has to know a gateway is there at all.
- Removing an agent does not leave work behind that its name would inherit if it came back.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-AGW-1 | Making an agent makes the one gateway that runs it | `making an agent makes the gateway that runs it`, `a gateway keeps what it is doing where its agent does`, `making an agent makes it and says where it stands` |
| ✅ | R-AGW-2 | Taking an agent away takes away the gateway that ran it | `taking an agent away takes the gateway that ran it`, `removing a gateway takes its job and what was kept for it` |
| ❌ | R-AGW-3 | Every channel an agent is reachable on is held open by the gateway that runs it | — |
| ✅ | R-AGW-4 | Taking an agent away takes the schedules that were its own | `taking an agent away takes the schedules that were its own` |
| ✅ | R-AGW-5 | Taking an agent away takes the account of what it did, and leaves nothing of its records behind | `taking an agent away takes the account of what it did`, `taking an agent away takes what its schedules did`, `taking an agent away takes what a run did`, `nothing of an agents records is left behind`, `removing an agent takes the account of what it did`, `removing an agent offers no flag that would change what goes` |
| ✅ | R-AGW-6 | Starting an agent starts the gateway that runs it | `starting hands it over and reports the gateway that resulted`, `start here runs it in this terminal`, `start here hands nothing to the machine`, `the verb a job already on disk invokes still runs it` |
| ✅ | R-AGW-7 | Stopping an agent stops the gateway that runs it | `stopping a named gateway stops that one`, `stopping every agent at once is asked for out loud`, `stopping without saying which stops nothing` |
| ✅ | R-AGW-8 | An agent is reported as running exactly when the gateway that runs it is | `agents lists them with what each is doing`, `one agent says every place it resolves` |
| ❌ | R-AGW-9 | Taking an agent away takes the channels that were its own | — |
| ✅ | R-AGW-10 | A gateway that has no agent is listed rather than left out | `a gateway with no agent is listed and marked` |
| ✅ | R-AGW-11 | A gateway that has no agent is given one only when its owner asks | `adopting a gateway moves what it wrote into the agents own`, `adopting a gateway brings what its log rotated into along`, `adopting a gateway that wrote nothing moves nothing`, `adopting a gateway that has no agent brings what it wrote in`, `a gateway that is still running is not adopted` |

## Open questions

- Whether an agent whose gateway will not start is reported as the agent failing or as the gateway.
- Whether a schedule run by hand should one day run inside the agent's gateway rather than in the terminal
  that asked for it, which would need a way to ask a running gateway for something.
- What a gateway that has no agent should do after long enough — nothing takes one away on its own today,
  and nothing says how long is long enough.
