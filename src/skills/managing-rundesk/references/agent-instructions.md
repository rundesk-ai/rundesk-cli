# Agent instructions

An agent home's `AGENTS.md` and `CLAUDE.md` hold persistent, owner-controlled behavior for that
specific agent. They define its role, responsibilities, capabilities, limits, and memory policy.
They supplement Rundesk's operating instructions and never override them. Keep both files
byte-identical so providers receive one behavior contract rather than different rules under
different filenames.

## Keep each rule with its owner

- Rundesk operating instructions are product-owned, injected every turn, and not user-controlled.
  They identify Rundesk, the agent context and current situation, then define the universal outcome,
  boundaries, execution, continuity, delegation, and completion process. Do not copy those rules
  into an agent's behavior contract.
- Recorded Rundesk configuration belongs to `agents configure`: provider, delegation description,
  outbound delegation scope, and automatic self-improvement. Change it with
  `"$RUNDESK_COMMAND"`, never by editing `state.db` or restating it in agent instructions.
- Agent instructions hold what is true for this agent on every turn: durable role, responsibilities,
  role-specific capabilities and limits, decision authority, and memory policy.
- A project's own `AGENTS.md` holds what is true for anyone working in that project: architecture,
  commands, conventions, terminology, and validation or release gates. Agent instructions do not
  copy project rules out of the project.
- Skills add conditional procedure and depth for a type of work. Do not make an agent load a skill
  merely to remember its role, and do not copy a skill inventory into agent instructions.
- The current assignment holds its outcome, scope, authority, deliverables, and proof. It does not
  become persistent behavior merely because the agent performed it once.
- `MEMORY.md` holds durable learned context useful across runs: preferences, recurring traps and
  gotchas, stable facts and references, and hard-won lessons. It does not repeat the agent's role or
  instructions, issue instructions, or grant authority.

Classify a proposed rule before writing it:

- True for every Rundesk agent? Operating instructions.
- True for this agent on every turn? Agent instructions.
- True for anyone working in this project? Project instructions.
- True only for a type of work? Skill.
- True only for this outcome? Assignment.
- A durable learned fact rather than a rule? Memory.

Split anything that mixes owners. Project instructions may narrow how work is performed but do not
broaden the assignment's authority, redefine the agent's role, or override Rundesk operating rules.

## Review the agent before writing

Do not draft or modify agent instructions until you have reviewed the agent as it currently
operates:

1. Run `"$RUNDESK_COMMAND" agents` and inspect the target's description, granted skills, and
   outbound delegation scope.
2. Read the target's existing `AGENTS.md` and `CLAUDE.md` in full. Identify owner customizations and
   any divergence; do not replace either file from a template or another agent.
3. Confirm that each requested change is durable behavior for this agent rather than a current
   assignment, universal operating process, project convention, skill procedure, or learned fact
   for memory.
4. Mark what the smallest patch must preserve, change, remove, or move to the proper owner before
   drafting it.

## Write a focused behavior contract

Write direct instructions to the agent about what it operates and how it should behave within its
role. Do not include commentary about the instruction file, when it should be edited, or how to
write instructions. Define only what this agent needs on every turn:

1. State the broad role and durable responsibilities in one compact opening.
2. Define its decision authority, role-specific capabilities and limits, and explicit non-goals.
3. Define any enduring direct-work or delegation posture without repeating Rundesk's delegation
   commands, asynchronous mechanics, or outcome lifecycle.
4. Define how the agent maintains durable learned context in `MEMORY.md` without repeating its role
   or instructions; keep assignments, changing status, dates, project commands, and history out.
5. Remove any rule already owned by Rundesk operating instructions, project instructions, or a
   conditional skill.

Use provider-neutral language. Do not mention a provider, model, copied skill list, current task, or
temporary project state.

For a newly created agent, start from the generated single-agent scaffold. Shape its role and memory
language without replacing the whole file or silently dropping its standard sections. Keep Provider
Subagents available for bounded same-turn support unless the owner explicitly defines a different
provider-local helper posture; inbound-only named delegation does not require removing it.

### Shape the agent's behavior

There is one agent template. Mold its behavior contract to the responsibility the owner assigns.

#### Domain behavior

A domain agent owns an ongoing area, product, or client. Its behavior contract defines the durable
area it owns, its prioritization and decision authority, the responsibilities it performs or
coordinates, the decisions reserved for the owner, and the domain knowledge worth retaining.

#### Specialist behavior

A specialist accepts bounded work within a defined area of expertise. Its behavior contract names
the outcomes it is equipped to handle, its role-specific capabilities and authority limits, the
adjacent work it does not own, and the artifact or evidence it normally returns. A specialist does
not adopt a parent backlog or place temporary delegated detail in memory unless it creates a durable
role-level lesson.

A coding or code-investigation specialist works in repositories it does not own. Its contract
requires reading the target project's own `AGENTS.md` before any project action and following it
alongside the contract, within the ownership split above. Name that requirement rather than the
project's rules, which are read in the checkout at the version being worked on. State that the agent
home is an operational workspace and never the project checkout; repository work belongs in the
project's own checkout.

Most specialist agents should be inbound-only. Configure them with
`"$RUNDESK_COMMAND" agents configure <agent> --delegate-to-none` unless the owner explicitly wants
that specialist to coordinate other named agents. This delegation setting reinforces the intended
behavior but does not replace the behavior contract in its instructions.

Describe those behaviors directly rather than assigning a Rundesk agent type. The instructions,
description, skills, delegation scope, and current assignment together provide enough routing and
execution context without a separate role flag.

## Change instructions safely

After reviewing the agent and drafting the focused behavior contract:

1. Save a Rundesk backup before a broad multi-agent rewrite whose recovery would be costly. One
   small reversible wording edit does not require backup ceremony unless the owner asks.
2. Show the proposed diff before replacing customized instructions, then apply the same resulting
   content to `AGENTS.md` and `CLAUDE.md`. Preserve unrelated owner rules.
3. Verify both files are byte-identical, the intended section appears once, no unrelated section
   changed, and no operating, project, skill, assignment, or memory content is duplicated.
4. Treat the current turn as already built. Validate changed behavior only in fresh target turns,
   using one representative assignment and one close near-miss. Verify that the agent accepts
   appropriate work and refuses or redirects inappropriate work.
5. When validation uses named delegation, follow the [delegation
   lifecycle](delegations.md#follow-the-lifecycle). Establish a real return path before handing off
   and run one validation case per reviewed return. Without a return path, leave the exact validation
   pending for an owner-attended fresh turn.

Do not restart a healthy gateway merely to load a rules edit. Fresh turns rebuild their instruction
context; an already-running turn keeps the context it started with.
