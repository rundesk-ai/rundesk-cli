---
id: SCH
name: Work that starts itself
last_verified: 2026-07-25
---

## What this is

Work rundesk begins because the time came, rather than because someone asked. A schedule says when, and
names what to start; what that turns out to be is not the schedule's concern. Schedules belong to one
gateway each, which is how one agent's schedules stay that agent's alone.

## Why it exists

- Things that should happen regularly happen without anyone remembering them.
- A schedule that could not run is never mistaken for one that did.
- What is scheduled, when it next runs, and what became of it last time are all visible at once.
- One agent's schedules are its own, and no other agent's to run or to change.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-SCH-1 | A schedule states when it runs in the way schedules are ordinarily stated | `a schedule is stated the way schedules are ordinarily stated`, `a schedule says lists ranges and steps`, `a day of the week is counted from sunday`, `a day and a weekday together mean either one`, `a schedule nobody can understand says so` |
| ✅ | R-SCH-2 | A schedule that is due starts what it names | `a schedule that is due starts what it names`, `only what is due is due`, `a schedule naming nothing to run is never added` |
| ✅ | R-SCH-3 | What a schedule names is carried to whatever starts it, and never read on the way | `what a schedule names is carried and never read`, `a schedule naming nothing this gateway can start is reported` |
| ✅ | R-SCH-4 | A schedule whose time passed while nothing was running is not run late | `a time that passed while nothing ran is not run late` |
| ✅ | R-SCH-5 | A schedule whose time passed while nothing was running is reported as having been passed | `what was passed over can still be counted`, `a very long absence is counted up to a point and no further` |
| ✅ | R-SCH-6 | A schedule does not begin again while what it started last time is still running | `a schedule does not begin again while the last is still running` |
| ✅ | R-SCH-7 | A schedule refused for still running is reported rather than passed over | `a schedule does not begin again while the last is still running` |
| ✅ | R-SCH-8 | Every schedule reports when it next runs, when it last ran, and what became of that | `the next time is the next one after now`, `the next time is never the moment asked about`, `the next time of a weekly schedule is found`, `a schedule that can never run says never`, `schedules are listed with when each next runs`, `changing a schedule that is not there says so` |
| ✅ | R-SCH-9 | A schedule runs once for the time it is due, however often the time is examined | `a schedule runs once for the minute it is due` |
| ✅ | R-SCH-10 | A schedule that cannot be understood leaves every other schedule running | `one schedule nobody can understand leaves the others running`, `something that is not a schedule at all is refused by itself`, `a schedule nobody can understand is reported and the others run`, `nothing written down is no schedules rather than a failure` |
| ✅ | R-SCH-11 | A schedule that is turned off is kept and reported, and does not run | `a schedule that is off does not run`, `a schedule that is off says so rather than a time`, `a schedule that is off is kept and shown as off`, `a schedule is turned off and on again without being lost` |
| ✅ | R-SCH-12 | Deciding what is due asks nothing of the machine beyond the time | `deciding what is due asks nothing of the machine`, `a rare schedule is found without examining every minute` |
| ✅ | R-SCH-13 | A schedule runs only in the gateway whose schedules it is among | `a gateway runs only its own schedules`, `schedules are asked for and changed on one gateway only` |
| ✅ | R-SCH-14 | A gateway never runs, reports or alters another gateway's schedules | `a gateway runs only its own schedules`, `schedules are asked for and changed on one gateway only` |

## Open questions

- Whether the time a schedule is stated in is ever anything other than the machine's own.
