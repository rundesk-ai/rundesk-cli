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

**Your direct message with the agent is one conversation, however you thread it.** Every message in
it shares one history and one session, so a follow-up asked beside an earlier exchange is asked of an
agent that remembers it. The answer to a message still arrives where you are reading: in the thread
you asked in, or in a thread rooted at your message when you asked outside one — so several
exchanges stay readable apart without becoming several conversations. **A channel is different**: a
thread there is its own conversation, which is what lets one channel hold unrelated work.

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

**It can name one person and it cannot address a room.** The agent is told, beside the name of
whoever spoke, the exact handle that mentions them — only for mentioning them, never to repeat —
so it can mention the person it is answering. An answer that names a Slack member —
`<@U01ABCDEF2G>`, the markup Slack itself uses — arrives as a real mention, so an agent asked to
loop somebody in can do it. Everything wider stays the text it looks like: `@channel`, `@here`,
`@everyone`, a user group, a channel link, and anything malformed, because notifying a room full of
people on the agent's behalf is not something anybody asked for. A private answer to the slash
command is escaped whole — those words are Rundesk's account of stored records rather than the
agent's own sentence.

**It sends files out, and takes one in only when the agent goes and asks for it.** A file the agent
attached to its answer is uploaded into the same conversation the answer went to — see
[files it sends](#files-it-sends). Nothing arriving is fetched: a file somebody uploads to the agent
is still not read. The one way a file comes in is `rundesk search <agent> --fetch`, which brings in
the attachments of a message the agent found and asked for by name — see
[what it can search](#what-it-can-search).

**It offers one slash command**, named after the agent, and every one of its answers is private to
whoever typed it — see [the one command it offers](#the-one-command-it-offers).

**The agent can go and look through this workspace on its own** — but only where this bot was
invited, and only when it asks. See [what it can search](#what-it-can-search).

## 1. Create the app from the manifest

Almost everything the adapter needs is one paste rather than twenty toggles. **The one thing the
manifest cannot carry is step 2**, so do not install the app yet.

1. Open <https://api.slack.com/apps> → **Create New App** → **From an app manifest**.
2. Pick the workspace.
3. Choose the **YAML** tab and paste the manifest below.
4. Change `display_information.name`, `features.bot_user.display_name`, and the
   `slash_commands` entry's `command` to what you want the agent called in Slack — the command is
   `/` and that name, so `ava` gives `/ava`. Change nothing else.
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
    # Slack's presence dot cannot represent whether this agent is running. Socket Mode and the
    # Events API do not drive it, `users.setPresence` cannot force a bot active, and
    # marking the bot always online is a static claim that stays green after the gateway stops —
    # which reads as a healthy agent that answers nothing. Left false, the indicator is not an
    # answer about Rundesk, and the answer is `rundesk gateways` and the agent's log.
    always_online: false

  app_home:
    # Without both of these nobody can send the bot a direct message, and the channel is deaf with
    # nothing to say why.
    home_tab_enabled: false
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false

  slash_commands:
    # One command for this agent, named after it, and the subcommand is the gesture: `/ava status`,
    # `/ava schedules`, `/ava provider codex`. A Slack command name belongs to the whole workspace,
    # so two agents each declaring `/status` is the second app taking the first one's command away.
    # Rename `command` and `description` for the agent; the adapter never checks the name, because
    # Slack delivers an app's commands only to that app's own connections.
    - command: /ava
      description: Ask this Rundesk agent for something, or steer it
      usage_hint: "status | schedules | delegations | stop | new | restart | shutdown | provider <name>"

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
      # Uploading a file the agent attached to its answer.
      - files:write
      # Declaring the one slash command above. It reads nothing and grants no access to a
      # conversation; without it the command cannot be declared at all.
      - commands
      # The last four are for `rundesk search`, and every one of them is optional. Leave them out
      # and everything else on this page works exactly as it does today — the agent simply searches
      # fewer kinds of conversation, and says so when it does. Read
      # `## What it can search` below before you decide. None of them widens what the bot may see:
      # each one covers a conversation the bot is already in.
      #
      # Listing the direct and group-direct conversations this bot is in, so an unscoped search can
      # find them. Without these two, a search still reads a direct conversation you name outright.
      - im:read
      - mpim:read
      # Reading what was said in a group direct conversation it is in.
      - mpim:history
      # Downloading a file somebody attached to a message the agent found. Without it, `search` works
      # and `--fetch` refuses by name.
      - files:read

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

**The four search scopes do not change that sentence, which is why they are safe to add.** Each one
covers a conversation the bot is already in — listing the direct conversations it is part of, reading
a group direct conversation it is part of, downloading a file from a message it can already read.
None of them reaches a channel it was not invited to, and none of them is a user token.

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
        can       attach=True, edit=none, max_text=3800, react=True, stream=False, thread=True
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

## Files it sends

**A file the agent attached to its answer is uploaded into the conversation the answer went to** —
the same channel, and the same thread when the answer is in one. A direct message is a conversation
like any other here, so an answer with a chart in it arrives with the chart.

The agent declares one by writing a local path into its final answer: `[report](/absolute/report.pdf)`
attaches a file and `![preview](/absolute/preview.png)` attaches an image. Rundesk takes the machine
path out of the words it posts, opens the file, fingerprints it, and hands the adapter the path with
the size and digest it approved. See [`../api/channels.md`](../api/channels.md#attachments-in-and-out)
for the whole of what Rundesk does with a declaration.

| | |
|---|---|
| files one answer may carry | 10 |
| bytes per file | 32 MiB |
| what is uploaded | the bytes this adapter re-opened and verified, never the path |
| where it lands | the answer's own channel and thread — including when the answer was long enough to be split and the files ride on its last piece |
| how long one answer has to get its files up | 8 seconds from the moment the answer is taken up |
| incoming files | not fetched, and no scope asks to |

**Every file is verified again, immediately before its own upload.** The adapter re-opens the path
itself with every directory on the way opened so it cannot be followed through a symbolic link,
streams the bytes into a snapshot, and compares the size and the SHA-256 with what Rundesk approved.
Between the approval and the upload a concurrent turn can replace the file — or replace a directory
above it with a link to somewhere else — and only a second open sees that. Anything that does not
match is not uploaded.

**The words are posted first, and a file that will not go is named where the answer is.** Slack has
no call that carries a message and a file together, so the answer is one call and each upload is
another. If an upload fails, the answer stays — you see it, and a short line under it says
`Could not attach: preview.png.` The agent's log carries the whole reason, including the path, which
the conversation never does.

**A delivery that was only a file and could not be uploaded is reported as failed** and still says so
in the conversation, so an answer nobody can see is never an answer nobody hears about.

**An answer has a few seconds to get its files up, and says so when it does not.** Rundesk waits a
bounded moment to hear what became of a delivery and settles the turn the instant that wait ends, so
uploads that ran on past it would answer into nothing — and a completion mark would stand over an
answer whose file never went. So one answer has 8 seconds from the moment it is taken up to get its
files up — the message it posts first is spent out of the same 8 — and an upload still running at the
end of it is given up on. A file given up on, and a file there was no time left to begin, are both
named the way a file that failed is named: `Could not attach: preview.png.`

**A file given up on is not cancelled, so it may still arrive afterwards** — Slack may finish an
upload Rundesk has stopped waiting for, and it would then appear with no line beside it. What the
agent reports is what it knows at the deadline, which is that the file did not go; calling something
still in flight a success is the alternative, and that cannot be told from a file that arrived. A
large file on a slow link is the case this costs.

**This needs `files:write`, which the manifest asks for.** An app installed before this release does
not have it: `rundesk channels doctor <agent>` names it, and the fix is
[step 3](#3-install-the-app-to-the-workspace) — **Reinstall to Workspace**, because a scope added
after a token was issued does not reach it.

## What it can search

`rundesk search` lets the agent go and look through this workspace mid-turn, read what it found,
narrow the question and ask again. It is the same verb on every platform — see
[the command](../api/conversations.md#search) — and this section is only what *Slack* does behind it.

```console
$ rundesk search ava "the invoice bug" --since 2026-08-01
2 found on slack, holding 'the invoice bug', since 2026-08-01  (9 places, 1600 messages looked through)
WHEN                  WHO   WHERE                  FILES  REF                      SAID
2026-08-30T14:02:11Z  Dana  the #operations room   1      C0OPS/1725026531.000200  the invoice bug is in the parser
2026-08-29T09:40:02Z  Sam   a direct message              D0SAM/1724924402.000100  re: the invoice bug — fixed?
```

### Where it looks, and where it cannot

**Only where this bot already is.** Slack publishes no search a bot token can call on its own, so the
adapter reads the conversations it is a member of and matches the words itself. That means:

| | |
|---|---|
| channels it was invited to | **yes**, public and private alike |
| threads inside those channels | **yes** — and this matters, because the agent answers every channel mention in a thread of its own |
| direct messages with the bot | **yes** |
| group direct messages it is in | **yes**, with `mpim:history` |
| channels it was never invited to | **no** |
| your own direct messages with other people | **no** |

**Said plainly, because it is the first thing people expect and do not get:** this searches what the
*bot* can see, not what *you* can see. Reaching a conversation the bot is not in would need a Slack
*user* token — one person's whole view of the workspace, including every private message they can
read — and no Rundesk agent is ever given one. The adapter refuses a `xoxp-` token by name.

**It matches words, not meaning.** Every word you type has to appear, ignoring case. There is no
stemming, no phrase, and no ranking, because Slack's own ranked search is not available to a bot
token here. Narrow with `--place`, `--from` and a window of days rather than with cleverer words.

### What it says when it could not look everywhere

**A search that stopped early always says so**, and it is never printed as an empty result. Reading
one as the other is how an agent concludes a thing was never discussed.

| You will see it say | Because |
|---|---|
| it used a default window of the last 30 days | you gave no `--since`, and it will not read all of history by default |
| direct or group-direct messages were not looked through | the app has not been granted `im:read`, `mpim:read` or `mpim:history`. The sentence names the one that is missing |
| it stopped after so many places, or so many pages | the search reached its own ceiling. Narrow it with `--place` or a shorter window |
| more conversations held threads than it opened | a thread is a second call to Slack, so a busy channel is bounded. Narrow with `--place` |
| Slack rate-limited it | it stops rather than waiting. A turn is running and you have not been answered yet |

**A conversation you name outright is always read**, even when the app cannot *list* that kind.
Listing and reading are two different scopes: without `im:read` an unscoped search finds no direct
messages, and `rundesk search ava invoice --place D0SAM` still reads that one.

### Bringing a file in

A result's `REF` is what `--fetch` takes:

```console
$ rundesk search ava --fetch 'C0OPS/1725026531.000200' --channel slack
2 from C0OPS/1725026531.000200, in ava's slack record
```

This needs `files:read`. Without it, searching works and `--fetch` refuses by name, saying which
scope to add. Up to ten files of 32 MiB each; the message is reached again before anything is
downloaded, and a file whose size does not match what Slack declared is refused while the rest still
come.

### One assumption worth knowing

**This assumes your app is internal to your workspace and is not publicly distributed.** Slack cut
`conversations.history` for non-Marketplace *distributed* apps to one request a minute returning
fifteen messages, and exempted apps a customer built for their own workspace — which is what the
manifest on this page creates. Switch distribution on for this app and search degrades sharply, from
hundreds of messages a second to fifteen a minute. Nothing here detects that; it will simply become
slow and say it stopped early.

## The one command it offers

The manifest in [step 1](#1-create-the-app-from-the-manifest) declares **one slash command, named
after the agent**, and the subcommand is what you are asking for:

```text
/ava status
/ava schedules
/ava provider codex
```

**One command per agent, because a Slack command name belongs to the whole workspace.** Two agents
each offering `/status` would be the second app taking the first one's command away; naming it after
the agent is what lets `ava` and `dev` stand in one workspace. The adapter never checks the name, so
whatever you called it is the command — Slack delivers an app's commands only to that app's own
connections.

| Subcommand | Does |
|---|---|
| `stop` | stop the turn running in this conversation |
| `new` | start a new session — the next message begins fresh |
| `restart` | restart this agent's gateway |
| `shutdown` | shut the gateway down for good — **asked for twice** |
| `status` | what this agent's gateway state is |
| `version` | the Rundesk version this agent is running |
| `agents` | every agent on the install, and the skills each holds |
| `skills` | the skills this agent holds |
| `schedules` | what this agent still has to run, soonest first |
| `delegations` | delegated work relevant to this conversation |
| `provider <name> [alias]` | change which brain answers for this agent |

**Every answer is private to whoever typed it**, wherever they typed it. It goes back as an
ephemeral response on that command's own response URL, so an answer listing every agent on the
install is never posted where a channel can read it.

**None of these starts a turn.** Each is answered out of what the install already knows, so it costs
no tokens and is answered in milliseconds rather than minutes.

**Anything else gets the list of what there is.** A typo, a bare `/ava`, or a `provider` with no name
is answered privately by the adapter itself, and nothing reaches the agent at all.

**One typed command is one command.** Slack gives every invocation an envelope of its own and sends
that envelope again whenever an acknowledgement does not reach it, so a redelivery is recognised and
dropped: it confirms nothing, changes nothing, and asks the agent for nothing. Typing the command
twice yourself is still two commands — which is what makes the `shutdown` confirmation below a real
one.

**`shutdown` is asked for twice.** The first ask says what it costs and gives you 30 seconds to ask
again. A gateway shut down from Slack cannot be started from Slack — the bot goes offline and there
is no command left — so starting it again takes the machine it runs on.

**Who may use it is who may reach the agent**: the same `--allow` list from
[step 8](#8-add-the-channel), decided by Rundesk on its own side. A command from anybody else is
silence — nothing posted, no call made — and one fixed line in the agent's log says a command
arrived from outside the lists. `provider` is narrower again: Rundesk refuses it on any channel more
than one person may reach, because which brain answers is an agent-wide decision.

**A command typed in a thread names the channel, not the thread.** Slack's command payload carries
no `thread_ts`, so there is nothing in it that says which thread you were in. In a direct message
that is exactly the conversation you are in. In a channel a turn runs inside a thread, so `/ava stop`
typed in the channel answers *Nothing is running here* — ask in the thread the turn is in, or use
`rundesk gateways` on the machine.

**An answer longer than Slack shows on one command says so.** Slack takes a bounded number of
answers on one command's URL, so a long `agents` directory ends with a line saying the rest is past
what Slack shows rather than being cut off where nobody was told. The same question has no bound on
the machine itself.

**Markdown a brain or Rundesk wrote is not translated.** `**ava**` reaches Slack as the characters
typed, because a partial translation that touched a fenced code block would be worse than none.

**An app installed before the command existed has no command.** A slash command is granted when the
app is installed, exactly as a scope is: add it to the app — the manifest, or **Slash Commands** in
the app's settings — and then **Reinstall to Workspace**.

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
| a channel **and a thread** | a direct conversation is keyed by no thread, so it has no session |
| a plan that includes the AI features | some of them are paid; Slack decides which |

Two consequences, and both are stated rather than worked around:

- **A direct message shows no status.** The method is keyed to a thread and a direct conversation
  is deliberately keyed by none — one direct message is one conversation, which is what keeps its
  history and its session whole. The 👀 on your message is what says it was taken up there.
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

**Each has its own command.** `/ava` is one app's and `/dev` is another's, which is why the command
is named after the agent rather than after what it does — see
[the one command it offers](#the-one-command-it-offers).

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

## What the agent is told about where it is standing

Every turn carries one ordinary sentence naming the audience, because a channel's name does not say
who reads it and an agent deciding how much to disclose needs that more than it needs the name.

| Where it was said | What the agent is told |
|---|---|
| a direct message | a direct message, which nobody else can read |
| a public channel | the `<name>` channel, which anybody in this workspace can read |
| a private channel | the `<name>` channel, which its invited members can read |
| a Slack Connect channel | the `<name>` channel, which people outside this workspace can read |
| a thread in any of them | *a thread in* the same sentence |

Taken from `conversations.info` — `is_private` and `is_ext_shared` — and never from the name, which
is a stranger's text and is flattened and clipped before it travels. Where Slack will not answer,
the sentence claims the narrower audience: a channel nobody could describe is never called
externally shared. This states who can read; it prescribes no policy about what to write.

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
without opening a second websocket. Then run `rundesk gateways logs ava`: every fixed boundary the
adapter names — what arrived on the websocket, and what became of it — is a line in that log, said
once per run and carrying no message text, id or credential. A traceback it had no words for is in
`data/agents/ava/channels/slack/stderr.log`, which the gateway copies into the log only when it
collects an adapter that has already exited — never while the channel is running.

| What you see | Usually |
|---|---|
| `there are no Slack tokens` | one of the two is unset. `xoxb-` is `SLACK_BOT_TOKEN`, `xapp-` is `SLACK_APP_TOKEN` |
| `holds a user token` | the `xoxp-` token was pasted instead of the bot token |
| `signed in as a person` | the token is a user token that does not carry the `xoxp-` prefix |
| `has not been granted …` | a scope was added after the token was issued. Reinstall the app to the workspace |
| `the app-level token … was not [accepted]` | Socket Mode is off, or the token has no `connections:write` |
| `it is not in C… yet` | nobody has run `/invite @rundesk` there |
| `opening the Socket Mode websocket…` with no later `Slack said hello…` | this machine opened the websocket but Slack has not greeted it; the channel does not report ready |
| `Slack said hello…` and no `Slack sent…` line after a test message | Slack established the websocket and has sent nothing on it. The remaining causes are Slack's side: the app was not installed again after its event subscriptions changed, or the message went to a different connection — see the connection count below |
| `Slack sent an events_api frame…` with no `Slack delivered…` line after it | the frame arrived and was not decoded into a request. That is the vendor client's boundary rather than the workspace's |
| `Slack says this app has 2 open Socket Mode connections` | something else is holding a connection for the same app — another machine, or an adapter that outlived its gateway. Slack sends each event to one of them, so roughly half of what is said reaches nobody |
| `a different Slack app than the bot token was issued by` | the two tokens came from two apps. Take the `xoxb-` token from one app's **OAuth & Permissions** and the `xapp-` token from that same app's **Basic Information**, then start the gateway again. The line is a report: the channel still reports ready and keeps running, and nothing restarts on its own |
| `could not establish whether…one Slack app` | Slack would not answer `bots.info`, so the comparison was not made either way. It changes nothing else |
| `Slack delivered…` | the fixed sentence names the boundary reached; it never includes message text, member, channel, workspace, or credential values |
| the bot answers a DM and ignores a channel | it was not invited, or nobody named it. It stays silent until named |
| an answer in a DM arrives in a thread | that is deliberate: your direct message is one conversation, and the thread is only where that exchange is read |
| a DM follow-up seems to have forgotten the earlier exchange | it should not — every message in one DM is one session. `rundesk messages <agent>` shows what was recorded |
| an exchange you had inside a DM thread before this version is not remembered | back then a thread inside a direct message was a conversation of its own, so it was recorded under a key nothing looks under now, and a new message in that direct message does not reach it. Nothing was deleted — `rundesk messages <agent>` still shows it — and the direct conversation carries on from here |
| the bot ignores direct messages | **App Home** → **Messages Tab** is off. The manifest turns it on; an app made by hand often has neither |
| the command does not appear when you type `/` | the app declares no slash command, or it was declared after the app was installed — add it and **Reinstall to Workspace** |
| Slack says the command failed | nothing acknowledged it inside Slack's three seconds. Usually no Socket Mode connection is open at all: `rundesk gateways ava` |
| the command answers with a list of subcommands | the word after it is not one the adapter offers, and the list is what there is |
| typing the command does nothing at all | whoever typed it is not on `--allow` and the channel is not either. Nothing is posted for somebody the lists do not cover; `rundesk gateways logs ava` names that boundary |
| `stop` in a channel says nothing is running | a command names the channel and not the thread the turn is in — ask in the thread |
| `Could not attach: <name>.` under an answer | that file did not go. `rundesk gateways logs ava` carries the whole reason — a file that changed after it was approved, a path that no longer opens, Slack refusing the upload, or the answer's own upload budget spent before that file was reached |
| a large attachment is named as not attached every time | it is not finishing inside the answer's 8-second upload budget. The words and the reason are both honest; what the file needs is a route off the machine that is not the answer |
| `has not been granted files:write` | the app was installed before the file upload existed. Add the scope and **Reinstall to Workspace** |
| an answer arrives and its file does not, with nothing said | the delivery carried no file: Rundesk attaches only an explicitly declared absolute path, never a file the agent merely read |
| a person the agent named shows as `<@U…>` text | only the exact `<@U…>` or `<@W…>` markup is kept. A labelled `<@U…\|name>`, a lowercased id, and anything malformed are escaped on purpose |
| `Changing the brain is an agent-wide decision…` | `provider` is refused on a channel more than one person may reach |
| no typing indicator ever appears | [step 2](#2-declare-the-app-as-an-agent) was skipped, or it was done after installing and the app has not been installed again since, or the exchange is a flat direct message. Nothing is posted in its place |
| `assistant:write` is missing from **Bot Token Scopes** | the agent declaration in step 2 did not take, or the app has not been installed again since it did |
| `standing not connected` after `add` | `add` connects once and leaves nothing running — start the gateway |

**Nothing here is verified against a live Slack workspace.** Every claim above is read out of
`src/channels/slack` and out of Slack's published method reference; the adapter's own behavior is
proved offline in `tests/test_channels_slack.py`. Setting up a real app is the one step only you can
run.
