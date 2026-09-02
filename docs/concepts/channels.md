# How an agent is reached, and how it reaches back

A channel is a connection between one agent and one platform. The gateway hosting that agent runs the
adapter behind it; the adapter owns the platform, and Rundesk owns access, turn state, history and
delivery.

The verbs are [`../api/channels.md`](../api/channels.md); writing an adapter is
[`../extending/adapters.md`](../extending/adapters.md). Setting one up is
[`../guides/discord.md`](../guides/discord.md) or [`../guides/slack.md`](../guides/slack.md).

## A channel is a connection, not a place

Connecting Discord gives an agent **one** channel that carries private messages and every room the
bot was invited to. Nothing is written down per place and there is nothing to name: the channel *is*
its adapter, so `rundesk channels add alan discord` gives alan a channel called `discord`, and one
list of ids says who may reach that agent wherever they say it.

A channel is found by its platform because a channel *is* its platform — one connection per agent, so
the kind is both the name somebody types and the row's identity.

## One exchange in the world is one conversation here

A direct message and a room are different exchanges and get different conversations. Uniqueness is
stated in the table, and the lookup is `INSERT … ON CONFLICT DO NOTHING` followed by a read — so two
gateways racing to record the same arriving message end up with one conversation between them rather
than two.

**A message that has already landed lands once.** The platform's own id is written down behind a
partial unique index, so a redelivery — which every chat platform does — costs nothing the second
time.

**A stranger's message is never recorded at all.** Whether somebody may be answered is decided before
anything is written, because a record of a message is a thing an agent could later be asked to read.
An empty allow list authorises nobody, never everybody.

## Who may reach an agent, and from where

**One list per channel, and each entry names one of two things.** A bare entry is a sender id and
always was, so every list written before this existed means exactly what it meant. A typed entry says
which kind of thing it names.

| Entry | Allows |
|---|---|
| `2207` | that sender, wherever they say it |
| `sender:2207` | the same thing, said out loud |
| `place:C0OPS` | anybody the adapter reports as being in that place |

The column is a JSON array of strings either way, so there is no second column and nothing to carry
forward. `channels.kept` is the one place a string is read as either kind, and `channels.hosting`
asks it about every message and every gesture — one rule over one list, because two rules would
eventually disagree about the same person, and the one they disagreed about would be the one holding
a control.

**The decision is made against two stable ids and never against a word.** An adapter reports `user`
and `external_place`; `display` and `where` are sentences it composed for a person to read, and a
display name is somewhere a stranger writes whatever they like. **A place entry allows anybody who is
somebody** — a record with no sender is an event rather than a person, and admitting one because of
where it happened would make a place entry a way in for anything that can post there.

The adapter is handed the two lists apart, as `RUNDESK_ALLOW` and `RUNDESK_ALLOW_PLACES`, and reads
them only to avoid working for nothing. An adapter that reports no place can still be reached by
naming a sender, which is what every channel could do before this existed.

**At most one channel may be `notified`**, held by a partial unique index. That is the channel gateway
notices, scheduled results and other unprompted messages go to; it does not select one person. The
shipped Discord adapter privately gives every user on that channel's allowlist one copy. The channel
is moved in one transaction rather than set directly, because a caller that clears the old one and
then fails to set the new leaves an agent that tells nobody anything.

## The adapter is a child, and its claim is the check

An adapter takes an exclusive `flock` on its own lock file and **the descriptor is passed to the
child**, so the claim lives exactly as long as the child. The kernel drops it however that ends — a
clean exit, a crash, a `SIGKILL`, the machine losing power — so a gateway that came up after a hard
stop can tell a live adapter from a stale record without trusting anything written down.

**A thread per adapter owns the stream; the loop owns the process.** A pipe nobody drains fills at
64 KB, after which the adapter blocks for ever writing into it — which looks exactly like a hang and
appears only once it has said enough. The gateway's loop sleeps fifteen seconds at a time, so
draining on the loop *is* that bug. The thread reads lines and records them; the loop asks only
whether the child is alive, starts one that is not, and stops them all at the end.

`STANDING` in a listing is asked of the kernel through that claim, exactly as `rundesk gateways` asks
about a gateway. `connected` means the adapter earned the readiness signal it reports; for Slack,
that requires Slack's `hello`, not merely a locally opened websocket.

## Going out: cut to what the platform takes

The cutting is in Rundesk, not in each adapter, and that is the whole reason the module exists. The
build this replaces held the limit in the adapter — 1900 in Discord's, 3800 in Slack's — and the two
drifted: Slack fixed a case where cutting at the last newline put a single completion line in a
message of its own carrying the mention, and Discord still has the original rule. One copy of a rule
cannot drift from itself.

Three things it gets right that a naive split does not:

| Rule | Prevents |
|---|---|
| a cut landing more than halfway back is taken at the limit instead | a ten-thousand-character paragraph going out as one short message and one enormous one |
| a fence open at the cut is closed and reopened, **with room kept for both** | a code block rendering as one broken block and then a page of unformatted text |
| a message is never empty | a platform refusing it, arriving as a failed delivery for something nobody needed sent |

Correctness never degrades here — only fidelity. What goes out says what it meant to say, or it is a
named failure.

## Files across the seam

**The adapter downloads and Rundesk decides where it lands.** The adapter holds the credential and
Rundesk does not; Rundesk owns the filesystem and the adapter does not. So the adapter fetches into
its own directory, says where it put each one, and Rundesk takes it from there.

**A download that succeeded is not a file that arrived.** The staged path must stand inside that
channel's own directory, be an ordinary file rather than a link or a device, and hold exactly as many
bytes as the platform said it would.

**A name from a platform is a stranger's text.** Anything outside letters, digits and `-_.` goes, so
traversal is not something to defend against: a name with no separators cannot reach out of the
directory it is written into. Sanitising alone is not enough — `report v2.csv` and `report-v2.csv`
both flatten to the same name — so a name that is already taken is made unique rather than
overwritten.

| Bound | Value |
|---|---|
| files per message | 10 |
| bytes per file | 32 MiB |
| characters in a stored name | 120 |
| days an arrived file is kept | 60, swept whole days at a time |

**Outgoing files are not copied or deleted.** Project output remains project output and a temporary
screenshot remains owned by the tool that made it. Rundesk owns only the landed copies under the
channel's dated `in/` directory.

## When a channel is not answering

`rundesk channels doctor [<agent>]` names what cannot be used and why, and exits non-zero when
anything is wrong.

| What you see | Usually |
|---|---|
| `standing not connected` after `add` | `add` connects once and leaves nothing running — start the gateway |
| the bot is online and ignores messages | the sender is not on the allow list, or the platform's message-content permission is off |
| a Slack bot answers a direct message and ignores a channel | it was not invited there, or nobody named it — see [`../guides/slack.md`](../guides/slack.md) |
| nothing unprompted ever arrives | no channel is `--notify` |
| the credential is set and the channel still fails | the value is kept under the adapter's own scoped name; `channels doctor` says which name it looked for |
