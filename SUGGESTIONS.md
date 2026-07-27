# Suggestions

**Open findings only.** Each was reproduced against the implementation that existed when it
was written, and each is still true. What has been fixed is deleted rather than kept as
history — the ledger is a work list, not an account of what was done, and a resolved entry
in it is one more thing to read before finding the thing that matters. Numbers are never
reused and gaps are expected: they are cited in commits, in `ROADMAP.md` and in each other.

Three findings are **partly** closed and say in their own status which half is still open —
4, 6 and 9. Read the status before the body. **28 is narrowed rather than partly closed** and
says in its own status what is left of it.

**What the clock closed.** Letting a schedule start a *turn* ran the whole chain in one line —
the clock fires, a gateway admits a turn, a brain answers, the account records it, the outcome
reaches a channel — so 22, 24 and 25 are fixed and gone from here: a program the gateway starts
is told where agents are kept, schedules are examined as soon as a gateway has its name, and a
day a weekday could still match is no longer skipped over. 26 was already fixed and was
re-verified across the move of schedules onto the store, where the reconciliation it asked for
had to be rewritten against rows. 28 is narrowed by that same move and says how.

**What the provider seam closed, and what it deliberately did not.** Opening the seam ran a
receiver — the run's own transcript — behind a program for the first time, and writing to
one for the first time. So 8, 10 and 16 are fixed and gone from here: the receiver has its
own patience rather than sharing a departed program's drain, a record it failed on is
offered again before anything later, a loss it was never given is handed over as a gap in
the place it happened, a run that lost records no longer reports that it was fine, two
writes that both have to wait no longer collide, and saying a record was lost is bounded
like everything else that adds to the queue.

**What the channel seam closed on its way in.** A channel is held open by a gateway for
weeks and is answered for after a crash, so three things were owed before one could be:
17, 26 and 27 are fixed and gone from here. A gateway's account is bounded wherever it
lands and readable across rotation and both writers, a change whose audit line failed no
longer reports a plain success, a schedule left saying it started by a gateway that died
is reconciled rather than shown as in flight, and what never finished has a reader at
last. **6, 9, 12, 23 and 30 are still untouched** — every one of them is about admitting
work into a gateway, or about handing a gateway back to the machine that supervises it.
A channel admitting a turn is exactly that path, so they are due as the channel is held
open rather than as it is designed, and each is to be reproduced on the baseline of the
day rather than taken from its write-up.

**What the Discord round closed on its way through.** Round eight reviewed the one channel
adapter that ships. Five defects it found were fixed in the same run and are therefore not
entries here — named only so a later reader does not spend the effort finding them again: a
goodbye that consumed the whole shutdown budget and left the connection dropped rather than
closed; a reconnection announced to the owner as the agent coming up; a mention stripper that
removed everybody's naming and any prose between a literal `<@` and the next `>`; two
attachments on one message rebuilt to one filename, so the second was written over the first;
and an eviction that dropped a conversation with a turn still running in it, leaving its typing
indicator renewing for the life of the process. What is left below is what nobody may fix
without the owner: two behaviour and contract decisions, and a documentation truth.

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
| Ownership, cleanup and bounded resources | findings **9**, **12**, **23**, **30** |
| Crash recovery and idempotency | findings **9**, **12**, **23** |
| Concurrency, locks and atomic decisions | findings **12**, **14**, **21**, **30** |
| Provider protocol boundary | **no change needed** — see "Reviewed, no change needed" below |
| Scheduling correctness | findings **12**, **21**; **24** and **25** fixed and gone |
| Install, update and removal safety | findings **4**, **14**, **15**, **28** (narrowed) |
| Source of truth and auditability | findings **28** (narrowed), **29**; extensions to **12**, **19** |
| Consumer command surface | findings **32–35**; extensions to **6**, **13**, **28** |
| Measured performance | finding **9** (second consequence); measurements below |
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
`src/rundesk/process.py`, and program ownership in
`src/rundesk/gateway.py`.

### Crash recovery and idempotency

Review gateway crashes, machine restarts, partial writes, interrupted schedules and
repeated CLI requests. A retry must not duplicate work, erase the only recovery
record or report a recovered state that was not proven. Finding 1 is the existing
regression reference for keeping recovery evidence when descendants may still live.

Relevant implementation: runtime and interruption records in
`src/rundesk/gateway.py`, schedule outcomes in
`src/rundesk/schedule.py`, and restart commands in
`src/rundesk/cli.py`.

