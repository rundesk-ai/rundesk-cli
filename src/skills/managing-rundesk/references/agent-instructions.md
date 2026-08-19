# Agent instructions

An agent home's `AGENTS.md` and `CLAUDE.md` hold persistent, owner-changeable behavior. Use them for
how this agent should work on every turn, including its role, authority, boundaries, communication,
delegation posture, and always-on quality rules. Keep both files byte-identical so providers receive
one role contract rather than different behavior under different filenames.

## Put each kind of state in one place

- Recorded Rundesk configuration belongs to `agents configure`: provider, operating role,
  delegation description, outbound delegation scope, and automatic self-improvement. Change it with
  `"$RUNDESK_COMMAND"`, never by editing `state.db` or restating it in agent instructions.
- Agent instructions hold durable behavior the owner expects on every turn. Do not put current
  assignments, changing project status, provider details, model names, or a skill inventory there.
- Skills add conditional procedure and depth for repeatable work. Do not make a specialist load a
  skill merely to remember its role; keep its always-on role contract in its agent instructions.
- A project's own `AGENTS.md` holds local architecture, commands, conventions, and gates. Agent-home
  rules require discovering and following it; they do not copy project rules out of the project.
- `MEMORY.md` holds durable facts and preferences useful across runs. Track active outcomes in the
  project's canonical tracker or the agent's compact operational index and resumable briefs.

When one proposed instruction mixes these owners, split it before editing. A skill can teach a
planner how to plan a database migration without becoming the reason a planning specialist knows it
must plan rather than implement.

## Write a specialist role contract

Give one specialist one durable lifecycle responsibility. State the contract compactly:

1. Name the assignments it accepts and the boundary that distinguishes them from another agent's.
2. State its default authority, including whether it plans, changes files, reviews read-only, tests,
   publishes, or must return for approval.
3. Name the input it must ground itself in: the original owner outcome, the assignment, applicable
   project instructions, existing work, and repository state.
4. Define the smallest useful handback: artifact or change, observed proof, changed paths, unresolved
   risks, and the exact decision needed when blocked.
5. Require scope classification. Request-required work and regressions introduced by its change stay
   in scope; pre-existing and adjacent findings are reported without becoming new work.

Keep the role focused on responsibility rather than technology inventory. A planning specialist
always produces decision-ready plans and does not implement. An implementation specialist makes the
bounded change and proves it without publishing unless assigned. A review specialist independently
compares the result with the original request and stays read-only unless fixes are assigned. Skills
may deepen any of those roles for a framework, integration, risk, or artifact.

Do not turn every task into the full specialist chain. The delegating owner chooses only the roles
the work's size and risk justify, retains the outcome, and reviews every handback.

## Change instructions safely

1. Run `"$RUNDESK_COMMAND" agents` and confirm the target's recorded role, description, and
   delegation scope. A rules edit does not change any of them.
2. Read both home instruction files in full. Identify existing customizations and any divergence
   before preparing the smallest patch. Never replace a customized file merely because a canonical
   template or another agent differs.
3. Save a Rundesk backup before a broad multi-agent rewrite or a role change whose recovery would be
   costly. One small reversible wording edit does not require backup ceremony unless the owner asks.
4. Apply the same resulting content to `AGENTS.md` and `CLAUDE.md`. Preserve unrelated owner rules,
   project pointers, and provider-neutral wording.
5. Verify both files are byte-identical, the intended section appears once, and no unrelated section
   changed. Re-run `"$RUNDESK_COMMAND" agents` when recorded configuration was changed separately.
6. Treat the current turn as already built. Validate changed behavior in the next fresh turn with one
   representative assignment and one close near-miss; do not claim the new contract worked merely
   because the files contain it.

Do not restart a healthy gateway merely to load a rules edit. Fresh turns rebuild their instruction
context; an already-running turn keeps the context it started with.
