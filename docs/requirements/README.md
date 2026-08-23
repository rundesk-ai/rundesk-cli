# Product requirements

This directory holds the product contracts that explain what Rundesk must do and how that behavior
is accepted. The current channel requirements were reconciled with the `refactor-2` product on
2026-08-08. The remaining files are preserved requirements from the previous build and are not
current promises unless a current PRD links to them.

| Document | Status | What it owns |
|---|---|---|
| [channel-adapter.md](./channel-adapter.md) | current draft | the provider-neutral channel-adapter product boundary and lifecycle |
| [channel-messaging.md](./channel-messaging.md) | current draft | behavior shared by every channel conversation |
| [channel-discord.md](./channel-discord.md) | current draft | Discord-specific setup, triggering, rendering, and commands |
| [channel-slack.md](./channel-slack.md) | predecessor reference | the previous build's Slack behavior; Slack is outside the current channel increment |
| [agent-delegation.md](./agent-delegation.md) | predecessor draft | the previous build's delegation design |
| [agent-role.md](./agent-role.md) | predecessor draft | the previous build's role-worker design |
| [machine-permissions.md](./machine-permissions.md) | current draft | what macOS lets a rundesk process do, and whose grants an answer is about |
| [provider-account-alias.md](./provider-account-alias.md) | implemented | optional additional provider accounts and immutable delegation selection |
| [rundesk-instructions.md](./rundesk-instructions.md) | current draft | ownership, composition, and acceptance of Rundesk operating and agent instructions |
| [team-catalog.md](./team-catalog.md) | approved | version-controlled agent teams, their managed instructions, grants, and activation lifecycle |

## Status and evidence

- **Draft** means the direction is written and reviewable but unresolved product choices remain.
- **Approved** means the product owner accepted the requirements and scope.
- **Implemented** means the named acceptance evidence was executed successfully against the stated
  build. A source path or test name alone does not earn this status.
- **Validated** means real-user or real-platform evidence also supports the intended outcome.
- **Superseded** means a later approved decision replaced the requirement; repository history keeps
  the former wording.

The validation tables distinguish current implementation evidence from executed acceptance. A test
that exists has not necessarily been run in the documentation task, and an offline adapter test does
not prove what Discord displayed on its service.

## Authority and change control

The Rundesk product owner decides product behavior and approves these PRDs. Code, tests, current
documentation, predecessor requirements, and research establish facts and constraints; they do not
silently redefine the desired product. When those sources conflict, the PRD records the conflict and
the owner decides whether the product or implementation changes.

Requirement IDs remain stable when the same product condition survives revision. New behavior gets a
new ID. Detailed wire formats and implementation choices belong in [adapters.md](../adapters.md), and
executed delivery evidence belongs in each PRD's validation table.

## Historical source

These documents began as requirements imported from the previous build in commit `217006b`. That
history remains available in Git. The current PRDs keep requirements that still express product
intent, revise requirements deliberately changed by this build, and expose unresolved carry-forward
choices instead of presenting predecessor checkmarks as current proof.
