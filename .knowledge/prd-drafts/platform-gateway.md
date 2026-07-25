---
id: GW
name: The gateway
last_verified: 2026-07-25
---

## What this is

A part of rundesk that stays running, named, and tended by the machine rather than by a person. It owns
every program rundesk runs while it is up, and there is one of each name so that any one of them can be
cycled without disturbing the rest.

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
| ✅ | R-GW-4 | Only one gateway of a given name runs at a time | `only one gateway of a name runs at a time`, `gateways of different names run alongside each other`, `a gateway claiming its own name twice is not a clash`, `one gateway stopping leaves the others running`, `a name is not left held by a claim that did not finish`, `giving back a name never removes the lock itself`, `a gateway that never claimed cannot give the name away`, `shutting down a gateway that never claimed touches nothing` |
| ✅ | R-GW-5 | A second gateway asked to start says why it will not, rather than starting | `a second gateway says why it will not start`, `a refused gateway refuses promptly rather than waiting` |
| ✅ | R-GW-6 | The gateway asked to stop refuses further work before it goes | `a gateway that is stopping takes no more work`, `a gateway stops when the machine asks it to`, `asking a gateway to stop both refuses work and ends the waiting` |
| ✅ | R-GW-7 | The gateway asked to stop goes without waiting past the time it is allowed | `stopping does not wait past the time it is allowed` |
| ✅ | R-GW-8 | The gateway going away ends every program it was running (R-PROC-5) | `a gateway going away ends what it was running`, `being asked to stop twice does not kill it mid shutdown`, `one gateway ending its work leaves another gateways work alone` |
| ✅ | R-GW-9 | Whether the gateway is running is answered by the gateway itself | `whether a gateway is running is answered by the gateway`, `a gateway never started is reported as not running`, `a record that cannot be read is survived`, `a record that is not about a gateway at all is survived`, `a running gateway keeps saying it is still going round`, `a gateway that stopped going round is told from one that is working` |
| ✅ | R-GW-10 | A gateway the machine believes is running but which is not is reported as not running | `a gateway that was killed is not reported as running` |
| ✅ | R-GW-11 | The gateway refuses to start when what it is made of does not fit the machine | `an install built for another python does not fit`, `a gateway refuses to start when it does not fit`, `an install needing nothing always fits`, `an install that still has one that fits fits` |
| ✅ | R-GW-12 | Stopping the gateway leaves nothing of it behind to be found by the next start | `a gateway asked to stop goes`, `stopping leaves nothing for the next start to find`, `the name a gateway gave back can be taken again`, `it is beside the install rather than inside the source`, `where it keeps things can be said`, `work unwinding after the gateway has gone does not rewrite the record` |
| ❌ | R-GW-13 | Every gateway an owner starts, inspects or stops is reached through the command line | — the command line does not reach the gateway yet |
| ✅ | R-GW-14 | Every gateway on the machine is found without knowing its name beforehand | `every gateway on the machine is listed`, `listing gateways where there are none says so` |
| ✅ | R-GW-15 | The same piece of work never runs twice at once under one gateway | `the same work is refused while it is already running`, `different work runs alongside itself`, `work that finished may be started again`, `work with no name never collides`, `the same work name under two gateways is two pieces of work` |
| ✅ | R-GW-16 | A gateway ends whatever the last gateway of its name left running | `taking a name ends what the last gateway of it was running`, `what is in flight is written down as it happens`, `work recorded by a gateway that has since gone is left alone`, `taking a name nobody left anything under is ordinary`, `a record saying nothing about work is survived`, `going with work still running leaves the record naming it` |
| ✅ | R-GW-17 | The gateway says so when it goes with work it could not end | `stopping does not wait past the time it is allowed` |
| ✅ | R-GW-19 | A gateway leaves alone anything it cannot show the last gateway of its name left running | `a number that now belongs to something else is left alone`, `a record that cannot prove what it left is left alone`, `when a process started is answered for one that exists` |
| ✅ | R-GW-20 | A gateway name that would reach outside the directory it belongs in is refused | `a name that would escape its directory is refused` |
| ✅ | R-GW-18 | What a gateway wrote about what happened outlives the gateway | `what a gateway wrote outlives the gateway`, `a gateway records coming up and going down`, `work that ended badly is recorded with its last words`, `a gateway that refused to start says why in writing`, `what was swept from a dead gateway is recorded`, `work that was refused as a duplicate is recorded`, `a gateway that cannot say it is alive writes that down and carries on` |

## Open questions

- Whether an owner may ask the gateway to stop without waiting for work in flight to finish.
- Whether a program the gateway was running is started again when it fails, given that repeating a turn
  repeats whatever that turn already did to the machine.
- A gateway whose name is never taken again is never swept, so what it left running is never ended by
  anyone. Finding those needs a pass over the whole machine, which is more than this is worth today.
- Whether R-GW-1, R-GW-2 and R-GW-3 assert what the machine's own supervisor does, or only rundesk's half.
