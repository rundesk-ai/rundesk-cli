---
name: managing-rundesk
description: Operate and inspect the Rundesk installation running this agent. Use for agent history, runs and costs, logs, channels, configuration, skills, catalogs, backups, agent lifecycle, or changes to how an agent runs — and whenever somebody refers to work this agent has no memory of. Use the dedicated schedule or role skill for those domains.
---

# Managing rundesk

Rundesk is the thing running you: your name, the record of everything you have been asked and
answered, the channels people reach you on, the schedules that start you.

**A question about you is a `rundesk` command, not a guess.** You have a shell and the same
access your owner does. `rundesk --help` is generated from the command and cannot be out of
date — where anything here disagrees with it, the command is right. Nothing else on this
machine is rundesk, whatever it calls its schedules or jobs.

## Never do these to yourself

- **Never stop or restart your own agent.** It stands down the gateway your turn runs inside —
  you stop mid-sentence. Give your owner the command instead.
- **Never remove an agent or uninstall rundesk** unless asked for that exact thing.
- **Never put a backup back unless asked for that exact copy.** A restore replaces everything,
  and agents made since that copy go away — one of them may be you.
- **`rundesk update` refuses while you are running.** Correct, not a fault.

## What you can manage

These list. **Read the reference before changing anything in that area.**

| Area | Start here | Deeper |
|---|---|---|
| What was said, what you did, what it cost | `messages` · `runs` · `usage` | `references/where-you-are.md` |
| Agents, gateways, channels, the install, skills | `agents` · `doctor` · `channels` · `status` · `config` · `skills` | `references/operating.md` |
| Your gateway's own account | `logs <you>` | `references/operating.md` |
| Copies of everything your owner keeps | `backups` | `references/backups.md` |

Three are a job rather than a listing and have a skill each: **`managing-schedules`**,
**`delegating-to-roles`**, **`writing-skills`**. Not given one? Say so.

## Work you cannot remember

You start fresh every session. Anything said in another conversation, on another day, or in a
different DM is in the record and not in your memory — and you will not feel the gap. Look it
up rather than saying you do not recall:

```sh
rundesk messages <you> --conversation <where>   this room alone. Start here
rundesk messages <you> --source schedule        what the clock started
```

Narrow before you widen. **`messages` first** — `runs` is ids and costs, and cannot answer
"what work?". Say that you looked it up rather than implying you remembered.

## Gotchas

- **Every command takes a name and it is almost always your own.** Without one, or with
  somebody else's, it answers about them.
- **Two direct messages are two conversations**, separate on purpose. Never carry one into the
  other without saying where it came from.
- **An empty answer is not the same as an impossible one.** `search` needs an SQLite feature
  not on every machine; it says `SEARCHING UNAVAILABLE` rather than returning nothing.
- **A schedule is the owner's clock, not your queue.** Never add one to move your own work out
  of the turn you are in — background work is a role.
- **Never write a path down.** Ask: `rundesk skills --where`, `rundesk backups --where`.
- **What you changed goes to your log**, not to this conversation.
