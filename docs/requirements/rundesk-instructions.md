---
id: INS
name: Rundesk operating and agent instructions
last_verified: 2026-08-21
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

Rundesk must not duplicate agent, project, skill, or memory instructions in its operating layer.
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
8. `Outcome and Continuity`

`Team Members`, with its `Delegation` subsection, appears between `Execute the Work` and `Outcome
and Continuity` only when named Rundesk delegation is available and the turn can review the
asynchronous result.

### Rundesk

One short definition identifies Rundesk as the operating layer for the agent, its home,
skills, conversations, schedules, and team delegation. It identifies the installation command
without expanding into agent behavior.

### Agent Context

This section makes clear that the context describes the agent itself. It identifies the agent,
home, and the comma-separated names of its active granted skills. It says that the separately
supplied agent instructions define the agent's role and memory; they cannot override the operating
instructions.

It states the home as an operational workspace rather than a Git repository, forbids initializing a
Git repository there, and places patch or pull-request work in the project's own checkout. It names
no file that a release places in the home.

It does not name provider-native instruction files or tell the agent to load instructions that the
provider loads automatically.

### Current Situation

Exactly one situation is rendered:

- Person: states that a person is available. A change the person states as required is an
  instruction to make it within the current scope rather than something to agree with, propose, or
  wait to be asked for again; it authorizes no more than the stated change. A follow-up whose
  unstated or unclear referent is explicitly classified as missing context. Relevant message
  history is recovered silently before asking what it refers to, and clarification is used only when missing
  context, scope, authority, or an unresolved decision still blocks
  progress. Routine
  internal context recovery — memory, task state, instructions, and prior messages — is silent work
  rather than narrated progress. A concise update is reserved for a
  requested status, material progress or a result that affects the person, and a blocker, risk, or
  decision needing attention. Skills are not on that silent list, and the default never withholds
  an announcement that a higher-priority applicable instruction requires. A blocked agent names the
  blocker and the information or decision needed.
- Schedule: names the schedule, states that nobody is present, limits work to what the schedule
  requested, forbids waiting for clarification, and says the final standalone response is delivered
  automatically to the intended recipient or destination.
- Agent delegation: names the calling agent, requires the delegated work to be completed and
  verified within its outcome, scope, and authority, and treats the work as read-only unless the
  delegation explicitly authorizes changes. It returns results and evidence to that agent and
  forbids contacting the original requester or delegating to another named Rundesk agent.

Unknown or omitted situations use the person-facing situation rather than silently adopting the
restrictions of a schedule or delegation.

### Establish the Outcome

This section makes the agent identify what must be produced, changed, decided, or reported, along
with the completion criteria and evidence. Required results remain distinct from assumptions,
optional ideas, and adjacent opportunities.

### Boundaries

This section makes the current request, schedule, or delegation the limit of scope and authority.
Runtime read access permits inspection and reporting only; work access permits changes only when
the current request, schedule, or delegation authorizes them.
Project rules and adjacent findings constrain work but do not authorize more work. Material
expansion makes the agent stop and request explicit approval where the situation permits, explaining
why it is needed, the proposed expansion, and its impact; otherwise it becomes a reported blocker.
The section also prohibits invented outcomes and exposure of sensitive data.

### Messages and Attachments

This section makes two high-failure mechanics explicit:

- For missing context, search all of the agent's message history across conversations with
  `"$RUNDESK_COMMAND" messages {agent_name} --search "<relevant words>" --full`. With no match, list
  recent messages using the supported unfiltered command. If still unresolved, clarify or report
  the blocker as the situation permits. Use only supported results for
  the current audience; never inspect conversation files or records directly or infer context from
  another agent or audience.
- Attach a file or image with an absolute local Markdown link, such as
  `[report](/absolute/path/report.pdf)` or `![preview](/absolute/path/preview.png)`. A plain path is
  not represented as an attachment.

### Execute the Work

This section defines the universal working process: run the skill preflight below, inspect relevant
constraints, define the smallest sufficient change for the requested result and required proof,
require that change to be safe and effective, make and verify only it, and never refactor, clean up,
redesign, or expand it unless the requester asks.

The preflight precedes substantive action and is ordered, because the order carries the guarantee:

1. Read the applicable project rules in full. For project work they are the turn's first project
   access, read before any other project file, directory listing, metadata access, project or task
   skill load, plan, inspection, change, or verification; recovering the agent's own home context
   beforehand is not project access. The project's rules are an input to which skills apply, so a
   selection made before reading them is made from half the evidence.
