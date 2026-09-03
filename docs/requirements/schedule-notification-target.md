---
id: SNT
name: The one destination a schedule reports to
last_verified: 2026-09-03
---

## What this is

A schedule may name one destination of its own — one channel, and one place or one person's direct
message on it — and its start notice, final report, failure report and attached files go there
instead of to the agent's agent-wide notified channel. Naming none keeps exactly what a schedule has
always done. The destination is written the way an allow-list entry is written, and is checked
against that channel's own allow list before it is stored.

## Why it exists

- An owner may want one schedule's report in a shared room without moving the agent's whole
  notification target off the channel it is reached on.
- Where a report lands is a choice somebody makes, so *nobody chose* has to stay tellable from a
  destination that happens to be the channel the agent is already notified on.
- A destination that cannot be delivered must be refused where it is typed, not discovered by a
  gateway at the moment the schedule was meant to run.
- Reaching a person is decided by one allow list. A schedule reporting to somebody that list does
  not name would be a way to reach them around it.

## Requirements

A ✅ names test methods observed to pass on 2026-09-03 on `/usr/bin/python3` (3.9.6), across
`test_agent_schedule_target_step.py`, `test_schedules_command.py`, `test_schedules_due.py`,
`test_schedules_firing.py`, `test_channels_delivery.py`, `test_channels_hosting.py`,
`test_channels_discord.py`, `test_channels_slack.py`, `test_providers_answering.py`, and
`test_gateway_channels.py`. A ❌ is not a claim that the behavior is absent — it is a claim that
nothing here proves it.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-SNT-1 | `--channel` and `--to` are a pair; one without the other is refused naming the missing one, before anything is written | `test_a_channel_with_no_destination_is_refused_naming_the_missing_flag`, `test_a_destination_with_no_channel_is_refused_naming_the_missing_flag` |
| ✅ | R-SNT-2 | `--to` is read exactly as an allow-list entry is read: a bare or `sender:`-prefixed id is that person's direct message, `place:<id>` is that place | `test_a_place_is_taken_and_read_back_the_way_it_was_typed`, `test_a_person_is_taken_and_read_back_as_a_bare_id`, `test_the_typed_spelling_of_a_person_is_taken_too` |
| ✅ | R-SNT-3 | A destination is refused when the channel is not one this install has, or not one this agent has | `test_a_channel_this_install_does_not_have_is_refused`, `test_a_channel_this_agent_does_not_have_is_refused` |
| ✅ | R-SNT-4 | A destination absent from that channel's allow list is refused, and one held on it as the other kind of thing is refused saying which kind it is held as | `test_a_destination_that_is_not_on_the_allow_list_is_refused`, `test_a_place_that_is_not_on_the_allow_list_is_refused`, `test_an_id_on_the_list_as_a_place_is_refused_when_named_as_a_person`, `test_an_id_on_the_list_as_a_person_is_refused_when_named_as_a_place` |
| ✅ | R-SNT-5 | A destination is refused when the channel's adapter does not declare that it can address one | `test_an_adapter_that_cannot_address_one_is_refused`, `test_it_says_it_can_address_one` (Discord and Slack) |
| ✅ | R-SNT-6 | Every refusal leaves the records exactly as they were | `assertNothingWasWritten` on each refusal case, `test_update_refuses_the_same_way_and_changes_nothing` |
| ✅ | R-SNT-7 | Three states are kept apart: no destination, a place, and a person — and a row saying half a destination is refused as a schedule nobody can act on rather than read as one of the other two | `test_a_schedule_that_names_nothing_reports_nowhere_of_its_own`, `test_a_place_is_read_as_a_place`, `test_a_person_is_read_as_a_person`, `test_a_destination_with_no_channel_is_refused`, `test_a_channel_with_no_destination_is_refused`, `test_a_schedule_whose_destination_cannot_be_understood_is_not_a_schedule` |
| ✅ | R-SNT-8 | The records refuse a row naming a person and a place, on insert and on update | `test_a_row_naming_a_person_and_a_place_is_refused`, `test_moving_an_existing_row_to_both_is_refused_too` |
| ✅ | R-SNT-9 | `update` moves a destination between kinds and clears the kind it moved off; naming the pair alone is a change on its own | `test_update_moves_it_from_a_place_to_a_person_and_clears_the_place`, `test_naming_only_the_destination_is_a_change_on_its_own` |
| ✅ | R-SNT-10 | `show`, `add` and `update` say the destination where there is one and say nothing extra where there is none | `test_show_says_it_too`, `test_a_schedule_that_names_neither_says_nothing_extra` |
| ✅ | R-SNT-11 | A listing gains its destination column only once something in it has one, so an untargeted install reads exactly as before | `test_a_listing_with_nothing_targeted_has_the_columns_it_always_had`, `test_a_listing_gains_the_column_only_once_something_is_targeted`, `test_an_untargeted_row_in_that_listing_says_nothing_in_the_column`, `test_a_bare_listing_of_every_agent_keeps_its_own_columns` |
| ✅ | R-SNT-12 | One resolver decides where anything unprompted goes; a named destination replaces the notified channel there and clears the channel's own place, and naming none answers exactly as before | `test_a_named_destination_replaces_the_notified_channel_entirely`, `test_the_channels_own_place_is_cleared_when_a_destination_is_named`, `test_naming_nothing_still_answers_with_the_notified_channel` |
| ✅ | R-SNT-13 | A destination is answered for an agent that has no notified channel at all | `test_a_destination_is_answered_for_an_agent_that_tells_nobody_anything` |
| ✅ | R-SNT-14 | The destination crosses the adapter seam as the platform's own ids, on every piece of a split delivery | `test_a_named_place_crosses_as_a_place`, `test_a_named_person_crosses_as_a_person`, `test_every_piece_of_a_long_report_carries_the_destination`, `test_an_ordinary_delivery_names_no_destination_at_all` |
| ✅ | R-SNT-15 | A firing carries the destination it began with, in memory and on disk, so a gateway that came up after the one which started the work reports into the destination the notice stands in | `test_it_is_written_into_the_record_beside_the_notice`, `test_a_gateway_that_came_up_after_the_one_that_started_it_still_knows_where` |
| ✅ | R-SNT-16 | Overlapping firings each keep their own destination | `test_two_overlapping_firings_each_keep_their_own` |
| ✅ | R-SNT-17 | A firing record that says nothing about a destination, or half of one, reports to the notified channel | `test_a_firing_started_before_this_release_reports_to_the_notified_channel`, `test_half_a_destination_on_a_record_reports_to_the_notified_channel` |
| ✅ | R-SNT-18 | The start notice, the final report and a failure report all go to the named destination | `test_the_notice_goes_to_the_place_the_schedule_named`, `test_the_report_goes_to_the_same_place_as_the_notice`, `test_a_failed_program_is_said_out_loud_where_the_schedule_says` |
| ✅ | R-SNT-19 | A place target's report stands in one thread hanging off the notice, named for the schedule, and a second delivery joins that same thread | `test_the_report_asks_for_a_thread_named_after_the_run`, `test_the_report_lands_in_a_thread_and_not_in_the_place`, `test_a_second_delivery_joins_the_same_thread`, `test_a_threaded_report_hangs_off_the_notice` |
| ✅ | R-SNT-20 | A thread is never asked for without a message to hang it off, and a platform that will not open one delivers into the place instead | `test_a_thread_is_never_asked_for_with_nothing_to_hang_it_off`, `test_nothing_is_threaded_without_something_to_hang_it_off`, `test_a_platform_that_will_not_open_one_gets_the_report_in_the_place` |
| ✅ | R-SNT-21 | A direct-message target uses the platform's own direct presentation and opens no thread | `test_a_direct_message_target_gets_the_platforms_own_presentation`, `test_a_named_person_reaches_the_conversation_they_read`, `test_a_named_person_reaches_the_conversation_slack_opens` |
| ✅ | R-SNT-22 | An aimed delivery is never fanned out to every allowed identity | `test_an_aimed_notice_is_never_copied_to_everybody` |
| ✅ | R-SNT-23 | A destination the adapter cannot reach is refused rather than delivered somewhere else | `test_a_person_this_platform_will_not_open_a_conversation_with_is_refused`, `test_a_person_slack_will_not_open_a_conversation_with_is_refused`, `test_a_destination_naming_neither_is_refused_and_never_falls_back` |
| ✅ | R-SNT-24 | A quiet run with no activity chatter still posts its final report to the named destination, and says nothing besides its two messages | `test_a_quiet_run_still_reports_to_the_destination_it_named` |
| ✅ | R-SNT-25 | A schedule that named nothing behaves exactly as it did: notified place, no destination, no thread | `test_a_schedule_that_named_nothing_is_the_run_it_always_was`, `test_a_schedule_that_names_neither_holds_nothing` |
| ✅ | R-SNT-26 | The stored change is additive, carried by a discovered step, and leaves every existing row and every existing schedule's behavior untouched | `test_an_agent_that_predates_it_has_it_after_being_carried`, `test_a_row_already_there_keeps_every_value_it_had`, `test_no_destination_is_written_for_it`, `test_it_is_still_a_schedule_the_product_can_read` |
| ✅ | R-SNT-27 | The step is safe against a store that already has the column, and against one with no schedules table | `test_running_it_again_changes_nothing_and_does_not_fail`, `test_a_row_already_naming_a_destination_survives_it_being_run_again`, `test_an_agent_with_no_schedules_table_is_left_alone` |
| ✅ | R-SNT-28 | Routing starts no provider turn and reaches no platform to decide where something goes | `test_a_named_destination_replaces_the_notified_channel_entirely` and the resolver's whole suite run offline under the closed-network harness; the adapter is asked only `--capabilities`, offline, at the moment a destination is written |
| ❌ | R-SNT-29 | A run by hand reports in the terminal and on no surface, whatever destination the schedule names | not proven — the terminal path posts to no channel today and no check would fail if one were added. `schedules run` for an asking schedule calls `providers.answering.for_a_schedule`, which returns the answer rather than delivering it |
| ✅ | R-SNT-30 | The final report of a run that delegated goes to the schedule's own destination, read off the row by the review turn | `test_a_delegated_result_reports_to_the_destination_the_schedule_named`, `test_a_delegated_result_of_an_untargeted_schedule_still_goes_to_the_notified_channel` |
| ❌ | R-SNT-31 | Removing somebody from a channel's allow list does not stop an existing schedule reporting to them | **an accepted gap, not a defect.** The allow list is read once, at the moment `--to` is written, and never again — so a destination taken off an allow list afterwards goes on receiving that schedule's reports. To stop it, remove the schedule or point it somewhere else. No check asserts either side |
| ✅ | R-SNT-32 | A run aimed at a named destination shows nothing on the way there — no typing indicator, no running remark, no delegation progress — and its report is the only record the adapter hears, so the notice and the report stay the two messages a scheduled run is allowed. A schedule that named nothing goes on showing what it always did, where it always did | `test_an_aimed_review_turn_says_nothing_besides_the_report`, `test_nothing_is_said_about_handed_over_work_where_a_schedule_named_a_destination`, and for the half that must not move `test_a_schedule_that_named_nothing_is_still_told_what_became_of_handed_over_work` (answering) |

