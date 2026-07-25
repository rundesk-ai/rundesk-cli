# Suggestions

**Open findings only.** Each was reproduced against the implementation that existed when it
was written, and each is still true. What has been fixed is deleted rather than kept as
history — the ledger is a work list, not an account of what was done, and a resolved entry
in it is one more thing to read before finding the thing that matters. Numbers are never
reused and gaps are expected: they are cited in commits, in `ROADMAP.md` and in each other.

Three findings are **partly** closed and say in their own status which half is still open —
4, 6 and 9. Read the status before the body.

**Where they came from.** Round two (6–22) reviewed the runtime and lifecycle against
`205467b`, with reproduction scripts and their output quoted inline. Round three (23–25)
followed up on the gateway foundation against `7841a0f`. Round four (26–29) asked which
store is authoritative for each runtime fact, against `43315ae` — **by reading the code and
by path arithmetic, not by running anything**, so treat its claims as verified against the
source and unverified at runtime. Round five (30) reviewed runtime readiness. Round six
(31–38) reviewed the command surface: whether an owner can operate Rundesk without knowing
its files or launchd plumbing. Candidates were always matched by underlying failure rather
than by wording, so each entry carries one implementation plan and one complete set of
regression criteria.

## Future low-level review focuses

Rundesk is intended to keep one gateway per agent online through `launchd`, run
Claude CLI or Codex CLI directly, and later relay provider events, questions and
approvals through channels such as Discord. Review the areas below before adding
those layers. Report only reproduced defects or concrete risks in the current code;
measured evidence may also justify concluding that no change is needed.

**Round two covered every area below.** Where it found something, the finding number is
named. Where it found nothing, that is recorded as a conclusion rather than left blank,
so a later round does not spend the effort again without new reason:

| Area | Outcome |
|---|---|
| Ownership, cleanup and bounded resources | findings **8**, **9**, **12**, **16**, **17**, **23**, **30** |
| Crash recovery and idempotency | findings **9**, **12**, **23**, **26** |
| Concurrency, locks and atomic decisions | findings **10**, **12**, **14**, **21**, **30** |
| Provider protocol boundary | **no change needed** — see "Reviewed, no change needed" below |
| Scheduling correctness | findings **12**, **21**, **24**, **25**, **26** |
| Install, update and removal safety | findings **4**, **14**, **15**, **28** |
| Source of truth and auditability | findings **26**, **27**, **28**, **29**; extensions to **12**, **17**, **19** |
| Consumer command surface | findings **31–38**; extensions to **6**, **13**, **17**, **27**, **28** |
| Measured performance | finding **9** (second consequence) and **17**; measurements below |
| Failure-injection coverage | see "Tests that prove only the easy half" below |
| Security and trust boundaries | **no change needed today** — see below |

### Ownership, cleanup and bounded resources

Findings 1 and 3 already cover surviving descendants and unbounded post-exit drains;
do not report them again unless they have regressed. Extend the review across every
owned process, task, pipe, file handle, queue and buffer:

- Success, failure, cancellation, silence, gateway shutdown and launchd termination
  must all reach the same truthful cleanup result.
- Slow consumers, unavailable channels, malformed or oversized records and provider
  output floods must not create unbounded memory, disk use or retries.
- Backpressure must not block the provider process, silently discard required
  records or allow a failed delivery task to disable all later delivery.

Relevant implementation: `Program`, `Held` and `end_all()` in
`src/rundesk_cli/process.py`, and program ownership in
`src/rundesk_cli/gateway.py`.

### Crash recovery and idempotency

Review gateway crashes, machine restarts, partial writes, interrupted schedules and
repeated CLI requests. A retry must not duplicate work, erase the only recovery
record or report a recovered state that was not proven. Finding 1 is the existing
regression reference for keeping recovery evidence when descendants may still live.

Relevant implementation: runtime and interruption records in
`src/rundesk_cli/gateway.py`, schedule outcomes in
`src/rundesk_cli/schedule.py`, and restart commands in
`src/rundesk_cli/cli.py`.

### Concurrency, locks and atomic decisions

Review simultaneous CLI commands, schedule changes, schedule firing, shutdown,
restart and update. A lock must cover the complete decision and mutation it claims
to protect, not only the initial check. Confirm that each durable fact has one writer
at a time and that an older completion cannot overwrite newer state.

Relevant implementation: gateway and schedule locks in
`src/rundesk_cli/gateway.py`, schedule mutation and outcome writes in
`src/rundesk_cli/schedule.py`, and active-work checks in
`src/rundesk_cli/updater.py`.

### Provider protocol boundary

Confirm the low-level runtime provides bidirectional process transport, ownership,
cancellation and bounded delivery without interpreting Claude, Codex, Discord,
approval or conversation semantics. Provider adapters should interpret provider
events; channel adapters should present them. Recommend a new boundary only when
current code would otherwise force those semantics into the runtime.

Relevant implementation: structured input and output in
`src/rundesk_cli/process.py` and orchestration in
`src/rundesk_cli/gateway.py`.

### Scheduling correctness

The original review excluded scheduling. Review time zones, daylight-saving
transitions, day-of-month/day-of-week rules, missed runs, long-running work,
non-overlap, restart recovery and outcome ordering. Due-time calculation should
remain pure; the gateway should own the work it starts; durable outcomes should
never move backward.

Relevant implementation: `src/rundesk_cli/schedule.py`, scheduled work in
`src/rundesk_cli/gateway.py`, and `tests/test_schedule.py`.

### Install, update and removal safety

Finding 2 covers proving that launchd and a gateway released a job. Findings 4 and 5
cover truthful start and restart outcomes. Do not duplicate them unless they regress.
Extend the review to updates racing active work, partial replacement, rollback,
multiple installed gateways and whether every destructive step preserves enough
state for a safe retry.

Relevant implementation: `src/rundesk_cli/updater.py`,
`src/rundesk_cli/supervisor.py`, `src/rundesk_cli/cli.py` and `install.sh`.

### Measured performance

Measure idle CPU, memory per gateway, message throughput, log growth, process startup
and shutdown time under realistic long-running workloads. Recommend optimization
only for a reproduced bottleneck, and prefer removing work or bounding it over
introducing caching or concurrency.

Relevant implementation: `src/rundesk_cli/process.py`,
`src/rundesk_cli/gateway.py` and log rotation behavior.

### Failure-injection coverage

Check whether tests exercise killed leaders and descendants, broken pipes, cancelled
tasks, failed or slow receivers, malformed records, permission errors, full-disk or
atomic-write failures, launchctl timeouts and interrupted updates. Missing tests are
actionable only when they protect a named behavior or failure path.

Relevant tests: `tests/test_process.py`, `tests/test_gateway.py`,
`tests/test_supervisor.py`, `tests/test_updater.py` and
`tests/test_schedule.py`.

### Security and trust boundaries

Review command construction, executable and path validation, inherited environment,
file permissions, untrusted provider output, secrets in logs and the future
authorization boundary for Discord replies and approvals. A channel user must never
gain broader process or filesystem authority merely by supplying message content.

Relevant implementation: process creation in `src/rundesk_cli/process.py`, launchd
job creation in `src/rundesk_cli/supervisor.py`, state and logs in
`src/rundesk_cli/gateway.py`, and archive handling in
`src/rundesk_cli/updater.py`.

## High impact

### 4. Do not report an unsupervised gateway as successfully started

**Status:** Open — **the missing-job half is closed; the same-name/PID half is not.**
`start` now asks whether launchd holds a job at all. See also **finding 15**, which shows
that the unsupervised gateway `start` learned to recognise is still invisible to uninstall.

`supervisor.loaded()` answers only whether launchd holds a job with the gateway's name (`supervisor.py:183-197`). `cmd_start()` treats
that boolean as proof that launchd owns the process currently holding the gateway
lock (`cli.py:290-298`), and `cmd_status()` uses the same inference for its
`SUPERVISED` column (`cli.py:484-495`). A dormant launchd job and a manually started
same-name gateway can therefore coexist. The job is loaded, but it does not own the
gateway PID and will not bring that process back when its terminal exits.

Reproduced with a running gateway PID 7 and a same-name loaded job whose interface
cannot identify an active PID:

```text
start=(0, 'gateway: ALREADY RUNNING (pid 7)')
status='gateway  RUNNING  7  ...  SUPERVISED yes'
```

The missing-job fix asks the right system and still asks too weak a question. The
smallest truthful answer is the active PID launchd owns for this job, compared with
`Standing.pid`; a loaded job with no active PID or a different PID is not supervising
the current gateway.

Regression criteria:

- "Already running" is success only when the supervisor confirms that its active job
  owns the same PID as the gateway record.
- A loaded but dormant same-name job, or one with a different PID, does not make a
  manually started gateway supervised.
- An unsupervised running gateway is reported as unsupervised with a non-zero exit.
- An unanswered supervisor query cannot be reported as success.
- `status` applies the same PID identity rule as `start`.

Relevant implementation: `loaded()` in `src/rundesk_cli/supervisor.py`;
`cmd_start()` and `cmd_status()` in `src/rundesk_cli/cli.py`.

