# GitHub issues

## Discover the issue contract

Confirm issues are enabled and find the default branch:

```sh
gh repo view <owner/repo> --json hasIssuesEnabled,defaultBranchRef
```

If issues are disabled, use the repository's documented support or discussion route when authorized,
or return a draft. Read applicable repository instructions, `CONTRIBUTING.md`, `SECURITY.md`, and
every matching Markdown template or YAML issue form from the default branch.

Preserve the selected template's required fields, order, checkboxes, and footer. Remove comments and
placeholders. Agreement, policy, search, consent, and Code of Conduct checkboxes are user
attestations: do not mark one complete merely because the user asked to file an issue. Require the
user's actual confirmation.

Inspect existing labels and issue types before naming them:

```sh
gh label list --repo <owner/repo> --limit 100
gh api -H 'X-GitHub-Api-Version: 2026-03-10' \
  repos/<owner>/<repo>/issue-types --jq '.[].name'
```

Do not invent a label or type. A 404 may mean issue types are unavailable for that repository;
authentication and permission failures remain blockers.

Issue-type flags vary across GitHub CLI versions. Check the installed surface before relying on one:

```sh
gh issue create --help | grep -- '--type'
```

If the selected type is required but the installed CLI cannot set it, stop with the complete draft
and the required CLI upgrade or supported repository route. Do not file a knowingly incomplete issue.

## Route and investigate

Confirm the behavior belongs to the target repository rather than a dependency, integration,
configuration, or caller. Separate observed behavior, expected behavior, and inferred mechanism. A
source trace is evidence, not a reproduction.

Credentials, exploitable paths, and potential vulnerabilities belong in the repository's
`SECURITY.md` route or private vulnerability reporting, never a public issue.

Search open and closed issues using the symptom, exact error, component, and a plain-language
variant:

```sh
gh issue list --repo <owner/repo> --state all \
  --search '<distinctive terms>' --limit 100
```

Read plausible matches. When one covers the same underlying problem, add only genuinely new evidence
when authorized. A closed issue can still be the duplicate.

## Write a checkable issue

Keep one independently closable problem per issue. Lead with observable impact, not a preferred
implementation. Use the repository template when one applies. Otherwise select a form from
[the fallback templates](issue-templates.md).

Ensure the final body answers:

- **Problem:** What observable behavior or limitation exists, who or what does it affect, and why is
  it worth changing?
- **Evidence:** What reproduction, sanitized output, source location, measurement, or published
  contract supports the claim? Which statements remain inference?
- **Expected outcome:** What observable result should replace the current state without prescribing
  an unapproved implementation?
- **Acceptance:** Which independently checkable outcomes distinguish complete from incomplete?
- **Verification:** For a proposal, which automated evidence and representative path will prove the
  acceptance criteria?

Remove chronology, advocacy, repeated request text, speculative causes, and generic headings that do
not help reproduce, decide, or accept the work. Put optional design ideas under a clearly labeled
possible approach so the issue survives a different implementation.

## Apply and verify

Write the final body to a Markdown file so shell quoting cannot change it:

```sh
gh issue create --repo <owner/repo> \
  --title '<concise, specific title>' \
  --body-file <issue-body.md> \
  [--type '<existing type>'] \
  [--label '<existing label>']
```

For edits, inspect the current issue and change only requested fields with `gh issue edit`. Then read
the stored result. For an authorized comment, use a body file or standard input rather than inline
shell text:

```sh
gh issue comment <number> --repo <owner/repo> --body-file <comment.md>
```

Close or reopen an issue only when the current decision authorizes that state change. Use the
repository's established reason and explain a duplicate with its canonical issue:

```sh
gh issue close <number> --repo <owner/repo> --reason completed
gh issue reopen <number> --repo <owner/repo>
```

Current GitHub CLI releases can mark a duplicate directly, but older releases cannot. Detect the
installed surface:

```sh
gh issue close --help | grep -- '--duplicate-of'
```

When supported, use `gh issue close <number> --duplicate-of <canonical-number>`. Otherwise, add an
authorized comment linking the canonical issue, then close with `--reason 'not planned'`. Never call
an issue a duplicate without identifying and reading the canonical report.

Read the stored result after any creation, edit, comment, close, or reopen:

```sh
gh issue view <number> --repo <owner/repo> \
  --json url,title,body,labels,issueType,state
```

Verify the target repository, title, body, labels, type, state, template compliance, privacy, and
URL. For a comment, read the issue comments and compare the stored author and body. Distinguish a
draft from a filed, edited, commented, closed, or reopened issue.
