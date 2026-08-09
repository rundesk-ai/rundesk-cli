---
id: CH
name: A channel conversation and the work that arrives on it
status: draft
owner: Rundesk product owner
last_updated: 2026-08-08
---

# Shared channel messaging product contract

## Problem and evidence

A person reaching a persistent agent from chat needs the same identity, conversation, authorization,
and turn outcome they would get from another surface. Messaging services differ in presentation and
delivery limits, but those differences must not change who may use the agent, what work ran, whether
it finished, or what was recorded.

The predecessor contract supplied the original behaviors. Current evidence lives in
[adapters.md](../adapters.md), the channel/provider seams, and their focused tests. Two predecessor
directions are not currently reachable and remain product decisions rather than implied promises:
per-channel activity controls and owner-written channel instructions.

## Outcome and success

An authorized person can continue a durable conversation, see an honest account of the turn, and
exchange replies and files without cross-conversation leakage or machine-path disclosure. An
unauthorized person receives no response and causes no provider cost.

Success is accepted through the observable scenarios below. No post-release usage measure has been
set for this increment.

## Product solution

Every channel maps platform exchanges to durable conversations owned by one agent. Rundesk performs
authorization before recording or starting work, composes platform-neutral context for the agent,
and sends shared state and delivery records back to the adapter. The adapter renders those records
without deciding turn state or exposing private tool details.

## Requirements

| ID | Product condition | Acceptance evidence |
|---|---|---|
| R-CH-1 | A message from an authorized identity starts or continues work for the agent that owns the channel. | Send an authorized first message and follow-up and inspect the resulting conversation and turns. |
| R-CH-2 | A configured channel belongs to exactly one agent; its messages, conversations, files, and history are never shared with another agent. | Configure equivalent adapters for two agents and verify isolated records and replies. |
| R-CH-3 | Each platform conversation keeps its own provider session, and no two conversations answer into one another. | Alternate messages across two conversations and inspect session/resume behavior. |
| R-CH-4 | A message or gesture from an identity the channel does not authorize is not recorded, answered, reacted to, or sent to a provider. | Exercise unauthorized message and gesture cases and inspect records, adapter output, and turn count. |
| R-CH-5 | Message text cannot choose a different agent, provider, model, or permission posture by naming one. | Send adversarial message text and inspect the admitted turn. |
| R-CH-6 | An attended channel may show broad activity and finished mid-turn remarks while work runs; it never exposes partial prose, raw tool arguments, or raw tool results. | Stream representative provider records and inspect every delivery offered to a stand-in channel. |
| R-CH-7 | Agent prose crosses the channel only as complete units; a part-written response is held until complete. | Exercise fragmented and completed provider text. |
| R-CH-8 | The final answer is delivered once and in full, split into bounded pieces when needed; an attachment refusal does not silently remove the answer text. | Exercise short, long, empty, split, and partly refused attachment outcomes. |
| R-CH-9 | A person can stop the active turn in their conversation without stopping another conversation or silently starting queued work behind it. | Run two conversations, stop one, and inspect both outcomes and queues. |
| R-CH-10 | A person can start their conversation fresh so the next turn does not resume its prior provider session. | Invoke the shared fresh-session control before, during, and after a turn. |
| R-CH-11 | When a turn ends, its provider process and turn-specific work no longer run; the long-lived channel connection may remain hosted. | Observe child-process and turn-lock state after done, stopped, and failed outcomes. |
| R-CH-12 | A channel delivery failure is reported without changing what the provider turn actually did; no failed delivery is marked as a successful answer. | Refuse final delivery and inspect the turn record, state mark, person-visible fallback, and logs. |
| R-CH-13 | Private tool arguments, results, paths, and unknown provider fields remain on the machine unless a separate explicit file-delivery rule permits a file. | Feed sentinel private values through provider records and inspect adapter deliveries. |
| R-CH-14 | A conversation's provider session can be resumed after its gateway or adapter restarts. | Complete a turn, restart hosting, and continue the same conversation. |
| R-CH-15 | Channel messages and turns are findable afterwards by conversation, source, and turn without relying on adapter-owned history. | Query the recorded conversation and turn after adapter restart. |
| R-CH-16 | An authorized person can request a restart from their channel. Rundesk reports the request immediately, stops the gateway gracefully, and lets supervision bring it back without presenting the acknowledgement as the turn's outcome. | Exercise restart while idle and working, with and without supervision, and inspect the interaction reply, gateway lifecycle, and active turn. |
| R-CH-17 | A message containing only attachments is valid. Accepted inbound files are local, bounded, named safely, and identified to the agent with their absolute local paths. | Exercise file-only, text-plus-file, invalid, partial, oversized, and duplicate-name messages. |
| R-CH-18 | An outbound local file is considered only when the agent explicitly declares it in the final answer; merely reading, editing, or creating a file never sends it. | Exercise declared and undeclared files, links in code fences, symlinks, changed files, and size/count limits. |
| R-CH-19 | A completed mid-turn remark may be shown when the next complete unit establishes that it was not the final answer; the final complete unit is the answer. An explicit final superseded after mid-turn guidance is not shown or remembered as a second answer. | Exercise one and several complete provider thoughts with and without intervening activity, including two explicit finals separated by guidance. |
| R-CH-20 | Nothing a channel does for an unauthorized identity is visible to that identity or billable to the owner. | Inspect platform activity, records, and provider turns after unauthorized input. |
| R-CH-21 | The agent receives platform-neutral context naming the surface, conversation, place, and speaker when the adapter can supply them. Missing optional display words are omitted rather than invented. | Compare direct, room, thread, named, and unnamed context blocks. |
| R-CH-23 | Only an authorized identity receives an answer to a shared gateway query. | Exercise every query as authorized and unauthorized identities. |
| R-CH-24 | A shared gateway query is answered from local state and starts no provider turn. | Compare turn counts before and after `status`, `version`, `agents`, `skills`, and `schedules`. |
| R-CH-25 | A follow-up racing with turn completion is either accepted as steering or durably becomes the next turn; it is never lost. | Drive both sides of the provider-input-close boundary. |
| R-CH-26 | A provider change is available only on a single-user channel, changes the agent-wide default atomically, and starts that conversation fresh; a refused change alters nothing. | Exercise accepted, shared-channel, unauthorized, unavailable-provider, and in-flight cases. |
| R-CH-28 | A final answer names the resolved provider without exposing the adapter's filesystem location. | Run named and path-form providers and inspect the completion metadata. |
| R-CH-29 | An inbound reply identifies the earlier platform message and includes bounded author/text context when the adapter resolved it. | Exercise resolved replies with long and multiline fields. |
| R-CH-30 | An unresolved inbound reply still starts the turn and says the earlier message could not be read without inventing its author or text. | Exercise deleted, uncached, and otherwise unavailable reply parents. |
| R-CH-31 | A final answer may declare up to the supported count and size of existing absolute local files through Markdown links, images, or local file URLs; machine paths are removed from posted text and refusals are visible. | Exercise each declaration form, encoded paths, duplicates, limits, replacement races, and refusal wording. |
| R-CH-32 | When an agent gains or loses a skill, one private owner notice names the change; a refused notice remains pending rather than being reported as delivered. | Change grants while connected, disconnected, stopped, and on multiple surfaces. |
| R-CH-33 | A replacement gateway recovers only the unresolved tail of a channel conversation, exactly once and at most one turn per conversation per sweep; older unclaimed messages cannot replay after later work was admitted. | Reproduce a stranded latest message, a later answered retry, later unrelated admitted work, concurrent pending messages in one conversation, and independent conversations. |
| R-CH-34 | An authorized person can request a graceful gateway shutdown from their channel. The response says what was requested without promising that an unsupervised gateway will return. | Exercise shutdown with supervised and unsupervised gateways and inspect the private acknowledgement and final gateway state. |