# Round two — 2026-07-25

Line numbers are against `205467b` plus the in-flight `_keep` edit to `process.py`.
`gateway.py` numbers match `HEAD`; `process.py` numbers below line ~320 sit 8 lines
above their `HEAD` equivalents.

All 384 tests pass alongside every finding below (`test_process` 84, `test_gateway` 103,
`test_cli` 73, `test_updater` 54, `test_install` 39, `test_supervisor` 38,
`test_schedule` 28). Four of these findings are contradicted by a test that names the
exact risk and then proves only the easy half; those are listed together at the end.

## Critical

### 6. Report a gateway whose liveness cannot be established as running, not stopped

**Status:** Open — **the destructive half is closed; what is left is an owner decision.**
Nothing now signals a process group on the strength of this answer: the stray sweep *takes*
the target's name and keeps it, and a name it cannot take is skipped untouched (R-GW-29).
What remains is purely what an owner is *told*.

`_held()` answers `False` for *every* `OSError` on opening the lock file, so "I could not
ask" becomes "it is not running", and `standing()` reports a live gateway as STOPPED:

```python
    try:
        handle = os.open(path, os.O_RDWR)
    except OSError:
        return False            # EACCES, EMFILE/ENFILE, EIO — all read as "not running"
```

This inverts a rule the same codebase states twice and comments at length: `_still_there()`
treats an unreachable group as *still there*, and `supervisor._still_holds()` treats silence
as *yes*.

**And it is the owner's call, not an oversight.** R-GW-9 is ratified with `a lock that
cannot be opened is not read as running` as part of its evidence — a test that asserts
exactly the behavior this finding wants reversed. `AGENTS.md` makes a change to ratified
behavior the owner's decision, so this waits on that decision rather than on an
implementation.

**The same decision, from round six.** When the lock *is* held but `<name>.json` is
unreadable, `standing()` maps the record to `{}`, `Standing.stale` reads a missing beat as
not stale, and `cmd_status()` prints `RUNNING`, no PID or version, `WORK idle`, and exits
zero. The process is known to exist and everything about its health is unknown. That should
be `STATE UNREADABLE`, `PID ?`, `WORK ?`, with `rundesk logs <name>` as the next action and
a non-zero result.

Regression criteria, if the owner takes it:

- A lock that cannot be opened for any reason other than "it is not there" is reported as
  held, never as free.
- A gateway whose liveness cannot be determined is not reported as stopped.
- A held gateway lock with unreadable state is never reported as plain `RUNNING` or `idle`;
  status names the unreadable state, points to its log and exits non-zero.

Relevant implementation: `_held()` and `standing()` in `src/rundesk_cli/gateway.py`;
`cmd_status()` in `src/rundesk_cli/cli.py`.

# src/rundesk_cli/gateway.py:593-617
    try:
        handle = os.open(path, os.O_RDWR)
    except OSError:
        return False            # EACCES, EMFILE/ENFILE, EIO — all read as "not running"
```

`_sweep_strays()` runs inside every `claim()` (`gateway.py:774`), over every record in
the run directory, and keys a `SIGTERM`/`SIGKILL` of a whole process group off that one
answer (`:483`, `:500`). `_held()` is therefore the only thing standing between a
routine gateway start and a tree-kill of another agent's live session. `standing()`
reads it too, so the same misread reports a running gateway as STOPPED.

This inverts a rule the same codebase states twice and comments at length:
`_still_there()` (`gateway.py:302-317`) treats an unreachable group as *still there*,
and `supervisor._still_holds()` (`supervisor.py:200-210`) treats silence as *yes*.
`_held()` — the most destructive of the three — is the one that reads unknown as gone.
Finding 2 fixed exactly this conflation on the launchd side; it was never applied here.

Reproduced outcome (`_held` made to fail on open, standing in for the OSError; the
consequence is the code path, not the trigger):

```text
alpha_holds_its_name=True
alpha_live_work_group=15742
held_says=False
standing_reports_running=False
second_gateway_swept=['alpha/turn']
alpha_work_group_alive_after=False
alpha_still_holds_lock=True
alpha_turn_outcome='failed'
```

A second, independent face of the same defect: even when `_held()` works it is asked
*once*, before the record is read, and never re-asked before the signal. The code
already re-asks immediately before the far less destructive `unlink` (`:496-501`, with
a comment explaining why); the kill has no such re-check. Reproduced with the race
executed deterministically:

```text
alpha_running=True  work_group=14189  alive=True
log="ending 'turn' (group 14189), left running by a gateway that is gone"
beta_swept=['alpha/turn']
alpha_work_group_alive_after=False
alpha_still_holds_name=True
```

Round three confirmed that one more liveness check is still insufficient: the target
can claim its name immediately after that check and before the signal. The lock has
to cover the decision it protects. A stray sweeper should open the target's lock,
take it exclusively without waiting, and hold it across the record read, identity
checks, signals and possible deletion. A claimant already holds that same lock across
predecessor cleanup and its initial record. If the sweeper cannot acquire it, the
target is live or unknown and must be skipped.

**Round six adds the opposite status lie from the same unknown-as-known policy.**
When the lock is held but `<name>.json` is malformed or unreadable, `standing()` maps
the record to `{}` (`gateway.py:643-663`). `Standing.stale` treats a missing beat as
not stale (`:611-615`), and `cmd_status()` consequently prints `RUNNING`, no PID or
version, `WORK idle`, and exits zero (`cli.py:472-507`). The process is known to exist;
everything about its health and work is unknown. That must be `STATE UNREADABLE`,
`PID ?`, `WORK ?`, with `rundesk logs <name>` as the next action and a non-zero status
result.

Regression criteria:

- A lock that cannot be opened for any reason other than "it is not there" must be
  reported as held, never as free.
- A gateway whose liveness cannot be determined must not be reported as stopped.
- The stray sweep holds the target name's lock continuously from its final liveness
  decision through record reconciliation, process signalling and record deletion.
- A non-blocking failure to acquire that lock skips the target without reading or
  signalling its work.
- No gateway start may end a process group belonging to a gateway that holds its name.
- A two-process barrier test pauses a sweeper at the old check/act boundary, lets the
  target claim and start recorded work, and proves the target group and record survive.
- A held gateway lock with malformed or unreadable state is never reported as plain
  `RUNNING` or `idle`; status names the unreadable state, points to its log and exits
  non-zero.

Relevant implementation: `_held()`, `standing()` and `_sweep_strays()` in
`src/rundesk_cli/gateway.py`.

### 8. Give the receiver its own budget, and say what it never got

**Status:** Open — **do not solve this by widening the post-exit drain.** That deadline was
narrowed deliberately, and `DRAIN_SECONDS` is one budget for the whole post-exit drain.
The same constant is now serving three unrelated purposes, and one of them is the
opposite of a drain:

- `Program.wait()` (`process.py:590`) — how long a leftover descendant may hold the
  pipe. Correctly short, and deliberately so.
- `_settle()` (`process.py:659`) — how long the *receiver* gets to take what it is
  owed. Wrongly short, and shared with the stderr drain.
- `close_input()` (`process.py:797`) — how long a stdin close may take to flush.

When `_settle()`'s budget runs out it cancels delivery and discards whatever `Held`
still holds. The `undelivered` counter added in `205467b` makes this audible in the
gateway log, which is a real improvement, but the records are still lost, `Result.ok`
is still `True`, and — unlike every other loss in this module — **no `Gap` reaches the
receiver**, so its own stream never learns it was truncated.

Reproduced outcome, production constants, a receiver taking 0.2s per record (a Discord
post under rate limiting is slower than that):

```text
DRAIN_SECONDS=2.0
result_reason='finished'
result_ok=True
records_written_by_program=50
records_the_receiver_got=9
program_undelivered=41
program_refused=0
elapsed=2.0s
```

Round five confirmed a second form of the same missing-delivery answer while the
program is still running. `_deliver()` removes a record from `Held` before invoking
the sink (`process.py:715-726`). If the sink raises, the exception path only increments
`refused` (`:733-737`): the record is gone, delivery continues with the next record,
and no `Gap` tells the recovered receiver where its stream broke. `Gateway.start()`
does not log the refused count until the provider finishes (`gateway.py:966-970`), so
a long-lived Claude or Codex process can lose an approval or clarification request and
remain waiting while Discord receives later events as though nothing were missing.

Reproduced with a sink that failed once and then recovered:

```text
receiver_after_failure=[b'two', b'three']
refused=1
gap_seen=False
```

The fix is to split the constant, **not** to loosen the post-exit drain deadline —
those are different deadlines that happen to share a name today. The read loop is
finished and the program is gone by the time `_settle()` runs, so nothing is waiting on
the receiver. While a program is still running, the current record must remain pending
until the sink accepts it; retry uses bounded backoff, later output remains inside
`HELD_BYTES`, and eviction still becomes an ordered `Gap` rather than silent loss.

Regression criteria:

- The receiver's budget is a separate, generous constant, settable by the caller that
  knows its own sink; the descendant drain keeps its short shared deadline.
- A sink that fails temporarily and then recovers receives the pending record before
  any later record, or receives an exact ordered `Gap` before later records if the
  bounded queue had to evict it.