### Concurrency, locks and atomic decisions

Review simultaneous CLI commands, schedule changes, schedule firing, shutdown,
restart and update. A lock must cover the complete decision and mutation it claims
to protect, not only the initial check. Confirm that each durable fact has one writer
at a time and that an older completion cannot overwrite newer state.

Relevant implementation: gateway and schedule locks in
`src/rundesk/gateway.py`, schedule mutation and outcome writes in
`src/rundesk/schedule.py`, and active-work checks in
`src/rundesk/updater.py`.

### Provider protocol boundary

Confirm the low-level runtime provides bidirectional process transport, ownership,
cancellation and bounded delivery without interpreting Claude, Codex, Discord,
approval or conversation semantics. Provider adapters should interpret provider
events; channel adapters should present them. Recommend a new boundary only when
current code would otherwise force those semantics into the runtime.

Relevant implementation: structured input and output in
`src/rundesk/process.py` and orchestration in
`src/rundesk/gateway.py`.

### Scheduling correctness

The original review excluded scheduling. Review time zones, daylight-saving
transitions, day-of-month/day-of-week rules, missed runs, long-running work,
non-overlap, restart recovery and outcome ordering. Due-time calculation should
remain pure; the gateway should own the work it starts; durable outcomes should
never move backward.

Relevant implementation: `src/rundesk/schedule.py`, scheduled work in
`src/rundesk/gateway.py`, and `tests/test_schedule.py`.

### Install, update and removal safety

Finding 2 covers proving that launchd and a gateway released a job. Findings 4 and 5
cover truthful start and restart outcomes. Do not duplicate them unless they regress.
Extend the review to updates racing active work, partial replacement, rollback,
multiple installed gateways and whether every destructive step preserves enough
state for a safe retry.

Relevant implementation: `src/rundesk/updater.py`,
`src/rundesk/supervisor.py`, `src/rundesk/cli.py` and `install.sh`.

### Measured performance

Measure idle CPU, memory per gateway, message throughput, log growth, process startup
and shutdown time under realistic long-running workloads. Recommend optimization
only for a reproduced bottleneck, and prefer removing work or bounding it over
introducing caching or concurrency.

Relevant implementation: `src/rundesk/process.py`,
`src/rundesk/gateway.py` and log rotation behavior.

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

Relevant implementation: process creation in `src/rundesk/process.py`, launchd
job creation in `src/rundesk/supervisor.py`, state and logs in
`src/rundesk/gateway.py`, and archive handling in
`src/rundesk/updater.py`.

## High impact

### 4. Do not report an unsupervised gateway as successfully started

**Status:** Open — **the missing-job half is closed; the same-name/PID half is not.**
`start` now asks whether launchd holds a job at all. See also **finding 15**, which shows
that the unsupervised gateway `start` learned to recognise is still invisible to uninstall.

`supervisor.loaded()` answers only whether launchd holds a job with the gateway's name.
`cmd_start()` treats that boolean as proof that launchd owns the process currently holding
the gateway lock. A dormant launchd job and a manually started same-name gateway can
therefore coexist. The job is loaded, but it does not own the gateway PID and will not
bring that process back when its terminal exits.

Reproduced with a running gateway PID 7 and a same-name loaded job whose interface
cannot identify an active PID:

```text
start=(0, 'gateway: ALREADY RUNNING (pid 7)')
```

`rundesk agents` now reports the two observable facts separately as `RUNNING 7` and
`LAUNCHD JOB LOADED`; it no longer claims that the job supervises that PID. `start` still
asks the right system too weak a question. The smallest truthful answer is the active PID
launchd owns for this job, compared with `Standing.pid`; a loaded job with no active PID or
a different PID is not supervising the current gateway.

Regression criteria:

- "Already running" is success only when the supervisor confirms that its active job
  owns the same PID as the gateway record.
- A loaded but dormant same-name job, or one with a different PID, does not make a
  manually started gateway supervised.
- An unsupervised running gateway is reported as unsupervised with a non-zero exit.
- An unanswered supervisor query cannot be reported as success.

Relevant implementation: `loaded()` in `src/rundesk/supervisor.py`;
`cmd_start()` in `src/rundesk/cli.py`.

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

Relevant implementation: `_held()` and `standing()` in `src/rundesk/gateway.py`;
`cmd_status()` in `src/rundesk/cli.py`.

# src/rundesk/gateway.py:593-617
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
`src/rundesk/gateway.py`.

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
`src/rundesk/gateway.py`.

