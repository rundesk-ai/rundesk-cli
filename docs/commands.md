# The command surface

Ten operations, and every one of them works. There is no "coming soon" list: a verb rundesk cannot
perform is a verb rundesk does not have.

```sh
rundesk status                            # the version, where the install is, and every configured value
rundesk version                           # the version, and whether it is out of date
rundesk configure [--<setting> <value>]   # change what this install is configured with
rundesk agents                            # the agents this install keeps
rundesk agents add <agent> --provider <provider>        # make one
rundesk agents configure <agent> --provider <provider>  # change what is behind one
rundesk agents remove <agent> --confirm   # take one away, and everything it remembers
rundesk gateways                          # every agent, and how its gateway stands
rundesk gateways start <agent>            # start one, and prove a gateway came up
rundesk gateways stop <agent> | --all     # take the job back, gracefully
rundesk gateways restart <agent> | --all  # stop it, prove it went, start it again
rundesk gateways logs <agent> [-n <lines>]  # what one gateway has been saying
rundesk gateways run <agent>              # be the gateway, in this terminal
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

## Some flags are required by the verb rather than by argparse

`--provider`, `--confirm`, and naming either a gateway or `--all` are all required, and none of them
is registered as `required=True`. That is deliberate and it is the same decision every time:
argparse's own refusal names a flag and does not say what to type. *"the following arguments are
required: --provider"* is true and is not an answer, and the person reading it still has to work out
what a provider is and where the agent's name goes.

So the verb checks instead, and every refusal ends with the whole command somebody should run:

```console
$ rundesk agents add cole
agents: FAILED — nothing said which provider — say which with: rundesk agents add cole --provider <provider>
        nothing was made
```

The distinction is worth the code because these guard an *effect* rather than describe one.
`--confirm` is not a value the command needs in order to work; it is the thing standing between a
person and an agent's whole memory, and a guard on that is worth wording. Which exit code each one
answers with is below — a missing `--provider` is a command line that was right and refused, and a
`stop` that named neither a gateway nor `--all` is the command line itself being wrong.

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

The agents this install keeps — one directory each, under `data/agents/`, and what stands inside one
is [`layout.md`](layout.md). With no sub-verb it lists them, because listing is what somebody wants
nine times in ten.

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

**A name no launchd label can carry is allowed, and warned about here.** An agent may be called
anything a directory may be called; a label is narrower. Such an agent works in every respect but
one — no job can ever be placed for it, so nothing starts its gateway at login and nothing brings it
back when it stops. It is said at the moment the name is chosen, while picking another is still free:

```console
$ rundesk agents add 'my agent' --provider claude
agent my agent added
        ...
        note      this name cannot be a launchd label, so no job can ever be placed for it — nothing starts its gateway at login and nothing brings it back when it stops. Run it with `rundesk gateways run` and stop it with `rundesk gateways stop`, or add the agent again under a name of letters, digits, a dot, a dash or an underscore
```

The note is not a refusal, because such a gateway does run and can be stopped — only supervision is
impossible. An ordinary name carries no note at all; one that appeared on every agent would stop
being read.

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
the command says so. The lock and the record a gateway leaves in that directory are named too, and
only when they are there: describing a removal larger than the one that would happen defeats the
point of describing it.

**A removal is refused while a gateway is running for that agent**, and this is the check the whole
confirmation exists to protect. Removing an agent out from under a live gateway leaves a program
holding a name, writing into a directory that is no longer there, hosting an agent that no longer
exists — and launchd puts it straight back when it dies, because the job outlives the records the
removal took.

```console
$ rundesk agents remove cole --confirm
agents: FAILED — a gateway is running for cole as pid 96111 — removing it now would leave a running program with no records
        stop it with: rundesk gateways stop cole
        nothing was removed
