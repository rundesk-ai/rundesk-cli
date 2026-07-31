---
name: writing-github-pull-requests
description: Prepare, open, or improve evidence-rich GitHub pull requests for any repository while following its contribution rules, templates, validation commands, and merge conventions. Use whenever asked to create, submit, draft, edit, or write up a PR; summarize implemented work for review; or judge whether a PR is ready to open.
---

# Writing a GitHub pull request

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version
of your own, copy it under a different name — that copy is yours and is never touched.*

A pull request is the case for merging a change, not a restatement of the diff. The repository
owns that case: read its rules and template before using the fallback here. Opening, editing,
requesting review, or pushing a PR changes external state; do only the actions the owner asked
for.

## Establish the repository contract

From the checkout, confirm the target repository, default branch, and current branch:

```sh
gh repo view --json nameWithOwner,url,defaultBranchRef
git remote -v
git branch --show-current
git status --short --branch
```

Read every applicable `AGENTS.md`, `CONTRIBUTING.md`, pull request template under the root,
`docs/`, or `.github/`, and the workflows that define required checks. Follow repository rules
for titles, issue links, attribution, changelogs, screenshots, test commands, and draft status.
Do not transplant conventions from another repository.

Match the target repository to an explicit `<base-remote>`, and match the branch's destination
repository or fork to an explicit `<push-remote>`. Confirm each with `git remote get-url`; never
assume either is `origin`. Resolve the base deliberately, using the repository default unless
the task or repository says otherwise. Verify that the current branch is neither the base nor
an unrelated worktree.

If the worktree is dirty, stop and resolve whether those changes belong before continuing. A PR
contains commits, not a working tree: never silently omit changes, discard them, or rewrite
history to make the branch look ready.

Check whether the head already has a PR before creating another:

```sh
gh pr list --repo <owner/repo> --state all \
  --head <branch> --json number,state,url,title,headRepositoryOwner
```

`gh pr list --head` accepts only the branch name, not `owner:branch`, so inspect
`headRepositoryOwner` before deciding a result is the same head. Inspect or update the existing
PR when one represents the same branch, owner, and change.

## Inspect exactly what will be reviewed

Fetch the selected base remote, then inspect the PR-shaped range against its remote-tracking
branch:

```sh
git fetch <base-remote> <base>
git log --oneline <base-remote>/<base>..HEAD
git diff --stat <base-remote>/<base>...HEAD
git diff --check <base-remote>/<base>...HEAD
git diff <base-remote>/<base>...HEAD
```

Triple-dot diff uses the merge base and shows the contribution as reviewers will see it.
Confirm that the branch contains one coherent change, no secrets or generated clutter, and no
unrelated edits. Check the base has not moved before opening or re-requesting review.

## Validate fresh

Run the repository's own test, lint, typecheck, build, documentation, and packaging commands in
proportion to the change. Never substitute a familiar toolchain for the repository's commands.

Only cite results observed in the current session. A stale test count is worse than no count
because it looks verified. If a required check cannot run, say exactly which check, why, and
whether the limitation predates the branch. Do not turn an unrun check into a checked box.

For a bug fix, prefer the same focused reproduction before and after: a regression test that
fails on the base and passes on the branch is stronger evidence than a suite that was green in
both places. For performance work, include the command, environment, and before/after numbers.

## Write the case

Use the repository template when one exists. Otherwise keep this spine and omit optional blocks
instead of filling them with `N/A`:

```md
## Summary
<1–2 lines: what changes and why.>

## Problem
- <impact, affected user or system, and why the current state is insufficient>

**Evidence:**
- <issue/task link, observed result, source location, request, or measurement>

**Root cause:** <bugs only: the responsible mechanism, not the problem restated>

## Implementation
- <the important choices, why this approach, and deliberate scope boundaries>

**Critical risk:** <only for auth/permissions, schema or migrations, billing, data loss,
privacy, or deploy changes: blast radius and mitigation>

## Validation
- ✅ <exact command or manual check and fresh result>
- ❌ <required check not run, exact reason, and whether pre-existing>

## How to test by hand
<Only for a user-visible surface: short steps and expected result.>

Closes #<issue-number>.
```

Keep the body scannable. Lead with the few facts that change review risk; link exhaustive logs
or design records instead of pasting them. Explain choices the diff cannot, not every file it
already shows.

Use the repository's title convention. With none, use an imperative summary under roughly 72
characters; use `type(scope): summary` only when the repository uses Conventional Commits.

## Link issues correctly

Use one full closing reference per issue the PR actually completes:

```md
Closes #12.
Closes owner/other-repository#34.
```

A bare `#12` is only a reference. `Closes #12 and #13` closes only the first issue, and GitHub
honors closing keywords automatically only when the PR targets the repository's default branch.
If the PR is partial work or targets a staging branch, use `Refs` or `Related` and state that the
issue remains open.

## Open and verify

Write the reviewed body to a temporary Markdown file. This preserves formatting and keeps
non-interactive commands from opening an editor.

```sh
git push -u <push-remote> <branch>
gh pr create --repo <owner/repo> \
  --base <base> \
  --head <branch> \
  --title '<title>' \
  --body-file <pr-body.md> \
  [--draft]
```

The bare head is for a branch in the target repository. For a user-owned fork, use
`--head <user>:<branch>`. `gh pr create` does not support an organization name in that
qualified head form; if an organization-owned fork is required, stop rather than silently
creating from another repository.

Do not add reviewers, assignees, projects, or merge settings unless the owner or repository
workflow asked for them. After creation, verify GitHub's stored result:

```sh
gh pr view <number> --repo <owner/repo> \
  --json url,title,body,baseRefName,headRefName,headRepository,headRepositoryOwner,isDraft,closingIssuesReferences
gh pr checks <number> --repo <owner/repo>
```

Confirm the base, head branch, head repository owner, rendered body, draft state, linked issues,
and URL. Report the URL plus any pending or failing checks. If `gh` is missing, unauthenticated,
or lacks permission, stop with the title and body ready to paste; do not silently switch
accounts, forks, or hosts.
