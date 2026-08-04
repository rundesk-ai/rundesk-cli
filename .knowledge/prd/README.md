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

The ontology is unchanged by the rebuild and is not an agent's to change. Requirement IDs are permanent,
so a `R-<AREA>-<n>` retired here is never reissued: a contract written for the rebuilt product starts its
numbering after the highest the retired one reached, and the retired contract stays readable in this
branch's history.

## Contents — maintained by hand

Add a row when you add a PRD; `doc-lint` fails the build if one is missing. Component, then file, each row
a link to the contract followed by a one-line gloss. Read top to bottom, this list is the product's
high-level map.

**The product is being rebuilt one part at a time, so this catalog is deliberately empty.** A contract
lands here when the behavior it describes is built and proven in the new `src/` — never before, and never
carried over from the build being replaced. The first will cover the command surface and the `rundesk`
lifecycle verbs: `status`, `version`, `update` and `uninstall`.

- **Base** — _(none yet)_
- **Command** — _(none yet)_
- **Platform** — _(none yet)_
- **Provider** — _(none yet)_
- **Agent** — _(none yet)_
- **Channel** — _(none yet)_
- **Lifecycle** — _(none yet)_