```

Asked of the kernel through the same lock `rundesk gateways` reads, so a gateway that was killed
outright is not mistaken for one that is up. Its third answer is kept as a third answer here too:
an agent nobody can *ask* about is not an agent that is safe to remove, and it is refused in the
same breath rather than treated as free.

It is checked below the confirmation rather than above it, which looks like the wrong way round and
is not. A description of a removal describes what would be taken; this decides whether it may happen
at all — and a gateway can come up in the gap between the two commands anyway, so the only moment
worth asking in is the moment of acting.

## gateways

One agent has one gateway: a supervised process that holds that agent's name and is brought back
when it dies. With no sub-verb it lists them, the way `agents` and `backups` do. The other five are
`start`, `stop`, `restart`, `logs` and `run`.

What a gateway is, and every state one can get stuck in, is [`gateways.md`](gateways.md). This is
what each verb guarantees and what each refuses.

```console
$ rundesk gateways
gateways in /Users/you/.rundesk/data/agents
AGENT  GATEWAY      JOB         OVERRIDE  LOGIN ITEM
ada    not running  not placed  enabled   cannot tell
cole   not running  not placed  enabled   cannot tell
        ada: not running and no job — start it with: rundesk gateways start ada
        cole: not running and no job — start it with: rundesk gateways start cole
```

**Four columns, because no one of them can answer on its own.** `GATEWAY` is the kernel's answer and
is the one to read first; `JOB` is whether launchd is holding a job for it; `OVERRIDE` is a store
that outlives every job and can refuse to start one; `LOGIN ITEM` is what macOS has been told about
it by its owner. Collapsing those into a single word would mean inventing a verdict nothing measured
— a job that has been disabled prints as a perfectly healthy one, and a job switched off in System
Settings is gone from launchd entirely. `cannot tell` is a first-class answer in every column: the
alternative is telling somebody their gateway is fine, or switched off, on the strength of a
question that failed.

Where they stand is printed even when there are none, because "no gateways" and "no gateways *here*"
are different things to learn. **A listing that answered exits `0`, whatever it found** — the exit
code says whether the question was answered, not whether the machine is healthy. What a bad state
costs is the word `running`, which no row gets unless it earned it:

```console
$ rundesk gateways
gateways in /Users/you/.rundesk/data/agents
AGENT  GATEWAY                            JOB         OVERRIDE  LOGIN ITEM
ada    not running                        not placed  enabled   cannot tell
cole   running, UNSUPERVISED (pid 96111)  not placed  enabled   cannot tell
        ada: not running and no job — start it with: rundesk gateways start ada
        cole: a gateway is holding this name and launchd has no job behind it — nothing brings it back when it stops, and nothing starts it at the next login. Run: rundesk gateways restart cole
```

A gateway holding its agent's name with nothing supervising it is the one state that looks like
health and is not, so it is never written as `running` on its own. Nothing brings it back when it
stops and nothing starts it at the next login, and somebody who read the word `running` there would
believe they were covered at the moment they were least covered.

**One row is worse than that and gets a word of its own.** An agent whose name cannot be a launchd
label is not merely unsupervised now — it can never be supervised at all, and no restart changes
that, so none is offered:

```console
$ rundesk gateways
AGENT     GATEWAY                               JOB               OVERRIDE     LOGIN ITEM
my agent  running, NEVER SUPERVISED (pid 8184)  cannot be placed  cannot tell  cannot tell
        my agent: a gateway is holding this name and launchd can never have a job for it — 'my agent' cannot be part of a launchd label. Nothing brings it back when it stops, nothing starts it at the next login, and no restart changes either of those while the agent is named this. Take it down with: rundesk gateways stop 'my agent'
