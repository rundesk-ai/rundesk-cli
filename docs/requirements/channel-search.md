---
id: SRCH
name: Searching the platforms an agent is connected to
last_verified: 2026-09-03
---

## What this is

One verb an agent runs to look through the platforms it has channels on, and to bring one result's
attachments onto this machine. Every channel answers the same request and returns the same row,
whatever platform stands behind it.

## Why it exists

An agent cannot be in every room, and a person referring to something said elsewhere expects it to be
able to go and look rather than to say it does not know. Doing that as one verb over the channels an
agent already has is what keeps it from becoming a skill per platform — and keeps platform knowledge
inside the adapter, which is the only place that may hold it.

## Requirements

|    | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-SRCH-1 | An agent searches every channel it has, or one it names, with one verb whose shape does not change between platforms. | `test_one_named_channel_is_the_only_one_asked`, `test_one_channel_refusing_never_costs_the_answer_another_gave` |
| ✅ | R-SRCH-2 | A search is narrowed to one place, one sender, and a window of days, in any combination, and a search narrowed by none of them is every place that channel can reach. | `test_every_part_of_the_narrowing_reaches_the_adapter_on_its_input`, `test_an_unscoped_search_says_empty_rather_than_leaving_a_key_out` |
| ✅ | R-SRCH-3 | Every result carries who said it, where it was said, when, and a handle that reaches that one message again. | `test_a_row_carries_who_where_when_the_ref_and_what_is_attached`, `test_full_prints_the_link_the_ref_the_files_and_the_whole_message` |
| ✅ | R-SRCH-4 | Found, found nothing, stopped before finishing, and could not look are four distinguishable answers, and a search that stopped early is never printed as an absence of conversation. | `test_found_prints_the_rows_and_says_how_far_it_looked`, `test_found_nothing_says_it_looked_and_is_not_a_failure`, `test_a_search_that_ran_out_with_nothing_never_reads_as_an_absence`, `test_a_search_that_ran_out_with_some_says_so_above_the_rows`, `test_a_channel_that_could_not_look_is_a_failure_and_says_why` |
| ✅ | R-SRCH-5 | What a channel says it looked through is reported where it said anything, and a channel that reported nothing is never read as one that looked nowhere. | `test_looked_is_left_out_rather_than_said_as_zero`, `test_found_nothing_says_it_looked_and_is_not_a_failure` |
| ✅ | R-SRCH-6 | The exit code says whether anything was looked through, never whether anything was found. | `test_the_exit_code_says_whether_anything_was_looked_through`, `test_found_nothing_says_it_looked_and_is_not_a_failure` |
| ✅ | R-SRCH-7 | A channel is searched with the same identity, allow list and credentials it is hosted with, so an agent finds what its own bot was admitted to and no more. | `test_both_invocations_are_told_who_the_channel_is_and_handed_its_credential` |
| ✅ | R-SRCH-8 | Whether a channel offers search is asked offline and with no credential, so a channel that offers none is skipped rather than run, and an adapter written before search existed is told apart from one that broke. | `test_capabilities_is_asked_first_and_a_channel_that_offers_none_is_never_run_with_one`, `test_an_adapter_written_before_search_existed_is_skipped_rather_than_crashed_into` |
| ✅ | R-SRCH-9 | A request reaches an adapter on its standard input as one object rather than on a command line, and the adapter's answer is read as an unvetted program's output — bounded, flattened, and cut to what was asked for whatever the adapter said. | `test_every_part_of_the_narrowing_reaches_the_adapter_on_its_input`, `test_more_results_than_were_asked_for_are_cut_to_the_bound_this_side_applies`, `test_a_strangers_newline_is_flattened_out_of_every_part_of_a_result`, `test_a_result_with_neither_words_nor_a_file_is_dropped` |
| ✅ | R-SRCH-10 | One channel that cannot be searched never costs the answer another channel gave, and each is named with the reason it was not searched. | `test_one_channel_refusing_never_costs_the_answer_another_gave`, `test_a_channel_whose_program_is_gone_is_named_and_costs_nothing_else` |
| ✅ | R-SRCH-11 | A result's attachments are brought in by a second act naming that result, never carried by the search itself. | `test_a_fetched_file_lands_where_one_that_arrived_would_have`, `test_fetching_with_words_is_refused_rather_than_half_done`, `test_fetching_without_naming_a_channel_is_refused_where_it_was_typed`, `test_a_ref_that_resolves_to_nothing_is_a_refusal_with_the_adapters_own_sentence` |
| ✅ | R-SRCH-12 | A fetched attachment lands where one that arrived through the same channel would have, under the same ownership and the same sweep, and no second place for it exists. | `test_a_fetched_file_lands_where_one_that_arrived_would_have`, `test_the_staged_copy_is_taken_away_whether_it_was_landed_or_not`, `test_a_fetched_file_is_the_one_thing_a_search_leaves_behind` |
| ✅ | R-SRCH-13 | A fetched file whose bytes do not match what the platform declared is refused by name, and the others still arrive. | `test_a_file_whose_bytes_do_not_match_is_refused_and_the_other_still_comes`, `test_a_partial_fetch_says_so` |
| ✅ | R-SRCH-14 | Only the invocation that stages a file is told where a file may be staged. | `test_only_fetch_is_told_where_it_may_stage_a_file` |
| ✅ | R-SRCH-15 | Search results are handed to the caller and never written into the agent's records, so an agent that narrows a question several times leaves nothing behind. | `test_the_search_command_writes_no_message_into_the_agents_records`, `test_a_fetched_file_is_the_one_thing_a_search_leaves_behind` |
| ✅ | R-SRCH-16 | A search that a channel could not be asked at all is refused where it was typed rather than sent to a platform. | `test_a_limit_past_the_ceiling_is_refused_where_it_was_typed`, `test_a_limit_below_one_is_refused`, `test_a_day_that_is_not_one_is_refused_before_anything_is_run`, `test_looking_for_nothing_is_refused` |
| ❌ | R-SRCH-17 | A search really reaches a live Slack workspace and a live Discord server, and the results really carry what those platforms hold. | not proven — no live workspace, server, app or credential was used, and none is permitted here. Every decision is proved offline against stand-ins. Exercise a scoped search, an unscoped one, a window, a fetch of a real attachment, and a guild Discord is still indexing. |
| ✅ | R-SRCH-18 | Every field of a result is bounded and flattened on rundesk's side whatever the adapter promised, including the ids, and the ref is held to the length the adapter contract publishes. | `test_an_id_is_a_strangers_text_too_and_is_bounded_like_one`, `test_a_strangers_newline_is_flattened_out_of_every_part_of_a_result`, `test_every_bound_holds_whatever_the_adapter_said` |
| ✅ | R-SRCH-19 | One fetch lands no more files than one arriving message may bring, says when more were offered, and a staged path no machine could hold is a line rather than a traceback. | `test_more_files_than_one_message_may_bring_are_cut_to_the_bound_this_side_applies`, `test_a_path_no_machine_could_hold_is_a_line_and_never_a_traceback` |
| ✅ | R-SRCH-20 | A channel that offers no search is never asked to fetch either, so no adapter is handed a credential and somewhere to write in order to find out it cannot answer. | `test_a_channel_that_offers_no_search_is_never_asked_to_fetch_either` |
| ✅ | R-SRCH-21 | Every way one channel can fail is that channel's own, and never discards an answer another channel already gave. | `test_any_trouble_one_channel_has_is_that_channels_and_not_the_searchs`, `test_a_channel_whose_program_is_gone_is_named_and_costs_nothing_else` |
| ✅ | R-SRCH-22 | A fetch narrows nothing, and every flag that narrows a search is refused on one rather than ignored. | `test_narrowing_a_fetch_is_refused_rather_than_ignored`, `test_fetching_with_words_is_refused_rather_than_half_done` |
| ✅ | R-SRCH-23 | An answer larger than a pipe holds reaches rundesk whole, and a program that prints without stopping is bounded rather than believed. | `test_an_answer_larger_than_a_pipe_holds_arrives_whole`, `test_a_program_that_never_stops_printing_is_bounded_rather_than_believed` |

## Open questions

- Whether a search should ever be offered a place the agent's own records already name, so an agent
  can search "the room this turn came from" without being told its id. Nothing does that today.
- What an agent should be told when two channels both find the same message on platforms that mirror
  each other. Nothing de-duplicates across channels, and nothing needs to yet.
