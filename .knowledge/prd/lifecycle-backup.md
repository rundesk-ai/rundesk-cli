---
id: BKP
name: Copies of what an owner keeps
last_verified: 2026-07-27
---

## What this is

Copies of everything an owner keeps, taken on demand or by the machine, kept apart from both
the program and the data so that removing either cannot reach them. Putting one back is its
own act, and the dangerous half.

## Why it exists

- What an owner's agents were told, did and said survives anything that happens to this machine.
- The command somebody runs when something is wrong never destroys the only copy.
- A copy that was taken can be put back, and says what it will change before it changes it.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-BKP-1 | A backup holds everything the owner keeps | `a backup holds what the owner keeps`, `a backup holds the skills library and this installs own configuration` |
| ✅ | R-BKP-2 | A backup holds nothing of the program | `a backup holds nothing of the program` |
| ✅ | R-BKP-3 | A backup leaves out what describes a running gateway or belongs to an update | `a backup leaves out what a gateway is using right now`, `a backup leaves out the copy an update is holding`, `a backup leaves out what belongs beside a database and not to it` |
| ✅ | R-BKP-4 | A backup says what it deliberately left out, and why | `a backup says what it left out and why` |
| ✅ | R-BKP-5 | A backup says which rundesk took it, why, and what shape each agent's records were in | `a backup says which rundesk took it and what shape each agent was in`, `a backup says why it was taken`, `an agent with no records yet is still named` |
| ✅ | R-BKP-6 | What a backup holds is put back with the permissions and links it had | `a file an owner made runnable is still runnable`, `a granted skill is kept as the link it is` |
| ✅ | R-BKP-7 | Backups sort by the moment they were taken when sorted by name | `a backup is named so that sorting by name sorts by time`, `a backup is named in one clock so an hour that happens twice still sorts` |
| ✅ | R-BKP-8 | A backup is never under its final name until it is complete | `nothing is under its final name until it is whole`, `a backup that could not be finished leaves nothing behind`, `backing up where there is nothing says so rather than writing an empty one` |
| ✅ | R-BKP-27 | Taking a backup never writes over one that is already there | `a second backup in the same second never writes over the first`, `two in one second still sort by the moment they were taken` |
| ✅ | R-BKP-9 | Records in use are copied as of one moment rather than as the file stands | `a backup of a database in use holds what was written to it` |
| ✅ | R-BKP-10 | Every copy that exists is listed, including one that cannot be read | `every backup there is reads back oldest first`, `a directory with no backups in it is empty rather than an error`, `something that is not a backup is listed rather than passed over` |
| ✅ | R-BKP-11 | Something that is not a backup is refused rather than read as an empty one | `a zip that says nothing about itself is not a backup`, `asking for a backup that was never there says which one` |
| ✅ | R-BKP-12 | A copy the machine cannot reach says so rather than failing as though it were damaged | `a backup that is not on this disk says so rather than failing obscurely` |
| ✅ | R-BKP-13 | How long copies are kept and when one is taken are the owner's to state | `an install reads backup values from its configuration`, `how long backups are kept is the owners to state`, `a time of day is read the way a person writes one` |
| ✅ | R-BKP-14 | Configuration that cannot be understood is refused rather than replaced by a default | `configuration that cannot be understood is refused rather than ignored`, `a length of time that would keep nothing is refused`, `a time of day that is not one is refused` |
| ✅ | R-BKP-15 | Records too damaged to copy as of one moment are kept as they are and named | `a database too damaged to copy consistently is kept exactly as it is` |
| ✅ | R-BKP-16 | Putting a copy back replaces everything the owner keeps, and says what it will change first | `an agent and its history are whole again after a restore`, `putting one back brings back what was removed and takes away what was added`, `what was runnable and what was a link are still that after a restore` |
| ✅ | R-BKP-17 | Putting a copy back takes a copy of what is there first | `a restore takes a copy of what is there first` |
| ✅ | R-BKP-18 | A copy written by a newer rundesk is refused before anything is moved | `records written by a newer rundesk are refused and nothing is moved`, `a backup taken by a newer rundesk is refused and nothing is moved`, `a backup at the shape installed is put back rather than refused` |
| ✅ | R-BKP-19 | A copy behind the shape installed is brought forward as it is put back | `a backup from an older shape is brought forward as it is put back`, `a restore brings records forward before it swaps anything in` |
| ✅ | R-BKP-20 | Putting a copy back while anything is running or any work is in flight is refused | `putting one back while work is in flight is refused`, `a gateway that will not stand down stops the restore`, `a restore stands gateways down and starts them again`, `a gateway that does not come back is said rather than passed over` |
| ✅ | R-BKP-21 | What was there survives a restore that fails part way | `what was there survives a restore that fails part way`, `what was there survives the swap itself going wrong` |
| ✅ | R-BKP-22 | Copies older than the stated age are taken away once a newer one exists | `copies past the stated age are taken away`, `a copy whose age cannot be read is never the one removed` |
| ✅ | R-BKP-23 | The newest copy is never taken away by age | `the only copy there is is never taken away by age`, `every copy being old still leaves the newest one` |
| ✅ | R-BKP-24 | Deleting a copy is asked for by name and never happens as a side effect | `one copy is removed by the name it is listed under`, `removing one that is not there says so`, `removing cannot reach outside the directory copies are kept in` |
| ✅ | R-BKP-25 | The machine takes a copy every day once it is asked to | `the daily job runs at the hour it was given`, `the daily job is never kept alive`, `the daily job carries where backups go`, `the daily job cannot be mistaken for a gateway`, `an agent may be called backup without colliding with the daily job`, `stopping the daily job takes its description away too` |
| ✅ | R-BKP-26 | Copies survive removing rundesk, with or without its data (R-RM-14) | `removing rundesk keeps the copies it took`, `purging keeps the copies it took` |
| ✅ | R-BKP-28 | Unavailable backup storage does not prevent install health from answering | `status survives a backup directory that does not answer` |
| ✅ | R-BKP-29 | Every command that reads the backup directory answers within a bound, and names a directory that did not rather than reporting none | `listing the backups survives a directory that does not answer`, `a directory that does not answer is not reported as no backups` |

## Open questions

- Whether a copy is ever taken automatically before an update as well as before a restore.
- Whether an owner may keep copies of one agent rather than of the whole install.
- What a restore does when the copy holds an agent whose name is now taken by a different one.
- Whether anything should verify a copy can still be read without putting it back.
