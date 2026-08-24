---
id: INS
name: Rundesk operating and agent instructions
last_verified: 2026-08-24
---

## What this is

Rundesk gives every turn a small product-owned operating layer, then lets the agent's own
instructions define who that agent is. The layers have separate owners and responsibilities so an
agent receives the context it needs without reading the same rules twice.

## Instruction ownership

- Rundesk operating instructions are product-owned, apply to every agent, and are not user
  controlled. They answer only what every agent needs answered the same way: where it is and what
  operates it, what this turn's situation is and which communication mechanics it may use, how to
  recover context Rundesk holds and this turn does not, what bounds the work and what must be
  loaded before it starts, which teammates are available for named delegation, and when a turn may
  honestly end. General work-quality guidance is not theirs to give: an agent's standards, method,
  and role belong to its own instructions.
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

Every rendered operating prompt contains these universal sections once and in this order:

1. `Rundesk`
2. `Agent Context`
3. `Current Situation`
4. `Scope and Boundaries`
5. `Before Acting`
6. `Outcome and Continuity`

The situation layer carries only communication mechanics that turn can use. Person-facing and
scheduled turns add `Messages and Attachments` after `Current Situation`; an agent-delegation turn
adds neither. This boundary follows the known turn situation rather than an agent-type flag: the
same durable agent may correctly receive different mechanics when a person asks it directly, a
schedule runs it, or another agent delegates to it.

`Team Members`, with its `Delegation` subsection, appears between `Before Acting` and `Outcome and
Continuity` only when named Rundesk delegation is available and the turn can review the
asynchronous result.

Naming the outcome is the first sentence of `Scope and Boundaries` rather than a section of its
own, because what completes the work and what bounds it are one decision. Every section heading
states when its rules apply, so an ordering guarantee is carried by the heading and not only by a
qualifier inside a bullet.

### Rundesk

One short definition identifies Rundesk as operating the agent. Person-facing commands use the bare
`rundesk ...` form. Commands inside a turn receive the resolved install root as a shell-quoted
`RUNDESK_HOME` assignment beside `"$RUNDESK_COMMAND"`, so provider tool shells cannot silently
substitute another install and unusual path characters cannot become shell syntax.

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

- Person: states that a person is available to answer. A change the person states as required is
  an instruction to make it within the current scope rather than something to agree with, propose,
  or wait to be asked for again; it authorizes no more than the stated change. Context the turn
  cannot see is classified as context to recover rather than a limitation to report, and the
  classification names its causes — an unclear referent, an earlier exchange, and anything a new
  session or a compaction dropped — because a turn whose conversation was present and is not any
  more does not recognize itself in "unclear referent" alone. The turn recovers that context,
  answers as though it had it, and asks only for what is still missing and still blocking.
  Recovering context is not progress: the turn neither announces a lookup nor lists what it
  searched, and reserves an update for a result, a decision, a blocker, or a requested status. That
  silence covers how context was found and never what governed the work, so an instruction to state
  which guidance was applied is unaffected. The same situation layer carries the message recovery
  and attachment mechanics below.
- Schedule: names the schedule, states that nobody is present, limits work to what the schedule
  requested, and says the final standalone response is delivered to the intended recipient or
  destination. Because nobody can be asked, context it cannot resolve is reported as a blocker
  rather than as a question. It may review supported prior messages when its recurring task
  requires them and may declare attachments in the delivered report.
- Agent delegation: names the calling agent, states that nobody is present, and says the final
  response returns to that agent alone. The delegation is the turn's complete brief and the only
  source of its outcome, scope, and authority, which is what removes the calling agent's
  conversation as something to go looking for and removes asking as an option without a separate
  prohibition for either; a brief too thin to work from is returned as the blocker, naming what is
  needed. The turn completes and verifies the work within that brief and treats it as read-only
  unless changes were explicitly authorized. Its final response is one handoff leading with the
  result, then exact changed artifacts, the verification it ran and what that showed, material
  assumptions, and remaining limitations. It does not contact the original requester or delegate to
  another named Rundesk agent, and receives no message-history or attachment mechanics. It is the
  smallest of the three situations, because a specialist's outcome, scope, and authority all arrive
  in its brief and the rules that exist because somebody is waiting have nothing to act on.

Unknown or omitted situations use the person-facing situation rather than silently adopting the
restrictions of a schedule or delegation.

### Messages and Attachments

This section makes two high-failure mechanics explicit for person-facing and scheduled turns.

