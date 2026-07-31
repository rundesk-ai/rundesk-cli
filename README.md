<h1 align="center">
  <img src="assets/readme/rundesk-banner.png" alt="Rundesk — Teammates that remember, adapt, and grow." width="100%">
</h1>

<p align="center">
  <a href="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml?query=branch%3Amain"><img src="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml/badge.svg?branch=main" alt="Build"></a>
  <a href="https://github.com/rundesk-ai/rundesk-cli/releases"><img src="https://img.shields.io/github/downloads/rundesk-ai/rundesk-cli/total?label=installs&amp;style=flat-square" alt="Installs"></a>
  <a href="https://github.com/rundesk-ai/rundesk-cli/releases/latest"><img src="https://img.shields.io/github/v/release/rundesk-ai/rundesk-cli?style=flat-square" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/rundesk-ai/rundesk-cli?style=flat-square" alt="MIT License"></a>
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
  📖 <a href="#-documentation"><strong>Docs</strong></a>
</p>

A coding agent usually lives in one terminal session. Close it, and the conversation
stops where you left it.

Rundesk gives that agent a name, a home, memory, and a way to keep working. Reach the
same agent from Discord, your terminal, or a schedule.

```sh
rundesk add ava --provider codex
rundesk channels ava add discord --kind discord --allow <your-discord-user-id>
rundesk start ava
```

DM `ava` tonight. The same agent, context, and workspace are still there tomorrow.

## ✨ Highlights

- **Reach it where you work.** Send a Discord DM, mention the agent in a server channel
  to open a dedicated thread, or continue from the terminal.
- **Keep it available.** macOS `launchd` owns one gateway per agent and brings it back
  after a crash, reboot, or update.
- **Let it work while you are away.** Run recurring or one-time work and deliver the
  result to a channel: `rundesk schedules ava add daily --when "0 4 * * *" --ask "review today's changes" --to discord-dms`
- **Improve how it handles your work.** Turn repeated procedures into reusable skills
  and integration CLIs, then grant them to any agent.
- **Keep it yours.** Rundesk runs locally, needs no hosted Rundesk server, and keeps
  backups outside the program and data an uninstall can remove.

## 🚀 Quick start