- A failed sink cannot spin, block the provider process or grow the queue beyond its
  byte budget.
- Records still held when that budget runs out are handed over as a `Gap` before
  delivery is cancelled, so the loss appears in the receiver's own stream.
- `Result` carries the undelivered count, and a run that lost records does not report
  `ok`.
- Finding 3's regression criteria still hold afterwards.

Relevant implementation: `Program.wait()`, `_settle()`, `Held` and `DRAIN_SECONDS` in
`src/rundesk_cli/process.py`; the log lines in `Gateway.start()` in
`src/rundesk_cli/gateway.py`.

### 9. Refuse work whose ownership cannot be established at the moment it starts

**Status:** Open — **read finding 23; this is the same transaction.** The half that
destroyed a proof already held is closed: `since` is asked for once, when the program is
registered, kept in `Gateway._known_since`, and read from there by every later record, so a
`ps` that fails or times out can no longer write `null` over an answer that was correct. The
look also moved off the event loop, so a beat no longer shells out once per running program
(R-GW-30).

What remains is the *initial* look. `started_at()` can fail the first time as easily as the
hundredth — it is a subprocess with a five-second budget, on the loaded machine where this
matters most — and `Gateway.start()` accepts the child and records `"since": null` when it
does. That work is never recoverably owned: no successor will ever act on it, and the group
becomes a permanent orphan, a provider CLI plus its editors, language servers and search
tools, holding a workspace until the machine reboots.

```text
record_after_start={'work': {'pgid': 8012, 'since': None}}
successor_log="left 'work' (group 8012) alone: the record cannot prove it is ours"
successor_swept=[]
group_still_running=True
```

Capturing once is therefore only sufficient if establishing the fingerprint is part of the
startup transaction described in finding 23: if it cannot be established, end the new
process group and fail the start.

Regression criteria:

- A new process whose initial fingerprint cannot be established is ended, and is not
  accepted as running work.
- Work left by a gateway is still swept after a beat the machine did not answer.

Relevant implementation: `Gateway.start()` and `started_at()` in
`src/rundesk_cli/gateway.py`.

## High impact

### 10. Serialise writes to one program

**Status:** Open

`send()` (`process.py:747-777`) does `write()` then `await drain()` with nothing
serialising the pair. On CPython ≤ 3.11 `FlowControlMixin._drain_helper` holds a single
`_drain_waiter` and asserts nobody else is waiting; on 3.12+ it holds a list and the
problem disappears. This project's floor is **3.9** (`AGENTS.md` "Tech stack";
`.github/workflows/build.yml` matrix `{ ubuntu-latest, python: '3.9' }`), which is also
`/usr/bin/python3` on macOS.

Reproduced outcome under `/usr/bin/python3` (3.9.6), two concurrent sends larger than
the pipe buffer to a program that is not reading:

```text
send_1='NotListening: it is not there to be written to'
send_2='AssertionError'
stderr='Future exception was never retrieved: BrokenPipeError(32, "Broken pipe")'
```

Under `python -O` the assert vanishes and the second waiter overwrites the first, so the
first `send()` is never woken — a permanent hang instead of an error. The caller gets an
`AssertionError` rather than the `NotListening` it is written to handle, and the bytes it
already queued stay in the transport buffer.

Two channel messages arriving close together, or an approval answer racing a queued user
message, is the ordinary case for this product.

Regression criteria:

- Two concurrent writes to a program that is not reading complete without error and in
  the order they were issued, on the oldest supported Python.
- The test proving write ordering uses records large enough to pause the transport;
  small ones never reach the code path (see "Tests that prove only the easy half").

Relevant implementation: `Program.send()` in `src/rundesk_cli/process.py`.

### 12. Keep the shutdown budget inside the one launchd allows

**Status:** Open

launchd's default `ExitTimeOut` is 20 seconds and `describe()`
(`supervisor.py:129-165`) does not set it. The gateway's own budget adds up past that:

| step | cost |
|---|---|
| `asyncio.wait_for(end_all(...), STOP_SECONDS)` (`gateway.py:542`, `:1056`) | up to 15.0s |
| `self._say()` on the not-drained path (`:1075`) | N × up to `PS_TIMEOUT_SECONDS` (5.0s), blocking the loop — see finding 9 |
| `_note_interrupted()` per program (`:1078-1081`) | N file rewrites |
| `asyncio.run` cancelling in-flight `start()` tasks — each `wait()` does `await self.end()` (2 × `GRACE_SECONDS` = 10s) then `_settle()` (2s) | unbounded, counted against nothing |

Past 20 seconds launchd sends `SIGKILL`, the gateway dies without finishing `_go()`, and
because every program is deliberately in its own session the whole tree survives with
nothing owning it — a surviving descendant nobody owns, reached by a different
route.

The task ownership is split inside `Gateway` itself. `serve()` retains only the beat and
tick tasks in local variables (`gateway.py:1047-1053`), while `_fire()` creates each
scheduled run with bare `asyncio.ensure_future()` and retains it nowhere
(`gateway.py:1165`). Its lifetime is therefore defined by the outer `asyncio.run()`
destroying the whole loop, not by the gateway that started it. The current cancellation
test has to search `asyncio.all_tasks()` by function name to recover the scheduled task
(`tests/test_gateway.py:1219-1223`), which is evidence that there is no owned handle to
assert against. That assumption directly obstructs provider streams, approval waits and
channel delivery tasks: they will share a long-lived loop, while cycling one gateway must
still affect only that gateway.

The smallest separation is one private task set per gateway and one spawn helper that
registers a task and removes it when done. Beat, tick and scheduled runs use it; `_go()`
cancels and awaits that set before releasing the gateway. Finding 12 must establish one
overall shutdown deadline shared by task cancellation, `end_all()`, reporting,
interruption writes and release; adding another independent timeout would only extend
the overrun this finding describes. This is not a task framework or a new module. It
gives the lifecycle owner a direct handle on work it already creates.

Round three proved the durable-state consequence, not only the shutdown-budget one.
`_go()` releases the gateway lock (`gateway.py:1083`) before an untracked scheduled
wrapper necessarily reaches `_remember()` (`:1154-1173`). `_remember()` has no
`_released` guard and writes the old gateway's whole in-memory `_outcomes` snapshot.
A successor can therefore claim the name and write a newer outcome, then have the old
wrapper overwrite it:

```text
before_old_finishes={'at': '2026-07-25 09:01', 'outcome': 'new successor result'}
after_old_finishes={'at': '2026-07-25 09:00', 'outcome': 'finished'}
```

This is the same missing task ownership, not a separate persistence abstraction.
Cancelling and awaiting the gateway's task set before releasing the name gives the
history one writer and closes both failures.

**Round four adds the one-line containment, and where the asymmetry shows.** The reaching
path is not exotic: it is the ordinary one. `_go()` releases at `gateway.py:1083`, `serve()`
returns, and `asyncio.run` then cancels the untracked wrapper, whose `CancelledError`
handler calls `_remember(one.name, "interrupted", fired)` (`:1162`) — by design, and after
the release. `_say()` already refuses to write once released, for exactly this reason
(`:1224-1225`); `_remember()` (`:1209`) does not. Adding `if self._released: return False`
to `_remember()` is not the fix for the missing task ownership, and does not remove the
shutdown-budget half of this finding, but it stops the durable outcome from moving backward
in the meantime and costs one line. Do it as containment; do not let it stand in for the
task set.

Regression criteria:

- `ExitTimeOut` is stated in the job rather than assumed, and is above the gateway's own
  worst-case shutdown.
- Every background task a gateway creates is retained by that gateway, removed when done,
  and cancelled and awaited within the same overall shutdown deadline as `_go()`'s other
  cleanup rather than left to `asyncio.run`.
- No task created by a gateway can call `_remember()` or write any other gateway-owned
  state after that gateway releases its name.
- A test keeps the event loop alive after one gateway stops and asserts its owned task set
  is empty, its scheduled run is recorded as interrupted, no child survives and another
  gateway's tasks remain untouched; it never inspects global tasks.
- A successor writes a newer schedule outcome while the old wrapper is deliberately
  held; releasing the old wrapper cannot move the durable outcome backward.
- A gateway with work that will not stop still exits inside the time the machine allows,
  asserted as wall-clock from `SIGTERM` to exit.

Relevant implementation: `Gateway._go()` and `Gateway.serve()` in
`src/rundesk_cli/gateway.py`; `describe()` in `src/rundesk_cli/supervisor.py`.

### 13. Do not have the machine undo a stop the owner asked for

**Status:** Open — **the symptom appears in `cmd_restart`, and the cause is not there.**

`serve()` returns `0 if drained else 1` (`gateway.py:1029`) and the job carries
`"KeepAlive": {"SuccessfulExit": False}` (`supervisor.py:161`). The exit status is
carrying two incompatible meanings: *refused to run, do not restart* (0, R-GW-25) and
*went down with work still out there* (1). launchd restarts on any non-zero exit
regardless of who signalled, so `rundesk stop` on a gateway with one stubborn program
stops it, launchd starts it again, and `_stand_down()` polls `_gone()` for
`CYCLE_PATIENCE` (20s) and reports `FAILED — still running after stop request`.

