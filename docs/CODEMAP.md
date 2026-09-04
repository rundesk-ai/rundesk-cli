# Codemap — Rundesk

Where each layer lives, and what is in it. Counts are of artifacts, so they survive a refactor and
go wrong visibly when the tree moves on without this page. A module count excludes `__init__.py`; a
documentation-home count excludes that home's own `README.md`.

The dependency spine points one way: `commands` → `lifecycle` → `core` → `utils`. The complete
domain-package graph is declared and enforced in `tests/test_layers.py`; a lower layer never imports
a higher one.

## Entry points (3)

| Path | What it is |
|---|---|
| `rundesk` | the installed entry point — finds itself, puts `src/` on the path, calls `cli.main` |
| `dev` | the checkout runner; scrubs every `RUNDESK_*` variable, then sets one scratch root and prints it |
| `install.sh` | fetches a release archive and hands off to `rundesk install` |

## Command surface (src/rundesk/commands/ — 24 modules, 23 groups)

One module per verb, and the only layer that may know `argparse`. Each takes a `Namespace` and
returns an exit code. `src/rundesk/cli.py` owns parser assembly and dispatch; `src/rundesk/exits.py`
owns the exit codes.

Twenty-two public groups — `status`, `version`, `configure`, `agents`, `gateways`, `backups`, `env`,
`login`, `ask`, `asked`, `messages`, `search`, `providers`, `permissions`, `turns`, `schedules`,
`channels`, `skills`, `teams`, `install`, `update`, `uninstall` — plus `_oauth`, the private token
bridge.

## Domain packages (src/rundesk/ — 11)

| Package | Modules | What it owns |
|---|---|---|
| `core/` | 5 | locations, configuration, durable values, sealed secrets, OAuth |
| `lifecycle/` | 6 | this program copy on a machine: releases, install, update, removal, backups, migrations |
| `agents/` | 5 | agent identity, home, records, and the per-agent store |
| `gateways/` | 6 | the hosting process and its `launchd` job |
| `providers/` | 11 | turns, continuations, and the provider-adapter boundary |
| `channels/` | 7 | conversations, authorization, and the channel-adapter boundary |
| `schedules/` | 4 | recurring and one-time work, and the claim that runs it once |
| `delegations/` | 3 | one agent's ask of another, and the answer it returns |
| `skills/` | 6 | the catalog index and per-agent grants |
| `teams/` | 3 | team declarations and member reconciliation |
| `capabilities/` | 2 | what macOS lets this process do, and whose grants an answer is about |

## Shared utilities (src/rundesk/utils/ — 8 modules)

Flat, concrete, and product-agnostic. Imports only the standard library and its own siblings, carries
no product terms, and keeps an accurate table in its `__init__.py`.

## Migrations (src/rundesk/agents/steps/ — 14; src/rundesk/lifecycle/steps/ — 0)

Numbered, discovered, and **immutable once shipped** — never renumbered, renamed, or edited. The
agent steps run from `0001_the_records_an_agent_keeps` to
`0014_where_one_schedule_reports`. The lifecycle registry exists and holds no shipped step yet.

## Adapters (src/ — 6)

Executables with a shebang and no `.py`, run as separate programs exchanging newline-delimited JSON.
Being extensionless is why a directory-scanning lint does not see them. A channel adapter answers
five invocations: `--capabilities`, `--check` and `serve` for the owner and the gateway, and `search`
and `fetch` for the agent itself. One of them answers a sixth nobody else says: `src/channels/slack`
runs itself as `upload`, because a file has a deadline and only a process can be held to one.

- `src/channels/` — `discord`, `slack`
- `src/providers/` — `codex`, `claude`, `grok`, `antigravity`

## Shipped artifacts (src/ — 2 trees)

| Path | What it is |
|---|---|
| `src/skills/` | the bundled `rundesk` catalog: `manifest.json` and 4 packages — `delegating-work`, `managing-github`, `managing-rundesk`, `writing-skills` |
| `src/templates/` | the agent home: an `AGENTS.md`/`CLAUDE.md` pair placed from one source, `MEMORY.md`, and purpose-named area templates for plans, research, retros, scripts, and tasks |

## Tests (tests/ — 88 suites, 3 support modules)

Directly runnable `unittest` suites. `tests/support.py` gives every case a temporary root, asserts
that Rundesk resolved that root before the case runs, and points the proxy variables at a closed port
so nothing a suite starts can leave the machine. `tests/fixtures_skills.py` holds skill fixtures, and
`tests/fixtures_gateways.py` the gateway and channel harness the two gateway suites share.
`scripts/suites` discovers every suite, runs each in its own interpreter, starts the slowest first
from durations it recorded last run, and fails on empty discovery. `tests/test_suites_runner.py`
proves that ordering never filters a suite out and that a damaged durations file cannot change a
result.

`tests/test_layers.py` is the architectural proof: it holds the package dependency graph, the
agent-guide heading contract, and the repository template digests.

## Documentation (docs/)

Three files at the root — `README.md`, `BRIEF.md`, `CODEMAP.md` — and every other page in a home:
`api/` (10 pages), `concepts/` (12), `guides/` (8), `extending/` (3), `requirements/` (12),
`research/` (33), plus `assets/`. Each home carries its own index.

## Repository configuration (root)

`requirements.txt` — adapter-only pins, exact: `discord.py` for `src/channels/discord` and
`slack_sdk` for `src/channels/slack`, and nothing under `src/rundesk/` imports either. `ruff.toml` — the development and CI lint contract,
never a product dependency. `cli-versions.lock` — which vendor CLI version each shipped adapter was
written against, and the captured stream that stands in for it so no suite needs an account or a
network. `.github/workflows/build.yml` — the suites across `ubuntu-latest` and `macos-latest` on
Python 3.9 and 3.13, plus a Ruff job.
