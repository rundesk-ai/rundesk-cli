# prd-drafts/ — proposals, isolated (catalog)

Draft PRDs not yet approved; a `../prd/` contract may never cite one (`doc-lint` enforces the isolation). **To write or modify one, follow [`../guides/docs-prd.md`](../guides/docs-prd.md).**

## Drafts — maintained by hand

Add a row when you add a draft; `doc-lint` fails the build if one is missing.

| Draft | Proposes | Reserved namespace |
|---|---|---|
| [agent-role](./agent-role.md) | a shared specialist definition a named agent hands one bounded task to, and the single reviewed handoff it gets back | `ROL` |
| [agent-delegation](./agent-delegation.md) | one bounded task a named agent hands to another named agent on this install, answered once by that agent as itself and reviewed before anybody hears it | `DEL` |