The owner asked for it to stop, it is running, and the message names the wrong cause.
Finding 5 fixed a different wrong message in this same function; this one cannot be
fixed there, because `_stand_down()` is reporting accurately what it observes.

**Round six adds two consumer-facing consequences of the same process/job conflation.**

- `rundesk serve <name>` is both the public foreground command and launchd's entrypoint
  (`cli.py:260-272`, `supervisor.py:141`). A duplicate name or unfit install prints
  `NOT STARTED` and exits zero solely to control launchd's retry policy, so a person or
  script receives success when no gateway started. Keep the launchd clean-refusal mapping
  in a private entrypoint; public `serve` must return non-zero.
- An ordinary drained `rundesk stop <name>` prints only `<name>: STOPPED`
  (`cli.py:464-468`), while `supervisor.stop()` merely sends `SIGTERM` "without
  forgetting the job" (`supervisor.py:302-306`). The loaded `RunAtLoad` job remains
  (`:160-161`), so the gateway returns at the next login or reboot. Add an explicit
  `gateway disable/remove <name>` that unloads and removes only Rundesk's plist, or make
  `stop` say `STOPPED — launchd remains enabled` with that exact next action.

Regression criteria:

- A gateway that stopped because it was asked stays stopped, whether or not it drained.
- A gateway that died is still restarted.
- The orphan case remains discoverable — the log, the run record and the interruption
  history already carry it, which is where something other than a supervisor reads it.
- Direct `rundesk serve` refusal is non-zero, while the generated launchd entrypoint
  still maps a permanent refusal to the no-retry outcome.
- `stop` states whether the launchd job remains enabled; the durable disable/remove
  command unloads and removes one owned job without touching another or its retained
  logs and schedules.

Relevant implementation: `Gateway.serve()` and `Gateway._go()` in
`src/rundesk_cli/gateway.py`; `describe()` in `src/rundesk_cli/supervisor.py`;
`_stand_down()` in `src/rundesk_cli/cli.py`.

### 14. Take the update lock before stopping anything

**Status:** Open

`run()` (`updater.py:119-184`) does `busy()` → `pause()` → `apply()`, and `_only_one()`
is taken inside `apply()` (`:187-218`). Both halves of R-UPD-21 — stopping what is about
to be replaced, and starting it again — sit outside the lock.

Reproduced outcome, with the lock held by a stand-in concurrent update:

```text
output='0.1.0: OUT OF DATE — 9.9.9 available, run: rundesk update'
output='FAILED — could not update: another update is already running'
exit=1
order=['busy-check', 'STOPPED the gateways', "STARTED them again: ['gateway']"]
```

The losing update stopped the gateways, discovered it had lost, and started them again —
at the moment the winner is inside `_copy_over()` replacing `rundesk` and
`src/rundesk_cli` as separate renames. A gateway brought up in that window can import a
mixed tree, and `fitness()` can be asked about a `.venv` mid-rebuild.

**Second face — a partial pause is never resumed.** `_stand_all_down()` stops gateways
in sequence (`cli.py:159-187`) and can return names already stopped plus a refusal from
a later gateway. `run()` checks that refusal at `updater.py:165-168` and returns before
entering the `try/finally` whose `resume()` begins at `:169`. An update that changes
nothing can therefore leave the earlier gateways down indefinitely.

Reproduced with `pause()` returning one stopped gateway and a refusal for the next:

```text
output='update: NOT APPLIED — agent-two would not stop'
exit=1
stopped=['agent-one']
resumed=[]
```

The update lock and the resume guarantee are one lifecycle transaction: once any
gateway has been stopped, every exit path must attempt to restore it.

Regression criteria:

- The lock covers `busy` → `pause` → `apply` → `resume` as one decision.
- An update that loses the race stops nothing and starts nothing.
- If `pause()` stops any gateways before refusing, `resume()` is still called for all
  of them before `run()` returns.
- A two-gateway test lets the first stop and the second refuse, proves no files move,
  and proves the first is observed up again or is reported as failed to return.

Relevant implementation: `run()`, `_only_one()` and `download_and_apply()` in
`src/rundesk_cli/updater.py`.

### 15. Account for a gateway that has no launchd job before deleting anything

**Status:** Open — **this is a fourth form of "prove the machine let go before deleting",
not a new guard.**

Finding 2's first regression criterion is that uninstall must stop before deleting
anything whenever either launchd or the gateway has not demonstrably let go. It is not
met for a gateway with no job: `stop_gateways()` (`install.sh:88-121`) calls
`take_all_back()` (`supervisor.py:352-395`), which iterates `described()` — jobs *this
install wrote* — and nothing else. A gateway started by hand is not enumerated, so
nothing about it is ever asked.

That is not a hypothetical path. `cmd_start()` prints `run in this terminal instead:
rundesk serve <name>` when there is no supervisor (`cli.py:313`), and `_stand_all_down()`
has a whole branch for gateways running unsupervised (`cli.py:176-183`) — finding 4 is
what taught it to. The runtime knows these gateways exist everywhere except here.

Reproduced outcome, a lock-holding gateway with no plist:

```text
gateway_running=True
jobs_this_install_wrote=[]
take_all_back_taken=[]
take_all_back_stubborn=[]
uninstall_would_proceed=True
```

The result is the outcome `stop_gateways()`' own comment describes: an agent nobody can
reach, with the one thing that could have stopped it deleted, plus every provider
process group it owns.

Regression criteria:

- Uninstall refuses while any gateway is running, whether or not this install wrote a
  job for it.
- The test that proves it does **not** write a plist first — the existing one
  (`tests/test_install.py:89`) does, which is why this case was never exercised.

Relevant implementation: `take_all_back()` in `src/rundesk_cli/supervisor.py`;
`stop_gateways()` in `install.sh`; `every()` in `src/rundesk_cli/gateway.py`.

## Medium impact

### 16. Bound `Held` on every path that adds to it

**Status:** Open

`Held.offer()` evicts when the bound is exceeded; `Held.lose()` (`process.py:222-254`)
appends a `Gap`, adds its weight and never checks. Every oversized record calls `lose()`
(`process.py:376-388`), so a program emitting only oversized records grows the queue
without limit.

Reproduced outcome with `MAX_RECORD_BYTES` lowered so the trigger is cheap:

```text
bound=1000 bytes
accounted=1280000 bytes
queued_items=20000
over_bound_by=1280x
```

Round five reproduced the same path directly against the current `Held.lose()`
(`process.py:249-254`), without relying on record framing:

```text
configured_bound=256
loss_markers=10000
accounted_bytes=640000
```

With production constants this needs roughly 80 GB of provider output, so it is slow
rather than acute. It is recorded because it is the same one-sided-bound shape that
`9916245` has just finished fixing on the other side, and the correction is to run the
existing eviction loop from `lose()` as well. Adjacent compatible gaps should be
coalesced so the retained loss count stays exact without spending one queue item per
lost record.

Regression criteria:

- Records lost without ever having been held are still bounded in bytes and items.
- Hundreds of thousands of oversized records against a non-consuming sink keep the
  queue within its configured budget.
- The eventual coalesced gaps report the exact number and reason of records lost.

Relevant implementation: `Held.offer()` and `Held.lose()` in
`src/rundesk_cli/process.py`.

### 17. Stop the rotated log from having an unrotated shadow

**Status:** Open

`_recorder()` adds a `StreamHandler(sys.stderr)` to every gateway logger
(`gateway.py:148-150`), and `describe()` points `StandardErrorPath` at
`logs/<name>.err` (`supervisor.py:163-164`). Every line that goes into the 2 MB × 3
rotated log also goes into a file that nothing prunes, nothing reads (`rundesk logs`
reads only `<name>.log`) and no requirement mentions. R-GW-18 bounds the log; its shadow
is unbounded, for as long as the gateway is up.

**Round four adds why `/dev/null` is the wrong half of the fix.** `<name>.err` is not
purely a duplicate. It is the **only** store for everything that never reaches the logger:
an interpreter-level traceback, an unraisable-exception report from a task nobody awaited,
and `cmd_serve()`'s `NOT STARTED — …` line (`cli.py:271`). `rundesk logs` cannot show any
of it, while `cmd_start()` and `_stand_down()` point the owner at exactly that command when
a gateway does not come up (`cli.py:321`, `:452`) — so the operator asking "why did it die"
is sent to the one file that cannot answer, and sending `StandardErrorPath` to `/dev/null`
would destroy the answer rather than bound it. Drop the stderr **handler** when the gateway
is not attached to a terminal, keep the file, and have `rundesk logs` show its tail when it
is non-empty: `.err` then holds only what the logger cannot, which is small, bounded in
practice, and the part worth keeping.

A second, smaller writer problem in the same store: `note()` (`gateway.py:117-129`) appends
to `<name>.log` **by path, from a different process**, while the gateway's
`RotatingFileHandler` (`:141-143`) rotates it by rename. A line written across a rotation
lands in `.log.1`, out of order, and external bytes are invisible to the handler's
`maxBytes` accounting, so rotation is late by however much the CLI has appended. Both are
minor next to the crash-output hole; record them together because both are "two writers,
one log file".

