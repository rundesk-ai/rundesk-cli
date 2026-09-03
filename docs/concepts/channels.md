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

**A conversation is an identity, and where an answer is read is not part of it.** The adapter decides
which of its places are one exchange, and Rundesk keeps the history and the provider session under
that one string — so a platform detail that only decides *where a reply appears* must stay out of it.
The shipped Slack adapter learned this the hard way: keying a direct conversation by the Slack thread
gave every threaded follow-up a session and a history of its own, and a turn already running in the
same direct message did not know the new message was for it. It keys a direct conversation by the
channel alone now, and derives the reply target from the `reply_to` Rundesk already carries — which
also means a later message steering a running turn cannot move where that turn's answer lands.

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

**One caller may name its own destination instead, and it is written the same way this list is.** A
schedule may report to one place or one person's direct message on a channel of its own choosing —
`docs/concepts/schedules.md` is what that is for. It reaches the same resolver everything unprompted
reaches and replaces the notified channel there, so there is one answer to *where does this go*; it
is checked against **this** list before it is written, because a destination the list does not name
would be a way to reach a person around it; and it is never fanned out, because it is one
destination somebody chose. `channels.kept.admitted_by` reads the string either way, so `place:C0OPS`
means the same thing in both places.

**Resolving one is the adapter's, and the reason is the credential.** A sender id names a person, not
the conversation they read, and opening that conversation is a call only the adapter can make;
the string an adapter composes for a place is its own, and rundesk never parses one. So the two ids
cross the seam as themselves and the adapter answers *where* — behind
`address` in its `--capabilities`, which is what lets rundesk refuse a destination it could not
deliver at the moment somebody types it. [`../extending/adapters.md`](../extending/adapters.md) is
the contract.

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
that requires Slack's `hello`, not merely a locally opened websocket. Where Slack names the app
behind that websocket and it is not the app the bot token was issued by, the adapter says so in the
agent's log and readiness is unaffected — every event would be going to the other app's connections,
and that is a thing to be told rather than a thing this decides.

## Going out: cut to what the platform takes

**An answer is composed for the surface that will show it.** What a brain says on the way to its
answer and the answer itself are both prose it wrote, so nothing in the words tells them apart —
the phase is known where the turn runs and nowhere else. A surface that shows a turn as it happens
is sent each finished thought as the next one supersedes it, marked `remark`, and its answer is the
last thought, because the rest is already on the platform. A surface that shows nothing until the
end is sent none of them, and its answer is *every* closing thought — everything the brain finished
saying after its last tool call, joined. What it said before and between its tools is working
narration and reaches neither surface inside an answer.

**A turn that closes on nothing still answers.** Where a turn completed and said nothing after its
last tool call, a surface showing the answer alone would otherwise show a completion mark and no
reply — an answer somebody cannot find rather than one that was never made. One short factual line
goes instead, claiming neither success nor failure and nothing about the work. A turn somebody
stopped is the exception and stays silent, because they know why it is quiet.

**Read the same way for both, the second kind loses words.** Two shipped providers say several
finished things after going to work and mark none of them final, so the last thought is the last of
several and the earlier ones are commentary — commentary a quiet surface never showed. `stream` in
the adapter's own `--capabilities` is what tells the two apart; unsaid means *shows it as it
happens*, so an adapter written before the question keeps the behaviour it was written against.

**An answer written is not an answer delivered.** What `told` reports is that the words were written
to the adapter, which is microseconds; whether they reached the platform is a round trip away and
arrives back as `delivered` or `failed`. A caller that waits — the one answering somebody — is told
in the log when it waited and heard neither, because silence and success are otherwise the same
sentence, and an adapter that has stopped reading its own input produces exactly the silence a
working one is allowed to produce.

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

## Looking the other way: what the agent asks the channel

Everything above is a channel carrying a message *to* an agent. A channel is also how an agent asks a
question of the platform behind it — `rundesk search`, run by the agent mid-turn, as often as the
question needs.

**The same connection, and nothing more than it.** A search is handed the identity, allow list and
credentials the channel is hosted with, so what it can reach is what that bot was admitted to: rooms
it was invited to, and private conversations it is part of. Not a person's own messages with somebody
else, and not a room the bot was never invited to. There is no scope on the command and none
available to it.

**One shape for every platform.** Each adapter answers the same request and returns the same row —
who said it, where, when, the words, a link, and what is attached — so an agent learns this once and
an agent with no channels has no search. What a platform can actually do differs a great deal and
belongs to that platform's guide; the seam does not.

**A search that did not finish is its own answer.** Found, found nothing, stopped early, and could
not look are four states, and the third is never printed as an empty list on its own. An agent that
read a spent budget as an absence would conclude a thing was never discussed.

**Nothing a search finds is written down.** Results were said to somebody else, somewhere else, so
they are handed back and never enter this agent's records, its conversations, or a backup. The one
exception is a file: an attachment brought in by `--fetch` lands under the channel's dated `in/`
directory, under the message it came from, owned and swept exactly like one that arrived on its own.
There is no second place for it.

See [`../api/conversations.md`](../api/conversations.md#search) for the verb and
[`../extending/adapters.md`](../extending/adapters.md#search) for the contract an adapter answers.

## When a channel is not answering

`rundesk channels doctor [<agent>]` names what cannot be used and why, and exits non-zero when
anything is wrong.

| What you see | Usually |
|---|---|
| `standing not connected` after `add` | `add` connects once and leaves nothing running — start the gateway |
| the bot is online and ignores messages | the sender is not on the allow list, or the platform's message-content permission is off |
| a Slack bot answers a direct message and ignores a channel | it was not invited there, or nobody named it — see [`../guides/slack.md`](../guides/slack.md) |
| a Slack bot is connected and answers nothing at all | `rundesk gateways logs <agent>` names each boundary the websocket reached — see [`../guides/slack.md`](../guides/slack.md) |
| nothing unprompted ever arrives | no channel is `--notify` |
| the credential is set and the channel still fails | the value is kept under the adapter's own scoped name; `channels doctor` says which name it looked for |
| `rundesk search` says a channel offers no search | that adapter does not answer the `search` invocation. Nothing is wrong with the channel and nothing is retried for it |
| a search finds nothing that is plainly there | the bot was not invited to that place. A search sees what the bot sees, never what you see |
