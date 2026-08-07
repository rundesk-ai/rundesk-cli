# Channels

A channel is one adapter connection for one agent. It holds the platform settings, allowed sender
IDs, credential name, and whether unsolicited notifications go there.

## Commands

| Command | Control |
|---|---|
| `channels` or `channels list [<agent>]` | List all channels or one agent's. |
| `channels add <agent> <adapter> --allow <id> [--allow <id> ...] [--notify] [--with '<adapter opts>']` | Connect and persist a channel after the adapter proves it can reach the platform. |
| `channels show <agent> <adapter>` | Show the complete stored channel definition. |
| `channels configure <agent> <adapter> [--allow <id> ...] [--deny <id> ...] [--notify]` | Add or remove allowed senders or choose the notification channel. |
| `channels test <agent> <adapter>` | Connect again and report what the adapter reached. |
| `channels remove <agent> <adapter> [--confirm]` | Preview removal; `--confirm` removes the connection. |
| `channels doctor [<agent>]` | Diagnose every channel or one agent's as READY, BLOCKED, UNREACHABLE, or DANGLING. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Connect safely

1. Run `channels doctor <agent>` and `env check <credential-name>` when the adapter's required name
   is known.
2. Have the owner run `env set <NAME>` at their own terminal. Never receive or pass the value.
3. Add at least one exact platform sender ID with repeatable `--allow`. An empty allow list is
   refused so a connected agent cannot silently answer nobody.
4. Quote `--with` as one string. Rundesk passes those words to the adapter without a shell and does
   not interpret platform-specific options.
5. Run `show`, `test`, and `doctor`; then inspect gateway logs after the gateway hosts it.

`add`, `test`, and `doctor` may connect to the platform. `add` records the channel only after the
adapter's check succeeds, although a credential typed during the attempt remains stored so the owner
need not re-enter it for an unrelated retry.

## Access and recovery

- `--allow` and `--deny` modify the access list; denying its last ID is refused. IDs are adapter
  values, not names Rundesk translates.
- Only one channel per agent is the `--notify` destination. Selecting another moves that role.
- Removal needs preview and `--confirm`; it does not erase message history or the separately stored
  credential. Use `env unset <NAME>` only when the owner also wants the value emptied.
- A channel failure must not take down the gateway. Use `channels doctor`, `channels test`, and
  `gateways logs` to isolate the adapter rather than cycling every agent.
