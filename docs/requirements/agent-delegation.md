---
id: DEL
name: One agent's ask of another, and the answer it returns
last_verified: 2026-08-16
---

## What this is

A delegation is one bounded task a named agent hands to another named agent on this
install. The agent it is handed to answers it once as itself — its own home, memory,
skills and brain — and that single answer is delivered back into the asking agent's own
conversation for review. The asking agent reviews it and answers the person who asked.

## Why it exists

- An agent can hand work to a colleague that genuinely knows something it does not.
- Neither agent loses what it is: the one answering is itself, not an execution of a role.
- No unreviewed work reaches the person who asked for it.

## Requirements

Evidence on every completed row names exact test methods in the current suite. The repository test
`test_every_completed_requirement_names_current_test_evidence` keeps those citations discoverable
when tests are renamed or removed. An incomplete row links the issue that owns the missing behavior;
it is not a claim that adjacent delegation behavior is absent.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-DEL-1 | A delegation is one bounded task one named agent hands another on this install, answered once | `test_it_lands_in_the_asking_agents_own_store`, `test_an_answering_agent_finds_what_was_handed_to_it`, `test_the_first_call_delivers_and_the_second_does_not` |
| ✅ | R-DEL-2 | An answering agent keeps its whole identity: its home, its memory, its skills, its brain | `test_another_agent_asking_gets_the_agent_layer`, `test_the_agent_that_asked_is_named`, `test_the_ones_that_are_always_there` |
| ❌ | R-DEL-3 | A delegation is admitted only by a turn belonging to the agent asking, still in flight | A terminal parent turn is still accepted; tracked by [#401](https://github.com/rundesk-ai/rundesk-cli/issues/401). |
| ❌ | R-DEL-4 | A turn on no surface the asking agent is reachable on cannot delegate | A turn in a conversation with no reachable channel is still accepted; tracked by [#401](https://github.com/rundesk-ai/rundesk-cli/issues/401). |
| ✅ | R-DEL-5 | Each delegation happens in a conversation of its own, never one a person is typing into or another bounded task shares | `test_the_brief_lands_as_a_message_in_a_conversation_of_its_own`, `test_each_task_has_its_own_conversation_and_answer` |
| ✅ | R-DEL-6 | A delegation turn is told the requester is an agent, nobody is present, and to report blocked | `test_another_agent_asking_gets_the_agent_layer`, `test_a_turn_answering_another_agent_is_shown_nobody`, `test_a_delegated_project_task_cannot_pollute_the_agents_own_memory` |
| ❌ | R-DEL-7 | A delegation never widens the authority the asking turn had, and may narrow it | Read access currently widens to work access; tracked by [#398](https://github.com/rundesk-ai/rundesk-cli/issues/398). |
| ✅ | R-DEL-8 | An agent already in the delegation chain is refused, and an agent reached by delegation cannot delegate | `test_an_agent_may_not_hand_work_to_itself`, `test_a_turn_already_answering_a_delegation_may_not_hand_it_on`, `test_a_turn_answering_another_agent_is_shown_nobody` |
| ❌ | R-DEL-9 | An agent answering a delegation cannot start a role run from that turn | The rebuilt CLI has no role-run command; tracked as stale scope by [#401](https://github.com/rundesk-ai/rundesk-cli/issues/401). |
| ✅ | R-DEL-10 | Only the last complete message a delegation turn writes is returned, and an answered ask may still be carried on | `test_an_unattended_turn_delivers_only_its_last_complete_response`, `test_resume_keeps_a_pre_upgrade_delegations_original_conversation` |
| ✅ | R-DEL-11 | Every answered delegation owes the asking agent exactly one review, delivered once | `test_the_first_call_delivers_and_the_second_does_not`, `test_an_external_parent_keeps_the_result_owed_until_a_review_turn_is_admitted`, `test_a_resumed_delegation_delivers_its_second_result_once` |
| ❌ | R-DEL-12 | An answer that cannot be reviewed after a bounded number of attempts is settled and the owner told | There is no total attempt ceiling or owner notice; tracked by [#401](https://github.com/rundesk-ai/rundesk-cli/issues/401). |
| ❌ | R-DEL-13 | A delegation nothing answered inside its window is settled and the asking agent told | There is no delegation expiry or deadline settlement; tracked by [#401](https://github.com/rundesk-ai/rundesk-cli/issues/401). |
| ✅ | R-DEL-14 | Rundesk records an answering agent's words and asserts nothing read out of them | `test_the_reply_once_the_turn_is_terminal`, `test_the_answer_it_reviewed_is_what_it_was_answering`, `test_an_unattended_turn_delivers_only_its_last_complete_response` |
| ✅ | R-DEL-15 | What a delegation shows a person carries no local path and no brief | `test_the_name_of_who_has_it_is_a_last_component_and_never_a_path`, `test_nothing_of_what_was_said_is_written_into_the_delegation` |
| ✅ | R-DEL-16 | Handing work to an agent, its progress and its outcome are shown where the person asked | `test_work_that_has_just_gone_out_says_who_has_it_and_which_ask_it_is`, `test_an_answer_that_came_back_says_so_and_how_long_it_took`, `test_the_review_turn_answers_in_the_room_the_work_was_asked_for_in` |
| ✅ | R-DEL-17 | A delegation record carries everything a surface needs to render it, correlated against nothing earlier | `test_every_word_rundesk_can_send_has_a_mark_and_words_of_its_own`, `test_a_state_this_release_has_never_heard_of_renders_nothing` |
| ✅ | R-DEL-18 | A delegation somebody ended has a durable stopped outcome distinct from answered, is emitted and listed as stopped, creates no review response, cannot be resumed, and names who asked | `test_stopped_work_is_terminal_and_distinct_from_answered_work`, `test_a_requested_stop_settles_without_a_review_or_response_turn`, `test_requested_stop_is_durably_stopped_and_never_answered_or_reviewed`, `test_stopped_work_cannot_be_resumed` |
| ✅ | R-DEL-19 | Guidance for working delegated work is durable and offered to the active provider turn immediately; only guidance that misses or is refused by that turn remains for the recipient's next turn | `test_a_delegated_provider_turn_incorporates_guidance_written_while_it_runs`, `test_pending_guidance_is_picked_up_by_the_active_turn_without_a_gateway_sweep`, `test_guidance_that_missed_the_active_turn_stays_pending` |
| ✅ | R-DEL-20 | A carried-on answered delegation keeps the provider session it already had, and is asked what was said rather than the task again | `test_resume_keeps_a_pre_upgrade_delegations_original_conversation`, `test_carrying_work_on_keeps_its_scoped_provider_and_model`, `test_the_delegation_keeps_its_identity_and_its_conversation` |
| ❌ | R-DEL-21 | A terminal delegation stays readable for a window counted from its latest activity; answered work is resumable, stopped work is not, and a listing says the deadline | Resume and stopped-work refusal exist, but no retention deadline or expiry exists; tracked by [#401](https://github.com/rundesk-ai/rundesk-cli/issues/401). |
| ✅ | R-DEL-22 | Guiding, ending and carrying on a delegation are three verbs, and each refusal names the one that was wanted | `test_say_refuses_answered_work_and_points_to_resume`, `test_stopped_work_cannot_be_resumed`, `test_an_agents_own_turn_guides_and_carries_on_without_naming_itself` |
| ✅ | R-DEL-23 | Guiding a delegation and carrying one on are each shown where the person asked, without repeating what was said | `test_words_said_into_work_still_going_are_shown_where_the_person_asked`, `test_a_steer_never_repeats_what_was_said`, `test_work_carried_on_says_so_rather_than_looking_like_a_new_delegation` |
| ✅ | R-DEL-24 | One named agent asking another from inside a turn is admitted as a delegation, and it is the only way in | `test_an_allowed_target_is_admitted`, `test_a_person_at_a_terminal_may_not`, `test_a_turn_already_answering_a_delegation_may_not_hand_it_on` |
| ✅ | R-DEL-25 | A turn is told which agent it belongs to, so a command run from it can tell whose work it is doing | `test_the_ones_that_are_always_there`, `test_the_turn_is_named_by_its_own_id` |
| ❌ | R-DEL-26 | Asking a role by name says it is a role and names the command that hands it work | The rebuilt CLI has no role-run command; tracked as stale scope by [#401](https://github.com/rundesk-ai/rundesk-cli/issues/401). |
| ✅ | R-DEL-27 | Each agent's outbound delegation scope is unrestricted by default, may be an exact allowlist or empty, filters every team shown to that agent, omits the complete named-agent instruction layer when empty, and refuses a direct handoff outside the same scope before writing anything; target removal prunes explicit allowlists so name recreation inherits no old authority; scope changes, revocation, and admission serialize under the install lock; NULL stays unrestricted and inbound delegation is unchanged | `test_a_made_agent_has_run_it_and_may_delegate_to_any_agent_by_default`, `test_an_unlisted_target_is_refused_before_either_delegation_write`, `test_a_completed_revocation_cannot_be_followed_by_stale_authority_admission`, `test_an_inbound_only_preview_omits_the_complete_named_agent_layer` |
| ✅ | R-DEL-28 | An authorized channel query shows each delegation relevant to that conversation once with stable identity, safe task identity, lifecycle state, origin session, current delivery target, replacement label, and timing; unrelated, stale, and private contents stay out, provider-local work is separate and explicitly incomplete, and the query neither wakes a provider nor mutates delegation state | `test_active_named_work_survives_a_replaced_origin_session_and_is_scoped_once`, `test_returned_work_is_awaiting_review_then_reviewed_and_later_becomes_stale`, `test_stopping_and_provider_local_work_are_distinct_without_claiming_full_visibility`, `test_delegations_use_the_shared_read_only_query_without_starting_a_turn` |
| ✅ | R-DEL-29 | An authorized delegation independently accepts provider and model overrides; requested spellings remain distinct from the canonical effective provider/model fixed before either work write; no override captures the target defaults at admission, provider-only uses that provider's default model, model-only uses the target provider, and both use both requests; steering and resume cannot mutate selection; answer, failure, stop, resume, restart, and crash preserve both the provider-specific session and byte-identical target configuration; inspection and returned evidence distinguish requested, effective admission, and actual terminal provenance | `test_a_scoped_provider_and_model_are_admitted_without_changing_the_target`, `test_requested_and_effective_provider_model_round_trip_separately`, `test_a_replacement_gateway_receives_the_same_scoped_provider_and_model`, `test_show_distinguishes_requested_effective_and_terminal_provenance`, `test_it_carries_provider_model_evidence_from_the_terminal_turn` |

## Open questions

- Whether the four windows should be configurable per install, as a role run's quiet hours
  already are, rather than staying module constants.
- Whether a turn woken to review a delegated answer should be able to delegate again. It is
  legal today; the role path refuses the analogue outright.
- Whether an answering agent should run a delegation turn while already answering somebody
  on a channel. It may today, and two concurrent turns can both write its `MEMORY.md`.
