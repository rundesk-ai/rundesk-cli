+++
title = "Asking"
subtitle = "one question to one agent, what the agent is told, and the record left behind"
status = "draft"
intent = """
Asking exists so that a person, a schedule and a channel all reach an agent the same way, and so that what
an agent did can be read back later. A question should never be silently dropped, and an agent should
never be answering two things at once in the same conversation.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk ask, turns, messages, search", cite = "commands" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Added instructions", value = "4000 characters each", cite = "instructions" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "A second question in one conversation", value = "refused, never queued", cite = "claim" },
  { label = "A turn that began", value = "always settles", cite = "settle" },
  { label = "A turn that said nothing", value = "recorded as failed", cite = "settle" },
]
+++

`rundesk ask <agent> <prompt>` puts a question to an [agent](agents.md) and prints the answer as it
arrives.[^commands] A question from a [channel](channels.md) and one from a [schedule](schedules.md) take
the same path, so all three behave alike.[^onepath] An agent asking another agent is described on
[delegation](asking/delegation.md).

## Claim

**An agent answers one thing at a time in one conversation.**[^claim] A second question arriving while the
first is still running is refused outright rather than queued, so a person is told to wait instead of being left
wondering.[^claim]

The question can be stopped from the moment it is accepted, not from the moment the model starts, so a
question that is still choosing a model can still be called off.[^claim] The name typed is matched to the
agent this install holds before any other step reads it, so a difference of capital letters reaches the
agent the person meant.[^resolve]

## Instructions

An agent is told the same things every turn: a core, where the question came from, its own operating
rules, its team, and whatever the caller adds, with each addition capped at 4000 characters.[^instructions]

A turn records a fingerprint of those instructions rather than their text.[^instructions] **The previous
session is picked up again only while that fingerprint has not moved** — so changing an agent's
instructions starts it fresh rather than leaving it half-guided by rules it can no longer see.[^instructions]

## Settling

The turn is written down before the model starts, and the question is recorded before it is sent, so work
that dies mid-flight still leaves a trace of what was asked.[^admit]

**A turn that began always settles.**[^settle] Settling writes the reply into the conversation, keeps the
session handle when the adapter offers one, and records what the turn cost.[^settle] A turn that reported
success while saying nothing is recorded as a failure, because an empty answer is not an
answer.[^settle]

## History

`rundesk turns` shows what one turn did, `rundesk messages` what was said in an agent's conversations, and
`rundesk search` asks the platforms the agent is connected to.[^commands]

[^commands]: `src/rundesk/commands/ask.py`, `src/rundesk/commands/turns.py`,
    `src/rundesk/commands/messages.py` and `src/rundesk/commands/search.py` — `register()` in each.
[^onepath]: `src/rundesk/providers/turns.py` — `run()`; `src/rundesk/providers/answering.py` —
    `OnAChannel` and `OnASchedule` reach the same function.
[^resolve]: `src/rundesk/agents/directory.py` — `known_as()` resolves a name differing in ASCII case,
    called by `cmd_ask()` in `src/rundesk/commands/ask.py` before anything is decided.
[^claim]: `src/rundesk/providers/turns.py` — `claiming()` takes the exclusive lock and raises `Busy`
    rather than waiting, and `_stoppable()` publishes the turn from the claim.
[^instructions]: `src/rundesk/providers/instructions.py` — `build()` composes the core, the situation,
    the operating rules, the team and the caller's additions, and `AN_ADDITION_AT_MOST` caps each one;
    `src/rundesk/providers/turns.py` — `_admit()` drops the session when the fingerprint has moved.
[^admit]: `src/rundesk/providers/turns.py` — `_admit()` writes the turn row before the adapter starts,
    and `_the_brain()` records the prompt before sending it.
[^settle]: `src/rundesk/providers/turns.py` — `_became()` writes the reply, keeps the session and fills
    the settled columns, treating a success that said nothing as failed, and
    `_settled_whatever_happens()` guarantees the row is settled.
