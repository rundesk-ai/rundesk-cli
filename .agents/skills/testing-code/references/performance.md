# Making test feedback faster without making it weaker

Optimize the time to trustworthy feedback, not the smallest number printed by a runner. A run made
faster by skipping required environments, weakening assertions, replacing a real boundary whose
wiring is the risk, or hiding failures behind retries has lost the contract this skill exists to
prove.

## Measure the delay before changing it

Name which feedback time matters:

| Target | Measure |
|---|---|
| Focused local loop | Edit or selection to the relevant result |
| Full local suite | Invocation to final result |
| Pull-request CI | Workflow start to every required check settling |
| First useful failure | Workflow start to an actionable failing result |

For CI, the target is usually the required critical path, not the sum of every job's runtime. A
ten-minute job running beside a twelve-minute job adds twelve minutes to the result, not twenty-two.
Queue time is operational latency but not test execution; record it separately.

Capture a comparable baseline before editing:

- exact command, revision, runner and runtime versions, machine or CI runner class, worker count;
- wall time and the runner's collection, setup, call, teardown, transform, import, or build phases
  when it reports them;
- tests discovered and executed, assertions where available, skips, retries, failures, and coverage
  mode; and
- CI checkout, tool setup, dependency install, build, test, report merge, and artifact-upload times.

Separate cold-cache and warm-cache runs. Repeat noisy measurements enough to see ordinary variation;
compare like with like and report the observations instead of promoting the best run. A profiler is
evidence about where time went, not permission to change the hottest test before understanding the
contract it proves.

## Remove work in risk order

Work from the largest measured contributor. Re-run the same measurement after each material change
so one improvement does not conceal a regression elsewhere.

1. **Remove duplicate proof.** Keep one case for each material behavior at the narrowest boundary
   containing its risk. Remove a wider duplicate only after mapping the contract it asserted to a
   surviving case. Changed-test or focused selection accelerates the local loop; it does not replace
   the repository's required broader gate unless the dependency map is itself proved complete.
2. **Stop rebuilding irrelevant state.** Create only the rows, files, services, application boots,
   seed data, or compiled targets the case needs. Attribute fixture setup and teardown separately
   from the call before changing either.
3. **Share only safe setup.** Move expensive setup to a wider fixture or class scope only when the
   result is read-only or reset between cases, cleanup is guaranteed, and running alone, reordered,
   and in parallel proves no state leaks. Shared mutable state buys speed with order dependence.
4. **Remove waiting, not synchronization.** Replace fixed sleeps with the event or condition that
   establishes completion and retain a diagnostic timeout. Reducing the sleep value only makes the
   race harder to reproduce.
5. **Move slow external behavior behind an owned boundary.** Unit tests use a maintained fake or
   stub for a remote service; a narrow contract or integration case catches drift. Keep a real local
   dependency when its serialization, transaction, query, filesystem, or process behavior is the
   risk under test.
6. **Tune concurrency after isolation.** Give workers unique databases, ports, paths, accounts, and
   other mutable resources. Measure worker counts on the actual runner: process startup, memory,
   database connections, I/O, and CPU oversubscription can make more workers slower.
7. **Balance shards by time.** Split a suite across CI machines only after one-machine concurrency is
   sound. Historical duration data usually balances better than test counts; new and changed cases
   still need deterministic assignment. Merge reports and prove the union discovered the same suite.
8. **Cache reproducible inputs, not correctness.** Key dependency and build caches by every input
   that changes their validity: operating system, architecture where relevant, runtime or compiler,
   lockfile, build mode, and configuration. Do not cache mutable databases, generated test outcomes,
   or state whose reuse bypasses setup. Prove both cache hit and miss paths; a clean run must be able
   to regenerate everything.

Do not introduce a runner plugin, service, larger CI runner, or extra shard merely because it can be
faster. That changes dependencies or cost and needs the assignment's authority plus measured value.

## Tune the runner that is actually installed

Read the repository's declared versions and local help before copying a command. These are routing
examples, not permission to add a dependency or replace established tooling.

### PHP, PHPUnit, Pest, and Laravel

- Pest exposes `--profile`, parallel workers, and time-balanced CI sharding in current releases.
  Profile first; choose `--processes` from measurements on the real CI runner.
- Laravel's parallel runner allocates a test database per process. Segment any other shared resource
  with the process token, and recreate parallel databases only when schema freshness requires it.
- Prefer Laravel's transaction-based `RefreshDatabase` when it matches the repository's isolation
  contract; the framework documents full migration and truncation resets as slower. Do not swap
  reset strategies without the full database matrix proving equivalent isolation and behavior.
