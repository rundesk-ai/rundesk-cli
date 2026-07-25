---
id: PROC
name: A program rundesk runs
last_verified: 2026-07-24
---

## What this is

Any program rundesk starts on the owner's behalf, and how rundesk keeps hold of it. rundesk does not
drive what such a program does — it decides that one runs, watches it, and ends it.

## Why it exists

- A session that takes hours is left to take them.
- Nothing rundesk started is ever left running with nobody owning it.
- What became of a program rundesk ran is always known.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-PROC-1 | rundesk chooses the environment a program it runs is given | `what it is given is what it sees`, `what it is not given it does not see`, `a program is given nothing unless rundesk says otherwise`, `the environment carries what a program needs to find itself` |
| ✅ | R-PROC-2 | rundesk finds a program it runs without depending on where a shell would look | `a program named rather than located is refused`, `a program is located once so nothing looks again`, `a program that is not there resolves to nothing` |
| ✅ | R-PROC-3 | Everything a program rundesk runs writes out is passed on as it is written | `everything it writes out is passed on`, `what it says arrives while it is still running`, `one enormous line is passed on whole`, `what it says survives being split mid character`, `the last thing it says is not lost for want of a newline`, `the last character is not lost for being half written` |
| ✅ | R-PROC-4 | rundesk ends a program it runs at any point, without waiting for that program to agree | `a program is ended whenever rundesk decides`, `a program that will not leave is ended anyway`, `giving up on a program does not leave it running` |
| ✅ | R-PROC-5 | Ending a program rundesk runs also ends everything that program started | `ending a program ends what it started` |
| ✅ | R-PROC-6 | A program that goes on saying things runs for as long as it keeps saying them | `a program that keeps talking is left to run`, `pauses do not add up across the things it says`, `a program may be allowed to be quiet indefinitely`, `a finished program is not waited on for the whole silence` |
| ✅ | R-PROC-7 | A program that has said nothing for longer than it is allowed is ended | `a program that goes quiet is ended`, `going quiet is measured from the last thing it said` |
| ✅ | R-PROC-8 | A program that finished on its own is told apart from one rundesk ended | `finishing is told apart from being ended`, `being ended is told apart from going quiet` |
| ✅ | R-PROC-9 | A program that failed is told apart from one that finished on its own | `failing is told apart from finishing`, `dying is told apart from finishing` |
| ✅ | R-PROC-10 | Any number of programs run at the same time without affecting one another | `programs run at the same time rather than in turn`, `what each says reaches only its own caller`, `one program ending badly leaves the others running` |
| ✅ | R-PROC-11 | Nothing a program started outlives the program that started it | `what a finished program left behind does not outlive it`, `a handler that raises does not leave the program running` |
| ✅ | R-PROC-12 | What a program says is never held against the memory of the machine it runs on | `only a tail is kept however much it says`, `output with no line ending is not held forever` |

## Open questions

- Whether how long a program may say nothing is fixed for every program, or set per kind of program.
- Whether a program rundesk started survives rundesk being killed outright, since a program in its own
  group is out of reach of anything that ends rundesk without warning.
