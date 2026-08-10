# The command surface

Eighteen commands, and every one of them works. There is no "coming soon" list: a verb rundesk
cannot perform is a verb rundesk does not have. `rundesk --help` is the count that cannot go stale;
this one is checked against it.

```sh
rundesk status                            # the version, where the install is, and every configured value
rundesk version                           # the version, and whether it is out of date
rundesk configure [--<setting> <value>]   # change what this install is configured with
rundesk agents                            # the agents this install keeps
rundesk agents add <agent> --provider <provider> [--describes <text>]        # make one
rundesk agents configure <agent> [--provider <provider>] [--describes <text>] [--self-improve <true|false>] [--delegate-to <agent> ... | --delegate-to-any | --delegate-to-none]  # change one
rundesk agents remove <agent> --confirm   # take one away, and everything it remembers
rundesk gateways                          # every agent, and how its gateway stands
rundesk gateways start <agent>            # start one, and prove a gateway came up
rundesk gateways stop <agent> | --all     # take the job back, gracefully
rundesk gateways restart <agent> | --all  # stop it, prove it went, start it again
rundesk gateways logs <agent> [-n <lines>]  # what one gateway has been saying
rundesk gateways run <agent>              # be the gateway, in this terminal
rundesk schedules                         # everything every agent starts because the time came
rundesk schedules list <agent>            # one agent's
rundesk schedules add <agent> <schedule> --run '<program>' | --ask '<prompt>'  --when '<cron>' | --at <moment>
rundesk schedules update <agent> <schedule> [--when|--at|--until|--run|--ask|--enable|--disable]
rundesk schedules show <agent> <schedule> # everything one was given
rundesk schedules run <agent> <schedule>  # run one now, in this terminal
rundesk schedules remove <agent> <schedule>       # take one away
rundesk channels                          # every agent's channels, and how each one stands
rundesk channels list <agent>             # one agent's
rundesk channels add <agent> <adapter> --allow <id> [--notify] [--with '<adapter opts>']
rundesk channels show <agent> <adapter>   # everything one channel was given
rundesk channels configure <agent> <adapter> [--allow <id>] [--deny <id>] [--notify]
rundesk channels test <agent> <adapter>   # connect again, and say what it reached
rundesk channels remove <agent> <adapter> --confirm       # take one away
rundesk channels doctor [<agent>]         # what cannot be used, and exactly why
rundesk backups                           # the copies of what rundesk keeps for you
rundesk backups save                      # copy what rundesk keeps, now
rundesk backups restore <backup> --confirm        # put a copy back
rundesk backups set-location <path>       # keep the copies in another directory
rundesk env list                          # every value rundesk keeps, shown only as a hint
rundesk env check <key>                   # whether one is set
rundesk env set <key>                     # keep one — typed, never passed as an argument
rundesk env unset <key>                   # empty one, leaving the name
rundesk skills                            # every skill this install has, and who holds which
rundesk skills list [<agent>]             # with an agent: what it holds, and what that needs
rundesk skills catalogs                   # every catalog, its version and where it came from
rundesk skills install <repository> [--confirm]   # install a catalog of skills
rundesk skills update <catalog> [--confirm]       # check one against where it came from
rundesk skills remove <catalog> [--confirm]       # take one away, and every skill in it
rundesk skills grant <agent> <catalog>/<skill> [--as <name>]   # give an agent a skill
rundesk skills revoke <agent> <skill>     # take one away from an agent
rundesk skills profiles <catalog>/<skill>         # every account one skill is configured for
rundesk skills configure <catalog>/<skill> [--profile <name>]  # set what it needs, guided
rundesk skills forget <catalog>/<skill> [--profile <name>] --confirm   # empty one account
rundesk skills doctor [<agent>]           # what cannot be used, and exactly why
rundesk update                            # move to the newest release, or say it is up to date
rundesk uninstall --confirm [--purge]     # remove rundesk; --purge also takes the data
rundesk install [--source <dir>] [--bin-dir <dir>]   # what install.sh runs
```

Ask `rundesk --help` rather than this page when the two disagree — the command is generated from
nothing and describes itself.

## Some flags are required by the verb rather than by argparse

`--provider`, `--allow`, `--confirm`, and naming either a gateway or `--all` are all required, and
none of them is registered as `required=True`. That is deliberate and it is the same decision every time:
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
version           0.45.0
home              /Users/you/.rundesk
program           /Users/you/.rundesk/app (installed)
data              /Users/you/.rundesk/data
backups           /Users/you/.rundesk/backups
secrets           /Users/you/.rundesk/data/secrets
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
automatic update  scheduled daily at 03:00 local time
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
rundesk 0.45.0
        0.45.0: UP TO DATE
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

Changing `update_enabled` or `update_time` immediately reconciles the root-specific launchd job.
The settings are saved atomically first; if launchd cannot be reconciled, `configure` exits non-zero
and says that the settings were saved, so repeating the command is an honest idempotent repair.
Disabling removes the job and its generated shim; changing the time replaces the loaded definition.

How far the install has been carried (`migration`) is shown by `status` but is not settable: setting
it by hand would make rundesk skip or repeat a migration step.

## agents

The agents this install keeps — one directory each, under `data/agents/`, and what stands inside one
is [`layout.md`](layout.md). With no sub-verb it lists them, because listing is what somebody wants
nine times in ten.

```console
$ rundesk agents
agents in /Users/you/.rundesk/data/agents
AGENT  PROVIDER  SKILLS                                  SELF-IMPROVE
ada    claude    managing-rundesk, researching-topics    yes
cole   openai    managing-rundesk, reviewing-code        yes
```

Skill names are current grants. They are shown so a person or routing agent can tell which standing
specialty belongs behind a name without loading any skill body.

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

Listings are split into `Domain agents` and `Specialist agents`; each section preserves name order.
Domain is the compatible default for existing and newly created agents.

### agents add

Makes an agent: its records, `home/`, `logs/`, and the files it lives by. `--provider` is required.

```console
$ rundesk agents add cole --provider claude --role domain
agent cole added
        provider  claude
        role      domain
        home      /Users/you/.rundesk/data/agents/cole/home
        logs      /Users/you/.rundesk/data/agents/cole/logs
        records   /Users/you/.rundesk/data/agents/cole/state.db
        rules     AGENTS.md, CLAUDE.md, MEMORY.md — how it works, and what it learns
        workspace plans/, research/, scripts/, retros/, tasks/ — agent-owned work, organized
        skill     rundesk/managing-rundesk — how it operates this install
        note      the provider is recorded and not proven — check it with: rundesk providers check
```

`--role` accepts exactly `domain` or `specialist` and defaults to `domain`. A domain agent owns an
ongoing operational area and its Desk queue when it holds `managing-your-desk`; its rules prioritize
standing specialists for bounded work in their focus or skill scope. A specialist accepts one
bounded assignment from its delegator and has no persistent Desk queue, Rundesk-operations workflow,
or standing named-agent delegation policy. Role is independent of provider, skills, delegation
scope, and whether a Desk exists.

**Every agent is given the files it lives by**, in its own `home/`: `AGENTS.md` is how it works and
`MEMORY.md` is what it has learned that is still true, and `CLAUDE.md` is the first of those under
the name some brains look for first — the same bytes, placed twice. They are the agent's and the
owner's to edit from that moment: **an update fills in one that is missing and never replaces one
that is there**, whatever it has been changed to. A release that shipped none says so on this line
instead, and the next `rundesk update` gives them.

The home also starts with `plans/`, `research/`, `scripts/`, `retros/`, and `tasks/`. Each carries a
short README describing what belongs there, how to keep it current, and its safety boundary. The
first four hold durable agent-owned work. `tasks/` holds active resumable briefs that the agent
removes after completion; neither kind moves canonical project state out of its project or preserves
disposable scratch. Updates fill an absent folder note but never replace one already there.

