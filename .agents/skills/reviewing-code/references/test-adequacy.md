# Judging test adequacy

This is a distinct judgment from reviewing the production code, and it is the one most often
replaced by a glance at whether CI is green.

A passing suite establishes that the assertions written did not fail. It does not establish that the
change is correct, that the tests would notice if it were not, or that the risky paths were exercised
at all.

## Ask what would have to break for this to go red

For each material behavior the change introduces or alters, name the test that would fail if it
regressed. If you cannot name one, that is the finding — stated as a coverage gap on a specific
behavior, not as "needs more tests".

The strongest single question in a review is: **would this test still pass if the change were
reverted?** A test added alongside a fix that passes against the unfixed code proves nothing, and it
is common — it usually means the test asserts the input, a constant, or a double's own return value.

Where the change is a bug fix, look for evidence the test was observed failing before the fix. A
regression test that nobody watched fail is an assumption.

## Read the assertions, not the test count

| Signal in the diff | What it usually means |
|---|---|
| Asserts a mock was called, with no state assertion | Interaction pinned; behavior unproven, and brittle to refactoring |
| Asserts `not None`, `truthy`, or that nothing threw | The weakest possible claim; almost any implementation passes |
| Expected value computed with production logic | Both can be wrong together; there is no independent oracle |
| Snapshot updated in the same commit as the behavior | The snapshot recorded the new output rather than checking it |
| Assertion loosened, tolerance widened, or `assertAlmostEqual` introduced | Check whether the requirement changed or the test was made to pass |
| A `sleep` before an assertion | Timing assumption; expect this to flake under load |
| New test skipped, or marked expected-failure | Counts as added coverage in the diff and provides none |
| Test name describes the method, not the behavior | Often a sign the test was written to the implementation |

Read the counts in the run output, not the word "green": discovered, executed, skipped, expected
failures, and retries. A suite that discovers zero tests exits successfully.

## Check the partitions the change actually created

A change usually adds cases, not just lines. Ask which of these the change makes reachable, and
whether any is covered:

- The error and failure paths, including what the caller sees.
- Boundaries: empty, one, maximum, past-the-end, zero, negative, null.
- Authorization: the caller who may not, not only the caller who may.
- Concurrency and repetition, where the change touches shared or persisted state.
- Rollback and partial failure, where the change writes more than one thing.

Absent tests for the happy path are obvious in review. Absent tests for the refusal path are not, and
they are where the security and data-integrity defects live.

## Weigh the boundary, not just the presence

A test at the wrong level can be worse than none: an end-to-end test for a pure calculation is slow,
flake-prone, and localizes nothing, while its existence discourages the unit test that would actually
pin the rule.

Check that the test's boundary matches the risk the change introduces, and that its label is honest —
an "integration" test that doubles the boundary it claims to integrate with is misnamed, and the
review should say which dependencies were actually real.

## Treat coverage as a locator, not a verdict

Coverage tells you which lines executed. It cannot tell you whether anything checked the result, and
a line can be fully covered by a test that asserts nothing about it.

Use a coverage delta to find *what the change left unexercised* and then judge whether those paths
matter. Do not report a percentage as a finding, and do not accept one as an answer. Where the change
is high-risk and the team runs mutation testing, a surviving mutant on the changed surface is a much
stronger signal than any coverage number.

## Name the kind of gap, not the quantity

A gap is easier to act on when it is classified, because the classification implies the case that
closes it:

| Kind | What is missing | The case that closes it |
|---|---|---|
| Unexercised unit | The change adds a module, class, or command with no test at all | One case per behavior it decides |
| Unexercised entry point | A tested file gained a public function, endpoint, or handler nothing calls in a test | A case at the boundary a caller uses |
| Missing ordinary use | The behavior is tested, but not the way it is actually called | A case built from what a real producer sends |
| Unexercised wiring | Two changed parts meet — a handler and a store, a producer and a consumer — and only each side is tested | One case across the join, with the real boundary |
| Unexercised failure | The change adds a way to fail and only the success path is asserted | A case that triggers the failure and asserts what the caller sees |

Rank them by what a defect there would cost, not by how many there are: a missing refusal case on an
authorization path outranks a dozen untested display helpers. A report of three gaps that all matter
is worth more than one of thirty.

Some absences are not gaps, and reporting them costs the report its authority:

- A private helper already exercised through the public behavior that uses it.
- An accessor or pass-through with no decision in it.
- Generated code, scaffolding, and framework wiring the repository does not customize.
- An input so unusual that no producer in the system can emit it.
- A case that would assert what an existing case already asserts.

## Report it as a finding, not as a preference

Test gaps follow the same evidence bar as any other finding: name the behavior, the path that reaches
it, what goes wrong undetected, and the smallest test that would catch it.

```text
[Important] Refund path has no failing-gateway coverage — app/Services/Refunds.php:88
Trigger: gateway returns a 502 after the ledger row is written
Impact: the refund is recorded locally and never issued; no test fails
Evidence: only the success path is asserted in RefundsTest; no case exercises a non-2xx response
Direction: one case stubbing a failed gateway response, asserting the ledger row is not committed
```

"Add more tests" is not a finding. "This behavior can regress silently, and here is the case that
would catch it" is.
