# Install-wide configuration

`~/.rundesk/data/config.json` is the source of every install-wide value. A fresh install
writes the complete configuration, including automatic update and backup times and the
skills every agent must receive:

```json
{
  "backups": {
    "at": "04:00",
    "keep_last": 14
  },
  "updates": {
    "at": "03:00"
  },
  "roles": {
    "quiet_hours": 6
  },
  "skills": {
    "granted": [
      "managing-rundesk",
      "managing-schedules",
      "delegating-to-roles",
      "filing-github-issues",
      "writing-github-pull-requests",
      "writing-plans",
      "organizing-workspaces"
    ]
  }
}
```

Change `updates.at` and run `rundesk update` to reschedule automatic updates.

`roles.quiet_hours` is how long work handed to a role may produce nothing at all before
Rundesk settles the run and tells the agent that handed it over. It measures inactivity
rather than total runtime — a specialist execution legitimately takes hours and keeps
writing records the whole time — so raise it only if a brain here goes genuinely silent
for longer than that while still working.

A skill in `skills.granted` is attached to every new and existing agent and cannot be
revoked until it is removed from this list. Updates and reinstalls restore missing
required grants without removing optional skills an owner added.

`backups.keep_last` is how many copies are kept: taking one takes the copies beyond that
number away, oldest first, and never the newest. It bounds what the directory costs, which
an age cannot — each copy grows with the data in it. An install configured by an older
release keeps whatever `backups.keep_days` it stated, and nothing reads it any more;
`rundesk config` lists it under what nothing on this machine reads, and removing that line
is the owner's to do.

Backups are kept outside the program and agent data, so an update, uninstall, or data
purge cannot remove them. The backup directory may also be a symlink to a synced folder:

```sh
rundesk backups on
rundesk backups
```

Use `rundesk backups restore <backup>` to preview and restore a saved installation.

## The values every program is given

Rundesk builds the environment for every program it starts rather than inheriting one, so a
variable exported in your own shell never reaches a gateway, a brain or an integration
command. `rundesk env` is how you place one that does:

```sh
rundesk env set GITHUB_TOKEN                      # typed here, not echoed
printf '%s' "$TOKEN" | rundesk env set GH --stdin # from a script
rundesk env set OP_GH --from 'op read op://work/github/token'
rundesk env                                       # what is kept, and never a value
rundesk env check                                 # whether each can still be produced
rundesk env unset GITHUB_TOKEN
```

`--stdin` takes **the whole of what is piped in**, so a value with lines in it — a deploy key,
a PEM — arrives entire; one trailing newline is dropped, because every keeper adds one.
`--from` has two limits worth knowing before you rely on it. **It runs no shell**: the words
you give it are run directly, so a pipe, a redirect or a `$(…)` inside that string is kept as
literal words and the value comes out wrong rather than refused. And it is given **ten seconds
to answer**, which `op read` can exceed the first time it raises a Touch ID prompt — run it
once by hand so the vault is already unlocked, and use `rundesk env check` afterwards.

There is one set for the whole install. Every brain, every channel adapter, every schedule
and every integration command is given all of it, which is why an integration finds its
credential with nothing exported first — the shell it runs in descends from a program
rundesk started.

A value is kept one of two ways. **Held** puts it in a file only you can read. **Fetched**
keeps the words of a command that prints one — `op read`, `pass show`, `gpg -d` — and runs
it again each time a program starts, so the value is never on this disk at all. The words
of that command are kept and are shown by `rundesk env show`, so do not write a value into
one.

**Nothing shows a value in full, to you or to an agent.** What is shown is the last few
characters and a mark taken with a key of this install's: two names holding one value carry
one mark, so you can see at a glance that a credential reached you by two routes. There is
no flag that prints the rest.

Some names are refused, and the refusal is the point rather than a formality: anything
rundesk itself decides for a program (`PATH`, `HOME`, anything beginning `RUNDESK_`), and
anything that would change what code a program loads or runs (`DYLD_*`, `LD_*`, `PYTHON*`,
`NPM_CONFIG_*`, `NODE_OPTIONS`, `ZDOTDIR`). A value under one of those names would run
somebody's code inside every turn of every agent, for ever. **Those are examples, not the
list** — around thirty more are refused for the same reason, among them every shell startup
variable, `GIT_SSH_COMMAND`, `PERL5OPT` and every CA bundle. `rundesk env set` says which
check refused a name and why, so try it rather than working from this paragraph.

**An agent may place less than you can, and the difference is deliberate.** From inside a
turn only a name plainly shaped like a credential is kept — one ending `_TOKEN`, `_API_KEY`,
`_KEY`, `_SECRET`, `_PASSWORD`, `_PASSPHRASE`, `_CREDENTIAL`, `_CREDENTIALS` or `_AUTH`.
Anything else is yours to place at your own terminal. That is not a list of what is
dangerous — it is the other way round: the list of what is dangerous can never be finished,
because every new brain and every new integration brings its own runtime's variables, so
what an agent may place is stated positively instead. `HTTPS_PROXY` is the example worth
knowing: it routes every brain, adapter, `git` and `npm` through an address of its choosing,
and you may well need it behind a corporate proxy — so you can set it and an agent cannot.
**What nobody can set beside it is the certificate**: `SSL_CERT_FILE`, `SSL_CERT_DIR`,
`REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` and `NODE_EXTRA_CA_CERTS` are refused to you as well,
because a name saying who a program trusts decides what code it will accept. A proxy that
presents its own certificate therefore has to be trusted by the machine — in the system
keychain, or wherever that runtime reads its trust from — and `rundesk env` cannot do it for
you.

A channel's own credential always wins over one kept here. Two agents may hold two
different bots, so a value named for a channel's own variable is never given to that
channel's adapter — place a channel credential with `rundesk channels <agent> add`.

Where they are kept:

```sh
rundesk env --where     # ${XDG_CONFIG_HOME:-$HOME/.config}/rundesk/secrets
```

`RUNDESK_SECRETS_DIR` moves it. It stands **outside** the data directory deliberately, so
**a backup never carries a credential** — and a restore onto a new machine brings back
everything except these, which have to be placed again. An update does nothing to them; an
uninstall leaves them, and `--purge` takes them.

A replaced value reaches every program started from then on. A brain picks it up on its
next turn with no restart; a channel adapter, which is held open for as long as the gateway
is up, picks it up when that gateway next starts it.
