# Testing against a station

How to run a checkout of this repo against a **station** — a disposable install of its own — so that
nothing you are testing reaches the rundesk somebody is actually using.

Read this before running `./rundesk` by hand, and always before `./install.sh`.

## Why a checkout reaches the live install by default

Two ways, and the first one surprises everybody:

1. **An agent's shell is a gateway's child.** rundesk hands every program it runs the live install's
   environment — `RUNDESK_AGENTS_DIR`, `RUNDESK_HOME`, `RUNDESK_SCRIPTS`, `RUNDESK_RUN`. So an agent that
   runs `./rundesk agents` from a checkout is running new code against the *owner's* agents, having asked
   for nothing of the kind. Confirm with `env | grep RUNDESK` before you believe otherwise.
2. **A launchd label belongs to the person, not to the install.** `RUNDESK_INSTALL_DIR` moves every file
   two installs could fight over and none of it reaches the label, so `ai.rundesk-automatic-update` names
   one registration on the whole machine (R-INS-18, reported as #146).

## The station

```sh
station=/tmp/rundesk-station
env -u RUNDESK_HOME -u RUNDESK_AGENTS_DIR -u RUNDESK_SCRIPTS -u RUNDESK_SKILL_LIBRARY \
    -u RUNDESK_RUN -u RUNDESK_CWD -u RUNDESK_POSTURE -u RUNDESK_PREFACE -u RUNDESK_RAW \
    RUNDESK_INSTALL_DIR="$station" \
    RUNDESK_DATA_DIR="$station/data" \
    RUNDESK_BACKUP_DIR="$station/backups" \
    RUNDESK_BIN_DIR="$station/bin" \
    RUNDESK_JOBS_DIR="$station/jobs" \
    RUNDESK_JOB_PREFIX=ai.rundesk-station \
    ./rundesk agents
```

Unset every inherited `RUNDESK_*` rather than only the ones that look dangerous — one kept "because it
seemed harmless" is the whole failure this avoids.

`RUNDESK_JOB_PREFIX` is the one that is not a directory. Set it whenever the station may write, load or
remove a job at all — `install.sh`, `--uninstall`, `update`, `backups`, `start`, `stop`. Without it the
files land in the station and the *machine* still hears about `ai.rundesk-automatic-update`.

It may not sit under `ai.rundesk.` — `described()` globs `<prefix>.*.plist`, so a dotted one would have
the ordinary install read every station gateway as its own. Use a hyphen; a bad one is refused before the
command runs.

## Check it worked

```sh
./rundesk agents                    # the live agents — this is what you are avoiding
<the station command above>         # `no agents`, on a station that has none
launchctl list | grep rundesk       # before and after anything that touches a job
```

`launchctl list` is the only place the launchd half of this shows: an install elsewhere that takes a
registration away leaves the other install's plist on disk, so nothing looks wrong afterwards.

## Throwing it away

```sh
rm -rf /tmp/rundesk-station
```

Only the station root. The live install is `~/.rundesk`, and nothing here should ever name it.
