# research/ — prior art (catalog)

Dated notes on how others solved a problem, each answering one question. **To write or modify one, follow [`../guides/docs-research.md`](../guides/docs-research.md).** Visual targets: sibling [`../references/`](../references/).

## Notes — maintained by hand

Add a row when you add a note; `doc-lint` fails the build if one is missing. Newest `Last updated` first.

| Last updated | Note | Question it answers |
|---|---|---|
| 2026-07-28 | [The Antigravity CLI as an agent's brain](./2026-07-28-antigravity-cli-as-a-brain.md) | What does the official Antigravity CLI actually do when driven headlessly, and which behavior must a Rundesk provider adapter absorb? |
| 2026-07-27 | [Which skills each installed brain discovers](./2026-07-27-skills-a-brain-discovers.md) | Where does each installed provider CLI look for skills, what does it actually load, and what mechanism can present one skill to every brain without a vendor path leaving `src/providers/`? |
| 2026-07-27 | [What makes a SKILL.md a model triggers and uses](./2026-07-27-authoring-a-skill.md) | What are the durable rules for writing a skill, so that our own guide and our shipped skill-writing skill teach what the field already knows rather than what we guessed? |
| 2026-07-26 | [What a brain can do when nobody is watching the turn](./2026-07-26-questions-approvals-and-recovery.md) | Driving command-line programs rather than APIs, what can and cannot be built for a turn nobody is watching — can a brain ask, can an answer get back, can an approval gate exist, and what survives a restart? |
| 2026-07-26 | [The Claude Code CLI as an agent's brain](./2026-07-26-claude-cli-as-a-brain.md) | What does the installed Claude Code CLI actually do when it is driven headlessly, and which of it has to be absorbed by an adapter? |
| 2026-07-26 | [The Grok CLI as an agent's brain](./2026-07-26-grok-cli-as-a-brain.md) | What does the installed Grok CLI actually do when it is driven headlessly, and which of it has to be absorbed by an adapter? |
| 2026-07-26 | [SQLite as a record store, and how the world orders migrations](./2026-07-26-sqlite-store-and-migrations.md) | How does the world order and record schema migrations, and what does practice say about SQLite as a per-agent record store with a single query seam? |
| 2026-07-26 | [The Codex CLI as an agent's brain](./2026-07-26-codex-cli-as-a-brain.md) | What does the installed Codex CLI actually do when it is driven headlessly, and which of it has to be absorbed by an adapter? |
| 2026-07-25 | [Provider CLI events and Discord interaction](./2026-07-25-provider-cli-discord-interaction.md) | Can Discord carry native Codex and Claude Code activity, approvals and questions without rundesk owning their agent loops? |
