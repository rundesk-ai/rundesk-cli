# Where an install keeps everything

**One root, and every other place derived downward from it.**

`RUNDESK_HOME` is the only location rundesk reads. It defaults to `~/.rundesk`, and everything else
is a function of it:

```
$RUNDESK_HOME/
  app/        the program itself
  data/       everything you accumulate — agents, logs, skills, catalogs, configuration
  backups/    copies of data/
  projects/   the shared directory work is checked out into
```

| Below the root | What may reach it |
|---|---|
| `app/` | an update replaces it whole; an uninstall takes it whole |
| `data/` | never touched by an update; kept by an uninstall unless a purge asks for it |
| `backups/` | survives removal, including a purge; may be a link to another disk |
| `projects/` | yours, never rundesk's to tidy |

Set the root and every one of those moves with it:

```sh
RUNDESK_HOME=/tmp/somewhere rundesk status
```

## The copies may live elsewhere, and that is still one variable

`rundesk backups set-location /Volumes/Big/rundesk-backups` moves the copies to another disk and
leaves `backups/` as a **link** to it.

A link and not a setting, and that is the whole point. `RUNDESK_HOME` stays the only location rundesk
reads, `backups/` is still `$RUNDESK_HOME/backups`, and nothing anywhere gained a second place to
look — the filesystem holds the indirection rather than the configuration. Redirect the root and
everything still moves with it.

`rundesk status` shows both, because they are two different questions:

```
backups  /Users/you/.rundesk/backups → /Volumes/Big/rundesk-backups
```

And when that disk is not plugged in, it says so rather than reading as an install with no copies:

```
backups  /Users/you/.rundesk/backups → /Volumes/Big/rundesk-backups — that directory is not there
```

## Why one variable and not twelve

The build this replaces read a dozen independent variables — one each for the install, the data,
backups, agents, run state, logs, launchd jobs, secrets, the skill library and the scripts directory —
each with its own default under the owner's home.

That is one variable too many, and the failure it produces is always the same: somebody redirects
eleven of them, believes they have isolated the run, and the twelfth resolves to the live install.
That is not hypothetical. It deleted an owner's installed skills, wrote a real credential into their
secrets directory, and unregistered the job that kept their machine updating itself — each time while
reporting an ordinary success, and each time with nothing in the output naming the directory it had
actually used.

With one root, a partial redirect is not something you can express.

## Unset and empty are different answers

Nobody having said where the install is means the default, and is ordinary.

A variable that is *there and empty* means something tried to say and produced nothing — a script
whose own variable was unset, a scrubber that ran in the wrong order. Reading that as "nobody said"
points the command at your live install at the exact moment something was trying to point it
elsewhere, so it is refused out loud instead:

```
status: FAILED — RUNDESK_HOME is set and empty, which is not the same as unset
```

## Roots that are refused

Everything below the root is a directory an uninstall may delete, so a root that is too broad is one
command away from taking your home with it. These are refused rather than worked with:

- an empty value, and a value that is only whitespace
- a relative path — it would resolve against whatever directory you happened to be in
- `/`
- your home directory itself

The last one is not theoretical either: the installer this replaces recorded that pointing an install
at a home directory once emptied it, and then printed success.

## Where the program is, is a different question

`rundesk status` reports `program` as well as `home`, and they are not derived from each other.

A checkout install has the program in a source tree while the data belongs under your home, so
deriving the second from the first is right exactly until somebody runs the command from a checkout —
which is what a developer does every time.
