---
name: writing-skills
description: Creates, revises, reviews, debugs, or publishes provider-neutral skills for rundesk. Use when asked to capture a repeatable workflow, add or improve a SKILL.md, fix triggering or token use, add scripts, references, assets, or credentials, troubleshoot an unusable skill, or share skills through a catalog — even when the request does not call the result a skill.
---

# Writing skills

Build the smallest skill that changes how an agent performs a repeatable task.

## Choose where it belongs

Put a private skill in the install's `local` catalog. Rundesk has no create verb; make the directory
and `SKILL.md` directly.

Ask rundesk where the library is. Never derive it from `RUNDESK_HOME` or write an absolute path into
the skill. Replace the example name before running this:

```sh
skill_name=release-notes
skill_library=$("$RUNDESK_COMMAND" skills | sed -n '1s/^skills in //p')
test -n "$skill_library" || exit 1
mkdir -p "$skill_library/local/$skill_name"
```

Write `<library printed above>/local/release-notes/SKILL.md`, then grant it. Use `$RUNDESK_AGENT` for
the agent taking this turn, or name another agent when the request does:

```sh
"$RUNDESK_COMMAND" skills grant "$RUNDESK_AGENT" local/release-notes
```

Writing the file only makes it available. Granting makes it discoverable, starting with the agent's
next turn because the current turn's environment is already built.

Read `references/publishing.md` before creating a skill meant for other installs. Published skills
belong in a catalog repository, not in `local`.

## Use only the shape the task needs

```text
<name>/
├── SKILL.md          required: triggering and core procedure
├── rundesk.json      optional: required environment values
├── scripts/          optional: deterministic or repeated commands
├── references/       optional: detail read only in named situations
└── assets/           optional: files copied or used in output
```

Do not create an optional directory until it has content. Do not add a `README.md`, changelog,
installation guide, or an account of how the skill was made.

Read `references/integrations.md` before adding `rundesk.json` or a script that reaches an external
service.

## Write the metadata first

Use only `name` and `description` in the frontmatter.

- Make `name` match its directory. Use at most 64 characters: lowercase letters, digits, and single
  hyphens.
- Make `description` say what the skill does and every real situation that should trigger it.
- Describe user intent, not only words a user might type. Most requests will not say the skill's
  name.
- Keep the description within 1024 characters and as short as complete coverage allows. Every agent
  holding the skill pays for it on every turn.
- Put all trigger guidance in the description. The body is unavailable until after triggering.

```markdown
---
name: release-notes
description: Drafts and reviews release notes for this team. Use when preparing a release, tagging a version, or explaining shipped changes to people who did not build them.
---
```

## Write only what changes behavior

Use imperative steps and lead with the action. Assume the reader can reason, edit files, and use
ordinary tools.

- Keep the core workflow, defaults, and non-obvious gotchas in `SKILL.md`.
- Give one good default. Offer choices only when the task truly requires a decision.
- Use exact commands or scripts for fragile operations; use concise judgment rules where several
  approaches are valid.
- Explain the failure a constraint prevents instead of adding unexplained `ALWAYS` or `NEVER` rules.
- Introduce every reference by when to read it, and link it directly from `SKILL.md`.
- State each fact once. Do not repeat a reference in the body.
- Remove general background, process history, dated claims, and anything already loaded from the
  agent's rules or the repository.

Treat 500 lines as a ceiling, not a target. If the body grows, keep universally needed procedure and
gotchas in it; move conditional detail one level down into a reference.

## Budget the context

| Part | When it costs tokens | Keep there |
|---|---|---|
| `description` | every turn | the shortest complete trigger |
| `SKILL.md` body | when the provider loads it after triggering | core procedure, defaults, gotchas |
| `references/` | only when read | conditional detail and larger examples |
| `scripts/` | output enters context | deterministic work with bounded plain-text output |
| `assets/` | only when used | templates and output material, not instructions |

Prefer a short example over another paragraph. Make scripts emit only what the agent needs next;
verbose JSON and unbounded listings spend the context the script was meant to save.

## Prove it works

Check the skill through the same surface an agent uses:

1. Confirm the directory name, frontmatter name, and description limits agree.
2. Grant the skill if the target agent does not already hold it, then run:

   ```sh
   "$RUNDESK_COMMAND" skills list "$RUNDESK_AGENT"
   "$RUNDESK_COMMAND" skills doctor "$RUNDESK_AGENT"
   ```

3. Run every shipped script with representative input and confirm it is executable.
4. Use a fresh turn to request the outcome without naming the skill. Confirm the description triggers
   it and the instructions change the result.
5. For a substantial skill, compare that result with a fresh baseline that does not hold the skill.
   If the result is materially the same, remove instructions that are not earning their token cost.
