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
rundesk add [--provider <provider>] [--model <model>] [--set <key=value>] [--instructions <text>] <agent>                                                                                                               make an agent, and the gateway that runs it
rundesk configure [--provider <provider>] [--model <model>] [--set <key=value>] [--instructions <text>] <agent>                                                                                                         change an existing agent's durable defaults
rundesk remove <agent>                                                                                                                                                                                                  take an agent away for good
rundesk agents                                                                                                                                                                                                          every agent this install has, and what each is doing
rundesk agents <agent>                                                                                                                                                                                                  what one agent is, and where it keeps things
rundesk doctor                                                                                                                                                                                                          what stands between every agent and a working turn
rundesk doctor <agent>                                                                                                                                                                                                  what stands between one agent and a working turn

# running one
rundesk start [--here] <agent>                                                                                                                                                                                          have the machine keep an agent running
rundesk stop [--all] <agent>                                                                                                                                                                                            stand an agent down
rundesk restart [--all] [--force] <agent>                                                                                                                                                                               cycle an agent, leaving the others alone
rundesk logs [-n <lines>] [--source <source>] <agent>                                                                                                                                                                   what an agent has been saying

# reaching it
rundesk ask [--provider <provider>] [--model <model>] [--set <key=value>] [--conversation <conversation>] [--fresh] [--read-only] [--steer] [--instructions <text>] <agent> <prompt>                                    one turn, streamed to this terminal
rundesk ask [--provider <provider>] [--model <model>] [--set <key=value>] [--conversation <conversation>] [--fresh] [--read-only] [--steer] [--instructions <text>] <agent> <prompt>                                    with standing instructions, told apart from the prompt
rundesk channels <agent> add --kind <kind> --allow <user> [--token-stdin] [--activity | --no-activity] <channel> -- <option> [<arg> ...]                                                                                put this agent on a channel
rundesk channels <agent> allow [--add <user>] [--remove <user>] <channel>                                                                                                                                               who may reach this agent through one channel
rundesk channels <agent> instructions <channel> <text>                                                                                                                                                                  what this agent is told about where it is
rundesk channels <agent> remove <channel>                                                                                                                                                                               take this agent off a channel
rundesk channels <agent> show <channel>                                                                                                                                                                                 one channel, and who may reach this agent through it
rundesk schedules <agent> add [--when <cron>] [--at <moment>] [--ask <prompt>] [--provider <provider>] [--model <model>] [--instructions <text>] [--to <channel>] [--in <where>] <schedule> -- <program> [<arg> ...]    add a schedule
rundesk schedules <agent> edit [--when <cron>] [--at <moment>] [--ask <prompt>] [--provider <provider>] [--model <model>] [--instructions <text>] [--to <channel>] [--in <where>] <schedule> -- <program> [<arg> ...]   change an existing schedule, keeping what it has done
rundesk schedules <agent> off <schedule>                                                                                                                                                                                keep a schedule but stop it running
rundesk schedules <agent> on <schedule>                                                                                                                                                                                 let a schedule run
rundesk schedules <agent> remove <schedule>                                                                                                                                                                             take a schedule away
rundesk schedules <agent> run <schedule>                                                                                                                                                                                run a schedule now, whether or not it is due
rundesk schedules <agent> show <schedule>                                                                                                                                                                               one schedule, and everything it was given
rundesk runs [--most <n>] <agent>                                                                                                                                                                                       what an agent has run, and what became of each
rundesk usage                                                                                                                                                                                                           what every agent has cost
rundesk usage <agent>                                                                                                                                                                                                   what one agent has cost

# handing work on
rundesk roles <agent> resume <run>                                                                                                                                                                                      carry a finished role run on — the further task is read from standard input
rundesk roles <agent> run [--target <directory>] [--label <text>] [--provider <provider>] [--model <model>] <role>                                                                                                      hand one bounded task to a role — the brief is read from standard input
rundesk roles <agent> say <run>                                                                                                                                                                                         say something to a role that is working — read from standard input
rundesk roles <agent> show <run>                                                                                                                                                                                        one role run in full
rundesk roles <agent> stop <run>                                                                                                                                                                                        end a role run before it finishes