**Requires macOS · Python 3.9+ · one [supported coding CLI](#-provider-adapters)
already installed and signed in**

Install Rundesk:

```sh
curl -fsSL https://raw.githubusercontent.com/rundesk-ai/rundesk-cli/main/install.sh | bash
```

Create an agent:

```sh
rundesk add ava --provider codex
```

Ask it to work:

```sh
rundesk ask ava "summarize what changed in this repository today"
```

Keep it available:

```sh
rundesk start ava
```

The next terminal `ask` resumes the same conversation. To reach the agent away from
your terminal, **[set up the Discord bot](docs/discord.md)**.

## 🧠 Provider adapters

Rundesk ships four provider adapters. They use the provider CLI and login already on
your machine; Rundesk does not copy provider credentials.

| Provider CLI | `--provider` | Differentiator |
|---|---|---|
| [OpenAI Codex CLI](https://learn.chatgpt.com/docs/codex/cli) | `codex` | Live steering |
| [Anthropic Claude Code](https://code.claude.com/docs/en/overview) | `claude` | — |
| [xAI Grok CLI](https://docs.x.ai/build/cli/headless-scripting) | `grok` | — |
| [Google Antigravity CLI](https://antigravity.google/docs/cli/install) | `antigravity` | — |

Every shipped adapter supports continuing conversations, model selection, tool activity,
and per-turn usage.

Choose a provider while creating an agent:

```sh
rundesk add claude-agent --provider claude
rundesk add grok-agent --provider grok
rundesk add antigravity-agent --provider antigravity
```

Change an existing agent's default without replacing its identity, home, memory,
conversations, channels, schedules, or history:

```sh
rundesk configure ava --provider claude
```

Rundesk checks the new adapter before changing the default. A turn already underway
finishes with the provider it started with; subsequent turns use the new default.

Change only the model, provider settings, or standing instructions:

```sh
rundesk configure ava --model opus
rundesk configure ava --set effort=high
rundesk configure ava --instructions "Keep answers concise."
```

On a single-user Discord channel, `/provider <provider>` changes the same agent-wide
default. Shared channels cannot change that default.

### Custom providers are first-class

```sh
rundesk add ava --provider /opt/my-provider --model fast-1 --set effort=high
```

A provider adapter is an executable that exchanges newline-delimited JSON records with
Rundesk. It can be a Python program, compiled binary, or shell script. Custom providers
receive the same agent homes, schedules, channels, records, usage reporting, and
lifecycle as shipped adapters.

→ **[Write a provider adapter](docs/extending/provider-adapters/references/the-contract.md)**

## 💬 Channel adapters

### Discord

Discord is the shipped channel adapter:

```sh
rundesk channels ava add discord --kind discord --allow <your-discord-user-id>
```

The command asks for the bot token without echoing it, proves the connection before
saving anything, and creates separate `discord-dms` and `discord-rooms` channels by
default.

On Discord, Rundesk supports:

- private direct messages and public server channels;
- a dedicated thread when the agent is mentioned in a public channel;
- continuing inside that thread without mentioning the agent again;
- explicit per-channel user allowlists;
- typing, state reactions, and optional live activity;
- long answers, generated files, and inbound attachments; and
- stopping or forgetting a conversation from chat.

Keep public-room behavior separate from private conversations:

```sh
rundesk channels ava instructions discord-rooms \
  "You are {agent} in {where.channel}. Others can read this, so keep it concise."
```

→ **[Set up the Discord bot](docs/discord.md)**

### Custom channels are first-class

Like a provider adapter, a channel adapter is an executable rather than code Rundesk
loads. It owns the vocabulary of its platform while Rundesk owns access control, turn
state, history, and delivery.

→ **[Write a channel adapter](docs/extending/channel-adapters/references/the-contract.md)**

<details>
<summary><strong>The full feature list</strong></summary>

### Agents and gateways

- Named agents with isolated homes, workspaces, rules, memory, and skills
- Private provider homes when supported; native-keyring and machine-login providers
  keep their state under the provider's own rules
- Diagnostics before a broken agent becomes an unattended failure
- One independently managed gateway per agent
- Clean start, stop, restart, update, uninstall, and optional purge operations

### Conversations and records

- Continuing or fresh conversations from terminal, channel, or schedule
- Read-only and working postures translated into each provider's native controls
- Messages, tool activity, outcomes, errors, and token usage recorded per turn
- Message filters and full-text search across an agent's conversations

### Schedules

- Standard five-field cron schedules and one-time local timestamps
- Agent turns or arbitrary executables by full path
- Per-schedule provider, model, instructions, and delivery channel
- Every schedule readable in full and editable without losing its history
- No overlapping run of the same schedule and no late execution after downtime

### Skills and integration CLIs

- A shared skill library with per-agent grants
- Built-in skills that update with Rundesk and owner-created skills that do not
- A shared executable library placed on every agent's `PATH`
- Guidance for building guarded, offline-tested service integrations

### Operations and data

- Install, automatic daily updates, version checks, status, and doctor commands
- Manual and automatic daily backups, restore, and configurable backup location
- Program files under `~/.rundesk/app`; agent data and configuration under
  `~/.rundesk/data`
- Agent removal that preserves its home unless purge is explicitly requested
- Generated command reference that cannot drift from the installed parser

</details>

## ❓ FAQ

<details>
<summary><strong>Does this replace Codex or Claude Code?</strong></summary>

No. Rundesk is the operating layer around the coding CLI you already use. The provider
still owns the model, context, caching, compaction, and tool execution. Rundesk
deliberately does not build a second agent loop.

</details>

<details>
<summary><strong>Won't a wrapper burn my tokens?</strong></summary>

Rundesk resumes the provider's native session. Skills use the provider's own discovery
mechanism instead of being pasted into every prompt, so Rundesk does not rebuild the
conversation around each turn.

</details>

<details>
<summary><strong>Does my code leave my machine?</strong></summary>

Only wherever the provider CLI already sends it. Rundesk has no hosted server, account,
or product telemetry.

</details>

<details>
<summary><strong>Linux or Windows?</strong></summary>

Not yet. Rundesk currently depends on macOS `launchd` to own its gateways. Follow the
[roadmap](ROADMAP.md) for platform work.

</details>

<details>
<summary><strong>What happens when Rundesk updates?</strong></summary>

Updates replace `~/.rundesk/app` and leave `~/.rundesk/data` untouched. When records need
to move forward, Rundesk stops every gateway and keeps a rollback copy of each database.
If a migration fails, it restores the records and previous release.

</details>

## 📖 Documentation

- **[CLI reference](CLI.md)** — every command and argument, generated from the parser
- **[Discord setup](docs/discord.md)** — create, authorize, connect, and test an agent's bot
- **[Install-wide configuration](docs/configuration.md)** — update time, backups, and required skills
- **[Provider adapter contract](docs/extending/provider-adapters/references/the-contract.md)** — put another coding CLI behind an agent
- **[Channel adapter contract](docs/extending/channel-adapters/references/the-contract.md)** — reach an agent from another platform
- **[Integration CLI guide](docs/extending/integration-clis/README.md)** — give every agent a custom command
- **[Tested contracts](.knowledge/prd/README.md)** — every guarantee and the test that proves it
- **[Roadmap](ROADMAP.md)** — what is built, what is next, and why
- **[Architecture](.knowledge/CODEMAP.md)** — how the system is organized

## 🤝 Contributing

Issues and pull requests are welcome.

```sh
python3 .knowledge/scripts/gate
```

The gate discovers every offline suite, checks documentation evidence, validates the
shell surface, and performs a real install and uninstall.

## 📄 License

Rundesk is available under the [MIT License](LICENSE).
