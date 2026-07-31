---
title: Set up the Discord bot
description: Create the application, enable the one intent Rundesk needs, install it to your server, and connect it to an agent.
sidebar:
  order: 1
---

Rundesk gives each agent its own Discord bot connection. The bot answers direct messages,
works in server rooms, opens a thread when mentioned, shows live activity, and exposes Rundesk
controls as slash commands.

You need an agent such as `ava` ([make one first](/start/first-agent/)), a Discord account, a
server where you can install apps, and your own Discord user ID.

:::caution[The bot token is a password]
Never paste it into a command, commit it, or send it in a message. Rundesk asks for it without
echoing it and stores it in a file readable only by your account.
:::

## 1. Create the application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Select **New Application**, name it whatever the bot should be called, and **Create**.
3. Open **Bot** in the sidebar. Set the username and avatar if you want.
4. Under **Authorization Flow**, leave **Require OAuth2 Code Grant** off.

**Public Bot** controls who may install it. Leave it off for a private bot only you install.
Turn it on if you want to use Discord's provided install link, or let other server admins
install it.

## 2. Enable Message Content Intent

Still on the **Bot** page, under **Privileged Gateway Intents**, enable:

- **Message Content Intent**

Leave **Presence Intent** and **Server Members Intent** off. Rundesk does not request them — it
authorizes people by numeric Discord user ID and reads neither presence nor the member list.

This one is easy to skip and produces a confusing failure. Without it the bot still comes
online, and Discord still delivers direct messages and messages that mention it — but ordinary
room messages are withheld. So the first mention works and every unmentioned follow-up in the
bot's own thread looks ignored.

## 3. Copy the bot token

On the same page:

1. Select **Reset Token**.
2. Complete Discord's confirmation or two-factor prompt.
3. Copy it into a password manager until Rundesk asks for it.

Discord shows a token once. If it is lost or exposed, reset it before using the bot.

## 4. Install it to your server

Open **Installation** in the portal.

1. Enable **Guild Install** under **Installation Contexts**.
2. Select **Discord Provided Link** under **Install Link**.
3. Under **Default Install Settings** for Guild Install, add both scopes:
   - `bot`
   - `applications.commands`
4. Grant these permissions:

| Permission | Why Rundesk needs it |
|---|---|
| View Channels | See the rooms it was pointed at |
| Send Messages | Answer |
| Create Public Threads | Move a room conversation out of the main channel |
| Send Messages in Threads | Continue there |
| Read Message History | Follow a thread it did not start |
| Add Reactions | Mark work as seen, finished, stopped, or failed |
| Attach Files | Deliver long answers and files the agent made |

Copy the install link, open it, choose your server, and authorize. Installing a server app
needs **Manage Server**.

If you left **Public Bot** off, use **OAuth2 → URL Generator** instead: same two scopes, same
permissions, then open the generated URL signed in as the application owner.

Channel permission overrides still apply. For the bot to work in a private channel, give its
role these same permissions on that channel or its parent category.

## 5. Copy your Discord user ID

In the Discord client:

1. **User Settings → Advanced**, enable **Developer Mode**.
2. Right-click your own profile and **Copy User ID**.

Rundesk needs at least one allowed user and does not accept usernames. Developer Mode also adds
**Copy Server ID** and **Copy Channel ID**, which you only need if you are narrowing where the
bot listens.

## 6. Connect it to the agent

```sh
rundesk channels ava add discord \
  --kind discord \
  --allow <your-discord-user-id>
```

Rundesk asks for the token without showing it, signs in, checks what the bot can actually
reach, and only then saves the channel. A token that does not work is never written down.

That creates two channels from the one bot:

- `discord-dms` — direct messages
- `discord-rooms` — every server room the bot can see

Each keeps its own allowlist and its own instructions. Repeat `--allow` for each additional
person.

### Narrowing where it listens

Discord-specific options go after `--`, which is required:

```sh
# direct messages only
rundesk channels ava add discord --kind discord --allow <user-id> -- --dm

# every room in one server
rundesk channels ava add discord --kind discord --allow <user-id> -- --server <server-id>

# one room
rundesk channels ava add discord --kind discord --allow <user-id> -- --channel <channel-id>
```

`--server` and `--channel` narrow the *room* channel. Neither adds direct messages.

For an unattended setup, `--token-stdin` reads one token from standard input — feed it from a
secret manager, never from a literal token in shell history.

### Tell it how to behave in public

```sh
rundesk channels ava instructions discord-rooms \
  "You are {agent} in {where.channel}. Others can read this, so keep it concise."
```

## 7. Restart and test

A gateway reads its channels and their instructions **when it starts**, so a newly added
channel needs a restart:

```sh
rundesk restart ava     # or: rundesk start ava, if it is stopped
rundesk channels ava
```

:::note
`REACHABLE` in the channel listing means the agent's gateway is running. It does not prove the
Discord connection came up — test the surfaces to confirm that.
:::

Then check each surface you enabled:

- **Direct message the bot.** It answers in that conversation.
- **Mention it in a room.** It opens a thread and answers there; later messages inside that
  thread need no further mention.
- **Run `/status`.** Confirms slash commands arrived.

Rundesk also offers `/stop`, `/new`, `/restart`, `/version`, `/agents`, `/help`, and
`/provider`, where the channel's access rules allow them. Global slash commands can take up to
an hour to appear; a channel added with `--server` also gets a server-scoped copy, which
usually shows up sooner.

## When it does not work

### Online but ignoring messages

Enable **Message Content Intent** (step 2), save, and `rundesk restart ava`. In a room, the
first message must mention the bot — Rundesk deliberately ignores unmentioned room messages
until it has opened a thread.

### Adding the channel says it cannot reach Discord

Reset the token in the portal and run the add command again. Also make sure nothing else is
connected with the same token: **a second connection silently wins**, and neither side reports
an error, so running the adapter by hand while the gateway is serving that channel makes one of
them stop receiving.

### It cannot see or answer in one room

Check the bot role *and that room's permission overrides* for View Channels, Send Messages,
Create Public Threads, Send Messages in Threads, and Read Message History.

### Slash commands never appear

Confirm the app was installed with the `applications.commands` scope, restart the agent once,
then give Discord's global registration time to propagate.

### The bot is offline

```sh
rundesk doctor ava
rundesk logs ava --source machine
```

More in [when something breaks](/guides/troubleshooting/).

---

Next: [what an agent can do once it is on Discord](/guides/discord/).
