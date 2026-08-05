# Research: Provider CLI events and Discord interaction

> **Carried across on 2026-08-04, intact, from the previous build's research directory** — a
> gitignored, reference-only tree that is expected to be deleted. Nothing here has been rewritten:
> the wording, the dates, the labels and the measurements are that build's. Two session identifiers
> captured from real accounts were shortened and nothing else was changed. Its internal citations
> name files in trees that are going away, so treat a `(internal)` source as provenance rather than
> as something you can open.
>
> **What is still true.** The three platform limits it records — a 2,000-character message body, a
> three-second acknowledgement for an interaction and a fifteen-minute follow-up token — and its
> central verdict, that a surface renders what a provider's own loop produced rather than
> reimplementing that loop. **What is not.** Almost every capability claim in it was read off vendor
> documentation and never exercised; the probe note of the following day
> ([`2026-07-26-questions-approvals-and-recovery.md`](2026-07-26-questions-approvals-and-recovery.md))
> re-ran them and refuted several. Read that one first and this one for the platform facts.


**Last updated:** 2026-07-25
**Question it answers:** Can Discord carry native Codex and Claude Code activity, approvals and questions without rundesk owning their agent loops?

## What they do

| Need | Codex | Claude Code | Discord |
|---|---|---|---|
| Stream agent activity | `codex exec --json` emits JSONL lifecycle, message, command, file-change, MCP, web-search and plan events. App Server additionally streams incremental message and command-output events.[1][2] | Headless mode emits newline-delimited JSON, and its partial-message option emits generated text as it arrives. Tool-use and subagent events are part of the stream.[4] | Apps can create and edit messages. Normal message content is limited to 2,000 characters, so long output must be edited, split or attached.[9] |
| Continue a conversation | App Server has persisted threads, normal new turns, active-turn steering and thread resume. `codex exec` can resume a completed session in a later invocation.[1][2] | Headless sessions return a session ID and can later be resumed. Direct CLI print mode also accepts queued messages with `--input-format stream-json`.[4][10] | Messages and component interactions identify the Discord channel where the exchange occurred.[8][9] |
| Approve tools | App Server sends client requests for command, file-change and permission approvals, and continues after the client returns a decision.[1] | The Agent SDK pauses in `canUseTool`. Direct headless CLI can send native permission prompts to a named MCP tool, or a `PreToolUse` hook can defer a matched tool call for an external answer. Neither path overrides an MCP tool marked `requiresUserInteraction`.[5][6][10] | Buttons can represent allow, deny and cancel choices, and component interactions return their application-defined ID.[7] |
| Answer clarifying questions | App Server can send the experimental `item/tool/requestUserInput` request with short structured questions and free-form options.[1][12] | `AskUserQuestion` reaches `canUseTool`. A direct CLI `PreToolUse` hook can defer the tool, let the process exit, and resume the same session after an external UI supplies answers.[5][6] | Selects handle single or multiple choices; modal text inputs handle a typed answer.[7] |

**Codex.** `codex exec --json` is the simpler automation surface. It produces a machine-readable event
stream and supports a later `exec resume`, but its permissions are chosen before the run and its current
headless request handlers reject approval and user-input requests rather than exposing a client response
channel.[2][3] It is therefore suitable for autonomous jobs, not for a Discord user approving a pending
action.

Codex App Server is the external-client surface used for rich integrations. Its default transport is
bidirectional newline-delimited JSON over standard input and output. A client initializes once, starts or
resumes a thread, starts a turn, reads streamed notifications, and answers server-initiated approval or
question requests by their request ID.[1] The CLI still labels the `app-server` command
experimental, while the protocol defines a stable local stdio surface for clients that do not opt into
`experimentalApi`. Selected methods, fields, `item/tool/requestUserInput` and WebSocket transport remain
experimental. The CLI can generate a protocol schema that matches the installed Codex version.[1][12][13]

