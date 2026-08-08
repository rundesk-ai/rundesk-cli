# The gateway that hosts each agent

**One agent, one gateway, one job.** This is the page to read when your agents have stopped.

A gateway is a process that holds one agent's name for as long as it is running. Behind each one is
a job registered with `launchd`, the only thing on a Mac that will start a program at login and put
it back when it dies. The job is what makes a gateway survive a crash, a logout and a reboot; the
process is what does the work.

A gateway hosts three things: **the work its schedules start**, **the adapters its channels connect
through**, and **the work other agents hand to this one**. All three hang off the same loop in the
same three places — reckoning with what a previous gateway left before anything begins, one pass
every beat, and a stop on the way out — and none of them may end the gateway hosting it. A schedule
that could not run, a platform that is down, an adapter nobody installed, a delegation that could not
be answered: each of those is a gateway that is *up* and complaining, never a gateway that refuses to
start.

They are siblings rather than a hierarchy, which is why adding the third was one edit and not a
rewrite: a gateway hosts a list.

**The third is why an agent you delegate to has to have a gateway running.** Its own gateway is what
notices work addressed to it and answers as itself; a delegation to an agent nothing is running would
wait for ever, so `rundesk ask` refuses it at the point of asking rather than letting the work sit.
The same loop collects the answers to what *this* agent handed out, and puts each in front of it —
into the turn already running if there is one, and by starting a turn if there is not. **The turn it
starts answers where the person asked**, out loud, on the channel the conversation stands on: waking
the agent is only half of it, and a review that reached its own records and no room at all is what a
delegation looked like from a direct message for as long as that half was missing.

**And it says so while the work is out.** In the room the work was asked for in — never the notified
channel and never the answering agent's own room — one line of small print when the work goes, one
every twenty minutes for as long as it is still out, and one when it comes back saying who answered
and how long it took. That is the gateway's to say rather than `rundesk ask`'s: the command runs in a
process with no channel connection and nothing to post through, so the only thing able to report a
delegation is whatever is already watching, which is this loop.

Underneath both is the part that had to be right before either could be trusted: a gateway starts,
holds its agent's name, says every fifteen seconds that it is still working, stops when it is asked
to, and can be told apart from one that has died.

**It also says three things out loud**, through the one channel an agent marked as the notified one:
that it has come up, that it is stopping, and that a schedule failed or was stopped. Not that a
schedule succeeded — a message per successful nightly job is how somebody learns to ignore the
channel. An agent with no notified channel says nothing at all, which is what configuring none asks
for.

The commands are in [`commands.md`](commands.md). This is what is underneath them.

## A live gateway keeps a Mac from idle-sleeping

On macOS, each gateway starts `/usr/bin/caffeinate -i -w <its pid>` and reads its assertion back from
the machine before it claims the name that commands report as live. The `-i` assertion prevents
**idle system sleep** while still allowing the display to sleep; `-w` ties it to the gateway's
process id, so a crash or `SIGKILL` releases it even though no cleanup code could run. Several
gateways each hold their own assertion, and macOS may idle-sleep again only after the last gateway
stops.

The helper is also checked on every beat. If it unexpectedly exits, the gateway crashes so launchd
can bring it back and re-establish the assertion; it never stays online while silently losing the
protection. If the assertion cannot be started at all, the gateway refuses to come online and says
why in its logs. A temporary machine limit is different: the start exits non-zero so launchd retries
under its throttle rather than leaving the gateway permanently down after the pressure passes. Other
platforms do nothing here. This does not override an explicit Sleep command, a closed laptop lid, or
emergency power management — it prevents the ordinary idle sleep that would otherwise take a
healthy gateway offline.

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

**That window is divided, not spent twice.** Both of the things a gateway hosts have children to
stop, so each is given a share of the twenty seconds the gateway allows itself and divides its share
again among its own children. A gateway that gave each of them the whole of it would still be
stopping when launchd ran out of patience and killed it — which orphans every child it had not
reached yet, each still holding the lock that says its work is going on.

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

### A gateway with no job is stopped by signalling it directly

Every stop above goes through the job, and for most gateways that is the whole story. Two do not have
one to go through, and a stop that only knew the one route would refuse them both — leaving a running
process no command could reach:

- **An agent whose name cannot be a launchd label.** `rundesk agents add` allows any name a directory
  may have, and a label is narrower. `rundesk gateways run` will host such an agent quite happily, so
  it is a real gateway with a real lock and no possible job. `agents add` now warns at the moment the
  name is chosen, but an agent added before that warning existed is still on somebody's disk.
- **An agent whose job launchd never actually started.** The job comes back cleanly and the name is
  still held, which is the proof the process was not launchd's to begin with.

In both cases the pid is read from the lock — so a pid is only ever signalled while the kernel says a
gateway is holding that name — and the process is sent the same signals its job would have sent it,
with the same window. The line reporting the stop says which route it took and why there was no job.

**Whether the process is really gone is decided by the lock, never by the signal's answer.** On macOS,
signalling the process group of something that has *just* become a zombie answers `EPERM` rather than
`ESRCH` — so with `--force`'s zero-second window, a gateway that had genuinely been killed reported
itself as one that would not go, perhaps one time in five. Asking the kernel who holds the lock is the
answer that cannot be wrong about this, and it is the one the command uses.

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
| It is running and nothing ever **can** supervise it | `running, NEVER SUPERVISED`, `cannot be placed` | 🔴 **No restart helps**, and none is offered. The agent's name cannot be a launchd label, so no job can ever be placed for it. Stop it with `rundesk gateways stop <agent>`; to have it supervised, add the agent again under a name of letters, digits, a dot, a dash or an underscore |
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
