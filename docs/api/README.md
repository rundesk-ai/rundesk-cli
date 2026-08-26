# api/

Every operation Rundesk offers. **Twenty-one commands, and every one works** — there is no
"coming soon" list: a verb Rundesk cannot perform is a verb Rundesk does not have.

`rundesk --help` is the count that cannot go stale. Where it and this directory disagree, believe the
command.

| Page | Covers |
|---|---|
| [agents.md](./agents.md) | `agents` — add, configure, remove, and what removal takes with it |
| [gateways.md](./gateways.md) | `gateways` — start, stop, restart, logs, run |
| [channels.md](./channels.md) | `channels` — add, test, configure, remove, doctor |
| [schedules.md](./schedules.md) | `schedules` — add, update, show, run, remove |
| [skills.md](./skills.md) | `skills` — install, grant, revoke, update, doctor |
| [teams.md](./teams.md) | `teams` — install and update a declared team |
| [providers.md](./providers.md) | `providers`, `login`, and the private token bridge |
| [conversations.md](./conversations.md) | `ask`, `asked`, `messages`, `turns` |
| [install.md](./install.md) | `status`, `version`, `install`, `update`, `uninstall` |
| [configure.md](./configure.md) | `configure`, `env`, `backups`, `permissions` |

## Every verb, in one place

```sh
rundesk status                            # the version, where the install is, and every configured value
rundesk version                           # the version, and whether it is out of date
rundesk configure [--<setting> <value>]   # change what this install is configured with
rundesk agents                            # the agents this install keeps
rundesk agents add <agent> --provider <provider> [--alias <alias>] [--describes <text>]        # make one
rundesk agents configure <agent> [--provider <provider> [--alias <alias>]] [--describes <text>] [--self-improve <true|false>] [--delegate-to <agent> ... | --delegate-to-any | --delegate-to-none]  # change one
rundesk agents remove <agent> --confirm   # take one away, and everything it remembers
rundesk gateways                          # every agent, and how its gateway stands
rundesk gateways start <agent>            # start one, and prove a gateway came up
rundesk gateways stop <agent> | --all     # take the job back, gracefully
rundesk gateways restart <agent> [--continue] | --all  # refuse active work; otherwise stop and start
rundesk gateways logs <agent> [-n <lines>]  # what one gateway has been saying
rundesk gateways run <agent>              # be the gateway, in this terminal
rundesk schedules                         # everything every agent starts because the time came
rundesk schedules list <agent>            # one agent's
rundesk schedules add <agent> <schedule> --run '<program>' | --ask '<prompt>'  --when '<cron>' | --at <moment>
rundesk schedules update <agent> <schedule> [--when|--at|--until|--run|--ask|--enable|--disable]
rundesk schedules show <agent> <schedule> # everything one was given
rundesk schedules run <agent> <schedule>  # run one now, in this terminal
rundesk schedules remove <agent> <schedule>       # take one away
rundesk channels                          # every agent's channels, and how each one stands
rundesk channels list <agent>             # one agent's
rundesk channels add <agent> <adapter> --allow <id> [--notify] [--with '<adapter opts>']
rundesk channels show <agent> <adapter>   # everything one channel was given
rundesk channels configure <agent> <adapter> [--allow <id>] [--deny <id>] [--notify]
rundesk channels test <agent> <adapter>   # connect again, and say what it reached
rundesk channels remove <agent> <adapter> --confirm       # take one away
rundesk channels doctor [<agent>]         # what cannot be used, and exactly why
rundesk providers aliases list <provider> # additional account aliases and normalized status
rundesk providers aliases add <provider> <alias>  # register an empty provider-owned home
rundesk providers aliases remove <provider> <alias> --confirm  # remove an unused alias home
rundesk providers status|login|logout <provider> [--alias <alias>]  # provider-owned auth flows
rundesk backups                           # the copies of what rundesk keeps for you
rundesk backups save                      # copy what rundesk keeps, now
rundesk backups restore <backup> --confirm        # put a copy back
rundesk backups set-location <path>       # keep the copies in another directory
rundesk env list                          # every value rundesk keeps, shown only as a hint
rundesk env check <key>                   # whether one is set
rundesk env set <key>                     # keep one — typed, never passed as an argument
rundesk env unset <key>                   # empty one, leaving the name
rundesk login <provider> [--profile <name>]        # connect a verified account in the browser
rundesk login <provider> --replace-client [--confirm]  # rotate this app client, discarding its grants
rundesk skills                            # every skill this install has, and who holds which
rundesk skills list [<agent>]             # with an agent: what it holds, and what that needs
rundesk skills catalogs                   # every catalog, its version and where it came from
rundesk skills install <repository> [--confirm]   # install a catalog of skills
rundesk skills update <catalog> [--confirm]       # check one against where it came from
rundesk skills remove <catalog> [--confirm]       # take one away, and every skill in it
rundesk skills grant <agent> <catalog>/<skill> [--as <name>]   # give an agent a skill
rundesk skills revoke <agent> <skill>     # take one away from an agent
rundesk skills profiles <catalog>/<skill>         # every account one skill is configured for
rundesk skills configure <catalog>/<skill> [--profile <name>]  # set what it needs, guided
rundesk skills forget <catalog>/<skill> [--profile <name>] --confirm   # empty one account
rundesk skills doctor [<agent>]           # what cannot be used, and exactly why
rundesk teams                            # every installed team and its members
rundesk teams install <repository> [--provider <provider>] [--confirm]
rundesk teams update <team> [--provider <provider>] [--confirm]
rundesk update [--continue]               # move to the newest release, or say it is up to date
rundesk uninstall --confirm [--purge --root <dir>]  # purge needs the matching explicit root
rundesk install [--source <dir>] [--bin-dir <dir>]   # what install.sh runs
```

