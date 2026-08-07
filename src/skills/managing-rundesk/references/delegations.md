# Agent-to-agent delegation

During an agent turn, use delegation to hand a bounded part of the current task to another agent.
The other agent works from its own home and memory, not from this conversation, and returns an
unchecked answer for the delegating agent to review. `ask` from an owner's terminal instead starts
an ordinary attended turn; it is not a delegation.

## Delegate well

Before delegating, confirm the target agent appears in the team available to this turn and that its
gateway is running. Brief it with:

- the exact task and why it matters;
- the files, system, or question in scope;
- whether it may only inspect or may also change state; and
- the evidence or result it must return.

Do not delegate to yourself. A turn that is already answering a delegation cannot delegate again;
delegation depth is one.

## Commands

| Command | Control |
|---|---|
| `ask <agent> '<brief>'` | During this agent turn, hand work to another agent and return immediately with a delegation id. |
| `asked` | List this agent's delegations as `working`, `stopping`, or `answered`. |
| `asked show <id>` | Show one delegation, including its target, conversation, and timestamps. |
| `asked say <id> '<words>'` | Add guidance to outstanding work; the target reads it at its next turn. |
| `asked stop <id>` | Request a stop without claiming the work has stopped. |
| `asked resume <id> '<more>'` | Reopen answered work in the target's existing provider session. |

Prefix every command with `"$RUNDESK_COMMAND"`. Inside an agent turn, Rundesk knows which agent is
delegating. From an owner's terminal, `asked` can inspect an agent's existing delegations by adding
`--agent <delegator>` immediately after the command, for example
`"$RUNDESK_COMMAND" asked --agent <agent> show <id>`.

## Follow the lifecycle

Delegation is non-blocking. The target gateway claims the work durably, runs it, and later wakes the
delegating agent with the answer. Do not wait by polling or treat the handoff message as completion.

- `working` means the target still owns the next action.
- `stopping` means a stop was requested but has not yet been proven.
- `answered` means the delegating agent must evaluate the result.

Use `say` only while work is outstanding; it does not interrupt a provider turn already in progress.
Use `resume` only after an answer. Review the returned evidence against the original task before
adopting it, making further changes, or reporting it as fact.
