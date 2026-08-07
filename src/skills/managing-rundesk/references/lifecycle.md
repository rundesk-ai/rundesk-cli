# Install lifecycle

Lifecycle commands manage Rundesk's program tree and launchd jobs. Treat update and removal as
machine-level operations; preserve owner data and report every refusal.

## Commands

| Command | Control |
|---|---|
| `install [--source <dir>] [--bin-dir <dir>]` | Install from a program tree and place the command link in the chosen PATH directory. Defaults use the running source and installer-selected bin directory. |
| `update` | Check the published release and move to it, or prove this install is already settled. |
| `uninstall [--confirm]` | Preview removal; `--confirm` removes program, job definitions, and command link while retaining owner data, backups, and credentials. |
| `uninstall --purge [--confirm]` | Also remove owner data and credentials. Backups are never removed. |

Prefix every command with `"$RUNDESK_COMMAND"` for an existing install. An update may restart the
gateway hosting the current agent; Rundesk queues that restart until the active turn finishes and
then brings the gateway back online.

## Install

- Outside an installed agent turn, explicitly set the intended `RUNDESK_HOME` and pin `--bin-dir`.
  Never assume the default root or write through an unrelated command on `PATH`.
- `--source` must be the Rundesk tree to place. A successful install settles migrations and records
  the command link it actually created.
- Run `status` using the newly placed absolute command. An installer that did not prove the result
  has not completed.

## Update

1. Run `status`, `version`, and `backups save`.
2. Run `update`. It cycles only gateways whose agents need migration, records which were running,
   and starts exactly those again even when carrying an agent fails. Do not stop them preemptively.
3. Preserve all three release answers: moved, already current, or unable to determine the published
   version. Unknown is not up to date. `version` may report UNKNOWN and exit `0` because it answered;
   `update` exits nonzero when it cannot determine what to install.
4. Run `status` and `version` again. Install migrations advance once in `config.json`; each agent's
   migrations advance independently, so one agent's failure need not conceal the others.

## Uninstall and purge

1. Save and list backups. Run the exact uninstall without `--confirm` and inspect the preview.
2. Use ordinary uninstall unless the owner explicitly requested deletion of data and credentials.
3. Add `--confirm` only after the owner approves the named root and retained/removed categories.
4. Report what was removed and what remains, especially the backup location.

Uninstall stops placed jobs before removing the program. `--purge` is irreversible from the local
install data; recovery requires an existing backup and separately restored credentials.
