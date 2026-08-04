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

**Three layers, and they point one way.** `commands` → `lifecycle` → `core`. Nothing lower may
import anything higher.

| Layer | Owns | May depend on |
|---|---|---|
| `rundesk` | finding itself and handing off | `src/rundesk/cli.py` — it holds no logic at all |
| `src/rundesk/cli.py` | the parser and the dispatch, and nothing else | the command modules |
| `src/rundesk/commands/` | one verb each: a `Namespace` in, an exit code out. The only layer that may know argparse | `lifecycle`, `core` |
| `src/rundesk/lifecycle/` | this copy of rundesk on a machine: releases, the program tree, migrations | `core` |
| `src/rundesk/core/` | where things are, how a small file is kept, how the install is configured | the standard library |
| `install.sh` | fetching a copy and handing over | nothing — it holds no product behavior |

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

```sh
./dev status                       # the command, against a scratch root
python3 scripts/suites             # every suite, found rather than listed
python3 tests/test_update.py       # one of them
/usr/bin/python3 scripts/suites    # the 3.9 floor
```

Read the `Ran N tests` line, not the word `OK`: a suite that skipped everything is not a suite that
passed.

## Definition of done

1. `python3 scripts/suites` passes, on the 3.9 floor as well as on a current Python.
2. **Every new guarantee is proven by a test you have watched fail.** Break the code, run the suite,
   see red, put the code back — restoring from a `cp` copy and never from git, because the file you
   would be restoring holds everything you have not committed. A test that stays green with the
   feature removed is worse than none, because it is counted.
3. Anything that touches install, update or removal is also run **for real**, against a scratch
   `RUNDESK_HOME` and a scratch `--bin-dir`. Both defects found in this rebuild so far were found
   that way and neither was visible from the suite.
4. `~/.rundesk` is exactly as you found it.
5. The docs in `docs/` are true in the same task that changed reality.
