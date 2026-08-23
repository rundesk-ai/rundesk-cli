# Agent instructions

An agent home's `AGENTS.md` and `CLAUDE.md` hold persistent, owner-controlled behavior for that
specific agent. They define its role, responsibilities, capabilities, limits, and any applicable
memory policy.
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
  role-specific capabilities and limits, decision authority, and whether its operating shape keeps
  learned context.
- A project's own `AGENTS.md` holds what is true for anyone working in that project: architecture,
  commands, conventions, terminology, and validation or release gates. Agent instructions do not
  copy project rules out of the project.
- Skills add conditional procedure and depth for a type of work. Do not make an agent load a skill
  merely to remember its role, and do not copy a skill inventory into agent instructions.
- The current assignment holds its outcome, scope, authority, deliverables, and proof. It does not
  become persistent behavior merely because the agent performed it once.
- For a domain agent, `MEMORY.md` may hold durable learned context useful across its ongoing area:
  preferences, recurring traps and gotchas, stable facts and references, and hard-won lessons. It
  does not repeat the agent's role or instructions, issue instructions, or grant authority.
- An inbound specialist does not keep `MEMORY.md`. Its bounded assignments span projects, so route
  current work to the handback, project facts to that project's instructions or documentation,
  reusable methods to the owning skill, durable role behavior to agent instructions, and universal
  behavior to Rundesk operating instructions.

Classify a proposed rule before writing it:

- True for every Rundesk agent? Operating instructions.
- True for this agent on every turn? Agent instructions.
- True for anyone working in this project? Project instructions.
- True only for a type of work? Skill.
- True only for this outcome? Assignment.
- A durable learned fact for an ongoing domain? Domain-agent memory. For an inbound specialist,
  move it to the canonical project, skill, or instruction owner.

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
   owned by an ongoing domain.
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
4. For a domain agent, define how it maintains durable learned context in `MEMORY.md` without
   repeating its role or instructions; keep assignments, changing status, dates, project commands,
   and history out. For an inbound specialist, omit memory entirely and route durable context to
   its canonical project, skill, or instruction owner.
5. Remove any rule already owned by Rundesk operating instructions, project instructions, or a
   conditional skill.

Use provider-neutral language. Do not mention a provider, model, copied skill list, current task, or
temporary project state.

For a newly created agent, start from the generated single-agent scaffold. Shape its role and, for a
domain agent, its memory language without replacing the whole instruction file or silently dropping
its standard sections. For an inbound specialist, remove the scaffold's `MEMORY.md` and every
instruction to read or maintain it. Keep Provider Subagents available for bounded same-turn support
unless the owner explicitly defines a different provider-local helper posture; inbound-only named
delegation does not require removing it.

### Shape the agent's behavior

There is one agent template. Mold its behavior contract to the responsibility the owner assigns.

Grant the skills that role needs on an ordinary turn, and leave the rest ungranted. A grant is what
makes a skill loadable for the work; an unrelated one is a description every turn pays for and a
body the agent should never open. Do not restate the loading procedure in the contract: Rundesk
already instructs every turn to read the applicable project rules in full, load every skill that
applies to the work, and only then act.

#### Domain behavior

A domain agent owns an ongoing area, product, or client. Its behavior contract defines the durable
area it owns, its prioritization and decision authority, the responsibilities it performs or
coordinates, the decisions reserved for the owner, and the domain knowledge worth retaining. It may
keep compact memory because that ongoing area supplies a stable context boundary.

#### Specialist behavior

A specialist accepts bounded work within a defined area of expertise. Its behavior contract names
the outcomes it is equipped to handle, its role-specific capabilities and authority limits, the
adjacent work it does not own, and the artifact or evidence it normally returns. A specialist does
not adopt a parent backlog or keep `MEMORY.md`. Its handback carries assignment evidence; durable
project facts, reusable methods, and universal behavior belong to their canonical owners instead of
following the specialist into unrelated projects.

##### Coding and code-investigation behavior

A coding or code-investigation specialist works in repositories it does not own, so its contract has
to be specific about the checkout it touches. Name each requirement rather than copying the
project's rules, which are read in the checkout at the version being worked on. Cut this contract
down to the agent's actual area and authority:

```markdown
## Role and Responsibilities

You implement bounded changes in repositories you do not own. Before any project action, read the
target repository's `AGENTS.md` in full and follow it alongside these instructions.

## Working in a Repository

- Establish the authoritative base, its remotes, the current branch, existing worktrees, and
  uncommitted changes before acting. A branch is not authoritative because it is checked out.
- Work in an isolated task worktree on a topic branch cut from that base unless the assignment
  names another safe workspace. A topic branch in the shared checkout is not isolation. Your home
  is an operational workspace, never the project checkout.
- Preserve owner and unrelated changes. Never reset, discard, overwrite, or fold somebody else's
  work into the task, and treat an unfamiliar file as owned data rather than as cleanup.
- Leave the shared checkout unchanged as found; it is not yours to tidy, and it may already carry
  work in progress. Leave your own task worktree clean with coherent commits on its topic branch,
  unless the assignment asks for an uncommitted patch to review — then leave it uncommitted and
  report that exact dirty state rather than abandoning or tidying it away.
- Run the verification the project defines, proportionate to the risk of the change, and report
  every gate that did not run.
- Do not push, use a code-hosting service, merge, release, or change external state without
  authority in the assignment.

## Handback

Return the exact checkout or worktree path, branch, commit or dirty files, verification and results,
limitations, and remaining work.
```

A read-only code investigator or reviewer drops the mutation rules: it creates no worktree, branch,
or commit, and returns findings and evidence instead of changes. It keeps the project's `AGENTS.md`,
the state it inspected, the verification it ran, the external-state limits, and the handback.

Most specialist agents should be inbound-only. Configure them with
`"$RUNDESK_COMMAND" agents configure <agent> --delegate-to-none` unless the owner explicitly wants
that specialist to coordinate other named agents. The setting removes `delegating-work`
automatically; do not grant delegation procedure to an agent with no named delegation authority.
This delegation setting reinforces the intended behavior but does not replace the behavior contract
in its instructions.

Describe those behaviors directly rather than assigning a Rundesk agent type. The instructions,
description, skills, delegation scope, and current assignment together provide enough routing and
execution context without a separate role flag.

## Change instructions safely

After reviewing the agent and drafting the focused behavior contract:

1. Save a Rundesk backup before a broad multi-agent rewrite whose recovery would be costly. One
   small reversible wording edit does not require backup ceremony unless the owner asks.
2. Before removing an existing specialist's memory, review it and move only still-valid material to
   the canonical project, skill, or instruction owner; do not preserve stale task history merely to
   avoid deletion. Then show the proposed diff before replacing customized instructions.
3. Apply the same resulting content to `AGENTS.md` and `CLAUDE.md`. Preserve unrelated owner rules.
4. Verify both files are byte-identical, the intended section appears once, no unrelated section
   changed, and no operating, project, skill, assignment, or memory content is duplicated. For an
   inbound specialist, also verify that `MEMORY.md` and every instruction to read or maintain it are
   absent.
5. Treat the current turn as already built. Validate changed behavior only in fresh target turns,
   using one representative assignment and one close near-miss. Verify that the agent accepts
   appropriate work and refuses or redirects inappropriate work.
6. In those fresh turns, inspect whatever load evidence the provider supports — its transcript,
   tool record, or the turn's own report — and confirm the order the turn actually took: the
   project's own rules read in full first, then every skill applicable to the assignment loaded
   with the references its body requires, then the remaining work. Confirm that a close but
   irrelevant granted skill stayed unloaded, and that a body already loaded earlier in the session
   was not loaded again. A skill named in a listing is not evidence that its body was read, and a
   body loaded after the work began did not govern it.
7. When validation uses named delegation, follow the `delegating-work` skill's handoff lifecycle.
   Establish a real return path before handing off and run one validation case per reviewed return.
   Without a return path, leave the exact validation pending for an owner-attended fresh turn.

Do not restart a healthy gateway merely to load a rules edit. Fresh turns rebuild their instruction
context; an already-running turn keeps the context it started with.
