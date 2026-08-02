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
6. **Cutting a release** — any version bump, tag, or publish — starts at
   `.knowledge/guides/cutting-a-release.md`. It answers what the `publishing-github-releases`
   skill asks of this repository; an agent that does not hold that skill still follows the guide.

## Hard gates — require explicit approval

- **Persisted state.** Any change to schema, stored data, or migrations is confirmed first.
- **Dependencies.** Do not add, remove, or major-version-bump a package without approval. An approved one
  is pinned in `requirements.txt` and reaches the machine only through `install.sh`.
- **Deletions.** Do not delete files outside the task's immediate scope without approval.
- **Commits.** Do not commit or push unless told to.
- **This file.** Never modify `AGENTS.md` without approval; when approved, follow
  `.knowledge/guides/docs-agents.md`.
- **The component ontology.** `base-` / `command-` / `platform-` / `agent-` / `channel-` / `lifecycle-`
  is declared in `.knowledge/prd/README.md` and signed off. Adding a component — a brain's is not declared
  yet — is the owner's call, and renaming or re-filing an existing one is worse than adding: requirement
  IDs are permanent.

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
  exits `NOT_AVAILABLE`, which is its own code and not argparse's usage one; a script that reads `0`
  believes the work happened, and one that reads `2` cannot tell a missing command from a typo.
- **Never let a test reach the network.** What is published and how an update is applied are arguments, so
  the suite passes or fails on this code and not on somebody else's uptime.

## Review and change threshold

No change is a valid completed outcome. The proposed change carries the burden of proof.

- A review tries to falsify ratified requirements, concrete rules in every governing `AGENTS.md` and
  owner-approved measurable limits. It does not search for ways the code could merely be different.
- Every review names its baseline — a commit, or a commit plus the named working-tree diff — and scope
  before reporting findings.
- A finding is actionable only when all are true:
  1. It exists on the current review baseline in a supported scenario.
  2. It violates a named `R-<AREA>-<n>` requirement, a concrete rule in a governing `AGENTS.md` or an
     owner-approved measurable limit; or it proves a new critical security, privacy, data-loss or
     state-corruption risk.
  3. It has a concrete user or operational consequence.
  4. It is reproduced or proven through a specific execution path.
  5. It is not a duplicate, deferred capability, accepted risk or closed decision without a reopening
     trigger.
  6. A regression check can distinguish fixed from unfixed.
- Behavior conforming to a ratified requirement is not a defect. A proposed behavior change is an owner
  decision; stop and ask rather than recording it as a finding.
- Refactoring, simplification, performance work and additional tests are not actionable without a
  qualifying defect, blocked ratified requirement or measured limit breach.
- Review-only work does not authorize implementation or a new task. A qualifying finding becomes work
  only when the owner accepts it or explicitly asked the same run to fix qualifying defects.
- `SUGGESTIONS.md` is the durable review ledger. Reviewers read its prior coverage and return the baseline,
  scope, outcome and reopening triggers; when ledger updates are authorized, the main agent records them.
- A completed review scope stays closed until relevant code, requirements or supported environments
  change; an incident, new reproduction, measured breach or recorded risk trigger also reopens it. Another
  available reviewer is not a reopening trigger.
- When nothing meets this threshold, report
  `NO ACTIONABLE FINDINGS at <baseline> for <review scope>.`

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
| `rundesk` | finding itself and handing off | `src/rundesk/cli.py` | hold any logic |
| `src/rundesk/cli.py` | the parser, the dispatch, and nothing else | the command groups below | do the work of a command inline |
| `src/rundesk/commands/*.py` | one command group each: a `Namespace` in, an exit code out | the modules below, and one another **one way** | depend on a group that depends on it |
| `src/rundesk/*.py` | one concern each, importable and testable alone | the standard library | know how it was invoked |
| `install.sh` | putting the command on a PATH, and taking it off | nothing in `src/` | contain product behavior |

## Best practices — do / don't

### A network call is an argument, not an import

The decision is what breaks; the transport is not. Pass it in and the whole module is testable offline.

```python
✅ def run(current, latest=None):          # resolved inside, so a test can replace it
       published = (latest or latest_version_online)()
❌ def run(current, latest=latest_version_online):   # bound once, at import — a test cannot reach it
```

### Determinism is designed, not hoped for

A decision receives every variable input — clock, environment, machine state and external reply — through
an argument or a replaceable collaborator resolved at call time.

