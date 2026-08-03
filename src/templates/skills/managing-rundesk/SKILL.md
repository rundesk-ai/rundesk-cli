---
name: managing-rundesk
description: Operate and inspect the Rundesk installation running this agent. Use for agent history, runs and costs, logs, channels, configuration, skills, catalogs, backups, agent lifecycle, or changes to how an agent runs — and whenever somebody refers to work this agent has no memory of. Use for writing or changing a role definition too, including what a new specialist is for and what its rules say. Use the dedicated schedule skill for schedules, and the role skill for handing work over.
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
- **Never ask anybody to send you a credential.** Not in a room, not in a DM. Anything said to
  you is in the record for ever and may be in a chat app besides — a token pasted to you is a
  token you have just published. Send your owner the command to type at their own terminal:
  `rundesk env set <NAME>`. Placing one yourself is for a value **you** minted, never one a
  person typed at you.
- **Never put a backup back unless asked for that exact copy.** A restore replaces everything,
  and agents made since that copy go away — one of them may be you.
- **`rundesk update` refuses while you are running.** Correct, not a fault.

## What you can manage

These list. **Read the reference before changing anything in that area.**

| Area | Start here | Deeper |
|---|---|---|
| What was said, what you did, what it cost | `messages` · `runs` · `usage` | `references/where-you-are.md` |
| Agents, gateways, channels, the install, skills | `agents` · `doctor` · `channels` · `status` · `config` · `skills` | `references/operating.md` |
| The values every program here is given | `env` · `env check <NAME>` | `references/operating.md` |
| Your gateway's own account | `logs <you>` | `references/operating.md` |
| Copies of everything your owner keeps | `backups` | `references/backups.md` |
| The specialists work is handed to | `roles <you>` | `references/writing-a-role.md` |

Three are a job rather than a listing and have a skill each: **`managing-schedules`**,
**`delegating-to-roles`**, **`writing-skills`**. Not given one? Say so.

**Writing or changing a role is here, not in `delegating-to-roles`** — that one hands work to a
role that exists. Read `references/writing-a-role.md` before creating or editing one; no command
makes a role, and a manifest field nobody reads is refused rather than ignored.

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
- **You may place less than your owner can, and that is on purpose.** From a turn, `env set`
  keeps only a name plainly shaped like a credential — ending `_TOKEN`, `_API_KEY`, `_KEY`,
  `_SECRET`, `_PASSWORD`, `_PASSPHRASE`, `_CREDENTIAL`, `_CREDENTIALS` or `_AUTH`. Anything
  else is refused and is your owner's to place at their own terminal. **It is a guard on the
  ordinary path and not a boundary** — it reads `RUNDESK_RUN` out of your own environment, so
  a shell that clears that variable places anything, and `env show` then records the change
  as having been made at your owner's own terminal, which falsifies the one account there is
  of who made it. Do not work around it that way or by renaming the thing; send them the
  command instead.
- **`rundesk env` never shows a value — to anyone, you included.** The last few characters and
  a mark are how you tell one from another. Asked what one *is*, the answer is that nothing on
  this machine can say, and there is no flag for it. Two names showing one mark hold one value.
- **Before saying an integration command is broken, run `rundesk env check <NAME>`.** A value
  fetched by a command can be there one hour and unreachable the next, and "could not answer"
  is not the same as "there is no value" — never replace a credential on the strength of it.
- **A value placed now reaches your *next* turn, not this one.** Your environment was built
  when this turn started, and nothing can change a running program's.
- **Never write a path down.** Ask: `rundesk skills --where`, `rundesk backups --where`,
  `rundesk env --where`.
- **What you changed goes to your log**, not to this conversation.
