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
| ✅ | R-SCH-1 | A schedule states when it runs in the way schedules are ordinarily stated | `a schedule is stated the way schedules are ordinarily stated`, `a schedule says lists ranges and steps`, `a day of the week is counted from sunday`, `whether a field was narrowed is what was written not what it adds up to`, `a day and a weekday together mean either one`, `a schedule nobody can understand says so`, `a schedule naming a program rather than locating it is never added` |
| ✅ | R-SCH-2 | A schedule that is due starts what it names | `a schedule that is due starts what it names`, `only what is due is due`, `a schedule naming nothing to run is never added` |
| ✅ | R-SCH-3 | What a schedule names is carried to whatever starts it, and never read on the way | `what a schedule names is carried and never read`, `a schedule naming nothing this gateway can start is reported`, `a turn can be given standing instructions from the command` |
| ✅ | R-SCH-4 | A schedule whose time passed while nothing was running is not run late | `a time that passed while nothing ran is not run late` |
| ✅ | R-SCH-5 | A schedule whose time passed while nothing was running is reported as having been passed | `what was passed over can still be counted`, `a very long absence is counted up to a point and no further`, `what fell due while nothing ran is said`, `what fell due is said after an ordinary stop and not only a crash`, `being up leaves something a later gateway can measure against` |
| ✅ | R-SCH-6 | A schedule does not begin again while what it started last time is still running | `a schedule does not begin again while the last is still running` |
| ✅ | R-SCH-7 | A schedule refused for still running is reported rather than passed over | `a schedule does not begin again while the last is still running` |
| ✅ | R-SCH-8 | Every schedule reports when it next runs, when it last ran, and what became of that | `the next time is the next one after now`, `the next time is never the moment asked about`, `the next time of a weekly schedule is found`, `a schedule that can never run says never`, `schedules are listed with when each next runs`, `changing a schedule that is not there says so`, `a day that only comes round every few years is still found`, `what each schedule last did survives a restart`, `a schedule that cannot be started says so where it can be read` |
| ✅ | R-SCH-9 | A schedule runs once for the time it is due, however often the time is examined | `a schedule runs once for the minute it is due`, `a clock stepping backwards does not run a schedule again`, `a schedule that already ran this minute does not run again after a restart`, `that a schedule fired is written down before it is run`, `a gateway coming straight back does not run the same minute again` |
| ✅ | R-SCH-10 | A schedule that cannot be understood leaves every other schedule running | `one schedule nobody can understand leaves the others running`, `something that is not a schedule at all is refused by itself`, `a schedule nobody can understand is reported and the others run`, `nothing written down is no schedules rather than a failure` |
| ✅ | R-SCH-11 | A schedule that is turned off is kept and reported, and does not run | `a schedule that is off does not run`, `a schedule that is off says so rather than a time`, `a schedule that is off is kept and shown as off`, `a schedule is turned off and on again without being lost`, `on or off has to be said as one or the other` |
| ✅ | R-SCH-12 | Deciding what is due asks nothing of the machine beyond the time | `deciding what is due asks nothing of the machine`, `a rare schedule is found without examining every minute` |
| ✅ | R-SCH-13 | A schedule runs only in the gateway whose schedules it is among | `a gateway runs only its own schedules`, `schedules are asked for and changed on one gateway only` |
| ✅ | R-SCH-14 | A gateway never runs, reports or alters another gateway's schedules | `a gateway runs only its own schedules`, `schedules are asked for and changed on one gateway only` |
| ✅ | R-SCH-15 | What a schedule last did, and when a gateway of its name was last up, outlive the gateway that wrote them | `what each schedule last did survives a restart`, `what fell due is said after an ordinary stop and not only a crash`, `being up leaves something a later gateway can measure against`, `that a schedule fired is written down before it is run` |
| ✅ | R-SCH-16 | A run cut short by the gateway going is told apart from one that could not start | `a run cut short by the gateway going is not called a failure to start`, `a schedule that cannot be started says so where it can be read` |
| ✅ | R-SCH-17 | A gateway's schedules that are there and cannot be read are never written over | `a schedules file that cannot be read is never written over`, `a schedules file that is valid json but not schedules is not read as none`, `a schedules file that is not there is told from one that cannot be read`, `changing schedules that cannot be read says nothing was changed` |
| ✅ | R-SCH-18 | A gateway's schedules that cannot be read are reported as unreadable rather than as none | `listing schedules that cannot be read never reports having none`, `a gateway whose schedules cannot be read still starts and says so`, `no schedule runs while the file cannot be read` |
| ✅ | R-SCH-19 | A change that altered no schedule leaves the file exactly as it was | `a change that changed nothing does not rewrite the file`, `a change that did change something is written` |
| ❌ | R-SCH-20 | A schedule run that already began is not begun again after the machine loses power | src/rundesk_cli/gateway.py:204 — no test, nothing here can cut the power |
| ✅ | R-SCH-21 | A schedule can be run by hand at any time, whether or not it is due | `a schedule can be run by hand whether or not it is due` |
| ✅ | R-SCH-22 | A schedule run by hand does not change when it next falls due on its own | `running a schedule by hand leaves the time it next falls due alone` |
| ✅ | R-SCH-23 | A schedule left saying it started by a gateway that is gone is reconciled | `a schedule left saying started by a gone gateway is reconciled`, `reconciling does not move the minute it fell due`, `work the sweep found still running is left alone`, `a schedule refused by a shutdown leaves no stale start` |
| ✅ | R-SCH-24 | A schedule is never shown as running when no gateway of its name is up | `a schedule whose gateway is gone is not shown as still running`, `a schedule running right now is shown as started` |

## Open questions

- Whether the time a schedule is stated in is ever anything other than the machine's own. It is the
  machine's today, which is what makes an hour that repeats a thing this has to survive rather than avoid.
- Whether two commands changing one gateway's schedules at once should wait for each other or refuse, given
  that waiting is what they do now and neither is told it waited.
