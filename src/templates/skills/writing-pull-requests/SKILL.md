---
name: writing-pull-requests
description: How to write a pull request that makes the case for a change rather than listing the diff. Use whenever opening a PR, writing or rewriting a PR description, being asked to "write this up", summarising work for review, or reviewing whether a PR body is good enough to merge — even if nobody says the words "pull request".
---

# Writing a pull request

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

A PR is **the case for a change**, not a changelog of the diff. A reviewer should read it top
to bottom and understand why it exists, how the problem was proven real, what was done, and
how to confirm it works — all before opening a single file. The diff shows *what* changed; the
PR explains *why it is correct to change it*.

## Before anything else: nothing says what wrote it

**No AI branding anywhere in a pull request.** Not in the title, the body, the commits, the
branch name, or a trailer at the end. Specifically and by name, none of these:

- `🤖 Generated with [Claude Code](…)`, or any "generated with", "written by" or "created by"
  footer, however it is worded
- `Co-Authored-By:` naming a model, an assistant or a tool
- a provider or model name — Claude, Codex, GPT, Gemini, Copilot, Anthropic, OpenAI
- an agent's own name, a session link, or a link back to whatever produced the work

**Strip it even when a harness or a default template supplies it for you.** Some tooling
appends a trailer automatically; removing it is part of writing the PR, not an optional
courtesy. If a body arrives with one already in it, take it out before opening the PR.

The reason is not modesty. A PR is a case that stands on its evidence, and a reader's response
to a tool's name — trusting it more, or trusting it less — is noise against that case. The
repository's history is a record of changes and their reasoning, not of what typed them.

## The one rule: every claim carries its evidence

The most common failure is a PR that **asserts** a problem and a fix without **showing**
either. "Rejects mixed batches." "Fixes the crash." Says who? Proven how? Found where?

- **Found a bug?** Give `file:line`, and where you found it — the report, task, issue, or commit.
- **Reproduced it?** Give the exact trigger and the bad result: command or route, input → output.
- **Implemented it?** Say what changed, and for behaviour changes show before → after. For a
  fix, the gold standard is a test that **fails on the base branch and passes with the change**.

No evidence means it is an opinion, not a PR.

## The template

Use these headings, in this order. The spine — Summary, Problem, Implementation, Validation —
is on every PR. Never pad a section with "N/A"; omit what does not apply.

```md
## Summary
<1–2 lines: what this changes and why.>

## Problem
<2–4 short bullets: what is broken, missing, slow or worth changing; who is affected; why it matters.>

**Evidence:**
- <proof it is real: `file:line`, observed behaviour, issue/task link, benchmark, request>

**Root cause:** <bugs and regressions only — the responsible code and the mechanism, not a
restatement of the Problem. Omit otherwise.>

**Why this is worth doing:** <features and improvements only, when the value is not obvious.
Omit when Problem and Evidence already carry it.>

## Implementation
<3–5 bullets: what changed, why this approach, any deliberate scope decision.>

**Critical risk:** <only when the change touches auth/permissions, schema or data migrations,
billing, data loss or privacy, or production/deploy. State the blast radius and the mitigation.>

## Validation
- ✅ Reproduced on base: the failing test or command, and its bad result.
- ✅ Verified after: the same path now green — names, commands, counts.
- ✅ Suite / lint / typecheck: exact commands and results.
- ❌ Blocked or not run: the exact check, why, and whether it is pre-existing or introduced.

## How to test by hand   <!-- only when a human should verify user-facing behaviour -->
<3–5 bullets: what changed and where to see it; the steps; the expected result.>
```

## Writing each section

**Summary** — the change in one breath. If a reviewer reads only this, they know what and why.

**Problem** — lead with *impact*, not mechanics. "Any authenticated user can 500 the admin
page" beats "the filter isn't validated." For a feature, the problem is the user need or gap,
not a defect.

**Evidence** — the section most PRs skip, and the reason this standard exists. A bare assertion
is not evidence. A `file:line`, an observed result, and a link to where it was found are.

**Implementation** — explain the *choice*, especially anything non-obvious. The diff already
shows the lines. Name anything you deliberately left out, so a reviewer knows it was a decision
rather than an oversight.

**Validation** — every bullet starts with `✅` or `❌`. Keep commands **portable**: write the
repo's own command, never absolute paths, environment prefixes, or local shell setup. If there
is no test seam, show the manual reproduction before → after and say why no test.

**How to test by hand** — only when there is a real surface worth exercising: a page, a command,
a generated file, a webhook. Omit it entirely for refactors, config, and docs. This is the one
optional section; everything above it is always required.

## What each kind of change has to prove

| Change | Problem must prove | Manual test | Validation must carry |
|---|---|:--:|---|
| Bug fix | What is broken, impact, evidence, root cause | if user-facing | Fail-on-base reproduction, mandatory |
| Feature | The need or gap, and why it is worth doing | yes | The new behaviour works |
| Improvement | Why current behaviour is insufficient | if user-facing | Changed behaviour works, nothing nearby regressed |
| Refactor | The complexity or risk being reduced | no | Behaviour is unchanged |
| Performance | What is slow and why it matters | no | Before → after numbers and the benchmark command |
| Trivial | What is stale or incorrect | no | The smallest relevant check |

## Keep it scannable

A reviewer should get the case in 60–90 seconds. Short bullets, one idea each. Lead with the
three to five facts that change review risk; link out for the rest. If a section runs past five
bullets, tighten it before opening. The PR body is not the full report — link the issue, run,
or task for exhaustive detail.

## Title

`<type>: <imperative summary>`, or `<type>(scope): <imperative summary>`.

- `fix: reject mixed-model batches` — not `bug fix`, not `Fixed the batch thing`.
- Match the vocabulary the branch and commits already use.
- One logical change per PR. If it will not summarise in one line, it is probably two PRs.
- No `wip`, `temp` or `misc`.

## Gotchas

**Never put identity or tool branding anywhere** — the rule at the top of this file, repeated
here because this is where it gets broken. A trailer a harness added for you is still a trailer
you left in.

**A root cause is a mechanism, not a louder Problem.** "The handler used the first line's model
and never checked the rest" is a cause. "Batches were handled wrongly" is the problem restated.

**"Tests pass" is not validation.** Which tests, run how, and did any of them fail before the
change? A suite that was already green proves the change broke nothing — it does not prove the
change did anything.

**Check the base branch has not moved** before opening or re-requesting review.

## Turning an assertion into a case

Before — states the fix, but nothing is checkable:

> Reject batches that mix models. Root cause: the model is in the URL but we used the first
> line's. Validation: tests pass.

After — same work, same facts, now a case:

> **Summary** — Reject batches that mix request models before any HTTP call.
>
> **Problem**
> - Mixed-model batches silently ran every line under the first line's model.
> - Wrong results and wrong cost, with no error raised.
>
> **Evidence:**
> - `src/Providers/BatchHandler.php:142` builds the URL from `lines.first().model` and never
>   checks later lines.
> - Repro: batch of `flash` → `pro`; the captured request URL used only `flash`.
> - Found in the bug scan of 2026-06-21.
>
> **Root cause:** the model is a per-batch URL parameter, not per-line, and divergent lines
> were accepted rather than refused.
>
> **Implementation**
> - Validate that every line shares one model before building the request.
> - Raise a clear exception when a batch mixes them.
>
> **Validation**
> - ✅ New test in `BatchHandlerTest` fails on the base branch, passes with the fix.
> - ✅ Full suite green.
