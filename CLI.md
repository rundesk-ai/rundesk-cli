# The rundesk command

A verb says **what**. The next word says **whose** — `start ava`, `logs ava`, `channels ava`.
`[planned]` is registered and not built: it exits `69` and changes nothing.

**Generated from the command itself** — do not edit. Run
`python3 .knowledge/scripts/cli-reference` after changing the parser; the gate fails when this
file and the command disagree. *Why* the surface is shaped this way is
[`.knowledge/guides/the-command-surface.md`](.knowledge/guides/the-command-surface.md).

## Every operation

```sh
# an agent, and its life
rundesk add <agent>                                                  make an agent, and the gateway that runs it   [planned]
rundesk remove [--purge] <name>                                      take a gateway away for good
rundesk agents <agent>                                               every agent this install has, and what each is doing   [planned]
rundesk doctor <agent>                                               what stands between an agent and a working turn   [planned]

# running one
rundesk start <name>                                                 have the machine keep a gateway running
rundesk stop [--remove] [--purge] <name>                             stand a gateway down
rundesk restart <name>                                               cycle a gateway, leaving the others alone
rundesk logs [-n <lines>] <name>                                     what a gateway has been saying
rundesk serve <name>                                                 run a gateway here, until it is asked to stop

# reaching it
rundesk ask <agent> "<prompt>"                                       one turn, streamed to this terminal   [planned]
rundesk channels <agent> add                                         put this agent on a channel of a named kind, with what that kind needs   [planned]
rundesk channels <agent> remove                                      take this agent off a channel   [planned]
rundesk channels <agent> show                                        one channel, and who is allowed to reach this agent through it   [planned]
rundesk schedules add --when <when> --run <program> ... <schedule>   add a schedule
rundesk schedules off <schedule>                                     keep a schedule but stop it running
rundesk schedules on <schedule>                                      let a schedule run
rundesk schedules remove <schedule>                                  take a schedule away
rundesk runs <agent> resume                                          carry one run on from where it stopped   [planned]
rundesk runs <agent> show                                            one run — what was asked, what it cost, how it ended, and its stream   [planned]
rundesk runs <agent> stop                                            end one run, leaving the agent it belongs to running   [planned]

# rundesk itself
rundesk status                                                       every gateway, and what it is doing
rundesk version [--check]                                            what is installed, and whether that is current
rundesk update [--check]                                             move to the newest published release
rundesk uninstall                                                    how to remove rundesk from this machine
```

## What the arguments mean

```sh
--check               say whether a newer release exists
--gateway <name>      whose schedules — a gateway's schedules are its own
--purge               with --remove, also take its log, schedules and history
--remove              and take it away for good, once it has stopped
--run <program>       what to start when it is due
--when <when>         when it runs, stated as a schedule is
-n, --lines <lines>   how many of the last lines to show
<action>              what to do with them — one of add | remove | show
<agent>               whose — the agent's name
<name>                which gateway — the only one, unless named
<schedule>            what to call it, and what to name it by later
```

## What it exits with

```sh
0    it did the thing
1    it ran and failed, and said why
2    typed wrongly — read the help
69   this rundesk has not built that yet, and nothing changed
```

`69` is `EX_UNAVAILABLE`, and deliberately not `2`: a script has to tell
"this version lacks the command" from "the caller got it wrong", because the two want
opposite things done about them (R-CMD-8).
