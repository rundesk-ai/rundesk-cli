# Sources

Checked 2026-09-02. Official documentation establishes the GitHub and GitHub CLI contracts below;
independent practitioner guidance supports issue and change-description quality. Catalog conclusions
are labeled separately.

## Repository templates and security routes

- GitHub's [Configuring issue templates for your repository](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository)
  documents Markdown templates, YAML issue forms, `.github/ISSUE_TEMPLATE/config.yml`, and the
  default-branch requirement. This supports inspecting the target repository's current templates
  before a fallback.
- GitHub's [Creating a pull request template for your repository](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository)
  documents supported template locations and the information maintainers can request.
- GitHub's [About repository security advisories](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/about-repository-security-advisories)
  documents private collaboration for repository vulnerabilities. This supports routing a potential
  vulnerability away from a public issue.

## Issues and pull requests

- The current [`gh issue create` reference](https://cli.github.com/manual/gh_issue_create) documents
  body files, templates, labels, and issue types. A compatibility check with GitHub CLI 2.83.1 on
  2026-08-23 found body/template/label support but no `--type` flag, while the current manual includes
  it. This observed version gap supports checking the installed command surface before requiring an
  issue type.
- The current [`gh issue comment` reference](https://cli.github.com/manual/gh_issue_comment) and
  [`gh issue close` reference](https://cli.github.com/manual/gh_issue_close) document body files,
  closure reasons, and duplicate selection. A compatibility check with GitHub CLI 2.83.1 on
  2026-08-23 found comment body files and close reasons but no `--duplicate-of` flag. This supports
  treating each action as an authorized mutation, checking the installed surface, and using a
  canonical-link comment plus `not planned` only when direct duplicate selection is unavailable.
- The current [`gh pr create` reference](https://cli.github.com/manual/gh_pr_create) documents
  explicit base and head selection, body files, drafts, user-qualified fork heads, the lack of
  organization-qualified fork heads, and default-branch closing keywords.
- The current [`gh pr merge` reference](https://cli.github.com/manual/gh_pr_merge) documents explicit
  merge methods, merge-queue behavior, and `--match-head-commit`. GitHub CLI 2.95.0 was also observed
  locally on 2026-09-02 to expose that head guard. This supports refusing a merge when the reviewed
  head moved instead of silently merging different content.
- The current [`gh pr review` reference](https://cli.github.com/manual/gh_pr_review) documents comment,
  approve, and request-changes decisions plus review bodies read from files. The current
  [`gh pr view` reference](https://cli.github.com/manual/gh_pr_view) documents hosted review,
  review-decision, check-rollup, merge-state, merge-time, base, and exact head fields. Together they
  support explicit review-effect selection, stored-state readback, and exact merged-head proof.
- GitHub's [About pull request reviews](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/about-pull-request-reviews)
  distinguishes comments, approvals, and requests for changes and notes that later code-modifying
  commits can invalidate approvals under repository policy. This supports tying a technical review
  and submitted decision to the inspected head rather than treating a prior review as permanently
  current.
- GitHub's [Linking a pull request to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)
  documents closing keywords and the requirement that the pull request target the default branch for
  automatic closure.
- Benjamin C. Haller's peer-reviewed practitioner article,
  [Ten simple rules for reporting a bug](https://pmc.ncbi.nlm.nih.gov/articles/PMC9562159/), draws on
  long software-development experience and recommends the correct reporting channel and template, a
  minimal reproducible example, expected behavior, relevant environment and output, and concise
  presentation. It is practitioner guidance, not a controlled comparison.
- Google's [Writing good CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html)
  says a change description should explain what changed and why, preserve decisions the code cannot
  show, disclose shortcomings, and remain useful as history. This package applies that judgment to a
  concise pull-request merge case rather than claiming Google's exact format is universal.

## Releases and versions

- The current [`gh release create` reference](https://cli.github.com/manual/gh_release_create)
  documents draft creation, existing-tag verification, generated notes, comparison start tags,
  prereleases, titles, and the no-new-commits guard.
- The current [`gh release verify` reference](https://cli.github.com/manual/gh_release_verify) and
  [`gh release verify-asset` reference](https://cli.github.com/manual/gh_release_verify-asset)
  define attestation and asset-digest verification. They support the explicit warning that these
  commands do not prove unrelated release state or deployment outcomes.
- GitHub's [Immutable releases](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/immutable-releases)
  documents protection for published release tags and assets while drafts remain mutable. This
  supports staging and inspecting a draft before publication, not rewriting a published tag.
- [Semantic Versioning 2.0.0](https://semver.org/) defines major, minor, patch, and prerelease
  semantics for projects that adopt SemVer. This package uses it only as a fallback when the target
  repository has no version policy or established scheme.

## Branch direction and protected delivery

- GitHub's [Creating a pull request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request)
  establishes that changes from the head are proposed into an explicit base branch.
- GitHub's [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
  documents required pull requests, reviews, status checks, and other merge gates. This supports
  routing production reconciliation through repository policy rather than bypassing it.
- Git's [`git worktree` reference](https://git-scm.com/docs/git-worktree.html) establishes that a
  repository has one main worktree and optional linked worktrees, that completed linked worktrees
  should be removed with `git worktree remove`, and that removal refuses an unclean worktree unless
  forced.
- Git's [`git branch` reference](https://git-scm.com/docs/git-branch) establishes that `-d` requires
  merged ancestry while `-D` forces deletion regardless of ancestry. This package permits `-D` only
  after the stored merged pull request and exact head OID independently prove a disposable
  squash-merged head.

## Catalog conclusions

- Applicable repository templates precede bundled fallbacks. The sources establish template
  locations and purpose; the precedence and line-by-line compliance check are safety conclusions for
  operating consistently across repositories.
- User attestations remain unchecked until the user confirms them. A request to file is authority to
  file, not evidence that every policy or agreement statement is true.
- GitHub delivery stays with the agent responsible for the outcome. This prevents account,
  repository, authority, evidence, and follow-up context from fragmenting across a mutation boundary;
  it is an accountability design decision rather than a GitHub platform rule.
- An already-ready pull request takes a direct merge-and-release path while its recorded head OID
  remains unchanged. This reuses exact-head evidence and removes duplicate planning, delegation,
  validation, and review; it does not remove repository-required merge, default-branch, release,
  deployment, or reconciliation gates. This is an owner operating requirement recorded on
  2026-09-02, not a GitHub platform rule.
- Live deployment-branch reconciliation is conditional on the repository's documented deployment
  model. GitHub sources establish base/head direction and protected delivery, but no universal branch
  name or automatic back-merge policy.
- Post-merge cleanup is part of completing a merged feature or fix: remove its disposable local
  branch, remote branch, and linked worktree, while preserving default, production, release, and
  shared development branches and stopping on ambiguity or uncommitted work. This is an owner
  operating requirement recorded on 2026-08-23, not a universal GitHub platform rule.
