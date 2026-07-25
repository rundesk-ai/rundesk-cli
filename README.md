# rundesk

A lightweight, provider-agnostic multi-agent gateway. Provider CLIs are the agent
brains; chat platforms are interchangeable channels; the engine between them knows
neither.

Standard library Python only — no packages to install, and nothing to build.

## Install

```sh
curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash
```

It installs into **`~/.rundesk`** — one directory under your home, holding rundesk and
anything it needs. Nothing else on your machine is written to, and your shell profile is
left alone: if the command is not on your `PATH`, the installer says so and shows the line
to add rather than editing a file you own.

From a checkout, `./install.sh` symlinks that checkout instead, so development and installed
use share one layout.

```sh
./install.sh --uninstall [--purge]   # take it off again
```

## Commands

```sh
rundesk                             # what it can do
rundesk version [--check]           # what is installed, and whether that is current
rundesk update [--check]            # move to the newest published release
rundesk uninstall                   # how to remove it
```

Everything else — `agents`, `new`, `doctor`, `run`, `replay`, `serve`, `start`,
`stop`, `restart`, `status`, `logs` — is registered and says **coming soon**. The
whole shape is visible from the start; a command that is not built exits non-zero
rather than reporting a success it did not earn.

## Version

One source of truth: `__version__` in `src/rundesk_cli/__init__.py`. The command reports it, the updater
compares against it, and a release tag must match it — CI fails a `vX.Y.Z` tag that disagrees.

```sh
rundesk version           # what this install is, without asking anyone
rundesk version --check   # …and whether a newer release exists
rundesk update            # move to it
```

Three answers, kept distinguishable on purpose: **up to date**, **vX.Y.Z is available**, and **could not
reach the forge** — the last exits non-zero, because "could not ask" must never read as "you are current".

## Tests

No test runner to install:

```sh
python3 tests/test_cli.py
python3 tests/test_updater.py
```
