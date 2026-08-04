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
    RUNDESK_SECRETS_DIR="$station/secrets" \
    RUNDESK_JOB_PREFIX=ai.rundesk-station \
    ./rundesk agents
```

**`RUNDESK_SECRETS_DIR` is the one that does not live under the install at all**, and
leaving it out is the most expensive mistake on this page. `secret.home()` falls back to
`${XDG_CONFIG_HOME:-$HOME/.config}/rundesk/secrets` — the *live* one — so a station that
redirected everything else still writes there, and a station `--uninstall --purge` **deletes
it**, taking the key, the registry and every held value with it. `backup.py` copies
`data_home()` and nothing else, on purpose (R-SEC-26), so there is no restore. Measured on
2026-08-03: an uninstall with nine other paths redirected printed
`removed /Users/somebody/.config/rundesk` in the middle of an otherwise ordinary success.
Check `ls ~/.config/rundesk` before and after anything that uninstalls.

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

Do not simulate an upgrade by running a second checkout's `install.sh` over a station installed from
the first. The automatic-update job records the checkout that wrote it, so the second correctly refuses
to claim that job as its own. Test upgrade provisioning with the feature checkout's command under the
same fully redirected environment, and let the checkout that installed the station uninstall it.

## Throwing it away

**Uninstall it first, and delete the directory second.** The plists live in `$station/jobs`, so `rm -rf`
takes the *files* and leaves every registration standing: the station's gateways keep running, and
`ai.rundesk-station.<name>`, `ai.rundesk-station-update` and `ai.rundesk-station-automatic-update` stay
bootstrapped in your launchd domain, `KeepAlive`-retrying a program under `/tmp` that is no longer there.
That is the orphan this whole page is about, made by hand.

```sh
env -u RUNDESK_HOME -u RUNDESK_AGENTS_DIR -u RUNDESK_SCRIPTS -u RUNDESK_SKILL_LIBRARY \
    -u RUNDESK_RUN -u RUNDESK_CWD -u RUNDESK_POSTURE -u RUNDESK_PREFACE -u RUNDESK_RAW \
    RUNDESK_INSTALL_DIR="$station" \
    RUNDESK_DATA_DIR="$station/data" \
    RUNDESK_BACKUP_DIR="$station/backups" \
    RUNDESK_BIN_DIR="$station/bin" \
    RUNDESK_JOBS_DIR="$station/jobs" \
    RUNDESK_SECRETS_DIR="$station/secrets" \
    RUNDESK_JOB_PREFIX=ai.rundesk-station \
    ./install.sh --uninstall

rm -rf "$station"
launchctl list | grep rundesk       # the same lines you started with, and no station ones
```

**The same variables, spelled out again on purpose.** Removal finds a job by the prefix it was told, so
an uninstall run from a shell that forgot `RUNDESK_JOB_PREFIX` finds nothing of the station's, reports
success, and leaves every station registration behind — with the directory gone, there is then nothing
left that even names them.

Only the station root. The live install is `~/.rundesk`, and nothing here should ever name it.
