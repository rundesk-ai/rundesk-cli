# Suggestions

Confirmed runtime and lifecycle findings. Each finding was reproduced against the
implementation that existed when it was written.

Six rounds are recorded here.

**Round one (2026-07-25, findings 1–5).** Runtime and lifecycle; scheduling excluded.
The original five failure shapes are resolved on current `main`. They remain here as
regression criteria: a future change should not reintroduce any of them. Finding 4
now also carries a distinct, still-open same-name/PID variant found in round three.
Five findings carry a pointer to a later finding that touches the same code or the
same guarantee — read the pair together before changing either, because two later
fixes can reintroduce a round-one failure if applied naively.

**Round two (2026-07-25, findings 6–22).** The review the "Future low-level review
focuses" section below asked for, scheduling included. Findings 6–9 are critical,
10–15 high, 16–22 medium. All are **open**. Every one was reproduced against
`205467b` plus the in-flight `_keep` edit; the reproduction scripts and their observed
output are quoted inline. Findings 6–12 block provider and channel work; the rest do
not.

**Round three (2026-07-25, findings 23–25 plus extensions to findings 4, 6, 9, 12
and 14).** A gateway-foundation follow-up against `7841a0f` plus the existing
uncommitted gateway changes. Candidate findings were matched by underlying failure,
not wording: five overlapped existing entries and were merged into them; only three
new findings were added. The five gateway-facing suites still pass (326 tests), and
each added failure was reproduced separately.

**Round four (2026-07-25, findings 26–29 plus extensions to findings 11, 12, 17, 18
and 19).** A source-of-truth and auditability review against `43315ae`: which store is
authoritative for each runtime fact, which writers touch it, and whether an operator can
determine what happened and what is happening now. Eleven candidates were matched by
underlying failure; seven overlapped existing entries and were merged into them, four are
new. **Unlike rounds one to three, round four was established by reading the code and by
path arithmetic, not by running reproduction scripts** — treat its claims as verified
against the source at `43315ae` and unverified at runtime. Where a merged finding gained
new material, it is marked `Round four adds`.

**Round five (2026-07-25, finding 30 plus extensions to findings 8, 11, 16, 23
and 26).** A next-phase runtime-readiness review against the current uncommitted
worktree. Five of six candidates were the same underlying failures already recorded
and were merged with their current line references and new reproductions; only the
missing gateway-wide admission limit was new. The four focused suites still pass
(253 tests), and every added failure was reproduced separately.

**Round six (2026-07-25, findings 31–38 plus extensions to findings 6, 7, 13, 17,
27 and 28).** A consumer command-surface review against `43315ae`: whether every verb,
status, outcome, log and next action lets an owner operate Rundesk without knowing its
files or launchd plumbing. Overlapping material was merged into six existing findings;
eight distinct command-surface failures are new. The merge is by failure shape, not
wording, so each issue has one implementation plan and one complete set of regression
criteria.

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
| Ownership, cleanup and bounded resources | findings **8**, **9**, **12**, **16**, **17**, **23**, **30**; findings 1 and 3 have not regressed |
| Crash recovery and idempotency | findings **9**, **12**, **20**, **23**, **26** |
| Concurrency, locks and atomic decisions | findings **6**, **7**, **10**, **11**, **12**, **14**, **21**, **30** |
| Provider protocol boundary | **no change needed** — see "Reviewed, no change needed" below |
| Scheduling correctness | findings **12**, **20**, **21**, **24**, **25**, **26** |
| Install, update and removal safety | findings **4**, **14**, **15**, **18**, **28** |
| Source of truth and auditability | findings **26**, **27**, **28**, **29**; extensions to **11**, **12**, **17**, **18**, **19** |
| Consumer command surface | findings **31–38**; extensions to **6**, **7**, **13**, **17**, **27**, **28** |
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

## Critical

### 1. Verify the whole process group after its leader exits

**Status:** Resolved — but see **finding 9**, which defeats this finding's third
regression criterion by a different route: the recovery record survives, as required,
and is written in a state that can no longer prove ownership, so no successor acts on it.

`Program.end()` returned immediately once the process-group leader had an exit code,
and `end_all()` excluded that `Program`. A gateway could consequently report a clean
shutdown and delete its recovery record while a descendant remained alive.

Reproduced outcome:

```text
leader_returncode=0
gateway_reported_drained=True
record_exists=False
child_alive=True
```

Regression criteria:

- Ending a program must inspect and end its process group even when the leader has
  already exited.
