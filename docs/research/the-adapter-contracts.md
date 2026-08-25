# The two adapter contracts, as the previous build defined them

Distilled 2026-08-04 from `docs_old/extending/`, where the previous build published the provider
adapter contract and the channel adapter contract as pages an outsider wrote against. Both are
gitignored, reference-only and expected to be deleted. **This page is the contract, not a
description of it** — the record kinds, the fields, the closed vocabularies and the JSON shapes
below are reproduced exactly, because those are the parts a re-implementation has to match. The
prose around them is compressed.

This build has not written its provider layer yet and has no channel layer at all, so treat this as
the thing being aimed at rather than as a description of anything that runs. Where a rule below was
settled by a measurement, the measurement is in one of the dated pages beside this one; those are
the evidence and this is the promise.

[`the-old-build.md`](the-old-build.md) says in a paragraph what an adapter *was* in that build. This
says what one had to do.

**One warning before anything else.** The `RUNDESK_*` names below are **not** the retired directory
variables. That build read a dozen independent `RUNDESK_*_DIR` variables to decide where an install
kept things, and this build replaced all of them with one root — see
[`docs/layout.md`](../concepts/layout.md). The variables on this page are a different thing entirely: they
are how a *turn* is described to a program rundesk starts, and every one of them is per-run rather
than per-install.

---

# The provider adapter contract

Rundesk does not run a conversation. It runs **your program**, gives it somewhere to work, reads
what you report, and ends it when the turn is over.

It is a program and not a plugin on purpose: rundesk never loads somebody else's code into the
gateway running every other agent, and an adapter author is not obliged to write Python. An adapter
can be a shell script. An adapter answers two questions — what it can do, and one turn.

## Question one: what can you do?

Run with `--capabilities`, print one JSON object, exit `0`:

```json
{"tools": true, "resume": true, "usage": true, "model": false}
```

| | |
|---|---|
| `tools` | you report what tools ran |
| `resume` | you can carry an earlier conversation on |
| `usage` | you report what a turn cost |
| `model` | you can name the model that actually answered |
| `steer` | you can be sent more words while a turn is still running |

Every field is `false` when left out, so `{}` is a valid answer and a complete adapter. **Rundesk
asks rather than assuming**, and never guesses from a name — so `false` means the work is simply
absent rather than expected and missing.

`--capabilities` is the only argument given; stdin is closed and nothing about a particular run is
set. An adapter that does not recognise the flag and does something else can do nothing, which is a
complete answer and never an error. It must need no account, no network and no login, and must
answer the same way every time. It is asked when a turn is admitted and written into that run's
record, **so that a turn which reported no tools and a brain that has none can be told apart
afterwards.**

**A declaration stops rundesk asking; it does not stop an adapter reporting.** Say `tools: false`
and emit a tool record anyway and the record is kept like any other. Only `steer` changes how a turn
is *run*.

## Question two: carry one turn

The adapter's path is whatever the agent was given as its provider — a bare name resolves among the
shipped ones, anything with a path separator is used as a path.

**Where to work arrives in the environment:**

| | |
|---|---|
| `RUNDESK_CWD` | the agent's own home — stand here, so what stands beside you is what your brain loads |
| `RUNDESK_PROVIDER_HOME` | yours alone, and it lasts: config, credentials, session files, anything you must remember between turns |
| `RUNDESK_MODEL` | the model asked for, or unset — a name you understand, not one we enumerate |
| `RUNDESK_RUN` | the id of this run, for correlating anything you keep |
| `RUNDESK_RESUME` | the handle you reported last time on this conversation, or unset for a new one |
| `RUNDESK_POSTURE` | `read` or `work` — how much of the machine this turn may touch |
| `RUNDESK_SETTINGS` | a JSON object of whatever the owner set, passed through unread |
| `RUNDESK_RAW` | somewhere to append everything your *brain* said, if you want to keep it |
| `RUNDESK_PREFACE` | standing instructions for this turn's situation, or unset |
| `RUNDESK_SKILLS` | the skills this agent was given — present them where your brain looks |
| `RUNDESK_CONTINUITY` | `NAME=verb,…` — which files beside the agent are the ones it lives by, and what changing one is called |

