# Codemap — rundesk-cli

The always-loaded structural map: *where things are*, layer by layer. Keep it current — when you move
or restructure files, update this in the same task.

**Stay high-level.** List entry points, layers, and where each *kind* of thing lives — not every file.
A map that mirrors the whole tree rots on the next commit; one that names the landmarks stays true.

## Entry Points

- `rundesk` — the executable the installer symlinks onto a PATH. It resolves its own location, puts
  `src/` on the path and hands off to `cli.main`. It owns no logic, so everything below is importable
  and testable without it.

## Domain / Data

- `src/rundesk_cli/__init__.py` — **`__version__`, the one source of what version this is.** The command
  reports it, the updater compares against it, and a release tag is expected to match it. Nothing else
  holds a copy.

## Backend / Services

- `src/rundesk_cli/cli.py` — the command surface: every verb the finished product will have, registered
  from the outset. `COMING_SOON` is the list of those planned and not built; each answers and exits
  `NOT_BUILT` rather than reporting a success it did not earn. A verb graduates out of that table into a
  real command as it lands.
- `src/rundesk_cli/updater.py` — where this install stands against what is published, and moving between
  them. Every network call is behind an argument, so the whole module is exercised offline.

## Frontend / UI

- No UI. The command line is the whole surface.

## Tests

- `tests/` — `unittest`, run directly (`python3 tests/test_cli.py`), never touching the network.
  `test_cli.py` walks every verb off the parser rather than a restated list, so a command added and
  wired nowhere is caught here. `test_updater.py` covers the three outcomes — behind, current, and
  could-not-ask — and that an archive cannot write outside where it is unpacked.

## Scripts And Commands

- `install.sh` — puts `rundesk` on a PATH and takes it off again (`--uninstall [--purge]`). Installs
  into `~/.rundesk`, one directory under the person's home holding rundesk and its `.venv`; from a
  checkout it symlinks that checkout instead, so development and installed use share one layout. It
  changes nothing else a person owns — a `PATH` that does not reach the command is reported, never
  edited — and refuses to claim success until the installed command answers.
- `.github/workflows/build.yml` — the gate: everything parses, the installer is valid shell, each test
  file runs, and a real install answers. Pinned to Python 3.9, the oldest a fresh macOS ships.
- `.github/workflows/release.yml` — a `vX.Y.Z` tag publishes the release that `rundesk update` finds.

## Integrations / Jobs

- `GitHub Releases` — the only thing this reaches out to: the newest published tag, and the archive an
  update is fetched from.

## Docs

- `.knowledge/` — the knowledge system (prd/, prd-drafts/, research/, references/, guides/). See `.knowledge/README.md`.

---
*Editing this file? Follow the standard first: [`guides/docs-codemap.md`](./guides/docs-codemap.md).*
