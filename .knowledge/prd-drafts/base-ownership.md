---
id: OWN
name: Owning what is running
last_verified: 2026-07-25
---

## What this is

Who is answerable for a thing that is running, whatever kind of thing it is. Every part of rundesk that
starts something is an owner, and these are the laws each of them keeps.

## Why it exists

- Nothing rundesk started is ever running with nobody answerable for it.
- One part of rundesk going wrong is never another part going wrong.
- The same piece of work is never being done twice over.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-OWN-1 | Everything rundesk starts has exactly one owner | `the same work is refused while it is already running`, `only one gateway of a name runs at a time` |
| ✅ | R-OWN-2 | An owner ends everything it owns before it goes | `a gateway going away ends what it was running`, `ending a program ends what it started` |
| ✅ | R-OWN-3 | Nothing rundesk starts outlives every owner it ever had | `what a finished program left behind does not outlive it`, `taking a name ends what the last gateway of it was running` |
| ❌ | R-OWN-4 | Keeping rundesk running is the machine's to do, and not rundesk's own | — no job describes a gateway to the machine yet |
| ✅ | R-OWN-5 | What one owner owns is unaffected by what any other owner does | `one gateway ending its work leaves another gateways work alone`, `one program ending badly leaves the others running` |
| ✅ | R-OWN-6 | An owner that goes without ending what it owned leaves it to the next owner of its name | `going with work still running leaves the record naming it`, `taking a name ends what the last gateway of it was running` |
| ✅ | R-OWN-7 | The same piece of work is never owned by two owners at once | `the same work is refused while it is already running`, `the same work name under two gateways is two pieces of work` |
| ✅ | R-OWN-8 | An owner ends only what it can show belongs to it | `a number that now belongs to something else is left alone`, `a record that cannot prove what it left is left alone` |
| ✅ | R-OWN-9 | What became of a thing rundesk owned is knowable after that thing has gone | `what a gateway wrote outlives the gateway`, `work that ended badly is recorded with its last words` |

## Open questions

- Whether an owner starts again something it owned that failed, given that repeating work repeats whatever
  that work already did to the machine. Nothing does this today.
- Whether a thing whose owner is gone and whose name is never taken again is anyone's to end.
