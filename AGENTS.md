# AGENTS

Rules for every agent working in this repository. These rules are law; where they conflict with your
general habits, this file wins.

This is the **`rundesk` command line — a lightweight, provider-agnostic multi-agent gateway, in
standard library Python**. It is being rebuilt from the outside in, and what is here works: the
lifecycle of the command itself. Everything else is coming, and until it is here it is not offered.

## Before you work

1. **Read [`docs/`](docs/)** — three pages, and they are short. [`layout.md`](docs/layout.md) is where
   an install keeps everything, [`commands.md`](docs/commands.md) is every operation and what it
   guarantees, [`development.md`](docs/development.md) is how to run and test a checkout without
   installing it. Read `development.md` before you run anything.
2. **Read the code you are about to change, in full, before changing it.** These modules are short
   and they explain themselves; the reasoning that matters is in the docstrings.
3. **Search before writing new logic** — reuse, extend, refactor.
4. When the owner raises a concern, investigate before contradicting: evidence, not a hunch.

## Never

- **Never touch `~/.rundesk`.** It is the owner's live install with real agents in it, not a fixture.
  Never install, uninstall, update, or write anything there, and never run a command that resolves
  there by default. Use `./dev`, or set `RUNDESK_HOME` to a scratch directory. Pin `--bin-dir` too:
  `install` with no `--bin-dir` writes into a real directory on your PATH. Check `ls ~/.rundesk`
  before and after anything that writes.
- **Never add a dependency.** The standard library is the whole toolkit. `requirements.txt` is empty
  and an empty one means no virtualenv is built at all, which is a feature. If you believe something
  genuinely cannot be done without a package, stop and ask.
- Never touch secrets or commit credentials.
- Never leave debug output or commented-out code in completed work.
- **Never offer an operation that is not built.** A verb rundesk cannot perform is a verb rundesk
  does not have. There is no "coming soon" surface and no exit code for one — do not reintroduce
  either.
- **Never let a command report a success it did not earn.** This is the rule the product is built
  around. An installer that did not check, a removal that did not happen, an update that could not
  ask and said "up to date" — each of those has cost this project real damage on a real machine.
- **Never let a test reach the network.** What is published and how a release is fetched are
  arguments, so the suite passes or fails on this code and not on somebody else's uptime.

## Hard gates — ask first

- **Persisted state.** Any change to what an install keeps on disk, or to a migration step that has
  shipped, is confirmed first.
- **Deletions.** Do not delete files outside the task's immediate scope.
- **Commits.** Do not commit or push unless told to.
- **This file.** Never modify `AGENTS.md` without approval.

## Tech stack

- **Runtime:** Python 3.9+ — the oldest a fresh macOS ships, and the floor CI pins. No build step and
  no packaging.
- **Dependencies:** the standard library, and nothing else.
- **Tests:** `unittest`, run directly. `python3 scripts/suites` runs them all.
- **Distribution:** `install.sh` fetches a release and hands off to `rundesk install`.

## Architecture — the rule that matters

**Four layers, and they point one way.** `commands` → `lifecycle` → `core` → `utils`. Nothing lower
may import anything higher, and `tests/test_layers.py` checks that rather than trusting it.

| Layer | Owns | May depend on |
|---|---|---|
| `rundesk` | finding itself and handing off | `src/rundesk/cli.py` — it holds no logic at all |
| `src/rundesk/cli.py` | the parser and the dispatch, and nothing else | the command modules |
| `src/rundesk/commands/` | one verb each: a `Namespace` in, an exit code out. The only layer that may know argparse | `lifecycle`, `core`, `utils` |
| `src/rundesk/lifecycle/` | this copy of rundesk on a machine: releases, the program tree, the copies, migrations | `core`, `utils` |
| `src/rundesk/core/` | where things are, how the install is configured, and the values it keeps | `utils` |
| `src/rundesk/utils/` | common functionality with no opinion about rundesk: a small file kept safely, a replacement staged, a table lined up | the standard library, **and nothing of rundesk's** |
| `install.sh` | fetching a copy and handing over | nothing — it holds no product behavior |

**`utils/` is few and concrete, not many and abstract.** A module there is named for the thing you
would go looking for, and the test is whether somebody hunting *"can this agent name be a
directory?"* would guess the file. Nobody guesses `naming.py`; everybody guesses `files.py`. Things
that fail together belong together — a name with a separator lands a file somewhere else and a write
that is not staged lands it half-written, so both live in `files`. Never take a name the standard
library has (`logging`, `types`, `select`, `signal`): anything inside the package imports yours
instead of the real one. Keep it flat until there are eight or ten, then group by what a module
touches — never into a drawer called `misc`. The module table in `utils/__init__.py` is checked
against the directory by `tests/test_layers.py`, because it had already gone stale once.

**`utils/` is the strict one, and the rule is a membership rule rather than a preference.** Nothing
in it may be domain knowledge or product logic: everything there is functionality any project could
have, and the mechanical test is that it imports the standard library and nothing of this product's —
not `paths`, not `config`, not even `exits`. If a function had to be told what an install, a release,
an agent or a copy is in order to be written, it belongs a layer up.

