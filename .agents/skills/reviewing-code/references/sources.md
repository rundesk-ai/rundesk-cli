# Code-review source basis

This package synthesizes review practice; it does not copy a provider's review UI or language manual.
Use these sources to audit or revise a rule. Links and claims were checked on **2026-08-07**, except
the naming entry below, which was added and checked on **2026-08-13**.

## Review scope and judgment

- [What to look for in a code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html) —
  Google Engineering Practices says to inspect every assigned human-authored line, read broader file
  and system context, evaluate design and functionality, and verify that tests would fail for broken
  behavior. It also requires reviewers to state when they cover only part of a change. This supports
  the rules against diff-only review, green-suite overconfidence, and sampled-scope overclaim.
- [Navigating a change in review](https://google.github.io/eng-practices/review/reviewer/navigate.html) —
  Google starts with the change's purpose and overall design, then moves through every file without
  omission. This establishes the skill's broad-view-before-lines order.
- [The standard of code review](https://google.github.io/eng-practices/review/reviewer/standard.html) and
  [How to write code-review comments](https://google.github.io/eng-practices/review/reviewer/comments.html) —
  Google favors changes that improve code health without demanding perfection, gives technical facts
  and repository style guides precedence over preference, and labels optional comments so they are
  not mistaken for blockers. Its comment examples explain the concrete cost and preferred direction,
  which supports impact-based severity and actionable findings.
- [What to look for in a code review — Naming](https://google.github.io/eng-practices/review/reviewer/looking-for.html) —
  Google lists naming as a review dimension in its own right: "Did the developer pick good names for
  everything? A good name is long enough to fully communicate what the item is or does, without
  being so long that it becomes hard to read." This is the basis for the trap row on names that pose
  a question or name nothing, and it sets both bounds — a name that communicates nothing and a name
  that has grown into a sentence are the same failure from opposite ends. The reportable threshold
  stays the skill's own: a name is a finding when it hides what a value holds or breaks a repository
  rule, not when a reviewer would have chosen differently. [Avidan and Feitelson, ICPC 2017](https://www.cs.huji.ac.il/~feit/papers/Names17ICPC.pdf)
  supplies the impact — with 9 professional developers over 38 recorded sessions, 3 of 6 production
  methods showed no comprehension difference between their real names and names replaced by
  consecutive letters, "due to poor and even misleading variable names". The naming rule itself, its
  evidence, and its ecosystem conflicts belong to the `database-design` package and are not restated
  here.
- [GitLab code-review guidelines](https://docs.gitlab.com/development/code_review/) — this
  open-source project's practitioner guidance starts with why the change exists, requires the entire
  diff to be read, recommends local validation when appropriate, and distinguishes blocking from
  non-blocking feedback. It corroborates the workflow without making one hosting service mandatory.

## Comparison and context traps

- [Git `diff` documentation](https://git-scm.com/docs/git-diff.html) and
  [GitHub's explanation of branch comparisons](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-comparing-branches-in-pull-requests) —
  the official references distinguish working-tree, staged, direct-endpoint, and merge-base
  comparisons. They establish why a reviewer must resolve the requested artifact and effective base.
  Git is a conditional example in this skill, not a required review system.
- [The code-review checklist for engineering teams](https://sourcegraph.com/blog/code-review-checklist) —
  Matt Tanner, Sourcegraph, 2026. This practitioner guide names the changed-lines blind spot and
  recommends checking call sites, downstream consumers, contracts, configuration, migrations, and
  observability. It supports tracing a patch through unchanged context.

## Security, reliability, and proof

- [NIST SP 800-218, Secure Software Development Framework 1.1](https://doi.org/10.6028/NIST.SP.800-218) —
  PW.7 calls for human review and/or analysis of readable code to find vulnerabilities and verify
  security requirements, then for discovered issues and remediations to be documented and triaged.
  This establishes security as a risk-driven review lens rather than a language-specific checklist.
- [OWASP Secure Code Review Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html) —
  manual review complements automated analysis by examining business logic, complex security
  mechanisms, and context-specific vulnerabilities. This supports validating analyzer output rather
  than promoting it directly to a finding.
- [Testing for Reliability](https://sre.google/sre-book/testing-reliability/) — Alex Perry and Max
  Luebbe, Google SRE. Passing tests reduce uncertainty but do not prove reliability; production also
  contains rollout, configuration, version, traffic, and monitoring combinations absent from a
  hermetic suite. This supports examining rollout and observability and limiting claims from green
  checks.

## Empirical evidence and catalog conclusions

- [Characteristics of Useful Code Reviews: An Empirical Study at Microsoft](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bosu2015useful.pdf) —
  Amiangshu Bosu, Michaela Greiler, and Christian Bird, MSR 2015. The mixed-method study interviewed
  seven developers about 145 comments, built and validated a classifier, then analyzed about 1.5
  million comments across five Microsoft projects. Functional and alternate-scenario findings were
  rated useful; false positives and unrelated future work were commonly rated not useful. Useful
  comment density fell as changed-file count grew. The authors caution that all studied projects were
  mature, large-scale Microsoft projects using one tool, so this skill adopts the signal-quality and
  scope lessons without claiming universal effect sizes.

The source set does not directly prescribe this skill's exact report template. The template is the
catalog's synthesis: location plus trigger, impact, evidence, and correction makes each finding
testable and actionable. Grouping symptoms by one root cause is likewise a reporting conclusion, not
an empirical claim; retain separate findings when triggers or corrections differ.

Three later rules are catalog conclusions on the same footing. The report lists every altered output
with what reads it whatever else was found, because a disclosure owed only by an empty report is
switched off by the first small finding; Bosu et al. rate alternate-scenario findings useful but say
nothing about what a report must disclose once it has something to say. A requirement whose only
source is the change under review is a finding, not a specification. And a check that discovered no
cases is reported as unrun rather than passing, because a discovery count of zero exercises nothing
whatever the runner returns.

## Excluded source patterns

- Vendor feature pages that describe a review product but offer no transferable review judgment.
- Unsourced severity scales, arbitrary line-count limits, and claims that one check proves readiness.
- Language-specific checklists presented as universal review practice.


## Test adequacy

- Google's [Code Coverage Best Practices](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html)
  states that coverage measures which code executed rather than whether it was verified, and warns
  against coverage targets as a quality goal.
- Martin Fowler, [TestCoverage](https://martinfowler.com/bliki/TestCoverage.html), makes the same
  argument and suggests probing whether a test does any work by removing it and seeing whether
  anything fails.
- Petrović and Ivanković,
  [State of Mutation Testing at Google](https://research.google/pubs/state-of-mutation-testing-at-google/),
  reports surviving mutants as a signal of undetected defects and describes the cost that keeps the
  technique targeted rather than universal.
- Martin Fowler, [Mocks Aren't Stubs](https://martinfowler.com/articles/mocksArentStubs.html), and
  *Software Engineering at Google*, [Test Doubles](https://abseil.io/resources/swe-book/html/ch13.html),
  support treating over-specified interaction assertions as brittle and as weaker evidence than state
  assertions.
- Luo et al., [An Empirical Analysis of Flaky Tests](https://mir.cs.illinois.edu/marinov/publications/LuoETAL14FlakyTestsAnalysis.pdf)
  (FSE 2014), found that 24% of flaky-test fixes changed the code under test, 94% of those fixing a
  real bug. It is the evidence for treating a timing-dependent assertion in a diff as a potential
  defect report rather than a nuisance.
- Google's [Code Review Developer Guide](https://google.github.io/eng-practices/review/) and
  [What to look for in a code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
  list tests as a first-class review dimension and direct reviewers to check that tests are correct
  and would fail when the code is broken.

The signal table, the partition list, and the finding format are this package's operational
conclusions. Links checked 23 August 2026.

## Compatibility and migrations

- Martin Fowler, [ParallelChange](https://martinfowler.com/bliki/ParallelChange.html), names the
  expand–migrate–contract sequence and states its purpose: keeping old and new forms working
  simultaneously so a change to a published interface can be made without a coordinated release. It
  is the basis for treating a single-step add-and-remove as a finding.
- Martin Fowler, [Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html),
  and [Pact](https://docs.pact.io/) establish that a provider change is safe only against a known set
  of consumers and their expectations, supporting the consumer-inventory requirement.
- [`ALTER TABLE`](https://www.postgresql.org/docs/current/sql-altertable.html) documents which forms
  take an `ACCESS EXCLUSIVE` lock and which avoid a table rewrite, and
  [MySQL's online DDL operations](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html)
  documents per-operation whether concurrent DML is permitted. Together they are why a migration is
  reviewed as an operation with a lock profile at production row counts rather than as a script.
- [gh-ost](https://github.com/github/gh-ost) documents the class of schema change that requires a
  copy-and-cutover tool rather than an in-place alter, evidence that duration and locking are real
  operational constraints rather than theoretical ones.

Catalog conclusion: the overlap table, the migration-as-operation checklist, and the specific
findings list are this package's operational judgments. The sources establish the mechanisms; they do
not publish that list.

## Review depth, duplication, and simplicity

Added and checked on **2026-08-24**.

- [What to look for in a code review — Complexity](https://google.github.io/eng-practices/review/reviewer/looking-for.html) —
  Google names over-engineering as a kind of complexity in its own right: code "made more generic
  than it needs to be, or added functionality that isn't presently needed by the system", and it
  directs reviewers to "encourage developers to solve the problem they know needs to be solved
  *now*, not the problem that the developer speculates *might* need to be solved in the future". It
  also supplies the threshold this package uses for all three depth passes: "'Too complex' usually
  means 'can't be understood quickly by code readers.'" That makes complexity a property of the
  reader rather than a metric, and it is why an unearned abstraction is a review dimension here and
  not a preference.
- [The standard of code review](https://google.github.io/eng-practices/review/reviewer/standard.html) —
  "there is no such thing as 'perfect' code — there is only *better* code", and reviewers "should not
  require the author to polish every tiny piece of a CL before granting approval". It also settles
  where a convention comes from: aspects of design "are based on underlying principles and should be
  weighed on those principles, not simply by personal opinion", while "any purely style point
  (whitespace, etc.) that is not in the style guide is a matter of personal preference". This is the
  basis for grounding a convention finding in a stated repository rule and for the worth-fixing bar.
- [How to write code review comments](https://google.github.io/eng-practices/review/reviewer/comments.html) —
  Google labels non-blocking feedback explicitly, with `Nit:`, `Optional (or Consider):` and `FYI:`,
  so it is not mistaken for a blocker, and it asks the reviewer to explain *why*. This supports
  reporting a depth finding as Optional by default and requiring its cost to be stated.
- Dave Thomas and Andy Hunt, *The Pragmatic Programmer, 20th Anniversary Edition* — the publisher's
  excerpt of [The Evils of Duplication](https://media.pragprog.com/titles/tpp20/dry.pdf) states the
  DRY principle as "Every piece of knowledge must have a single, unambiguous, authoritative
  representation within a system", and its section *Not All Code Duplication is Knowledge
  Duplication* supplies the boundary directly, in a review setting: given two validators with
  identical bodies checking an age and a quantity, "during code review, the resident know-all bounces
  this code, claiming it's a DRY violation … They are wrong. The code is the same, but the knowledge
  they represent is different … That's a coincidence, not a duplication." The change-together test in
  this package is that passage restated as a question a reviewer can ask.
- Sandi Metz, [The Wrong Abstraction](https://www.sandimetz.com/blog/2016/1/20/the-wrong-abstraction),
  20 January 2016 — "duplication is far cheaper than the wrong abstraction". The article traces how an
  extraction acquires a parameter for the third caller and a conditional for the fourth until it is
  harder to read than what it replaced, and recommends re-inlining before extracting again. It is the
  evidence for treating a premature consolidation as the more expensive error.
- Martin Fowler, [Yagni](https://martinfowler.com/bliki/Yagni.html), 26 May 2015 — a presumptive
  feature is one "we presume our software needs in the future", and Fowler separates its costs into
  build, delay, carry, and repair, noting that delay and carry land even when the guess turns out
  right. This is the cost model behind the speculation pass, and the reason a present caller is the
  test rather than plausibility.
- The Bosu, Greiler and Bird study cited above supplies the empirical half: unrelated future work and
  low-value comments were the categories developers rated not useful. That is what the do-not-report
  list encodes.

Catalog conclusions on this material: the trigger table that decides which pass a change earns, the
three-way separation of duplication from simplicity from speculation, the Optional-by-default
severity for a depth finding, the do-not-report list as a list, and the rule that a second pass over
unchanged code should find nothing new. The sources establish the dimensions and the thresholds; none
of them publishes this routing.

## Attribution

This package adapts `skills/reviewing-code/` from the Rundesk skills catalog at
<https://github.com/rundesk-ai/rundesk-skills>, commit
`680e3d720547dbb563e6e15808e15c8f5bdd4083`, published by Rundesk AI under the MIT License.

Material modifications: the routing description narrowed against its neighbouring packages in this
catalog; a maintainer validation record added; the cross-layer impact rules, the trap rows covering a
self-ratified requirement and a check that discovered nothing, and the owed consumer inventory added;
and the depth references and the trigger table that routes to them added. The evidence requirement,
the severity definitions, and the verdict format are carried forward unchanged.