```

Commands printed for such a name are quoted for a shell, so what is offered is what a shell accepts.

### gateways start

Places the job and then **proves a gateway came up**, rather than proving that launchd accepted one.
A job the supervisor took is not a process that started: the plist can be perfect and the spawn can
still fail, in which case launchd removes the job again and says so only in the unified log. So the
kernel is asked afterwards, and a start that cannot show a gateway holding the name is a failure
that says where to read next.

It is safe to run again on any state — it rewrites the job, clears an override nobody remembers,
takes back whatever was loaded under that name, and puts it back — **except on a gateway that is
already running, where it does nothing at all.** Every step of that resolver begins by taking the
old job back, which ends the gateway that is up. A start that ran it unconditionally would take an
agent down in the middle of its work in order to report that it was running, and that is not
hypothetical: an ordinary start in the build this replaces ended a live agent's whole process tree.

The exception is the one state where "already running" would be a lie:

```console
$ rundesk gateways start cole
gateways: FAILED — cole is running as pid 96111 and launchd has no job behind it
        nothing brings that gateway back when it stops, and nothing starts it at the next login.
        put it under launchd with: rundesk gateways restart cole
        nothing was started
```

A name that is not an agent on this install is refused before anything is placed, and so is an agent
nobody can ask about — a second gateway started beside a first is the one thing this must never do,
and "cannot tell" is not a quiet form of "not running".

### gateways stop

Takes the job back and then proves the name came free. **Graceful**: the gateway is sent `SIGTERM`
and given the whole of its shutdown window to finish what it was holding, because a gateway is
holding somebody's work and a stop that does not let it finish is a stop that loses some.

The job's file goes with the job, and that is what makes this a stop rather than a pause. At login
macOS bootstraps the `LaunchAgents` directory on its own, so a stop that left the file behind would
be a stop that undid itself the next time somebody logged in, with nothing anywhere having said so.

`--force` kills the gateway where it stands instead of asking it to finish. It is for a gateway that
**will not go** — one ignoring `SIGTERM`, so that a graceful stop blocks for the whole window — and
never for one that is merely busy, which is exactly the gateway with something to lose. It takes
work away mid-flight, and the command says so on the line reporting what it did, but only where a
gateway really was up: claiming it took something away from a name nothing was holding would be the
command overstating what it cost.

**A name or `--all`, one of them, never both and never neither.** The build this replaces let a bare
`restart` mean every agent, and it took down every gateway somebody had:

```console
$ rundesk gateways stop
gateways: FAILED — stop was not told which gateway
        one:   rundesk gateways stop <agent>
        every: rundesk gateways stop --all
        nothing was changed
```

That is a `2` and not a `1` — see the table at the bottom. Nobody said which gateway, so the command
line itself was wrong; the gateway is not one that would not stop.

Stopping something that was never started is not a failure. It is the state that was asked for, and
it is reported as such.

**A gateway with no job to take back is stopped by signalling the process directly.** Two gateways
have none: one whose agent is named something no launchd label can carry — `rundesk gateways run`
hosts it quite happily — and one whose job came back cleanly while the name is still held, which is
the proof launchd never started that process. Without this route both are running programs no command
can reach.

```console
$ rundesk gateways stop 'my agent'
gateway stopped for my agent as pid 8851
        this gateway had no job, so it was stopped by signalling the process directly
        why    'my agent' cannot be part of a launchd label — an agent hosted by one is named with letters, digits, a dot, a dash or an underscore
