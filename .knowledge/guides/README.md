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

| Guide | How to |
|---|---|
| [the-command-surface.md](./the-command-surface.md) | Read the command's shape, and check a new verb against it |
| [moving-onto-the-store.md](./moving-onto-the-store.md) | Move a reader or writer off the old layout and onto what an agent keeps |
| [testing-against-a-station.md](./testing-against-a-station.md) | Run a checkout against a disposable install, so testing never reaches the live one |

## Moved out of here

Three how-tos are no longer here, and they did not all go to the same place.

**Writing a skill** ships as a skill — `src/templates/skills/writing-rundesk-skills/` — so the
agent doing the work is handed it rather than being expected to find it.

**Building a provider adapter** and **building a channel adapter** are documentation, under
`docs/extending/`, each carrying the full contract beside it as `references/the-contract.md`.
They are not skills: writing an adapter is a thing a person does once against this repository,
not a thing an agent needs in front of it on every turn. Named rather than linked — a catalog
link out of `.knowledge` is checked against a tree that holds `.knowledge` alone.

Edit them where they live. A guide that duplicated one would be a second place for the same
rule to be wrong.

## Rules for a project how-to

One task per file, named for the action. Steps in order with the actual commands and a check that confirms success. Self-contained.
