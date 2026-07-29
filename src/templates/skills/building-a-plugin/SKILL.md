---
name: building-a-plugin
description: How to write, publish and version a rundesk plugin — a bundle of commands and skills a third party installs from a GitHub release, with its own shared records and its own migrations. Use whenever anyone wants to package a capability so other people can install it, asks how to publish or release a plugin, asks why a plugin will not install or has failed, or wants an existing integration command turned into something installable.
---

# Building a plugin

A plugin is what an integration becomes when somebody other than its author has to install it.
One `manifest.json`, a command, usually a skill, and a version — and rundesk installs it,
updates it, migrates its records and removes it.

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

## Start from one that works

```sh
rundesk plugins init weather          # writes a plugin that already installs
rundesk plugins check weather         # says whether anybody could install it
rundesk plugins install ./weather --confirm
```

`init` writes the whole shape, not a sketch: a launcher that finds its own files, a store that
opens the shared records safely, one migration step, a companion skill, and a manifest that
already declares the rundesk it was written against. **Never start from a blank directory** —
every rule below is already obeyed by what `init` gives you.

## Plugin or script?

| | Use a script | Use a plugin |
|---|---|---|
| Who wrote it | the owner | somebody else |
| Who installs it | nobody — it is just there | `rundesk plugins install` |
| Versioned | no | yes, and the tag must match |
| Updates | by hand | with `rundesk update` |
| Removable cleanly | by hand | `rundesk plugins remove` |

An owner's own command belongs in the script library (`rundesk scripts --where`) and the
`building-integration-clis` skill covers it. The moment somebody else has to install it, it is
a plugin.

## The shape

```text
manifest.json          the whole contract
bin/<name>             the command an agent types — executable, resolves its own location
lib/                   implementation; standard library first
skills/<name>/SKILL.md the companion skill, linked into rundesk's library on install
migrations/001.py      numbered steps for the plugin's own records
tests/                 offline, synthetic fixtures, never the live service
```

## The one rule about versions

**`manifest.json`'s `version` and the git tag must be the same word.** Tag `v1.4.0` carries
`"version": "1.4.0"`. Rundesk refuses an install where they disagree, for the reason it holds
itself to the same rule: a release tagged differently from what it declares is one nobody can
reason about.

Releasing is: bump `version`, commit, tag `vX.Y.Z`, publish a GitHub release. **Patch** for
fixes, **minor** for backward-compatible features, **major** for anything that breaks a
command's arguments or output. A new migration step is at least a minor.

`"manifest": 1` is a different number and you do not choose it — it is the format's version,
and rundesk refuses a plugin whose format it does not know rather than misreading it.

## What rundesk checks before it installs anything

All of it against a temporary directory, so a refusal leaves nothing behind:

- the name is lowercase letters, digits and single hyphens — the tightest shape every brain and
  every shell accepts;
- every declared path lands **inside** the plugin, and none is absolute;
- every command exists and is executable (`chmod +x` before you publish);
- every skill would actually be indexed — directory name, `name:` in the frontmatter and the
  manifest entry all the same word, or a brain indexes one and looks up another;
- migration steps are numbered without a gap or a duplicate;
- `requires.rundesk` is a range it can judge — `>=`, `==`, `<`, comma-separated;
- no credential carries a value.

`rundesk plugins check <path>` runs exactly these. Run it before every release.

## Records, and the fact they are shared

`state/` is yours and is **never replaced by an update**; `app/` is the release and is replaced
whole. Nothing written in `app/` survives an update — put everything worth keeping in `state/`.

**Every agent on the machine reaches the same database.** Two agents answering two people at
once are two processes against one file, so open it in WAL with a busy timeout — `init`'s
`lib/store.py` already does — and refuse records whose version this build does not understand
rather than reading them hopefully.

A migration step is `up(conn, state)`, numbered for the version it brings records *to*. Rundesk
runs it inside one transaction that also stamps the version, so:

- **do not commit, roll back, or stamp the version** — rundesk does all three, and a step that
  commits early breaks the promise that makes running it again safe;
- **never delete a file.** Copy, and return what is now spare; rundesk removes those only once
  the version has committed, so a step that died leaves both copies rather than neither;
- bump `EXPECTS` in `store.py` in the same commit that adds the step.

## Credentials

Names in the manifest, values in `${XDG_CONFIG_HOME:-$HOME/.config}/<name>/env`, mode `0600`.
Never in the repository, never in `state/` — rundesk backs up its whole data directory, so a
token beside the records ends up in every archive the owner keeps. A manifest with a value in
it is refused outright, because a manifest is published.

Rundesk gives programs a small environment, so anything exported in an interactive shell is not
there. Read the file.

## Why yours might fail

An update prints one word a plugin: `skipped` was not moved and still works, `failed` is
installed and unreachable — kept, but off every agent's `PATH`. `rundesk plugins` says why.

- **its `requires.rundesk` excludes the rundesk now running** — the commonest cause after an
  owner updates rundesk. Widen the range and publish;
- **a migration step failed** — the plugin stays on the version that worked, and its records
  were put back;
- **its manifest stopped being readable**;
- **a name it wants is taken** by something the owner wrote. Rundesk never overwrites that; you
  rename.

`rundesk plugins` says which and why.

## Before you publish

```sh
python3 -m unittest discover tests    # offline, no network
rundesk plugins check .
rundesk plugins install . --confirm   # then run the command from outside its source tree
```

Test offline against synthetic fixtures — never the live service, and never confirm a mutation
as a smoke test. The command contract in `building-integration-clis` applies unchanged:
credential-free `--help`, a `status` verb, bounded listings, compact text with `--json` for
structured output, errors to stderr with a non-zero exit, and mutations dry-run until
`--confirm` names the exact action.
