# prd-drafts/ — proposals, isolated (catalog)

Draft PRDs not yet approved; a `../prd/` contract may never cite one (`doc-lint` enforces the isolation). **To write or modify one, follow [`../guides/docs-prd.md`](../guides/docs-prd.md).**

## Drafts — maintained by hand

Add a row when you add a draft; `doc-lint` fails the build if one is missing.

| Draft | Proposes | Reserved namespace |
|---|---|---|
| [agent-role](./agent-role.md) | a shared specialist definition a named agent hands one bounded task to, and the single reviewed handoff it gets back | `ROL` |
| [platform-secrets](./platform-secrets.md) | one set of named values this install keeps for every program it starts, told apart without any of them ever being shown | `SEC` |
