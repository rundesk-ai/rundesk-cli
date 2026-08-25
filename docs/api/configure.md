# Configuration, values, and copies

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

Changing `update_enabled` or `update_time` immediately reconciles the root-specific launchd job.
The settings are saved atomically first; if launchd cannot be reconciled, `configure` exits non-zero
and says that the settings were saved, so repeating the command is an honest idempotent repair.
Disabling removes the job and its generated shim; changing the time replaces the loaded definition.

How far the install has been carried (`migration`) is shown by `status` but is not settable: setting
it by hand would make rundesk skip or repeat a migration step.

## env

The values rundesk hands to what it talks to — a Discord bot's token, a Slack app's key. An owner
places one once and everything rundesk starts finds it, with nobody having exported anything in a
shell a gateway will never see.

```console
$ rundesk env set DISCORD_TOKEN
DISCORD_TOKEN: 
DISCORD_TOKEN is set — MTIxxxxxxxxken

$ rundesk env list
values in /Users/you/.rundesk/data/secrets
NAME             VALUE
DISCORD_TOKEN    MTIxxxxxxxxken
SLACK_BOT_TOKEN  not set
```

**A value is never typed as an argument.** There is no `env set KEY value` and no flag that takes
one: `argv` is in your shell's history the moment you press return, and visible in `ps` to every
other user on the machine while the command runs. It is read from the terminal without echoing, or
from a pipe when something else is driving — `printf %s "$TOKEN" | rundesk env set KEY` — so it
never becomes a command that hangs in a script either.

**Nothing ever shows a whole value**, to you or to anything else. What is shown is three characters
at each end; a short value shows nothing at all, because six characters of eight is most of it, and
the width between is fixed so the shape says nothing about the length.

`check` exits non-zero when a value is not set, so `rundesk env check DISCORD_TOKEN && …` does the
right thing in a shell. `unset` empties a name and **leaves the name**, so a listing shows an
integration that was configured here and is now switched off, rather than one that was never set up.

Where these are kept and what protects them is [`layout.md`](../concepts/layout.md) — the short version is that
the files are yours alone, each value is sealed on disk with a key kept beside it, and a backup
carries both. Protect backup storage as credential-bearing data.

## backups

The copies of `data/`. With no sub-verb it lists them, newest first, because listing is what somebody
wants nine times in ten.

```console
$ rundesk backups
copies in /Users/you/.rundesk/backups
BACKUP
2026-08-04T03-00-00Z.zip
2026-07-28T03-00-00Z
```

Where they are kept is printed even when there are none. "No copies" and "no copies *here*" are
different things to learn.

**Nothing there, and not being able to look, are different answers.** An install nobody has copied
anything on says so. A `backups/` that cannot be read — or that points at a disk nobody has plugged
in — is a failure, because answering "none yet" would tell somebody their copies are gone at the
moment they are merely unplugged, and what that person does next is act on it.

### backups save

Copies `data/` whole into one compressed ZIP, under a name that says when it was made, and says what
it is called.

```console
$ rundesk backups save
saved 2026-08-04T03-00-00Z.zip
        from   /Users/you/.rundesk/data
        in     /Users/you/.rundesk/backups
        let go of 2026-07-21T03-00-00Z.zip
```

The data is first made consistent in a private staging directory, then written beneath `data/` in an
archive with a root `manifest.json`. The manifest records the backup format and version, when it was
made, and any source file removed by supported concurrent cleanup before its turn to be copied. That
file is omitted and named in the command output rather than making every other healthy file go
uncopied. Other read errors still fail the save. The archive is verified and renamed into place only
once all of it is there, so an interruption never leaves a finished `.zip` name on a partial copy.

File and directory modes are recorded explicitly, and symbolic links remain links rather than
copies of what they point at.

The copy includes `data/secrets/`: sealed values and the key that opens them. Treat backup storage as
credential-bearing data. The files remain private, but sealing does not protect a complete copy from
somebody who can read it.

It then lets go of the oldest past `backup_retention`. **This is the only thing in rundesk that
removes a copy**, it considers only names that are copies, and a copy it could not remove is said out
loud — but neither changes the exit code, because the operation asked for was a copy and the copy is
there.

### backups restore

`--confirm` is required, and a copy of what is there now is taken **before** anything is replaced —
so restoring the wrong name costs a command rather than everything you had. Without `--confirm` it
says exactly what it would do and does none of it.

```console
$ rundesk backups restore 2026-07-28T03-00-00Z.zip --confirm
        kept 2026-08-04T03-00-00Z.zip — a copy of /Users/you/.rundesk/data as it was
restored 2026-07-28T03-00-00Z.zip
        into   /Users/you/.rundesk/data
```

The copy that was kept is named before the swap starts rather than in a summary afterwards, because
every failure from that point on is one where knowing the name is the way back.