Searching wide and answering narrow are two separate rules, and the section states them as two.
Collapsed into one, the audience boundary reads as a scope for the search itself: a live turn
narrowed its lookup to the room it was standing in and told the person that this channel's history
was empty, then asked them to paste the outcome back.

- Recover context with `messages {agent_name} --search "<relevant words>" --full`, then
  `messages {agent_name} --full` for the recent ones. Both commands read every conversation the
  agent has had. The turn never narrows them to one channel or conversation, and looks nowhere
  else, because nothing else holds this history — a stated boundary that also ends the outward
  search a bare prohibition invited.
- The turn answers only from results for the current `{source_kind}:{audience_id}`, never reads
  conversation files or records directly, and never repeats another agent's or audience's content.
  This is a rule about what may be said back, not about where to look.
- The turn never reports history as empty or unavailable and never asks for what a lookup should
  have found. With no match it says the search found no match and asks only for what is missing;
  on a scheduled turn that unresolved remainder is a blocker instead of a question.
- Attach a file or image with an absolute local Markdown link, such as
  `[report](/absolute/path/report.pdf)` or `![preview](/absolute/path/preview.png)`. A plain path is
  not represented as an attachment.

### Scope and Boundaries

This section opens by making the agent name what must be produced, changed, or reported, what
completes it, and what proves it. That, with the current request, schedule, or delegation, is the
whole of the turn's scope and authority, and the section closes the three things that read as
licence to do more — project rules, adjacent findings, and a useful opportunity — in the same
sentence that grants the scope, rather than leaving them to a later prohibition.

Runtime read access permits inspection and reporting only; work access permits changes only when
the current request, schedule, or delegation authorizes them. The turn delivers the smallest safe
and effective change that produces the requested result and its proof, and adds no further
deliverables, refactors, cleanup, integrations, or follow-up work. That prohibition is stated once,
in the section that owns scope. Needing materially broader scope, authority, or access is an
approval request naming why, what is proposed, and its impact, or a blocker where nobody can
approve it. The section also prohibits invented facts, capabilities, actions, or outcomes, and
exposure of secrets or sensitive information.

### Before Acting

This section is the ordered preflight, and its heading carries the ordering. "Before substantive
action" was read as "before changing anything": turns listed the tree, opened task files and loaded
project skills, and only then read the rules that decide which skills apply. The trigger is now the
project access itself — any file, listing, metadata, plan, inspection, change, or verification —
under a heading that says when the section applies.

1. Read the project's own rules in full. The project's rules are an input to which skills apply, so
   a selection made before reading them is made from half the evidence. Recovering the agent's own
   home context beforehand is not project access, and non-project work has no project rules.
2. From the skill descriptions, identify every skill applicable to this request and project, and no
   others. An unrelated granted skill stays unloaded, and file access alone does not trigger a
   development skill. Applicability follows the work itself: a standalone development task outside
   any repository may still need the skill it names.
3. Load each applicable body, together with the references it requires, through the provider's own
   skill mechanism. A skill that is listed or granted is not a skill that is loaded, and a body
   already loaded in the current session is not loaded again.
4. Inspect, create, or change anything else only after that.

A required body or reference which will not load stops the work as a reported blocker rather than
being replaced by its description. The instructions say when and what; descriptions and bodies
remain provider-native and are never copied into the prompt.

Rundesk instructs this preflight; it does not enforce or observe it. No release records which skill
bodies or references a turn loaded, and no acceptance test can prove a turn ran the preflight.
Runtime enforcement and per-turn load receipts are outside this requirement and remain unbuilt.

### Outcome and Continuity

This section combines the completion gate with ownership beyond one turn. An outcome is complete
only when every requested result, material claim, and reviewed handback is verified; an accepted
command or a started process is progress rather than proof. While verification remains, the turn
says what happened, what it verified and how, and what is still unchecked.

The continuation rule states the mechanism rather than repeating the prohibition, because the
prohibition alone did not hold: told only that a background process is not a continuation path, a
measured turn started one, started a monitor over it, wrote that it would report as soon as the
result landed, and ended. Inside a harness that really does deliver such a notification that belief
is correct, and only Rundesk's turn boundary makes it false. The turn is therefore told that it
ends when the agent stops writing and that nothing wakes it for a background command, tool session,
monitor, or child process; it waits for the result inside the turn, or stops the process and
reports the blocker, unless that process is itself the requested outcome — which must then be
started so it outlives the turn. That obligation is stated because the licence alone was obeyed to
the letter and still failed: a measured turn started a server, proved it with a real `200`, did not
kill it, and left the person a dead URL, because the child died with the turn that started it.

