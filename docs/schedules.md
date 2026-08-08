# What a schedule is, and every state one can get stuck in

A schedule is work an agent starts because the time came. It belongs to one agent, lives in that
agent's own records, and is fired by the gateway hosting that agent — so no other agent can run it,
report on it or change it, and there is no install-wide table for two gateways to disagree over.

The one policy exception is `weekly-self-improve-upkeep`: Rundesk owns its name and decides when it
is due from that agent's own usage. It still uses every firing guarantee on this page.

## Protected upkeep follows usage, not elapsed time

Each agent starts with automatic upkeep on. Seven distinct local calendar dates containing terminal
work for that agent make one run due, however far apart those dates are. Several turns on one date
count once. Done, failed, and stopped turns count because each is evidence about how the agent was
used; a working turn does not count until it settles, and the upkeep turn never counts itself.

The first and seventh qualifying dates freeze the evidence interval and diary date in the prompt.
Any terminal upkeep attempt—done, failed, or stopped—starts a new seven-date cycle so a provider
failure cannot retry every gateway beat. Turning upkeep off retains accumulated dates; turning it
back on starts immediately if seven dates are already owed.

The policy is visible through `schedules list` and `schedules show`. `add`, `update`, `run`, and
`remove` refuse its reserved name. Its only switch is the agent's configuration:

```sh
rundesk agents configure AGENT --self-improve <true|false>
```

One compatibility exception prevents the new reservation from trapping old owner work. If an
owner schedule already used this name before the policy existed, it remains an ordinary schedule
that can be shown, updated, run, or removed. Rundesk does not adopt or overwrite it, and automatic
upkeep stays blocked for that agent until the owner schedule is removed.

The gateway supplies the interval and runs verified maintenance, retrospective, and self-improvement
in order. Detailed evidence remains in the turn; the surfaced final is one short attention-first
sentence. The protected row is inert to ordinary cron evaluation and exists only to carry the
frozen prompt, lock, process record, output, and last attempt through this ordinary lifecycle.

[`commands.md`](./commands.md#schedules) is what each verb guarantees and what each refuses. This is
what a schedule *is*, and what to do when one is not doing what you expected.

## Two halves that know nothing about each other

**When it is due** is arithmetic over what somebody typed, and it asks nothing of the machine but the
time — which is passed in. A year of firings is decided in a millisecond, and the clock being an
argument is why.

**What it starts** is carried and never read on the way. The kind of work is one branch in one place,
so what a schedule *does* — start a program, or ask the agent — changes nothing about deciding *when*.

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

## What a run says on a surface, and the two messages it is allowed

A schedule that **asks the agent** reports where the agent is told things — the one channel marked
`notified`, at its `notify_place`. Two messages, and never a third:

| When | What goes out |
|---|---|
| the run starts | `💻 Working on '<schedule>' — I will report back when it is done.` |
| the run ends | what the agent answered, **as a reply to that notice** |

**The notice exists so the report has somewhere to land.** Without it, work that began at six in the
morning first shows itself as an answer arriving twenty minutes later beside answers to other
questions, tied to nothing. Rundesk keeps whatever the platform called the notice and quotes it at the
end, so the two read as one exchange.

**A schedule that starts a program says neither**, and that is the same rule rather than an exception:
a program has no answer to report, so promising to report back is a promise rundesk would not be
keeping. One that *fails* is still said out loud, exactly as before.

**Nothing between the two ever reaches the surface.** A scheduled turn runs in a process of its own
which holds no channel, so its working notes have nothing to be posted through — the whole run is in
the agent's records and in `<schedule>.out`, and the report is the only thing a person is shown. That
is a property of where the work runs, not a filter anybody has to maintain.

**A run that could not announce still reports.** A gateway that has just come up fires a schedule due
in that same minute before its adapters have finished connecting, so there was nobody to tell that the
run had begun; its answer still goes out, standing on its own rather than under a notice. The same is
true of an agent with no notified channel — nothing is said at either end, which is what somebody who
configured no channel asked for.

**A gateway that came up after the one which started the work still reports.** Both facts the report
needs — that this run owes one, and the notice it goes under — are written beside the firing before
the work starts, so they outlive the process that announced.

## What is not built

A schedule asks the agent with `--ask` or starts a program with `--run`, and exactly one of the two —
the records hold that as a `CHECK` and the command says it in words. Every invocation of an
agent-asking schedule gets **a fresh conversation and provider session**, so tonight cannot inherit
last night's context and a run at three in the morning never lands in the exchange somebody types
into. It may delegate to a named agent; that result returns to the same invocation session for review,
and the reviewed final report goes to the agent's notified channel.

`rundesk schedules run` takes either kind by hand, and neither uses up the minute it next falls due —
testing a schedule must not be how you stop it happening.

What is still not built: a schedule carries `provider_name` and `model_name` columns that nothing
writes. A schedule runs on the agent's own brain, and a way to override that per schedule is a verb
nobody has asked for. The `channel` and `channel_place_id` columns are the same — **where a run
reports is the agent's notified channel and is not stated per schedule**, so those two are still
written by nothing. A schedule that reports somewhere of its own is a verb nobody has asked for
either, and the columns are what it would be built on.
