# Research: what a gateway tells its agent, before anybody else does

> **Carried across on 2026-08-04, intact, from the previous build's research directory** — a
> gitignored, reference-only tree that is expected to be deleted. Nothing here has been rewritten:
> the wording, the dates, the labels and the measurements are that build's. Two session identifiers
> captured from real accounts were shortened and nothing else was changed. Its internal citations
> name files in trees that are going away, so treat a `(internal)` source as provenance rather than
> as something you can open.
>
> **What is still true.** Everything it reports about the two comparable products, read at pinned
> checkouts and cited line by line — the cache-boundary marker, the trust-wrapper vocabularies, the
> anti-fabrication rule, and the self-poisoning review loop. **What is not.** The section headed
> *What rundesk shipped at the compared baseline*, and the verdict after it, describe the previous
> build's `agent.py`, `channel.py` and `instructions.py` at a commit that no longer exists. The layer
> shape those refer to is distilled in [`instruction-layers.md`](instruction-layers.md).


**Last updated:** 2026-07-29
**Question it answers:** What internal prompt text do comparable self-hosted agent gateways ship to their
agents, how is it layered against what an owner writes, and what does that say about the shape and contents
of rundesk's own standing words?

## What they do

Two products in the same shape as rundesk — a self-hosted gateway running a personal agent, reached from
chat apps — both ship a substantial internal prompt of their own, distinct from anything their owner
writes. Both were read at a pinned checkout rather than from documentation [1][2].

### OpenClaw

The whole base prompt is one 1458-line TypeScript function, `buildAgentSystemPrompt()` in
`src/agents/system-prompt.ts:693`, emitting every section as string-array literals. There are no markdown
prompt templates; the only shipped `.md` template, `src/agents/templates/HEARTBEAT.md`, is deliberately
empty [1]. Roughly 25 `buildXSection()` helpers each return `string[]` and self-gate, and composition is
array spread plus `.filter(Boolean).join("\n")` [1].

It opens `You are a personal assistant running inside OpenClaw.` and goes straight into a tool catalog [1].
The register throughout is telegraphic and near-free of function words — `## Execution Bias` reads
`Actionable request: act now.` / `Final claim needs evidence or named blocker.` [1].

The prompt is physically split by a literal marker,
`SYSTEM_PROMPT_CACHE_BOUNDARY = "\n<!-- OPENCLAW_CACHE_BOUNDARY -->\n"`, in
`packages/ai/src/utils/system-prompt-cache-boundary.ts`. Everything above it is memoized in a 64-entry LRU
keyed by a SHA-256 of ~35 inputs (`system-prompt.ts:1037-1079`) and sent to Anthropic with
`cache_control: ephemeral` (`packages/ai/src/providers/anthropic.ts:1591-1620`); providers without
breakpoint support strip the marker [1]. Section placement follows from this: date and time, channel
context, messaging rules, runtime state and reactions all sit below the line, and a comment at
`system-prompt.ts:1421-1424` records that a cron run's volatile session key is deliberately not rendered
because it would defeat literal-prefix caching [1].

Safety is six lines (`system-prompt.ts:990-998`), framed against agentic drift rather than content:

> No independent goals, self-preservation, replication, resource acquisition, power-seeking, or plans beyond user request.
> Safety/oversight > completion. Conflict: pause/ask. Obey stop/pause/audit; never bypass safeguards.
> Never copy self or change prompts/safety/tool policy unless user explicitly requests.

There is no refusal policy, harmful-content taxonomy or jailbreak language anywhere in the shipped
prompt [1].

`## Interaction Style` has `fallback: []` (`system-prompt.ts:1146`) — the default agent ships **no
personality section at all**. Tone comes from the owner's `SOUL.md`, ranked explicitly in the prompt:
`SOUL.md: persona/tone. Follow it unless higher-priority instructions override.` (`:244`) [1].

Trust is stratified at the token level, with four distinct wrapper vocabularies: trusted metadata
(`### Inbound Context (trusted metadata)`, `src/auto-reply/reply/inbound-meta.ts:606`), untrusted channel
text (`<untrusted-text>`), internal runtime (`<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>`), and external content
wrapped in `<<<EXTERNAL_UNTRUSTED_CONTENT id="{hex8}">>>` with a spelled-out injection warning
(`src/security/external-content.ts:76-87`). Spoofed markers are rewritten to `[[MARKER_SANITIZED]]`,
`sanitize-for-prompt.ts` strips Unicode Cc/Cf/U+2028/U+2029 from every interpolated runtime string against
a stated threat model of attacker-controlled directory names, and `wrapPromptDataBlock` HTML-escapes `<`
and `>` so content cannot close its own tag [1].

