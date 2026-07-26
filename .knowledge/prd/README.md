# prd/ — tested contracts (catalog)

The ratified, test-backed PRDs — one per built system. **To write or modify one, follow [`../guides/docs-prd.md`](../guides/docs-prd.md).**

## Components — authored

The project's ontology, in order (`prefix — gloss`). The owner's call; an agent stops and asks. Citations
run toward `base-`: a higher layer may cite a lower one, never the reverse.

```
1. base-       — laws true of every part, whatever it is
2. command-    — the command line itself: what it offers, and how a verb behaves
3. platform-   — the runtime rundesk is: what stays up, and what it keeps hold of
4. provider-   — the seam a brain is reached through, and what any adapter must do
5. agent-      — the named identity work is run for: its home, and what it loads
6. channel-    — the surfaces an agent is reached on, and what arrives from them
7. lifecycle-  — this copy of rundesk on a machine: how it arrives, moves and leaves
```

`provider-` sits under `agent-` because an agent chooses which brain answers for it, while an adapter
knows nothing of whose turn it is running — that is what lets a stranger write one.

`platform-` sits under `agent-` because an agent is reached through what stays running, while a gateway
knows nothing of whose work it is holding. `agent-` sits under `channel-` because a channel dispatches
work for an agent, while an agent is the same agent whatever it is reached on. `channel-` sits under
`lifecycle-` because moving this copy of rundesk has to account for what is connected, while a channel
knows nothing of how rundesk arrived.

Every component in the list above now has at least one contract, except `base-`. Adding another is the
owner's call at the time its work arrives, and it is a row here.

## Contents — maintained by hand

Add a row when you add a PRD; `doc-lint` fails the build if one is missing. Component, then file, each row
a link to the contract followed by a one-line gloss. Read top to bottom, this list is the product's
high-level map.

- **Base** — _(none yet)_
- **Command**
  - [command-surface](./command-surface.md) — every operation the command offers, and how one that is not built behaves.
- **Platform**
  - [platform-process](./platform-process.md) — a program rundesk runs, and how it keeps hold of it while it does.
  - [platform-gateway](./platform-gateway.md) — the part that stays running, one of each name, and what it takes with it.
  - [platform-schedule](./platform-schedule.md) — work rundesk begins because the time came, belonging to one gateway each.
- **Provider**
  - [provider-adapter](./provider-adapter.md) — the seam a brain is reached through: a program rundesk runs rather than code it loads, and what any adapter must do.
- **Agent**
  - [agent-home](./agent-home.md) — the named identity work is run for, the home it loads from, and how far apart two of them are kept.
  - [agent-gateway](./agent-gateway.md) — the one gateway an agent runs in, made with it and taken away with it.
  - [agent-run](./agent-run.md) — one occurrence of work, the account it leaves behind, and what a conversation is continued from.
  - [agent-store](./agent-store.md) — everything one agent keeps that outlives the moment: what it is configured to do, what it has done, and how it is whole again from that alone.
- **Channel**
  - [channel-adapter](./channel-adapter.md) — the seam a surface is reached through: a program rundesk runs rather than code it loads, and what any channel adapter must do.
  - [channel-messaging](./channel-messaging.md) — what any channel does with what arrives on it, whatever its platform can and cannot show.
  - [channel-discord](./channel-discord.md) — what a turn looks like on Discord: threads, marks, its own commands, and what it costs.
  - [agent-usage](./agent-usage.md) — what every run cost in tokens, and how sure anything derived from them is.
- **Lifecycle**
  - [lifecycle-install](./lifecycle-install.md) — getting rundesk onto a machine, and knowing it worked.
  - [lifecycle-update](./lifecycle-update.md) — which version this is, which has been published, and moving between them.
  - [lifecycle-migration](./lifecycle-migration.md) — bringing what is already on a machine into the shape a newer rundesk expects, in the window an update already stands every gateway down for.
  - [lifecycle-removal](./lifecycle-removal.md) — taking rundesk off a machine, and what is left when it goes.
