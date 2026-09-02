---
id: SLK
name: Slack, as an agent is reached on it
last_verified: 2026-09-02
---

## What this is

What wakes a Rundesk agent on Slack, where its answer goes, and how little it shows while it works.
Everything about the platform lives in `src/channels/slack` and nowhere else; adding it needed one
change under `src/rundesk/` — the typed authorization address `R-CH-39` and `R-CAD-25` describe —
and no change to the record vocabulary.

The `SLK` namespace was withdrawn on 2026-08-25 with the previous build's Slack contract and is
reissued here. Nothing in the tree cites the old rows, and they remain in git history only.

## Why it exists

- An agent stands in somebody else's workspace and is silent there until it is named.
- Several separately installed agents can share one thread without waking each other.
- Nothing an agent posts into a shared channel is bookkeeping about the answer rather than the
  answer, so a channel full of people reads a conversation and not a build log.
- Two agents working in one thread can each read what the other answered, so a person can ask one
  what it makes of the other's reply.
- No Slack user OAuth token, and no scope that reads a channel the bot was not invited to.

## Requirements

|    | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-SLK-1 | A direct message from an allowed sender starts a turn with no mention. | `test_a_direct_message_wakes_without_a_mention`, `test_a_direct_message_arrives_keyed_by_its_channel` |
| ✅ | R-SLK-2 | A message in a shared channel starts a turn only where it explicitly names this agent's bot, including inside a thread the agent has already answered in. | `test_a_channel_message_that_names_nobody_wakes_nothing`, `test_a_later_message_in_a_thread_it_answered_wakes_nothing`, `test_a_mention_is_checked_and_not_taken_on_slacks_word` |
| ✅ | R-SLK-3 | A mention at the top of a channel is answered in a new thread rooted at that message; a mention inside an existing thread is answered in that thread. | `test_a_mention_at_the_top_of_a_channel_roots_a_thread_at_itself`, `test_a_mention_inside_an_existing_thread_answers_in_that_thread`, `test_a_mention_arrives_keyed_by_the_thread_it_opened` |
| ✅ | R-SLK-4 | A mention inside another person's thread carries a bounded slice of that thread up to the invoking message, fetched once at invocation and never watched. | `test_a_mention_in_somebody_elses_thread_carries_what_stood_above_it`, `test_a_thread_longer_than_one_page_is_walked_to_the_message_that_asked`, `test_each_page_after_the_first_is_asked_for_by_cursor`, `test_a_thread_that_fits_in_one_page_is_asked_for_once_and_never_watched`, `test_nothing_after_the_invoking_message_is_carried`, `test_what_the_walk_holds_is_bounded_however_long_the_thread_is`, `test_a_join_notice_in_the_thread_is_still_not_carried` |
| ✅ | R-SLK-5 | Mentioning one of several agent bots in a thread wakes only the bots named. | `test_naming_another_bot_does_not_wake_this_one`, `test_naming_both_bots_wakes_this_one_too` |
| ✅ | R-SLK-6 | A bot-authored event, an edit, a deletion, a join notice, a duplicate delivery and malformed input start no turn. | `test_a_bot_authored_event_wakes_nothing`, `test_an_edit_a_deletion_and_a_join_are_not_somebody_speaking`, `test_an_envelope_slack_sent_again_is_acted_on_once`, `test_the_same_message_through_a_second_event_is_acted_on_once`, `test_malformed_input_wakes_nothing` |
| ✅ | R-SLK-7 | A Socket Mode envelope is acknowledged before any work, whether or not it wakes anything. | `test_an_envelope_is_acknowledged_before_anything_else_happens`, `test_an_envelope_is_acknowledged_even_when_it_wakes_nothing` |
| ✅ | R-SLK-8 | A conversation is keyed by workspace, channel and thread, so the same channel id in two workspaces is two conversations. | `test_the_same_channel_in_two_workspaces_is_two_conversations`, `test_a_channel_and_the_thread_in_it_are_not_the_same_conversation`, `test_it_reads_back_as_the_three_pieces_it_was_written_from` |
| ✅ | R-SLK-9 | An unallowed sender or place costs no platform call, produces no record and receives no response. | `test_a_stranger_costs_nothing_and_is_told_nothing`, `test_a_place_it_does_not_allow_costs_nothing`, `test_a_forged_display_name_never_reaches_the_decision` |
| ✅ | R-SLK-10 | Nothing Slack sees carries running commentary, tool activity, delegation news, token counts, timing or a stats footer. | `test_the_running_commentary_is_shown_as_nothing_at_all`, `test_work_handed_to_another_agent_is_shown_as_nothing`, `test_what_a_turn_cost_never_reaches_the_message`, `test_the_answer_is_the_whole_of_what_is_posted` |
| ✅ | R-SLK-11 | A message taken up is marked on the exact invoking message; a finished turn replaces that mark with a completion mark; a stopped or failed turn takes it down and puts nothing up. | `test_a_message_taken_up_is_marked_on_the_exact_message_that_asked`, `test_a_finished_turn_replaces_the_eyes_with_a_check`, `test_a_turn_that_was_stopped_takes_the_eyes_down_and_puts_nothing_up`, `test_the_new_mark_goes_up_before_the_old_one_comes_down` |
| ✅ | R-SLK-12 | A running turn shows Slack's own agent-session status and never a message imitating one. Only statuses Slack documents are sent, never an empty one, and a settled turn is put back to `active` alone. | `test_work_starting_sets_slacks_own_agent_session_status`, `test_no_message_is_posted_to_imitate_typing`, `test_every_way_a_turn_ends_puts_the_status_back`, `test_a_turn_that_ends_naming_no_message_still_puts_the_status_back`, `test_only_statuses_slack_documents_are_ever_sent`, `test_no_status_call_is_ever_made_with_an_empty_status`, `test_a_status_this_adapter_does_not_recognise_is_never_sent`, `test_a_settled_turn_asks_for_active_and_nothing_else` |
| ✅ | R-SLK-13 | Where Slack's agent session is unavailable — an app never declared as an agent, or a direct message that is not in a thread — no indicator is shown, nothing is posted in its place, and the refusal names what to go and do. | `test_a_flat_direct_message_has_no_session_and_nothing_is_posted_instead`, `test_a_workspace_where_the_app_is_no_agent_says_so_once_and_posts_nothing` |
| ✅ | R-SLK-25 | Every state record makes at most one agent-session call and never a second: a refusal is reported and acted on only by making fewer calls afterwards. A rate limit with a positive finite `Retry-After` sets a monotonic deadline before which this adapter makes no status call anywhere; one with no usable delay stops the mechanism until the adapter restarts rather than calling again. | `test_no_error_earns_a_second_call`, `test_a_turn_makes_at_most_one_call_for_each_state_record`, `test_nothing_here_waits_on_anything`, `test_a_failure_is_reported_where_it_happened`, `test_a_rate_limit_sets_an_embargo_for_exactly_as_long_as_slack_asked`, `test_the_embargo_suppresses_a_later_record_in_a_different_channel`, `test_a_place_is_allowed_again_once_the_embargo_has_passed`, `test_a_standing_embargo_is_extended_and_never_shortened`, `test_the_embargo_is_a_moment_and_not_a_countdown`, `test_a_rate_limit_with_no_usable_delay_stops_rather_than_calling_again`, `test_no_non_finite_delay_ever_becomes_a_deadline`, `test_a_stopped_mechanism_says_so_once` |
| ✅ | R-SLK-27 | A refusal about one channel or thread suppresses only that session and is bounded; only a refusal Slack documents as being about the token, the app or the method puts the mechanism down everywhere; anything else is one call that failed and suppresses nothing. | `test_only_a_proven_capability_failure_puts_the_mechanism_down`, `test_a_channel_refusal_never_quiets_a_different_place`, `test_a_refused_place_is_not_asked_about_again`, `test_two_threads_in_one_channel_are_two_sessions`, `test_what_is_remembered_about_refused_places_is_bounded`, `test_a_stopped_mechanism_makes_no_further_call_anywhere`, `test_a_word_this_release_has_never_heard_of_suppresses_nothing`, `test_a_failure_is_reported_where_it_happened` |
| ✅ | R-SLK-26 | A bounded thread slice carries another invited agent's answers, named safely, and never this app's own earlier messages. Reading them wakes nothing. | `test_another_agents_answer_is_carried_into_the_context`, `test_this_apps_own_earlier_answers_are_never_carried_back_to_it`, `test_our_own_line_is_left_out_by_either_id_alone`, `test_a_peer_apps_name_is_a_strangers_text_and_is_bounded`, `test_a_peer_app_is_never_asked_of_users_info`, `test_carrying_a_peer_answer_does_not_widen_what_wakes_the_agent` |
| ✅ | R-SLK-14 | An answer is posted in the thread the turn is in, and a direct message answer starts no thread. | `test_an_answer_is_posted_in_the_thread_the_turn_is_in`, `test_an_answer_in_a_direct_message_starts_no_thread` |
| ✅ | R-SLK-15 | Everything a brain wrote is escaped, so no answer can address a channel or ping a person. | `test_an_answer_cannot_address_the_room`, `test_an_answer_cannot_ping_somebody`, `test_the_ampersand_is_escaped_first_so_nothing_is_escaped_twice` |
| ✅ | R-SLK-16 | Text past the platform limit is refused rather than cut a second time, and a delivery carrying a file is refused in words that say why. | `test_text_past_the_limit_is_refused_rather_than_cut_a_second_time`, `test_a_delivery_carrying_a_file_is_refused_in_words_that_say_why` |
| ✅ | R-SLK-17 | Access uses a Slack App bot token and an app-level token; a user token is refused by name and no user-history or search scope is requested. | `test_a_user_token_is_refused_by_name`, `test_a_bot_token_that_signed_in_as_a_person_is_refused`, `test_no_user_history_or_search_scope_is_ever_wanted`, `test_both_credentials_are_named_and_only_named` |
| ✅ | R-SLK-18 | No credential value reaches an argument, the channel's settings, or any record Rundesk keeps. | `test_no_credential_is_ever_written_into_the_settings`, `test_both_credentials_are_named_and_only_named` |
| ✅ | R-SLK-19 | A missing bot scope is named while somebody is at a terminal rather than found at serve time, and a token that will not report its scopes is not refused over it. | `test_a_missing_scope_is_named_while_somebody_is_at_a_terminal`, `test_a_token_that_will_not_say_its_scopes_is_not_refused_over_it` |
| ✅ | R-SLK-20 | A credential Slack will never accept again ends the adapter rather than being reconnected into; one channel it was not invited to does not. | `test_a_revoked_token_ends_the_connection_rather_than_being_retried`, `test_one_channel_it_was_not_invited_to_does_not_end_the_connection`, `test_serving_without_a_token_is_a_refusal_nothing_should_restart` |
| ✅ | R-SLK-21 | Connection and loss are each reported once per change, so a quiet agent can be told from a deaf one. | `test_it_says_ready_once_however_often_it_is_asked`, `test_it_says_gone_once_per_loss`, `test_a_loss_before_it_was_ever_up_says_nothing` |
| ✅ | R-SLK-22 | `--capabilities` answers offline with no vendor library present, and declares only what this surface really does. | `test_it_answers_with_nothing_installed`, `test_it_is_honest_about_being_quiet`, `test_the_text_limit_is_the_one_constant_and_not_a_copy` |
| ❌ | R-SLK-23 | The behavior above holds against a real Slack workspace. | not proven — no live workspace, app, or credential was used. Create an app from [the guide](../guides/slack.md), invite it to a channel, and exercise a direct message, a top-level mention, a mention in another person's thread, a later unmentioned message in that thread, and two bots in one thread. |
| ❌ | R-SLK-24 | Slack's agent-session status really appears and really clears on a workspace whose app has been declared an agent. | not proven — the calls, their values and their ordering are proved offline against the four statuses Slack documents. Whether Slack renders one is what only a real workspace answers: declare the app an agent, install it again, and watch one turn in a thread. |

