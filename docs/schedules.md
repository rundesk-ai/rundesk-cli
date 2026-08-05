# What a schedule is, and every state one can get stuck in

A schedule is work an agent starts because the time came. It belongs to one agent, lives in that
agent's own records, and is fired by the gateway hosting that agent — so no other agent can run it,
report on it or change it, and there is no install-wide table for two gateways to disagree over.

[`commands.md`](./commands.md#schedules) is what each verb guarantees and what each refuses. This is
what a schedule *is*, and what to do when one is not doing what you expected.

## Two halves that know nothing about each other

**When it is due** is arithmetic over what somebody typed, and it asks nothing of the machine but the
time — which is passed in. A year of firings is decided in a millisecond, and the clock being an
argument is why.

**What it starts** is carried and never read on the way. The kind of work is one branch in one place,
so the day rundesk can run a provider, nothing about deciding *when* changes.

## The machine's own clock, and the one hour a year that repeats

`--when`, `--at` and `--until` are local, kept exactly as typed, and matched against this machine's
clock. That is not an exception to [`time.md`](./time.md) — those are a *statement about the future*,
and somebody who writes `0 9 * * *` means nine o'clock where they are. What a schedule last **did** is
a record: UTC, compared and sorted, shown back in local time with its offset.

A moment carrying a zone or a `Z` is refused rather than converted. An owner who writes one means
something rundesk cannot honour, and reinterpreting it quietly would be wrong by an hour for part of
the year and invisible for the rest of it.

The consequence is that a repeated wall-clock hour is something rundesk has to survive rather than
avoid. **What has already fired is compared with a strict "after", never "different from".** A clock
does not only stand still, it goes backwards — an hour repeats every autumn and a correction can step
it back at any time — and asking whether this minute *differs* from the last one lets every minute of
that hour through, which is an hour of double-firing once a year for anything running more often than
hourly.

## A schedule runs once for the minute it is due, across a restart

The minute a firing is claimed for is written to the agent's records **before the work starts**, and
if that write fails nothing is started at all. Better not to run than to run twice: work that visibly
happened with nothing recording it is work that repeats on the way back up.

That is also why the guard is durable rather than held in memory. The build this replaces kept it in
the gateway process, so a crash between starting and finishing — plus a supervisor bringing the
gateway back within seconds — ran the same schedule twice for the one minute it was due.

**A minute that passed while nothing was running is not run late.** Not because anything suppresses
it: being due is only ever asked about *now*, and there is no backlog anywhere to replay. A gateway
coming up on Monday does not fire Friday's.

## The claim is a lock, and the work itself holds it

Before a firing starts, rundesk takes an exclusive lock on `<schedule>.lock` in the agent's
`schedules/` directory — and hands the open descriptor **to the child**. A lock of this kind belongs
to the open file, not to a process, so it lives exactly as long as the work and everything the work
started, and the kernel drops it however that ends: a clean exit, a crash, a kill, the machine losing
power.

Three things follow, and each was a defect in the build this replaces:

- **A schedule cannot begin again while the last one is still going, across processes.** The old
  build guarded inside the gateway, so `rundesk schedules run` typed at a terminal knew nothing about
  it and could start a second copy of the same work.
- **A schedule is never shown as running when it is not.** The question goes to the kernel, never to
  something a process wrote down — a recorded process id is a number that gets reused, and a gateway
  killed outright leaves it pointing at a stranger's program.
- **A gateway that came up after the one which started the work still knows work is going on.** It
  adopts it rather than starting a second, and reports honestly when it ends.

## The three outcomes, and why one of them is not a failure

| | What it means |
|---|---|
| `completed` | it ran and said it was happy — rundesk collected the exit code |
| `failed` | it ran and said it was not, or it never started at all |
| `stopped` | **nobody can say** — whatever was watching went away first |

`stopped` is not a kind of failure. A status belongs to the process that started the work, so a
gateway that was killed, or one that came up after the work began, has no way to learn it. Work that
may well have finished perfectly is never written down as having failed.

## When a schedule is not doing what you expected

Everything below is read from `rundesk schedules list <agent>`, `rundesk schedules show <agent>
<schedule>` and `rundesk gateways logs <agent>`. Between them they say which of these it is.

| What you see | What it is |
|---|---|
| `NEXT` says `off` | somebody disabled it. `rundesk schedules update <agent> <name> --enable` |
| `NEXT` says `expired` | its `--until` has passed, or it stated one moment and that moment is gone |
| `NEXT` says `never` | its date does not arrive — `0 0 30 2 *` says the thirtieth of February |
| `NEXT` says `cannot be read` | the row is there and cannot be understood. `show` says why |
| `LAST` says `never ran` and `NEXT` is in the past | its minute went by while no gateway was up, and it is deliberately not run late |
| `LAST` says `running` and has for hours | the work has not finished. The log says when it started; `<schedule>.out` says what it has written |
| nothing in the log at all | no gateway is up for that agent. `rundesk gateways` |
| `skipped: what it started last time is still running` | the previous firing has not ended, so this occurrence was let go and said so |
| `did not start` | the program is not on the machine, or is not executable |
| `was interrupted: the gateway that started it is gone` | a gateway went away mid-run, and what the work came to cannot be read |

**A schedule nobody can understand does not stop the others.** A typo in the fourth of five is a
reason to say so about the fourth, and it is said **once** rather than every fifteen seconds — a bad
cron does not fix itself, and a log that grew with the complaint would bound itself out of the
evidence.

## Nothing a schedule does can take a gateway down

A firing that could not be recorded, a program that is not on the machine, a disk that filled — none
of them ends the process hosting the agent. That is not politeness: a gateway exiting non-zero is a
request to be restarted, so a permanent condition would become an endless restart that escalates into
the supervisor's throttling and simply looks like a hang.

The other side of the same rule is that a gateway going down **does** take its work with it, inside
the window the supervisor allows before it kills the gateway outright. Work started in a session of
its own is outside the supervisor's reach, so if the gateway does not stop it, nothing will.

## What is not built

Nothing in this release runs a provider, so a schedule that asks an agent rather than naming a program
cannot be started — and there is no way to type one. The records hold that kind, the clock decides it,
and the firing path has the seam for it, so the day a provider process lands nothing about an agent's
records has to move. Until then it is not on the command, because a verb rundesk cannot perform is a
verb rundesk does not have.

Channels are the same: a schedule carries where it would report, and nothing reads it yet.
