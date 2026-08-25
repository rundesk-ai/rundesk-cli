# A team, once it is installed

A team catalog is a skill catalog that also declares named agents. Installing one creates those
agents, owns their durable instructions, and keeps them from drifting: the catalog is the source of
truth, and reconciliation is what makes that true on a machine that has moved on.

[catalogs.md](catalogs.md) is how a catalog is written and published. This page is what happens on
the install that takes one.

## What a team catalog declares

A team catalog is a version-controlled skill catalog that also declares a set of named agents. It
owns those agents' durable instructions, memory policy, delegation scope, and positive skill
allowlists. Provider accounts, channels, schedules, projects, credentials, and models remain local to
each Rundesk installation.

The catalog contains ordinary `manifest.json` and `skills/` entries, plus:

```text
team.json
agents/
  forge/AGENTS.md
  piper/AGENTS.md
```

`team.json` schema 2 contains `schema`, `name`, `catalogs`, and `members`. Its name must equal
`manifest.json`'s name. `catalogs` is a duplicate-free array of shared catalog dependencies, each
with its exact `name` and GitHub repository or local-directory `source`. Schema 1 remains accepted
for existing self-contained teams and has no `catalogs` field. Each member contains:

- `name`: the Rundesk agent name;
- `description`: the sentence other agents use when routing work;
- `instructions`: a relative path below `agents/` to its canonical `AGENTS.md`;
- `skills`: the exact positive allowlist this member receives, which may be empty. Schema 2 uses
  fully qualified `<catalog>/<skill>` addresses from the team or a declared dependency. Schema 1
  keeps local skill names, interpreted as skills from the team catalog;
- `delegates_to`: the exact named-agent scope, as an array. An empty array makes the member
  inbound-only; and
- `self_improve`: `true` or `false`, controlling Rundesk's protected weekly upkeep for this member.

All fields are required. Unknown fields, duplicate members, dependencies, or skills, paths that
escape the catalog, missing instructions, undeclared catalogs, invalid names, and cross-team member
collisions are refused before a confirmed operation mutates the install. Two addresses with the
same skill name are refused for one member because installed grants stand under that name.

## Lifecycle

`rundesk teams install <repository>` fetches and validates the complete team and every missing
dependency, previews whether each dependency will be installed or reused, and changes nothing.
An installed dependency is reused only when its recorded source matches the declaration and it
holds every referenced skill; a same-named catalog from another source is refused. `--confirm`
installs missing dependencies, installs the team catalog, and reconciles its members. Shared
catalogs remain independently installed catalogs and can be reused by any number of teams. A provider
is installation-local: `--provider` supplies the provider for every new member. Installation refuses
any declared name that already exists; remove each colliding agent before installing the team so
every member begins from its catalog-owned workflow.

An installed team protects its dependencies from being removed through `rundesk skills remove`.
Ordinary catalog update and refresh also refuse a replacement that retires a skill referenced by an
installed team. Change the team declaration first; unreferenced dependency catalogs keep their
ordinary independent lifecycle.

`rundesk teams update <team>` fetches the configured source, validates the replacement, previews
catalog and member changes, and changes nothing. `--confirm` replaces changed catalog content and
reconciles every declared member even when the fetched tree is unchanged, so the operation repairs
instruction, memory, grant, and delegation drift. It refuses a newly declared member name already
held by an agent no team manages, at preview and at confirmation, and names the removal required.

`rundesk update` and the daily automatic updater also check every installed team catalog, after the
application and independently of ordinary catalogs. They require no separate confirmation, validate
each fetched declaration and every catalog it declares as a dependency before any gateway,
dependency catalog, team catalog, or member is changed, install a missing dependency and reuse a
matching installed one, reconcile every declared member even when the tree is unchanged, and report
application, ordinary-catalog, and team-catalog outcomes separately. Failure to fetch or validate
one team or one of its dependencies preserves its last working release, members, and member
gateways, and does not stop another catalog.

