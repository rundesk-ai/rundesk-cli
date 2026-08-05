# The gateway that hosts each agent

**One agent, one gateway, one job.** This is the page to read when your agents have stopped.

A gateway is a process that holds one agent's name for as long as it is running. Behind each one is
a job registered with `launchd`, the only thing on a Mac that will start a program at login and put
it back when it dies. The job is what makes a gateway survive a crash, a logout and a reboot; the
process is what does the work.

What a gateway hosts — adapters, a provider, the subprocesses an agent runs — is not built yet. What
is built is the part that has to be right before any of that can be trusted: a gateway starts, holds
its agent's name, says every fifteen seconds that it is still working, stops when it is asked to, and
can be told apart from one that has died. A provider recorded against an agent is recorded and not
proven, and starting a gateway does not change that.

The commands are in [`commands.md`](commands.md). This is what is underneath them.

## Liveness is asked of the kernel, and no file decides anything

**A gateway that was killed outright must never look alive.** Everything here is arranged around
that one property, and it is the property a written-down process id cannot have. A pid file is a
number a process wrote about itself: nothing updates it when that process is killed, loses its
machine to a power cut, or is taken away by the supervisor. Worse, the numbers are reused — a
recorded pid whose process is gone is a pid that now belongs to something else, and anything that
acted on it would be acting on a stranger's program.

So a gateway holds an exclusive lock on a file in its agent's own directory, taken by the kernel and
held for the whole life of the process. The kernel releases it however the process ended. Asking
whether a gateway is running is asking the kernel whether that lock can be taken, and a gateway that
crashed reads as offline with its record still sitting whole on the disk.

There is a record beside the lock, and it is read **only after** the lock has already said somebody
is there. That is where the pid in `rundesk gateways` comes from, and it is why a listing sometimes
shows a running gateway with no pid at all: the kernel said it is up, and it had nothing readable to
say about itself.

**There are three answers and not two.** Online, offline, and nobody can tell — a lock nothing could
open at all, because its directory is unreadable or its permissions were changed. That third answer
is kept as a third answer everywhere it appears, and never quietly folded into "not running":
reporting an agent nobody can ask about as free is how a second gateway comes to be started beside a
first, and how a live one is orphaned by a removal.

**A lock file left behind is not a held lock, and nothing sweeps it.** The lock lives on the file
rather than on its name, so deleting the file while another process holds a lock on it means the next
caller creates a *new* file and locks that — and both then believe they have it. That is the exact
failure that lock-by-existence schemes have, and it would be arrived at by the back door. A file left
lying there is somewhere for the next gateway to hang its lock on.

## Every refusal exits zero, and that is not a mistake

The job carries `KeepAlive { SuccessfulExit: false }`, which means exactly one thing:

```
exit 0                   do not bring me back
exit anything else       bring me back
```

Read forwards that is obvious. Read backwards it is the sharpest edge in this product. **An uncaught
Python exception exits `1`** — so a gateway that refused to run because its agent does not exist
would be brought back, refuse again, and be brought back again, for ever. launchd would escalate that
into its own exponential throttling until the restarts were minutes apart, and the whole thing would
simply look like a hang, with nothing anywhere naming what was wrong.

So every refusal a gateway makes reaches `0`, including the case where the check that decides to
refuse is itself the thing that fails. That is why `rundesk gateways run <agent>` prints
`gateway: NOT RUNNING — …` and then exits `0`, which reads wrong until you know who the exit code is
addressed to. It is a sentence in a conversation with launchd, not a report to a person. The report
to the person is the line above it.

Once a gateway is up and working the asymmetry reverses: from there an exception is a *crash*, it
exits non-zero, and being brought back is the right answer. A permanent condition and a fault are
two different things, and the exit code is the only place the difference can be said.

The same contract is why a gateway handles `SIGTERM` and `SIGHUP` rather than being ended by them.
An orderly stop unwinds and writes a line saying it stopped; a gateway that was killed outright
writes nothing at all. Reading the log is how you tell those two apart, and it only works because the
polite path really is polite.

## The job's name carries a fingerprint of `RUNDESK_HOME`

