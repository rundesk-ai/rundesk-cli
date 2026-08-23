<h1 align="center">
  <img src="assets/readme/rundesk-banner.png" alt="Rundesk — Teammates that remember, adapt, and grow." width="100%">
</h1>

<p align="center">
  <a href="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml?query=branch%3Amain"><img src="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml/badge.svg?branch=main" alt="Build"></a>
  <a href="https://github.com/rundesk-ai/rundesk-cli/releases/latest"><img src="https://img.shields.io/github/v/release/rundesk-ai/rundesk-cli?style=flat-square&color=blue" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/rundesk-ai/rundesk-cli?style=flat-square" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#-highlights"><strong>✨ Highlights</strong></a>
  &nbsp;·&nbsp;
  <a href="#-quick-start"><strong>🚀 Quick start</strong></a>
  &nbsp;·&nbsp;
  <a href="#-teams-and-skills"><strong>👥 Teams</strong></a>
  &nbsp;·&nbsp;
  <a href="#-provider-adapters"><strong>🧠 Providers</strong></a>
  &nbsp;·&nbsp;
  <a href="#-discord"><strong>💬 Discord</strong></a>
  &nbsp;·&nbsp;
  <a href="#-documentation"><strong>📖 Docs</strong></a>
</p>

Rundesk turns the coding agents you already use into durable teammates. Each agent gets a name,
home, memory, skills, and a gateway that keeps it available after the terminal closes. Rundesk runs
locally on macOS with Codex, Claude Code, Grok, or Antigravity.

## ✨ Highlights

- **Work from anywhere.** Continue one conversation from the terminal or Discord.
- **Keep agents available.** macOS `launchd` brings each gateway back after a crash, reboot, or
  update.
- **Schedule work.** Run recurring or one-time tasks and deliver results through the agent's
  notification channel.
- **Build a real team.** Install versioned specialists with shared skills and canonical
  instructions.
- **Keep control.** Rundesk has no hosted server or product telemetry. Your agents and records stay
  under your local Rundesk home.

## 🚀 Quick start

