# Install and run a team

A team catalog is a repository that declares named specialists — their instructions, memory policy,
delegation scope and skills — and installs them as real agents. Installing one is always two
commands: a preview, then the same command with `--confirm`.

What a team is once installed is [`../concepts/teams.md`](../concepts/teams.md); the verbs are
[`../api/teams.md`](../api/teams.md); publishing one is
[`../extending/catalogs.md`](../extending/catalogs.md#building-a-team-catalog).

## 1. Preview

```sh
rundesk teams install https://github.com/rundesk-ai/rundesk-team-development --provider codex
```

Nothing is installed or changed. The preview is where you read:

- which shared catalogs will be **installed** and which will be **reused**;
- each member it would create, and with which provider;
- what each member's instructions, memory, skill allowlist and weekly upkeep would become.

`--provider` applies only to agents the command *creates*. It is required when there is a member to
create.

## 2. Confirm

```sh
rundesk teams install https://github.com/rundesk-ai/rundesk-team-development --provider codex --confirm
```

**A declared member name that already exists is refused**, and the refusal names the exact
`rundesk agents remove <agent> --confirm` to run first. That is deliberate: every member has to begin
from its catalog-owned instructions rather than inheriting whatever an existing agent had.

A confirmed install that fails part-way leaves no team — the catalog is taken away again and every
agent it created is removed.

## 3. Start only the agents you want

Members are created with their gateways **stopped**.

```sh
rundesk teams
rundesk gateways start forge
```

An agent with no gateway running cannot be reached on a channel, cannot run a schedule, and cannot
answer a delegation.

## 4. Update

```sh
rundesk teams update development-team
rundesk teams update development-team --confirm
```

Update reconciles every declared member **even when the fetched tree is unchanged**, so it is also
how you repair local drift in instructions, memory, delegation scope or the skill allowlist.

`rundesk update` and the daily updater check installed teams too, without a separate confirmation.
They stand down only members that were online and start exactly those again.

## Skills without the agents

The same repository installs as an ordinary skill catalog if you only want what it teaches:

```sh
rundesk skills install https://github.com/rundesk-ai/rundesk-team-development --confirm
rundesk skills grant ava rundesk-team-development/managing-development-work
```

No agents are created and no team marker is written. Installing the team later promotes that catalog
in place and creates the declared agents, keeping the skills already installed.

Once a catalog was installed through `teams install`, ordinary `skills update` and `skills remove`
can no longer move it independently of its agents.

## What to check afterwards

```sh
rundesk agents           # every member, its provider, skills and delegation scope
rundesk skills doctor    # anything a member holds and cannot use
rundesk gateways         # which members are actually up
```
