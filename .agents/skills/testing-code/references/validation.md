# Testing Code Validation

This is the current validation record for `testing-code`; the repository-wide method is in
[Validating Skills](../../../docs/guides/validation.md).

## Boundary under test

The skill should activate for designing, adding, repairing, assessing, or speeding up automated
tests and their local or CI feedback loop, choosing a test boundary, reproducing a defect as a
failing case, or diagnosing flaky, brittle, slow, or falsely green results. It should not activate
for production performance, a framework's test syntax alone, reviewing a completed change, or
diagnosing a failure whose cause is unknown.

Testing asks **what proves this behavior**. Debugging asks why a failure happens; review asks whether
a change is good.

## Trigger and exclusion cases

| ID | Request shape | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| TST-T01 | Add tests for this payment calculation | Load | ✅ | – |
| TST-T02 | "This test passes locally and fails in CI about a third of the time" | Load | ✅ | – |
| TST-T03 | "Nobody knows why the export is empty" | Do not load; `debugging-code` owns it | ✅ | – |
| TST-T04 | Review this pull request | Do not load; `reviewing-code` owns it | ✅ | – |
| TST-T05 | What is the syntax for a parameterized case in this runner? | Do not load; syntax alone is not the boundary | ✅ | – |
| TST-T06 | Turn a reported defect into a failing case before fixing it | Load | ✅ | – |
| TST-T07 | Laravel feature tests using factories and fakes | Compose with `using-laravel`; that package supplies the framework mechanics, this one the method | ✅ | – |
| TST-T08 | Python unittest isolation and cleanup | Compose with `using-python` | ✅ | – |
| TST-T09 | "What are we not testing here?" pointed at an existing suite | Load; assessing what a suite leaves unguarded is inside the boundary | ✅ | – |
| TST-T10 | "Our pull-request suite takes 18 minutes; make the feedback faster without dropping checks" | Load and read `performance.md` | – | ✅ |
| TST-T11 | "Profile this slow production endpoint" | Do not load; production performance belongs to the stack and debugging packages | – | – |
| TST-T12 | "The container build takes 14 of our 16 CI minutes; tests take one" | Do not load for CI wording alone; the measured bottleneck is outside test execution | – | – |
| TST-T13 | "Review this completed pull request that parallelizes PHPUnit" | Do not own the task; `reviewing-code` owns completed-change review | – | – |

## Workflow and authority cases

| ID | Request shape | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| TST-W01 | A test asserting a private collaborator was called | Assert the observable contract instead, unless the interaction is itself required behavior | ✅ | – |
| TST-W02 | An end-to-end test proposed for a pure calculation | Choose the narrowest boundary containing the risk | ✅ | – |
| TST-W03 | A mocked serializer described as an integration test | Reject the label; name which dependencies were real | ✅ | – |
| TST-W04 | A flaky test wrapped in a retry | Treat the flake as a defect; preserve seed, order, timing, and artifacts and fix the cause | ✅ | – |
| TST-W05 | A `sleep` before an async assertion | Wait on the condition with a diagnostic timeout | ✅ | – |
| TST-W06 | "Tests pass, so the fix works" | Require the test to be observed failing for the reported reason before the correction, or state the limitation explicitly | ✅ | – |
| TST-W07 | A green run reported with no counts | Read exit status, discovered and executed counts, skips, and retries; zero discovered is not a pass | ✅ | – |
| TST-W08 | A coverage target proposed as the goal | Coverage locates unexercised code; it does not prove assertions or justify an invented target | ✅ | – |
| TST-W09 | An assertion weakened until the suite is green | Reject it; update expectations from the requirement, not from current output | ✅ | – |
| TST-W10 | A unit case proposed for a transformation whose result is stored and drives an action elsewhere | Prove the transformation in a unit and the consequence where it lands; the narrowest boundary containing the risk reaches the consumer | ✅ | – |
| TST-W11 | A case written for edge-case behavior nobody specified | Refuse to record a guess as a requirement; the behavior is returned as a question, not asserted | ✅ | – |
| TST-W12 | A fixture-driven check that passes having discovered no fixtures | Report the discovered count and treat zero as unrun, whatever the check returned | ✅ | – |
| TST-W13 | Cases built from the single input the assignment illustrated | Derive the partitions from what real producers emit and existing consumers accept, including alternate representations and missing or malformed values | ✅ | – |
| TST-W14 | A suite to be assessed, whose test names read as complete | Work from what the code decides, stores, refuses, and emits, not from the test directory; a name is not an inventory | ✅ | – |
| TST-W15 | A case that executes the changed line while asserting something else | Report it as unguarded, not covered; execution is not verification and a percentage cannot show the difference | ✅ | – |
| TST-W16 | An assessment covering a surface larger than the risk in it | Rank by what a defect costs and stop; a complete list of trivia is not the deliverable | ✅ | – |
| TST-W17 | Work in a stack whose own package is installed | Load it for the runner's fixtures, doubles, and isolation while this package supplies the method | ✅ | – |
| TST-W18 | A slow suite with no timing evidence | Record a comparable baseline and attribute collection, setup, call, teardown, build, or CI phase time before proposing a fix | – | ✅ |
| TST-W19 | `--parallel` proposed for cases sharing one database and fixed port | Isolate every mutable resource, then benchmark worker counts on the actual runner | – | – |
| TST-W20 | A warm cache makes one CI run look fast | Separate cold and warm results, prove cache invalidation inputs and miss regeneration, and keep mutable test state out of the cache | – | – |
| TST-W21 | Two identical CI jobs run in parallel and settle together | Removing one reduces runner cost, not proven feedback latency; claim latency only when the critical path, queue, or contention improves in observed CI runs | – | ✅ |
| TST-W22 | A faster run discovers fewer cases after changing selection | Reject the speed claim unless the missing cases are an explained, authorized gate change | – | – |
| TST-W23 | Four equal-count shards finish in 3, 4, 5, and 14 minutes | Balance from representative durations, account deterministically for new cases, merge reports, and prove the shard union matches full discovery | – | – |
| TST-W24 | More workers slow a memory-constrained CI runner | Measure worker counts and choose the fastest stable level within CPU, memory, I/O, connection, and resource limits | – | – |
| TST-W25 | A browser journey repeats a decision table covered at lower levels | Move repeated partitions to narrow cases but retain the real journey that proves browser or protocol wiring | – | – |
| TST-W26 | A proposed improvement cuts time but weakens a load-bearing assertion | Reject it; comparable before/after time is valid only when the protected behavior still fails under a safe break probe | – | – |

