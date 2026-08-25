# What an agent is told, and who owns each part

Every turn is composed from layers with separate owners. Rundesk contributes a small product-owned
operating layer; the agent's own instructions define who that agent is; the project contributes local
convention; the runtime supplies skills. Nothing is written twice, because an agent that reads the
same rule from two owners cannot tell which one moved when they disagree.

This page is the source of truth for that composition. What it must guarantee, and what proves each
guarantee, is [requirements/rundesk-instructions.md](../requirements/rundesk-instructions.md).

## Instruction ownership

- Rundesk operating instructions are product-owned, apply to every agent, and are not user
  controlled. They answer only what every agent needs answered the same way: where it is and what
  operates it, what this turn's situation is and which communication mechanics it may use, how to
  recover context Rundesk holds and this turn does not, what bounds the work and what must be
  loaded before it starts, which teammates are available for named delegation, and when a turn may
  honestly end. General work-quality guidance is not theirs to give: an agent's standards, method,
  and role belong to its own instructions.
- Agent instructions are controlled per agent. They define that agent's durable role,
  responsibilities, role-specific capabilities and limits, and memory policy, but cannot override
  Rundesk operating instructions.
- Project instructions apply only while work is being done in that project. They define local
  conventions and constraints without redefining the agent or Rundesk.
- Skills provide task-specific procedures and are supplied by the runtime. Their contents are not
  copied into the operating instructions.
- The current assignment supplies the immediate outcome and authority. It does not become durable
  agent behavior merely because it appeared in a turn.

Rundesk must not duplicate agent, project, skill, or memory instructions in its operating layer.
Providers may load those layers through their native instruction mechanisms.

## Operating instruction structure

Every rendered operating prompt contains these universal sections once and in this order:

1. `Rundesk`
2. `Agent Context`
3. `Current Situation`
4. `Scope and Boundaries`
5. `Before Acting`
6. `Outcome and Continuity`

The situation layer carries only communication mechanics that turn can use. Person-facing and
scheduled turns add `Messages and Attachments` after `Current Situation`; an agent-delegation turn
adds neither. This boundary follows the known turn situation rather than an agent-type flag: the
same durable agent may correctly receive different mechanics when a person asks it directly, a
schedule runs it, or another agent delegates to it.

`Team Members`, with its `Delegation` subsection, appears between `Before Acting` and `Outcome and
Continuity` only when named Rundesk delegation is available and the turn can review the
asynchronous result.

Naming the outcome is the first sentence of `Scope and Boundaries` rather than a section of its
own, because what completes the work and what bounds it are one decision. Every section heading
states when its rules apply, so an ordering guarantee is carried by the heading and not only by a
qualifier inside a bullet.

### Rundesk

One short definition identifies Rundesk as operating the agent. Person-facing commands use the bare
`rundesk ...` form. Commands inside a turn receive the resolved install root as a shell-quoted
`RUNDESK_HOME` assignment beside `"$RUNDESK_COMMAND"`, so provider tool shells cannot silently
substitute another install and unusual path characters cannot become shell syntax.

### Agent Context

This section makes clear that the context describes the agent itself. It identifies the agent,
home, and the comma-separated names of its active granted skills. It says that the separately
supplied agent instructions define the agent's role and memory; they cannot override the operating
instructions.

It states the home as an operational workspace rather than a Git repository, forbids initializing a
Git repository there, and places patch or pull-request work in the project's own checkout. It names
no file that a release places in the home.

It does not name provider-native instruction files or tell the agent to load instructions that the
provider loads automatically.

### Current Situation

Exactly one situation is rendered:

