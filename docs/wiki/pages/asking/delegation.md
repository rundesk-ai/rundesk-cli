+++
title = "Delegation"
subtitle = "one agent's brief to another, the order it is written, and how an answer settles"
status = "draft"
intent = """
Delegation exists so that an agent can hand a piece of work to a named agent and get an answer back into
its own conversation. Work handed over should always come back or be recorded as stopped, and a chain of
agents asking each other should be impossible to build.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk asked show, say, stop, resume", cite = "commands" },
  { label = "Delegation name", value = "del-<parent turn>-<six hex characters>", cite = "admission" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Task limit", value = "16 kB", cite = "admission" },
  { label = "Briefs answered a pass", value = "4", cite = "settling" },
  { label = "Answers collected a pass", value = "4", cite = "settling" },
  { label = "Progress notice", value = "every 20 minutes", cite = "notices" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "An agent delegating to itself", value = "refused", cite = "admission" },
  { label = "A turn already answering a brief", value = "may not delegate", cite = "admission" },
]
+++

An agent hands work to another by running `rundesk ask` from inside its own turn.[^handed] Everything else
about a turn is described on [asking](../asking.md); this page covers the brief, the row that records it
and the answer that settles it.

## Admission

Every ask from inside a turn takes the delegation path, including one naming the agent itself, so the
guard against an agent delegating to itself cannot be stepped around.[^route] A turn that is already
answering a brief may not delegate.[^admission] Those two refusals together make a cycle impossible to
build at the first step.[^admission]

The asking agent's own delegation scope decides the target: any agent, no agent, or an exact
list.[^scope] A gateway that is definitely offline refuses the hand-over; one whose state cannot be read
does not.[^handed] The brief is capped at 16 kB, and the delegation is named `del-` followed by the
asking turn and six hex characters.[^admission]

## A hand-over that fails

**A hand-over that dies halfway hands over nothing.**[^handed] The brief reaches the answering agent before the
asking agent records that it is owed an answer, so the only half-done state is one where no agent is
looking for work and no agent is waiting for it.[^handed]

## Settling

The [gateway](../gateways.md) runs three sweeps each pass.[^settling] It answers briefs handed to its own
agent, at most four; it collects answers owed to its agent, at most four; and it offers again an answer
already recorded that no turn has read, at most two.[^settling]

An answer is the last message of the terminal turn that answered the newest thing the asking agent
said.[^settling] A failed turn still answers.[^settling] A turn that finished saying nothing is reported
with its status rather than as silence.[^settling] A stop the asking agent requested settles without being
reviewed.[^settling]

The answer is delivered into the asking agent's own conversation first, and only then recorded as
answered, under the install lock and against the same answer.[^settling] Settlement follows the record
rather than the turn: an answer that is durably the asking agent's has come back, even when no turn has
read it yet.[^settling]

## Steering

`rundesk asked` lists what this agent handed over, and shows, steers, stops or carries on one of
them.[^commands] Guidance given mid-flight is carried in a field of its own rather than joined to the
person's words.[^steering]

## Notices

A room hears four standings — handed over, still working, came back and stopped — said once each while
true, and three events — guided, stopping and carried on — said once each time they happen.[^notices] A
delegation still running says so every 20 minutes.[^notices]

[^commands]: `src/rundesk/commands/asked.py` — `register()` declares `show`, `say`, `stop` and `resume`,
    and `cmd_asked()` lists when no verb is named.
[^handed]: `src/rundesk/commands/ask.py` — `_handed_over()` reads the scope, collapses the gateway
    standing so only a definitely-offline gateway refuses, writes the brief with
    `arriving.recorded_for_a_delegation()` and then the row with `admitting.admitted()`, and its comment
    gives the reason for that order.
[^route]: `src/rundesk/commands/ask.py` — `cmd_ask()` routes every ask made from inside a turn through
    `_handed_over()`.
[^admission]: `src/rundesk/delegations/admitting.py` — `refusal()` refuses an agent delegating to itself
    and a turn already answering one, `a_name()` mints the name from `NAMED` and `MARK_CHARACTERS`, and
    `A_TASK_AT_MOST` caps the brief.
[^scope]: `src/rundesk/agents/delegating.py` — `decoded()` reads the three states and `allows()` decides
    one target.
[^settling]: `src/rundesk/delegations/hosting.py` — `_answered_what_was_handed_here()`,
    `_collected_what_came_back()` and `_reviewed_what_was_recorded()`, bounded by `STARTED_AT_MOST`,
    `COLLECTED_AT_MOST` and `REVIEWED_AT_MOST`; `_what_they_answered()` reads the terminal turn's last
    message; the docstring states that settlement follows the record rather than the turn.
[^steering]: `src/rundesk/providers/protocol.py` — `build_say_line()` carries guidance in
    `STEERING_CONTEXT` rather than joining it to the person's words.
[^notices]: `src/rundesk/delegations/hosting.py` — `STANDS`, `HAPPENED` and `STILL_WORKING_EVERY`.
