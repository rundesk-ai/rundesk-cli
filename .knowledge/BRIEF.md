# Brief — rundesk-cli

*The always-loaded briefing every agent reads first: the story of what we're building and why. One
screen, stable, PII-free.*

## Story

`rundesk` is the command line for a lightweight, provider-agnostic multi-agent gateway: a person runs a
small team of AI coding agents on their own machine and talks to them from a chat app. This repository is
the **standard-library Python rewrite of that command**, built from the outside in. Two layers are here:
this copy of rundesk on a machine, and the **gateway** — the long-lived process an agent will work inside,
one per name, kept up by the machine itself and owning every program it starts. The agents are not here
yet; the verbs that will reach them are registered and say so plainly until they land.

## Why it exists

The original command is TypeScript on Node, and Node was the only thing it made a user install: the agent
brains it drives are native binaries, so nothing else on the machine needed a runtime. Python is already on
every Mac, needs no build step and no package manager, which turns installing into downloading a file and
putting it on a PATH.

The rewrite goes outside in because each layer has to be trustworthy before the next can rest on it.
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
  version this install is on, and which has been published; the gateway — starting one, keeping it up,
  saying what it is doing, and ending everything it started when it goes; and the programs it runs, which
  are ended on silence rather than on a clock, because a session may legitimately take hours.
- **Out of scope:** agents, provider brains, chat channels, turns and transcripts. Those verbs are
  registered and answer "coming soon" until each is built. rundesk also does not supervise: keeping a
  gateway up is the machine's, and writing our own would be the largest thing here that nobody asked for.
  No dependencies, no build step, and no second way into the product besides this command.

## External Systems

- `GitHub Releases` — which version has been published, and the archive an update is fetched from.
- `python3` — the runtime, taken as already present on the machine rather than installed.
- `launchd` — what keeps a gateway running, brings it back when it falls over, and starts it again after
  a restart. rundesk writes the job and hands it over; it supervises nothing itself.

---
*Editing this file? Follow the standard first: [`guides/docs-brief.md`](./guides/docs-brief.md).*