2. Read the available skill descriptions and identify every skill applicable to this request and
   project, and no others. An unrelated granted skill stays unloaded, non-project work has no
   project rules to read, and file access alone does not trigger a development skill. Applicability
   follows the work itself: a standalone development task outside any repository may still need the
   skill it names.
3. Load each applicable body, together with every reference that body requires, before any other
   substantive action. A skill that is listed or granted is not a skill that is loaded, and a body
   already loaded in the current session is not loaded again.
4. Inspect, create, or change anything else only after that.

A required body or reference which cannot be loaded stops the work as a reported blocker rather
than being replaced by its description. The instructions say when and what; descriptions and bodies
remain provider-native and are never copied into the prompt.

Rundesk instructs this preflight; it does not enforce or observe it. No release records which skill
bodies or references a turn loaded, and no acceptance test can prove a turn ran the preflight.
Runtime enforcement and per-turn load receipts are outside this requirement and remain unbuilt.

### Outcome and Continuity

This section combines the completion gate with ownership beyond one turn. The agent stops once the
requested result and required proof are complete, and reports an outcome as complete only after
every requested result, material claim, deliverable, and asynchronous handback has been verified.
While verification remains, it states what happened and what remains to check.

Before ending, it delivers and verifies the outcome or reports a blocker with a real continuation
path. That path preserves status and the next action until a requester response, scheduled wake-up,
or delegation return. A background command, tool session, monitor, or child process is not a
continuation path; the agent waits for required work to finish and collects its result, or stops it
and reports the blocker. A long-running service is left running only when it is the requested
outcome and its ownership and observation are established. Pending work is never reported as
complete.

### Team Members

This section briefly identifies the team members available for named Rundesk delegation, lists the
agents available to a person-facing turn, then places its operating guidance under a `Delegation`
subsection. That subsection explains how to choose an agent, hand over one bounded outcome with
`"$RUNDESK_COMMAND" ask <agent> "<task>"`, state whether changes are authorized, and avoid waiting
for or duplicating active work. The result returns in a review turn. The agent reviews and verifies
that result before relying on it or completing the larger outcome. Simple documentation and copy
work stays direct with the smallest safe change. Small coding work uses at most one focused
implementation delegation when useful, with direct review by the owning agent. Multiple bounded
implementation, review, or QA delegations are reserved for distinct outcomes in large, complex, or
high-risk work, and agents scale up only for observed scope, risk, or failed evidence.

It is omitted for schedules because their asynchronous result cannot return to the same turn for
review. It is omitted for agent-to-agent delegations because named Rundesk delegation stops at one
level. An empty team also omits the section.

## Agent instruction template

Rundesk ships one provider-neutral agent template at `src/templates/agent/AGENTS.md` and places its
bytes under both native instruction filenames. The runtime does not classify agents as domain or
specialist agents. Those terms may be used as behavior-design patterns when an owner molds an
agent's durable role through its instructions, description, skills, and delegation scope.

The template contains only `Agent Instructions`, `Role and Responsibilities`, `Responses`,
`Provider Subagents`, and `Memory`. It addresses the agent directly and defines what it operates,
its durable responsibilities, role-specific capabilities and limits, how it answers, its supporting
use of provider-local subagents, and how it maintains separate memory. It contains no
instruction-authoring or self-editing guidance and does not repeat the operating outcome lifecycle.
Provider-local subagents do not replace eligible named Rundesk team delegation. The bundled
`managing-rundesk` guidance owns the review and writing process for changing agent instructions.
Its specialist design step carries a coding and code-investigation subsection: one reusable
implementation-specialist contract, preceded by the ownership rationale and followed by the
read-only investigator delta. The contract makes a coding agent read the target repository's own
`AGENTS.md` before any project action and follow it alongside its own; establish the authoritative
base, remotes, branch, existing worktrees, and uncommitted changes before acting; work in an
isolated task worktree on a topic branch cut from that base unless the assignment names another safe
workspace; preserve owner and unrelated changes without resetting, discarding, overwriting, or
folding them into the task; leave the shared checkout unchanged as found and its own task worktree
clean with coherent commits on its topic branch, keeping an explicitly requested review patch
uncommitted and reporting that exact dirty state; run the project's verification proportionate to
risk and report every gate that did not run; change no external state without assignment authority;
and hand back
the exact checkout or worktree, branch, commit or dirty files, verification and results,
limitations, and remaining work. A read-only investigator or reviewer creates no worktree, branch,
or commit and returns findings and evidence instead. The agent home stays an operational workspace
and never the project checkout, and the subsection names requirements rather than copying any
project's rules.
The separate `agent/MEMORY.md` template holds durable learned context such as preferences, traps,
gotchas, stable facts and references, and hard-won lessons without repeating agent instructions. A
person's durable preference for how work is done or answered — brevity, candor, format, or depth of
detail — is learned context for that file rather than part of the agent's role, so a stated reply
preference is recorded in memory instead of becoming a role rule.

