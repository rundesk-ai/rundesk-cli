---
id: PLG
name: A plugin somebody else wrote
last_verified: 2026-07-28
---

## What this is

Software a third party publishes, installed onto this copy of rundesk from a versioned
release, shared by every agent on the machine, and moved forward by the same update that
moves rundesk. It contributes files an agent runs and a brain reads; it is never code
rundesk loads.

## Why it exists

- An owner can extend what every agent can do without writing it, and without editing
  rundesk.
- What a stranger publishes can be updated, held back and removed, which a file dropped in
  a directory by hand cannot.
- Nothing a stranger ships can take an owner's agents down, replace an owner's own work, or
  cost an owner what a plugin has kept.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-PLG-1 | A plugin declares its name, its version and what it provides, in one manifest read rather than guessed at | `a plugin declares its name its version and what it provides`, `a directory with no manifest is not a plugin`, `a plugin providing nothing at all is refused` |
| ✅ | R-PLG-2 | Everything about a plugin is checked before anything is written where an owner would have to clean it up | `a plugin that is refused leaves no directory behind to clean up` |
| ✅ | R-PLG-3 | A manifest format this copy of rundesk does not understand is refused rather than read hopefully | `a manifest format from the future is refused rather than guessed at`, `a manifest that does not say which format it is written in is refused` |
| ✅ | R-PLG-4 | A name no brain and no shell would accept is refused | `a name no brain or shell would accept is refused`, `a name no brain would accept is refused before anything is written` |
| ✅ | R-PLG-5 | A command that could never run is refused on the machine of whoever wrote it | `a command that is not executable is refused before anybody installs it` |
| ✅ | R-PLG-6 | A manifest may name only files inside the plugin that named them | `a command path pointing outside the plugin is refused`, `an absolute command path is refused` |
| ✅ | R-PLG-7 | A skill a plugin ships is held to the rules a brain's loader holds an owner's to (R-AGT-27) | `a skill no brain would index is refused with the reason` |
| ✅ | R-PLG-8 | A plugin declares the credentials it needs by name, and a manifest carrying a value is refused | `a manifest carrying a credential value is refused`, `a credential is declared by name and whether it is needed` |
| ✅ | R-PLG-9 | A plugin becomes visible to any agent only once everything that could fail has worked | `a plugin that is not installed leaves nothing of itself behind` |
| ✅ | R-PLG-10 | A plugin's records are made and moved by its own numbered steps, on its own version (R-MIG-2, R-MIG-13, R-MIG-14, R-MIG-15) | `the records version is read off the steps that ship`, `steps that cannot be ordered are refused before anything is installed`, `the records a plugin keeps are made by running its steps`, `a plugin with no steps is installed without records being made` |
| ✅ | R-PLG-11 | A plugin installs from a directory or an archive on this machine, and a published release is reached through the same path | `a plugin installs from a directory on this machine`, `a plugin installs from an archive`, `a path on this machine is never mistaken for a repository` |
| ✅ | R-PLG-12 | An archive that would write outside where it is unpacked is refused (R-UPD-24) | `an archive that would write outside where it is unpacked is refused` |
| ✅ | R-PLG-13 | A plugin declares which versions of rundesk it fits, and a range that cannot be judged is refused rather than assumed | `a plugin that names no range fits anything`, `a range is judged against the version it is given`, `a range this cannot judge is refused rather than guessed` |
| ✅ | R-PLG-14 | A plugin is judged against the rundesk about to run, and one that does not fit is held back rather than dragged forward | `a plugin needing a newer rundesk is refused with both versions named`, `a release needing a newer rundesk is not dragged into this one`, `an installed plugin that no longer fits is held back before it is moved` |
| ✅ | R-PLG-15 | A plugin is moved after every agent's records and before anything is back up, and nothing it does can fail that update | `a plugin that cannot be moved never fails the update it rides`, `a machine with no plugins does nothing and says nothing`, `a plugin whose manifest cannot be read is held back rather than skipped`, `plugins are moved after every agents records and before anything is back up`, `an update lands even when every plugin is held back`, `a plugin step that raises is not something an update has to survive`, `an update with nothing newer still moves plugins when it mends` |
| ✅ | R-PLG-16 | Taking rundesk off a machine takes away every link a plugin stood, whatever it kept (R-RM-7) | `taking rundesk off pulls every link a plugin stood` |
| ✅ | R-PLG-17 | One install puts a plugin's command within reach of every agent, with no step for each | `a plugin puts its command on every agents path`, `one install serves every agent through one directory` |
| ✅ | R-PLG-18 | A plugin's skills stand in the one library, and are granted and revoked as any other are | `a plugin puts its skills in the library every agent reads`, `a skill a plugin ships can be granted and then revoked` |
| ✅ | R-PLG-19 | What a plugin stands in a shared directory survives the install being moved or copied | `a link a plugin stands is relative so the install can be moved` |
| ✅ | R-PLG-20 | Nothing a plugin does can replace or remove something the owner put there, whatever it is called | `an owners own script of the same name refuses the install`, `an owners own skill of the same name refuses the install`, `removing touches nothing an owner wrote that shares a name` |
| ✅ | R-PLG-21 | Installing over a plugin already installed is refused, and says what to do instead | `installing the same plugin twice says to update it instead` |
| ✅ | R-PLG-22 | A release tagged differently from the version its manifest declares is refused (R-UPD-9) | `a release tagged differently from what it declares is refused`, `a release tagged differently from its manifest is not taken` |
| ✅ | R-PLG-23 | Where each plugin came from and at which tag is recorded, and unreadable provenance is never written back as empty | `where a plugin came from and at which tag is recorded`, `a ledger that cannot be read is never written back as empty` |
| ✅ | R-PLG-24 | What a plugin's own steps did is left where somebody looking for it would read it, and never in an agent's account | `what a plugins migration did is left in its own log not an agents` |
| ✅ | R-PLG-25 | Every agent reaches one copy of what a plugin keeps | `every agent reaches one copy of what a plugin keeps` |
| ✅ | R-PLG-26 | A plugin moves to what is published, and stays where it is when that is not newer | `a newer release replaces the one installed`, `a release that is not newer leaves everything where it was` |
| ✅ | R-PLG-27 | What a plugin keeps survives every update of that plugin | `what a plugin keeps survives being moved forward` |
| ✅ | R-PLG-28 | A release that cannot be moved to leaves the plugin on the version that worked | `a new release whose step fails stays on the version that worked` |
| ✅ | R-PLG-29 | What every agent can reach agrees with what is installed and fit | `a plugin held back is taken off every agents path`, `a release that stops providing a command takes it off the path` |
| ✅ | R-PLG-30 | A release that no longer calls itself the plugin installed is refused | `a plugin that calls itself something else now is refused` |
| ✅ | R-PLG-31 | A plugin held back is let go the moment whatever held it back is settled | `a plugin that fits again comes back by itself` |
| ✅ | R-PLG-32 | Removing a plugin takes it away from every agent at once | `removing a plugin takes its command off every agents path` |
| ✅ | R-PLG-33 | What a plugin kept outlives its removal unless removing it was asked to take that too | `what a plugin kept stays unless somebody asks for it to go`, `asking for it to go takes the records as well`, `removing one takes it off and says what it kept` |
| ✅ | R-PLG-34 | Only a directory rundesk laid down can be removed, and a name that is a path is refused before it is joined to anything (R-AGT-26) | `a name that is a path is refused before it is joined to anything`, `a plugin nobody installed cannot be removed`, `removal never reaches a directory rundesk did not lay down` |
| ✅ | R-PLG-35 | A new plugin can be started from something that already installs | `the plugin that is scaffolded is one that installs`, `the template is renamed throughout rather than only in its manifest`, `scaffolding over something that is already there is refused`, `a new plugin is written ready to install` |
| ✅ | R-PLG-36 | An owner can see what is installed, at which version, from where, and which are held back | `a plugin that is there and broken is listed with why`, `a directory rundesk did not lay down is not a plugin`, `a machine with no plugins says so and says how to get one`, `where plugins are kept is printed and nothing else`, `what is installed is listed with its version and where it came from` |
| ✅ | R-PLG-37 | An owner is shown what a plugin declares before any of it is written, and confirms before it lands | `installing without confirming shows what it would do and writes nothing`, `confirming is what installs it` |
| ✅ | R-PLG-38 | A plugin verb that did not do the work says so and exits non-zero (R-CMD-4) | `something that is not a plugin is refused and exits non zero`, `removing one nobody installed says so rather than reporting success` |
| ✅ | R-PLG-39 | Whether something is a plugin anybody could install is answerable before it is published | `checking a directory says whether anybody could install it`, `checking something that is not one names what is wrong with it` |
| ✅ | R-PLG-40 | Every directory a plugin touches is resolved through the one module that owns it, so a redirected install cannot reach the owner's own | `every directory a plugin touches follows the override it was given` |

