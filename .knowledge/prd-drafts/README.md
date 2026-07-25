# prd-drafts/ — proposals, isolated (catalog)

Draft PRDs not yet approved; a `../prd/` contract may never cite one (`doc-lint` enforces the isolation). **To write or modify one, follow [`../guides/docs-prd.md`](../guides/docs-prd.md).**

## Drafts — maintained by hand

Add a row when you add a draft; `doc-lint` fails the build if one is missing.

| Draft | Proposes | Reserved namespace |
|---|---|---|
| [agent-home](./agent-home.md) | what an agent is, the home it loads from, and how far apart two of them are kept | `AGT` |
| [agent-gateway](./agent-gateway.md) | the one gateway an agent runs in, made with it and taken away with it | `AGW` |
| [channel-messaging](./channel-messaging.md) | what any channel does, whatever its platform can and cannot show | `CH` |
| [channel-discord](./channel-discord.md) | what a turn looks like on Discord — threads, marks and its own commands | `DIS` |