## High impact

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
`src/rundesk/gateway.py`; `describe()` in `src/rundesk/supervisor.py`.

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
`src/rundesk/gateway.py`; `describe()` in `src/rundesk/supervisor.py`;
`_stand_down()` in `src/rundesk/cli.py`.

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
`src/rundesk` as separate renames. A gateway brought up in that window can import a
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
`src/rundesk/updater.py`.

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

Relevant implementation: `take_all_back()` in `src/rundesk/supervisor.py`;
`stop_gateways()` in `install.sh`; `every()` in `src/rundesk/gateway.py`.

## Medium impact

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
`interrupted_path()` and `schedules_path()` in `src/rundesk/gateway.py`.

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
`src/rundesk/cli.py`; `Gateway._fire()` and `Gateway.start()` in
`src/rundesk/gateway.py`.

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
in `src/rundesk/gateway.py`; `_in_flight()` in `src/rundesk/cli.py`.

# Round four — 2026-07-25

Line numbers are against `43315ae`. Established by reading the source and by path
arithmetic, **not** by reproduction scripts — see the note in the header. Each finding
names the store, its writers, and the concrete disagreement or loss.

## High impact

### 28. Read a supervised gateway's directories from its own job, not from the ambient environment

**Status:** Open, and **narrowed to one variable and a half**. This was finding 22 one level
up: 22 was the gateway failing to pass the directories *down*, and this is a command failing
to read them *out of* the job already carrying them. 22 is fixed and gone.

What is left of this one is smaller than its body describes, because two things shrank it.
Everything of an agent's is derived from the agents root, so for an agent the only directory a
command and its gateway can disagree about is `RUNDESK_AGENTS_DIR` — `RUNDESK_RUN_DIR` and
`RUNDESK_LOG_DIR` reach only a gateway that is not an agent. And `RUNDESK_SCHEDULES_DIR` is
gone: a schedule is a row an agent keeps, so the whole class of "a schedule added and shown as
due by the command line, unknown to the gateway that would have run it" is unreachable now.
`RUNDESK_JOBS_DIR` is the half — it is in the job and read from the ambient environment.

Not fixed here on purpose: resolving the run and log directories out of the plist would
entrench the two the remaining store move deletes.

`describe()` bakes all four directories into the job's `EnvironmentVariables`
(`supervisor.py:148-159`), with a comment recording that omitting one "silently split the
machine in two". That fixes the gateway's half. The other half is unfixed: the values are a
snapshot taken when `rundesk start` ran, and every later command resolves the same
directories from **its own** environment (`gateway.py:109`, `:160`, `:193`). Nothing
compares the two, and nothing detects a difference.

So `RUNDESK_RUN_DIR=/tmp/x rundesk start gw` produces a healthy supervised gateway whose
lock and record live in `/tmp/x`, after which a plain command reads `~/.rundesk/run`:

- `cmd_agents()` finds no lock but still finds the plist through `described()`, so it
  reports `STOPPED` and `LAUNCHD JOB LOADED` while the gateway is up and working.
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

**Round six added part of the operator-facing reader.** `rundesk agents <agent>` shows the
paths resolved from the command's environment, but it neither reads the job's environment
nor shows the launchd plist. The CLI must identify which install, run state, schedules,
logs and launchd plist are authoritative; overrides must be shown exactly, not normalized
back to defaults. The interruption history supplies what this view must link, and finding 35
supplies the rest of the owned-state inventory.

Regression criteria:

- With a job whose `RUNDESK_RUN_DIR` differs from the ambient one and a live lock and record
  in the job's directory, `agents` does not report the gateway as stopped and `_in_flight()`
  sees its work.
- `stop` and `restart` act on the gateway the job describes.
- A name with no job keeps today's behaviour exactly.
- The CLI prints the exact resolved install, run, schedule, log and launchd job paths for
  both default and overridden locations.

Relevant implementation: `describe()` in `src/rundesk/supervisor.py`; `home()`,
`logs_home()` and `schedules_home()` in `src/rundesk/gateway.py`; `cmd_agents()`,
`_named()` and `_in_flight()` in `src/rundesk/cli.py`.

## Medium impact

### 29. Key durable work records by run, not by work name

**Status:** Open — **the smallest change that unblocks channel work.** Findings 26 and
27 each work around this key; none of them removes it.

Every durable per-work row is keyed by the work's *name* and is therefore last-write-wins
on a fact that has one value per **occurrence**:

- `_note_interrupted()` — `said[work] = {…}` (`gateway.py:383`)
- `_remember()` — `self._outcomes[name] = {…}` (`gateway.py:1208`)

Two consequences today, before any channel exists. The first is history that cannot
accumulate: work interrupted twice keeps only the second, so the reader of that history has nothing to count
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
`_note_interrupted()` in `src/rundesk/gateway.py`; `RETAINED_LINES` and the module
docstring in `src/rundesk/process.py`.

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
`Gateway._run_scheduled()` in `src/rundesk/gateway.py`; per-program receiver bounds
in `src/rundesk/process.py`.

# Round six — 2026-07-25

Line numbers are against `43315ae`. Material that repeated an existing failure is merged
above; findings 32–35 are only the distinct consumer command-surface gaps.

## High impact

### 32. Require an explicit scope for `stop` and `restart`

**Status:** Open

1. **Command and location:** `rundesk stop`, `rundesk restart`;
   `src/rundesk/cli.py:101-105`, `:343-351`.
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

1. **Command and location:** `rundesk uninstall`; `src/rundesk/cli.py:89`,
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

**Status:** Open — what a gateway itself writes is now bounded and readable (R-GW-35, R-GW-36); this is the control log for what the *command* did, which still has none.

1. **Command and location:** `start`, `stop`, `restart`, `update`;
   `src/rundesk/cli.py:275-321`, `:375-469`;
   `src/rundesk/updater.py:154-184`, `:211-262`.
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

**Status:** Open — read with findings 28 and 29 for inventory and run IDs.

1. **Command and location:** `status`, `schedules`, and the missing work controls;
   `src/rundesk/cli.py:472-507`, `:610-635`;
   `src/rundesk/gateway.py:678-709`, `:880-910`.
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
   gateway or run discoverable, as R-GW-38 now requires of a gateway.

## Tests that prove only the easy half

Each of these exists, passes, and is cited as evidence for a requirement it does not
fully cover. They are listed together because the pattern matters more than any one of
them: `check-evidence` can prove a cited test exists, and cannot prove it reaches the
state it is named for.

| Test | Cited for | What it does not reach |
|---|---|---|
| `test_removing_rundesk_refuses_while_a_gateway_is_still_running` (`tests/test_install.py:89`) | R-RM-9 | Writes a plist first, so the no-job case in finding 15 is never exercised |
| `test_inside_a_thread_it_opened_it_answers_without_being_named` (`tests/test_discord.py`) | R-DIS-3 | Drives `where_to_answer(ours=True)`, a pure function. Nothing proves `ours` is ever true on the wire, where it is `message.channel.owner_id == self.user.id` — so if Discord reports a message-thread's owner as the message's author rather than the bot that opened it, the agent needs naming again inside its own thread and the row is green on a mistake. One look at a real thread settles it |

# Round seven — 2026-07-26

Line numbers are against `0197953` plus the working tree that closed the clock phase. Found by
three reviews of that phase's diff and by driving it end to end; each was reproduced against the
code as it stands rather than argued from the source.

## Critical

### 39. A read-only command cannot read records whose `-shm` is not there

**Status:** Open, and the first thing to settle in the phase that owns the store.

`Store._reading` opens `file:<path>?mode=ro` (`store.py:270-277`). The database is in WAL mode,
and **a read-only SQLite connection cannot open a WAL database when the `-shm` file is absent**:
it has to create it and cannot. That is not a rare state — it is what a clean close leaves
behind, so a gateway or a turn that finishes and closes tidily is what puts the records into it.

Reproduced from nothing:

```text
store.Store(at).made()
rm state.db-wal state.db-shm
store.Store(at).runs()
  -> sqlite3.OperationalError: unable to open database file
```

Every read-only verb goes through this connection — `runs`, `usage`, `search`, `schedules`,
`agents`, `doctor` — and none of them catches `sqlite3.OperationalError`, because nothing of the
database's is supposed to reach them (`store.py` says so in its own docstring). So the owner gets
a traceback from the command they typed to find out what happened last night.

Nothing in the suite catches it: every case writes before it reads, in the same process, which
leaves the two files in place. It was found by a case that reads while a *separate* process is
writing — `tests/test_gateway.py`'s `_fired` waits it out and says why.

Regression criteria:

- Reading records whose `-wal` and `-shm` are absent answers, rather than raising.
- A read still cannot write: whatever makes the read work is enforced by the database, not by a
  convention a reviewer has to notice.