`MEMORY.md` is a compact working index for the next run, not a transcript or project notebook.
Ordinary work keeps owner preferences, the agent's role and responsibilities, reusable cross-project
process and gotchas, and a small active-project pointer: name, stable location, purpose, role, and
authoritative overview. Commands, deliverable paths, changing state, dates, and change history stay
with the project or an earned shared index. A substantial open task may keep resumable scope, checks,
and done criteria in `tasks/`; lasting truth returns to the project and the agent removes the brief
when the task closes. Memory keeps the current fact instead of a dated correction story; a turn that
learned nothing durable leaves it alone. Ordinary work removes only temporary files and directories
that turn created; it does not inventory the home.

When useful durable context would make `MEMORY.md` dense, the agent may link from it to a canonical,
purpose-named index in its home. `PROJECTS.md`, `CLIENTS.md`, and `OPEN_ITEMS.md` are examples, not
files every agent should create. An index earns its file only when the role has enough reusable
detail; it may include a stable entrypoint when that prevents repeated discovery. The agent reads it
when relevant and applies the same correction, compaction, and stale-entry removal rules. The link
keeps `MEMORY.md` as the small first-read map and prevents detached notes the next session would
never discover.

Periodic compaction and workspace upkeep are a focused Rundesk-management task, not daily prompt
weight. The bundled `managing-rundesk` skill has conservative maintenance, retrospective, and
self-improvement references for one focused upkeep pass. Maintenance runs first,
preserving unavailable active mappings, uncertain files, deliverables, provider-managed content,
symlinks, and project/user files; only confirmed stale continuity and agent-created obsolete clutter
are removed.

The retrospective phase reads the previous weekly entry, reviews bounded public evidence, and
updates one dated diary with what went well, where the agent failed or caused repeated asks, and one
testable improvement. It records observable correction, dissatisfaction, or distrust without
diagnosing the owner's mood, retains compact older entries as longitudinal evidence, and promotes a
lesson only to its proper durable home. The final phase starts with that diary and previous
`weekly-self-improve-upkeep` reports, then reviews a bounded sample of other messages and turns for repeated
friction, corrections,
missing context, failed outcomes, and ignored capability routes.
Heavy specialist work stays delegated to a materially better active named agent; a same-turn helper
is next when no standing specialist fits; a skill is recommended only for a recurring capability
this agent must own and neither route covers. The pass compares available and granted skills, never
revokes from non-use alone, and changes no grants or standing rules without explicit authority. Its
scheduled response is deliberately short and attention-first: owner actions only, or one line saying
upkeep completed and no action is needed.

**Every agent is given `rundesk/managing-rundesk`**, which is how it operates the install running
it — where things are, what its own gateway is doing, which values are set. It is a floor of the
product rather than a choice: `rundesk skills revoke` will not take it away, and `rundesk update`
gives it back to any agent standing without one. An install whose catalogs have not been placed yet
says so on this line instead, and the next `rundesk update` grants it.

**The provider is recorded and it is not proven**, and the command says so every time —
adding an agent runs no adapter, asks nothing what it can do and finds out about no
sign-in. `rundesk providers check` is what answers that. Nothing in
this release runs one: no credential is checked, no request is made, and there is no gateway to
start. An agent added with a provider nobody has ever spelled correctly looks exactly like one that
works, and a line implying otherwise would be a success this release did not earn.

**`--describes` is what an agent is for, in one sentence, and it is what the *other* agents read.**
Every agent's preface lists its colleagues and what each is for, so this is how one agent decides
whether a piece of work is somebody else's to do. An agent nobody has described is left out of that
listing rather than named blank: a bare name in a list of specialists is an invitation to guess, and
guessing is what this field exists to prevent. It is capped at one sentence, because every agent's
description is charged to every other agent's prompt on every turn.

`configure` takes any combination of its flags, and every named value moves in one write. `--role
<domain|specialist>` changes the recorded role and grouping only. It never rewrites `AGENTS.md` or
`CLAUDE.md`, because those may contain owner customizations; applying a different template requires
an explicit, separately reviewed edit to both files. An empty
`--describes` takes the description away rather than storing a blank — unset and set-to-empty stay
different answers, since a listing has to tell an agent nobody has described from one described as
nothing. `--self-improve` controls Rundesk's automatic self-improvement work for this agent; it
starts on, and accepts `yes/no`, `true/false`, `on/off`, and `1/0`.

Delegation scope controls where this agent may hand work, not who may hand work to it. It starts
unrestricted for new agents and agents carried forward from an earlier release. Configure exactly
one of these modes:

```console
$ rundesk agents configure ava --delegate-to forge --delegate-to trace
ava: may now delegate to forge, trace

$ rundesk agents configure forge --delegate-to-none
forge: may not delegate to another named agent now

$ rundesk agents configure ava --delegate-to-any
ava: may now delegate to any available agent
```

`--delegate-to <agent>` is repeatable and replaces the whole scoped list; it does not append to an
older one. `--delegate-to-none` makes the agent inbound-only for named-agent work: other agents may
still delegate to it, but it is shown no named agents and no named-agent delegation instructions.
`--delegate-to-any` restores the default. The three modes are mutually exclusive, and an invalid
target changes none of the other settings named in the same command.

The `DELEGATES TO` column in `rundesk agents` says `any`, `none`, or the configured agent names.
That is policy, not availability: an allowed target still needs a description and a running gateway
before it is offered in a turn. A direct `rundesk ask` from inside a turn is checked against the
same policy before any delegation is written. Scope changes, scope revocation during removal, and
direct handoff admission share the install state-change lock: whichever completes first determines
the policy the next operation sees.

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
        the provider is recorded and not proven — check it with: rundesk providers check
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
the command says so. What its channels keep, what its schedules keep, and the lock and record a
gateway leaves in that directory are named too, each only when it is there: describing a removal
larger than the one that would happen defeats the point of describing it.

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

**And refused while any of its work or any of its channels is still running**, which is the same
question asked of the other two things that hold a lock of their own. A schedule run by hand and an
adapter adopted from a gateway that is gone both hold only their own lock and never `gateway.lock`,
so an agent with no gateway anywhere can still have a program running as it — and this removal takes
the directory that lock stands in. Unlinking a lock while something holds it hands the name away: a
later agent of the same name claims a fresh inode and locks that, while the original is still
running against the old one.

```console
$ rundesk agents remove cole --confirm
agents: FAILED — cole is still connected: discord — removing it now would take the lock that adapter is holding, and a channel of the same name later would connect a second one beside it
        see what is connected with: rundesk channels list cole
        nothing was removed
```

Both are asked of the kernel through the lock files rather than of the records, so they are still
answerable when an agent's database cannot be read — which is one of the states somebody removes an
agent in. A claim nobody can *ask* about is refused in the same breath as one that is held, for the
reason the gateway's own third answer is: reporting an agent nobody can ask about as free is how a
live program comes to be orphaned by a removal.

Before the target is taken away, its name is removed from every other agent's explicit delegation
allowlist under the same install state-change lock. Recreating an agent with that name therefore
does not restore old allowlist authority. An unrestricted (`any`) scope remains unrestricted, as
does inbound delegation; those are policies rather than references to the removed agent.

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