**Round six adds the control-surface failures around these same stores.**

- `cmd_logs()` reads only the current `<name>.log` (`cli.py:638-654`), not the rotated
  `.log.1`–`.log.3` history and not launchd's `.out` or `.err`. Yet failed start and
  restart point to `rundesk logs <name>` (`cli.py:321`, `:460`). The advised command can
  therefore say `NO LOG` while the startup traceback exists in `<name>.err`, or omit the
  older lines that explain the current tail. Default output should combine labeled
  gateway and launchd sources across rotation; `--source gateway|launchd|all` may narrow
  it.
- `note()` neither creates the log directory nor returns its `OSError`. On the first
  schedule change in a clean home, `rundesk schedules add` can print `ADDED` and persist
  the schedule while producing no audit line anywhere. A successful mutation whose
  history write failed must say `WARNING — change applied, but not logged: <path>:
  <reason>` and must not return full success.

Regression criteria:

- What a gateway writes is bounded wherever it lands.
- No line appears in both `<name>.log` and `<name>.err`.
- A startup failure that never reaches the logger is still shown by `rundesk logs`.
- `note()` and the gateway's own handler cannot lose a line to a rotation between them.
- A failure held only in `<name>.err`, and needed context held only in `.log.1`, are both
  reachable through the command with source labels.
- The first schedule change in a clean home creates its log; forced append failure keeps
  the truthful schedule mutation, names the log path and returns a partial/failure
  outcome rather than silent success.

Relevant implementation: `_recorder()` and `note()` in `src/rundesk_cli/gateway.py`;
`describe()` in `src/rundesk_cli/supervisor.py`; `cmd_logs()`, `cmd_serve()`,
`cmd_start()` and `_stand_down()` in `src/rundesk_cli/cli.py`.

### 19. Stop a gateway name from claiming another gateway's history file

**Status:** Open

`checked()` (`gateway.py:53-60`) allows `.`, and `ran_path`/`seen_path`/
`interrupted_path` build `<name>.ran.json` and friends. Verified:

```text
ran_path('foo')            == 'foo.ran.json'
schedules_path('foo.ran')  == 'foo.ran.json'
same_file=True
checked('foo.ran')='foo.ran'   # accepted
```

A gateway named `foo.ran` and a gateway named `foo` share one file, one holding
schedules and the other holding history.

**Round four adds what actually happens when they do, in both directions — it is silent
destruction reported as success.** Neither writer notices the other's shape:

- `rundesk schedules --gateway foo.ran add …` opens `foo.ran.json`, which holds `foo`'s
  outcome history — a dict. `written_schedules()` returns `[]` for anything that is not a
  list (`gateway.py:97-102`), so `changing_schedules()` appends to nothing and writes a
  one-element schedule list over the file. Every outcome `foo` had recorded is gone, and
  the command prints `ADDED`. This is the "empty over unreadable" shape (R-SCH-17) reached by
  a second route, so the two fixes reinforce each other but neither covers the other.
- In the other direction `foo`'s `_remember()` (`:1210`) writes its outcome dict over
  `foo.ran`'s schedules file, and `foo.ran` silently has no schedules from then on —
  `written_schedules()` maps the dict back to `[]`, so `rundesk schedules` reports
  `NO SCHEDULES` rather than a fault.

`checked()` is the only gate, `R-GW-20` guards names that escape the *directory* and
nothing guards names that collide *inside* it, and gateway names will be agent names chosen
by a person.

Regression criteria:

- A gateway name cannot resolve to a path another gateway already owns. Either refuse the
  reserved suffixes or give each gateway its own directory.
- The set of reserved suffixes is derived from the `*_path` helpers rather than restated by
  hand, so a new sidecar file is covered the day it lands.
- No schedules command overwrites a file whose contents are not a schedule list (R-SCH-17).

Relevant implementation: `checked()`, `ran_path()`, `seen_path()`,
`interrupted_path()` and `schedules_path()` in `src/rundesk_cli/gateway.py`.

### 21. Give updates a durable maintenance barrier rather than a repeated check

**Status:** Open

`_stand_all_down()` (`cli.py:147-188`) re-asks `what_is_running()` immediately before
each `machine.stop()`, which narrows the window but does not close it: nothing stops a
gateway's `_tick()` from firing a schedule between the check and the `SIGTERM`. R-UPD-23
is therefore best-effort, and neither the contract nor the command says so.

Regression criteria: work that begins during an update's busy check is not killed by it.
The smallest honest fix is a maintenance flag the gateway consults in `_fire()` and
`start()`, set for the duration of `pause` → `resume`, so a gateway being stood down
refuses new work durably instead of racing.

Relevant implementation: `_in_flight()` and `_stand_all_down()` in
`src/rundesk_cli/cli.py`; `Gateway._fire()` and `Gateway.start()` in
`src/rundesk_cli/gateway.py`.

### 22. Tell a program the gateway starts where rundesk's state lives

**Status:** Open

`environment()` (`process.py:973-991`) passes `RUNDESK_HOME` but not `RUNDESK_RUN_DIR`,
`RUNDESK_LOG_DIR` or `RUNDESK_SCHEDULES_DIR`. `supervisor.describe()` carries all four
into the gateway, with a comment recording that leaving one out "silently split the
machine in two" — and the same split is reintroduced one level down for any scheduled
program that is itself `rundesk`.

Regression criteria: a program the gateway starts reads the same places the gateway
does.

Relevant implementation: `environment()` in `src/rundesk_cli/process.py`.

# Round three — 2026-07-25

Line numbers are against the working-tree state reviewed on 2026-07-25:
`7841a0f` plus the then-uncommitted changes in `cli.py`, `gateway.py`, `process.py`
and `supervisor.py`. Five gateway-facing suites passed alongside these findings
(`test_gateway` 103, `test_process` 84, `test_schedule` 28, `test_supervisor` 38 and
`test_cli` 73).

## Critical

### 23. Do not run work whose ownership record could not be committed

**Status:** Open — **read finding 9 first;** its remaining half is this same transaction.

`Gateway.start()` spawns the program, calls `_say()`, logs that it started and waits
for it (`gateway.py:940-952`). `_say()` catches every `OSError` from `_record()` and
only logs a warning (`:1216-1235`). The program therefore continues even when the
durable runtime record does not name it.

Reproduced by failing only the record write that first contained the new work:

```text
log="could not update the record: simulated full disk"
log="started 'work' (group 9775)"
child_alive=True
memory_running=['work']
durable_running=[]
```

Round five independently reproduced the same current-worktree failure with the
post-spawn runtime write forced to raise:

```text
provider_alive=True
durable_working={}
log="could not update the record: simulated full disk"
```

The runtime record is not merely status. It is the only recovery identity a successor
has after the gateway dies, and `_in_flight()` uses it to decide whether an update may
stop the gateway. Continuing after this failure permits an unreachable provider tree,
a duplicate successor, or an update that kills work while reporting the gateway idle.

The smallest fix is a transactional startup boundary, not a new state layer:

1. spawn the child;
2. establish the immutable process fingerprint from finding 9;
3. commit the runtime record naming it;
4. only then report the work as started.

If either identity or record persistence fails, immediately end the whole new process
group, remove it from `running`, and fail the start. Later heartbeat refreshes can
remain best-effort because ownership has already been durably established.

Regression criteria:

- A process is not accepted as started until its PID and immutable start fingerprint
  are durably present in the runtime record.
- Failure to establish that identity or write the first in-flight record ends the
  entire process group and raises to the caller.
- Memory, `what_is_running()`, status and update safety cannot disagree about whether
  newly accepted work exists.
- A failure-injection test makes only the first in-flight record write fail and proves
  the child and everything it started are gone.

Relevant implementation: `Gateway.start()`, `Gateway._record()` and `Gateway._say()`
in `src/rundesk_cli/gateway.py`; `_in_flight()` in `src/rundesk_cli/cli.py`.

## High impact

### 24. Examine schedules immediately after a gateway starts

**Status:** Open

`Gateway._tick()` delegates to `_over_and_over()` (`gateway.py:1087-1101`), whose
first action is `await asyncio.sleep(every)` (`:1183-1186`). With
`TICK_SECONDS = 20`, a gateway does not examine schedules until twenty seconds after
claiming its name.

Observed directly:

```text
immediately_after_tick_started=0 checks
after_first_interval=1 check
```

A schedule is due only in its stated minute. If launchd starts or recovers a gateway
during that minute's final twenty seconds, the first check lands in the next minute
and the occurrence is silently lost. `_say_what_was_missed()` cannot account for it:
that runs during `claim()`, before this new post-start gap exists.

The smallest fix is one synchronous `_fire(schedule, datetime.now())` after claim and
before the repeating sleep. The existing durable per-minute guard already prevents
the immediate check and the first interval check from firing the same minute twice.

Regression criteria:

- A gateway examines schedules once immediately after it claims its name.
- Starting at `09:30:55` with work due at `09:30` starts it before a fake clock
  advances to `09:31`.
