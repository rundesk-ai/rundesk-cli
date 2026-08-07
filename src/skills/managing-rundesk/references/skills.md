# Skills

Skills are filesystem instruction bundles in Rundesk's library. Catalogs supply skills; grants make
selected skills visible to an agent; profiles configure the values a skill declares.

## Library and catalog commands

| Command | Control |
|---|---|
| `skills` or `skills list [<agent>]` | List the library or one agent's grants. |
| `skills catalogs` | List installed catalogs, versions, and sources. |
| `skills install <repository> [--confirm]` | Validate and preview a local directory or GitHub catalog; `--confirm` installs it. |
| `skills update <catalog> [--confirm]` | Compare with its source; `--confirm` replaces catalog content when changed. |
| `skills remove <catalog> [--confirm]` | Preview removal; `--confirm` removes the catalog and its grants. |

## Grant and value commands

| Command | Control |
|---|---|
| `skills grant <agent> <catalog/skill> [--as <name>]` | Present a skill to an agent, optionally under an alias. |
| `skills revoke <agent> <skill>` | Remove one grant as it stands in that agent. |
| `skills profiles <catalog/skill>` | List configured accounts without revealing values. |
| `skills configure <catalog/skill> [--profile <name>]` | Prompt at the terminal for the values that account needs. |
| `skills forget <catalog/skill> [--profile <name>] [--confirm]` | Preview emptying one account; `--confirm` forgets it. |
| `skills doctor [<agent>]` | Diagnose all grants or one agent's and print exact fixes. |

Prefix every command with `"$RUNDESK_COMMAND"`.

## Safe workflow

1. Run `skills catalogs` and `skills list` before changing the library.
2. Preview catalog install, update, or removal without `--confirm`; repeat with it only after source,
   catalog name, changed files, and affected grants match the request.
3. Grant by full `catalog/skill` address. Use `--as` only to resolve a name collision or present two
   copies under distinct names.
4. Configure values at the owner's terminal, never through chat. A named profile is a separate
   account; no `--profile` means the default account.
5. Run `skills doctor <agent>` after each grant, profile change, catalog update, or credential fix.
   A value set during the current turn reaches the next turn, not the already-running process.

## Catalog and grant behavior

- Install and update may read a local directory or reach GitHub. The catalog source remains the
  source of truth: update replaces installed catalog content, including local edits to that fetched
  copy.
- Removing a catalog also revokes grants pointing into it. Save a backup and inspect the preview.
- The shipped `rundesk` catalog and required `rundesk-skills` catalog cannot be removed. Rundesk
  never replaces or removes the owner's `local` catalog.
- Revoking a skill removes the agent's presentation, not the library copy or stored profiles.
- Every agent granted a skill can reach every configured profile for it. Profiles choose coherent
  account value sets; they are not per-agent access control and never fall back to default values.
- `forget` empties values for only the selected skill account. It requires preview and `--confirm`.
- `doctor` checks granted skills. A library skill that is not granted has no agent context to
  diagnose.

## Create or publish skills

The commands above manage skills that already exist. Use
[Writing skills](../../writing-skills/SKILL.md) to create, revise, review, debug, or publish one; it
routes to its integration and publishing references only when they are needed.

Rundesk has no `skills create`, `skills validate`, or `skills publish` commands.