Reconciliation prerequisites that cannot be recovered from are proved before a gateway moves and
before any dependency, catalog, or member is written: every existing member's records must be
readable, and nothing that is neither a file nor a symlink may stand where one of that member's
managed instruction or memory pages belongs. Beyond that, a failure met part-way through
reconciliation puts back the catalog tree, each declared member's instruction and memory pages and
the description, delegation scope and upkeep this lifecycle owns, and the grants of every agent
this catalog reaches. An agent it reaches only through a grant keeps its own pages and records: the
lifecycle never writes them, so it never puts them back and never refuses a team over their shape.

A confirmed initial installation is held on the same terms, from before its catalog arrives: a
wholly new team catalog and every agent it created are removed, and a promoted skills-only catalog
returns to its prior tree, version, and grants. The dependency catalogs it installed first stay
installed and granted to nobody, which is the one deliberate exception and is named in the failure.

This is a compensating restore rather than a transaction: an agent this reconciliation created is
taken away again, nothing that existed before it began is ever removed, a dependency catalog
installed for this team stays installed with nothing granted from it, and a failure while putting
state back is reported as its own named outcome instead of being reported as success. Every
expected reconciliation failure is named against its own team, so the teams after it are still
checked.

No update adopts an agent it does not already manage. A declared member name already held by an
agent no installed team manages fails the explicit team update and the manual or daily refresh
alike, names the `rundesk agents remove <agent> --confirm` needed, and leaves that agent's files,
records, and grants exactly as they were, together with the installed team's last working version.
A name may only be taken over after the owner has removed the colliding agent.

Turn admission also performs a network-free reconciliation of that one member from the installed
catalog before instructions or grants are read. Thus local drift cannot cross into a later turn;
catalog source changes arrive only through the explicit guarded team command or the guarded
manual/daily update lifecycle.

For each member, reconciliation:

1. creates the agent when absent;
2. writes the catalog's instruction bytes atomically to both `AGENTS.md` and `CLAUDE.md`;
3. removes `MEMORY.md`, making the team member explicitly memoryless;
4. writes the declared description and delegation scope;
5. enables or disables the member's protected weekly upkeep from `self_improve`;
6. grants every declared fully qualified skill and revokes every grant outside that positive
   allowlist;
7. preserves Rundesk's required operating skill and conditional delegation skill; and
8. leaves the member's gateway stopped for the owner to start when wanted.

A member removed by a later catalog version is released from team management rather than deleted.
Removing agents, channels, schedules, credentials, or projects is outside this lifecycle. Removing
an unlisted optional skill grant is part of the positive allowlist contract.

Installation and the explicit team update do not start gateways. The successful command names
`rundesk gateways start <agent>` so the owner can start only the agents they want to use. The
combined manual/daily lifecycle instead stands down only online members and restores exactly that
set after reconciliation; members that began offline remain offline.

## Ownership and safety

A named agent may be managed by at most one installed team catalog. Initial installation refuses
every existing same-named agent and reports the exact `rundesk agents remove <agent> --confirm`
command required before retrying. A team never changes provider credentials or grants itself
external authority.

Team catalogs are data-only. Rundesk executes no repository hook, migration script, or agent-authored
code during installation or update. `rundesk skills install` may install the same repository as an
ordinary skill catalog: it writes no team marker, creates no agent, and leaves `team.json` inert.
That skills-only installation follows ordinary skill update, refresh, and removal behavior. A
catalog installed through `rundesk teams install` carries the team marker, and ordinary skill
update, refresh, and removal refuse or skip it so team content cannot move without member
reconciliation. Installing the team after the skills promotes the existing catalog in place,
preserving its skills while adding team ownership and reconciling the declared agents.

An agent turn may run a confirmed team install or update when the owner authorized that effect and
the turn's configured tool access can invoke Rundesk. Rundesk does not infer owner authorization
from agent-turn environment variables. Preview, `--confirm`, validation, collision, locking,
reconciliation, positive allowlist, and stopped-gateway guarantees are identical for terminal and
in-turn callers. Repository protection, task authorization, and configured tool access remain the
authority boundaries.