- PHPUnit's result cache can order by prior defects or duration. That can improve time to a useful
  result, but reordering alone does not reduce the work in a complete suite and can expose an
  order-dependent defect rather than cause one.

### Python

- Pytest's `--durations` and `--durations-min` separate slow setup, call, and teardown entries. Fix
  the phase that is slow rather than rewriting the assertion because its case ranks highly.
- `pytest-xdist` can distribute cases across workers, with scheduling modes that trade isolation and
  fixture reuse against balance. It is an optional dependency: use it only when already declared or
  when adding it is authorized, then prove every worker gets unique mutable resources.
- Standard-library `unittest` exposes `--durations` on Python 3.12 and later. On every supported
  version, reserve `setUpClass()` for expensive read-only state and register class cleanup as soon as
  the resource is acquired. Keep mutable fixtures per case.
- Last-failed selection and markers shorten a focused loop. The required CI suite still proves full
  discovery unless repository policy defines another complete, verified selection strategy.

### JavaScript and browser tests

- Vitest reports transform, setup, import, environment, and test time separately. Its worker pool,
  isolation, file parallelism, and shard settings solve different bottlenecks; benchmark them rather
  than changing all four. Disable isolation only for a proven-clean group whose order and parallel
  runs remain deterministic.
- Jest normally uses worker processes, yet constrained containers can run faster in band or with a
  smaller `--maxWorkers`. Measure the CI runner instead of assuming every reported CPU is usable.
- Playwright parallelizes by worker and shards across machines. Give each worker independent server
  data and accounts, retain failure traces or reports, and merge shard reports before calling the
  required check complete.
- A browser journey stays broad when browser, protocol, or rendering wiring is the risk. Moving its
  decision table into unit cases can reduce repetition; deleting the one real journey cannot.

### C++ and CTest

- Separate build time from test time before tuning either. A faster incremental build is not a
  faster test, and a test-only profile does not explain compilation.
- CTest runs selected cases with `-R` and parallel cases with `-j` or `CTEST_PARALLEL_LEVEL`.
  Declare processor or exclusive-resource needs where the project uses them, and cap concurrency by
  measured CPU, memory, I/O, device, port, and license limits.
- Use an explicit positive parallel level unless the project's CMake floor establishes the newer
  omitted-or-zero semantics; those changed in CMake 3.29.
- Use CTest load and resource controls when the runner would otherwise oversubscribe. Preserve the
  full required run after a focused local selection and keep failure output available.

## Shorten CI's critical path

After optimizing the test work itself, inspect the workflow graph:

- run independent required checks concurrently, but do not duplicate checkout, dependency install,
  build, or service startup inside one job without measuring the tradeoff against artifact transfer;
- distinguish wall-clock feedback from runner consumption: removing an identical job that ran beside
  another reduces cost, not the successful-path critical path, unless queue or shared-resource
  contention was observed;
- cache package-manager downloads or immutable build inputs with complete keys, never credentials;
- shard only a suite large enough to repay job startup and report-merge overhead;
- keep compatibility matrices separate from shards: environments repeat the suite to prove different
  contracts, while shards partition one inventory and must reunite into one complete result;
- use fail-fast to reduce wasted work after a decisive failure when the remaining failures are not
  required evidence; distinguish that from making the successful path faster; and
- retain concise failure diagnostics. Removing logs, traces, or reports can reduce upload time while
  increasing the time from failure to correction.

Do not move a required check to a later schedule and report the pull-request path as optimized. That
changes the gate. Name it as a coverage or policy tradeoff and obtain the authority to make it.

## Accept a speed improvement only with proof

Run the same relevant case and required broader checks before and after. The improvement is supported
only when:

- wall time or CI critical-path time improves beyond ordinary observed variation on a comparable
  environment;
- discovery, execution, assertion, skip, retry, environment, and coverage-mode differences are
  explained and intentional;
- the load-bearing cases still fail when their protected behavior is broken;
- the suite passes alone, reordered where supported, and at the chosen parallelism without shared
  state or resource exhaustion; and
- cold-cache CI remains correct, warm-cache CI demonstrates the expected hit, all shards settle,
  and their merged reports account for the complete required suite.

Report the baseline, bottleneck, change, before and after measurements, correctness checks, cost or
resource change, and any unmeasured path. A local benchmark and workflow edit do not prove a CI
latency change; call that path unmeasured until comparable CI runs settle, and do not headline or
summarize it as improved CI feedback. “Faster” without those facts is an impression, not a result.
