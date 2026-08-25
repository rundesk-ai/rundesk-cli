# Brief — Rundesk

*What Rundesk is and why it exists. One screen, and it changes when the project does.*

## Story

Rundesk turns the coding-agent CLIs already installed on a Mac — Codex, Claude Code, Grok,
Antigravity — into durable named teammates. Each agent gets a name, a home, memory, skills, and a
gateway that keeps it reachable after the terminal closes. It runs locally: there is no hosted
server, no account, and no product telemetry.

This repository is the Python rewrite of the `rundesk` command. It ships the program, its installer,
the agent-home templates, the provider and channel adapters, and the bundled `rundesk` skill catalog.

## Why it exists

A coding CLI is a session. It starts when a terminal opens, ends when it closes, and has no identity
of its own — nothing it learned survives, nothing can reach it while it is not running, and there is
no way to keep two of them at different jobs. Rundesk is the operating layer around the CLI somebody
already uses and pays for: it keeps the agent alive under `launchd`, keeps its records, carries its
conversation across restarts, and gives it a way to be reached from somewhere other than a terminal.

The provider still owns the model, the context, caching, compaction, and tool execution. Rundesk
owns everything around them.

## Users

- People running a supported coding CLI on macOS, already installed and signed in, who want it to
  outlive the terminal.
- People who want more than one agent — named specialists with their own instructions, memory, and
  skills, installed from a versioned team catalog rather than configured by hand.

*Sourced from the readme's requirements and its teams and FAQ sections. The market this serves, and
who it is being sold to, are the owner's to state and are deliberately not guessed at here.*

## Scope

- **Covers:** agents; gateways; providers; channels; schedules; skills and catalogs; teams;
  ask, turns, and messages; backups; permissions; OAuth; and the install, update, and removal of the
  program itself.
- **Refuses:**
  - Linux and Windows — a gateway is a macOS `launchd` job.
  - A hosted server, an account, or product telemetry.
  - Owning the model, context, caching, compaction, or tool execution. Those stay with the provider.
  - Copying provider credentials. Rundesk uses the provider CLI and login already on the machine.
  - Runtime dependencies. `src/rundesk` is standard library only; the exact pins in
    `requirements.txt` are for adapters, which are separate programs across a pipe.
  - An external secret keeper or the system keychain. Both are stronger, and both need the key to
    stop living on this disk, which a gateway starting at boot cannot have.

## External systems

- `launchd` — hosts each agent's gateway and brings it back after a crash, a reboot, or an update.
- The provider CLIs — `codex`, `claude`, `grok`, `antigravity`, run under the owner's existing login.
- Discord — the shipped channel adapter, and the one runtime pin in `requirements.txt`.
- GitHub — `github.com` and `api.github.com`, for release archives during install and update, and
  for fetching skill and team catalogs.
- SQLite — the per-agent record store, through the standard library's `sqlite3`.
