---
id: AGW
name: An agent, and the one gateway it runs in
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
| ❌ | R-AGW-1 | Making an agent makes the one gateway that runs it | — |
| ❌ | R-AGW-2 | Taking an agent away takes away the gateway that ran it | — |
| ❌ | R-AGW-3 | Every channel an agent is reachable on is held open by the gateway that runs it | — |
| ❌ | R-AGW-4 | Taking an agent away takes the schedules and channels that were its own | — |
| ❌ | R-AGW-5 | Taking an agent away keeps the account of what it did until a removal is asked for that too | — |
| ❌ | R-AGW-6 | Starting an agent starts the gateway that runs it | — |
| ❌ | R-AGW-7 | Stopping an agent stops the gateway that runs it | — |
| ❌ | R-AGW-8 | An agent is reported as running exactly when the gateway that runs it is | — |

## Open questions

- What becomes of the gateway that exists today under no agent's name, once every gateway has one.
- Whether running a gateway in this terminal stays a gateway verb, or becomes the agent's like the rest.
- Whether an agent whose gateway will not start is reported as the agent failing or as the gateway.
