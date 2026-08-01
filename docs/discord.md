# Set up a Discord bot

Rundesk gives each agent its own Discord bot connection. The bot can answer direct
messages, work in server channels, open a thread when mentioned, show live activity,
and expose Rundesk controls as slash commands.

You need:

- a Rundesk agent, such as `ava`;
- a Discord account;
- a Discord server where you can install apps; and
- your Discord user ID.

The bot token is a password. Never paste it into a command, commit it, or send it in a
message. Rundesk asks for it without echoing it and stores it in a file readable only by
your account.

## 1. Create the application and bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Select **New Application**, give the application the name you want the bot to use,
   and select **Create**.
3. Open **Bot** in the sidebar. Customize the bot's username and avatar if wanted.
4. Under **Authorization Flow**, leave **Require OAuth2 Code Grant** off.

Rundesk never edits the bot's username, avatar, or account profile. Those remain under
the bot owner's control in Discord.

**Public Bot** controls who may install the bot. It can stay off for a private bot that
only the application owner or team installs. Turn it on if you want to use Discord's
provided install link or let other server administrators install it.

## 2. Enable the gateway intent

On the **Bot** page, find **Privileged Gateway Intents** and enable:

- **Message Content Intent**

Leave **Presence Intent** and **Server Members Intent** off. Rundesk does not request
them: it authorizes people by their numeric Discord user IDs and does not read presence
or the server member list.

Without Message Content Intent the bot can come online, and Discord still exposes direct
messages and server messages that mention it. Ordinary server messages are withheld,
though, so the first mention can work while every unmentioned follow-up in the bot's
thread appears to be ignored.

## 3. Copy the bot token

Still on the **Bot** page:

1. Select **Reset Token**.
2. Complete Discord's confirmation or two-factor prompt.
3. Copy the token and keep it in a password manager until Rundesk asks for it.

Discord shows the token once. If it is lost or exposed, reset it before using the bot.

## 4. Configure the install link

Open **Installation** in the Developer Portal.

1. Enable **Guild Install** under **Installation Contexts**.
2. Select **Discord Provided Link** under **Install Link**.
3. Under **Default Install Settings** for Guild Install, add these scopes:
   - `bot`
   - `applications.commands`
4. Grant the bot these permissions:
   - **View Channels**
   - **Send Messages**
   - **Create Public Threads**
   - **Send Messages in Threads**
   - **Read Message History**
   - **Add Reactions**
   - **Attach Files**

Those permissions match Rundesk's behavior. Thread permissions let an agent move a
server conversation out of the main channel; reactions show when work is seen, finished,
stopped, or failed; and Attach Files carries long answers and files the agent made.

Copy the install link, open it, choose your server, and authorize the app. Installing a
server app requires **Manage Server** permission.

If you keep **Public Bot** off, use **OAuth2** → **URL Generator** instead. Select the same
two scopes and permissions, then open the generated URL while signed in as the
application owner or a member of its team.

Channel permission overrides still apply. If the bot should work in a private channel,
give its role the same permissions in that channel or its parent category.

## 5. Copy your Discord IDs

In the Discord client:

1. Open **User Settings** → **Advanced**.
2. Enable **Developer Mode**.
3. Right-click your profile and select **Copy User ID**.

Rundesk requires at least one allowed user and does not accept usernames. Repeat
`--allow` for each additional person who may reach the agent.

Developer Mode also adds **Copy Server ID** and **Copy Channel ID** to server and channel
menus. You only need those IDs when narrowing where the bot listens.

## 6. Add Discord to the agent

Run:

```sh
rundesk channels ava add discord \
  --kind discord \
  --allow <your-discord-user-id>
```

Rundesk asks for the bot token without showing it, signs in, verifies what the bot can
reach, and only then saves the channel. The default command creates:

- `discord-dms` for direct messages; and
- `discord-rooms` for every server room the bot can see.

Each channel has its own allowlist and instructions even though both use the same bot.

To listen in direct messages only:

```sh
rundesk channels ava add discord \
  --kind discord \
  --allow <your-discord-user-id> \
  -- --dm
```

To listen in every room in one server:

```sh
rundesk channels ava add discord \
  --kind discord \
  --allow <your-discord-user-id> \
  -- --server <server-id>
```

To listen in one server channel:

```sh
rundesk channels ava add discord \
  --kind discord \
  --allow <your-discord-user-id> \
  -- --channel <channel-id>
```

The `--` is required before Discord-specific options. `--server` and `--channel` narrow
the room channel; they do not add direct messages.

For a non-interactive setup, `--token-stdin` reads one token from standard input. Feed it
from a secret manager or another protected source—never from a literal token in shell
history.

Set public-room instructions before loading the new channels:

```sh
rundesk channels ava instructions discord-rooms \
  "You are {agent} in {where.channel}. Others can read this, so keep it concise."
```

## 7. Load and test the channels

Review the saved channel configuration and the agent's current state:

```sh
rundesk channels ava
rundesk agents ava
```

The **REACHABLE** value in the channel listing means the agent's gateway is running; it
does not prove that the Discord connection started successfully.

If the agent is stopped, start it:

```sh
rundesk start ava
```

If it is already running, restart it:

```sh
rundesk restart ava
```

A gateway reads its channels and channel instructions when it starts. Restart it after
adding a channel or changing its instructions; `rundesk start` does not reload an agent
that is already running.

Then test both surfaces you enabled:

- Send the bot a direct message. It answers in that conversation.
- Mention the bot in a server channel. It opens a thread and answers there; later
  messages inside that thread do not need another mention.
- Run `/status` to confirm its slash commands are available.

Rundesk also offers `/stop`, `/new`, `/restart`, `/version`, `/agents`, `/skills`,
`/schedules`, `/help`, and `/provider` where the channel's access rules allow them.
`/schedules` lists the agent's schedules that can still run, soonest first; a one-time
schedule whose moment has gone is left out — `rundesk schedules <agent> --expired` is
where those are read. Global slash commands can take
up to an hour to appear. When the channel was added with `--server`, Rundesk also syncs
a server-scoped copy that normally appears sooner.

## Troubleshooting

### The bot is online but ignores messages

Enable **Message Content Intent** on the application's **Bot** page, save the change, and
restart the agent:

```sh
rundesk restart ava
```

In a server channel, mention the bot for the first message. Rundesk intentionally ignores
unmentioned room messages until it has opened a thread.

### Adding the channel says the bot cannot reach Discord

- Reset the token in the Developer Portal if it may be stale.
- Run the add command again and paste the new token when prompted.
- Do not run another Rundesk gateway or Discord adapter with the same bot token;
  competing connections can make one silently stop receiving messages.

### The bot cannot see or answer in one channel

Check the bot role and that channel's permission overrides for **View Channels**,
**Send Messages**, **Create Public Threads**, **Send Messages in Threads**, and
**Read Message History**. Add **Attach Files** and **Add Reactions** for full Rundesk
behavior.

### Slash commands do not appear

Confirm the app was installed with the `applications.commands` scope. Restart the agent
once, then allow time for Discord's global command registration to propagate.

### The bot is offline

Check the agent and its gateway log:

```sh
rundesk doctor ava
rundesk logs ava
```

If the agent is stopped, start it with `rundesk start ava`.