- Person: states that a person is available to answer. A change the person states as required is
  an instruction to make it within the current scope rather than something to agree with, propose,
  or wait to be asked for again; it authorizes no more than the stated change. Context the turn
  cannot see is classified as context to recover rather than a limitation to report, and the
  classification names its causes — an unclear referent, an earlier exchange, and anything a new
  session or a compaction dropped — because a turn whose conversation was present and is not any
  more does not recognize itself in "unclear referent" alone. The turn recovers that context,
  answers as though it had it, and asks only for what is still missing and still blocking.
  Recovering context is not progress: the turn neither announces a lookup nor lists what it
  searched, and reserves an update for a result, a decision, a blocker, or a requested status. That
  silence covers how context was found and never what governed the work, so an instruction to state
  which guidance was applied is unaffected. The same situation layer carries the message recovery
  and attachment mechanics below.
- Schedule: names the schedule, states that nobody is present, limits work to what the schedule
  requested, and says the final standalone response is delivered to the intended recipient or
  destination. Because nobody can be asked, context it cannot resolve is reported as a blocker
  rather than as a question. It may review supported prior messages when its recurring task
  requires them and may declare attachments in the delivered report.
- Agent delegation: names the calling agent, states that nobody is present, and says the final
  response returns to that agent alone. The delegation is the turn's complete brief and the only
  source of its outcome, scope, and authority, which is what removes the calling agent's
  conversation as something to go looking for and removes asking as an option without a separate
  prohibition for either; a brief too thin to work from is returned as the blocker, naming what is
  needed. The turn completes and verifies the work within that brief and treats it as read-only
  unless changes were explicitly authorized. Its final response is one handoff leading with the
  result, then exact changed artifacts, the verification it ran and what that showed, material
  assumptions, and remaining limitations. It does not contact the original requester or delegate to
  another named Rundesk agent, and receives no message-history or attachment mechanics. It is the
  smallest of the three situations, because a specialist's outcome, scope, and authority all arrive
  in its brief and the rules that exist because somebody is waiting have nothing to act on.

Unknown or omitted situations use the person-facing situation rather than silently adopting the
restrictions of a schedule or delegation.

### Messages and Attachments

This section makes two high-failure mechanics explicit for person-facing and scheduled turns.

Searching wide and answering narrow are two separate rules, and the section states them as two.
Collapsed into one, the audience boundary reads as a scope for the search itself: a live turn
narrowed its lookup to the room it was standing in and told the person that this channel's history
was empty, then asked them to paste the outcome back.

- Recover context with `messages {agent_name} --search "<relevant words>" --full`, then
  `messages {agent_name} --full` for the recent ones. Both commands read every conversation the
  agent has had. The turn never narrows them to one channel or conversation, and looks nowhere
  else, because nothing else holds this history — a stated boundary that also ends the outward
  search a bare prohibition invited.
- The turn answers only from results for the current `{source_kind}:{audience_id}`, never reads
  conversation files or records directly, and never repeats another agent's or audience's content.
  This is a rule about what may be said back, not about where to look.
- The turn never reports history as empty or unavailable and never asks for what a lookup should
  have found. With no match it says the search found no match and asks only for what is missing;
  on a scheduled turn that unresolved remainder is a blocker instead of a question.
- Attach a file or image with an absolute local Markdown link, such as
  `[report](/absolute/path/report.pdf)` or `![preview](/absolute/path/preview.png)`. A plain path is
  not represented as an attachment.

### Scope and Boundaries

This section opens by making the agent name what must be produced, changed, or reported, what
completes it, and what proves it. That, with the current request, schedule, or delegation, is the
whole of the turn's scope and authority, and the section closes the three things that read as
licence to do more — project rules, adjacent findings, and a useful opportunity — in the same
sentence that grants the scope, rather than leaving them to a later prohibition.

Runtime read access permits inspection and reporting only; work access permits changes only when
the current request, schedule, or delegation authorizes them. The turn delivers the smallest safe
and effective change that produces the requested result and its proof, and adds no further
deliverables, refactors, cleanup, integrations, or follow-up work. That prohibition is stated once,
in the section that owns scope. Needing materially broader scope, authority, or access is an
approval request naming why, what is proposed, and its impact, or a blocker where nobody can
approve it. The section also prohibits invented facts, capabilities, actions, or outcomes, and
exposure of secrets or sensitive information.

### Before Acting

