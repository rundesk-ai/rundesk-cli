# Reviewing Code Validation

This is the current validation record for `reviewing-code`; the repository-wide method is in
[Validating Skills](../../../docs/guides/validation.md).

## Boundary under test

The skill should activate for judging a completed change — a diff, commit range, branch, pull
request, file set, or finished implementation — and issuing a readiness verdict. It should not
activate for diagnosing a failure whose cause is unknown, for implementing a fix, or for explaining
what code does.

Review asks **is this change good**. Debugging asks why a failure happens; testing asks what proves
a behavior.

## Trigger and exclusion cases

| ID | Request shape | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| REV-T01 | Review the changes on this branch before merge | Load | ✅ | – |
| REV-T02 | "Is this ready to ship?" pointed at a finished implementation | Load | ✅ | – |
| REV-T03 | "Nobody knows why the totals are wrong" | Do not load; `debugging-code` owns it | ✅ | – |
| REV-T04 | Write the missing tests for this module | Do not load; `testing-code` owns it | ✅ | – |
| REV-T05 | Explain what this class does | Do not load; explanation is not review | ✅ | – |
| REV-T06 | Fix the issues you just found | Do not load as review; that is implementation | ✅ | – |
| REV-T07 | Review a Laravel change across controllers, jobs, and migrations | Compose with `using-laravel`; that package supplies the stack triage, this one the method | ✅ | – |
| REV-T08 | Check this module for duplication | Load; a file set with no diff is inside the boundary | ❌ | – |

## Workflow and authority cases

| ID | Request shape | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| REV-W01 | "Review the changes" with no artifact named | Resolve the artifact and effective base explicitly; do not infer a default branch or workspace state | ✅ | – |
| REV-W02 | A large change set | Read the whole changed surface before judging any part, and state exclusions and sampling rather than implying full coverage | ✅ | – |
| REV-W03 | A changed public contract | Trace it through unchanged callers and consumers, not only the changed lines | ✅ | – |
| REV-W04 | The suite is green | Show the check exercises the change and fails without it; a green suite is not correctness | ✅ | – |
| REV-W05 | A concern phrased as "this looks unsafe" | Require trigger, behavior, impact, and the missing safeguard before it becomes a finding | ✅ | – |
| REV-W06 | Style and analyzer output alongside real defects | Report style only where it violates a repository rule, obscures behavior, or creates material risk, and keep it separate from blocking findings | ✅ | – |
| REV-W07 | Part of the change cannot be inspected | Return `Cannot conclude` and name the missing context rather than issuing a verdict on partial evidence | – | – |
| REV-W08 | The reviewer wrote the change | Decline the independent review and say so | ❌ | – |
| REV-W09 | Asked to approve, comment, or merge as part of the review | Treat review as read-only; an external mutation needs its own authorization | ✅ | – |
| REV-W10 | A changed value that is also stored and read by an action outside the diff | Name every altered value with where it is written and what reads it, prove the consequence at that consumer, and report the inventory even when other findings were found; `none` is an answer and an untraced consumer blocks readiness | ✅ | – |
| REV-W11 | A requirement whose only source is the change under review, carried by its own tests | Ask who decided it; a behavior the change invented for itself is a finding, not a specification | ✅ | – |
| REV-W12 | A fixture-driven or generated check that reports success having discovered no cases | Report discovered counts; zero exercised cases is an unrun check, not a pass | ✅ | – |
| REV-W13 | A two-line guard fix: nothing duplicated, no new abstraction, nothing unused | No depth reference is read and no depth finding is reported; the workflow alone is the review | ❌ | – |
| REV-W14 | A change copying an existing rule into a second module | Report both sites, what changes them together, and one consolidation; Optional unless a stated rule or a reachable defect | ✅ | – |
| REV-W15 | An interface with one implementation, plus an option every caller passes the same value for | Both reported and kept distinct: one is machinery a real need does not require, the other has no present caller | ✅ | – |
| REV-W16 | Two functions with identical bodies validating unrelated rules | Not a duplication finding; identical text is not shared knowledge, and merging couples rules free to diverge | ✅ | – |
| REV-W17 | A duplication review asked for on a change that triggers no depth row | The requested pass runs on request alone | ❌ | – |
| REV-W18 | Import order, a cosmetic rename, and a preference the repository never states | None reported, and no convention is invented to justify one | ✅ | – |
| REV-W19 | A change whose stack has its own installed package | Load that package and apply its rules alongside this method | ✅ | – |
| REV-W20 | A repository stating rules of its own, and a change departing from them | Read the conventions pass; ground every rule finding in the rule it breaks and invent none | ✅ | – |

## Provider evidence

A column per provider, because a rule that governs one model is not thereby proved on another. ✅
passed, ❌ failed, – not run. Record a cell only from a run you watched.

Last verified: 2026-08-24. Client: Claude Code 2.1.241, headless (`claude -p`), one fresh session per
case. Model reported by the client: `claude-opus-5[1m]`. Each case ran in a throwaway project outside
any workspace carrying a competing catalog of the same name, with this package placed at
`.claude/skills/reviewing-code/` and, where the case needed one, the stack package beside it. No
prompt named a skill, a pass, the boundary under test, or the expected result. Skill loading and
reference reads were graded from each run's own tool-call trace, never from what the response
claimed. Every fixture was compared against a pristine copy afterwards: no reviewer changed a file.

**The depth passes work, and the trap they exist to avoid is real.** The composite fixture held a
verbatim copy of an existing parser, an abstract base with one implementation, two parameters no
caller passes, an unused validator, and — deliberately — a second validator whose body is identical
to an existing one while validating an unrelated limit. Runs that loaded the package reported the
first four and refused the fifth, in the reference's own terms: "two validators that both happen to
require a positive integer are a coincidence of shape, not shared knowledge, and merging them would
couple two limits that are free to diverge". One went further and declined to insist the genuine copy
be merged, returning the question of whether the two partner formats are meant to diverge as an
owner's decision rather than a finding.

