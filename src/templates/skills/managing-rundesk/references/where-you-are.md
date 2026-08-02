# Where you are, and what you are talking about

Read this when a command answers about the wrong install, or when a name, id or
conversation you typed matched nothing.

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
it. You can write skills too — `writing-skills` says how. It is not one every agent
starts with, so ask for it rather than assuming you have it.

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
where their surface gave a name, so a Discord DM reads as `<member>` rather than `user`, and it
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
