# Debugging Code Validation

This is the current validation record for `debugging-code`; the repository-wide method is in
[Validating Skills](../../../docs/guides/validation.md).

## Boundary under test

The skill should activate when a failure's cause is not yet proved — a crash, hang, regression,
inconsistent behavior, wrong result, or a failing test, build, or runtime check. It should not
activate for judging a completed change, for explaining a cause that is already established, or for
writing tests as the primary task.

The three quality packages sit close together, and the seam is the question being asked:
**debugging asks why does this happen**, review asks **is this change good**, testing asks **what
proves this behavior**.

## Trigger and exclusion cases

| ID | Request shape | Expected behavior |
|---|---|---|
| DBG-T01 | "It crashes in release builds but not debug builds" | Load |
| DBG-T02 | "Two users report the total is sometimes wrong. Nobody knows why." | Load |
| DBG-T03 | Review this pull request for defects | Do not load; `reviewing-code` owns it |
| DBG-T04 | Explain how the retry mechanism works — no failure reported | Do not load; nothing is unproved |
| DBG-T05 | Add unit tests for an existing, working function | Do not load; `testing-code` owns it |
| DBG-T06 | The cause is already proved; apply the fix | Do not load; implementation, not investigation |
| DBG-T07 | A Laravel queue job that silently stops processing | Load, and route to the Laravel mechanics |
| DBG-T08 | A React component rendering twice in development | Load, and route to the React mechanics |

## Workflow and authority cases

| ID | Request shape | Expected behavior |
|---|---|---|
| DBG-W01 | A failure reported with a summarized error message | Require the exact error, stack, command, inputs, versions, and timestamps before theorizing; a summary can erase the distinguishing clue |
| DBG-W02 | An intermittent failure that passed on one run | Re-run the exact case; do not treat a single pass as resolution |
| DBG-W03 | Several plausible causes proposed at once | Test one hypothesis at a time and keep observation, inference, and hypothesis separate |
| DBG-W04 | "It works now after a rebuild" | Rule out a stale artifact and prove the build identity before accepting the cause |
| DBG-W05 | React component runs twice in development | Identify Strict Mode as the messenger, not the defect; reject a fix whose evidence is disabling it |
| DBG-W06 | "I think the cause is the cache layer" with no reproduction | Reject fluent assurance; require the observed divergence, not an inference from reading code |
| DBG-W07 | The failing environment cannot be reproduced locally | Say so and name what is missing, rather than diagnosing from source alone |
| DBG-W08 | Reproducing would touch production or customer data | Stop and escalate rather than reproducing against real state |
| DBG-W09 | Debug instrumentation added during the investigation | Remove it before the correction is proposed |

## Provider evidence

Last verification: not yet run against a live provider matrix.

- Claude Code: pending. This package was added after the sampled run performed for the ten
  technology packages.
- Codex: not run.

No case below is marked passed.

## Limits

DBG-T03, DBG-T05, and DBG-T06 are the exclusion cases most likely to misfire, because the three
quality packages share vocabulary. They should be exercised first, and against each other rather
than in isolation. No case reproduces a live failure; workflow cases are graded on the evidence
demanded and the order of investigation.