Channel rules live in the per-surface tier, not the core: group-chat behavior including the exact
`NO_REPLY` silence contract is assembled in `src/auto-reply/reply/groups.ts:143-179`, and Discord's
`wrap bare URLs like <https://example.com> to suppress embeds` is one line at `groups.ts:154` [1].

Ordinary owner configuration adds through workspace context files (AGENTS.md, SOUL.md, MEMORY.md,
rendered under `# Project Context`) and per-channel `systemPrompt` config rather than replacing the base.
Extensions are a separate trust tier: `before_agent_start` prompt-build hooks may return `systemPrompt`
and replace the whole built prompt (`attempt-prompt-assembly.ts:123-151`, `prepare.ts:1163-1192`,
`agent-session-prompting.ts:216-243`), while provider plugins may replace three individual sections
(`system-prompt-contribution.ts:7-10`) [1]. Nothing carries a version string; the only prompt-identity
mechanism is the stable-prefix hash [1]. Estimated at ~1.8–2.3k tokens for a full render before workspace
files and the skills index; the renderer could not be executed at this checkout, so the figure is an
estimate [1].

On `sk-ant-oat…` subscription credentials the transport prepends
`You are Claude Code, Anthropic's official CLI for Claude.` plus a billing header, sets
`user-agent: claude-cli/2.1.75`, and renames tools via `toClaudeCodeName`, under a source comment reading
`// Stealth mode: Mimic Claude Code's tool naming exactly` (`anthropic.ts:128,157,1567-1589`) [1].

### Hermes Agent

The text lives as parenthesized Python string constants in `agent/prompt_builder.py` (2090 lines);
`agent/system_prompt.py:147` `build_system_prompt_parts()` assembles three tiers — stable, context,
volatile — joined with `\n\n` at `:543`. There is no `prompts/` directory and no template file for the base
prompt; markdown is used only for the 180 shipped `SKILL.md` files, a separate on-demand layer [2].

Identity is `DEFAULT_AGENT_IDENTITY` (`prompt_builder.py:139`), also seeded verbatim as the default
`SOUL.md` (`hermes_cli/default_soul.py:3`) — so the owner's replaceable persona file starts as a copy of
the built-in one [2].

`TASK_COMPLETION_GUIDANCE` (`:339`) is an anti-fabrication rule, and the code comment above it names the
runs that caused it — an Opus task that produced an 85-byte file, and a DeepSeek run on the same task that
"pushed through PEP-668 wall, then returned fabricated listings" [2]:

> …the deliverable is a working artifact backed by real tool output — not a description of one…
> NEVER substitute plausible-looking fabricated output (made-up data, invented file contents, synthesised
> API responses) for results you couldn't actually produce. Reporting a blocker honestly is always better
> than inventing a result.

`MEMORY_GUIDANCE` (`:160`) rules on the grammar of a saved memory, not only its content [2]:

> Write memories as declarative facts, not instructions to yourself. 'User prefers concise responses' ✓ —
> 'Always respond concisely' ✗… Imperative phrasing gets re-read as a directive in later sessions and can
> cause repeated work or override the user's current request. Procedures and workflows belong in skills,
> not memory.
> …If a fact will be stale in a week, it does not belong in memory.

A skills index is mandatory in the prompt (`:1739`, `## Skills (mandatory)` plus `<available_skills>`),
instructing the model to load any partially relevant skill before replying [2]. Skill descriptions are
silently truncated at 60 characters (`agent/skill_utils.py:782,796`), and the prompt states that
constraint in three separate places — the `skill_manage` tool description, `_AUTHORING_STANDARDS`, and the
curator prompt [2].

The learning loop is not an in-conversation nudge. Every 10 user turns (`agent_init.py:1591`) or 10 tool
iterations without a `skill_manage` call (`agent_init.py:1691`), a completed turn forks a second `AIAgent`
(`turn_finalizer.py:651`) inheriting the parent's cached system prompt byte-for-byte and its conversation,
then sends one review prompt as a user turn. The fork is `_persist_disabled`, `max_iterations=16`, and
shares `session_id` purely for prefix-cache warmth, with a comment citing "~26% end-to-end cost reduction
on Sonnet 4.5" (`background_review.py:690-800`) [2]. `_SKILL_REVIEW_PROMPT` (`:181`) pushes for output:

