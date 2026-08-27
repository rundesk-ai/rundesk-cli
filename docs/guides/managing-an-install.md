# Run a Rundesk install day to day

What to check, what to change, and what to do before something risky. Every command here is in
[`../api/install.md`](../api/install.md) and [`../api/configure.md`](../api/configure.md); this is the
order to use them in.

## Check where you stand

```sh
rundesk status
```

One screen: the version, where the install is, how many agents it keeps, whether it is fit to run,
and every configured value. Two lines repay attention.

- **`program`** says which copy of the code answered and whether it is this root's own install or a
  checkout. Running a checkout against an install's data is an ordinary thing to do by accident.
- **`migration`** says how far the install has been carried. Arriving on a release and settling on it
  are different; see [`../concepts/lifecycle.md`](../concepts/lifecycle.md#arriving-is-not-settling).

```sh
rundesk version
```

Asks GitHub whether a newer release exists. **`UNKNOWN` is never reported as up to date** — if GitHub
could not be reached the line goes to stderr and says so.

## Update

```sh
rundesk update
```

It reports three outcomes separately — application, ordinary catalogs, team catalogs — because a
repository that has been deleted is a true catalog failure and a false reason to say the application
update failed.

If a provider turn or schedule is active, the update is recorded and retried by a detached worker
rather than taking work away mid-flight. Updates replace the program under `~/.rundesk/app` and
preserve everything under `~/.rundesk/data`.

Automatic daily updates are on by default:

```sh
rundesk configure --update-enabled no
rundesk configure --update-time 03:00
```

## Keep copies

```sh
rundesk backups          # what there is, newest first
rundesk backups save     # one now
```

**Save one before anything approved and destructive.** A copy is the whole of `data/`. It carries the
sealed value store *and its key*, so treat wherever it is kept as credential-bearing data.

```sh
rundesk backups set-location /Volumes/big/rundesk-backups
rundesk backups restore <backup> --confirm
```

A restore replaces everything the install keeps, and keeps a copy of what it replaced. Retention is
`rundesk configure --backup-retention <n>`.

## Values a skill or adapter needs

```sh
rundesk env list          # names and a hint, never the values
rundesk env set DISCORD_TOKEN
rundesk env check DISCORD_TOKEN && echo set
```

**A value is typed at the prompt, never passed as an argument** — an argument reaches the shell
history and the process list. `env check` exits non-zero when a value is not set, so it composes in a
script.

## What macOS lets Rundesk do

```sh
rundesk permissions            # what the last check found; runs nothing
rundesk permissions check      # prove it now
rundesk permissions lineage    # whose grants an answer here would be about
```

**An answer belongs to a process, not to a machine.** Anything you start from a terminal inherits
what you once granted that terminal; a gateway starts with nothing. Read the lineage line rather than
the invocation — only a run that says `gateway` is a fact about one.
[`../concepts/permissions.md`](../concepts/permissions.md) has the verdicts.

## When something is wrong

Start with the doctors. Both exit non-zero when anything is wrong, and `0` when there is nothing to
check at all.

```sh
rundesk gateways            # is anything holding the name
rundesk gateways logs ava
rundesk channels doctor
rundesk skills doctor
rundesk providers check codex
```

| Symptom | Look at |
|---|---|
| an agent answers in the terminal and nowhere else | `rundesk gateways` — the gateway is what serves channels and schedules |
| the bot is online and silent | `rundesk channels doctor ava` |
| a skill is granted and the brain cannot see it | `rundesk skills doctor ava` |
| a scheduled job never ran | `rundesk gateways logs <agent>` — every firing is accounted for there |
| a turn behaved oddly | `rundesk turns <agent> <turn>` |

## Remove it

```sh
rundesk uninstall --confirm            # removes rundesk, keeps what it kept for you
rundesk uninstall --confirm --purge    # also takes the data — never the backups
```

Without `--confirm` both describe what they would take and exit non-zero, because a removal that took
nothing and exited `0` would tell a script the removal was done.