The first four are always set. `RUNDESK_MODEL`, `RUNDESK_RESUME` and `RUNDESK_SETTINGS` are **absent
rather than empty** when there is nothing to say, so `${RUNDESK_MODEL:-default}` does what you would
hope. `RUNDESK_PROVIDER_HOME` is made before the program starts and is the adapter's to write in.

**The prompt arrives on stdin**, and how depends on the one capability that changes how a turn is
run. Declaring `steer: false` (or nothing) gets plain text with stdin closing straight after it.
Declaring `steer: true` keeps stdin open for as long as the turn lasts, so nothing can mean "the
prompt ended" any more, and everything arrives as one JSON record per line —
`{"type":"say","text":"…"}` — the prompt first and anything said later the same way.

**The adapter reports on stdout, one JSON object per line, flushed as it happens:**

```json
{"type": "text",   "text": "Looking at the logs now.", "whole": true}
{"type": "think",  "text": "The error is in the parser."}
{"type": "tool",   "id": "1", "name": "Bash", "did": "run"}
{"type": "result", "id": "1", "ok": true, "summary": "3 files changed"}
{"type": "usage",  "input": 1200, "output": 340, "cached": 8000, "session": 9200, "model": "…"}
{"type": "file",   "at": "/…/workspace/chart.png", "name": "chart.png"}
{"type": "done",   "ok": true, "session": "<the brain's own opaque handle>"}
```

Seven kinds of record, and only `done` is required. **stderr is the adapter's** — it is kept and
never mistaken for what was reported.

| | must have | may have |
|---|---|---|
| `text` · `think` | `text` | `whole` |
| `tool` | `id` (a string) | `name` — your brain's own word · `did` |
| `result` | `id`, matching a `tool` you sent | `ok` · `summary` |
| `usage` | | `input` · `output` · `cached` · `written` · `session` · `model` |
| `file` | `at` (an absolute path) | `name` |
| `done` | `ok` | `session` · `why`, when it failed |

**A line that is not JSON, or a kind not listed, is kept verbatim and shown to nobody**, so nothing
an adapter emits can break a turn — and an adapter can be ahead of rundesk without waiting for it.

## The rules that will bite you

**`did` is what the tool *did*, not what the brain calls it.** The same action is `Bash` on one
brain, `shell` on the next and `run_terminal_command` on a third, and a surface that recognised a
vendor's names would carry that vendor's vocabulary forever. The list is closed and short: **`read`,
`search`, `run`, `edit`, `list`, `make`, `delegate`**, plus the three continuity verbs below. If
what a tool did is not one of those, **leave `did` out** — `name` still carries the adapter's own
word, and a reader that shows nothing is better than one taught to believe a word that means
something else here.

**An agent editing a file it lives by is different news from an agent editing a file it was working
on, and both arrive as `edit`.** `RUNDESK_CONTINUITY` hands over the pairing —
`AGENTS.md=rules,MEMORY.md=memory,SOUL.md=identity` — so which files those are stays rundesk's to
change rather than becoming a copy of its layout the adapter holds. Two things are the whole of
getting it right: **match where the file stands, not what it is called** (it qualifies when the
resolved path sits directly in `RUNDESK_CWD`, and both sides are resolved before comparing, because
every checkout on the machine has an `AGENTS.md`); and **writes only**, because reading these is
what a turn does before it answers anything and reporting that would say the agent rewrote itself
every turn.

**Report the turn's own tokens, not the conversation's.** A brain that hands over a running total
has to be subtracted from what was reported last time, and what you subtract from belongs in
`RUNDESK_PROVIDER_HOME`, keyed by the brain's own session handle — the previous build kept it in a
gateway's memory and lost it on every restart, over-reporting the first turn of every existing
thread afterwards. Three cases decided in advance: a handle never seen subtracts nothing and that
turn reads high; a total lower than last time means the conversation was restarted underneath you,
so report it whole rather than negative; and if you cannot tell at all, report nothing rather than a
guess.

