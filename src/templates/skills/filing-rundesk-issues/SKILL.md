---
name: filing-rundesk-issues
description: Apply Rundesk-specific ownership, evidence, privacy, issue-type, label, and identity rules when filing or correcting an issue in rundesk-ai/rundesk-cli. Use whenever a rundesk command behaves wrongly, crashes, reports something untrue, conflicts with its help, or lacks a needed capability; whenever someone asks to file Rundesk work; and alongside filing-github-issues for every Rundesk issue.
---

# Filing an issue against Rundesk

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

Read and follow `filing-github-issues` for the shared workflow: repository discovery, duplicate
search, evidence structure, public-data redaction, templates, filing, and verification. This
page contains only the additions for **`rundesk-ai/rundesk-cli`**, a public repository.

## Prove Rundesk owns it

Before classifying a defect, check:

```sh
rundesk <verb> --help
rundesk version
rundesk update --check
rundesk doctor <agent>
```

- A mistyped command, missing credential, provider login, or invalid agent configuration is not
  a Rundesk defect. `doctor` names those conditions.
- A stack trace may place the fault in a provider, channel adapter, skill, or dependency. File it
  where the responsible code lives.
- A source trace is a hypothesis until a real probe or the repository's test harness reproduces
  it. If reproduction would be destructive or require unavailable infrastructure, say so.
- Behavior guaranteed by a ratified `.knowledge/prd/` requirement is not a bug for differing
  from an expectation. A request to change that contract is a Feature.

Rundesk defects are crashes, data loss, behavior contradicting `CLI.md` or generated `--help`,
and commands that report a success they did not earn. A missing capability is a Feature; agreed
maintenance to working behavior, shipped skills, or agent guidance is a Task.

## Use Rundesk's taxonomy

Set exactly one existing issue type:

- `Bug` — broken or untrue documented behavior.
- `Feature` — a capability Rundesk does not have.
- `Task` — scoped maintenance, refactoring, or shipped guidance that is not a defect.

Labels are facets, never duplicate types:

- `skills` — agent guidance under `src/templates/skills/`.
- `documentation` — human-facing material.
- `epic` — work that needs decomposition before implementation.
- `priority: critical|high|medium|low` — impact and urgency, not confidence or effort.

There is deliberately no `bug` or `enhancement` label. Confirm the live labels before using one.
Title the issue `<area>: <specific outcome or failure>`; the area is `doctor`, `schedules`,
`discord`, `skills`, or another Rundesk component, not the issue type.

## Protect the owner's private data

In addition to the generic public redaction rules, never publish:

- `rundesk messages` output, turn transcripts, prompts, or channel history;
- whole `rundesk logs` output, which may contain conversation text and credentials;
- absolute paths below an agent home, which expose the owner's username.

`rundesk doctor` is useful evidence but prints paths. Replace the home prefix with `<agent home>`.
Describe the shape of private input; never paste the input itself.

## Finish the Rundesk issue

Add acceptance criteria that distinguish complete from incomplete. End the body, after a blank
line, with exactly one filing identity:

```md
🤖 by <Agent>
```

Use the agent's display name. Do not add provider, model, tool, session, generated-by, or model
co-author branding. File with `--repo rundesk-ai/rundesk-cli`, verify the stored type and labels,
and give the owner the issue URL.

When a pull request completes the issue, its body carries one `Closes #<n>` line per issue and
the author verifies GitHub's `closingIssuesReferences` before merge.
