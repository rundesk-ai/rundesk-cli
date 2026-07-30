<h1 align="center">
  <img src="assets/readme/rundesk-banner.png" alt="Rundesk — Teammates that remember, adapt, and grow." width="100%">
</h1>

<p align="center">
  <a href="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml?query=branch%3Amain"><img src="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml/badge.svg?branch=main" alt="Build"></a>
  <a href="https://github.com/rundesk-ai/rundesk-cli/releases"><img src="https://img.shields.io/github/downloads/rundesk-ai/rundesk-cli/total?label=installs&amp;style=flat-square" alt="Installs"></a>
  <a href="https://github.com/rundesk-ai/rundesk-cli/releases/latest"><img src="https://img.shields.io/github/v/release/rundesk-ai/rundesk-cli?style=flat-square" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey?style=flat-square" alt="macOS">
</p>
<p align="center">
  ✨ <a href="#-highlights"><strong>Highlights</strong></a>
  &nbsp;·&nbsp;
  🚀 <a href="#-quick-start"><strong>Quick start</strong></a>
  &nbsp;·&nbsp;
  🧠 <a href="#-provider-adapters"><strong>Providers</strong></a>
  &nbsp;·&nbsp;
  💬 <a href="#-channel-adapters"><strong>Channels</strong></a>
  &nbsp;·&nbsp;
  🧩 <a href="#-documentation"><strong>Extending Rundesk</strong></a>
  &nbsp;·&nbsp;
  📖 <a href="#-documentation"><strong>Docs</strong></a>
</p>

**Run self-improving AI coding agents as durable, named teammates on your own Mac — then
reach them in Discord DMs, public channel threads, your terminal, or a schedule.**

Rundesk gives the coding CLI you already use its own workspace, rules, memory, skills,
conversations, and history. Agents preserve what they learn and can turn repeated work into
reusable skills and integration CLIs, improving how they work over time. Rundesk does not
replace Codex, Claude Code, Grok, or Google Antigravity; it gives those tools a dependable,
token-efficient operating layer.

## ⚡ It's this simple

```sh
rundesk add ava --provider codex
rundesk channels ava add discord --kind discord --allow <your-discord-user-id>
rundesk start ava
```

DM the agent for private work. Mention it in a public server channel and Rundesk opens a
dedicated thread; inside that thread, the conversation continues without mentioning the
agent again.

The same agent is also available from the terminal:

```sh
rundesk ask ava "review this repository and tell me the highest-risk open issue"
```

## ✨ Highlights

- **Bring your own coding agent.** Use the shipped Codex, Claude Code, Grok, or Google
  Antigravity adapter, or point Rundesk at a provider adapter you wrote.
- **One identity, one home.** Every agent has its own workspace, rules, memory, skills,
  conversations, and logs.
- **Always available.** macOS `launchd` keeps each agent's gateway running and brings it
  back after a crash, reboot, or automatic update.
- **Discord DMs and public threads.** Work privately in direct messages, or mention an
  agent in a server channel to open a dedicated thread for that conversation.
- **Terminal and scheduled work.** Continue the same agent from the command line,
  recurring cron schedules, or one-time scheduled turns.
- **A durable account of every turn.** Inspect messages, tool activity, outcomes, and
  token usage without relying on a provider's private session format.
- **Token-efficient by design.** Rundesk preserves native provider sessions, caching, and
  compaction instead of rebuilding the conversation inside a second agent loop.
- **Reusable capabilities.** Grant agents on-demand skills and place shared integration
  CLIs on every agent's `PATH`.
- **Self-improving by design.** Agents can turn repeated work into reusable skills and
  integration CLIs, so a capability developed once can be granted to every agent.
- **Local and recoverable.** Rundesk keeps its program separate from your data, supports
  manual and daily backups, and never requires a hosted Rundesk server.

## 💡 Why Rundesk?

Coding agents are excellent at a turn of work, but their native home is usually one terminal
session. Rundesk adds the parts needed to operate them over time:

- a stable identity and workspace for each agent;
- an always-on gateway owned by the operating system;
- conversations that resume across turns and surfaces;
- schedules that run once, never overlap, and do not run late after downtime;
- access controls for chat channels;
- normalized history and usage across different provider CLIs; and
- updates, backups, diagnostics, and removal with explicit ownership boundaries.

The provider and channel seams are programs, not in-process plugins. A custom adapter can be
written in any language and receives the same scheduling, lifecycle, history, and channel
behavior as a shipped adapter.

