# Backups

Backups copy the install's durable `data`. They do not include credentials, program releases, or the
backup directory itself.

## Commands

| Command | Control |
|---|---|
| `backups` | List copies newest first and show their location. |
| `backups save` | Make a copy now and apply configured retention. |
| `backups restore <backup> [--confirm]` | Preview a whole-data restore; `--confirm` performs it. |
| `backups set-location <path>` | Move the backup collection and make that directory its location. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Save and restore safely

1. Run `backups` and record the exact copy name and location.
2. Run `backups save` before an approved destructive operation.
3. For restore, use the exact listed name without `--confirm` and inspect what will be replaced.
4. Repeat with `--confirm` only when the owner requested that whole-install rollback.
5. Run `status`, `agents`, and `gateways` after restore. Rundesk cycles gateways that were running
   and carries restored agent records through current migrations before declaring success.

Restore replaces all agent data and configuration with the chosen copy. Agents, conversations,
schedules, channels, and grants created later may disappear. Rundesk first preserves the data being
replaced, but that does not make an accidental restore harmless.

## Location and limits

- `set-location` moves the full collection. Use an explicit absolute path, then run `backups` and
  verify the reported location before relying on it.
- `configure --backup-enabled` controls the safety copy made before an update carries outstanding
  install migrations. `--backup-retention` controls how many copies a manual save keeps.
- Credentials live separately and are never restored. Diagnose missing values with `env` and
  `skills doctor`; have the owner type replacements at their terminal.
- Backups are never removed by uninstall, including purge. Keep an external copy when machine loss
  is part of the threat model.
