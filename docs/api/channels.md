# Channels

## channels

How an agent is reached, and how it reaches back. A channel belongs to one agent and lives in that
agent's own records, and the gateway hosting that agent is what runs the program behind it. With no
sub-verb it lists every channel on the install; with an agent it lists that agent's.

**A channel is a connection, not a place.** Connecting Discord gives an agent *one* channel that
carries private messages and every room the bot was invited to — there is nothing per-place written
down, and nothing to name. The channel **is** its adapter, so `rundesk channels add alan discord`
gives alan a channel called `discord`, and one list of ids says who may reach that agent wherever
they say it.

| Command | Does |
|---|---|
| `channels [list [<agent>]]` | every agent's channels, or one agent's |
| `channels add <agent> <adapter> --allow <id> [--notify] [--with '<adapter opts>']` | connect an agent to a platform |
| `channels show <agent> <adapter>` | everything one channel was given |
| `channels configure <agent> <adapter> [--allow <id>] [--deny <id>] [--notify]` | change who may reach it, or what is notified |
| `channels test <agent> <adapter>` | reach the platform again, and say what it found |
| `channels remove <agent> <adapter> --confirm` | take one away |
| `channels doctor [<agent>]` | what cannot be used, and exactly why |

`--allow` and `--deny` repeat, once per person or place. `--with` is handed to the adapter as one
quoted string: Rundesk parses none of it and it never reaches a shell.

### Attachments, in and out

**A local link in the agent's final answer is an attachment declaration.** `[report](/absolute/report.pdf)`
attaches a file, `![preview](/absolute/preview.png)` attaches an image, and a local
`file:///absolute/path` destination works too. Percent-encoded characters in either local form are
decoded. Rundesk removes the machine path from the posted text,
opens any readable ordinary local file in place, fingerprints it, and has the adapter reopen and
verify the same bytes before sending. It never guesses from files the agent merely read or edited.
A declaration made in an earlier finished remark is held and attached with the final answer rather
than leaking its path mid-turn. Up to ten files of 32 MiB each may go with one answer; a file that
cannot go is named safely in the answer and logged with the full reason.

**A directory on the way to the file is searched, never listed, and a refusal says which of the
things it was.** Passing through a directory and reading what is in it are two different
permissions, and asking for the second turned away a readable file standing in a directory that
granted only the first. The log line names the component at fault and the errno the machine
answered with — a symbolic link, the directory's own mode bits, a macOS privacy grant, a component
that went away between the check and the open, and something that is not a directory are five
different things to go and do. **The component at fault is not always the one the error arrived
on**: a directory nothing may search refuses the lookup of its own child, so the errno can carry the
name of a file that refused nothing, and the line names the directory above it instead. **A privacy
grant is the asking process's**, so the same file may
open from a terminal and not from a gateway; `rundesk permissions` reports that, and only for the
lineage it was proved in.

**Outgoing files are not copied or deleted.** Project output remains project output, and a temporary
Computer Use screenshot remains owned by that tool or the operating system. An adapter's
verification snapshot exists only for the send and is closed afterwards.

