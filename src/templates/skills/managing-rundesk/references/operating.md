# Operating rundesk

Read this for the exact commands behind any of the areas the skill lists — agents,
gateways, channels, and what an install is made of.

## Managing rundesk

You can operate rundesk with the same command your owner uses. Everything below is real and
built.

**Agents.**

```sh
rundesk agents                 every agent, and what each is doing
rundesk agents <name>          one agent: what it is, and where it keeps things
rundesk doctor <name>          what stands between an agent and a working turn
rundesk add <name>             make an agent, and the gateway that runs it
rundesk configure <name>       change its provider, model, settings, or instructions
rundesk remove <name>          take one away for good
```

`add` makes the agent *and* its gateway; `remove` takes both. There is no way to end up with
one without the other. `rundesk configure <name> --provider <provider>` changes an existing
agent's default brain without replacing it; provider-specific model and settings are cleared
unless replacements are supplied. The same verb changes `--model`, `--set`, and
`--instructions` defaults.

**Running them.**

```sh
rundesk start <name>           have the machine keep it running
rundesk stop <name>            stand it down
rundesk restart <name>         cycle it, leaving the others alone
```

**Reaching them.**

```sh
rundesk ask <name> "…"         one turn, streamed back
rundesk channels <name>        what it is reachable on — add, show, remove, instructions
rundesk schedules <name>       what it runs on its own — add, on, off, remove, run
```

**Handing heavy work to a specialist.**

```sh
rundesk roles <name>                    what it can hand work to, and what it has
rundesk roles <name> run <role>      hand one bounded task on — the brief is read from stdin
rundesk roles <name> show <run>         one run in full
```

A role is two files an owner writes below where agents are kept: `role.json` naming a
description, the skills that role exposes, and a posture; and `AGENTS.md` holding the rules
one execution follows. Everything else is worked out — the name is the directory, and the
revision is a digest of what the role is, so nobody maintains a version.

Handing work on is something an agent does *from inside its own turn*, which is why the brief
comes in on standard input rather than as an argument. What happens then:

- the run is admitted and everything it will use — the rules, the skills, the brief — is copied
  into a bundle of its own and never changes for that run;
- the agent's turn can end; the gateway carries the work;
- the worker stands in the project you named, so that repository's own instruction files apply
  to it, and it is given the role's skills and none of the agent's;
- when it finishes, the agent is woken once to read the report, check it, and answer.

The worker is not another agent. It has no home, no memory, no history, and it cannot start a
role run of its own. It is refused a target inside the agent's own home, it can never do
more than the turn that delegated to it could, and a run stays resumable for a fortnight after
its last activity before its bundle is swept — the record of what it did stays.

On a single-user Discord channel, `/provider <provider>` changes the agent-wide default
after Rundesk checks authorization and the adapter. The next message in that Discord
conversation starts fresh; an already-running turn finishes with the provider it began
with. Shared channels cannot change an agent-wide default.

**Schedules are their own skill.** What a schedule is *for*, how to say when, where its
outcome lands and what a channel that spans a server does to that are all in
`managing-schedules`. A fresh configuration requires that grant for every new agent.
If it is on this machine and you were not given it, say so rather than guessing at the parts.
The one thing worth carrying here: a schedule is the owner's clock, never a way to move your
own work out of the turn you are in.


**What things cost, and how rundesk itself is.**

```sh
rundesk usage [<name>]         what every agent has cost, or one of them
rundesk status                 how rundesk is on this machine
rundesk version                what is installed, and whether it is current
```

**Backups are their own skill.** What a copy holds, when taking one is worth it, and why
putting one back is never yours to decide are in `managing-backups`. Reach for it
before anything irreversible.

**A credential is never typed as an argument.** Anything on a command line is readable through
the process list and is written into shell history. Where a channel needs a token, rundesk
takes it on standard input or from a file the owner already controls. Never put a secret in a
command, a file you write, or anything you say.

## When something is not there

If a command you expect does not exist, you are on an older rundesk than this file describes —
check `rundesk version`. If a command exists but reports `NOT AVAILABLE`, it is registered and
not built yet: rundesk declares its whole surface from the outset so that nothing pretends to
have worked. Either way, say what you found rather than working around it.