```python
✅ def due(schedule, now): return schedule.matches(now)
❌ def due(schedule): return schedule.matches(datetime.now())
```

- Elapsed time and deadlines use `time.monotonic()`; wall time is only for calendar decisions, display and
  durable timestamps. Never compare the two.
- An `async def` never calls blocking sleep or a synchronous subprocess. Small local metadata reads and
  atomic writes may stay synchronous; anything unbounded leaves the event loop. Every new task has an owner
  that observes its exception and awaits, cancels or drains it during shutdown.
- User-visible and persisted output never relies on set, mapping or filesystem iteration order; sort it.
- A new persisted read-modify-write holds one lock across the read, decision and write. Unreadable state is
  not empty state and is never written back as empty.
- Broad exception handling exists only at cleanup and process boundaries, where it re-raises or produces a
  truthful failure outcome.
- Tests isolate every external surface they touch: the network, `HOME`, launchd and Rundesk state
  directories. Use real processes and clocks only when their operating-system behavior is the subject.
- Do not modify unrelated existing code merely to satisfy this section; a current violation needs an
  accepted finding under the review threshold above.

### One domain verb has one meaning

Use Rundesk's domain nouns — gateway, program, schedule, run, job, record, outcome and interruption — and
name the effect, not the mechanism.

```python
✅ def loaded(job): ...
✅ schedules = read_schedules(gateway)
❌ def check_thing(data): ...
```

- `cmd_<verb>` adapts a CLI command; `read` / `load` / `find` / `list` do not mutate; `write` / `save` /
  `remember` mutate durable state; `claim` / `release` change ownership; `start` / `stop` / `end` describe
  runtime lifecycle. Do not reuse one of these verbs for a different effect.
- Predicates read as yes-or-no questions at the call site; an `is_` or `has_` prefix is optional when the
  bare domain word already does so, such as `loaded(job)` or `tag_matches(tag, version)`.
- Collections are plural, one domain object is singular and units appear where ambiguity is possible
  (`timeout_seconds`, `held_bytes`, `started_at`).
- Placeholder names such as `one`, `it`, `said`, `done`, `data` and `info` stay inside tiny expressions
  where the role is unmistakable; longer scopes use the domain noun.
- Comments explain the invariant or failure being prevented, not the syntax below them.
- Apply these rules to new names and names already changing for an accepted task. Never create a rename-only
  task to retrofit untouched code.

### Say what is not built, and exit non-zero

```python
✅ print(f"{name}: NOT AVAILABLE — planned, not built yet", file=sys.stderr); return NOT_AVAILABLE
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
CLI.md                      every operation and argument — generated from the parser, never edited
src/rundesk/                one concern per module; the core
src/rundesk/commands/       one command group per module; the only layer that may know argparse
src/providers/              the brains that ship, one program each; run, never imported
src/channels/               the surfaces that ship, one program each; run, never imported
src/migrations/             one step forward each, named for the version it brings data up to
src/templates/              what a new agent's home is copied from
tests/                      unittest, run directly, offline
install.sh                  install, and --uninstall [--purge]
requirements.txt            what is needed beyond the standard library, pinned
.venv/                      where the install puts it — made by install.sh, git-ignored
.github/workflows/          the gate, and what a version tag publishes
.knowledge/                 the knowledge system, its two linters, and the gate
```

## Build, test & run

```sh
./rundesk                                          # the command surface
python3 .knowledge/scripts/gate                    # every suite, both linters, evidence, shell
```

**The gate:** that, then a real `./install.sh` and `./install.sh --uninstall`. The suites are **found**,
not listed — a file added to `tests/` is in the gate the day it lands, and `gate` fails when the workflow
does not name it too, because a list kept in two places is a list that disagrees with itself. Run one on
its own (`python3 tests/test_cli.py`) whenever that is what you want; it is not the gate.
`check-evidence` is not optional — `doc-lint` cannot tell whether a cited test is real, and this repo has
already shipped four contracts citing tests copied from another repository.

CI runs the same list on the oldest Python a fresh macOS ships and on a current one, on Linux and on
macOS, with an empty `.venv` beside the checkout so a runner is the machine a developer has. It finishes
by installing for real: the command answers, everything declared is present and importable, an installed
rundesk actually starts a gateway, and uninstalling leaves nothing but the checkout.

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