A current archive is checked completely before a safety copy or live-data change: its manifest,
single `data/` root, member names, entry types, modes, and duplicate/path-escape hazards must all be
valid. A copy with no readable `config.json` is refused, as is one whose secret store contains a
link. Existing v0.40 directory copies remain restorable and appear in the same chronological list as
new ZIPs. Pre-v0.40 `rundesk-data-*.zip` archives used a different format and are explicitly refused;
this release does not guess that they are compatible or report them as missing.

**A copy older than this release is carried forward once it lands.** The copy holds the migration mark
it had when it was taken, so the steps that run are exactly the ones it missed — and never the ones it
already had. **Being back is not the same as being settled**: if a step cannot finish, the command
says so and exits non-zero, because the data really is the copy that was asked for and really has not
been carried onto this release. `rundesk update` settles an install and is safe to run again.

### backups set-location

Moves the copies to another directory and links `backups/` at it.

```console
$ rundesk backups set-location /Volumes/Big/rundesk-backups
        moved 2026-08-04T03-00-00Z.zip
rundesk keeps its copies in /Volumes/Big/rundesk-backups
        linked /Users/you/.rundesk/backups → /Volumes/Big/rundesk-backups
```

A link rather than a setting, on purpose: `RUNDESK_HOME` stays the only location rundesk reads, so
the copies can live anywhere without there being a second place to look.

Everything is copied to the new place **first**, and taken from the old one only once every copy is
confirmed to be there — so a move that dies partway is a tidying job and never a loss. Everything is
carried, not only the copies: a move that left your own files behind in a directory it then replaced
with a link would be a move it did not make.

## permissions

What **macOS** lets rundesk do. Not what a brain's tool permissions allow — every provider adapter
already runs its CLI with that switched off, and this reports on none of it.

```console
$ rundesk permissions
as of 2026-08-08T15:40:55Z, about gateway (/opt/homebrew/…/Python.app/Contents/MacOS/Python)

PROBE                  IS
control/accessibility  blocked
control/post-events    blocked
screen/grant           ready
files/full-disk        blocked
shell/admin            not checked
permissions: 3 still not allowed — rundesk permissions check to prove them again
```

The bare verb **runs nothing**: it says what the last check found, so *what is still not allowed* can
be asked without touching the machine. A probe nobody has run says `not checked` rather than
borrowing a verdict.

**An answer belongs to a process, not to a machine.** macOS makes the nearest application bundle
responsible for a permission, so anything you start from a terminal inherits what you once granted
that terminal, while a gateway — a launchd job with no application above it — starts with nothing.
The two disagree, which is why every answer names the lineage it was proved in:

```console
$ rundesk permissions lineage
terminal — com.googlecode.iterm2
  /Applications/iTerm.app/Contents/MacOS/iTerm2 is responsible for this process
  below: …/Python ← /bin/zsh ← /Applications/iTerm.app/Contents/MacOS/iTerm2
```

**Asking from inside a turn is not reliably asking as the gateway.** Measured: `"$RUNDESK_COMMAND"
permissions check` run through a brain's tool call answered `unknown (…/codex)` and proved that
program's grants, because the tool leaves the gateway shim out of the parent chain. Read the lineage
line rather than the invocation — only a run that says `gateway` is a fact about one, and the bare
verb says so unprompted about anything stored from another lineage.

```console
$ rundesk permissions check
these answers are about this gateway (/opt/homebrew/…/Python.app/Contents/MacOS/Python)
one grant covers every agent on this machine — they are one client, not one each. The client is the
interpreter at the path above, so a `brew upgrade` of it takes the grants away with no warning and
this is what finds out

control
  accessibility  blocked     this process is not trusted for Accessibility …
                     open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
screen
  grant    ready       this process itself holds Screen Recording …
  capture  ready       the screen can be captured — a readable 8x8 image came back
permissions: 1 of 11 cannot be used by …/Python:
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
```

`check` proves them now and writes down what it found; naming a group (`control`) or one probe
(`files/full-disk`) proves only that, and leaves every other stored answer at its older timestamp.
With nothing named it proves everything needed to operate the machine; `--everything` adds the rest.
It **refuses to run at all** when it cannot work out which lineage it is in — a table of verdicts with
no process named is a claim about nobody.

Seven verdicts, one per thing there is to do: `ready`, `blocked`, `unasked`, `closed`, `absent`,
`unrunnable`, `unproven`. The last is the third state and counts as trouble — a check that proved
nothing has proved nothing. Exit `0` only when everything asked for is `ready`.

**Nothing prompts and nothing is left behind.** Every probe is a preflight or a read; where no
non-prompting way to ask exists, the probe answers `unproven` rather than guessing. The screenshot is
eight pixels of one corner and is deleted on every path — and it is not attempted at all without the
grant, because asking for one without it was measured making macOS *write* the grant.

[`permissions.md`](../concepts/permissions.md) has the whole of it, and
[`research/2026-08-08-what-this-mac-lets-a-process-do.md`](../research/2026-08-08-what-this-mac-lets-a-process-do.md)
has the measurements.
