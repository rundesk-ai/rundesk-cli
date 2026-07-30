---
name: write-a-channel-adapter
description: How to reach a Rundesk agent from your own messaging platform — the whole contract, and a working adapter in thirty lines.
---

# Write a channel adapter

Rundesk does not know what a message is. It runs **your program**, holds it open for as
long as the agent is up, reads what you say arrived, and tells you how the turn that
followed is going. That program is an adapter, and this is everything it has to do.

It is a program and not a plugin on purpose: Rundesk never loads your code into the gateway
that runs every other agent, and you are not obliged to write Python. An adapter can be a
shell script.

Your adapter answers **two questions**. Whether it can reach what it was pointed at, and
one conversation.

## Question one: can you reach it?

Run with `--check`, followed by whatever options the owner typed. Connect, sign in, verify
you can actually see the place you were given, print one JSON object, exit `0`:

```json
{"ok": true, "settings": {"space": "9930", "room": "1180"}, "secret": {"env": "MY_TOKEN"}, "describes": "#operations in Acme"}
```

| | |
|---|---|
| `ok` | whether the owner should be allowed to add this channel at all |
| `settings` | everything you will need next time, in your own words — handed straight back and never read |
| `secret` | where you found the credential, so it can be shown as present without being shown |
| `describes` | one line naming what you can see, for a person deciding whether it is the right place |
| `why` | when `ok` is false, what was wrong and what to do about it |

**Take a minute if you need one, and no longer in silence.** A check may say nothing for
a minute and take five altogether before it is given up on and treated as having failed —
generous for a slow sign-in, and finite because somebody is standing at a terminal waiting
for it. Say something on stderr if you are going to be a while.

**Nothing is written down until you say `ok`.** An agent whose channel is misconfigured
must find out while somebody is typing the command, not at three in the morning when
somebody asks it something. If you cannot sign in, cannot see the room, or were given
options you do not understand, say so and say `ok: false` — a channel that was never added
is a better outcome than one that is silently deaf.

**The options are yours, not ours.** Everything after `--` on the command line reaches you
exactly as typed. Rundesk does not parse it, does not validate it, and has no list of what
your platform needs. Whatever your surface calls its places — a server, a workspace, a
room, a number — those words live in your adapter and nowhere else.

**Say `ok: false` and still exit `0` if the refusal was considered.** What is read is the
answer, not the code — but a program that dies without printing one is a program that
failed rather than a check that refused, and the difference is what an owner is shown.

**Say what you understood, not what you were told.** `settings` is what comes back to you
next time, so normalise it here: resolve a name to an id, drop what you ignored, fill in
what you defaulted. What you return is what an owner will be running on in a year.

## Question two: carry one conversation

**We run your program and hold it open.** It runs for as long as the agent's gateway does,
which is weeks. It is not started per message, and it is never polled: a reply that lands
after somebody has asked again is a reply that failed.

**You are told where you are, through the environment:**

| | |
|---|---|
| `RUNDESK_CHANNEL` | this channel's name, the one the owner added it under |
| `RUNDESK_AGENT` | whose channel it is |
| `RUNDESK_CHANNEL_HOME` | yours alone, and it lasts: anything you must remember between restarts |
| `RUNDESK_SETTINGS` | the object your own `--check` returned, handed straight back — `{}` if you returned nothing |
| `RUNDESK_ALLOW` | who may reach this agent here, comma separated. The first is the owner |

All five are always set, and `RUNDESK_SETTINGS` is `{}` rather than absent when you have
nothing kept. The one variable you named in `secret` is set too, and nothing else from
the owner's environment reaches you — so name it, or you will not have it.

**`RUNDESK_ALLOW` is not the authorization, but do use it to avoid working for nothing.**
Rundesk checks who may be answered and still does — you cannot get that wrong, and a
message from anybody else is dropped whatever you report. What you *can* get wrong is
doing expensive or visible work first: downloading what somebody attached, opening a
thread, posting anything at all. All of that happens before Rundesk has seen a word, so
for somebody who can never be answered it is waste at best and, in a room full of people,
an agent visibly reacting to a stranger it is about to ignore.

So check it before you *act*, and let Rundesk decide whether to *answer*. And do not show
the list to anybody: it is who can reach this agent, which is not a thing to hand out.