```

The pid comes from the lock, so one is only ever signalled while the kernel says a gateway is holding
that name, and whether it really went is decided by the lock rather than by what the signal answered.
See [gateways.md](./gateways.md) for why that distinction is load-bearing on macOS.

### gateways restart

Stop, prove the old one is gone, then start — **never the other way round.** Starting over a job the
supervisor is still holding keeps the definition it already had *without failing*, so a restart that
started first would report a restart and go on running the old program for ever. A stop that did not
clearly work therefore ends the cycle there, with the gateway down and the failure said out loud,
rather than being followed by a start that cannot mean what it says.

`--force` means the same thing it means on `stop` and costs the same thing: the gateway is killed
rather than asked, and whatever it was doing is taken away where it stood. What it skips is the
*waiting*. It skips none of the proving — the new gateway is still shown to be holding the name
before the command says it restarted anything.

**Both spellings are the same stop**, which is what makes that true. `--force` was once its own path
that killed the launchd *label* and went straight on to bootstrap a replacement — correct only while
launchd holds a job for that label. Against a gateway with no job it reached nothing, and the check
that a gateway had come up was then answered by the original process, still running under its
original pid. It reported killing and replacing a gateway it had not touched, in the one state a
person runs `--force` to get out of. Both now go through the stop above, including its fall back to
signalling the process directly.

### gateways logs

What one gateway has been saying, twenty lines by default — **and, every time, what the machine's
supervisor caught around it.** Those are two orthogonal facts about one gateway and both are shown,
each labelled with the file it came from, because the case that matters most is the one where they
disagree: a gateway that started, wrote its `up` line and then died on an uncaught exception has a
perfectly ordinary day log and a traceback in a file the day log knows nothing about.

```console
$ rundesk gateways logs cole -n 5
logs for cole in /Users/you/.rundesk/data/agents/cole/logs
        what cole's own gateway wrote, in /Users/you/.rundesk/data/agents/cole/logs:
[2026-08-05 08:26:43-04:00] INFO:    gateway up for cole on 0.37.0 as pid 95177
[2026-08-05 08:26:45-04:00] INFO:    gateway stopping for cole: asked to stop with signal 15
[2026-08-05 08:28:40-04:00] INFO:    gateway up for cole on 0.37.0 as pid 96111
[2026-08-05 08:28:42-04:00] WARNING: gateway did not start: a gateway is already running for cole as pid 96111 — one agent has one gateway, and this one is standing down
        the supervisor caught nothing in gateway.out or gateway.err — everything above is the gateway's own log
```

**Three answers and never two**, for each of them. Lines, nothing yet, or could not be read — an
empty list handed back for a directory nobody may read is a report of a quiet gateway, and whoever
believes that goes looking in entirely the wrong place. So an empty source says which kind of empty
it is rather than being left out.

Nothing anywhere and nothing captured means the gateway never got far enough to write a word, which
puts the failure upstream of rundesk entirely — so what is printed is the command that finds it:

```console
$ rundesk gateways logs nina
logs for nina in /Users/you/.rundesk/data/agents/nina/logs
        what nina's own gateway wrote, in /Users/you/.rundesk/data/agents/nina/logs:
        nothing has been written by nina's own gateway yet
        and the supervisor caught nothing either — a gateway that never started at all leaves its only account in the unified log:
        log show --last 10m --predicate 'process == "launchd" OR process == "xpcproxy"' --style compact
```

Asking for no lines is refused rather than answered with nothing, and refused as a `2`, because
argparse already answers `2` for an `-n` that is not a number. One flag answering `2` for a value
that is not a number and `1` for a value that is not a count is the same mistake reported two ways,
and neither a person nor a script can tell why.

### gateways run

Be the gateway for one agent, in this terminal. This is what the job runs, and running it by hand is
how you watch a gateway start without launchd in the way.

**Its exit code belongs to launchd rather than to you**, and the whole of `gateways.md`'s exit-code
contract applies to it: every refusal exits `0`, because under this job a non-zero exit is a request
to be restarted, and a permanent condition that asked to be restarted becomes an endless loop. So an
agent that does not exist is a refusal and a `0`, and so is a name another gateway is already
holding:

```console
$ rundesk gateways run cole
[2026-08-05 08:28:42-04:00] gateway cole: this process is pid 96134, running 0.37.0
gateway: NOT RUNNING — a gateway is already running for cole as pid 96111 — one agent has one gateway, and this one is standing down
```

The first line is written before anything is parsed or read, and it is not decoration: an empty
capture file beside a job launchd says has run is the one signal that the failure is upstream of
this program.

**The claim is the check.** There is no version of this that asks whether a gateway is running and
then starts one — between the asking and the starting another gateway can arrive, and that gap is
how an ordinary start once ended a live agent's whole process tree.

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

## skills

The skills this install has, which agent holds which, and what each of them needs to work. A
**catalog** is what you install, update and remove; a **skill** is what you grant. Nothing installs
one skill and nothing removes one, because a catalog is what somebody publishes and follows.

```console
$ rundesk skills
skills in /Users/you/.rundesk/data/skills
CATALOG         SKILL              AGENTS
rundesk         managing-rundesk   alan, ben
rundesk         writing-skills     —
rundesk-skills  writing-plans      alan
local           my-thing           —

