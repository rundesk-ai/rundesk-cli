---
name: write-a-skill
description: How to write a skill an agent's brain will actually pick up, where it lives in rundesk, and how to give one to an agent.
---

# Write a skill

A skill is a folder holding a `SKILL.md`. Every brain rundesk ships behind reads it —
`claude`, `codex` and `grok` all index the same file unchanged — and each **discovers it
by itself**. Rundesk never reads a skill and never puts one in a prompt.

That last point is the design, not an implementation detail. Injecting a skill's text
would charge every turn for every skill whether it was relevant or not, put rundesk in the
business of deciding relevance, and break `R-PRV-5`, which requires everything added to a
turn to appear in that turn's account.

## Where a skill lives

```
~/.rundesk/data/skills/<name>/SKILL.md      the library — every skill on the machine
~/.rundesk/data/agents/<agent>/home/skills/ what that agent was given: a link each
```

Write it into the library, then give it to an agent:

```sh
mkdir -p ~/.rundesk/data/skills/release-notes
$EDITOR ~/.rundesk/data/skills/release-notes/SKILL.md
rundesk skills grant ava release-notes
rundesk skills                                # who has what, and where each came from
```

**The grant is the link, not a record of one.** `ls` reads it and `rm` revokes it, and
there is no second copy that could disagree with what a brain will actually find. That
matters because rundesk does not load skills — the brain does — so the only thing with any
force is what is standing in the agent's directory before the brain runs. A rule in a
configuration file would describe what rundesk placed while the brain read on.

A grant is a link, so editing the library edits what every agent holding that skill reads,
with nothing to re-run.

## What ships, and what is yours

Skills under `src/templates/skills/` in this repository are **built in**. The install lays
them down in the library, and `rundesk update` brings them forward to whatever the new
release ships. `rundesk skills` marks them `built-in`.

**An update overwrites a built-in**, because that is what makes it rundesk's to improve.
To customise one, copy it under a different name — that copy is yours, is marked `yours`,
and is never touched.

This is deliberately different from the agent templates (`R-AGT-23`), which are seeds
copied once and the owner's forever. A template is a starting point; a built-in skill is
product content.

## The format

```markdown
---
name: release-notes
description: How this team writes release notes. Use when asked to draft, review or edit
  release notes, a changelog, or a version announcement.
---

# Release notes

<the body>
```

Use `name` and `description` and nothing else. Other keys exist and differ between brains,
and one brain silently dropping a skill over a key another accepts is not worth it.

- `name` matches the folder exactly: lowercase letters, digits and single hyphens, at most
  64 characters — the tightest of the three brains, not ours.
- `description` is at most 1024 characters.

`rundesk skills grant` checks all of this and refuses rather than placing something a
loader would skip in silence.

## Writing one

The rules are not ours either — they are what four independent bodies of guidance agree
on, and they are recorded with sources in
[`../research/2026-07-27-authoring-a-skill.md`](../research/2026-07-27-authoring-a-skill.md).
The short form:

- **The description is the whole of what triggers it.** Say what it does *and* when to use
  it, name the situations, and lean pushy — brains under-trigger far more than they
  over-trigger. A "when to use this" heading in the body is read only after the decision
  it would inform has been made.
- **Assume the model is capable.** Would it get this wrong without the line? If not, cut
  it. A skill is what it does not already know.
- **Gotchas earn their place first** — the facts that defy a reasonable assumption, and
  they stay in the body, because a model cannot know to go and read a file about a trap it
  does not know exists.
- **Under 500 lines.** Once loaded, a skill stays in context, so every line is paid for
  repeatedly. Overflow goes in `references/` and each one is introduced by *when to read
  it*.
- **Never** a `README.md`, a changelog, credentials, machine-specific paths, or anything
  already in `AGENTS.md`, `SOUL.md` or `MEMORY.md`.

The shipped `writing-skills` skill teaches this to agents, and obeys every rule in it.

## Proving one works

**Run it without the skill first.** Without that baseline a pass says nothing — the model
may simply have known. Then grant it and ask again, in a fresh session, in the words
somebody would really use, without mentioning the skill, for something only the skill can
supply.

Two traps this repository has already paid for:

- Never ask something the conversation could already answer. The model answers from
  earlier in the thread and the skill looks like it worked.
- A trivial one-step request triggers no skill however good the description, because a
  brain only reaches for one on work it cannot easily do unaided.

`.knowledge/scripts/probe-skills` does this against the installed CLIs. Its `--offline`
half costs nothing: `grok inspect --json` and codex's `skills/list` both report what they
discovered without a turn.

## Which brain reads where

Measured 2026-07-27, and re-measured when a version moves — the full table with versions
is in [`../research/2026-07-27-skills-a-brain-discovers.md`](../research/2026-07-27-skills-a-brain-discovers.md).

| Brain | Reads, relative to the directory a turn stands in |
|---|---|
| `claude` | `.claude/skills` and nothing else |
| `codex` | `.agents/skills` and `.codex/skills` |
| `grok` | `.grok`, `.agents`, `.claude` and `.cursor` skills |

**A bare `skills/` is read by nobody**, which is why the agent's own `skills/` is a source
that adapters present from rather than something a brain finds.

Each adapter links what its agent was given into its own root, inside the agent's home. An
adapter author does not need this table: they are told `RUNDESK_SKILLS` and place from it
wherever their brain looks — see
[`write-a-provider-adapter.md`](./write-a-provider-adapter.md).