**The same four are set while you are being checked**, except `RUNDESK_SETTINGS` — you
have not returned any yet. So `RUNDESK_CHANNEL_HOME` is there and is already made, which
is what lets a credential in a file be found by the check that has to prove it.

**You report on stdout, one JSON object per line**, flushed as it happens:

```json
{"type": "ready"}
{"type": "arrived",  "conversation": "1180", "user": "2207", "text": "what changed today?", "ref": "8841", "direct": false}
{"type": "control",  "conversation": "1180", "user": "2207", "control": "stop", "ref": "8842"}
{"type": "configure", "conversation": "1180", "user": "2207", "provider": "claude", "ref": "8844"}
{"type": "query",    "conversation": "1180", "user": "2207", "query": "status", "ref": "8843"}
{"type": "gone",     "why": "the socket closed"}
```

**stderr is yours.** Say what went wrong there; it is kept, and it is never mistaken for
what you reported.

That is the whole of what you say. Six kinds of record, and only `arrived` starts a brain turn.

**What each record needs**, and nothing else is required of you:

| | must have | may have |
|---|---|---|
| `ready` | | |
| `arrived` | `conversation`, `user` | `text` · `ref` · `direct` · `attachments` · `where` · `called` · `parts` · standard channel context · prompt override/append/replaces |
| `control` | `conversation`, `user`, `control` | `ref` |
| `configure` | `conversation`, `user`, `provider`, `ref` | |
| `query` | `conversation`, `user`, `query`, `ref` | |
| `gone` | | `why` |

**`usage` may name the model that answered.** `model` is there when the brain said which
one it was and absent when it did not, because nothing here guesses. Everything else on
that record is a count of tokens: `input` is fresh, `cached` is re-read, and an absent one
means the brain could not tell rather than that it was zero.

**`session` is the one that answers "how big is this conversation now".** The others say
what the turn was billed for; this says the size it ended at, so somebody can decide
whether to start a fresh one — and it falls when a conversation is compacted. Lead with it
where a brain reports it, and show what you always showed where one does not. It is a
count of tokens and is nothing to do with the opaque session handle a turn is resumed on,
which never reaches a surface at all.

**A gesture is checked the same way a message is.** A `control` from somebody not allowed
is dropped exactly as their message would be, and you are told nothing either way — so a
button or a command your surface shows to a whole room is safe to show, and will simply do
nothing for anybody who may not use it. Do not build your own check for it, and do not
promise the person anything you have not been told happened.

**A query is read-only gateway information, never an arbitrary command.** The closed list
is `status`, `version`, `agents`, and `help`. Rundesk authorizes it exactly as it authorizes
a message or control, starts no brain turn, and answers with a `query-result` carrying the
same `conversation`, `query`, and `ref`, plus `text`. Correlate that `ref` to the platform
interaction that asked and keep the answer private where the platform supports private
responses. Never offer a generic command or arguments: that would expose mutating gateway
operations through a record whose contract promises read-only inspection.

**A provider change is a configuration request, not a message or generic command.**
Report `configure` with the provider as the owner typed it. Because this changes an
agent-wide default, Rundesk accepts it only from a single-user channel; membership in a
shared room is not agent administration. It proves the adapter can run, changes the
default, and forgets this conversation's provider sessions in one transaction. It answers
with `configure-result`, carrying the same `conversation` and `ref` plus private `text`
for the interaction that asked. A turn already running keeps the provider it began with;
the next message waits and starts fresh rather than steering the old provider.

**`did` is what a tool did, and the list is closed.** It is one of exactly eleven words —
`read`, `search`, `run`, `edit`, `list`, `make`, `delegate`, `memory`, `rules`, `profile`,
`identity` — or it is absent, and absent is common. Show a mark or a word of your own for
each.

**The last four are a file the agent lives by being rewritten**, and they are apart from
`edit` on purpose: `MEMORY.md`, `AGENTS.md`, `USER.md` and `SOUL.md` are what an agent *is*
between turns, so one of them changing is different news from a working file changing.
They name what changed rather than what was done — the act is always the same one — so a
surface with nothing but the raw word still reads. Give each its own mark; folding them
back into `edit` throws away the only part a reader wanted. `profile` is the odd one and
worth wording carefully: `USER.md` is what the agent knows about the *owner*, so it is not
the agent's own the way the other three are.