On macOS, the gateway establishes its idle-system-sleep assertion **before** it takes the lock the
kernel reports as running. A start therefore cannot prove the gateway came up while the Mac is still
free to idle-sleep underneath it; if `/usr/bin/caffeinate` cannot establish that protection, the
gateway refuses to come online and the start reports the refusal. A temporary machine resource
limit instead makes the gateway crash so launchd tries again after its throttle; it is never turned
into a permanent refusal that strands the gateway after the limit clears.

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
[2026-08-05 08:26:43-04:00] INFO:    gateway up for cole on 0.45.0 as pid 95177
[2026-08-05 08:26:45-04:00] INFO:    gateway stopping for cole: asked to stop with signal 15
[2026-08-05 08:28:40-04:00] INFO:    gateway up for cole on 0.45.0 as pid 96111
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
[2026-08-05 08:28:42-04:00] gateway cole: this process is pid 96134, running 0.45.0
gateway: NOT RUNNING — a gateway is already running for cole as pid 96111 — one agent has one gateway, and this one is standing down
```

The first line is written before anything is parsed or read, and it is not decoration: an empty
capture file beside a job launchd says has run is the one signal that the failure is upstream of
this program.

**The claim is the check.** There is no version of this that asks whether a gateway is running and
then starts one — between the asking and the starting another gateway can arrive, and that gap is
how an ordinary start once ended a live agent's whole process tree.

On macOS that claim is taken only after `/usr/bin/caffeinate` is holding an idle-system-sleep
assertion for this process. It lasts for exactly the gateway's lifetime, including a gateway run by
hand, and the display remains free to sleep.

## schedules

Work an agent starts because the time came, rather than because somebody asked. A schedule belongs to
one agent and lives in that agent's own records, so no other agent can run it, report on it or change
it — and the gateway hosting that agent is what fires it. With no sub-verb it lists every schedule
that can still run on the install; with an agent it lists that agent's. Expired schedules stay out of
the ordinary operational view; `rundesk schedules list [<agent>] --expired` lists only those.

What a schedule is, and every state one can get stuck in, is [`schedules.md`](schedules.md). This is
what each verb guarantees and what each refuses.

Every agent also has one protected policy named `weekly-self-improve-upkeep`. It starts on and is
shown even before it has a stored firing. Seven distinct local calendar dates on which that agent
finishes work make one upkeep due; several turns on one date count once, and the dates may span
months. A failed or stopped turn counts as use, the upkeep turn itself does not, and a working turn
must settle before upkeep starts. After any upkeep attempt, the next seven usage dates begin a new
cycle.

The agent's gateway runs the policy through the ordinary schedule lock, process, output, settlement,
and final-report lifecycle. Its hard-coded task supplies the exact evidence interval and diary date,
then requires verified workspace/continuity maintenance, a retrospective, and evidence-based
self-improvement in that order. The final is one short attention-first sentence; detailed evidence
stays in the turn records. Turn it on or off per agent with
`rundesk agents configure <agent> --self-improve <true|false>`. Ordinary schedule commands cannot
add, update, run, disable, or remove this protected name; the agent setting is its only control.
An owner schedule already carrying that name from before the policy remains owner-controlled and
blocks automatic upkeep until it is removed; Rundesk never adopts or overwrites it.

```console
$ rundesk schedules
schedules in /Users/you/.rundesk/data/agents
AGENT  SCHEDULE  WHEN         NEXT              LAST
ada    digest    0 9 * * 1    2026-08-10 09:00  completed 2026-08-03 09:00
cole   nightly   0 2 * * *    2026-08-06 02:00  failed 2026-08-05 02:00
cole   once      2026-09-01T06:00  2026-09-01 06:00  never ran
```

`NEXT` is a local minute, or one of three words that are not times: `off` for a schedule somebody
switched off, `expired` in an `--expired` listing for one that can never be due again, and `never`
for one whose date does not arrive — `0 0 30 2 *` says the thirtieth of February. `LAST` tells
`never ran` from an outcome, because an owner seeing only that a schedule is spent cannot tell work
that happened from work that silently did not, and it says `running` while work is in flight.

The protected upkeep row instead says `after 7 usage dates`; its `NEXT` is `off`, `due`, or the
number of additional usage dates needed. Disabling it does not erase accumulated usage, so turning
it back on starts immediately when seven dates are already owed.

**A schedule is stated on this machine's own clock.** `--when` takes the five fields schedules have
always used and `--at` takes one moment, `YYYY-MM-DDTHH:MM`. Both are kept exactly as typed. A moment
carrying a zone or a `Z` is refused rather than converted — an owner who writes one means something
rundesk cannot honour, and quietly reinterpreting it is worse than saying so. What a schedule last
*did* is recorded in UTC, because that is compared and sorted, and is shown back in local time.

### schedules add

```console
$ rundesk schedules add cole nightly --when '0 2 * * *' --run '/usr/local/bin/backup.sh --full'
schedule nightly added for cole
        when      0 2 * * *
        run       /usr/local/bin/backup.sh --full
        until     not yet
        enabled   yes
        next      2026-08-06 02:00
        last      never ran
        logs      /Users/you/.rundesk/data/agents/cole/logs
        output    /Users/you/.rundesk/data/agents/cole/schedules/nightly.out
```

**`--run` takes one string and never reaches a shell.** It is split into words the way a shell would
split them and handed straight to the program, so nothing in it is globbed, expanded, or read as `;`,
`&&` or a redirection — a schedule cannot mean one thing when a person tests it and another when the
gateway runs it.

**The program is located when the schedule is added.** A path that is not on the machine is a mistake
somebody can fix at the moment they make it; found instead by a gateway, it is a line in a log at two
in the morning saying a schedule nobody was watching did not run.

```console
$ rundesk schedules add cole nightly --when '0 2 * * *' --run '/usr/local/bin/backup.sh'
schedules: FAILED — /usr/local/bin/backup.sh is not a program on this machine — a schedule naming one that is not there can never run, so say where it really is
        nothing was added
```

`--until <moment>` is when it is finished: after it, the schedule never runs again, however often its
time comes round. `--disabled` keeps it and does not run it.

**`--ask '<prompt>'` instead of `--run`, never as well as it.** A schedule either starts a program or
asks the agent, and the records hold that as a `CHECK`:

```console
$ rundesk schedules add cole weekday-client-update --when '0 9 * * 1-5' --ask 'Post the weekday client update.'
schedule weekday-client-update added for cole
        when      0 9 * * 1-5
        ask       Post the weekday client update.
        until     not yet
        enabled   yes
        next      2026-08-07 09:00
        last      never ran
```

A schedule that asks the agent gets **a fresh conversation for every invocation**, so a run at three in
the morning never lands in the exchange somebody types into. It reports where the agent is told
things — one message when it starts and its answer when it ends, and nothing in between. If it
delegates, the returned result resumes that invocation for review and only the final reviewed answer
is reported.
[`schedules.md`](schedules.md#what-a-run-says-on-a-surface-and-the-two-messages-it-is-allowed) is what
that looks like and what happens when there is nowhere to say it.

### schedules update

Changes one in place, keeping every record of what it has already done. **Only what is named moves**,
and `--when` and `--at` replace each other — a schedule states a repeating time or one moment, never
both. Naming nothing to change is refused rather than reported as a success.

```console
$ rundesk schedules update cole nightly
schedules: FAILED — nothing was named to change about nightly
        change one with: rundesk schedules update cole nightly --when '<cron>'
        nothing was changed
