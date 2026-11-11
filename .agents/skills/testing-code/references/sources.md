# Testing-code source map

Use this map to audit a lesson, not as more testing procedure. Tool documentation establishes
observable runner and environment contracts; practitioner sources establish recurring failures and
field-tested replacements. Links were checked 7 August 2026.

## Contract, boundary, and maintainability

- [Google Engineering Practices: what to look for in a code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
  asks whether a test would fail when code is broken, warns that tests do not test themselves, and
  requires simple, useful assertions. This supports proving a regression fails and keeping test
  logic small. When the faulty revision cannot safely run, the skill requires disclosing that limit
  rather than substituting an unsourced proof technique.
- [Google Testing Blog: Test Behavior, Not Implementation](https://testing.googleblog.com/2013/08/testing-on-toilet-test-behavior-not.html)
  documents refactor-brittle interaction assertions and the exception for implementation details
  that are actual requirements. It establishes the first good/bad pair and mock boundary.
- Ham Vocke's [Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html),
  published by Martin Fowler, distinguishes unit, integration, contract, and end-to-end scopes;
  recommends observable behavior, real local dependencies, few high-level journeys, and no duplicate
  high-level coverage. The boundary labels in `SKILL.md` are a compact synthesis, not universal
  framework definitions.
- [Pact: writing consumer tests](https://docs.pact.io/consumer) distinguishes contract testing from
  provider functional testing and says each interaction should catch a consumer bug or a real
  misunderstanding. This establishes the narrow contract-test purpose.
- [Microsoft's unit-testing best practices](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices)
  provides worked bad/good cases for minimal inputs, readable Arrange/Act/Assert structure, avoiding
  logic in expected results, and testing private behavior through public behavior. Although its
  syntax is .NET-specific, these cited failure mechanisms are not.
- [Google Testing Blog: Include Only Relevant Details in Tests](https://testing.googleblog.com/2023/10/include-only-relevant-details-in-tests.html)
  demonstrates both traps behind test helpers: noisy fixtures obscure relevance, while over-extracted
  setup hides critical values and their relationship to the assertion.

Two rules in this section are catalog conclusions rather than source claims. Where a locally
computed value is stored or decides an action elsewhere, the narrowest boundary containing its risk
reaches that consumer: Pact establishes that producer and consumer must agree on the message and the
pyramid establishes that a wider case must answer a question a narrower one cannot, but neither says
on which side of a stored value the risk sits. Drawing partitions from what real producers emit and
existing consumers accept, rather than from the example an assignment happened to give, is the same
conclusion applied to inputs.

## Isolation, dependencies, and nondeterminism

- Bazel's normative [Test Encyclopedia](https://bazel.build/reference/test-encyclopedia) defines a
  hermetic test as depending only on declared or runner-guaranteed resources. It explains why
  undeclared services weaken reproducibility and risk cross-test collisions or accidental load, and
  requires unique temporary paths and cleanup when isolation is not supplied.
- John Micco's [Flaky Tests at Google and How We Mitigate Them](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html)
  reports that retries reduce false positives but encourage teams to ignore flakiness. It supports
  treating retries as mitigation/evidence rather than proof of a pass.
- George Pirocanac's [Test Flakiness remedies](https://testing.googleblog.com/2021/03/test-flakiness-one-of-main-challenges.html)
  maps order dependence, shared state, incomplete cleanup, environment assumptions, and timing races
  to isolation, controlled inputs, and synchronization rather than arbitrary delay.
- [pytest's flaky-test guidance](https://docs.pytest.org/en/stable/explanation/flaky.html) identifies
  uncontrolled system state and failed cleanup as common causes, points to order-randomizing and
  replay tools, and warns that a flaky signal can hide genuine failures.
- [Google Testing Blog: Time is Random](https://testing.googleblog.com/2008/04/tott-time-is-random.html)
  reproduces clock-dependent boundary failures and replaces ambient time with a controlled input.
- [Google Testing Blog: Sleeping Is Not Synchronization](https://testing.googleblog.com/2008/08/tott-sleeping-synchronization.html)
  shows that a fixed sleep is both slow and still racy; synchronization on the completion condition is
  the replacement. Playwright's current [auto-waiting contract](https://playwright.dev/docs/actionability)
  independently demonstrates bounded, condition-based actions and assertions in a maintained runner.

## Execution evidence and coverage

- [pytest exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html) distinguishes a
  successful collected run from exit code 5, where no tests were collected. This is direct evidence
  for rejecting zero-discovery false greens even when another runner reports them less clearly.
- Python's [`unittest` result and skip contracts](https://docs.python.org/3/library/unittest.html#skipping-tests-and-expected-failures)
  show that skipped and expected-failure cases are not executed as ordinary passing tests and are
  reported separately. The lesson is to inspect counts and reasons, not to prescribe Python syntax.
- [Google Testing Blog: Code Coverage Best Practices](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html)
  says coverage is a lossy, indirect metric: covered code may only be incidental or weakly asserted,
  no ideal percentage applies universally, and uncovered risky behavior is the useful review target.

## Deliberate omissions

- Framework syntax, runner configuration, snapshot mechanics, browser selectors, and language-specific
  fixture APIs belong in the relevant project or ecosystem skill.
- Universal coverage percentages, fixed test-layer ratios, and a rule to mock every dependency were
  omitted because the sources make them context-dependent or identify their failure modes.
- Production test traffic, retries-as-success, fixed sleeps, and “green means proven” were not softened
  into preferences because the cited contracts and field reports document concrete safety or signal
  failures and usable replacements.


## Boundaries and doubles

- Martin Fowler, [Mocks Aren't Stubs](https://martinfowler.com/articles/mocksArentStubs.html),
  establishes the double vocabulary and the state-verification versus behavior-verification
  distinction that decides between a stub and a mock.
- Gerard Meszaros, [Test Double](http://xunitpatterns.com/Test%20Double.html) in *xUnit Test
  Patterns*, is the origin of the five-term taxonomy — dummy, stub, spy, mock, fake — used in the
  table above.
- Google's [Know Your Test Doubles](https://testing.googleblog.com/2013/07/testing-on-toilet-know-your-test-doubles.html)
  restates the same distinctions in short form and warns against over-specified interaction tests.
- *Software Engineering at Google*, [Test Doubles](https://abseil.io/resources/swe-book/html/ch13.html),
  is the source of the preference order — real implementation, then fake, then stubbing, then
  interaction testing — and of the drift argument for maintained fakes over widespread mocking. It
  reports one organization's practice at scale.
- *Software Engineering at Google*, [Testing Overview](https://abseil.io/resources/swe-book/html/ch11.html)
  and [Unit Testing](https://abseil.io/resources/swe-book/html/ch12.html), support preferring the
  narrowest boundary and treating brittleness from over-specification as a maintenance cost.
- Google's [Just Say No to More End-to-End Tests](https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html)
  argues from experience that broad end-to-end suites are slow, flaky, and poor at localizing
  failure. It is an engineering opinion piece, not a study.
- Martin Fowler, [Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html),
  and [Pact](https://docs.pact.io/) establish contract testing as the mechanism that catches a
  double drifting from the real service.

The dependency-default table and the "doubles you own" rule are this package's operational
conclusions. Links checked 23 August 2026.

## Flaky diagnosis

- Luo, Hariri, Eloussi, and Marinov,
  [An Empirical Analysis of Flaky Tests](https://mir.cs.illinois.edu/marinov/publications/LuoETAL14FlakyTestsAnalysis.pdf)
  (FSE 2014), is the source of every number on this page: the study scope of 201 commits across 51
  Apache projects, the ten-category classification and its counts in Table 2, and findings F.1–F.12
  in Table 1 — including that 78% of flaky tests were flaky when written, 96% were
  platform-independent, 54% of async-wait fixes used a wait-for construct, 74% of order-dependency
  fixes cleaned shared state, and that 24% of fixes modified the code under test with 94% of those
  fixing a real bug. Its scope is open-source Java projects at the Apache Software Foundation; the
  proportions should be read as that population, not as a universal constant.
- Martin Fowler,
  [Eradicating Non-Determinism in Tests](https://martinfowler.com/articles/nonDeterminism.html),
  supplies the remedies organized by cause — isolation and rebuilt state, callbacks or polling
  instead of bare sleeps, test doubles for remote services with contract tests to catch drift,
  wrapping the system clock, and sizing resource pools to one so a leak surfaces immediately. It is
  also the source of the bounded-quarantine practice, including numeric and time limits.
- Google's [Where do our flaky tests come from?](https://testing.googleblog.com/2017/04/where-do-our-flaky-tests-come-from.html)
  reports, across 4.2 million tests, that larger tests are more prone to flakiness, and that one
  team found a newly flaky test traced to a production bug about one time in six. It is an
  engineering report on one codebase, not a controlled study.
- Google's [Flaky Tests at Google and How We Mitigate Them](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html)
  describes rerunning a failing test to classify it as flaky. Treat that as detection, not as a fix:
  the same practice used as a pass condition is the retry trap above.
- [`pytest-randomly`](https://github.com/pytest-dev/pytest-randomly) is one concrete implementation
  of seeded order randomization, cited as an example of the facility to look for in whichever runner
  is in use.

The ordering of the isolation table, the reproduction-rate step, and the do-not list are this
package's operational conclusions. Links checked 23 August 2026.

## Proving teeth

- Martin Fowler, [TestCoverage](https://martinfowler.com/bliki/TestCoverage.html), argues that
  coverage is useful for finding untested code and misleading as a target, and describes deleting a
  test and checking whether anything fails as a way to see whether it was doing work. It supports
  both the coverage caveat here and the probe itself.
- Google's [Code Coverage Best Practices](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html)
  states that coverage measures execution rather than verification, and cautions against treating a
  coverage number as a quality goal.
- Petrović and Ivanković,
  [State of Mutation Testing at Google](https://research.google/pubs/state-of-mutation-testing-at-google/),
  reports mutation testing applied at scale, including the cost of the technique and the handling of
  equivalent and unproductive mutants. It is an industrial experience report on one codebase.
- [PIT](https://pitest.org/) and [Stryker](https://stryker-mutator.io/) are maintained mutation
  testing implementations, cited as evidence that the technique is available in practice rather than
  only in research.
- Luo et al., [An Empirical Analysis of Flaky Tests](https://mir.cs.illinois.edu/marinov/publications/LuoETAL14FlakyTestsAnalysis.pdf)
  (FSE 2014), reports that 24% of flaky-test fixes changed the code under test and 94% of those
  fixed a real bug — the reason a test that passes for the wrong reason is treated here as a
  correctness risk rather than a tidiness one.

The break/observe/restore ordering, the false-pass table, and the copy-not-`git checkout` rule are
this package's operational conclusions. Links checked 23 August 2026.

## Assessing a suite

No new source underlies this reference; it applies the coverage sources already cited above to the
task of judging an existing suite rather than one change.

- Fowler's [TestCoverage](https://martinfowler.com/bliki/TestCoverage.html) establishes the one fact
  the whole reference rests on: coverage "is a useful tool for finding untested parts of a codebase"
  and "of little use as a numeric statement of how good your tests are", because "high coverage
  numbers are too easy to reach with low quality testing". That is why the assessment maps behaviors
  to cases rather than reading a percentage. The Google coverage post cited above makes the same
  argument; its body could not be retrieved on the check date, so nothing here rests on it alone.
- [Google Engineering Practices: what to look for in a code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
  states that tests do not test themselves and asks whether a test would fail when the code is
  broken. It is the basis for probing the load-bearing mappings instead of accepting them.

Catalog conclusions, and local heuristics rather than sourced findings: working from a behavior
inventory instead of the test directory, the three mapping outcomes, treating a case that executes
the line while asserting something else as the failure a percentage cannot show, ranking by the cost
of the defect, and the list of absences not worth reporting. Links checked 24 August 2026.

## Test and CI performance

### Measurement and stack mechanics

- [Pytest: profiling test execution duration](https://docs.pytest.org/en/stable/how-to/usage.html#profiling-test-execution-duration)
  documents `--durations` and `--durations-min` and reports setup, call, and teardown durations. It
  establishes the Python profiling example, not a universal slow-test threshold.
- [`pytest-xdist`: running tests across multiple CPUs](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)
  documents worker selection and the `load`, `loadscope`, `loadfile`, `loadgroup`, and `worksteal`
  schedulers. The fixture-reuse and balancing tradeoff is bounded to projects that already use or
  are authorized to add this plugin.
- Python's [`unittest` class and module fixtures](https://docs.python.org/3/library/unittest.html#class-and-module-fixtures)
  documents `setUpClass()` and `addClassCleanup()`, including cleanup after setup failure; the same
  manual documents `--durations` as added in Python 3.12. The read-only restriction is this catalog's
  isolation rule, not a promise made by `unittest`.
- Pest's [Optimizing Tests](https://pestphp.com/docs/optimizing-tests) documents `--profile`,
  `--parallel`, explicit process counts, parallel-isolation requirements, and time-balanced CI
  shards based on recorded durations.
- Laravel's [Testing: Getting Started](https://laravel.com/docs/12.x/testing) documents parallel
  process counts, per-process databases and tokens, persistent parallel databases, and explicit
  recreation. Laravel's [Database Testing](https://laravel.com/docs/12.x/database-testing) says
  migration and truncation resets are significantly slower than `RefreshDatabase`, whose behavior
  depends on schema state and transactions.
- PHPUnit's [CLI options](https://docs.phpunit.de/en/12.5/cli-options.html) documents result caching,
  duration and defect execution order, reproducible random-order seeds, and failure on zero tests.
  Ordering changes time to a particular result; the documentation does not claim it reduces total
  work, so the reference states that limit explicitly.
- Vitest's [Improving Performance](https://vitest.dev/guide/improving-performance.html) separates
  isolation, file parallelism, pools, caching, directory search, and sharding, and warns through its
  distinct controls that they solve different costs. Its example report separates transform, setup,
  import, environment, and test time.
- Jest's [Troubleshooting](https://jestjs.io/docs/troubleshooting#tests-are-extremely-slow-on-docker-andor-continuous-integration-ci-server)
  documents that constrained Docker or CI environments may improve with `--runInBand` or a limited
  `--maxWorkers`. Its reported percentages are environment examples, not expected gains, and are not
  carried into the skill.
- Playwright's [Parallelism](https://playwright.dev/docs/test-parallel) documents worker isolation,
  worker limits, sharding, and maximum-failure controls. The requirement to preserve and merge
  complete reports is this catalog's proof rule.
- CMake's [`ctest(1)`](https://cmake.org/cmake/help/latest/manual/ctest.1.html) documents focused
  selection, parallel level, processor accounting, job-server integration, load limits, resource
  specifications, and JUnit output. It establishes why C++ build time, test time, and constrained
  resources need separate attribution.

### CI mechanics

- GitHub's [Dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
  documents exact and partial key matching, automatic save after a successful job, setup-action
  support for common package managers, branch scope, cache-poisoning boundaries, and the prohibition
  on storing secrets. The complete-key and clean-regeneration checks are catalog conclusions from
  that invalidation and trust model.
- GitHub's [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
  documents matrix jobs and `strategy.fail-fast`, including cancellation of queued and in-progress
  matrix jobs. This supports distinguishing reduced failure-path work from a faster successful path.
- GitHub's [workflow artifact guidance](https://docs.github.com/en/actions/tutorials/store-and-share-data)
  documents sharing build and test outputs between jobs and retaining failure artifacts. Whether
  transfer beats rebuilding must still be measured for the repository.

Operational synthesis rather than a sourced universal ranking: optimize trustworthy feedback rather
than a runner's smallest duration; measure focused local, full local, CI critical-path, and
first-failure latency separately; distinguish queue time and phase timing; compare cold and warm
caches; remove duplicate proof before tuning workers; isolate before parallelizing; balance shards by
duration; prove the shard union; optimize the CI graph after test work; and accept a speed claim only
when comparable before/after runs preserve discovery, assertion strength, failure sensitivity, and
clean regeneration. Links checked 26 August 2026.

## Attribution

This package adapts `skills/testing-code/` from the Rundesk skills catalog at
<https://github.com/rundesk-ai/rundesk-skills>, commit
`680e3d720547dbb563e6e15808e15c8f5bdd4083`, published by Rundesk AI under the MIT License.

Material modifications: the routing description narrowed against its neighbouring packages in this
catalog; a maintainer validation record added; the consumer-reaching boundary rule, the
partition-derivation rule, and the unspecified-behavior rule added; the stack-mechanics step and the
suite-assessment reference added; and measured local and CI performance guidance added. The boundary
table, trap replacements, and run-evidence rules are carried forward unchanged.
