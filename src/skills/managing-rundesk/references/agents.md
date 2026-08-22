# Agents

An agent owns `data/agents/<agent>/`: its records, home, identity files, and logs. Manage it by name;
do not edit its database to change identity or provider.

## Commands

| Command | Control |
|---|---|
| `agents` or `agents list` | List agents with provider, skills, and outbound delegation scope. |
| `agents add <agent> --provider <provider> [--describes <text>]` | Create an agent. `--describes` is the one-sentence purpose another agent reads before delegating. |
| `agents configure <agent> [--provider <provider>] [--describes <text>] [--self-improve <true\|false>] [--delegate-to <agent> ... \| --delegate-to-any \| --delegate-to-none]` | Change recorded settings. Unnamed fields stay unchanged. |
| `agents remove <agent> [--confirm]` | Preview removal; `--confirm` removes the agent and everything it remembers. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Decide the intended behavior

Before creating an agent, determine whether the owner intends it to behave primarily as a domain
agent or a specialist. These are behavior-design patterns, not Rundesk configuration values.

- A domain agent owns an ongoing project, client, or operating area. Its instructions should define
  intake, prioritization, continuity, delegation, integration, and owner communication.
- A specialist accepts bounded work in a focused area and returns evidence. Its instructions should
  define accepted assignments, adjacent boundaries, execution authority, verification, handback,
  and when to stop. In most cases, configure it with `--delegate-to-none` so it receives work but
  does not create another named delegation. That setting automatically removes `delegating-work`;
  do not grant the skill back to an inbound-only specialist. Keep outbound delegation only when the
  owner explicitly intends the specialist to coordinate other agents.

Both use the same `agents add` command and the same initial template. After creation, refine the
agent's owner-controlled instructions to express the intended behavior directly. Do not infer the
pattern from its provider, skills, name, or delegation scope, and do not look for a role flag.

Read [Agent instructions](agent-instructions.md) before designing or changing an agent's persistent
behavior.

## Write the delegation description

Treat `--describes` as a routing contract, not a biography. In one sentence, name the durable
responsibility it owns and the project, client, specialty, or operating boundary that lets another
agent decide whether to delegate there. Describe responsibility, not merely abilities: an agent may
have many skills without accepting every task those skills could perform.

Do not use transient assignments, current status, provider or model names, or a skill inventory as
the description. Put changing task state in the task's own tracker and let `agents` report provider
and grants. Update the description when durable responsibility changes; remove it only when the
agent should no longer appear to other agents as a delegation route. Verify the stored sentence with
`agents` after every change.

## Scope outbound delegation

Delegation is unrestricted by default. Use repeated `--delegate-to <agent>` options to replace that
default with an exact allowlist, `--delegate-to-none` to make an agent inbound-only, and
`--delegate-to-any` to restore the default. The modes are mutually exclusive:

```sh
"$RUNDESK_COMMAND" agents configure cole --delegate-to forge --delegate-to trace
"$RUNDESK_COMMAND" agents configure forge --delegate-to-none
"$RUNDESK_COMMAND" agents configure cole --delegate-to-any
```

This setting controls only where the configured agent may delegate. An inbound-only agent can
still receive work. When its outbound scope is empty, Rundesk removes the entire named-agent team
and delegation instruction block from its turns and revokes `delegating-work`. Setting an exact
allowlist or restoring `any` grants the bundled skill when it is absent. New agents start
unrestricted and receive the skill by default. Removing a target also removes its name from every
explicit allowlist, so recreating the name does not restore old authority; unrestricted scopes stay
unrestricted. Do not edit `state.db`; verify `DELEGATES TO` and `SKILLS` with `agents` after every
change.

## Safe operating flow

1. Run `providers` and `providers check <provider>`. Recording a provider does not prove it can run.
2. Confirm whether the owner intends domain or specialist behavior, then add the agent with a name
   that can also be a launchd label: letters, digits, `.`, `-`, or `_`. Configure an inbound-only
   specialist with `--delegate-to-none`; do not leave its default delegation grant in place.
3. Run `agents` to verify the recorded result, then `gateways start <agent>` to prove it starts.
4. Apply [Agent instructions](agent-instructions.md) to mold the shared template into the intended
   behavior. Edit `MEMORY.md` only when changing durable context it should know; neither belongs in
   `state.db`.

## Removal and recovery

- Removal refuses while the agent has a running gateway, hosted channel, or firing schedule. Stop
  the owning activity first; do not force past the refusal.
- Save a backup, run removal without `--confirm`, inspect the preview, then repeat with `--confirm`
  only for the exact requested agent.
- Removal takes the agent's Rundesk-managed memory. A later backup cannot recover what an earlier
  removal deleted; restore an older backup only when the owner explicitly chooses that whole-install
  rollback.
- Extra files the owner placed inside the agent directory are kept, along with that directory.
  Read the removal result to distinguish a removed agent from a fully absent path.
- If a configured provider fails, keep the agent and diagnose with `providers check`, `ask`, and
  `turns`. Reconfiguring the name merely records another provider; it does not test credentials.
