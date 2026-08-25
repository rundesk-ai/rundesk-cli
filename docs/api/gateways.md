# Gateways

## gateways

One agent has one gateway: a supervised process that holds that agent's name and is brought back
when it dies. With no sub-verb it lists them, the way `agents` and `backups` do. The other five are
`start`, `stop`, `restart`, `logs` and `run`.

What a gateway is, and every state one can get stuck in, is [`gateways.md`](../concepts/gateways.md). This is
what each verb guarantees and what each refuses.

```console
$ rundesk gateways
gateways in /Users/you/.rundesk/data/agents
AGENT  GATEWAY      JOB         OVERRIDE  LOGIN ITEM
ada    not running  not placed  enabled   cannot tell
cole   not running  not placed  enabled   cannot tell
        ada: not running and no job — start it with: rundesk gateways start ada
        cole: not running and no job — start it with: rundesk gateways start cole
```

**Four columns, because no one of them can answer on its own.** `GATEWAY` is the kernel's answer and
is the one to read first; `JOB` is whether launchd is holding a job for it; `OVERRIDE` is a store
that outlives every job and can refuse to start one; `LOGIN ITEM` is what macOS has been told about
it by its owner. Collapsing those into a single word would mean inventing a verdict nothing measured
— a job that has been disabled prints as a perfectly healthy one, and a job switched off in System
Settings is gone from launchd entirely. `cannot tell` is a first-class answer in every column: the
alternative is telling somebody their gateway is fine, or switched off, on the strength of a
question that failed.

Where they stand is printed even when there are none, because "no gateways" and "no gateways *here*"
are different things to learn. **A listing that answered exits `0`, whatever it found** — the exit
code says whether the question was answered, not whether the machine is healthy. What a bad state
costs is the word `running`, which no row gets unless it earned it:

```console
$ rundesk gateways
gateways in /Users/you/.rundesk/data/agents
AGENT  GATEWAY                            JOB         OVERRIDE  LOGIN ITEM
ada    not running                        not placed  enabled   cannot tell
cole   running, UNSUPERVISED (pid 96111)  not placed  enabled   cannot tell
        ada: not running and no job — start it with: rundesk gateways start ada
        cole: a gateway is holding this name and launchd has no job behind it — nothing brings it back when it stops, and nothing starts it at the next login. Run: rundesk gateways restart cole
```

A gateway holding its agent's name with nothing supervising it is the one state that looks like
health and is not, so it is never written as `running` on its own. Nothing brings it back when it
stops and nothing starts it at the next login, and somebody who read the word `running` there would
believe they were covered at the moment they were least covered.

**One row is worse than that and gets a word of its own.** An agent whose name cannot be a launchd
label is not merely unsupervised now — it can never be supervised at all, and no restart changes
that, so none is offered:

```console
$ rundesk gateways
AGENT     GATEWAY                               JOB               OVERRIDE     LOGIN ITEM
my agent  running, NEVER SUPERVISED (pid 8184)  cannot be placed  cannot tell  cannot tell
        my agent: a gateway is holding this name and launchd can never have a job for it — 'my agent' cannot be part of a launchd label. Nothing brings it back when it stops, nothing starts it at the next login, and no restart changes either of those while the agent is named this. Take it down with: rundesk gateways stop 'my agent'
```

Commands printed for such a name are quoted for a shell, so what is offered is what a shell accepts.

### gateways start

Places the job and then **proves a gateway came up**, rather than proving that launchd accepted one.
A job the supervisor took is not a process that started: the plist can be perfect and the spawn can
still fail, in which case launchd removes the job again and says so only in the unified log. So the
kernel is asked afterwards, and a start that cannot show a gateway holding the name is a failure
that says where to read next.

On macOS, the gateway establishes its idle-system-sleep assertion **before** it takes the lock the
kernel reports as running. A start therefore cannot prove the gateway came up while the Mac is still
free to idle-sleep underneath it; if `/usr/bin/caffeinate` cannot establish that protection, the
gateway refuses to come online and the start reports the refusal. A temporary machine resource
limit instead makes the gateway crash so launchd tries again after its throttle; it is never turned
into a permanent refusal that strands the gateway after the limit clears.

It is safe to run again on any state — it rewrites the job, clears an override nobody remembers,
takes back whatever was loaded under that name, and puts it back — **except on a gateway that is
already running, where it does nothing at all.** Every step of that resolver begins by taking the
old job back, which ends the gateway that is up. A start that ran it unconditionally would take an
agent down in the middle of its work in order to report that it was running, and that is not
hypothetical: an ordinary start in the build this replaces ended a live agent's whole process tree.

