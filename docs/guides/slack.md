# Set up a Slack bot

Reach one Rundesk agent from Slack: in direct messages, and in the channels you invite it to.
About twenty minutes, most of it waiting for Slack's own pages to load.

**Slack needs two credentials, not one.** An app-level token opens the connection and a bot token
calls the API, and neither works without the other. That is Slack's design rather than Rundesk's,
and it is the one place people get stuck.

**No public URL and no port to open.** This uses Socket Mode: the app opens an outbound websocket,
exactly as the Discord adapter opens a gateway connection. Nothing has to reach your machine.

**One Slack app per agent.** One bot is one identity; two agents behind one token are one presence
answering twice, and nobody reading the channel can tell which of them replied.

You need a Rundesk agent, a Slack account, and permission to install an app into the workspace.

## What it will and will not do

| Where | When it answers |
|---|---|
| a direct message to the bot | every message, with no mention needed |
| a channel it was invited to | only a message that names it — `@rundesk what changed today?` |
| a thread it opened | only a message that names it again |
| somebody else's thread | only a message that names it, and it answers in that thread |

**It is deliberately quiet.** The final answer is the only thing it posts. There is no running
commentary, no tool or activity lines, no delegation notices, no token counts, no timing, and no
footer under the answer. A turn looks like this and nothing else:

| | |
|---|---|
| 👀 on your message | Rundesk has taken the message up |
| Slack's own agent-session status | the agent is working — see [the typing indicator](#the-typing-indicator) |
| ✅ replacing the 👀 | the answer has gone out |

A turn that was stopped, or that failed, takes the 👀 down and puts nothing up. The sentence the
agent delivers is the news.

**It attaches no files, in either direction**, and a delivery carrying one is refused in words that
say so. It offers no slash commands, so two agents in one workspace never fight over a command name.

## 1. Create the app from the manifest

Almost everything the adapter needs is one paste rather than twenty toggles. **The one thing the
manifest cannot carry is step 2**, so do not install the app yet.

1. Open <https://api.slack.com/apps> → **Create New App** → **From an app manifest**.
2. Pick the workspace.
3. Choose the **YAML** tab and paste the manifest below.
4. Change `display_information.name` and `features.bot_user.display_name` to what you want the agent
   called in Slack. Change nothing else.
5. Select **Create**. Do not install it yet — step 2 changes what installing grants.

```yaml
# A Slack app for one Rundesk agent, in one paste.
#
# Change display_information.name and features.bot_user.display_name to the agent's name.
# Everything else is what src/channels/slack needs, and each part has a consequence named beside it.
display_information:
  name: Rundesk
  description: A Rundesk agent, reachable here.
  background_color: "#1f2933"

features:
  bot_user:
    display_name: rundesk
    # Socket Mode does not drive Slack's presence indicator. Keep the bot visibly available;
    # gateway health is reported by Rundesk and its logs, not by Slack's green dot.
    always_online: true

  app_home:
    # Without both of these nobody can send the bot a direct message, and the channel is deaf with
    # nothing to say why.
    home_tab_enabled: false
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false

oauth_config:
  scopes:
    bot:
      # Being named in a channel. This is the whole of the shared-channel wake-up.
      - app_mentions:read
      # Answering, and setting the agent session's status while a turn runs.
      - chat:write
      # Reading the thread a mention stands in, so an answer has the question above it.
      - channels:history
      - groups:history
      # Naming the channel an answer is being written in, and checking at --check time that the bot
      # is really in the channels it was pointed at.
      - channels:read
      - groups:read
      # Direct messages. `im:write` opens the conversation unprompted news is written to.
      - im:history
      - im:write
      # 👀 while a turn runs and ✅ once it has answered. Without step 2 there is no typing
      # indicator at all, so these are the whole of what says a turn was heard.
      - reactions:write
      # Saying who spoke, in the words Slack shows rather than as an id the brain cannot read.
      - users:read

settings:
  event_subscriptions:
    # Two, and only two. There is deliberately no `message.channels` and no `message.groups`: an
    # unmentioned message in a channel or in a thread produces no event at all, which is why the
    # agent cannot wake on one and why several agent bots can share a thread.
    bot_events:
      - app_mention
      - message.im

  # No public request URL and no inbound firewall hole: the app opens the connection.
  socket_mode_enabled: true
  token_rotation_enabled: false
```

