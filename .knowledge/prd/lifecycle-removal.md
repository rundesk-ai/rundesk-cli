---
id: RM
name: Taking rundesk away
last_verified: 2026-07-26
---

## What this is

Removing rundesk from a machine: what goes, what stays, and who decides. It is the one thing the command
cannot do for itself, because doing it removes the command that is doing it.

## Why it exists

- Removing rundesk leaves nothing of it behind.
- Nothing a person put there themselves goes with it — a copy of the source least of all.
- Someone who wants it gone types one command, and is told plainly when it could not.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-RM-1 | Removing rundesk leaves no command behind | `removing rundesk leaves no command behind` |
| ✅ | R-RM-2 | Removing rundesk leaves a copy of the source that was already there | `removing rundesk leaves a copy of the source alone`, `removing rundesk leaves a checkout where it stands` |
| ✅ | R-RM-3 | Removing rundesk leaves a command of the same name belonging to something else | `removing rundesk leaves a command it did not install` |
| ✅ | R-RM-4 | Settings a person made are kept unless removal is asked to take them | `removing rundesk keeps settings unless asked to take them`, `removing rundesk keeps what the gateways wrote unless asked to take it` |
| ✅ | R-RM-5 | The command removes rundesk itself rather than describing how to remove it | `uninstall removes rundesk rather than explaining how to`, `uninstall passes a purge through rather than deciding for you` |
| ✅ | R-RM-6 | Removing rundesk that was never installed says so rather than failing | `removing rundesk that was never installed says so` |
| ✅ | R-RM-7 | Removing rundesk takes what the install put there for it | `removing rundesk takes what was installed for it` |
| ✅ | R-RM-8 | Removing rundesk takes the directory the install created, and the one above it once nothing of the owner's is left in it | `removing an install the installer made takes its directory`, `purging takes what the gateways wrote as well`, `removing an install from before the program had its own directory` |
| ✅ | R-RM-9 | Removing rundesk stops everything it was keeping running, before anything is deleted | `removing rundesk stops every gateway it was keeping`, `removing rundesk leaves a job it did not write`, `a gateway that will not stop is reported rather than assumed`, `a job the machine still holds is not reported as taken back`, `a machine too busy to answer is not taken as having nothing`, `a gateway that would not stop can still be found next time`, `asking the machine to let go does not itself forget the job`, `removing rundesk refuses while a gateway is still running`, `removing rundesk where nothing was ever started is ordinary` |
| ✅ | R-RM-10 | What a gateway wrote about what happened is kept unless removal is asked to take it (R-GW-18) | `removing rundesk keeps what the gateways wrote unless asked to take it`, `purging takes what the gateways wrote as well` |
| ✅ | R-RM-11 | A removal that did not happen is reported as a failure rather than as success | `uninstall that removed nothing says so and fails`, `uninstall with no installer says where to get one` |
| ✅ | R-RM-12 | Removing the program cannot reach what the owner keeps, rather than remembering not to | `removing the program cannot reach what the owner keeps`, `purging takes what the owner keeps as well`, `removing rundesk leaves a checkout where it stands` , `a downloaded install puts the program in its own directory` |
