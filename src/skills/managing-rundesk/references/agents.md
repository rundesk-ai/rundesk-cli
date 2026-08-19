# Agents

An agent owns `data/agents/<agent>/`: its records, home, identity files, and logs. Manage it by name;
do not edit its database to change identity or provider.

## Commands

| Command | Control |
|---|---|
| `agents` or `agents list` | List domain agents and specialists separately, with provider and outbound delegation scope. |
| `agents add <agent> --provider <provider> [--role <domain\|specialist>] [--describes <text>]` | Create an agent. Role defaults to domain; `--describes` is the one-sentence purpose another agent reads before delegating. |
| `agents configure <agent> [--provider <provider>] [--role <domain\|specialist>] [--describes <text>] [--self-improve <true\|false>] [--delegate-to <agent> ... \| --delegate-to-any \| --delegate-to-none]` | Change recorded settings. Unnamed fields stay unchanged, and role changes never rewrite rules. |
| `agents remove <agent> [--confirm]` | Preview removal; `--confirm` removes the agent and everything it remembers. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Choose the operating role

Use `domain` for an agent that owns ongoing work, a project/client area, and its persistent Desk
queue when it holds `managing-your-desk`. Use `specialist` for an agent that accepts one bounded
assignment from its delegator. Domain is the default for creation and migration.

Role is independent of provider, skills, outbound delegation scope, and whether a Desk exists. A
specialist may be inbound-only, but the role itself does not set that scope. Creation writes the
selected canonical template to both `AGENTS.md` and `CLAUDE.md` with identical bytes. Configuring a
different role changes only the record and team grouping; it deliberately preserves both rule files.
If the owner explicitly asks to apply another template later, inspect both files for customization,
prepare the replacement visibly, and make the two resulting files byte-identical. Never infer
permission to replace rules from a role change alone.

Read [Agent instructions](agent-instructions.md) before designing or changing an agent's persistent
behavior or specialist role focus.

## Write the delegation description

Treat `--describes` as a routing contract, not a biography. In one sentence, name the durable
responsibility it owns and the domain, project, client, or operating boundary that lets another
agent decide whether to delegate there. Describe ownership, not merely abilities: a specialist may
have many skills without owning every task those skills could perform.

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

This setting controls only where the configured agent may delegate. An inbound-only specialist can
still receive work. When its outbound scope is empty, Rundesk removes the entire named-agent team
and delegation instruction block from its turns. Removing a target also removes its name from every
explicit allowlist, so recreating the name does not restore old authority; unrestricted scopes stay
unrestricted. Do not edit `state.db`; verify `DELEGATES TO` with `agents` after every change.

## Safe operating flow

1. Run `providers` and `providers check <provider>`. Recording a provider does not prove it can run.
2. Choose `domain` or `specialist`, then add the agent with a name that can also be a launchd label:
   letters, digits, `.`, `-`, or `_`.
3. Run `agents` to verify the recorded result, then `gateways start <agent>` to prove it starts.
4. Apply [Agent instructions](agent-instructions.md) when changing how the agent works. Edit
   `MEMORY.md` only when changing durable context it should know; neither belongs in `state.db`.

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
