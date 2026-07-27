---
name: managing-backups
description: How rundesk keeps copies of everything your owner has, and what putting one back really does. Use whenever anyone asks to back something up, take or list copies, restore, roll back, undo a removal, recover a lost agent or its history, or asks whether something can be got back — and before you do anything destructive, because taking a copy first is cheap and putting one back is not.
---

# Managing backups

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

There are two acts here and they are not the same size. **Taking a copy is safe, quick, and
never interrupts anything.** **Putting one back replaces everything your owner keeps** — and
that is theirs to decide, not yours.

## What a copy holds

Everything your owner keeps: every agent, its home and workspace, everything it has been told
and has said, the skills library, and this install's configuration.

It does **not** hold rundesk itself. A release can be downloaded again, so a copy of the
program would be a second copy of something already published. If somebody's rundesk is
broken, the answer is to install it again — their data is not what is wrong.

Each copy carries a manifest saying what it holds *and what it deliberately left out*, so you
never have to guess. Two things are left out on purpose and both matter:

- **Live gateway state.** Put back, it would claim gateways that are not running.
- **A running database's side files.** The copy of the records is taken as of one moment
  rather than as the file happens to sit, so what is in it is already whole.

## Taking one

```sh
rundesk backups            what copies there are, with dates and sizes
rundesk backups add        take one now
```

Copies are named so that sorting by name sorts by time, and taking one **never writes over a
copy that is already there** — not even another taken in the same second.

**Take one before anything irreversible.** Before an update, before you are asked to remove an
agent, before anything you would not want to explain afterwards. It costs seconds. You do not
need to ask permission to take a copy.

Old copies are cleared out for you as new ones arrive, and **the newest is never deleted**,
whatever its age.

## Putting one back — read this before you type it

```sh
rundesk backups restore <backup> --yes
```

**`--yes` is not optional for you, and is not permission.** The command asks "continue?" and
reads the answer from the terminal. You have no terminal, so it sees the input end, takes that
as *no*, prints "nothing was changed" and exits **0** — a success code for something that did
not happen. Without the flag you will report a restore you did not do. The flag replaces the
prompt, not your owner's decision: everything below still has to be true before you type it.

**This replaces everything, not the part that looks wrong.** An agent removed since that copy
was taken comes back. An agent made since it was taken goes away — possibly you. Every gateway
is stood down to do it.

So:

- **Only if you were asked for that exact thing, naming that exact copy.** "Can you fix this"
  is not a request to restore. Neither is "get X back", unless they have said which copy.
- **Say which copy you mean first.** Run `rundesk backups`, tell them the name, when it was
  taken and what it says it holds, and let them confirm.
- **Say what will change.** The command prints which agents come back and which go away before
  it does anything. Read that out; do not skip past it.
- If in any doubt, give them the command and let them run it.

It refuses on its own in several cases, and a refusal is not a thing to work around:

- Records written by a **newer** rundesk than this one. This copy cannot be read safely and
  saying so is the correct outcome.
- **Work in flight**, or a gateway that will not stand down. Wait, or tell your owner.
- An archive that is not a rundesk backup, or one the cloud has not downloaded yet.

It takes a copy of what is there *before* it replaces anything, which is the only reason a
mistake here is survivable. **Do not treat that as permission.**

## Getting rid of one

```sh
rundesk backups remove <backup> --yes
```

`--yes` for the same reason as above: without it the command asks, sees no terminal, removes
nothing and exits 0. By name, one at a time, and never as a side effect of anything else. Copies survive removing
rundesk — including `rundesk uninstall --purge`, which takes the data and still keeps them —
so this is the only way one goes.

## The short version

| They asked for | Do |
|---|---|
| a backup, or you are about to do something destructive | `rundesk backups add` — just do it |
| what copies exist | `rundesk backups` |
| something restored, naming the copy | say what changes, confirm, then `restore <backup> --yes` |
| "get it back" with no copy named | list them, ask which |
| something fixed | investigate — do **not** restore |
