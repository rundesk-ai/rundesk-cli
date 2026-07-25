# Codemap — rundesk-cli

The always-loaded structural map: *where things are*, layer by layer. Keep it current — when you move
or restructure files, update this in the same task.

**Stay high-level.** List entry points, layers, and where each *kind* of thing lives — not every file.
A map that mirrors the whole tree rots on the next commit; one that names the landmarks stays true.

## Entry Points

- `rundesk` — the executable the installer symlinks onto a PATH. It resolves its own location, puts
  `src/` on the path and hands off to `cli.main`. It owns no logic, so everything below is importable
  and testable without it.
- The machine's own supervisor, running `rundesk serve <name>` from a job `supervisor.py` wrote. The
  second way in, and the one nobody types: it is how a gateway is still there tomorrow.

## Domain / Data

- `src/rundesk_cli/__init__.py` — **`__version__`, the one source of what version this is.** The command
  reports it, the updater compares against it, and a release tag is expected to match it. Nothing else
  holds a copy. `ROOT` is the same idea for *where* this install is, resolved rather than assumed.

## Backend / Services

- `src/rundesk_cli/cli.py` — the command surface: every verb the finished product will have, registered
  from the outset. What the gateway verbs act on is passed in rather than imported, so the surface knows
  the verbs and nothing of locks, records or process groups. `COMING_SOON` is the list of those planned and not built; each answers and exits
  `NOT_BUILT` rather than reporting a success it did not earn. A verb graduates out of that table into a
  real command as it lands.
- `src/rundesk_cli/updater.py` — where this install stands against what is published, and moving between
  them. Every network call is behind an argument, so the whole module is exercised offline.
- `src/rundesk_cli/process.py` — a program rundesk runs, and how it keeps hold of it: its own session so
  ending it ends the whole tree, silence rather than duration as the failure, output streamed and never
  accumulated. Knows nothing of gateways or agents, and holds no state of its own, so any number of
  programs run at once.
- `src/rundesk_cli/gateway.py` — the part that stays running. One per name from the outset, since a
  gateway per agent is how one agent is cycled without disturbing the rest. Owns every program started
  through it, and proves it is alive with a lock the kernel drops when the process dies. Writes what
  happened to its own log, kept apart from its run state because history has to outlive the gateway.
- `src/rundesk_cli/schedule.py` — work that starts itself: what a schedule is, when one is next due, and
  which are due now. Knows nothing of gateways or processes, and what a schedule names is carried without
  ever being read — so the day it names an agent rather than a command, nothing here changes. The time is
  an argument, so a year of firings is decided in a millisecond.
- `src/rundesk_cli/supervisor.py` — handing a gateway to the machine that keeps it running: one job per
  gateway, and never one this install did not write. Every call out to the machine is an argument, so it
  is exercised on a machine with no supervisor at all.

## Frontend / UI

- No UI. The command line is the whole surface.

## Tests

- `tests/` — `unittest`, run directly (`python3 tests/test_cli.py`), never touching the network.
  `test_cli.py` walks every verb off the parser rather than a restated list, so a command added and
  wired nowhere is caught here. `test_updater.py` covers the three outcomes — behind, current, and
  could-not-ask — and that an archive cannot write outside where it is unpacked. `test_process.py` and
  `test_gateway.py` drive real processes and real signals, with the waits turned down.

## The layers, and which way they point

`cli` → `gateway` → `process`, and `supervisor` → `gateway`. `process` has never heard of a gateway,
which is what lets any number of programs run at once without coordinating. The command surface takes
what the gateway verbs act on as an argument rather than importing it, so the surface knows the verbs
and nothing of locks, records or process groups — and every one of them is tested with no gateway and
no supervisor anywhere near it.

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
