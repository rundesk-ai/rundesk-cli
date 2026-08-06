# Publishing a skill catalog

Read this when a skill must be installable by other rundesk installs. Publish a catalog repository;
rundesk installs, updates, and removes catalogs, then grants individual skills from them.

## Build the repository

Put `manifest.json` at the repository root and skills under `skills/`:

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

- Use schema `1`; other schemas are refused.
- Make `name` a safe directory name. Do not use the reserved names `rundesk` or `local`.
- Keep `version` and `description` useful to a person reading `rundesk skills catalogs`.
- Do not list skills in the manifest. Rundesk finds every `skills/<name>/SKILL.md`.
- Include at least one valid skill; an empty catalog is refused.

## Validate before publishing

Preview an install from the working directory. Without `--confirm`, rundesk fetches or copies,
validates the manifest and every skill, reports the exact install, and changes nothing:

```sh
"$RUNDESK_COMMAND" skills install ./acme-skills
```

Fix every reported skill together. Confirm that frontmatter names match directories, descriptions are
present and within 1024 characters, `rundesk.json` parses, and every file directly under `scripts/` is
executable and tested.

## Publish and install

Push the catalog at the root of a GitHub repository's default branch. Rundesk accepts the base
repository URL only; it does not accept a branch, subdirectory, archive URL, or another forge.

The repository must be publicly readable for direct installation. Rundesk sends no GitHub
credential when it fetches a catalog.

Give installers these commands:

```sh
"$RUNDESK_COMMAND" skills install https://github.com/acme/acme-skills
"$RUNDESK_COMMAND" skills install https://github.com/acme/acme-skills --confirm
"$RUNDESK_COMMAND" skills grant <agent> acme-skills/<skill>
```

The first command is the preview; the second performs the install. A skill is not discoverable by an
agent until it is granted.

For a private repository, have the owner clone it and install the clone by its absolute path, such as
`/Users/me/catalogs/acme-skills`. Rundesk records the path exactly as typed and resolves it again on
every update, so a relative path can fail from another working directory. Rundesk follows that
directory, not its Git remote; the owner must pull changes into the clone before updating the catalog.

## Publish updates

Change the repository and push its default branch. Bump `version` so listings explain the release,
but do not rely on it to trigger an update: rundesk compares the catalog's content and treats the
repository as authoritative.

Installers can preview and apply the change:

```sh
"$RUNDESK_COMMAND" skills update acme-skills
"$RUNDESK_COMMAND" skills update acme-skills --confirm
```

Removing a skill from the repository revokes it from every agent when the catalog updates. Treat that
as a breaking change and state it before publishing.
