---
id: TEAM
name: Versioned team catalogs
last_verified: 2026-08-24
---

## What this is

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

`team.json` schema 1 contains `schema`, `name`, and `members`. Its name must equal
`manifest.json`'s name. Each member contains:

- `name`: the Rundesk agent name;
- `description`: the sentence other agents use when routing work;
- `instructions`: a relative path below `agents/` to its canonical `AGENTS.md`;
- `skills`: the exact positive allowlist this member receives from this catalog, which may be empty;
- `delegates_to`: the exact named-agent scope, as an array. An empty array makes the member
  inbound-only; and
- `self_improve`: `true` or `false`, controlling Rundesk's protected weekly upkeep for this member.

All fields are required. Unknown fields, duplicate members or skills, paths that escape the catalog,
missing instructions, undeclared skills, invalid agent names, and cross-team member collisions are
refused before a confirmed operation mutates the install.

## Lifecycle

`rundesk teams install <repository>` fetches and validates the complete catalog, previews every
effect, and changes nothing. `--confirm` installs the catalog and reconciles its members. A provider
is installation-local: `--provider` supplies the provider for every new member. Installation refuses
any declared name that already exists; remove each colliding agent before installing the team so
every member begins from its catalog-owned workflow.

`rundesk teams update <team>` fetches the configured source, validates the replacement, previews
catalog and member changes, and changes nothing. `--confirm` replaces changed catalog content and
reconciles every declared member even when the fetched tree is unchanged, so the operation repairs
instruction, memory, grant, and delegation drift.

`rundesk update` and the daily automatic updater also check every installed team catalog, after the
application and independently of ordinary catalogs. They require no separate confirmation, validate
each fetched declaration before mutation, reconcile every declared member even when the tree is
unchanged, and report application, ordinary-catalog, and team-catalog outcomes separately. Failure
to fetch or validate one team preserves its last working release and does not stop another catalog.

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
6. grants every declared skill and revokes every grant outside that positive allowlist;
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

## Acceptance

- A synthetic local team catalog previews without mutation, then installs into a disposable root.
- An agent-turn environment with command access can apply the same confirmed skill and team catalog
  operations as a terminal caller.
- Missing members exist with their configured descriptions and delegation scopes.
- Their `AGENTS.md` and `CLAUDE.md` match the catalog byte-for-byte and no `MEMORY.md` remains.
- Each member's protected weekly upkeep state matches its `self_improve` setting.
- Each member holds exactly its positive allowed list, plus product-required grants; an unlisted
  grant from any catalog is removed on reconciliation.
- Every member's gateway activation is requested through the injected supervisor boundary.
- A second confirmed update is idempotent.
- Local drift is repaired even when the source tree is unchanged.
- A changed catalog version updates instructions, grants, and delegation scope together.
- Invalid manifests, existing same-named agents, missing providers for new members, cross-team
  collisions are refused without false success.
- The same repository installs, updates, and removes as skills only without creating agents or team
  ownership; it can then be promoted in place to a team, which remains protected from ordinary skill
  lifecycle changes and leaves every gateway stopped.
- The complete suite, Python 3.9 floor, lint, syntax, privacy, and disposable-install gates pass.