- The immediate check plus the ordinary tick still starts a due minute exactly once.
- Shutdown requested during claim still starts nothing.

Relevant implementation: `Gateway.serve()`, `Gateway._tick()` and
`Gateway._over_and_over()` in `src/rundesk_cli/gateway.py`.

## Medium impact

### 25. Do not skip weekday matches when finding the next cron occurrence

**Status:** Open

The direct matcher correctly implements cron's day-of-month/day-of-week OR rule:
when both are narrowed, either match is sufficient (`schedule.py:227-247`).
`Schedule.next_after()` uses `_skip()`, however, and `_skip()` jumps to the next day
whenever the day of month does not match (`:261-278`) without considering that the
weekday may already match.

Reproduced with `0 9 15 * 1`, which means 09:00 on every Monday or every fifteenth:

```text
due_at_2026-07-13_09:00=True
next_after_2026-07-12_08:00=2026-07-15 09:00
passed_over_through_2026-07-14=0
```

Actual gateway firing uses the direct matcher and runs on Monday. The command's
`NEXT` value and the gateway's missed-run account use `next_after()` and claim that
Monday never existed. The runtime and its source of truth therefore contradict each
other.

The smallest fix is to disable the day-of-month jump when both day and weekday are
narrowed. Other skips that cannot bypass a weekday match remain valid.

Regression criteria:

- From Sunday July 12, 2026, `0 9 15 * 1` reports Monday July 13 at 09:00 as next.
- The same Monday is counted by `passed_over()`.
- Day-only, weekday-only and unrestricted schedules keep their existing skip behavior
  and performance.
- `due_at()`, `next_after()` and `passed_over()` agree on every combined
  day/weekday fixture.

Relevant implementation: `Schedule.next_after()`, `_matches()` and `_skip()` in
`src/rundesk_cli/schedule.py`; schedule listing and missed-run reporting in
`src/rundesk_cli/gateway.py` and `src/rundesk_cli/cli.py`.

# Round four — 2026-07-25

Line numbers are against `43315ae`. Established by reading the source and by path
arithmetic, **not** by reproduction scripts — see the note in the header. Each finding
names the store, its writers, and the concrete disagreement or loss.

## High impact

### 26. Reconcile a schedule outcome left saying `started` by a gateway that died

**Status:** Open — **read finding 12 first;** its `_released` guard is the other half of
keeping this file truthful.

`_fire()` writes the outcome `started` durably *before* the run begins
(`gateway.py:1125`), which is correct and is what R-SCH-9 rests on. Nothing ever rewrites
it if the gateway dies mid-run. `_pick_up_where_it_left_off()` (`:789-803`) reads the row
back verbatim, and `claim()` (`:737-787`) performs no reconciliation between it and the
sweep that has just established the work is gone.

The result is two durable stores describing one event and disagreeing:

| store | says |
|---|---|
| `<name>.ran.json` | `{"at": …, "outcome": "started"}` — indistinguishable from running now |
| `<name>.interrupted.json` | the same work, ended, with `ended` true or false |

`rundesk schedules` reads only the first (`cli.py:602-627`), so its `OUTCOME` column
presents dead work as in-flight until that schedule next falls due — which for a daily
schedule is a day. This is the first question asked after a crash, and the command answers
it wrongly while the correct answer is already on disk one file away.

Round five reproduced the adjacent shutdown-before-spawn form of the same stale
`"started"` fact. `_fire()` writes `"started"` and creates the scheduled wrapper
(`gateway.py:1112-1130`). If shutdown sets `_stopping` before the wrapper enters
`Gateway.start()`, `_run_scheduled()` catches `Stopping` and returns without replacing
the outcome (`:1144-1153`). No process exists for `_go()` to end or for a later sweep
to reconcile:

```text
schedule='nightly'
process_started=False
durable_outcome={'at': '2026-07-25 09:30', 'outcome': 'started'}
```

The sweep already knows the work names it accounted for, so no new state is needed: after
`_sweep_predecessor()` and `_sweep_strays()` return, rewrite any `_outcomes` row still
reading `started` to `interrupted`. The shutdown-before-spawn branch needs the matching
local correction: record `"interrupted"` or `"not started"` for the original due
minute before the `Stopping` handler returns.

Regression criteria:

- A `.ran.json` row left saying `started`, whose work the sweep has just accounted for, no
  longer says `started` once `claim()` returns.
- `rundesk schedules` does not present that row as in-flight.
- A row saying `started` for work the sweep found **still running** (identity unproven,
  finding 6) is left alone — it is genuinely in flight.
- A wrapper refused by `Stopping` never leaves `"started"` behind when no process
  spawned.
- Reconciling the row does not move its `at` minute, or R-SCH-9's guard is defeated.

Relevant implementation: `Gateway.claim()`, `_pick_up_where_it_left_off()`, `_fire()` and
`_remember()` in `src/rundesk_cli/gateway.py`; `_list_schedules()` in
`src/rundesk_cli/cli.py`.

### 27. Give the interruption history a reader, and a way to be resolved

**Status:** Open — the entries are now kept under one hold (R-GW-27); this makes them
answer something.

`what_was_interrupted()` (`gateway.py:356-365`) has no caller anywhere in the product —
grep across `src/`, `install.sh` and `.knowledge/prd/` finds only `_note_interrupted()`
and the tests. R-GW-23 is satisfied by writing the file; nothing reads it back. Two
consequences:

- **No reader.** The store that exists to say what never finished cannot be reached from
  the command line. `status` shows only what is running *now* (`cli.py:464-499`), and
  `logs` shows prose. "What did not finish" is answered by hand-reading JSON out of
  `~/.rundesk/schedules/`, which is not an answer an operator has during an incident — and
  it is the fact a channel adapter needs on reconnect to tell a conversation its session
  died.
- **No resolution.** Entries are keyed by work name (`:383`) and are never cleared, so work
  interrupted once in March is still listed in July, alongside work interrupted a minute
  ago, with nothing distinguishing outstanding from long since fine. Combined with the
  keying, the same work interrupted ten times shows only the tenth — which is precisely the
  fact R-GW-24 (work that keeps taking the gateway down) will need, being overwritten
  before it can be counted. See finding 29.

**Round six adds discovery and the concrete command shape.** `cmd_status()` discovers
names only from run records and Rundesk-owned launchd descriptions (`cli.py:472-482`);
`gateway.every()` scans only the run directory (`gateway.py:695-709`). A gateway name
that survives only in schedules, logs or `<name>.interrupted.json` is therefore absent
from `status`, and the owner must already know its name before asking any other command.
Add `rundesk interruptions [gateway]` with `WORK`, `AT`, `ENDED`, and `REASON`; status
should discover every Rundesk-owned state source and show a nonzero interruption count.

Regression criteria:

- Interrupted work is visible through the command line without reading a file by hand.
- Work that later completes is no longer presented as outstanding.
- The count of times one piece of work was interrupted survives (finding 29).
- Ended and unresolved entries are rendered distinctly with their time and reason.
- A schedules-, log- or interruption-only gateway is discoverable without knowing its
  name in advance.

Relevant implementation: `what_was_interrupted()` and `_note_interrupted()` in
`src/rundesk_cli/gateway.py`; `cmd_status()` in `src/rundesk_cli/cli.py`.

### 28. Read a supervised gateway's directories from its own job, not from the ambient environment

**Status:** Open — **this is finding 22 one level up.** Finding 22 is the gateway failing
to pass the directories *down* to a program it starts; this is a command failing to read
them *out of* the job that is already carrying them. Same split, opposite direction, and
the fixes are independent.

`describe()` bakes all four directories into the job's `EnvironmentVariables`
(`supervisor.py:148-159`), with a comment recording that omitting one "silently split the
machine in two". That fixes the gateway's half. The other half is unfixed: the values are a
snapshot taken when `rundesk start` ran, and every later command resolves the same
directories from **its own** environment (`gateway.py:109`, `:160`, `:193`). Nothing
compares the two, and nothing detects a difference.

So `RUNDESK_RUN_DIR=/tmp/x rundesk start gw` produces a healthy supervised gateway whose
lock and record live in `/tmp/x`, after which a plain command reads `~/.rundesk/run`:

- `cmd_status()` finds no lock but still finds the plist through `described()`
  (`cli.py:471-474`), so it prints the gateway as `STOPPED  -  -  SUPERVISED yes` while it
  is up and working.
- `_named()` (`cli.py:338-346`) and `_gone()` decide `stop` and `restart` against the wrong
  directory.
- `_in_flight()` (`cli.py:216-227`) reads no record, so `update` concludes the machine is
  idle and replaces files under a gateway with work in flight — R-UPD-23's guard checking a
  directory that does not contain the answer.

For a supervised gateway the job **is** the authority on where its state lives, because it
is what the running process was given. The smallest fix is to resolve the three directories
from the job's `EnvironmentVariables` whenever a job for that name exists, falling back to
the environment when there is none. A warning when they differ is the cheaper stopgap and
leaves the wrong answer in place.

