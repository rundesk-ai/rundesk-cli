---
name: writing-skills
description: Use when creating, modifying, reviewing, testing, or publishing a Rundesk skill, including reusable workflow scripts and external integrations. It supplies compact authoring, behavioral verification, and catalog publication. Do not use it to perform an existing skill's workflow or write one-off project automation.
---

# Writing skills

## Choose the artifact

- A skill is the **instruction boundary**: when to act, what judgment to apply, which procedure to
  follow, and how to prove the outcome.
- A workflow script is the **deterministic mechanism** for repeated local transformation,
  validation, or orchestration.
- An integration adds an **external-service boundary**: credentials, accounts, network failures,
  permissions, or remote effects.

Keep one-off automation in its project and one agent's private repeated command in that agent's
scripts area. Package a script in a skill only when future turns need routing or judgment to use it.
Do not replace deterministic code with prose an agent must reinterpret.

Read [Reusable workflow scripts](references/workflow-scripts.md) before shipping any reusable
script. Also read [External-service integrations](references/integrations.md) when it uses
credentials, profiles, OAuth, a network, or remote effects.

## Place it safely

Create a private skill in `local` only when live creation or installation is authorized. For a
draft, review, repository change, or isolated test, stay in the named workspace or temporary
directory; do not inspect or change the live library to discover where the result might later go.

For an authorized private skill, ask Rundesk for the library instead of deriving it from
`RUNDESK_HOME` or embedding an absolute path. Replace the example name:

```sh
skill_name=release-notes
skill_library=$("$RUNDESK_COMMAND" skills | sed -n '1s/^skills in //p')
test -n "$skill_library" || exit 1
mkdir -p "$skill_library/local/$skill_name"
```

Write `<library>/local/<name>/SKILL.md`, then grant it to the named agent:

```sh
"$RUNDESK_COMMAND" skills grant "$RUNDESK_AGENT" local/release-notes
```

The grant becomes discoverable on the agent's next turn, not the current one. Read
[Publishing a skill catalog](references/publishing.md) before creating a skill for other installs;
published skills belong in a catalog repository, not `local`.

## Use only the needed shape

```text
<name>/
├── SKILL.md          required: routing and core procedure
├── rundesk.json      optional: required environment values
├── scripts/          optional: reusable commands
├── tests/            optional: script contracts when no catalog test area owns them
├── references/       optional: conditionally loaded detail
└── assets/           optional: copied or output material
```

Create optional paths only with content. Omit README, changelog, installation guide, and creation
history.

## Write routing first

Frontmatter has only `name` and `description`.

- Match `name` to the directory. Use at most 64 lowercase letters, digits, and single hyphens.
- Route by user intent, including indirect requests that may not name the skill. Start with `Use
  when`, `Apply when`, or equivalent applicability language; prompt phrases are not triggers.
- Aim for two short sentences: applicability, then the specialized workflow or knowledge supplied.
  Add `Do not use` only for a likely near-miss. Include only concepts needed to route before the
  body loads. Omit steps, tests, benefit claims, and implementation detail; name a file type, tool,
  or format only when it determines whether the skill should trigger.
- Use the shortest description that still routes correctly; 1,024 characters is a ceiling, not a
  target. Put every trigger there because each holder pays for it every turn and the body is
  unavailable until routing succeeds.

```yaml
# Bad: embeds implementation and verification that cannot help routing.
description: Use when creating release notes. It reads Git history, writes Markdown, groups commits, checks links, runs validation, and produces concise internal and public versions with accurate formatting.

# Good: states intent, supplied judgment, and the closest boundary only.
description: Use when preparing release notes from shipped repository changes. It supplies an audience-focused workflow grounded in verified history. Do not use for unreleased plans.
```

## Keep only behavioral guidance

Use imperative steps in execution order. Assume the reader can reason, edit, and use ordinary
tools. Keep a sentence only when it changes execution, prevents a likely failure, or routes needed
detail.

- Keep core procedure, one strong default, and non-obvious gotchas in `SKILL.md`.
- Use exact commands for fragile operations; use concise judgment where several approaches work.
- Explain the failure a constraint prevents instead of adding unexplained emphasis.
- Introduce each reference with when to read it. Keep one source of truth; link instead of restating.
- Remove background, process history, dated claims, and rules already loaded elsewhere.
- Distinguish observed contracts from recommended defaults. Source technical constraints, and teach
  real traps as symptom, cause, replacement, and observable proof.

Keep `SKILL.md` under 500 lines; move conditional detail one level into linked references.

## Budget context

| Part | Token cost | Keep there |
|---|---|---|
| `description` | every turn | shortest complete trigger |
| `SKILL.md` | after routing | core procedure, defaults, gotchas |
| `references/` | when read | conditional detail and larger examples |
| `scripts/` | output enters context | deterministic work with bounded output |
| `tests/` | validation only | executable contracts and edge cases |
| `assets/` | when used | templates and output material |

Prefer short examples. Bound script output to what the next decision needs.

## Prove the whole skill

1. Validate directory name, frontmatter name, description syntax, and limits.
2. When a grant is needed, apply it and verify the next turn:

   ```sh
   "$RUNDESK_COMMAND" skills list "$RUNDESK_AGENT"
   "$RUNDESK_COMMAND" skills doctor "$RUNDESK_AGENT"
   ```

3. Run each script's reference-owned edge matrix and direct executable entry point.
4. In different fresh turns, try a direct request, an indirect request, and a close near-miss.
   Confirm the body and required references load before work; fix routing by category, not copied
   prompt phrases.
5. For a substantial skill, compare the same task with a fresh baseline without the skill. Then
   have a separate test agent use it without the expected implementation. Review artifacts and
   commands directly; the agent's summary is not proof. Remove guidance that earns no material
   improvement.
6. Review generated writing separately from executable correctness: routing precision, execution
   order, useful judgment, concision, duplication, and reference discipline. Green script tests do
   not prove writing quality. Source or observe factual promises; test executable claims and narrow
   partial truths. Challenge semantic claims with an adversarial counterexample that preserves
   convenient aggregates while changing the real relationship or outcome—mutation checks cannot
   repair a wrong test oracle. Review the whole interface, including empty success, duplicate
   evidence, and every data-dependent output section.