A turn ends in exactly one of three states: a verified outcome, a named blocker carrying its next
action, or a continuation Rundesk resumes — a requester response, a scheduled wake-up, or a
delegation return. The third is a permission and not only a prohibition, because an agent whose
only honest endings were verified and blocked has nowhere to put a delegation still out or a
schedule that will wake it. Work waiting on one of those three events is never reported as
complete.

### Team Members

This section briefly identifies the team members available for named Rundesk delegation, lists the
agents available to a person-facing turn, then places its operating guidance under a `Delegation`
subsection. That subsection is a routing boundary rather than a second delegation procedure. It
names the positive signals for considering delegation: a teammate's stated responsibility is a
materially better fit for one bounded outcome, coordination is proportionate, or independent
expertise, parallel work, or required review would improve the result. It names the corresponding
direct-work signals: small or mechanical work, continuing ownership, or coordination whose cost
exceeds its value. Ordinary conversation and simple documentation, formatting, or copy-only changes
stay direct. Availability and skill names alone never justify delegation.

The agent applies those routing signals before loading delegation guidance. It does not load
`delegating-work` merely because a teammate is available. Only when named delegation is a genuine
option is that skill classified as applicable, and its body must load before the agent chooses a
target or acts. The skill owns target selection, briefing, asynchronous lifecycle, steering,
resuming, and return review; the always-loaded operating layer does not repeat those procedures.

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
Provider-local subagents serve bounded same-turn review, research, exploration, and validation that
the parent supervises and integrates. Named Rundesk agents serve asynchronous handoffs when durable
responsibility and specialized granted skills make one materially better suited; their answers can
wake review turns, while provider-local work is not a durable continuation path. The bundled
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

Agent creation, configuration, listings, team context, and communication mechanics do not expose or
depend on an agent-type flag. Existing customized instruction files remain untouched. A legacy
stored role column remains in agent records for compatibility with immutable migration history, but
current behavior does not read or change it. Situation-specific composition avoids making one
durable label predict every way an agent may be invoked.

