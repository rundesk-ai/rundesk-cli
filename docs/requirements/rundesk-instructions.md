---
id: INS
name: Rundesk operating and agent instructions
last_verified: 2026-08-25
---

## What this is

Rundesk gives every turn a small product-owned operating layer, then lets the agent's own
instructions define who that agent is. The layers have separate owners so an agent receives the
context it needs without reading the same rule twice. How they compose, section by section, is
[../instructions.md](../instructions.md); this page holds what that composition must guarantee.

## Why it exists

- An agent needs what every agent needs answered the same way — where it is, what this turn is,
  what bounds the work, and when it may honestly stop — without that answer competing with its own
  role.
- Work-quality guidance is not Rundesk's to give. Standards, method, and role belong to the agent's
  own instructions, and duplicating them in the operating layer makes both unreliable.
- A prompt that varies between identical turns cannot be reasoned about, so composition is
  deterministic, inspectable, and bounded.

## Requirements

A ✅ names the test methods observed to pass, and the whole suite was run on Python 3.14 and the
3.9 floor on 2026-08-25 with 83 suites and 4,197 tests green. Cases asserting a universal boundary
derive the situation set from the instruction module rather than a maintained list, so a situation
added later is covered without a test edit — and that discovery fails when it finds no situation
block, because a loop over nothing passes. The tests do not freeze editorial prose: copy may be
improved without rewriting them so long as the structural contract stays true.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-INS-1 | Operating and agent instructions have the separate ownership and precedence defined above | not proven — `src/rundesk/providers/instructions.py` and the bundled `agent-instructions.md` implement it, but no test names the ownership boundary |
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

## Open questions

- What would prove `R-INS-1`. Ownership and precedence are implemented and documented, but no test
  fails if a later change lets the operating layer restate an agent's own standards, which is the
  duplication the whole contract exists to prevent.
- Whether the largest-required-stack bound should be asserted per situation as well as in total.
  Optional additions are bounded individually as they are supplied and sit outside that total.
- Whether bundled guidance should be accepted against more than the one example contract carrying
  each required behavior, scoped to the design step that owns it.
