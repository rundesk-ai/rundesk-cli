---
id: UPD
name: Staying current
last_verified: 2026-07-24
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
| ❌ | R-UPD-21 | An update leaves nothing that was running in a broken state | src/rundesk_cli/updater.py:150 — an update replaces the install without looking at what is running |
| ❌ | R-UPD-22 | An update brings back whatever it stopped in order to perform it | src/rundesk_cli/updater.py:150 — an update stops nothing, so it brings nothing back |
| ❌ | R-UPD-23 | An update refuses rather than interrupting work that is in flight | src/rundesk_cli/updater.py:122 — an update does not ask what is in flight |

## Open questions

- How an update stops and restarts what is running is undecided. The cheap shape is the update calling the lifecycle commands the product will already have; a registry of hooks is the expensive one, and nothing needs it yet. Something does run now, so this is answerable rather than hypothetical.
- Whether an update should refuse outright while a turn is in flight, or wait for one to finish, is undecided.
