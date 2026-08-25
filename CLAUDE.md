# AGENTS

Rules for every agent working in this repository. These instructions define how to work here; where they conflict with general habits, this file wins.

## Purpose

This repository ships `rundesk`, a lightweight provider-agnostic multi-agent gateway, its installer,
agent-home templates, provider and channel adapters, and the bundled `rundesk` skill catalog. It is
distributed onto machines with durable agent state, so command outcomes, stored formats, migrations,
install/update behavior, and the Python 3.9 floor are contracts.

Read [`docs/BRIEF.md`](docs/BRIEF.md) and [`docs/CODEMAP.md`](docs/CODEMAP.md) first. Then
[`docs/api/`](docs/api/) for the operation contract, [`docs/concepts/layout.md`](docs/concepts/layout.md)
for installed state, and [`docs/guides/development.md`](docs/guides/development.md) before running a
checkout. A `docs/concepts/` page is the source of truth for its subsystem;
[`docs/extending/catalogs.md`](docs/extending/catalogs.md) is the contract for a published catalog.

## Before you work

1. Read `docs/BRIEF.md` and `docs/CODEMAP.md`, then `docs/api/`, `docs/concepts/layout.md`, and
   `docs/guides/development.md`; then the pages for what you are changing, and every file you edit.
2. Load the smallest complete set of applicable runtime skills. Use `writing-skills` for bundled
   skills, `naming-grammar-conventions` before choosing or changing recurring or cross-layer terms,
   and `managing-github` for pull requests or releases.
3. Inspect `git status`, the relevant diff, and the current tests before editing. Preserve other
   people's changes and treat unfamiliar files as owned data, not cleanup candidates.
4. Search before adding logic, terminology, tests, or documentation. Reuse, extend, or refactor the
   existing answer rather than creating a second one.
5. Establish the requested outcome, limits, compatibility requirements, and observable proof.
   Investigate concerns with code, tests, docs, or a safe reproduction before contradicting them.
6. Use [`.github/pull_request_template.md`](.github/pull_request_template.md) for pull-request work;
   preserve its headings and checklists and prove each claim against the exact head commit.

## Repository layout

```text
rundesk                         installed entry point; delegates to src/rundesk/cli.py
dev                             checkout runner with an isolated default root
install.sh                      fetches a release and hands off to rundesk install
src/rundesk/                    standard-library product code
  commands/                     argparse boundary; one verb per module
  lifecycle/                    releases, program copies, install changes, migrations
  core/                         paths, configuration, and stored values
  utils/                        product-agnostic common functions
  agents/, channels/, providers/, gateways/, schedules/, delegations/, skills/, capabilities/
                                  bounded domain packages; dependencies are enforced by tests
src/channels/, src/providers/   external adapter entry points
src/skills/                     bundled catalog manifest and skill packages
src/templates/                  agent home rules and purpose-named area templates
tests/test_*.py                 directly runnable isolated suites
tests/support.py                scrubbed environment, closed network, and scratch-root harness
scripts/suites                  discovers every suite and fails on empty discovery
docs/                           README, BRIEF and CODEMAP; every other page is in a home
  api/                          every operation, one page per group, and what each guarantees
  concepts/                     how a subsystem works, and how it fails
  guides/                       one task each, start to finish
  extending/                    writing an adapter or catalog against a published contract
  requirements/                 what must be true, and whether anything proves it
  research/                     dated findings about the world outside this repository
requirements.txt                exact adapter-only runtime pins; core rundesk remains stdlib
ruff.toml                       development/CI lint contract
```

Place work in the narrowest owning package. Do not create a second path resolver, state store,
transport, lifecycle route, migration registry, skill index, or documentation source of truth.

## Package and artifact contract

- The `src/rundesk` runtime supports Python 3.9+ and uses the standard library. Preserve 3.9 syntax
  and APIs. Adapter dependencies are exceptional, exact pins in `requirements.txt`; changing them
  or adding a dependency requires approval.
- Tests are `unittest` suites run directly and through `scripts/suites`. They use temporary roots,
  injected transports, and a closed network. Test success never depends on a remote service.
- `RUNDESK_HOME` is the only install-root variable. Resolve it on every call; unset and empty are
  distinct. A function given a root derives every path and lock from that root.
- Preserve command names, flags, exit behavior, installed layout, stored schemas, provider/channel
  contracts, archive layout, copies, lock boundaries, and old-release install/update compatibility.
- Shipped migrations under `src/rundesk/lifecycle/steps/` and `src/rundesk/agents/steps/` are
  immutable: never renumber, rename, or edit one. Add the next discovered step, make it safe when no
  change is needed, and settle with the release that landed in its own interpreter.
- `src/skills/manifest.json` and each discovered `src/skills/<name>/SKILL.md` form the bundled
  catalog. Directory and frontmatter names match; packages contain their own references and
  metadata; no skill depends on another checkout at runtime. A bundled skill may teach only commands
  and behavior this release actually provides. Use `writing-skills` for changes.