**Both shipped adapters send a file out; Discord takes one in as it arrives, and Slack only when the
agent asks for a message's files by name with `rundesk search --fetch`.** Discord carries the file with
the message, so a file that will not verify refuses the whole delivery. Slack has no call that takes
both: the words are posted, each file is verified and uploaded on its own, and a delivery whose file
could not go names it in the conversation and is reported failed — so nothing marks an answer
complete when a piece of it is missing. See [`../guides/slack.md`](../guides/slack.md#files-it-sends). Incoming channel files are different:
Rundesk owns their landed copies under the channel's dated `in/` directory and sweeps whole days
after 60 days, including for channels later disconnected.

```console
$ rundesk channels
channels in /Users/you/.rundesk/data/agents
AGENT  CHANNEL  REACHES                          ALLOWED  TOLD  STANDING
alan   discord  rundesk#4471, reaching you#0     2        yes   connected (pid 96144)
cole   discord  colebot#8812, reaching you#0     1        no    not connected
```

**`ALLOWED` counts entries, not people.** A `place:` entry admits everybody the platform reports as
being in that place, so one entry may be a room full of them. `channels show` prints the entries
themselves.

### What `STANDING` means

`STANDING` is asked of the kernel through the claim an adapter holds, exactly as `rundesk gateways`
asks whether a gateway is up, and the record beside it is read only afterwards — a record holds a
pid, and a pid whose process is gone is a number that now belongs to something else. `cannot tell` is
a first-class answer there for the same reason it is one in `gateways`.

**`connected` means somebody is reading it, and the gateway is what keeps that true.** An adapter
runs for months and is listened to, so one that nothing is draining is receiving messages and
recording none of them — which is what a gateway killed outright leaves behind, and what an adapter
whose reader stopped becomes. A gateway ends any adapter it is not reading, on the beat, and starts
one it *is* reading in its place after the usual hold-off; the log says so in both halves:

```console
$ rundesk gateways logs alan -n 4
[…] WARNING: channel discord: adopted from a gateway that is gone, and nothing in this gateway is reading it
[…] INFO:    channel discord: ended, because nothing was reading it — another is started once the hold-off has passed
[…] INFO:    channel discord: started as pid 91586
[…] INFO:    channel discord: connected as rundesk#4471
```

An adapter is only ever signalled once the kernel has said its claim is still held — a pid read off
a claim nobody holds is a number that now belongs to something else. There is one state left over:
a gateway killed in the instant between claiming a channel and writing down the pid leaves an
adapter nothing can name, and that one is said in the log with the path of the claim it is holding,
because a state nothing here can resolve is a state to report and not to be silent about.

### channels add

`--allow` is required, is repeatable, and takes the id that platform knows somebody by.

#### What an entry may name

| Entry | Allows |
|---|---|
| `341709...` | that sender, wherever they say it. **The plain form, and what every list held before this** |
| `sender:341709...` | the same thing, said out loud |
| `place:C01ABCDEF2G` | anybody the adapter reports as being in that place |

Only those two words make an entry typed, so a platform whose ids carry a colon keeps meaning what it
meant. An entry naming nothing — `place:` with no id — is refused where it was typed, and `--deny`
takes an entry written exactly as it stands on the list.

A place entry allows anybody who is somebody: an event with no sender behind it — a bot, a join
notice, a platform's own housekeeping — is refused however allowed the place is. **The adapter never
makes this decision**; it reports the two ids the platform knows and Rundesk decides. See
[`concepts/channels.md`](../concepts/channels.md#who-may-reach-an-agent-and-from-where).

#### What the platform wants first

**What the platform wants first.** Rundesk holds no list of what any platform needs, so what a
channel asks for comes from its adapter and is named on the refusal. The shipped **Slack** adapter
asks for two: a **bot token** (`xoxb-`, OAuth & Permissions) and an **app-level token** (`xapp-`,
Basic Information → App-Level Tokens, scope `connections:write`). A user token is refused by name.
The [Slack setup guide](../guides/slack.md) walks it through, including the app manifest, the minimum
bot scopes, and what Slack's agent-session typing indicator needs. For the shipped Discord adapter
that is three things, all of them from Discord rather than from here: a **bot token** (Developer
Portal → your application → Bot → Reset Token), the **Message Content Intent** switched on for that
bot (same page, under Privileged Gateway Intents — without it Discord blanks every message in a room
and in a thread unless it names the bot, and the gateway is closed with `4014` rather than
connecting), and your **numeric user id** for `--allow` (Discord → Settings → Advanced → Developer
Mode, then right-click your profile → Copy User ID; a username is not an id and can be changed). The
[Discord setup guide](../guides/discord.md) walks it through step by step.

```console
$ rundesk channels add alan discord --allow 341709...
the discord adapter needs 1 value before alan can use it
        DISCORD_BOT_TOKEN__ALAN   the discord adapter reads DISCORD_BOT_TOKEN, and this is alan's own
        >
alan is connected to discord
        reaches   rundesk#4471, reaching you#0
        allowed   341709...
        told      no
        needs     DISCORD_BOT_TOKEN__ALAN (set)
        settings  {}
        can       attach=True, edit=full, max_text=2000, react=True, stream=True, thread=True
        adapter   /Users/you/.rundesk/app/src/channels/discord
        keeps     /Users/you/.rundesk/data/agents/alan/channels/discord
        standing  not connected
        invite    https://discord.com/oauth2/authorize?client_id=...
        the bot is not in any server until somebody with permission adds it there
```

#### What `add` writes, and when

**`add` connects once and leaves nothing running**, which is what `standing not connected` on the
last line means — so the next thing to type is `rundesk gateways start <agent>`. The **invite** is
printed here and kept nowhere: `channels show` cannot reproduce it, so it is worth saving. A bot
already in a server has to be sent it again before it may open a thread or attach a file.

**A `FAILED` here does not always mean nothing was written.** `--notify` is marked inside the same
lock and after the row, and it has its own guard: where the channel was added and only the marking
failed, the failure says so and names `rundesk channels configure <agent> <adapter> --notify` rather
than sending somebody to add a channel that is already standing.

**`--notify` is the other half of a first setup, and nothing refuses its absence.** `--allow` is who
may *reach* the agent and, on Discord, who receives private unprompted notices; `--notify` selects
the channel adapter where the agent *speaks first*. Left off, the channel connects
and answers when spoken to and never says anything unprompted — no gateway coming up or going down,
no schedule report, no delegation handing back a result. That is a legitimate thing to want, so it
is not an error; the only sign is `told no` in the block above. The up-notice is gated on the
notified channel having reached its platform, and an agent with no notified channel counts as ready
rather than waiting for a connection that will never exist.

So **make Discord the notified channel on the first channel added**. Every allowed user receives
their own private copy while direct answers remain in the conversation that asked. Adding it later
is `channels configure <agent> <adapter> --notify`, followed by a gateway restart: the
up-notice is said once per gateway, and one already running has said it.

**An empty allow list authorises nobody, never everybody**, so leaving `--allow` off is refused —
by the verb rather than by argparse, in a sentence ending with the whole command to type. An agent
connected to a platform with nobody allowed is an agent that answers no one, and a stranger's message
is dropped in silence rather than answered with a refusal that would confirm somebody is listening.

**Nothing about a channel is written down until the adapter says it reached something.** The program
is found, asked offline what it can do, and then asked to connect; only an `ok` from that last
question writes a row. A channel that is misconfigured has to be found out about while somebody is
standing at a terminal, not at three in the morning when they ask the agent something.

#### Where the credential is kept

**The credential is read from the terminal and never passed as an argument** — `env` says why at
length — and it is written down *before* the connection is proven, deliberately: somebody who has
just pasted a bot token should not have to paste it again because the connection was refused for an
unrelated reason. `rundesk env unset <name>` empties it.

**The name a credential is kept under is the adapter's own, and it is recorded rather than worked out
again.** `channels.hosting` hands the adapter each recorded name back with its value under that same
name, so the recorded name and the name the adapter reads are one fact.

**Where the value is kept is the agent's own, though.** One bot is one identity: two agents behind
one Discord token receive the same messages and nobody reading the room can tell which of them
replied. So what is typed above is kept under `DISCORD_BOT_TOKEN__ALAN` — the same profile naming
`rundesk skills` uses, on a name `rundesk env set` already accepts — and cole's under
`DISCORD_BOT_TOKEN__COLE`. Two agents on one platform are two bots without anybody having to arrange
it.

**One name is read, and a plain `DISCORD_BOT_TOKEN` is not one of them.** There is no fallback. A
shared name is exactly the shape that lets two agents be one bot by accident, and every way of
keeping it — read second, read only when nothing scoped exists — is that accident with a longer path
to it. A channel whose own name holds nothing is `BLOCKED`, said at a terminal, rather than an agent
quietly signing in as somebody else.

The adapter is handed the value under `DISCORD_BOT_TOKEN`, exactly as it declared it. **`channels
doctor` resolves it by the same call a gateway does**, so a channel reported `READY` is one whose
credential a gateway really finds — and a value that is there and cannot be opened is reported as
that rather than as missing.

**An agent's name is used, or the agent can hold no credential — it is never mangled.** An agent
already named something a variable can be — letters, digits and underscores, starting with a letter
— has a name of its own, upper-cased. Any other agent is **refused** a credentialled channel, by
`add`, before it prompts for anything, and reported `BLOCKED` by `doctor` with no command to type,
because there is no rename verb and no honest one to suggest. Nothing is folded: `a-b` and `a_b`
would both become `A_B`, and two agents would quietly share one bot. Such an agent may still have
any channel whose adapter needs no credential.

`--with '<adapter opts>'` is anything the adapter itself takes, as one quoted string. Rundesk parses
none of it and has no list of what any platform wants — what comes back in `settings` is the
adapter's own normalised account. It is split into words the way a shell would and handed over as a
list, so nothing in it is globbed, expanded, or read as `;`, `&&` or a redirection; it is a flag
rather than a bare `--` because argparse matches positionals in contiguous runs, and a flag between
them makes the most natural spelling of `--` an `unrecognized arguments` error.

`--notify` makes this the channel adapter unprompted things go through. At most one channel per agent
may be that. The shipped Discord adapter privately resolves every allowed user; the adapter-reported
place remains the compatible destination for adapters that do not fan out.

#### Moving an existing channel onto the agent's own name

**Do this before you update to v0.41.0.** From that release a plain `DISCORD_BOT_TOKEN` is not read,
so a channel still relying on one stops working the moment the new gateway starts. Nothing rewrites,
copies or moves a value on your behalf — copying one token onto several agents would give them all
one bot, which is the thing this shape exists to prevent, and no program can create a second Discord
application for you.

The order matters, and it is: stage every scoped key first, prove it on the release you are still
running, then update, then restart. **Never any of it as an argument** — every value is typed at a
prompt or piped, so nothing lands in a shell's history.

**1 · While still on v0.40.x, put a key in place for every agent that has a channel.**

```sh
rundesk channels                             # every agent with a channel, and how each stands
rundesk env list                             # which names hold something. Hints only, never a value

# In the Discord Developer Portal, per agent: an application, its own Bot, Reset Token,
# and Message Content Intent switched on.

rundesk env set DISCORD_BOT_TOKEN__ALAN      # prompts without echoing. Or: printf %s "$T" | rundesk env set …
rundesk env set DISCORD_BOT_TOKEN__COLE
```

An agent may keep the bot it is already running as: set that agent's scoped name to the token it is
already using, and it stays the same bot with the same identity in the same servers. Every *other*
agent needs a new application, because one token cannot be two identities.

**2 · Check the staging with `env check`, which is the only verb that can answer yet.** v0.40.x
reads the plain name and nothing else, so `channels doctor` and `channels test` cannot tell you
anything about a scoped key while you are still on it — they would keep reporting `READY` off the
shared token right up to the update. What they *can* do is name every agent you have to cover:

```sh
rundesk channels                             # every agent with a channel — one key needed per row
rundesk env check DISCORD_BOT_TOKEN__ALAN    # exits non-zero until it is staged
rundesk env check DISCORD_BOT_TOKEN__COLE
```

A green `env check` for every agent in that listing is the whole of what can be proved before the
update. It says the key is there and readable; whether the token behind it is the right one is what
step 4 finds out.

**3 · Update, then restart.**

```sh
rundesk update
rundesk gateways restart <agent>             # a running adapter holds the token it started with
```

`rundesk update` restarts the gateways it stood down, so this is a check rather than a step for
those; an agent whose gateway you had stopped yourself needs starting.

**4 · Now prove it, on the release that reads the scoped name.**

```sh
rundesk channels test alan discord           # reaches the platform again. Writes nothing
rundesk channels doctor                      # exits non-zero if anything is not ready
```

Read the `needs` line: it names `DISCORD_BOT_TOKEN__<AGENT>` and says `(set)`. A `BLOCKED` here is an
agent whose key was missed in step 1, and the summary names the one command that fixes it.

**5 · Then tidy up.** Once `rundesk channels doctor` exits zero and every `needs` line names a
`__<AGENT>` name, the shared one has no reader left:

```sh
rundesk env unset DISCORD_BOT_TOKEN
```

Open the invite for each new application and add that bot where you want it — a second application
is in no server until somebody puts it there, and the old bot goes on sitting in those servers until
you remove it.

**If an agent's name cannot carry a credential** — anything but letters, digits and underscores
starting with a letter — it can hold none, and `doctor` says so with no command to type. Nothing is
folded, because `a-b` and `a_b` would become one name and two agents would share one bot. The
answers are an agent whose name can carry one, or a channel whose adapter needs no credential.

### channels configure

Changes who may reach an agent there, and which channel is the told one. **Naming nothing to change
is refused rather than reported as a success**, and so is an id named both to allow and to deny.

```console
$ rundesk channels configure alan discord --allow 220755...
alan's discord channel changed
        allowed   341709..., 220755...
```

An id that was never on the list is refused rather than passed over — *"deny 2207"* aimed at a list
that never held it is somebody typing the wrong id, and answering "done" would leave them believing
they had taken away access they had not. Taking the last one away is refused too, because a channel
with an empty list answers nobody: remove the channel instead.

There is no `--confirm` here. It is on `remove`, and the line between them is the one `skills` draws:
would somebody want to read this before it happened. Setting a channel up is a credential, an allow
list and a round trip to a platform, and none of that comes back from a copy of `data/`.

### channels test

Asks the adapter to reach the platform again with what the channel already has, and says what it found. It
changes nothing at all, including the record of what it found — a token that was reset in somebody's
developer portal is the case this exists for, and the answer to that is a sentence at a terminal
rather than a channel quietly rewritten underneath whoever is reading it.

What reaching proves is adapter-specific. Discord opens its gateway connection. Slack authenticates,
validates the granted scopes, and obtains a Socket Mode URL without opening a second websocket that
could take live events from the gateway's connection.

### channels remove

`--confirm` is required. Without it the command says exactly what it would take and takes none of it,
and exits non-zero: **a removal that did not happen is a failure.**

```console
$ rundesk channels remove alan discord
remove: this would take alan's discord channel
        take     the connection — alan would no longer be reachable on discord, and 341709... could no longer reach it there
        keep     /Users/you/.rundesk/data/agents/alan/channels/discord — what arrived through it, and what its adapter wrote
        keep     DISCORD_BOT_TOKEN__ALAN — rundesk env forgets nothing here
        nothing was removed. To go ahead:
        rundesk channels remove alan discord --confirm
```

What arrived through the channel stays, and so does the credential. Both are named in the preview
rather than left to be discovered: a removal that described more than it would do defeats the point
of describing it, and one that described less would be worse. The credential is named as the name it
really stands under — `DISCORD_BOT_TOKEN__ALAN` — because that is the name somebody would have to
type to `rundesk env unset` it afterwards.

### channels doctor

Says what cannot be used and why, names the one command that answers it, and **exits non-zero when
anything is wrong** — the way `env check` and `skills doctor` do, so a script can gate on it.

```console
$ rundesk channels doctor
alan
  discord  READY        rundesk#4471, reaching you#0
cole
  discord  BLOCKED      DISCORD_BOT_TOKEN__COLE — nothing this install can read is kept under that name
  quiet    DANGLING     there is no quiet adapter on this install — looked in ...
channels: 2 of 3 cannot be used:
        rundesk env set DISCORD_BOT_TOKEN__COLE
        rundesk channels remove cole quiet --confirm
```

**The one name a credential stands under is what is said**, and it is the one the summary tells you
to set. There is no second place to look, so naming a plain `DISCORD_BOT_TOKEN` here would send
somebody to set a value this release ignores. An agent whose name cannot carry a credential at all is
`BLOCKED` saying exactly that, and gets **no** command in the summary — there is no rename verb and
no honest thing to type.

| Verdict | Means |
|---|---|
| `READY` | the adapter is there, its credential is set, and its `--check` came back `ok` just now |
| `BLOCKED` | no name this channel's credential could stand under holds anything this install can read — including one that is there and cannot be opened, which is never read past to the shared name |
| `UNREACHABLE` | everything is in place and `--check` failed now — the platform said why |
| `DANGLING` | there is no program behind this channel any more |
| `GIVEN UP` | it checks out from here, and the gateway hosting it has stopped trying to start it |

An agent whose channels cannot be read at all is a fifth outcome and is not a verdict: it is reported
under that agent's own name — *`<agent>`'s channels cannot be read — …* — and counted in the same
denominator, because an agent whose records will not open is not an agent with no channels.

**`GIVEN UP` is the one verdict that does not come from the adapter.** This verb asks in a process of
its own, so a failure that shows itself only once an adapter is really serving — a close code the
platform will answer with for ever — leaves every question here answered correctly. When an adapter
exits `78` its gateway stops starting it for the rest of that gateway's life, and until this verdict
existed the channel was reported `READY` while nothing had hosted it for hours. `rundesk gateways
restart <agent>` is the whole of the fix, and it is what the summary tells you to type.

**It really asks the adapter**, and that platform-specific round trip is what `UNREACHABLE` costs. A
credential that is set and no longer accepted is the failure this exists to find, and nothing on
this machine can tell that from a working one: the adapter has to be asked. A channel whose
credential is missing is `BLOCKED` without paying for a round trip.

The columns are measured against what is actually there rather than fixed. The findings go to stdout
and the summary to stderr, so a script can read one and ignore the other — and the findings are
flushed first, or the summary would appear above what it summarises when both are merged into one
pipe.
