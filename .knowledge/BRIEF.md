# Brief — rundesk-cli

*The always-loaded briefing every agent reads first: the story of what we're building and why. One
screen, stable, PII-free.*

## Story

`rundesk` is the command line for a lightweight, provider-agnostic multi-agent gateway: a person runs a
small team of AI coding agents on their own machine and talks to them from a chat app. This repository is
the **standard-library Python rewrite of that command**, started from the install lifecycle outward. The
gateway itself — agents, brains, channels, turns — is not here yet; every verb it will have is registered
and says so plainly until it lands.

## Why it exists

The original command is TypeScript on Node, and Node was the only thing it made a user install: the agent
brains it drives are native binaries, so nothing else on the machine needed a runtime. Python is already on
every Mac, needs no build step and no package manager, which turns installing into downloading a file and
putting it on a PATH. The rewrite starts at install, update and uninstall because that is what a user meets
first, and what has to be trustworthy before anything built on top of it can be.

## Users / ICP

- A single technical owner, self-hosting on their own macOS machine, who wants their agents reachable and
  their tooling legible enough to maintain themselves — and who should never have to install a runtime, a
  package manager or a build step to get started.

## Scope

- **Active areas:** the command surface and how it describes itself; install, update and uninstall; which
  version this install is on, and which has been published.
- **Out of scope:** everything the gateway does — agents, provider brains, chat channels, turns,
  transcripts, supervision. Those verbs are registered and answer "coming soon" until each is built. No
  dependencies, no build step, and no second way into the product besides this command.

## External Systems

- `GitHub Releases` — which version has been published, and the archive an update is fetched from.
- `python3` — the runtime, taken as already present on the machine rather than installed.

---
*Editing this file? Follow the standard first: [`guides/docs-brief.md`](./guides/docs-brief.md).*
