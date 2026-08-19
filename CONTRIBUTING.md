# Contributing to Rundesk

Thank you for helping improve Rundesk. This guide takes a new checkout from clone to the same gate
used on pull requests, without installing Rundesk or changing a live installation.

## Set up a checkout

Rundesk requires Python 3.9 or newer. The product uses only the Python standard library, has no
build step, and does not need a virtual environment.

```sh
git clone https://github.com/rundesk-ai/rundesk-cli.git
cd rundesk-cli
python3 --version
python3 scripts/suites
```

Do not run `./rundesk` while developing: without an explicit `RUNDESK_HOME`, it resolves the live
installation under your home directory. Use `./dev` instead; it scrubs inherited Rundesk settings
and selects a checkout-local scratch root.

```sh
./dev status
./dev --home /tmp/rundesk-contributor-check status
```

Never install, update, remove, or test against `~/.rundesk`. Tests and development commands must use
a disposable root, and install checks must also use a disposable `--bin-dir`.

## Run the gate

The complete test command is:

```sh
python3 scripts/suites
```

It discovers every `unittest` suite, closes network access for everything the tests start, and fails
when it finds no tests. Read the reported suite and test counts, not only the final `OK`.

Run a focused suite while working:

```sh
python3 -B tests/test_cli.py
```

Use `-B` for repeated focused runs so stale bytecode cannot answer a mutation check. Before opening
a pull request, run the complete suite on both the Python 3.9 floor and a current Python:

```sh
/usr/bin/python3 scripts/suites
python3 scripts/suites
```

Pull requests also run Ruff 0.16.1. Ruff is a development tool, not a product dependency. To run the
same check without adding anything to the repository:

```sh
python3 -m venv /tmp/rundesk-lint
/tmp/rundesk-lint/bin/pip install ruff==0.16.1
/tmp/rundesk-lint/bin/ruff check src tests scripts/suites rundesk
```

The required GitHub gate runs every suite on Python 3.9 and 3.13 on both macOS and Ubuntu, then runs
Ruff. A documentation-only change still runs that gate because commands and examples are part of
the product contract.

## Make a change

- Keep the runtime on the Python standard library; do not add product dependencies.
- Preserve the layer direction: `commands` → `lifecycle` → `core` → `utils`.
- Pass network operations into the code so every automated test remains offline.
- Resolve `RUNDESK_HOME` on each call rather than caching paths at import time.
- Update the relevant documentation whenever behavior or a command changes.
- Add a focused regression for every new guarantee. Break the implementation, watch the regression
  fail, and restore from a temporary copy before running it green.

Changes to persisted state require a new forward migration under
`src/rundesk/lifecycle/steps/`. Never rename, renumber, or edit a migration that has shipped. Test
install, update, removal, backup, or migration work for real against a disposable `RUNDESK_HOME` and
`--bin-dir` in addition to the automated suites.

## Commits and pull requests

Keep a commit focused on one reviewable outcome and use the repository's conventional prefix, such
as `fix:`, `feat:`, `docs:`, `test:`, or `chore:`. Do not include credentials, private URLs,
transcripts, personal information, or absolute home paths.

Before submitting:

1. Rebase or merge the current `main` branch and inspect the complete merge-base diff.
2. Run `git diff --check` and the full gate above.
3. Push a topic branch to your fork and open a pull request against `rundesk-ai/rundesk-cli:main`.
4. Complete every applicable section of the pull-request template. Leave an unproven validation box
   unchecked and state the exact blocker.
5. Link the issue the change completes with a standalone `Closes #<number>.` line. Use `Refs` when
   the pull request handles only part of an issue.

Bug reports and feature requests use the repository's GitHub issue forms. Search open and closed
issues first, provide the smallest sanitized evidence that proves the report, and never publish
credentials, prompts, transcripts, private messages, personal names, or absolute home paths.

## Release impact

Before Rundesk declares a stable 1.0 contract, approved breaking changes advance the minor version;
1.0 is a deliberate stability milestone rather than an automatic consequence of pre-stable work.
Rundesk otherwise follows semantic release impact:

- **Patch** — a backward-compatible correction.
- **Minor before 1.0** — a backward-compatible capability or an approved breaking CLI,
  adapter-protocol, persisted-state, or compatibility change.
- **Minor after 1.0** — a backward-compatible capability.
- **Major after 1.0** — a breaking CLI, adapter-protocol, persisted-state, or compatibility change.

A pull request should describe its release impact when the change is not plainly documentation,
tests, or internal maintenance. Releases and their notes are published through
[GitHub Releases](https://github.com/rundesk-ai/rundesk-cli/releases).
