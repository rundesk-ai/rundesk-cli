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
- `MEMORY.md` holds durable facts and preferences useful across runs. It does not issue instructions
  or grant authority; the agent instructions define when and how the agent maintains it.

Classify a proposed rule before writing it:

- True for every Rundesk agent? Operating instructions.
- True for this agent on every turn? Agent instructions.
- True for anyone working in this project? Project instructions.
- True only for a type of work? Skill.
- True only for this outcome? Assignment.
- A durable learned fact rather than a rule? Memory.

Split anything that mixes owners. Project instructions may narrow how work is performed but do not
broaden the assignment's authority, redefine the agent's role, or override Rundesk operating rules.

## Generate a focused behavior contract

Start from the agent's description, instructions, and delegation scope. Read both existing home
instruction files in full, preserve owner customizations, and define only what this agent needs on
every turn:

1. State the broad role and durable responsibilities in one compact opening.
2. Define its decision authority, role-specific capabilities and limits, and explicit non-goals.
3. Define any enduring direct-work or delegation posture without repeating Rundesk's delegation
   commands, asynchronous mechanics, or outcome lifecycle.
4. Define what durable role knowledge belongs in `MEMORY.md` and keep assignments, status, dates,
   project commands, and history out.
5. Remove any rule already owned by Rundesk operating instructions, project instructions, or a
   conditional skill.

Use provider-neutral language. Do not mention a provider, model, copied skill list, current task, or
temporary project state.

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

Most specialist agents should be inbound-only. Configure them with
`"$RUNDESK_COMMAND" agents configure <agent> --delegate-to-none` unless the owner explicitly wants
that specialist to coordinate other named agents. This delegation setting reinforces the intended
behavior but does not replace the behavior contract in its instructions.

Describe those behaviors directly rather than assigning a Rundesk agent type. The instructions,
description, skills, delegation scope, and current assignment together provide enough routing and
execution context without a separate role flag.

## Change instructions safely

1. Run `"$RUNDESK_COMMAND" agents` and confirm the target's description and delegation scope. A
   behavior edit does not change either one.
2. Read both home instruction files in full. Identify existing customizations and divergence before
   preparing the smallest patch. Never replace a customized file merely because a canonical
   template or another agent differs.
3. Save a Rundesk backup before a broad multi-agent rewrite whose recovery would be costly. One
   small reversible wording edit does not require backup ceremony unless the owner asks.
4. Show the proposed diff before replacing customized instructions, then apply the same resulting
   content to `AGENTS.md` and `CLAUDE.md`. Preserve unrelated owner rules.
5. Verify both files are byte-identical, the intended section appears once, no unrelated section
   changed, and no operating, project, skill, assignment, or memory content is duplicated.
6. Treat the current turn as already built. Validate changed behavior in the next fresh turn with
   one representative assignment and one close near-miss. Verify that the agent accepts appropriate
   work and refuses or redirects inappropriate work.

Do not restart a healthy gateway merely to load a rules edit. Fresh turns rebuild their instruction
context; an already-running turn keeps the context it started with.