## Open questions

- Whether Markdown a brain wrote should be translated into Slack's `mrkdwn` dialect. It is not
  today: `**bold**` reaches Slack as the characters typed, and only the reserved `&`, `<` and `>` are
  escaped. A partial translation that touched a fenced code block would be worse than none.
- What a rate limit with no usable `Retry-After` should cost. The status mechanism stops until the
  channel is started again, because there is no interval to invent and Slack says a caller must wait
  for the response's delay before using that method in that workspace again. Whether Slack ever
  answers a 429 on this method without a `Retry-After` is unknown, and only a real workspace answers
  it.
- Whether the agent declaration can be made in an app manifest. Slack's reference publishes no key
  for it, so [the guide](../guides/slack.md) makes it an ordered step in the app's own settings and
  none is invented here. If one is published, the manifest and that step move together.
- Whether a bounded thread slice should also be carried for a mention that opens its own thread,
  from the channel above it rather than from the thread. It is not today, and the channel above is
  not something the agent was invited into a conversation about.
- What a thread past the read ceiling should carry. `conversations.replies` pages forward, so the
  pre-mention thread is walked to its end and only the newest lines are kept; past 500 messages the
  walk stops, says so in the agent's log, and carries lines that are genuinely earlier in the thread
  rather than directly above the question. Whether that is better than carrying nothing there is not
  settled, and only a real workspace says how often it happens.
- Whether an outbound or inbound file should be carried. `attach` is declared `false` and a delivery
  carrying one is refused; Slack's `files:read`/`files:write` are deliberately not requested.
