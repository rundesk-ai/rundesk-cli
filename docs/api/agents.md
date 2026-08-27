# Agents

## agents

The agents this install keeps — one directory each, under `data/agents/`, and what stands inside one
is [`layout.md`](../concepts/layout.md). With no sub-verb it lists them, because listing is what somebody wants
nine times in ten.

| Command | Does |
|---|---|
| `agents [list]` | every agent this install keeps, and what is behind it |
| `agents add <agent> --provider <provider> [--alias <alias>] [--describes <text>]` | make one |
| `agents configure <agent> [--provider <provider>] [--alias <alias>] [--describes <text>] [--self-improve <true\|false>] [--delegate-to <agent> … \| --delegate-to-any \| --delegate-to-none]` | change what one is configured with |
| `agents remove <agent> --confirm` | take one away, and everything it remembers |

```console
$ rundesk agents
agents in /Users/you/.rundesk/data/agents
AGENT  PROVIDER  DESCRIPTION                  SKILLS                                DELEGATES TO  SELF-IMPROVE
ada    claude    Owns research and synthesis. managing-rundesk, researching-topics  any           yes
cole   codex     Owns bounded implementation. managing-rundesk, reviewing-code      forge         yes
```

The description is the stored routing sentence supplied with `--describes`; whitespace is flattened
so even an older multiline value remains one table cell. `not described` means no sentence was set,
`empty description` preserves a legacy empty value, and `not available` marks a legacy record that
cannot expose the field. Skill names are current grants. Together with delegation scope, these let a
person or routing agent inspect which standing specialty belongs behind a name without loading a
skill body.

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

Listings use one name-ordered table. An agent's purpose, skills, and delegation scope provide the
routing context without a separate type.

### agents add

Makes an agent: its records, `home/`, `logs/`, and the files it lives by. `--provider` is required.

```console
$ rundesk agents add cole --provider claude
agent cole added
        provider  claude
        home      /Users/you/.rundesk/data/agents/cole/home
        logs      /Users/you/.rundesk/data/agents/cole/logs
        records   /Users/you/.rundesk/data/agents/cole/state.db
        rules     AGENTS.md, CLAUDE.md, MEMORY.md — how it works, and what it learns
        workspace plans/, research/, scripts/, retros/, tasks/ — agent-owned work, organized
        skill     rundesk/managing-rundesk — how it operates this install
        note      the provider is recorded and not proven — check it with: rundesk providers check
```

#### What a new agent is given

**Every new agent is given the files it lives by**, in its own `home/`: `AGENTS.md` is how it works
and `MEMORY.md` is what it has learned that is still true, and `CLAUDE.md` is the first of those
under the name some brains look for first — the same bytes, placed twice. They are the agent's and
the owner's to edit from that moment. An update restores an absent rule or work-area note and never
replaces one that is there, whatever it has been changed to. It does not recreate an absent
`MEMORY.md`, because removing that file is how an owner says this agent keeps no cross-run memory.

The home also starts with `plans/`, `research/`, `scripts/`, `retros/`, and `tasks/`. Each carries a
short README describing what belongs there, how to keep it current, and its safety boundary. The
first four hold durable agent-owned work. `tasks/` holds active resumable briefs that the agent
removes after completion; neither kind moves canonical project state out of its project or preserves
disposable scratch. Updates fill an absent folder note but never replace one already there.

#### What `MEMORY.md` is for

`MEMORY.md` is compact durable learned context for the next run, not another instruction file, a
transcript, or a project notebook. It keeps owner preferences, recurring traps and gotchas, stable
facts and references, and hard-won lessons. It does not repeat the agent's role and responsibilities
or any operating, project, or skill instructions. Commands, deliverable paths, assignments, changing
state, dates, and history stay with the project or task system. Memory keeps the current fact instead
of a dated correction story; a turn that learned nothing durable leaves it alone.

When useful durable context would make `MEMORY.md` dense, the agent may link from it to a canonical,
purpose-named index in its home. `PROJECTS.md`, `CLIENTS.md`, and `OPEN_ITEMS.md` are examples, not
files every agent should create. An index earns its file only when the role has enough reusable
detail; it may include a stable entrypoint when that prevents repeated discovery. The agent reads it
when relevant and applies the same correction, compaction, and stale-entry removal rules. The link
keeps `MEMORY.md` as the small first-read map and prevents detached notes the next session would
never discover.

#### The weekly upkeep pass

Periodic compaction and workspace upkeep are a focused Rundesk-management task, not daily prompt
weight. The bundled `managing-rundesk` skill has conservative maintenance, retrospective, and
self-improvement references for one focused upkeep pass. Maintenance runs first,
preserving unavailable active mappings, uncertain files, deliverables, provider-managed content,
symlinks, and project/user files; only confirmed stale continuity and agent-created obsolete clutter
are removed.

The retrospective phase reads the previous weekly entry, reviews bounded public evidence, and
updates one dated diary with what went well, where the agent failed or caused repeated asks, and an
evidence-backed candidate action or honest no-change. It records observable correction,
dissatisfaction, or distrust without diagnosing the owner's mood, retains compact older entries as
longitudinal evidence, and promotes a lesson only after repeated evidence or an explicit durable
owner preference. The final phase starts with that diary and previous
`weekly-self-improve-upkeep` reports, then reviews a bounded sample of other messages and turns for repeated
friction, corrections,
missing context, failed outcomes, and ignored capability routes.
Heavy bounded work stays delegated to a materially better active named agent; a same-turn helper
is next when no named agent fits; a skill is recommended only for a recurring capability
this agent must own and neither route covers. The pass compares relevant available and granted skills
only when selected friction indicates a capability gap, never revokes from non-use alone, and changes
no grants or standing rules without explicit authority. Its
scheduled response is deliberately short and attention-first: owner actions only, or one line saying
upkeep completed and no action is needed.

#### Every agent holds `managing-rundesk`

**Every agent is given `rundesk/managing-rundesk`**, which is how it operates the install running
it — where things are, what its own gateway is doing, which values are set. It is a floor of the
product rather than a choice: `rundesk skills revoke` will not take it away, and `rundesk update`
gives it back to any agent standing without one. An install whose catalogs have not been placed yet
says so on this line instead, and the next `rundesk update` grants it.

#### The provider is recorded, never proven

**The provider is recorded and it is not proven**, and the command says so every time —
adding an agent runs no adapter, asks nothing what it can do and finds out about no
sign-in. `rundesk providers check` is what answers that. Nothing in
this release runs one: no credential is checked, no request is made, and there is no gateway to
start. An agent added with a provider nobody has ever spelled correctly looks exactly like one that
works, and a line implying otherwise would be a success this release did not earn.

#### `--describes` is what the other agents read

**`--describes` is what an agent is for, in one sentence, and it is what the *other* agents read.**
Every agent's preface lists its colleagues and what each is for, so this is how one agent decides
whether a piece of work is somebody else's to do. An agent nobody has described is left out of that
listing rather than named blank: a bare name in a team list is an invitation to guess, and
guessing is what this field exists to prevent. It is capped at one sentence, because every agent's
description is charged to every other agent's prompt on every turn.

`configure` takes any combination of its flags, and every named value moves in one write. It never
rewrites `AGENTS.md` or `CLAUDE.md`, because those may contain owner customizations; changing
persistent behavior requires an explicit, separately reviewed edit to both files. An empty
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

#### A name launchd cannot label

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
$ rundesk agents configure cole --provider claude
cole: provider is now claude
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
