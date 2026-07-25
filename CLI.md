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
rundesk add <agent>                                                               make an agent, and the gateway that runs it
rundesk remove [--purge] <agent>                                                  take an agent away for good
rundesk agents                                                                    every agent this install has, and what each is doing
rundesk agents <agent>                                                            what one agent is, and where it keeps things
rundesk doctor                                                                    what stands between every agent and a working turn
rundesk doctor <agent>                                                            what stands between one agent and a working turn

# running one
rundesk start [--here] <agent>                                                    have the machine keep an agent running
rundesk stop [--all] <agent>                                                      stand an agent down
rundesk restart [--all] <agent>                                                   cycle an agent, leaving the others alone
rundesk logs [-n <lines>] <agent>                                                 what an agent has been saying

# reaching it
rundesk ask <agent> "<prompt>"                                                    one turn, streamed to this terminal   [planned]
rundesk channels <agent>                                                          the channels an agent is reachable on, and who may use them   [planned]
rundesk channels <agent> add <channel> --kind <kind>                              put this agent on a channel, named as a schedule is   [planned]
rundesk channels <agent> remove <channel>                                         take this agent off a channel   [planned]
rundesk channels <agent> show <channel>                                           one channel, and who is allowed to reach this agent through it   [planned]
rundesk schedules <agent> add --when <cron> <schedule> -- <program> [<arg> ...]   add a schedule
rundesk schedules <agent> off <schedule>                                          keep a schedule but stop it running
rundesk schedules <agent> on <schedule>                                           let a schedule run
rundesk schedules <agent> remove <schedule>                                       take a schedule away
rundesk schedules <agent> run <schedule>                                          run a schedule now, whether or not it is due
rundesk runs <agent>                                                              what an agent has run, and what became of each   [planned]
rundesk runs <agent> resume <run>                                                 carry one run on from where it stopped   [planned]
rundesk runs <agent> show <run> [--stream]                                        one run — what was asked, what it cost, and how it ended   [planned]
rundesk runs <agent> stop <run>                                                   end one run, leaving the agent it belongs to running   [planned]
rundesk usage                                                                     what every agent has cost   [planned]
rundesk usage <agent>                                                             what one agent has cost   [planned]
rundesk usage <agent> <run>                                                       what one run cost   [planned]

# rundesk itself
rundesk status                                                                    how rundesk itself is on this machine
rundesk version [--check]                                                         what is installed, and whether that is current
rundesk update [--check]                                                          move to the newest published release
rundesk uninstall [--purge]                                                       remove rundesk from this machine
```

## What the arguments mean

```sh
--all                 every agent on this machine
--check               say whether a newer release exists
--here                run it in this terminal instead of handing it to the machine
--kind <kind>         which kind of channel it is — `discord`, and others as they land
--purge               also take every agent's home, log and history
--when <cron>         when it runs, as five cron fields — minute, hour, day, month, weekday
-n, --lines <lines>   how many of the last lines to show
<agent>               which agent — the name it was made under
<channel>             what to call this channel, and what to name it by later
<program>             after `--`, the full path of what to start when it is due, and its arguments — a bare name is refused, because a gateway runs with almost no PATH
<prompt>              what to ask it, in quotes
<run>                 which run — the id listed against each by `runs`
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
