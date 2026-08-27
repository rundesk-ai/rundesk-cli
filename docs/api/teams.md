# Teams

## teams

A team catalog adds version-controlled named agents to an ordinary skill catalog. What a team is
once installed, and everything reconciliation puts back, is
[`concepts/teams.md`](../concepts/teams.md). This is what each verb takes and what each refuses.

| Command | Does |
|---|---|
| `teams [list]` | every installed team and its members |
| `teams install <repository> [--provider <provider>] [--confirm]` | install a team catalog and its stopped agents |
| `teams update <team> [--provider <provider>] [--confirm]` | update and reconcile an installed team |

`<repository>` is a GitHub URL or a directory on this machine. `--provider` supplies the provider
for agents the command *creates* — new members on install, newly declared members on update — and
is never applied to a member that already exists.

### Preview and confirmation are separate

Without `--confirm` the command says what it would do, does none of it, and exits non-zero.

```console
$ rundesk teams install ./development-team --provider codex
install: this would install team development-team from ./development-team
        catalog  rundesk-skills — reuse installed from https://github.com/rundesk-ai/rundesk-skills; require writing-plans
        member   forge — create with provider codex
                 replace AGENTS.md and CLAUDE.md; remove MEMORY.md; allow only development-team/implementing, rundesk-skills/writing-plans plus Rundesk-required skills; weekly upkeep on; leave gateway stopped
        nothing was installed or changed. To go ahead:
        rundesk teams install ./development-team --provider codex --confirm
```

The preview is where a shared catalog says whether it will be installed or reused, and where a
member says what its instructions, memory, skills and upkeep will become.

### What each verb refuses

| Refusal | Applies to | What to do |
|---|---|---|
| a declared member name already exists | `install` | the refusal names the exact `rundesk agents remove <agent> --confirm` to run first |
| a newly declared name is held by an agent no team manages | `update`, at preview *and* confirmation | remove that agent; it keeps its files, records and grants until you do |
| a member's records cannot be read | `update` | refused before anything moves |
| something that is neither a file nor a symlink stands where a managed page belongs | `update` | refused before anything moves |

The clean-start rule behind the first two is that every member begins from its catalog-owned
instructions, memory policy, delegation scope, skill allowlist and upkeep setting. A part-way
failure puts back what it had already changed and names what it could not; the terms are in
[`concepts/teams.md`](../concepts/teams.md#lifecycle).

### Members start stopped

Both verbs leave every member gateway stopped, and the successful command names what to run:

```console
$ rundesk gateways start forge
```

`rundesk update` and the daily updater check installed teams without a separate confirmation step.
They stand down only members that were online and restore exactly that set.

### The same repository, installed two ways

`rundesk skills install <repository>` installs only the skill catalog: no agents, no team marker,
and it updates and removes like any ordinary catalog. Installing the team later promotes that
catalog in place and creates the declared agents, keeping the skills already installed. Once a
catalog was installed through `teams install`, ordinary `skills update`, catalog refresh, and
`skills remove` can no longer move it independently of its agents.

An agent turn may run these commands when the owner authorized that effect and the turn's tool
access can invoke Rundesk. Rundesk never infers that authorization from the environment, and every
preview, `--confirm`, validation, collision and locking guard applies whether the command came from
a terminal or a turn.
