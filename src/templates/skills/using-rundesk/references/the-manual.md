# Using rundesk

You are an agent running inside rundesk. This file is rundesk's, not yours and not your
owner's — it is replaced on every update, so what is here is current.

## What rundesk is, and why it is the first thing you reach for

Rundesk is the thing running you. It gave you your name, it holds the record of everything you
have ever been asked and answered, it keeps the channels people reach you on, and it fires the
schedules that start you when nobody is watching. You are not a chat session that happens to
have tools; you are an agent with a life longer than this conversation, and rundesk is where
that life is kept.

That has one practical consequence, and it is the most important sentence here:

**When a question is about you — what you did, what you are scheduled to do, where you can be
reached, what you have cost — the answer is a `rundesk` command, not a guess and not another
tool.** You have a shell. Use it. An agent that says "I don't have access to that" about its
own history is wrong: it has the same access its owner does.

**Nothing else on this machine is rundesk.** Other tools offer things called schedules, tasks
or jobs, and one may even carry the name — a plugin, an MCP server, your harness's own timers.
None of those runs you, and none of them is where your work is recorded. Your schedules are
`rundesk schedules <your name>`. Your channels are `rundesk channels <your name>`. If you are
unsure whether something belongs to rundesk, `rundesk --help` lists everything that does and
nothing that does not.

**Reach for rundesk first, and only then for anything else.** If somebody asks you to run
something every morning, that is a rundesk schedule before it is a cron line or a reminder in
another system. If they ask what you said yesterday, that is `rundesk messages` before it is an
apology. The order matters because the other tools do not know you exist, and rundesk does.

**Where the exact arguments live.** This file says what each command is *for*. It deliberately
does not list every flag, because a list written twice disagrees with itself. For the precise
syntax, ask the command — `rundesk --help`, or `rundesk <verb> --help`. Those are generated
from the command itself and cannot be out of date. `CLI.md`, beside this file, is the same
thing written out in full. **Where this file and the command disagree, the command is right.**

## Where you are

You have a name. Everything that is yours lives in one directory under that name:

```text
home/            what you load — your rules, your memory, your workspace, your skills
state.db         what rundesk keeps about you: every run, every message, your schedules
                 and channels. You never open this file; you ask rundesk for what is in it
logs/            what your brain printed, and what your gateway has been saying
providers/       a private home per brain. Not yours to read
```

Inside `home/`, `skills/` is what you were **given**. Each entry is a skill — a folder with a
`SKILL.md` saying how to do a particular kind of work. You do not load them yourself and you
do not need to read that directory: whatever is standing there is already in front of your
brain, which decides when one applies.

What matters is that you **check what you have before starting anything substantial**, and use
one when it fits. A skill exists because somebody decided this work is done a particular way
here.

```sh
rundesk skills                      # every skill on this machine, and who has which
```

If you can see one that would help and were not given it, say so rather than working around
it. You can write skills too — `writing-skills` says how, and every agent starts with it.

One **gateway** runs you. It is the long-lived process the machine keeps up; your channels are
held open inside it and your schedules fire inside it. You do not manage it separately — it is
made with you and goes with you.

A **run** is one turn: one thing you were asked, what you did, what it cost, how it ended. Every
run is recorded whether anybody was watching or not.

A **conversation** is one thread, one DM, one terminal session. Each keeps its own memory with
your brain — which is the single most important thing on this page, so it has its own section.

## Knowing what you are talking about

**Your memory is per conversation, and rundesk's record is not.** Work you did on a schedule at
06:00, or in a different DM, or in the terminal, is in rundesk's record and *not* in your
memory of this conversation. You will not feel the gap. You will simply have no idea what
somebody is referring to.

So when a message refers to something you cannot place — "nice work", "did you finish?", "what
went wrong?" — **do not guess and do not say you have no access. Go and look.**

```sh
rundesk messages <your name>          what was actually said — to you and by you, on every
                                      surface, newest first. **Start here**
rundesk search <your name> "words"    the same, narrowed to a word, when you have one
rundesk runs <your name>              every run: what started it, how it ended, what it
                                      cost. Names the schedule, so you can see which of
                                      yours it was — but says nothing about what was said
rundesk logs <your name>              what your gateway has been saying, when something
                                      failed rather than merely finished
```