Every person-facing agent receives Team Members and Delegation whenever at least one eligible
teammate is available under its outbound delegation scope. A legacy role value never suppresses or
changes that section. The situation and delegation-depth exclusions defined above still apply.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-INS-1 | Operating and agent instructions have the separate ownership and precedence defined above | `src/rundesk/providers/instructions.py`, `src/skills/managing-rundesk/references/agent-instructions.md` |
| ✅ | R-INS-2 | Every prompt has the required universal operating sections — `Rundesk`, `Agent Context`, `Current Situation`, `Scope and Boundaries`, `Before Acting`, `Outcome and Continuity` — once and in order | `test_the_always_on_sections_are_present_once_and_in_order` |
| ✅ | R-INS-3 | Every prompt has exactly one current situation, with person-facing behavior as the default | `test_every_turn_gets_exactly_one_current_situation`, `test_the_default_situation_is_person_to_agent` |
| ✅ | R-INS-4 | Team Members is present only for a person-facing turn with an available team | `test_team_members_are_only_composed_for_a_person_facing_turn`, `test_an_empty_team_has_no_heading_or_layer`, `test_a_schedule_is_not_shown_or_used_to_find_a_named_team` |
| ✅ | R-INS-5 | Operating prompts remain deterministic, inspectable, and bounded | `test_the_same_inputs_build_the_same_bytes`, `test_the_byte_breakdown_and_fingerprint_match_the_rendered_text`, `test_static_layers_and_the_largest_required_stack_stay_bounded` |
| ✅ | R-INS-6 | All agents start from one canonical template and public agent operations do not expose a type flag | `test_it_uses_the_single_agent_rules`, `test_role_is_not_an_add_option`, `test_role_is_not_a_configure_option`, `test_it_lists_all_agents_in_one_table` |
| ✅ | R-INS-7 | Legacy agent roles never suppress an otherwise eligible Team Members and Delegation section | `test_legacy_roles_do_not_remove_team_delegation_from_an_agents_instructions` |
| ✅ | R-INS-8 | Every turn is told its agent home is an operational workspace rather than a Git repository, and that patch or pull-request work belongs in the project's own checkout, without naming a file the release places in that home | `test_no_turn_is_told_its_home_is_a_project_repository`, `test_the_files_an_agent_lives_by_are_spelled_the_same_way_everywhere` |
| ✅ | R-INS-9 | A person-facing turn classifies context it cannot see — an unclear referent, an earlier exchange, or anything a new session or compaction dropped — as context to recover rather than a limitation to report, recovers it, answers as though it had it, forbids direct conversation-record reading and repeating another agent's or audience's content, and asks only for what is still missing and still blocking | `test_a_person_turn_asks_only_after_recovering_message_history`, `test_a_follow_up_with_a_missing_referent_requires_history_recovery`, `test_context_lost_to_a_new_session_or_compaction_is_the_same_trigger`, `test_referent_recovery_is_person_facing_and_keeps_a_privacy_boundary`, `test_context_recovery_cannot_bypass_supported_audience_records`, `test_clarification_remains_available_when_recovery_cannot_unblock_progress` |
| ✅ | R-INS-10 | A change a person states as required is an instruction to make within the current scope, not something to agree with, propose, or wait to be asked for again | `test_a_stated_change_is_an_instruction_rather_than_a_proposal` |
| ✅ | R-INS-11 | The one agent template sets a short, outcome-first default for answering a person and excludes a result returned to a calling agent | `test_the_rules_have_the_required_sections`, `test_a_person_is_answered_briefly_and_a_calling_agent_in_full` |
| ✅ | R-INS-12 | Every turn is told that its turn ends when it stops writing and that nothing wakes it for a background command, tool session, monitor, or child process, so it waits for the result inside the turn or stops the process and reports the blocker, unless that process is itself the requested outcome, which must then be started so it outlives the turn | `test_a_background_process_is_not_a_continuation_path`, `test_the_continuation_rule_names_the_turn_boundary_that_makes_it_true` |
| ✅ | R-INS-13 | Every turn is instructed to run an ordered skill preflight before substantive action: read the applicable project rules in full, identify every applicable skill and no others, load each applicable body and its required references before any other substantive action, treat a granted skill as unloaded, skip a body already loaded in the session, and stop as a blocker when an applicable body or reference cannot be loaded | `test_every_turn_must_load_every_applicable_skill_body_before_acting` |
| ✅ | R-INS-14 | A person-facing turn treats recovering context as work rather than progress: it neither announces a lookup nor lists what it searched, reserves an update for a result, a decision, a blocker, or a requested status, and scopes that silence to how context was found so an instruction to state which guidance governed the work is unaffected | `test_a_person_turn_keeps_routine_internal_recovery_silent` |
| ✅ | R-INS-15 | Every turn is told not to report work as complete before every requested result, material claim, and reviewed handback is verified, that a command accepted or a process started is progress rather than proof, and that a report made while verification remains states what happened, what was verified and how, and what is still unchecked | `test_no_work_is_reported_complete_before_its_outcome_is_verified` |
| ✅ | R-INS-16 | The bundled specialist design step teaches a coding agent's contract to follow the target repository's own `AGENTS.md`, inspect authoritative state, mutate only in an isolated task worktree on a topic branch unless another safe workspace is named, preserve unrelated work, leave the shared checkout unchanged as found and its own task worktree clean with coherent commits on its topic branch while honoring an explicitly requested uncommitted patch, verify proportionately, change no external state without authority, and hand back exact location, state, and gaps | `test_a_coding_specialist_contract_is_specific_about_the_checkout` |
| ✅ | R-INS-17 | That design step separates read-only code investigation and review, which creates no worktree, branch, or commit and returns findings and evidence instead of changes | `test_a_read_only_investigator_creates_no_worktree_branch_or_commit` |
| ✅ | R-INS-18 | The bundled design step aligns granted skills with the durable role, naming both the ungranted skill the work needed and the unrelated grant every turn pays for | `test_the_design_step_grants_the_skills_the_durable_role_needs` |
| ✅ | R-INS-19 | That guidance names Rundesk's loading procedure once and keeps it out of the fenced agent contract | `test_the_universal_loading_procedure_is_named_once_and_never_copied` |
| ✅ | R-INS-20 | Instruction validation inspects supported load evidence in fresh turns for the order actually taken, an irrelevant granted skill left unloaded, and an already-loaded body not loaded again, while keeping the representative-and-near-miss acceptance case | `test_validation_inspects_the_order_a_fresh_turn_actually_took` |
| ✅ | R-INS-21 | For project work the applicable project rules are the turn's first project access, read in full before any other project file, directory listing, metadata access, skill load, plan, inspection, change, or verification, while the agent's own home context stays available beforehand | `test_the_projects_own_rules_are_the_first_project_access` |
| ✅ | R-INS-22 | Every turn is told to leave an unrelated granted skill unloaded, that non-project work has no project rules, and that file access alone does not trigger a development skill | `test_file_access_alone_does_not_trigger_a_development_skill` |
| ✅ | R-INS-23 | The one agent template classifies a durable preference for how work is done or answered as learned context for `MEMORY.md` rather than part of the agent's role | `test_a_durable_reply_preference_is_learned_context_not_a_role_rule` |
| ✅ | R-INS-24 | Every person-facing agent with named delegation gets concise, balanced routing signals for when to consider delegation and when to work directly; ordinary conversation and simple documentation, formatting, or copy-only changes stay direct, availability and skill names do not trigger the skill, and a genuine delegation option requires loading `delegating-work` before choosing or acting because it owns the procedure | `test_it_names_positive_signals_for_considering_delegation`, `test_it_names_when_direct_work_is_better`, `test_it_routes_delegation_procedure_to_the_skill` |
| ✅ | R-INS-25 | Every turn delivers the smallest safe and effective change that produces the requested result and its proof, adds no further deliverables, refactors, cleanup, integrations, or follow-up work — stated once, in the section that owns scope — and treats materially broader scope, authority, or access as an approval request naming why, what is proposed, and its impact, or as a blocker where nobody can approve it | `test_every_turn_defines_the_smallest_sufficient_change_before_editing`, `test_every_turn_forbids_unrequested_refactoring_and_scope_expansion`, `test_every_turn_stops_when_the_requested_result_and_proof_are_complete`, `test_broader_scope_requires_approval_with_impact` |
| ✅ | R-INS-26 | Every turn distinguishes person-facing `rundesk ...` commands from its own root-bound command prefix, and renders the resolved install root as one shell-safe assignment | `test_the_prompt_names_the_install_root_for_provider_tool_shells`, `test_the_prompt_shell_quotes_every_install_root_as_one_assignment` |
| ✅ | R-INS-27 | Communication mechanics follow turn capabilities without an agent-type flag: person-facing and scheduled turns receive supported same-audience message review and attachment syntax, with unresolved scheduled context reported as a blocker instead of a clarification request, while agent-delegation turns receive neither | `test_communication_mechanics_follow_the_turn_situation`, `test_a_schedule_may_review_supported_messages_without_waiting_for_clarification` |
| ✅ | R-INS-28 | An agent-delegation turn is told nobody is present, that its response returns to the calling agent alone, that the delegation is its complete brief and the only source of its outcome, scope, and authority, that a brief too thin to work from is returned as the blocker naming what is needed, and that its final response is one handoff leading with the result and carrying exact changed artifacts, the verification it ran and what that showed, material assumptions, and remaining limitations | `test_a_delegated_turn_is_an_internal_handoff_with_no_person_to_ask` |
| ✅ | R-INS-29 | The agent-delegation situation stays the smallest of the three, because a specialist receives its outcome, scope, and authority in its brief and pays for none of the rules that exist because somebody is waiting | `test_a_delegated_turn_pays_for_none_of_the_person_facing_mechanics` |
| ✅ | R-INS-30 | Context recovery searches every conversation the agent has had and is never narrowed to one channel or conversation; the current-audience boundary governs only what may be answered from and repeated back | `test_the_lookup_is_never_narrowed_to_the_audience_it_answers` |
| ✅ | R-INS-31 | No turn reports history as empty or unavailable, or asks a person for what a lookup should have found; a zero-match lookup is stated as a completed search with no match, followed by a request for only what is missing | `test_context_lost_to_a_new_session_or_compaction_is_the_same_trigger`, `test_a_person_is_never_asked_for_what_a_lookup_should_have_found` |
| ✅ | R-INS-32 | The supported message lookup is stated as the whole of the search for conversation context, so a zero-match result ends the search rather than sending it outward to unrelated systems, projects, or checkouts | `test_the_supported_lookup_is_where_the_search_ends` |
| ✅ | R-INS-33 | Every turn may end in exactly one of three states — a verified outcome, a named blocker carrying its next action, or a continuation Rundesk resumes at a requester response, a scheduled wake-up, or a delegation return — and work waiting on one of those is never reported as complete | `test_every_turn_cannot_end_without_delivery_or_a_continuation_path`, `test_every_turn_stops_when_the_requested_result_and_proof_are_complete` |
| ✅ | R-INS-34 | Naming the outcome opens the section that bounds it rather than occupying a section of its own, and each section heading states when its rules apply | `test_the_outcome_is_named_where_the_scope_it_bounds_is_named`, `test_the_always_on_sections_are_present_once_and_in_order` |

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
