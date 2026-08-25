---
id: CAD
name: The seam a channel adapter is reached through
status: draft
owner: Rundesk product owner
last_updated: 2026-08-21
---

# Channel adapter product contract

## Problem and evidence

An owner must be able to reach the same Rundesk agent from a messaging service without that service
becoming part of Rundesk's core or weakening the guarantees other channels rely on. Adapter authors
also need one stable product boundary: a minimal surface must still carry a complete conversation,
and a capable surface may add richer presentation without changing what a turn means.

The predecessor requirements established the external-adapter direction. The current product proves
that shape with the shipped Discord adapter and the contract in [adapters.md](../adapters.md). The
current product deliberately changed one predecessor decision: a channel is now one adapter
connection for one agent, not one configured row for every place on a platform.

## Outcome and success

An owner can add, diagnose, operate, and remove a supported channel with predictable authorization,
credential, lifecycle, and failure behavior. A third-party adapter can carry the same shared channel
experience without a Rundesk core change.

Success is accepted requirement by requirement. Real-platform behavior is validated separately from
offline protocol and lifecycle behavior; no aggregate adoption or reliability target has been set.

## Product solution

Rundesk runs a channel adapter as an external program. One configured adapter is one connection for
one agent, and platform rooms, threads, and direct messages become conversations discovered through
that connection. Rundesk owns authorization, durable conversations, turn state, and lifecycle;
the adapter owns platform sign-in, platform vocabulary, and how shared state appears there.

## Requirements

| ID | Product condition | Acceptance evidence |
|---|---|---|
| R-CAD-1 | A channel adapter is a program Rundesk runs and isolates, never code it loads into the gateway. | A custom executable adapter completes capability, connection-check, and hosted-conversation scenarios without a Rundesk source change. |
| R-CAD-2 | An adapter Rundesk has never heard of can carry a complete authorized conversation, including a final answer, while unsupported presentation features remain optional. | Run the minimal custom-adapter scenario from add through one complete conversation. |
| R-CAD-3 | Rundesk decides whether work is `seen`, `working`, `done`, `stopped`, or `failed`. | Drive every state through a stand-in adapter and confirm no adapter record can change the turn's outcome. |
| R-CAD-4 | The adapter is told how work stands and decides only how its platform presents that shared state. | Confirm full and minimal stand-in adapters receive the same states and render them without deriving one. |
| R-CAD-5 | A channel with no reactions, typing, editing, threading, or attachments still carries the authorized conversation and final answer. | Complete the minimal-surface acceptance scenario. |
| R-CAD-6 | The agent's gateway hosts its configured channels for the gateway's lifetime and stops them within its shutdown window. | Exercise gateway start and graceful stop with a hosted stand-in adapter and inspect liveness before and after. |
| R-CAD-7 | A recoverable adapter disconnect is reported and retried without ending an active provider turn; a permanent refusal is given up for that gateway lifetime and diagnosed distinctly. | Exercise recoverable exit and permanent refusal paths, then run channel diagnosis. |
| R-CAD-8 | When the agent's gateway is not running, the owner is told the channel is out of reach rather than led to believe messages are being received. | Inspect channel and gateway status with the gateway stopped. |
| R-CAD-9 | Adding or testing a channel proves the adapter can connect before the configuration is accepted; a failed check keeps no channel row. | Attempt setup with accepted and refused credentials and inspect the resulting channel list. |
| R-CAD-10 | Every configured channel has at least one explicitly authorized platform identity; an empty list authorizes nobody and cannot be stored. | Attempt add and configuration changes that would leave no authorized identity. |
| R-CAD-11 | A credential an adapter needs is entered outside the command line, kept in Rundesk's private store, and supplied only under the name the adapter declared. | Inspect argv, persisted channel settings, backup contents, and the stand-in adapter environment. |
| R-CAD-12 | Channel listings, setup results, and diagnosis show only whether a declared credential is present, never its value. | Exercise every channel readout with a known sentinel credential and confirm the sentinel never appears. |
| R-CAD-13 | Platform-specific options and vocabulary remain behind the adapter boundary; shared channel behavior uses platform-neutral terms. | Add a custom adapter with unfamiliar options and inspect the stored settings and shared records. |
| R-CAD-14 | The adapter normalizes its own settings, and Rundesk preserves them without interpreting platform-specific fields. | Round-trip an unfamiliar settings object through add, show, test, and hosted startup. |
| R-CAD-15 | One agent has at most one configured channel for a given adapter. That connection may carry many platform places, each with its own conversation; places are not configured as separate channels. | Deliver direct, room, and thread messages through one adapter row and confirm their conversations remain distinct. |
| R-CAD-17 | An authorized channel can ask a closed set of read-only gateway questions: `status`, `version`, `agents`, `skills`, and `schedules`. Unknown questions do nothing. | Exercise every shared query and an unknown query through a stand-in adapter. |
| R-CAD-18 | A channel may request a provider change only through Rundesk's shared authorization and single-user guard, and it receives a correlated result. | Exercise accepted, unauthorized, shared-channel, and unavailable-provider cases. |
| R-CAD-19 | An owner can inspect and change who may reach an existing channel, but cannot remove an identity that was never allowed or reduce the channel to nobody. | Exercise add, deny, replacement, unknown-id, and last-id cases. |
| R-CAD-20 | Records crossing the adapter boundary identify a conversation with the platform's identifier, never an internal Rundesk database id. | Inspect inbound and outbound records for a representative conversation. |
| R-CAD-21 | Values Rundesk keeps for other purposes are not inherited by an adapter; it receives only the bounded runtime environment and credentials it declared. | Start a stand-in adapter beside sentinel environment values and inspect its environment. |
| R-CAD-22 | The owner can list, inspect, reconnect-test, configure, remove, and diagnose a channel, with missing credentials, unreachable platforms, missing adapters, and a gateway that gave up reported as different states. | Execute the channel management flow against each state and compare the result and exit code. |
| R-CAD-23 | An adapter declares what it can present, and the owner is shown that declaration during setup without the channel becoming unusable for abilities it lacks. | Add adapters with full and empty capability declarations and complete a conversation on both. |
| R-CAD-24 | A transient adapter disconnect marks the channel offline immediately, gives the adapter time to reconnect itself, and replaces a live adapter that remains disconnected; durable messages wait until the channel is ready. | Simulate `ready` → `gone` → `ready`, then `ready` → `gone` without recovery; inspect channel status, adapter replacement, pending-message recovery, and permanent `EX_CONFIG` refusal. |

