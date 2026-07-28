---
title: Put an agent on Discord
description: Reach an agent from your phone, with per-channel allowlists and separate instructions for public rooms.
sidebar:
  order: 1
---

Discord is the shipped first-class channel adapter. One command puts an agent there.

```sh
rundesk channels ava add discord --kind discord --allow <your-discord-user-id>
```

The command asks for the bot token securely when it needs one, **proves the connection before
saving anything**, and creates separate `discord-dms` and `discord-rooms` channels by default.
You can narrow it instead to direct messages only, to one server, or to one channel.

## What works on Discord

- Direct messages and server rooms
- A dedicated thread when the agent is mentioned in a room
- Explicit per-channel user allowlists
- Typing indicators, state reactions, and optional live activity
- Long answers and generated files delivered as attachments
- Inbound message attachments
- Stopping or forgetting a conversation from chat

## Public rooms need different instructions

The separate `discord-dms` and `discord-rooms` channels exist so an agent can behave
differently where other people are reading.

```sh
rundesk channels ava instructions discord-rooms \
  "You are {agent} in {where.channel}. Others can read this, so keep it concise."
```

Channel instructions keep public-room behavior separate from private conversation. An agent
that is chatty in your DMs should not be chatty in a shared room.

## Changing the provider from chat

On a **single-user** channel, that user can run `/provider <provider>` to change the
agent-wide default. Rundesk validates the adapter first, keeps any turn already running on its
original provider, and starts the next message in that Discord conversation fresh.

Shared channels cannot change an agent-wide default — one person in a room should not be able
to re-brain a teammate everybody else is using.

## Access control is Rundesk's, not the platform's

Allowlists are explicit and per-channel. The channel adapter owns the vocabulary and behavior
of Discord; Rundesk owns who is allowed to talk to the agent, the turn state, the history, and
the delivery. That division is what makes a [custom channel](/extend/channel-adapters/) safe
to write.
