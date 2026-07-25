---
id: INS
name: Getting rundesk onto a machine
last_verified: 2026-07-24
---

## What this is

How rundesk arrives on a machine and becomes a command a person can run. It ends the moment that command
answers; keeping it current and taking it away are their own contracts.

## Why it exists

- Someone with a bare machine ends up with a working command, from one instruction.
- Everything rundesk needs arrives with it — nothing is put in place by hand, before or after.
- An install that did not work says so, rather than leaving a command that cannot run.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-INS-1 | A machine with none of rundesk on it installs it with one instruction | install.sh:1 — the path exists, but no release has been published to install from |
| ✅ | R-INS-2 | Installing asks for nothing the machine does not already ship with | `installing needs nothing already present beyond the machines own` |
| ✅ | R-INS-3 | Anything rundesk needs in order to run is put there by the install, never by the person | `the command finds what was installed for it`, `nothing needed means no virtualenv is made at all` |
| ✅ | R-INS-4 | Anything the install puts in place for rundesk stays inside rundesk's own directory | `what rundesk needs goes inside its own install` |
| ✅ | R-INS-5 | An install refuses to report success until the command it installed answers | `an install refuses to report success until the command it installed answers` |
| ✅ | R-INS-6 | Installing again on the same machine leaves it as it was | `installing again leaves the machine as it was` |
| ✅ | R-INS-7 | The installed command is reachable by name from any directory | `the installed command is reachable by name from any directory` |
| ✅ | R-INS-8 | Installing from a copy of the source uses that copy rather than fetching a second | `installing from a copy of the source uses that copy` |
| ✅ | R-INS-9 | An install says so when the command it placed is not reachable by name | `an install says so when the command it placed is not reachable` |
| ✅ | R-INS-10 | Everything rundesk needs is declared, so an install can provide all of it | `everything the code imports is the standard library or declared` |
| ✅ | R-INS-11 | An install refuses to report success while what it installed does not fit together | `an install refuses to report success while what it installed does not fit together` |
| ✅ | R-INS-12 | A person has nothing left to do for rundesk to run once an install reports success | `an install refuses to report success until the command it installed answers`, `the command finds what was installed for it` |
| ✅ | R-INS-13 | Everything an install puts on a machine lives in one directory under the person's home | `the install lives under the persons home`, `an install writes nothing outside the places it says` |
| ✅ | R-INS-14 | An install changes nothing a person owns beyond placing the command | `an install does not change the path it only says so` |
| ✅ | R-INS-15 | An install with no copy of the source takes the newest published version, not the newest work | `an install without a checkout takes the newest release not the branch` |
