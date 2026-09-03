# Providers

Providers are executable adapters for CLI brains. They speak newline-delimited JSON over pipes;
Rundesk imports no provider library.

## Commands

| Command | Control |
|---|---|
| `providers` or `providers list` | List shipped and owner-provided adapters and their program paths. |
| `providers check <provider>` | Ask an adapter for capabilities offline; accepts a known name or program path. |
| `providers aliases list|add|remove <provider> ...` | List, register, or confirmed-remove additional account aliases. `default` is reserved. |
| `providers status|login|logout <provider> [--alias <alias>]` | Use the provider-owned account flow; login/logout are interactive and logout requires confirmation. |
| `providers instructions [<agent>] [--situation <person\|schedule\|agent>] [--layers] [--turn <turn>]` | Render current instructions, show only layer byte counts, or recompose a past turn and compare it. |
| `providers run <agent> --schedule <schedule>` | Take the provider turn for an asking schedule. This is the schedule launch path, not the normal attended interface. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Inspect before running

1. Run `providers` to resolve the program actually selected.
2. Run `providers check <provider>`. It performs no account login, network request, or turn; it
   proves only that the adapter runs and reports a usable protocol and capabilities.
3. Use `providers instructions <agent> --layers` to inspect prompt cost, or omit `--layers` to inspect
   the composed instructions. Use `--turn <turn>` when investigating whether a past prompt still
   matches current files.
4. Run `ask <agent> '...'` to prove real provider execution, credentials, and account access.

Adding or configuring an agent records a provider and optional additional-account alias. Omitting
the alias means the ordinary provider account. It does not prove the adapter, brain, or login.
Provider-specific model names belong on `ask --model`; Rundesk passes them through.

## Trust boundary and recovery

- A provider process receives the values the install owns because skills and adapters may need
  them. Treat every installed provider as trusted with all install credentials; per-agent profiles
  select values for a skill but are not process containment.
- A capability check can succeed while a real turn fails. Inspect the exact turn with `turns`, then
  separate adapter/protocol failure from account or network failure.
- `providers run` exists so the scheduler can start an unattended `--ask`. Do not use it instead of
  `ask` for ordinary management; it requires an existing schedule and follows schedule conversation
  and claim rules.
- Never inspect, copy, print, or synchronize files inside `data/provider-accounts/`. Use only the
  provider commands above. Backups deliberately omit these homes, so re-register and authorize
  aliases after a restore.