$ rundesk skills grant alan rundesk-skills/writing-plans
alan holds writing-plans
        from     rundesk-skills/writing-plans
        stands   /Users/you/.rundesk/data/agents/alan/home/skills/writing-plans
```

**A skill is addressed `<catalog>/<skill>`, always.** Two catalogs may both hold `writing-plans`, so a
verb that took the bare name would have to guess — and a guess that is unambiguous today stops being
so the moment a second catalog is installed. A bare name is refused, naming every catalog that holds
one, so being wrong costs a copy-paste.

`install`, `update`, `remove` and `forget` say what they would do, do none of it, and **exit non-zero**
without `--confirm`. `grant` and `revoke` do not ask: each is one link in one directory, and somebody
who typed the wrong one types the other verb.

### Two catalogs cannot be removed

`rundesk` ships inside the release and is replaced out of it on every update — it is how an agent
operates *this* version, so it is never fetched and never removable. `rundesk-skills` is the general
catalog rundesk depends on, fetched like any other and equally undeletable. `local` is yours and
rundesk never touches it. [`layout.md`](layout.md) says why the first two are separate.

Catalogs are also checked on **every** `rundesk install` and `rundesk update`, including an update
that found no newer release — a catalog is somebody else's repository and moves on its own schedule.
That happens after the release has already landed and **cannot change the exit code**: a repository
somebody deleted last week is a true thing to say and a false reason to report that an update failed.

### More than one account of the same thing

A skill that talks to something outside this machine says what it needs, and a **profile** is a whole
named set of those values — not a suffix on one. Three Jira sites is the case that decides it: a site
is a URL, an address and a token that only mean anything together.

```console
$ rundesk skills configure rundesk-skills/jira --profile acme
jira needs 3 values for acme
        JIRA_BASE_URL__ACME   your Jira site, e.g. https://acme.atlassian.net
        > 
        ...
profile acme is complete

$ rundesk skills profiles rundesk-skills/jira
profiles for rundesk-skills/jira
PROFILE    STANDING    MISSING
(default)  not set     JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
acme       complete    —
gamma      INCOMPLETE  JIRA_API_TOKEN__GAMMA
```

Profiles are **found**, not declared: the set of them is whatever suffixes are standing on the names a
skill declares, so a fourth account needs no edit to the skill, its catalog, or anything on this
machine. **Every profile is reachable by any agent holding the skill** — nothing binds one to another.

**A named profile never falls back to a plain value.** That is the rule the shape exists for: falling
back is how one site's URL comes to be paired with another site's token, and the request succeeds
against the wrong company. A profile carries all of its own values or it is reported incomplete.

Values are typed, never passed as arguments, and never printed back — `env` says why. `configure` exits
non-zero when the account is still incomplete, and `forget` empties a whole account at once.

### doctor

`rundesk skills doctor` says what cannot be used and why, names the one command that fixes it, and
**exits non-zero when anything is wrong** — the way `env check` does, so a script can gate on it. It
reads nothing and runs nothing: whether a credential is set is asked of the store, and whether a
script can run is decided from what is on the disk.

```console
$ rundesk skills doctor
alan
  jira              rundesk-skills  PARTIAL   2 of 3 profiles are usable
      acme  ready
      beta  ready
      gamma  INCOMPLETE
          JIRA_API_TOKEN__GAMMA — an API token from id.atlassian.com
  old-thing         —               DANGLING  the grant points at nothing