This section is the ordered preflight, and its heading carries the ordering. "Before substantive
action" was read as "before changing anything": turns listed the tree, opened task files and loaded
project skills, and only then read the rules that decide which skills apply. The trigger is now the
project access itself — any file, listing, metadata, plan, inspection, change, or verification —
under a heading that says when the section applies.

1. Read the project's own rules in full. The project's rules are an input to which skills apply, so
   a selection made before reading them is made from half the evidence. Recovering the agent's own
   home context beforehand is not project access, and non-project work has no project rules.
2. From the skill descriptions, identify every skill applicable to this request and project, and no
   others. An unrelated granted skill stays unloaded, and file access alone does not trigger a
   development skill. Applicability follows the work itself: a standalone development task outside
   any repository may still need the skill it names.
3. Load each applicable body, together with the references it requires, through the provider's own
   skill mechanism. A skill that is listed or granted is not a skill that is loaded, and a body
   already loaded in the current session is not loaded again.
4. Inspect, create, or change anything else only after that.

A required body or reference which will not load stops the work as a reported blocker rather than
being replaced by its description. The instructions say when and what; descriptions and bodies
remain provider-native and are never copied into the prompt.

Rundesk instructs this preflight; it does not enforce or observe it. No release records which skill
bodies or references a turn loaded, and no acceptance test can prove a turn ran the preflight.
Runtime enforcement and per-turn load receipts are outside this requirement and remain unbuilt.

### Outcome and Continuity

This section combines the completion gate with ownership beyond one turn. An outcome is complete
only when every requested result, material claim, and reviewed handback is verified; an accepted
command or a started process is progress rather than proof. While verification remains, the turn
says what happened, what it verified and how, and what is still unchecked.

The continuation rule states the mechanism rather than repeating the prohibition, because the
prohibition alone did not hold: told only that a background process is not a continuation path, a
measured turn started one, started a monitor over it, wrote that it would report as soon as the
result landed, and ended. Inside a harness that really does deliver such a notification that belief
is correct, and only Rundesk's turn boundary makes it false. The turn is therefore told that it
ends when the agent stops writing and that nothing wakes it for a background command, tool session,
monitor, or child process; it waits for the result inside the turn, or stops the process and
reports the blocker, unless that process is itself the requested outcome — which must then be
started so it outlives the turn. That obligation is stated because the licence alone was obeyed to
the letter and still failed: a measured turn started a server, proved it with a real `200`, did not
kill it, and left the person a dead URL, because the child died with the turn that started it.

A turn ends in exactly one of three states: a verified outcome, a named blocker carrying its next
action, or a continuation Rundesk resumes — a requester response, a scheduled wake-up, or a
delegation return. The third is a permission and not only a prohibition, because an agent whose
only honest endings were verified and blocked has nowhere to put a delegation still out or a
schedule that will wake it. Work waiting on one of those three events is never reported as
complete.

### Team Members

This section briefly identifies the team members available for named Rundesk delegation, lists the
agents available to a person-facing turn, then places its operating guidance under a `Delegation`
subsection. That subsection is a routing boundary rather than a second delegation procedure. It
names the positive signals for considering delegation: a teammate's stated responsibility is a
materially better fit for one bounded outcome, coordination is proportionate, or independent
expertise, parallel work, or required review would improve the result. It names the corresponding
direct-work signals: small or mechanical work, continuing ownership, or coordination whose cost
exceeds its value. Ordinary conversation and simple documentation, formatting, or copy-only changes
stay direct. Availability and skill names alone never justify delegation.

The agent applies those routing signals before loading delegation guidance. It does not load
`delegating-work` merely because a teammate is available. Only when named delegation is a genuine
option is that skill classified as applicable, and its body must load before the agent chooses a
target or acts. The skill owns target selection, briefing, asynchronous lifecycle, steering,
resuming, and return review; the always-loaded operating layer does not repeat those procedures.

It is omitted for schedules because their asynchronous result cannot return to the same turn for
review. It is omitted for agent-to-agent delegations because named Rundesk delegation stops at one
level. An empty team also omits the section.