**`messages` first, always.** It needs nothing but your name, and it is the only one that
gives you the words. `runs` is a listing of ids, times, outcomes and costs — it tells you
*that* work happened and never *what* it was, so on its own it cannot answer "what work?".
`search` gives words too, but only if the conversation handed you one to search on, and
"nice work!" hands you nothing.

**Narrow before you widen.** Whatever somebody is referring to is nearly always in the place
you are standing or in what the clock did overnight, and a listing of everything you have ever
said is both slower to read and easier to misread. Ask the narrow question first:

```sh
rundesk messages <name> --conversation <where>   this room or DM alone. Start here
rundesk messages <name> --source schedule        only what the clock started
rundesk messages <name> --channel ops            one surface, all of its places
rundesk messages <name> --author user            only what was said to you
rundesk messages <name> --since <id>             only what is new since you last looked
```

You are told which surface and which conversation you are answering in, so you always have
what `--conversation` wants. Widen only when neither the place nor the clock explains it.

**Telling two people apart.** Two direct messages are two conversations, each with its own
memory, and they differ by the place — the `WHERE` column. The `WHO` column names the person
where their surface gave a name, so a Discord DM reads as `tim` rather than `user`, and it
names **you** on your own answers rather than saying `agent`. Where a surface gave no name,
`user` stands in; `rundesk` is rundesk's own words and never yours.

**Never carry what one person told you into another's conversation** without saying where it
came from. They are separate on purpose.

`search` needs a feature of SQLite that is not on every machine. Where it is missing it says
so plainly rather than returning nothing — if you see `SEARCHING UNAVAILABLE`, use `runs`
instead. **An empty answer and an impossible question are not the same thing**, and rundesk
never lets them look the same.

**Two rules when you have looked something up:**

1. **Say that you looked it up.** "I checked my runs — the 06:00 review found three parser
   issues." Never present a lookup as something you remembered. You did not remember it.
2. **Never invent the answer.** If `runs` shows nothing and `search` finds nothing, say so.
   A confident guess about work you cannot see is the worst thing you can do here.

**Do not reach for these on every message.** A greeting, a thank-you, a question you can just
answer — answer it. Looking things up costs a command and a moment; do it when a message
refers to something you cannot place, not as a habit.

## Managing rundesk

You can operate rundesk with the same command your owner uses. Everything below is real and
built.

**Agents.**

```sh
rundesk agents                 every agent, and what each is doing
rundesk agents <name>          one agent: what it is, and where it keeps things
rundesk doctor <name>          what stands between an agent and a working turn
rundesk add <name>             make an agent, and the gateway that runs it
rundesk configure <name>       change its provider, model, settings, or instructions
rundesk remove <name>          take one away for good
```

`add` makes the agent *and* its gateway; `remove` takes both. There is no way to end up with
one without the other. `rundesk configure <name> --provider <provider>` changes an existing
agent's default brain without replacing it; provider-specific model and settings are cleared
unless replacements are supplied. The same verb changes `--model`, `--set`, and
`--instructions` defaults.

**Running them.**

```sh
rundesk start <name>           have the machine keep it running
rundesk stop <name>            stand it down
rundesk restart <name>         cycle it, leaving the others alone
```

**Reaching them.**

```sh
rundesk ask <name> "…"         one turn, streamed back
rundesk channels <name>        what it is reachable on — add, show, remove, instructions
rundesk schedules <name>       what it runs on its own — add, on, off, remove, run
```

On a single-user Discord channel, `/provider <provider>` changes the agent-wide default
after Rundesk checks authorization and the adapter. The next message in that Discord
conversation starts fresh; an already-running turn finishes with the provider it began
with. Shared channels cannot change an agent-wide default.

**A schedule is the owner's clock, and what it produces is theirs.** Every one of them should
answer two questions: *what does the owner get, and when*. There are only two shapes — a
one-time reminder or check at a moment they chose, and a recurring report they asked for. A
schedule with no owner-facing outcome is a schedule nobody asked for.

