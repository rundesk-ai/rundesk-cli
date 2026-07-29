---
name: managing-rundesk-schedules
description: What a rundesk schedule is for and how to work one — the owner deliverable it exists to produce, saying when as a moment or a repeating time, where its outcome lands, and why it is never a way to move your own work out of a turn. Use whenever anyone asks for a reminder, a recurring report, something to happen at a time, or asks what an agent runs on its own; and whenever you are about to add, change, turn off or run a rundesk schedule.
---

# Managing rundesk schedules

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

```sh
rundesk schedules <name>       what this agent runs on its own — add, on, off, remove, run
```

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
path — or ask a turn. `--to <channel>` is which surface its outcome reaches, named by the
channel it was added under rather than by anything about the platform, and `--in <where>` is
which place on that surface:

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

**Change one in place — never remove and add it again.** The verbs are `add`, `show`, `edit`,
`on`, `off`, `remove` and `run`.

```sh
rundesk schedules <name> show morning          everything this one was given
rundesk schedules <name> edit morning --when "0 9 * * *"
```

So "move the morning report to nine" is one `edit`, and what it has already done stays with it.
Removing and re-adding loses that: a run outlives its schedule, but *which* schedule it was does
not, so the name-to-run link is what you would be throwing away. Read it back with `show` before
you change it rather than reconstructing it from memory.

`off` is what somebody means by "stop it for now": it keeps the schedule and what it last did,
and `on` puts it back. A moment that has been used cannot be reused — add another schedule
rather than trying to revive one.

**Running one by hand does not use its moment up.** `rundesk schedules <name> run <schedule>`
does the work now and changes nothing about when it falls due on its own, which is what makes
it safe for checking that a job does what somebody expects before the night it matters.

**You never post it yourself.** There is no command that sends a message, deliberately: you do
the work and answer, and the gateway delivers the outcome through the channel already held
open. So a schedule needs no knowledge of the platform at all.

**Two messages go out, and the first one is not yours.** A schedule that asks a turn is
announced before you start: rundesk posts *"💻 Working on 'nightly' — I will report back when
it is done"* in its own words, where the report will land, and what you found arrives as a
**reply to that message**. A run that failed, was cancelled or never got going still answers
its own notice, so nothing is left hanging. A schedule that starts a *program* announces
nothing — it has no report to anchor.

That notice is rundesk's, not yours. It is not written into your record, so it is not in
`rundesk messages` — if somebody replies to it, the words they are answering are not
something you will find you said.

**On a scheduled turn you are heard once, at the end.** What is delivered is the last whole
thought your brain finished, not your working on the way there. Nobody is watching a schedule
run, so progress prose is dropped rather than posted. Put the whole answer in the last thing
you say.

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

**A channel that spans a server has no one room to post in**, so a schedule that says nothing
about where lands in whichever conversation on it was most recently active *when the run
started* — a different room on a different morning, or a thread somebody opened. The notice and
the report go to the same place, resolved once at the start, so a long run cannot announce
itself in one room and report in another.

**`--in <where>` is what fixes that, and it is yours to set.** Give the room in the surface's
own words — for Discord a room name or id — and both messages land there every time, whatever
the channel spans, even if nothing has been said in that room yet. Nobody has to add a second
channel for it:

```sh
rundesk schedules <name> add nightly --when "0 6 * * *" \
    --ask "summarise what changed yesterday" --to ops --in "#operations"
rundesk schedules <name> edit nightly --in "#operations"    # or --in "" to follow the
                                                            # conversation again
```

So when an owner asks for a daily post in one named room and the channel points at "every
room", set `--in` rather than promising the channel will happen to land there. Promising a room
you cannot guarantee is the failure mode here, and it will not show up until the morning it
lands somewhere else.

You can see which places on a channel have actually been used — the `WHERE` column names each:

```sh
rundesk messages <name> --channel ops
```

A schedule that fires with no channel configured still runs and is still recorded — it is
reported by `rundesk schedules <name>` and readable with `rundesk messages <name> --source
schedule`.