**Keep cached tokens apart from fresh ones.** `input` is fresh only — what `cached` and `written`
count is not in it, because those three are billed at three different rates, which is why they are
three fields. Folding them together reports a number that is technically real and practically a lie.
**Leave a field out rather than guessing at it:** an absent `cached` means *could not tell* and is
recorded differently from a `cached` of zero. A total you cannot split is still the truth; a split
you invented is not.

**`session` on a `usage` record is not a cost.** It is how big the conversation is *now*, at the
moment the turn ended, so a person can decide whether to start a fresh one — a level and never a
running total, and it goes *down* when a conversation is compacted, which no total can. It has
nothing to do with `done`'s `session`, which is the opaque handle a later turn is carried on from.

**Say `whole` when what you just said is finished.** A brain writing its reply a fragment at a time
says nothing complete until it stops, so nothing can be shown to anybody until the turn ends; a
brain that says several complete things as it works is writing the way a person does, and marking
each one lets a surface show it as it is said. Leave it out and the behaviour is the old one, which
is correct and merely quieter.

**Say when the brain made something, or nobody will ever see it.** Otherwise a turn that drew a
chart can only mention it in a sentence. `file` is an absolute path on this machine that the adapter
really wrote; naming something outside the agent's own workspace and home is not an error and simply
will not be sent.

**`RUNDESK_PREFACE` is appended, never substituted, and this one will bite.** Map it onto whatever
the brain has for *adding* to its instructions. **Never map it to anything that replaces the system
prompt** — send an owner's paragraph there and you have not added a paragraph, you have deleted the
brain and left the paragraph, and the turn will merely behave strangely while looking like the
model's fault. **Find out *when* the brain reads it**: some take it every time, some bind it when a
conversation is created and silently ignore it after, and an argument that is accepted and then
dropped is worse than one never sent. A brain with no notion of standing instructions is not a
broken one; ignoring the variable is a whole adapter.

**`RUNDESK_SKILLS` is a directory of skills, and presenting them is the adapter's job.** Link, do
not copy, so an owner editing a skill reaches every agent holding it with nothing to re-run. **Link
each skill, never the whole directory** — making a vendor-owned path an alias for the library means
that vendor's own skill-installer writes into the library and anything aimed at that directory
destroys it. Make nothing when there is nothing. Remove only what you put there: the shipped
adapters unlinked an entry only when it was a symlink *and* now dangled. Discovering nothing is a
whole adapter, and rundesk will not compensate by putting skill text in a prompt — that would charge
every turn for every skill and make the account untrue. `RUNDESK_PROVIDER_HOME` is **not** where
skills go.

**`RUNDESK_POSTURE` is a request, and honouring it is the adapter's.** `read` means the owner asked
this turn to look without changing anything; `work` is the ordinary case. **Rundesk enforces nothing
— it has no way to, and pretending otherwise would be worse than saying so.** Map it onto whatever
the brain really has. If the brain has nothing to map it onto, ignore it; that is honest, and it is
why nothing here describes a posture as containment.

**`RUNDESK_SETTINGS` is not rundesk's to understand.** Whatever the owner set arrives as one JSON
object, with no keys rundesk defines. Map what you know onto your own flags, ignore what you do not,
and say on stderr when something recognised is malformed.

**Never a credential — not in settings, and not on a command line.** What an owner set is written
into the run's record, so a token put there is a token in a file outliving the turn. Anything on a
command line is readable through the process list and kept in a shell's history. And **do not go
looking for the owner's own configuration**: `RUNDESK_PROVIDER_HOME` is empty the first time an
agent reaches a brain, which for most brains means not signed in — say so and say what to run,
rather than quietly copying somebody's credentials in. Sharing one sign-in between agents may well
be what they want, and it is theirs to decide.

