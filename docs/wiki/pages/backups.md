+++
title = "Backups"
subtitle = "the contents of a copy, when one is taken, and putting one back"
status = "draft"
intent = """
Backups exist so that an owner can undo a bad migration, a wrong restore or a lost agent without losing
the work their agents have done. A copy should survive removing Rundesk CLI itself, and no copy should
ever be half written.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk backups save, restore, set-location", cite = "commands" },
  { label = "Location", value = "backups, beside the data", cite = "location" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Copy name", value = "the moment it was taken, in UTC", cite = "named" },
  { label = "Copies held", value = "set by the owner, 7 by default", cite = "retention" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "A copy", value = "the whole of the data, never part of it", cite = "whole" },
  { label = "A half-written copy", value = "never left under a copy's name", cite = "whole" },
  { label = "Removing Rundesk CLI", value = "leaves every copy", cite = "survive" },
  { label = "A copy", value = "holds usable credentials", cite = "secrets" },
]
+++

A copy holds everything Rundesk CLI keeps for the owner: every agent, its records, its settings and its
sealed values.[^whole] **Copies live outside the data they protect and survive removing the program,
including a purge**, because a copy the uninstaller takes with it is worth nothing.[^survive]

## Contents

A copy is the whole of the data under a name giving the moment it was taken, in UTC with hyphens where a
clock has colons, because a colon in a filename means something else to some tools.[^named]

Each agent's records are copied through the database's own snapshot facility from a read-only connection,
so a copy taken while an agent is working is still readable.[^whole] Three things are deliberately left
out: the credential homes the providers own, a half-finished update's intent, and a handoff waiting to
resume.[^whole] The `projects/` directory is not copied either.[^survive]

**A copy holds usable credentials** whenever the install has sealed values, so it deserves the same care
as the install.[^secrets]

## Timing

`rundesk backups save` takes one now.[^commands] An update takes one on its own **immediately before a
migration carries the install forward**, and only when the owner has copies switched on; if that copy
cannot be taken, the update stops rather than migrating without a way back.[^before] A restore takes one
of what it is about to replace, so restoring the wrong name costs a command rather than everything.[^back]

Every copy is built in a private place and only given its real name once it is complete and verified, so
**nothing under a copy's name is ever partial**.[^whole]

## Putting one back

`rundesk backups restore <name> --confirm` swaps the data for the copy.[^commands] A copy may have been
taken on an older release, so a restore carries what it restored forward before finishing.[^back]

Restoring is the way back from a bad migration; there is no reverse migration step.[^before]

## Location

`rundesk backups set-location <path>` moves where copies live — every copy is put in the new place first,
then removed from the old.[^location] A copies directory pointing at a disk that is not plugged in is
reported as unreachable rather than as having no copies.[^location]

Old copies are removed only when a run prunes them, and a copy that cannot be read is never counted as
a copy worth keeping.[^retention]

[^commands]: `src/rundesk/commands/backups.py` — `register()` declares `save`, `restore` and
    `set-location`, and `cmd_backups()` lists when no verb is named.
[^whole]: `src/rundesk/lifecycle/backups.py` — the module docstring states a copy is the whole of the
    data; `save()` builds it in a private directory and renames it in only once `_verified()` passes;
    `_a_snapshot()` copies each agent's records through the database's own snapshot from a read-only
    connection; `_without_provider_accounts()`, `_without_update_intents()` and
    `_without_lifecycle_handoffs()` leave the three out.
[^named]: `src/rundesk/lifecycle/backups.py` — `WHEN` gives the name its shape and its comment gives the
    reason for hyphens, and `named()` adds a counter when two copies land in one second.
[^survive]: `src/rundesk/core/paths.py` — `backups()`, whose docstring states copies survive removal
    including a purge; `src/rundesk/commands/uninstall.py` — `_confirmed_uninstall()` lists them as left;
    `src/rundesk/lifecycle/home.py` — `PROJECTS_NOTE` states the projects directory is not copied.
[^secrets]: `src/rundesk/lifecycle/home.py` — `BACKUPS_NOTE` states a copy holds usable credentials when
    the install has sealed values.
[^before]: `src/rundesk/commands/update.py` — `_kept_before_carrying()` takes a copy only when a migration
    is outstanding and copies are switched on, raises `CouldNotKeep` rather than carrying without one, and
    its docstring states the restore command is the way back rather than a reverse step.
[^back]: `src/rundesk/lifecycle/backups.py` — `restore()` takes a copy of what it replaces first and then
    `_settle()` carries the restored data forward; the module docstring gives the reason.
[^location]: `src/rundesk/lifecycle/backups.py` — `relocate()` copies to the new place before removing
    from the old, and `_reachable()` reports an unplugged disk rather than answering that there are no
    copies.
[^retention]: `src/rundesk/lifecycle/backups.py` — `prune()` refuses a count below one and only counts a
    copy `restorable()` accepts; `src/rundesk/core/config.py` — `INITIAL` sets the default kept.