- The four read-only verbs answer with a gateway of that agent writing at the same moment.

Relevant implementation: `Store._reading()` and `Store._open()` in `src/rundesk/store.py`.

### 41. The Codex adapter drops what Codex asks *it*, so an approval hangs the turn forever

**Status:** Open. Latent today and reachable by one setting; recorded by the Phase 14 research
rather than fixed, because fixing it is a different task under a different baseline.

`Codex._listen` (`src/providers/codex`) sorts every message into two kinds: an answer to
something it asked (`"id"` plus `result`/`error`) and a notification (`_heard`). A **server-initiated
request** — `"id"` *and* `"method"` — is neither, so it falls through to `_heard`, which recognises
no such method and returns. Nothing is answered and nothing is said.

`codex app-server` at 0.145.0 defines six of these, generated by the CLI itself:
`item/commandExecution/requestApproval`, `item/fileChange/requestApproval`,
`item/permissions/requestApproval`, `item/tool/requestUserInput`, `mcpServer/elicitation/request`
and `mcpServer/oauth` flows. Codex **waits** for the reply.

Reproduced, in the probe committed at `.knowledge/scripts/probe-asking` (`codex-approve`):

```text
thread/start {"approvalPolicy": "untrusted", "approvalsReviewer": "user", "sandbox": "read-only"}
turn/start   "create a file …"
  -> item/fileChange/requestApproval arrives, nothing answers it
  -> the turn does not complete inside 120s and has to be killed
with a client that answers {"decision": "decline"}:
  -> `patch rejected by user`, no file, turn/completed normally
```

What keeps it latent is that the adapter never sets `approvalPolicy` and Codex's default does not
ask. So this is not a defect an owner can hit today — it is one that arrives the moment approvals
are wanted, or the moment Codex changes that default, and it arrives as a turn that never ends
rather than as an error anybody can read. `R-PRV-13` — ending an adapter on silence — is `❌` and
would not save it either: the adapter is not silent, it is talking about everything except the
question it was asked.

Regression criteria:

- A server-initiated request that the adapter has no policy for is **answered**, with a refusal,
  rather than ignored — a turn must not be able to wait on a decision nobody will make.
- What was asked and what was answered both appear in the run's account (`R-PRV-10`).
- A turn under an approval policy with no client answer ends rather than hanging.

Relevant implementation: `Codex._listen` and `Codex._heard` in `src/providers/codex`.

### 42. A read-only posture on Claude does not stop it writing to its own memory

**Status:** Open. A boundary finding rather than a crash; it decides what `R-PRV-18` may honestly
claim on this brain.

`R-PRV-18` says an adapter is told how much of the machine a turn may touch, and the Claude adapter
maps `read` onto an allowlist because prior art measured the allowlist to be the only thing that
holds. Measured on 2.1.220, it does not hold for one path: with `--allowedTools Read` and nothing
else, a turn asked to remember a word wrote a file to
`~/.claude/projects/<resolved cwd slug>/memory/`, outside the agent's own directory entirely.

Two consequences, and the second is the one that matters to the product:

- A turn an owner asked to **only look** wrote something durable, and nothing in the run's account
  says so.
