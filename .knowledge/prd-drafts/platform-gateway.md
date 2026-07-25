---
id: GW
name: The gateway
last_verified: 2026-07-24
---

## What this is

The part of rundesk that stays running. It is started once and then tended by the machine rather than by
a person, and it is the owner of every program rundesk runs while it is up.

## Why it exists

- Agents are reachable without anyone keeping rundesk running by hand.
- The machine coming back brings rundesk back with it.
- What the owner is told about the gateway is what the gateway itself says.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-GW-1 | The gateway keeps running with nobody tending it | — the machine's own supervisor does this, and no job describes one yet |
| ❌ | R-GW-2 | The gateway that falls over is running again without anyone asking | — the machine's own supervisor does this, and no job describes one yet |
| ❌ | R-GW-3 | The gateway is running again after the machine it is on restarts | — the machine's own supervisor does this, and no job describes one yet |
| ✅ | R-GW-4 | Only one gateway runs at a time | `only one gateway of a name runs at a time`, `gateways of different names run alongside each other` |
| ✅ | R-GW-5 | A second gateway asked to start says why it will not, rather than starting | `a second gateway says why it will not start` |
| ✅ | R-GW-6 | The gateway asked to stop refuses further work before it goes | `a gateway that is stopping takes no more work`, `a gateway stops when the machine asks it to` |
| ✅ | R-GW-7 | The gateway asked to stop goes without waiting past the time it is allowed | `stopping does not wait past the time it is allowed` |
| ✅ | R-GW-8 | The gateway going away ends every program it was running (R-PROC-5) | `a gateway going away ends what it was running` |
| ✅ | R-GW-9 | Whether the gateway is running is answered by the gateway itself | `whether a gateway is running is answered by the gateway`, `a gateway never started is reported as not running`, `a record that cannot be read is survived`, `a gateway that stopped going round is told from one that is working` |
| ✅ | R-GW-10 | A gateway the machine believes is running but which is not is reported as not running | `a gateway that was killed is not reported as running` |
| ✅ | R-GW-11 | The gateway refuses to start when what it is made of does not fit the machine | `an install built for another python does not fit`, `a gateway refuses to start when it does not fit`, `an install needing nothing always fits`, `an install that still has one that fits fits` |
| ✅ | R-GW-12 | Stopping the gateway leaves nothing of it behind to be found by the next start | `a gateway asked to stop goes`, `stopping leaves nothing for the next start to find`, `the name a gateway gave back can be taken again` |
| ❌ | R-GW-13 | Every gateway an owner starts, inspects or stops is reached through the command line | — the command line does not reach the gateway yet |
| ✅ | R-GW-14 | The command line manages every gateway running on the machine, not one of them | `every gateway on the machine is listed`, `listing gateways where there are none says so` |
| ✅ | R-GW-15 | The same piece of work never runs twice at once under one gateway | `the same work is refused while it is already running`, `different work runs alongside itself`, `work that finished may be started again`, `work with no name never collides` |

## Open questions

- Whether an owner may ask the gateway to stop without waiting for work in flight to finish.
- Whether a program the gateway was running is started again when it fails, given that repeating a turn
  repeats whatever that turn already did to the machine.
- Whether R-GW-1, R-GW-2 and R-GW-3 assert what the machine's own supervisor does, or only rundesk's half.
