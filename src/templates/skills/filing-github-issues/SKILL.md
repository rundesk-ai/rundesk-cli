---
name: filing-github-issues
description: Create, edit, or triage evidence-rich GitHub issues under each repository's rules. Use for issue drafts or filing, confirmed defects, scoped feature requests, duplicate searches, comments, or private security routing.
---

# Filing a GitHub issue

The repository owns its tracker. Discover and follow its conventions before applying the
fallbacks here. Creating or editing an issue changes an external system: do it when the owner
asked to file or update one; otherwise return a ready-to-file draft.

## Establish the target and its rules

Never infer the repository from a nearby directory or an issue number alone. From a checkout:

```sh
gh repo view --json nameWithOwner,url,hasIssuesEnabled,defaultBranchRef
```

For a repository named by the owner, pass `--repo <owner/repo>` to every `gh` command. If no
target can be established, stop and ask rather than filing in the wrong tracker.
If `hasIssuesEnabled` is false, do not attempt creation; follow the repository's prescribed
support or discussion route when authorized, or return the issue as a draft.

Read the applicable `AGENTS.md`, `CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/`, and
`SECURITY.md`. Inspect every issue template, including YAML issue forms, then select the one
whose stated purpose matches the report. Use the default branch's templates unless the task is
explicitly changing those templates. Repository instructions and templates win over every
fallback below.

Treat the selected template as a body contract:

- preserve its required sections, field order, checkbox wording, and requested footer;
- answer every required prompt with evidence specific to this issue;
- apply only title prefixes, labels, assignees, projects, and issue types the template or
  repository requires;
- remove comments and placeholders, and never mark a claim or check as complete unless proven.

For a YAML issue form, inspect each `body` entry and its `validations.required` value. The
submitted issue body must contain the corresponding rendered headings and answers even when it
is created through `gh` instead of the web form. If any repository template applies, do not use
the fallback merely because it is shorter.
Inspect the labels and issue types before naming either:

```sh
gh label list --repo <owner/repo> --limit 100
gh api -H 'X-GitHub-Api-Version: 2026-03-10' \
  repos/<owner>/<repo>/issue-types --jq '.[].name'
```

Do not invent a label or type. An HTTP 404 means issue types are unavailable for that target;
omit the type unless repository rules require one. Authentication, permission, and other API
failures are blockers rather than proof that no types exist.

## Route before reporting

Confirm that the behavior belongs to this repository rather than a dependency, integration,
configuration, or caller. Separate three kinds of claim:

- **Observed:** what was run or received, with the exact result.
- **Expected:** the documented contract or concrete user need.
- **Inferred:** a source location or likely mechanism that has not itself been executed.

A source trace is useful evidence, but it is not a reproduction. Say when a report is based
only on inspection because running it would be destructive, require unavailable hardware, or
need a real outage.

If the report could expose a vulnerability, credential, or exploitable path, follow
`SECURITY.md` or GitHub's private vulnerability reporting route. Never publish it merely
because ordinary bugs use public issues.

## Search before creating

Search open and closed issues using the symptom, exact error, affected component, and a second
plain-language phrase:

```sh
gh issue list --repo <owner/repo> --state all --search '<distinctive terms>' --limit 100
```

Read plausible matches. If one covers the same underlying problem or request, add only the new
evidence to it when authorized; do not split the history across a duplicate. A closed issue may
identify the fixed version, a rejected proposal, or the condition needed to reopen it.

## Build a checkable case

Keep one issue to one independently closable problem. Lead with impact and current behavior,
not the implementation you expect. Include only sections that add information, and end with
acceptance criteria somebody else can verify.

Use the selected repository template when one applies. Only when none applies, use the closest
fallback.

### Bug

```md
## What happened
<Who is affected, what failed, and the consequence.>

## Reproduce
<Smallest exact setup and commands or actions, in order.>

**Expected:** <the documented or intended result>

**Actual:** <the observed result, trimmed to the failure>

## Environment
- version or commit: <value>
- operating system/runtime: <only what affects the report>

## Evidence
- <fresh reproduction result, source location, regression range, or sanitized log excerpt>

## Acceptance criteria
- [ ] <observable condition that distinguishes fixed from unfixed>
```

### Feature or scoped work

```md
## Need
<Who needs what, and what is impossible or costly today.>

## Evidence
- <concrete example, request, measurement, or current limitation>

## Scope
- <the bounded capability or outcome>

## Out of scope
- <the nearest tempting expansion>

## Acceptance criteria
- [ ] <observable completion condition>
```

For a feature, keep implementation ideas under **Possible approach** and label them as such.
An issue should survive the first design changing.

## Redact for the audience

Assume a public repository is indexed and cached. Read every excerpt before posting it. Remove:

- credentials, cookies, authorization headers, private remote URLs, and partially masked keys;
- private messages, prompts, transcripts, customer data, and whole log files;
- personal names, email addresses, usernames embedded in home paths, and internal hostnames;
- unrelated environment variables or configuration.

Use placeholders such as `<home>`, `<token>`, and `<internal host>`. Quote only the few lines
that prove the claim. When unsure, omit the material and say what was withheld.

## File and verify

Before filing, compare the finished body against the selected template line by line. Confirm
that every required field is present and substantive, the order is intact, no placeholder or
instructional comment remains, and no checkbox overstates the evidence.

Write the body to a temporary Markdown file. `--body-file` preserves Markdown and avoids shell
quoting failures; explicit flags avoid an editor prompt in a non-interactive turn.

```sh
gh issue create --repo <owner/repo> \
  --title '<concise, specific title>' \
  --body-file <issue-body.md> \
  [--type '<existing type>'] \
  [--label '<existing label>']
```

Use the repository's title convention. With none, name the affected component and behavior;
avoid titles such as `bug`, `broken`, or `feature request` that add no identifying detail.

After creation, read GitHub's stored result rather than trusting the command input:

```sh
gh issue view <number> --repo <owner/repo> --json url,title,body,labels,issueType,state
```

Confirm the title, Markdown, labels/type, and URL. Recheck the stored body against the selected
template; creation succeeding does not prove template compliance. Report the URL to the owner.
If `gh` is missing, unauthenticated, or lacks permission, stop with the exact body ready to
paste; do not quietly switch accounts, repositories, or publication routes.