- The agent-home template in `src/templates/agent/` is a shipped artifact. Preserve the required
  identical `AGENTS.md`/`CLAUDE.md` pair placed from that one source.

## Safety and approval gates

Get explicit owner approval before changing persisted state or a migration design, command or
stored-format compatibility, Python floor or dependencies, install/update/removal/copy behavior, an
out-of-scope deletion, these rule files, or before committing, pushing, tagging, or releasing unless
the current request already grants that action.

- Never touch the live `~/.rundesk`: do not install, update, remove, write, migrate, run a command
  that resolves there, or inspect its stored contents. Use `./dev` or an explicit disposable
  `RUNDESK_HOME`, and pin a disposable `--bin-dir` for every install path.
- Record the live root's directory-level before/after check around any validation capable of writing
  and confirm it is unchanged. The check is a guard, never permission to read agent data.
- Never commit or expose credentials, tokens, private URLs, customer data, channel/person identity,
  private-project language, owner-specific paths, or other private identifiers. Use synthetic data.
- Never use destructive Git commands to undo shared work, including `reset --hard`, `checkout`, or
  `restore`. Make narrow edits and preserve unrelated worktree and index state.
- Never let a test reach the network. Pass decisions and transports as arguments and use the closed
  test harness.
- Never expose an operation that is not implemented or report an outcome the command did not earn.
  Unable to ask, unreadable, empty, current, and settled are distinct states when the product treats
  them as distinct.
- Never leave debug output, commented-out code, a disabled test, placeholder, or task-created
  temporary process, root, bin directory, or artifact.

## Delegation

Delegate only bounded, self-contained work when it materially helps. Give each worker non-overlapping
file ownership, the applicable rules, prohibited changes, expected evidence, and a definition of done.
Delegation never expands scope or approval. The parent agent retains product and naming decisions,
integration, review, and final proof. Do not duplicate delegated work or accept a summary as evidence
without inspecting the artifact and rerunning the relevant checks.

## Architecture and conventions

The core dependency spine points one way: `commands` -> `lifecycle` -> `core` -> `utils`. The complete
domain-package graph is declared and enforced in `tests/test_layers.py`; update architecture and its
mechanical proof together rather than bypassing it.

- `rundesk` finds itself and delegates. `src/rundesk/cli.py` owns parser assembly and dispatch.
  Command modules alone know `argparse`; each takes a `Namespace` and returns an exit code.
- Lifecycle owns this program copy on a machine: releases, install/update/removal, migrations, and
  replacement. Core owns locations, configuration, and durable values. Lower layers never import a
  higher layer.
- `utils/` is flat, few, concrete, and product-agnostic. It imports only the standard library and
  its own siblings. Do not place product terms or behavior there, use a grab-bag module, or shadow a
  standard-library module name. Keep its `__init__.py` table accurate.
- Pass network decisions and transports as arguments and resolve replaceable callables inside the
  function body, not as import-time default arguments.
- Resolve locations on every call. Never cache `RUNDESK_HOME`, collapse unset into empty, or derive a
  lock from any root other than the exact install or directory being changed.
- Preserve tri-state distinctions. Missing is not unreadable; unable to ask is not up to date; newest
  is not settled. Refuse or report the exact known state.
- Use the established domain lexicon: install, release, step, root, program, data, copy, agent,
  gateway, provider, channel, schedule, delegation, catalog, skill, grant. One domain verb has one
  meaning: `read`/`found` do not mutate; `write`/`stated` change durable state; `place`/`remove` act
  on the program tree; `carry` moves an install forward. Preserve published spellings and document
  intentional layer mappings.
- Name modules for the concrete thing a reader seeks, operations for outcomes, and values/entities
  with noun phrases. Comments explain an invariant or prevented failure, never restate syntax.
- A discovery check fails when it discovers nothing. Read test counts, not only `OK`.

## Documentation duties

Keep documentation true in the same change as behavior.

- Keep `docs/` in its layout. Only `README.md`, `BRIEF.md`, and `CODEMAP.md` sit at its root;
  every other page is in `api/`, `concepts/`, `guides/`, `extending/`, `requirements/`, or
  `research/`. Use the `structuring-project-docs` skill before adding a home, moving a page, or
  writing a requirement. Never create a second source of truth, and never create an empty home.
- Keep pages thin. Lead with the fact, use a table wherever the content is tabular, and split a page
  that has grown past a screen per section rather than trimming it evenly.
- Add a page's row to its home's `README.md` in the same change that adds the page. An index behind
  its directory is worse than no index.
- Keep every file in `docs/requirements/` on the closed schema: `id`/`name`/`last_verified`
  frontmatter, then `What this is`, `Why it exists`, `Requirements`, `Open questions`. A ✅ names a
  check that was observed to pass; a source path is not evidence, and neither is an unrun test.
  Requirement IDs are `R-<NS>-<n>`, one namespace per file, never reused and never renumbered.
