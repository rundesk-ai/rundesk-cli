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

**Nothing is written down until you say `ok`.** An agent whose channel is misconfigured
must find out while somebody is typing the command, not at three in the morning when
somebody asks it something. If you cannot sign in, cannot see the room, or were given
options you do not understand, say so and say `ok: false` — a channel that was never added
is a better outcome than one that is silently deaf.

**The options are yours, not ours.** Everything after `--` on the command line reaches you
exactly as typed. Rundesk does not parse it, does not validate it, and has no list of what
your platform needs. Whatever your surface calls its places — a server, a workspace, a
room, a number — those words live in your adapter and nowhere else.

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

**`RUNDESK_ALLOW` is for addressing people, never for deciding about them.** Rundesk
checks who may be answered and you do not (see below); this is here so you can greet the
owner, or show whose message you are marking. Do not filter on it and do not show it to
anybody: it is a list of who can reach this agent, which is not a list to hand out.

**The same four are set while you are being checked**, except `RUNDESK_SETTINGS` — you
have not returned any yet. So `RUNDESK_CHANNEL_HOME` is there and is already made, which
is what lets a credential in a file be found by the check that has to prove it.

**You report on stdout, one JSON object per line**, flushed as it happens:

```json
{"type": "ready"}
{"type": "arrived",  "conversation": "1180", "user": "2207", "text": "what changed today?", "ref": "8841", "direct": false}
{"type": "control",  "conversation": "1180", "user": "2207", "control": "stop", "ref": "8842"}
{"type": "gone",     "why": "the socket closed"}
```

**stderr is yours.** Say what went wrong there; it is kept, and it is never mistaken for
what you reported.

That is the whole of what you say. Four kinds of record, and only `arrived` really matters.

**What each record needs**, and nothing else is required of you:

| | must have | may have |
|---|---|---|
| `ready` | | |
| `arrived` | `conversation`, `user` | `text` · `ref` · `direct` · `attachments` |
| `control` | `conversation`, `user`, `control` | `ref` |
| `gone` | | `why` |

**`did` is what a tool did, and the list is closed.** It is one of exactly six words —
`read`, `search`, `run`, `edit`, `list`, `make` — or it is absent, and absent is common.
Show a mark or a word of your own for each.

**Do not show `name`.** It is the brain's own identifier for the tool — `commandExecution`
on one, `Bash` on the next — and putting it in front of a reader means putting one
vendor's vocabulary in front of somebody who has never heard of that vendor. It is in the
record so an account can be read back afterwards, not so it can be displayed. Show the
verb, and when there is none say something true and general: a brain that gave no verb did
something this vocabulary has no word for yet, and its identifier is not a translation
of that. A `did` you do not recognise cannot happen today
and would mean this list had grown, so treat it the way you treat an absent one.

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
{"type": "state",  "conversation": "1180", "run": "7-a3f1", "state": "taken",   "ref": "8841", "can": {"steer": true}}
{"type": "tool",   "conversation": "1180", "run": "7-a3f1", "id": "1", "name": "Bash", "did": "run"}
{"type": "result", "conversation": "1180", "run": "7-a3f1", "id": "1", "ok": true, "summary": "3 files changed"}
{"type": "think",  "conversation": "1180", "run": "7-a3f1", "text": "The error is in the parser."}
{"type": "usage",  "conversation": "1180", "run": "7-a3f1", "input": 1200, "output": 340, "cached": 8000}
{"type": "said",   "conversation": "1180", "run": "7-a3f1", "text": "I'll look at the logs."}
{"type": "answer", "conversation": "1180", "run": "7-a3f1", "text": "Three files changed — the parser was dropping…", "attachments": [{"name": "chart.png", "at": "/…/workspace/chart.png"}]}
{"type": "state",  "conversation": "1180", "run": "7-a3f1", "state": "finished"}
```

Read a line, show what you can of it, keep reading. Your stdin stays open for the whole
life of the channel.

**`said` is a finished remark, `answer` is the reply.** A brain that says several
complete things while it works sends each as `said` as it says it, and the last thing it
says arrives as the `answer` — which is the one somebody will reply to, and the one worth
anchoring to the message that asked. A brain that writes its reply a piece at a time
sends no `said` at all and only an `answer`, so a surface that treats them identically is
still correct and merely noisier.

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
| `running` | still going, said again from time to time for anything that lapses |
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

say '{"type":"ready"}'
while IFS= read -r asked; do
  [ -n "$asked" ] || continue
  say "$(printf '{"type":"arrived","conversation":"here","user":"me","text":%s}' \
        "$(printf '%s' "$asked" | json)")"
done < /dev/tty
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
"a surface Rundesk has never heard of" a claim rather than a hope. It checks what can be checked of *your program*: that it answers `--check` with something
that can be acted on, that it names a credential rather than handing one over, that what
it reports is a record this seam understands, and that it is a program at all rather than
something that has to be imported.

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
