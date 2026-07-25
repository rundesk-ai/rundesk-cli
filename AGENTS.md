# AGENTS

Rules for every agent working in this repository. These rules are law; where they conflict with your general
habits, this file wins.

This is the **`rundesk` command line — a lightweight, provider-agnostic multi-agent gateway, in standard
library Python**. The *what & why* lives in `.knowledge/BRIEF.md`; the knowledge map is
`.knowledge/README.md`. This file defines how you build here.

## Before you work

Load light; pull depth only when the task needs it.

1. **Always read first:** `.knowledge/BRIEF.md` (what & why), `.knowledge/CODEMAP.md` (where things are),
   `.knowledge/MEMORY.md` (current friction). `.knowledge/README.md` maps the rest.
2. **On demand, when the task enters an area:** `.knowledge/prd/` (ratified contracts — source of truth),
   `.knowledge/prd-drafts/` (proposals), `.knowledge/research/` + `.knowledge/references/` (prior art, visual
   targets), `.knowledge/guides/` (how to write each doc + project how-tos).
3. **How work flows:** `research/` -> `prd-drafts/` -> `prd/`; a `prd/` contract never cites a draft. New
   guaranteed behavior is a `prd/` row backed by a test — cite its `R-<AREA>-<n>` in the code. Follow a doc's
   guide before writing or modifying it, and keep docs true in the same task. Run
   `python3 .knowledge/scripts/doc-lint .knowledge` before finishing; scratch -> `.knowledge/tmp/`.
4. Read every file before editing it; search before writing new logic — reuse, extend, refactor.
5. When the user raises a concern, investigate before contradicting — evidence, not a hunch.

## Hard gates — require explicit approval

- **Persisted state.** Any change to schema, stored data, or migrations is confirmed first.
- **Dependencies.** Do not add, remove, or major-version-bump a package without approval. An approved one
  is pinned in `requirements.txt` and reaches the machine only through `install.sh`.
- **Deletions.** Do not delete files outside the task's immediate scope without approval.
- **Commits.** Do not commit or push unless told to.
- **This file.** Never modify `AGENTS.md` without approval; when approved, follow
  `.knowledge/guides/docs-agents.md`.
- **The component ontology.** `base-` / `command-` / `lifecycle-` is declared in `.knowledge/prd/README.md`
  and signed off. Adding a component — the gateway's own are not declared yet — is the owner's call, and
  renaming or re-filing an existing one is worse than adding: requirement IDs are permanent.

## Never

- Never touch secrets or commit credentials.
- Never leave debug output or commented-out code in completed work.
- **Never add a dependency without approval, and never one the install does not place.** The standard
  library is the default and the preference. What genuinely cannot be done without — a websocket client
  for the Discord gateway, say — is declared in `requirements.txt` and installed by `install.sh` into the
  install's own `.venv`, pinned exactly. **Never the machine's Python**: modern ones refuse to be written
  to, and a tool that makes its user reason about that has already lost them. Nothing is ever left for a
  person to `pip install` by hand (R-INS-3, R-INS-4).
- **Never let a command report success it did not earn.** A verb that is planned and not built says so and
  exits `NOT_BUILT`; a script that reads `0` believes the work happened.
- **Never let a test reach the network.** What is published and how an update is applied are arguments, so
  the suite passes or fails on this code and not on somebody else's uptime.

## Tech stack

- **Runtime:** Python 3.9+ — the oldest version a fresh macOS ships, which is the floor CI pins. No build
  step and no packaging.
- **Dependencies:** the standard library, and nothing else unless it cannot be done without. What is
  needed is pinned in `requirements.txt` and installed by `install.sh` into the install's own `.venv`,
  which the launcher puts on the path. No requirements means no virtualenv is made at all.
- **Tests:** `unittest`, run directly (`python3 tests/test_cli.py`). No runner to install, and nothing
  reaches the network.
- **Distribution:** `install.sh` symlinks the checkout's `rundesk` onto a PATH directory.

## Architecture — the one rule that matters

