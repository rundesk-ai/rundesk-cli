# Agents

An agent owns `data/agents/<agent>/`: its records, home, identity files, and logs. Manage it by name;
do not edit its database to change identity or provider.

## Commands

| Command | Control |
|---|---|
| `agents` or `agents list` | List every agent and recorded provider. |
| `agents add <agent> --provider <provider> [--describes <text>]` | Create an agent. `--describes` is the one-sentence purpose another agent reads before delegating. |
| `agents configure <agent> [--provider <provider>] [--describes <text>] [--self-improve <true\|false>]` | Change provider, delegation description, or protected upkeep. Unnamed fields stay unchanged. |
| `agents remove <agent> [--confirm]` | Preview removal; `--confirm` removes the agent and everything it remembers. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Safe operating flow

1. Run `providers` and `providers check <provider>`. Recording a provider does not prove it can run.
2. Add the agent with a name that can also be a launchd label: letters, digits, `.`, `-`, or `_`.
3. Run `agents` to verify the recorded result, then `gateways start <agent>` to prove it starts.
4. Edit the agent's `AGENTS.md` and `MEMORY.md` when changing how it works or what it knows; those
   files are its identity, not columns in `state.db`.

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