| ✅ | R-PLG-41 | A skill a plugin ships is named as that plugin's rather than as the owner's | `a skill a plugin shipped names the plugin rather than saying yours` |

| ✅ | R-PLG-42 | A plugin installed again after a removal picks the records that removal kept back up | `installing again after a removal picks the kept records back up` |

| ✅ | R-PLG-43 | A new plugin is written whole or not at all, whatever its name is made of | `a hyphenated name still produces credential names a shell can export`, `a scaffold that fails leaves nothing half written behind` |

| ✅ | R-PLG-44 | An update says what it moved as one ordered list: rundesk first, then every plugin, each with both versions and its outcome | `every plugin gets a row whether or not anything happened to it`, `what moved is listed in order with rundesk first`, `the list comes after the release it is about`, `an owner with no plugins sees exactly what they saw before`, `the version being left survives the handover to the new release`, `rundesks own row shows where it came from and where it got to` |
| ✅ | R-PLG-45 | An install that has never had a plugins directory updates exactly as it always did | `an install that has never had a plugins directory updates as it always did` |

## Open questions

- Whether a plugin should be able to ship a provider or channel adapter, which would put a
  stranger's program in the run path of every turn rather than only in an agent's own.
- What a plugin that two owners want at two different versions on one machine means, given
  a plugin is installed once and shared.
- Whether a plugin held back should be reported by `doctor` as well as by `plugins`, and
  whether anything should report it without being asked.
- Whether `rundesk plugins update`, run on its own, should take the same window `rundesk
  update` does. It does not today, so an owner running it by hand can move a plugin's
  shared records while agents are live — the step is still one transaction and a command
  that meets records it does not understand refuses rather than reads them, but the
  guarantee is weaker than the one an update gives.
- What becomes of what a plugin kept when the plugin is never reinstalled — nothing collects
  it today, and nothing knows how long it has been there.
