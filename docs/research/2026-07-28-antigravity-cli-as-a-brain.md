# Research: The Antigravity CLI as an agent's brain

> **Carried across on 2026-08-04, intact, from the previous build's research directory** — a
> gitignored, reference-only tree that is expected to be deleted. Nothing here has been rewritten:
> the wording, the dates, the labels and the measurements are that build's. Two session identifiers
> captured from real accounts were shortened and nothing else was changed. Its internal citations
> name files in trees that are going away, so treat a `(internal)` source as provenance rather than
> as something you can open.
>
> **What is still true.** Everything about `agy 1.1.8` on Darwin 25.5.0, including the soft-denial
> defect where a refused write exits zero reporting success. **What is not.** Its verdict ships a
> provider under the previous build's directory layout and PRD; the behaviour it describes is the
> part to keep.


**Last updated:** 2026-07-28  
**Question it answers:** What does the official Antigravity CLI actually do when driven headlessly, and which behavior must a Rundesk provider adapter absorb?

## What they do

Everything marked **Measured** here was probed against Google's signed `agy 1.1.8` arm64
binary on Darwin 25.5.0 using a personal Google account.[11] The prompts were ordinary,
read-only project questions except for one explicit edit in a disposable fixture. No
credential, keyring record, private API, or browser session was inspected.[11] Everything marked
**Documented** comes from Google's current CLI documentation or changelog.

| Need | Antigravity CLI behavior |
|---|---|
| Run one unattended turn | **Measured:** piping a prompt to `agy --output-format stream-json` selects print mode and emits NDJSON. `-p` instead consumes the next word as its prompt.[11] |
| Authenticate | **Documented:** `agy` uses the native OS keyring and opens browser OAuth when no session exists. No token environment variable, service-account mode, or supported config-home override is documented.[1][2] |
| Identify and resume a conversation | **Measured:** `init.conversation_id` and `result.conversation_id` carry the same UUID. `--conversation <uuid>` recalled an unguessable natural project nickname across separate processes and emitted only the new turn.[3][11] |
| Identify the answering model | **Measured:** when `--model gemini-3.6-flash-low` was requested, `init.model` reported that exact resolved slug. The live model inventory is account-dependent.[4][11] |
| Report per-turn usage | **Measured:** fresh turns repeat the same totals in `result.usage`; resumed turns make `result.usage` cumulative across the conversation. Each new invocation's `step_update.usage` blocks are deltas and sum to that turn alone. `cache_read_tokens` stays separate from fresh input.[5][11] |
| Report tools | **Measured:** a tool has an `ACTIVE` and terminal `DONE` or `ERROR` step sharing `step_index`; `tool_info.name`, parameters, output, or error are attached. `list_dir`, `view_file`, `grep_search`, `run_command`, `replace_file_content`, and `write_to_file` were observed.[5][11] |
| Select the working project | **Measured:** cwd alone is insufficient for an unseen directory: `init.cwd` named the requested directory while tools stood in Antigravity's persistent scratch project. `--new-project` bound a fresh conversation to the working tree; exact resume restored it.[3][11] |
| Contain a turn | **Documented and measured:** `--sandbox` is OS containment. `--mode plan` is a read-only workflow, not a boundary. In headless mode, an unapproved write was soft-denied and no file appeared; `accept-edits` plus `--dangerously-skip-permissions` completed the requested edit inside the sandbox.[6][7][8][11] |
| Present a workspace skill | **Documented and measured:** the current open-standard location is `.agents/skills/<name>/SKILL.md`; a folder symlink was indexed and Antigravity attempted to read its target. Skills are indexed at conversation start.[9][11] |
| Steer a running turn | **Not supported:** no documented headless input channel accepts words after the piped prompt. |

### The stream

The committed `tests/samples/antigravity-stream.jsonl` is a sanitized subset of a real
1.1.8 capture. Private paths, account details, conversation IDs, and tool output were
replaced; event structure and numeric relationships were retained.[11]

The observed step vocabulary also included `user_input`, `unknown`, `checkpoint`,
`system_message`, and `error_message`. They are framing or state and produce no Rundesk
record.[11]

### Permission-denial defect

**Measured:** a headless `plan` turn asked to write emitted a `write_to_file` tool error,
printed a useful denial to stderr, left the filesystem unchanged, then exited zero with:

```json
{"status":"SUCCESS","response":""}
```

That matches upstream issue #702's report that soft-denied work can look successful.[10][11]

### Missing-resume behavior

**Measured:** an unknown `--conversation` id does not fail. Version 1.1.8 silently starts a
new UUID and may stand it in the scratch project.[11]

## What we can borrow

- The CLI's NDJSON stream already separates initialization, tool lifecycle, text deltas,
  usage, and terminal outcome.
- Exact conversation IDs carry context across short-lived provider processes.
- Workspace-standard skills let a provider discover only the skills standing in that
  agent's home.

## What to avoid

- Do not put a prompt after `-p`; it becomes process-list-visible argv, while piping is
  already supported.
- Do not use cumulative `result.usage` for resumed turns.
- Do not infer the tool workspace from `init.cwd` when no project was selected.
- Do not call a headless soft-denial successful merely because version 1.1.8 exits zero.
- Do not inspect, copy, or redirect native-keyring authentication.

## Verdict for us

Ship `src/providers/antigravity` under the existing provider-adapter PRD. It invokes only
the installed official binary, preserves the owner's machine login without inspecting it,
and disables managed-turn auto-updates. Fresh sessions use `--new-project`; resume uses the
exact stream-reported id and retries fresh when Antigravity silently replaces it.

Map streamed reply deltas once, pair tool steps by `step_index`, and sum only step-level
usage. Correct the mechanically provable false-success case: a tool errored and the terminal
result contains no response or streamed text. A tool error followed by a real answer remains
a successful turn.

Use `plan` plus sandbox and unapproved permissions for read posture. Use `accept-edits`,
sandbox, and automatic approval for work posture. Present granted skills through individual
symlinks under `.agents/skills`; never link the whole granted directory.

The provider remains independent of channel transport. Discord receives only Rundesk's
normalized records and never sees Google credentials.

## Open questions

- Default-model `init` events may omit `model`; report one only when the stream names it.
- The CLI docs disagree on one older global skills path; use the measured workspace path.
- No supported unattended/service authentication mode or isolated configuration-home
  override was found.
- Signals, print timeouts, malformed JSON schema failures, and every possible tool name
  remain unprobed; synthesize failed `done` for every truncated stream.

## Sources

1. [Google Antigravity CLI installation and authentication](https://antigravity.google/docs/cli/install)
2. [Official Antigravity CLI README — authentication](https://github.com/google-antigravity/antigravity-cli#authentication)
3. [Google Antigravity CLI conversations](https://antigravity.google/docs/cli/conversations)
4. [Google Antigravity models (CLI view)](https://antigravity.google/docs/models?app=cli)
5. [Antigravity CLI changelog, including stream-json in 1.1.8](https://github.com/google-antigravity/antigravity-cli/blob/main/CHANGELOG.md)
6. [Google Antigravity CLI permissions](https://antigravity.google/docs/cli/permissions)
7. [Google Antigravity CLI execution modes](https://antigravity.google/docs/cli/modes)
8. [Google Antigravity CLI sandbox](https://antigravity.google/docs/cli/sandbox)
9. [Google Antigravity Agent Skills](https://antigravity.google/docs/skills)
10. [Upstream issue #702 — JSON and soft-denial behavior](https://github.com/google-antigravity/antigravity-cli/issues/702)
11. Live 1.1.8 probes and sanitized `tests/samples/antigravity-stream.jsonl` capture (internal)