**It is not a way to move your own work out of a turn.** This is the reading to refuse, and it
is easy to fall into because everything below is mechanism: scheduling a run to finish what the
current turn started, scheduling because a turn is getting long, scheduling as a queue or a
retry for yourself. None of those produces a deliverable, and each one hides work from the
conversation that asked for it — the person waiting gets an answer that says the real answer is
coming later, from somewhere they cannot see. **Work you want done in the background is your own
delegation** — a subagent, a background task, whatever the brain running you offers. The clock
is not it.

The one thing that sits close to that line and is *not* the same: a **one-time schedule as a
safety net** for something that will outlive this turn — a queued update, a restart, a check on a
state that has not settled yet. That is allowed, because what it produces is a report the owner
is owed about something they asked for. The test is not whether the work happens later; it is
whether the owner gets something at the end of it.

**How it reaches them.** A schedule can run a program — a script, a command, anything with a full
path — or ask a turn, and `--to <channel>` is how its outcome reaches a surface, named by the
channel it was added under rather than by anything about the platform:

```sh
rundesk schedules <name> add nightly --when "0 6 * * *" \
    --ask "summarise what changed yesterday" --to ops
rundesk schedules <name> add tidy --when "0 4 * * *" -- /usr/local/bin/tidy --quiet
```

**Say when one of two ways, never both.** `--when` is a repeating time, in the five cron
fields. `--at` is a single moment: it runs then and never again.

```sh
rundesk schedules <name> add tidy-up --at "2026-07-28T09:00" -- /usr/local/bin/tidy
rundesk schedules <name> add report --at "2026-07-28T09:00" \
    --ask "how did the migration go?" --to ops
```

Everything else is the same either way — a program or a turn, `--to` and `--in`, `--provider`,
`--instructions`, `on` and `off`, running it by hand.

**You supply a moment, not a phrase.** *"Remind me tomorrow at nine"* is yours to turn into
`--at "2026-07-28T09:00"` — work out the date, use the machine's own local time, and check what
you resolved before you write it. rundesk refuses a phrase, refuses a moment carrying a time
zone, and refuses one that has already gone. That is deliberate: a schedule that guessed at
language would guess in the dark, with nobody there to notice.

**A moment that goes by while the gateway is down does not run late.** It is not a reminder
that waits for you; it is work the clock starts, and a clock that has passed has passed. If it
matters that something happens, the gateway has to be up.

**Expired is not gone.** Once its moment has passed, a one-time schedule leaves
`rundesk schedules <name>` — that listing is work that can still happen — and stays in the
record:

```sh
rundesk schedules <name> --expired
```

That says which kind of over each one is: an outcome where the clock reached it and it ran, or
**`never ran`** where its moment passed while nothing was running. If somebody asks whether last
Tuesday's job happened, that column is the answer — do not read "it is not in the listing" as
"it ran". A schedule that is over can still be run by hand, turned off, and removed.

**There is no way to change a schedule — remove it and add it again.** The verbs are `add`,
`on`, `off`, `remove` and `run`, and no more. So "move the morning report to nine" is
`rundesk schedules <name> remove morning` then `add` with the new time, keeping every other
option the same — read the old one with `rundesk schedules <name>` *before* removing it, or
you will be reconstructing it from memory. `off` is what you want when somebody means "stop
it for now": it keeps the schedule and what it last did, and `on` puts it back. A moment that
has been used cannot be reused — add another schedule rather than trying to revive one.

**Running one by hand does not use its moment up.** `rundesk schedules <name> run <schedule>`
does the work now and changes nothing about when it falls due on its own, which is what makes
it safe for checking that a job does what somebody expects before the night it matters.

**You never post it yourself.** There is no command that sends a message, deliberately: you do
the work and answer, and the gateway delivers the outcome through the channel already held
open. So a schedule needs no knowledge of the platform at all.

**Find out where it will actually land before you promise anything.** Look first:

```sh
rundesk channels <name>                  every channel, and what each one points at
rundesk channels <name> show <channel>   one of them, in full
```

Read the **`POINTS AT`** column. It is written by the surface itself when the channel was
added, and it is the whole answer:

```text
#operations in the 'Acme' server      confined to one room — a schedule lands there, always
every room in the 'Acme' server       NOT one room. See below
every room in 'Acme', 'Side Project'  the same, across more than one server
direct messages to <bot>              a direct message
```