- That memory is keyed by the **working directory**, and rundesk stands every one of an agent's
  turns in that agent's own home. So all of one agent's conversations share a memory namespace,
  and a *fresh* conversation answers another's question — reproduced in `probe-asking
  claude-resume`, where a fresh session standing in the same directory named a word only the
  previous conversation had been given. That is what `R-PRV-17`'s per-conversation handle exists
  to prevent, arriving underneath it.

Regression criteria:

- Either the read posture on this brain genuinely prevents durable writes, or the adapter stops
  claiming that it does and says what it really constrains.
- Two conversations of one agent cannot read each other's contents, or the limit is written down
  where an owner meets it rather than discovered.

Relevant implementation: `src/providers/claude`, and the posture rows of
`.knowledge/prd/provider-adapter.md`. Evidence:
`.knowledge/research/2026-07-26-questions-approvals-and-recovery.md`.

## High impact

### 40. A turn a schedule asked for is not ended when its gateway goes

**Status:** Open — **half closed.** The reporting is fixed and the ending is not.

`Gateway.asking` admits a turn whose brain is started by `turn.carry`, not by `Gateway.start`, so
it is not in `running` and `process.end_all` cannot reach it. As of `0197953` the gateway counts
it: `_go()` reports `drained=False`, exits non-zero, keeps its record and writes an interruption
naming it, so a supervisor is no longer told a clean stop happened while a brain was answering.

What is still open is that nothing ends the brain. Cancelling the task would not: `turn.carry`
has no cleanup that ends its `process.Program`, so the adapter and everything it started outlive
the gateway. **A channel turn has the same hole** — `Answering.stop()` cancels the exchange and
the program is left the same way — so this is one fix in `turn.carry`, not two, and it is not
specific to the clock.

Regression criteria:

- A gateway that goes while a turn is in flight leaves no adapter process behind, from either a
  schedule or a channel.
- The turn's outcome is still recorded as interrupted rather than as a failure to start.

Relevant implementation: `turn.carry()` in `src/rundesk/turn.py`; `Gateway._go()` and
`Gateway._asked()` in `src/rundesk/gateway.py`; `Answering.stop()` in `src/rundesk/answering.py`.

## Recorded on the way past, and not fixed

Neither meets the threshold — no reproduced consequence — and both would be found again by
somebody reading the same code, so they are written down rather than left to be re-derived.

- **`conversation.thread` and `conversation.parent_id` are columns nothing writes.** The unique
  key is `(channel, space, thread)` and `thread` is always `""`, because `turn.carry` never
  passes one; Discord folds a thread into `space` by reporting the thread's own id as the
  conversation. `parent_id` says so in `migrations/001.py` itself. R-STO-9 is ✅ on a case that
  passes `kind="thread"`, which is a different thing. Either a surface reports a branch and both
  columns start meaning something, or they are two fields a reader will assume are populated.
- **`ask --instructions` is not filled in or bounded the way every other preface is.**
  `channel.preface` runs `_fill` over `{agent}`, `{where}` and the rest and clips to
  `INSTRUCTIONS_MOST`; `--instructions` reaches the brain exactly as typed, so `{agent}` written
  there arrives as literal braces. Not wrong — a turn's own instructions are typed for that turn
  — but it is one surface of two behaving differently about the same-looking text.

## Reviewed, no change needed

Recorded so a later round does not repeat the work without new reason.

**Provider protocol boundary.** No provider, channel, approval or conversation semantics
have leaked into the runtime. `schedule.run` is carried and never read; `process` has no
knowledge of a gateway; `Held` and `Gap` are transport concepts. No new boundary is
needed — the existing `sink` / `send` / `Gap` surface is sufficient for a provider
adapter, and the two findings that stood in the way of one — a write that had to wait,
and a receiver sharing a departed program's drain — are fixed.

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

# Round eight — 2026-07-26

**Scope:** `src/channels/discord` (1,196 lines) and `tests/test_discord.py` — the one channel
adapter that ships, reviewed against `channel-discord`, `channel-messaging`, `channel-adapter` and
`guides/write-a-channel-adapter.md`, which the adapter's own docstring makes its governing contract.

**Baseline:** `37d0753`, reviewed on branch `phase-8-updates-an-owner-can-trust`. That branch was
merged and the checkout moved to `main` (`66387d7`) mid-review by another agent; `37d0753` is an
ancestor of it and the reviewed scope is **byte-identical at both**, so nothing here needed
re-establishing. The suite passed alongside every finding: `test_discord` 69 before, 84 after, and
the whole gate `GATE_EXIT=0` on 20 suites — with `test_discord` genuinely running rather than
skipping, which is checked by reading the count and the interpreter rather than the word `ok`.

**Outcome:** five defects found and fixed in the same run (named in the preamble, not entered here),
three left open below. Every claim was reproduced by driving the real adapter offline; nothing in
this round reached Discord, and the nine `❌` platform rows are untouched because a row nobody
watched stays `❌`.

## High impact

### 43. Two Discord channels on one bot token, and it is what `channels add` does by default

**Status:** Open — **a contract decision, not an adapter fix**, which is why nothing was changed.

`wanted()` returns `(True, True)` when no place is named, so one `rundesk channels <agent> add
discord …` writes two channels: `<name>-dms` and `<name>-rooms` (R-CAD-15). `_hold_channels()` is
"one task per channel, each started through `start`" (`gateway.py:1273-1276`), so two channels are
two adapter processes — and both read the same `token_from`, so they are two gateway connections on
one bot token. `.knowledge/MEMORY.md` records what that does, twice: one of the two stops receiving,
with no error on either side.

The consequence is worse than a plain outage because the failure looks like success. Each adapter
greets the owner on connect, so an owner adding Discord the ordinary way gets **two** "Gateway
online" messages, one from each channel — and then one kind of place is silently deaf. There is
nothing at `--check` time, nothing in the log, and nothing an owner could reasonably infer.

Reproduced structurally, offline: `wanted(options([]))` is `(True, True)`; `_shape()` emits both
suffixes; `_hold_channels()` starts one adapter per channel record; `token_for()` reads the same
variable in each. The Discord half of it is the owner's own reproduction, recorded in `MEMORY.md`.

**Why this is the contract's and not the adapter's.** R-CAD-15 — an adapter says which kinds of
place it reached, and each becomes a channel of its own — assumes the kinds of place are
independently connectable. On Discord they are two views of **one** connection. Either one adapter
process serves both kinds for a platform that works that way, or an adapter gains a way to say that
its shapes share a connection and rundesk holds one process open for the set. Both are changes to
`channel-adapter`, and the second is the one that keeps a stranger's adapter first-class.

Regression criteria:

- Adding Discord with no place named leaves the agent reachable in **both** direct messages and
  rooms at the same time, proved by a message in each being answered.
- An owner is told once that the agent came up, however many channels one `add` wrote.
- A platform whose kinds of place genuinely are independent is unaffected.

Relevant implementation: `wanted()`, `_shape()` and `token_for()` in `src/channels/discord`;
`_hold_channels()` in `src/rundesk/gateway.py`; R-CAD-15 in `.knowledge/prd/channel-adapter.md`.

### 44. A control is acknowledged with a promise nothing kept, including to somebody not allowed

**Status:** Open — **two candidate fixes and the choice is a behaviour decision**, so it waits.

`Agent._made` answers every slash command with `"✋ stopping this turn."`, `"🧹 this conversation
starts fresh."` or `"♻️ restarting the agent — it will be back in a moment."` *before* rundesk has
been told anything. `Answering._control` (`answering.py:308-318`) then drops the gesture in silence
when the person is not allowed, and `stop` drops it again when no turn is running there.

