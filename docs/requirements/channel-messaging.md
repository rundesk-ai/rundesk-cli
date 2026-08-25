---
id: CH
name: A channel conversation and the work that arrives on it
last_verified: 2026-08-25
---

## What this is

Every channel maps a platform's exchanges to durable conversations owned by one agent. Rundesk
authorizes before it records or starts anything, composes platform-neutral context for the agent,
and hands shared state and delivery records back to the adapter. The adapter renders those records
without deciding turn state or exposing private tool detail.

## Why it exists

- A person reaching an agent from chat gets the same identity, conversation, authorization, and
  turn outcome they would get from any other surface.
- Presentation and delivery limits differ between services; who may use the agent, what ran,
  whether it finished, and what was recorded do not.
- An unauthorized person receives no response and causes no provider cost.

## Requirements

A ✅ names the test methods that cite the requirement and were observed to pass on 2026-08-25 —
`test_providers_answering.py`, `test_channels_hosting.py`, `test_channels_discord.py`, and
`test_channels_delivery.py`, 395 tests across the four. A ❌ carries the acceptance that has not
been executed.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-CH-1 | A message from an authorized identity starts or continues work for the agent that owns the channel. | not proven — Send an authorized first message and follow-up and inspect the resulting conversation and turns. |
| ❌ | R-CH-2 | A configured channel belongs to exactly one agent; its messages, conversations, files, and history are never shared with another agent. | not proven — Configure equivalent adapters for two agents and verify isolated records and replies. |
| ❌ | R-CH-3 | Each platform conversation keeps its own provider session, and no two conversations answer into one another. | not proven — Alternate messages across two conversations and inspect session/resume behavior. |
| ❌ | R-CH-4 | A message or gesture from an identity the channel does not authorize is not recorded, answered, reacted to, or sent to a provider. | not proven — Exercise unauthorized message and gesture cases and inspect records, adapter output, and turn count. |
| ❌ | R-CH-5 | Message text cannot choose a different agent, provider, model, or permission posture by naming one. | not proven — Send adversarial message text and inspect the admitted turn. |
| ✅ | R-CH-6 | An attended channel may show broad activity and finished mid-turn remarks while work runs; it never exposes partial prose, raw tool arguments, or raw tool results. | `test_what_the_agent_did_is_shown_while_the_turn_is_still_running` |
| ❌ | R-CH-7 | Agent prose crosses the channel only as complete units; a part-written response is held until complete. | not proven — Exercise fragmented and completed provider text. |
| ❌ | R-CH-8 | The final answer is delivered once and in full, split into bounded pieces when needed; an attachment refusal does not silently remove the answer text. | not proven — Exercise short, long, empty, split, and partly refused attachment outcomes. |
| ✅ | R-CH-9 | A person can stop the active turn in their conversation without stopping another conversation or silently starting queued work behind it. | `test_a_turn_can_be_stopped_from_the_conversation_it_is_running_in` |
| ❌ | R-CH-10 | A person can start their conversation fresh so the next turn does not resume its prior provider session. | not proven — Invoke the shared fresh-session control before, during, and after a turn. |
| ❌ | R-CH-11 | When a turn ends, its provider process and turn-specific work no longer run; the long-lived channel connection may remain hosted. | not proven — Observe child-process and turn-lock state after done, stopped, and failed outcomes. |
| ❌ | R-CH-12 | A channel delivery failure is reported without changing what the provider turn actually did; no failed delivery is marked as a successful answer. | not proven — Refuse final delivery and inspect the turn record, state mark, person-visible fallback, and logs. |
| ✅ | R-CH-13 | Private tool arguments, results, paths, and unknown provider fields remain on the machine unless a separate explicit file-delivery rule permits a file. | `test_activity_carries_what_it_did_and_never_what_the_tool_was_given` |
| ❌ | R-CH-14 | A conversation's provider session can be resumed after its gateway or adapter restarts. | not proven — Complete a turn, restart hosting, and continue the same conversation. |
| ❌ | R-CH-15 | Channel messages and turns are findable afterwards by conversation, source, and turn without relying on adapter-owned history. | not proven — Query the recorded conversation and turn after adapter restart. |
| ❌ | R-CH-16 | An authorized person can request a restart from their channel. Rundesk reports the request immediately, stops the gateway gracefully, and lets supervision bring it back without presenting the acknowledgement as the turn's outcome. | not proven — Exercise restart while idle and working, with and without supervision, and inspect the interaction reply, gateway lifecycle, and active turn. |
| ❌ | R-CH-17 | A message containing only attachments is valid. Accepted inbound files are local, bounded, named safely, and identified to the agent with their absolute local paths. | not proven — Exercise file-only, text-plus-file, invalid, partial, oversized, and duplicate-name messages. |
| ❌ | R-CH-18 | An outbound local file is considered only when the agent explicitly declares it in the final answer; merely reading, editing, or creating a file never sends it. | not proven — Exercise declared and undeclared files, links in code fences, symlinks, changed files, and size/count limits. |
| ✅ | R-CH-19 | A completed mid-turn remark may be shown when the next complete unit establishes that it was not the final answer; the final complete unit is the answer. An explicit final superseded after mid-turn guidance is not shown or remembered as a second answer. | `test_a_finished_thing_said_mid_turn_is_shown_when_the_next_one_arrives`, `test_a_remark_already_posted_is_not_repeated_inside_the_answer`, `test_a_remark_is_plain_and_only_the_answer_is_the_answer` |
| ❌ | R-CH-20 | Nothing a channel does for an unauthorized identity is visible to that identity or billable to the owner. | not proven — Inspect platform activity, records, and provider turns after unauthorized input. |
| ✅ | R-CH-21 | The agent receives platform-neutral context naming the surface, conversation, place, and speaker when the adapter can supply them. Missing optional display words are omitted rather than invented. | `test_a_brain_is_told_who_is_speaking_and_where` |
| ✅ | R-CH-23 | Only an authorized identity receives an answer to a shared gateway query. | `test_a_stranger_is_never_steered_and_never_told_they_are_one` |
| ❌ | R-CH-24 | A shared gateway query is answered from local state and starts no provider turn. | not proven — Compare turn counts before and after `status`, `version`, `agents`, `skills`, `schedules`, and `delegations`. |
| ❌ | R-CH-25 | A follow-up racing with turn completion is either accepted as steering or durably becomes the next turn; it is never lost. | not proven — Drive both sides of the provider-input-close boundary. |
| ✅ | R-CH-26 | A provider change is available only on a single-user channel, changes the agent-wide default atomically, and starts that conversation fresh; a refused change alters nothing. | `test_changing_the_brain_writes_it_down_for_every_turn_after` |
| ✅ | R-CH-28 | A final answer names the resolved provider without exposing the adapter's filesystem location. | `test_the_answer_carries_what_the_turn_cost_and_only_the_first_piece_does` |
| ✅ | R-CH-29 | An inbound reply identifies the earlier platform message and includes bounded author/text context when the adapter resolved it. | `test_a_quoted_message_is_kept_apart_from_what_the_person_typed` |
| ✅ | R-CH-30 | An unresolved inbound reply still starts the turn and says the earlier message could not be read without inventing its author or text. | `test_a_parent_discord_did_not_hand_over_still_says_a_reply_happened`, `test_a_quoted_message_is_kept_apart_from_what_the_person_typed` |
| ✅ | R-CH-31 | A final answer may declare up to the supported count and size of existing absolute local files through Markdown links, images, or local file URLs; machine paths are removed from posted text and refusals are visible. | `test_a_file_the_brain_linked_is_actually_sent`, `test_a_linked_file_is_taken_and_only_its_label_is_left` |
| ❌ | R-CH-32 | When an agent gains or loses a skill, one private owner notice names the change; a refused notice remains pending rather than being reported as delivered. | not proven — Change grants while connected, disconnected, stopped, and on multiple surfaces. |
| ❌ | R-CH-33 | A replacement gateway recovers only the unresolved tail of a channel conversation, exactly once and at most one turn per conversation per sweep; older unclaimed messages cannot replay after later work was admitted. | not proven — Reproduce a stranded latest message, a later answered retry, later unrelated admitted work, concurrent pending messages in one conversation, and independent conversations. |
| ❌ | R-CH-34 | An authorized person can request a graceful gateway shutdown from their channel. The response says what was requested without promising that an unsupervised gateway will return. | not proven — Exercise shutdown with supervised and unsupervised gateways and inspect the private acknowledgement and final gateway state. |
| ❌ | R-CH-35 | The shared delegation query resolves the current platform place to one durable conversation after authorization, joins current named-agent work with only the provider-local lifecycle visible in the current provider session, labels session replacement and delivery routing, and excludes unrelated or stale completed work without mutating state. | not proven — Query authorized and unauthorized identities across two conversations before/after session reset and review; inspect turn/delegation counts, privacy sentinels, item identity/state/routing/timing, and partial-visibility wording. |

## Open questions

- Whether per-channel activity controls and owner-written channel instructions are wanted. Both
  came from the previous build, neither is reachable today, and neither is an implied promise.
- Whether `R-CH-22` and `R-CH-27` were withdrawn deliberately. The numbering skips both.
- Out of scope, and deliberately: provider-adapter behavior and platform-specific presentation,
  which belong to the adapter that owns the platform.
