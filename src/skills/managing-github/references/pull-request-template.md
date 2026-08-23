# Fallback GitHub pull-request template

Use this only when the target repository has no applicable pull-request template. Replace every
comment and placeholder, preserve the core headings, and check only outcomes proven by the exact
head. Add a conditional section only when it materially helps review.

````md
## Problem

<!-- State the current behavior or limitation, who or what it affects, and the consequence. -->

## Proposed solution

<!-- Describe the implemented outcome, important decisions and rationale, its boundary, and preserved behavior. -->

## Evidence

<!-- Give concise before-and-after observations, source locations, measurements, or contract links. Distinguish evidence from validation. -->

## Acceptance criteria

- [ ] <!-- Independently checkable outcome proven by this exact head. -->

## Validation

- [ ] `<exact command or manual check>` — `<observed result>`
- [ ] Required GitHub checks pass for the exact head commit.

<!-- Use one standalone `Closes #<number>.` line per completed issue. Use `Refs` for partial work. -->

## Agent

<!-- Replace the placeholder with the filing agent's display name. Omit provider and generated-by branding. -->

🤖 by <Agent>
````

Add **Scope and compatibility** when a public contract, migration, dependency, permission, or
preserved behavior changes. Add **Risks and safeguards** for a material security, privacy, data,
billing, destructive-operation, or deployment risk. Add **Manual user path** when a short
representative path would help a reviewer observe the result.