**No `search:read`, no `users:read.email`, and nothing that reads a channel the bot was not invited
to.** The bot sees direct messages sent to its own App Home and the channels somebody added it to.
It does not inherit the installer's messages or their view of the workspace.

## 2. Declare the app as an agent

**The manifest cannot do this and no key is invented here for it.** Slack's own words are that only
apps declared as agents in their app settings can create sessions, and that declaring one *adds the
`assistant:write` scope to it* — which is why this comes before the app is installed, and why an app
already installed has to be installed again afterwards.

1. Still in <https://api.slack.com/apps>, open this app.
2. Find its agent declaration in the app's settings and switch it on. Slack has moved and renamed
   this control more than once, so it is not named here; it is the setting that declares the app an
   agent, described in [Slack's agent sessions guide](https://docs.slack.dev/ai/agent-sessions/).
3. Confirm `assistant:write` has appeared under **OAuth & Permissions** → **Bot Token Scopes**. That
   scope appearing is what says the declaration took.

**Skipping this step is not a broken setup.** Everything else works: the agent answers, marks the
message it was asked on, and marks it again when it is done. What is missing is the typing indicator
while a turn runs — see [the typing indicator](#the-typing-indicator) — and nothing is posted in its
place.

## 3. Install the app to the workspace

**After step 2 and not before**, because the token is issued with the scopes granted at the moment it
is installed and a scope added afterwards does not reach a token already handed out.

1. **OAuth & Permissions** → **Install to Workspace**, and approve the scopes.
2. If the app was already installed, use **Reinstall to Workspace** — the button says so once the
   scopes have changed under it.

## 4. Copy the bot token

**OAuth & Permissions** → **Bot User OAuth Token**. It begins `xoxb-`.

This is a password: anything holding it can post as your bot. Never paste it into a command.

**Never a user token.** A token beginning `xoxp-` is a *person's*, and carries their own view of the
workspace — every direct message they can read. The adapter refuses one by name before it calls
anything.

## 5. Create the app-level token

**Basic Information** → **App-Level Tokens** → **Generate Token and Scopes**.

- Name it anything; `socket` will do.
- Add the scope **`connections:write`**, and only that one.
- **Generate**, then copy it. It begins `xapp-`. Slack shows it once.

## 6. Invite the bot where you want it

In Slack, in each channel the agent should be reachable in:

```text
/invite @rundesk
```

A bot in no channel can still be reached by direct message. It cannot see or answer in a channel it
has not been invited to, and a private channel needs the invitation explicitly.

## 7. Find the ids

| What | Where |
|---|---|
| your member id — `U01ABCDEF2G` | your profile → the **⋮** menu → **Copy member ID** |
| a channel id — `C01ABCDEF2G` | the channel → **View channel details** → the bottom of the About tab |

A display name is not an id, and it can be changed by the person who holds it.

## 8. Add the channel

```console
$ rundesk channels add ava slack --allow U01ABCDEF2G --notify
the slack adapter needs 2 values before ava can use it
        SLACK_BOT_TOKEN__AVA   the slack adapter reads SLACK_BOT_TOKEN, and this is ava's own
        >
        SLACK_APP_TOKEN__AVA   the slack adapter reads SLACK_APP_TOKEN, and this is ava's own
        >
ava is connected to slack
        reaches   rundesk in Acme
        allowed   U01ABCDEF2G
        told      yes — unprompted things go to T01ACME:D01ABCDEF2G
        needs     SLACK_BOT_TOKEN__AVA (set), SLACK_APP_TOKEN__AVA (set)
        settings  {"max_text": 3800}
        can       attach=False, edit=none, max_text=3800, react=True, stream=False, thread=True
        adapter   /Users/you/.rundesk/app/src/channels/slack
        keeps     /Users/you/.rundesk/data/agents/ava/channels/slack
        standing  not connected
```

Both tokens are typed at a prompt without echoing and kept under this agent's own name.
Rundesk writes down the *names* and never what is in them.

**Nothing is written down until the adapter says it reached something.** A wrong token, an app-level
token without `connections:write`, or a missing scope is something you find out here rather than at
three in the morning.

**`--notify` makes this the channel the agent speaks first on**, and it lands in your own direct
message. Left off, the agent answers when spoken to and never says anything unprompted.

### Who may reach it

`--allow` takes one entry per person or place, and repeats.

| Entry | Allows |
|---|---|
| `U01ABCDEF2G` | that member, wherever they say it — the plain form every channel has always used |
| `sender:U01ABCDEF2G` | the same thing, said out loud |
| `place:C01ABCDEF2G` | **anybody** Slack reports as being in that channel |

```sh
# any real person in #operations, plus one person by direct message
rundesk channels add ava slack --allow place:C01ABCDEF2G --allow U01ABCDEF2G --notify

# add a second channel later
rundesk channels configure ava slack --allow place:C09PRIVATE

# take one away, written exactly as it stands on the list
rundesk channels configure ava slack --deny place:C09PRIVATE
```

**A place entry allows anybody in that place and not the place itself**, so a bot posting there, a
join notice, and anything else Slack reports without a member behind it are all refused. An entry
naming nothing — `place:` with no id — is refused where you typed it.

Rundesk decides this, not the adapter, and a message from anybody else is dropped in silence:
replying to say somebody is a stranger confirms the agent is listening and spends your tokens doing
it.

## 9. Start it

```sh
rundesk gateways start ava
```

`channels add` connects once and leaves nothing running, which is what `standing not connected` on
the last line means.

## The typing indicator

The adapter sets Slack's own agent-session status through `agents.sessions.setStatus` — the current
method. It uses neither the older `assistant.threads.setStatus` nor the streaming methods, and it
**never posts a message to imitate a typing indicator**. Where the status cannot be set, nothing is
shown.

It needs all of:

| | |
|---|---|
| a granular bot token carrying `chat:write` | the manifest above asks for it |
| the app **declared as an agent** | [step 2](#2-declare-the-app-as-an-agent), in the app's own settings. The manifest cannot carry it |
| the app installed **after** that declaration | [step 3](#3-install-the-app-to-the-workspace). The scope it adds does not reach a token already issued |
| the bot to be a member of the channel | `/invite @rundesk` |
| a channel **and a thread** | so a direct message that is not in a thread has no session |
| a plan that includes the AI features | some of them are paid; Slack decides which |

Two consequences, and both are stated rather than worked around:

- **A flat direct message shows no status.** The status is keyed to a thread and a direct
  conversation that is not in one has none. The 👀 on your message is what says it was taken up.
- **An app that was never declared an agent shows no status.** The adapter says so once, in the
  agent's log, naming what to go and do, and posts nothing in its place.

**A session takes one of four words** — `active`, `processing`, `suspended`, `closed` — and this
sends two of them: `processing` while a turn runs and `active` when it settles. There is no fifth and
no empty status; that one clears the *older* `assistant.threads.setStatus` and this method answers it
with `invalid_status`.

The session is asked back to `active` on every way a turn ends, including one that ends before a turn
ever began. **Each of those is one call to Slack, and there is never a second.** Nothing waits and
nothing is retried: a status is a courtesy on top of a turn that has already been answered, and a
refusal is reported in the agent's log and acted on only by making *fewer* calls afterwards.

What a refusal costs depends on what Slack said, and on nothing this guide guesses at:

| Slack answered | What stops |
|---|---|
| `ratelimited` with a `Retry-After` | no status call anywhere until that has passed. Slack says the delay applies to this method in this workspace, so nothing is sent inside it |
| `ratelimited` with nothing usable | the typing indicator, until the channel is started again. There is no interval to invent, and calling again is the thing to avoid |
| `feature_disabled`, `missing_scope`, `not_allowed_token_type`, `team_access_not_granted`, `method_deprecated`, `deprecated_endpoint` | the typing indicator everywhere — each of these is Slack talking about the token, the app or the method. Usually it means [step 2](#2-declare-the-app-as-an-agent) was skipped |
| `channel_not_found`, `not_authorized`, `no_permission`, `thread_ts_required`, `thread_ts_not_allowed` | the indicator **in that one thread**. Every other channel is unaffected |
| anything else | nothing. One call failed, it is logged, and the next turn tries as normal |

## Several agents in one thread

Install a separate Slack app for each agent, invite each to the channels it belongs in, and add each
to its own Rundesk agent.

**Each bot wakes only when it is named.** Slack delivers `app_mention` to the app that was mentioned,
and the adapter checks its own member id in the text besides — so `@ava` in a thread wakes `ava` and
nothing else, `@ava @dev` wakes both, and a message naming neither wakes nobody. Each answers in the
thread the mention stands in, so one thread can hold a conversation with two agents and the people
in it.

**Each reads what the other said, and never what it said itself.** Ask `@dev` something, read the
answer, then ask `@ava` what she makes of it: the bounded thread slice ava is handed at that moment
carries dev's answer, named as dev, because otherwise she would be given the question with the answer
it was about taken out. Her own earlier messages are left out of it — handing a brain the last thing
it said back to itself is not context. That reading happens only when somebody names her; no bot's
message ever wakes anything.

## A workspace install is not an organisation install

On Slack Enterprise Grid these are different acts and both may be needed.

| | |
|---|---|
| **Workspace installation** | what step 1 does. The app is installed into one workspace and reaches the channels and direct messages in it |
| **Organisation approval** | an org admin allows the app to be installed at all. Without it, installing is refused before it starts |
| **Organisation installation** | an org admin installs the app across workspaces. It is a separate action, and it does not follow from approval |

An app approved and not installed reaches nothing. An app installed into one workspace reaches that
workspace, and a channel in a second workspace stays invisible to it even where the two are in one
organisation — which is why the conversation key carries the workspace id, so an agent reachable
from two of them never folds two exchanges into one.

## Troubleshooting

Start with `rundesk channels doctor ava`, which authenticates and asks Slack for a Socket Mode URL
without opening a second websocket. Then run `rundesk gateways logs ava`. What the adapter wrote to stderr is in
`data/agents/ava/channels/slack/stderr.log`.

| What you see | Usually |
|---|---|
| `there are no Slack tokens` | one of the two is unset. `xoxb-` is `SLACK_BOT_TOKEN`, `xapp-` is `SLACK_APP_TOKEN` |
| `holds a user token` | the `xoxp-` token was pasted instead of the bot token |
| `signed in as a person` | the token is a user token that does not carry the `xoxp-` prefix |
| `has not been granted …` | a scope was added after the token was issued. Reinstall the app to the workspace |
| `the app-level token … was not [accepted]` | Socket Mode is off, or the token has no `connections:write` |
| `it is not in C… yet` | nobody has run `/invite @rundesk` there |
| `opening the Socket Mode websocket…` with no later `Slack said hello…` | this machine opened the websocket but Slack has not greeted it; the channel does not report ready |
| `Slack said hello…` with no `Slack delivered…` line after a test message | Slack established the websocket, but no event has crossed the adapter's observed boundaries yet |
| `Slack delivered…` | the fixed sentence names the boundary reached; it never includes message text, member, channel, workspace, or credential values |
| the bot answers a DM and ignores a channel | it was not invited, or nobody named it. It stays silent until named |
| the bot ignores direct messages | **App Home** → **Messages Tab** is off. The manifest turns it on; an app made by hand often has neither |
| no typing indicator ever appears | [step 2](#2-declare-the-app-as-an-agent) was skipped, or it was done after installing and the app has not been installed again since, or the exchange is a flat direct message. Nothing is posted in its place |
| `assistant:write` is missing from **Bot Token Scopes** | the agent declaration in step 2 did not take, or the app has not been installed again since it did |
| `standing not connected` after `add` | `add` connects once and leaves nothing running — start the gateway |

**Nothing here is verified against a live Slack workspace.** Every claim above is read out of
`src/channels/slack` and out of Slack's published method reference; the adapter's own behavior is
proved offline in `tests/test_channels_slack.py`. Setting up a real app is the one step only you can
run.
