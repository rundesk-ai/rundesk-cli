# The command surface

`rundesk` with no operation names everything it offers. Ask it rather than this page when the two
disagree — the command is generated from nothing and describes itself.

## Built

```sh
rundesk status              # how rundesk itself is on this machine
rundesk version             # what version this install is
```

`status` answers *how rundesk is*: its version, which root answered, where the program stands, and
whether it can run here. What agents there are and what they are doing is `agents` — two questions,
two commands, and one command answering both is a command nobody can predict the output of.

`version` reports the installed version and reaches nothing outside the machine.

## Registered, not built yet

```sh
rundesk version --check     # whether a newer release has been published
rundesk update [--check]    # move to the newest published release
rundesk uninstall [--purge] # remove rundesk from this machine

rundesk agents ...          # the named identities work is run for
rundesk messages ...        # what an agent has been asked, and what it answered
rundesk schedules ...       # work an agent starts because the time came
rundesk skills ...          # the skill library, and who is granted what
rundesk channels ...        # the surfaces an agent is reached on
rundesk backups ...         # copies of everything you keep
rundesk env ...             # the values every program rundesk starts is given
rundesk gateways ...        # the long-lived process an agent works inside
```

## What an unbuilt operation does

The product is rebuilt one part at a time, which leaves a question the command has to answer well:
what should `rundesk agents list` do on a day agents have not been rebuilt?

Three answers are wrong. Saying nothing and exiting `0` tells a script the work happened. Failing as
though it was attempted tells a person their machine is broken. Answering with argparse's usage error
makes "not built yet" and "you typed it wrongly" the same reply.

So every operation the finished product will offer is **listed from the outset**, and one that is not
built yet:

- **accepts the arguments it will take once built.** `rundesk skills install some/repo --confirm`
  is understood today; the option does not become a usage error just because the verb is not written.
- **names which part of itself is missing** — `skills grant`, not `skills`.
- **points at something that works.**
- **exits `69`.**

```console
$ rundesk agents list
agents list: NOT AVAILABLE — planned, not built yet
        what this rundesk can do:  rundesk --help
$ echo $?
69
```

## Exit codes

| Code | Means |
|---|---|
| `0` | it was done |
| `1` | it was attempted and did not work |
| `2` | the command line itself was wrong — a typo, an unknown verb |
| `69` | the operation is real, registered, and not built yet |

`69` is `EX_UNAVAILABLE` from the BSD conventions, and it exists so that `2` can keep meaning only
one thing. If an unbuilt verb answered `2`, a script could not tell an operation arriving in a later
release from one that will never exist.
