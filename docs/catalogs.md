# Writing a skill, and publishing a catalog

A skill is a directory holding a `SKILL.md`. Every provider CLI rundesk runs already reads that
format, so nothing here is rundesk's invention and a skill you write works outside rundesk too.

A **catalog** is a repository of them. It is the unit rundesk installs, updates and removes; a skill is
the unit it grants to an agent.

## Writing one of your own

Your own skills stand in the `local` catalog, which the install makes and rundesk never fetches into.
Ask where the library is rather than writing a path down — an install can be pointed anywhere:

```sh
rundesk skills                    # prints the library, and everything in it
library=$(rundesk skills | head -1 | sed 's/^skills in //')

mkdir -p "$library/local/app/skills/release-notes"
$EDITOR "$library/local/app/skills/release-notes/SKILL.md"
rundesk skills grant alan local/release-notes
```

```markdown
---
name: release-notes
description: How this team writes release notes. Use when asked to draft, review or edit release notes, when a version is being tagged, or when deciding what a change should say to somebody who did not make it.
---

# Release notes

Write for somebody who did not make the change...
```

`name` and `description` are the only frontmatter to use. Other fields exist, they differ between
providers, and one provider silently dropping a skill over a key another accepts is not worth the
trouble. `name` must equal the directory it stands in — a provider indexes it by the directory — and
`description` is the **whole** triggering mechanism, because nothing below the frontmatter is read
until the skill has already been triggered.

The shipped `writing-skills` skill teaches this properly, including what makes a description trigger
and what never belongs in a skill. It is granted from `rundesk/writing-skills`.

## Declaring what a skill needs

A skill that talks to something outside this machine says so, in `rundesk.json` beside its `SKILL.md`.
It has exactly one key:

```json
{
  "needs": {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com"
  }
}
```

A map of environment variable to **why it is needed**. That one field drives the install preview, the
guided `rundesk skills configure`, which profiles exist, every listing and every `doctor` verdict.

The reason is not decoration. It is what somebody reads when `rundesk skills doctor` tells them a value
is missing, and the only thing that says where to go and get one. A skill with no `rundesk.json`
declares nothing, needs nothing, and is never reported as blocked.

**Never put a credential in a skill.** Name the variable; the owner places it with `rundesk env set`.

**Declare the plain names, and profiles come for free.** An owner with three Jira sites sets
`JIRA_API_TOKEN__ACME`, `JIRA_API_TOKEN__BETA` and so on, and rundesk finds those accounts from the
names you declared. A profile carries all of its own values or it is reported incomplete, so nothing
you write has to handle a half-configured one.

Values are declared **in the order you write them**, and `configure` asks for them in that order — put
the site before the token, the way a person would set it up.

### What is deliberately not in this format

| Not here | Why |
|---|---|
| a `skills` list in the manifest | skills are found by walking `skills/`; a list is a second thing to keep in step with a directory |
| `optional` | declare what is required. A value your script uses if it happens to be there is your business, and `SKILL.md` is where you say so |
| per-script needs | one declaration per skill. Two granularities is two ways to be inconsistent |
| a profile declaration | profiles are found from what is stored, so adding an account needs no edit to your catalog |

One required file with four fields and one optional file with one field is the whole contract. That is
the amount somebody can still hold in their head in a year, which is the point.

## Publishing a catalog

A catalog is a repository with `manifest.json` at its root and `skills/` beside it:

```text
acme-skills/
├── manifest.json
└── skills/
    ├── release-notes/
    │   └── SKILL.md
    └── jira/
        ├── SKILL.md
        ├── rundesk.json
        └── scripts/search.py
```

```json
{
  "schema": 1,
  "name": "acme-skills",
  "version": "1.2.0",
  "description": "Skills for working on Acme's systems."
}
```

`name` must be usable as a directory name; `version` is shown to people; `schema` is the contract
version and this release accepts `1`. A manifest declaring any other schema is **refused rather than
read hopefully** — a field this release has never seen might be the one saying where the skills are,
and a hopeful reading installs an empty catalog while reporting success.

**Which skills it holds is found, not listed.** Every directory under `skills/` with a `SKILL.md` in
it. Adding one is a directory appearing.

A manifest carrying a `skills` list is still read — the published `rundesk-skills` catalog has one,
and rundesk ignores it rather than refusing it. Nothing is gained by keeping one in step with the
directory beside it, which is the whole reason the list stopped being the answer.

A catalog holding **no** skills is refused. A repository pointed at the wrong branch would otherwise
install in silence, and the symptom arrives days later as an agent that does not know something.

A catalog holding a skill no provider would load is refused too, and **every** such skill is named
rather than the first — a refusal naming one is a refusal somebody fixes and meets again.

## Installing it

```sh
rundesk skills install https://github.com/acme/acme-skills            # says what it would do
rundesk skills install https://github.com/acme/acme-skills --confirm
```

Two kinds of source and no others: a **GitHub repository URL**, or a **directory on this machine**. The
directory is how you work on a catalog before publishing it, and it is why the whole of rundesk's own
test suite runs with no network:

```sh
rundesk skills install ./acme-skills --confirm
rundesk skills update acme-skills --confirm
```

If your catalog is not on GitHub, clone it yourself and point rundesk at the clone. Every source shape
accepted here is one rundesk has to keep fetching correctly for ever, so there are two.

## How an update decides there is something to do

**What is on the far end is authoritative, and the version decides nothing.** A catalog whose author
edited a skill without bumping a number is still one this install should be running.

So the far end is asked, cheaply: the `ETag` from the last fetch goes back out as `If-None-Match`, and
a catalog nobody has touched answers `304` with no body at all. When something has changed, the whole
tree is replaced.

**A local edit inside a catalog is discarded, and that is the feature.** The repository is the source
of truth, so replacing the tree also repairs a skill somebody edited in place — which is what keeps
every machine running the same thing. To change a catalog skill, change it where it is published, or
copy it into `local` under a new name.

A skill that disappears from a catalog is **revoked from every agent holding it**, and each is named:
a grant pointing at a skill that is not there is a link every provider skips in silence, so the agent
would go on being described as holding something it cannot use.

## When it goes wrong

| It says | It means |
|---|---|
| `there is no manifest.json at the top of what was fetched` | the repository root has no manifest, or the archive has more than one directory in it |
| `declares no skills` | nothing under `skills/` holds a `SKILL.md` |
| `holds N skill(s) that cannot be used` | each one is named, with what is wrong: a frontmatter name that does not match its directory, a missing description, or a `rundesk.json` that will not parse |
| `is already installed` | use `rundesk skills update <catalog>` |
| `calls itself X and this install has it as Y` | the manifest was renamed; install it under the new name and remove the old |
| `is the catalog that ships inside the release` | you cannot install a catalog called `rundesk`; it comes out of the release |

`rundesk skills doctor` is the other half of this: it says which granted skill cannot be used, which
account, which value, and the one command that fixes it.