```

### schedules run

Runs one now, in this terminal, whether or not it is due — and prints what the program wrote, on the
stream the program wrote it to.

```console
$ rundesk schedules run cole nightly
backing up /Users/you/work
done, 412 files
schedule nightly completed
```

**The exit code is the program's**, so this composes in a script. A program that never started is a
`1` with no exit code quoted, because nothing ran and reporting a code would say it ran and disagreed.

**Running by hand never uses up the one moment a schedule states and never moves when it next falls
due.** Testing a schedule must not be how you stop it happening. It does write down what became of it,
because it did run — and it takes the same lock the clock takes, so it cannot start a second copy of
work a gateway is already doing.

### What a firing leaves behind

Everything a schedule's work writes is appended to `data/agents/<agent>/schedules/<schedule>.out`, and
the account of each firing is in the agent's own log beside every other thing its gateway said:

```console
$ rundesk gateways logs cole
[2026-08-05 02:00:00-04:00] INFO:    schedule nightly is due for 2026-08-05 02:00
[2026-08-05 02:00:00-04:00] INFO:    schedule nightly started as pid 4471: /usr/local/bin/backup.sh --full
[2026-08-05 02:00:31-04:00] ERROR:   schedule nightly failed with exit 2 in under 31s
[2026-08-05 02:00:31-04:00] ERROR:     rsync: link_stat "/Volumes/x" failed: No such file or directory
```

It ran, it finished, or it failed and why — and the last of those carries a bounded tail of what the
program wrote, so the file is worth opening on its own. Every way a firing does not get that far is
named rather than left silent, and [`schedules.md`](schedules.md#when-a-schedule-is-not-doing-what-you-expected)
lists what each of those lines means and what to do about it.

## channels

How an agent is reached, and how it reaches back. A channel belongs to one agent and lives in that
agent's own records, and the gateway hosting that agent is what runs the program behind it. With no
sub-verb it lists every channel on the install; with an agent it lists that agent's.

**A channel is a connection, not a place.** Connecting Discord gives an agent *one* channel that
carries private messages and every room the bot was invited to — there is nothing per-place written
down, and nothing to name. The channel **is** its adapter, so `rundesk channels add alan discord`
gives alan a channel called `discord`, and one list of ids says who may reach that agent wherever
they say it.

**A local link in the agent's final answer is an attachment declaration.** `[report](/absolute/report.pdf)`
attaches a file, `![preview](/absolute/preview.png)` attaches an image, and a local
`file:///absolute/path` destination works too. Percent-encoded characters in either local form are
decoded. Rundesk removes the machine path from the posted text,
opens any readable ordinary local file in place, fingerprints it, and has the adapter reopen and
verify the same bytes before sending. It never guesses from files the agent merely read or edited.
A declaration made in an earlier finished remark is held and attached with the final answer rather
than leaking its path mid-turn. Up to ten files of 32 MiB each may go with one answer; a file that
cannot go is named safely in the answer and logged with the full reason.

**Outgoing files are not copied or deleted.** Project output remains project output, and a temporary
Computer Use screenshot remains owned by that tool or the operating system. Discord's verification
snapshot exists only for the send and is closed afterwards. Incoming channel files are different:
Rundesk owns their landed copies under the channel's dated `in/` directory and sweeps whole days
after 60 days, including for channels later disconnected.

```console
$ rundesk channels
channels in /Users/you/.rundesk/data/agents
AGENT  CHANNEL  REACHES                          ALLOWED  TOLD  STANDING
alan   discord  rundesk#4471, reaching you#0     2        yes   connected (pid 96144)
cole   discord  colebot#8812, reaching you#0     1        no    not connected
```

`STANDING` is asked of the kernel through the claim an adapter holds, exactly as `rundesk gateways`
asks whether a gateway is up, and the record beside it is read only afterwards — a record holds a
pid, and a pid whose process is gone is a number that now belongs to something else. `cannot tell` is
a first-class answer there for the same reason it is one in `gateways`.

**`connected` means somebody is reading it, and the gateway is what keeps that true.** An adapter
runs for months and is listened to, so one that nothing is draining is receiving messages and
recording none of them — which is what a gateway killed outright leaves behind, and what an adapter
whose reader stopped becomes. A gateway ends any adapter it is not reading, on the beat, and starts
one it *is* reading in its place after the usual hold-off; the log says so in both halves:

```console
$ rundesk gateways logs alan -n 4
[…] WARNING: channel discord: adopted from a gateway that is gone, and nothing in this gateway is reading it
[…] INFO:    channel discord: ended, because nothing was reading it — another is started once the hold-off has passed
[…] INFO:    channel discord: started as pid 91586
[…] INFO:    channel discord: connected as rundesk#4471
```

An adapter is only ever signalled once the kernel has said its claim is still held — a pid read off
a claim nobody holds is a number that now belongs to something else. There is one state left over:
a gateway killed in the instant between claiming a channel and writing down the pid leaves an
adapter nothing can name, and that one is said in the log with the path of the claim it is holding,
because a state nothing here can resolve is a state to report and not to be silent about.

### channels add

`--allow` is required, is repeatable, and takes the id that platform knows somebody by.

**What the platform wants first.** Rundesk holds no list of what any platform needs, so what a
channel asks for comes from its adapter and is named on the refusal. For the shipped Discord adapter
that is three things, all of them from Discord rather than from here: a **bot token** (Developer
Portal → your application → Bot → Reset Token), the **Message Content Intent** switched on for that
bot (same page, under Privileged Gateway Intents — without it Discord blanks every message in a room
and in a thread unless it names the bot, and the gateway is closed with `4014` rather than
connecting), and your **numeric user id** for `--allow` (Discord → Settings → Advanced → Developer
Mode, then right-click your profile → Copy User ID; a username is not an id and can be changed). The
README's [Setting up a Discord bot](../README.md#setting-up-a-discord-bot) walks it through.

```console
$ rundesk channels add alan discord --allow 341709...
the discord adapter needs 1 value before alan can use it
        DISCORD_BOT_TOKEN__ALAN   the discord adapter reads DISCORD_BOT_TOKEN, and this is alan's own
        > 
alan is connected to discord
        reaches   rundesk#4471, reaching you#0
        allowed   341709...
        told      no
        needs     DISCORD_BOT_TOKEN__ALAN (set)
        settings  {}
        can       attach=True, edit=full, max_text=2000, react=True, stream=True, thread=True
        adapter   /Users/you/.rundesk/app/src/channels/discord
        keeps     /Users/you/.rundesk/data/agents/alan/channels/discord
        standing  not connected
        invite    https://discord.com/oauth2/authorize?client_id=...
        the bot is not in any server until somebody with permission adds it there
```

**`add` connects once and leaves nothing running**, which is what `standing not connected` on the
last line means — so the next thing to type is `rundesk gateways start <agent>`. The **invite** is
printed here and kept nowhere: `channels show` cannot reproduce it, so it is worth saving. A bot
already in a server has to be sent it again before it may open a thread or attach a file.

**A `FAILED` here does not always mean nothing was written.** `--notify` is marked inside the same
lock and after the row, and it has its own guard: where the channel was added and only the marking
failed, the failure says so and names `rundesk channels configure <agent> <adapter> --notify` rather
than sending somebody to add a channel that is already standing.

**`--notify` is the other half of a first setup, and nothing refuses its absence.** `--allow` is who
may *reach* the agent; `--notify` is where the agent *speaks first*. Left off, the channel connects
and answers when spoken to and never says anything unprompted — no gateway coming up or going down,
no schedule report, no delegation handing back a result. That is a legitimate thing to want, so it
is not an error; the only sign is `told no` in the block above. The up-notice is gated on the
notified channel having reached its platform, and an agent with no notified channel counts as ready
rather than waiting for a connection that will never exist.

So **make the owner's own direct message the notified channel on the first channel added**. Adding
it later is `channels configure <agent> <adapter> --notify`, followed by a gateway restart: the
up-notice is said once per gateway, and one already running has said it.

