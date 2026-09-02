---
id: DIS
name: Discord, as an agent is reached on it
last_verified: 2026-09-02
---

## What this is

One Discord bot connection serves an agent's direct messages and the servers it is invited to.
Direct messages stay where they are; a server mention opens a dedicated thread when Discord
permits it, and the agent continues there without another mention. Rundesk supplies the shared
turn records and the adapter renders them with Discord's reactions, typing, replies, private
command responses, and file uploads.

## Why it exists

- An authorized person reaches the intended agent from Discord and can tell whether work was seen,
  is running, or has ended.
- A shared server does not become an always-listening bot, and long-running work stays readable.
- Read-only questions are answered privately without starting a provider turn or spending a token.

## Requirements

A ✅ names the test methods that cite the requirement and were observed to pass on 2026-09-02 —
`test_channels_discord.py`, `test_channels_delivery.py`, `test_channels_hosting.py`, and
`test_providers_answering.py`, 402 tests across the four. A ❌ carries the acceptance that has not
been executed. Offline scenarios cannot prove what Discord's own service displayed.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-DIS-1 | Mentioning the agent in a server channel opens a thread for the conversation when Discord permits it; if thread creation is refused, the agent answers in the originating channel and reports the degradation. | not proven — Exercise successful and permission-refused thread creation on Discord. |
| ❌ | R-DIS-2 | In a shared server channel or another party's thread, the agent stays silent until mentioned by an authorized user. | not proven — Send mentioned and unmentioned messages in rooms and unrelated threads. |
| ❌ | R-DIS-3 | Inside a thread the agent opened, an authorized user can continue without mentioning it again. | not proven — Continue a thread across several turns and a gateway restart. |
| ❌ | R-DIS-4 | In a direct message, the agent answers in that direct conversation. | not proven — Complete new and resumed direct-message turns. |
| ❌ | R-DIS-5 | A recorded inbound message is marked with Discord's seen reaction when its external message id is available. | not proven — Inspect the real message after admission and after a redelivery. |
| ✅ | R-DIS-6 | Discord shows typing while a turn is working and stops renewing it when the turn ends. | `test_a_turn_being_worked_on_starts_the_indicator` |
| ✅ | R-DIS-7 | A terminal turn is marked with one ending reaction for done, stopped, or failed. | `test_the_mark_saying_how_it_ended_goes_on_the_message_that_asked` |
| ✅ | R-DIS-8 | A turn carries one state reaction at a time: the ending reaction is placed before the seen reaction is removed, and a failed replacement leaves the existing reaction rather than erasing state. | `test_the_mark_saying_how_it_ended_goes_on_the_message_that_asked` |
| ✅ | R-DIS-9 | A failed turn is distinguishable from a stopped turn, and its person-visible result does not expose private tool details. | `test_a_failure_says_what_failed_and_never_why` |
| ✅ | R-DIS-10 | Discord offers `/stop`, `/new`, `/restart`, and `/shutdown` as described controls and `/status`, `/version`, `/agents`, `/skills`, `/schedules`, `/delegations`, and `/provider` as described queries/configuration. | `test_every_gesture_is_described_where_it_is_offered` |
| ✅ | R-DIS-11 | A slash command is acknowledged within Discord's interaction window and its final result is private to the invoking user. Results beyond one Discord message continue losslessly across ordered ephemeral followups; if Discord refuses a continuation, a private incomplete-response warning and an adapter log prevent the partial result from looking complete. | `test_a_control_is_held_open_and_completed_by_what_rundesk_says` |
| ❌ | R-DIS-12 | A control that changes a running turn is reflected by that turn's own state and outcome, not invented by the slash-command acknowledgement. | not proven — Stop, restart, and shut down active and idle cases. |
| ❌ | R-DIS-13 | Text longer than one Discord message is split without loss at safe boundaries; only the first answer piece carries reply/recipient emphasis, and declared files accompany the last piece. | not proven — Compare reconstructed short, multiline, and no-break long answers with the original. |
| ❌ | R-DIS-14 | Discord writes are paced and failures are correlated so a refused or rate-limited delivery is never reported as complete. | not proven — Exercise burst, rate-limit, forbidden, deleted-channel, and locked-thread cases. |
| ❌ | R-DIS-15 | Every allowed user receives a private gateway-online notice after the Discord connection is ready and a gateway-going-offline notice during graceful shutdown. | not proven — Start and stop a gateway on real Discord with one and several allowed users, and with no notified channel. |
| ❌ | R-DIS-16 | The bot presents the agent as online while its channel connection is serving and attempts to present it as offline during graceful shutdown without blocking shutdown indefinitely. | not proven — Observe presence across connect, resume, graceful stop, and a presence API refusal. |
| ✅ | R-DIS-17 | A completed answer includes one quiet usage summary and omits quantities the provider did not report. | `test_cache_writes_are_never_shown`, `test_the_answer_carries_what_the_turn_cost_and_only_the_first_piece_does`, `test_the_whole_line_a_person_reads`, `test_what_a_turn_cost_stands_above_the_answer_in_small_print` |
| ❌ | R-DIS-19 | Each accepted local file explicitly declared by the agent is uploaded with the final answer; a verification or Discord refusal is visible and never leaks the machine path. | not proven — Upload representative text/image files and exercise changed, missing, oversized, and permission-refused files. |
| ✅ | R-DIS-20 | Discord renders broad activity compactly while work runs, collapses adjacent repeats, and never shows raw arguments, results, or provider tool names. | `test_a_failure_says_what_failed_and_never_why`, `test_what_the_agent_did_is_shown_while_the_turn_is_still_running` |
| ✅ | R-DIS-21 | The agent is told whether the Discord message came from a direct message, room, or thread, with available server/room/thread and speaker display names in shared platform-neutral context. | `test_a_brain_is_told_who_is_speaking_and_where`, `test_a_direct_message_says_so` |
| ❌ | R-DIS-22 | Discord exposes the shared authorized queries as private slash commands and correlates each private answer with the interaction that requested it. | not proven — Exercise status, version, agents, skills, schedules, and delegations concurrently from authorized and unauthorized users. |
| ❌ | R-DIS-23 | A Discord interaction is handled only by the configured agent channel whose connection received it. | not proven — Configure two agents and ensure one interaction produces one correctly routed answer. |
| ✅ | R-DIS-24 | Completion metadata shows compact elapsed time measured from turn admission until the answer is ready. | `test_the_whole_line_a_person_reads` |
| ❌ | R-DIS-25 | `/provider` is available only when the channel has one authorized user; accepted and refused changes are private and start the conversation fresh only on success. | not proven — Exercise single-user, multi-user, unauthorized, unavailable-provider, and in-flight cases. |
| ❌ | R-DIS-26 | A gateway returning from update maintenance names the installed version now listening and links that release. | not proven — `tests/test_gateway_maintenance.py`; `TheChannelsItHosts.test_a_gateway_returning_from_an_update_names_and_links_the_installed_release`; real-platform presentation check. |
| ❌ | R-DIS-27 | An ordinary gateway startup adds no update wording and no release link. | not proven — `TheChannelsItHosts.test_a_gateway_that_came_up_says_so_through_the_channel_that_is_told_things`; compare with the update-maintenance case. |
| ✅ | R-DIS-28 | The final answer replies to the Discord message that asked when it still belongs to that conversation; a missing or cross-channel reference cannot prevent the answer. | `test_a_remark_is_plain_and_only_the_answer_is_the_answer`, `test_an_answer_in_a_private_conversation_is_quoted_and_tinted`, `test_an_answer_quotes_what_it_answers`, `test_the_answer_quotes_the_message_that_asked` |
| ✅ | R-DIS-29 | When the provider reports conversation size, that size leads the token counts in completion metadata; when it does not, no conversation size is invented. | `test_a_brain_that_said_how_big_the_conversation_got_leads_with_that`, `test_the_answer_carries_what_the_turn_cost_and_only_the_first_piece_does` |
| ❌ | R-DIS-30 | A scheduled agent turn posts one start notice and its final report as a reply to that notice, with no intervening activity posts; an unavailable notice cannot prevent the report. | not proven — Run successful, failed, empty, deleted-notice, and overlapping schedule cases. |
| ❌ | R-DIS-31 | In a multi-person place, the completed answer identifies its human recipient beneath the completion metadata; direct messages and non-answer notices do not add redundant mentions. | not proven — Compare direct, room, thread, split, scheduled, and mid-turn messages. |
| ❌ | R-DIS-32 | Connecting never edits the bot username, avatar, or profile identity configured by its owner in Discord. | not proven — Snapshot bot identity before and after check, connect, and resume. |
| ✅ | R-DIS-33 | Completion metadata begins with the resolved provider name without exposing a path-form provider's filesystem location. | `test_the_answer_carries_what_the_turn_cost_and_only_the_first_piece_does`, `test_the_whole_line_a_person_reads` |
| ✅ | R-DIS-34 | An inbound Discord reply carries the parent message id and available cached author/text into the shared reply context without fetching an unavailable parent. | `test_a_resolved_reply_carries_the_message_it_answers` |
| ❌ | R-DIS-35 | A terminal notice never claims an idle turn is working and never erases the working indication for a newer turn. | not proven — Race two turns and their ending/working state records. |
| ❌ | R-DIS-36 | `/skills` privately lists the current agent's granted skills in a complete, readable response. | not proven — Exercise no grants, many grants beyond one Discord message, and concurrent requests. |
| ❌ | R-DIS-37 | `/schedules` privately lists the current agent's schedules that can still run, soonest first, and says when none remain. | not proven — Exercise repeating, future, expired, disabled, and unreadable schedules. |
| ❌ | R-DIS-38 | An unsolicited notice is sent as a private direct message to every allowed user, starts no conversation, and is not recorded as agent-authored speech. | not proven — Exercise short, long, empty, refused, and retried notices on real Discord. |
| ❌ | R-DIS-39 | A notice addressed to one authorized user is sent privately to that user and refused for an identity outside the channel allow list. | not proven — Exercise authorized and unauthorized targeted notices. |
| ❌ | R-DIS-40 | A completed answer names its recipient only in a place holding more than that one person; a direct message adds no redundant mention. | not proven — Compare direct, room, thread, and scheduled answers. |
| ❌ | R-DIS-41 | When a completed answer names its recipient, the mention stands beneath the completion metadata rather than before it. | not proven — Inspect short and split answers in a multi-person place. |
| ❌ | R-DIS-42 | `/agents` privately lists every known agent in deterministic, case-insensitive agent order. Each agent is exactly `- **name** (provider) — description` followed by `  - Skills: ...`, with skills in deterministic, case-insensitive order. Provider paths expose only their final component; missing providers say `provider unknown`; unreadable providers say `provider cannot be read`. Missing or empty descriptions say `no description`; unreadable descriptions say `description cannot be read`; no grants says `none`; unreadable grants says `cannot be read`. Zero agents says exactly `No agents.` The query starts no provider turn. | not proven — Exercise zero agents, described and undescribed agents, bare/path/missing/unreadable providers, no/one/many grants, unreadable records and grants, case-varied ordering, long output, and concurrent requests; verify exact privacy-safe Markdown, lossless ordered ephemeral followups, and no provider turn. |
| ❌ | R-DIS-43 | `/delegations` privately shows each relevant named-agent and observable provider-local item once for the invoking DM, room, or thread. Named-agent work distinguishes active, stopping, returned-awaiting-review, and reviewed; preserves reset/replacement routing; excludes unrelated and stale work; and exposes no full prompt, result, hidden reasoning, credential, provider tool name, path, or opaque session handle. Provider-local visibility is explicitly partial. | not proven — Exercise authorized and unauthorized DM/room/thread queries, active/stopping/returned/reviewed and stale records, a reset origin routed into the current turn, provider-local start/result records, long concurrent responses, sentinels, and unchanged turn/delegation state. |
| ✅ | R-DIS-44 | Every currently allowed Discord user receives one private copy of an unsolicited notice. A stale stored notification DM and duplicate DM destinations add no recipient, a schedule reply anchor is used only for its primary copy, and every recipient's attachment is independently verified. Direct answers never fan out. | `test_every_allowed_user_receives_the_notice_once`, `test_two_allowed_ids_for_one_dm_still_receive_one_notice`, `test_only_the_primary_notice_copy_quotes_the_schedule_announcement`, `test_each_recipient_gets_a_fresh_verified_attachment`, `test_a_direct_answer_stays_in_the_one_conversation_that_asked` |

## Open questions

- The maintained real-Discord verification pass for platform-only behavior: what it covers, who
  runs it, and which release gate it blocks.
- Whether `R-DIS-18` was withdrawn deliberately. The numbering skips it.
- Out of scope, and deliberately: Slack, per-place channel configuration, and any presentation
  that would change what a turn means rather than how it looks.
