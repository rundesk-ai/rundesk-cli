---
name: delegating-work
description: Use when named delegation is a genuine option for current work, when preparing or reviewing a handoff, or when continuing delegated work to a verified outcome. It supplies context recovery, deliberate skill selection, necessary-only delegation, evidence requirements, and continuation discipline. Do not use for ordinary Rundesk operations, domain-specific implementation guidance, or conversation with no genuine delegation option.
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

## Check your own skills before delegating

Before deciding to delegate, inspect your available skill descriptions and load each skill whose
intent matches the work. Apply that guidance to the delegation decision: it may give you the domain
knowledge, workflow, or tools to handle the task directly. If another agent remains materially better
suited, use what you learned to make the scope, constraints, evidence, and definition of done precise.

A grant only makes a skill available; do not treat its body as already loaded. Do not load unrelated
skills, and do not infer a target's responsibility from its skill list.

## Decide whether to delegate

Count the full coordination cost: selecting and briefing a target, waiting for the return, reviewing
its evidence, and integrating it. Work directly when that cost is not clearly outweighed by better
speed, expertise, independence, or risk reduction. Ordinary conversation and simple documentation,
formatting, copy-only, or mechanical changes normally stay direct unless a real specialist judgment
or required independent review changes the balance.

Delegate only when another available agent is materially better suited to one bounded outcome and
can return evidence the current agent can review. Availability alone is not a reason to delegate.

Choose the mechanism that fits the work. Use a provider-local subagent for bounded review,
research, exploration, or validation that the current turn can supervise and integrate. Keep the
parent turn active and retain ownership of the result. Prefer a named Rundesk agent when its durable
responsibility and specialized granted skills make it materially better suited and the work benefits
from an asynchronous handoff that may outlive this turn. A named answer can wake a new review turn;
a provider-local subagent is not a durable continuation path.

Choose the target from its description and the delegation scope offered to the current turn. Use its
durable responsibility, not a temporary assignment. Relevant granted skills may confirm that a
named target has the procedure or capability the task needs, but skill names alone never establish
ownership. Do not infer ownership from the target's name or provider. A target offered to the
current turn is already an available route; do not add a gateway preflight. Send the handoff
directly and let `ask` report if admission is no longer possible. Do not delegate to yourself, and
do not delegate again from a turn that is already answering a delegation.

Choose role fit before writing the brief. A complete brief cannot repair a role mismatch. Send
implementation only to a target whose durable responsibility is implementing changes. Send
independent review only to a review target, and only after a finished, inspectable change exists.
Do not send discovery, planning, production analysis, or implementation to a target whose
responsibility is reviewing completed changes.

Before delegating implementation, identify its verification boundaries. Work spanning more than one
repository or more than one material risk boundary normally becomes separate dependency-ordered
phases, each leaving a coherent result with its own observable proof. Keep it in one handoff only
when it is one atomic outcome that cannot be safely implemented or verified in phases; state the
shared invariant and why splitting would weaken the result. Similar changes in two repositories are
not atomic merely because their implementations resemble each other.

If no permitted target materially fits, continue directly or report the routing gap. Do not bypass
the delegation scope with an attended `ask`.

Never delegate GitHub delivery to a named agent. The primary agent that received and owns the
requested outcome retains drafting or submitting issues; drafting, creating, or updating pull
requests; pushing branches; monitoring or responding to checks and reviews; and merging, tagging,
or publishing releases. Load `managing-github` and perform those actions directly. A named
implementation delegation ends with local implementation artifacts and evidence for primary review
and integration, even when the target has repository access or holds `managing-github`. An agent
asked directly by a person is primary for that request; this boundary applies when it hands work to
another named agent.

## Write the delegation brief

Include all of these fields. If a field is unknown, name the gap and require the target to preserve
it as uncertainty rather than inventing an answer.

1. **Task** — the exact outcome or question, with the relevant files, system, and time boundary.
2. **Why** — the decision or larger outcome this supports.
3. **Scope and authority** — what is included, excluded, and whether the target may inspect or edit.
   Never imply permission to publish, deploy, change credentials, broaden scope, or perform GitHub
   delivery reserved to the primary agent.
4. **Context** — the original request, acceptance criteria, current state, prior decisions, and
   assignment-specific inputs the target will not otherwise have.
5. **Constraints** — project rules, invariants, assumptions to test, and required tools.
6. **Evidence** — artifacts, locations, commands, test output, sources, reproduction, or comparison
   the target must return.
7. **Definition of done** — observable conditions that must all be true for the handoff to be complete.

Use this shape:

```text
Task: <one bounded outcome>
Why: <what decision or deliverable it supports>
Scope: <paths, system, question, and time boundary>
Authority: <inspect only | may edit these exact files; no push, issue, pull request, merge, tag, release, publish, or deploy>
Context: <original request, acceptance criteria, current state, prior decisions, and required inputs>
Constraints: <rules, invariants, and assumptions to test>
Evidence required: <artifacts and exact proof to return>
Definition of done: <observable completion conditions>
Return format: <result, evidence, uncertainties, and blocker if incomplete>
```

Do not write “look into this,” “fix anything needed,” or “report back” without an outcome and proof
standard. A good `Why` prevents locally correct work from solving the wrong problem; a good
definition of done prevents a plausible summary from being mistaken for completion.

A quality brief lets the recipient begin without guessing and omits history that does not affect the
assignment. Do not assume a named agent has the parent's conversation context. For a provider-local
subagent, include assignment-specific context that its provider may not inherit, but do not copy the
configured role's generic review or research instructions into the brief. For independent code
review, provide the exact base and head or precise dirty diff, the requested behavior and acceptance
criteria, the current working-tree state, the few highest-risk invariants specific to the change,
and the evidence needed for a verdict. Omit the review target's generic checklist and do not restate
its configured role.

Never make a brief look complete by turning an inference into a fact or inventing a design intent,
constraint, input, or acceptance criterion. Mark a material missing fact as an uncertainty or
blocker and state what the recipient may do without it.

Read [Brief examples](references/brief-examples.md) when composing or reviewing an implementation,
code-review, or research handoff. Adapt its fields to the task; do not copy an example's authority or
proof into a different kind of work.

## Manage the delegation

Hand work over with `ask`; it returns a delegation id immediately. Keep that id as the handle for
observing and controlling the work. Read [Delegation operations](references/operations.md) before
starting or managing a handoff; it gives the exact commands, provider selection, state refusals, and
return behavior.

Use each operation for its one meaning:

- List or `show` to inspect ownership, state, and provider provenance.
- `say` to steer work that is still running when its current course must change or a timely
  clarification materially improves it. Avoid status prompts and piecemeal optional guidance;
  provider delivery differs as described in the operations reference.
- `stop` to request an early terminal end. A stop request is not proof that work has stopped.
- `resume` to continue answered work in the same provider session. Stopped work cannot resume.

Treat the state as the next-action contract: `working` may be steered or stopped; `stopping` is
waiting for the terminal stop; `stopped` is closed; `answered` requires review and may be resumed.
Do not send `say` to answered work, resume working work, or treat a refusal as a state change.

Handing work off is non-blocking progress, not completion. Do not poll for the result or leave a
background process as ownership of the outcome. End with the delegated answer as the real resumption
event when no other useful in-scope work remains.

## Review and settle the handoff

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