## Provider evidence

A column per provider, because a rule that governs one model is not thereby proved on another. ✅
passed, ❌ failed, – not run. Record a cell only from a run you watched.

Claude last verified: 2026-08-24. Client: Claude Code 2.1.241, headless (`claude -p`), one fresh
session per case. Model reported by the client: `claude-opus-5[1m]`.

Codex last verified: 2026-08-26. Client: Codex CLI 0.148.0, headless (`codex exec --ephemeral
--ignore-user-config`), one fresh session per run. Model reported by the client: `gpt-5.6-sol`.

Each case ran in a throwaway project outside any workspace carrying a competing catalog, with this
package placed at `.claude/skills/<name>/` or `.agents/skills/<name>/` and nothing naming the skill,
the expected behavior, or the boundary under test. Skill and reference loading were graded from the
run's own tool-call trace, not from what the response claimed. Only cells marked above were run;
every other cell is untouched because nothing was observed.

**What the assessment runs showed.** Two independent runs were given an ordinary request — "our tests
here feel thin, what are we not covering?" — against a four-method ledger whose three tests read as
complete. Both loaded this package and both read `assessing-a-suite.md`. Neither worked from the test
directory: one broke six behaviors one at a time and the other ten, re-running the suite after each,
and both reported the resulting table. Both found that only one of the four methods was load-bearing,
both named the `assertIsNotNone` case as executing the line while asserting nothing — "this reads as
covered and isn't" — and both ranked by what a defect would cost rather than listing everything.

Both also found a defect the fixture's author had not planted: `refund` guards only the upper bound,
so a negative argument increases the recorded total and overcharges. One demonstrated it against a
real in-memory store. That is the reference's central claim working — the gap was not visible from
the test names, and the behavior inventory is what exposed it.

Both runs left the project byte-identical to a pristine copy taken beforehand.

**What the performance comparison showed.** The fixture had five Python `unittest` cases rebuilding
one expensive read-only catalog per case and two CI jobs running the same full command concurrently.
The natural task asked for faster local and pull-request feedback without dropping checks. One fresh
baseline without the skill measured once, safely moved the immutable setup to `setUpClass`, retained
5/5 cases, and removed the duplicate CI job. It did not test non-default order or test sensitivity,
and it incorrectly called removal of a parallel duplicate a CI feedback-time improvement.

The first skill-enabled draft measured five comparable runs before and after, rejected an accidental
zero-discovery command, passed a non-default order, and temporarily changed a catalog value to prove
the load-bearing assertion failed before restoring it. It still grouped lower runner consumption
under CI feedback improvement. That observed failure added the explicit critical-path and claim-
separation rules in `SKILL.md` and `performance.md`.

In the final fresh run, the provider loaded both files, measured three valid 5/5 baselines and three
5/5 results, and reported mean local wall time moving from 0.90 seconds to 0.15 seconds. It also ran
normal and error cases independently, verified all five methods remained, and compiled the files.
Its final report called the workflow edit reduced duplicate runner work and explicitly refused to
claim equivalent pull-request wall-clock improvement because hosted CI was not observed. The fixture
files, raw commands, outputs, and final diff were inspected directly after every run.

## Limits

`TST-W17` is proved for writing a case and unproved for judging one. Asked to add the missing tests
for a path, the run loaded this package and `using-python` together, and it read
`boundaries-and-doubles.md` and `proving-teeth.md`. It replaced the existing suite's `Mock` store with
a small fake and gave the reference's own reason — with a mock, `add` returns a canned value and the
test asserts the mock's own answer instead of the reversal — then broke the method three ways and
recorded which cases failed for each, restoring from a copy rather than `git checkout`, as that
reference requires. It touched only the test file. In the two assessment runs, by contrast, the stack
package was installed and neither loaded it; judging an existing suite leans less on a runner's
mechanics. Read the cell as covering the writing case only.

TST-W06 is this package's central claim and the hardest to verify from a transcript alone, because a
model can describe observing a failure it did not observe. Grade it on whether the run and its
result are reported, not on the narration. TST-T03 and TST-T04 are the exclusion cases most likely
to misfire.

TST-T10, TST-W18, and TST-W21 are proved only for the small Python fixture described above. The
parallel-resource, cache, shard, worker-limit, browser-boundary, and weakened-assertion cases remain
unverified as direct prompts. A fluent list of generic speed tips does not pass TST-W19 through
TST-W26.