**Do not show `name`.** It is the brain's own identifier for the tool — `commandExecution`
on one, `Bash` on the next — and putting it in front of a reader means putting one
vendor's vocabulary in front of somebody who has never heard of that vendor. It is in the
record so an account can be read back afterwards, not so it can be displayed. Show the
verb, and when there is none say something true and general: a brain that gave no verb did
something this vocabulary has no word for yet, and its identifier is not a translation
of that. A `did` you do not recognise cannot happen today
and would mean this list had grown, so treat it the way you treat an absent one.

**One channel is one place, and one `add` may make several.** Two kinds of place — private
messages and rooms full of people — are **two channels**, not one channel that branches.
That is not a style preference: a channel carries the list of who may reach the agent
through it, and the people who may speak to an agent in a public room are not the people
who may speak to it in private. One channel spanning both means one allow-list spanning
both.

So your `--check` reports the kinds of place it can actually reach, and rundesk writes one
channel for each. **Work out what those are rather than asking** — you are signed in by the
time you answer, so anything the platform can tell you is something an owner should not
have to look up and paste. Ours asks Discord which servers the bot is in; it used to
require the id, which was asking somebody to go and copy a number out of a URL to answer a
question the adapter could answer itself.

```json
{"ok": true, "secret": {"env": "MY_TOKEN"},
 "shapes": [
   {"suffix": "dms",   "describes": "direct messages to acme-bot",
    "settings": {"dm": true},
    "fills": []},
   {"suffix": "rooms", "describes": "#ops in Acme",
    "settings": {"room": "1180"},
    "fills": ["channel", "server"]}
 ]}
```

An owner who typed `channels ava add acme …` gets `acme-dms` and `acme-rooms`. **Reporting
no shapes at all is a whole adapter** — it gets exactly one channel, under the name that was
typed, which is what every adapter did before this existed.

Three things belong to a shape and not to the whole:

- **`settings`** — narrowed to that place and nothing else, so the direct-message channel
  is told nothing about a room and cannot drift into answering in one.
- **`instructions`** — an optional adapter-specific addition for that kind of place. It is
  written into the record where an owner reads and rewrites it, and it appends after
  Rundesk's trigger instruction rather than replacing it.
- **`fills`** — the pieces of a place you promise to supply, which an owner writes as
  `{where.channel}`. Declare them and they are checked when an owner writes them; leave them
  out and `{where}` on its own is all anybody can use.

**Say where it was said, and who said it — in the words your surface shows.** `where` is
what a person reading your platform would call the place (`#ops on the Rundesk server`, `a
direct message`, `the thread 'what changed today?' under #ops`), and `called` is the name
your platform shows for the person, not their identifier. `parts` is that same place broken
up — `{"channel": "#ops", "server": "Acme"}` — under the names you declared in `fills`, so
an owner can say "you are in {where.channel}" without dragging the server along with it. A
phrase is all `where` can ever be; the parts are what makes it writable. Both are optional and separately
so; say neither and everything works exactly as before.

Also report the standard context your platform can supply: `channel_name`, `channel_id`,
`channel_parent_name`, `channel_parent_id`, `channel_thread_name`, and
`channel_thread_id`. These describe a destination, an optional containing place, and an
optional nested conversation without teaching Rundesk platform nouns. A Discord server is
a parent place; an email adapter may use a mailbox there; an iMessage adapter may leave it
empty. `conversation` remains the stable identifier for the exact exchange.

Set `direct` to `true` for a private conversation and `false` for a public room or thread;
Rundesk uses that trigger to select its standard instruction. If your adapter needs
different wording for one arrival, `prompt_override` replaces only that trigger
instruction and `prompt_append` adds wording after it. Neither can replace Rundesk's core
instruction. An adapter shipped with Rundesk may use `prompt_replaces` to identify one
exact default that an older shipped version stored as owner instructions; arbitrary
adapters cannot remove owner text, and anything the owner changed remains additive. Keep
platform-specific variables and wording inside your adapter.