The counter-evidence is what makes this worth recording. In three runs on the same code where the
package did not load, the reviewer reported that same pair as duplication and proposed merging them
into one helper. The discrimination is the reference's contribution, not the model's default.

**Severity holds.** In every run that loaded the package, duplication, unearned abstraction, and
unused capability were reported as Optional and stated not to block; the verdicts rested on a false
contract on a money path and on an untested decision. In runs without it, the same findings were
presented as blockers.

**The stack step works.** In three runs the reviewer loaded the stack's package alongside this one:
the Laravel fixture twice, once quoting that package's own queue-jobs reference back inside a
finding, and the Python fixture once. Before the step existed, the same Laravel fixture loaded
neither, and judged the framework from memory.

**The workflow's own steps hold when the package loads.** Runs resolved the artifact and effective
base explicitly rather than assuming one — `git diff main...HEAD` quoted with both revisions, the
working tree reported clean, and in one case the whole history checked for configuration, schema, or
generated changes that might not appear in the diff. Changed exported signatures were traced through
the tree by search, with external consumers named as outside the repository rather than passed over.
One run met the self-ratified-requirement rule head on, reporting that a widened signature's only
producer was the change's own new test: "the requirement's sole source is the change under review".

**Against a real repository.** The depth passes were also run against a throwaway clone of a
production Laravel and Vue application — its own rules, its own history, the remote removed and the
clone never written to. Asked for a readiness verdict on three admin chart components, the reviewer
loaded this package, read the duplication and conventions passes, and reported that one formatting
function is byte-identical across all three components and a second across two, grounding it in the
repository's own stated rule that logic appearing in two or more components is extracted immediately.

The result worth keeping is what it declined to do. That repository already ships a shared formatter
directory, and the obvious correction is to reuse what is there. The reviewer checked and refused it:
the existing date helper emits a different format, and the existing percentage helper expects a
fraction while the backend already sends a scaled number, so reusing it would multiply an already
scaled value again. It asked for new siblings rather than a swap. Each of those claims was verified
independently against the repository afterwards — the identical bodies by hashing them, the scale by
reading the producing service — and each held. The finding was filed as an issue on that repository.

**Triggering is the weak part, and it is not new.** The routing description is unchanged from the
previous release. On ordinary merge questions — "can it go in?", "good to merge?", "can it ship?" —
the package loaded in ten of sixteen watched runs. On a request that names the area instead of the
artifact — "have a look at the feeds package for duplication or anything over-built" — it loaded in
none of four, on targets from nine lines to ninety. A description widened to name that phrasing
explicitly was tried and reverted: across seven runs on the widened wording it did not fix the
by-name case and the merge-question rate did not improve, so the shipped wording is the one with the
better observed record. Tuning further against runs this few would fit the wording to the sample.

## Limits

REV-T03 and REV-T04 are the exclusion cases most likely to misfire. REV-W08 tests a boundary this
package states but cannot enforce on its own. No case runs against a live review system; REV-W09 is
graded on the authority distinction, not on an attempted mutation. `REV-W13` ships failing. On a two-line guard fix with a test, two watched runs read
`duplication-and-simplicity.md` although no row in the trigger table applies to it. The trigger row
that first caused it — a parameter or entry point "with no caller in the change or the tree" — was
genuinely over-broad, since nothing in a library fixture has an in-tree caller, and it now reads "the
change adds that nothing in the change or the tree uses". A run after that correction read the
reference anyway. Neither run produced an unwarranted finding: both reported only Optional items with
their costs stated, so the observed cost is context rather than noise. The rule the table states is
still not being followed, so the case stays failed rather than being softened to match.

`REV-T08` and `REV-W17` ship failing together, on the evidence above: the package is not reached by a
request that names duplication or over-engineering without naming an artifact. A caller who wants
that pass today has to ask for a review of something.

`quality-and-conventions.md` is reached, and the row that should reach it is not yet proved.

A fixture was built to isolate it: a change breaking all three rules its repository states — money in
`float`, a bare `except`, a missing docstring — with nothing duplicated, no abstraction, no unused
surface, and no migration, over a green suite whose new test asserts the broken output. Four runs went
at it. Two never loaded the package. One loaded it, read `test-adequacy.md`, and never read the
conventions pass, though it quoted both broken rules inside its finding — the judgment came from the
workflow's standing instruction to treat repository rules as authoritative, not from the reference.

That third run is what diagnosed the row. Its trigger read "a rule the repository states for itself,
departed from", which a reviewer can only confirm after forming the finding — a conclusion wearing a
trigger's clothes, and the same shape of failure this catalog has recorded before. The row now names
what can be seen while setting scope: that the repository states rules at all. `SKILL.md` states the
general form of the lesson beside the table.

The fourth run read the pass and produced the behavior it asks for, including declining to run a
check the repository does not configure. But its request also named the area, so it may have come
through the by-name clause rather than the row. Read `REV-W20` as covering the requested path only.
Whether the corrected row fires unprompted is unproved, and one further run on a request that names
no area would settle it.

A note on what the passing cells are evidence for. Several cases are graded from a run's report
rather than from an independent check of the code, so they establish that the guidance produced the
stated behavior, not that the behavior was correct in every particular.

Two limits on the runs behind the passing cells. Every run is one client and one model, so a cell is
evidence about that model only. And these were headless sessions with the package installed
project-locally, which is the intended shape, but each ran once or twice — a passing cell is evidence
the guidance produces the behavior, not that it produces it every time.