## Scope

**In:** authorization; conversation/session identity; turn activity and final answers; shared
controls and queries; replies; inbound and outbound attachments; private operational notices.

**Out:** Discord-specific rendering; channel setup and credentials; provider protocol internals;
cross-surface conversation linking; pricing or spend limits.

## Decisions and open questions

| Item | Status and impact | Decision needed |
|---|---|---|
| Activity visibility | The predecessor required an owner-controlled quiet channel, but the current product exposes no channel switch and always offers broad activity to capable surfaces. | Decide whether activity is always on, off by default, or configurable before restoring R-CH-27. |
| Owner-written channel instructions | Predecessor R-CH-22 required them; the current channel schema and command surface have no reachable setting. | Decide whether this product direction carries forward before adding persisted state. |
| Newly allowed user introduction | Predecessor R-CH-33 required an agent-authored private greeting; no current behavior was established in this audit. | Decide whether to carry it forward and who receives it before specifying acceptance. |
| Conversation retention | Current records are durable, but no product retention window is approved. | Decide before any automated conversation or message deletion is introduced. |

## Validation

| Requirement area | Current evidence checked | Result | Last checked |
|---|---|---|---|
| Authorization and inbound flow | `src/rundesk/channels/hosting.py`, `src/rundesk/channels/arriving.py`, `tests/test_channels_hosting.py`, `tests/test_channels_arriving.py` | Current mechanics inspected; acceptance not executed in this PRD pass. | 2026-08-08 |
| Turn presentation and controls | `src/rundesk/providers/answering.py`, `tests/test_providers_answering.py` | Offline suite passed on current Python and macOS Python 3.9; activity-policy decision remains open. | 2026-08-08 |
| Attachments and replies | `src/rundesk/channels/files.py`, `src/rundesk/channels/delivery.py`, `tests/test_channels_files.py`, `tests/test_channels_delivery.py` | Current mechanics inspected; acceptance not executed in this PRD pass. | 2026-08-08 |
| Operational notices | `src/rundesk/gateways/host.py`, `tests/test_gateway_host.py` | Skill-change notice mechanics inspected; newly allowed user greeting not established. | 2026-08-08 |
