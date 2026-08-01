# Brief — rundesk-cli

*The always-loaded briefing every agent reads first: the story of what we're building and why. One
screen, stable, PII-free.*

## Story

`rundesk` is the command line for a lightweight, provider-agnostic multi-agent gateway: a person runs a
small team of AI coding agents on their own machine and talks to them from a chat app. It is **standard
library Python**, and it is built from the outside in. Five layers are here: this copy of rundesk on a
machine; the **agent** — the named identity work is run for, with a home of rules, memory and workspace it
loads, and everything of its own in one directory; the **gateway** — the long-lived process an agent works
inside, one per agent, kept up by the machine itself and owning every program it starts; **schedules**,
which turn a stated time into work that gateway starts and owns like any other; and the **brain** an agent
reaches, through a seam that is a program rundesk runs rather than code it loads — so one nobody here has
heard of is first class, and every turn leaves an account of what it did, what its brain said and what it
cost; and the **surfaces** an agent is reached *from*, through a seam of exactly the same shape — a
program rundesk runs rather than code it loads — so a chat app nobody here has heard of is one more
program rather than a change to any of this. Discord is the first, and its gateway is held open by the
agent's own for as long as it is up.

## Why it exists

The agent brains rundesk drives are native binaries, so nothing on the machine needs a runtime of its own.
Python is already on every Mac, needs no build step and no package manager, which turns installing into
downloading a file and putting it on a PATH — no toolchain, and nothing for a person to set up first.

Building goes outside in because each layer has to be trustworthy before the next can rest on it.
Install, update and uninstall came first: that is what a person meets. The gateway came next, because an
agent is a program that runs for hours and spawns programs of its own — so what owns it, what ends it, and
what happens when the machine takes it away have to be settled before there is anything to own. rundesk
supervises nothing itself; it hands that to what the machine already has.

## Users / ICP

- A single technical owner, self-hosting on their own macOS machine, who wants their agents reachable and
  their tooling legible enough to maintain themselves — and who should never have to install a runtime, a
  package manager or a build step to get started.

## Scope

- **Active areas:** the command surface and how it describes itself; install, update and uninstall; which
  version this install is on, and which has been published; versioned skill catalogs installed from
  repositories into the shared library, with grants still decided per agent; the agent — making one, seeing what you have,
  saying what stands between it and a working turn, and taking it away with everything that was its own;
  the gateway that runs it — starting one, keeping it up, saying what it is doing, and ending everything it
  started when it goes; the programs it runs, which are
  ended on silence rather than on a clock, because a session may legitimately take hours, and which are
  read either as words for a person or as whole records for something that parses them — that second kind
  being written back to while it runs, which is how an agent brain is reached; schedules,
  which are per gateway so that an agent's are its own, are never run late and never overlap; **the seam a
  brain is reached through** — a program rundesk runs rather than code it loads, so a brain nobody here has
  heard of is reached exactly as one that ships is; **one turn**, asked for from this terminal and streamed
  back to it, carried on where it left off and steered while it runs; **the account a turn leaves** —
  what it did, what its brain actually said, and what it cost; and **the seam a surface is reached
  through**, the mirror of the first — putting an agent on a channel, proving it before writing anything
  down, holding it open inside the agent's gateway, deciding there and only there what state a turn is in,
  and carrying what arrives on it through to an answer; and **the specialist an agent hands heavy work
  to** — a shared role definition, one isolated execution of it that never carries the agent's
  identity, memory or operational rules, and exactly one report the named agent reviews before anybody
  else hears about it.
- **Out of scope:** reading a run back from the command line. Those operations are registered and answer
  "coming soon" until built — what each run became and cost, said in a listing rather than read off the
  account itself. Nothing here claims a provider loaded a rule, works a cost out from prices, or asks a
  brain what its plan has left. Approvals and a brain's own questions are a later phase; stopping a turn
  and starting a conversation again are gestures at the conversation and are here.
  rundesk also does not supervise: keeping a gateway up is the machine's, and writing our own would be
  the largest thing here that nobody asked for. No dependencies, no build step, and no second way into
  the product besides this command.

## External Systems

- `GitHub Releases` — which version has been published, and the archive an update is fetched from.
- `GitHub repositories` — public skill catalogs fetched by repository URL and tracked by their declared version.
- `python3` — the runtime, taken as already present on the machine rather than installed.
- `launchd` — what keeps a gateway running, brings it back when it falls over, and starts it again after
  a restart. rundesk writes the job and hands it over; it supervises nothing itself.

---
*Editing this file? Follow the standard first: [`guides/docs-brief.md`](./guides/docs-brief.md).*
