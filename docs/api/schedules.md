# Schedules

## schedules

Work an agent starts because the time came, rather than because somebody asked. A schedule belongs to
one agent and lives in that agent's own records, so no other agent can run it, report on it or change
it — and the gateway hosting that agent is what fires it. With no sub-verb it lists every schedule
that can still run on the install; with an agent it lists that agent's. Expired schedules stay out of
the ordinary operational view; `rundesk schedules list [<agent>] --expired` lists only those.

What a schedule is, and every state one can get stuck in, is [`schedules.md`](../concepts/schedules.md). This is
what each verb guarantees and what each refuses.

Every agent also has one protected policy named `weekly-self-improve-upkeep`. It starts on and is
shown even before it has a stored firing. Seven distinct local calendar dates on which that agent
finishes work make one upkeep due; several turns on one date count once, and the dates may span
months. A failed or stopped turn counts as use, the upkeep turn itself does not, and a working turn
must settle before upkeep starts. After any upkeep attempt, the next seven usage dates begin a new
cycle.

The agent's gateway runs the policy through the ordinary schedule lock, process, output, settlement,
and final-report lifecycle. Its hard-coded task supplies the exact evidence interval and diary date,
then requires verified workspace/continuity maintenance, a retrospective, and evidence-based
self-improvement in that order. The review starts with bounded listings, investigates at most two
repeated frictions, and treats bookkeeping as maintenance rather than proof of improved execution.
The final is one short attention-first sentence naming the behavior improved, an honest no-change
result, or the owner action a known blocker requires; detailed evidence stays in the turn records.
Turn it on or off per agent with
`rundesk agents configure <agent> --self-improve <true|false>`. Ordinary schedule commands cannot
add, update, run, disable, or remove this protected name; the agent setting is its only control.
An owner schedule already carrying that name from before the policy remains owner-controlled and
blocks automatic upkeep until it is removed; Rundesk never adopts or overwrites it.

```console
$ rundesk schedules
schedules in /Users/you/.rundesk/data/agents
AGENT  SCHEDULE  WHEN         NEXT              LAST
ada    digest    0 9 * * 1    2026-08-10 09:00  completed 2026-08-03 09:00
cole   nightly   0 2 * * *    2026-08-06 02:00  failed 2026-08-05 02:00
cole   once      2026-09-01T06:00  2026-09-01 06:00  never ran
```

`NEXT` is a local minute, or one of three words that are not times: `off` for a schedule somebody
switched off, `expired` in an `--expired` listing for one that can never be due again, and `never`
for one whose date does not arrive — `0 0 30 2 *` says the thirtieth of February. `LAST` tells
`never ran` from an outcome, because an owner seeing only that a schedule is spent cannot tell work
that happened from work that silently did not, and it says `running` while work is in flight.

The protected upkeep row instead says `after 7 usage dates`; its `NEXT` is `off`, `due`, or the
number of additional usage dates needed. Disabling it does not erase accumulated usage, so turning
it back on starts immediately when seven dates are already owed.

**A schedule is stated on this machine's own clock.** `--when` takes the five fields schedules have
always used and `--at` takes one moment, `YYYY-MM-DDTHH:MM`. Both are kept exactly as typed. A moment
carrying a zone or a `Z` is refused rather than converted — an owner who writes one means something
rundesk cannot honour, and quietly reinterpreting it is worse than saying so. What a schedule last
*did* is recorded in UTC, because that is compared and sorted, and is shown back in local time.

### schedules add

```console
$ rundesk schedules add cole nightly --when '0 2 * * *' --run '/usr/local/bin/backup.sh --full'
schedule nightly added for cole
        when      0 2 * * *
        run       /usr/local/bin/backup.sh --full
        until     not yet
        enabled   yes
        next      2026-08-06 02:00
        last      never ran
        logs      /Users/you/.rundesk/data/agents/cole/logs
        output    /Users/you/.rundesk/data/agents/cole/schedules/nightly.out
```

