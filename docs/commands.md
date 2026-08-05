# The command surface

Nine operations, and every one of them works. There is no "coming soon" list: a verb rundesk cannot
perform is a verb rundesk does not have.

```sh
rundesk status                            # the version, where the install is, and every configured value
rundesk version                           # the version, and whether it is out of date
rundesk configure [--<setting> <value>]   # change what this install is configured with
rundesk agents                            # the agents this install keeps
rundesk agents add <agent> --provider <provider>        # make one
rundesk agents configure <agent> --provider <provider>  # change what is behind one
rundesk agents remove <agent> --confirm   # take one away, and everything it remembers
rundesk backups                           # the copies of what rundesk keeps for you
rundesk backups save                      # copy what rundesk keeps, now
rundesk backups restore <backup> --confirm        # put a copy back
rundesk backups set-location <path>       # keep the copies in another directory
rundesk env list                          # every value rundesk keeps, shown only as a hint
rundesk env check <key>                   # whether one is set
rundesk env set <key>                     # keep one — typed, never passed as an argument
rundesk env unset <key>                   # empty one, leaving the name
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
secrets           /Users/you/.rundesk/secrets
projects          /Users/you/.rundesk/projects
agents            /Users/you/.rundesk/data/agents — 2 agents
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

`agents` is where they stand and how many there are, in one row rather than two — the count is only
ever *of* that directory. A root nothing has been installed into, an install nobody has added an
agent to, and an agents directory that cannot be read are three different answers and not one.
Which agents they are is `rundesk agents`, so the names are not repeated here.

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

## agents

The agents this install keeps — one directory each, under `data/agents/`. With no sub-verb it lists
them, because listing is what somebody wants nine times in ten.

```console
$ rundesk agents
agents in /Users/you/.rundesk/data/agents
AGENT  PROVIDER
ada    claude
cole   openai
```

Where they stand is printed even when there are none, and an install nobody has added one to says
so rather than printing an empty table:

```console
$ rundesk agents
agents in /Users/you/.rundesk/data/agents
        no agents yet — add one with: rundesk agents add <agent> --provider <provider>
```

**An agent is a directory holding `state.db`.** Not a name in a list somewhere — so a half-made
directory and a directory somebody made by hand are not agents and are not listed as ones. An agent
whose records are there and cannot be read is listed with a provider nobody can answer for, rather
than left out: leaving it out would say the agent is gone, and what somebody does next is make a new
one over what survived.

### agents add

Makes an agent: its records, `home/`, and `logs/`. `--provider` is required.

```console
$ rundesk agents add cole --provider claude
agent cole added
        provider  claude
        home      /Users/you/.rundesk/data/agents/cole/home
        logs      /Users/you/.rundesk/data/agents/cole/logs
        records   /Users/you/.rundesk/data/agents/cole/state.db
        note      the provider is recorded and not proven — nothing in this release runs one
```

**The provider is recorded and it is not proven**, and the command says so every time. Nothing in
this release runs one: no credential is checked, no request is made, and there is no gateway to
start. An agent added with a provider nobody has ever spelled correctly looks exactly like one that
works, and a line implying otherwise would be a success this release did not earn.

All of it is built under a staged name and renamed into place once, at the end — so an interruption
leaves litter rather than a directory wearing an agent's name and not being one.

A name already taken is refused, and the refusal names the agent that is there. That includes a name
differing only by case: the volume macOS ships with cannot tell `Cole` from `cole`, so allowing both
would give two agents one `state.db` to write over each other in.

### agents configure

Changes what an agent is configured with.

```console
$ rundesk agents configure cole --provider openai
cole: provider is now openai
        the provider is recorded and not proven — nothing in this release runs one
```

**Naming nothing to change is refused rather than reported as a success.** A command that says it
worked having changed nothing teaches somebody it worked, and the next thing they do rests on a
change that never happened — the same reasoning as `configure` one level up.

### agents remove

`--confirm` is required. Without it, the command says exactly what it would take and takes none of
it, and exits non-zero: **a removal that did not happen is a failure.**

```console
$ rundesk agents remove cole
remove: this would take the agent cole from /Users/you/.rundesk/data/agents
        take   /Users/you/.rundesk/data/agents/cole/state.db — everything cole remembers, and what SQLite keeps beside it
        take   /Users/you/.rundesk/data/agents/cole/home — where cole started, and what it put there
        take   /Users/you/.rundesk/data/agents/cole/logs
        keep   anything else you put in /Users/you/.rundesk/data/agents/cole
        nothing was removed. To go ahead:
        rundesk agents remove cole --confirm
