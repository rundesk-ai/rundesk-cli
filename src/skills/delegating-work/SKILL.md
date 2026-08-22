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
