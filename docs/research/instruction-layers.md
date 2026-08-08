# How a system prompt was assembled, and the one rule the shape rested on

Distilled 2026-08-04 from the previous build's `instruction-layers.md` guide — gitignored,
reference-only, and expected to be deleted. The module it describes no longer exists and its
requirement ids are that build's, but the shape and the reasoning are architecture-independent, and
this build will have to decide the same thing the first time it composes anything to put in front of
a brain. What the two comparable products do about the same problem is in
[`2026-07-29-what-a-gateway-tells-its-agent.md`](2026-07-29-what-a-gateway-tells-its-agent.md); this
is what the previous build did about it.

Everything below is read off that build's own guide and its code. Nothing here was measured except
where a line says so.

---

## The shape

Everything a brain reads before it reads a word of the task was built by one composer. Every
execution got a core layer, then **exactly one** layer naming who asked.

```
CORE                       always, whatever this is and whoever asked
├── USER_TO_AGENT          a person sent this agent a message
│   ├── DIRECT_MESSAGE     …in a private conversation
│   ├── PUBLIC_ROOM        …in a room others read
│   └── ONBOARDING         …nobody has spoken yet
├── AGENT_TO_AGENT         another named agent asked
├── SCHEDULE_TO_AGENT      a schedule came due
└── AGENT_TO_ROLE          an agent put a role on
```

Then, in order, whatever the caller appended: the owner's own instructions, an adapter's, a
schedule's. Every one of those appends and none of them replaces an earlier layer.

**A trigger belongs to exactly one layer, and a person is the answer for anything not named.** A
surface this release has never heard of is somebody typing; what the other three layers withhold are
the rules that assume somebody is waiting. So an unclassified trigger is given a person's rules, and
one of the others only by being named. That is the safe way round, and it is the kind of default
that is easy to get backwards.

---

## The one rule: the core carries no identity

The role layer received the core layer, and a role execution has no home, no memory, no voice, no
channels and no product to operate. **So anything identity-bearing that leaks into the core is
handed straight to a role execution.** The core was therefore small, and only what is true of every
execution:

- you are running inside this product;
- never invent a fact, path, flag or command you have not confirmed exists;
- never put a secret in a file, a log, a commit or your output — refer to it by name;
- never dress a failure as progress: say what you verified and how, and what you did not do;
- where you are blocked, say so and stop, naming the action and what it was for.

The core **may never contain** a home path, the names of the files an agent lives by, memory, voice,
attachments, channels, schedules, roles, the product's own commands, or history recovery.

Three of the four layers are a named agent and each needed the same identity text, so that was
written once as one fragment and composed into those three. **The role layer never includes it — not
conditionally, structurally**: the role layer is reached *instead of* the agent one, so there is no
branch anybody can get wrong. That distinction is the whole safety of the design, and it is what let
the previous build reverse an earlier decision (that the role composer must refuse to call the
shared one) without reintroducing the leak.

The safety of that reversal was one test, and it is the test to keep: **a role execution's
instructions name no home, no memory file, no identity file, no channel, no schedule, no attachment
rule and no product command** — asserted by searching the built string for each of those, never by
reading the composition back.

---

## Two things that moved, and why

**Recovering work somebody referred to, and handing heavy work to a specialist, are person-only.**
Both sat in the layer every turn read, so a delegation preface carried each of them beside the
paragraph forbidding it. Proved on a live install rather than reasoned about. They belong to the
person layer because that is where they were always true: history recovery needs a person to have
referred to something, and work handed to a specialist reports back in a *later* turn, which only
helps where there will be one somebody is waiting in.

**A scheduled run receives neither**, and that is the taxonomy holding rather than an oversight —
nobody is present.

**Where an ordering must survive.** The role layer was in two parts because the role's own locked
rules sat *between* them, spliced byte for byte with nothing filled into them:

```
CORE
AGENT_TO_ROLE            whose behalf, what you are not, how far authority reaches
<the role's locked rules, byte-identical>
AGENT_TO_ROLE_TASK       this run, this target, this workspace, what the report must contain
```

A role that receives its own rules *after* the task details, or with a substitution made in them, is
a different run from the one that was admitted.

---

## The rules a later layer is checked against

- **Ask which single layer a new rule is true of.** If the answer is "more than one", it belongs in
  the shared fragment or in the core — never copied into two.
- **Adding a top-level layer means saying which triggers reach it**, whether it composes the agent
  identity fragment, and whether the listing of what an agent may hand work to lands beside it.
- **Emit an environment fact only when the environment is non-default**, rather than asserting it
  always. The previous build's core stated that the workspace had no git repository, which was true
  when it was written and is not a thing to assert unconditionally.
- **Channel-shaped rules do not belong in the invariant core.** Both comparable products place
  formatting and silence rules per surface; the previous build stated a mobile-reply rule in the
  layer that was also told to a terminal turn and to a scheduled run reporting into a log.
- **Substitute by hand, not through `str.format`.** Owner text arrives with braces in it eventually,
  and `str.format` raises mid-turn when it does.
- **Bound each externally supplied layer at ingestion and never clip the finished stack**, because
  clipping the whole silently drops whichever later append-only layers fell past the boundary.
- **Keep the invariant part invariant, because prefix caching pays for it.** Both comparable
  products let cache economics decide the physical ordering of sections, and one of them keeps a
  literal marker in the prompt naming the boundary. Whatever this build does, which tier a fragment
  belongs to should be a decision the code records rather than one each new fragment re-litigates.
- **Nothing reaches a brain that the run's account does not show**, including anything the product
  itself added. Text put into a turn and left out of the record makes the record a lie, and it is
  invisible precisely because it *is* the record.

---

## What to keep proving

Two checks, and neither is optional if this build grows a composer.

**Prove what did not change.** The previous build kept a captured file holding every preface the
composer had built *before* the layers were named, captured once and never regenerated from the code
it guards. A test that rebuilt its own expectation would agree with any change at all. Rebuild each
preface, undo only the differences that were asked for, and compare whole.

**Prove the leak cannot come back.** The role-execution search above, plus an assertion that no
substitution placeholder of any kind appears in the core.