**An empty allow list authorises nobody, never everybody**, so leaving `--allow` off is refused —
by the verb rather than by argparse, in a sentence ending with the whole command to type. An agent
connected to a platform with nobody allowed is an agent that answers no one, and a stranger's message
is dropped in silence rather than answered with a refusal that would confirm somebody is listening.

**Nothing about a channel is written down until the adapter says it reached something.** The program
is found, asked offline what it can do, and then asked to connect; only an `ok` from that last
question writes a row. A channel that is misconfigured has to be found out about while somebody is
standing at a terminal, not at three in the morning when they ask the agent something.

**The credential is read from the terminal and never passed as an argument** — `env` says why at
length — and it is written down *before* the connection is proven, deliberately: somebody who has
just pasted a bot token should not have to paste it again because the connection was refused for an
unrelated reason. `rundesk env unset <name>` empties it.

**The name a credential is kept under is the adapter's own, and it is recorded rather than worked out
again.** `channels.hosting` hands the adapter each recorded name back with its value under that same
name, so the recorded name and the name the adapter reads are one fact.

**Where the value is kept is the agent's own, though.** One bot is one identity: two agents behind
one Discord token receive the same messages and nobody reading the room can tell which of them
replied. So what is typed above is kept under `DISCORD_BOT_TOKEN__ALAN` — the same profile naming
`rundesk skills` uses, on a name `rundesk env set` already accepts — and cole's under
`DISCORD_BOT_TOKEN__COLE`. Two agents on one platform are two bots without anybody having to arrange
it.

**One name is read, and a plain `DISCORD_BOT_TOKEN` is not one of them.** There is no fallback. A
shared name is exactly the shape that lets two agents be one bot by accident, and every way of
keeping it — read second, read only when nothing scoped exists — is that accident with a longer path
to it. A channel whose own name holds nothing is `BLOCKED`, said at a terminal, rather than an agent
quietly signing in as somebody else.

The adapter is handed the value under `DISCORD_BOT_TOKEN`, exactly as it declared it. **`channels
doctor` resolves it by the same call a gateway does**, so a channel reported `READY` is one whose
credential a gateway really finds — and a value that is there and cannot be opened is reported as
that rather than as missing.

**An agent's name is used, or the agent can hold no credential — it is never mangled.** An agent
already named something a variable can be — letters, digits and underscores, starting with a letter
— has a name of its own, upper-cased. Any other agent is **refused** a credentialled channel, by
`add`, before it prompts for anything, and reported `BLOCKED` by `doctor` with no command to type,
because there is no rename verb and no honest one to suggest. Nothing is folded: `a-b` and `a_b`
would both become `A_B`, and two agents would quietly share one bot. Such an agent may still have
any channel whose adapter needs no credential.

`--with '<adapter opts>'` is anything the adapter itself takes, as one quoted string. Rundesk parses
none of it and has no list of what any platform wants — what comes back in `settings` is the
adapter's own normalised account. It is split into words the way a shell would and handed over as a
list, so nothing in it is globbed, expanded, or read as `;`, `&&` or a redirection; it is a flag
rather than a bare `--` because argparse matches positionals in contiguous runs, and a flag between
them makes the most natural spelling of `--` an `unrecognized arguments` error.

`--notify` makes this the channel unprompted things go to. At most one channel per agent may be that,
and where it writes is what the adapter reported rather than something to go and find: a gateway
coming up is answering nobody and has no conversation to reply into.

#### Moving an existing channel onto the agent's own name

**Do this before you update to v0.41.0.** From that release a plain `DISCORD_BOT_TOKEN` is not read,
so a channel still relying on one stops working the moment the new gateway starts. Nothing rewrites,
copies or moves a value on your behalf — copying one token onto several agents would give them all
one bot, which is the thing this shape exists to prevent, and no program can create a second Discord
application for you.

The order matters, and it is: stage every scoped key first, prove it on the release you are still
running, then update, then restart. **Never any of it as an argument** — every value is typed at a
prompt or piped, so nothing lands in a shell's history.

**1 · While still on v0.40.x, put a key in place for every agent that has a channel.**

```sh
rundesk channels                             # every agent with a channel, and how each stands
rundesk env list                             # which names hold something. Hints only, never a value

# In the Discord Developer Portal, per agent: an application, its own Bot, Reset Token,
# and Message Content Intent switched on.

rundesk env set DISCORD_BOT_TOKEN__ALAN      # prompts without echoing. Or: printf %s "$T" | rundesk env set …
rundesk env set DISCORD_BOT_TOKEN__COLE
```

An agent may keep the bot it is already running as: set that agent's scoped name to the token it is
already using, and it stays the same bot with the same identity in the same servers. Every *other*
agent needs a new application, because one token cannot be two identities.

**2 · Check the staging with `env check`, which is the only verb that can answer yet.** v0.40.x
reads the plain name and nothing else, so `channels doctor` and `channels test` cannot tell you
anything about a scoped key while you are still on it — they would keep reporting `READY` off the
shared token right up to the update. What they *can* do is name every agent you have to cover:

```sh
rundesk channels                             # every agent with a channel — one key needed per row
rundesk env check DISCORD_BOT_TOKEN__ALAN    # exits non-zero until it is staged
rundesk env check DISCORD_BOT_TOKEN__COLE
```

A green `env check` for every agent in that listing is the whole of what can be proved before the
update. It says the key is there and readable; whether the token behind it is the right one is what
step 4 finds out.

**3 · Update, then restart.**

```sh
rundesk update
rundesk gateways restart <agent>             # a running adapter holds the token it started with
```

`rundesk update` restarts the gateways it stood down, so this is a check rather than a step for
those; an agent whose gateway you had stopped yourself needs starting.

**4 · Now prove it, on the release that reads the scoped name.**

```sh
rundesk channels test alan discord           # really connects, as this agent. Writes nothing
rundesk channels doctor                      # exits non-zero if anything is not ready
```

Read the `needs` line: it names `DISCORD_BOT_TOKEN__<AGENT>` and says `(set)`. A `BLOCKED` here is an
agent whose key was missed in step 1, and the summary names the one command that fixes it.

**5 · Then tidy up.** Once `rundesk channels doctor` exits zero and every `needs` line names a
`__<AGENT>` name, the shared one has no reader left:

```sh
rundesk env unset DISCORD_BOT_TOKEN
```

Open the invite for each new application and add that bot where you want it — a second application
is in no server until somebody puts it there, and the old bot goes on sitting in those servers until
you remove it.

**If an agent's name cannot carry a credential** — anything but letters, digits and underscores
starting with a letter — it can hold none, and `doctor` says so with no command to type. Nothing is
folded, because `a-b` and `a_b` would become one name and two agents would share one bot. The
answers are an agent whose name can carry one, or a channel whose adapter needs no credential.

### channels configure

Changes who may reach an agent there, and which channel is the told one. **Naming nothing to change
is refused rather than reported as a success**, and so is an id named both to allow and to deny.

```console
$ rundesk channels configure alan discord --allow 220755...
alan's discord channel changed
        allowed   341709..., 220755...
```

An id that was never on the list is refused rather than passed over — *"deny 2207"* aimed at a list
that never held it is somebody typing the wrong id, and answering "done" would leave them believing
they had taken away access they had not. Taking the last one away is refused too, because a channel
with an empty list answers nobody: remove the channel instead.

There is no `--confirm` here. It is on `remove`, and the line between them is the one `skills` draws:
would somebody want to read this before it happened. Setting a channel up is a credential, an allow
list and a round trip to a platform, and none of that comes back from a copy of `data/`.

### channels test

Asks the adapter to connect again with what the channel already has, and says what it reached. It
changes nothing at all, including the record of what it found — a token that was reset in somebody's
developer portal is the case this exists for, and the answer to that is a sentence at a terminal
rather than a channel quietly rewritten underneath whoever is reading it.

