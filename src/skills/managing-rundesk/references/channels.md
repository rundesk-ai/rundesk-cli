# Channels

A channel is one adapter connection for one agent. It holds the platform settings, the allow list,
credential names, and whether unsolicited notifications go there. Two adapters ship: `discord` and
`slack`.

## Commands

| Command | Control |
|---|---|
| `channels` or `channels list [<agent>]` | List all channels or one agent's. |
| `channels add <agent> <adapter> --allow <id> [--allow <id> ...] [--notify] [--with '<adapter opts>']` | Connect and persist a channel after the adapter proves it can reach the platform. |
| `channels show <agent> <adapter>` | Show the complete stored channel definition. |
| `channels configure <agent> <adapter> [--allow <id> ...] [--deny <id> ...] [--notify]` | Add or remove allowed senders and places, or choose the notification channel. |
| `channels test <agent> <adapter>` | Reach the platform again and report what the adapter found. |
| `channels remove <agent> <adapter> [--confirm]` | Preview removal; `--confirm` removes the connection. |
| `channels doctor [<agent>]` | Diagnose every channel or one agent's as READY, BLOCKED, UNREACHABLE, DANGLING, or GIVEN UP. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Connect safely

1. Run `channels doctor <agent>` and `env check <credential-name>` when the adapter's required name
   is known.
2. Have the owner run `env set <NAME>__<AGENT>` at their own terminal. Never receive or pass the
   value. **The name is per-agent and there is no shared fallback**: the adapter declares
   `DISCORD_BOT_TOKEN`, the value is kept under `DISCORD_BOT_TOKEN__ALAN`, and a plain
   `DISCORD_BOT_TOKEN` is not read at all. One Discord application per agent — two agents behind one
   token are one bot answering twice. The `slack` adapter declares two names,
   `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`, and refuses a Slack user token by name.
3. Add at least one entry with repeatable `--allow`. An empty allow list is refused so a connected
   agent cannot silently answer nobody. An entry is one of three things:

   | Entry | Allows |
   |---|---|
   | `2207` | that sender, wherever they say it — the plain form every list has always used |
   | `sender:2207` | the same thing, said out loud |
   | `place:C0OPS` | anybody the adapter reports as being in that place |

   Only `sender:` and `place:` make an entry typed; anything else before a colon is part of the ID.
   An entry naming nothing (`place:` with no ID) is refused. `--deny` takes an entry written exactly
   as it stands on the list. Rundesk decides admission, never the adapter, and a place entry never
   admits an event with no sender behind it.
4. **Pass `--notify` on the first channel, and make it the owner's own direct message.** On Discord,
   every allowed user receives unsolicited notices privately; no separate recipient list is needed.
   See below: this is the one setup mistake the command cannot warn about.
5. Quote `--with` as one string. Rundesk passes those words to the adapter without a shell and does
   not interpret platform-specific options.
6. Run `show`, `test`, and `doctor`; then inspect gateway logs after the gateway hosts it.

`add`, `test`, and `doctor` run the adapter's platform check. Discord opens its gateway connection;
Slack authenticates and obtains a Socket Mode URL without opening it. `add` records the channel only
after the check succeeds, although a credential typed during the attempt remains stored so the
owner need not re-enter it for an unrelated retry.

## The notified channel, and why a first setup must not skip it

**`--allow` is who may reach the agent and, on Discord, who receives its private unsolicited
notices. `--notify` selects which channel adapter speaks first.** Only the first is required, so a
channel added without `--notify` connects, answers when spoken to, and never says anything on its
own.

What is lost is everything unprompted: the gateway announcing that it came up and that it is going
down, a skill gained or revoked, a schedule's report, a delegation handing its result back. The
gateway's up-notice is gated on the notified channel having reached its platform, and an agent with
no notified channel is treated as ready — deliberately, because waiting for a connection that will
never exist would hold the notice for ever, which is the same silence from the other side.

**So there is no error and no warning.** `add` refuses a missing `--allow` outright; a missing
`--notify` leaves a working agent and one word — `told no` — in the block it prints. Observed on a
real setup: the bot answered a DM immediately and the owner asked why it had never announced itself.

- **Make Discord the notified channel** on the first channel added. Each allowed user receives their
  own private copy; adding or denying an allowed ID changes that recipient set when the adapter next
  starts. Direct replies still stay only in the conversation that asked.
- Adding it afterwards is `channels configure <agent> <adapter> --notify` — **then restart the
  gateway**, because the up-notice is said once per gateway and the one already running has
  said it.
- Only one channel adapter per agent is notified. Selecting another moves that role; schedules do
  not choose a caller's DM separately.

## Access and recovery

- `--allow` and `--deny` modify the access list; denying its last ID is refused. IDs are adapter
  values, not names Rundesk translates.
- Removal needs preview and `--confirm`; it does not erase message history or the separately stored
  credential. Use `env unset <NAME>` only when the owner also wants the value emptied.
- A channel failure must not take down the gateway. Use `channels doctor`, `channels test`, and
  `gateways logs` to isolate the adapter rather than cycling every agent.