**`--run` takes one string and never reaches a shell.** It is split into words the way a shell would
split them and handed straight to the program, so nothing in it is globbed, expanded, or read as `;`,
`&&` or a redirection — a schedule cannot mean one thing when a person tests it and another when the
gateway runs it.

**The program is located when the schedule is added.** A path that is not on the machine is a mistake
somebody can fix at the moment they make it; found instead by a gateway, it is a line in a log at two
in the morning saying a schedule nobody was watching did not run.

```console
$ rundesk schedules add cole nightly --when '0 2 * * *' --run '/usr/local/bin/backup.sh'
schedules: FAILED — /usr/local/bin/backup.sh is not a program on this machine — a schedule naming one that is not there can never run, so say where it really is
        nothing was added
```

`--until <moment>` is when it is finished: after it, the schedule never runs again, however often its
time comes round. `--disabled` keeps it and does not run it.

**`--ask '<prompt>'` instead of `--run`, never as well as it.** A schedule either starts a program or
asks the agent, and the records hold that as a `CHECK`:

```console
$ rundesk schedules add cole weekday-client-update --when '0 9 * * 1-5' --ask 'Post the weekday client update.'
schedule weekday-client-update added for cole
        when      0 9 * * 1-5
        ask       Post the weekday client update.
        until     not yet
        enabled   yes
        next      2026-08-07 09:00
        last      never ran
```

A schedule that asks the agent gets **a fresh conversation for every invocation**, so a run at three in
the morning never lands in the exchange somebody types into. It reports where the agent is told
things — one message when it starts and its answer when it ends, and nothing in between. If it
delegates, the returned result resumes that invocation for review and only the final reviewed answer
is reported.
[`schedules.md`](../concepts/schedules.md#what-a-run-says-on-a-surface-and-the-two-messages-it-is-allowed) is what
that looks like and what happens when there is nowhere to say it.

### schedules update

Changes one in place, keeping every record of what it has already done. **Only what is named moves**,
and `--when` and `--at` replace each other — a schedule states a repeating time or one moment, never
both. Naming nothing to change is refused rather than reported as a success.

```console
$ rundesk schedules update cole nightly
schedules: FAILED — nothing was named to change about nightly
        change one with: rundesk schedules update cole nightly --when '<cron>'
        nothing was changed
```

### schedules run

Runs one now, in this terminal, whether or not it is due — and prints what the program wrote, on the
stream the program wrote it to.

```console
$ rundesk schedules run cole nightly
backing up /Users/you/work
done, 412 files
schedule nightly completed
```

**The exit code is the program's**, so this composes in a script. A program that never started is a
`1` with no exit code quoted, because nothing ran and reporting a code would say it ran and disagreed.

**Running by hand never uses up the one moment a schedule states and never moves when it next falls
due.** Testing a schedule must not be how you stop it happening. It does write down what became of it,
because it did run — and it takes the same lock the clock takes, so it cannot start a second copy of
work a gateway is already doing.

### What a firing leaves behind

Everything a schedule's work writes is appended to `data/agents/<agent>/schedules/<schedule>.out`, and
the account of each firing is in the agent's own log beside every other thing its gateway said:

```console
$ rundesk gateways logs cole
[2026-08-05 02:00:00-04:00] INFO:    schedule nightly is due for 2026-08-05 02:00
[2026-08-05 02:00:00-04:00] INFO:    schedule nightly started as pid 4471: /usr/local/bin/backup.sh --full
[2026-08-05 02:00:31-04:00] ERROR:   schedule nightly failed with exit 2 in under 31s
[2026-08-05 02:00:31-04:00] ERROR:     rsync: link_stat "/Volumes/x" failed: No such file or directory
```

It ran, it finished, or it failed and why — and the last of those carries a bounded tail of what the
program wrote, so the file is worth opening on its own. Every way a firing does not get that far is
named rather than left silent, and [`schedules.md`](../concepts/schedules.md#when-a-schedule-is-not-doing-what-you-expected)
lists what each of those lines means and what to do about it.