Say them anyway. Without them a brain is handed the words and nothing else, so it answers a
room of forty people in the same voice it uses for a direct message, and the person it is
talking to is a number it never sees. They reach the brain the way everything reaches it —
named in the words of the turn — and they are never a control: where an answer goes is
decided from `conversation` and never from these, so nothing a sender can type in their own
display name can redirect anything. Rundesk flattens both to one line and clips them before
they go anywhere, so a name with a newline in it cannot end rundesk's sentence and begin one
of its own.

**Attachments go both ways, and both are files already on this machine.** What somebody
attached arrives on `arrived` — download it yourself, put it somewhere under your own
`RUNDESK_CHANNEL_HOME`, and report `{"name": …, "at": …}` with an absolute path. Anything
that is not a readable file here is dropped rather than passed on, because the brain that
would open it runs here and has no credential for your platform. What the *agent* made
arrives on `answer` the same way, already checked to be inside where that agent works —
send it if your surface can, and ignore it if it cannot.

`conversation` is whatever your platform calls one exchange — a thread, a room, a chat, a
phone number. Rundesk never parses it and never shows it to anyone; it is the key a
conversation's session is kept under, so the only thing that matters is that the same
exchange produces the same one every time. `user` is who spoke, in whatever your platform
calls people. A message needs `text` or `attachments` — words, or something attached, or
both — so a photograph sent with nothing typed is an ordinary message and not a broken one. `ref` is what a mark would attach to, if your platform has marks.

**You are told how the turn is going, on stdin**, one JSON object per line:

```json
{"type": "state",  "conversation": "1180", "run": null,     "state": "taken",   "ref": "8841"}
{"type": "state",  "conversation": "1180", "run": "7-a3f1", "state": "running", "can": {"steer": true}}
{"type": "tool",   "conversation": "1180", "run": "7-a3f1", "id": "1", "name": "Bash", "did": "run"}
{"type": "result", "conversation": "1180", "run": "7-a3f1", "id": "1", "ok": true, "summary": "3 files changed"}
{"type": "think",  "conversation": "1180", "run": "7-a3f1", "text": "The error is in the parser."}
{"type": "usage",  "conversation": "1180", "run": "7-a3f1", "input": 1200, "output": 340, "cached": 8000, "session": 9200, "model": "…"}
{"type": "said",   "conversation": "1180", "run": "7-a3f1", "text": "I'll look at the logs."}
{"type": "said",   "conversation": "1180", "place": null, "schedule": "nightly", "began": true, "text": "💻 Working on 'nightly' — I will report back when it is done."}
{"type": "said",   "conversation": "1180", "place": null, "schedule": "nightly", "text": "Nothing broke overnight."}
{"type": "answer", "conversation": "1180", "run": "7-a3f1", "text": "Three files changed — the parser was dropping…", "attachments": [{"name": "chart.png", "at": "/…/workspace/chart.png"}]}
{"type": "state",  "conversation": "1180", "run": "7-a3f1", "state": "finished"}
{"type": "query-result", "conversation": "1180", "query": "status", "ref": "8843", "text": "ava: RUNNING"}
{"type": "configure-result", "conversation": "1180", "ref": "8844", "text": "Default provider changed to claude. The next message starts fresh."}
```

Read a line, show what you can of it, keep reading. Your stdin stays open for the whole
life of the channel.

**`said` is a finished remark, `answer` is the reply.** A brain that says several
complete things while it works sends each as `said` as it says it, and the last thing it
says arrives as the `answer` — which is the one somebody will reply to, and the one worth
anchoring to the message that asked. A brain that writes its reply a piece at a time
sends no `said` at all and only an `answer`, so a surface that treats them identically is
still correct and merely noisier.

**A `said` naming a `schedule` is the clock's, and it comes in pairs.** Work rundesk starts
because the time came says so where that schedule reports — `{"type": "said", "schedule":
"nightly", "began": true, …}` — and what it found arrives later as another `said` carrying
the same name and no `began`. **Keep what you posted for the first, and make the second a
reply to it**, so an owner scrolling a busy conversation sees an outcome attached to the
thing that started it rather than floating loose among answers to other questions. In
memory is enough and durable storage is wrong: if your program restarts the run dies with
it, so there is no report left to anchor. A name you are holding nothing for is posted
plainly, which is what every scheduled report did before there were notices. The name is a
key and never something to read, exactly as `place` is — which is the other field these
carry: the room the owner named for this schedule, yours to resolve, and the only way to
reach one nobody has spoken in yet. Both go to the *same* conversation, decided when the
first is sent: post the pair where you are told and never work the second one out again.

