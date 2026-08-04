# guides/ — writing standards & how-tos (catalog)

**`docs-*.md`** — the shipped writing standards (versioned by `knowledge-template`; don't edit per project). **`<verb-noun>.md`** — project how-tos you author for recurring tasks in this repo.

## Contents — maintained by hand

Add a row when you add a guide; `doc-lint` fails the build if one is missing.

### Shipped standards

| Guide | Standard for |
|---|---|
| [docs-prd.md](./docs-prd.md) | PRDs in `../prd/` (and drafts) |
| [docs-research.md](./docs-research.md) | Research notes in `../research/` |
| [docs-brief.md](./docs-brief.md) | `../BRIEF.md` |
| [docs-codemap.md](./docs-codemap.md) | `../CODEMAP.md` |
| [docs-memory.md](./docs-memory.md) | `../MEMORY.md` |
| [docs-overview.md](./docs-overview.md) | `../OVERVIEW.md` |
| [docs-agents.md](./docs-agents.md) | `AGENTS.md` |

### Project how-tos

_(none yet)_

The how-tos written for the build being replaced went with it. Each described a procedure against code
that no longer exists — how the command surface was shaped, how a system prompt was layered, how to move
a reader onto the store, how to test against a disposable install. Rewriting one before the thing it
describes is rebuilt would be writing fiction, so each returns when its part lands and is proven.

## Rules for a project how-to

One task per file, named for the action. Steps in order with the actual commands and a check that confirms success. Self-contained.
