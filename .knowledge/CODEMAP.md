# Codemap — rundesk-cli

The always-loaded structural map: *where things are*, layer by layer. Keep it current — when you move
or restructure files, update this in the same task.

**Stay high-level.** List entry points, layers, and where each *kind* of thing lives — not every file.
A map that mirrors the whole tree rots on the next commit; one that names the landmarks stays true.

## The state of the tree

**The product is being rebuilt, and `src/` is empty of everything the rebuild has not reached.** The
build being replaced is readable in this branch's history; it is reference, never an import. A module
appears below when it is written and proven, so this map is short on purpose and grows one part at a
time. If something you expect is missing here, it has not been rebuilt yet — and the command will say so
rather than pretend.

## Entry Points

_(none yet — the launcher lands with the foundation.)_

## Domain / Data

_(none yet.)_

### Where an install keeps what it keeps

**One root, and everything derived downward from it.** This is the decision the rebuild exists to get
right: the replaced build resolved its locations from a dozen independent environment variables, each
defaulting under the owner's home, so redirecting all but one still reached the live install.

`RUNDESK_HOME` is the only location the product reads (default `~/.rundesk`). Everything else is a
function of it:

| Below the root | What it holds | What may reach it |
|---|---|---|
| `app/` | the program itself | an update replaces it whole; an uninstall takes it whole |
| `data/` | everything the owner accumulates | never touched by an update; kept by an uninstall unless a purge asks for it |
| `backups/` | copies of `data/` | survives removal, including a purge |
| `projects/` | the shared directory agents check work out into | the owner's, never rundesk's to tidy |

Where the *program* stands and where the *data* stands are two different questions, and the program's
own location is never used to answer the second: a checkout install has the program in a source tree
while the data belongs under the owner's home.

## Backend / Services

_(none yet.)_

## Frontend / UI

- No UI. The command line is the whole surface.

## Tests

_(none yet.)_ `unittest`, run directly (`python3 tests/<file>.py`). No runner to install, and nothing
reaches the network. The rebuild adds one shared `tests/support.py` that owns the path insert and the
scratch-root isolation, because the replaced build had no shared helper and repeated both in every
suite — which is how a suite came to run against the owner's real install without anyone noticing.

## Scripts And Commands

_(none yet.)_ The gate, the reference generator and the evidence check are rewritten against the new
tree as the parts they check are built.

## Docs

- `.knowledge/` — the knowledge system (prd/, prd-drafts/, research/, references/, guides/). See
  `.knowledge/README.md`. The shipped standards and linter are checksum-pinned; the catalogs are ours.
- `brief.md` at the repository root — the owner's restructure plan for the command surface and the
  records behind it. Read it; never edit it.

---
*Editing this file? Follow the standard first: [`guides/docs-codemap.md`](./guides/docs-codemap.md).*