Rundesk keeps its own prompt overhead small. Provider adapters resume each provider's native
conversation, while skills use the provider's native discovery mechanism instead of being
copied into every prompt. The provider remains responsible for its context, prompt caching,
and compaction, so Rundesk adds durable memory and channel routing without rebuilding a
second orchestration loop around every turn.

## 🚀 Quick start

### Requirements

- macOS
- Python 3.9 or newer
- At least one [supported provider CLI](#-provider-adapters), installed and signed in

### Install

```sh
curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash
```

Rundesk installs under `~/.rundesk` without editing your shell profile:

```text
~/.rundesk/
  app/          the installed Rundesk release
  data/         your agents, skills, scripts, history, and configuration
```

Updates replace `app/`; uninstall leaves `data/` alone unless you explicitly ask to purge it.
When an update needs to migrate agent records, Rundesk first stops every gateway and keeps a
rollback copy of each database. If any migration fails, it restores every agent's records and
keeps the previous release in place.

### Create and check an agent

```sh
rundesk add ava --provider codex
rundesk doctor ava
rundesk ask ava "summarize what changed in this repository today"
```

Answers stream to the terminal. The next `ask` resumes the same terminal conversation; use
`--fresh` to start again, `--read-only` for a constrained turn, or `--steer` with Codex to
add instructions while a turn is running.

### Keep it running

```sh
rundesk start ava
rundesk agents
rundesk logs ava
```

Each agent has its own gateway. Restarting or stopping one does not disturb the others, and
stopping a gateway ends the provider and every child process it started.

### Schedule work

Run a recurring turn:

```sh
rundesk schedules ava add nightly \
  --when "0 3 * * *" \
  --ask "review today's changes and report anything risky"
```

Run once and post the outcome to an existing channel:

```sh
rundesk schedules ava add release-check \
  --at "2026-07-29T09:00" \
  --ask "verify the release and summarize the result" \
  --to discord-dms
```

Schedules can start an agent turn or an executable by full path. Rundesk records the
outcome either way.

Read one back in full, and change it without losing what it has already done:

```sh
rundesk schedules ava show nightly
rundesk schedules ava edit nightly --when "0 4 * * *" --to discord-dms
```

Only what you name changes; everything else — including when it last ran and what that
came to — stays exactly as it was.

## 🧠 Provider adapters

Rundesk ships four first-class provider adapters. Each uses the provider CLI and login
already established on your machine; Rundesk does not copy provider credentials.

| Provider CLI | `--provider` | First-class support |
|---|---|---|
| [OpenAI Codex CLI](https://learn.chatgpt.com/docs/codex/cli) | `codex` | Continuing conversations, model selection, tool activity, per-turn usage, and live steering |
| [Anthropic Claude Code](https://code.claude.com/docs/en/overview) | `claude` | Continuing conversations, model selection, tool activity, and per-turn usage |
| [xAI Grok CLI](https://docs.x.ai/build/cli/headless-scripting) | `grok` | Continuing conversations, model selection, tool activity, and per-turn usage |
| [Google Antigravity CLI](https://antigravity.google/docs/cli/install) | `antigravity` | Continuing conversations, model selection, tool activity, and per-turn usage |

Choose a default provider while creating an agent:

```sh
rundesk add claude-agent --provider claude
rundesk add grok-agent --provider grok
rundesk add antigravity-agent --provider antigravity
```

Use `configure` on an existing agent to change its default without replacing its
identity, home, memory, conversations, channels, schedules, or history:

```sh
rundesk configure ava --provider claude
```

Rundesk first checks that the new adapter can run, then changes the default atomically.
Because models and settings are provider-specific, old values are cleared unless you
supply replacements with `--model` and `--set`. A turn already underway finishes with
the provider it started with; subsequent turns use the new default.

Use the same command to change only the model, provider settings, or standing instructions:

```sh
rundesk configure ava --model opus
rundesk configure ava --set effort=high
rundesk configure ava --instructions "Keep answers concise."
```

On a single-user Discord channel, that user can run `/provider <provider>` to change the
same agent-wide default. Rundesk validates the adapter, keeps any turn already running on
its original provider, and starts the next message in that Discord conversation fresh.
Shared channels cannot change an agent-wide default.

Or choose a different provider or model for one turn or schedule without changing the
agent's default.

### Custom providers are first-class

```sh
rundesk add ava --provider /opt/my-provider --model fast-1 --set effort=high
```

A provider adapter is an executable that exchanges newline-delimited JSON records with
Rundesk. It can be a Python program, compiled binary, or shell script. Custom providers use
the same agent homes, schedules, channels, turn records, usage reporting, and lifecycle as
the adapters above.

→ **[Write a provider adapter](docs/extending/provider-adapters/references/the-contract.md)**

## 💬 Channel adapters

### Discord

Discord is the shipped first-class channel adapter:

```sh
rundesk channels ava add discord --kind discord --allow <your-discord-user-id>
```

The command securely asks for the bot token when needed, proves the connection before
saving anything, and creates separate `discord-dms` and `discord-rooms` channels by default.
You can also narrow it to direct messages, one server, or one channel.

On Discord, Rundesk supports:

- private direct messages and public server channels;
- a dedicated thread when the agent is mentioned in a public channel;
- continuing inside that thread without mentioning the agent again;
- explicit per-channel user allowlists;
- typing, state reactions, and optional live activity;
- long answers and generated files as attachments;
- inbound message attachments; and
- stopping or forgetting a conversation from chat.

```sh
rundesk channels ava instructions discord-rooms \
  "You are {agent} in {where.channel}. Others can read this, so keep it concise."
```

Channel instructions keep public-room behavior separate from private conversations.

### Custom channels are first-class

Like a provider adapter, a channel adapter is an executable rather than code Rundesk loads.
It owns the vocabulary and behavior of its platform while Rundesk owns access control, turn
state, history, and delivery. A custom channel gets the same agent and turn lifecycle as
Discord without changing Rundesk core.

→ **[Write a channel adapter](docs/extending/channel-adapters/references/the-contract.md)**

## 🧰 Everything Rundesk supports

### Agents and gateways

- Named agents with isolated homes, workspaces, rules, memory, and skills
- Private provider homes when the provider supports one; native-keyring and machine-login
  providers keep their state under the provider's own rules
- Diagnostics before a broken agent becomes an unattended failure
- One independently managed gateway per agent
- Clean start, stop, restart, update, uninstall, and optional purge operations

### Conversations and records

- Continuing or fresh conversations from terminal, channel, or schedule
- Read-only and working postures, translated into each provider's native controls
- Messages, tool activity, outcomes, errors, and token usage recorded per turn
- Message filters and full-text search across an agent's conversations

### Schedules

- Standard five-field cron schedules
- One-time schedules at an exact local timestamp
- Agent turns or arbitrary executables by full path
- Per-schedule provider, model, instructions, and delivery channel
- Every schedule readable in full, and editable in place without losing its history
- No overlapping run of the same schedule and no late execution after downtime

### Skills and integration CLIs

- A shared skill library with per-agent grants
- Built-in skills that update with Rundesk and owner-created skills that do not
- A shared executable library placed on every agent's `PATH`
- Companion guidance for building guarded, offline-tested service integrations

### Operations and data

- Install, automatic daily self-updates, version check, status, and doctor commands
- Manual backups, automatic daily backups, restore, and configurable backup location
- Program and owner data kept in separate directories
- Agent removal that preserves its home unless purge is explicitly requested

`~/.rundesk/data/config.json` is the source of every install-wide value. A fresh install
writes the complete configuration, including the skills every agent must receive:

```json
{
  "backups": {
    "at": "04:00",
    "keep_days": 30
  },
  "updates": {
    "at": "03:00"
  },
  "skills": {
    "granted": [
      "managing-rundesk",
      "managing-rundesk-schedules",
      "managing-rundesk-backups",
      "filing-rundesk-issues"
    ]
  }
}
```

Change `updates.at` and run `rundesk update` to reschedule automatic updates. A skill in
`skills.granted` is attached to every new and existing agent and cannot be revoked until it
is removed from this list. Updates and reinstalls reconcile missing required grants without
removing optional skills an owner added.
- Generated command reference that cannot drift from the installed parser

## 📖 Documentation

- **[CLI reference](CLI.md)** — every command and argument, generated from the parser
- **[Provider adapter contract](docs/extending/provider-adapters/references/the-contract.md)** — put another coding CLI behind an agent
- **[Channel adapter contract](docs/extending/channel-adapters/references/the-contract.md)** — reach an agent from another platform
- **[Integration CLI guide](docs/extending/integration-clis/README.md)** — give every agent a custom command
- **[Tested contracts](.knowledge/prd/README.md)** — every guarantee and the test that proves it
- **[Roadmap](ROADMAP.md)** — what is built, what is next, and why
- **[Architecture](.knowledge/CODEMAP.md)** — how the system is organized

## 🧪 Tests

The test suite is offline: it does not start a real provider or reach the network.

```sh
python3 .knowledge/scripts/gate
```

The gate discovers every suite, checks the documentation evidence, validates the shell
surface, and performs a real install and uninstall.

## License

Rundesk is available under the [MIT License](LICENSE).
