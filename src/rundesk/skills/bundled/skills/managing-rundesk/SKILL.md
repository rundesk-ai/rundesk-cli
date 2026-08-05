---
name: managing-rundesk
description: Operate and inspect the Rundesk install running this agent. Use for anything about this agent or another one, gateways starting and stopping, the values programs here are given, copies of what the owner keeps, the version this install is on, or where rundesk keeps something — and whenever somebody asks what rundesk can do, or something on this machine is not behaving and rundesk might be why. Use it before guessing at a path or a setting, even if nobody says the word "rundesk".
---

# Managing rundesk

Rundesk is the thing running you: your name, the directory you start in, the gateway that keeps you
alive, and the values handed to every program started here.

**A question about this install is a `rundesk` command, not a guess.** You have a shell and the same
access your owner does. `rundesk --help` is generated from the command itself and cannot be out of
date — where anything here disagrees with it, the command is right. Nothing else on this machine is
rundesk, whatever it calls its own jobs.

## Never do these

- **Never stop or restart your own gateway.** It is the process your turn is running inside, so you
  stop mid-sentence and nothing you were saying arrives. Give your owner the command instead.
- **Never remove an agent, and never uninstall rundesk**, unless asked for that exact thing by name.
- **Never ask anybody to send you a credential.** Not in a room, not in a message. Anything said to
  you is in the record and may be in somebody's chat app besides — a token pasted to you is a token
  that has just been published. Send your owner the command to type at their own terminal:
  `rundesk env set <NAME>`.
- **Never put a copy back unless asked for that exact copy.** `rundesk backups restore` replaces
  everything rundesk keeps, and any agent made since that copy goes away. One of them may be you.

## What there is

Every one of these lists when given nothing, and every one of them prints where it is working.

| Ask about | Command |
|---|---|
| This install: its version, where it keeps things, whether it is fit to run | `rundesk status` |
| Whether it is out of date | `rundesk version` |
| What it is configured with, and changing that | `rundesk configure` |
| The agents here, and what is behind each | `rundesk agents` |
| Whether an agent's gateway is up, and what it has been doing | `rundesk gateways` · `rundesk gateways logs <agent>` |
| The values every program started here is given | `rundesk env` |
| Copies of everything the owner keeps | `rundesk backups` |
| The skills this install has, and which agent holds which | `rundesk skills` |
| Whether a skill an agent holds can actually be used | `rundesk skills doctor` |

**A verb rundesk does not have is a verb rundesk cannot do.** There is no "coming soon" and no flag
that turns one on. If something you want is not in `rundesk --help`, say so plainly rather than
inventing a command that fails.

## Credentials

- **`rundesk env` never shows a value — to anyone, you included.** A few characters at each end and
  a fixed mark between them is how you tell one value from another. Asked what one *is*, the honest
  answer is that nothing on this machine can say, and there is no flag for it.
- **Before saying an integration is broken, run `rundesk env check <NAME>`.** "Cannot be read" and
  "was never set" are different answers with different fixes, and it says which. Never replace a
  credential on the strength of a program's own error message.
- **A value placed now reaches your *next* turn, not this one.** Your environment was built when
  this turn started, and nothing can change a running program's.
- **`rundesk skills doctor` is the fastest way to find out why a skill is not working.** It says
  which value is missing, which account it belongs to, and the one command that fixes it — and it
  exits non-zero when anything is wrong, so it can be run from a script.

## Gotchas

- **Almost every command takes an agent's name, and it is usually your own.** Given somebody else's,
  it answers about them; given none, it answers about all of them.
- **Never write a path down.** An install can be pointed anywhere, so a path that is true here is
  wrong on the next machine. `rundesk status` says where this one keeps things, and every listing
  prints the directory it is reading.
- **`rundesk update` may refuse while a gateway is running**, and that is correct rather than a
  fault: an agent's records cannot be carried forward while something has them open. It names the
  agent, and stopping that gateway and running it again finishes the job.
- **An empty answer and a refusal are different.** A listing that found nothing exits zero and says
  so in words; something that could not be done exits non-zero and says what it left behind. Read
  which one you got before reporting it.
- **What you changed goes to your gateway's log**, not to this conversation. `rundesk gateways logs
  <you>` is where to look for what actually happened.