> Be ACTIVE — most sessions produce at least one skill update, even if small. A pass that does nothing is a
> missed learning opportunity, not a neutral outcome.
> …Frustration signals like 'stop doing X', 'this is too verbose', 'just give me the answer'… are
> FIRST-CLASS skill signals.
> Do NOT capture… Negative claims about tools or features ('browser tools do not work', 'X tool is
> broken')… These harden into refusals the agent cites against itself for months after the actual problem
> was fixed.

A separate 7-day curator pass (`curator.py:417`) exists to undo the loop's over-production, opening
"A collection of hundreds of narrow skills where each one captures one session's specific bug is a FAILURE
of the library — not a feature" and setting a floor of 10 archives per pass [2].

That loop shipped a self-poisoning defect: the fork originally shared the parent's session and wrote its
harness turn into the real transcript, after which the agent re-read "Review the conversation above and
update the skill library…" as a standing instruction and became the curator instead of answering the user.
The fix is the `_persist_disabled` hard stop plus a defensive filter matching the first ~50 characters of
its own two prompts to scrub old rows on read (`hermes_state.py:319-324`) [2].

Steering needed a trust marker for the inverse reason: `prompt_builder.py:632` records that a plain
"User guidance:" line appended to a tool result "gets refused as suspected prompt injection (observed in
the wild)", so genuine mid-turn owner input is delivered inside a bounded
`[OUT-OF-BAND USER MESSAGE — …]` marker that `STEER_CHANNEL_NOTE` (`:646`) tells the model to trust — and
to trust *only* in that exact form [2]. Tool results from `web_search`, `web_extract`, `browser_*` and
`mcp_*` are wrapped in `<untrusted_tool_result source="...">`, with `_neutralize_delimiters` rewriting any
embedded copy of the token so a poisoned page cannot close the boundary early
(`tool_dispatch_helpers.py:600-608`) [2].

The prompt varies by model, aggressively: Claude and Anthropic models receive none of the enforcement
blocks; `("gpt","codex","gemini","gemma","grok","glm","qwen","deepseek")` receive
`TOOL_USE_ENFORCEMENT_GUIDANCE`; Gemini and Gemma additionally receive Google-specific guidance; GPT,
Codex and Grok receive a 2.7 KB execution-discipline block; and for GPT-5 and Codex the whole thing is sent
under role `developer` rather than `system` (`prompt_builder.py:664`,
`transports/chat_completions.py:353,531`). Alibaba gets a hardcoded model-identity patch for an upstream
API bug (`system_prompt.py:331`) [2].

Only the identity slot is owner-replaceable — `~/.hermes/SOUL.md` swaps out `DEFAULT_AGENT_IDENTITY`, and
everything after it is appended, reachable from config only through boolean switches and a per-platform
`platform_hints: {replace|append}` override [2]. Nothing is versioned; there is no `PROMPT_VERSION`
constant, and `prompt_builder.py` alone carries 142 commits — but `tests/agent/test_prompt_builder.py` is
1727 lines [2]. Prompt budget is a first-class concern: `hermes prompt-size` builds a real offline agent
and prints a byte breakdown by tier (`hermes_cli/prompt_size.py`) [2]. Measured constants include
`KANBAN_GUIDANCE` at 5.5 KB and computer-use guidance at ~4.5 KB; a typical CLI session assembles roughly
10–13 KB of fixed guidance before the skills index, which then usually dominates [2].

`build_nous_subscription_prompt` (`prompt_builder.py:1778`) injects a capability block that tells the agent
to suggest a paid Nous subscription when an unavailable capability would be unlocked by one [2].

### What both do, and what neither does

Both ship an internal prompt that ordinary owner configuration adds to rather than replaces, although
OpenClaw gives trusted extension hooks a whole-prompt replacement path [1]. Both keep every fragment in
code rather than in template files; both let prompt-cache economics decide the physical ordering of
sections; and neither ships a content-safety or refusal policy of any kind — all safety text in both is
operational, and content policy is left to the model [1][2]. Neither versions its prompt text [1][2].
Hermes credits ported prompt material from Cline, OpenCode, OpenAI's prompting guide and OpenClaw in source
comments [2].

### What rundesk shipped at the compared baseline