**The notice is rundesk's own bookkeeping and not the agent's speech**, which is why it is
not in the record of what the agent said. On a surface where anybody can reply to any
message, somebody *will* reply to it — and that is an ordinary message, starting an
ordinary turn, whose brain has no record of a line it never wrote. Send it on as you would
any other; there is nothing for an adapter to do about it. The report beneath it is written
down, so a reply to *that* reaches a session that saw it.

**Nothing repeats, so keep your own time.** `running` is sent once, when the turn is
admitted — it is not a heartbeat, and a surface whose "still working" indicator lapses
after a few seconds has to renew it on its own clock. The shipped Discord adapter does
exactly that, because there is nothing to lean on. Do not wait for a second `running`;
none is coming.

**The order is fixed, and the last two are the ones worth knowing.** `taken` arrives
first, on its own, the moment the message is picked up — it carries the `ref` of the
message that asked but not yet a `run` or a `can`, because neither exists until a turn
has been admitted. `running` arrives next and carries both. Then whatever the agent did,
as it does it. Then the `answer`, **and only then** the `finished`. So by the time you
are told a turn is finished you already have its answer, and a surface that waits for
`finished` before posting anything will still post everything.

## The rules that will bite you

**Rundesk decides what state a turn is in. You decide only how it looks.** There are five,
and they arrive as `state` records in this order:

| | |
|---|---|
| `taken` | it has been picked up — the first thing that happens, and the one worth showing fastest |
| `running` | it is under way, and this is where `run` and `can` first appear |
| `finished` | it worked, and the answer has already been handed to you |
| `stopped` | somebody stopped it |
| `failed` | it did not work, and `why` says what went wrong |

Do not work any of these out for yourself. An adapter that decided on its own when a
message had been seen would be re-implementing the turn, and two surfaces would eventually
disagree about what happened to the same run — with the run's own account matching
neither. You are told; you show.

**Work goes out early, and prose does not.** What the agent *did* — a tool it ran, a
thought it closed — arrives while it is happening, and is worth showing then. What it
*says* arrives once, at the end, as a single `answer`. You will never be handed a
part-written one, so there is no way for you to post half a sentence and no discipline
required of you not to. If your platform can edit a message, edit the running commentary;
never the answer.

**Show what you have and skip what you have not.** There is no capability declaration to
fill in. A surface with no reactions simply never marks anything; one with no typing
indicator never types; one that cannot edit posts again instead. A turn completes anyway.
Correctness never degrades — only fidelity — and the poorest surface there is, one that
can only post text, is a first-class channel rather than a broken one.

**Ask what the brain can do before offering it.** The `state` record that opens a turn
carries `can`, which is what the *brain* behind this agent declared. Offering somebody a
way to interrupt a turn whose brain said `steer: false` offers something that cannot
happen. Read it, and offer what is real.

**A control is a gesture, not an answer.** There are three. `stop` ends the turn running
in that conversation; `forget` throws away where that conversation had got to, so the next
message starts fresh; and `restart` cycles the whole agent, which is the only one whose
effect is larger than the conversation it was made in — every conversation's turn ends
with it, so offer it as something deliberate rather than as something easy to hit. Both are yours to offer however your platform offers
things — a command, a word, a button. Acknowledge the gesture if your platform makes you,
but **what a control did comes back as the turn's own outcome**, never as the acknowledgement.
Answering a `stop` by publishing what the turn had written so far is how a half-finished
sentence gets posted as though it were the reply.

**Never a credential on a command line, and never one you keep.** Anything on a command
line is readable through the process list and kept in a shell's history. Read your token
from the environment variable you named in `secret`, or from a file the owner already
controls. Do not put it in `settings`: that is written to a file that outlives you.

**Look in both places, because only one of them is there when it matters.** A person
adding your channel is at a terminal and has exported a variable. The machine that keeps
an agent up has no terminal and no shell profile — it starts your program with a built
environment, so that variable is not there, which is the state your channel spends its
whole life in. Fall back to a file inside your own `RUNDESK_CHANNEL_HOME`, and never
write one yourself: putting a credential on disk is the owner's decision to make, not
yours to make for them.

