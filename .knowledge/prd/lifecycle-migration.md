---
id: MIG
name: Moving data between versions
last_verified: 2026-07-26
---

## What this is

Bringing what is already on a machine into the shape a newer rundesk expects, in the window an
update already stands every gateway down for. A step forward exists; a step back does not.

## Why it exists

- An update never costs an owner what their agents said, did or were told.
- An update that goes wrong leaves the data as it was, and says so.
- A version that cannot be understood is refused, rather than read and half-believed.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-MIG-1 | Data is moved to a newer shape while nothing an owner runs is up | `records are moved forward while nothing an owner runs is up`, `every agent is brought forward when an update lands` |
| ✅ | R-MIG-2 | A step that brings data forward is found rather than listed | `a step dropped into the directory is found without a list being edited` |
| ✅ | R-MIG-3 | Steps run in order, from the shape on disk to the shape now installed | `steps are ordered by the number they carry and never by their name` |
| ✅ | R-MIG-4 | A step runs once, and an update that stopped partway does not run it again | `running again after the step is fixed resumes at it and does not redo the one before` |
| ✅ | R-MIG-5 | A step that fails leaves the data exactly as it was | `a step that fails leaves the data exactly as it was` |
| ✅ | R-MIG-6 | A step that fails stops the update and leaves every agent down | `a migration that fails leaves every agent down and says which and why`, `an agent whose records cannot be moved names that agent` |
| ✅ | R-MIG-7 | An owner is told which agent could not be moved, which step failed, and what it had reached | `which step failed and the version it reached are both named`, `an agent whose records cannot be moved names that agent`, `what went wrong is left in that agents own log` |
| ✅ | R-MIG-8 | Data newer than this copy of rundesk understands is refused rather than read (R-STO-12) | `data newer than this rundesk understands is refused rather than read` |
| ✅ | R-MIG-9 | A newly made agent is built by taking every step in order | `a brand new agent is built by running the steps that ship`, `an agent is made with the records it keeps` |
| ✅ | R-MIG-10 | Data behind the shape installed is refused rather than moved forward by whatever opened it | `records behind the shape installed are refused on open and never moved forward` |
| ✅ | R-MIG-11 | A step moves what is kept as files as well as what is kept as records | `what a step copied is let go of only once the version has committed` |
| ✅ | R-MIG-12 | What a step copied is let go of only once the version it reached has been recorded | `a step that fails after copying leaves both copies and the version where it was` |
| ✅ | R-MIG-13 | A step's stamp of the version it reached is kept with its work and never apart from it | `a steps version stamp is committed with its work and never apart from it` |
| ✅ | R-MIG-14 | Two steps claiming one version are refused rather than one of them chosen | `two steps claiming one version are refused rather than one of them chosen` |
| ✅ | R-MIG-15 | The shape this copy of rundesk understands is read off the steps that ship with it | `the shape this rundesk understands is the last step that ships` |
| ✅ | R-MIG-16 | A number too large to be recorded as a version is refused rather than wrapped | `a number that could not be a version is refused rather than wrapped` |
| ✅ | R-MIG-17 | Nothing an update moves loses an account, a log, or what a schedule last did | `nothing an update moves loses an account a log or what a schedule last did` |
| ✅ | R-MIG-18 | Data moved forward is never moved back | `records moved forward are never moved back`, `records are left alone when the files never landed` |

## Open questions

- Whether an update part-way through moving data can be resumed or must be run again from the
  version on disk.
- Whether an owner may ask what a step would do before it does it.
- What happens to an agent whose records cannot be read at all when every other agent's can.
- Whether a copy of what was there is kept after a move is proved, and for how long.
- Whether a machine that never updates, only reinstalls, needs any of this.
- What becomes of something an earlier rundesk left behind that belongs to no agent, given
  nothing outside an agent carries a version to move it under.
