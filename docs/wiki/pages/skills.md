+++
title = "Skills"
subtitle = "the three catalogs every install has, adding another, and granting one to an agent"
status = "draft"
intent = """
A skill exists so that an agent is taught something once and every agent that needs it can be given the
same thing. Adding a catalog should be one command against an address the owner can read, and a catalog
that fails to update should leave the working one in place.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk skills list, catalogs, install, update, remove, grant, revoke, profiles, configure, forget, doctor", cite = "commands" },
  { label = "Address", value = "<catalog>/<skill>", cite = "library" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Catalogs every install has", value = "3", cite = "three" },
  { label = "Skills shipped in the release", value = "4", cite = "bundled" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "What a catalog holds", value = "found by reading it, never listed in a manifest", cite = "library" },
  { label = "Source", value = "a GitHub repository, or a directory on this machine", cite = "fetch" },
  { label = "managing-rundesk", value = "held by every agent, and cannot be revoked", cite = "floors" },
]
+++

A skill is something an [agent](agents.md) is taught, and a catalog is a set of them under one
name.[^library] Eleven verbs add a catalog, grant a skill and set how it is configured.[^commands] A
catalog may also declare a [team](skills/teams.md).

**A catalog's description never lists what it holds.**[^library] The skills are found by reading the catalog, so a
catalog cannot claim a skill it does not carry.[^library]

## Catalogs

Three catalogs are always present and cannot be removed.[^three]

| Catalog | Where it comes from |
|---|---|
| `rundesk` | inside the release, replaced out of it on every update[^three] |
| `rundesk-skills` | fetched from GitHub, and moves independently of the release[^three] |
| `local` | the owner's own, and never fetched[^three] |

The release carries four skills: delegating work, managing GitHub, managing this install, and writing a
skill.[^bundled]

## Adding one

A catalog comes from a GitHub repository or a directory on this machine.[^fetch] A fetch that finds
nothing changed since last time does no work.[^fetch]

The whole catalog is read and checked in a temporary place first, and **every broken skill is reported at
once** rather than one per attempt.[^fetch] A catalog holding no skill is refused.[^fetch] Whether an
update is a real change is decided by what the catalog contains, never by its version number, so a
catalog that forgot to raise its version is still updated.[^fetch]

**A failed update leaves the working catalog in place.**[^fetch] Catalogs are refreshed only after a new
release has already landed, each on its own, so one deleted repository cannot fail an update.[^refresh]

## Grants

Granting a skill puts it in the agent's own skills directory, and that entry *is* the grant — there is no
separate record to fall out of step.[^grants] A grant normally points at the catalog's copy; granting it
under a different name makes a copy instead, renamed so the agent sees the name asked for.[^grants]

Each granted skill is linked into every place the agent's providers look for one, one skill at a time, and
only links Rundesk CLI made are ever cleaned up.[^grants]

Two skills are set by the product rather than the owner: every agent holds the skill for managing this
install and cannot revoke it, and the delegating skill is held while the agent may hand work to
another.[^floors]

[^commands]: `src/rundesk/commands/skills.py` — `register()` declares the eleven verbs.
[^library]: `src/rundesk/skills/library.py` — `DECLARED` names the file a skill declares itself in,
    `ADDRESS` gives the address form, `found()` reads the catalog rather than a list, and the module
    docstring states a manifest does not name its skills.
[^three]: `src/rundesk/skills/library.py` — `BUNDLED`, `DEPENDED` and `MINE`;
    `src/rundesk/skills/catalogs.py` — `may_be_removed()` and `what_stays()`, and `place_bundled()`,
    which is given no fetcher and so cannot reach the network.
[^bundled]: `src/skills/manifest.json` — the catalog's name and description;
    `src/skills/delegating-work/SKILL.md`, `src/skills/managing-github/SKILL.md`,
    `src/skills/managing-rundesk/SKILL.md` and `src/skills/writing-skills/SKILL.md`.
[^fetch]: `src/rundesk/skills/catalogs.py` — `source_trouble()` accepts a GitHub repository or a local
    directory, `_brought_down()` returns nothing when the source reports no change, `_checked()` refuses
    every broken skill at once and a catalog holding none, `brings_a_change()` decides on contents, and
    `_swapped()` exchanges the trees and records the fetch marker last so a failure leaves the old tree
    readable.
[^refresh]: `src/rundesk/skills/catalogs.py` — `refresh()` checks each catalog inside its own guard after
    the release has landed.
[^grants]: `src/rundesk/skills/grants.py` — the module docstring states the entry is the grant, `_placed()`
    makes the link, `_copied()` and `_renamed()` handle a renamed grant, and `presented()` links into each
    of `VENDOR_ROOTS` and prunes only links Rundesk CLI made.
[^floors]: `src/rundesk/skills/library.py` — `REQUIRED` and `DELEGATING`;
    `src/rundesk/skills/grants.py` — `required_reconciled()`.
