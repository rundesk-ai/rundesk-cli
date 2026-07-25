---
id: PROC
name: A program rundesk runs
last_verified: 2026-07-25
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
| ✅ | R-PROC-2 | rundesk finds a program it runs without depending on where a shell would look | `a program named rather than located is refused`, `naming no program at all is refused`, `a schedule naming a program rather than locating it is never added` |
| ✅ | R-PROC-3 | Everything a program rundesk runs writes out is passed on as it is written | `everything it writes out is passed on`, `what it says arrives while it is still running`, `one enormous line is passed on whole`, `what it says survives being split mid character`, `the last thing it says is not lost for want of a newline`, `the last character is not lost for being half written`, `what went wrong still arrives in the order it was said` |
| ✅ | R-PROC-4 | rundesk ends a program it runs at any point, without waiting for that program to agree | `a program is ended whenever rundesk decides`, `a program that will not leave is ended anyway`, `a first signal that does not land is not the end of it`, `giving up on ending a program still ends it`, `ending waits for the whole tree not just the one we started`, `a group that vanishes while being ended is not chased`, `giving up on a program does not leave it running`, `ending a program that already finished does nothing`, `ending a program that never started does nothing`, `reading a program that was never started is refused` |
| ✅ | R-PROC-5 | Ending a program rundesk runs also ends everything that program started | `ending a program ends what it started`, `a gateway going away ends what the work left running`, `ending says whether the group really went`, `ending something that will not go says it did not`, `ending nothing at all is a success` |
| ✅ | R-PROC-6 | A program that goes on saying things runs for as long as it keeps saying them | `a program that keeps talking is left to run`, `pauses do not add up across the things it says`, `a program may be allowed to be quiet indefinitely`, `a finished program is not waited on for the whole silence` |
| ✅ | R-PROC-7 | A program that has said nothing for longer than it is allowed is ended | `a program that goes quiet is ended`, `going quiet is measured from the last thing it said`, `a program that stops talking but keeps running is not waited on forever` |
| ✅ | R-PROC-8 | A program that finished on its own is told apart from one rundesk ended | `finishing is told apart from being ended`, `being ended is told apart from going quiet`, `a program that closes its output and goes quiet is told apart` |
| ✅ | R-PROC-9 | A program that failed is told apart from one that finished on its own | `failing is told apart from finishing`, `dying is told apart from finishing` |
| ✅ | R-PROC-10 | Any number of programs run at the same time without affecting one another | `programs run at the same time rather than in turn`, `what each says reaches only its own caller`, `one program ending badly leaves the others running`, `two programs with receivers run at once without crossing` |
| ✅ | R-PROC-11 | Nothing a program started outlives the program that started it | `what a finished program left behind does not outlive it`, `a talkative leftover does not hold the drain open forever`, `a gateway going away ends what the work left running`, `what a finished program left behind is ended anyway if it will not go`, `a handler that raises does not leave the program running`, `everything still running is ended together` |
| ✅ | R-PROC-13 | A program is ended once it has run longer than it is ever allowed, however much it is saying | `a program that never stops talking is still ended eventually`, `a talkative leftover does not hold the drain open forever`, `a program that closes its output is still held to the ceiling`, `running a long time is not by itself a reason to be ended`, `a program may be allowed to run without any ceiling`, `a gateway can start work with no ceiling on how long it runs`, `overrunning is told apart from going quiet` |
| ✅ | R-PROC-12 | What a program says is never held against the memory of the machine it runs on | `only a tail is kept however much it says`, `output with no line ending is not held forever`, `what went wrong is not held against the machine`, `what is held for a receiver is bounded in bytes` |
| ✅ | R-PROC-14 | rundesk writes to a program while that program is running | `a program is written to while it is running`, `what is written arrives in the order it was written`, `a program that has gone is not written to forever`, `a program not started to be written to says so`, `writing to a program that never started is refused`, `a program is given no input and one stream unless rundesk says otherwise`, `a gateway starts work it can write to and read records from`, `work the gateway only reads is given no input and one stream` |
| ✅ | R-PROC-15 | What a program writes to its error stream is kept apart from what it writes out | `the two streams are kept apart`, `a program is given no input and one stream unless rundesk says otherwise`, `what work said went wrong is written down rather than parsed`, `work the gateway only reads is given no input and one stream` |
| ✅ | R-PROC-16 | A program is never held up by rundesk failing to read one of its streams | `a program is not held up by a stream nobody reads`, `a conversation larger than the pipes completes` |
| ✅ | R-PROC-17 | Whoever receives what a program says never holds that program up | `a receiver that fails neither stops nor ends the program`, `a receiver that is slow does not slow the program`, `a receiver that never reads is told what it missed`, `a gateway starts work it can write to and read records from`, `a receiver that refuses is recorded rather than lost`, `a receiver that fails after being awaited is survived too`, `two programs with receivers run at once without crossing` |
| ✅ | R-PROC-18 | What a program says reaches its receiver whole or is reported as lost | `a record is never passed on in pieces`, `a record at the limit is still passed on whole`, `a record split across reads arrives whole`, `a record the program did not finish is not passed on as one`, `bytes that are not text survive whole`, `a carriage return before the ending is not part of the record`, `an empty record is still a record`, `records are refused from a program whose streams are folded`, `a record too big before its ending arrives is dropped and the rest kept` |
| ✅ | R-PROC-19 | rundesk chooses the directory a program it runs starts in | `a program starts where rundesk puts it`, `a program rundesk gives no directory starts where rundesk did`, `a gateway starts work in the workspace it is given` |
| ✅ | R-PROC-21 | Whoever receives what a program says never ends that program | `a receiver that fails neither stops nor ends the program`, `a receiver that fails after being awaited is survived too`, `a receiver that refuses is recorded rather than lost` |
| ✅ | R-PROC-20 | A program is told there is no more input without being ended | `a program is told there is no more coming without being ended`, `writing after there is no more coming is refused`, `telling a program with no input there is no more does nothing` |

## Open questions

- What a receiver may conclude from the order of two things a program said, now that the streams can be
  kept apart. Within one there is an order and it is exact; between the two there is none at all, and
  nothing here can supply one — a moment stamped on it would be when rundesk read it, not when the
  program said it. Whatever needs the two related has to take that from inside what it is parsing.
- Whether how long a program may say nothing, and how long it may run at all, are fixed for every
  program or set per kind of program.
- A program does survive rundesk being killed outright, since it is in a group of its own and out of
  reach of anything that ends rundesk without warning. What ends it is whatever takes over the name it
  was started under, next time that happens; whether that is soon enough is the part still open.
