# GitHub pull requests

## Discover the pull-request contract

Read applicable repository instructions, `CONTRIBUTING.md`, pull-request templates, and workflows
that define required checks. Inspect templates on the default branch and preserve the matching
template's headings, order, questions, checklists, and footer. Remove comments and placeholders;
support each checked claim with evidence from the exact head.

Map the target repository and branch destination to explicit remotes:

```sh
git remote get-url <base-remote>
git remote get-url <push-remote>
```

Resolve the base from repository rules or the default branch. Confirm the current branch is not the
base or an unrelated worktree. If the worktree is dirty, determine which changes belong to the
request before proceeding. Never hide, discard, or rewrite changes to make a branch appear ready.

Check for an existing pull request from the same branch and owner:

```sh
gh pr list --repo <owner/repo> --state all --head <branch> \
  --json number,state,url,title,headRepositoryOwner
```

`--head` takes the branch name in this listing. Inspect `headRepositoryOwner` before deciding whether
to update an existing pull request or open another.

## Inspect the review range

Fetch the selected base and inspect the merge-base range reviewers will receive:

```sh
git fetch <base-remote> <base>
git log --oneline <base-remote>/<base>..HEAD
git diff --stat <base-remote>/<base>...HEAD
git diff --check <base-remote>/<base>...HEAD
git diff <base-remote>/<base>...HEAD
```

Confirm one coherent outcome, no credentials or generated clutter, no unrelated edits, and no
unexplained change outside the accepted boundary. Run repository-required validation. Report only
checks observed for the current head and name each required check that remains unrun.

## Separate review judgment from hosted review state

Use the applicable technical review workflow to inspect the diff for defects, regressions, security,
and maintainability. This GitHub workflow owns the hosted pull-request context around that judgment:
the explicit repository and pull request, base and head, template compliance, requested reviewers,
existing reviews, check state, and any authorized review submission.

Inspect the current hosted state before calling a pull request ready or deciding what kind of review
is appropriate:

```sh
gh pr view <number> --repo <owner/repo> \
  --json url,title,body,baseRefName,headRefName,headRefOid,isDraft,reviewDecision,reviewRequests,reviews,statusCheckRollup
gh pr checks <number> --repo <owner/repo>
```

Do not infer code quality from a filled template, green checks, or an existing approval. Conversely,
do not submit a GitHub review merely because a technical reviewer returned findings: confirm the
review applies to the pull request's current head, sanitize the body, and require authority for the
exact `comment`, `approve`, or `request changes` effect.

Record the current `headRefOid`, submit a prepared review body from a file, and select exactly one
decision:

```sh
gh pr review <number> --repo <owner/repo> --comment --body-file <review.md>
gh pr review <number> --repo <owner/repo> --approve --body-file <review.md>
gh pr review <number> --repo <owner/repo> --request-changes --body-file <review.md>
```

After submission, read `reviews`, `latestReviews`, `reviewDecision`, and the current head OID back.
Verify the stored author, decision, and body, and confirm the head still equals the recorded OID. If
the head changed, report that the technical judgment may be stale; do not silently resubmit or
change the decision.
Requesting or removing reviewers, dismissing a review, resolving threads, merging, or enabling
auto-merge are separate mutations and require their own authority.

## Write the merge case

A pull-request body is a scan-friendly review map, not an implementation diary, design archive, or
test transcript. Use the repository template when one applies. Otherwise complete the
[fallback pull-request template](pull-request-template.md).

Keep the body proportionate:

- State the current problem and its impact in one or two lines.
- Explain three to six important solution decisions, their rationale, boundaries, and preserved
  behavior. Link deeper artifacts rather than pasting algorithms or chronology.
- Give concise before-and-after evidence when the diff alone cannot establish the result.
- Map acceptance criteria to observable outcomes proven by the exact head.
- Name material compatibility and risk; group exact validation commands with observed results.
- Give the shortest representative manual path, normally no more than five steps.
- Make blockers, unrun checks, and readiness visible.

Delete generic filler, repeated request text, changed-file inventories, and claims such as “works as
expected.” Preserve a repository's required identity block. With none, append:

```md
## Agent

🤖 by <Agent display name>
```

