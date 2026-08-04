# Codemap — rundesk-cli

The always-loaded structural map: *where things are*, layer by layer. Keep it current — when you move
or restructure files, update this in the same task.

**Stay high-level.** List entry points, layers, and where each *kind* of thing lives — not every file.
A map that mirrors the whole tree rots on the next commit; one that names the landmarks stays true.

## The state of the tree

**The product is being rebuilt, and `src/` holds only what the rebuild has reached.** The
build being replaced is readable in this branch's history; it is reference, never an import. A module
appears below when it is written and proven, so this map is short on purpose and grows one part at a
time. If something you expect is missing here, it has not been rebuilt yet — and the command will say so
rather than pretend.

## Entry Points

- `rundesk` — the executable an install symlinks onto a PATH. It resolves its own location, puts
  `src/` on the path and hands off to `cli.main`. **It owns no logic**, which is what makes
  everything below it importable and testable without it.
- `dev` — the same command pointed at a scratch root instead of the owner's install. Scrubs every
  `RUNDESK_*` variable **and then** sets the one the product reads, and prints the root it used.
  Use it for anything you would otherwise type as `./rundesk`.

## Domain / Data

- `src/rundesk/__init__.py` — **`__version__`, and nothing else.** The one source of what version
  this copy is. Nothing holds a copy of it.
- `src/rundesk/exits.py` — the four codes a command may end with, and why `NOT_AVAILABLE` is its
  own number rather than argparse's usage one.
- `src/rundesk/planned.py` — every operation the finished product will offer, from the owner's
  `brief.md`. An entry leaves this table on the day its verb becomes real.

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

## Backend / Services (src/rundesk/)

- `src/rundesk/paths.py` — **the one root, and everything derived downward from it.** Described
  above; the module the rebuild exists for.
- `src/rundesk/cli.py` — the parser, the dispatch, and nothing else. A verb's parser is built beside
  the verb in a small function; the build this replaces registered thirty verbs inline in one
  function of about 680 lines. `offered()` reads the surface off the parser, so nothing anywhere
  keeps a second list of what the command can do.
- `src/rundesk/commands/` — **one command group per module, and the only layer that may know
  argparse.** A group takes a `Namespace` and hands back an exit code. `__init__.py` holds what more
  than one group needs and nothing below wants: how a table is printed, and how an operation that is
  not built refuses.

## Frontend / UI

- No UI. The command line is the whole surface.

## Tests (tests/)

`unittest`, run directly (`python3 tests/test_cli.py`). No runner to install, and nothing reaches the
network.

- `tests/support.py` — **the import path and the scratch root, in one place.** Every suite inherits
  `Isolated`, which gives the case a temporary root and then *asserts* the product resolved it before
  the case runs. The build this replaces had no shared helper: thirty-five suites each isolated a
  slightly different subset of a dozen locations, and one of them wrote real agents onto the owner's
  machine. A case that quietly ran against the live install passes just as green as one that did not.
- `tests/test_paths.py` — one root, the places below it, and the roots that are refused.
- `tests/test_cli.py` — the surface, walked **off the parser**, so a verb wired to nothing is caught
  the day it lands.

## Scripts And Commands

- `.knowledge/scripts/suites` — runs every suite, **found rather than listed**, and fails when it
  finds none. CI calls this same script. The runner it replaces globbed a directory that had moved,
  matched nothing, and printed success.
- The reference generator and the evidence check return when the parts they check are built.

## Docs

- `.knowledge/` — the knowledge system (prd/, prd-drafts/, research/, references/, guides/). See
  `.knowledge/README.md`. The shipped standards and linter are checksum-pinned; the catalogs are ours.
- `brief.md` at the repository root — the owner's restructure plan for the command surface and the
  records behind it. Read it; never edit it.

---
*Editing this file? Follow the standard first: [`guides/docs-codemap.md`](./guides/docs-codemap.md).*
