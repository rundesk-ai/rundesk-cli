---
name: reviewing-code
description: Use when asked to review a diff, change set, commit, branch, merge or pull request, file set, or completed implementation for defects, regressions, security, reliability, maintainability, duplication, over-engineering, performance, test gaps, or repository-rule violations, and to issue a readiness verdict. It supplies a language-, platform-, and version-control-neutral workflow for establishing scope, tracing changed contracts to their callers, matching review depth to what the change contains, proving a finding before reporting it, and ranking by reachable impact. Do not use it to diagnose a failure whose cause is unknown, to implement the fix, or merely to explain what code does.
---

# Review code

Judge the change against intended behavior and repository rules, not personal preference. Seek
material problems; perfection is not the bar.

Treat review as read-only unless the user also asks for fixes. Do not post comments, approve, request
changes, merge, deploy, or mutate an external system without explicit authorization.

## Set the subject and scope

1. Read repository rules, the requirement, and relevant design decisions.
2. Resolve the artifact, intended outcome, and effective base. Ask the review system what it compares;
   do not infer a default branch, revision, or workspace state.
3. Enumerate the scope, including local staged, unstaged, and untracked work when applicable. Check
   hidden or truncated files and generated, dependency, schema, configuration, and documentation
   changes. State exclusions, sampling, and unavailable evidence.

If the repository uses Git, select the command matching the named artifact:

```sh
git status --short
git diff
git diff --cached
git show <commit>
git diff <base>...<head>
```

Use the repository's native comparison otherwise. A precise review of the wrong comparison is still
the wrong review.

## Load the stack's own rules

This skill supplies the review method and nothing about any particular technology. The rule a change
actually violates belongs to the package that owns that stack — `using-laravel`, `using-inertia`,
`using-vuejs`, `using-reactjs`, `using-tailwindcss`, `using-python`, `using-cpp`, `using-axmol`,
`using-postgres`, `using-mysql`, `using-sqlite`, and their neighbours.

Read the package for every language, framework, and data store the scope turns up, as soon as the
scope turns it up. A change reaching a framework and the database under it is two packages, not one.
Judging a stack from memory is how a reviewer reports a convention the framework does not have and
misses the trap it does. None of them needs to be installed for the method here to work.

## Trace behavior beyond the patch

1. Read the reason, history, and primary entry points; scan the complete change for boundaries,
   surprises, and high-risk operations.
2. Inspect every in-scope human-authored line and enough whole-file context to understand its
   contract.
3. Search changed names, interfaces, schemas, formats, flags, and invariants through callers,
   consumers, persistence, configuration, failure paths, and rollout. Name every value the change
   alters and, for each, where it is written and what reads it. One that is stored, or that decides
   an action somewhere else, is proved at that boundary and not only where it was computed.
4. Inspect tests, documentation, migrations, generated outputs, and operational changes that prove
   or carry the behavior.

Follow risk: correctness, boundaries, data integrity, trust, authorization, validation, privacy,
concurrency, compatibility, recovery, observability, and resource bounds. Check whether proof exercises
the changed behavior. Flag complexity or performance only for a concrete cost or defect risk.

Apply repository rules as authoritative. Report style only when it violates those rules, obscures
behavior, or creates material maintenance risk.

## Avoid known review traps

These pairs distill the evidence in [references/sources.md](references/sources.md), which should be
read when auditing or revising a rule. Angle brackets below are placeholders, not fabricated defects.

| Bad | Do instead |
|---|---|
| Review the convenient diff. | Name the artifact and effective base first. |
| Inspect changed lines only. | Trace contracts through unchanged callers and consumers. |
| `Green means correct.` | Show the check exercises the change and fails when it breaks. |
| `This might break` or `This looks unsafe.` | Show `<trigger> -> <behavior> -> <impact>` and the missing or bypassed safeguard. |
| Inflate uncertain concerns. | Rank reachable impact; mark uncertainty unverified. |
| Promote preference or analyzer output. | Require policy or a reachable failure. |
| Report each symptom. | Report one root cause and its affected paths. |
| Wave through a name that poses a question or names nothing. | Flag it where it hides what a value holds or breaks a rule, and give the value it should name. |
| Sample, then declare readiness. | Name scope; use `Cannot conclude` when omissions block judgment. |
| Accept a rule the change wrote for itself. | Ask who decided it; a requirement whose only source is the change under review is a finding. |
| Count a check that discovered nothing. | Report discovered counts; zero exercised cases is an unrun check, not a pass. |
| Review every change at one depth. | Read the reference the change's own contents trigger, and no more. |