Do not add provider, model, tool, session, vendor link, generated-by footer, or provider-style
co-author attribution. Follow the repository title convention; use an imperative title only when no
convention exists.

Reconcile every issue named by the assignment or pull request before opening, updating, or merging
the pull request:

- If the exact head satisfies the issue's acceptance criteria and targets the default branch, put
  one full closing reference such as `Closes #123` in the body. A bare issue URL, `#123`, `Refs`, or
  `Related` does not close the issue.
- If the pull request is partial, targets a staging base, or leaves any acceptance criterion unmet,
  use `Refs #123` or `Related to #123`. State the unmet outcome in the body and explicitly report
  that the issue will remain open; do not present the issue as completed.
- If the relationship is unclear, read the issue and compare every acceptance criterion with the
  exact head. Do not omit the link or choose a closing keyword from the title alone.

Before an authorized merge, inspect `closingIssuesReferences` and confirm it matches that issue
disposition. After a default-branch merge, read each completed issue back and require `state: CLOSED`;
if GitHub did not close it, report the mismatch and correct it only when issue closure is authorized.

## Open, update, and verify

Recheck repository, base, head, review range, template, validation, and authority immediately before
mutation. Use a body file:

```sh
git push -u <push-remote> <branch>
gh pr create --repo <owner/repo> \
  --base <base> \
  --head <branch> \
  --title '<title>' \
  --body-file <pull-request-body.md> \
  [--draft]
```

For a user-owned fork, qualify the head as `<user>:<branch>`. GitHub CLI does not support an
organization name in that qualified form. Stop rather than opening from a different repository.

For an existing pull request, inspect it before `gh pr edit` and change only requested fields. Do not
add reviewers, assignees, projects, labels, merge queues, or merge settings without specific
authority.

Read the stored pull request and checks:

```sh
gh pr view <number> --repo <owner/repo> \
  --json url,title,body,baseRefName,headRefName,headRefOid,headRepository,headRepositoryOwner,isDraft,closingIssuesReferences,latestReviews,reviewDecision,reviews
gh pr checks <number> --repo <owner/repo>
```

Verify repository, base, head, owner, title, body, template, identity, privacy, draft state, closing
links, and URL. Report pending or failing checks; creation alone is not merge readiness.

## Clean up after merge

Treat cleanup as the final part of an authorized merge. Read the stored pull request again and
require `state: MERGED`, a non-empty `mergedAt`, and its exact `headRefName` and `headRefOid`. This
stored result is the merge proof for squash and rebase merges too; ancestry alone cannot prove
those outcomes.

Delete a branch only when it is the disposable, task-scoped head created for that merged pull
request, such as a feature, fix, documentation, or chore branch. Never delete the default branch,
the pull-request base, a protected branch, a production or deployment branch, a release branch, a
shared development or integration branch, an active or unmerged pull-request head, or any branch
whose purpose or ownership is unclear. A familiar name is not enough to classify a branch as
disposable.

Before deletion, prove the local and remote refs still point at the recorded `headRefOid` and
inspect every worktree holding the branch:

```sh
gh pr view <number> --repo <owner/repo> \
  --json state,mergedAt,baseRefName,headRefName,headRefOid
git worktree list --porcelain
git rev-parse refs/heads/<head>
git ls-remote --heads <push-remote> refs/heads/<head>
```

If either ref moved after merge, stop instead of deleting new work. If the head is checked out in
the main worktree, switch that checkout to the updated base before deleting it. If it has a linked
worktree, require a clean status and remove that exact worktree with `git worktree remove`; never
force-remove an unclean or locked worktree. Then delete the exact local and remote head refs:

```sh
git switch <base>
git merge --ff-only <base-remote>/<base>
git branch -D <head>
git push <push-remote> --delete <head>
```

`-D` is justified here only because the stored merged pull request and exact head OID already prove
the disposable ref is complete; a squash merge is not an ancestor of the updated base. Do not use
`gh pr merge --delete-branch` blindly because it skips this branch-role, ref, and worktree review.

Finally, verify the local listing and remote query return no matching ref. Report preserved
long-lived branches and any cleanup withheld because a guard failed.
