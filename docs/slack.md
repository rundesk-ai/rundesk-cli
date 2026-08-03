# Set up a Slack bot

Reach one Rundesk agent from Slack: in direct messages, and in the channels you invite it
to. Twenty minutes, most of it waiting for Slack's own pages to load.

**Slack needs two credentials, not one.** An app-level token opens the connection and a bot
token calls the API, and neither works without the other. That is Slack's design rather than
Rundesk's, and the one place people get stuck — so both are called out at every step below.

**No public URL, no port to open.** This uses Socket Mode: the app opens an outbound
websocket, exactly as the Discord adapter opens a gateway connection. Nothing has to reach
your machine from the internet.

You will need to be able to install an app into the workspace. In most workspaces that is an
admin; in one you own it is you.

---

## 1. Create the app from the manifest

Everything the adapter needs — the scopes, the events, the one slash command, the bot's
presence behaviour — is in one file, so this is a paste rather than twenty toggles.

1. Open <https://api.slack.com/apps> and choose **Create New App** → **From an app
   manifest**.
2. Pick the workspace.
3. Choose the **YAML** tab and paste the whole of
   [`slack-app-manifest.yaml`](./slack-app-manifest.yaml).
4. Before you click Create, change two things:
   - `display_information.name` and `features.bot_user.display_name` — what you want the
     agent called in Slack.
   - `features.slash_commands[0].command` — leave it as `/rundesk` for your first agent.
     **A slash command name belongs to one app per workspace**, and the last app to register
     one wins it, so a second agent needs its own (`/winston`). See step 7.
5. **Create**, then **Install to Workspace** and approve the scopes.

## 2. Copy the bot token

**OAuth & Permissions** → **Bot User OAuth Token**. It begins `xoxb-`.

This is one of the two. It is a password: anything holding it can post as your bot.

## 3. Create and copy the app-level token

**Basic Information** → scroll to **App-Level Tokens** → **Generate Token and Scopes**.

- Name it anything — `socket` will do.
- Add the scope **`connections:write`**. It will not work without exactly this one.
- **Generate**, then copy it. It begins `xapp-`.

This is the second. Slack shows it once; if you lose it, generate another.

## 4. Give the tokens to Rundesk

Two ways, and the second is the one that survives a reboot.

**In the shell you are about to run `channels add` from:**

```sh
export SLACK_BOT_TOKEN=xoxb-…
export SLACK_APP_TOKEN=xapp-…
```

**Or in files the channel owns.** A supervised gateway starts with a built environment and
no shell profile, so a variable you exported by hand is not there once the machine is keeping
the agent up — which is the only way it is meant to run. The adapter looks in its own
directory for two files, and never writes either one itself:

```text
<rundesk data>/agents/<agent>/channels/<channel>/token        the xoxb- one
<rundesk data>/agents/<agent>/channels/<channel>/app-token    the xapp- one
```

`rundesk channels <agent> show <channel>` prints where that directory is. Adding the channel
makes it, so export the variables for step 6 and write the files afterwards if you prefer
them on disk.

Rundesk writes down the *names* of these two variables and never what is in them.

## 5. Invite the bot to a channel

In Slack, in each channel you want the agent reachable in:

```text
/invite @rundesk
```

A bot in no channel can still be reached by direct message. It cannot see or answer in a
channel it has not been invited to, and Slack gives it no way to notice that it is missing.

## 6. Find your own member ID

Your profile → the **⋮** menu → **Copy member ID**. It looks like `U01ABCDEF2G`.

This is who may reach the agent. It is not your display name and not your email.

## 7. Add Slack to the agent

```sh
rundesk channels ava add slack --kind slack --allow U01ABCDEF2G
```

This signs in with both tokens, asks Slack which channels the bot is actually in, and writes
**two channels**:

| | |
|---|---|
| `slack-dms` | direct messages to the bot |
| `slack-rooms` | the channels it has been invited to |

They are two because a channel carries the list of who may reach the agent through it, and
the people who may speak to an agent in a public channel are not the people who may speak to
it privately. Each has its own allowed list.

Nothing is written down unless the check passes, so a wrong token or an uninvited bot is
something you find out here rather than at three in the morning.