The executable owns nothing. `rundesk` resolves its own location, puts `src/` on the path and calls
`cli.main` — every decision lives in a module that can be imported and tested without it.

| Layer | Owns | May depend on | Must not |
|---|---|---|---|
| `rundesk` | finding itself and handing off | `src/rundesk_cli/cli.py` | hold any logic |
| `src/rundesk_cli/cli.py` | the command surface and dispatch | the modules below | do the work of a command inline |
| `src/rundesk_cli/*.py` | one concern each, importable and testable alone | the standard library | know how it was invoked |
| `install.sh` | putting the command on a PATH, and taking it off | nothing in `src/` | contain product behavior |

## Best practices — do / don't

### A network call is an argument, not an import

The decision is what breaks; the transport is not. Pass it in and the whole module is testable offline.

```python
✅ def run(current, latest=None):          # resolved inside, so a test can replace it
       published = (latest or latest_version_online)()
❌ def run(current, latest=latest_version_online):   # bound once, at import — a test cannot reach it
```

### Say what is not built, and exit non-zero

```python
✅ print(f"rundesk {name}: coming soon …", file=sys.stderr); return NOT_BUILT
❌ pass  # silently returns 0, and the script that called it carries on
```

### Read the surface off the parser, never restate it

A list written twice is a list that disagrees with itself.

```python
✅ for verb in verbs():          # walked off the parser, so a new command is covered the day it lands
❌ for verb in ["agents", "doctor", "run"]:   # a hand-kept copy, already wrong
```

## Directory structure

```
rundesk                     the executable the installer symlinks onto PATH
src/rundesk_cli/            one concern per module; cli.py is the surface
tests/                      unittest, run directly, offline
install.sh                  install, and --uninstall [--purge]
requirements.txt            what is needed beyond the standard library, pinned
.venv/                      where the install puts it — made by install.sh, git-ignored
.github/workflows/          the gate, and what a version tag publishes
.knowledge/                 the knowledge system, and its two linters
```

## Build, test & run

```sh
./rundesk                                          # the command surface
python3 tests/test_cli.py                          # the surface, and what it refuses
python3 tests/test_updater.py                      # version, update, and their outcomes
python3 tests/test_install.py                      # putting it on a machine, and taking it off
bash -n install.sh                                 # the installer is valid shell
python3 .knowledge/scripts/doc-lint .knowledge     # the docs are valid
python3 .knowledge/scripts/check-evidence          # every ✅ names a test that exists
```

**The gate:** all seven. `check-evidence` is not optional — `doc-lint` cannot tell whether a cited test
is real, and this repo has already shipped four contracts citing tests copied from another repository.

## Documentation duties

Keep docs true in the same task that changes reality. Before creating or editing a doc, read its home
`README.md` and follow its `guides/docs-*.md`.

- Moved/restructured files -> update `.knowledge/CODEMAP.md`.
- Hit friction — **anything that cost you a failed attempt**: an env var or flag you had to discover,
  a guard you had to satisfy, a command that only worked the second way you tried it, an error whose
  message didn't say what to do -> **write the line into `.knowledge/MEMORY.md` the moment you find
  the workaround, before you carry on** — by the end of the task it will feel too small to mention,
  which is exactly how the next agent loses the same hour. Delete it once solved.
- Owner ratifies a draft (**the whole file**, not one row) -> `git mv` it into `prd/`; IDs carry over and
  the conformance review then sets glyphs. **Approval moves a draft, not proof** — proof is the glyph
  column. Behavior and its requirement row change in the same commit.
- Scratch -> `.knowledge/tmp/` (git-ignored).

## Definition of done

1. The gate passes: the tests, the shell check, doc-lint, and a real install that answers.
2. Every rule here held — no dependency added, nothing claiming a success it did not earn.
3. New guaranteed behavior is proven by a `prd/` requirement and its test.
4. **Friction you hit is in `.knowledge/MEMORY.md`, not only in your reply** — the next agent reads the
   file, not this conversation. Hit none? Say that in your reply. **Never write "no friction" into the
   file** — `MEMORY.md` records traps, never their absence.