**`RUNDESK_RAW` is worth using.** Rundesk sees what the *adapter* reported and never what the brain
said before records were made of it, so a brain changing its output shape shows up as records
quietly going missing with nothing to compare against. Append the brain's own stream verbatim.
Nothing reads it, so there is no format to match and nothing to get wrong.

**Both the exit code and `done` matter, and they mean different things.** `done.ok` is what the
*brain* made of the turn; the exit code is what became of the *program*. A turn is recorded as
having worked only when both say so, so a brain that answered fine inside an adapter that then
crashed reads as the failure it was. A brain that simply said no is not the program failing — `done
ok:false` and exit `0` is the exact answer. **What must never happen is exiting with no `done` at
all**: that is a turn that never said it finished, and nothing downstream can tell it from one still
running.

**Take as long as you need, but keep talking.** Nothing bounds how long a turn may run — an agent
that thinks for an hour is working. What is bounded is how long it may say *nothing at all*, and
anything written to stderr counts.

**Exit when the turn is done, and take your children with you.** A stopped turn gets `SIGTERM` to
the whole process group and a few seconds before `SIGKILL`; a parting `done` is welcome and not
required.

## The smallest adapter that is not a lie

```sh
#!/usr/bin/env bash
set -euo pipefail

[ "$*" = "--capabilities" ] && { printf '{}\n'; exit 0; }

json() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'; }
say()  { printf '%s\n' "$1"; }

cd "$RUNDESK_CWD"                   # work where the agent works

# The turn arrives on stdin and goes to your brain the same way. Never as an argument:
# what somebody asks their agent is readable through the process list otherwise.
answer=$(your-cli --model "${RUNDESK_MODEL:-default}" --read-prompt-from-stdin) || {
  say '{"type":"done","ok":false,"why":"your-cli would not answer"}'
  exit 1
}

say "$(printf '{"type":"text","text":%s}' "$(printf '%s' "$answer" | json)")"
say '{"type":"done","ok":true}'
```

---

# The channel adapter contract

The mirror of the first, and deliberately the same shape. Rundesk does not know what a message is;
it runs a program, holds it open for as long as the agent is up, reads what arrived, and says how
the turn that followed is going. An adapter answers two questions — whether it can reach what it was
pointed at, and one conversation.

## Question one: can you reach it?

Run with `--check`, followed by whatever options the owner typed. Connect, sign in, verify you can
see the place you were given, print one JSON object, exit `0`:

```json
{"ok": true, "settings": {"space": "9930", "room": "1180"},
 "secret": {"env": "MY_TOKEN"}, "describes": "#operations in Acme"}
```

`ok` decides whether the channel may be added at all. `settings` is everything the adapter will need
next time, in its own words, handed straight back and never read. `secret` says where the credential
was found, so it can be shown as present without being shown. `describes` is one line naming what
was reached, for a person deciding whether it is the right place. `why` says what was wrong when
`ok` is false.

**Nothing is written down until the check says `ok`.** An agent whose channel is misconfigured must
find out while somebody is typing the command, not at three in the morning when somebody asks it
something. **Say `ok: false` and still exit `0` if the refusal was considered** — what is read is
the answer, not the code, and a program that dies without printing one failed rather than refused.

**The options belong to the adapter.** Everything after `--` reaches it exactly as typed; rundesk
does not parse it and has no list of what any platform needs. **Say what you understood, not what
you were told** — normalise `settings` here, because what comes back is what an owner will be
running on in a year.

**One `add` may make several channels, because one channel is one place.** Private messages and
rooms full of people are **two channels**, not one that branches: a channel carries the list of who
may reach the agent through it, and the people who may speak to an agent in a public room are not
the people who may speak to it in private. So the check reports the kinds of place it can reach, and
rundesk writes one channel for each:

```json
{"ok": true, "secret": {"env": "MY_TOKEN"},
 "shapes": [
   {"suffix": "dms",   "describes": "direct messages to acme-bot",
    "settings": {"dm": true}, "fills": []},
   {"suffix": "rooms", "describes": "#ops in Acme",
    "settings": {"room": "1180"}, "fills": ["channel", "server"]}
 ]}
```

**Work out what those are rather than asking.** The adapter is signed in by the time it answers, so
anything the platform can tell it is something an owner should not have to look up and paste.
**Reporting no shapes at all is a whole adapter** — it gets exactly one channel under the name that
was typed.

## Question two: carry one conversation

The program runs for as long as the agent's gateway does, which is weeks. It is **not started per
message and never polled**: a reply landing after somebody has asked again is a reply that failed.

| | |
|---|---|
| `RUNDESK_CHANNEL` | this channel's name, the one the owner added it under |
| `RUNDESK_AGENT` | whose channel it is |
| `RUNDESK_CHANNEL_HOME` | yours alone, and it lasts: anything you must remember between restarts |
| `RUNDESK_SETTINGS` | the object your own `--check` returned, handed back — `{}` if you returned nothing |
| `RUNDESK_ALLOW` | who may reach this agent here, comma separated. The first is the owner |

All five are always set. The one variable named in `secret` is set too, **and nothing else from the
owner's environment reaches the program** — so name it, or you will not have it.

**Six record kinds go out**, and only `arrived` starts a brain turn:

```json
{"type": "ready"}
{"type": "arrived",   "conversation": "1180", "user": "2207", "text": "what changed today?", "ref": "8841", "direct": false}
{"type": "control",   "conversation": "1180", "user": "2207", "control": "stop", "ref": "8842"}
{"type": "configure", "conversation": "1180", "user": "2207", "provider": "claude", "ref": "8844"}
{"type": "query",     "conversation": "1180", "user": "2207", "query": "status", "ref": "8843"}
{"type": "gone",      "why": "the socket closed"}
```

| | must have | may have |
|---|---|---|
| `ready` | | |
| `arrived` | `conversation`, `user` | `text` · `ref` · `direct` · `attachments` · `reply_to` · `where` · `called` · `parts` · channel context |
| `control` | `conversation`, `user`, `control` | `ref` |
| `configure` | `conversation`, `user`, `provider`, `ref` | |
| `query` | `conversation`, `user`, `query`, `ref` | |
| `gone` | | `why` |

`conversation` is whatever the platform calls one exchange — a thread, a room, a chat, a phone
number. Rundesk never parses it and never shows it; it is the key a conversation's session is kept
under, so the only thing that matters is that the same exchange produces the same one every time. A
message needs `text` **or** `attachments`, so a photograph sent with nothing typed is an ordinary
message and not a broken one.

**A control is a gesture, and there are three.** `stop` ends the turn running in that conversation;
`forget` throws away where that conversation had got to; `restart` cycles the whole agent, which is
the only one whose effect is larger than the conversation it was made in. **What a control did comes
back as the turn's own outcome, never as the acknowledgement** — answering a `stop` by publishing
what the turn had written so far is how a half-finished sentence gets posted as though it were the
reply.

**A query is read-only gateway information, never an arbitrary command.** The closed list is
`status`, `version`, `agents`, `help`. It starts no brain turn and is answered with a `query-result`
carrying the same `ref`. Never offer a generic command or arguments: that would expose mutating
operations through a record whose contract promises read-only inspection.

**Everything about the turn arrives on stdin**, one JSON object per line, for the whole life of the
channel:

```json
{"type": "state",  "conversation": "1180", "run": null,     "state": "taken",   "ref": "8841"}
{"type": "state",  "conversation": "1180", "run": "7-a3f1", "state": "running", "can": {"steer": true}}
{"type": "tool",   "conversation": "1180", "run": "7-a3f1", "id": "1", "name": "Bash", "did": "run"}
{"type": "result", "conversation": "1180", "run": "7-a3f1", "id": "1", "ok": true, "summary": "3 files changed"}
{"type": "think",  "conversation": "1180", "run": "7-a3f1", "text": "The error is in the parser."}
{"type": "usage",  "conversation": "1180", "run": "7-a3f1", "input": 1200, "output": 340, "cached": 8000, "session": 9200}
{"type": "said",   "conversation": "1180", "run": "7-a3f1", "text": "I'll look at the logs."}
{"type": "answer", "conversation": "1180", "run": "7-a3f1", "provider": "stand-in", "text": "Three files changed…"}
{"type": "state",  "conversation": "1180", "run": "7-a3f1", "state": "finished"}
{"type": "role",   "conversation": "1180", "role_run": "…", "state": "handed", "role": "development", "elapsed": 0}
{"type": "owner-notice", "text": "🧩 **Skill added** — `research`"}
{"type": "query-result", "conversation": "1180", "query": "status", "ref": "8843", "text": "…"}
```

**Rundesk decides what state a turn is in; the adapter decides only how it looks.** There are five —
`taken`, `running`, `finished`, `stopped`, `failed` — and they arrive in that order. An adapter that
decided on its own when a message had been seen would be re-implementing the turn, and two surfaces
would eventually disagree about what happened to the same run, with the run's own account matching
neither.

**The order is fixed, and the last two are the ones worth knowing.** `taken` arrives first and
alone, the moment the message is picked up; it carries the `ref` of the message that asked but not
yet a `run` or a `can`, because neither exists until a turn has been admitted. `running` carries
both. Then whatever the agent did, as it does it. Then the `answer`, **and only then** `finished` —
so a surface that waits for `finished` before posting anything will still post everything.

**Nothing repeats, so keep your own time.** `running` is sent once, when the turn is admitted. It is
not a heartbeat, and a surface whose "still working" indicator lapses after a few seconds has to
renew it on its own clock.

**`said` is a finished remark, `answer` is the reply.** A brain that says several complete things
while it works sends each as `said`; the last thing it says arrives as the `answer`, which is the
one somebody will reply to. A brain writing its reply a piece at a time sends no `said` at all, so
an adapter treating them identically is still correct and merely noisier. **Work goes out early and
prose does not** — you will never be handed a part-written answer, so there is no way to post half a
sentence.

**Ask what the brain can do before offering it.** The `state` record opening a turn carries `can`,
which is what the *brain* declared. Offering somebody a way to interrupt a turn whose brain said
`steer: false` offers something that cannot happen.

**Do not show `name`.** It is the brain's own identifier for a tool, and putting it in front of a
reader means putting one vendor's vocabulary in front of somebody who has never heard of that
vendor. Show `did`, which on this side of the seam is one of exactly ten words — `read`, `search`,
`run`, `edit`, `list`, `make`, `delegate`, `memory`, `rules`, `identity` — or absent, and absent is
common. **The last three are a file the agent lives by being rewritten**, apart from `edit` on
purpose, because what an agent *is* between turns changing is different news from a working file
changing.

**Who is allowed is rundesk's decision, not the adapter's.** The adapter reports who spoke; whether
that person may be answered is checked here. `RUNDESK_ALLOW` is not the authorization — but use it
to avoid working for nothing, because downloading an attachment, opening a thread or posting
anything at all happens before rundesk has seen a word, and for somebody who can never be answered
that is waste at best and, in a room full of people, an agent visibly reacting to a stranger it is
about to ignore. **Do not show the list to anybody.** At least one allowed user is required when a
channel is added; there is no way to say "anybody", deliberately.

**A message from somebody not allowed is never dispatched and the adapter is told nothing.** Silence
is the answer on purpose: replying to a stranger to tell them they are a stranger confirms the agent
is listening and spends the owner's tokens doing it.

**Show what you have and skip what you have not.** There is no capability declaration to fill in. A
surface with no reactions never marks anything; one that cannot edit posts again instead.
**Correctness never degrades — only fidelity** — and the poorest surface there is, one that can only
post text, is a first-class channel rather than a broken one.

