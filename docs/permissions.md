# Permissions — what this Mac lets rundesk do

**This is not about a brain's tool permissions.** Every provider adapter already runs its CLI with
that system switched off — `--dangerously-skip-permissions`, `danger-full-access`,
`bypassPermissions` — and [`providers.md`](providers.md) says so outright. Nothing here changes that
or reports on it.

What this page is about is **macOS TCC**: whether the machine will let a rundesk process drive the
UI, see the screen, script an application, or read a protected folder. An agent that owns the Mac it
runs on needs all of it, and until something asks, nobody knows which of it is actually available.

```
rundesk permissions                    what the last check found, when, and in which lineage
rundesk permissions lineage            whose grants an answer here would be about
rundesk permissions check [<what>...]  prove them now, and write down what was found
    --everything                       also prove the ones not needed to operate the machine
    --verbose                          also print what each program really said
```

The bare verb **runs nothing**. It reports, and the checking verb is named — so nothing happens on
somebody's machine because they typed the verb to see what it was.

---

## An answer belongs to a process, not to a machine

This is the thing to understand before reading a single verdict.

macOS does not attribute a permission to the process that asks for it. It walks up to the nearest
**application bundle** and makes that the *responsible process*. So everything you start from a
terminal inherits whatever you once granted that terminal, and a gateway — a launchd job, with no
application anywhere above it — is its own responsible process and starts with nothing.

Measured, on one machine, with one probe:

| Started by | Responsible process | Screen Recording | Accessibility |
|---|---|---|---|
| a shim, from a terminal | `iTerm.app` | yes | yes |
| the same shim, under launchd | itself, the interpreter | **no** | **no** |

**So a check run in your terminal will tell you a gateway can do things it cannot.** That is not a
caveat about this command; it is the reason the command prints a lineage line first and refuses to
run at all when it cannot work out which lineage it is in. A table of verdicts with no process named
is a claim about nobody.

**Asking from inside a turn is not reliably asking as the gateway, and this was measured.**
`"$RUNDESK_COMMAND" permissions check` run through a brain's tool call answered
`unknown (…/codex)` — the brain's program starts what it runs in a way that leaves the gateway shim
out of the parent chain, so the command proved *that* program's grants and wrote them down under a
lineage of `unknown`. A stored `ready` from such a run says nothing about the launchd interpreter a
gateway actually runs as.

So read the first line before any verdict below it. **Only a run that says `gateway` is a fact about
one**, whatever started it, and the command says so unprompted on every other lineage:

```console
$ rundesk permissions
as of 2026-08-15T10:02:11Z, about unknown (/opt/homebrew/bin/codex)
  nothing here was proved in a gateway, so none of it says what a gateway may do — it is about
  /opt/homebrew/bin/codex
```

Whether a turn *can* ask as its gateway depends on how the brain starts what it runs, and that is
the brain's and not rundesk's. It has not been measured for any brain that does keep the shim in the
chain, so the honest instruction is the lineage line rather than an invocation: **if it does not say
`gateway`, it is not one.**

## Two things about a gateway's grants that surprise people

**One grant covers every agent.** Two gateway shims differing only in the agent they name were
measured to be a single TCC client, because the shim `exec`s the interpreter and its own name is gone
from the running image before anything gated is called. Adding a second agent needs no new grant.

**The grant is the interpreter's, and an upgrade takes it away.** The client macOS records is the
Python that gateways run as, at its full versioned path. A `brew upgrade` of that interpreter moves
the path, and every grant stops applying — silently, with no error, until something fails. This
command is what finds out. It is also why the row you tick in a privacy pane says `Python` rather than
`rundesk`, and why that grant reaches every other script run by the same interpreter.

Neither is solved. Giving rundesk a name of its own in those panes would mean the named thing being
what python runs *as* rather than a wrapper that execs away, which is a build step this project does
not have.

## The verdicts

One verdict per thing there is to do about it, so no two mean the same action.

| Verdict | What it means | What to do |
|---|---|---|
| `ready` | it works | nothing — the only one that is not work |
| `blocked` | the machine refused | open the one pane named beside it |
| `unasked` | never asked, so it is asking whoever is at the desktop now | answer the dialog, run it again |
| `closed` | the application is here and not running | `open -a` it; a probe may not open a window for you |
| `absent` | the application is not here | nothing to grant |
| `unrunnable` | the program that settles it is missing or would not start | it refused nothing — this is a machine problem |
| `unproven` | it could not be settled either way | the third state, and never a quiet `ready` |

`unproven` counts as trouble and fails the command. A check that proved nothing has proved nothing,
and a command exiting zero on one is a command nobody can gate on.

## What is probed

| Group | Probes | Needed |
|---|---|---|
| `control` | `accessibility`, `post-events`, `listen-events`, `system-events` | yes |
| `screen` | `grant`, `capture` | yes |
| `files` | `desktop`, `documents`, `downloads`, `full-disk`, `app-data` | yes |
| `shell` | `admin` | no |

**Driving the machine is four grants, not one.** Accessibility, posting input events, observing input
events and Apple Events to System Events are separate services. An agent granted only Accessibility
can read the UI and cannot type, so these are four findings with four fixes rather than one line.

**`screen` is two probes and the order between them matters.** `screen/grant` reads the
non-prompting preflight and is the authority. `screen/capture` then takes a real eight-pixel picture
and decodes it, which proves the pipeline end to end in a way a boolean cannot — but it runs **only
after** the grant is confirmed. Asking for a capture without the grant was measured making macOS
*write* one, and a probe that grants the permission it was asked to report on is worse than useless.

**`shell/admin` is reported and never gated.** An agent that owns the machine but cannot install
software should learn that from a verdict, not from a password prompt in a log nobody is watching.

## Nothing prompts, and nothing is left behind

Every probe is a preflight or a read, and where no non-prompting way to ask exists the probe answers
`unproven` rather than shipping a guess. A consent dialog raised by a background gateway is a dialog
on somebody's desktop with no context, and the wrong button on it writes a **denial** that persists.

Every probe also declares what it touches, printed by `rundesk permissions` before anything runs. The
screenshot is eight pixels of the top-left corner and is deleted on every path.

## What is kept

`rundesk permissions check` writes what it found into `data/config.json`, so *what is still not
allowed* can be asked without running anything.

> **A report of what was true when it was last asked is not a cache anything decides on.**

TCC state is the machine's — you tick a box, an update resets grants, an upgrade moves the
interpreter, and nothing tells rundesk. So `check` always re-proves, and **nothing ever reads the
stored answer to decide whether it may act.** It exists to be shown.

It carries the lineage it was proved in, and says so when you read it back from a different one. A
partial check updates only what it proved and leaves every other answer at its older timestamp. A
probe that has never been run is **absent** from it rather than `unproven` — never asked and
asked-and-unanswerable are different answers.

## Exit codes

`0` when every probe that was asked for is `ready`. `1` for anything else, including `unproven`, and
for a name nobody has — which is refused with the list of what there is, never an empty table that
reads as a clean machine.

## Where the measurements are

[`research/2026-08-08-what-this-mac-lets-a-process-do.md`](research/2026-08-08-what-this-mac-lets-a-process-do.md)
holds what was established and how, including the eleven questions still open and the section that
was written three times before it was right.
