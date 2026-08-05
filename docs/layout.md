# Where an install keeps everything

**One root, and every other place derived downward from it.**

`RUNDESK_HOME` is the only location rundesk reads. It defaults to `~/.rundesk`, and everything else
is a function of it:

```
$RUNDESK_HOME/
  app/            the program itself
  data/           everything you accumulate — agents, logs, skills, catalogs, configuration
  backups/        copies of data/
  projects/       the shared directory work is checked out into
  secrets/        the values you place for what rundesk talks to
  .rundesk.lock   held while one command at a time changes this install
```

| Below the root | What may reach it |
|---|---|
| `app/` | an update replaces it whole; an uninstall takes it whole |
| `data/` | never touched by an update; kept by an uninstall unless a purge asks for it |
| `backups/` | survives removal, including a purge; may be a link to another disk |
| `projects/` | yours, never rundesk's to tidy |
| `secrets/` | **never copied by a backup**; taken only by a purge |
| `.rundesk.lock` | rundesk's own; taken away by an uninstall |

`.rundesk.lock` is the file one command at a time holds while it changes the install. It stands
beside the directories rather than inside `data/` on purpose: the operations it makes safe *move
`data/` itself*, and a lock inside the thing being renamed away is a lock two commands can end up
holding different copies of. That is not hypothetical — a `configure` landing in the moment a
restore had renamed `data/` aside recreated the directory, reported success, and had its change
deleted by the restore's own rollback.

One lock for the whole install rather than one per directory, because the races worth stopping are
between *different* commands touching different things, and a lock per directory lets exactly those
through.

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

## Why the values you place are not below `data/`

`rundesk env set` keeps a token where a backup cannot reach it, and that is the whole of its
placement: **a copy is a copy of `data/` and nothing else**, so this install's backups are
structurally incapable of holding a credential rather than careful not to. There is no code path
from a copy to `secrets/`, so there is none to get wrong.

It follows that a restore does not put a credential back either, which is the right way round: a
value somebody typed once is not state a copy should be able to reinstate.

The directory is `0700` and every file in it `0600`, repaired on each write, and neither the
directory nor the key may be reached through a symlink — a link decides where bytes land, and a
dangling `key` aimed into `data/` would put the one thing that opens every value into the directory
a backup copies.

Each value is sealed with a key kept beside it, so nothing is readable text on the disk. Each is
also signed **over its name as well as its bytes**, so a value that was tampered with *or moved to
a different name* is refused rather than opened: signing the bytes alone would let anybody able to
edit the file swap two sealed values between names, with no key at all, and a program asking for
its Discord token would be handed the Slack one and send it to Slack.

**The key sits beside the values because a gateway has to start at boot with nobody typing**, which
is the honest limit of the whole thing: this stops a credential being readable text on a disk, in a
stray copy, or in whatever a filesystem hands back after a delete. It does not stop somebody with
the owner's account, or root.

## What a copy does not carry

A copy is made with the standard library, and on macOS that quietly means **extended attributes and
resource forks are not copied** — Finder tags, Finder comments, and anything else stored beside a
file rather than in it. Not a choice: CPython has no `os.listxattr` on macOS at all, so the standard
library's own copy step is a no-op there, on every version including the 3.9 floor.

The contents of every file are copied exactly. It is worth knowing before you rely on a restore to
bring back something that was never in the bytes.

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