### channels remove

`--confirm` is required. Without it the command says exactly what it would take and takes none of it,
and exits non-zero: **a removal that did not happen is a failure.**

```console
$ rundesk channels remove alan discord
remove: this would take alan's discord channel
        take     the connection — alan would no longer be reachable on discord, and 341709... could no longer reach it there
        keep     /Users/you/.rundesk/data/agents/alan/channels/discord — what arrived through it, and what its adapter wrote
        keep     DISCORD_BOT_TOKEN__ALAN — rundesk env forgets nothing here
        nothing was removed. To go ahead:
        rundesk channels remove alan discord --confirm
```

What arrived through the channel stays, and so does the credential. Both are named in the preview
rather than left to be discovered: a removal that described more than it would do defeats the point
of describing it, and one that described less would be worse. The credential is named as the name it
really stands under — `DISCORD_BOT_TOKEN__ALAN` — because that is the name somebody would have to
type to `rundesk env unset` it afterwards.

### channels doctor

Says what cannot be used and why, names the one command that answers it, and **exits non-zero when
anything is wrong** — the way `env check` and `skills doctor` do, so a script can gate on it.

```console
$ rundesk channels doctor
alan
  discord  READY        rundesk#4471, reaching you#0
cole
  discord  BLOCKED      DISCORD_BOT_TOKEN__COLE — nothing this install can read is kept under that name
  quiet    DANGLING     there is no quiet adapter on this install — looked in ...
channels: 2 of 3 cannot be used:
        rundesk env set DISCORD_BOT_TOKEN__COLE
        rundesk channels remove cole quiet --confirm
```

**The one name a credential stands under is what is said**, and it is the one the summary tells you
to set. There is no second place to look, so naming a plain `DISCORD_BOT_TOKEN` here would send
somebody to set a value this release ignores. An agent whose name cannot carry a credential at all is
`BLOCKED` saying exactly that, and gets **no** command in the summary — there is no rename verb and
no honest thing to type.

| Verdict | Means |
|---|---|
| `READY` | the adapter is there, its credential is set, and it connected just now |
| `BLOCKED` | no name this channel's credential could stand under holds anything this install can read — including one that is there and cannot be opened, which is never read past to the shared name |
| `UNREACHABLE` | everything is in place and `--check` failed now — the platform said why |
| `DANGLING` | there is no program behind this channel any more |
| `GIVEN UP` | it checks out from here, and the gateway hosting it has stopped trying to start it |

An agent whose channels cannot be read at all is a fifth outcome and is not a verdict: it is reported
under that agent's own name — *`<agent>`'s channels cannot be read — …* — and counted in the same
denominator, because an agent whose records will not open is not an agent with no channels.

**`GIVEN UP` is the one verdict that does not come from the adapter.** This verb asks in a process of
its own, so a failure that shows itself only once an adapter is really serving — a close code the
platform will answer with for ever — leaves every question here answered correctly. When an adapter
exits `78` its gateway stops starting it for the rest of that gateway's life, and until this verdict
existed the channel was reported `READY` while nothing had hosted it for hours. `rundesk gateways
restart <agent>` is the whole of the fix, and it is what the summary tells you to type.

**It really connects**, and that is what `UNREACHABLE` costs. A credential that is set and no longer
accepted is the failure this exists to find, and nothing on this machine can tell that from a working
one: the adapter has to be asked. A channel whose credential is missing is `BLOCKED` without paying
for a round trip.

The columns are measured against what is actually there rather than fixed. The findings go to stdout
and the summary to stderr, so a script can read one and ignore the other — and the findings are
flushed first, or the summary would appear above what it summarises when both are merged into one
pipe.

## providers

The brains this install can run. A provider is a **program rundesk runs**, never code it loads, so
this asks about programs — where each one is, and what it says it can do. All three verbs are
offline: none runs a turn, needs an account, or reaches a network.

```console
$ rundesk providers
providers in /Users/you/.rundesk/app/src/providers and /Users/you/.rundesk/data/providers
PROVIDER    PROGRAM
a-stand-in  /Users/you/.rundesk/data/providers/a-stand-in
claude      /Users/you/.rundesk/app/src/providers/claude
codex       /Users/you/.rundesk/app/src/providers/codex
grok        /Users/you/.rundesk/app/src/providers/grok
```

A bare name resolves among the ones that ship and then among the ones this install has been given, in
that order — a release's own adapter is what somebody gets by typing its name, and an install cannot
quietly shadow it. Anything with a separator in it is used as a path, so an adapter being written
right now needs nothing installed anywhere.

```console
$ rundesk providers check a-stand-in
a-stand-in
  program   /Users/you/.rundesk/data/providers/a-stand-in
CAN     IT SAYS
tools   yes
resume  yes
model   no
usage   yes
steer   no

it also said, and rundesk did not ask:
NAME     VALUE
version  "0.146.0"
```

**Absent means no.** An adapter that answers `{}` can do none of it, which is a complete and honest
answer rather than an error — a plain conversational CLI is a first-class brain here, not a degraded
one. Anything it reported that rundesk did not ask about is shown as it said it, because a version an
adapter volunteers is what somebody reads a month later to find out what changed under them.

```console
$ rundesk providers instructions ava --layers
LAYER           BYTES
core            510
a_person_asked  593

1105 bytes in 2 layers, 3fe0d980fc34
```

What a brain is told before it reads a word of the task, with what each layer costs. Without
`--layers` it prints the prompt itself; with `--trigger` it renders a different situation. Naming no
agent leaves the placeholders standing, which is how to read the shape of a layer on an install with
no agents in it.

The number at the end is a fingerprint of the whole. Every turn records it, so what a brain was told
is provable afterwards without a copy of it being kept — and a prompt that changed between releases
says so rather than leaving somebody to guess.

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

To ask on a gateway's behalf, ask from inside a turn: `"$RUNDESK_COMMAND" permissions check`.

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

[`permissions.md`](permissions.md) has the whole of it, and
[`research/2026-08-08-what-this-mac-lets-a-process-do.md`](research/2026-08-08-what-this-mac-lets-a-process-do.md)
has the measurements.

## messages

What an agent has been told, and what it said back.

**The agent is the first caller of this, before its owner is.** A person refers to work the agent has
no record of — *"the invoice bug you looked at last week"* — and the agent reads its own history back
before answering rather than saying it does not know. Its own instructions name this command for
exactly that.

```console
$ rundesk messages ava --search invoice
2 ava said or was told holding 'invoice'
WHEN                  WHO   WHERE            IN  SAID
2026-08-06T13:11:29Z  user  discord 9930-ops  2   [invoice] again, different room
2026-08-06T13:11:29Z  user  discord dm-4471   1   the [invoice] bug is in the parser
```

One bounded line each, because every line the agent reads costs tokens and a listing that answered
with fifty whole messages would spend a turn's budget on finding out what the turn was about.
`--full` prints bodies. `IN` is the conversation, which is what `--conversation` takes.

**`WHERE` says what carried it *and* which exchange on that thing**, and the second half is not
decoration. A private message and a public room are both `discord`, and two schedules are both
`schedule` — so an agent reading its own history back could not tell what it had been told in
confidence from what it had said in front of a room, and one asked *how did the client update go*
got a listing in which nothing said which schedule any line came from. The second word is the
platform's own name for the place, or the schedule's own name, and it is what
`rundesk schedules show` is typed with.

Four ways to narrow and they compose: `--search` for words, `--channel` for where it was said,
`--source` for what kind of thing started it, `--conversation` for one exchange, and `--since` for a
day. With no words at all it is the conversation read back, newest first.

