# Delegation brief examples

Read only the example matching the kind of handoff being prepared or reviewed. Preserve the common
contract fields from the main skill, but derive authority, evidence, and done conditions from the
actual assignment.

## Coding implementation

```text
Task: Add duplicate-invoice validation to the existing create flow.
Why: Prevent duplicate invoices without changing the response contract.
Scope: Inspect the relevant request, model, migration, and tests; edit only the files needed.
Authority: May edit scoped repository files and run focused tests; no push, issue, pull request, merge, tag, or release; no deploy, credentials, or unrelated refactor.
Context: The existing create flow and response contract are authoritative; acceptance requires duplicate rejection without changing successful unique creation.
Constraints: Follow repository rules and existing validation conventions.
Evidence required: Changed files, behavior summary, and exact focused test command and output.
Definition of done: Duplicate input is rejected, unique input still succeeds, tests pass, and no unrelated behavior changes.
Return format: Result, changed files, verification, limitations, and blocker if incomplete.
```

Review the diff and test output yourself. “Tests passed” without the command or output is not proof.

## Code or design review

```text
Task: Use the configured senior review role to review <base>...<head> for authentication-timeout correctness and regression risk; do not edit.
Why: Decide whether it is safe to merge without weakening session or logout behavior.
Scope: Review the exact diff, affected auth code, nearby callers needed to validate behavior, and relevant tests only.
Authority: Inspect only; do not modify files, create a PR, or change repository state.
Context: The original request is <request>. Acceptance requires <criteria>. The working tree is <clean | contains named unrelated changes>; the implementation is otherwise ready for review.
Constraints: Follow repository rules and distinguish defects from optional improvements.
Evidence required: Severity, location, failure scenario, reasoning, and reproduction or test gap for each finding; checked coverage if there are no findings.
Definition of done: Every scoped change is reviewed and the verdict is evidence-backed.
Return format: Findings first, then checked coverage, uncertainties, and blocker if incomplete.
```

The brief names the configured role to select its established focus; it does not repeat that role's
generic checklist. The assignment supplies what the role cannot know: the exact change, supplied
intent, acceptance criteria, repository state, and required proof.

## Simplification review

```text
Task: Use the configured DRY/simplicity review role to inspect <base>...<head> for material duplication, redundancy, over-abstraction, or avoidable complexity; do not edit.
Why: Decide whether the change is clear and maintainable enough to merge without expanding its design surface.
Scope: Review the exact diff and only the nearby existing code needed to prove a duplication or simpler established pattern.
Authority: Inspect only; do not modify files, create a PR, or change repository state.
Context: The original request is <request>. Acceptance requires <criteria>. If the assignment supplies a compatibility or design constraint, name it; otherwise do not infer one.
Constraints: Follow repository rules; report only consequential simplifications, not style preferences or speculative redesigns.
Evidence required: Exact locations, concrete maintenance cost, the smaller safe alternative, and any behavior or compatibility constraint it preserves; checked coverage if there are no findings.
Definition of done: Every scoped change is checked and each finding demonstrates a material benefit over the current design.
Return format: Findings first, then checked coverage, uncertainties, and blocker if incomplete.
```

## Research or comparison

```text
Task: Compare the current official lifecycle commands with the local managing-rundesk guidance.
Why: Identify documentation drift before teaching a workflow that can fail at runtime.
Scope: Official sources and the local skill only, as of <date>.
Authority: Inspect and report; do not edit, install, or change Rundesk state.
Context: The local guidance will be used for <decision>; acceptance requires every material command and lifecycle claim to match current official behavior.
Constraints: Separate sourced facts, inferences, and unknowns; do not fill source gaps from memory.
Evidence required: Source links or file locations and a claim-by-claim classification.
Definition of done: Every listed claim is confirmed, contradicted, or unverified with retraceable evidence.
Return format: Comparison table, material conclusion, limitations, and blocker if incomplete.
```