skills: 2 of 3 cannot be used:
        rundesk skills configure rundesk-skills/jira --profile gamma
        rundesk skills revoke alan old-thing
```

| Verdict | Means |
|---|---|
| `READY` | every profile is complete, and every command it ships would run |
| `PARTIAL` | at least one profile is usable and at least one is not |
| `BLOCKED` | no profile is usable — a required value is missing everywhere |
| `UNRUNNABLE` | every credential is in place and a command it ships is not executable |
| `STALE` | a copied grant is behind the catalog it came from; `rundesk update` remakes it |
| `DANGLING` | the grant no longer resolves — its skill left its catalog, or the catalog went |
| `BROKEN` | the skill itself will not load, or what it declares cannot be read |

`PARTIAL` exists because two working Jira sites and one half-configured is neither a healthy
integration nor a broken one, and collapsing it either way would cry wolf on a working setup or hide
the site that fails at three in the morning.

Writing a skill or publishing a catalog is [`catalogs.md`](catalogs.md).

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

- **every gateway job this root placed, by the full name launchd knows it by, one agent at a time —
  and before `app/` goes.** A job that outlived the program it points at is a machine trying to
  start a command that is not there, at every login, for ever. And it is one label at a time and
  never a family or a prefix because a job's name belongs to the person rather than to a directory:
  the build this replaces called every install's job the same thing, and one install's uninstall
  booted out another install's live gateway. A job that will not come back stops the removal, rather
  than leaving the machine pointed at a program that is about to be deleted.
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

Three codes, and the line between the last two is the one worth being careful about: **`1` says the
command was understood and could not be carried out, and `2` says it was never a command.** A script
that cannot tell those apart retries the wrong one.

Everything that lists — `status`, `agents`, `gateways`, `backups`, `env list`, `configure` with
nothing to change — exits `0` for whatever it found, because the question was *what is there* and
that question was answered. `rundesk gateways` finding every gateway on the machine down is a
listing that worked. What a bad state costs is the word `running`, not the exit code.

Three commands are written to have their code read by a script, and they are the ones to build on:

- **`rundesk env check <key>`** exits non-zero when a value is not set, so
  `rundesk env check DISCORD_TOKEN && …` does the right thing in a shell.
- **`rundesk version`** exits `0` even when it could not reach GitHub, because the question it was
  asked — what version is this — was answered from the machine itself. Being unable to ask is said
  on stderr as `UNKNOWN` and is never reported as being up to date.
- **`rundesk gateways start <agent>`** exits `0` only once a gateway has been shown to be holding
  the name. A job the supervisor accepted is not a gateway that started, and the exit code here
  means the second thing.

Where a refusal is a `2` rather than a `1`, it is because nobody said what to do. **`rundesk
gateways stop` with neither a name nor `--all` is a `2`** — the gateway is not one that would not
stop; the command line never named one. `gateways stop <agent> --all` is a `2` for the mirror
reason, and so is `gateways logs <agent> -n 0`, because argparse already answers `2` for an `-n`
that is not a number and one flag must not report the same class of mistake two ways.

Where a refusal is a `1`, the command line was right and could not be carried out: an agent that is
not on this install, an agents directory nobody can read, `--provider` left off, `--confirm` left
off. **A removal that did not happen is a failure** — `agents remove` and `uninstall` without
`--confirm` describe what they would take and exit `1`, because a command that took nothing and
exited `0` would tell a script the removal was done.

**The gateway process itself is the one exception on this page, and it is not an exception to the
table.** `rundesk gateways run` exits `0` on every refusal. That code is not a report to a person;
it is a sentence in a conversation with launchd, where `0` means *do not bring me back*. See
[`gateways.md`](gateways.md).
