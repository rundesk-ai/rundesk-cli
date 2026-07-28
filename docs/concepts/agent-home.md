---
title: The agent home
description: Four markdown files decide who an agent is, who it works for, and what it has learned.
sidebar:
  order: 2
---

Every agent gets its own home directory. Four markdown files in it are loaded before anything
is asked of the agent, and together they are the whole of its continuity — an agent starts
fresh every session, and these files are what survives.

```text
AGENTS.md    the operating rules, loaded before anything is asked
SOUL.md      who the agent is and how it works — wins on conflict
USER.md      who it works for and how they want to be answered
MEMORY.md    what it has learned that is still true
```

`CLAUDE.md` sits alongside them and points at `AGENTS.md`, because no provider reads another
provider's filename.

## Why four files and not one

Each answers a different question, and they change on different schedules.

| File | Question | Changes |
|---|---|---|
| `AGENTS.md` | How does work get done here? | Rarely — it is the contract |
| `SOUL.md` | Who is this agent? | Rarely, and never without telling the owner |
| `USER.md` | Who is it for? | When you learn something about the person |
| `MEMORY.md` | What is true right now? | Constantly |

`SOUL.md` wins on conflict. When `USER.md`, `MEMORY.md`, or a request contradicts it, the
agent holds the line and says why rather than drifting.

## The test for a memory line

`MEMORY.md` fills up with narration unless something stops it. A line earns its place only
when all four hold:

1. **Durable** — still true next week.
2. **Learned** — the agent found it out; it isn't already in these files.
3. **Load-bearing** — the agent would act differently next session for knowing it.
4. **Theirs to keep** — no secrets, no raw dumps, nothing they were asked to forget.

Decisions, constraints, preferences, and open loops qualify. Narrating a session does not.
A line gets deleted the moment it stops being true.

The practical shape is four sections — **Decisions**, **Constraints**, **Preferences**, and
**Open loops** — with the last one meant to empty out.

## Keeping it honest

Two files, two jobs, and every fact has exactly one home: `USER.md` for facts about the
person, `MEMORY.md` for facts about the work. Lines added to `USER.md` are dated, so the
owner can see what the agent concluded about them and correct it.

A long memory file is one nobody has pruned. Under 50 lines is the working limit; past that,
consolidate before adding.
