---
name: the-command-surface
description: How the rundesk command is organised — the one rule it obeys, what every verb is for, and which overlaps were deliberately removed.
---

# The command surface — how it is organised, and why

The command is the whole product, so its shape is a design decision rather than an accumulation. This
says what the shape is and what it refuses to be, so a verb added later can be checked against it instead
of merely fitting in. What is built today and what is planned is read off `rundesk --help`, never from
here — a list written twice is a list that disagrees with itself.

## The one rule

**A verb says what. The next word says whose.**

```
rundesk start ava
        ^^^^^ ^^^
        what  whose
```

Everything obeys it: `start ava`, `stop ava`, `logs ava`, `doctor ava`, `channels ava`, `runs ava`,
`schedules ava`. There is no second shape to learn, and no command where the agent arrives as an option
while every other command takes it as a word.

### Why some verbs take no noun

`add ava` makes an agent. It is not `agents add ava`, for the same reason `start ava` is not
`agents start ava`: **at the top level there is exactly one kind of thing to add**, and it is an agent.
A verb whose object is unambiguous does not need the object spelled out.

Nested verbs are different, because there the object *is* ambiguous:

```
rundesk add ava                    an agent — the only thing you add at this level
rundesk channels ava add ops …     a channel — qualified by the group it sits in
rundesk schedules ava add tidy …   a schedule — likewise
```

This is the convention `git` uses (`git add` is files, `git remote add` is remotes), and it holds as
long as the unqualified verb means the product's primary noun. If a second unqualified `add` is ever
proposed, the rule has been broken and one of them is in the wrong place.

## What each verb is for

Read `rundesk --help` for what exists right now. This says what each is *for*, which the help line has
no room for.

### The agent, and its life

| Verb | What it is for |
|---|---|
| `add <agent>` | Make an agent and the one gateway that runs it. Never one without the other. |
| `remove <agent>` | Take both away, and the schedules and channels that were the agent's. |
| `agents` | Every agent, and what each is doing right now. The table you look at first. |
| `agents <agent>` | One agent: what it is, and where it keeps things. |
| `doctor [<agent>]` | What stands between an agent and a working turn, without starting a provider. |

### Running one

| Verb | What it is for |
|---|---|
| `start <agent>` | Have the machine keep it running, and bring it back after a crash or a reboot. |
| `stop <agent>` | Stand it down. |
| `restart <agent>` | Cycle it, leaving every other agent alone. |
| `logs <agent>` | What it has been saying. Reads the file, so an agent that has gone can still be asked. |

### Reaching it

| Verb | What it is for |
|---|---|
| `ask <agent> "…"` | One turn, streamed to this terminal. |
| `channels <agent>` | The channels it is reachable on. `add <channel> --kind …`, `remove`, `show`. |
| `schedules <agent>` | What it does because the time came, and what became of each. |
| `runs <agent>` | What it has run, and how each ended. `show <run>`, `resume <run>` or `stop <run>`. |

### Rundesk itself

| Verb | What it is for |
|---|---|
| `status` | How rundesk is: its version, whether the supervisor answers, whether the install is fit. |
| `version` | What is installed, and whether that is current. |
| `update` | Move to the newest published release. |
| `uninstall` | Take rundesk off this machine. |

## Naming, so two things never read as one

A name means the same thing everywhere it appears, and a thing you name is named the same way as its
neighbours. Both rules were broken before they were written down:

- **`<agent>` everywhere** — not `<name>` on one verb and `<agent>` on another. The gateway verbs took
  `<name>` because a gateway was their subject; the subject is the agent, and the argument says so.
- **A thing you make is named by you, and described by options.** `schedules add <schedule> --when …`
  and `channels add <channel> --kind …` are the same shape. An earlier draft had `channels add <kind>`,
  which made the slot after `add` mean the *type* on one verb and the *name* on another.
- **`[--flag]` for what is optional to pass, `<value>` for a value you supply** — never `[<both>]` on
  one token.

**One verb is not on the rule yet.** `schedules` names its agent with `--gateway` rather than as the next
word, and puts the schedule's name last instead of first. It is built, and moving it is a change to a
shipped grammar — Phase 1 does it, along with making the agent the subject of the gateway verbs. Read it
as the exception it is, not as a second pattern.

## Overlaps that were removed, and why

Each of these was on the surface or proposed for it, and each was resolved rather than lived with. They
are recorded because the reasoning is what stops them coming back.

| The overlap | What was done |
|---|---|
| `run` and `runs` — one letter apart, and one of them starts work that costs money | The verb became **`ask`**. A run is still what an occurrence is called, so `runs` still lists them. The nearest pair on the surface is now `ask` and `agents`. |
| `status` and `agents` both listed agents | **`agents`** answers "what do I have and what is it doing". **`status`** answers "how is rundesk" — version, supervisor, install fitness. Two questions, two commands. |
| `bindings` as a verb, beside `channels` | Removed. Which provider and model answer is an **option where the entry point is made** (`channels ava add ops --kind discord --provider claude`), and the agent supplies what was left out. Reaching an agent from Discord is one command, not two. A binding is still what a run resolved — it is just not something anyone maintains. |
| `serve` beside `start` — both run an agent | Folded into **`start`**, which takes where it runs rather than there being a second verb for it. `serve` survives only as what an already-written launchd job invokes, so nothing installed breaks. |
| `show <run>` beside `replay <run>` — both look back at one run | One **`show`**, with a flag for the stream. A distinction that needs a paragraph to explain is one a consumer will get wrong. |
| `remove` beside `stop --remove` — two ways to remove | One way: **`remove`**. |
| `uninstall` printing instructions and exiting zero | It removes rundesk, or it fails. A command that reports success without doing the thing is the failure this product is most careful about. |

## What a verb that is not built does

Every operation the product will offer is listed from the outset (`R-CMD-1`), described where it is
listed (`R-CMD-2`), and refuses honestly until it is built:

```
$ rundesk channels ava add ops --kind discord
channels add: NOT AVAILABLE — planned, not built yet
        what this rundesk can do:  rundesk --help
$ echo $?
69
```

**`69` and not `2`.** Argparse spends `2` on a usage error, and those are different situations wanting
opposite things done about them: `69` means this rundesk does not have that yet, so wait for a release
or upgrade; `2` means the command was typed wrongly, so read the help. A script that cannot tell them
apart can act on neither (`R-CMD-8`). `69` is `EX_UNAVAILABLE`, which is what the BSD exit table has
always called this.

A planned verb also accepts the arguments it will eventually take (`R-CMD-7`), so a script written
against tomorrow's rundesk gets our refusal today rather than argparse's.

## Adding a verb

1. Does an existing verb already answer this question? The table above exists because the answer was
   "yes" more often than expected.
2. Is its object unambiguous at the level it sits? If not, it belongs under a group.
3. Add it to `PLANNED` in `src/rundesk_cli/cli.py`, with the one line `--help` will show.
4. The tests walk the parser, so a verb registered and answered nowhere fails without anything being
   added to a list.

---
*This is a project how-to. The contracts it points at are in [`../prd/`](../prd/README.md).*
