# prd-drafts/ — proposals, isolated (catalog)

Draft PRDs not yet approved; a `../prd/` contract may never cite one (`doc-lint` enforces the isolation). **To write or modify one, follow [`../guides/docs-prd.md`](../guides/docs-prd.md).**

## Drafts — maintained by hand

Add a row when you add a draft; `doc-lint` fails the build if one is missing.

| Draft | Proposes | Reserved namespace |
|---|---|---|
| [channel-messaging](./channel-messaging.md) | what any channel does, whatever its platform can and cannot show | `CH` |
| [channel-discord](./channel-discord.md) | what a turn looks like on Discord — threads, marks and its own commands | `DIS` |
| [provider-adapter](./provider-adapter.md) | the seam a brain is reached through, and what any adapter must do | `PRV` |
| [agent-run](./agent-run.md) | one occurrence of work, the account it leaves, and what a conversation continues from | `RUN` |
| [agent-usage](./agent-usage.md) | what every run cost, in tokens and in money, and how sure that is | `USE` |
