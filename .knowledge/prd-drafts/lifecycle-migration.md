---
id: MIG
name: Moving data between versions
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
| ❌ | R-MIG-1 | Data is moved to a newer shape while nothing an owner runs is up | — |
| ❌ | R-MIG-2 | A step that brings data forward is found rather than listed | — |
| ❌ | R-MIG-3 | Steps run in order, from the shape on disk to the shape now installed | — |
| ❌ | R-MIG-4 | A step runs once, and an update that stopped partway does not run it again | — |
| ❌ | R-MIG-5 | A step that fails leaves the data exactly as it was | — |
| ❌ | R-MIG-6 | A step that fails stops the update and leaves every agent down | — |
| ❌ | R-MIG-7 | An owner is told which step failed and what it had reached | — |
| ❌ | R-MIG-8 | Data newer than this copy of rundesk understands is refused rather than read (R-STO-17) | — |
| ❌ | R-MIG-9 | A fresh install runs no step and is stamped with the shape it was born in | — |
| ❌ | R-MIG-10 | What was already there is kept until the newer shape is written and readable | — |
| ❌ | R-MIG-11 | A step moves what is kept as files as well as what is kept as records | — |
| ❌ | R-MIG-12 | Nothing an update moves loses an account, a log, or what a schedule last did | — |
| ❌ | R-MIG-13 | Data moved forward is never moved back | — |
| ❌ | R-MIG-14 | Which shape an install's data is in is readable without opening any agent's records | — |

## Open questions

- Whether an update part-way through moving data can be resumed or must be run again from the
  version on disk.
- Whether an owner may ask what a step would do before it does it.
- What happens to an agent whose records cannot be read at all when every other agent's can.
- Whether a copy of what was there is kept after a move is proved, and for how long.
- Whether a machine that never updates, only reinstalls, needs any of this.