The exception is the one state where "already running" would be a lie:

```console
$ rundesk gateways start cole
gateways: FAILED — cole is running as pid 96111 and launchd has no job behind it
        nothing brings that gateway back when it stops, and nothing starts it at the next login.
        put it under launchd with: rundesk gateways restart cole
        nothing was started
```

A name that is not an agent on this install is refused before anything is placed, and so is an agent
nobody can ask about — a second gateway started beside a first is the one thing this must never do,
and "cannot tell" is not a quiet form of "not running".

### gateways stop

Takes the job back and then proves the name came free. **Graceful**: the gateway is sent `SIGTERM`
and given the whole of its shutdown window to finish what it was holding, because a gateway is
holding somebody's work and a stop that does not let it finish is a stop that loses some.

The job's file goes with the job, and that is what makes this a stop rather than a pause. At login
macOS bootstraps the `LaunchAgents` directory on its own, so a stop that left the file behind would
be a stop that undid itself the next time somebody logged in, with nothing anywhere having said so.

`--force` kills the gateway where it stands instead of asking it to finish. It is for a gateway that
**will not go** — one ignoring `SIGTERM`, so that a graceful stop blocks for the whole window — and
never for one that is merely busy, which is exactly the gateway with something to lose. It takes
work away mid-flight, and the command says so on the line reporting what it did, but only where a
gateway really was up: claiming it took something away from a name nothing was holding would be the
command overstating what it cost.

**A name or `--all`, one of them, never both and never neither.** The build this replaces let a bare
`restart` mean every agent, and it took down every gateway somebody had:

```console
$ rundesk gateways stop
gateways: FAILED — stop was not told which gateway
        one:   rundesk gateways stop <agent>
        every: rundesk gateways stop --all
        nothing was changed
```

That is a `2` and not a `1` — see the table at the bottom. Nobody said which gateway, so the command
line itself was wrong; the gateway is not one that would not stop.

Stopping something that was never started is not a failure. It is the state that was asked for, and
it is reported as such.

**A gateway with no job to take back is stopped by signalling the process directly.** Two gateways
have none: one whose agent is named something no launchd label can carry — `rundesk gateways run`
hosts it quite happily — and one whose job came back cleanly while the name is still held, which is
the proof launchd never started that process. Without this route both are running programs no command
can reach.

```console
$ rundesk gateways stop 'my agent'
gateway stopped for my agent as pid 8851
        this gateway had no job, so it was stopped by signalling the process directly
        why    'my agent' cannot be part of a launchd label — an agent hosted by one is named with letters, digits, a dot, a dash or an underscore
```

The pid comes from the lock, so one is only ever signalled while the kernel says a gateway is holding
that name, and whether it really went is decided by the lock rather than by what the signal answered.
See [gateways.md](../concepts/gateways.md) for why that distinction is load-bearing on macOS.

### gateways restart

A normal restart closes work admission and inspects every selected gateway before it stops one. An
active provider turn, an active schedule, or activity that cannot be inspected is a refusal:
**nothing is restarted.** For `--all`, this is one atomic preflight across the selected set, so a
busy later gateway cannot leave an earlier one already cycled. The admission barrier remains held
through the restart decision, preventing new work from entering after the quiet check.

After that preflight, restart stops, proves the old one is gone, then starts — **never the other way
round.** Starting over a job the supervisor is still holding keeps the definition it already had
*without failing*, so a restart that started first would report a restart and go on running the old
program for ever. A stop that did not clearly work therefore ends the cycle there, with the gateway
down and the failure said out loud, rather than being followed by a start that cannot mean what it
says.

`--force` bypasses the active-work refusal and means the same thing it means on `stop`: the gateway
is killed rather than asked, and whatever it was doing is taken away where it stood. What it skips
is the preflight and the *waiting*. It skips none of the proving — the new gateway is still shown
to be holding the name before the command says it restarted anything.

**Both spellings are the same stop**, which is what makes that true. `--force` was once its own path
that killed the launchd *label* and went straight on to bootstrap a replacement — correct only while
launchd holds a job for that label. Against a gateway with no job it reached nothing, and the check
that a gateway had come up was then answered by the original process, still running under its
original pid. It reported killing and replacing a gateway it had not touched, in the one state a
person runs `--force` to get out of. Both now go through the stop above, including its fall back to
signalling the process directly.