- A gateway must report itself drained only when every owned process group is gone.
- A recovery record must remain when shutdown cannot prove that the group is gone.

Relevant implementation: `Program.end()`, `end_all()` and `Gateway._go()` in
`src/rundesk_cli/process.py` and `src/rundesk_cli/gateway.py`.

### 2. Prove both launchd and the gateway released a job before uninstalling

**Status:** Resolved for jobs this install wrote — see **finding 15** for a fourth form
of the same failure that this guard never enumerated: a gateway with no launchd job at
all is invisible to `take_all_back()`, so uninstall proceeds while it is still running.

Uninstall could proceed without proving that launchd released every job. The failure
had several forms:

- `take_all_back()` ignored a failed removal result and judged success only from
  gateway-process liveness.
- `python3 ... || echo` changed the supervisor cleanup's failure status back to
  success, bypassing the uninstall guard.
- A failed or timed-out `launchctl print` was treated as proof that a job was absent.
- A plist could be deleted after an accepted `bootout` while its gateway was still
  running, leaving the next attempt unable to discover it.

Reproduced outcome:

```text
taken=['gateway']
stubborn=[]
plist_exists=True
machine_loaded=True
```

Regression criteria:

- Uninstall must stop before deleting anything whenever either launchd or the gateway
  has not demonstrably let go.
- An unanswered supervisor query must remain "unknown", not become "not loaded".
- The job description must remain available for retries until both parties are gone.
- The shell cleanup function must preserve the Python cleanup command's failure status.

Relevant implementation: `take_all_back()`, `_let_go()` and `remove()` in
`src/rundesk_cli/supervisor.py`, plus `stop_gateways()` in `install.sh`.

## High impact

### 3. Bound the entire post-exit output drain

**Status:** Resolved — **do not revert while fixing finding 8.** Finding 8 concerns the
same constant used for a second, opposite purpose in `_settle()`. The fix there is to
split the constant, never to loosen the deadline this finding tightened.

`DRAIN_SECONDS` bounded each individual read rather than the complete drain period.
A descendant that inherited stdout and kept writing completed every read, so cleanup
could continue until the 48-hour ceiling, or forever when no ceiling was configured.

Reproduced outcome:

```text
leader_returncode=0
wait_done_after_0.6s=False
child_alive=True
```

Regression criteria:

- The drain uses one deadline shared by every post-exit read.
- Continuous descendant output cannot extend that deadline.
- Reaching the drain deadline proceeds to process-group cleanup.

Relevant implementation: `Program.wait()` in `src/rundesk_cli/process.py`.

### 4. Do not report an unsupervised gateway as successfully started

**Status:** Partially resolved — the missing-job case below is resolved. The
same-name/PID case found in round three remains open. See also **finding 15**, which
shows the unsupervised gateway this finding taught `start` to recognise is still
invisible to uninstall.

`rundesk start` returned success whenever the gateway process was already running,
without checking whether launchd held its job. A manually started gateway was therefore
reported as covered even though it would not return after exiting or rebooting.

Reproduced outcome:

```text
start_code=0
output='gateway: ALREADY RUNNING (pid 7)'
supervised=False
machine_actions=[]
```

**Remaining same-name/PID gap.** `supervisor.loaded()` answers only whether launchd
holds a job with the gateway's name (`supervisor.py:183-197`). `cmd_start()` treats
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

### 5. Return failure when restart stops a gateway but cannot start it again

**Status:** Resolved — see **finding 13**, which surfaces in this same function with a
message this finding did not cover, and whose cause is upstream in `Gateway.serve()`
rather than in `_stand_down()`. Do not attempt to fix finding 13 here.

When stopping succeeded but the subsequent supervisor start was refused,
`rundesk restart` printed `ALREADY STOPPED` and returned zero even though it had left
the gateway down.

Reproduced outcome:

```text
restart_code=0
output='agent-one: ALREADY STOPPED'
actions=[('stop', 'agent-one'), ('start', 'agent-one')]
```

Regression criteria:

- A refused post-stop start returns non-zero.
- The message says that restart failed after stopping, rather than describing the
  gateway as merely already stopped.
- A successful restart is reported only after the replacement gateway is observed up.

Relevant implementation: `_stand_down()` in `src/rundesk_cli/cli.py`.

---

# Round two — 2026-07-25

Line numbers are against `205467b` plus the in-flight `_keep` edit to `process.py`.
`gateway.py` numbers match `HEAD`; `process.py` numbers below line ~320 sit 8 lines
above their `HEAD` equivalents.

