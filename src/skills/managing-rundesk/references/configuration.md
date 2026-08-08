# Configuration and values

Rundesk derives every location from `RUNDESK_HOME`. Install settings live in `data/config.json`;
credential values live separately and are masked in every command output.

## Inspect the install

| Command | Control |
|---|---|
| `status` | Show version, root, program, data, backups, command link, migrations, and health. |
| `version` | Show the installed version and whether the published state is newer, current, or unknown. |
| `configure` | List every owner-settable setting, effective value, and exact flag. |

Always run these as `"$RUNDESK_COMMAND" ...`. `status` is the first answer to path and install
identity questions. Do not construct a path from defaults or set `RUNDESK_HOME` inside a turn.

## Settings

`configure` accepts any combination of current setting flags and applies them atomically:

| Flag | Value |
|---|---|
| `--backup-enabled <yes|no>` | Enable or disable the safety copy made before update carries outstanding install migrations. |
| `--backup-retention <n>` | Keep this many recognized copies when `backups save` prunes older ones. |
| `--update-enabled <yes|no>` | Record whether automatic updates are intended to be enabled. |
| `--update-time <HH:MM>` | Record the intended local time for an automatic update check. |
| `--turn-records-days <n>` | Keep at least one day of detailed tool records. Messages and turn ledger rows remain. |

Run `configure` first because newer releases may add settings. Invalid multi-setting input changes
nothing; a successful call changes every requested setting together.

Automatic upkeep is per-agent rather than an install setting. Inspect `agents`, then use
`agents configure <agent> --self-improve <true|false>`. The protected
`weekly-self-improve-upkeep` policy cannot be enabled, disabled, run, or removed through `schedules`.
A pre-policy owner schedule already using that name remains ordinary owner work and blocks the
automatic policy until the owner removes it; Rundesk never adopts or overwrites it.

The current release stores `update_enabled` and `update_time` but does not itself schedule automatic
update jobs from them. Use `update` for an update that exists today.

## Credential values

| Command | Control |
|---|---|
| `env` or `env list` | List names and masked hints, never complete values. |
| `env check <KEY>` | Exit successfully only when the name has a usable value; distinguish missing, empty, and unreadable. |
| `env set <KEY>` | Read a value without echo from a terminal, or from standard input. The value is never an argument. |
| `env unset <KEY>` | Empty the value while retaining its known name. |

Never request, print, echo, or paste a credential into chat or an argument. Give the owner the `env
set` command to type locally. A changed value is available to newly started processes and the next
agent turn; it cannot alter the environment of the current process.

Backups exclude values. When a restore, machine move, or integration failure leaves a value absent,
use `env check`, `channels doctor`, or `skills doctor` to name what the owner must set.