**Claude Code.** Headless `claude -p` can stream JSON events, partial text and final session metadata.[4]
For a live integration, the SDK's `canUseTool` callback pauses on both permission requests and
`AskUserQuestion` until the host answers.[5] Direct CLI offers two different routes: the
`--permission-prompt-tool` flag sends native permission prompts to a named MCP tool, while a `PreToolUse`
hook can return `defer` for a matched approval or question.[6][10] Claude then exits with the pending tool
call and session ID preserved; `claude -p --resume <session-id>` re-enters the hook so an external answer
can be supplied.[6] `PermissionRequest` hooks do not fire in `-p` mode, and deferred tool use currently
requires one tool call rather than a parallel batch.[6][11] The permission-prompt tool cannot approve an
MCP tool marked `requiresUserInteraction`; Claude converts that attempted approval to a denial.[10]

**Discord.** Buttons, selects and modal text inputs provide the controls needed for approvals,
multiple-choice questions and free-form answers.[7] Every interaction must receive an initial
acknowledgement within three seconds; its token remains usable for follow-up responses for 15 minutes.[8]

## What we can borrow

- The answer is **yes**: Discord can be the remote user interface while the provider remains responsible
  for the conversation, tools, skills and model work. Rundesk needs a structured, bidirectional adapter,
  not a new agent loop or a subprocess that only copies terminal text.
- Keep the provider's loop intact. Translate Discord input into provider turns and provider events into
  Discord presentation; do not reconstruct prompts, context, tool execution or skills in rundesk.
- Map each Discord channel or thread to its provider session. Acknowledge Discord interactions
  immediately, then continue provider work asynchronously and create or edit ordinary bot messages as
  events arrive.
- Use Codex App Server over local stdio for a Discord-connected Codex agent. Reserve `codex exec --json`
  for work whose permission policy is settled before it begins.
- Use Claude's headless JSON stream. Route native permission prompts through
  `--permission-prompt-tool` when rundesk can host the small MCP broker; otherwise use selected
  `PreToolUse` defer/resume hooks. Use defer/resume for `AskUserQuestion` and plan approval, and treat MCP
  tools marked `requiresUserInteraction` as unsupported until rundesk adopts a documented interactive
  provider surface for them.
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
- Discord-connected Claude runs headlessly with streamed JSON, a permission-prompt MCP tool or selected
  `PreToolUse` hooks for approvals, and `PreToolUse` defer/resume for questions and plan approval.
- Claude MCP tools marked `requiresUserInteraction` are outside that direct-CLI approval path; preserving
  them would require the Agent SDK or another documented interactive provider surface.
- Discord renders text as coalesced message edits, tools as status/result messages, choices as selects or
  buttons, and free-form answers through a modal or an explicitly correlated reply.

This feeds `platform-process` where a provider protocol needs bidirectional, separately typed streams. It
also feeds the future provider and channel contracts, whose component names and guarantees remain an owner
decision. The current generic process runner should remain useful for ordinary programs; the structured
provider protocol should be a separate concern rather than weakening that boundary.

## Open questions

- Which provider requests must survive a gateway restart, and what can each provider actually resume after
  its protocol process dies while waiting for approval?
- Which optional Codex App Server features require the experimental API, and can the first adapter stay on
  the stable stdio surface while rundesk pins supported CLI versions and validates generated schemas?
- Should a Claude question wait in a live process or always use defer/resume so a slow Discord answer does
  not hold resources?
- Is the Python Agent SDK acceptable if a required Claude MCP tool uses `requiresUserInteraction`, despite
  the project's current Python 3.9 and standard-library-only constraints?
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
10. Anthropic, Claude Code CLI reference — https://code.claude.com/docs/en/cli-usage
11. Anthropic, Automate actions with hooks — https://code.claude.com/docs/en/hooks-guide
12. OpenAI Codex source, app-server request definitions — https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/common.rs#L1512-L1516
13. OpenAI Codex source, CLI command declaration — https://github.com/openai/codex/blob/main/codex-rs/cli/src/main.rs#L146-L147