**Round six adds the operator-facing reader.** Even after command resolution uses the
right directories, nothing in the CLI shows which install, run state, schedules, logs
and launchd plist are authoritative. Add those resolved paths to `rundesk inspect
<gateway>` or `rundesk paths [gateway]`; environment overrides must be shown exactly,
not normalized back to defaults. Finding 27 supplies the history this view must link,
and finding 35 supplies the rest of the owned-state inventory.

Regression criteria:

- With a job whose `RUNDESK_RUN_DIR` differs from the ambient one and a live lock and record
  in the job's directory, `status` does not report the gateway as stopped and `_in_flight()`
  sees its work.
- `stop` and `restart` act on the gateway the job describes.
- A name with no job keeps today's behaviour exactly.
- The CLI prints the exact resolved install, run, schedule, log and launchd job paths for
  both default and overridden locations.

Relevant implementation: `describe()` in `src/rundesk_cli/supervisor.py`; `home()`,
`logs_home()` and `schedules_home()` in `src/rundesk_cli/gateway.py`; `cmd_status()`,
`_named()` and `_in_flight()` in `src/rundesk_cli/cli.py`.

## Medium impact

### 29. Key durable work records by run, not by work name

**Status:** Open — **the smallest change that unblocks channel work.** Findings 26 and
27 each work around this key; none of them removes it.

Every durable per-work row is keyed by the work's *name* and is therefore last-write-wins
on a fact that has one value per **occurrence**:

- `_note_interrupted()` — `said[work] = {…}` (`gateway.py:383`)
- `_remember()` — `self._outcomes[name] = {…}` (`gateway.py:1208`)

Two consequences today, before any channel exists. The first is history that cannot
accumulate: work interrupted twice keeps only the second, so finding 27 has nothing to count
and R-GW-24 has no input. The second is already visible in the code — `_remember()`'s
never-move-backwards rule (`:1205-1207`) needs to hold two timestamps in a row that has one,
and degrades to appending the second into the *outcome string*:
`"finished (for 2026-11-01 01:05)"`. During a daylight-saving fallback that is the normal
path for an hour, so the `OUTCOME` column carries a parenthesised timestamp and the
`LAST RUN` column shows a minute that has not arrived yet. The rule is right; the row cannot
express it.

Nothing here argues for a database or a new persistence layer — the JSON-per-fact design and
the four-directory split are sound, and `process.py:96-99` is correct that a durable
transcript is not that module's concern. What is missing is a **key**. `Gateway.start()`
already mints an identifier for unnamed work (`gateway.py:919`); minting one for *all* work
and carrying it into the record's `working` entry, the interruption row and every log line
about that work is a small change that:

- lets the existing files hold history instead of only a latest value;
- gives interleaved log lines from concurrent programs something to be correlated by, which
  is what turns "the operator can read the log" into "the operator can trace one turn";
- gives the channel layer somewhere to hang a turn's outcome, its pending question and the
  approval that answered it — all per-occurrence facts that today have no key and therefore
  no home.

Regression criteria:

- The same work name interrupted twice leaves two distinguishable durable records.
- A schedule outcome never needs a timestamp inside its outcome string; a repeated hour
  records two rows rather than mutating one.
- Every log line concerning a piece of work carries its run identifier, walked off the log
  rather than restated.
- The identifier appears in the runtime record's `working` entry, so a successor and a
  channel adapter name the same run the same way.

Relevant implementation: `Gateway.start()`, `_record()`, `_remember()` and
`_note_interrupted()` in `src/rundesk_cli/gateway.py`; `RETAINED_LINES` and the module
docstring in `src/rundesk_cli/process.py`.

# Round five — 2026-07-25

Line numbers are against the current uncommitted runtime worktree. The focused suites
pass alongside this finding (`test_process` 84, `test_gateway` 103, `test_schedule`
28 and `test_supervisor` 38).

## High impact

### 30. Bound how much distinct work one gateway may admit

**Status:** Open

`Gateway.running` is an unconstrained dictionary (`gateway.py:711-714`).
`Gateway.start()` refuses a duplicate name but admits every distinct name and registers
it before spawning (`:917-940`); scheduled work reaches that same path through a task
created for every due schedule (`:1112-1130`). There is no gateway-wide admission
limit, pending-start limit or refusal based on resource capacity.

This prevents concurrent scheduled and user-triggered work from being safely enabled
under sustained or duplicated demand. Each admitted name creates a subprocess, process
group, pipes, asyncio tasks, diagnostic tails and potentially an `HELD_BYTES` receiver
allowance. Per-program bounds therefore do not bound the gateway: enough distinct names
multiply them until file descriptors, memory or the process table is exhausted.

Reproduced with 24 distinct long-running names:

```text
distinct_starts_requested=24
admitted=24
refused=0
```

The smallest low-level improvement is one explicit per-gateway active-work limit,
checked before `Program` registration or subprocess creation and shared by scheduled
and user-triggered starts. Work beyond the limit should be refused immediately with a
specific capacity result; no general scheduler or pending-work abstraction is needed.

Regression criteria:

- Mixed scheduled and user-triggered work can run concurrently up to the same stated
  per-gateway limit.
- The next distinct start is refused before constructing or spawning a `Program`.
- A refused schedule records a truthful capacity outcome rather than `"started"`.
- Capacity is returned exactly once when work finishes, fails, is cancelled or is
  ended by gateway shutdown.
- Repeated over-capacity requests do not grow a pending task queue, open descriptors or
  increase the gateway's retained-output budget.

Relevant implementation: `Gateway.running`, `Gateway.start()`, `Gateway._fire()` and
`Gateway._run_scheduled()` in `src/rundesk_cli/gateway.py`; per-program receiver bounds
in `src/rundesk_cli/process.py`.

# Round six — 2026-07-25

Line numbers are against `43315ae`. Material that repeated an existing failure is merged
above; findings 31–38 are only the distinct consumer command-surface gaps.

## High impact

### 31. Keep Rundesk options out of the scheduled program

**Status:** Open

1. **Command and location:** `rundesk schedules add`; `src/rundesk_cli/cli.py:109-117`,
   `:557-587`.
2. **Current behaviour:** `--run` uses `argparse.REMAINDER`, while `--gateway` belongs to
   the parent parser. In the natural command
   `rundesk schedules add daily --when daily --run /bin/echo hi --gateway alpha`,
   `--gateway alpha` becomes program arguments and the schedule is added to the default
   gateway. The success line names only the schedule: `daily: ADDED — next ...`.
3. **Why it blocks:** A successful command can target the wrong gateway and later pass a
   Rundesk option to the agent program. Nothing in the result exposes either mistake.
4. **Replacement:** Use an explicit program boundary:
   `rundesk schedules add NAME --gateway GATEWAY --when WHEN -- PROGRAM [ARG ...]`.
   Print `GATEWAY/NAME: ADDED — next ...`; reject ambiguous legacy ordering without writing.
5. **Test:** Assert the canonical form stores the exact gateway and argv; the ambiguous
   form exits nonzero and leaves the schedule file byte-for-byte unchanged; the success
   line names both gateway and schedule.

### 32. Require an explicit scope for `stop` and `restart`

**Status:** Open

1. **Command and location:** `rundesk stop`, `rundesk restart`;
   `src/rundesk_cli/cli.py:101-105`, `:343-351`.
2. **Current behaviour:** Both accept an optional singular `name`, but omission silently
   expands to every gateway found in runtime records or launchd jobs.
3. **Why it blocks:** `rundesk restart` reads like the default gateway, not every gateway.
   The command help does not disclose the fan-out before the action occurs.
4. **Replacement:** Require either `NAME` or `--all`. A bare command is a usage error:
   `restart: NAME or --all is required`; it changes nothing.
5. **Test:** For both verbs, prove bare invocation exits with the usage code and performs
   no launchd calls; `NAME` touches one gateway; `--all` touches the complete discovered
   set and prints one outcome per gateway.

### 33. Make `rundesk uninstall` the removal command

**Status:** Open — read with finding 15 for the ownership rule.

1. **Command and location:** `rundesk uninstall`; `src/rundesk_cli/cli.py:89`,
   `:230-242`.
2. **Current output:** It exits 0 after printing `uninstall: USE THE INSTALLER` and a
   checkout path or remote `curl | bash` instruction. It removes nothing.
3. **Why it blocks:** The advertised control verb is an instruction page. It makes users
   find or download a second control surface, and exit 0 falsely means the uninstall ran.
4. **Replacement:** Have `rundesk uninstall [--purge]` invoke the guarded owned-removal
   path and propagate its result. If instructions remain useful, expose them as
   `rundesk uninstall --help`, not as a successful uninstall.
5. **Test:** In an isolated install, assert the command removes only Rundesk-owned files,
   preserves history unless `--purge` is explicit, refuses foreign/ambiguous ownership,
   and returns nonzero with the installer failure message when removal is incomplete.

### 34. Give lifecycle and update outcomes a durable control log

**Status:** Open — gateway program logs remain finding 17.

1. **Command and location:** `start`, `stop`, `restart`, `update`;
   `src/rundesk_cli/cli.py:275-321`, `:375-469`;
   `src/rundesk_cli/updater.py:154-184`, `:211-262`.
