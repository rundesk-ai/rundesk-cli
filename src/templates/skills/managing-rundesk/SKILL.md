---
name: managing-rundesk
description: Operate and inspect the Rundesk installation running this agent. Use for agent history, runs and costs, logs, channels, configuration, skills, catalogs, backups, agent lifecycle, or changes to how an agent runs — and whenever somebody refers to work this agent has no memory of. Use the dedicated schedule or role skill for those domains.
---

# Managing rundesk

Rundesk is the thing running you. It gave you your name, it holds the record of everything you
have been asked and answered, it keeps the channels people reach you on, and it fires the
schedules that start you when nobody is watching.

**When a question is about you — what you did, what you are scheduled to do, where you can be
reached, what you have cost — the answer is a `rundesk` command, not a guess and not another
tool.** You have a shell. An agent that says "I don't have access to that" about its own
history is simply wrong: it has the same access its owner does.

**Nothing else on this machine is rundesk.** Other tools offer things called schedules, tasks
or jobs, and one may even carry the name. None of those runs you. `rundesk --help` is generated
from the command itself and cannot be out of date — **where anything here disagrees with the
command, the command is right.**

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

## What you can manage

One row per area: the command that opens it, and where the detail is. The commands here only
*list*. **Read the reference before changing anything in that area.**

| Area | Start here | Go deeper |
|---|---|---|
| What was said, and what you did | `rundesk messages <you>` · `rundesk runs <you>` | `references/where-you-are.md` |
| What it cost | `rundesk usage <you>` | `references/where-you-are.md` |
| Agents, and the gateways that run them | `rundesk agents` · `rundesk doctor <name>` | `references/operating.md` |
| Where you can be reached | `rundesk channels <you>` | `references/operating.md` |
| What this install is and holds | `rundesk status` · `rundesk config` · `rundesk skills` | `references/operating.md` |
| What your gateway has been saying | `rundesk logs <you>` | `references/operating.md` |
| Copies of everything your owner keeps | `rundesk backups` | `references/backups.md` |

Three areas are a job rather than a listing, and have a skill each. Reach for the skill rather
than working the commands out:

- **`managing-schedules`** — what starts you when nobody is watching.
- **`delegating-to-roles`** — handing heavy work to a specialist, and reviewing what comes back.
- **`writing-skills`** — writing one.

Not given one? Say so. `rundesk skills grant <you> <name>` is the line your owner types.

## Finding work you cannot remember

You start every session fresh. Everything said in another conversation, on another day, or in a
different direct message is in the record and **not** in your memory. You will not feel the gap
— you will simply have no idea what somebody is referring to. So look it up rather than saying
you do not recall:

```sh
rundesk messages <you> --conversation <where>   this room or DM alone. Start here
rundesk messages <you> --source schedule        only what the clock started
rundesk messages <you> --since <id>             only what is new since you last looked
```

**Narrow before you widen.** Whatever somebody means is nearly always in the place you are
standing or in what the clock did overnight.

**`messages` first, always.** `runs` is a listing of ids, times and costs — it says *that* work
happened and never *what was said*, so on its own it cannot answer "what work?".

**Say that you looked it up**, rather than implying you remembered. If nothing is there, say so
plainly. `references/where-you-are.md` covers naming a conversation, and what to do when the
name you were given matches nothing.

## Gotchas

- **Every command takes a name, and it is almost always your own.** One run without a name, or
  with somebody else's, answers about them.
- **Two direct messages are two conversations**, each with its own memory, told apart by the
  place. Never carry what one person told you into another's without saying where it came from.
- **An empty answer and an impossible question are not the same thing.** `search` needs a
  feature of SQLite that is not on every machine; where it is missing it says
  `SEARCHING UNAVAILABLE` rather than returning nothing. Use `runs` instead when you see that.
- **A schedule that names you runs a whole turn**, with its own conversation and its own memory.
  Work you did on one is not in front of you now.
- **A schedule is the owner's clock, not your queue.** It exists to put something in front of
  them at a moment they chose. Never add one to move your own work out of the turn you are in,
  to finish something later, or because a turn is getting long — work you want carried on in the
  background is a role, and the clock is not it.
- **Never write a path down.** An install can be pointed anywhere; ask instead —
  `rundesk skills --where`, `rundesk backups --where`.
- **What you changed goes to your log, not to this conversation.** `rundesk logs <you>` is where
  an owner reads back what you did to their install.
