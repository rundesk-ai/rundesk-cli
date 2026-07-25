# prd-drafts/ — proposals, isolated (catalog)

Draft PRDs not yet approved; a `../prd/` contract may never cite one (`doc-lint` enforces the isolation). **To write or modify one, follow [`../guides/docs-prd.md`](../guides/docs-prd.md).**

## Drafts — maintained by hand

Add a row when you add a draft; `doc-lint` fails the build if one is missing.

| Draft | Proposes | Reserved namespace |
|---|---|---|
| [platform-process](./platform-process.md) | Any program rundesk starts on the owner's behalf, and how rundesk keeps hold of it. | `PROC` |
| [platform-gateway](./platform-gateway.md) | The part of rundesk that stays running, and what the machine tending it guarantees. | `GW` |
