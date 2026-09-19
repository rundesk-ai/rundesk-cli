+++
title = "Installing"
subtitle = "putting Rundesk CLI on a machine, moving it to a newer release, and taking it away"
status = "draft"
intent = """
Installing exists so that one command leaves a working `rundesk` on a machine, and so that moving to a
newer release or removing the program never costs an owner what their agents hold. An install should never
be left half replaced, and removing the program should never remove the copies.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Bootstrap", value = "install.sh", cite = "bootstrap" },
  { label = "Commands", value = "rundesk install, rundesk update, rundesk uninstall", cite = "verbs" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Oldest Python accepted", value = "3.9", cite = "bootstrap" },
  { label = "Longest an update may settle", value = "5 minutes", cite = "settle" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Release archive", value = "no checksum or signature", missing = true },
  { label = "A program tree holding .git", value = "never removed", cite = "removal" },
  { label = "Copies", value = "survive removal, including a purge", cite = "removal" },
]
+++

One command puts Rundesk CLI on a machine: `install.sh` finds a Python, fetches a release and then hands
every decision to the copy it fetched.[^bootstrap] Three verbs place it, move it forward and take it
away.[^verbs] Where everything lands is described on [the install root](install-root.md).

## Install

The script takes the first Python it finds at 3.9 or newer, and stops with
`rundesk needs python3.9 or newer, and this machine has none` when the machine has none.[^bootstrap] Run
from inside a checkout it installs that checkout; otherwise it reads the newest published tag and
downloads it.[^bootstrap]

Installing places the program, puts `rundesk` on a path and then **runs the installed command to prove it
answers** before reporting success.[^install] It proves it with `status` rather than `version`, so the
proof still works with the machine offline.[^install] A path that is not on the owner's search path is
pointed out rather than edited into a shell profile.[^install]

Installing over an install whose agents are still up becomes an update instead, so a live machine is never
torn down under its own gateways.[^install]

## Update

An update keeps three answers apart: nothing is published, the newest release could not be asked for, and
the install is behind.[^release] **It refuses to move when it could not ask**, rather than assuming it is
current.[^update] Being on the newest release is not the same as being settled on it, so an install
already on the newest release still finishes carrying itself forward.[^update]

Files are swapped one at a time, each new one put in place beside the old and only then exchanged, and put
back in reverse if any step fails.[^swap] Where putting them back also fails, the install says plainly
that it is neither release and must be installed again.[^swap]

Carrying the install forward is handed to a fresh copy of the release that just landed, because the
process doing the update is still running the old one.[^settle]

The archive is checked for the shape of a Rundesk CLI tree and for any path that would escape the
directory it unpacks into.[^archive] Nothing checks a checksum or a signature. {missing}

## Removal

Removing takes back every agent's job, removes the command link only where it points into this install,
and removes the program — unless the program tree holds a `.git` directory, which Rundesk CLI will not
delete.[^removal]

The data goes only when `--purge` asks for it, and a confirmed purge must also name the root, because an
environment variable alone is not an explicit target for something irreversible.[^removal] **The copies
are never removed, whatever is asked.**[^removal]

[^bootstrap]: `install.sh` — `find_python()` takes the first interpreter at 3.9 or newer and prints the
    refusal; the fetch block installs a checkout when it is in one and otherwise reads the newest tag from
    the releases redirect; the final block hands over to `install --source`.
[^verbs]: `src/rundesk/cli.py` — `_register_install()` declares `--source` and `--bin-dir`,
    `_register_update()` declares `--continue`, and `_register_uninstall()` declares `--confirm`,
    `--purge` and `--root`.
[^install]: `src/rundesk/commands/install.py` — `cmd_install()` places the tree, links the command and
    calls `_answers()`, whose docstring says `status` is used because the question must be answerable
    offline; `_say_if_unreachable()` points out a path not on `PATH`; `_guarded_update()` runs an update
    when a gateway is not offline.
[^release]: `src/rundesk/lifecycle/release.py` — `latest_published()` and `described()` keep
    `NO RELEASES`, `UNKNOWN` and `OUT OF DATE` apart, and the module docstring states the three answers are
    never collapsed.
[^update]: `src/rundesk/commands/update.py` — `_cmd_update()` fails when the release could not be asked
    for, and settles even when the installed release is not older.
[^archive]: `src/rundesk/commands/update.py` — `_brought_down()` looks for a tree `tree.is_rundesk()`
    accepts; `src/rundesk/utils/archives.py` — `unpacked()` refuses a member escaping the directory.
[^swap]: `src/rundesk/lifecycle/tree.py` — `replace()` stages each entry and exchanges it, and
    `_put_back()` reverses the run, raising `HalfReplaced` when that also fails.
[^settle]: `src/rundesk/commands/update.py` — `settled_by_the_new_release()` runs the settling step under
    a fresh interpreter, bounded by `SETTLE_SECONDS`, and the module docstring gives the reason.
[^removal]: `src/rundesk/commands/uninstall.py` — `_confirmed_uninstall()` takes back the jobs, removes
    the link and the program, and lists the copies as left; `cmd_uninstall()` requires `--root` with a
    confirmed purge; `src/rundesk/lifecycle/tree.py` — `remove()` refuses a tree holding `.git`.
