---
name: delegating-work
description: Use when carrying out work that may require recovering missing context, selecting and loading skills, deciding whether another Rundesk agent should help, writing or reviewing a delegation, or continuing work until an outcome is proved. It supplies an agent workflow for scope, context, deliberate skill use, necessary-only delegation, evidence-based review, and continuation paths. Do not use it as a substitute for Rundesk command reference or domain-specific implementation guidance.
---

# Work to an outcome

Own the requested outcome until every required result is delivered and proved. Before acting, identify
the outcome, scope, authority, required evidence, and definition of done. Keep optional findings
separate from the required result.

## Recover context before acting

When a referent, decision, owner, constraint, or prior result is missing, recover it from the current
conversation, supported Rundesk history, and the project's current source in that order. Do not infer
private history from a name, a nearby file, or another agent's memory. Separate observed facts,
inferences, and unknowns. Ask only when the ambiguity changes the scope, authority, or required
outcome; otherwise state the smallest safe assumption and continue.

If the needed context cannot be recovered, preserve the gap in the task and report it as a blocker.
Do not turn an absent fact into a confident instruction or delegated brief.

## Load only applicable skills

Inspect available skill descriptions before substantive work. Select every skill whose intent matches
the task, then read each selected `SKILL.md` completely and load the references it requires before
using the skill. A grant makes a skill available; it does not mean the body is already loaded.

Do not load unrelated skills to make the task look covered, and do not use a skill because its name
resembles the task. If a required skill is unavailable, say so and use only the remaining authorized
guidance; never claim that the unavailable workflow was applied.

## Decide whether to delegate

Work directly when the task is small or mechanical, when it needs the current agent's continuing
ownership, or when delegation would add more coordination than value. Delegate only when another
available agent is materially better suited to one bounded outcome and can return evidence the current
agent can review. Availability alone is not a reason to delegate.

Choose the target from its description and the delegation scope offered to the current turn. Use its
durable responsibility, not a temporary assignment.
Do not infer ownership from the target's name, provider, skill list, or gateway state. Gateway state
only confirms whether the selected route can run. Do not delegate to yourself, and do not delegate
again from a turn that is already answering a delegation.

Before handing off, confirm the selected gateway is running and make the brief a contract:

```sh
"$RUNDESK_COMMAND" gateways
```

If no permitted target materially fits, continue directly or report the routing gap. Do not bypass
the delegation scope with an attended `ask`.

## Write the delegation brief

Include all of these fields. If a field is unknown, name the gap and require the target to preserve
it as uncertainty rather than inventing an answer.

1. **Task** — the exact outcome or question, with the relevant files, system, and time boundary.
2. **Why** — the decision or larger outcome this supports.
3. **Scope and authority** — what is included, excluded, and whether the target may inspect or edit.
   Never imply permission to publish, deploy, change credentials, or broaden scope.
4. **Context and constraints** — known facts, project rules, assumptions to test, and required tools.
5. **Evidence** — artifacts, locations, commands, test output, sources, reproduction, or comparison
   the target must return.
6. **Definition of done** — observable conditions that must all be true for the handoff to be complete.

Use this shape:

```text
Task: <one bounded outcome>
Why: <what decision or deliverable it supports>
Scope: <paths, system, question, and time boundary>
Authority: <inspect only | may edit these exact files; no publish/deploy>
Constraints: <rules, invariants, and assumptions to test>
Evidence required: <artifacts and exact proof to return>
Definition of done: <observable completion conditions>
Return format: <result, evidence, uncertainties, and blocker if incomplete>
```

Do not write “look into this,” “fix anything needed,” or “report back” without an outcome and proof
standard. A good `Why` prevents locally correct work from solving the wrong problem; a good
definition of done prevents a plausible summary from being mistaken for completion.

## Start, review, and continue the handoff

Handing work off is non-blocking progress, not completion. Use the supported `ask` and `asked`
commands from this turn's delegation surface; do not poll for completion or leave a background
process as ownership of the outcome.

When an answer returns, review it against the original brief:

- Is the requested result present, or only discussed?
- Does each material claim have the requested evidence?
- Were scope, authority, constraints, and project rules respected?
- For code, did you inspect the diff and relevant test output yourself?
- For research or review, can the important claims be retraced and reproduced?
- Are limitations, uncertainty, and unresolved decisions explicit?

Adopt only what the evidence supports. If proof is missing, request a bounded correction or finish
the verification yourself; do not silently fill the gap.

Before ending a turn, choose one real terminal state:

- **Complete** — every required result is delivered and verified.
- **Continue** — useful in-scope work remains, so leave a durable continuation path naming the next
  action and the event that resumes it, such as an owner response or a delegated answer.
- **Blocked** — safe in-scope checks and alternatives are exhausted; state the exact blocker and the
  decision or external change required.

An open shell, background process, delegation id, or “I started it” is not a continuation path. Do
not report pending work as complete, and do not end a turn while required work remains without one of
the two honest paths: continue with a real resumption event or report the blocker.

## Examples

### Coding implementation

```text
Task: Add duplicate-invoice validation to the existing create flow.
Why: Prevent duplicate invoices without changing the response contract.
Scope: Inspect the relevant request, model, migration, and tests; edit only the files needed.
Authority: May edit scoped repository files and run focused tests; no publish, deploy, credentials, or unrelated refactor.
Constraints: Follow repository rules and existing validation conventions.
Evidence required: Changed files, behavior summary, and exact focused test command and output.
Definition of done: Duplicate input is rejected, unique input still succeeds, tests pass, and no unrelated behavior changes.
```

Review the diff and test output yourself. “Tests passed” without the command or output is not proof.

### Code or design review

```text
Task: Review the authentication-timeout diff for correctness and regression risk; do not edit.
Why: Decide whether it is safe to merge without weakening session or logout behavior.
Scope: Review the diff, affected auth code, and relevant tests only.
Authority: Inspect only; do not modify files, create a PR, or change repository state.
Evidence required: Severity, location, failure scenario, reasoning, and reproduction or test gap for each finding; checked coverage if there are no findings.
Definition of done: Every scoped change is reviewed and the verdict is evidence-backed.
```

### Research or comparison

```text
Task: Compare the current official lifecycle commands with the local managing-rundesk guidance.
Why: Identify documentation drift before teaching a workflow that can fail at runtime.
Scope: Official sources and the local skill only, as of <date>.
Authority: Inspect and report; do not edit, install, or change Rundesk state.
Evidence required: Source links or file locations and a claim-by-claim classification.
Definition of done: Every listed claim is confirmed, contradicted, or unverified with retraceable evidence.
```
