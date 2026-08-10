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
rundesk agents add ava --provider codex
rundesk channels add ava discord --allow <your-discord-user-id>
rundesk gateways start ava
```

DM `ava` tonight. The same agent, context, and workspace are still there tomorrow.

## ✨ Highlights

- **Reach it where you work.** Send a Discord DM, mention the agent in a server channel
  to open a dedicated thread, or continue from the terminal.
- **Keep it available.** macOS `launchd` owns one gateway per agent and brings it back
  after a crash, reboot, or update.
- **Let it work while you are away.** Run recurring or one-time work, and the result goes
  to the channel the agent is told things through:
  `rundesk schedules add ava daily --when "0 4 * * *" --ask "review today's changes"`
- **Improve how it handles your work.** Turn repeated procedures into reusable skills
  and integration CLIs, then grant them to any agent.
- **Keep it yours.** Rundesk runs locally, needs no hosted Rundesk server, and keeps
  compressed backups outside the program and data an uninstall can remove. Each backup
  contains sealed credentials and their key, so its storage is credential-bearing.

## 🚀 Quick start

**Requires macOS · Python 3.9+ · one [supported coding CLI](#-provider-adapters)
already installed and signed in**

Install Rundesk:

```sh
curl -fsSL https://get.rundesk.ai/rundesk | bash
```

Create an agent:

```sh
rundesk agents add ava --provider codex
```

Ask it to work:

```sh
rundesk ask ava "summarize what changed in this repository today"
```

Keep it available:

```sh
rundesk gateways start ava
```

The next terminal `ask` resumes the same conversation. To reach the agent away from
your terminal, see **[Setting up a Discord bot](#setting-up-a-discord-bot)** below.

## 🧠 Provider adapters

Rundesk ships three provider adapters. They use the provider CLI and login already on
your machine; Rundesk does not copy provider credentials. `rundesk providers` lists what
this install can actually run.

| Provider CLI | `--provider` | Differentiator |
|---|---|---|
| [OpenAI Codex CLI](https://learn.chatgpt.com/docs/codex/cli) | `codex` | Live steering |
| [Anthropic Claude Code](https://code.claude.com/docs/en/overview) | `claude` | — |
| [xAI Grok CLI](https://docs.x.ai/build/cli/headless-scripting) | `grok` | — |

Every shipped adapter supports continuing conversations, model selection, tool activity,
and per-turn usage.

Choose a provider while creating an agent:

```sh
rundesk agents add claude-agent --provider claude
rundesk agents add grok-agent --provider grok
```

Change an existing agent's default without replacing its identity, home, memory,
conversations, channels, schedules, or history:

```sh
rundesk agents configure ava --provider claude
```

Rundesk checks the new adapter before changing the default. A turn already underway
finishes with the provider it started with; subsequent turns use the new default.

A model or a posture is chosen per turn rather than stored on the agent:

```sh
rundesk ask ava --model opus "review this"
rundesk ask ava --read-only "what changed today?"
```

On a single-user Discord channel, `/provider <provider>` changes the same agent-wide
default. Shared channels cannot change that default.

### Custom providers are first-class

```sh
rundesk agents add ava --provider /opt/my-provider
```

A provider adapter is an executable that exchanges newline-delimited JSON records with
Rundesk. It can be a Python program, compiled binary, or shell script. Custom providers
receive the same agent homes, schedules, channels, records, usage reporting, and
lifecycle as shipped adapters.

→ **Writing a provider adapter** — the contract returns with the provider seam

## 💬 Channel adapters

### Discord

Discord is the shipped channel adapter. It is not special: it is a program Rundesk runs,
written against the [published contract](docs/adapters.md), and `rundesk channels doctor`
says what any channel cannot do and exactly why.

**A channel is a connection, not a place.** One `discord` channel per agent carries private
messages and every room the bot was invited to, so there is nothing to point it at and
nothing to name. One list of ids says who may reach the agent, and it says so wherever they
say it.

On Discord, Rundesk supports:

- private direct messages and public server channels;
- a dedicated thread when the agent is mentioned in a public channel;
- continuing inside that thread without mentioning the agent again;
- an explicit allowlist of ids, which nobody outside is ever answered or told about;
- typing, state reactions, and live activity that batches a burst of tools into one edit;
- long answers split to Discord's limit, generated files, and inbound attachments; and
- `/stop`, `/new`, `/restart`, `/shutdown`, `/status`, `/version`, `/agents`, `/skills`,
  `/schedules`, `/delegations` and `/provider` from chat.

Every slash-command answer is private to the authorized person who asked. `/agents` is the
install-wide directory: it lists every known agent with its description and granted skills without
starting a provider turn. Long private answers continue across ordered ephemeral followups rather
than being cut at Discord's message limit.

`/delegations` is the conversation-scoped work view. It shows current named-agent work—including
work whose originating provider session was reset while its result stayed routed to this
conversation—and the provider-local helper lifecycle the current session reported. It never shows
full briefs or results, and says when provider-local visibility is only partial.

#### Setting up a Discord bot

You need three things from Discord before `channels add` can succeed. Rundesk refuses,
without writing anything down, until it has connected — so getting one wrong costs a
retry rather than a broken agent at three in the morning.

1. **A bot token.** In the [Developer Portal](https://discord.com/developers/applications),
   create an application, open **Bot**, and **Reset Token**. Copy it.
2. **The Message Content Intent.** On that same **Bot** page, under **Privileged Gateway
   Intents**, switch on **Message Content Intent**. Without it Discord blanks every message
   in a room and in a thread unless it names the bot, so no thread could be opened and
   nothing said in one could be read. Rundesk refuses while it is off, and a gateway would
   be closed with `4014` rather than connecting.
3. **Your own numeric user id.** In Discord, **Settings → Advanced → Developer Mode** on,
   then right-click your profile and **Copy User ID**. This is a number, never a username —
   a username can be changed and an id cannot.

Then:

```sh
rundesk channels add ava discord --allow <your-discord-user-id> --notify
```

**Set `--notify` on the first channel you add, and let that be your own DM.** The two flags
answer different questions: `--allow` is who may *reach* the agent, and `--notify` is where the
agent *speaks first*. Without it you get an agent that answers when spoken to and never says
anything on its own — no "gateway came up", no "gateway going down", no schedule report, nothing
a delegation hands back. There is no error, because an agent that tells nobody is a legitimate
thing to want; the only sign is `told no` in the block `add` prints. Your own DM is the right
first choice: it exists before any server does, only you can read it, and it is where you want
the news that the thing is running.

It asks for the token without echoing it, connects, and only then writes the channel down.
On success it prints an **invite** URL — the bot is in no server until somebody with
permission opens that URL and adds it. A bot already in a server has to be sent the invite
again before it may open a thread or attach a file.

**One Discord application per agent.** One bot is one identity: two agents behind one token
receive the same messages, both may answer, and nobody reading the room can tell which of them
replied. So each agent gets its own application, its own name and its own avatar — and Rundesk
keeps each token under that agent's own name (`DISCORD_BOT_TOKEN__AVA`), without anybody having to
arrange it. **A plain `DISCORD_BOT_TOKEN` is not read**, so there is no shared name for two agents
to end up sharing. Upgrading an install that has one is a short, ordered procedure:
[Moving an existing channel onto the agent's own name](docs/commands.md#moving-an-existing-channel-onto-the-agents-own-name).

Finally, start the gateway — `channels add` connects once to prove the channel and does not
leave anything running:

```sh
rundesk gateways start ava
```

Then say hello to the bot in a DM. If nothing answers, `rundesk channels doctor` and
`rundesk gateways logs ava` are the two things to read. If it answers you but never speaks
first, it is the paragraph above: `rundesk channels configure ava discord --notify`, then
restart the gateway so the notice it announces itself with has somewhere to go.

### Custom channels are first-class

Like a provider adapter, a channel adapter is an executable rather than code Rundesk
loads. It owns the vocabulary of its platform while Rundesk owns access control, turn
state, history, and delivery.

→ **Writing a channel adapter** — the contract returns with the channel seam

<details>
<summary><strong>The full feature list</strong> — the published release, not yet checked against this tree</summary>

> **Read this block with the caveat the rest of the page no longer needs.** Everything above was
> checked line by line against `rundesk --help` on this branch. This list was not, and parts of it
> are known to be ahead of this tree — a schedule takes no per-schedule provider, model or delivery
> channel here; a role is a delegation target rather than anything a person can type; and there is no
> command-reference generator. It is kept because it is an accurate account of the published build
> and a useful map of where this one is going. `rundesk --help` is the truth about this copy.

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

### Role workers

- A role is two files — what the specialist is, and the rules one execution of it follows
- An agent hands a role one bounded task and carries on; it is woken to review the report
- The worker runs in the project you name, under that project's own instruction files
- None of the agent's identity, memory, history or unrelated skills reach it
- What a run used is locked when it is admitted and stays resumable for fourteen days
- The agent is the only thing that answers you, and it checks the report before it does

### Skills and integration CLIs

- A shared skill library with per-agent grants
- Required Rundesk operating skills that every agent retains
- The general `rundesk-skills` catalog included automatically on every install
- Versioned repository catalogs updated with every Rundesk update and removed as collections
- Owner-created skills that Rundesk never replaces
- A shared executable library placed on every agent's `PATH`
- Guidance for building guarded, offline-tested service integrations

Every install includes the general [`rundesk-skills`](https://github.com/rundesk-ai/rundesk-skills)
catalog without granting its skills automatically. Install another catalog from its repository
URL; Rundesk previews every declared skill before confirmation:

```sh
rundesk skills install https://github.com/rundesk-ai/rundesk-skills
rundesk skills install https://github.com/rundesk-ai/rundesk-skills --confirm
rundesk skills grant ava python-patterns
```

Catalog repositories use one `manifest.json` contract
whether they publish one skill or a collection.

First-party optional integrations use the same contract:

- [Apple skills](https://github.com/rundesk-ai/rundesk-skills-apple) — Calendar, Contacts,
  Mail, and Messages on macOS.
- [Integration skills](https://github.com/rundesk-ai/rundesk-skills-integrations) —
  Cloudflare, Confluence, Coolify, Discord, Jira, Monarch Money, Sentry, and Stripe.

Each command is packaged inside its skill. Service integrations use the system Python standard
library; Apple integrations use macOS system frameworks and tools. Neither catalog installs
dependencies. Credentials use isolated owner configuration by default with an explicit shared
dotenv option.

### Operations and data

- Install, automatic daily updates, version checks, status, and doctor commands
- Manual compressed backups, restore, and configurable backup location
- Existing v0.40 directory backups remain restorable; older `rundesk-data-*.zip` archives use a
  different format and are refused rather than guessed compatible
- One set of environment values every program rundesk starts is given, so integration
  commands find their credentials without anything being exported — held here or fetched
  by a command you name, never shown in full, and included in protected backups
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

Not yet. Rundesk currently depends on macOS `launchd` to own its gateways.

</details>

<details>
<summary><strong>What happens when Rundesk updates?</strong></summary>

Updates replace `~/.rundesk/app` and leave `~/.rundesk/data` untouched. When records need
to move forward, Rundesk stops every gateway and keeps a rollback copy of each database.
If a migration fails, it restores the records and previous release.

After the Rundesk transaction succeeds—even when Rundesk was already current—it installs
the default general catalog if absent and checks every installed catalog's repository. A
newer version replaces the catalog atomically; checking the same version also restores its
exact files to remove local drift. One failed catalog is reported without preventing the
others from being checked or rolling back an otherwise healthy CLI update.

</details>

## 📖 Documentation

- **[Commands](docs/commands.md)** — every operation, what it guarantees, and what each exit code means
- **[Channel adapters](docs/adapters.md)** — writing the program behind a channel: the three invocations, and every record
- **[Provider adapters](docs/providers.md)** — what a turn is, and writing the program behind a brain
- **[Gateways](docs/gateways.md)** and **[Schedules](docs/schedules.md)** — what each is, and every state one can get stuck in
- **[Where an install keeps things](docs/layout.md)** — one root, and everything derived from it
- **[Working on a checkout](docs/development.md)** — running and testing without installing

> **This branch is a rebuild in progress**, and `rundesk --help` is always the truth about what this
> copy can do. Every command outside the collapsed feature list above was checked against it: a verb
> Rundesk cannot perform is a verb Rundesk does not have, so nothing you can copy out of this page
> and run is a verb this tree lacks. The collapsed list is the one exception and says so where it
> stands.

## 🤝 Contributing

Issues and pull requests are welcome.

```sh
python3 scripts/suites
```

It discovers every suite rather than listing them, runs them offline, and fails when it finds none.
Read [`docs/development.md`](docs/development.md) before running anything against a checkout: every
location resolves under your home by default, and `./dev` is what points a run somewhere safe.

## 📄 License

Rundesk is available under the [MIT License](LICENSE).