**You are running exactly when the agent is up, so say so if your platform can.** The
gateway starts you when the agent starts and ends you when it stops; there is no record
telling you either, because your own lifetime is the signal. If your surface has a
presence — an online light, a status, a badge — set it when you connect and clear it on
the way out, and it will mean the one thing worth meaning: that something is there to
answer. Tie it to your socket instead and it says an agent is up when the process behind
it has gone.

**Say when you have gone, and come back by yourself.** Reconnecting is yours — you know
what your platform's backoff wants and Rundesk does not. Say `gone` when you lose the
connection and `ready` when you have it again, so an owner can see the difference between
a quiet agent and a deaf one. If you exit, the gateway will start you again; that is a
coarser recovery than your own, and losing whatever arrived in between.

**A record we do not recognise is kept, not refused.** Emit something new and it lands in
the run's account verbatim. It will not be shown and it will not break anything — so you
can be ahead of us without waiting for us.

**Do not write anything down that only you have.** The run's own account already records
what was asked, what the brain did and what it cost, keyed by the `run` you are given. You
add delivery on top of that. An adapter that kept its own record would become the only
place something was written down, and it goes when your platform's history does.

**Take as long as you need, but keep talking.** Nothing bounds how long a channel is held
open — that is the point of it. What is bounded is nothing at all: you are not required to
say anything on an idle day, and an idle socket is not a failure.

**Exit when you are told to**, and take your children with you. When the gateway goes you
get a `SIGTERM` to your whole process group and a few seconds to leave before a `SIGKILL`.
A goodbye to the owner on the way out is welcome and never required.

## A working adapter

The poorest surface there is: it reads lines from its own standard input as though they
were messages, and prints answers. Thirty lines, no dependencies:

```sh
#!/usr/bin/env bash
# my-channel — the smallest channel that is not a lie.
set -euo pipefail

json() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'; }
say()  { printf '%s\n' "$1"; }

if [ "${1:-}" = "--check" ]; then
  # Nothing to connect to, so nothing can be wrong with it.
  say '{"ok":true,"settings":{},"describes":"this terminal"}'
  exit 0
fi

# What we are told about the turn, shown as it happens. This surface has no marks and
# no typing indicator, so it says the state in words — which is a complete channel.
while IFS= read -r line; do
  case "$line" in
    *'"answer"'*) printf 'agent: %s\n' "$line" >&2 ;;
    *'"state"'*)  printf '(%s)\n' "$line" >&2 ;;
  esac
done <&0 &

# Its "platform" is a file the owner drops lines into — a terminal would do for `--here`
# and there is no terminal at all once the machine is keeping this agent up, which is how
# it really runs.
say '{"type":"ready"}'
inbox="$RUNDESK_CHANNEL_HOME/inbox"
: > "$inbox"
tail -n0 -F "$inbox" | while IFS= read -r asked; do
  [ -n "$asked" ] || continue
  say "$(printf '{"type":"arrived","conversation":"here","user":"me","text":%s}' \
        "$(printf '%s' "$asked" | json)")"
done
```

Point an agent at it and it is a first-class channel:

```sh
rundesk channels ava add mine --kind /opt/my-channel --allow me
rundesk start ava
```

Give it whatever your platform needs, without anything changing here:

```sh
rundesk channels ava add ops --kind /opt/my-channel --allow 2207 -- --space 9930 --room 1180
```

## What Rundesk keeps for you, and what you keep yourself

Two places, and you decide the shape of both.

**The record** is what your own `--check` returned as `settings`. Rundesk writes it down,
hands it straight back in `RUNDESK_SETTINGS` every time it starts you, and reads none of
it. Nest it, repeat it, number it — whatever your platform needs is a shape nobody here
has to have thought of. The only thing Rundesk requires is that it is a JSON object, so
that there is something to hand back.

**Your own home** is `RUNDESK_CHANNEL_HOME`, and nothing here ever looks inside it. A
file, a directory, a database, whatever you like. Use it for anything that changes while
you run — a cursor into your platform's history, a cache of who is who, the last message
id you saw. Rundesk never reads it, never writes it, and never tidies it.

The line between them: the record is what an owner *configured*, and it changes when they
run `channels add` again. Your home is what you *learned*, and it survives restarts
without anybody being asked about it. Putting a credential in either is the one thing not
to do — the record is a file that outlives you, and your home is a file you did not ask
the owner's permission to write a secret into.

