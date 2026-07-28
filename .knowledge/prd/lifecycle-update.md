---
id: UPD
name: Staying current
last_verified: 2026-07-28
---

## What this is

Which version this copy of rundesk is, which one has been published, and moving from the first to the
second. Everything here is answerable without changing anything.

## Why it exists

- The version in use is knowable without asking anyone.
- Being behind is obvious, and so is what to do about it.
- Not being able to ask is never mistaken for being current.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-UPD-1 | The installed command reports which version it is | `version says what is installed` |
| ✅ | R-UPD-2 | The version is reported without reaching anything outside the machine | `version says what is installed without asking anyone` |
| ✅ | R-UPD-3 | The installed command reports whether a newer version has been published | `version check reports against what is published`, `the published tag is read out of the release`, `it asks the releases endpoint for this repository`, `newer is compared by number and not by text` |
| ✅ | R-UPD-4 | Being behind is reported with what to do about it | `being behind is said in words that name the way out` |
| ✅ | R-UPD-5 | Being unable to ask what is published is never reported as being current | `an unreachable forge is reported as unknown never as current`, `a forge that cannot be reached says nothing rather than guessing`, `a reply that is not json is survived`, `each of the three answers is distinguishable` |
| ✅ | R-UPD-6 | A published version that cannot be read is never reported as newer | `a version that cannot be read never claims an update`, `a release with no tag is not turned into one`, `something that is not a version is not guessed at` |
| ✅ | R-UPD-7 | The version this copy reports can always be compared against a published one | `the version in the code is one that can be compared`, `a published tag is compared against a bare local version`, `a version is read with or without its v` |
| ✅ | R-UPD-8 | Asking where this copy stands never changes it | `check never moves the install`, `check only reports and changes nothing` |
| ✅ | R-UPD-9 | Every way of asking where this copy stands gives the same answer | `version check and update check agree on where this install stands`, `update says where it stands rather than reaching out blindly` |
| ✅ | R-UPD-10 | rundesk moves itself to the newest published version | `a release is downloaded unpacked and laid over the install`, `being behind moves the install` |
| ✅ | R-UPD-11 | An update replaces what the newer version ships | `the new release replaces what was there`, `a directory is replaced rather than merged` |
| ✅ | R-UPD-12 | An update leaves what the newer version does not ship | `what the release does not ship is left alone` |
| ✅ | R-UPD-13 | An update leaves the command runnable | `the entry point and installer come out executable` |
| ✅ | R-UPD-14 | An update that does not complete leaves this copy as it was | `a download that fails leaves the install as it was`, `an archive that is not shaped like a release is refused`, `an update that stops partway leaves the command able to run`, `an update that stops partway leaves nothing of itself behind` |
| ✅ | R-UPD-15 | A published version is refused when it is not shaped like one | `an archive that is not shaped like a release is refused`, `an archive cannot write outside where it is unpacked`, `an archive cannot write through a link that points outside` |
| ✅ | R-UPD-16 | An update moves only to the version most recently published | `being behind moves the install` |
| ✅ | R-UPD-17 | No version other than the most recently published can be asked for | `an update cannot be pointed at a version of your choosing` |
| ✅ | R-UPD-18 | An update that finds nothing newer leaves this copy alone | `up to date says so and changes nothing` |
| ✅ | R-UPD-19 | A published version is named the same as the version the command reports | `a tag naming something else is refused`, `publishing a release actually applies the rule` |
| ✅ | R-UPD-20 | Nothing published is told apart from being unable to ask | `nothing published is told apart from being unable to ask` |
| ✅ | R-UPD-21 | An update leaves nothing that was running in a broken state | `an update stops what it is about to replace the files of`, `an update refused by what is running replaces nothing`, `an update with nothing running stops and starts nothing`, `an update stops every supervised gateway that is running`, `an external update acts on jobs owned by the target install`, `an update refuses rather than taking down what it cannot start again`, `an update on a machine with no supervisor stops nothing`, `a gateway that will not stop leaves the install untouched` |
| ✅ | R-UPD-22 | An update brings back whatever it stopped in order to perform it, unless moving its records forward failed (R-MIG-6) | `an update brings back what it stopped`, `an update that failed still brings back what it stopped`, `an update that broke a gateway says so rather than reporting success`, `a gateway that does not come back is reported rather than passed over` |
| ✅ | R-UPD-23 | An update refuses rather than interrupting work that is in flight | `an update refuses while work is in flight`, `an update says what is in flight rather than something`, `an update with nothing in flight goes ahead`, `checking never refuses for work in flight`, `what is in flight is asked of every gateway that is running` |
| ✅ | R-UPD-24 | An update that stops before replacing anything brings back every gateway it stood down | `an update that stops before replacing anything brings back what it stood down`, `a gateway that would not restart after a refusal is named` |
| ✅ | R-UPD-25 | An update that replaced only part of a release puts back what was there, or says it could not | `an update that replaced only part of a release puts back what was there`, `an install that could not be put back says so rather than reporting a failure`, `a swap that fails puts back what was working` |
| ✅ | R-UPD-26 | Only one update changes an install at a time, from the first thing it stops to the last it starts | `only one update changes an install at a time`, `an update refuses while another is already running`, `an update that finishes leaves the way clear for the next` |
| ✅ | R-UPD-27 | What an install is made of is checked as usable rather than merely installed | `what an install needs is installed and then checked`, `a set that cannot satisfy itself is a build that failed`, `what pip reported is checked against what actually landed` |
| ✅ | R-UPD-28 | A rebuild that fails puts back what the install was running before it | `what was working is put back when the build fails`, `a build that worked lets go of what it replaced` |
| ✅ | R-UPD-29 | A release that stops needing something takes it away rather than leaving it for ever | `a release that stops needing something leaves it behind no longer`, `nothing declared makes no virtualenv at all` |
| ✅ | R-UPD-30 | What an install is made of comes forward before what its agents keep | `what an install is made of comes forward before what it keeps` |
| ✅ | R-UPD-31 | An update that cannot bring either forward puts the install back on the release it was | `an update that cannot build what a release needs puts the release back`, `a migration that fails puts the install back and says which and why` |
| ✅ | R-UPD-32 | An install already current but unfit is mended rather than reported as current | `an install already current but unfit is mended rather than called current`, `an install that is current and fits is left entirely alone`, `asking where a broken install stands still changes nothing` |
| ✅ | R-UPD-33 | Everything after the files are replaced is done by the release that was just installed | `the rest of the window is handed to the release that just landed`, `the release that took over brings every gateway back`, `a release whose entry point will not start is put back` |
| ✅ | R-UPD-34 | Asking what an update would do names what it would install and what it would move | `update check names every step it would run and installs nothing`, `asking what an update would do is asked of nothing but this machine` |
| ✅ | R-UPD-35 | An agent-initiated update is completed by a supervisor-owned process outside every gateway | `the update worker is outside the gateway namespace`, `the machine owns the worker that may stop gateways`, `agent initiation queues the external worker and returns` |
| ✅ | R-UPD-36 | An update request durably records pending, running, and final states | `pending running and final outcomes are durable`, `agent initiation queues the external worker and returns` |
| ✅ | R-UPD-37 | Duplicate update requests share one worker request and cannot overlap | `duplicate requests share one pending update`, `duplicate agent initiation kicks without reinstalling the worker` |
| ✅ | R-UPD-38 | The external worker waits for active turns before running the guarded updater | `an update refuses while work is in flight`, `update busy reader includes provider turns`, `bootstrap child drives the old target with its new update logic`, `external worker waits for the origin run record to finish` |
| ✅ | R-UPD-39 | Connected channel adapters do not themselves block an otherwise idle update | `a connected channel adapter does not block an idle update` |
| ✅ | R-UPD-40 | A channel-triggered update outcome is delivered after its originating agent reconnects | `final outcome waits for its origin agent and is delivered once`, `a completed update is delivered after the channel reconnects` |
| ✅ | R-UPD-41 | A channel-triggered update resumes its originating work after the agent reconnects | `a completed update resumes its originating work after reconnect` |
| ✅ | R-UPD-42 | The machine queues one automatic Rundesk update every day at the configured local time, which defaults to three in the morning | `the daily trigger defaults to three in the morning`, `the automatic update time is the owners to state`, `the daily trigger queues the crash recoverable worker`, `installing schedules daily updates for the configured time` |
| ✅ | R-UPD-43 | Gateways stopped for an update report maintenance, then report its completion when they return | `an update marks maintenance until the gateway is back`, `update maintenance is not announced as an unexplained outage`, `a gateway returning from an update says maintenance is complete` |
| ✅ | R-UPD-44 | A successor update worker restores each gateway its predecessor stopped, without starting deliberately stopped gateways | `an interrupted update stays active for the supervisor to retry`, `a successor worker restores only a gateway marked for maintenance`, `a successor worker never starts a gateway on an unfit release` |
| ✅ | R-UPD-45 | Triggering a pending update wakes its supervisor-owned worker | `duplicate agent initiation kicks a loaded stopped worker`, `a second daily trigger wakes without reinstalling the worker`, `a loaded one shot worker can be kicked again` |

## Open questions

- How long an account of what a run did is kept, and whether an owner or a size decides. Separate from
  the copy an update takes, which is answered: that one lives exactly as long as the move it insures.