**`--search` takes words, and only words.** Whatever you type is matched as the words themselves, so
`C++`, `it's fine` and `50%` all mean what they look like. There is no query syntax to learn and none
to get wrong: `AND` is the word *and*, a bare `"` is a quote mark, and several words means a message
holding all of them. This is why there are no operators — the alternative was a search that answered
an apostrophe with an error about the agent's records.

**An empty answer says what was looked for**, so "nothing matched" is readable apart from "you
narrowed it to nothing":

```console
$ rundesk messages ava --search invoice --channel nowhere
nothing ava said or was told holding 'invoice', on nowhere
```

**Where an install has no full-text index it says so.** SQLite is not always built with one; the
search then falls back to matching plain text, which finds different things — no stemming, no phrase,
no ranking — and somebody comparing two answers has to know which they got.

## turns

Every turn an agent has taken, what each cost, and what one actually did.

`rundesk messages` is what was *said*; this is what it *cost* and what became of it. Two different
questions, kept apart because they are read for different reasons and answered from different tables.

```console
$ rundesk turns ava
turns ava has taken, newest first
TURN  WHEN                  WAS   IN  COST                           UNKNOWN  LOST
2     2026-08-06T13:39:13Z  done  2   20in 1510out 302567cr 17453cw  0        0
1     2026-08-06T13:38:14Z  done  1   20in 1510out 302567cr 17453cw  0        0
```

The four billed quantities are shown apart because they are billed at three different rates — fresh
input, cache reads and cache writes — and a single total would be a number that is real and
misleading. **A dash is not a zero**: it means nobody reported one, and a cost nobody measured and a
cost of nothing are different answers.

**`UNKNOWN` and `LOST` are how a vendor moving under you becomes visible.** The first counts records
this release did not understand and the second records that never arrived. Both are zero on a healthy
turn; both climbing means an adapter and its brain have drifted apart, and nothing else in the product
will tell you before somebody notices an agent behaving oddly.

With a turn as well, it shows that one whole: what it was admitted with, what the adapter said it
could do, every record in the order it happened, what it came to — and, where it did not answer,
whether waiting will help or whether somebody has to act.

## ask

Ask an agent something, here, in this terminal, and watch it work.

```console
$ rundesk ask ava "what changed in the queue today?"
  read
    3 files changed
Nothing urgent — three merged pull requests and one rename.

20 in, 1510 out, 302567 cached, 17453 written · 9200 in the conversation  ·  turn 7
```

The attended way in: a gateway answers a channel and the clock starts a schedule, and this is a
person typing. Type while it works and the words are offered to the active brain, if that brain said
it can be steered. Messages arriving through a channel and guidance sent with `asked say` use the
same active-first rule; anything that misses or is refused stays durable for a following turn.

Tools are shown by what they **did** rather than by whatever the vendor calls them, so a `Bash`, a
`shell` and a `run_terminal_command` all read as `ran`. Prose is shown when it is finished and never
while it is being written, because a reply that rewrites itself in place is unreadable. `--thinking`
adds what it is reasoning about, which is long and off by default.

**One conversation per agent, not one per command** — asking again carries the same exchange on,
which is what a person means by asking again. `--fresh` starts a new one on the brain.

**It refuses rather than queues.** A conversation already being answered in is busy, and the claim
is the kernel's, so this competes correctly with a gateway answering the same agent on a channel
with no coordination between them.

### Run from inside a turn, it hands work over instead

**One agent asking another is a delegation, whichever verb was typed.** Typed by a person, `ask` is
what it always was. Run by an agent from inside its own turn — naming somebody other than itself —
it hands the work over and returns at once:

```console
$ rundesk ask bob "audit the exporter retention policy and report what you find"
handed to bob  ·  del-1-6c9092
  asynchronous — the result reaches this turn if active and steerable; otherwise wakes a review turn
```

This is the front door rather than a second command, and it is not a convenience. Left alone, an
agent could run a whole turn on somebody else's agent from inside its own — no record, no guards,
and nobody owed a review. The build this replaces shipped exactly that and found every rule the
feature is made of was one command away from being bypassed.

**Nothing waits.** Bob's own gateway picks the work up and answers it as itself out of its own home
and memory. The result reaches ava's current turn if it is still running and steerable; otherwise it
wakes a review turn. What ava gets is bob's last complete message, verbatim and labelled unchecked — rundesk
summarises nothing and asserts nothing about it — and nothing bob wrote reaches any person until ava
has reviewed it.

**Five things are refused**, each with what to type instead:

| | |
|---|---|
| a person typing it | not a delegation — it is an ordinary turn on that agent |
| an agent naming itself | that is a turn, not a delegation |
| a turn already answering a delegation | work handed over cannot be handed on again |
| a target outside the asking agent's delegation scope | change that agent's scope, or keep the work here |
| an agent whose gateway is not running | nothing would ever answer it, so it says how to start one |

The last is the one worth knowing about operationally: **an agent you intend to delegate to needs a
gateway running.** Its own gateway is what picks the work up, so `rundesk gateways start bob` is a
prerequisite, and launchd brings it back at every login afterwards. A delegation to an agent nothing
is running would otherwise wait for ever while the agent that made it believed it had handed work
over, which is a success nothing earned.

`rundesk asked --agent ava` lists ava's work. `asked say <id> <words>` durably adds guidance to
working work. The recipient's gateway offers it to the active provider turn immediately; if that
turn has just ended or cannot be steered, the guidance remains for its next turn on the same
delegation. `asked stop <id>` records an early end request; the recipient's next gateway beat stops
the live provider process group, or settles an unstarted brief as stopped without launching it. The
listing says `stopping` until that terminal outcome comes back, then settles it without waking the
asking agent for another review response and lists it as `stopped`, never `answered`. Stopped work
cannot be resumed. `asked resume <id> <words>` continues answered work in the provider session it
already had. Each delegation has its own
conversation, so two tasks handed to the same specialist by one parent turn cannot share an answer.

**All three are shown where the person asked**, in the room the work was handed out in, as one line
of small print — *updated bob*, *asked bob to stop*, *carried on with bob*. Never the words
themselves: guidance is between two agents. Saying nothing here was what made steering invisible to
somebody watching a channel, who saw work go out and then nothing until it came back.

**`resume` starts the clock again; `say` and `stop` do not.** How long work has been out is counted
from the phase it is in, so carrying an hour-old ask on reads as *carried on with bob* and then
silence until the new work is twenty minutes old, and the answer says how long that new work took
rather than how old the ask is. The delegation keeps its id, its conversation and its provider
session throughout — resuming is the same ask continued, which is the whole difference between it
and handing the task over again.

**The depth is one.** An agent answering a delegation is shown no team in its instructions and is
refused here if it tries anyway, so `ava → bob → ava` has no path to exist and there is no chain to
walk. A turn woken to *review* an answer is an ordinary turn and may hand out new work, subject to
the reviewing agent's current delegation scope.

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

Where these are kept and what protects them is [`layout.md`](layout.md) — the short version is that
the files are yours alone, each value is sealed on disk with a key kept beside it, and a backup
carries both. Protect backup storage as credential-bearing data.

## skills

The skills this install has, which agent holds which, and what each of them needs to work. A
**catalog** is what you install, update and remove; a **skill** is what you grant. Nothing installs
one skill and nothing removes one, because a catalog is what somebody publishes and follows.

