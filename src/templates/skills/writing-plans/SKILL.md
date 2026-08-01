---
name: writing-plans
description: Create implementation plans for multi-step development work and save them in the agent workspace. Use when requirements or a specification need to become an executable plan before code changes, especially when another agent or future session may implement it.
---

# Writing plans

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version
of your own, copy it under a different name — that copy is yours and is never touched.*

A plan is an implementation contract: a worker with repository access but no conversation
history can follow it without guessing. Make it specific enough to execute and short enough
to remain useful when the code changes.

## Decide whether a plan helps

Write a plan when the work has three or more dependent steps, crosses components, carries a
risky migration, or will be handed to another worker or session. For a small local edit, state
the intent and verification in the turn instead of creating a document nobody needs.

If the requirements contain independent outcomes, split them into separate plans when each can
produce a working, testable result. Keep one plan when splitting would hide shared constraints or
force the same decision to be repeated.

## Put it in the agent workspace

Save every plan under the resolved agent workspace shown in the turn instructions:

```text
<workspace>/plans/YYYY-MM-DD-<short-topic>.md
```

Use lowercase words and hyphens in the filename. Create `plans/` if an older workspace does not
already contain it. A project may keep specifications, roadmaps, or issue notes elsewhere; do not
scatter implementation plans among them. If the owner explicitly names another destination, their
location wins.

## Inspect before decomposing

Read the requirements and the repository's own rules first. Locate the relevant implementation,
tests, interfaces, migrations, and documentation. Confirm paths and commands rather than recalling
them. Record unresolved choices that materially change the solution and ask before planning past
them; choose ordinary implementation details and state the choice.

Map the files before writing tasks. For each file, say whether it is created, modified, or tested
and what responsibility it has. Follow the existing structure unless restructuring is part of the
requested outcome.

## Plan document contract

Begin with:

```markdown
# <Outcome> implementation plan

**Goal:** <one sentence describing the completed behavior>

**Approach:** <the key design and why it fits this repository>

**Constraints:**
- <requirements, compatibility limits, authorization boundaries, and things that must not break>

**Proof:** <the checks that demonstrate the outcome>
```

Then write numbered tasks in dependency order. Each task contains:

```markdown
## 1. <Testable outcome>

**Files:**
- Modify: `exact/path`
- Test: `exact/test/path`

**Change:** <the concrete behavior, interfaces, data flow, and edge cases>

**Verify:** `<exact command>` — expect <observable result>
```

Use exact paths, existing symbol names, and commands verified in the repository. Include interface
signatures or data shapes when another task depends on them. Include representative code only when
it resolves an ambiguity that prose cannot; a plan is not a duplicate patch.

Every task ends in an independently checkable result. Fold setup, configuration, and documentation
into the task whose outcome needs them. Split a task when a reviewer could reasonably accept one
part and reject the other, not merely to make the checklist longer.

Do not put commits, pushes, deployments, messages, destructive operations, or account changes into
the plan unless the owner authorized them. If authorized, name the boundary and the verification.

## Remove guesswork

Replace placeholders such as `TBD`, “add validation,” “handle errors,” or “write tests” with the
specific cases and expected results. Do not say “similar to the previous task”; a worker may receive
only one task. Do not name files, flags, APIs, or commands you have not confirmed exist.

Separate facts from proposals. When a detail is inferred, label it and say what evidence would
confirm it. When discovery must happen during execution, make that discovery an explicit first step
with a decision rule for what follows.

## Review the finished plan

Before handing it off:

1. Map every requirement to at least one task and remove work that serves none.
2. Check that paths, symbols, interfaces, and terminology agree across tasks.
3. Search for placeholders and vague verification; replace each with an observable check.
4. Confirm task order follows dependencies and each task leaves a coherent state.
5. Confirm the plan preserves owner changes and stays within granted authority.

Say where the plan was saved and summarize the outcome, major decisions, open choices, and first
task. Do not begin implementation unless the request also authorized it.
