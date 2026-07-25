# Research: Provider CLI events and Discord interaction

**Last updated:** 2026-07-25
**Question it answers:** Can Discord carry native Codex and Claude Code activity, approvals and questions without rundesk owning their agent loops?

## What they do

The short answer is **yes, through each provider's structured interface**. Discord can be the remote user
interface while Codex or Claude Code remains responsible for the conversation, tools, skills and model
work. A subprocess that only copies terminal text is not enough: interactive requests need a structured
event from the provider and a supported route for sending the user's answer back.

| Need | Codex | Claude Code | Discord |
|---|---|---|---|
| Stream agent activity | `codex exec --json` emits JSONL lifecycle, message, command, file-change, MCP, web-search and plan events. App Server additionally streams incremental message and command-output events.[1][2] | Headless mode emits newline-delimited JSON, and its partial-message option emits generated text as it arrives. Tool-use and subagent events are part of the stream.[4] | Apps can create and edit messages. Normal message content is limited to 2,000 characters, so long output must be edited, split or attached.[9] |
| Continue a conversation | App Server has persisted threads, normal new turns, active-turn steering and thread resume. `codex exec` can resume a completed session in a later invocation.[1][2] | Headless sessions return a session ID and can later be resumed. Streaming input is also available for a process kept open.[4][5] | A Discord channel or thread ID can be the user's stable address; the application supplies the mapping to the provider session. |
| Approve tools | App Server sends client requests for command, file-change and permission approvals, and continues after the client returns a decision.[1] | The Agent SDK pauses in `canUseTool`; direct headless CLI integrations can answer native permission dialogs through `PermissionRequest` hooks.[5][6] | Buttons can represent allow, deny and cancel choices, and component interactions return their application-defined ID.[7] |
| Answer clarifying questions | App Server can send the experimental `item/tool/requestUserInput` request with short structured questions and free-form options.[1] | `AskUserQuestion` reaches `canUseTool`. A direct CLI `PreToolUse` hook can defer the tool, let the process exit, and resume the same session after an external UI supplies answers.[5][6] | Selects handle single or multiple choices; modal text inputs handle a typed answer.[7] |

**Codex.** `codex exec --json` is the simpler automation surface. It produces a machine-readable event
stream and supports a later `exec resume`, but its permissions are chosen before the run and its current
headless request handlers reject approval and user-input requests rather than exposing a client response
channel.[2][3] It is therefore suitable for autonomous jobs, not for a Discord user approving a pending
action.

Codex App Server is the external-client surface used for rich integrations. Its default transport is
bidirectional newline-delimited JSON over standard input and output. A client initializes once, starts or
resumes a thread, starts a turn, reads streamed notifications, and answers server-initiated approval or
question requests by their request ID.[1] App Server and some request types are still marked experimental,
and the CLI can generate a protocol schema that matches the installed Codex version.[1]

**Claude Code.** Headless `claude -p` can stream JSON events, partial text and final session metadata.[4]
For a live integration, the SDK's `canUseTool` callback pauses on both permission requests and
`AskUserQuestion` until the host answers.[5] The direct-CLI alternative is documented too: a `PreToolUse`
hook returns `defer`, Claude exits with the pending tool call and session ID preserved, the host asks in
its own UI, and `claude -p --resume <session-id>` re-enters the same hook so the answer can be supplied.[6]
Deferred tool use currently requires one tool call rather than a parallel batch, so that path needs a
tested fallback.[6]

**Discord.** Buttons, selects and modal text inputs provide the controls needed for approvals,
multiple-choice questions and free-form answers.[7] Every interaction must receive an initial
acknowledgement within three seconds; its token remains usable for follow-up responses for 15 minutes.[8]
That makes the safe pattern: acknowledge immediately, run the provider asynchronously, and create or edit
ordinary bot messages as events arrive.

## What we can borrow

- Keep the provider's loop intact. Translate Discord input into provider turns and provider events into
  Discord presentation; do not reconstruct prompts, context, tool execution or skills in rundesk.
