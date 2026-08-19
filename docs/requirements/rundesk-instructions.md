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
  controlled. They define Rundesk, agent context, the universal process for working and owning an
  outcome, message and attachment mechanics, the current situation, and available named-agent
  delegation.
- Agent instructions are controlled per agent. They define that agent's durable role,
  responsibilities, role-specific capabilities and limits, and memory policy, but cannot override
  Rundesk operating instructions.
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
3. `Current Situation`
4. `Establish the Outcome`
5. `Boundaries`
6. `Messages and Attachments`
7. `Execute the Work`
8. `Maintain Continuity`
9. `Definition of Done`

`Team Members`, with its `Delegation` subsection, appears between `Maintain Continuity` and
`Definition of Done` only when named Rundesk delegation is available and the turn can review the
asynchronous result.

### Rundesk

One short definition identifies Rundesk as the operating layer for the agent, its home,
skills, conversations, schedules, and team delegation. It identifies the installation command
without expanding into agent behavior.

### Agent Context

This section makes clear that the context describes the agent itself. It identifies the agent,
home, and the comma-separated names of its active granted skills. It says that the separately
supplied agent instructions define role, responsibilities, capabilities, limits, and memory without
overriding the operating instructions.

It does not name provider-native instruction files or tell the agent to load instructions that the
provider loads automatically.

### Current Situation

Exactly one situation is rendered:

- Person: states that a person is available and permits clarification only when missing context,
  unclear scope or authority, or an unresolved decision prevents meaningful progress. A blocked
  agent names the blocker and the information or decision needed.
- Schedule: names the schedule, states that nobody is present, limits work to what the schedule
  requested, forbids waiting for clarification, and says the final standalone response is delivered
  automatically to the intended recipient or destination.
- Agent delegation: names the calling agent, requires the delegated work to be completed and
  verified within its outcome, scope, and authority, and returns results and evidence to that agent.
  It forbids contacting the original requester or delegating to another named Rundesk agent.

Unknown or omitted situations use the person-facing situation rather than silently adopting the
restrictions of a schedule or delegation.

### Establish the Outcome

This section makes the agent identify what must be produced, changed, decided, or reported, along
with the completion criteria and evidence. Required results remain distinct from assumptions,
optional ideas, and adjacent opportunities.

### Boundaries

This section makes the current request, schedule, or delegation the limit of scope and authority.
Project rules and adjacent findings constrain work but do not authorize more work. Material
expansion requires explicit authorization where the situation permits it and otherwise becomes a
reported blocker. The section also prohibits invented outcomes and exposure of sensitive data.

### Messages and Attachments

This section makes two high-failure mechanics explicit:

- When a request appears out of context or refers to prior work, decisions, or discussions that are
  not present, search all of the agent's message history across conversations before continuing or
  asking for clarification. The operating instructions include the executable form
  `"$RUNDESK_COMMAND" messages {agent_name} --search "<relevant words>" --full`.
- Attach a file or image with an absolute local Markdown link, such as
  `[report](/absolute/path/report.pdf)` or `![preview](/absolute/path/preview.png)`. A plain path is
  not represented as an attachment.

### Execute the Work

This section defines the universal working process: load the skills required by the work and project
depth, inspect existing work and constraints, break larger outcomes into ordered verifiable steps,
take the smallest complete set of actions, and adjust the approach when evidence requires it.

### Maintain Continuity

This section keeps the agent responsible for an outcome beyond one turn. The agent continues while
useful in-scope work remains. Before ending it either verifies completion, identifies the blocker,
or preserves status and a next action tied to a real event that will resume the work. Pending work is
never reported as complete.

### Team Members

This section briefly identifies the team members available for named Rundesk delegation, lists the
agents available to a person-facing turn, then places its operating guidance under a `Delegation`
subsection. That subsection explains how to choose an agent, hand over one bounded outcome with
`"$RUNDESK_COMMAND" ask <agent> "<task>"`, and avoid waiting for or duplicating active work. The
result returns in a review turn. The agent reviews and verifies that result before relying on it or
completing the larger outcome.

It is omitted for schedules because their asynchronous result cannot return to the same turn for
review. It is omitted for agent-to-agent delegations because named Rundesk delegation stops at one
level. An empty team also omits the section.

### Definition of Done

This final operating section permits a completion claim only after every requested result meets its
criteria, material claims and deliverables are verified, required asynchronous results are reviewed,
and no known required work remains. Otherwise the agent reports the outcome as pending or blocked
and preserves its continuation path.

## Agent instruction template

Rundesk ships one provider-neutral agent template at `src/templates/agent/AGENTS.md` and places its
bytes under both native instruction filenames. The runtime does not classify agents as domain or
specialist agents. Those terms may be used as behavior-design patterns when an owner molds an
agent's durable role through its instructions, description, skills, and delegation scope.

The template contains only `Agent Instructions`, `Role and Responsibilities`, and `Memory`. It
defines the agent's durable role, responsibilities, capabilities, limits, and memory policy without
repeating the operating outcome lifecycle. A new client, project, or assignment does not change the
agent instructions unless the owner is changing how that agent should operate across turns. The
separate `agent/MEMORY.md` template holds durable learned context such as preferences, traps,
gotchas, stable facts and references, and hard-won lessons without repeating agent instructions.

Agent creation, configuration, listings, and team context do not expose or depend on an agent-type
flag. Existing customized instruction files remain untouched. A legacy stored role column remains
in agent records for compatibility with immutable migration history, but current behavior does not
read or change it.

Every person-facing agent receives Team Members and Delegation whenever at least one eligible
teammate is available under its outbound delegation scope. A legacy role value never suppresses or
changes that section. The situation and delegation-depth exclusions defined above still apply.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-INS-1 | Operating and agent instructions have the separate ownership and precedence defined above | `src/rundesk/providers/instructions.py`, `src/skills/managing-rundesk/references/agent-instructions.md` |
| ✅ | R-INS-2 | Every prompt has the required operating sections once and in order | `test_the_always_on_sections_are_present_once_and_in_order` |
| ✅ | R-INS-3 | Every prompt has exactly one current situation, with person-facing behavior as the default | `test_every_turn_gets_exactly_one_current_situation`, `test_the_default_situation_is_person_to_agent` |
| ✅ | R-INS-4 | Team Members is present only for a person-facing turn with an available team | `test_team_members_are_only_composed_for_a_person_facing_turn`, `test_an_empty_team_has_no_heading_or_layer`, `test_a_schedule_is_not_shown_or_used_to_find_a_named_team` |
| ✅ | R-INS-5 | Operating prompts remain deterministic, inspectable, and bounded | `test_the_same_inputs_build_the_same_bytes`, `test_the_byte_breakdown_and_fingerprint_match_the_rendered_text`, `test_static_layers_and_the_maximum_prompt_stay_bounded` |
| ✅ | R-INS-6 | All agents start from one canonical template and public agent operations do not expose a type flag | `test_it_uses_the_single_agent_rules`, `test_role_is_not_an_add_option`, `test_role_is_not_a_configure_option`, `test_it_lists_all_agents_in_one_table` |
| ✅ | R-INS-7 | Legacy agent roles never suppress an otherwise eligible Team Members and Delegation section | `test_legacy_roles_do_not_remove_team_delegation_from_an_agents_instructions` |

## Acceptance

Automated acceptance tests enforce the required sections, ordering, situation composition, and layer
boundaries. They do not freeze editorial prose. Copy may be improved without rewriting tests as long
as the requirements and structural contract remain true.