The line is finer than it looks, so here is where it was drawn: `as_table` lays out columns and lives
in `utils`; `as_written` renders an unset value as the words "not yet" and lives in `commands`,
because choosing the words a product speaks is not common functionality. Do not put something in
`utils` merely because two layers happen to use it today.

A verb's parser is built beside the verb, in a small function. The build this replaces had one
`build_parser()` of about 680 lines, which is where a surface goes to stop being readable.

## Best practices — do / don't

### A network call is an argument, not an import

The decision is what breaks; the transport is not. Pass it in and the whole module is testable
offline — and resolve it **inside** the body, because a default bound in the signature is decided
once, when the function is defined, and nothing can reach past it.

```python
✅ def cmd_update(args, asking=None):
       line, published, could_ask = release.standing(__version__, asking)
❌ def cmd_update(args, asking=release.latest_published):   # bound at import; a test cannot replace it
```

### Where things are is resolved on every call, never cached

`RUNDESK_HOME` is the **only** location this product reads, and everything else is a function of it.
Binding a location at import is how a suite comes to write into the real install.

- Never add a second location variable. If you think you need one, you are about to recreate the
  defect this rebuild exists to fix.
- **Unset and set-to-empty are different answers**, and so are "missing" and "unreadable". Anything
  that collapses them loses state — a value nobody could read is never written back as empty.

### A lock belongs to the install it is changing

Anything handed a directory to work on derives its lock from *that* root, never from `RUNDESK_HOME`.
A function given somewhere to work that reaches outside it to lock is the one-location defect in
miniature — and it happened: a call passed an explicit directory and left a lock file in a live
install that nothing else in that run went near.

### Say which of the three it is

Being unable to ask is not a quiet form of being up to date, an unreadable file is not an empty one,
and being on the newest release is not the same as being settled on it. Every one of those pairs has
a third state, and every bug of this kind looks like a feature that silently never fires.

### One domain verb has one meaning

Use the product's own nouns — install, release, step, root, program, data, copy — and name the
effect, not the mechanism. `read`/`found` do not mutate; `write`/`stated` change durable state;
`place`/`remove` act on the program tree; `carry` moves an install forward. Comments explain the
invariant or the failure being prevented, not the syntax below them.

### Anything that finds its own work fails when it finds none

A check that discovered nothing has proved nothing. `scripts/suites` fails on an empty discovery for
exactly this reason: the runner it replaces globbed a directory that had moved, matched zero files,
and printed success.

## Migrations

Two levels. **Install migrations** are here — `src/rundesk/lifecycle/steps/NNNN_name.py`, one step
per file, found rather than listed. **Agent migrations** are a separate level and are not built yet.

- **A step that has shipped is never renumbered, renamed or edited.** Its id is how every install on
  every machine knows whether it has run. A step that needs changing is a new step.
- A step is written to be safe against an install that does not need it. Check, then act.
- A step may create and may copy; it deletes only what it has just replaced.
- After files land, the install is settled by **the release that landed**, in its own interpreter —
  the process doing the replacing still holds the previous release's imported modules.

## Build, test & run

**There is no build step.** No packaging, no compile, no virtualenv — `requirements.txt` is empty and
an empty one means no environment is built at all. Running the checkout *is* the build.

```sh
./dev status                       # the command, against a scratch root
python3 scripts/suites             # every suite, found rather than listed
python3 tests/test_update.py       # one of them
/usr/bin/python3 scripts/suites    # the 3.9 floor
ruff check src tests scripts/suites rundesk    # what CI enforces on every pull request
```

Read the `Ran N tests` line, not the word `OK`: a suite that skipped everything is not a suite that
passed.

**`ruff` is not a dependency of the product.** It is configured in [`ruff.toml`](ruff.toml), fetched
in CI, and nothing a person installs ever sees it — which is what keeps `requirements.txt` empty. You
do not need it to work here, but the gate is not met until it is clean, so it is cheaper to have it:
`docs/development.md` has the two lines that put it in a scratch virtualenv outside the tree.

## Definition of done

These are a gate, not a checklist to sample from. Work that has not been through all of them is not
finished, however complete it looks.

1. `python3 scripts/suites` passes, on the 3.9 floor as well as on a current Python. There is no
   build to run: an empty `requirements.txt` is the whole environment.
2. **`ruff check src tests scripts/suites rundesk` is clean.** CI enforces it on every pull request,
   so a branch that skipped it is a branch that fails there instead of here.
3. **Every new guarantee is proven by a test you have watched fail.** Break the code, run the suite,
   see red, put the code back — restoring from a `cp` copy and never from git, because the file you
   would be restoring holds everything you have not committed. A test that stays green with the
   feature removed is worse than none, because it is counted.
4. Anything that touches install, update, removal or the copies is also run **for real**, against a
   scratch `RUNDESK_HOME` and a scratch `--bin-dir`. The first defects found in this rebuild were
   found that way and none of them was visible from a green suite.
5. `~/.rundesk` is exactly as you found it. Check it before and after, not only after.
6. The docs in `docs/` are true in the same task that changed reality — including the list of
   operations in `commands.md`, which is the page that claims to be complete.