## From nothing to a working channel

The whole path, in the order you will actually do it.

**1. Answer `--check` first, before anything else works.** Until it returns `ok`, nothing
about your channel is written down and there is nothing to run. Get this right on its own:

```sh
MY_TOKEN=… /opt/my-channel --check --room 1180
# {"ok": true, "settings": {"room": "1180"}, "secret": {"env": "MY_TOKEN"}, "describes": "#ops"}
```

**2. Run the suite against it.** It needs no platform and no token:

```sh
git clone https://github.com/rundesk-ai/rundesk-cli && cd rundesk-cli
python3 tests/test_channel.py --adapter /opt/my-channel -- --room 1180
```

**3. Add it to an agent.** This runs your `--check` for real and refuses to write anything
if it says no:

```sh
export MY_TOKEN=…
rundesk add ava --provider codex
rundesk channels ava add ops --kind /opt/my-channel --allow <your user id> -- --room 1180
rundesk channels ava show ops
```

**4. Start the agent.** Your program is started here, and held open for as long as the
agent is up:

```sh
rundesk start ava        # kept up by the machine
rundesk start ava --here # or in this terminal, where you can watch it
```

**5. When it does not work, look here first:**

```sh
rundesk logs ava                     # everything, including what your program said went wrong
rundesk logs ava --source machine    # what escaped before there was a log at all
rundesk channels ava                 # is it reachable? is the agent even running?
```

Anything your program writes to stderr appears in that log as it happens, prefixed with
your channel's name. **Use it.** A surface that fails silently is one nobody can help,
and this is the one place an owner will look.

**6. Remember there is no shell where this really runs.** Once the machine is keeping the
agent up, your program starts with a built environment and none of your profile. A token
exported in a terminal is gone; a `PATH` you rely on is not there. Find what you need from
`RUNDESK_CHANNEL_HOME`, or from an absolute path.

## Who is allowed to use it

**Rundesk decides, not you.** You report who spoke; whether that person may be answered is
checked here, against the list the owner gave `--allow`. You do not need to filter, and you
must not rely on having filtered — an adapter that got it wrong would be an agent answering
strangers on a machine where it runs tools.

At least one allowed user is required when a channel is added. There is no way to say
"anybody", deliberately, and adding that would be the shortest path to the worst outcome
this product has.

A message from somebody who is not allowed is never dispatched, and you are told nothing
about it. Silence is the answer on purpose: replying to a stranger to tell them they are a
stranger confirms the agent is listening and spends the owner's tokens doing it.

## Proving it

The same suite every shipped channel passes is the one yours passes — that is what makes
"a surface Rundesk has never heard of" a claim rather than a hope. It checks what can be checked of *your program* without having your platform: that it
answers `--check` with something that can be acted on, that it names a credential rather
than handing one over, that it survives a whole turn's worth of records being told to it,
that everything it reports back is something this seam can act on, and that it is a
program at all rather than something that has to be imported.

It cannot make *your* platform deliver a message, so it cannot prove a conversation
end to end. Only you can do that — against your own fake, or against a server you own.

What it does **not** check is the half that is ours — that a delivery which fails does not
end the turn it was reporting, that a reconnection finds the conversation it already had,
that nobody unauthorized is dispatched. Those hold whatever adapter is in front of them,
and they are proved against a fake rather than against you.

Run it against yours:

```sh
git clone https://github.com/rundesk-ai/rundesk-cli && cd rundesk-cli
python3 tests/test_channel.py --adapter /opt/my-channel
```

Run bare it needs no account, no token and no network — the adapters it drives are then
small programs, which is the same thing yours is. Pointed at yours it really runs your
adapter, though not your platform: what a fake cannot prove is your surface's own limits
and timings, and that is what a canary against a private server of your own is for.

**If your adapter follows this page and the suite still fails it, this page is wrong** — it
is the contract, and the code is what has to move.

---
*This page is the contract — if your adapter follows it and the suite still fails, this page
is what moves. [`../prd-drafts/channel-adapter.md`](../prd-drafts/channel-adapter.md) is the
list of requirements it is held to, and which test proves each; it describes this page
rather than the other way round.*
