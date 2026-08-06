---
name: writing-skills
description: Write, review or fix a skill so a brain actually triggers it and uses it correctly. Use when asked to add a skill, capture a repeated procedure so it does not have to be explained again, publish a catalog of skills, work out why a skill is never triggered or is triggered for the wrong thing, or when a skill needs a credential — even if nobody says the word "skill".
---

# Writing skills

A skill is a directory holding a `SKILL.md`. Every brain rundesk runs already reads that format, so
nothing here is rundesk's invention and a skill you write works outside rundesk too.

## Where a skill goes

Your own skills stand in the `local` catalog. Ask where the library is rather than writing a path
down — an install can be pointed anywhere:

```sh
rundesk skills                       # prints the library and everything in it
mkdir -p <library>/local/app/skills/<name>
$EDITOR <library>/local/app/skills/<name>/SKILL.md
rundesk skills grant <agent> local/<name>
```

Nothing fetches into `local` and nothing rundesk does removes it. Skills that came from a catalog are
a different matter: **anything you edit inside one is replaced the next time that catalog is
checked**, because the repository is the source of truth. To change one, change it where it is
published — or copy it into `local` under a new name.

## The shape

```text
<name>/
├── SKILL.md          required: what this is, and when to reach for it
├── rundesk.json      optional: the credentials it needs
├── scripts/          optional: commands it ships
├── references/       optional: material read only when it is needed
└── assets/           optional: templates and files used in output
```

`name` and `description` are the only frontmatter to use. Other fields exist, they differ between
brains, and one brain silently dropping a skill over a key another accepts is not worth the trouble.

```markdown
---
name: release-notes
description: How this team writes release notes. Use when asked to draft, review or edit release notes, when a version is being tagged, or when deciding what a change should say to somebody who did not make it.
---
```

## The description is the whole triggering mechanism

**Nothing below the frontmatter is read until the skill has already been triggered**, so a "when to
use this" section in the body cannot help decide anything. Everything about when to reach for it goes
in the description.

- Third person, and pushy. Say what it does, then every situation it applies to.
- Name the situations somebody would be in, not the words they would use. Most people asking for the
  thing your skill does will never say its name.
- 1024 characters is the limit and is enforced. A hundred to two hundred words is the useful range.
- End with the escape hatch the good ones have: *"— even if nobody says the word X."*

## The body

Under 500 lines, and under is not a target to approach. Once triggered it stays in context for the
rest of the conversation, so every line is a recurring cost paid on every turn afterwards.

- Imperative and verb first. "To do X, do Y" — not "you should".
- **Assume a capable reader.** Only write what it would get wrong without you. If a competent person
  would do the right thing unprompted, cut it.
- **The most valuable thing you can write is the gotcha** — the environment-specific fact that
  defeats a reasonable assumption. Rows that look deleted and are not. One id spelled three ways. A
  health check that answers while the database is down. These go in the body, never in a reference,
  because a reader may not recognise the moment to go and look.
- Give a default rather than a menu. A skill that lists four options has moved the decision back to
  the reader.
- Explain why. Writing ALWAYS or NEVER in capitals is usually a sign the reason is missing.
- Introduce a reference by **when to read it**: "Read `references/api-errors.md` if the API answers
  anything but 200" — never "see references/ for details". Keep them one level deep.
- Say something once. A fact in both the body and a reference is a fact with two places to be wrong.

## Credentials

A skill that talks to something outside this machine says what it needs, in `rundesk.json` beside the
`SKILL.md`. One key, and a reason against every name:

```json
{
  "needs": {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com"
  }
}
```

The reason is not decoration. It is what somebody reads when `rundesk skills doctor` tells them the
value is missing, and it is the only thing that says where to go and get one.

**Never put a credential in a skill.** Name the variable and let the owner place it:
`rundesk env set JIRA_API_TOKEN`.

**More than one account is ordinary and needs nothing from you.** An owner with three Jira sites sets
`JIRA_API_TOKEN__ACME`, `JIRA_API_TOKEN__BETA` and so on, and rundesk finds those profiles from the
names you declared. Declare the plain names and say in the body that a profile may be named; a
profile carries all of its own values or it is reported incomplete, so nothing you write has to
handle a half-configured one.

## What never goes in a skill

- `README.md`, `CHANGELOG.md`, installation notes, or any account of how the skill was written.
- Credentials, tokens, or anything only true on one machine — including absolute paths.
- Anything the reader already loads every turn. A copy is the same words paid for twice and a second
  place to be wrong.
- Dated claims nothing will come back and correct.

## Publishing a catalog

A catalog is a repository with a `manifest.json` at its root and a `skills/` directory beside it.
Which skills it holds is **found** rather than listed — every directory under `skills/` with a
`SKILL.md` in it — so there is no list to keep in step with the directory.

```json
{
  "schema": 1,
  "name": "acme-skills",
  "version": "1.2.0",
  "description": "Skills for working on Acme's systems."
}
```

```sh
rundesk skills install https://github.com/acme/acme-skills            # says what it would do
rundesk skills install https://github.com/acme/acme-skills --confirm
```

A local directory is a valid source too, which is how you try a catalog before publishing it.

## Prove it works

**Test with a fresh reader that does not know it is being tested.** Ask for the outcome — "using the
skill at `<path>`, do X" — never "review this skill". Give it the raw material rather than your
conclusions, and never show it the answer you expect.

Run the same task **without** the skill first. If the result is the same, the skill is not earning
the context it costs, and the honest thing is to delete it.

Three checks before it is finished:

- `rundesk skills doctor` says nothing about it.
- A brain triggered it from a request that never used its name.
- Every script it ships is executable. A script that is present and not executable looks exactly like
  one that works, right up until something tries.
