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

Removing rundesk stops every gateway it was keeping and takes their jobs with them, before
anything is deleted — and refuses outright if one of them will not stop. What your gateways
*wrote* is kept: their logs, your schedules, and the account of what those schedules did.
`--purge` takes those as well.

## Commands

```sh
rundesk                             # what it can do
rundesk version [--check]           # what is installed, and whether that is current
rundesk update [--check]            # move to the newest published release
rundesk uninstall                   # how to remove it
rundesk status                      # how rundesk itself is on this machine
```

### The gateway

A gateway is the part that stays running. There is one per **name** — one per agent,
once there are agents — so any one of them is restarted without disturbing the rest.

```sh
rundesk start <agent> [--here]      # have the machine keep one running, or run it here
rundesk stop <agent> | --all        # stand one or every agent down
rundesk remove <agent> [--purge]    # take a stopped agent away for good
rundesk restart <agent> | --all     # cycle one or every agent
rundesk agents [<agent>]            # what every agent is doing, or where one keeps things
rundesk logs <agent> [-n]           # what one has been saying
rundesk schedules <agent> [...]     # work that starts itself — see below
```

`stop` and `restart` require either one agent or an explicit `--all`. Removal always names
one: standing every gateway down is a fine thing to ask for and a terrible thing to guess
at, so removal never does.

`start` creates a gateway by writing a job the machine keeps — which is also why one
you are finished with stays in your machine's background items until it is removed.
`stop` deliberately leaves that job alone, so the gateway comes back on the next start.
`remove` is what takes it: the job, what the gateway was doing, and its name.

What a gateway *wrote* is kept — its log, its schedules and the account of what those
schedules did. `--purge` takes those too. Removal refuses outright while the gateway is
still running, or while the machine will not let go of its job, and in either case takes
nothing at all: half-removed is worse than not removed, because the job is the only thing
that would ever find that gateway again.

rundesk supervises nothing itself. `start` writes a job and hands it to launchd, which
brings a gateway back if it falls over and starts it again after a reboot. A gateway
that *refuses* to run — a virtualenv that no longer fits, a name already held — ends
cleanly so the machine does not spend the rest of the day restarting it.

`agents` asks the gateways rather than the machine, so it can show the one thing a
supervisor cannot: up, and not going round.

```
AGENT    STATE    PID    UPTIME  LAUNCHD JOB  VERSION  WORK
ava      RUNNING  4192   2h14m   LOADED       0.1.1    2 (a-conversation, another)
claude   WEDGED   4210   6h02m   LOADED       0.1.1    idle
codex    STOPPED  -      -       NOT LOADED   -        -
```

`LAUNCHD JOB` is asked of the machine, not read off a file: a job description sitting in
a directory is not a job launchd is keeping, and the two come apart. It is reported
separately from the gateway process state and PID because a loaded job does not prove
which process, if any, it owns.

### Schedules

Work that starts itself, because the time came. Every gateway has its own — so when there
are agents, each one's schedules are its own and never another's to run.

```sh
rundesk schedules <agent>                                      # what is scheduled, and what it last did
rundesk schedules <agent> add <name> --when <cron> -- <cmd…>   # state one
rundesk schedules <agent> remove <name>                        # take it away
rundesk schedules <agent> on|off <name>                        # keep it, but stop it running
rundesk schedules <agent> run <name>                           # run it now
```

```
SCHEDULE  STATE  WHEN         NEXT              LAST RUN          OUTCOME
tidy      ON     */5 * * * *  2026-07-25 10:45  2026-07-25 10:40  finished
nightly   OFF    0 3 * * *    off               2026-07-24 03:00  finished
```

- **Nothing is run late.** A time that passed while nothing was running is gone — running
  five at once on the way up is worse than not running them — but the gap is written to
  the log, because silence is indistinguishable from a schedule that never worked.
- **Nothing overlaps.** A schedule that is still running when it next falls due is skipped
  and said so, using the same guard that stops any work running twice.
- **It runs once for the minute it is due**, however often the clock is examined — across a
  restart, and across the hour a clock goes back.
- **What it names is refused where it is written.** A gateway runs with almost no `PATH`,
  so a program named rather than located is refused by `add` rather than discovered at
  three in the morning.

An agent and its gateway now share one name and one home: `rundesk add ava` makes both,
`rundesk start ava` starts its gateway, and `rundesk schedules ava` shows its schedules.
Provider turns, channels, runs and usage are registered and still say **coming soon**.
Run `rundesk --help` for the list; it is read off the command rather than copied out here,
so it cannot come to disagree with what you have installed. A command that is not built
exits `69` rather than reporting a success it did not earn — a number of its own, so a
script can tell "this rundesk does not have that" from "you typed it wrong".

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
- **Removing one takes nothing while anything still holds it.** A gateway that is running,
  a job the machine will not release, a name another process is using — any of them and
  removal reports why and takes nothing, rather than leaving something running that nothing
  can find.

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
python3 tests/test_schedule.py     # work that starts itself, because the time came
python3 tests/test_cli.py          # every verb, and what it honestly refuses
python3 tests/test_updater.py      # which version this is, and moving between them
python3 tests/test_install.py      # putting it on a machine, and taking it off
```

What each of those guarantees is written down as a contract in
[`.knowledge/prd/`](./.knowledge/prd/), row by row, with the test that proves it named
beside it — and `python3 .knowledge/scripts/check-evidence` fails the build if a row
names a test that does not exist.