## Some flags are required by the verb rather than by argparse

`--provider`, `--allow`, `--confirm`, `--root` for a confirmed purge, and naming either a gateway or
`--all` are all required by their applicable verbs, and none is registered as `required=True`. That
is deliberate and it is the same decision every time:
argparse's own refusal names a flag and does not say what to type. *"the following arguments are
required: --provider"* is true and is not an answer, and the person reading it still has to work out
what a provider is and where the agent's name goes.

So the verb checks instead, and every refusal ends with the whole command somebody should run:

```console
$ rundesk agents add cole
agents: FAILED — nothing said which provider — say which with: rundesk agents add cole --provider <provider>
        nothing was made
```

The distinction is worth the code because these guard an *effect* rather than describe one.
`--confirm` is not a value the command needs in order to work; it is the thing standing between a
person and an agent's whole memory, and a guard on that is worth wording. Which exit code each one
answers with is below — a missing `--provider` is a command line that was right and refused, and a
`stop` that named neither a gateway nor `--all` is the command line itself being wrong.

## Exit codes

| Code | Means |
|---|---|
| `0` | it was done |
| `1` | it was attempted and did not work |
| `2` | the command line itself was wrong — a typo, an unknown verb, a bad flag |

Three codes, and the line between the last two is the one worth being careful about: **`1` says the
command was understood and could not be carried out, and `2` says it was never a command.** A script
that cannot tell those apart retries the wrong one.

Everything that lists — `status`, `agents`, `gateways`, `backups`, `env list`, `configure` with
nothing to change — exits `0` for whatever it found, because the question was *what is there* and
that question was answered. `rundesk gateways` finding every gateway on the machine down is a
listing that worked. What a bad state costs is the word `running`, not the exit code.

Five commands are written to have their code read by a script, and they are the ones to build on:

- **`rundesk env check <key>`** exits non-zero when a value is not set, so
  `rundesk env check DISCORD_TOKEN && …` does the right thing in a shell.
- **`rundesk version`** exits `0` even when it could not reach GitHub, because the question it was
  asked — what version is this — was answered from the machine itself. Being unable to ask is said
  on stderr as `UNKNOWN` and is never reported as being up to date.
- **`rundesk gateways start <agent>`** exits `0` only once a gateway has been shown to be holding
  the name. A job the supervisor accepted is not a gateway that started, and the exit code here
  means the second thing.
- **`rundesk channels doctor [<agent>]`** and **`rundesk skills doctor [<agent>]`** exit non-zero
  when anything is wrong, and `0` when there is nothing to check at all — an install with no channels
  is not an install with a broken one. The findings go to stdout so a script can read them and the
  summary to stderr so it can ignore them.

Where a refusal is a `2` rather than a `1`, it is because nobody said what to do. **`rundesk
gateways stop` with neither a name nor `--all` is a `2`** — the gateway is not one that would not
stop; the command line never named one. `gateways stop <agent> --all` is a `2` for the mirror
reason, and so is `gateways logs <agent> -n 0`, because argparse already answers `2` for an `-n`
that is not a number and one flag must not report the same class of mistake two ways.

Where a refusal is a `1`, the command line was right and could not be carried out: an agent that is
not on this install, an agents directory nobody can read, `--provider` left off, `--confirm` left
off. **A removal that did not happen is a failure** — `agents remove` and `uninstall` without
`--confirm` describe what they would take and exit `1`, because a command that took nothing and
exited `0` would tell a script the removal was done.

**The gateway process itself is the one exception on this page, and it is not an exception to the
table.** `rundesk gateways run` exits `0` on every refusal. That code is not a report to a person;
it is a sentence in a conversation with launchd, where `0` means *do not bring me back*. See
[`gateways.md`](../concepts/gateways.md).
