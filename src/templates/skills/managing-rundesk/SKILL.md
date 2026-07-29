---
name: managing-rundesk
description: How to operate rundesk — the thing running you — including your own history, your agents, the channels you are reached on, what runs have cost, and the handful of commands that would end your own turn. Use whenever a question is about you or this install rather than about the work: what you did, where you can be reached, what something cost, how an agent is made or configured, or when anyone asks you to change how you are running. Schedules and backups have skills of their own.
---

# Managing rundesk

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

Rundesk is the thing running you. It gave you your name, it holds the record of everything you
have been asked and answered, it keeps the channels people reach you on, and it fires the
schedules that start you when nobody is watching.

**When a question is about you — what you did, what you are scheduled to do, where you can be
reached, what you have cost — the answer is a `rundesk` command, not a guess and not another
tool.** You have a shell. An agent that says "I don't have access to that" about its own
history is simply wrong: it has the same access its owner does.

**Nothing else on this machine is rundesk.** Other tools offer things called schedules, tasks
or jobs, and one may even carry the name. None of those runs you. `rundesk --help` lists
everything that is rundesk and nothing that is not.

## Never do these to yourself

Each one ends your own turn or somebody else's work.

- **Never stop or restart your own agent.** `rundesk stop <your own name>` stands down the
  gateway your turn is running inside — you stop mid-sentence and what you were saying never
  arrives. Asked to restart yourself, give your owner the command instead of running it.
- **Never remove an agent or uninstall rundesk** unless you were asked for that exact thing.
  Both are destructive and neither can be undone.
- **Never put a backup back unless you were asked for that exact copy.** A restore replaces
  everything your owner keeps, not only the part that looks wrong — agents made since that copy
  go away, and one of them may be you.
- **`rundesk update` refuses while you are running.** Your turn is work in flight and an update
  refuses rather than interrupting it. That is correct, not a fault.

## What to reach for

```sh
rundesk messages <you>              what was actually said, newest first — start here
rundesk runs <you>                  every run: what started it, how it ended, what it cost
rundesk schedules <you>             what starts you when nobody is watching
rundesk channels <you>              where you can be reached
rundesk usage <you>                 what your turns have cost
rundesk logs <you>                  what your gateway has been saying, when something failed
rundesk skills                      every skill here, and which you were given
rundesk config                      how this install is configured, and what defaulted
```

**Two of these have a skill of their own.** `managing-rundesk-schedules` is what an agent runs
on its own and what a schedule is *for*; `managing-rundesk-backups` is copies and what putting
one back really does. Reach for those rather than working either out from the commands, and if
you were not given one, say so — `rundesk skills grant <you> <name>` is the line your owner
types.

For the exact arguments, ask the command — `rundesk <verb> --help` is generated from the
command itself and cannot be out of date. **Where anything disagrees with the command, the
command is right.**

## Finding work you cannot remember

Your memory is per conversation; rundesk's record is not. Work you did on a schedule at 06:00,
or in a different direct message, is in the record and **not** in your memory here. You will not
feel the gap — you will simply have no idea what somebody is referring to.

So when a message refers to something you cannot place, look it up:

```sh
rundesk messages <you> --conversation <where>   this room or DM alone. Start here
rundesk messages <you> --source schedule        only what the clock started
rundesk messages <you> --since <id>             only what is new since you last looked
```

**Narrow before you widen.** Whatever somebody means is nearly always in the place you are
standing or in what the clock did overnight.

**`messages` first, always.** `runs` is a listing of ids, times and costs — it says *that* work
happened and never *what was said*, so on its own it cannot answer "what work?".

**Say that you looked it up**, rather than implying you remembered. And if nothing is there,
say that plainly.

## Gotchas

**Two direct messages are two conversations**, each with its own memory, told apart by the
place. Never carry what one person told you into another's conversation without saying where it
came from — they are separate on purpose.

**An empty answer and an impossible question are not the same thing.** `search` needs a feature
of SQLite that is not on every machine; where it is missing it says `SEARCHING UNAVAILABLE`
rather than returning nothing. Use `runs` instead when you see that.

**A schedule that names you runs a whole turn**, with its own conversation and its own memory.
Work you did on one is not in front of you now.

**A schedule is the owner's clock, not your queue.** It exists to put something in front of them
at a moment they chose — a reminder, a check, a report they asked for. Never add one to move your
own work out of the turn you are in, to finish something later, or because a turn is getting
long: work you want done in the background is your own delegation, and the clock is not it.
`managing-rundesk-schedules` is the rest of it.

## The rest

[`references/the-manual.md`](./references/the-manual.md) is everything else rundesk does,
written for an agent rather than for a person. Read it when you are asked to do something with
rundesk that is not on the list above — managing schedules and channels, understanding what a
run recorded, or working out why something is not there.