# rundesk itself
rundesk status                                                                                                                                                                                                          how rundesk itself is on this machine
rundesk version [--check]                                                                                                                                                                                               what is installed, and whether that is current
rundesk update [--check] [--status]                                                                                                                                                                                     move to the newest published release
rundesk env check <name>                                                                                                                                                                                                prove each can still be produced, without showing one
rundesk env set [--stdin] [--from <command>] <name>                                                                                                                                                                     keep a value under a name, or replace the one already there
rundesk env show <name>                                                                                                                                                                                                 one value: how it is kept, and what tells it apart
rundesk env unset <name>                                                                                                                                                                                                take one value away, and only that one
rundesk backups add                                                                                                                                                                                                     take a backup now
rundesk backups off                                                                                                                                                                                                     stop the machine taking one every day
rundesk backups on                                                                                                                                                                                                      have the machine take one every day
rundesk backups remove [--yes] <backup>                                                                                                                                                                                 delete one backup, and only that one
rundesk backups restore [--yes] <backup>                                                                                                                                                                                put a backup back, replacing everything this install keeps
rundesk uninstall [--purge]                                                                                                                                                                                             remove rundesk from this machine

# not yet grouped
rundesk config                                                                                                                                                                                                          how this install is configured, and where each value came from
rundesk messages [--most <n>] [--since <id>] [--channel <channel>] [--conversation <where>] [--author <kind>] [--who <identity>] [--source <how>] <agent>                                                               what was said, newest first
rundesk resume <agent>                                                                                                                                                                                                  carry one run on from where it stopped   [planned]
rundesk scripts [--where]                                                                                                                                                                                               the integration commands every agent can invoke
rundesk search [--most <n>] <agent> <words>                                                                                                                                                                             what was said, by the words in it
rundesk skills catalogs                                                                                                                                                                                                 the installed skill catalogs and their versions
rundesk skills grant <agent> <skill>                                                                                                                                                                                    give an agent one of the skills in the library
rundesk skills install [--confirm] <repository>                                                                                                                                                                         install every skill declared by a repository
rundesk skills remove [--yes] <catalog>                                                                                                                                                                                 remove an installed catalog and its skills
rundesk skills revoke <agent> <skill>                                                                                                                                                                                   take a skill away from an agent
rundesk skills update <catalog>                                                                                                                                                                                         move an installed catalog to its newer version
```

## What it looks like

Signatures say what is *allowed*. These say what it **is** — the three things an
owner makes, as they are actually typed.

**An agent**

```sh
# an agent called ava, answered by the codex this machine already has
rundesk add ava --provider codex
# change ava's default brain without replacing the agent
rundesk configure ava --provider claude
# one answered by a brain you wrote, told which model and how hard to think
rundesk add ava --provider /opt/my-brain --model fast-1 --set effort=high
# have the machine keep it running, and bring it back when it falls over
rundesk start ava
```

**A channel**

```sh
# reachable in direct messages and in every room it has been invited to
rundesk channels ava add discord --kind discord --allow 123456789012345678
#   writes two channels — discord-dms and discord-rooms — each with its own allowed list, settings and instructions
# direct messages only; --server <id> or --channel <id> narrows the rooms instead
rundesk channels ava add discord --kind discord --allow 123456789012345678 -- --dm
# what it is told about where it is, before it reads a word of the message
rundesk channels ava instructions discord-rooms "You are {agent} in {where.channel}. Others read this, so keep it short."
# what it is reachable on, and whether it is reachable at all
rundesk channels ava
```

**A value every program is given**

```sh
# typed here, not echoed, and never shown in full again by anything
rundesk env set GITHUB_TOKEN
# the words of the command are kept, and run again each time a program starts
rundesk env set OP_GITHUB --from 'op read op://work/github/token'
#   the value is never an argument — from a script, pipe it in instead
# what every program rundesk starts is given: a hint and a mark, never a value
rundesk env
# whether each can still be produced, without producing one for you to read
rundesk env check
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
# a script or command run once, at one moment, and never again
rundesk schedules ava add tidy-up --at "2026-07-28T09:00" -- /usr/local/bin/tidy
# the same one moment, asking a turn and saying what it came to on a surface
rundesk schedules ava add report --at "2026-07-28T09:00" --ask "how did the migration go?" --to ops
# the one-time schedules that are over — which ran, and which never did
rundesk schedules ava --expired
# keep it, and stop it running
rundesk schedules ava off nightly
```

**A role**

```sh
# the specialists ava can hand heavy work to, and the runs it has admitted
rundesk roles ava
# one bounded task, run in that project under the role's own rules
rundesk roles ava run development --target ~/code/exporter --label "csv export"
#   an agent hands work on from inside its own turn, and the brief arrives on standard input — the outcome, what it may do, and what done looks like
# one run: which role and revision, where it worked, and whether ava has reviewed it
rundesk roles ava show rol-3-vfs3
```

## What the arguments mean

```sh
--activity, --no-activity       show what the agent is doing and saying while it works; off means one message a turn, the answer (default: on)
--add <user>                    allow this person too — repeatable
--all                           every agent on this machine
--allow <user>                  who may reach this agent through it — at least one, always; repeatable
--ask <prompt>                  what to ask this agent when it is due, in quotes — a turn rather than a program
--at <moment>                   instead of --when: the one moment it runs, on this machine's own clock, as YYYY-MM-DDTHH:MM. It runs then and never again — a moment is given, never a phrase like 'tomorrow at nine'
--author <kind>                 only what this kind of author said — one of agent | rundesk | user
--channel <channel>             only what was said on this channel, by the name it was added under
--check                         say whether a newer release exists
--confirm                       install after reviewing what the repository declares
--conversation <conversation>   which conversation to carry on — this terminal's, when left out
--conversation <where>          only what was said in one place on it — the direct message or room, either as the WHERE column prints it or in the platform's own word alone
--expired                       instead, the one-time schedules whose moment has gone — whether each ran, or whether it passed while nothing was running
--force                         restart now even when doing so interrupts active work
--fresh                         start the conversation again rather than carrying it on
--from <command>                instead of keeping a value: the command that prints it, run again each time a program starts — the words of the command are kept, and what it printed never is
--here                          run it in this terminal instead of handing it to the machine
--in <where>                    which place on that channel to say it in, in that surface's own words — for Discord: a room name or id, or on a DM channel the person's user id (the same id as --allow) or the DM channel id. Left out, it follows the conversation
--instructions <text>           what every turn for this agent is told before it reads a prompt, where neither the schedule nor the surface said — empty takes it off
--kind <kind>                   which kind of surface — one that ships, or the path of a program that speaks yours
--label <text>                  a short safe name for the task, shown where other people can read it — never a path and never the brief
--model <model>                 which model, in that brain's own words
--most <n>                      how many to show, newest first (default: 20)
--provider <provider>           which brain answers for it when a turn does not say
--purge                         also take every agent's home, log and history
--read-only                     let this turn look at the machine without changing it
--remove <user>                 stop allowing this person — repeatable, and never the last one
--set <key=value>               anything that brain takes, carried to it unread; repeatable
--since <id>                    only what was said after this one, by the id shown beside it
--source <how>                  only messages belonging to work admitted this way — one of channel | role | schedule | terminal
--source <source>               whose lines to show — what the gateway wrote, or what the machine caught that never reached it — one of all | gateway | machine
--status                        show the last queued update and its final outcome
--stdin                         read the value from what is piped in rather than asking for it
--steer                         keep saying more to it while it works — a line at a time, until you stop
--target <directory>            the project directory the work happens in — the brain stands there, so the project's own instruction files load normally
--to <channel>                  which channel to say what this came to on, by the name it was added under — the account and `schedules` say it either way
--token-stdin                   read the credential this channel needs from standard input, one line; asked for at the terminal when left out
--when <cron>                   when it runs, over and over, as five cron fields — minute, hour, day, month, weekday
--where                         print the directory they are kept in, and nothing else
--who <identity>                only what this one person said, as the WHO column names them
--yes                           do not ask first — for a script, never for a person
-n, --lines <lines>             how many of the last lines to show, from each source
<agent>                         which agent — the name it was made under
<backup>                        which one, by the name it is listed under
<catalog>                       which catalog
<channel>                       what to call it, and what to name it by later
<name>                          what programs read it as — letters, digits and underscores, never beginning with a digit
<option>                        after `--`, whatever this kind of channel needs — carried to it exactly as typed, and never read here
<program>                       after `--`, the full path of what to start when it is due, and its arguments — a bare name is refused, because a gateway runs with almost no PATH
<prompt>                        what to ask it, in quotes
<repository>                    a GitHub repository URL, local directory or archive
<role>                          which role — one this install has, by its own name
<run>                           which role run — the id `roles` lists
<schedule>                      what to call it, and what to name it by later
<skill>                         which skill, by the name it is under
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