`--continue` is the explicit safe self-restart form for an active channel provider turn. It may
name only that turn's own agent and cannot be combined with `--all` or `--force`. The command
records the exact agent, turn, conversation, and admitted owner-message boundary, then returns
normally. After that turn and any scheduled work settle, the gateway exits through its already
placed supervisor job. A replacement must prove a changed pid, its running version, and the exact
origin channel connected before one direct continuation turn wakes the conversation. It resumes the
exact provider session when its provider and instruction fingerprint remain valid; otherwise it
starts a fresh session under current rules and tells the agent how to recover the recorded
conversation. A terminal or ambiguous caller, another agent, an unsupervised gateway, newer owner
input, or an already-claimed handoff wakes nobody. Without the flag, restart keeps the synchronous
stop-and-start behavior above.

As with delegation, turn identity from `RUNDESK_AGENT`, `RUNDESK_RUN`, and the matching agent home
is a correctness boundary for commands run by the brain, not containment from a hostile same-user
process: every agent already has the owner's shell. The command cross-checks all three against the
live turn so another agent's ordinary environment cannot be mistaken for the origin.

### gateways logs

What one gateway has been saying, twenty lines by default — **and, every time, what the machine's
supervisor caught around it.** Those are two orthogonal facts about one gateway and both are shown,
each labelled with the file it came from, because the case that matters most is the one where they
disagree: a gateway that started, wrote its `up` line and then died on an uncaught exception has a
perfectly ordinary day log and a traceback in a file the day log knows nothing about.

```console
$ rundesk gateways logs cole -n 5
logs for cole in /Users/you/.rundesk/data/agents/cole/logs
        what cole's own gateway wrote, in /Users/you/.rundesk/data/agents/cole/logs:
[2026-08-05 08:26:43-04:00] INFO:    gateway up for cole on 0.51.0 as pid 95177
[2026-08-05 08:26:45-04:00] INFO:    gateway stopping for cole: asked to stop with signal 15
[2026-08-05 08:28:40-04:00] INFO:    gateway up for cole on 0.51.0 as pid 96111
[2026-08-05 08:28:42-04:00] WARNING: gateway did not start: a gateway is already running for cole as pid 96111 — one agent has one gateway, and this one is standing down
        the supervisor caught nothing in gateway.out or gateway.err — everything above is the gateway's own log
```

**Three answers and never two**, for each of them. Lines, nothing yet, or could not be read — an
empty list handed back for a directory nobody may read is a report of a quiet gateway, and whoever
believes that goes looking in entirely the wrong place. So an empty source says which kind of empty
it is rather than being left out.

Nothing anywhere and nothing captured means the gateway never got far enough to write a word, which
puts the failure upstream of rundesk entirely — so what is printed is the command that finds it:

```console
$ rundesk gateways logs nina
logs for nina in /Users/you/.rundesk/data/agents/nina/logs
        what nina's own gateway wrote, in /Users/you/.rundesk/data/agents/nina/logs:
        nothing has been written by nina's own gateway yet
        and the supervisor caught nothing either — a gateway that never started at all leaves its only account in the unified log:
        log show --last 10m --predicate 'process == "launchd" OR process == "xpcproxy"' --style compact
```

Asking for no lines is refused rather than answered with nothing, and refused as a `2`, because
argparse already answers `2` for an `-n` that is not a number. One flag answering `2` for a value
that is not a number and `1` for a value that is not a count is the same mistake reported two ways,
and neither a person nor a script can tell why.

### gateways run

Be the gateway for one agent, in this terminal. This is what the job runs, and running it by hand is
how you watch a gateway start without launchd in the way.

**Its exit code belongs to launchd rather than to you**, and the whole of `gateways.md`'s exit-code
contract applies to it: every refusal exits `0`, because under this job a non-zero exit is a request
to be restarted, and a permanent condition that asked to be restarted becomes an endless loop. So an
agent that does not exist is a refusal and a `0`, and so is a name another gateway is already
holding:

```console
$ rundesk gateways run cole
[2026-08-05 08:28:42-04:00] gateway cole: this process is pid 96134, running 0.51.0
gateway: NOT RUNNING — a gateway is already running for cole as pid 96111 — one agent has one gateway, and this one is standing down
```

The first line is written before anything is parsed or read, and it is not decoration: an empty
capture file beside a job launchd says has run is the one signal that the failure is upstream of
this program.

**The claim is the check.** There is no version of this that asks whether a gateway is running and
then starts one — between the asking and the starting another gateway can arrive, and that gap is
how an ordinary start once ended a live agent's whole process tree.

On macOS that claim is taken only after `/usr/bin/caffeinate` is holding an idle-system-sleep
assertion for this process. It lasts for exactly the gateway's lifetime, including a gateway run by
hand, and the display remains free to sleep.
