# Writing a channel adapter

**This is what ships.** Every claim on this page was read out of the code as it stands: where it
states a field, a bound or an exit code, it is because `src/rundesk/channels/`, the one working
adapter in `src/channels/discord`, and the suites in `tests/` say so. Where the code and its own
docstrings disagree, the code is what is written here and the disagreement is named.

[`research/the-adapter-contracts.md`](research/the-adapter-contracts.md) reproduces the contract the
*previous* build published, and is a correct record of that. It is not a description of this one: the
record kinds are different, the turn states are different, the key is `say:`/`do:` and not `type:`,
and half of what it describes does not exist here. Write against that page and you produce something
this gateway cannot talk to. This page supersedes it.

[`providers.md`](providers.md) is the **other** seam — the one a brain is reached through. The two
are deliberately the same shape and are not the same contract: a channel adapter's records are keyed
`say:`/`do:` and a provider adapter's by `type:`, and the two kinds of adapter do not share a
namespace on disk.

[`gateways.md`](gateways.md) is what hosts an adapter, [`commands.md`](api/commands.md#channels) is how a
person connects one, and [`layout.md`](layout.md) is where an install keeps things.

## An adapter is a program, never a plugin

Three things follow from that and they are worth naming together.

**Rundesk does not load somebody else's code into the gateway hosting every other agent.** One
channel that raised on import would take an agent's whole gateway with it.

**An adapter author is not obliged to write Python.** The seam is a pipe carrying newline-delimited
JSON. The example at the bottom of this page is `/bin/sh`.

**A vendor library lives on the far side of the seam and never enters the gateway.** Reaching Discord
needs `discord.py`; rundesk's own code imports nothing outside the standard library. The only reason
those two facts are compatible is that the import happens in a different process.

### Where one stands

| Where | Whose it is |
|---|---|
| `paths.code()/channels/<name>` — an install's `app/src/channels/` | part of the release, replaced whole by an update |
| `data/adapters/<name>` | this install's own; never touched by an update |
| any path with a separator in it | yours, right now, wherever you are writing it |

**A bare name resolves among the shipped ones first and then among the given ones**; anything with a
separator is used as a path and is expanded for `~`. So `discord` is the adapter that ships,
`my-thing` is one somebody dropped into `data/adapters/`, and
`/Users/me/work/thing` is one being written this afternoon and installed nowhere.

The order is deliberate: a release's own adapter is the one somebody gets by typing its name, and an
install cannot quietly shadow it.

**Found by looking rather than listed.** There is no registry — `adapters.known()` reads the two
directories. A registry beside a directory of programs is two things to keep in step, and when they
drift one says the adapter is known while the other cannot produce it, so a channel is offered and
then cannot start.

**It has to be a file and it has to be executable**, and those are asked separately: somebody told
"not there" about a program that is there without its executable bit goes looking in the wrong place
entirely. `chmod +x` and give it a shebang.

### Which interpreter runs it

**Decided by rundesk and handed over on `PATH`. Never discovered by the adapter.**

If the install has built its virtualenv, `app/.venv/bin` is put on the front of `PATH` — so
`#!/usr/bin/env python3` in your shebang resolves to the install's own interpreter, a shell adapter
is unaffected, and neither had to be told anything. It goes on `PATH` rather than in front of the
argv because an adapter is an executable with a shebang of its own, and running a shell script
through `python3` is nonsense.

The build this replaces had each adapter find that virtualenv by counting parent directories. The
count was wrong for a whole release and nothing failed until somebody added a channel. **Do not count
directories, and do not go looking for rundesk.** Import what you need by name and let the failure be
an `ImportError` you can report in a sentence.

The virtualenv can be absent — a machine with no network has a working install and no packages — so
an adapter with a dependency answers `--check` with the `ImportError` as the refusal it is, rather
than pretending otherwise.

## The three invocations

| | Bounded | What it is |
|---|---|---|
| `--capabilities` | 60 s | what you can do — offline, no account, the same answer every time |
| `--check` | 300 s | sign in, and report what you reached |
| `serve` | not bounded | hold the connection open for as long as the agent is up |

**Match them exactly rather than searching argv.** An adapter that took a mistyped `--check` for a
request for its capabilities would answer a question nobody asked and look as though it worked.
Anything that is not one of the three: say so on stderr and exit non-zero.

**Nothing from rundesk's own environment reaches you except a named handful.** `PATH`, `HOME`,
`TMPDIR`, `TZ`, `LANG`, `LC_ALL` are carried through if they are set; `TERM` is set to `dumb`,
because nothing here is a terminal and nothing may draw on one. Everything else is dropped. A
variable you did not ask for is one you cannot come to depend on by accident — and the thing most
likely to be in a gateway's environment is a credential belonging to a different agent.

### `--capabilities`

**argv:** exactly `--capabilities`, and nothing after it.

**Environment:** the handful above, and nothing else. No credential, no allow list, no settings.

**stdin:** `/dev/null`, here and on `--check` both. Only `serve` gets one it can read.

**Print:** one JSON object. Read as the whole of stdout parsed as JSON, and failing that as the last
non-blank line — so a program that printed a warning before its answer has still answered.

**Exit code:** read. Non-zero is `{}`. So is a program that did not start, one that did not finish in
sixty seconds, and one that printed something that is not an object.

**`{}` is a whole answer and never an error.** Every missing field is read as the least capable
answer, so an adapter that does not recognise the flag and does something else can do nothing — which
is complete, and is not a refusal. Nothing is retried and nothing is refused for it.

Asked offline and with no account, so that **a fidelity difference is a fact rather than a guess**:
an adapter that cannot edit a message is told apart from one that can and did not.

```json
{"stream": true, "edit": "full", "react": true, "thread": true, "attach": true, "max_text": 2000}
```

That is the shipped Discord adapter's answer, and it is a fair template. **Be honest about what is in
it**, and know what it costs today: rundesk asks the question, prints the answer on the `can` line of
`channels add`, and **keeps none of it** — the `channels` table has no column for it, so `channels
show` has nothing to show and nothing anywhere reads a key. See
[what is not built yet](#what-is-not-built-yet).

### `--check`

**argv:** `--check`, followed by whatever the owner typed after `--with`, split the way a shell would
word-split it and carried through exactly. **Rundesk parses none of it and holds no list of what any
platform needs.** It never reaches a shell, so nothing in it is globbed, expanded, or read as `;`,
`&&` or a redirection.

**Environment:** the handful, plus `RUNDESK_ALLOW`, plus each credential the adapter named, under the
name the adapter named it.

**`RUNDESK_ALLOW` is set here and not only at hosting time**, and it is not decoration: an adapter
that reports where unprompted things would land does it by opening a private conversation with the
first id on the list, so one asked to connect without the list refuses before it has signed in.

**Print:** one JSON object, read the same way as above.

**Exit code:** not read. `adapters.checked` reads whether the program started and finished, and then
the object; it never looks at the code. **Exit `0` anyway, including for `ok: false`** — a refusal is
an answer, `--capabilities` on the same program *is* judged by its code, and one convention across
all three invocations is one nobody has to remember.

The distinction that matters is the other one: **a program that died without printing an object
failed; one that printed `ok: false` refused.** Both reach the caller as `ok=False`, and `why` is the
sentence that says which — and it is the whole of what a person standing at a terminal can act on.
Say what was wrong, not that something was.

**Nothing about a channel is written down until this says `ok`.** An agent whose channel is
misconfigured has to find that out while somebody is at a terminal, not at three in the morning when
they ask it something.

```json
{"ok": true,
 "describes": "rundesk#4471, reaching you#0 — a bot already in a server has to be sent this invite again before it may open a thread in a room",
 "notify_place": "1180",
 "settings": {},
 "secret": {"env": ["DISCORD_BOT_TOKEN"]},
 "invite": "https://discord.com/oauth2/authorize?client_id=…&scope=bot&permissions=…"}
```

```json
{"ok": false, "why": "there is no bot token — nothing set DISCORD_BOT_TOKEN",
 "secret": {"env": ["DISCORD_BOT_TOKEN"]}}
```

**`describes` is where a standing setup caveat rides**, because it is the one line of this answer a
person is ever shown — `channels add` prints it, `channels show` keeps it, `channels doctor` repeats
it. Anything an owner still has to go and do belongs there rather than in prose nobody will read.

| Field | | What it is for |
|---|---|---|
| `ok` | required | whether the channel may be written down at all. Anything falsy is a refusal |
| `why` | on a refusal | the sentence a person acts on. Without one they are told only that the adapter would not connect |
| `describes` | optional | one line naming what was reached, for somebody deciding whether it is the right thing. Falls back to the adapter's name |
| `notify_place` | optional | where unprompted things would land. **Required in practice if the channel is ever to take `--notify`** — a gateway coming up is answering nobody and has no conversation to reply into. Said-nothing and said-empty are kept apart |
| `settings` | optional | your own normalised account of the options, handed back verbatim as `RUNDESK_SETTINGS` when you are hosted. Anything that is not an object is recorded as `{}` |
| `secret` | optional | `{"env": [...]}` — the names you read credentials from. A single name as a bare string is accepted as a list of one |
| `invite` | optional | printed after a successful `add`, for a platform where the bot has to be sent somewhere |

**Say what you understood, not what you were told.** `settings` is what an owner will still be running
on in a year, so normalise here; the words that produced it are deliberately not kept and are never
replayed by `channels test`.

**The credential name comes back on a refusal too, and that is the whole of how rundesk knows what to
ask for.** `channels add` asks once with the allow list and no credential; an adapter that answers
`ok: false` **and names the variable it looked in** gets a prompt, and then a second `--check` with
the value set. Drop the name from the refusal and the only thing `add` can answer with is to repeat
itself.

**The name is yours and is recorded exactly as it arrives.** Rundesk hands it back at hosting time
under that same name, so the recorded name and the name you look in are one fact. Declare
`DISCORD_BOT_TOKEN`, read `DISCORD_BOT_TOKEN`, and never anything else.

**Where rundesk *keeps* the value is per-agent, and none of that crosses this seam.** One bot is one
identity, so alan's token is kept under `DISCORD_BOT_TOKEN__ALAN` and cole's under
`DISCORD_BOT_TOKEN__COLE` — the same profile convention `rundesk skills` uses — and **a plain
`DISCORD_BOT_TOKEN` is not read at all.** There is no fallback: an agent whose own name holds nothing
is started without your credential, and your `--check` refusal naming the variable is what a person
sees. You are handed the value under the name you declared, exactly as before. An adapter that wants
two credentials is still an adapter that declares two names.

### `serve`

**argv:** exactly `serve`.

**Environment:** the handful, plus:

| | |
|---|---|
| `RUNDESK_AGENT` | whose channel this is |
| `RUNDESK_CHANNEL` | the platform, which is also the channel's name |
| `RUNDESK_CHANNEL_HOME` | this channel's own directory — somewhere to put what you fetch |
| `RUNDESK_SETTINGS` | the object your own `--check` returned, as JSON text. `{}` if you returned nothing |
| `RUNDESK_ALLOW` | who may reach this agent here, comma separated |
| each name from `secret.env` | its value, out of the install's sealed store — kept under `<NAME>__<AGENT>` and nowhere else, and always handed over as `<NAME>`. A name nothing is kept under is left out rather than set empty, and a plain `<NAME>` is never read |

**stdin** is a pipe and is readable: records come in, one JSON object per line. **stdout** is a pipe
and is drained continuously by a thread of the gateway's — records go out the same way. **stderr** is
appended to `stderr.log` in this channel's directory, which the gateway rotates.

**The channel's claim is a `flock` this process holds and passes down to you.** It lives exactly as
long as you and everything you start, and the kernel drops it however that ends — a clean exit, a
crash, a `SIGKILL`, the machine losing power. That is what lets a gateway which came up after the one
that started you know you are still there and refuse to start a second adapter beside you. You never
ask about it and never touch it.

**Exit codes:**

| | |
|---|---|
| `78` (`EX_CONFIG`) | *starting me again cannot help.* Nothing starts this channel again for the life of this gateway |
| anything else, **including `0`** | held off ten seconds and started again |

`78` is the whole of the agreement, because the two sides of this seam are two processes and cannot
share a constant. Use it for a revoked token, an intent mask a platform will refuse for ever, a close
code that is not going to change. **It is read and not merely written down:** logged and restarted on
the flat ten-second hold-off, a revoked Discord token is a login attempt every ten seconds — about
8,600 a day — which is the Cloudflare ban of the machine's own address that the adapter's close-code
table exists to avoid.

**You are asked to stop before you are signalled.** `{"do": "stop"}` comes down stdin, and then
`SIGTERM` to your whole process group with `SIGKILL` behind it. **The default disposition for
`SIGTERM` is to die where you stand**, so an adapter that wants its goodbye and its cleanup to run
handles the signal — the shipped one does, and had to: the goodbye and every last write were simply
never reached before it did.

## The record vocabulary

One JSON object per line, both ways. Nothing is nested inside anything and nothing spans lines.

### What an adapter says — `say:`

Nine are recognised, and the table below has one row for each. **Anything else is ignored in
silence**, which is deliberate: rundesk may be behind an adapter, and a record it does not know is
not a channel that has gone wrong.

```json
{"say": "ready", "as": "rundesk#4471"}
{"say": "gone", "why": "the socket closed"}
{"say": "note", "level": "warning", "text": "could not bring in report.csv: HTTPException: 403"}
{"say": "failed", "id": "1754431200.123456-0-7", "why": "Discord would not take it: Forbidden"}
{"say": "delivered", "id": "1754431200.123456-0-7", "external_id": "9002"}
{"say": "arrived", "conversation": "1180", "user": "2207", "text": "what changed today?",
 "external_id": "8841",
 "attachments": [{"name": "report.csv", "at": "/…/channels/discord/fetched/8841/0", "bytes": 8}]}
{"say": "control", "conversation": "1180", "user": "2207", "control": "stop", "ref": "i-9911"}
{"say": "query", "conversation": "1180", "user": "2207", "query": "status", "ref": "i-9912"}
{"say": "configure", "conversation": "1180", "user": "2207", "provider": "codex", "ref": "i-9913"}
```

| | Required | Optional | What rundesk does with it |
|---|---|---|---|
| `ready` | — | `as` | one `INFO` line in the agent's log: *connected as …* |
| `gone` | — | `why` | one `WARNING` line. `no reason given` when `why` is absent |
| `note` | `text` | `level` | one line at that level. `level` is `DEBUG`, `INFO`, `WARNING` or `ERROR`, case-insensitive; anything else becomes `INFO` |
| `failed` | `why` | `id` | one `WARNING` line: *could not deliver — …*. `id` releases what rundesk was holding for that delivery, and the reason is kept against it for whoever settles the turn behind it |
| `delivered` | `id` | `external_id` | one line saying the answer reached the platform, naming the message it answered, and **`external_id` is kept** — see below. **Never a mark** |
| `arrived` | `conversation`, `user`, and `text` **or** `attachments` | `external_id` | the message, if that user may be answered |
| `control` | `control`, `user` | `conversation`, `ref` | one gesture, if that user may be answered and the word is one rundesk knows — see [gestures](#gestures) |
| `query` | `query`, `user` | `conversation`, `ref` | one question, answered out of what this install already knows |
| `configure` | `provider`, `user` | `conversation`, `ref` | the agent's default brain is changed |

**Say `ready` when you have the connection and `gone` when you lose it**, once per change and not
once per reconnection attempt behind it — that is how somebody tells a quiet agent from a deaf one.
Rundesk marks the channel offline on `gone`, lets the adapter recover its own session first, and
restarts an adapter that remains disconnected for the host's 120-second recovery grace period.
Messages held for that channel remain durable and are recovered only after `ready`.

`note` is for something an owner should know **that you have words for**. Anything you have no words
for goes to stderr; see [the rules](#the-rules-that-will-bite).

#### `arrived`, in detail

| Field | | |
|---|---|---|
| `conversation` | required, non-empty | whatever the platform calls one exchange — a thread, a room, a chat, a phone number. Rundesk never parses it and never shows it. The one thing that matters is that the same exchange produces the same string every time. A message with an empty one is dropped |
| `user` | required | the id that platform knows somebody by. **Checked against the allow list before anything else happens** |
| `text` | required unless `attachments` | what was said. Clipped at 64 KiB rather than refused |
| `attachments` | required unless `text` | what they attached, already fetched onto this machine — see below |
| `external_id` | optional | the platform's own id for this message. **Without it there is no redelivery guard and no `seen` mark** |
| `display` | optional | what the platform calls the person speaking. Reaches the brain, so an agent in a room can address somebody by name |
| `where` | optional | **one ordinary sentence** saying where this was said — `a direct message`, `the ops room in Acme`. Rundesk never parses it and never names a room itself; what a place is called is the one thing only you know |
| `reply_to` | optional | the earlier message this one answers — see below. Left out entirely when it answers nothing |

**`reply_to` is an object, and it is not the `reply_to` on a `deliver`.** One word, two records,
two shapes, and they travel in opposite directions: outbound it is a bare id saying *this delivery is
the answer*, and inbound it is what somebody was replying to when they wrote. Named the same because
that is the word both the platform and the person use.

```json
{"reply_to": {"id": "8800", "resolved": true, "author": "Dana", "text": "shall I deploy?"}}
{"reply_to": {"id": "8800", "resolved": false}}
```

| | | |
|---|---|---|
| `id` | required | the platform's id for the message being answered |
| `resolved` | required | whether you actually have that message. **Anything but `true` is read as no** |
| `author` | on a resolved one | who wrote it |
| `text` | on a resolved one | what it said |

**Send `resolved: false` rather than nothing when you cannot read the parent.** A reply whose parent
is unavailable is still a reply, and a brain told *they answered an earlier message that could not be
read* can say so; one told nothing is handed "yes, that one" with no idea what *that one* was.

**Do not go and fetch it.** This is the inbound path, in front of every message, and a fetch is a
round trip. Use what the platform already handed you — the shipped adapter reads Discord's `resolved`
and then its cached message, and asks for nothing.

**Anything beside `resolved: false` is discarded**, author and text both. A parent you could not read
is one you cannot describe, and a guess reaches a brain as though it were what somebody wrote.

**Rundesk bounds both before they reach a prompt** — the name flattened to one line and clipped, the
quote clipped with a marker saying so. Narrow them anyway: this is a stranger's text and the bound
that protects a prompt is the one that runs on rundesk's side.

**A message that is only a file is still a message.** Neither text nor attachments is nothing, and
nothing is recorded.

**`external_id` is worth passing.** With it, a redelivery — which every chat platform does — costs
nothing the second time, because the message lands once. Without it, two identical lines are two
things somebody said. The previous build had the column and the index and no adapter ever passed an
id through the seam, so the guard was correct and prevented nothing.

Each entry of `attachments`:

| | | |
|---|---|---|
| `at` | required | absolute path to what you fetched. **Must stand inside `RUNDESK_CHANNEL_HOME`**, must be an ordinary file, and must not be reached through a relative step |
| `name` | optional | what the platform called it — a stranger's text, flattened by rundesk and nowhere else. Falls back to the basename of `at` |
| `bytes` | optional | **what the platform said it would be — never your own measurement of what you wrote.** Checked against the file's real size, and a mismatch is refused. Reporting your own `stat()` here makes rundesk compare its measurement with its own, which agrees always: the shipped adapter did exactly that, and a download cut off part way landed and was named to the brain as whole. Leave it out entirely if the platform declared nothing; said-nothing and said-zero are different answers |

**Rundesk takes each one from there** into the agent's own account of what arrived — under the day,
under the message, under a name that is both safe and unused — and **removes what you staged either
way**, whether it was taken or refused. A file you fetch is a file rundesk removes. Do not clean up
after yourself and do not report a path you have not written.

The shipped adapter writes into `$RUNDESK_CHANNEL_HOME/fetched/<message id>/<n>` and names each file
by its position, because the platform's name is flattened and made unused in exactly one place and
that place is not the adapter.

##### Where the shipped Discord adapter answers, and what it needs to

Worth reading even if you are writing for another platform, because the *shape* is the general one:
**an adapter may move an exchange somewhere quieter, and the record that moves it is the record that
names the new place.**

| What arrives | Where the exchange goes | What `conversation` is |
|---|---|---|
| a direct message | flat, where it was said | that conversation's id |
| a room message naming the bot | a thread opened on that message | the **thread's** id |
| a message in a thread the bot opened | that thread, with nobody naming the bot again | the thread's id |
| a message in somebody else's thread | that thread, but only if the bot is named | the thread's id |
| a room message naming nobody | nowhere. An agent in a shared server is quiet until spoken to | — |

A room is somebody else's, and the reason for the thread is stronger than tidiness: a reply that
rewrites itself in place is unreadable, so an answer that arrives whole after minutes of working
needs somewhere of its own to arrive into.

**It degrades rather than failing.** Opening a thread needs `CREATE_PUBLIC_THREADS`, which the invite
now asks for — but an invite grants what it asked for once, when somebody accepts it, so a bot that
was already in a server does not have it until it is sent the invite again. When Discord refuses, the
message is answered in the room and a `note` says so once. A channel that stopped working because it
could not open a thread would be worse than one that answers in the room.

**It needs one privileged intent, and this is the whole of Discord's setup story.** `MESSAGE_CONTENT`
must be switched on for the bot — *Developer Portal → Applications → this bot → Bot → Privileged
Gateway Intents*. Without it Discord blanks the content of every guild message that does not
@-mention the bot, including every message inside a thread the bot opened itself, so the thread would
open and then nothing said in it could be read. `--check` reads the application's flags and **refuses
while it is off**, because the alternative is close code `4014` at `serve` time: not resumable, exit
`78`, and a gateway that then never starts the channel again. `GUILD_MEMBERS` and `GUILD_PRESENCES`
are still not asked for; nothing reads a member list or a presence.

### What an adapter is told — `do:`

Five, and only five exist today.

```json
{"do": "deliver", "id": "1754431200.123456-0-7", "place": "1180", "text": "Three files changed…",
 "reply_to": "8841", "cost": "codex · 2.2k input · 481 output · 78k cached · 1m elapsed"}
{"do": "deliver", "id": "1754431200.123456-2-9", "place": "1180", "text": "here it is",
 "files": [{"name": "chart.png", "at": "/…/agents/alan/home/chart.png", "bytes": 9,
            "sha256": "b1f3…"}]}
{"do": "state", "place": "1180", "external_id": "8841", "state": "seen"}
{"do": "activity", "place": "1180", "did": "run"}
{"do": "delegation", "place": "1180", "state": "handed", "who": "dev", "ask": "del-41-4e07c5",
 "provider": "codex"}
{"do": "delegation", "place": "1180", "state": "answered", "who": "dev", "ask": "del-41-4e07c5",
 "elapsed": "1m", "provider": "claude", "provider_alias": "work"}
{"do": "answered", "ref": "c-91f2", "text": "3 schedules, next at 09:00"}
{"do": "stop"}
```

| | Fields | |
|---|---|---|
| `deliver` | `id`, `place`, `text`, sometimes `files`, sometimes `reply_to`, sometimes `cost` | post it. `id` is rundesk's own handle for this piece, of the shape `<unix time>-<n>`; hand it back on a `failed` |
| `state` | `place`, `external_id`, `state` | show what rundesk says a turn is doing |
| `activity` | `place`, `did`, sometimes `ok`, sometimes `who` | show what the agent is doing, while it is still doing it |
| `delegation` | `place`, `state`, `who`, `ask`, sometimes `elapsed`, sometimes `provider` and with it sometimes `provider_alias` | show what became of work this agent handed to another agent, which brain is doing it, and what has just been done to it |
| `answered` | `ref`, `text` | the answer to a `control`, `query` or `configure` you sent, against the `ref` you gave it |
| `stop` | — | stop. The signals follow either way |

**A long answer arrives as several `deliver` records, and `files` go with the last of them.** The
words describing a file are what a reader wants above it, and a platform hangs an attachment under
the message it came with. A record carrying `files` and an empty `text` is one to take; a record with
neither is never sent.

**`reply_to` is how rundesk says *this one is the answer*.** It carries the `external_id` of the
message being answered. A delivery with it is posted as a reply to that message; a delivery without
it — running commentary, progress, anything mid-turn — is posted plainly, because a conversation
where every line quotes the same message is unreadable. **Do not invent a field of your own for
this**, and do not read the text and guess: which piece is the answer is turn state, and turn state
is rundesk's.

The shipped Discord adapter also *tints* the reply, which is the point of it: a message that names
somebody is drawn by their own client with an amber bar down the side, and a reply draws it by
pinging the author of the message it quotes. **Nothing here builds an embed and nothing sets a
colour** — the emphasis on an answer is drawn by the reader's own client, and that is the only way to
get it. Two cases get the quote dropped: a message the adapter wrote itself, where the ping would
reach the bot and leave the person waiting untinted; and a message standing in another channel, which
happens on the first answer inside a freshly opened thread, because the message that asked is still
in the room above and a reply does not reach across. A direct conversation is **not** one of them —
it was, and that was wrong: the tint is what separates the answer from the commentary above it, and
in a one-to-one conversation the reply ping is the only thing that draws it at all.

**Build the reference so a deleted message cannot cost you the answer.** Discord refuses an entire
message that quotes one it can no longer resolve — `fail_if_not_exists=False` there — and a turn runs
for minutes, which is long enough for somebody to delete their own question.

**`cost` is what the turn cost, composed by rundesk and rendered by you.** It arrives on the same
piece as `reply_to` and never on a later one — one answer is one answer, and the same number said
four times is noise. Put it **above** the words: a long answer pushes anything after it off a phone
screen, and which brain answered and what it cost are worth seeing without scrolling. Show it in
whatever quiet register your platform has, so it does not read as a sentence the agent wrote — the
shipped adapter uses Discord's `-# ` subtext. **The words are not yours to change**, and the room it
needs is already taken out of `max_text` before the text was split, so putting it above what you were
handed cannot push a piece past the limit.

#### What the agent is doing — `activity`

**Broad, countable, and disposable.** One record per thing the agent did, carrying the closed word and
nothing else. `did` is one of `read`, `search`, `run`, `edit`, `list`, `make`, `delegate`, `memory`,
`rules`, `identity` — the same list `providers/protocol.py` defines — or **empty**, which is a real
answer meaning *something happened and there is no honest name for it*: a brain thinking, or a tool
outside the closed set. Render an empty one as your own broad fallback rather than dropping it.

`ok` is present only when there is something to say about how it came back: `false` means it failed,
and `true` appears only for `delegate`, where the ending is news of its own. `who` names a subagent
and appears nowhere else.

**What a tool was given and what it answered never cross this seam**, and neither does the brain's own
name for it. A command line and a path are somebody's private business, and this is posted into a
room. The build this replaces sent the vendor's name too, and a commentary read `commandExecution`
and `imageGeneration` in front of somebody who had never heard of that vendor.

**Growing one message is yours to decide, and so is when to stop.** The shipped adapter gathers a
burst for a moment so ten tools are one write, collapses adjacent repeats to `line **(x3)**`, and
edits one message in place **for as long as that message is still the last thing in the
conversation** — anything else posted there, or anybody speaking, starts a fresh one, because
editing a message the reader has already scrolled past changes history rather than showing progress.
A surface that cannot edit posts instead and is a first-class channel; a surface that wants to show
none of it shows none of it. Correctness never depends on any of this.

**Anything you do not recognise: say so as a `note` and read on.** One record you could do nothing
with is not a channel going away.

#### Work handed to another agent — `delegation`

**A different thing from an `activity` line naming `delegate`, and the difference decides how it is
rendered.** That one is a brain reaching for its own vendor's subagent tool: it begins and ends
inside one turn, and it is disposable. This one is one rundesk agent handing a bounded task to
another rundesk agent on the same install — it **outlives the turn that handed it over**, often by
many minutes, and the person who asked is left watching a room in the meantime.

So do not fold it into the running commentary. Post it as a message of its own, and treat anything
you were growing as no longer last.

`state` is one of seven, and the list is closed. Four say where the work stands and three say what
has just been done to it:

| | What it means | How the shipped adapter renders it |
|---|---|---|
| `handed` | the work has gone to `who` | `-# 🤖 handed to **dev** · del-41-4e07c5` |
| `working-still` | it is still out, said once per twenty minutes | `-# ⏳ **dev** still working · 20m` |
| `answered` | it came back; the answer itself follows as an ordinary `deliver` | `-# ✅ **dev** answered · 1m` |
| `stopped` | a requested stop reached its terminal outcome; no answer is owed | `-# ✋ **dev** stopped · 15s` |
| `guided` | somebody put words into it while it runs | `-# 💬 updated **dev**` |
| `stopping` | somebody asked it to end — a request, never an outcome | `-# 🛑 asked **dev** to stop` |
| `carried-on` | a finished one was resumed, in the session it already had | `-# 🔁 carried on with **dev**` |

`provider` is **which brain is doing the work**, and it may arrive on any of the seven. It is the
*effective* provider — the canonical one resolved when the delegation was admitted, which is what is
actually running — and never the spelling somebody typed, which may be a relative path and may be
half an override. `provider_alias` is the account inside that provider, and it appears **only beside
a `provider`**: an account alias on its own names an account of nothing. Both are the pair
`rundesk asked show` calls the effective provider and effective account alias.

**Both are absent where nothing is known**, exactly as `elapsed` is — a delegation admitted before a
provider travelled with one has no answer to give, and rundesk leaves the field out rather than
sending an empty one. Render a line without them as the line you rendered before this existed; do
not invent a word like *unknown* to fill the gap.

**A provider may be a path**, because an adapter somebody wrote is named by where it lives. Show its
last component and never the directories above it, the way you already do for `who` on an `activity`
line: posting the whole of one publishes the owner's directory layout and their username to
everybody who can read the channel. The shipped adapter puts what is left beside the name —
`-# 🤖 handed to **dev** (codex) · del-41-4e07c5`, and with an account alias
`-# 🤖 handed to **dev** (claude · work) · del-41-4e07c5`.

`ask` is the delegation's own name, which is what somebody types to guide, stop or carry it on —
`rundesk asked <agent> say|stop|resume <ask>`. The shipped adapter shows it on `handed` and leaves it
off the rest, because by then the room has already been told it.

`elapsed` is **words and never a number** — `47s`, `20m`, `2h` — rendered by rundesk for every
platform, exactly as `cost` is. It is absent when nothing is known, which is not the same as zero.

**It measures the phase the work is in, not the age of the ask.** Work that was carried on starts
counting again from the resume, so a `working-still` after one says how long the *new* work has been
going and an `answered` after one says how long the new work took. Render what you are handed and
derive nothing from `ask`: an hour-old delegation resumed a minute ago is `carried-on` and then
silence, not `still working · 1h`.

**The last three never carry `elapsed`, and rundesk sends none for them.** They are news about
somebody reaching *into* the work rather than about the work, and "· 41m" beside `updated dev` reads
as how long the reach took. **Nor do they carry what was said**: guidance is between two agents, and
a room shown it would be reading somebody's private direction to their colleague back to them.

**At most one of these is sent per delegation per beat, and what just happened wins.** A steer that
also crossed a twenty-minute boundary is one piece of news, not two — so do not expect a `guided` and
a `working-still` in the same moment, and do not correlate them if you get both.

**There is no state for a delegation that failed.** How the work went is the *answer's* to say, and
that answer arrives a moment later as an ordinary delivery; a mark here claiming failure would be
rundesk asserting something about words it has never read.

**A state you do not recognise: render nothing for it and read on.** Rundesk may be ahead of your
adapter, and a line invented to cover a word you do not understand is worse than no line.

#### The turn states

**`seen`, `working`, `done`, `stopped`, `failed`** — and not `taken`, `running`, `finished`, which is
what the previous build's contract published and what nothing here speaks.

| | What it means | How the shipped adapter renders it |
|---|---|---|
| `seen` | the message has been written down | 👀 on the message named by `external_id` |
| `working` | the agent is working | a typing indicator in `place`, renewed on the adapter's own clock |
| `done` | the turn finished | ✅ |
| `stopped` | somebody stopped it | ✋ |
| `failed` | it did not finish | ⚠️ |

**All five have a producer.** `seen` is the one that needs no turn — a message arriving is the whole
of the event — and it is sent the moment the message is written down, including on a redelivery,
because the mark belongs to the message and an adapter that has just restarted no longer knows it put
one up. The other four say what became of a turn: `working` goes up the moment one is admitted, and
exactly one of `done`, `stopped` or `failed` when it settles.

**A terminal state names the message it belongs to, and `working` does not.** `working` is the place's
condition rather than one message's — it is a typing indicator, and a second mark there would say a
turn had been seen twice — so it arrives without an `external_id` and there is nothing to react to.
The other three always carry one.

**Put the new mark up before taking the old one down.** A message with no mark for a moment reads as
a turn nobody picked up, and the order is the only thing that decides which of those somebody sees.
If the new one will not go up, the old one staying is the failure to prefer.

## The rules that will bite

**Authorization is rundesk's, and a stranger gets silence.** You report who spoke; whether they may
be answered is decided against the channel's own record and nothing you send changes it. A message
from anybody else is never written down, never answered, and never logged — replying to say somebody
is a stranger confirms the agent is listening and spends the owner's tokens doing it. **`RUNDESK_ALLOW`
is not the authorization.** Read it only to avoid working for nothing: reacting, opening a thread or
downloading three hundred megabytes for somebody who can never be answered is waste at best, and in a
room full of people it is an agent visibly attending to a stranger it is about to ignore. Never show
the list to anybody. It is read once, when you are started — a `channels configure --allow` reaches
you when the gateway next starts your adapter, not before.

**Rundesk decides what state a turn is in; you decide only how it looks.** An adapter working out on
its own when a message had been seen would be re-implementing the turn, and two surfaces would
eventually disagree about the same run with the run's own account matching neither.

**Splitting is core's job. Do not re-split.** The text on a `deliver` is already inside what the
platform takes. **Check it and refuse it if it is not** — a text past your limit is rundesk having
failed to split, and cutting it quietly would report as whole a delivery that was not. The previous
build held the limit in each adapter, and the two drifted: Slack found that cutting at the last
newline could put a single completion line in a message of its own carrying the mention, and fixed
it; Discord still had the original rule. One copy of a rule cannot drift from itself.

**A file going out is verified twice and the second check is yours.** Rundesk resolves an explicitly
declared absolute path, opens every component with `O_NOFOLLOW` and reports
the size and digest of the descriptor it opened. **Re-open it the same way, stream it into a snapshot,
compare both against `bytes` and `sha256`, and send the snapshot rather than the path.** Between the
approval and the send a concurrent turn can replace the file — or replace a directory above it with a
link to somewhere else — and only a re-open sees that. Refuse the whole delivery on any mismatch:
posting the words and quietly leaving the file behind reports a delivery that did not happen the way
it was asked for, and nothing downstream could tell.

**Open the directories on the way for search, not with `O_RDONLY | O_DIRECTORY`.** A walk needs to
pass *through* a directory and never to list it, and asking for the larger of the two refuses a file
that opens perfectly: a directory granting `--x` answers `EACCES` to the second and hands over the
named file below it to the first. Use `O_SEARCH` (`O_EXEC`, `0x40000000`) on macOS and `O_PATH |
O_DIRECTORY` on Linux; some supported macOS CPython 3.9 builds omit the names for the Darwin flag.
Rundesk's approval asks for exactly this, so an adapter that asks for more refuses what rundesk
approved and the send fails on the far side of the seam. `O_NOFOLLOW` stays on every component and
the search descriptor still requires a directory, so a non-directory is refused exactly as before.

**Say which component would not open, and what the machine answered.** A refusal reading only *could
not be opened without following a link* was written down for a directory that was not a link, and
the file was an ordinary readable PNG — the process simply could not open that directory. Carry the
errno into the sentence and name the component at fault; a link, a mode bit, a privacy grant
and a component that went away are four different things to go and look at.

**The component the error arrives on is not always the component at fault**, and the two flags above
are exactly where they part. `O_SEARCH` refuses an unsearchable directory at that directory;
`O_PATH` opens it and lets the refusal land one component lower, on a child whose own permissions
were never consulted — so the same machine state produces two different sentences blaming two
different components, and only one of them is true. On `EACCES` or `EPERM`, ask the directory above
first: look the component up in it (`lstat` with `dir_fd`, which needs search permission there and
none at all on what it finds). Refused, the directory above is what holds the mode bit and is what
the sentence must name; answered, the refusal really is the named component's own.

**The interpreter arrives on `PATH`. Never count directories.** Covered above; it cost the previous
build a whole release.

**Never a credential on a command line, and never one in `settings`.** A command line is readable
through the process list and lands in a shell's history. `settings` is written into the channel's
record, so a token put there is a token in a file that outlives the connection. One environment
variable, named by you in `secret.env`, and no fallback file — a second place to look is a second
thing that can silently be the wrong one.

**stdout is a protocol; stderr is for what you have no words for.** One traceback across stdout is a
line no reader can parse in the middle of a stream it is parsing. Anything worth an owner's attention
that you *do* have words for is a `note`, which is a line a reader parses like every other line.
Nothing else may go to stdout — no library that prints, no progress bar, no `print` you left in.

**Flush every line as you write it.** stdout is a pipe, and a pipe is block-buffered by default: an
adapter that buffers is one whose `ready` sits unseen until a block's worth has piled up behind it.
The answer to one message must not wait behind the answer to the next. `print(…, flush=True)` in
Python; in `/bin/sh` the `printf` builtin writes straight through, which is why the example below
needs nothing.

**End your lines.** A run of more than a megabyte with no newline in it is read to its end and thrown
away, and a warning is written once. Measured before it was bounded: an adapter that wrote 300MB
without a newline took the gateway from 17MB to 735MB of resident memory, after which the kernel
ended the gateway outright, which logs nothing anywhere.

**Bound your own read too.** Rundesk's records are small, and a reader with no ceiling is the same
defect facing the other way.

**Keep what you hold bounded.** You run for months. A map with an entry per conversation and no way
out of it is a leak that shows first on the machine that has been up longest, and a background task
dropped without being cancelled goes on running for the rest of the process's life.

**Nothing you write down is the only copy.** The agent's own records hold what was asked and what
came back. An adapter keeping its own account becomes the only place something was said, and it goes
when the platform's history does.

## Every bound and number

Rundesk's, unless the last column says otherwise.

| | | What it protects |
|---|--:|---|
| ceiling on `--capabilities` | 60 s | the one place an unvetted program runs before anything is written down. The answer needs no network and no account, so a minute is already generous |
| ceiling on `--check` | 300 s | it signs in to somebody else's service over somebody else's network — and a person is standing at a terminal waiting for it |
| ceiling on `serve` | none | a program that will still be here in six months |
| one line read from an adapter | 1 MiB | what is held at once, never what may be said. Past it with no newline, the run is discarded |
| a message body written down | 64 KiB | a stranger's text arriving on somebody else's schedule. Clipped, not refused |
| attachments taken from one message | 10 | an agent's directory is not somewhere a stranger gets to fill |
| one attachment | 32 MiB | the same, by size |
| days of arrivals kept | 60 | swept whole days at a time, once a day, age taken from the directory's name and never from a modification time a restore would have reset |
| an attachment's name | 120 chars, `A-Za-z0-9._-` only | kept from the *end* — an extension is worth more than the start of a sentence somebody used as a filename. Everything else becomes `-`, which makes traversal impossible rather than merely refused |
| files one delivery may carry | 10 | de-duplicated by path first: one file named twice is one file, and a platform would post it twice |
| a message rundesk splits to | 2000 chars | what a platform is assumed to take when nothing said otherwise. Small enough to be safe everywhere |
| hold-off before an adapter is started again | 10 s | long enough not to hammer a platform that is refusing us, short enough that an owner does not notice |
| hold-off after exit `78` | this gateway's lifetime | what has to change is the channel's configuration, and putting that right ends with the gateway being restarted |
| stopping one adapter, on shutdown | the gateway's share, divided, never below 1 s | the whole shutdown has to fit inside the job's `ExitTimeOut`, and channels share that budget with schedules |
| stopping one adapter, mid-life | 5 s | the loop is held for the whole of it and the beat is fifteen seconds — and it is enough for a `SIGTERM` to be answered before the `SIGKILL` behind it |
| `stderr.log` | 256 KiB, 3 kept | moved aside when the adapter is started. A channel that reconnects noisily for a week must not fill a disk, and the beginning of the trouble is the part worth keeping |
| an adapter's last words copied into the agent's log | 20 lines, 500 chars each | the whole of it stays in the file; a megabyte of traceback would roll the rest of the day off the end of what somebody came to read |
| a display name carried into a prompt | 80 chars, one line | **both sides', and neither is a copy of the other.** Narrow it so what you send is what you meant; rundesk narrows it again because a bound that lives only on the far side of a seam is one a third-party adapter can be wrong about. A display name is somewhere somebody can write something shaped like an instruction, and a newline is how they would end our sentence and start their own |
| what one message may bring in | 10 files, 32 MiB each | *the adapter's*, and not a second copy of rundesk's — it exists so the adapter does not spend a platform's bandwidth on files that will be refused a moment later |

## The smallest adapter that is not a lie

Complete, and it runs. It reaches no platform and says so.

```sh
#!/bin/sh
# quiet — an adapter that reaches no platform and is honest about it.
set -eu

case "${1-}" in
--capabilities)
    # Every field left out is read as the least capable answer, so `{}` is a whole adapter.
    printf '%s\n' '{"max_text": 2000}'
    exit 0
    ;;
--check)
    shift                                  # whatever the owner typed after --with is now "$@"
    if [ -z "${RUNDESK_ALLOW-}" ]; then
        # A refusal, not a failure: it prints an object and exits 0, and `why` is the whole of
        # what a person at a terminal can act on.
        printf '%s\n' '{"ok": false, "why": "nothing said who may reach this agent"}'
        exit 0
    fi
    printf '%s\n' '{"ok": true, "describes": "nothing at all — this reaches no platform", "notify_place": "nowhere", "settings": {}, "secret": {"env": []}}'
    exit 0
    ;;
serve)
    printf '%s\n' '{"say": "ready", "as": "quiet"}'
    while IFS= read -r line; do
        case "$line" in
        *'"do": "stop"'*) break ;;
        *'"do": "deliver"'*)
            printf '%s\n' '{"say": "note", "level": "info", "text": "a delivery went nowhere"}'
            ;;
        esac
    done
    printf '%s\n' '{"say": "gone", "why": "rundesk asked this to stop"}'
    exit 0
    ;;
esac

printf 'quiet: %s is not one of --capabilities, --check [options] or serve\n' "${*:-nothing}" >&2
exit 2
```

It is honest in the four ways that matter: it declares only what it can do, it refuses rather than
pretending when it has not been told who may reach the agent, it answers every invocation the seam
asks for, and it never claims to have delivered anything. Matching `"do"` with a shell `case` is fine
for this and is not fine for a real one — a real adapter parses each line as JSON.

**Put it somewhere and point rundesk at it:**

```sh
chmod +x ~/work/quiet
rundesk channels add alan ~/work/quiet --allow 341709...
```

The separator matters: a bare name is looked for among the installed adapters, and anything with a
separator in it is used as a path. `~` is expanded.

> **`./quiet` on its own does not work today**, and the failure is confusing rather than loud:
> `Path("./quiet")` normalises to `quiet`, which then has no separator left in it by the time the
> program is started, so it is looked for on `PATH` and the refusal reads *"the ./quiet adapter did
> not start: [Errno 2] No such file or directory: 'quiet'"*. An absolute path works, and so does any
> relative path with a directory component that survives normalising — `ad/quiet`, `../ad/quiet`.
> Named here because it is exactly the spelling somebody reaches for first.

## What is not built yet

Said plainly, because a page that quietly omitted this would be one somebody writes against and then
cannot explain.

**What `--capabilities` says is asked for and thrown away.** It is printed once, by `channels add`,
and there is no column in the `channels` table holding it. `max_text` is the exception and is read —
out of the channel's `settings`, where a `--check` may put it — so an adapter that reports one there
is split to it and one that does not gets a flat 2000. Declare your real limit anyway, and go on
checking the text you are handed, because that check is what catches the day the two disagree.

**A delivery is correlated with what became of it, but never with a mark.** `{"say": "delivered",
"id": …, "external_id": …}` is read: rundesk writes down that the answer reached the platform, naming
the message it answered. It does **not** turn into a `done` — it did once, and that was wrong, because
a turn that failed still delivers a sentence saying so and the acknowledgement cannot tell the two
apart. What a turn came to is decided by the turn. The `id` on a `failed` is read the same way;
`retry_after` with it is not — and on the shipped Discord adapter it is not even reachable, because
`discord.py` raises the one exception carrying it only when a ceiling rundesk does not set is
configured. Send it if your platform gives you one; nothing acts on it yet.

**`external_id` on a `delivered` is worth passing, and this is the only moment rundesk can learn
it.** It is what the *platform* called the message you just posted, and rundesk keeps it against its
own `id` for that delivery — so something rundesk sent can later be replied to. A schedule that says
`💻 Working on…` puts its report under that notice twenty minutes later by quoting exactly this. An
adapter that acknowledges without one is a whole adapter and nothing fails: the report is then posted
on its own rather than as a reply, which is the honest outcome for a platform that has no ids.

**`place` on an `arrived` is read by nothing.** The shipped adapter sends `"dm"` or `"room"` and
rundesk keeps neither. `display` and `where` **are** read — both reach the brain as part of the turn,
which is how an agent in a shared room can name the person it is answering and say which room it is
standing in. They were dead for a while and this page said so.

**There is no `query-result`.** That is the previous build's contract and is named here only because
somebody will arrive from that page looking for it.

`control`, `query` and `configure` **do** exist, and this page said for a while that they did not —
which was wrong, and wrong in the way that matters most, because somebody writing a third-party
adapter against it could not implement a slash command at all. The shipped Discord adapter sends all
three and the gateway answers them; the answer comes back as `{"do": "answered", "ref": …, "text":
…}`, which is the fifth `do:` record. They are in the `say:` table above, where they belong — the
correction was made in this paragraph first and the table went on saying *five* for a while longer,
so the page contradicted itself two hundred lines apart about the very thing it was correcting.

<a id="gestures"></a>
### Gestures — the words rundesk knows

**Closed sets, and that is the whole of their value.** A gesture whose name is whatever the caller
typed is a command runner with a chat window in front of it, and a word absent from these is a word
the gateway does nothing about, however a platform spells it. Send the wire word, not the label you
show a person.

| | Words |
|---|---|
| `control` | `stop`, `forget`, `restart`, `shutdown` |
| `query` | `status`, `version`, `agents`, `skills`, `schedules`, `delegations` |
| `configure` | takes `provider` — a value, not a word from a set |

`forget` is the wire word and *new* is what a person is usually offered: the gesture starts the next
message fresh, and *forget* says what happens to the session while *new* says what they get.

**Answer with `ref` or not at all.** Put your platform's own id for the waiting interaction on the
gesture, and rundesk hands it back on `{"do": "answered", "ref": …}`. Without one there is nothing to
complete, and somebody watches a spinner until their platform gives up. A gesture is answered out of
what this install already knows and **never by starting a turn**, so the answer comes back in
milliseconds; a control that really does take time says so through the turn's own outcome instead.

**`agents` is the private, install-wide directory.** An authorized user receives every known agent,
not only the agent whose Discord connection received the gesture. Each agent is exactly two Markdown
bullet lines:

```markdown
- **ava** (codex) — coordinates release work
  - Skills: managing-rundesk, writing-plans
```

Agent names and each agent's skill names are sorted case-insensitively, with deterministic ordering
when case alone is not enough. A provider path is reduced to its final component so the machine's
layout is not disclosed; a missing provider is `provider unknown`, and an unreadable one is
`provider cannot be read`. A missing or empty description is `no description`; one that cannot be
read is `description cannot be read`. No granted skills is `none`; grants that cannot be read is
`cannot be read`. The zero-agent answer is exactly `No agents.` None of these states starts a
provider turn, and an unreadable field never makes its agent disappear.

**`delegations` is private and conversation-scoped.** The adapter supplies the current platform
conversation as `conversation`; Rundesk resolves that to its durable conversation only after the
configured identity has been authorized. Named-agent work is shown once with its stable id, safe
one-line task identity, lifecycle state, originating turn/session, current delivery target, and
timing. A later fresh turn labels the original session as reset/replaced. Returned work stays
visible through review; reviewed work falls out after a later turn makes it stale. Provider-local
helpers are separate and limited to lifecycle events reported by the current provider session, so
the response explicitly calls that visibility partial. No prompt, result, provider tool name, or
session handle is returned, and the query never starts a provider turn or changes delegation state.

**The shipped Discord adapter never cuts a private slash answer at its message limit.** It sends the
first piece and every continuation as ordered ephemeral followups to the interaction that supplied
`ref`, preserving every character in order. This applies to `agents`, `skills`, `schedules`,
`delegations`, and any other gesture answer long enough to need more than one Discord message. If Discord refuses a
continuation, the adapter logs the refusal and attempts a private incomplete-response warning so the
delivered prefix cannot be mistaken for the whole answer.

**A stranger's gesture is dropped in silence**, exactly as a stranger's message is. Narrowing it on
your side first is worth doing so nobody is shown a spinner for an answer that will never come — but
that is to avoid visible work, and it is never the decision.

**Nothing downloads on rundesk's side.** The adapter holds the credential and rundesk does not; the
adapter fetches, and rundesk decides where it lands. The previous build's page has that the other way
round on the way out and is right about the way in.

## How to check your adapter

**By hand, which is most of it.** Both questions are ordinary programs answering on stdout:

```sh
./quiet --capabilities
RUNDESK_ALLOW=341709... ./quiet --check
RUNDESK_ALLOW=341709... MY_TOKEN=… ./quiet --check --room 9930
./quiet nonsense; echo $?          # 2, and the complaint on stderr
```

Read what comes back with `python3 -m json.tool` if you want it checked as JSON. Then the three things
that are easy to get wrong and invisible from a successful run:

- **stdout carries the object and nothing else.** `./quiet --check >/dev/null` should show you every
  line you meant to put on stderr, and no others.
- **`ok: false` still exits `0`.** `echo $?` after a refusal.
- **`serve` flushes.** `./quiet serve | cat` should print `ready` immediately, not when the process
  ends.

**Then through rundesk.** Against a scratch root, never `~/.rundesk`:

```sh
export RUNDESK_HOME=/tmp/scratch-rundesk
rundesk agents add alan --provider anthropic
rundesk channels add alan ~/work/quiet --allow 341709...
rundesk channels show alan ~/work/quiet
rundesk channels test alan ~/work/quiet    # connect again; changes nothing
rundesk channels doctor
```

The channel is addressed afterwards by exactly the string that was typed, so use one spelling. From
a checkout, `./dev --home /tmp/scratch-rundesk channels …` does the same thing and refuses to point
at the real install.

`channels add` prints what it wrote down. The `can` line is your `--capabilities` answer, printed
there once and kept nowhere, so it is the only place you will ever see it; `keeps` is the directory
that becomes your `RUNDESK_CHANNEL_HOME`; `standing` is asked of the kernel through the claim.

**`rundesk channels doctor` really connects**, exits non-zero when anything is wrong, and answers in
one of four words:

| | What it says about your adapter |
|---|---|
| `READY` | it is there, its credential is set, and `--check` came back `ok` just now |
| `BLOCKED` | a name in your `secret.env` has no value on this install. No round trip was paid |
| `UNREACHABLE` | everything is in place and your `--check` said no. The `why` you wrote is the line printed |
| `DANGLING` | there is no program at that name any more — moved, renamed, or its executable bit lost |

**And `serve` is only ever exercised by a gateway.** `rundesk gateways run <agent>` hosts one in the
foreground; what your adapter says lands in that agent's day log in `data/agents/<name>/logs/`, and
what it wrote to stderr lands in `data/agents/<name>/channels/<kind>/stderr.log` — where `<kind>` is
the channel's name flattened the way a filename is, so a path-form adapter gets a long one. Watch
both. The
first pass of the loop is where a channel that cannot start says so, and it says it once rather than
every fifteen seconds.
