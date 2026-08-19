---
id: INS
name: Rundesk operating and agent instructions
last_verified: 2026-08-19
---

## What this is

Rundesk gives every turn a small product-owned operating layer, then lets the agent's own
instructions define who that agent is. The layers have separate owners and responsibilities so an
agent receives the context it needs without reading the same rules twice.

## Instruction ownership

- Rundesk operating instructions are product-owned, apply to every agent, and are not user
  controlled. They define Rundesk, agent context, universal operating rules, message and attachment
  mechanics, the current situation, and available named-agent delegation.
- Agent instructions are controlled per agent. They define that agent's role, behavior, working
  method, and memory policy, but cannot override Rundesk operating instructions.
- Project instructions apply only while work is being done in that project. They define local
  conventions and constraints without redefining the agent or Rundesk.
- Skills provide task-specific procedures and are supplied by the runtime. Their contents are not
  copied into the operating instructions.
- The current assignment supplies the immediate outcome and authority. It does not become durable
  agent behavior merely because it appeared in a turn.

Rundesk must not duplicate agent, workspace, skill, or memory instructions in its operating layer.
Providers may load those layers through their native instruction mechanisms.

## Operating instruction structure

Every rendered operating prompt contains these sections once and in this order:

1. `Rundesk`
2. `Agent Context`
3. `Core Rules`
4. `Messages and Attachments`
5. `Current Situation`

`Team Members` follows `Current Situation` only when named Rundesk delegation is available and the
turn can review the asynchronous result.

### Rundesk

One short definition identifies Rundesk as the operating layer for the agent, its workspace,
skills, conversations, schedules, and team delegation. It identifies the installation command
without expanding into agent behavior.

### Agent Context

This section makes clear that the context describes the agent itself. It identifies the agent,
home, workspace, and runtime-provided skills, and says that the separately supplied agent
instructions define role, behavior, and memory without overriding the operating instructions.

It does not name provider-native instruction files or tell the agent to load instructions that the
provider loads automatically.

### Core Rules

The opening sentence tells the agent to follow the operating rules and its agent instructions before
acting. The section supplies only universal boundaries: remain within scope and authority, respect
the situation, do not invent or expose secrets, disclose incomplete work and blockers, inspect
relevant state, take only necessary actions, and verify completion.

Role-specific behavior, access modes, memory policy, and development-only process do not belong in
this section.

### Messages and Attachments

This section makes two high-failure mechanics explicit:

- When a request appears out of context or refers to prior work, decisions, or discussions that are
  not present, search the agent's messages before continuing or asking for clarification. The
  operating instructions include the executable form
  `"$RUNDESK_COMMAND" messages {agent_name} --search "<relevant words>" --full`.
- Attach a file or image with an absolute local Markdown link, such as
  `[report](/absolute/path/report.pdf)` or `![preview](/absolute/path/preview.png)`. A plain path is
  not represented as an attachment.

### Current Situation

Exactly one situation is rendered:

- Person: identifies the current conversation as the response path, makes the current request the
  source of scope and authority, and permits a focused question only when a missing decision blocks
  safe progress.
- Schedule: names the schedule, states that nobody is present, limits work to what the schedule
  requested, forbids waiting for clarification, and says the final standalone response is delivered
  automatically to the intended recipient or destination.
- Agent delegation: names the calling agent, limits work to the delegated authority, returns
  results and evidence to that agent, and leaves integration and final communication with the
  caller. It forbids contacting the original requester or delegating to another named Rundesk agent,
  while allowing bounded use of provider-local subagents.

Unknown or omitted situations use the person-facing situation rather than silently adopting the
restrictions of a schedule or delegation.

### Team Members

This section lists the named Rundesk agents available to a person-facing turn and explains how to
choose one, hand over one bounded assignment with `"$RUNDESK_COMMAND" ask <agent> "<task>"`, avoid
waiting for or duplicating active work, and review the result before relying on it.

It is omitted for schedules because their asynchronous result cannot return to the same turn for
review. It is omitted for agent-to-agent delegations because named Rundesk delegation stops at one
level. An empty team also omits the section.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-INS-1 | Operating and agent instructions have the separate ownership and precedence defined above | `src/rundesk/providers/instructions.py`, `src/skills/managing-rundesk/references/agent-instructions.md` |
| ✅ | R-INS-2 | Every prompt has the required operating sections once and in order | `test_the_always_on_sections_are_present_once_and_in_order` |
| ✅ | R-INS-3 | Every prompt has exactly one current situation, with person-facing behavior as the default | `test_every_turn_gets_exactly_one_current_situation`, `test_the_default_situation_is_person_to_agent` |
| ✅ | R-INS-4 | Team Members is present only for a person-facing turn with an available team | `test_team_members_are_only_composed_for_a_person_facing_turn`, `test_an_empty_team_has_no_heading_or_layer`, `test_a_schedule_is_not_shown_or_used_to_find_a_named_team` |
| ✅ | R-INS-5 | Operating prompts remain deterministic, inspectable, and bounded | `test_the_same_inputs_build_the_same_bytes`, `test_the_byte_breakdown_and_fingerprint_match_the_rendered_text`, `test_static_layers_and_the_maximum_prompt_stay_bounded` |

## Acceptance

Automated acceptance tests enforce the required sections, ordering, situation composition, and layer
boundaries. They do not freeze editorial prose. Copy may be improved without rewriting tests as long
as the requirements and structural contract remain true.