So two ordinary paths end with somebody told something that did not happen:

- Somebody **not on the allow list** types `/restart` in a shared room and is told the agent is
  restarting. That is both a promise nothing kept and a confirmation that the agent is listening —
  which is the exact thing the guide's silence rule exists to avoid: "replying to a stranger to
  tell them they are a stranger confirms the agent is listening".
- An owner types `/stop` in the **room** rather than in the thread the turn is running in, and is
  told the turn is stopping. `interaction.channel_id` is the room, which is not that conversation,
  so nothing is stopped.

This breaks two concrete rules in `guides/write-a-channel-adapter.md`: "do not promise the person
anything you have not been told happened", and silence for somebody not allowed. It does **not**
break R-DIS-12 — the acknowledgement carries none of the turn's own output, which is the trap that
requirement is about, and the adapter avoids it correctly.

The owner's choice:

- **Reword only.** Acknowledge the gesture rather than its effect. Smallest change, stays inside
  Discord's three seconds (R-DIS-11), and what the control actually did still arrives as the turn's
  own outcome.
- **Reword, and say nothing at all to an id absent from `RUNDESK_ALLOW`.** Closer to the guide's
  silence rule, but Discord then shows that person "The application did not respond", and the
  command is listed to them either way — so it buys less than it appears to.

Regression criteria:

- No acknowledgement states an effect that rundesk has not reported.
- A `/stop` where no turn is running, and any control from somebody not allowed, leave the person
  with nothing that claims something happened.
- The acknowledgement still lands inside the time Discord allows.

Relevant implementation: `Agent._made` and `COMMANDS` in `src/channels/discord`;
`Answering._control` in `src/rundesk/answering.py`.

## Medium impact

### 45. The nine unproven Discord rows point at lines that mean nothing

**Status:** Open — a documentation truth, and the rows belong to a ratified contract, so they were
not edited without the owner.

Every `❌` row in `.knowledge/prd/channel-discord.md` carries a `src/channels/discord:<line>` anchor
in place of the test it cannot name. All nine had already drifted off their subject **before this
round touched the file**, verified against the reviewed commit itself:

```text
git show 37d0753:src/channels/discord | sed -n '69p'   # R-DIS-14, "writes are paced"
  #: agent will never see once it is being kept up properly — which is the only way it is
                                                        :243p  # R-DIS-11, the three seconds
      if said:                                                 # (inside token_for)
                                                        :271p  # R-DIS-16, presence
  is still a word that has to go somewhere.                    # (inside split_at's docstring)
                                                        :279p  # R-DIS-15, up and down
                                                               # (a blank line)
```

