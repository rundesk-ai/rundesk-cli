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
| ✅ | R-GW-1 | The gateway keeps running with nobody tending it | `the job runs the command this install placed`, `the machine is told to start it at load and keep it up`, `handing a gateway over writes the job and asks the machine to take it`, `a machine with nothing to hand it to says so` |
| ✅ | R-GW-2 | The gateway that falls over is running again without anyone asking | `the machine is told to start it at load and keep it up`, `a gateway that ended well is not started again` |
| ✅ | R-GW-3 | The gateway is running again after the machine it is on restarts | `the machine is told to start it at load and keep it up` |
| ✅ | R-GW-4 | Only one gateway of a given name runs at a time | `only one gateway of a name runs at a time`, `gateways of different names run alongside each other`, `a gateway claiming its own name twice is not a clash`, `one gateway stopping leaves the others running`, `a name is not left held by a claim that did not finish`, `giving back a name never removes the lock itself`, `a gateway that never claimed cannot give the name away`, `shutting down a gateway that never claimed touches nothing` |
| ✅ | R-GW-5 | A second gateway asked to start says why it will not, rather than starting | `a second gateway says why it will not start`, `a refused gateway refuses promptly rather than waiting` |
| ✅ | R-GW-6 | The gateway asked to stop refuses further work before it goes | `a gateway that is stopping takes no more work`, `a gateway stops when the machine asks it to`, `asking a gateway to stop both refuses work and ends the waiting` |
| ✅ | R-GW-7 | The gateway asked to stop goes without waiting past the time it is allowed | `stopping does not wait past the time it is allowed` |
| ✅ | R-GW-8 | The gateway going away ends every program it was running (R-PROC-5) | `a gateway going away ends what it was running`, `being asked to stop twice does not kill it mid shutdown`, `one gateway ending its work leaves another gateways work alone` |
| ✅ | R-GW-9 | Whether the gateway is running is answered by the gateway itself | `whether a gateway is running is answered by the gateway`, `a gateway never started is reported as not running`, `a record that cannot be read is survived`, `a lock that cannot be opened is not read as running`, `a record that is not about a gateway at all is survived`, `a running gateway keeps saying it is still going round`, `a gateway that stopped going round is told from one that is working`, `whether it is going round survives the clock being changed`, `status tells a wedged gateway from a working one`, `status says what each gateway has in flight` |
| ✅ | R-GW-10 | A gateway the machine believes is running but which is not is reported as not running | `a gateway that was killed is not reported as running` |
| ✅ | R-GW-11 | The gateway refuses to start when what it is made of does not fit the machine | `an install built for another python does not fit`, `a gateway refuses to start when it does not fit`, `an install needing nothing always fits`, `an install that still has one that fits fits` |
| ✅ | R-GW-12 | Stopping the gateway leaves nothing of it behind to be found by the next start | `a gateway asked to stop goes`, `stopping leaves nothing for the next start to find`, `the name a gateway gave back can be taken again`, `it is beside the install rather than inside the source`, `where it keeps things can be said`, `work unwinding after the gateway has gone does not rewrite the record` |
| ✅ | R-GW-13 | Every gateway an owner starts, inspects or stops is reached through the command line | `serving runs the gateway of the name given`, `starting hands it over and reports the gateway that resulted`, `starting says so when no gateway results`, `starting a gateway that is already running changes nothing`, `stopping a named gateway stops that one`, `cycling a gateway stops it and starts it again`, `only our jobs are listed`, `someone elses job is never removed`, `someone elses job is never stopped or started`, `someone elses job is never handed to the machine as ours`, `handing over a name belonging to something else is refused`, `a machine that refuses without explaining is still reported`, `cycling waits for the old one to actually go`, `cycling says so rather than starting one that never stopped`, `the machine is never waited on without a bound`, `a machine that does not answer in time is given up on` |
| ✅ | R-GW-14 | Every gateway on the machine is found without knowing its name beforehand | `every gateway on the machine is listed`, `listing gateways where there are none says so`, `stopping without a name stops every gateway`, `status says which gateways are up` |
| ✅ | R-GW-15 | The same piece of work never runs twice at once under one gateway | `the same work is refused while it is already running`, `different work runs alongside itself`, `work that finished may be started again`, `work with no name never collides`, `the same work name under two gateways is two pieces of work` |
| ✅ | R-GW-16 | A gateway ends whatever the last gateway of its name left running | `taking a name ends what the last gateway of it was running`, `a leftover that ignores the polite signal is ended anyway`, `what is in flight is written down as it happens`, `work recorded by a gateway that has since gone is left alone`, `taking a name nobody left anything under is ordinary`, `a record saying nothing about work is survived`, `going with work still running leaves the record naming it` |
| ✅ | R-GW-17 | The gateway says so when it goes with work it could not end | `stopping does not wait past the time it is allowed` |
| ✅ | R-GW-19 | A gateway leaves alone anything it cannot show the last gateway of its name left running | `a number that now belongs to something else is left alone`, `a record that cannot prove what it left is left alone`, `a record that does not say what was running is left alone`, `when the machine cannot say when a process started`, `when a process started is answered for one that exists` |
| ✅ | R-GW-20 | A gateway name that would reach outside the directory it belongs in is refused | `a name that would escape its directory is refused`, `nothing builds a path from a name that would escape`, `no job is written for a name that would escape` |
| ✅ | R-GW-21 | Work left by a gateway whose name nobody takes up again is still ended | `starting any gateway ends work left under a name nobody uses`, `a record with nothing left running is not kept forever`, `a running gateways work is never swept by another` |
| ❌ | R-GW-22 | Work interrupted by the gateway restarting is taken up where it stopped, not begun again | — nothing records where a piece of work had got to |
| ❌ | R-GW-23 | Work in flight when a gateway goes is answered for rather than dropped in silence | — nothing tells anyone that work was interrupted |
| ❌ | R-GW-24 | Work that keeps taking the gateway down with it is stopped rather than taken up again | — nothing is taken up again yet, so nothing can do so repeatedly |
| ✅ | R-GW-25 | A gateway refusing to run ends in a way that does not have the machine start it again | `a gateway that refuses to run ends well`, `a gateway that ended well is not started again`, `a gateway that cannot start is not started as fast as the machine can` |
| ✅ | R-GW-18 | What a gateway wrote about what happened outlives the gateway | `what a gateway wrote outlives the gateway`, `a gateway records coming up and going down`, `work that ended badly is recorded with its last words`, `a gateway that refused to start says why in writing`, `what it writes goes beside the run directory by default`, `a log that cannot be read is reported rather than crashing`, `what was swept from a dead gateway is recorded`, `work that was refused as a duplicate is recorded`, `a gateway that cannot say it is alive writes that down and carries on` |

## Open questions

- Whether an owner may ask the gateway to stop without waiting for work in flight to finish.
- Whether a program the gateway was running is started again when it fails, given that repeating a turn
  repeats whatever that turn already did to the machine.
- How often a gateway may be started before rundesk treats starting it as the fault, rather than
  whatever it is starting for.
- R-GW-1, R-GW-2 and R-GW-3 are proven as rundesk's half — the job says what the machine must do.
  What the machine then actually does is the machine's, and is not asserted here.
