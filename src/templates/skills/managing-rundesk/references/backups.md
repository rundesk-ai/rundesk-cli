# Backups

Two acts, not the same size. **Taking a copy is safe, quick and interrupts nothing.** **Putting
one back replaces everything your owner keeps** — theirs to decide, not yours.

## What a copy holds

Every agent, its home and workspace, everything said, the skills library, this install's
configuration. Not rundesk itself: a release can be downloaded again, so a broken install is
reinstalled rather than restored. Each copy carries a manifest of what it holds and what it
deliberately left out.

## Taking one

```sh
rundesk backups            what copies there are, with dates and sizes
rundesk backups add        take one now
```

**Take one before anything irreversible** — an update, a removal, anything you would not want to
explain afterwards. Seconds, and no permission needed. Taking one never writes over an existing
copy, and the newest is never swept.

## Putting one back

```sh
rundesk backups restore <backup> --yes
```

**`--yes` is not permission — without it you do nothing at all.** The command asks "continue?"
and reads a terminal you do not have, so it sees the input end, takes it as *no*, prints
"nothing was changed" and exits **0**. You would report a restore that never happened.

**It replaces everything, not the part that looks wrong.** An agent removed since that copy
comes back; an agent made since it goes away — possibly you. Every gateway stands down.

- **Only if asked for that exact thing, naming that exact copy.** "Can you fix this" is not a
  restore request; neither is "get X back" without a named copy.
- **Name the copy first** — run `rundesk backups`, say which and when, let them confirm.
- **Read out what will change.** The command prints which agents come back and which go away.
- In any doubt, hand over the command instead of running it.

It refuses on its own for records from a newer rundesk, for work in flight, and for an archive
that is not a backup. **A refusal is not a thing to work around.** It copies what is there
before replacing anything — that is why a mistake is survivable, not permission.

## Removing one

```sh
rundesk backups remove <backup> --yes
```

`--yes` for the same reason. By name, one at a time, never as a side effect. Copies survive
`rundesk uninstall --purge`, so this is the only way one goes.

## The short version

| They asked for | Do |
|---|---|
| a backup, or you are about to do something destructive | `backups add` — just do it |
| what copies exist | `backups` |
| something restored, naming the copy | say what changes, confirm, then `restore <backup> --yes` |
| "get it back" with no copy named | list them, ask which |
| something fixed | investigate — do **not** restore |
