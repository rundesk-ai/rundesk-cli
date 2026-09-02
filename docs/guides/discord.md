# Set up a Discord bot

Rundesk gives each agent its own Discord bot. The bot can answer direct messages, open a thread
when mentioned in a server channel, send files, show activity, and offer Rundesk slash commands.

You need:

- a Rundesk agent, such as `ava`;
- a Discord account;
- a server where you have permission to install apps; and
- your numeric Discord user ID.

The bot token is a password. Never paste it into a command, commit it, or send it in a message.
Rundesk prompts for it without echoing it and keeps it under that agent's own name.

## 1. Create the application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Select **New Application**, enter the name you want the agent to use, and select **Create**.
3. Open **Bot** in the sidebar.
4. Add the agent's username and profile image. These are the name and avatar people see in Discord.

![Discord Developer Portal Bot page with the username and profile image controls highlighted](../assets/discord/bot-profile.png)

*Give the bot the same name and profile image you want people to recognize as the agent.*

Use one Discord application per Rundesk agent. One bot is one identity; sharing a token between two
agents lets both receive and answer the same messages.

## 2. Copy the bot token

On the **Bot** page:

1. Select **Reset Token**.
2. Complete Discord's confirmation or two-factor prompt.
3. Copy the token and keep it in a password manager until Rundesk asks for it.

![Discord Developer Portal Bot page with Reset Token highlighted](../assets/discord/bot-token.png)

*Reset the token, copy it once, and keep it private until Rundesk prompts for it.*

Discord shows the token once. If it is lost or exposed, reset it before connecting the bot.

## 3. Enable Message Content Intent

Still on the **Bot** page, find **Privileged Gateway Intents** and enable:

- **Message Content Intent**

Leave **Presence Intent** and **Server Members Intent** off. Rundesk does not request them.

![Discord privileged gateway intents with Message Content enabled and Server Members disabled](../assets/discord/privileged-intents.png)

*Enable Message Content Intent only. Leave Presence Intent and Server Members Intent off.*

Without Message Content Intent, Discord hides ordinary server and thread messages from the bot.
Rundesk checks this setting and refuses the connection instead of saving a channel that cannot read
its conversations.

## 4. Configure the installation

Open **Installation** in the Developer Portal.

1. Under **Installation Contexts**, enable **Guild Install**.
2. Under **Install Link**, select **Discord Provided Link**.
3. Under **Default Install Settings** for Guild Install, add these scopes:
   - `bot`
   - `applications.commands`
4. Grant only these permissions:
   - **View Channels**
   - **Add Reactions**
   - **Send Messages**
   - **Attach Files**
   - **Read Message History**
   - **Create Public Threads**
   - **Send Messages in Threads**

![Discord Guild Install scopes and least-privilege permissions required by Rundesk](../assets/discord/install-settings.png)

*Guild Install needs the `bot` and `applications.commands` scopes plus the seven permissions shown.*

These permissions match what the shipped Discord adapter does. Rundesk does not need **Change
Nickname**, **Connect**, **Embed Links**, **Manage Channels**, **Manage Messages**, or **Manage
Threads**.

The install link is generated above the default settings. You can use it now, but Rundesk also
prints a verified invite after it connects in the next steps. A bot already installed in a server
must be authorized again if its scopes or permissions change.

![Discord Installation page with the generated install link highlighted](../assets/discord/install-link.png)

*Copy the Discord-provided install link after saving the scopes and permissions.*

## 5. Copy your Discord user ID

In the Discord app:

1. Open **User Settings** → **Advanced**.
2. Enable **Developer Mode**.
3. Right-click your profile and select **Copy User ID**.

Use the numeric ID, not a username. Repeat `--allow` for each additional person who may reach the
agent.

## 6. Connect the bot to the agent

Run:

```sh
discord_user_id=123456789012345678
rundesk channels add ava discord --allow "$discord_user_id" --notify
```

Replace `ava` with the agent's name and the example ID with your own. Rundesk asks for the bot token
without echoing it, connects to Discord, verifies Message Content Intent, and only then saves the
channel.

Use `--notify` for the first channel you add. `--allow` controls who may reach the agent and who
receives private gateway notices, schedule results, and returned delegated work. `--notify` selects
Discord as the adapter for those unsolicited messages. Direct replies still go only to the DM,
room, or thread that asked.

On success, save the printed **invite** URL and open it to add the bot to a server. The URL already
contains Rundesk's required scopes and permissions. The bot is not in a server until someone with
permission authorizes it there.

## 7. Start and test the gateway

`channels add` proves the connection and then exits. Start the agent's persistent gateway:

```sh
rundesk gateways start ava
```

Then test the surfaces you enabled:

- Send the bot a direct message.
- Mention the bot in a server channel. It opens a thread; later messages in that thread do not need
  another mention.
- Run `/status` to confirm the slash commands are available.

If the bot answers but never speaks first, mark the channel for notifications and restart:

```sh
rundesk channels configure ava discord --notify
rundesk gateways restart ava
```

## Troubleshooting

Run the channel diagnosis first:

```sh
rundesk channels doctor ava
rundesk gateways logs ava
```

### The bot is online but ignores messages

Enable **Message Content Intent** on the application's **Bot** page, then restart the gateway. In a
server channel, mention the bot in the first message so it can open the conversation thread.

### Slash commands do not appear

Authorize the bot with the `applications.commands` scope. If the bot was already installed, open
the invite printed by `channels add` and authorize it again.

### The bot cannot answer in one channel

Check that channel's role overrides for **View Channels**, **Send Messages**, **Create Public
Threads**, **Send Messages in Threads**, and **Read Message History**. Grant **Attach Files** and
**Add Reactions** for the complete Rundesk experience.

### The token was lost or exposed

Reset it on the application's **Bot** page, remove and reconnect the channel through Rundesk, and
never put the replacement token in shell history or a message.
