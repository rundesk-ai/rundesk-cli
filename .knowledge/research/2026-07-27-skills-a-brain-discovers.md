# Research: which skills each installed brain discovers, and how one skill reaches all three

**Last updated:** 2026-07-27
**Question it answers:** Where does each installed provider CLI look for skills, what does it actually load, and what mechanism can present one skill to every brain without a vendor path leaving `src/providers/`?

## What they do

### The format has converged

All three shipped brains read the same unit: a directory holding `SKILL.md`, YAML frontmatter plus a
Markdown body. The format is an open standard originally developed by Anthropic and now carrying a
public specification and a client showcase of around forty-five adopters.[1] The specification defines
`name` and `description` as required and `license`, `compatibility`, `metadata` and `allowed-tools` as
optional, and defines **no field for an agent, an owner, a grant or a provider**.[1]

Measured: one identical `SKILL.md`, planted once, was indexed by claude 2.1.220, codex-cli 0.145.0 and
grok 0.2.112 without complaint.[14]

### All three auto-load by progressive disclosure

Name and description sit in the model's index every turn; the body loads only when the skill is used.
Claude documents the metadata as always-loaded with the body loaded on invocation.[2] Codex injects a
`### Available skills` listing and instructs the main agent to open the matching `SKILL.md` before
acting.[3] Grok states that it "activates a skill only when it applies to your current task".[13]

So a skill costs its description per turn and its body only when relevant. Nothing has to be injected
into a prompt for a brain to use one.

### Where each one looks — measured, not read off documentation

One canary per candidate directory, each declaring its own unguessable code, planted under a single
scratch working directory, with a bare `skills/` as the control.[14]

| Brain | Version | Read | Not read |
|---|---|---|---|
| claude | 2.1.220 | `.claude/skills` | `.agents`, `.codex`, `.grok`, `.cursor`, bare `skills/` |
| codex | codex-cli 0.145.0 | `.agents/skills`, `.codex/skills` | `.claude`, `.grok`, `.cursor`, bare `skills/` |
| grok | 0.2.112 | `.grok`, `.agents`, `.claude`, `.cursor` skills | `.codex`, bare `skills/` |

**A bare `skills/` directory is read by nobody**, on all three current versions.[14] Claude reading only
its own root agrees with its published location table.[2]

Discovery is relative to the directory the CLI is standing in, and walks upward. Measured: the upward
walk is bounded by the **git repository root** — with no repository above it, discovery stopped at the
working directory itself; after `git init` two levels up, a skill at that new root became visible to a
working directory that could not previously see it. Confirmed on both codex and grok.[14]

### Symlinks are followed, and de-duplicated

Claude documents that a skill entry may be a symlink to a directory elsewhere on disk, that it follows
it, and that "if the same target is reachable from more than one location, Claude Code loads the skill
once".[2] Measured on all three brains, in both a per-skill layout and a whole-directory layout, and
through a **two-hop** chain of link-to-link.[14] Codex reports the resolved target path; grok reports the
link path.[14] With three vendor roots all linked to one source, each brain indexed the skill exactly
once.[14]

This contradicts the finding recorded against the build this repository replaces, that no provider
follows a link.[14]

### Each brain also reads the machine owner's own skills

Measured, standing in a scratch directory with the owner's environment: grok listed 23 skills from
`~/.grok/skills` and codex 16 from `~/.codex/skills`, on every working directory. `~/.claude/skills` did
not exist on the machine measured.[14]

Relocating the vendor's home removes them: with `GROK_HOME` and `CODEX_HOME` pointed at a private
directory, owner-level skills fell to zero while the working directory's own remained.[14]

That relocation costs the sign-in. Codex and grok each keep a plain `auth.json` inside the home, so a
private home is logged out until a credential is placed there; measured, a copied `auth.json` restored
both.[14] Claude keeps no credential file — its sign-in is in the macOS keychain — and **cannot be
isolated at all**: `CLAUDE_CONFIG_DIR` pointed at a scratch directory, `CLAUDE_CONFIG_DIR` pointed at
claude's own default `~/.claude`, and `HOME` relocated with `USER` preserved each reported
`loggedIn: false`.[14]

### `.agents/` is a convention for maximum visibility, not a scope

`.agents/skills` was proposed in December 2025 to stop each vendor inventing its own directory, and the
proposal's adoption list names around eighteen clients.[4] It is a convention rather than part of the
specification, and the specification's client guidance recommends scanning it *alongside* a client's own
directory.[5] Nothing in the proposal addresses which agent may use which skill.[4]

### How comparable products decide which agent gets which skill

- **Hermes Agent** makes a "profile" a separate home directory — its own `config.yaml`, `SOUL.md`,
  memories, sessions and skills — selected by `HERMES_HOME`. Skills are scoped by which home they were
  installed into; there is no per-profile allowlist.[7][8]
- **OpenClaw** gives each agent its own workspace but also has machine-wide skill roots, and therefore
  adds an explicit per-agent allowlist in central configuration — `agents.entries.<id>.skills`, which
  replaces rather than merges with the defaults, and where an empty list means none.[9] Its own
  documentation states that this allowlist is "a visibility and loading filter… not a shell-time
  authorization boundary".[10]
- **OpenCode** is the only product found that scopes *skills* per agent, through `allow` / `deny` / `ask`
  pattern permissions where `deny` hides a skill from the agent.[11]
- **Goose** scopes extensions per recipe through a hard allowlist but applies no per-recipe restriction
  to skills.[12]