## Prove and rank findings

Require **location -> trigger -> behavior -> impact -> missing safeguard**. Confirm callers and tests
do not resolve it and it was introduced by or blocks the change. Ask, mark unverified, or omit when
proof is incomplete. Keep unrelated pre-existing problems out of change findings.

Assign severity from impact:

- **Blocking:** likely compromise, data loss, outage, or fundamental correctness failure; prevents
  readiness.
- **Important:** reachable regression, contract break, or material operational risk; normally
  prevents readiness.
- **Optional:** worthwhile improvement that does not affect readiness. Keep these few and separate.

A duplication, unearned-abstraction, or unused-capability finding is Optional unless it breaks a rule
the repository states or carries a defect you can reach. Depth findings do not decide readiness alone.

When permitted, run the smallest prescribed check that tests a material concern. Do not change code
during review-only work. Record commands, discovered counts, skips, and failures; separate observation
from inference. One green suite is never exhaustive.

## Report a defensible decision

Put findings first, ordered by severity and impact:

```text
[severity] Concise title — path/to/file:line
Trigger: <input, state, or sequence>
Impact: <observed behavior and consequence>
Evidence: <trace, check, and missing safeguard>
Direction: <small correction, without redesigning the change>
```

Then, whatever you found, list the outputs the change alters with where each is written and what
reads it. `None` is an answer; an unexamined consumer is not, and it blocks a ready verdict. Add
decision-relevant assumptions, questions, checks not run, and exclusions. End with one verdict:

- **Ready:** no material finding blocks the fully stated scope.
- **Changes requested:** name the findings that prevent readiness.
- **Cannot conclude:** name the missing context or excluded risk that prevents a defensible verdict.

If there are no findings, say `No material findings` and name any material area not validated. This
means no demonstrated defect was found in scope; it does not prove correctness.

## Choose the pass the change earns

Run the workflow above on every change. Read a reference beyond it only when the scope turns up one
of these, or the requester named that area:

| What the scope turns up | Read |
|---|---|
| A second place holding a rule an existing place already holds | [duplication-and-simplicity.md](references/duplication-and-simplicity.md) |
| A new interface, layer, factory, generic, flag, option, or hook | [duplication-and-simplicity.md](references/duplication-and-simplicity.md) |
| A parameter, option, field, or entry point the change adds that nothing in the change or the tree uses | [duplication-and-simplicity.md](references/duplication-and-simplicity.md) |
| Rules the repository states for itself — a guide, a contributing file, a committed linter configuration | [quality-and-conventions.md](references/quality-and-conventions.md) |
| A unit a reader cannot follow quickly, or a name that hides what it holds | [quality-and-conventions.md](references/quality-and-conventions.md) |
| Behavior it introduces or alters, and the checks that claim to prove it | [test-adequacy.md](references/test-adequacy.md) |
| Stored data, a migration, or a published contract | [compatibility-and-migrations.md](references/compatibility-and-migrations.md) |

No row triggered is an answer, not a reason to look harder: that change is reviewed by the workflow
above and nothing else. A row is decided from what you can see before judging, not from the finding
you are about to write — a trigger you can only confirm by having already reached the conclusion
never fires in time to help. A pass the requester asked for by name runs whether or not a row triggers it.

A pass can be run over the same scope by a subagent where your tooling provides one. Brief it with
the scope, the pass's question, and the bar its reference states, then confirm what it returns
against the code yourself before any of it becomes a finding.
