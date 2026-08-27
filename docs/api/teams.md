# Teams

## teams

A team catalog adds version-controlled named agents to an ordinary skill catalog. What a team is
once installed, and everything reconciliation puts back, is
[`concepts/teams.md`](../concepts/teams.md). This is what each verb takes and what each refuses.

| Command | Does |
|---|---|
| `teams [list]` | every installed team and its members |
| `teams install <repository> [--provider <provider>] [--confirm]` | install a team catalog and its stopped agents |
| `teams update <team> [--source <repository>] [--provider <provider>] [--confirm]` | update and reconcile an installed team |

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
                 replace AGENTS.md and CLAUDE.md; remove MEMORY.md; team-managed skills development-team/implementing, rundesk-skills/writing-plans plus Rundesk-required skills; every other grant preserved; weekly upkeep on; leave gateway stopped
        nothing was installed or changed. To go ahead:
        rundesk teams install ./development-team --provider codex --confirm
```

`--provider` is used for the new agents created by installation. Installation refuses any declared
member name that already exists and prints the exact `rundesk agents remove <agent> --confirm`
command required before retrying. This clean-start boundary ensures every member begins with the
catalog-owned instructions, memory policy, delegation scope, team-managed skills, and weekly
upkeep setting.

The preview is where a shared catalog says whether it will be installed or reused, and where a
member says what its instructions, memory, skills and upkeep will become.

### What each verb refuses

| Refusal | Applies to | What to do |
|---|---|---|
| a declared member name already exists | `install` | the refusal names the exact `rundesk agents remove <agent> --confirm` to run first |
| a newly declared name is held by an agent no team manages | `update`, at preview *and* confirmation | remove that agent; it keeps its files, records and grants until you do |
| a user-managed grant occupies a name the declaration needs | `update`, refresh, or that member's turn admission | revoke it, or keep it under the alias command the refusal names |
| a member's records cannot be read | `update` | refused before anything moves |
| something that is neither a file nor a symlink stands where a managed page belongs | `update` | refused before anything moves |

The clean-start rule behind the first two is that every member begins from its catalog-owned
instructions, memory policy, delegation scope, team-managed grants and upkeep setting. A part-way
failure puts back what it had already changed and names what it could not; the terms are in
[`concepts/teams.md`](../concepts/teams.md#lifecycle).

### Updating one team, and changing where it comes from

`rundesk teams update <team>` fetches the recorded source and reconciles against it, repairing local
instruction, memory, delegation and team-managed grant drift **even when the fetched tree is
unchanged** — drift is local, so there is nothing upstream for it to show up in.
`--source <repository>` replaces the recorded GitHub repository or local directory in that same
guarded update. It never reuses the old source's ETag, it validates that the new catalog carries the
installed team's exact name, and it is named in both the preview and the completed result. The new
source is recorded even when its tree is byte-identical to the old one. A reconciliation that fails
part-way restores the old catalog tree, the recorded source and member state together.

### Members start stopped

Both verbs leave every member gateway stopped, and the successful command names what to run:

```console
$ rundesk gateways start forge
```

### Team-managed and user-managed grants

The member's `skills` array names the **team-managed grants** and may be empty. Every other grant
the member holds is **user-managed**: reconciliation compares the previously installed declaration
with the incoming one, revokes only the exact grants this team declared and no longer declares —
matched on both the installed name and the full `<catalog>/<skill>` address, so a copy made with
`--as` is never taken — grants every declared skill that is absent, and leaves everything else
standing. An empty array means the team manages no optional grant; it does not strip the member.
Editing the array is how a team version adds or removes a stack-specific or task-specific
capability, and `rundesk skills grant` is how an owner adds one the team does not manage. Rundesk's
required operating skill and its conditional delegation skill are preserved as before. An initial
installation is unchanged: every member name must be absent, so each one begins with its declared
grants and nothing else.

A declaration is refused before any dependency, gateway, catalog, page, record, or grant moves when
a user-managed grant occupies a name it needs. An update or refresh is refused for the whole team,
and turn admission refuses only the member being admitted. A newly declared name held by an agent no
team manages is answered first, with the `rundesk agents remove <agent> --confirm` that clears it,
rather than with a collision over grants that agent's owner never gave this team a say over.

The collision refusal names the member, the grant standing there, the declared address, and the two
commands that clear it — `rundesk skills revoke <agent> <skill>`, or `rundesk skills grant <agent>
<catalog>/<skill> --as <name>` to keep it under another name. The same refusal answers a declaration
that turns an inbound-only member outbound while a `delegating-work` grant other than Rundesk's own
occupies that name; while a member stays inbound-only Rundesk needs no grant there and that custom
grant is left alone. Nothing here invents an alias or revokes a grant this team never declared.

One grant nothing can preserve is a grant to a skill its catalog stopped supplying: a catalog
version that retires a skill takes every grant to it, whoever made them.

The member's required `self_improve` boolean enables or
disables Rundesk's protected weekly upkeep and is repaired from the catalog on later turns. A member
removed from a later team version is no longer managed and is not deleted. Team catalogs execute no
installation hook.

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
