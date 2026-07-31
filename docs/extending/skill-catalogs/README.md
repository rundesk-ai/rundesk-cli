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
Rundesk also performs that same comparison for every installed repository after each
successful `rundesk update`, including an update where the CLI itself is already current.

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

## Integration packages and environments

A script-backed skill remains an inert package during install and update. Rundesk validates and
copies its complete directory, preserves executable files, and never runs repository setup code.
The package owns its launcher and support code; credentials, mutable state, and caches stay outside
the catalog because an update atomically replaces catalog files.

The repository release is authoritative: every catalog check replaces changed scripts, adds new
files, removes files absent from the repository, and discards local edits inside catalog-managed
skills—even when the manifest version is unchanged. Keep anything that must survive an update in
the external config, cache, or state locations below.

First-party integrations use this boundary:

- no shared runtime environment; each launcher resolves only its own package files;
- system Python standard library only, so installation downloads no dependencies;
- isolated credentials by default under
  `${XDG_CONFIG_HOME:-$HOME/.config}/rundesk/integrations/<skill>/env`;
- an explicit `RUNDESK_INTEGRATIONS_ENV` shared dotenv for owners who prefer one managed file;
- `${XDG_CACHE_HOME:-$HOME/.cache}/rundesk/integrations/<skill>/` for disposable cache;
- `${XDG_STATE_HOME:-$HOME/.local/state}/rundesk/integrations/<skill>/` for non-secret state.

Do not install dependencies into the machine's Python or create an undocumented environment shared
by skills. Until Rundesk defines a declarative isolated third-party runtime, publish standard-library
code or a self-contained executable. The complete author contract and a copyable package shape live
in the public [integration catalog environment guide](https://github.com/rundesk-ai/rundesk-skills-integrations/blob/main/ENVIRONMENTS.md).

The Apple integrations use the same isolation model while relying on documented macOS system
frameworks. See the [Apple environment guide](https://github.com/rundesk-ai/rundesk-skills-apple/blob/main/ENVIRONMENTS.md).

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

## Default catalog and lifecycle

Fresh installs seed `https://github.com/rundesk-ai/rundesk-skills`. The same step runs after
every successful Rundesk update, so an existing installation receives the general catalog
without a separate migration command. It is still a regular external catalog: its skills
are optional per-agent grants and its repository version is independent from Rundesk's.

Every installed catalog is checked from the repository URL in its provenance. Repositories
are independent: a download or validation failure is reported, the last working version
stays active, and Rundesk continues checking the rest. A removed default catalog is seeded
again at the next install or successful Rundesk update.
