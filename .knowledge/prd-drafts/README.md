# prd-drafts/ — proposals, isolated (catalog)

Draft PRDs not yet approved; a `../prd/` contract may never cite one (`doc-lint` enforces the isolation). **To write or modify one, follow [`../guides/docs-prd.md`](../guides/docs-prd.md).**

## Drafts — maintained by hand

Add a row when you add a draft; `doc-lint` fails the build if one is missing.

| Draft | Proposes | Reserved namespace |
|---|---|---|
| [platform-store](./platform-store.md) | Everything one agent keeps that outlives the moment — what it is configured to do, and what it has done — held apart from every other agent's. | `STO` |
| [lifecycle-migration](./lifecycle-migration.md) | Bringing what is already on a machine into the shape a newer rundesk expects, in the window an update already stands every gateway down for. | `MIG` |
