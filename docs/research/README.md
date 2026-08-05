# Research

**What was found out, kept where it can be read after the thing that taught it is gone.**

This is not part of the product's documentation. [`docs/`](../) describes rundesk as it is, and a page
appears there when the thing it describes is built and works. A page appears *here* when somebody
spent an afternoon establishing something and the next person would otherwise spend the same
afternoon.

Two kinds of thing belong here, and nothing else:

- **What a previous build learned the hard way.** The build this one replaces is in `src_old/` and
  friends, which are gitignored, reference-only, and will be deleted. Everything in them that cost a
  real incident to discover is worth more than the code is, and it does not survive the deletion
  unless somebody writes it down.
- **What the platform actually does**, as opposed to what its manual says or what anybody
  remembers — verified by running it, with the output kept.

Two rules for a page here:

1. **Say how you know.** Measured, read in a manual, or recalled are three different claims, and a
   reader deciding whether to trust a line needs to know which it is. Mark the ones you are unsure
   about rather than leaving them level with the rest.
2. **Date it, and say what it was true of.** A platform note is true of a version. A lesson from a
   previous build is true of that build. Neither ages well silently.

## Written here

| Page | What it holds |
|---|---|
| [`the-old-build.md`](the-old-build.md) | how the previous build did agents and gateways, and every incident it recorded |
| [`launchd-on-macos.md`](launchd-on-macos.md) | what `launchctl` really does, and every state a job can get stuck in |
| [`macos.md`](macos.md) | what the filesystem, the keychain, the shells, the tools and the shipped Python actually do |
| [`python.md`](python.md) | what the language and its standard library do, and how a test here is proved |
| [`the-adapter-contracts.md`](the-adapter-contracts.md) | what a provider adapter and a channel adapter each have to do, and the numbers that bound them |
| [`instruction-layers.md`](instruction-layers.md) | how a system prompt was assembled, and the one rule the shape rested on |
| [`open-questions.md`](open-questions.md) | what the previous build wrote down and never settled |
| [`working-practice.md`](working-practice.md) | how that build wrote things down, named things, and moved readers onto a new store |
| [`2026-08-05-what-a-skills-commands-are-handed.md`](2026-08-05-what-a-skills-commands-are-handed.md) | the environment a skill's own commands will be given, decided while building skills and not yet implemented |
| [`2026-08-05-the-old-builds-channel-system.md`](2026-08-05-the-old-builds-channel-system.md) | what the previous build's two channel adapters and their seam actually did |
| [`2026-08-05-how-other-gateways-do-channels.md`](2026-08-05-how-other-gateways-do-channels.md) | seven comparable products on plugin boundary, capabilities, identity, authorization and setup |
| [`2026-08-05-designing-the-channel-system.md`](2026-08-05-designing-the-channel-system.md) | what is settled about channels, what is open, and the options — a proposal, not a description |
| [`2026-08-05-the-old-builds-provider-system.md`](2026-08-05-the-old-builds-provider-system.md) | the previous build's six provider modules end to end, and every incident each one cost |
| [`2026-08-05-how-other-gateways-run-a-provider.md`](2026-08-05-how-other-gateways-run-a-provider.md) | OpenClaw and Hermes on supervising a provider process, and the two shapes to refuse |
| [`2026-08-05-designing-the-provider-system.md`](2026-08-05-designing-the-provider-system.md) | what is settled about providers, the terms-of-service position, and the nine-phase route — a proposal, not a description |

## Carried over intact

The previous build's own research directory, copied on 2026-08-04 with the date each was established kept
in its filename. These are **measurements of the outside world** on a stated day against a stated version,
so they are not rewritten and not merged — a rewritten measurement is a recollection. Each opens with a
note saying what in it is still true of this build and what is not.

| Page | What it holds |
|---|---|
| [`2026-07-25-provider-cli-discord-interaction.md`](2026-07-25-provider-cli-discord-interaction.md) | whether a chat surface can carry provider activity, approvals and questions — mostly doc-derived, and refuted in part the next day |
| [`2026-07-26-claude-cli-as-a-brain.md`](2026-07-26-claude-cli-as-a-brain.md) | what the Claude Code CLI does driven headlessly, its stream, its usage arithmetic and every flag trap |
| [`2026-07-26-codex-cli-as-a-brain.md`](2026-07-26-codex-cli-as-a-brain.md) | what the Codex CLI does driven headlessly, and why its usage figure is a running total |
| [`2026-07-26-grok-cli-as-a-brain.md`](2026-07-26-grok-cli-as-a-brain.md) | what the Grok CLI does driven headlessly, and the two flags that read like containment and are not |
| [`2026-07-26-questions-approvals-and-recovery.md`](2026-07-26-questions-approvals-and-recovery.md) | what a brain can do when nobody is watching the turn — asking, approving, steering, and surviving a restart |
| [`2026-07-26-sqlite-store-and-migrations.md`](2026-07-26-sqlite-store-and-migrations.md) | what SQLite actually does as a per-agent record store, and how the world orders and records migrations |
| [`2026-07-27-authoring-a-skill.md`](2026-07-27-authoring-a-skill.md) | what four bodies of vendor guidance agree makes a `SKILL.md` a model triggers and uses correctly |
| [`2026-07-27-skills-a-brain-discovers.md`](2026-07-27-skills-a-brain-discovers.md) | which skill directories each installed brain really reads, and how one skill reaches all three |
| [`2026-07-28-antigravity-cli-as-a-brain.md`](2026-07-28-antigravity-cli-as-a-brain.md) | what the Antigravity CLI does driven headlessly, including a denial that exits zero |
| [`2026-07-29-what-a-gateway-tells-its-agent.md`](2026-07-29-what-a-gateway-tells-its-agent.md) | what two comparable self-hosted gateways put in front of their agents, and what neither ships |
