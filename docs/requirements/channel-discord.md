---
id: DIS
name: Discord as an agent is reached on it
status: draft
owner: Rundesk product owner
last_updated: 2026-08-08
---

# Discord channel adapter product contract

## Problem and evidence

An owner wants the same persistent Rundesk agent available in Discord without turning a shared
server into an always-listening bot or making long-running work unreadable. Discord adds platform
constraints—mentions, threads, message limits, interaction deadlines, reactions, presence, and
permissions—that must preserve the shared channel contract rather than redefine it.

The predecessor Discord requirements established the intended experience. Current behavior is
described in [adapters.md](../adapters.md), [commands.md](../commands.md#channels), the shipped
`src/channels/discord` adapter, and focused tests. The product owner added `/agents` on 2026-08-08 as
an install-wide, private, read-only Discord query.

## Outcome and success

An authorized Discord user can reach the intended agent in a direct message or server conversation,
understand whether work was seen, is active, or ended, and receive the complete answer and declared
files. Read-only commands answer privately without starting a provider turn.

Success is accepted through offline scenarios plus a maintained real-Discord verification pass for
platform-only behavior. No post-release adoption target has been set.

## Product solution

One Discord bot connection serves an agent's direct messages and invited servers. Direct messages
stay in place. A server mention opens a dedicated thread when Discord permits it, and the agent
continues in that thread without another mention. Rundesk supplies shared turn records; the Discord
adapter renders them with Discord's reactions, typing, replies, private command responses, and file
uploads.

## Requirements

| ID | Product condition | Acceptance evidence |
|---|---|---|
| R-DIS-1 | Mentioning the agent in a server channel opens a thread for the conversation when Discord permits it; if thread creation is refused, the agent answers in the originating channel and reports the degradation. | Exercise successful and permission-refused thread creation on Discord. |
| R-DIS-2 | In a shared server channel or another party's thread, the agent stays silent until mentioned by an authorized user. | Send mentioned and unmentioned messages in rooms and unrelated threads. |
| R-DIS-3 | Inside a thread the agent opened, an authorized user can continue without mentioning it again. | Continue a thread across several turns and a gateway restart. |
| R-DIS-4 | In a direct message, the agent answers in that direct conversation. | Complete new and resumed direct-message turns. |
| R-DIS-5 | A recorded inbound message is marked with Discord's seen reaction when its external message id is available. | Inspect the real message after admission and after a redelivery. |
| R-DIS-6 | Discord shows typing while a turn is working and stops renewing it when the turn ends. | Observe a long-running real turn through done, stopped, and failed endings. |
| R-DIS-7 | A terminal turn is marked with one ending reaction for done, stopped, or failed. | Exercise each ending and inspect the final reaction. |
| R-DIS-8 | A turn carries one state reaction at a time: the ending reaction is placed before the seen reaction is removed, and a failed replacement leaves the existing reaction rather than erasing state. | Exercise successful and refused reaction replacement and inspect event order. |
| R-DIS-9 | A failed turn is distinguishable from a stopped turn, and its person-visible result does not expose private tool details. | Exercise provider, tool, and delivery failures plus an explicit stop. |
| R-DIS-10 | Discord offers `/stop`, `/new`, `/restart`, and `/shutdown` as described controls and `/status`, `/version`, `/agents`, `/skills`, `/schedules`, and `/provider` as described queries/configuration. | Inspect registered commands and exercise each as an authorized user. |
| R-DIS-11 | A slash command is acknowledged within Discord's interaction window and its final result is private to the invoking user. Results beyond one Discord message continue losslessly across ordered ephemeral followups; if Discord refuses a continuation, a private incomplete-response warning and an adapter log prevent the partial result from looking complete. | Exercise every command on real Discord under ordinary and delayed gateway handling, including complete and refused multi-message results; reconstruct complete results and inspect the warning and log for a refusal. |
| R-DIS-12 | A control that changes a running turn is reflected by that turn's own state and outcome, not invented by the slash-command acknowledgement. | Stop, restart, and shut down active and idle cases. |
| R-DIS-13 | Text longer than one Discord message is split without loss at safe boundaries; only the first answer piece carries reply/recipient emphasis, and declared files accompany the last piece. | Compare reconstructed short, multiline, and no-break long answers with the original. |
| R-DIS-14 | Discord writes are paced and failures are correlated so a refused or rate-limited delivery is never reported as complete. | Exercise burst, rate-limit, forbidden, deleted-channel, and locked-thread cases. |
| R-DIS-15 | The notified owner receives a gateway-online notice after the Discord connection is ready and a gateway-going-offline notice during graceful shutdown. | Start and stop a gateway on real Discord with and without a notified channel. |
| R-DIS-16 | The bot presents the agent as online while its channel connection is serving and attempts to present it as offline during graceful shutdown without blocking shutdown indefinitely. | Observe presence across connect, resume, graceful stop, and a presence API refusal. |
| R-DIS-17 | A completed answer includes one quiet usage summary and omits quantities the provider did not report. | Exercise providers with full, partial, zero, and missing usage. |
| R-DIS-19 | Each accepted local file explicitly declared by the agent is uploaded with the final answer; a verification or Discord refusal is visible and never leaks the machine path. | Upload representative text/image files and exercise changed, missing, oversized, and permission-refused files. |
| R-DIS-20 | Discord renders broad activity compactly while work runs, collapses adjacent repeats, and never shows raw arguments, results, or provider tool names. | Run representative read/search/run/edit/make/delegate activity and inspect posts/edits. |
| R-DIS-21 | The agent is told whether the Discord message came from a direct message, room, or thread, with available server/room/thread and speaker display names in shared platform-neutral context. | Compare prompt context for each Discord place shape and missing display metadata. |
| R-DIS-22 | Discord exposes the shared authorized queries as private slash commands and correlates each private answer with the interaction that requested it. | Exercise status, version, agents, skills, and schedules concurrently from authorized and unauthorized users. |
| R-DIS-23 | A Discord interaction is handled only by the configured agent channel whose connection received it. | Configure two agents and ensure one interaction produces one correctly routed answer. |
| R-DIS-24 | Completion metadata shows compact elapsed time measured from turn admission until the answer is ready. | Exercise second-, minute-, and hour-length examples plus repeated admission records. |
| R-DIS-25 | `/provider` is available only when the channel has one authorized user; accepted and refused changes are private and start the conversation fresh only on success. | Exercise single-user, multi-user, unauthorized, unavailable-provider, and in-flight cases. |
| R-DIS-26 | A gateway returning from update maintenance names the installed version now listening and links that release. | Exercise the first startup after update maintenance. |
| R-DIS-27 | An ordinary gateway startup adds no update wording and no release link. | Compare ordinary startup with the update-maintenance notice. |
| R-DIS-28 | The final answer replies to the Discord message that asked when it still belongs to that conversation; a missing or cross-channel reference cannot prevent the answer. | Exercise direct, room, thread, deleted-question, and split-answer cases. |
| R-DIS-29 | When the provider reports conversation size, that size leads the token counts in completion metadata; when it does not, no conversation size is invented. | Exercise complete and missing-context usage reports. |
| R-DIS-30 | A scheduled agent turn posts one start notice and its final report as a reply to that notice, with no intervening activity posts; an unavailable notice cannot prevent the report. | Run successful, failed, empty, deleted-notice, and overlapping schedule cases. |
| R-DIS-31 | In a multi-person place, the completed answer identifies its human recipient beneath the completion metadata; direct messages and non-answer notices do not add redundant mentions. | Compare direct, room, thread, split, scheduled, and mid-turn messages. |
| R-DIS-32 | Connecting never edits the bot username, avatar, or profile identity configured by its owner in Discord. | Snapshot bot identity before and after check, connect, and resume. |
| R-DIS-33 | Completion metadata begins with the resolved provider name without exposing a path-form provider's filesystem location. | Exercise named and path-form providers. |
| R-DIS-34 | An inbound Discord reply carries the parent message id and available cached author/text into the shared reply context without fetching an unavailable parent. | Exercise resolved, cached, deleted, forwarded, and ordinary messages. |
| R-DIS-35 | A terminal notice never claims an idle turn is working and never erases the working indication for a newer turn. | Race two turns and their ending/working state records. |
| R-DIS-36 | `/skills` privately lists the current agent's granted skills in a complete, readable response. | Exercise no grants, many grants beyond one Discord message, and concurrent requests. |
| R-DIS-37 | `/schedules` privately lists the current agent's schedules that can still run, soonest first, and says when none remain. | Exercise repeating, future, expired, disabled, and unreadable schedules. |
| R-DIS-38 | A notice meant for the owner alone is sent as a direct message, starts no conversation, and is not recorded as agent-authored speech. | Exercise short, long, empty, refused, and retried notices. |
| R-DIS-39 | A notice addressed to one authorized user is sent privately to that user and refused for an identity outside the channel allow list. | Exercise authorized and unauthorized targeted notices. |
| R-DIS-40 | A completed answer names its recipient only in a place holding more than that one person; a direct message adds no redundant mention. | Compare direct, room, thread, and scheduled answers. |
| R-DIS-41 | When a completed answer names its recipient, the mention stands beneath the completion metadata rather than before it. | Inspect short and split answers in a multi-person place. |
| R-DIS-42 | `/agents` privately lists every known agent in deterministic, case-insensitive agent order. Each agent is exactly `- **name** — description` followed by `  - Skills: ...`, with skills in deterministic, case-insensitive order. Missing or empty descriptions say `no description`; unreadable descriptions say `description cannot be read`; no grants says `none`; unreadable grants says `cannot be read`. Zero agents says exactly `No agents.` The query starts no provider turn. | Exercise zero agents, described and undescribed agents, no/one/many grants, unreadable records and grants, case-varied ordering, long output, and concurrent requests; verify the exact Markdown, lossless ordered ephemeral followups, and no provider turn. |

## Scope

**In:** Discord setup and connection; direct/server/thread triggering; state, activity, answer, reply,
file, presence, notice, and slash-command rendering; the new `/agents` command.

**Out:** Slack; Discord administration beyond the bot's required permissions; automatic thread
archival; provider behavior; a general web console; public command responses.

## Decisions and open questions

| Item | Status and impact | Decision needed |
|---|---|---|
| `/agents` access | **Decided:** it follows the existing read-only query boundary. Any user authorized on this channel may invoke the install-wide query, and only that user sees the response. | None. |
| `/agents` ordering and empty states | **Decided:** agents and skills sort case-insensitively with deterministic tie-breaking. Missing or empty description is `no description`; unreadable description is `description cannot be read`; no grants is `none`; unreadable grants is `cannot be read`; zero agents is `No agents.` | None. |
| Very long prose as a file | Current behavior splits text. The predecessor also required an automatic text-file fallback, which is not approved for this revision. | Decide whether and at what threshold Discord should attach prose instead of splitting it. |
| Activity control | Owned by the shared PRD; current Discord behavior renders the activity it receives. | Resolve the shared activity-policy decision before adding a Discord-specific switch. |
| Thread lifecycle | Rundesk opens threads but no product direction says whether it archives quiet ones. | Decide only if automatic archival is proposed. |
| Multi-person steering | Authorization is shared, but who may steer an active turn in a multi-user thread is not separately defined. | Decide before introducing per-turn speaker ownership. |
| Real-Discord release evidence | Offline suites cannot prove reactions, typing, presence, command timing, permission grants, or upload presentation. | Establish and maintain a scratch-bot verification protocol and its release cadence. |

## Validation

| Requirement area | Current evidence checked | Result | Last checked |
|---|---|---|---|
| Routing, replies, rendering, commands | `src/channels/discord`, `tests/test_channels_discord.py` | Offline suite passed on current Python and macOS Python 3.9; real-Discord acceptance was not executed. | 2026-08-08 |
| Shared delivery and turn composition | `src/rundesk/channels/hosting.py`, `src/rundesk/providers/answering.py`, `tests/test_channels_hosting.py`, `tests/test_providers_answering.py` | Offline suites passed on current Python and macOS Python 3.9. | 2026-08-08 |
| Gateway and scheduled notices | `src/rundesk/gateways/host.py`, `tests/test_gateway_host.py` | Current mechanics inspected; R-DIS-30 is implemented in this branch, correcting the stale predecessor note. | 2026-08-08 |
| `/agents` | R-DIS-42; focused Discord, hosting, and provider-answering scenarios plus the full 67-suite runs on current Python and macOS Python 3.9. | Offline acceptance passed for exact nested bullets, escaping/flattening, empty and unreadable states, ordering, authorization, no provider turn, lossless pagination, and visible continuation refusal. Real-Discord presentation remains unvalidated. | 2026-08-08 |
