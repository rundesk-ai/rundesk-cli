---
name: instruction-layers
description: How a system prompt is assembled — the four layers, what may go in each, and the one rule the whole shape rests on.
---

# Instruction layers — how a system prompt is assembled

Everything a brain reads before it reads a word of the task is built by one composer in
`src/rundesk/instructions.py`. This says what the layers are, what belongs in each, and what
must never leak between them. A layer added later is checked against this rather than merely
fitting in.

## The shape

Every execution gets `CORE_INSTRUCTIONS`, then **exactly one** layer naming who asked.

```
CORE_INSTRUCTIONS          always, whatever this is and whoever asked
├── USER_TO_AGENT          a person sent this agent a message
│   ├── DIRECT_MESSAGE     …in a private conversation        (appended to USER_TO_AGENT only)
│   ├── PUBLIC_ROOM        …in a room others read            (appended to USER_TO_AGENT only)
│   └── ONBOARDING         …nobody has spoken yet            (appended to USER_TO_AGENT only)
├── AGENT_TO_AGENT         another named agent asked
├── SCHEDULE_TO_AGENT      a schedule came due
└── AGENT_TO_ROLE          an agent put a role on
```

Then, in order, whatever the caller appends: the owner's own instructions, an adapter's, a
schedule's.

**A trigger belongs to exactly one layer, and a person is the answer for anything not named.**
A surface this release has never heard of is somebody typing; what the other three layers
withhold are the rules that assume somebody is waiting, so an unclassified trigger is given a
person's rules and one of the others only by being named. That is the safe way round.

## The one rule: CORE carries no identity

`AGENT_TO_ROLE` receives `CORE_INSTRUCTIONS`, and a role execution has no home, no memory, no
voice, no channels and no Rundesk to operate. **Anything identity-bearing that leaks into the
core is handed straight to a role execution**, which is the failure R-ROL-5 was written to
prevent.

CORE is therefore small, and is only what is true of every execution:

- You are running inside Rundesk.
- Never invent a fact, path, flag or command you have not confirmed exists.
- Never put a secret in a file, a log, a commit or your output — refer to it by name.
- Never dress a failure as progress. Say what you verified and how, and what you did not do.
- Where you are blocked, say so and stop, naming the action and what it was for.

**CORE may never contain** a home path, the three home files, `MEMORY.md`, `SOUL.md` or voice,
attachments, channels, schedules, roles, `rundesk` commands, or history recovery.

## The shared agent fragment

Three of the four layers are a named agent, and each needs the same identity text — home, the
three files, memory, voice, attachments, operating Rundesk, and the roles listing. That is
written once as `AGENT_IDENTITY` and composed into those three. A list written twice is a list
that disagrees with itself, and this one is long.

`AGENT_TO_ROLE` never includes it. **Not conditionally — structurally**: the role layer is
reached *instead of* the agent one, so there is no branch anybody can get wrong.

The roles listing is the same idea one step along. It lands beside the fragment where there is
something to list, and never at all under `AGENT_TO_AGENT`, whose own text forbids putting a
role on one paragraph later.

### Why the two person-only bullets moved

Recovering work somebody referred to, and handing heavy work to a role, both sat in the layer
every turn read. A delegation preface therefore carried each of them beside the paragraph
forbidding it — proved on a live station, not reasoned about. They are `USER_TO_AGENT`'s now,
because that is where they were always true: history recovery needs a person to have referred
to something, and a role reports back in a *later* turn, which only helps where there will be
one somebody is waiting in.

**A scheduled run no longer receives either.** That is the taxonomy holding rather than an
oversight: nobody is present, and `SCHEDULE_TO_AGENT` still says how to report a role handoff
while the roles listing beside the fragment still says which roles exist and how to run one.

## AGENT_TO_ROLE, and the ordering that must survive

The layer is in two parts, because the role's own locked `AGENTS.md` sits **between** them and
is spliced byte for byte with nothing filled into it (R-ROL-10):

```
CORE_INSTRUCTIONS
AGENT_TO_ROLE            whose behalf, what you are not, how far authority reaches
<the role's locked AGENTS.md, byte-identical>
AGENT_TO_ROLE_TASK       this run, this target, this workspace, what the report must contain
```

A role that receives its own rules after the task details, or with a substitution made in them,
is a different run from the one that was admitted.

## What R-ROL-5 says now

`for_role()` used to refuse to call `build()`, and R-ROL-5 gave the reason: the two orders were
written apart rather than one being the other with layers removed, "which is the shape that
quietly grows a leak back in".

**The owner decided to standardise on one composer.** That is a real reversal, and it is only
safe because CORE carries no identity — there is nothing left to leak, and the role layer is
reached instead of the agent fragment rather than by stripping it. R-ROL-5 now reads: a role
execution receives the core layer and its own, and never the agent fragment.

The whole safety of that reversal is one test, and it must keep existing:

> **A role execution's instructions name no home, no `MEMORY.md`, no `SOUL.md`, no channel, no
> schedule, no attachment rule and no `rundesk` command** — asserted against the built string
> by searching for each of those, never by reading the composition back.

## Changing any of this

Two checks, and neither is optional.

1. **Prove what did not change.** `tests/samples/instructions-before-the-layers-were-named.json`
   holds every preface this composer built before the layers existed, captured once and never
   regenerated from the code it guards. A test that rebuilt its own expectation would agree with
   any change at all. Rebuild each preface, undo only the differences the owner asked for, and
   compare whole.
2. **Prove the leak cannot come back.** The role-execution search above, and the assertion that
   no `STANDARD_VARIABLES` or `ROLE_VARIABLES` placeholder appears in CORE.

Adding a fifth top-level layer means saying which triggers reach it, whether it composes
`AGENT_IDENTITY`, and whether the roles listing lands beside it. Adding a rule means asking
which single layer it is true of — and if the answer is "more than one", it belongs in the
fragment or in CORE, not copied.
