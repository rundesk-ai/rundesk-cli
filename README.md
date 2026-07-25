# rundesk

A lightweight, provider-agnostic multi-agent gateway. Provider CLIs are the agent
brains; chat platforms are interchangeable channels; the engine between them knows
neither.

Standard library Python only — no packages to install, and nothing to build.

## Install

```sh
curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash
```

From a checkout, `./install.sh` symlinks that checkout, so development and installed
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

## Tests

No test runner to install:

```sh
python3 tests/test_cli.py
python3 tests/test_updater.py
```