- Update `docs/api/` whenever the public operation list or a command guarantee changes, including
  the complete verb list in its `README.md`.
- Update `docs/concepts/layout.md` for every installed path, stored item, ownership, migration, copy, lock, or
  lifecycle-layout change.
- Update `docs/guides/development.md` when the supported run, isolation, lint, or test process changes.
- Update the owning page for providers, channels, catalogs, gateways, schedules, permissions,
  adapters, teams, instructions, time, or another documented subsystem.
- Update bundled skill instructions and references when the behavior they teach changes. Never let
  a skill promise an unavailable verb or stale workflow.
- Keep `AGENTS.md` and `CLAUDE.md` byte-identical. Edit one complete source and copy it to the other;
  never maintain divergent instructions.

## Build, test, and run

There is no build or packaging step. Running the checkout is the build. Before commands capable of
writing, capture the directory-level state of `~/.rundesk`; perform all work in disposable paths;
then repeat the live-root check and confirm no change.

A change limited to `README.md` does not require the full Python suites or Ruff locally. Run
`python3 -B tests/test_layers.py`, render the Markdown through GitHub, verify every changed link,
anchor, command, and product claim against its source, and run `git diff --check`. Required GitHub
checks still run on the pull request.

```sh
./dev status
python3 scripts/suites
/usr/bin/python3 scripts/suites
ruff check src tests scripts/suites rundesk
bash -n dev
bash -n install.sh
git diff --check
```

Run `python3 scripts/suites` on a current interpreter and the floor suite with a confirmed Python
3.9 interpreter; `/usr/bin/python3` is the documented local floor only when its version check says
3.9. CI proves both 3.9 and current Python on Linux and macOS. Run the CI-equivalent AST parse over
`src/**/*.py`, `tests/*.py`, `scripts/suites`, and `rundesk`. Read every suite count and the final
discovery summary. `ruff` is a development-only gate, not permission to add a product dependency.

For install, update, removal, migration, or copy work, exercise the real path with one disposable
`RUNDESK_HOME` and one disposable `--bin-dir`; inspect success and a material refusal/failure path,
exit status, output, and filesystem effects. Clean both paths afterward. Record exact commands,
versions, suite/test counts, shell checks, live-root before/after result, and observations.

## Pull requests and releases

- Complete the pull-request template from evidence for the exact head commit. Explain every
  unchecked or inapplicable item; never pre-check a future result.
- Inspect the full diff and commit-visible artifacts for credentials, private URLs, customer data,
  channel/person identity, private-project language, owner-specific paths, and unrelated files
  before publication. Use a GitHub noreply identity for public authorship and verify actual metadata.
- Required CI must pass for the exact PR head. After merge, verify the exact merge commit's `main`
  workflow before any authorized release tag.
- A release tag `vX.Y.Z` must equal `src/rundesk/__init__.py::__version__`; publish only the expected
  archive and preserve install/update compatibility. Follow the protected release workflow.
- Process-only changes to `AGENTS.md`, `CLAUDE.md`, pull-request templates, or equivalent repository
  guidance do not change runtime or bundled-catalog versions. Published command, persisted-state, or
  skill behavior follows its normal compatibility, SemVer, migration, and release rules.
- Do not commit, push, merge, tag, publish, deploy, install, or release unless the current request
  explicitly grants that action.

## Definition of done

A task is complete only when all applicable items below are observed, not inferred:

1. The full requested scope is implemented, with no unreported stub, TODO, unrelated change,
   temporary process, scratch root, bin directory, or artifact.
2. For runtime changes, every discovered suite passes with non-zero counts on a current Python and
   confirmed Python 3.9; the CI-equivalent AST parse, `ruff`, both shell parses, and
   `git diff --check` pass. A `README.md`-only change instead passes the focused documentation gate
   in **Build, test, and run**.
3. Every new guarantee has a focused regression test observed failing without the implementation and
   passing with it. A process-only guide change instead requires guide parity and heading-order proof.
4. Any affected command, install, update, removal, migration, or copy path has isolated success and
   material refusal/failure evidence. The live `~/.rundesk` directory-level before/after check matches.
5. Architecture direction, immutable migrations, earned outcomes, naming semantics, Python floor,
   offline tests, stored formats, and bundled catalog contracts remain intact unless explicitly and
   validly changed.
6. Documentation is current, and `AGENTS.md` and `CLAUDE.md` are byte-identical with the required
   heading order.
7. The final diff is narrow, clean, privacy-reviewed, and contains no secret, private identifier,
   owner-specific path, disabled test, debug residue, or unrelated artifact.
8. Report changed paths, exact commands and observed results, manual checks, and every unrun or
   blocked check. Re-read this file and verify this definition before calling the work complete.