## Agent instruction template

Rundesk ships one provider-neutral agent template at `src/templates/agent/AGENTS.md` and places its
bytes under both native instruction filenames. The runtime does not classify agents as domain or
specialist agents. Those terms may be used as behavior-design patterns when an owner molds an
agent's durable role through its instructions, description, skills, and delegation scope.

The template contains only `Agent Instructions`, `Role and Responsibilities`, `Responses`,
`Provider Subagents`, and `Memory`. It addresses the agent directly and defines what it operates,
its durable responsibilities, role-specific capabilities and limits, how it answers, its supporting
use of provider-local subagents, and how it maintains separate memory. It contains no
instruction-authoring or self-editing guidance and does not repeat the operating outcome lifecycle.
Provider-local subagents serve bounded same-turn review, research, exploration, and validation that
the parent supervises and integrates. Named Rundesk agents serve asynchronous handoffs when durable
responsibility and specialized granted skills make one materially better suited; their answers can
wake review turns, while provider-local work is not a durable continuation path. The bundled
`managing-rundesk` guidance owns the review and writing process for changing agent instructions.
Its specialist design step carries a coding and code-investigation subsection: one reusable
implementation-specialist contract, preceded by the ownership rationale and followed by the
read-only investigator delta. The contract makes a coding agent read the target repository's own
`AGENTS.md` before any project action and follow it alongside its own; establish the authoritative
base, remotes, branch, existing worktrees, and uncommitted changes before acting; work in an
isolated task worktree on a topic branch cut from that base unless the assignment names another safe
workspace; preserve owner and unrelated changes without resetting, discarding, overwriting, or
folding them into the task; leave the shared checkout unchanged as found and its own task worktree
clean with coherent commits on its topic branch, keeping an explicitly requested review patch
uncommitted and reporting that exact dirty state; run the project's verification proportionate to
risk and report every gate that did not run; change no external state without assignment authority;
and hand back
the exact checkout or worktree, branch, commit or dirty files, verification and results,
limitations, and remaining work. A read-only investigator or reviewer creates no worktree, branch,
or commit and returns findings and evidence instead. The agent home stays an operational workspace
and never the project checkout, and the subsection names requirements rather than copying any
project's rules.
The separate `agent/MEMORY.md` template holds durable learned context such as preferences, traps,
gotchas, stable facts and references, and hard-won lessons without repeating agent instructions. A
person's durable preference for how work is done or answered — brevity, candor, format, or depth of
detail — is learned context for that file rather than part of the agent's role, so a stated reply
preference is recorded in memory instead of becoming a role rule.

The bundled design step also aligns an agent's granted skills with its durable role: grant what the role
needs on an ordinary turn, leave the rest ungranted, and do not restate Rundesk's loading procedure
in the agent's own contract. Its validation step inspects whatever load evidence the provider
supports in fresh turns and confirms the order actually taken — project rules first, then every
applicable body with its required references, then the remaining work — including that a close but
irrelevant granted skill stayed unloaded and an already-loaded body was not loaded again.

`Responses` sets the durable default for answering a person: a short, direct, natural reply that
reads like a text message, leading with the outcome and carrying only the context needed to
understand, act on, or verify it. The agent expands that default when the work is complex or
carries real risk, or when the person asks for more. A result returned to a calling agent is
excluded from that default and carries whatever detail and evidence that agent needs to verify and
use the work.

Agent creation, configuration, listings, team context, and communication mechanics do not expose or
depend on an agent-type flag. Existing customized instruction files remain untouched. A legacy
stored role column remains in agent records for compatibility with immutable migration history, but
current behavior does not read or change it. Situation-specific composition avoids making one
durable label predict every way an agent may be invoked.

Every person-facing agent receives Team Members and Delegation whenever at least one eligible
teammate is available under its outbound delegation scope. A legacy role value never suppresses or
changes that section. The situation and delegation-depth exclusions defined above still apply.
