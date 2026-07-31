# Publishing skill catalogs

A skill catalog is a Git repository with `manifest.json` at its root. The repository is
the install, version, update, and removal unit; each declared skill remains its own grant
unit. Rundesk validates and copies catalog files but never imports or executes them during
installation.

## Manifest format

Every repository uses the same manifest whether it contains one skill or many:

```json
{
  "schema": 1,
  "name": "example-skills",
  "version": "1.2.3",
  "description": "Maintained skills for example work.",
  "skills": [
    {
      "name": "first-skill",
      "path": "skills/first-skill"
    },
    {
      "name": "second-skill",
      "path": "skills/second-skill"
    }
  ]
}
```

A repository containing one skill still uses `skills` as a list:

```json
{
  "schema": 1,
  "name": "example-skill",
  "version": "1.0.0",
  "description": "One maintained skill.",
  "skills": [
    {
      "name": "example-skill",
      "path": "skills/example-skill"
    }
  ]
}
```

The contract is intentionally the same for guidance-only packages and skills containing
package-local scripts, references, or assets.

- `schema` is the manifest contract version. This release accepts `1`.
- `name` identifies the installed catalog and uses lowercase letters, digits, and single
  hyphens.
- `version` is an exact semantic version with three numeric parts, such as `1.2.3`.
- `description` says what the collection is for.
- `skills` is a non-empty list. Every entry names a complete Agent Skill directory inside
  the repository; its `name`, directory name, and `SKILL.md` name must agree.

Increment `version` whenever installed catalog content changes. `rundesk skills update`
only activates a repository whose declared version is newer than the installed version.

## Repository shape

```text
example-skills/
├── manifest.json
└── skills/
    ├── first-skill/
    │   └── SKILL.md
    └── second-skill/
        ├── SKILL.md
        └── scripts/
```

Paths must stay inside the repository. Each skill directory is one complete portable
package; keep its scripts, references, assets, and other required resources beside its
`SKILL.md`.

## Install and grants

Install by repository URL, not by a catalog/skill pair:

```sh
rundesk skills install https://github.com/example/example-skills
rundesk skills install https://github.com/example/example-skills --confirm
```

The first command previews the validated manifest. Confirmation installs every declared
package into the shared library and grants none. Grant individual skills separately:

```sh
rundesk skills grant <agent> first-skill
```

Catalog updates and removal use the manifest's catalog name:

```sh
rundesk skills update example-skills
rundesk skills remove example-skills
rundesk skills remove example-skills --yes
```

An update or removal is refused if it would take away a skill still granted to any agent.
Catalog installation also refuses to replace an owner-authored package with the same name.