**Attachments go both ways and both are files already on this machine.** What somebody attached is
downloaded by the adapter into its own home and reported with an absolute path; anything that is not
a readable file here is dropped, because the brain that would open it runs here and has no
credential for that platform. What the agent made arrives with `name`, absolute `at`, `bytes` and a
lowercase `sha256` — read the file once, verify both values, and send that byte snapshot rather than
reopening the path, and refuse symlink traversal in every path component while opening. Together
those stop a concurrent turn replacing an approved file or its parent between the check and the
send.

**You are running exactly when the agent is up, so say so if the platform can.** There is no record
telling an adapter either way, because its own lifetime is the signal — set a presence when you
connect and clear it on the way out, and it means the one thing worth meaning. **Say `gone` when you
lose the connection and `ready` when you have it back**, so an owner can see the difference between
a quiet agent and a deaf one; reconnecting is the adapter's, because it knows what its platform's
backoff wants and rundesk does not.

**Do not write anything down that only you have.** The run's own account already records what was
asked, what the brain did and what it cost. An adapter keeping its own record would become the only
place something was written down, and it goes when the platform's history does.

**Never a credential on a command line, and never one you keep.** Read the token from the
environment variable named in `secret`, or from a file the owner already controls — and **look in
both places, because only one of them is there when it matters**: a person adding a channel is at a
terminal with a variable exported, and the machine keeping an agent up has no terminal and no shell
profile, which is the state a channel spends its whole life in.

---

## The numbers, and what chose each one

Read off the previous build's own constants and their docstrings. None of these is a measurement of
the outside world; each is a decision with a reason, and the reasons are what transfer.

| Number | What it bounds | Why that number |
|---|--:|---|
| silence before a program is taken for wedged | 1800 s | generous on purpose — a working session can be quiet for a long time while one tool call runs, and ending one of those ends real work |
| ceiling on a program however much it says | 48 h | silence cannot see a program wedged in a loop that keeps announcing itself; set far past what real work reaches, because this is the backstop and silence is the instrument |
| grace between SIGTERM and SIGKILL | 5 s | bounded well under a supervisor's own patience, because being killed is how children get left behind |
| drain after a program has gone | 2 s | a drain, not a wait for more work |
| a slow *receiver* after the program has gone | 30 s | its own constant, and the opposite of a drain — shared with the drain at two seconds, a receiver spending a fifth of a second per record got nine of fifty and the run still reported it had finished |
| silence while an adapter answers `--capabilities` | 60 s | it is a question whose answer the adapter already knows, asked offline and without a network |
| ceiling on `--capabilities` | 300 s | this is the one place rundesk runs an unvetted program *before* a turn is admitted; without a backstop a chatty or broken adapter hangs every ask with nothing written down |
| silence while a channel `--check` connects and signs in | 60 s | a window of silence, like everything else rundesk waits on |
| ceiling on a channel `--check` | 300 s | generous against a slow platform, and finite because a person is standing at a terminal waiting for it |
| read buffer / longest held line | 64 KB / 4 MB | neither is a limit on what a program may say, only on how much is held at once, so a program that never emits a newline cannot grow us without bound |
| one externally supplied instruction layer | 4000 chars | each layer is bounded at ingestion; the completed stack is not clipped, because clipping it would silently drop whichever later layers fell past the boundary |
| a display name or place phrase carried into a prompt | 80 chars | a stranger's words on their way into a prompt, so flattened to one line and clipped — a display name is somewhere somebody can write something shaped like an instruction |
| a quoted parent message | 255 chars | enough to recognise the item, without a reply dominating the new turn |
| attachments carried from one message | 10, 32 MB each | a chat platform accepts far more than a turn can use, and an agent's workspace is not somewhere a stranger gets to fill |
| places one `add` may make | 8 | a bound rather than a belief: an adapter reporting a thousand shapes would otherwise write a thousand records under one command |
| skill name / description | 64 / 1024 chars | not ours — the tightest limit any of the three brains enforces, and the specification's, respectively |