`RUNDESK_HOME` isolates everything else an install keeps. **It cannot isolate a launchd job's name.**
A job's name lives in one person's login session, not below any directory, so two installs that
derived the same name would be two installs pointing at one job — and that is not hypothetical. The
build this replaces called every install's job `ai.rundesk.gateway`, and a second install's uninstall
booted out the live install's gateway.

So the root is part of the name. Each job is called
`ai.rundesk.<fingerprint of the root>.gateway.<agent>`, where the fingerprint is eight characters of
a digest of the resolved `RUNDESK_HOME`. A scratch install and a real one derive different names and
cannot reach each other's jobs. The root is *resolved* first, so the same directory reached through a
symlink or spelled with a `..` segment is the same install — two spellings that fingerprinted
differently would give one install two jobs for one agent, and both would start.

What that buys is a rule rather than a habit: **nothing in rundesk ever sweeps or matches a prefix of
`ai.rundesk`.** Every operation names one whole job, and a job whose name does not fingerprint back
to the root it claims to belong to is refused rather than acted on. That is the whole of the fix for
the incident above, and it is what lets `rundesk uninstall` take back this install's jobs on a
machine that has two.

It does not make a job's name private. The override store, the login session and the Login Items
register are all the *person's*, and every one of them outlives any install.

## Why the job points at a program named after the agent

macOS lists a background item by the **basename of the program it starts**. Measured on this machine:
jobs pointed straight at an interpreter appear in that register as `python`, `sh` and `bash` — the
name of the interpreter, not of anything the owner recognises.

A gateway pointed straight at an interpreter would therefore show its owner an anonymous `python` row
in System Settings → General → Login Items & Extensions. Several agents would show several identical
`python` rows, and one careless toggle would take them all away at once. That matters more than
untidiness, because switching one off there is the **one lockout on this page with no command that
undoes it**.

So each job points at a small named program of its own, written into that agent's own directory and
called `rundesk-gateway-<agent>`, which hands off to the release this install is running. It costs
one file per gateway and it is the only mitigation available for the failure mode with no way back.

It lives inside the agent's directory rather than under `app/` on purpose: `app/` is what an update
replaces whole, and a job whose program vanishes mid-update spawns, fails, and is **removed by
launchd** — after which nothing on the command line says the job was ever there.

> **One thing here is not settled.** Whether the register records the name of that program, or the
> name of the interpreter it hands off to, has not been established: it needs a job to be placed and
> the register read afterwards, and that has not been done. Both are consistent with what was
> measured. It is written down as unsettled rather than claimed, because the register is exactly
> where a confident wrong answer costs the most.

## Graceful is the default, and `--force` takes work away

`rundesk gateways stop` and `rundesk gateways restart` are graceful. The gateway is sent `SIGTERM`
and given the whole of its shutdown window — twenty-five seconds — to finish what it was holding, and
only then does launchd insist. That is the default because a gateway is holding somebody's work, and
a stop that does not let it finish is a stop that loses some.

**`--force` kills it where it stands, first, and then takes the job back.** It is for a gateway that
*will not go* — one ignoring `SIGTERM`, so that a graceful stop blocks for the whole window — and
never for one that is merely busy, which is exactly the gateway with something to lose. What it buys
is the waiting: with nothing left to wait for, taking the job back returns at once. What it costs is
whatever the gateway was doing. The command says so on the line reporting what it did, and only where
a gateway really was up.

`--force` skips none of the proving. A forced restart still shows a new gateway holding the name
before it says it restarted anything.

**And a restart is a stop that was proved, then a start.** Never the other way round: starting over a
job the supervisor is still holding keeps the definition it already had *without failing*, so a
restart that started first would report a restart and go on running the old program for ever.

## Where a gateway's account of itself is

Two places, and they answer different questions. `rundesk gateways logs <agent>` reads both.

**The agent's own day files**, in `data/agents/<name>/logs/`, one file per day, kept for a fortnight
and swept by the gateway itself once a day rather than once at startup — a gateway that is doing its
job is one nobody restarts, and one swept in March would be sitting on two hundred files by now. This
is everything the gateway said after it had a log of its own to say it in.

