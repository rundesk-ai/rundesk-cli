---
id: BKP
name: A copy of what the owner keeps, and how many of them stand
last_verified: 2026-09-03
---

## What this is

`backups save` and the copy an update takes before carrying make one archive of `data/` under a name
that says when it was made, verified before it is named like a copy. Retention lets go of the oldest
past `backup_retention`, and it is the only thing in Rundesk that removes one. Everything about the
copy lives in `src/rundesk/lifecycle/backups.py`; the update path reaches it from
`src/rundesk/commands/update.py`.

## Why it exists

- A copy is what somebody reaches for on the worst day they have had with this product, so a copy
  that is damaged, half-written, quietly absent, or removed while something still needs it has failed
  at the only moment it existed for.
- A backup location may be cloud-backed. Such a filesystem can list copies immediately and still
  refuse the header rewrites a ZIP writer makes, minutes into an archive; and a file it holds can be
  out of reach for a moment without being anything but a copy.
- `backup_retention` promised a bound on how many copies stand, and an install that keeps seven held
  fifty.

## Requirements

A ✅ names test methods observed to pass on 2026-09-03 on `/usr/bin/python3` (3.9.6) and Python
3.14.6, in `test_backups.py` and `test_update.py`. A ❌ is not a claim that the behavior is absent —
it is a claim that nothing here proves it.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-BKP-1 | Before any archive is built, the destination is proved able to write, reread and rename a small private file; a destination that cannot is refused naming `backups set-location`, no archive is constructed, and every existing copy stands. | `test_a_location_that_cannot_finalize_is_refused_before_archive_construction` |
| ✅ | R-BKP-2 | The archive is written forward without seeking on its destination, under a private `.incoming` name, verified there and renamed into place only when whole, so a destination that rejects a seek still receives a verified copy and a copy that did not finish is never named like one that did. | `test_a_cloud_location_that_rejects_zip_seeks_receives_a_verified_copy`, `test_a_copy_that_could_not_be_renamed_into_place_leaves_nothing_named`, `test_save_staging_cleanup_failure_leaves_no_finished_copy_or_retention_claim` |
| ✅ | R-BKP-3 | The snapshot is staged on the configured backup filesystem, so moving the backup location moves the capacity a save depends on and an exhausted system temporary directory does not fail it. | `test_relocation_keeps_large_staging_off_an_exhausted_system_temporary_directory` |
| ✅ | R-BKP-4 | Retention validates every copy before it removes any. Only the shape of the bytes makes a copy unrestorable; a copy that cannot be reached or whose validation cannot finish cleanly ends the pass with nothing removed, and the command says the copy was saved and nothing was let go. | `test_retention_archive_read_failure_preserves_every_copy_and_reports_it`, `test_retention_cleanup_failure_reports_that_no_copy_was_let_go`, `test_save_reports_the_copy_even_when_the_retention_cannot_be_read` |
| ✅ | R-BKP-5 | A successful update that took a copy before carrying applies `backup_retention` once the whole settle has succeeded, so no more restorable copies stand than the setting permits and the copy just taken is the newest kept; an update that took no copy prunes nothing. | `test_retention_is_applied_once_the_update_has_landed`, `test_an_update_that_took_no_copy_prunes_nothing` |
| ✅ | R-BKP-6 | A settle that fails lets go of no copy: the copy it names as the way back, and every older one, stand. | `test_a_failed_settle_lets_go_of_no_copy`, `test_the_copy_is_named_when_a_step_does_not_finish` |
| ✅ | R-BKP-7 | What retention could not remove is said out loud and never changes the outcome of the save or the update that ran it. | `test_save_reports_the_copy_even_when_the_retention_cannot_be_read`, `test_retention_cleanup_failure_reports_that_no_copy_was_let_go` |
| ❌ | R-BKP-8 | A real iCloud Drive location receives a verified copy and retention applies afterwards. | not proven — no cloud-backed location was used. Every destination refusal is reproduced against a stand-in filesystem. Configure `backups set-location` to an iCloud Drive directory holding many copies, run `backups save`, and confirm one verified copy landed and the inventory fell to `backup_retention`. |

## Open questions

- Whether a copy that could not be checked should be named in the listing as *cannot be read right
  now* rather than shown like any other. Today `rundesk backups` lists it and retention leaves the
  whole set alone until it can be read.
- Whether the automatic updater should say, on the owner's notified channel, when retention could
  not be applied. Today the sentence stands in the update's own output.
