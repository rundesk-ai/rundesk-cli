---
title: Channel adapters
description: Reach a Rundesk agent from a surface it does not already support.
sidebar:
  order: 2
---

A channel adapter makes an agent reachable somewhere new — Slack, SMS, a webhook, a device on
your desk. Like a provider adapter, it is **an executable** rather than code Rundesk loads.

## The division of labour

This is the part worth understanding before you write anything:

| The adapter owns | Rundesk owns |
|---|---|
| The vocabulary and behavior of the platform | Access control |
| Connecting, and staying connected | Turn state |
| Rendering a reply the way that platform expects | History |
| Platform-specific affordances — threads, reactions, attachments | Delivery |

You are not implementing authorization, conversation state, or the record of what was said.
Rundesk decides who is allowed to talk to the agent and what happens to the answer. The
adapter translates.

A custom channel gets the same agent and turn lifecycle as the shipped Discord adapter
without changing Rundesk core.

## The failure mode to expect

An adapter that connects but never answers is the common one, and it is almost always the
inbound record shape rather than the connection. The contract spells out the records each
way:

→ **[The channel adapter contract](https://github.com/rundesk-ai/rundesk-cli/blob/main/src/templates/skills/building-a-channel-adapter/references/the-contract.md)**

If you are working with a Rundesk agent, grant it the `building-a-channel-adapter` skill.

## Seeing a shipped one first

Discord is the reference implementation and worth reading before writing your own — it
exercises threads, allowlists, reactions, live activity, attachments in both directions, and
per-channel instructions. See [Put an agent on Discord](/guides/discord/).
