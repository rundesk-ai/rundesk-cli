---
id: TEAM
name: Versioned team catalogs
last_verified: 2026-08-23
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
  and
- `delegates_to`: the exact named-agent scope, as an array. An empty array makes the member
  inbound-only.

All fields are required. Unknown fields, duplicate members or skills, paths that escape the catalog,
missing instructions, undeclared skills, invalid agent names, and cross-team member collisions are
refused before a confirmed operation mutates the install.

## Lifecycle

`rundesk teams install <repository>` fetches and validates the complete catalog, previews every
effect, and changes nothing. `--confirm` installs the catalog and reconciles its members. A provider
is installation-local: `--provider` supplies the provider only for members that do not already
exist, while existing members keep their provider and account selection.

`rundesk teams update <team>` fetches the configured source, validates the replacement, previews
catalog and member changes, and changes nothing. `--confirm` replaces changed catalog content and
reconciles every declared member even when the fetched tree is unchanged, so the operation repairs
instruction, memory, grant, and delegation drift.

Turn admission also performs a network-free reconciliation of that one member from the installed
catalog before instructions or grants are read. Thus local drift cannot cross into a later turn;
catalog source changes still require the explicit guarded update above.

For each member, reconciliation:

1. creates the agent when absent;
2. writes the catalog's instruction bytes atomically to both `AGENTS.md` and `CLAUDE.md`;
3. removes `MEMORY.md`, making the team member explicitly memoryless;
4. writes the declared description and delegation scope;
5. grants every declared skill and revokes every grant outside that positive allowlist;
6. preserves Rundesk's required operating skill and conditional delegation skill; and
7. starts or repairs the member's supervised gateway and proves it is running.

A member removed by a later catalog version is released from team management rather than deleted.
Removing agents, channels, schedules, credentials, or projects is outside this lifecycle. Removing
an unlisted optional skill grant is part of the positive allowlist contract.

The catalog update and persisted reconciliation complete before gateway activation. A gateway
failure is reported as an incomplete team activation with the exact retry command; it is never
reported as full success. Re-running the confirmed team update is the recovery path.

## Ownership and safety

A named agent may be managed by at most one installed team catalog. Installing a team over an
existing unmanaged agent is an explicit adoption shown in the preview; the required `--confirm`
authorizes the named instruction replacement, memory removal, delegation change, and skill-allowlist
reconciliation. A team never changes provider credentials or grants itself external
authority.

Team catalogs are data-only. Rundesk executes no repository hook, migration script, or agent-authored
code during installation or update. Ordinary `rundesk skills install`, `skills update`, automatic
catalog refresh, and `skills remove` refuse or skip team catalogs so team content cannot move without
its member reconciliation. A confirmed team install or update is refused from inside an agent turn;
an owner reviews and applies it from a terminal. Agents may propose source changes but cannot apply
the team state they are governed by through the supported in-turn command path. This is a correctness
guard, not an operating-system sandbox; repository protection and owner review remain the authority
boundary against a process deliberately bypassing its environment.

## Acceptance

- A synthetic local team catalog previews without mutation, then installs into a disposable root.
- Missing members exist with their configured descriptions and delegation scopes.
- Their `AGENTS.md` and `CLAUDE.md` match the catalog byte-for-byte and no `MEMORY.md` remains.
- Each member holds exactly its positive allowed list, plus product-required grants; an unlisted
  grant from any catalog is removed on reconciliation.
- Every member's gateway activation is requested through the injected supervisor boundary.
- A second confirmed update is idempotent.
- Local drift is repaired even when the source tree is unchanged.
- A changed catalog version updates instructions, grants, and delegation scope together.
- Invalid manifests, missing providers for new members, cross-team collisions, ordinary skill
  lifecycle attempts, and gateway failures are refused or reported without false success.
- The complete suite, Python 3.9 floor, lint, syntax, privacy, and disposable-install gates pass.
