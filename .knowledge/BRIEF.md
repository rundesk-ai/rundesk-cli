# Brief — rundesk-cli

*The always-loaded briefing every agent reads first: the story of what we're building and why. One
screen, stable, PII-free.*

## Story

`rundesk` is the command line for a lightweight, provider-agnostic multi-agent gateway: a person runs a
small team of AI coding agents on their own machine and talks to them from a chat app. It is **standard
library Python** — already on every Mac, no build step, no package manager — so installing it is
downloading a file and putting it on a PATH.

**This repository is being rebuilt.** A first build reached a working product and, in doing so, learned
what the shape should have been; it is readable in this branch's history and is not the thing being
extended. The rebuild goes one part at a time, outside in, and each part is finished — proven by a
contract and its tests — before the next begins. Until a part lands, its operations are **registered on
the command and refuse honestly**, so the command never claims a capability it does not have.

## Why it exists

Every layer has to be trustworthy before the next can rest on it, and the first build proved which layer
that starts at. It is not the agents: it is **where things are on disk**. The replaced build resolved its
locations from a dozen independent environment variables, each with its own default under the owner's
home, so redirecting eleven of them still wrote into the live install — which it did, repeatedly, while
reporting success. The rebuild has **one root and everything derived downward from it**, so isolating a
run is one decision rather than twelve, and a partial redirect is not expressible.

The order after that is the order a person meets the product in: getting it onto a machine, knowing which
version it is and moving to a newer one, and taking it off again. Then the agent, the gateway that keeps
it up, the brain it reaches, and the surfaces it is reached from.

## Users / ICP

- A single technical owner, self-hosting on their own macOS machine, who wants their agents reachable and
  their tooling legible enough to maintain themselves — and who should never have to install a runtime, a
  package manager or a build step to get started.

## Scope

- **Built, or being built now:** the command surface and how it describes itself; where an install keeps
  everything, resolved from one root; which version this install is and which has been published; moving
  between them; and taking rundesk off a machine, keeping what the owner made unless asked to take it.
- **Registered and refusing, until its part is built:** the agent — making one, seeing what you have, and
  taking it away with everything that was its own; the gateway that runs it; schedules, which turn a
  stated time into work a gateway starts and owns; skills, installed from catalogs into a shared library
  and granted per agent; the channels an agent is reached on; the values every program it starts is given;
  copies of what the owner keeps; and reading back what an agent has been asked and has answered.
- **Out of scope:** supervising anything itself — keeping a gateway up is the machine's job, and writing
  our own supervisor would be the largest thing here nobody asked for. No dependencies unless something
  genuinely cannot be done without one, no build step, and no second way into the product besides this
  command.

## External Systems

- `GitHub Releases` — which version has been published, and the archive an update is fetched from.
- `python3` — the runtime, taken as already present on the machine rather than installed.
- `launchd` — what will keep a gateway running once gateways are rebuilt. rundesk writes the job and hands
  it over; it supervises nothing itself.

---
*Editing this file? Follow the standard first: [`guides/docs-brief.md`](./guides/docs-brief.md).*