All 384 tests pass alongside every finding below (`test_process` 84, `test_gateway` 103,
`test_cli` 73, `test_updater` 54, `test_install` 39, `test_supervisor` 38,
`test_schedule` 28). Four of these findings are contradicted by a test that names the
exact risk and then proves only the easy half; those are listed together at the end.

## Critical

### 6. Treat a liveness question that could not be answered as "still running"

**Status:** Open

`_held()` answers `False` for *every* `OSError` on opening the lock file, so "I could
not ask" becomes "it is not running":

```python
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

### 7. Never write an empty schedules file over one that could not be read

**Status:** Open

`written_schedules()` maps both "the file is not there" and "the file could not be read
or parsed" to `[]` (`gateway.py:97-102` via `_read_json()` at `:176-181`).
`changing_schedules()` then writes `keeping` back unconditionally (`:91`), including on
the paths where the command decided there was nothing to do. A file that still contains
every schedule as recoverable text is replaced with `[]`, and the command reports
success.

Reproduced outcome — a hand-edited file with one stray character, then
`rundesk schedules --gateway gateway off nightly`:

```text
output='nightly: NOT FOUND — gateway has no schedule by that name'
exit=1
file_after='[]'
```

and the `add` path, which reports success while doing the same thing:

```text
output='new: ADDED — next 2026-07-26 04:00'
exit=0
file_after='[{"name": "new", "when": "0 4 * * *", "run": ["/bin/echo", "x"]}]'
```

A transient `OSError` on the read — `EINTR`, `ENFILE`, a stalled volume — destroys a
perfectly valid file the same way. This also contradicts `written_schedules()`' own
docstring, which reads the file as-written *because* removing a broken schedule is the
main thing anyone wants to do with one.

**Round six adds the read-only face.** `rundesk schedules --gateway gateway` calls the
same reader through `_list_schedules()` (`cli.py:610-635`), prints
`gateway: NO SCHEDULES`, and exits zero for the malformed file. Before any destructive
mutation, the control surface has already turned "cannot read the configuration" into a
healthy empty state. The error must name the path and parse/read reason, say that no
change was made, and preserve the original bytes.

Regression criteria:

- A schedules file that exists but cannot be parsed is never overwritten; the command
  says so and exits non-zero.
- "Absent" and "unreadable" are distinguishable at the point of decision, not collapsed
  by the reader.
- A change that made no modification does not rewrite the file at all.
- Listing a malformed or unreadable schedules file exits non-zero and never prints
  `NO SCHEDULES`.

Relevant implementation: `changing_schedules()`, `written_schedules()` and
`_read_json()` in `src/rundesk_cli/gateway.py`; `_add_schedule()` and
`_change_schedule()` in `src/rundesk_cli/cli.py`.

### 8. Give the receiver its own budget, and say what it never got

**Status:** Open — **read finding 3 first.**

Finding 3 correctly made `DRAIN_SECONDS` one deadline for the whole post-exit drain.
The same constant is now serving three unrelated purposes, and one of them is the
opposite of a drain:

- `Program.wait()` (`process.py:590`) — how long a leftover descendant may hold the
  pipe. Correctly short; this is finding 3's fix.
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

The fix is to split the constant, **not** to loosen the deadline finding 3 tightened —
those are different deadlines that happen to share a name today. The read loop is
finished and the program is gone by the time `_settle()` runs, so nothing is waiting on
the receiver. While a program is still running, the current record must remain pending
until the sink accepts it; retry uses bounded backoff, later output remains inside
`HELD_BYTES`, and eviction still becomes an ordered `Gap` rather than silent loss.

Regression criteria:

- The receiver's budget is a separate, generous constant, settable by the caller that
  knows its own sink; the descendant drain keeps finding 3's short shared deadline.
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

### 9. Capture a process's start time once, and never let a failed lookup erase it

**Status:** Open — **read findings 1 and 23 first.**

Finding 1 established that a recovery record must remain when shutdown cannot prove a
group is gone. It does remain. It is then written in a state that can no longer prove
anything, by the beat.

`_record()` re-derives `"since": started_at(program.pid)` for every running program on
every beat (`gateway.py:878-882`). `started_at()` (`:320-337`) shells out to `ps` and
returns `None` on any `OSError`, `SubprocessError` or five-second timeout. The value it
re-derives is a process start time, which cannot change. Once `since` is `null`,
`_sweep_predecessor()` (`:433-436`) refuses to act on the record for the rest of its
life, and the group becomes a permanent orphan: a provider CLI plus its editors,
language servers and search tools, holding a workspace, until the machine reboots.

Reproduced outcome — one failed `ps` at one beat:

```text
record_after_start={'work': {'pgid': 8012, 'since': 'Sat Jul 25 12:25:23 2026'}}
record_after_one_failed_ps={'work': {'pgid': 8012, 'since': None}}
successor_log="left 'work' (group 8012) alone: the record cannot prove it is ours"
successor_swept=[]
group_still_running=True
```

The proof is destroyed by exactly the condition that makes orphans likely: a loaded
machine.

**Second consequence — a blocking subprocess on the event loop.** `started_at()` is a
synchronous `subprocess.run`, called once per running program, per beat, from inside the
running loop. While it runs nothing reads provider stdout, nothing is delivered to a
sink, and queued signal handlers do not run. Measured with 8 programs:

```text
programs=8
one_say_blocked_the_loop_for=31ms
worst_case=PS_TIMEOUT_SECONDS(5.0) x 8 = 40s
```

`_go()` calls `_say()` on the not-drained shutdown path (`gateway.py:1075`), so the
worst case lands inside the shutdown window — see finding 12. Both consequences are
removed by the same change.

Round three also exercised the initial lookup failure, not only a later heartbeat.
`Gateway.start()` currently accepts the child and records `"since": null` when the
first `started_at()` fails. That work was never recoverably owned. Capturing once is
therefore only sufficient if establishing the initial fingerprint is part of the
startup transaction described in finding 23: if it cannot be established, end the
new process group and fail the start.

Regression criteria:

- `since` is captured once, when the program is registered, and reused.
- A new process whose initial fingerprint cannot be established is ended and is not
  accepted as running work.
- A failed or timed-out `started_at()` never downgrades a value already held.
- A beat does not stop the gateway reading what its programs are saying.
- Work left by a gateway is still swept after a beat the machine did not answer.

Relevant implementation: `Gateway._record()`, `Gateway.start()`, `started_at()` and
`_sweep_predecessor()` in `src/rundesk_cli/gateway.py`.

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

### 11. Hold a lock across the interruption history's read and write

**Status:** Open

`_note_interrupted()` (`gateway.py:368-394`) reads, modifies and writes with no lock.
Its own docstring names the hazard — *"two writers working from their own snapshots is
how one of them loses the other's entry"* — and then performs it. `_sweep_strays()`
makes concurrent writers routine: every gateway start writes into every abandoned name's
file, so a reboot bringing several gateways up together is the normal case.

Reproduced outcome, two processes, 20 entries each, under the 50-entry cap, three runs:

```text
run_1: wrote=40 file_holds=20 (A=6  B=14)  lost=20
run_2: wrote=40 file_holds=21 (A=1  B=20)  lost=19
run_3: wrote=40 file_holds=20 (A=0  B=20)  lost=20
```

Round five independently reproduced the same lost update with a barrier forcing two
processes to read the empty snapshot before either wrote (`gateway.py:382-392`):

```text
concurrent_interruptions=['second']
```

R-GW-23 — work in flight when a gateway goes is answered for rather than dropped in
silence — is the mechanism a channel layer would use to tell a conversation that its
session died. On the one occasion it matters most it loses half of what it records.

The lock this needs already exists in the right shape: `changing_schedules()`
(`gateway.py:75-95`) holds an `flock` on a `.changing` sidecar across the whole
read-and-write. Generalising it is the fix, and it also carries findings 7 and 20.

**Round four adds a second concurrent pair, which the fix must also cover.** The
reproduced case above is two *sweepers* racing on one abandoned name. The other pair is a
sweeper racing the file's **owner**: `_sweep_strays()` tests `_held(name)` at
`gateway.py:484`, then reads the record and notes interruptions; if the gateway of that
name claims in between, it writes its own predecessor sweep into the same
`<name>.interrupted.json` (`:769-773`), and the sweeper's later whole-file write erases
those fresh entries. So the file has two writers even when only one gateway is starting.
Both pairs close with one lock, but only if the lock is taken on the **target's** name
rather than on the writer's — this is the same lock finding 6 requires the stray sweep to
hold across its whole decision, so implement them together.

Regression criteria:

- Two gateways noting interruptions at once lose none of them; the test uses real
  concurrent processes, not sequential calls.
- A sweeper paused between its liveness check and its interruption write cannot erase an
  entry the target gateway wrote after claiming its name.
- Every unlocked read-modify-write of a durable file is either given the lock or shown
  to have exactly one writer.

Relevant implementation: `_note_interrupted()`, `_written_whole()` and
`changing_schedules()` in `src/rundesk_cli/gateway.py`.

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
nothing owning it — the outcome finding 1 exists to prevent, reached by a different
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

**Status:** Open — **the symptom appears where finding 5 was fixed; the cause is not there.**

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

**Status:** Open — **this is the fourth form of finding 2, not a new guard.**

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

### 18. Keep the owner's schedules and history unless removal is asked to take them

**Status:** Open

`schedules_home()` defaults to `~/.rundesk/schedules` (`gateway.py:193`), and
`install.sh:160-167` removes `$INSTALL_DIR` entirely. `--purge` guards only
`~/.config/rundesk` (`install.sh:147`). Schedules are unambiguously settings a person
made, so an ordinary uninstall destroys them — which R-RM-4 says it must not.

**Round four adds the rest of what goes with them, and what `--purge` is actually
guarding.** `INSTALL_DIR` defaults to `~/.rundesk` (`install.sh:23`), which is the parent
of all three data directories (`gateway.py:109`, `:160`, `:193`) — so the unconditional
`rm -rf` also takes `logs/<name>.log`, `<name>.ran.json` and `<name>.interrupted.json`.
That is the whole audit trail, and it contradicts R-GW-18 ("what a gateway wrote outlives
the gateway") as well as R-RM-4, at the one moment an owner is most likely to want it: a
reinstall after trouble. Meanwhile the flag that exists to ask about person-owned state
guards `~/.config/rundesk`, which **nothing in `src/` ever writes** — grep finds it only in
`install.sh:146` and two install tests. So the gate protects an empty placeholder while the
real state goes unasked.

Regression criteria:

- Removing rundesk keeps schedules unless asked to take them.
- Removing rundesk keeps the gateway logs, schedule outcomes and interruption history
  unless asked to take them; with `--purge`, all of it goes.
- The message naming what was left alone names what is actually there.

Relevant implementation: `install.sh` uninstall block; `schedules_home()`, `logs_home()`
and `home()` in `src/rundesk_cli/gateway.py`.

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
  the command prints `ADDED`. This is finding 7's "empty over unreadable" shape reached by
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
- No schedules command overwrites a file whose contents are not a schedule list (finding 7).

Relevant implementation: `checked()`, `ran_path()`, `seen_path()`,
`interrupted_path()` and `schedules_path()` in `src/rundesk_cli/gateway.py`.

### 20. Make the history files durable, not merely atomic for readers

**Status:** Open

`_written_whole()` (`gateway.py:163-173`) writes beside and renames, which is correct
against a concurrent reader, but performs no `fsync` of the file or of the directory.
R-SCH-9's guarantee that a firing is written down before it is run therefore survives a
process crash — which is what it was written for — but not a power loss or hard reset,
which is when a repeated side-effecting run is most likely.

This is not worth paying on every 15-second beat. It is worth paying on `ran.json`,
`interrupted.json` and `schedules.json`, and it belongs in the single persistence
helper that finding 11 introduces.

Regression criteria: the files that record what has already happened are durable across
power loss; the beat record is not required to be.

Relevant implementation: `_written_whole()` in `src/rundesk_cli/gateway.py`.

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

**Status:** Open — **read findings 1 and 9 first.**

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

**Status:** Open — **read finding 11 first;** it keeps the entries, this makes them
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

**Status:** Open — **the smallest change that unblocks channel work.** Findings 11, 26 and
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

**Status:** Open — read with findings 2, 15 and 18 for ownership, purge and history rules.

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
| `test_one_gateway_noting_an_interruption_does_not_erase_anothers` (`tests/test_gateway.py:1721-1727`) | R-GW-23 | Two sequential calls in one process; names the concurrent hazard in its docstring and never creates it |
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

**Cancellation of `Program.wait()`.** Tested directly with a receiver that never
returns: cancellation propagates, the child is ended, and the undelivered count is
reported. No finding.

```text
wait_propagated_cancellation_after=2.0s
child_alive_after_cancel=False
undelivered=5
```

**Retained diagnostic tails.** A concrete duplication between `deque(maxlen=...)`
and `_Lines._keep()` was reproduced during the runtime-boundary review and fixed in
`c173038`. The deque owned count eviction while `_keep()` owned byte accounting, so an
automatic eviction removed an item without subtracting its bytes. With a three-item,
100-byte limit, six 20-byte entries left two entries (40 actual bytes) while
`_held_bytes` still said 100. Sustained rollover eventually collapsed a tail that was
well below the byte cap to one line.

The fix is the smallest useful separation: the deque no longer evicts independently;
one `_keep()` implementation owns both count and byte eviction for `_Lines` and
`_Records` (`process.py:286-328`, `:358-400`). The direct regression test
`test_a_long_run_does_not_shrink_the_tail_it_is_keeping`
(`tests/test_process.py:1101-1118`) exercises sustained rollover without a subprocess.
Keep this single source of truth: long-running provider streams can contain large tool
results, and the retained tail is both a memory guarantee and the only diagnostic
returned when a program fails. No further decoupling is justified while that invariant
remains directly tested.

**Security and trust boundaries.** Nothing actionable today. `located()` refuses a
program named rather than resolved, in one place, applied both at schedule-add time and
at start; `environment()` builds rather than inherits; `_safe_extract()` handles the
link-target escape that most implementations miss; the release lookup deliberately
carries no credentials. The authorization boundary for channel replies and approvals
does not exist yet because the channel does not — it should be reviewed when it lands,
not before.

## Simplification opportunities

Not defects. Listed because each one removes a duplicated *decision*, and three of them
are where the findings above came from.

- **One JSON reader.** `_read_json()` exists (`gateway.py:176`) and is used three times;
  `standing()` (`:624-629`), `what_is_running()` (`:664-669`), `_sweep_predecessor()`
  (`:411-415`) and `_anything_left()` (`:506-518`) each re-implement it with slightly
  different shape checking. Four places must agree on what an unreadable record means,
  and finding 7 is what happens when they do not.
- **One orphan-reconciliation seam (findings 1, 6 and 9).**
  `_sweep_predecessor()` (`gateway.py:415-488`) currently parses durable state, decides
  whether identity is proven, probes the live group, sends TERM/KILL, sleeps, probes
  again, logs and records the interruption in one loop. `process._signal_group()`
  (`process.py:919-938`) separately documents that a failed signal must not end
  escalation. The duplicated decision still has the opposite failure shape at
  `gateway.py:469-487`: any `OSError` breaks escalation, yet the entry is appended to
  `swept` even if the group still answers. That is distinct from the ratified case where
  TERM and KILL were both sent and only an unreaped leader may still answer: that case
  may remain swept while recording `ended=False`. Finding 6 also supplies a different
  destructive race: `_sweep_strays()` must re-check the gateway-name lock immediately
  before it invokes the entry seam. Finding 9 supplies the process identity proof that
  the seam must never downgrade. Tests at `tests/test_gateway.py:938-1016` create and
  kill real process groups, so they cannot safely or deterministically cover every
  permission failure, identity change or group that survives both signals.

  Keep record I/O and iteration in place. Extract one same-module function for a decoded
  work entry, supplied only the presence probe, start-time probe, signal operation and
  pause operation it already uses; return the existing outcome facts for the caller to
  log and persist. A direct test can then script `present → TERM fails → still present`,
  `present → TERM → present → KILL → gone`, a fingerprint mismatch and an identity
  change between probes. Assert that failure to send or complete escalation remains
  unswept and retained; when both signals were sent, assert the current ratified swept
  status and `ended=False` if the group still answers. A separate direct test changes
  the gateway-name lock between record discovery and dispatch and proves the entry seam
  is never invoked. This is the highest-value consolidation because the code can kill a
  whole provider process tree or erase its only recovery record; it adds no class,
  public interface or new file.
- **One atomic-persistence helper.** `_written_whole()` (no lock), `changing_schedules()`
  (correct lock, one file), `_note_interrupted()` (needs the lock, lacks it).
  A `changing(path)` context manager yielding the parsed contents and writing them back
  under an `flock`, with `fsync` for the history files, carries findings 11 and 20
  together.
- **Return the reason rather than storing it.** `updater.why_unavailable`
  (`updater.py:34`) is a module global set in `latest_version_online()` and read in
  `run()` (`:140`). When `latest` is injected — the seam the module is built around —
  the global holds whatever the last real call left. Returning `(tag, why)` completes
  the seam.
- **Split `Gateway.start()`** (`gateway.py:888-977`), which combines the stopping check,
  name allocation, duplicate refusal, spawn, the born-into-shutdown recovery, the wait
  and five logging decisions. The born-into-shutdown branch (`:943-951`) is a lifecycle
  decision inside a work-starting method, and separating "register and spawn" from "wait
  and report" is what makes finding 12's task-holding fix natural.