`check-evidence` cannot catch it: it proves a **backticked** name is a real test, and these are
deliberately written plainly precisely because the row is `❌`. So the one column that is meant to
be the honest map of what nobody has confirmed sends the next person to the wrong part of the file,
and every edit to the adapter moves all nine again.

Regression criteria:

- What an unproven row points at survives an edit somewhere else in the same file — a function or a
  constant's name rather than a line number.
- The nine rows point at what they are about, checked by reading each one.

Relevant implementation: the Evidence column of `.knowledge/prd/channel-discord.md`;
`.knowledge/scripts/check-evidence`.

### 46. `CODEMAP.md` tells every agent that nothing reads the store, and four modules do

**Baseline:** `c25bbc6`, working tree clean. **Scope:** `.knowledge/CODEMAP.md`, found while auditing
`MEMORY.md`.

`CODEMAP.md`'s entry for `src/rundesk/store.py` still ends: "**Nothing reads it yet**; it is built
and proved before anything moves onto it, so deleting it would leave the product exactly as it is."
That was true when the store was built ahead of its callers. It is now false — `agent.py:28`,
`answering.py:34`, `cli.py:40` and `turn.py:43` all import it, and the product reads the store on
the ordinary path.

Why it matters rather than merely being untidy: `CODEMAP.md` is **always loaded**, so this is not a
stale corner somebody might find, it is a sentence every agent reads before every task. It invites
exactly two wrong moves — treating `store.py` as removable dead weight, and building a second path
to what an agent keeps on the belief that nothing depends on this one — and the second is the more
expensive, because `store.py` is declared elsewhere in the same file as "the only way in to it".

This is a documentation-truth defect against a concrete rule in the governing `AGENTS.md`
("Keep docs true in the same task that changes reality"; "Moved/restructured files -> update
`.knowledge/CODEMAP.md`"), not a behaviour change. Nothing in the gate can catch it: `doc-lint`
checks form, and `check-evidence` only reads `prd/` rows.

**Fix:** replace the "nothing reads it yet" clause with what is now true — which modules read it and
that it remains the only way in. One clause; left unfixed here only because `CODEMAP.md` was outside
the audit's scope and `AGENTS.md` gates changes outside a task's immediate scope.

**Regression check:** the sentence is absent, and `grep -rn "from rundesk import.*store" src/` names
the readers the entry claims.

Relevant implementation: `.knowledge/CODEMAP.md`, the `src/rundesk/store.py` entry under
"Backend / Services".

## Recorded on the way past, and not fixed

None meets the threshold — each is a behaviour change, and a behaviour change is the owner's
decision — and all would be found again by anybody reading the same code.

- **`--check` proves reachability and never the ability to write.** `_room()` fetches a guild or a
  channel; nothing asks whether the bot may post in it. A server-wide room channel can therefore be
  added cleanly and be unable to answer in most of the server's rooms, which is `403 Missing Access`
  at three in the morning — the exact outcome `_room()`'s own docstring says the check exists to
  prevent. The failure *is* reported when it happens (`could not write: Forbidden…`) rather than
  swallowed, which is right; what is missing is the check at setup.
- **The controls an owner does not have.** "Answer in these three rooms and no others" — no, it is
  one room or a whole server. "Never open threads, answer inline" — no. Both are small changes
  inside the adapter (`within` already compares one value; `where_to_answer` is one branch), and
  both are behaviour. **"Answer this person in DMs but not that one" already works**, because the
  two kinds of place are two channels with two allow lists — worth writing down as the seam holding
  a line rather than as a gap.
- **What "named" means is a direct user mention and nothing else.** A role the bot holds, an
  `@everyone`, a reply to the bot with its ping turned off, and an edit that adds a mention (there
  is no `on_message_edit`) all leave the agent silent, which *conforms* to R-DIS-2.
- **A group DM would be answered as a private one**, and handed the direct-message instructions
  that say "Nobody else can read it". Bots cannot join group DMs, so there is no supported scenario
  and this is not a finding — but the instruction would be untrue the day that changes.
- **`--bot <application id>` is accepted, stored in `settings`, and read by nothing.**
- **The cold guild cache is audited and clean.** `_room_named` waits for the connection;
  `_where_to_write` and `_react` both fall back to `fetch_channel`. `_typing` uses `get_channel`
  with neither, and only ever runs after a message has arrived, so there is no reachable
  consequence.
