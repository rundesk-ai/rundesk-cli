---
id: RM
name: Taking rundesk away
last_verified: 2026-07-24
---

## What this is

Removing rundesk from a machine: what goes, what stays, and who decides. It is the one thing the command
cannot do for itself, because doing it removes the command that is doing it.

## Why it exists

- Removing rundesk leaves nothing of it behind.
- Nothing a person put there themselves goes with it — a copy of the source least of all.
- Someone who wants it gone learns how from the command itself.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-RM-1 | Removing rundesk leaves no command behind | `removing rundesk leaves no command behind` |
| ✅ | R-RM-2 | Removing rundesk leaves a copy of the source that was already there | `removing rundesk leaves a copy of the source alone`, `removing rundesk leaves a checkout where it stands` |
| ✅ | R-RM-3 | Removing rundesk leaves a command of the same name belonging to something else | `removing rundesk leaves a command it did not install` |
| ✅ | R-RM-4 | Settings a person made are kept unless removal is asked to take them | `removing rundesk keeps settings unless asked to take them` |
| ✅ | R-RM-5 | The command says how it is removed rather than attempting it | `uninstall hands the job to the installer` |
| ✅ | R-RM-6 | Removing rundesk that was never installed says so rather than failing | `removing rundesk that was never installed says so` |
| ✅ | R-RM-7 | Removing rundesk takes what the install put there for it | `removing rundesk takes what was installed for it` |
| ✅ | R-RM-8 | Removing rundesk takes the directory the install created | `removing an install the installer made takes its directory` |
| ✅ | R-RM-9 | Removing rundesk stops everything it was keeping running, before anything is deleted | `removing rundesk stops every gateway it was keeping`, `removing rundesk leaves a job it did not write`, `a gateway that will not stop is reported rather than assumed`, `a job the machine still holds is not reported as taken back`, `a machine too busy to answer is not taken as having nothing`, `a gateway that would not stop can still be found next time`, `asking the machine to let go does not itself forget the job`, `removing rundesk refuses while a gateway is still running`, `removing rundesk where nothing was ever started is ordinary` |