```

Confirmation is a flag rather than a typed answer at a prompt, for the reason `uninstall` gives: a
prompt in a script is a command that hangs, and one that assumes "yes" with no terminal is worse
than no prompt at all. An agent's whole memory is what this takes, and no copy of `data/` made
afterwards brings it back.

What it takes is named one thing at a time and never swept, and the agent's own directory goes only
if it is then empty — anything you left in there is kept, along with the directory holding it, and
the command says so.

**Whether a gateway is running for that agent is not yet checked.** It cannot be checked by the
layer that removes one — `agents/` sits below `gateways/` and may not import it — so it belongs to
this command, and it is left until there is a `rundesk gateways` verb to stop one with. Refusing
before then would leave somebody an agent they cannot remove and nothing to type to free it. Until
that lands, removing an agent whose gateway is up leaves a running program with no records.

## backups

The copies of `data/`. With no sub-verb it lists them, newest first, because listing is what somebody
wants nine times in ten.

```console
$ rundesk backups
copies in /Users/you/.rundesk/backups
BACKUP
2026-08-04T03-00-00Z
2026-07-28T03-00-00Z
```

Where they are kept is printed even when there are none. "No copies" and "no copies *here*" are
different things to learn.

**Nothing there, and not being able to look, are different answers.** An install nobody has copied
anything on says so. A `backups/` that cannot be read — or that points at a disk nobody has plugged
in — is a failure, because answering "none yet" would tell somebody their copies are gone at the
moment they are merely unplugged, and what that person does next is act on it.

### backups save

Copies `data/` whole, under a name that says when it was made, and says what it is called.

```console
$ rundesk backups save
saved 2026-08-04T03-00-00Z
        from   /Users/you/.rundesk/data
        in     /Users/you/.rundesk/backups
        let go of 2026-07-21T03-00-00Z
```

The copy is built under a name no finished copy wears and renamed into place only once all of it is
there, so an interruption leaves litter rather than a copy that is not one.

It then lets go of the oldest past `backup_retention`. **This is the only thing in rundesk that
removes a copy**, it considers only names that are copies, and a copy it could not remove is said out
loud — but neither changes the exit code, because the operation asked for was a copy and the copy is
there.

### backups restore

`--confirm` is required, and a copy of what is there now is taken **before** anything is replaced —
so restoring the wrong name costs a command rather than everything you had. Without `--confirm` it
says exactly what it would do and does none of it.

```console
$ rundesk backups restore 2026-07-28T03-00-00Z --confirm
        kept 2026-08-04T03-00-00Z — a copy of /Users/you/.rundesk/data as it was
restored 2026-07-28T03-00-00Z
        into   /Users/you/.rundesk/data
```

The copy that was kept is named before the swap starts rather than in a summary afterwards, because
every failure from that point on is one where knowing the name is the way back.

A directory with no readable `config.json` is refused: it is not a copy of an install's data whatever
it is named, and putting it back would leave rundesk unable to tell how far it had been carried.

**A copy older than this release is carried forward once it lands.** The copy holds the migration mark
it had when it was taken, so the steps that run are exactly the ones it missed — and never the ones it
already had. **Being back is not the same as being settled**: if a step cannot finish, the command
says so and exits non-zero, because the data really is the copy that was asked for and really has not
been carried onto this release. `rundesk update` settles an install and is safe to run again.

### backups set-location

Moves the copies to another directory and links `backups/` at it.

```console
$ rundesk backups set-location /Volumes/Big/rundesk-backups
        moved 2026-08-04T03-00-00Z
rundesk keeps its copies in /Volumes/Big/rundesk-backups
        linked /Users/you/.rundesk/backups → /Volumes/Big/rundesk-backups
```

A link rather than a setting, on purpose: `RUNDESK_HOME` stays the only location rundesk reads, so
the copies can live anywhere without there being a second place to look.

Everything is copied to the new place **first**, and taken from the old one only once every copy is
confirmed to be there — so a move that dies partway is a tidying job and never a loss. Everything is
carried, not only the copies: a move that left your own files behind in a directory it then replaced
with a link would be a move it did not make.

## env

The values rundesk hands to what it talks to — a Discord bot's token, a Slack app's key. An owner
places one once and everything rundesk starts finds it, with nobody having exported anything in a
shell a gateway will never see.

```console
$ rundesk env set DISCORD_TOKEN
DISCORD_TOKEN: 
DISCORD_TOKEN is set — MTIxxxxxxxxken

$ rundesk env list
values in /Users/you/.rundesk/secrets
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

Where these are kept and what protects them is [`layout.md`](layout.md) — the short version is that
a backup cannot contain one, the files are yours alone, and each value is sealed on disk with a key
kept beside it.

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
- `secrets/`, **only with `--purge`** — a credential left on a machine rundesk has been removed
  from is the worst thing here to leave lying about, and an ordinary removal keeps them because
  they are yours and no backup can bring them back
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
