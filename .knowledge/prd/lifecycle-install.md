---
id: INS
name: Getting rundesk onto a machine
last_verified: 2026-07-28
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
| ✅ | R-INS-1 | A machine with none of rundesk on it installs it with one instruction | `the one instruction names the same thing everywhere it is given`, `the one instruction points at the repository rundesk updates from`, `a release serves the file the one instruction asks for`, .github/workflows/build.yml:one-instruction — the published release installed from an empty directory |
| ✅ | R-INS-2 | Installing asks for nothing the machine does not already ship with | `installing needs nothing already present beyond the machines own` |
| ✅ | R-INS-3 | Anything rundesk needs in order to run is put there by the install, never by the person | `the command finds what was installed for it`, `nothing needed means no virtualenv is made at all` |
| ✅ | R-INS-4 | Anything the install puts in place for rundesk stays inside rundesk's own directory | `what rundesk needs goes inside its own install` |
| ✅ | R-INS-5 | An install refuses to report success until the command it installed answers | `an install refuses to report success until the command it installed answers` |
| ✅ | R-INS-6 | Installing again on the same machine leaves it as it was | `installing again leaves the machine as it was` |
| ✅ | R-INS-7 | The installed command is reachable by name from any directory | `the installed command is reachable by name from any directory` |
| ✅ | R-INS-8 | Installing from a copy of the source uses that copy rather than fetching a second | `installing from a copy of the source uses that copy`, `a checkout at the install path installs itself rather than downloading` |
| ✅ | R-INS-9 | An install says so when the command it placed is not reachable by name | `an install says so when the command it placed is not reachable` |
| ✅ | R-INS-10 | Everything rundesk needs is declared, so an install can provide all of it | `everything the code imports is the standard library or declared` |
| ✅ | R-INS-11 | An install refuses to report success while what it installed does not fit together | `an install refuses to report success while what it installed does not fit together` |
| ✅ | R-INS-12 | A person has nothing left to do for rundesk to run once an install reports success | `an install refuses to report success until the command it installed answers`, `the command finds what was installed for it` |
| ✅ | R-INS-13 | Everything rundesk's install is made of lives in one directory under the person's home, kept apart from what the owner keeps | `the install lives under the persons home`, `an install writes nothing outside the places it says` , `a downloaded install puts the program in its own directory`, `installing over the layout from before leaves what the owner keeps` |
| ✅ | R-INS-14 | An install changes nothing a person owns beyond placing the command | `an install does not change the path it only says so`, `an install refuses a directory too important to be one programs`, `an install refuses to replace a checkout it did not create`, `an install refuses to replace a command of the same name` |
| ✅ | R-INS-15 | An install with no copy of the source takes the newest published version, not the newest work | `an install without a checkout takes the newest release not the branch`, `release lookup failures leave the existing install alone`, `a valid release response installs only its exact tag` |
| ✅ | R-INS-16 | Every proposed release must work for a new owner and preserve an existing owner's data and gateway behavior when upgrading from the latest release | `every pull request verifies fresh installs and upgrades from the latest release`, .github/workflows/build.yml:upgrade-existing-install — the latest tag is upgraded on macOS and Ubuntu |
| ✅ | R-INS-17 | The installer answers for its own options, and one it does not know changes nothing | `asking the installer for help prints usage and installs nothing`, `an option the installer does not know is refused before anything changes`, `help is answered even when something destructive follows it`, `an unknown option after uninstall is refused rather than ignored` |
| ✅ | R-INS-18 | Installing writes the file this install is configured through, with every section it knows and no values in them | `installing writes the configuration an owner can read`, `a section is written empty so a default can still improve`, `installing again changes nothing an owner configured` |