2. **Current behaviour:** Launchd refusals, failed restarts and update outcomes are
   terminal-only. Rundesk has per-gateway program logs, but no durable log for control
   actions; some launchd failures can contain an empty explanation.
3. **Why it blocks:** After a terminal closes, an operator cannot establish who requested
   a lifecycle change, what launchd answered, whether an update completed, or which
   recovery command was offered. `rundesk logs` cannot answer those questions.
4. **Replacement:** Add `rundesk logs --system` and record action, target, launchd result
   and final outcome. CLI failures should name the failed layer and a concrete next action,
   for example `alpha: START FAILED — launchd gave no reason; run: rundesk logs --system`.
5. **Test:** Inject empty launchd refusals, restart timeout, and update refusal/failure/
   success. Assert truthful stderr and exit codes, and assert the same terminal outcome and
   next command are present in the durable system log.

### 35. Expose scheduled commands and individual work through Rundesk

**Status:** Open — read with findings 27–29 for inventory, interruption history and run IDs.

1. **Command and location:** `status`, `schedules`, and the missing work controls;
   `src/rundesk_cli/cli.py:472-507`, `:610-635`;
   `src/rundesk_cli/gateway.py:678-709`, `:880-910`.
2. **Current behaviour:** Schedule listing omits the stored `run` command. Status reduces
   live work to names, with no per-run details or control. There is no Rundesk command to
   inspect one run or stop one work item without stopping its gateway.
3. **Why it blocks:** Users cannot verify what an unattended schedule will execute, trace
   one same-name occurrence, or stop only the faulty work Rundesk owns.
4. **Replacement:** Add `rundesk schedules show GATEWAY/NAME` with a shell-quoted command,
   and `rundesk work list|show|stop [RUN_ID]`. Use finding 29's run ID and keep gateway
   lifecycle commands separate.
5. **Test:** Round-trip an argv containing spaces and option-looking arguments; assert
   `show` reproduces it unambiguously. Start two work items, stop one by run ID, and prove
   the other and the gateway remain running. Each owned state source alone must make its
   gateway or run discoverable as required by finding 27.

### 36. Do not install `main` when release lookup failed

**Status:** Open

1. **Command and location:** remote `install.sh`; `install.sh:198-214`;
   `tests/test_install.py:565-604`.
2. **Current behaviour:** A missing tag caused by no release, HTTP 403/404, malformed JSON,
   a dropped connection or another curl failure takes the same branch:
   `no release published yet; taking the main branch instead.` The current test explicitly
   codifies that fallback.
3. **Why it blocks:** The installer reports an unverified network failure as a known
   repository state, then installs unreleased code while the user believes release
   discovery succeeded.
4. **Replacement:** Fail closed:
   `install: FAILED — could not determine the newest release; check the connection and retry`.
   Do not request `refs/heads/main.tar.gz`.
5. **Test:** Separately inject timeout, 403, 404, malformed JSON and an empty tag. Each must
   exit nonzero, preserve the existing install, and never request the main archive. A valid
   release response must still install only its exact tag.

## Medium impact

### 37. Name Rundesk, gateways, work and launchd as separate subjects

**Status:** Open — finding 4 covers the underlying PID/ownership truth test.

1. **Command and location:** top-level help and `status`;
   `src/rundesk_cli/cli.py:63-127`, `:472-507`.
2. **Current output:** Subjectless verbs (`start`, `stop`, `logs`) mix Rundesk and gateway
   operations. Status labels launchd state as `SUPERVISED yes/no/?`, although a loaded job,
   a running gateway process and Rundesk owning that PID are different facts. Help leaves
   gateway positional arguments undescribed.
3. **Why it blocks:** A user cannot tell whether `stop` disables launchd, stops a gateway,
   or stops its work. `SUPERVISED yes` sounds healthier and more durable than “launchd job
   currently loaded”.
4. **Replacement:** Keep the concise verbs but name their subjects in help and output.
   Replace `SUPERVISED` with `LAUNCHD JOB: LOADED|NOT LOADED|UNKNOWN`; show gateway process
   state/PID and work separately. Document `NAME` and every omission rule.
5. **Test:** Semantic help/status tests must cover loaded job with no process, process with
   no loaded job, unknown launchd response, and loaded foreign/same-name PID. No state may
   collapse to `?` or imply process ownership it has not proved.

### 38. Reserve a distinct exit code for unavailable commands

**Status:** Open

1. **Command and location:** planned commands such as `doctor`;
   `src/rundesk_cli/cli.py:46-60`, `:72-81`, `:245-247`.
2. **Current behaviour:** A recognized but unimplemented command prints
   `doctor: NOT BUILT ...` and exits 2. Argparse also exits 2 for invalid syntax.
3. **Why it blocks:** Scripts cannot distinguish “this Rundesk version lacks the command”
   from “the caller supplied an invalid command”. Those require different recovery actions.
4. **Replacement:** Keep 2 for usage and return a documented unavailable code, such as
   `EX_UNAVAILABLE` (69), for planned commands. The message should end with the available
   action: `run: rundesk --help`.
5. **Test:** Assert invalid syntax and a planned command return different documented codes;
   the planned command accepts arbitrary future arguments, changes no state, and prints the
   concise availability message and next command.


## Tests that prove only the easy half

Each of these exists, passes, and is cited as evidence for a requirement it does not
fully cover. They are listed together because the pattern matters more than any one of
them: `check-evidence` can prove a cited test exists, and cannot prove it reaches the
state it is named for.

| Test | Cited for | What it does not reach |
|---|---|---|
| `test_what_is_written_arrives_in_the_order_it_was_written` (`tests/test_process.py:955-965`) | R-PROC-14 | 20 concurrent sends of four bytes each; the transport never pauses, so `drain()` returns before touching `_drain_waiter` — finding 10's state is never entered |
| `test_a_receiver_that_is_slow_does_not_slow_the_program` (`tests/test_process.py:1144-1167`) | R-PROC-17 | Sets up finding 8 exactly, asserts only that the *program* was not slowed and `result.ok`; never looks at what the receiver got (9 of 50) |
| `test_removing_rundesk_refuses_while_a_gateway_is_still_running` (`tests/test_install.py:89`) | R-RM-9 | Writes a plist first, so the no-job case in finding 15 is never exercised |

## Reviewed, no change needed

Recorded so a later round does not repeat the work without new reason.

**Provider protocol boundary.** No provider, channel, approval or conversation semantics
have leaked into the runtime. `schedule.run` is carried and never read; `process` has no
knowledge of a gateway; `Held` and `Gap` are transport concepts. No new boundary is
needed — the existing `sink` / `send` / `Gap` surface is sufficient for a provider
adapter, once findings 8 and 10 are fixed.

**Scheduling arithmetic, except finding 25.** `_not_yet()` uses strictly-greater so a
repeated hour cannot double-fire; `_remember()` refuses to move an outcome backwards;
and a firing is written down before the run starts. The clock being an argument keeps
all of this directly testable. Round three found one contradiction the earlier pass
missed: `_matches()` implements the day/weekday OR rule correctly while `_skip()` can
bypass the weekday half, so `next_after()` and `passed_over()` disagree with actual
firing. That exception is finding 25; the other reviewed arithmetic remains sound.

**Cancellation of `Program.wait()`.** Tested directly with a receiver that never returns:
cancellation propagates, the child is ended, and the undelivered count is reported.

**Retained diagnostic tails.** One `_keep()` owns both count and byte eviction for `_Lines`
and `_Records` (`process.py:286-328`, `:358-400`), and the deque does not evict on its own.
Keep it that way: long-running provider streams can carry large tool results, and the
retained tail is both a memory guarantee and the only diagnostic returned when a program
fails. Splitting the two again is what let an eviction drop an item without subtracting its
bytes. `test_a_long_run_does_not_shrink_the_tail_it_is_keeping` holds the line.

**Persisted reads and writes.** One reader (`gateway._read()`) says which of missing,
unreadable or written a file turned out to be, and one writer (`gateway.changing()`) holds
the read, the decision and the write under one `flock`. Anything new that persists state
goes through them rather than opening a file itself — four hand-rolled readers disagreeing
about what an unreadable file meant is what R-SCH-17 and R-GW-26 exist to prevent.

**Security and trust boundaries.** Nothing actionable today. `located()` refuses a
program named rather than resolved, in one place, applied both at schedule-add time and
at start; `environment()` builds rather than inherits; `_safe_extract()` handles the
link-target escape that most implementations miss; the release lookup deliberately
carries no credentials. The authorization boundary for channel replies and approvals
does not exist yet because the channel does not — it should be reviewed when it lands,
not before.

## Simplification opportunities

- **Split `Gateway.start()`** (`gateway.py:1155-1250`) — **deferred to finding 12, not an
  invitation on its own.** It combines the stopping check, name allocation, duplicate
  refusal, spawn, fingerprint capture, the born-into-shutdown recovery, the wait and five
  logging decisions. Separating "register and spawn" from "wait and report" is what makes
  finding 12's task-holding fix natural, and that is the only reason to do it: on its own
  this is a structural change to working, tested code with no defect behind it, which the
  change threshold in `AGENTS.md` does not admit. Do it when finding 12 is done, or not at
  all.