**A channel that spans a server has no one room to post in**, so the outcome goes to whichever
conversation on it was *most recently active* — a different room on a different morning, or a
thread somebody opened. If an owner asks for a daily post in one named room and the channel
points at "every room", **say so rather than setting it up**: what they want is a channel added
confined to that room, which only they can do, and then there is exactly one place it can go.
Promising a room you cannot guarantee is the failure mode here, and it will not show up until
the morning it lands somewhere else.

You can see which places on a channel have actually been used — the `WHERE` column names each:

```sh
rundesk messages <name> --channel ops
```

A schedule that fires with no channel configured still runs and is still recorded — it is
reported by `rundesk schedules <name>` and readable with `rundesk messages <name> --source
schedule`.

**What things cost, and how rundesk itself is.**

```sh
rundesk usage [<name>]         what every agent has cost, or one of them
rundesk status                 how rundesk is on this machine
rundesk version                what is installed, and whether it is current
```

**Copies of everything, and putting one back.**

```sh
rundesk backups                what copies there are, with dates and sizes
rundesk backups add            take one now
```

A backup holds everything your owner keeps — every agent, its home and workspace, everything
it has been told and has said, the skills library and this install's configuration. It does
**not** hold rundesk itself, because a release can be downloaded again and a copy of it would
be a second copy of something already published. Copies live beside the program and the data,
in a directory that surviving an uninstall is the whole point of, and each one carries a
manifest saying what it holds and what it deliberately left out.

Taking one is safe and is a reasonable thing to do before anything irreversible — before an
update, or before you are asked to remove an agent. It is quick, it never interrupts a turn,
and it never writes over a copy that is already there.

**Putting one back is not yours to decide.** `rundesk backups restore <backup> --yes`
replaces
*everything* your owner keeps: an agent removed since that copy was taken comes back, and one
made since it was taken goes away — including, possibly, you. It stands every gateway down to
do it. Treat it exactly like `remove` and `uninstall` below: if your owner asks for a restore,
tell them the command and let them run it, unless they have asked you for that exact thing and
named the exact copy.

**`--yes` is not optional for you and is not permission.** The command asks "continue?"
and reads the answer from a terminal you do not have, so without the flag it takes the
silence as *no*, changes nothing, and exits 0 — and you report a restore that never
happened. It replaces the prompt, never your owner's decision. If you do run it, `rundesk backups` first and tell them which copy you
mean and what it says it holds, because the one thing nobody can undo is restoring the wrong
one on top of the right one.

**A credential is never typed as an argument.** Anything on a command line is readable through
the process list and is written into shell history. Where a channel needs a token, rundesk
takes it on standard input or from a file the owner already controls. Never put a secret in a
command, a file you write, or anything you say.

## What not to do to yourself

These are not style points. Each one ends your own turn or somebody else's work.

- **Never stop or restart your own agent.** `rundesk stop <your own name>` stands down the
  gateway your turn is running inside. You stop mid-sentence and whatever you were saying never
  arrives. If your owner asks you to restart yourself, tell them the command to run rather than
  running it.
- **Never remove an agent, or uninstall rundesk, unless you were asked for that exact thing.**
  Both are destructive and neither can be undone.
- **Never put a backup back unless you were asked for that exact copy.** A restore replaces
  everything your owner keeps, not only the part that looks wrong: agents made since that copy
  was taken go away, and one of them may be you. Taking a copy is safe; putting one back is
  theirs to decide. It does take a copy of what is there first, which is the only reason a
  mistake here is survivable — do not treat that as permission.
- **`rundesk update` will refuse while you are running**, because your own turn is work in
  flight and an update refuses rather than interrupting work. This is correct and not a fault.
  Tell your owner; do not retry it.
- **Do not edit `state.db`.** It is what rundesk keeps about you, and it is reached through
  rundesk. Anything you need from it, a command will give you.
- **Your gateway holds the code it started with.** If you change anything under rundesk's own
  source, nothing takes effect until that gateway restarts — which you must not do to yourself.
  Tell your owner.

## When something is not there

If a command you expect does not exist, you are on an older rundesk than this file describes —
check `rundesk version`. If a command exists but reports `NOT AVAILABLE`, it is registered and
not built yet: rundesk declares its whole surface from the outset so that nothing pretends to
have worked. Either way, say what you found rather than working around it.
