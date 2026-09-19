+++
title = "Install root"
subtitle = "the directory Rundesk CLI keeps everything in, what sits inside it, and the settings it holds"
status = "draft"
intent = """
The install root exists so that everything Rundesk CLI holds on a machine sits under one directory the
owner names, and so that pointing a command somewhere else reaches none of the original. Naming that
directory should be one decision, and half a redirect should be impossible to ask for.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Variable", value = "RUNDESK_HOME", cite = "home" },
  { label = "Default", value = "~/.rundesk", cite = "home" },
  { label = "Settings file", value = "data/config.json", cite = "config" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Settings the owner sets", value = "5", cite = "settable" },
  { label = "Wait for a busy install", value = "10 seconds, or 5 minutes while a directory moves", cite = "locks" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Set and empty", value = "refused, not read as unset", cite = "home" },
  { label = "The home directory as the root", value = "refused", cite = "allowed" },
  { label = "Copies", value = "survive a purge", cite = "backups" },
]
+++

**One variable says where everything is.**[^home] `RUNDESK_HOME` names the directory, defaults to `~/.rundesk`,
and every other location is worked out from it — so there is no way to move half an install and leave the
rest behind.[^home] [Installing](installing.md) is what puts a program there.

## Location

The variable is read afresh on every command, so pointing a single command at a scratch directory does not
disturb the real one.[^home]

**A variable that is there and empty is refused, not treated as unset.**[^home] An empty value means something
tried to say where the root was and produced nothing — a script whose own variable was never set — and
reading that as an unset variable would send the command at the owner's live install at the exact moment
the owner was trying to point it elsewhere.[^home]

A root must also be somewhere it is safe to delete from later: a relative path, the top of the filesystem
and the person's own home directory are each refused.[^allowed]

## Contents

| Path | Holds |
|---|---|
| `app/` | the program, which an update replaces whole[^tree] |
| `data/` | the settings, the agents and the skill library[^prepare] |
| `data/agents/<name>/` | one agent's records, home and logs[^agent] |
| `data/skills/<catalog>/` | one skill catalog[^library] |
| `data/secrets/` | the sealed values, readable only by their owner[^secrets] |
| `backups/` | the copies, which removing Rundesk CLI never takes[^backups] |
| `projects/` | work an agent is pointed at, and the directory no copy holds[^prepare] |

Each carries a `README.md` saying what it is, rewritten on every install and update, so a person who opens
the directory is not guessing.[^prepare]

## Settings

The owner sets five things: whether copies are taken, how many to hold, how many days of turn detail to
hold, whether updates happen on their own, and what time of day they run.[^settable] Four more values are
Rundesk CLI's own record of the install and cannot be set by hand.[^settable]

The settings live under `data/` rather than beside the program, **so an update cannot reach what the owner
chose**.[^config] Reading them never writes them, and a file that cannot be read stops the command instead
of falling back to defaults — an owner who turned automatic updates off does not find them back on
later.[^config]

## Waiting

One process changes an install at a time.[^locks] A command that finds another already working waits up to
10 seconds for a small file, and up to 5 minutes while a whole directory is being moved, then gives up and
says so rather than working on a tree that is halfway somewhere else.[^locks]

## Migrations

An install records how far it has been carried forward.[^migration] Rundesk CLI ships no install migration
step yet, so a fresh install records none.[^steps] Each [agent](agents.md) is carried separately, so one
agent that cannot be moved never stops the others.[^migration]

[^home]: `src/rundesk/core/paths.py` — `home()` reads `HOME_IS`, returns `DEFAULT_HOME` when unset and
    raises `Refused` when set and empty; the module docstring states that one variable governs everything,
    that it is resolved on every call, and why an empty value is refused.
[^allowed]: `src/rundesk/core/paths.py` — `allowed()` refuses a relative path, the filesystem anchor,
    `Path.home()` and a path whose parent is itself.
[^tree]: `src/rundesk/core/paths.py` — `app()`; `src/rundesk/lifecycle/tree.py` — `place()` and
    `replace()`.
[^prepare]: `src/rundesk/lifecycle/home.py` — `directories()` names each one, `prepare()` makes them and
    rewrites each `README.md`, and `PROJECTS_NOTE` states that the projects directory is not backed up.
[^agent]: `src/rundesk/agents/directory.py` — `RECORDS`, `HOME` and `LOGS`, and the accessors `where()`,
    `records()`, `home()` and `logs()`.
[^library]: `src/rundesk/skills/library.py` — `where()` and `stands()`.
[^secrets]: `src/rundesk/core/paths.py` — `secrets()`; `src/rundesk/core/secrets.py` — `ONLY_MINE` sets
    the directory mode, and `SEALED` names the sealed form.
[^backups]: `src/rundesk/core/paths.py` — `backups()`, whose docstring states the copies survive removal
    including a purge; `src/rundesk/commands/uninstall.py` — `_confirmed_uninstall()` lists them as left.
[^config]: `src/rundesk/core/config.py` — `where()` puts the file under `data/`; the module docstring
    states an update must not reach it; `read()` fills absent values for the read alone and raises
    `Unreadable` rather than defaulting.
[^settable]: `src/rundesk/core/config.py` — `INITIAL` and `MANAGED`; `settable()` is the first without the
    second.
[^locks]: `src/rundesk/utils/locking.py` — `only_one()` takes one claim at a time and raises `Stuck` when
    the wait runs out; `WAITING_SECONDS` and `WHILE_A_DIRECTORY_MOVES` set the two waits;
    `src/rundesk/core/paths.py` — `lock()`, whose docstring states a caller derives the claim from the
    root it was handed.
[^migration]: `src/rundesk/lifecycle/migration.py` — `carry()` and `stamp_without_running()`, and the
    module docstring separating an install carried once from an agent carried per agent.
[^steps]: `src/rundesk/lifecycle/steps/__init__.py` — the directory holds no step, and `newest()` in
    `src/rundesk/lifecycle/migration.py` answers `None`.