- Use Codex App Server over local stdio for a Discord-connected Codex agent. Reserve `codex exec --json`
  for work whose permission policy is settled before it begins.
- Use Claude's headless JSON stream with native hooks. Use `PermissionRequest` for actual permission
  dialogs and `PreToolUse` defer/resume for `AskUserQuestion` and plan approval.
- Store only the routing state rundesk owns: Discord channel/thread, provider session/thread, active turn,
  pending request, authorized user and expiry.
- Coalesce text deltas into periodic message edits. Render tool activity separately and summarize or
  attach output that will not fit safely in a Discord message.
- Treat approval responses as single-use capabilities: bind each to the intended user, provider request,
  conversation and expiry, then default to denial when any part does not match.

## What to avoid

- Do not bridge the interactive terminal UI through a pseudo-terminal unless every structured option has
  failed. Terminal rendering and keystroke menus are presentation, not a stable integration protocol.
- Do not build the channel directly on the current `Program.on_line` seam. It supplies synchronous,
  untyped strings; provider stdin is closed and stderr is merged into stdout, so it cannot carry a
  bidirectional JSON protocol safely.
- Do not describe `codex exec --json` as interactive. It can show a completed question as an ordinary
  message and resume later, but it cannot answer a native approval or `request_user_input` in that run.
- Do not use bypass-permission modes merely to make headless execution finish. A Discord bridge exists so
  the owner can retain the providers' permission decisions, not erase them.
- Do not publish raw tool arguments and results by default. They can contain file contents, credentials,
  private paths or output far larger than Discord should receive.
- Do not let a Discord send failure kill the provider turn. Network delivery needs an asynchronous queue,
  bounded retries and a durable final result separate from the provider process reader.

## Verdict for us

Use **provider-native structured adapters**, not a rundesk conversational loop:

- Discord-connected Codex runs through App Server's local stdio protocol.
- Autonomous Codex jobs may use `codex exec --json`.
- Discord-connected Claude runs headlessly with streamed JSON, `PermissionRequest` hooks for native
  approvals, and `PreToolUse` defer/resume for questions and plan approval.
- Discord renders text as coalesced message edits, tools as status/result messages, choices as selects or
  buttons, and free-form answers through a modal or an explicitly correlated reply.

This feeds `platform-process` where a provider protocol needs bidirectional, separately typed streams. It
also feeds the future provider and channel contracts, whose component names and guarantees remain an owner
decision. The current generic process runner should remain useful for ordinary programs; the structured
provider protocol should be a separate concern rather than weakening that boundary.

## Open questions

- Which provider requests must survive a gateway restart, and what can each provider actually resume after
  its protocol process dies while waiting for approval?
- Are Codex App Server's experimental surface and structured question request acceptable if rundesk pins
  supported CLI versions and validates their generated schemas?
- Should a Claude question wait in a live process or always use defer/resume so a slow Discord answer does
  not hold resources?
- Which tool fields may appear in Discord, which require redaction, and which remain available only in the
  local transcript?
- Who may answer in a shared Discord channel: the agent owner only, an allowlist, or anyone with a role?

## Sources

1. OpenAI, Codex App Server — https://developers.openai.com/codex/app-server/
2. OpenAI, Codex non-interactive mode — https://developers.openai.com/codex/noninteractive/
3. OpenAI Codex source, non-interactive request handling — https://github.com/openai/codex/blob/main/codex-rs/exec/src/lib.rs#L1584-L1717
4. Anthropic, Run Claude Code programmatically — https://code.claude.com/docs/en/headless
5. Anthropic, Handle approvals and user input — https://code.claude.com/docs/en/agent-sdk/user-input
6. Anthropic, Hooks reference — https://code.claude.com/docs/en/hooks
7. Discord, Component reference — https://docs.discord.com/developers/components/reference
8. Discord, Receiving and responding to interactions — https://docs.discord.com/developers/interactions/receiving-and-responding
9. Discord, Message resource — https://docs.discord.com/developers/resources/message
