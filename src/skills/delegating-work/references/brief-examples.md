# Delegation brief examples

Read only the example matching the kind of handoff being prepared or reviewed. Preserve the common
contract fields from the main skill, but derive authority, evidence, and done conditions from the
actual assignment.

## Coding implementation

```text
Task: Add duplicate-invoice validation to the existing create flow.
Why: Prevent duplicate invoices without changing the response contract.
Scope: Inspect the relevant request, model, migration, and tests; edit only the files needed.
Authority: May edit scoped repository files and run focused tests; no publish, deploy, credentials, or unrelated refactor.
Constraints: Follow repository rules and existing validation conventions.
Evidence required: Changed files, behavior summary, and exact focused test command and output.
Definition of done: Duplicate input is rejected, unique input still succeeds, tests pass, and no unrelated behavior changes.
Return format: Result, changed files, verification, limitations, and blocker if incomplete.
```

Review the diff and test output yourself. “Tests passed” without the command or output is not proof.

## Code or design review

```text
Task: Review the authentication-timeout diff for correctness and regression risk; do not edit.
Why: Decide whether it is safe to merge without weakening session or logout behavior.
Scope: Review the diff, affected auth code, and relevant tests only.
Authority: Inspect only; do not modify files, create a PR, or change repository state.
Constraints: Follow repository rules and distinguish defects from optional improvements.
Evidence required: Severity, location, failure scenario, reasoning, and reproduction or test gap for each finding; checked coverage if there are no findings.
Definition of done: Every scoped change is reviewed and the verdict is evidence-backed.
Return format: Findings first, then checked coverage, uncertainties, and blocker if incomplete.
```

## Research or comparison

```text
Task: Compare the current official lifecycle commands with the local managing-rundesk guidance.
Why: Identify documentation drift before teaching a workflow that can fail at runtime.
Scope: Official sources and the local skill only, as of <date>.
Authority: Inspect and report; do not edit, install, or change Rundesk state.
Constraints: Separate sourced facts, inferences, and unknowns; do not fill source gaps from memory.
Evidence required: Source links or file locations and a claim-by-claim classification.
Definition of done: Every listed claim is confirmed, contradicted, or unverified with retraceable evidence.
Return format: Comparison table, material conclusion, limitations, and blocker if incomplete.
```
