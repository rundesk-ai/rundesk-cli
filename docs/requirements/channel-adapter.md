---
id: CAD
name: The seam a channel adapter is reached through
last_verified: 2026-09-03
---

## What this is

A channel adapter is a program Rundesk runs, never code it loads. One configured adapter is one
connection for one agent, and the platform's rooms, threads, and direct messages become
conversations discovered through that connection. Rundesk owns authorization, durable
conversations, turn state, and lifecycle; the adapter owns platform sign-in, platform vocabulary,
and how shared state is shown there.

## Why it exists

- An owner can reach the same agent from a messaging service without that service becoming part of
  Rundesk, or weakening what other channels rely on.
- An adapter author has one stable boundary: a minimal surface still carries a complete
  conversation, and a capable surface may present it richly without changing what a turn means.
- A third-party adapter can carry the same shared experience with no change to Rundesk's own code.

## Requirements

`R-CAD-25`, `R-CAD-26` and `R-CAD-27` are proven and name the checks that prove them. Every other
row carries the acceptance that has not been executed rather than a citation: `R-CAD-*` is cited in
`src/rundesk/providers/answering.py`, but a citation is not a check. The mechanics of the unproven
rows were inspected against [adapters.md](../extending/adapters.md),
`src/rundesk/channels/adapters.py`, `src/rundesk/channels/hosting.py`, and
`src/rundesk/commands/channels.py`; inspection is not proof.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-CAD-1 | A channel adapter is a program Rundesk runs and isolates, never code it loads into the gateway. | not proven — A custom executable adapter completes capability, connection-check, and hosted-conversation scenarios without a Rundesk source change. |
| ❌ | R-CAD-2 | An adapter Rundesk has never heard of can carry a complete authorized conversation, including a final answer, while unsupported presentation features remain optional. | not proven — Run the minimal custom-adapter scenario from add through one complete conversation. |
| ❌ | R-CAD-3 | Rundesk decides whether work is `seen`, `working`, `done`, `stopped`, or `failed`. | not proven — Drive every state through a stand-in adapter and confirm no adapter record can change the turn's outcome. |
| ❌ | R-CAD-4 | The adapter is told how work stands and decides only how its platform presents that shared state. | not proven — Confirm full and minimal stand-in adapters receive the same states and render them without deriving one. |
| ❌ | R-CAD-5 | A channel with no reactions, typing, editing, threading, or attachments still carries the authorized conversation and final answer. | not proven — Complete the minimal-surface acceptance scenario. |
| ❌ | R-CAD-6 | The agent's gateway hosts its configured channels for the gateway's lifetime and stops them within its shutdown window. | not proven — Exercise gateway start and graceful stop with a hosted stand-in adapter and inspect liveness before and after. |
| ❌ | R-CAD-7 | A recoverable adapter disconnect is reported and retried without ending an active provider turn; a permanent refusal is given up for that gateway lifetime and diagnosed distinctly. | not proven — Exercise recoverable exit and permanent refusal paths, then run channel diagnosis. |
| ❌ | R-CAD-8 | When the agent's gateway is not running, the owner is told the channel is out of reach rather than led to believe messages are being received. | not proven — Inspect channel and gateway status with the gateway stopped. |
| ❌ | R-CAD-9 | Adding or testing a channel proves the adapter can connect before the configuration is accepted; a failed check keeps no channel row. | not proven — Attempt setup with accepted and refused credentials and inspect the resulting channel list. |
| ❌ | R-CAD-10 | Every configured channel has at least one explicitly authorized platform identity; an empty list authorizes nobody and cannot be stored. | not proven — Attempt add and configuration changes that would leave no authorized identity. |
| ❌ | R-CAD-11 | A credential an adapter needs is entered outside the command line, kept in Rundesk's private store, and supplied only under the name the adapter declared. | not proven — Inspect argv, persisted channel settings, backup contents, and the stand-in adapter environment. |
| ❌ | R-CAD-12 | Channel listings, setup results, and diagnosis show only whether a declared credential is present, never its value. | not proven — Exercise every channel readout with a known sentinel credential and confirm the sentinel never appears. |
| ❌ | R-CAD-13 | Platform-specific options and vocabulary remain behind the adapter boundary; shared channel behavior uses platform-neutral terms. | not proven — Add a custom adapter with unfamiliar options and inspect the stored settings and shared records. |
| ❌ | R-CAD-14 | The adapter normalizes its own settings, and Rundesk preserves them without interpreting platform-specific fields. | not proven — Round-trip an unfamiliar settings object through add, show, test, and hosted startup. |
| ❌ | R-CAD-15 | One agent has at most one configured channel for a given adapter. That connection may carry many platform places, each with its own conversation; places are not configured as separate channels. | not proven — Deliver direct, room, and thread messages through one adapter row and confirm their conversations remain distinct. |
| ❌ | R-CAD-17 | An authorized channel can ask a closed set of read-only gateway questions: `status`, `version`, `agents`, `skills`, and `schedules`. Unknown questions do nothing. | not proven — Exercise every shared query and an unknown query through a stand-in adapter. |
| ❌ | R-CAD-18 | A channel may request a provider change only through Rundesk's shared authorization and single-user guard, and it receives a correlated result. | not proven — Exercise accepted, unauthorized, shared-channel, and unavailable-provider cases. |
| ❌ | R-CAD-19 | An owner can inspect and change who may reach an existing channel, but cannot remove an identity that was never allowed or reduce the channel to nobody. | not proven — Exercise add, deny, replacement, unknown-id, and last-id cases. |
| ❌ | R-CAD-20 | Records crossing the adapter boundary identify a conversation with the platform's identifier, never an internal Rundesk database id. | not proven — Inspect inbound and outbound records for a representative conversation. |
| ❌ | R-CAD-21 | Values Rundesk keeps for other purposes are not inherited by an adapter; it receives only the bounded runtime environment and credentials it declared. | not proven — Start a stand-in adapter beside sentinel environment values and inspect its environment. |
| ❌ | R-CAD-22 | The owner can list, inspect, reconnect-test, configure, remove, and diagnose a channel, with missing credentials, unreachable platforms, missing adapters, and a gateway that gave up reported as different states. | not proven — Execute the channel management flow against each state and compare the result and exit code. |
| ❌ | R-CAD-23 | An adapter declares what it can present, and the owner is shown that declaration during setup without the channel becoming unusable for abilities it lacks. | not proven — Add adapters with full and empty capability declarations and complete a conversation on both. |
| ❌ | R-CAD-24 | A transient adapter disconnect marks the channel offline immediately, gives the adapter time to reconnect itself, and replaces a live adapter that remains disconnected; durable messages wait until the channel is ready. | not proven — Simulate `ready` → `gone` → `ready`, then `ready` → `gone` without recovery; inspect channel status, adapter replacement, pending-message recovery, and permanent `EX_CONFIG` refusal. |
| ✅ | R-CAD-25 | An adapter may report the platform's own identifier for the place a message or gesture came from, and is handed the allowed senders and the allowed places as two separate values. An adapter that reports no place, and one that has never heard of the second value, keeps working unchanged. | `test_an_adapter_is_handed_the_senders_bare_and_the_places_apart` (hosting and command), `test_an_arrival_that_names_no_place_still_admits_a_named_sender`, `test_the_stable_place_is_carried_in_a_field_of_its_own` |
| ✅ | R-CAD-26 | Where a caller waited for a delivery to land and no acknowledgement arrived, the agent's log says so and names how many of the deliveries are still outstanding, counted after the wait so a late acknowledgement is never reported as an unanswered one. It records that the outcome is unknown, never that the platform refused: an adapter that acknowledges nothing is a whole adapter and no turn fails over the line. | `test_a_delivery_nobody_ever_answered_is_said_rather_than_passed_over`, `test_only_the_deliveries_still_outstanding_are_counted`, `test_a_delivery_that_was_answered_is_not_reported_as_unanswered` |
| ✅ | R-CAD-27 | An answer is composed for the surface that will show it, from the `stream` capability the adapter declares. Where a surface shows a turn as it happens, each finished thought is delivered as it is superseded, marked as something said on the way to the answer, and the answer is the last thought. Where a surface shows nothing until the end, no such delivery is sent and the answer is every finished thought **after the brain's last tool call**, joined — so several closing thoughts all survive while what was said before and between the tools, which is working narration, is in neither. An explicit final supersedes in both, and the latest one alone is the answer rather than every marked one joined. Where such a turn completes and closes without a word after its last tool call, one short factual line is delivered rather than nothing at all — it claims neither success nor failure and says nothing about what the work did — while a turn somebody stopped stays silent. An adapter that declares nothing keeps the first behaviour, no surface infers the phase from the text, and a file declared in an unposted thought still travels with the answer. | `test_a_surface_that_shows_only_the_answer_is_given_every_finished_thought`, `test_working_narration_is_left_out_of_a_quiet_surfaces_answer`, `test_a_quiet_surface_posts_only_the_latest_of_two_explicit_finals`, `test_a_completed_quiet_turn_that_closed_on_nothing_still_says_so`, `test_a_stopped_quiet_turn_that_closed_on_nothing_stays_silent`, `test_a_surface_that_shows_a_turn_as_it_happens_still_gets_commentary`, `test_an_adapter_that_declares_nothing_keeps_the_commentary_it_always_had`, `test_a_file_declared_in_an_unposted_thought_still_goes_with_the_answer`, `test_a_remark_says_it_is_one_so_a_final_only_surface_can_tell`, `test_a_delivery_marked_as_a_remark_is_still_shown_here` (Discord), `test_something_said_on_the_way_to_an_answer_is_not_posted` (Slack), and the composition itself in `test_every_thought_after_the_last_tool_joins_in_the_order_it_was_said`, `test_working_narration_before_and_between_the_tools_is_left_out`, `test_the_latest_explicit_final_is_the_whole_closing_response`, `test_a_turn_that_closed_at_a_tool_boundary_has_no_closing_response` (protocol) |

## Open questions

- Which declared abilities and limits Rundesk must retain and honor before capability negotiation
  is complete. It shows the capability object today and keeps little of it, so a second adapter
  with a smaller text limit could expose drift.
- Whether one conversation may span more than one surface. An agent may hold several adapter
  connections; conversation linking is undefined and should be decided before it is built.
- The maintained real-platform acceptance protocol and release gate. Offline lifecycle tests
  cannot prove service reconnection or display behavior.
- Whether `R-CAD-16` was withdrawn deliberately. The numbering skips it.
- Out of scope, and deliberately: provider-adapter behavior, platform-specific presentation —
  Discord's in [channel-discord.md](./channel-discord.md) and Slack's in
  [channel-slack.md](./channel-slack.md) — a marketplace or remote adapter registry, and per-place
  channel *configuration*. A place named on the allow list is not that: it is who may reach the
  agent, and the channel is still one connection with nothing written down per place.
