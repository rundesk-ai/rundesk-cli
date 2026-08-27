# Teams

A team catalog is a repository that declares named agents — their instructions, memory policy,
delegation scope, skill allowlist, and weekly upkeep — and installs them as real agents. Rundesk
owns those members' managed state and repairs drift from the installed catalog.

## Commands

| Command | Control |
|---|---|
| `teams` or `teams list` | List every installed team and its members. |
| `teams install <repository> [--provider <provider>]` | Preview the install. Changes nothing. |
| `teams install <repository> [--provider <provider>] --confirm` | Install the catalog, its dependencies, and every declared member. |
| `teams update <team> [--provider <provider>]` | Preview the reconciliation. Changes nothing. |
| `teams update <team> [--provider <provider>] --confirm` | Replace changed catalog content and reconcile every declared member. |

Prefix every command with `"$RUNDESK_COMMAND"`. `<repository>` is a GitHub URL or a directory on this
machine.

## Always preview first

Run the command without `--confirm`, read what it says it would do, and add `--confirm` only when the
preview matches the request. The unconfirmed form exits non-zero and changes nothing.

The preview names which shared catalogs would be installed and which reused, each member that would
be created and with which provider, and what each member's instructions, memory, skills, and upkeep
would become.

`--provider` applies only to agents the command creates. It is never applied to a member that already
exists.

## What reconciliation owns

For each declared member, an update writes the catalog's instructions to both `AGENTS.md` and
`CLAUDE.md`, removes `MEMORY.md`, writes the declared description and delegation scope, sets weekly
upkeep from `self_improve`, grants every declared skill, and revokes every grant outside that
positive allowlist while preserving Rundesk's required operating skill.

An update reconciles **even when the fetched tree is unchanged**, so it is also the repair for local
drift.

## Refusals to expect

- A declared member name that already exists is refused on install. The refusal names the exact
  `agents remove <agent> --confirm` required. Do not run that removal without an explicit owner
  request naming the agent.
- A newly declared name held by an agent no team manages is refused on update, at preview and at
  confirmation. That agent keeps its files, records, and grants.
- A member whose records cannot be read, or a non-file standing where a managed page belongs, is
  refused before anything moves.

## After installing

- Members are created with their gateways stopped. Start only the agents the owner wants with
  `gateways start <agent>`.
- A member removed by a later catalog version is released from team management, not deleted.
- Once a catalog was installed as a team, `skills update` and `skills remove` can no longer move it
  independently of its agents.
- Report each surface's outcome separately. A team catalog that failed to fetch does not mean the
  application update failed.