The bundled design step also aligns an agent's granted skills with its durable role: grant what the role
needs on an ordinary turn, leave the rest ungranted, and do not restate Rundesk's loading procedure
in the agent's own contract. Its validation step inspects whatever load evidence the provider
supports in fresh turns and confirms the order actually taken — project rules first, then every
applicable body with its required references, then the remaining work — including that a close but
irrelevant granted skill stayed unloaded and an already-loaded body was not loaded again.

`Responses` sets the durable default for answering a person: a short, direct, natural reply that
reads like a text message, leading with the outcome and carrying only the context needed to
understand, act on, or verify it. The agent expands that default when the work is complex or
carries real risk, or when the person asks for more. A result returned to a calling agent is
excluded from that default and carries whatever detail and evidence that agent needs to verify and
use the work.

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
| ✅ | R-INS-5 | Operating prompts remain deterministic, inspectable, and bounded | `test_the_same_inputs_build_the_same_bytes`, `test_the_byte_breakdown_and_fingerprint_match_the_rendered_text`, `test_static_layers_and_the_largest_required_stack_stay_bounded` |
| ✅ | R-INS-6 | All agents start from one canonical template and public agent operations do not expose a type flag | `test_it_uses_the_single_agent_rules`, `test_role_is_not_an_add_option`, `test_role_is_not_a_configure_option`, `test_it_lists_all_agents_in_one_table` |
| ✅ | R-INS-7 | Legacy agent roles never suppress an otherwise eligible Team Members and Delegation section | `test_legacy_roles_do_not_remove_team_delegation_from_an_agents_instructions` |
| ✅ | R-INS-8 | Every turn is told its agent home is an operational workspace rather than a Git repository, and that patch or pull-request work belongs in the project's own checkout, without naming a file the release places in that home | `test_no_turn_is_told_its_home_is_a_project_repository`, `test_the_files_an_agent_lives_by_are_spelled_the_same_way_everywhere` |
| ✅ | R-INS-9 | A person-facing turn classifies a follow-up with an unstated or unclear referent as missing context, recovers it through supported same-audience history before asking what it refers to, forbids direct conversation-record and cross-agent/audience inference, and permits clarification only when recovery cannot unblock progress | `test_a_person_turn_asks_only_after_recovering_message_history`, `test_a_follow_up_with_a_missing_referent_requires_history_recovery`, `test_referent_recovery_is_person_facing_and_keeps_a_privacy_boundary`, `test_context_recovery_cannot_bypass_supported_audience_records`, `test_clarification_remains_available_when_recovery_cannot_unblock_progress` |
| ✅ | R-INS-10 | A change a person states as required is an instruction to make within the current scope, not something to agree with, propose, or wait to be asked for again | `test_a_stated_change_is_an_instruction_rather_than_a_proposal` |
| ✅ | R-INS-11 | The one agent template sets a short, outcome-first default for answering a person and excludes a result returned to a calling agent | `test_the_rules_have_the_required_sections`, `test_a_person_is_answered_briefly_and_a_calling_agent_in_full` |
| ✅ | R-INS-12 | Every turn is told a background command, tool session, monitor, or child process is not a continuation path and cannot deliver a result after the turn settles | `test_a_background_process_is_not_a_continuation_path` |
| ✅ | R-INS-13 | Every turn is instructed to run an ordered skill preflight before substantive action: read the applicable project rules in full, identify every applicable skill and no others, load each applicable body and its required references before any other substantive action, treat a granted skill as unloaded, skip a body already loaded in the session, and stop as a blocker when an applicable body or reference cannot be loaded | `test_every_turn_must_load_every_applicable_skill_body_before_acting` |
| ✅ | R-INS-14 | A person-facing turn keeps routine internal context recovery — memory, task state, instructions, prior messages, but not skills — silent, reserves a concise update for a requested status, material progress or a result that affects the person, and a blocker, risk, or decision, and never withholds an announcement a higher-priority applicable instruction requires | `test_a_person_turn_keeps_routine_internal_recovery_silent` |
| ✅ | R-INS-15 | Every turn is told not to report work as complete before verifying the requested outcome, that a command accepted or a process started is progress rather than proof, and that a report made while verification remains states what happened and what remains to check | `test_no_work_is_reported_complete_before_its_outcome_is_verified` |
| ✅ | R-INS-16 | The bundled specialist design step teaches a coding agent's contract to follow the target repository's own `AGENTS.md`, inspect authoritative state, mutate only in an isolated task worktree on a topic branch unless another safe workspace is named, preserve unrelated work, leave the shared checkout unchanged as found and its own task worktree clean with coherent commits on its topic branch while honoring an explicitly requested uncommitted patch, verify proportionately, change no external state without authority, and hand back exact location, state, and gaps | `test_a_coding_specialist_contract_is_specific_about_the_checkout` |
| ✅ | R-INS-17 | That design step separates read-only code investigation and review, which creates no worktree, branch, or commit and returns findings and evidence instead of changes | `test_a_read_only_investigator_creates_no_worktree_branch_or_commit` |
| ✅ | R-INS-18 | The bundled design step aligns granted skills with the durable role, naming both the ungranted skill the work needed and the unrelated grant every turn pays for | `test_the_design_step_grants_the_skills_the_durable_role_needs` |
| ✅ | R-INS-19 | That guidance names Rundesk's loading procedure once and keeps it out of the fenced agent contract | `test_the_universal_loading_procedure_is_named_once_and_never_copied` |
| ✅ | R-INS-20 | Instruction validation inspects supported load evidence in fresh turns for the order actually taken, an irrelevant granted skill left unloaded, and an already-loaded body not loaded again, while keeping the representative-and-near-miss acceptance case | `test_validation_inspects_the_order_a_fresh_turn_actually_took` |
| ✅ | R-INS-21 | For project work the applicable project rules are the turn's first project access, read in full before any other project file, directory listing, metadata access, skill load, plan, inspection, change, or verification, while the agent's own home context stays available beforehand | `test_the_projects_own_rules_are_the_first_project_access` |
| ✅ | R-INS-22 | Every turn is told to leave an unrelated granted skill unloaded, that non-project work has no project rules, and that file access alone does not trigger a development skill | `test_file_access_alone_does_not_trigger_a_development_skill` |
| ✅ | R-INS-23 | The one agent template classifies a durable preference for how work is done or answered as learned context for `MEMORY.md` rather than part of the agent's role | `test_a_durable_reply_preference_is_learned_context_not_a_role_rule` |
| ✅ | R-INS-24 | Every person-facing agent with named delegation keeps simple documentation and copy work direct, uses at most one focused implementation delegation for small coding work when useful, reviews that return within its own role, and reserves multiple bounded implementation, review, or QA delegations for distinct outcomes in large, complex, or high-risk work | `test_simple_documentation_and_copy_work_stays_direct`, `test_small_coding_work_has_one_focused_implementation_handoff`, `test_multiple_delegations_are_reserved_for_distinct_complex_work`, `test_scaling_never_weakens_project_or_safety_gates` |
| ✅ | R-INS-25 | Every turn defines the smallest safe and effective change sufficient for the requested result and required proof, makes and verifies only that change without unrequested refactoring, cleanup, redesign, or expansion, stops when the result and proof are complete, and requests explicit approval with the reason, proposed expansion, and impact before taking materially broader scope | `test_every_turn_defines_the_smallest_sufficient_change_before_editing`, `test_every_turn_forbids_unrequested_refactoring_and_scope_expansion`, `test_every_turn_stops_when_the_requested_result_and_proof_are_complete`, `test_broader_scope_requires_approval_with_impact` |

## Acceptance

Automated acceptance tests enforce the required sections, ordering, situation composition, and layer
boundaries. The largest required stack — every discovered situation at the largest team listing a
caller can supply, before any optional additions — is measured, so no situation is bounded only by
the case that named it. Optional additions are bounded individually as they are supplied and are not
part of that total. They do not freeze editorial prose: copy may be improved without rewriting tests
as long as the requirements and structural contract remain true.

Cases that assert a universal boundary derive the situation set from the instruction module rather
than from a maintained listing, so a situation added later is covered by each of them without a test
edit. That discovery fails when it finds no situation block, because a loop over nothing passes.

Bundled guidance is accepted against the one example contract that carries each required behavior,
scoped to the design step that owns it, rather than against a rule restated in prose and again in
the example.