- **Claude Code** gives a subagent a `skills:` frontmatter list, and documents that it controls which
  skills are **preloaded, not which the subagent may access** — a subagent can still invoke unlisted
  skills through the Skill tool. Denying access is done negatively, by removing the Skill tool.[6]

The specification declines to scope at all, delegating it to the client, and describes a catalog
filtering step in which a client hides skills that settings or a permission system deny.[5]

## What we can borrow

- **The format, unchanged.** One `SKILL.md`, `name` and `description`. There is nothing to invent and a
  house dialect would only break portability.
- **Symlinks as the reuse mechanism.** It is the one pattern that works with brains that discover by
  filesystem, it is documented by claude and measured on all three, and de-duplication makes overlapping
  placement harmless.
- **Hermes's home-per-agent isolation**, which is the shape this product already has: an agent's own
  directory is its scope, and no configuration expresses it.
- **The specification's catalog-filtering idea**, inverted to suit us: we cannot filter what a brain
  loads, but we decide what is placed before it runs, which is the same effect achieved earlier.
- **`metadata`** as the sanctioned extension point, if anything of ours ever needs to travel in a skill.

## What to avoid

- **Injecting a skill's text into a prompt.** It charges every turn for every skill, puts us in the
  business of deciding relevance, and would break the requirement that everything added to a turn appears
  in that turn's account.
- **An allowlist in configuration.** OpenClaw needs one because it owns the agent loop and does the
  loading. We do not load anything, so a rundesk allowlist could only ever describe what rundesk placed
  while the brain went on reading the owner's own roots — a boundary that is not one, which is the exact
  failure OpenClaw warns about.[10]
- **Treating a vendor directory as a scope.** Grok reads three other vendors' roots, so a skill placed
  "for codex" is also handed to grok. Directory identity carries no permission.
- **Linking a whole directory rather than each skill.** It makes a vendor-owned path an alias for the
  owner's canonical one, so a brain's own skill-installer writes into the source of truth and a
  destructive command aimed at a vendor's directory destroys it.
- **Relocating a vendor's home as default behaviour.** It logs every agent out, and on claude there is no
  way back in without a browser. The build this replaces tried it and reverted it.
- **Reading a vendor's field or search path off its documentation.** Claude's own docs list only
  `.claude/skills` and are right; the previous build's note that no provider follows a link was wrong
  against current versions. Every row above was re-measured.

## Verdict for us

**Present, never inject.** The agent's own `skills/` is the source; the adapter links each entry into the
one root its brain reads, inside the agent's home, and the brain's native discovery does the rest. This
feeds `provider-adapter` (a new variable naming the source) and `agent-home` (the agent's skills being its
own).

**The scope is the agent's home, and it needs no mechanism.** Because every brain discovers from the
directory it stands in, and a turn stands in its own agent's home, one agent cannot reach another's.
Measured across three agents and three brains: an agent granted one skill answered with that one, an
agent granted another answered with that other, and an agent granted nothing answered nothing — while a
skill in the library granted to no one was reached by no one.[14]

**The grant is the set of entries in that directory.** Not a record of one — the thing itself. It is
legible, diffable and revocable, and there is no second copy to disagree with it. An entry may be a real
directory or a symlink into a shared library, which is what makes reuse cost nothing.

**Isolating a vendor's home is not part of the design.** It works on two brains of three and is
impossible on the third, and it is the same act as logging an agent out. Recorded here as evidence for
`agent-home`'s open question about whether agents share the owner's sign-in — the answer now has numbers
against it — and as evidence that `RUNDESK_PROVIDER_HOME` is not where skills belong.

**What is not claimed.** Rundesk turns on no discovery of the owner's own skills, and cannot turn it off
either. `doctor` reports what is discoverable per brain rather than asserting a boundary we do not hold.

## Open questions

- Whether claude will ever expose a way to scope out user-level skills without removing its sign-in.
- What a skill should do when it must behave differently on one brain than another; no product surveyed
  scopes a skill by provider, and `compatibility` is advisory free text ignored by loaders.[1]
- Whether the git-root widening of the upward walk should be defended against or merely documented.
- Whether a shared library should eventually be managed by a verb or left as links an owner makes.

## Sources

1. Agent Skills — specification and overview — https://agentskills.io/specification
2. Claude Code — Skills — https://code.claude.com/docs/en/skills
3. OpenAI Codex — Skills — https://developers.openai.com/codex/skills
4. agentskills/agentskills issue 15 — the `.agents/` proposal — https://github.com/agentskills/agentskills/issues/15
5. Agent Skills — adding skills support to your agent — https://agentskills.io/client-implementation/adding-skills-support
6. Claude Code — Subagents — https://code.claude.com/docs/en/sub-agents
7. Hermes Agent — skills system — https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
8. Hermes Agent — profiles — https://hermes-agent.nousresearch.com/docs/user-guide/profiles/
9. OpenClaw — skills — https://docs.openclaw.ai/tools/skills
10. OpenClaw — skills configuration — https://docs.openclaw.ai/tools/skills-config
11. OpenCode — skills — https://opencode.ai/docs/skills/
12. Goose — using skills — https://goose-docs.ai/docs/guides/context-engineering/using-skills/
13. The Grok CLI's own shipped skills guide, `docs/user-guide/08-skills.md` inside its home — (internal)
14. Skill discovery, symlink, isolation and three-agent scope probes, run 2026-07-27 against claude 2.1.220, codex-cli 0.145.0 and grok 0.2.112 — (internal)
