---
name: managing-github
description: "Use when work reaches a GitHub-hosted issue, pull request or review, release, tag, or live deployment-branch boundary, including indirectly after investigation, completed development, or repository policy requires delivery. Also trigger when work discovers a repository defect that may need duplicate search or an issue even without a filing request; selection does not authorize creation. Covers templates, submission, updates, reviews, and stored-result proof. Never trigger for repository or organization administration such as branch protection, rulesets, settings, permissions, secrets, or webhooks; local implementation or Git; GitHub Actions authoring; or technical code review with no hosted PR operation."
---

# Manage GitHub

Use one safety contract, then load only the operation reference required by the request.

## Keep the ownership boundary explicit

This skill owns externally stored GitHub issues, pull requests, pull-request reviews, releases, and
their readback. It does not own local implementation, development planning, technical code-review
judgment, generic branch maintenance, GitHub Actions design, repository settings, permissions,
rulesets, secrets, or organization administration.

The agent responsible for the overall outcome retains every GitHub mutation. A specialist may return
a local branch, diff, commit, issue draft, pull-request draft, release recommendation, and evidence;
it does not file, edit, push, tag, publish, request review, or follow up unless it is itself the
responsible agent and the request authorizes that exact action.

## Trigger from the workflow, not only the request wording

Load this skill when the active work reaches a GitHub-hosted boundary, including when:

- investigation finds a repository defect that may need an issue, duplicate search, comment, or
  closure decision;
- verified development work is ready for the repository's required branch push or pull-request
  path;
- an existing pull request needs stored-state inspection, template or readiness review, an
  authorized review submission or update, or check follow-up;
- a versioned change reaches the repository's release, tag, notes, asset, or branch-reconciliation
  contract; or
- another in-scope repository workflow requires reading GitHub templates, rules, checks, or the
  authoritative hosted object before proceeding.

Do not load it merely because local code happens to be hosted on GitHub. Stay with the local
development workflow until GitHub state, policy, or delivery affects the next decision.

Triggering this skill does not grant a mutation. If the workflow reveals a useful issue or pull
request that the user did not authorize and repository policy does not require, inspect and prepare
the artifact, then present the delivery decision instead of silently creating it.

## Apply the shared contract

Inspect freely. Create, edit, push, tag, publish, upload, request review, or reconcile a branch only
when the current request or repository policy authorizes that exact effect. An authorization for
implementation is not authorization for GitHub delivery.

Establish the account, repository, default branch, remotes, branch, and worktree:

```sh
gh auth status --active
gh repo view <owner/repo> --json nameWithOwner,url,defaultBranchRef
git remote -v
git branch --show-current
git status --short --branch
```

When the owner names a repository, pass `--repo <owner/repo>` to every repository-scoped `gh`
command that supports it. `gh repo view` instead takes `<owner/repo>` positionally, while
`gh auth status` establishes the active host and account without selecting a repository. Never infer
a target from a nearby directory, a bare issue or pull-request number, or remembered state. Do not
silently switch accounts, hosts, repositories, forks, remotes, base branches, or head branches.

Read the target repository's applicable instructions, contribution and security guides, templates,
and release contract. A matching repository template takes precedence over this package's fallback;
preserve its headings, order, required prompts, attestations, and footer. Keep this package's
evidence, privacy, authorization, and stored-result checks inside that structure.

Before public text leaves the workspace, remove credentials, private URLs, customer data, private
conversations, internal hostnames, personal identifiers, owner-specific paths, and unrelated logs.
Keep only the evidence the public artifact needs.

After every mutation, read the stored object back from GitHub and compare its repository, identity,
content, target, and state with the request. A zero exit status proves command acceptance, not the
intended stored result. If `gh` is missing, unauthenticated, too old for a required operation, or
unauthorized, return the prepared artifact and exact blocker; do not switch tools or accounts
silently.

## Choose the operation

- [Issues](references/issues.md): investigate, triage, draft, file, edit, comment on, close, or verify
  an issue; select a repository template, existing label, and supported issue type; search
  duplicates; route security reports.
- [Pull requests](references/pull-requests.md): inspect the review range, prepare or open a pull
  request, select explicit base and head, apply its template, inspect hosted review state, submit an
  authorized comment, approval, or change request, link issues, and verify stored content and checks.
- [Releases](references/releases.md): discover the repository release contract, choose a compatible
  version and exact tag, prepare or publish a release, verify its target and assets, recover from a
  failed attempt, or reconcile a live deployment branch.

Read multiple operation references only when the request genuinely spans them. Read
[references/sources.md](references/sources.md) when auditing or changing these GitHub workflow rules.