**Narrowing it.** Give any of these after a `--`:

```sh
# direct messages only
rundesk channels ava add slack --kind slack --allow U01ABCDEF2G -- --dm

# one channel and no other
rundesk channels ava add slack --kind slack --allow U01ABCDEF2G -- --channel C01ABCDEF2G

# a second agent in the same workspace needs its own command name
rundesk channels ava add slack --kind slack --allow U01ABCDEF2G -- --command ava
```

`--command ava` must match what you put in the manifest for *that* app. Two agents sharing a
command name means one of them silently never receives it.

## 8. Start it

```sh
rundesk start ava          # kept up by the machine
rundesk start ava --here   # or in this terminal, where you can watch it
```

The bot's green dot comes on when the socket opens and goes off when the agent stops, and
you get a direct message either way.

---

## What it looks like

**In a direct message.** Say anything. You get 👀 while it works, whatever it is doing if you
asked to see that, and then the answer with what it cost above it.

**In a channel.** Mention the agent. It answers in a thread under your message, and inside
that thread you can keep talking without mentioning it again. It stays silent in a channel
until it is named, and it will not join a thread it has never answered in.

**The command.** `/rundesk help` lists everything. The gesture is the first word:

| | |
|---|---|
| `/rundesk stop` | stop the turn running here |
| `/rundesk new` | start a new session — the next message begins fresh |
| `/rundesk restart` | restart this agent's gateway |
| `/rundesk status` `version` `agents` `skills` `schedules` `roles` | read-only, answered only to you |
| `/rundesk provider <name>` | change the agent's default provider, on a single-user channel only |

**What Slack cannot do that Discord can.** There is no typing indicator — Slack has none for
a bot that does not force a thread-only UI on every conversation — so the 👀 mark and the
running commentary are what tell you a turn is alive. Everything else is the same.

## Changing who may reach the agent

```sh
rundesk channels ava allow slack-dms U01ABCDEF2G U03HIJKLM4N
rundesk channels ava show slack-rooms
```

The first name in the list is the owner: gateway notices go to them. Somebody newly added
gets an introduction from the agent itself, in a direct message.

A message from anybody not on the list is dropped in silence. That is deliberate — replying
to a stranger to tell them they are a stranger confirms the agent is listening and spends
your tokens doing it.

---

## Troubleshooting

Start with `rundesk logs ava`. Everything the adapter says goes there, prefixed with the
channel's name.

### Adding the channel says there are no Slack credentials

Both variables have to be set, and it names the one that is missing. `xoxb-` is
`SLACK_BOT_TOKEN`; `xapp-` is `SLACK_APP_TOKEN`. Pasting them the wrong way round produces
this too.

### Adding the channel says Slack refused the credentials

The bot token is wrong, or the app was never installed to the workspace. Reinstall from
**OAuth & Permissions** and copy the token again.

### It says this bot is not in any channel

Nobody has invited it anywhere. `/invite @rundesk` in one channel, then add it again — or
use `-- --dm` if direct messages are all you want.

### The bot is online but ignores messages in a channel

Three things, in the order they go wrong:

1. It was never invited to that channel.
2. You did not mention it. It stays silent until named.
3. The channel is private and the app is missing `groups:history`. Reinstall from the
   manifest.

### The bot ignores direct messages

**App Home** → **Show Tabs** → **Messages Tab** must be on, with *Allow users to send
Slash commands and messages from the messages tab* ticked. The manifest sets both; an app
made by hand often has neither.

### The slash command does nothing, or is not offered

Another app in the workspace owns that name — Slack gives a command to one app, and the last
one to register it wins. Rename it in **Slash Commands**, reinstall, and tell the adapter
with `-- --command <the new name>`.

If the command exists but times out, check **Socket Mode** is on and **Interactivity &
Shortcuts** is enabled. Without interactivity the command is delivered nowhere.

### The bot shows as active after the agent has stopped

`always_online` is true in the app manifest. Set it false — the green dot should follow the
connection, which is what makes it mean anything.

### A file the agent made never arrives

`files:write` is missing, or the bot is not in the channel it is uploading to. Both show as a
refusal in `rundesk logs ava`.