**`gateway.out` and `gateway.err`**, in the same directory. These are not rundesk's: launchd opens
them and writes into them whatever the process put on its standard output and standard error. They
are **the only account of a start that died before the gateway had a log of its own** — a missing
interpreter, a job launchd would not take, an exception on the way up. Nothing had opened `logs/`
yet, so nothing is in it.

The very first thing a gateway does, before it parses or reads anything, is write one line into
`gateway.out` saying what process it is and what version it is running. That line is the point of the
whole arrangement: **an empty `gateway.out` beside a job launchd says has run means the failure is
upstream of rundesk entirely**, and belongs in the machine's unified log rather than here. `rundesk
gateways logs` prints the command for that when it finds nothing anywhere.

launchd opens those two files in append mode and never rotates them, so in a crash loop every restart
adds another traceback for ever. rundesk moves them aside itself once they grow past a quarter of a
megabyte, keeping three previous generations — enough tracebacks that a crash loop still has its
beginning in it, and a bounded cost per agent whatever happens.

## Every state a gateway can be in, and what gets it out

`rundesk gateways` reads four independent sources and shows them as four columns, because no one of
them can answer alone. `GATEWAY` is the kernel's answer; `JOB` is whether launchd is holding a job;
`OVERRIDE` is a store that can refuse to start one and that outlives every job; `LOGIN ITEM` is what
the owner has told macOS. **`LOGIN ITEM` reads `cannot tell` for most gateways most of the time**,
which is the honest answer rather than a fault: that register is undocumented, and reporting a
gateway as switched off on the strength of a guess would be worse than saying nothing.

| What is wrong | How you can tell | What resolves it |
|---|---|---|
| Nothing | `GATEWAY` says running, `JOB` says placed | — |
| It was never started | `not running`, `not placed` | `rundesk gateways start <agent>` |
| It is running and nothing is supervising it | `running, UNSUPERVISED`, `not placed` | `rundesk gateways restart <agent>` — the job can only be placed over a name that is free |
| It is up and has stopped working | `running, no beat` | `rundesk gateways logs <agent>` first, then `rundesk gateways restart <agent>` |
| It keeps dying and being brought back | a start that placed the job and could not show a gateway holding the name | `rundesk gateways logs <agent>` — and fix what it says. Restarting a crash loop faster does not end it |
| Something switched the job off, perhaps years ago | `OVERRIDE` says `disabled` | `rundesk gateways start <agent>` — it clears the override before every start, unconditionally, because nothing on a Mac ever deletes one of those records |
| launchd is running a definition other than the one on disk | the listing says so, naming both | `rundesk gateways restart <agent>` |
| The gateway will not go | a graceful stop blocks for its whole window | `rundesk gateways stop <agent> --force`, or `restart --force`. **This takes work away mid-flight** |
| The program was quarantined, because the install was unzipped from a download | a start that never comes up, on a root that arrived that way | `xattr -dr com.apple.quarantine <your RUNDESK_HOME>` |
| You are over SSH, with nobody logged in at the desktop | `JOB` and `OVERRIDE` read `cannot tell`, and the note says there is no login session | none from there — a gateway is placed from the desktop. This is never reported as "not running": over SSH every gateway on the machine would otherwise look absent |
| **The owner switched it off in System Settings** | `LOGIN ITEM` says `switched off` | 🔴 **No command of any kind.** System Settings → General → Login Items & Extensions, and turn it back on |

That last row is the reason this page exists in the shape it does. A denial there does not merely
block the launch — it removes the job from launchd, after which every command-line question about it
answers exactly as it would for a job that was never installed. Nothing rundesk can run puts it back,
and nothing rundesk could add would; the only honest thing to do is detect it and say so, which is
what the `LOGIN ITEM` column is for.

One further state is recorded in
[`research/launchd-on-macos.md`](research/launchd-on-macos.md) and is **not settled**: launchd has a
"penalty box" it can put a job in, and what puts a job there and what gets it out was never
established. It is named here rather than left out, because a page about never being stuck that
quietly omitted a state would be the wrong kind of complete.

What is above was established against a real machine, and the working out is on that page — the exit
codes, what each launchd command really does, and, marked as such, which claims were measured and
which are still believed rather than proven.
