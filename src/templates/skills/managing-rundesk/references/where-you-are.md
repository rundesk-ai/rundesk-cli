# Where you are, and naming what you mean

Read this when a command answers about the wrong thing, or when a name or conversation you
typed matched nothing.

## Everything of yours is in one directory

```text
home/         what you load — rules, memory, workspace, skills
state.db      every run, message, schedule and channel. Ask rundesk for it, never open it
logs/         what your brain printed, and what your gateway has been saying
providers/    a private home per brain. Not yours to read
```

`home/skills/` is what you were **given** — already in front of your brain, which decides when
one applies, so you never read that directory. But check what you hold before anything
substantial, and say so if one that would help was not granted.

One **gateway** runs you: made with you, goes with you, nothing to manage separately. A **run**
is one turn. A **conversation** is one thread, DM or terminal session, each with its own memory.

## Reading a conversation back

```sh
rundesk messages <you>                          everything, newest first
rundesk messages <you> --conversation <where>   one room or DM. Start here
rundesk messages <you> --source schedule        what the clock started
rundesk messages <you> --channel ops            one surface, all its places
rundesk messages <you> --author user            only what was said to you
rundesk messages <you> --since <id>             only what is new
rundesk search <you> "words"                    narrowed to a word, when you have one
```

A listing prints `<channel>/<space>`, and the filter takes that or the bare space — both work.

**An empty listing and a name that matched nothing look identical.** Check the name before
concluding a conversation is empty.

## Which install

An install can be pointed anywhere, so never write a path down — ask:

```sh
rundesk skills --where       the skill library
rundesk backups --where      where copies are kept
rundesk scripts --where      the owner's integration commands, first on your PATH
```
