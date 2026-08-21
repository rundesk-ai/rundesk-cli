---
name: writing-skills
description: Use when creating, modifying, reviewing, debugging, or publishing a Rundesk skill, or when building reusable integrations or workflow scripts that automate repeated agent work. It supplies the artifact boundaries, compact writing method, script and integration guidance, behavior tests, and catalog publishing workflow needed to make the result reliable and discoverable. Do not use it merely to perform a workflow taught by an existing skill or to write one-off project automation.
---

# Writing skills

Build the smallest reusable package that changes how an agent performs a repeatable task.

## Choose the artifact before writing it

Separate the jobs before deciding which files exist:

- A skill is the **instruction boundary**: when to act, which judgments to make, what procedure to
  follow, and how to prove the outcome.
- A workflow script is the **deterministic mechanism** for repeated local transformation,
  validation, or orchestration. It belongs in a skill only when an agent needs the skill's routing
  and instructions to use it correctly.
- An integration adds an **external-service boundary**: credentials, permissions, accounts,
  network failures, or remote side effects.

Keep one-off automation in the owning project. Keep one agent's private, repeatedly useful command
in that agent's established scripts area. Build a skill when future turns need to discover the
capability from a request and apply reusable judgment around it. Do not wrap a script in a skill
merely to store it, or replace deterministic code with prose an agent must reinterpret every time.

Read [Reusable workflow scripts](references/workflow-scripts.md) before adding a local script or
building reusable automation that does not call an external service. Read
[External-service integrations](references/integrations.md) before adding credentials, profiles,
OAuth, network access, or remote side effects.

## Choose where it belongs

Put a private skill in the install's `local` catalog. Rundesk has no create verb; make the directory
and `SKILL.md` directly.

Use the live library path only when the request authorizes creating or installing the private skill
there. For a draft, review, repository change, or isolated test, stay in the named workspace or
temporary directory and do not inspect or change the live library merely to check where the final
skill could go.

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

Read [Publishing a skill catalog](references/publishing.md) before creating a skill meant for other
installs. Published skills belong in a catalog repository, not in `local`.

## Use only the shape the task needs

```text
<name>/
├── SKILL.md          required: triggering and core procedure
├── rundesk.json      optional: required environment values
├── scripts/          optional: deterministic or repeated commands
├── tests/            optional: script contracts when no catalog test area owns them
├── references/       optional: detail read only in named situations
└── assets/           optional: files copied or used in output
```

Do not create an optional directory until it has content. Do not add a `README.md`, changelog,
installation guide, or an account of how the skill was made.

## Write the routing description first

Use only `name` and `description` in the frontmatter.

- Make `name` match its directory. Use at most 64 characters: lowercase letters, digits, and single
  hyphens.
- Treat `description` as the routing instruction. State applicability directly with `Use when`,
  `Apply when`, or equivalent imperative wording, then name the user goals and situations that
  require it, including indirect requests that may not name the skill. The exact phrase is not a
  trigger; the intent and boundary are.
- Follow with one short sentence stating the specialized workflow or knowledge the skill supplies.
  Describe the user's intent, not the skill's files or implementation.
- Add `Do not use` only to separate a likely near-miss from the skill's scope.
- Keep the description within 1024 characters and as short as complete coverage allows. Every agent
  holding the skill pays for it on every turn.
- Put all trigger guidance in the description. The body is unavailable until after triggering.

```markdown
---
name: release-notes
description: Use this skill when the user asks to prepare a release, tag a version, summarize shipped changes, or explain those changes to people who did not build them. It supplies a workflow for turning repository history into accurate, audience-focused release notes. Do not use it for unreleased implementation plans or general code summaries.
---
```

## Write only what changes behavior

Use imperative steps and lead with the action. Assume the reader can reason, edit files, and use
ordinary tools. Keep a sentence only when it changes execution, prevents a likely failure, or routes
the reader to conditional detail. Delete it otherwise.

- Keep the core workflow, defaults, and non-obvious gotchas in `SKILL.md`.
- Give one good default. Offer choices only when the task truly requires a decision.
- Use exact commands or scripts for fragile operations; use concise judgment rules where several
  approaches are valid.
- Explain the failure a constraint prevents instead of adding unexplained `ALWAYS` or `NEVER` rules.
- Introduce every reference by when to read it, and link it directly from `SKILL.md`.
- Keep one source of truth for each instruction. Link to it from anywhere else that needs it; never
  restate it in `SKILL.md`, another reference, or a consuming skill.
- Remove general background, process history, dated claims, and anything already loaded from the
  agent's rules or the repository.
- Record the source for a technical constraint in the repository or a focused source reference.
  Distinguish observed contracts from the skill author's recommended default.
- Teach known traps as symptom, cause, preferred replacement, and observable proof. Do not invent a
  caution or example merely to make the guidance look complete.

Treat 500 lines as a ceiling, not a target. If the body grows, keep universally needed procedure and
gotchas in it; move conditional detail one level down into a reference.

## Budget the context

| Part | When it costs tokens | Keep there |
|---|---|---|
| `description` | every turn | the shortest complete trigger |
| `SKILL.md` body | when the provider loads it after triggering | core procedure, defaults, gotchas |
| `references/` | only when read | conditional detail and larger examples |
| `scripts/` | output enters context | deterministic work with bounded plain-text output |
| `tests/` | only during validation | executable contracts for shipped commands and edge cases |
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

3. Run every shipped script with representative input and its documented edge cases. Use the
   applicable workflow-script or integration reference for the complete matrix.
4. In different fresh turns, try a direct request, an indirect request that implies the capability,
   and a close near-miss that shares the description's terms but is out of scope. Confirm the body
   and required references load before work begins. Tighten missed scope or false matches by
   category, not by copying individual prompt phrases into the description.
5. For a substantial skill, run the same realistic task in a fresh baseline without the skill.
   Compare routing, decisions, failure handling, output, and proof. If the skilled result is not
   materially better, remove instructions that are not earning their token cost or reconsider
   whether the capability needs a skill.
6. Have a separate test agent use the skill without being told the expected implementation. Review
   the created artifact and observed commands directly; the agent's summary is not proof.
7. Review the generated writing separately from executable correctness. Check routing precision,
   execution order, non-obvious judgment, concision, duplication, and reference discipline. Green
   script tests do not prove that another agent will understand or use the skill well. Trace each
   factual promise and example to an observed behavior or a cited source; test an executable claim
   directly, and narrow wording that is true only for some inputs or tools. Challenge semantic
   claims with an adversarial counterexample that preserves convenient aggregates while changing
   the relationship or outcome the user actually cares about; mutation checks cannot repair a
   wrong test oracle. Review the whole interface, including empty success, duplicate evidence, and
   every data-dependent output section, rather than proving only the main listing.
