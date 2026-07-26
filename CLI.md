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
rundesk add [--provider <provider>] [--model <model>] [--set <key=value>] [--instructions <text>] <agent>                                                                              make an agent, and the gateway that runs it
rundesk remove <agent>                                                                                                                                                                 take an agent away for good
rundesk agents                                                                                                                                                                         every agent this install has, and what each is doing
rundesk agents <agent>                                                                                                                                                                 what one agent is, and where it keeps things
rundesk doctor                                                                                                                                                                         what stands between every agent and a working turn
rundesk doctor <agent>                                                                                                                                                                 what stands between one agent and a working turn

# running one
rundesk start [--here] <agent>                                                                                                                                                         have the machine keep an agent running
rundesk stop [--all] <agent>                                                                                                                                                           stand an agent down
rundesk restart [--all] <agent>                                                                                                                                                        cycle an agent, leaving the others alone
rundesk logs [-n <lines>] [--source <source>] <agent>                                                                                                                                  what an agent has been saying

# reaching it
rundesk ask [--provider <provider>] [--model <model>] [--set <key=value>] [--conversation <conversation>] [--fresh] [--read-only] [--steer] [--instructions <text>] <agent> <prompt>   one turn, streamed to this terminal
rundesk ask [--provider <provider>] [--model <model>] [--set <key=value>] [--conversation <conversation>] [--fresh] [--read-only] [--steer] [--instructions <text>] <agent> <prompt>   with standing instructions, told apart from the prompt
rundesk channels <agent> add --kind <kind> --allow <user> [--token-stdin] [--activity | --no-activity] <channel> -- <option> [<arg> ...]                                               put this agent on a channel
rundesk channels <agent> instructions <channel> <text>                                                                                                                                 what this agent is told about where it is
rundesk channels <agent> remove <channel>                                                                                                                                              take this agent off a channel
rundesk channels <agent> show <channel>                                                                                                                                                one channel, and who may reach this agent through it
rundesk schedules <agent> add --when <cron> [--ask <prompt>] [--provider <provider>] [--model <model>] [--instructions <text>] [--to <channel>] <schedule> -- <program> [<arg> ...]    add a schedule
rundesk schedules <agent> off <schedule>                                                                                                                                               keep a schedule but stop it running
rundesk schedules <agent> on <schedule>                                                                                                                                                let a schedule run
rundesk schedules <agent> remove <schedule>                                                                                                                                            take a schedule away
rundesk schedules <agent> run <schedule>                                                                                                                                               run a schedule now, whether or not it is due
rundesk runs [--most <n>] <agent>                                                                                                                                                      what an agent has run, and what became of each
rundesk usage                                                                                                                                                                          what every agent has cost
rundesk usage <agent>                                                                                                                                                                  what one agent has cost

# rundesk itself
rundesk status                                                                                                                                                                         how rundesk itself is on this machine
rundesk version [--check]                                                                                                                                                              what is installed, and whether that is current
rundesk update [--check]                                                                                                                                                               move to the newest published release
rundesk uninstall [--purge]                                                                                                                                                            remove rundesk from this machine

# not yet grouped
rundesk resume <agent>                                                                                                                                                                 carry one run on from where it stopped   [planned]
rundesk search [--most <n>] <agent> <words>                                                                                                                                            what was said, by the words in it
```

## What it looks like

Signatures say what is *allowed*. These say what it **is** — the three things an
owner makes, as they are actually typed.

**An agent**

```sh
# an agent called ava, answered by the codex this machine already has
rundesk add ava --provider codex
# one answered by a brain you wrote, told which model and how hard to think
rundesk add ava --provider /opt/my-brain --model fast-1 --set effort=high
# have the machine keep it running, and bring it back when it falls over
rundesk start ava
```

**A channel**

```sh
# reachable in direct messages and in every room it has been invited to
rundesk channels ava add discord --kind discord --allow 279024636254224384
#   writes two channels — discord-dms and discord-rooms — each with its own allowed list, settings and instructions
# direct messages only; --server <id> or --channel <id> narrows the rooms instead
rundesk channels ava add discord --kind discord --allow 279024636254224384 -- --dm
# what it is told about where it is, before it reads a word of the message
rundesk channels ava instructions discord-rooms "You are {agent} in {where.channel}. Others read this, so keep it short."
# what it is reachable on, and whether it is reachable at all
rundesk channels ava
```

**A schedule**

```sh
# at three every morning, one turn, in a conversation of its own
rundesk schedules ava add nightly --when "0 3 * * *" --ask "summarise what changed today"
# the same, told it is running unattended before it reads a word
rundesk schedules ava add nightly --when "0 3 * * *" --ask "check the deploy" --instructions "Nobody is watching."
# a different brain for a different schedule, on the same agent
rundesk schedules ava add weekly --when "0 9 * * 1" --ask "what is worth knowing?" --provider codex
# a program rather than a turn, by its full path
rundesk schedules ava add tidy --when "0 4 * * *" -- /usr/local/bin/tidy --quiet
# keep it, and stop it running
rundesk schedules ava off nightly
```

## What the arguments mean

```sh
--activity, --no-activity       show what the agent is doing while it works, not only what it finally says (default: on)
--all                           every agent on this machine
--allow <user>                  who may reach this agent through it — at least one, always; repeatable
--ask <prompt>                  what to ask this agent when it is due, in quotes — a turn rather than a program
--check                         say whether a newer release exists
--conversation <conversation>   which conversation to carry on — this terminal's, when left out
--fresh                         start the conversation again rather than carrying it on
--here                          run it in this terminal instead of handing it to the machine
--instructions <text>           what every turn for this agent is told before it reads a prompt, where neither the schedule nor the surface said — empty takes it off
--kind <kind>                   which kind of surface — one that ships, or the path of a program that speaks yours
--model <model>                 which model, in that brain's own words
--most <n>                      how many to show, newest first (default: 20)
--provider <provider>           which brain answers for it when a turn does not say
--purge                         also take every agent's home, log and history
--read-only                     let this turn look at the machine without changing it
--set <key=value>               anything that brain takes, carried to it unread; repeatable
--source <source>               whose lines to show — what the gateway wrote, or what the machine caught that never reached it — one of all | gateway | machine
--steer                         keep saying more to it while it works — a line at a time, until you stop
--to <channel>                  which channel to say what this came to on, by the name it was added under — the account and `schedules` say it either way
--token-stdin                   read the credential this channel needs from standard input, one line; asked for at the terminal when left out
--when <cron>                   when it runs, as five cron fields — minute, hour, day, month, weekday
-n, --lines <lines>             how many of the last lines to show, from each source
<agent>                         which agent — the name it was made under
<channel>                       what to call it, and what to name it by later
<option>                        after `--`, whatever this kind of channel needs — carried to it exactly as typed, and never read here
<program>                       after `--`, the full path of what to start when it is due, and its arguments — a bare name is refused, because a gateway runs with almost no PATH
<prompt>                        what to ask it, in quotes
<run>                           which run — the id listed against each by `runs`
<schedule>                      what to call it, and what to name it by later
<text>                          what to tell it, with {agent} {channel} {surface} {where} {called} {user} {conversation} filled in — empty takes it back off, and left out shows what is there
<words>                         what to look for, in the words that were actually said
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
