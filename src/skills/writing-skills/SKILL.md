---
name: writing-skills
description: Write, review or fix a skill so a brain actually triggers it and uses it correctly. Use when asked to add a skill, capture a repeated procedure so it does not have to be explained again, publish a catalog of skills, work out why a skill is never triggered or is triggered for the wrong thing, or when a skill needs a credential — even if nobody says the word "skill".
---

# Writing skills

A skill is a directory holding a `SKILL.md`. Every brain rundesk runs already reads that format, so
nothing here is rundesk's invention and a skill you write works outside rundesk too.

## Where a skill goes

Your own skills stand in the `local` catalog, one directory each, directly inside it:

```text
<library>/local/
├── manifest.json          rundesk wrote this; leave it alone
├── my-thing/SKILL.md      yours
└── another-thing/SKILL.md yours
```

**Ask where the library is rather than writing the path down** — an install can be pointed anywhere,
so a path that is right on this machine is wrong on the next one. The first line of
`"$RUNDESK_COMMAND" skills` says it.

```sh
"$RUNDESK_COMMAND" skills                      # prints the library, and everything in it
mkdir -p <library>/local/<name>
$EDITOR <library>/local/<name>/SKILL.md
"$RUNDESK_COMMAND" skills grant <agent> local/<name>
```

**Writing the file is not enough for an agent to have it.** A skill in the library is available to be
granted; an agent uses only what it has been granted, which is why the last line is there. Give it to
yourself and it is yours from your *next* turn — your environment was built when this turn started.
`"$RUNDESK_COMMAND" skills list <agent>` says what an agent holds, and `skills doctor` says why one
of them cannot be used.

`local` is flat because nothing fetches into it, and nothing rundesk does removes it. Every other
catalog keeps its skills a level down, under `app/skills/`, so that a re-fetch can replace the whole
tree in one move — which is exactly why **anything you edit inside one of those is replaced the next
time that catalog is checked**. The repository is the source of truth there. To change such a skill,
change it where it is published, or copy it into `local` under a new name.

## The shape

```text
<name>/
├── SKILL.md          required: what this is, and when to reach for it
├── rundesk.json      optional: the credentials it needs
├── scripts/          optional: commands it ships — executable, standard library only
├── references/       optional: depth read only when it is needed
└── assets/           optional: templates and files used in output
```

**Everything but `SKILL.md` is optional and most skills have none of it.** This very skill is an
example of two of them: the file you are reading is the whole of how to write a skill, and
`references/integrations.md` beside it is the part only somebody writing an integration ever needs.
That is the split to copy — the skill itself holds what every reader needs on every use, and a
reference holds what one reader needs occasionally.

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

## Reaching something outside this machine

**Advanced, and most skills need none of it.** A skill that tells an agent how to do something needs
no credentials, ships no commands, and stops at the sections above.

If yours has to sign in to an API, a ticket tracker or a deploy service, **read
`references/integrations.md`**. It covers the whole of it: declaring what you need in `rundesk.json`
and why the reason against each name matters, how a script you ship reads those values, how an owner
with three accounts gets profiles for free, and what `doctor` says when it is not working.

Two rules are worth knowing before you decide to go there, because they change what you write:

- **Never put a credential in a skill.** You name the variable; the owner places it with
  `"$RUNDESK_COMMAND" env set <NAME>`, at their own terminal, where nothing writes it down.
- **A value placed now reaches the next turn, not this one.** The environment was built when the turn
  started.

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
