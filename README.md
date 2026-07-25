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

### The gateway

A gateway is the part that stays running. There is one per **name** — one per agent,
once there are agents — so any one of them is restarted without disturbing the rest.

```sh
rundesk serve [name]                # run one here, until it is asked to stop
rundesk start [name]                # hand it to the machine, which keeps it running
rundesk stop [name]                 # stand it down
rundesk restart [name]              # cycle one, leaving the others alone
rundesk status                      # every gateway, and what each is working on
rundesk logs [name] [-n]            # what one has been saying
```

Leave the name out and it means the one gateway there is today — and every one of
them, for `stop`, `restart`, `status` and `logs`, once there are several.

rundesk supervises nothing itself. `start` writes a job and hands it to launchd, which
brings a gateway back if it falls over and starts it again after a reboot. A gateway
that *refuses* to run — a virtualenv that no longer fits, a name already held — ends
cleanly so the machine does not spend the rest of the day restarting it.

`status` asks the gateways rather than the machine, so it can show the one thing a
supervisor cannot: up, and not going round.

```
gateway              running kept up, pid 4192, version 0.1.1, 2 in flight (a-conversation, another)
agent-two            WEDGED — not going round kept up, pid 4210, version 0.1.1, idle
agent-three          not running kept up
```

Everything else — `agents`, `new`, `doctor`, `run`, `replay` — is registered and says
**coming soon**. The whole shape is visible from the start; a command that is not built
exits non-zero rather than reporting a success it did not earn.

### What a gateway guarantees

- **One of each name.** Proved by a lock the kernel drops however the process died, so a
  gateway that was killed cannot leave a record that makes it look alive.
- **It owns what it starts.** Everything a gateway runs goes in its own process group, so
  ending it ends the whole tree — the provider CLI and every tool it spawned.
- **Nothing runs twice.** The same piece of work is refused while it is already running,
  and a gateway ends work an earlier gateway of that name left behind.
- **Long work is left alone.** A session may run for hours; what is ended is one that has
  gone silent, or one still going long past when real work would have finished.
- **It writes down what happened**, to a log that outlives it — kept apart from its run
  state, because stopping clears what a gateway is *doing* and must not clear what it did.

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

No test runner to install, and nothing reaches the network or runs a provider:

```sh
python3 tests/test_process.py      # a program rundesk runs, and keeping hold of it
python3 tests/test_gateway.py      # one gateway per name, and what it takes with it
python3 tests/test_supervisor.py   # handing a gateway to the machine that keeps it up
python3 tests/test_cli.py          # every verb, and what it honestly refuses
python3 tests/test_updater.py      # which version this is, and moving between them
python3 tests/test_install.py      # putting it on a machine, and taking it off
```

What each of those guarantees is written down as a contract in
[`.knowledge/prd/`](./.knowledge/prd/), row by row, with the test that proves it named
beside it — and `python3 .knowledge/scripts/check-evidence` fails the build if a row
names a test that does not exist.
