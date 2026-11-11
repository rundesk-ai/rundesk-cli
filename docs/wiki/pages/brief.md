+++
title = "Brief"
subtitle = "purpose, reasoning, users, scope and outside systems"
status = "draft"
goals = false
intent = """
The brief exists so that a reader arriving at Rundesk CLI, person or agent, learns in one screen what it is,
who it is for and what it refuses. It stays short and stable, and names nothing private.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Name", value = "rundesk", cite = "program" },
  { label = "Source", value = "github.com/rundesk-ai/rundesk-cli", link = "https://github.com/rundesk-ai/rundesk-cli", cite = "release" },
]

[[infobox]]
group = "Requirements"
rows = [
  { label = "System", value = "macOS", cite = "job" },
  { label = "Python", value = "3.9 or newer", cite = "floor" },
  { label = "Dependencies", value = "none for the program itself", cite = "stdlib" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Account", value = "none, and no product telemetry", cite = "stdlib" },
  { label = "Provider credentials", value = "used where they are, never copied", cite = "login" },
]
+++

**Rundesk CLI** turns a coding-agent CLI already installed on a Mac into a named agent that outlives the
terminal. Each agent gets a home, records of its own, and a gateway that `launchd` restarts after a crash,
a reboot or an update.[^job]

## Purpose

A coding CLI is a session: it starts when a terminal opens and ends when it closes. Rundesk CLI keeps the
agent's records in a database of its own,[^records] carries a conversation across restarts by resuming
the provider's session,[^resume] and gives the agent a way to be reached from Discord or Slack.[^channels]

The provider still owns the model, the context and the tools. Rundesk CLI starts the provider's own command
and reads what it prints.[^turn]

## Users

People running a supported coding CLI on macOS who want it to answer when no terminal is open, and people
who want more than one agent, each with its own instructions, memory and skills.[^instructions] Who
Rundesk CLI is sold to is the owner's to state. {missing}

## Scope

Rundesk CLI covers agents, gateways, providers, channels, schedules, skills, teams, delegation, backups and
the install of the program itself.[^commands] It refuses four things:

| Refused | Reason |
|---|---|
| Linux and Windows | a gateway is a macOS `launchd` job[^job] |
| A runtime dependency in the program | `rundesk install` places a tree that runs on the standard library, and builds a virtual environment only when `requirements.txt` names something[^stdlib] |
| Copying a provider's credentials | Rundesk CLI runs the provider command under the login already on the machine[^login] |
| The system keychain for its own values | Rundesk CLI seals values under its own key beside the data[^secrets] |

## Outside systems

`launchd` hosts each gateway.[^job] The provider commands `codex`, `claude`, `grok` and `antigravity` run
each turn.[^turn] Discord and Slack are the two shipped channels.[^channels] GitHub serves release
archives and skill catalogs.[^release] SQLite holds each agent's records.[^records]

[^program]: `src/rundesk/cli.py` — `build_parser()` names the program `rundesk`.
[^job]: `src/rundesk/gateways/job.py` — `document()` writes the `launchd` property list, and `place()`
    bootstraps it; `plist_of()` puts it in `~/Library/LaunchAgents`.
[^floor]: `src/rundesk/commands/status.py` — `PYTHON_FLOOR`, which `_unfit()` compares against;
    `install.sh` — `find_python()` accepts the first interpreter at 3.9 or newer.
[^stdlib]: `src/rundesk/lifecycle/packages.py` — `built()` makes a virtual environment only for a
    non-empty `requirements.txt`; `src/rundesk/lifecycle/tree.py` — `place()` copies the program tree.
[^records]: `src/rundesk/agents/records.py` — `reading()` and `writing()` open the agent's `state.db`
    through `sqlite3`.
[^resume]: `src/rundesk/providers/turns.py` — `_admit()` resumes the provider's session when the
    instruction fingerprint has not moved.
[^channels]: `src/rundesk/channels/adapters.py` — `known()` finds the shipped channel adapters
    `discord` and `slack`.
[^turn]: `src/rundesk/providers/adapters.py` — `talking_to()` starts the adapter, which runs the
    vendor's own command; `known()` finds `claude`, `codex`, `grok` and `antigravity`.
[^instructions]: `src/rundesk/providers/instructions.py` — `build()` composes each agent's own
    instructions.
[^commands]: `src/rundesk/cli.py` — `build_parser()` registers every command group.
[^login]: `src/rundesk/providers/adapters.py` — `account_login()` runs the adapter's own
    `--account-login` attached to the owner's terminal.
[^secrets]: `src/rundesk/core/secrets.py` — `SEALED` and `KEY_IN`, the sealed form and the key beside
    the data.
[^release]: `src/rundesk/lifecycle/release.py` — `REPO` and `ARCHIVE_URL`, the release archive address.
