# Agent-to-agent delegation

During an agent turn, use delegation to hand a bounded part of the current task to another agent.
The other agent works from its own home and memory, not from this conversation, and returns an
unchecked answer for the delegating agent to review. `ask` from an owner's terminal instead starts
an ordinary attended turn; it is not a delegation.

## Delegate well

Choose the target from its description in the team available to this turn: that sentence is the
agent's durable routing scope. Do not infer ownership from its name, provider, skill list, or gateway
state; gateway state says only whether the chosen route is currently available. If no description
matches the work, do not delegate on a guess.

The team shown to this turn is also bounded by this agent's outbound delegation scope. The default
allows any available peer; a scoped agent sees only its allowlist; an inbound-only agent sees no
named-agent delegation instructions at all. Do not work around an absent target by invoking `ask`
directly: Rundesk checks the same scope before it records a handoff. The scope does not control who
may delegate work to this agent.

Before delegating, confirm the chosen agent's gateway is running. Brief it with:

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
| `asked` | List this agent's delegations as `working`, `stopping`, `stopped`, or `answered`. |
| `asked show <id>` | Show one delegation, including its target, conversation, and timestamps. |
| `asked say <id> '<words>'` | Steer outstanding work now; if the active turn is missed, its next turn reads the durable guidance. |
| `asked stop <id>` | Durably request a stop; the target gateway ends the live provider process or settles an unstarted brief without launching it, then closes the delegation without another review response. |
| `asked resume <id> '<more>'` | Reopen answered work in the target's existing provider session. |

Prefix every command with `"$RUNDESK_COMMAND"`. Inside an agent turn, Rundesk knows which agent is
delegating. From an owner's terminal, `asked` can inspect an agent's existing delegations by adding
`--agent <delegator>` immediately after the command, for example
`"$RUNDESK_COMMAND" asked --agent <agent> show <id>`.

Owners configure the outbound routes with `agents configure <agent>`: repeat `--delegate-to
<target>` for an exact list, use `--delegate-to-none` for an inbound-only agent, or use
`--delegate-to-any` to restore unrestricted delegation. `agents` shows the resulting policy as
`any`, `none`, or the configured names. Removing a target prunes it from explicit lists before the
removal; recreating that name does not restore old authority, while `any` remains unrestricted.

## Follow the lifecycle

Delegation is non-blocking. The target gateway claims the work durably, runs it, and later wakes the
delegating agent with the answer. Do not wait by polling or treat the handoff message as completion.

- `working` means the target still owns the next action.
- `stopping` means a stop was requested but the target turn has not yet reported its terminal state;
  once stopped, the delegation settles silently rather than waking a review turn.
- `stopped` is a durable terminal outcome distinct from `answered`; it cannot be resumed.
- `answered` means the delegating agent must evaluate the result.

Use `say` only while work is outstanding. The target gateway offers it to the provider turn already
running and keeps it for the next turn only when that live steer is missed or refused. Use `resume`
only after an answer. Review the returned evidence against the original task before
adopting it, making further changes, or reporting it as fact.