## Open questions

- **R-SNT-31 is a settled decision, not an oversight.** The owner chose to leave the behaviour as it
  is: re-checking the allow list at delivery time would make a report vanish silently the day
  somebody tidied a list, which is the failure mode this contract is otherwise built to avoid, and
  a visible gap is safer than an invisible one. So an operator has to know two things, and both are
  stated on the row above and in [`schedules.md`](../api/schedules.md#where-one-schedule-reports):
  **the allow list is checked once, when the destination is written**, and **taking somebody off an
  allow list does not stop a schedule already pointed at them** — `rundesk schedules remove` or a
  new `--channel`/`--to` is what stops it. Refusing at delivery and saying so in the agent's log
  remains the alternative if that trade is ever revisited.
- **A run that delegated reports to the right destination but not into a thread.** `R-SNT-30` covers
  where it lands; the thread in `R-SNT-19` is opened by the report path, which a delegating run
  suppresses in favour of its review turn. That review answers without quoting the notice — which is
  what it did before any of this existed, for the notified channel too — so on a place target the
  reviewed report stands in the place beside its notice rather than under it.
- **There is no way to clear a destination once set.** `--channel` and `--to` can move one; nothing
  removes one and returns a schedule to the notified channel short of removing and re-adding it. No
  spelling for that was decided.
- **Nothing reports what an adapter says it can do.** `address` is asked at the moment a destination
  is written and thrown away, like the rest of `--capabilities`, so `channels show` cannot tell an
  owner in advance which of their channels a schedule may be pointed at.
- **A thread is remembered in the gateway process and nowhere else.** A gateway that restarts
  mid-run asks the platform for a second thread on the same notice, is refused, and delivers into
  the place — correct and survivable, and not the same thread the earlier pieces went into.
