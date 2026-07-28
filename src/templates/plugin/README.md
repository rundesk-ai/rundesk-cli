# rundesk-plugin-example

A rundesk plugin. One repository, one plugin, one `manifest.json` at its root.

```sh
rundesk plugins install owner/rundesk-plugin-example
rundesk plugins grant winston example
```

## Layout

```
manifest.json          name, version, what it provides — the whole contract
bin/example            the command an agent types (executable, resolves its own location)
lib/                   implementation, standard library only
skills/example/        the companion skill, linked into rundesk's skill library
migrations/001.py      numbered steps for the plugin's own shared records
tests/                 offline, synthetic fixtures, never reaches the live service
```

## The one rule about versions

**`manifest.json`'s `version` and the git tag must be the same.** Tag `v1.4.0` carries
`"version": "1.4.0"`, always. Rundesk refuses an install where they disagree, for the same
reason it holds itself to it: a release tagged differently from what it reports is one nobody
can reason about — the manifest names one thing, the update offers another, and every version
comparison after that is against a number that was never true.

Releasing is therefore: bump `version`, commit, tag `vX.Y.Z`, publish a GitHub release.
`rundesk plugins update` sees it within the hour.

Follow release impact, as rundesk does: **patch** for fixes, **minor** for backward-compatible
features, **major** for anything that breaks a command's output or arguments. A new migration
step is at least a minor.

## Records

Everything worth keeping goes in `state/`, which rundesk gives you beside `app/` and never
replaces. **It is shared** — every agent on the machine reaches the same database — so
`lib/store.py` opens it in WAL with a busy timeout, and refuses records it does not understand
rather than reading them hopefully.

`app/` is replaced whole by every update. Nothing written there survives one.

## Credentials

Names in `manifest.json`, values in `~/.config/example/env`, mode `0600`. Never in this
repository, never in `state/` — rundesk backs up its whole data directory, so a token beside
the records ends up in every archive the owner keeps.

## Checks

```sh
python3 -m unittest discover tests   # offline, no network
rundesk plugins check .              # manifest, names, versions, step numbering
```
