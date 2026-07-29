---
id: CMD
name: The command surface
last_verified: 2026-07-24
---

## What this is

Everything `rundesk` offers, and how it behaves when asked for something that has not been built. The
command is the only way into the product, so what it lists is what the product is.

## Why it exists

- Someone new can see the whole shape of the product without reading anything else.
- Nothing the command does is discovered only by being told about it.
- A script is never told a thing happened when it did not.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-CMD-1 | Every operation the product will offer is listed by the command from the outset | `the planned list and the built commands do not overlap` |
| ✅ | R-CMD-2 | Every operation the command lists is described where it is listed | `every verb is described` |
| ✅ | R-CMD-3 | The command with no operation named describes what it can do | `bare command describes itself and succeeds` |
| ✅ | R-CMD-4 | An operation that is not built says so rather than appearing to work | `a planned command says so and does not report success` |
| ✅ | R-CMD-5 | An operation that is not built ends unsuccessfully | `a planned command says so and does not report success` |
| ✅ | R-CMD-6 | Every operation the command lists is answered by something | `every verb is reachable and none falls through`, `every operation is reachable including the ones under a verb` |
| ✅ | R-CMD-7 | An operation that is not built accepts the arguments it will take once built | `a planned command tolerates the arguments it will take` |
| ✅ | R-CMD-8 | An operation that is not built ends differently from one named wrongly | `a command that is not there is told apart from one typed wrong` |
| ✅ | R-CMD-9 | An operation that is not built points at a command that does work | `a planned command names something that does work` |
| ✅ | R-CMD-10 | An operation that is not built says which part of it is missing | `a planned command says which of it is not there` |
| ✅ | R-CMD-11 | An owner can ask what this install is configured with, and which of it defaulted | `what an install is configured with is answerable`, `a value that was stated is told apart from one that defaulted`, `an unreadable configuration is refused rather than reported as defaults` |
