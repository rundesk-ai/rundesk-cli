# prd/ — tested contracts (catalog)

The ratified, test-backed PRDs — one per built system. **To write or modify one, follow [`../guides/docs-prd.md`](../guides/docs-prd.md).**

## Components — authored

The project's ontology, in order (`prefix — gloss`). The owner's call; an agent stops and asks. Citations
run toward `base-`: a higher layer may cite a lower one, never the reverse.

```
1. base-       — laws true of every part, whatever it is
2. command-    — the command line itself: what it offers, and how a verb behaves
3. platform-   — the runtime rundesk is: what stays up, and what it keeps hold of
4. lifecycle-  — this copy of rundesk on a machine: how it arrives, moves and leaves
```

`platform-` sits under `lifecycle-` because moving this copy of rundesk has to account for what is
running at the time, while what is running knows nothing of how it arrived.

The gateway's remaining components — a brain, a channel, an agent — are not declared yet. Each is the
owner's call at the time its work arrives, and adding one is a row here.

## Contents — maintained by hand

Add a row when you add a PRD; `doc-lint` fails the build if one is missing. Component, then file, each row
a link to the contract followed by a one-line gloss. Read top to bottom, this list is the product's
high-level map.

- **Base** — _(none yet)_
- **Command**
  - [command-surface](./command-surface.md) — every operation the command offers, and how one that is not built behaves.
- **Lifecycle**
  - [lifecycle-install](./lifecycle-install.md) — getting rundesk onto a machine, and knowing it worked.
  - [lifecycle-update](./lifecycle-update.md) — which version this is, which has been published, and moving between them.
  - [lifecycle-removal](./lifecycle-removal.md) — taking rundesk off a machine, and what is left when it goes.