## Scope

**In:** custom and shipped channel adapters; setup and management; authorization; credentials;
gateway hosting and recovery; the shared query/configuration seam.

**Out:** provider-adapter behavior; platform-specific Discord presentation; Slack; a marketplace or
remote adapter registry; per-place channel configuration.

## Decisions and open questions

| Item | Status and impact | Decision needed |
|---|---|---|
| One connection rather than one channel per platform place | Decided by the current product; this supersedes the predecessor wording of R-CAD-15. | None. |
| Capability enforcement | Rundesk currently shows the capability object but keeps little of it; a second adapter with a smaller text limit could expose drift. | Decide which declared abilities and limits Rundesk must retain and honor before calling capability negotiation complete. |
| Concurrent surfaces | One agent may have more than one adapter connection, but whether one conversation may span surfaces is undefined. | Decide before adding any conversation-linking feature. |
| Real-platform recovery evidence | Offline lifecycle tests cannot prove service reconnection or display behavior. | Choose the maintained real-platform acceptance protocol and release gate. |

## Validation

| Requirement area | Current evidence checked | Result | Last checked |
|---|---|---|---|
| Adapter contract | [adapters.md](../adapters.md), `src/rundesk/channels/adapters.py`, `tests/test_channels_command.py` | Current mechanics inspected; acceptance not executed in this PRD pass. | 2026-08-08 |
| Gateway hosting and recovery | `src/rundesk/channels/hosting.py`, `src/rundesk/gateways/host.py`, `tests/test_channels_hosting.py` | Offline suite passed on current Python and macOS Python 3.9, including transient disconnect state, native reconnect, and stuck-adapter replacement; real-platform recovery remains unvalidated. | 2026-08-21 |
| Channel management | [commands.md](../api/commands.md#channels), `src/rundesk/commands/channels.py`, `tests/test_channels_command.py` | Current mechanics inspected; acceptance not executed in this PRD pass. | 2026-08-08 |