At baseline `4cb891e`, `STANDING` in `src/rundesk/agent.py:620` was one constant, ~200 tokens, filled only with `{name}`, and its
comment states the prefix-caching reason for keeping it invariant. `agents.told()` (`:653`) layers it:
rundesk's words first, then nearest-wins among the schedule or turn, the surface, the agent, and finally
`channel.by_default()` (`channel.py:444`). It reaches an adapter as one `RUNDESK_PREFACE` environment
variable, which each shipped adapter maps to that brain's native slot — `--append-system-prompt`,
`--rules`, `developerInstructions`, or a prepend. `channel.preface()` bounds owner text at
`INSTRUCTIONS_MOST` and `_fill()` substitutes by hand rather than through `str.format` so a brace in
arriving text cannot raise mid-turn. `turn.py:264-269` writes the preface into the conversation authored by
`rundesk`. There is no skills index: a grant is a symlink and the brain discovers the directory
(`skill.py`) [3].

## What we can borrow

- A named cache boundary as a first-class concept, so which tier a fragment belongs to is a decision the
  code records rather than one each new fragment re-litigates.
- An explicit wrapper vocabulary for arriving text, marking what is data and what is an instruction — and,
  from Hermes's inverse failure, a trusted marker for genuine mid-turn owner steering.
- The anti-fabrication rule, which is the one piece of either shipped prompt that is about the honesty of a
  reported outcome rather than about a mechanism.
- Emitting an environment fact only when the environment is non-default, rather than asserting it always.
- Keeping tone and persona out of the shipped core and ranking the owner's file explicitly, as OpenClaw
  does with `SOUL.md`.
- A command that prints the assembled prompt with a byte breakdown by tier, the way `hermes prompt-size`
  does, so prompt budget is inspectable rather than estimated.

## What to avoid

- A skills index in the prompt. Hermes's 60-character silent truncation is its most-repeated authoring
  rule, and its curator pass exists to clean up what the index encourages.
- A background review fork that shares the live transcript. Hermes's agent read its own curator prompt back
  as a standing instruction and stopped answering its user; the same shape is reachable here, because our
  preface is deliberately written into the conversation as something rundesk said.
- Channel-shaped rules in the invariant core. Both products place formatting and silence rules per surface;
  ours currently states a mobile-reply rule in `STANDING`, which is also told to a terminal turn and to a
  scheduled run reporting into a log.
- Environment facts asserted absolutely in the core, such as our claim that the workspace has no git
  repository.
- Vendor impersonation on subscription credentials, as OpenClaw's transport does.
- A commercial upsell inside the agent's own standing words, as Hermes's subscription block is.
- Content-safety or refusal text. Neither ships any, and adding it would put us alone in spending an
  invariant prefix on what the model already does.

## Verdict for us

The resulting architecture keeps `RUNDESK_PREFACE` as the one delivery seam and makes its ownership
visible: `instructions.py` holds Rundesk's invariant core and three trigger blocks, while channel and
provider adapters retain platform-specific wording and transport wrappers. Standard variables name
communication concepts rather than Discord concepts, adapter overrides can replace only a trigger, and
owner, agent, schedule and per-turn instructions append without replacing an earlier layer.

Two broader prompt-content decisions remain deliberately outside that structural change:

1. **Decide the untrusted-text question deliberately.** We have the hygiene — bounded, hand-filled — and no
   marker. Both products carry one, and both arrived at theirs after a failure in production. Cheap now,
   expensive to retrofit once owners have written standing instructions around the current wording.
2. **Do not build a learning loop.** If one is ever proposed, its fork's persistence is isolated on day one
   and that isolation is a requirement with a test, not a convention.

Not doing: a skills index, a personality section, content-safety text, and per-model prompt variation —
the last because our seam already hands the whole question to an adapter.

## Open questions

- Whether a marker for arriving text can be stated once in `channel.py` without the seam learning a
  platform's vocabulary.
- Whether the mobile-reply rule belongs to a surface or to an owner's own standing instructions.
- Whether either product's prompt has changed since the pinned checkouts; both were read at one commit and
  neither is versioned, so drift is invisible from here.
- What a prompt-size command would cost us, given that a preface is assembled per turn rather than cached
  in a session the way both of theirs are.

## Sources

1. OpenClaw source, read at local checkout `0920946f8356c529c073ce7185588f4a84068821` (2026-07-25), upstream https://github.com/openclaw/openclaw — (internal)
2. Hermes Agent source, read at local checkout `a61183b56fdb45b9d2a0f2f6b8482e665ccf702f` (2026-07-24), upstream https://github.com/NousResearch/hermes-agent — (internal)
3. This repository at `4cb891e` — `src/rundesk/agent.py`, `channel.py`, `answering.py`, `turn.py`, `skill.py`, `src/providers/` — (internal)