**Requires macOS · Python 3.9+ · one [supported coding CLI](#-provider-adapters) installed and
signed in**

```sh
curl -fsSL https://get.rundesk.ai/rundesk | bash
rundesk agents add ava --provider codex
rundesk ask ava "summarize what changed in this repository today"
```

The next `ask` continues the same conversation. Keep the agent available after the terminal closes:

```sh
rundesk gateways start ava
```

Add Discord when you want to reach it away from your terminal, or schedule work for later:

```sh
rundesk schedules add ava daily --when "0 4 * * *" --ask "review today's changes"
```

## 👥 Teams and skills

A team catalog packages named specialists, canonical instructions, and the skills they use. Install
the complete [Rundesk development team](https://github.com/rundesk-ai/rundesk-team-development):

```sh
rundesk teams install https://github.com/rundesk-ai/rundesk-team-development --provider codex
rundesk teams install https://github.com/rundesk-ai/rundesk-team-development --provider codex --confirm
```

Team members are created with their gateways stopped. Start only the agents you want to use:

```sh
rundesk gateways start forge
```

You can install the same repository as a skills-only catalog without creating agents:

```sh
rundesk skills install https://github.com/rundesk-ai/rundesk-team-development
rundesk skills install https://github.com/rundesk-ai/rundesk-team-development --confirm
rundesk skills grant ava rundesk-team-development/managing-development-work
```

Installing the team later keeps the existing catalog and adds the managed agents. See
[Skills and catalogs](docs/catalogs.md) for the package contract and publication workflow.

#### Supported first-party catalogs

- [`rundesk-skills`](https://github.com/rundesk-ai/rundesk-skills) — engineering, research, design,
  planning, and operating guidance; installed by default.
- [`rundesk-skills-apple`](https://github.com/rundesk-ai/rundesk-skills-apple) — guarded Calendar,
  Contacts, Mail, and Messages integrations for macOS.
- [`rundesk-skills-integrations`](https://github.com/rundesk-ai/rundesk-skills-integrations) —
  guarded service integrations for Cloudflare, Atlassian, Coolify, Discord, Monarch Money, Sentry,
  Slack, and Stripe.
- [`rundesk-skills-google`](https://github.com/rundesk-ai/rundesk-skills-google) — Search Console,
  Analytics, PageSpeed Insights, and Merchant Center integrations.
- [`rundesk-skills-gamedev`](https://github.com/rundesk-ai/rundesk-skills-gamedev) — game design,
  production, art, simulation, Axmol, and C++ guidance.
- [`desk-cli`](https://github.com/rundesk-ai/desk-cli) — task, desk, project, page, mention, and asset
  workflows for Desk.

The skills under this repository's `src/skills/` ship with Rundesk as the reserved `rundesk`
catalog. They stay version-coupled to the CLI instead of being installed from an external catalog.

## 🧠 Provider adapters

Rundesk uses the provider CLI and login already on your machine; it does not copy provider
credentials. `rundesk providers` lists what the current install can run.

| Provider CLI | `--provider` | Notes |
|---|---|---|
| [OpenAI Codex CLI](https://learn.chatgpt.com/docs/codex/cli) | `codex` | Supports live steering |
| [Anthropic Claude Code](https://code.claude.com/docs/en/overview) | `claude` | — |
| [xAI Grok CLI](https://docs.x.ai/build/cli/headless-scripting) | `grok` | — |
| [Google Antigravity CLI](https://antigravity.google/docs/cli/install) | `antigravity` | Cannot be steered mid-turn |

Choose a provider when creating an agent or change its default later:

```sh
rundesk agents add claude-agent --provider claude
rundesk agents configure ava --provider claude
```

Changing the provider keeps the agent's identity, home, memory, conversations, channels, schedules,
and history. Active work finishes with the provider it started with.

Models and read-only posture can be selected per turn:

```sh
rundesk ask ava --model opus "review this"
rundesk ask ava --read-only "what changed today?"
```

Custom providers are executable adapters that exchange newline-delimited JSON records with
Rundesk. See the [provider adapter contract](docs/providers.md).

## 💬 Discord

Discord is the included channel adapter. One bot connection per agent supports direct messages,
server channels, dedicated threads, allowlisted access, attachments, activity updates, and agent
commands from chat.

To connect an agent, create a bot in the
[Discord Developer Portal](https://discord.com/developers/applications), enable **Message Content
Intent**, and copy your numeric Discord user ID. Then run:

```sh
discord_user_id=123456789012345678
rundesk channels add ava discord --allow "$discord_user_id" --notify
rundesk gateways start ava
```

Rundesk prompts for the token without echoing it and verifies the connection before saving the
channel. Use one Discord application per agent so each has its own identity. `--notify` makes this
the channel for gateway notices, scheduled results, and other unprompted messages.

If the bot does not answer, check the channel and gateway directly:

```sh
rundesk channels doctor ava
rundesk gateways logs ava
```

Custom channel adapters are executables too. Rundesk owns access control, turn state, history, and
delivery while the adapter owns its platform. See the [channel adapter contract](docs/adapters.md).

## ❓ FAQ

<details>
<summary><strong>Does this replace Codex or Claude Code?</strong></summary>

No. Rundesk is the operating layer around the coding CLI you already use. The provider still owns
the model, context, caching, compaction, and tool execution.

</details>

<details>
<summary><strong>Won't a wrapper burn my tokens?</strong></summary>

Rundesk resumes the provider's native session. Skills use the provider's discovery mechanism
instead of being pasted into every prompt.

</details>

<details>
<summary><strong>Does my code leave my machine?</strong></summary>

Only wherever the provider CLI already sends it. Rundesk has no hosted server, account, or product
telemetry.

</details>

<details>
<summary><strong>Linux or Windows?</strong></summary>

Not yet. Rundesk currently uses macOS `launchd` to manage gateways.

</details>

<details>
<summary><strong>What happens when Rundesk updates?</strong></summary>

Updates replace the program under `~/.rundesk/app` while preserving the agent data under
`~/.rundesk/data`. Rundesk also checks installed catalogs and restores their declared files when
needed.

</details>

## 📖 Documentation

- **[Commands](docs/commands.md)** — operations, guarantees, and exit codes
- **[Channel adapters](docs/adapters.md)** — the executable contract behind a channel
- **[Provider adapters](docs/providers.md)** — turns and the executable contract behind a provider
- **[Skills and catalogs](docs/catalogs.md)** — packages, repositories, validation, and releases
- **[Gateways](docs/gateways.md)** and **[Schedules](docs/schedules.md)** — lifecycle and recovery
- **[Install layout](docs/layout.md)** — one root and everything derived from it
- **[Development](docs/development.md)** — safe checkout and test workflows

## 🤝 Contributing

Start with the [contributing guide](CONTRIBUTING.md) and use `./dev` for checkout commands so your
live Rundesk install stays untouched.

```sh
python3 scripts/suites
```

- [Report a bug](https://github.com/rundesk-ai/rundesk-cli/issues/new?template=bug-report.md)
- [Propose a change](https://github.com/rundesk-ai/rundesk-cli/issues/new?template=change-proposal.md)
- [Open a pull request](.github/pull_request_template.md)

## 📄 License

Rundesk is available under the [MIT License](LICENSE).