```console
$ rundesk skills
skills in /Users/you/.rundesk/data/skills
CATALOG         SKILL             AGENTS
rundesk         managing-rundesk  alan, ben
rundesk         writing-skills    —
rundesk-skills  writing-plans     alan
local           my-thing          —

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
operates *this* version, so it is never fetched and never removable. One skill in it,
`managing-rundesk`, is a floor every agent holds: `revoke` refuses it, and `rundesk update` gives it
back to an agent standing without one. `rundesk-skills` is the general
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
  jira           rundesk-skills  PARTIAL   2 of 3 profiles are usable
      acme  ready
      beta  ready
      gamma  INCOMPLETE
          JIRA_API_TOKEN__GAMMA — an API token from id.atlassian.com
  writing-plans  rundesk-skills  READY     needs nothing
  old-thing      —               DANGLING  the grant points at nothing
skills: 2 of 3 cannot be used:
        rundesk skills configure rundesk-skills/jira --profile gamma
        rundesk skills revoke alan old-thing
```

The columns are measured against what is actually there rather than fixed, so a long catalog name
does not run into the next one. The findings go to stdout and the summary to stderr, so a script can
read one and ignore the other — and the findings are flushed first, or the summary would appear above
what it summarises when both are merged into one pipe.

| Verdict | Means |
|---|---|
| `READY` | every profile is complete, and every command it ships would run |
| `PARTIAL` | at least one profile is usable and at least one is not |
| `BLOCKED` | no profile is usable — a required value is missing everywhere |
| `UNRUNNABLE` | every credential is in place and a command it ships is not executable |
| `UNSEEN` | the grant is there and no provider can find it; `rundesk update` links it, unless something of yours holds the name |
| `STALE` | a copied grant is behind the catalog it came from; `rundesk update` remakes it |
| `DANGLING` | the grant no longer resolves — its skill left its catalog, or the catalog went |
| `BROKEN` | the skill itself will not load, or what it declares cannot be read |

`PARTIAL` exists because two working Jira sites and one half-configured is neither a healthy
integration nor a broken one, and collapsing it either way would cry wolf on a working setup or hide
the site that fails at three in the morning.

`UNSEEN` exists because a grant and its linking are two separate writes. The link into each provider's
own root is made after the grant, under a lock of its own, so it can be refused on its own — and what
that leaves is a skill that is correct in every listing and invisible to every brain. `grant` sends anybody who
meets that refusal here, so this is the command that has to be able to answer it. (`revoke` does not,
and deliberately: it takes the grant away before it links, so by the time it can fail there is no
grant left for this command to look at. It names `rundesk update`, which clears the leftover links.)

**`UNSEEN` has two causes and only one of them is rundesk's to fix.** A provider root with nothing
under the name is linked by the next sweep, so `rundesk update` repairs it. A root where a link or
directory of *your own* stands under that name is one rundesk will never replace — so it says what is
in the way and offers no command, because there is not one: move that entry, or hold the skill under
another name with `rundesk skills grant … --as <name>`.

Writing a skill or publishing a catalog is [`catalogs.md`](catalogs.md).

## update

Moves this install to the newest published release, or says it is already on it.

```console
$ rundesk update
0.40.0: OUT OF DATE — v0.41.0 is available, run: rundesk update
        installing v0.41.0
rundesk updated to v0.41.0
        what changed: https://github.com/rundesk-ai/rundesk-cli/releases/tag/v0.41.0
```

Takes no flags. The order is chosen so the failure that cannot damage anything happens first: ask,
then fetch to a temporary directory, stand down every online gateway, then swap and settle. The swap
stages every entry and renames them into place, putting back what was there if any part fails — so an
interrupted update leaves the install on the release it was, never on neither. Gateways that were
already offline remain offline; every gateway the update stopped is started again by the release
that landed, never by the updater's cached old job logic. A foreground gateway whose name launchd
cannot supervise must be stopped in its terminal first, because an unattended update cannot restore
it and will not take it offline permanently.

If a provider turn or schedule is active, a manual update is recorded durably and returns without
fetching or stopping anything. A detached install-level worker waits for the install to become
quiet, closes new-work admission, and then runs the ordinary update transaction. The worker has no
agent, conversation, turn, or delegation context, so infrastructure work never appears as activity
inside a DM. Losing the worker does not lose the request: the daily coordinator sees the same
`queued-update.json` and retries it. A failed attempt remains owned by the detached worker and is
retried with a hold-off; uninstall cancels the request and excludes that worker and every other
update for the full removal transaction before it touches the coordinator or program.

The notified channel receives these maintenance notices around a successful update:

- `🛠️ Installing an update — I'm installing the new rundesk update, be back shortly.`
- `👋 I'm back — new rundesk update installed, release notes for v0.41.0`, with the release notes
  linked to that version.

The return notice is written only after the new release settles and is consumed only by a gateway
running that exact version. An ordinary stop/start keeps the ordinary gateway notices.

The program-tree swap never replaces `data/`; migration steps may deliberately carry its layout.
When migration work is waiting and `backup_enabled` is on, settlement first makes and verifies the
safety copy described under `backups save`. If that copy cannot be made, migration does not begin
and the update fails with the reason; turning backups on therefore guarantees a rollback boundary
rather than merely requesting one.

**Being on the newest release is not the same as being settled on it.** An update interrupted between
replacing the files and settling — a machine that slept, a terminal that closed — leaves an install
whose code is current and whose configuration and migrations belong to the release before it. So
`rundesk update` settles the install even when it reports `UP TO DATE`; everything it does is
idempotent, and running it again is how you finish an update that stopped halfway.

When `update_enabled` is on, launchd makes one attempt per local calendar day at `update_time`.
The coordinator is outside every gateway process tree and uses the same update transaction as this
command. Before asking for a release it closes work admission and inspects kernel-held provider and
schedule claims. Active work, or activity that cannot be inspected safely, produces a logged
`DEFERRED` outcome and a private durable request; one detached install-level worker waits until all
turns and schedules finish, then uses the same update transaction without forcing work down. A
request already waiting is preserved and given a worker rather than replaced. Repeated launchd
starts while that worker owns the queue claim are logged and skipped. Failures remain non-zero and
the durable worker retries through the same rerunnable settlement path as a manual update.
The job carries a fixed minimal system `PATH`, so reconciliation and status do not change according
to the shell or development environment that happened to invoke them.

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

- the root-specific automatic update job and generated shim, before `app/` goes
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
- `data/`, **only with `--purge`**, including the live credential store below it
- `backups/` — **never.** Not "not by default": there is no argument to this command that reaches
  them. Copies can contain recoverable credentials, so purging the live store is not the same as
  removing every credential from the machine.

A removal that did not happen is reported as a failure. That is the whole point of the command.

## install

What `install.sh` runs after it has fetched a copy. Usable by hand from a checkout:

```sh
./rundesk install --bin-dir ~/.local/bin
```

It places the program, lays down the directories and their notes, writes or fills in the
configuration, carries the migrations, reconciles the daily update job, links the command, and then **proves the installed command
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

Five commands are written to have their code read by a script, and they are the ones to build on:

- **`rundesk env check <key>`** exits non-zero when a value is not set, so
  `rundesk env check DISCORD_TOKEN && …` does the right thing in a shell.
- **`rundesk version`** exits `0` even when it could not reach GitHub, because the question it was
  asked — what version is this — was answered from the machine itself. Being unable to ask is said
  on stderr as `UNKNOWN` and is never reported as being up to date.
- **`rundesk gateways start <agent>`** exits `0` only once a gateway has been shown to be holding
  the name. A job the supervisor accepted is not a gateway that started, and the exit code here
  means the second thing.
- **`rundesk channels doctor [<agent>]`** and **`rundesk skills doctor [<agent>]`** exit non-zero
  when anything is wrong, and `0` when there is nothing to check at all — an install with no channels
  is not an install with a broken one. The findings go to stdout so a script can read them and the
  summary to stderr so it can ignore them.

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
