# Publishing a skill catalog

Read this when other Rundesk installs must install the skill. The catalog is the release boundary:
group skills only when owner, audience, runtime, permissions, and release cadence align. Keep private
identifiers and local-only workflows out of public catalogs.

Read the target repository rules, contribution template, and release process first. They control
layout, sources, tests, versioning, and publication authority; this checklist does not override them.

## Build and validate

Put `manifest.json` at the repository root and packages under `skills/<name>/`:

```json
{
  "schema": 1,
  "name": "acme-skills",
  "version": "1.2.0",
  "description": "Skills for working on Acme's systems."
}
```

Use schema `1`, a safe non-reserved name, and a useful version and description. Do not list skills;
Rundesk discovers `skills/<name>/SKILL.md`. At least one valid skill is required.

Preview from the working directory:

```sh
"$RUNDESK_COMMAND" skills install ./acme-skills
```

Without `--confirm`, Rundesk copies and validates the complete catalog but changes nothing. The
preview is validation, not publication. Before pushing, fix every reported package together; run
the repository suite, applicable script or integration matrices, and fresh routing cases; inspect
the complete diff for credentials and private data; and reconcile documentation, indexes, and
version metadata.

## Publish and install

Publish at a public GitHub repository's default-branch root. Direct installation accepts only the
base repository URL and sends no GitHub credential.

```sh
"$RUNDESK_COMMAND" skills install https://github.com/acme/acme-skills
"$RUNDESK_COMMAND" skills install https://github.com/acme/acme-skills --confirm
"$RUNDESK_COMMAND" skills grant <agent> acme-skills/<skill>
```

The first command previews, the second installs, and the grant makes a skill discoverable.

For a private repository, the owner clones it and installs that absolute local path. Rundesk records
the path exactly and follows the directory, not its Git remote; the owner must pull changes before
updating. Avoid relative paths because updates may run from another working directory.

## Publish updates

Push the default branch and bump `version` so listings explain the release. Content, not version,
determines whether Rundesk finds an update:

```sh
"$RUNDESK_COMMAND" skills update acme-skills
"$RUNDESK_COMMAND" skills update acme-skills --confirm
```

Removing a package revokes every grant on update. Treat that as a breaking change. Trigger changes
can stop routing, and script-interface changes can break callers; follow repository version and
release gates. A branch or pull request is not publication—verify the exact default-branch commit
and required release artifact before saying an update is available.
