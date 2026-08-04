# The command surface

Six operations, and every one of them works. There is no "coming soon" list: a verb rundesk cannot
perform is a verb rundesk does not have.

```sh
rundesk status                            # the version, where the install is, and every configured value
rundesk version                           # the version, and whether it is out of date
rundesk configure [--<setting> <value>]   # change what this install is configured with
rundesk update                            # move to the newest release, or say it is up to date
rundesk uninstall --confirm [--purge]     # remove rundesk; --purge also takes the data
rundesk install [--source <dir>] [--bin-dir <dir>]   # what install.sh runs
```

Ask `rundesk --help` rather than this page when the two disagree — the command is generated from
nothing and describes itself.

## status

Answers *how rundesk is*. Takes no flags.

```console
$ rundesk status
WHAT              IS
version           0.37.0
home              /Users/you/.rundesk
program           /Users/you/.rundesk/app (installed)
data              /Users/you/.rundesk/data
backups           /Users/you/.rundesk/backups
projects          /Users/you/.rundesk/projects
fit to run        yes
backup_enabled    yes
backup_retention  7
command_link      /Users/you/.local/bin/rundesk
last_updated_at   2026-08-04T20:48:04Z
migration         nothing to carry — this release ships no migration steps
update_enabled    yes
update_time       03:00
```

`last_updated_at` is when a version last actually arrived — the install, or an update that really
moved. A run of `update` that finds nothing newer does not touch it, so the answer does not drift to
"just now" every time you check. Which version that was is `rundesk version`, so it is not repeated
here.

`program` says which copy of the code answered and whether it is this root's own install or a
checkout — running a checkout against an install's data is an ordinary thing to do by accident, and
this is where you see it. Exits non-zero when rundesk cannot run here.

## version

Reports the version and checks whether a newer one has been published. The check is not optional:
the reason anybody asks a program its version is to find out whether it is the one they should be
running.

```console
$ rundesk version
rundesk 0.37.0
        0.37.0: UP TO DATE
```

**Being unable to ask is never reported as being up to date.** If GitHub cannot be reached the line
says `UNKNOWN` and goes to stderr, so it cannot be mistaken for the answer. The command still exits
`0`, because the question asked — what version is this — was answered from the machine itself.

## configure

Shows what the install is configured with, or changes it.

```console
$ rundesk configure
SETTING           IS     SET IT WITH
backup_enabled    yes    rundesk configure --backup-enabled <value>
backup_retention  7      rundesk configure --backup-retention <value>
update_enabled    yes    rundesk configure --update-enabled <value>
update_time       03:00  rundesk configure --update-time <value>

$ rundesk configure --backup-retention 30 --update-time 04:30
backup_retention is now 30
update_time is now 04:30
```

The flags are generated from the configuration, so a setting a release starts offering is settable
the day it lands. Yes-or-no values accept `yes/no`, `true/false`, `on/off` and `1/0`.

**Naming two settings and getting one wrong changes neither.** Half-applied configuration leaves an
install in a state nobody typed.

How far the install has been carried (`migration`) is shown by `status` but is not settable: setting
it by hand would make rundesk skip or repeat a migration step.

## update

Moves this install to the newest published release, or says it is already on it.

```console
$ rundesk update
0.37.0: OUT OF DATE — v0.38.0 is available, run: rundesk update
        installing v0.38.0
rundesk updated to v0.38.0
        what changed: https://github.com/rundesk-ai/rundesk-cli/releases/tag/v0.38.0
```

Takes no flags. The order is chosen so the failure that cannot damage anything happens first: ask,
then fetch to a temporary directory, then swap. The swap stages every entry and renames them into
place, putting back what was there if any part fails — so an interrupted update leaves the install on
the release it was, never on neither.

`data/` is never touched by an update.

**Being on the newest release is not the same as being settled on it.** An update interrupted between
replacing the files and settling — a machine that slept, a terminal that closed — leaves an install
whose code is current and whose configuration and migrations belong to the release before it. So
`rundesk update` settles the install even when it reports `UP TO DATE`; everything it does is
idempotent, and running it again is how you finish an update that stopped halfway.

## uninstall

`--confirm` is required. Without it, the command says exactly what it would take and what it would
keep, and removes nothing.

```console
$ rundesk uninstall
uninstall: this would remove rundesk from /Users/you/.rundesk
        take   the command, and /Users/you/.rundesk/app
        keep   /Users/you/.rundesk/data
        keep   /Users/you/.rundesk/backups
        nothing was removed. To go ahead:
        rundesk uninstall --confirm
```

Confirmation is a flag rather than a typed answer at a prompt, because this has to behave the same
when nobody is watching: a prompt in a script is a command that hangs, and one that assumes "yes"
with no terminal is worse than no prompt at all.

What it takes, one named thing at a time, never a sweep:

- the PATH link — **only where it points into this install's own `app/`**, so a second install on the
  machine keeps its command
- `app/`, whole, unless it looks like somebody's checkout
- `data/`, **only with `--purge`**
- `backups/` — **never.** Not "not by default": there is no argument to this command that reaches
  them, and the code that removes things does not name the directory at all.

A removal that did not happen is reported as a failure. That is the whole point of the command.

## install

What `install.sh` runs after it has fetched a copy. Usable by hand from a checkout:

```sh
./rundesk install --bin-dir ~/.local/bin
```

It places the program, lays down the directories and their notes, writes or fills in the
configuration, carries the migrations, links the command, and then **proves the installed command
answers** — an installer that reports success without checking has told somebody their machine is
ready when it is not.

It proves it with `status` rather than `version`, so the proof is answerable from the machine alone.
`version` asks GitHub, and an install that fails because GitHub is slow has reported a failure it did
not earn — the mirror of the mistake this whole command is built to avoid. `status` also refuses when
the interpreter behind the link is too old, which is exactly the install that looks finished and
cannot run.

## Exit codes

| Code | Means |
|---|---|
| `0` | it was done |
| `1` | it was attempted and did not work |
| `2` | the command line itself was wrong — a typo, an unknown verb, a bad flag |
