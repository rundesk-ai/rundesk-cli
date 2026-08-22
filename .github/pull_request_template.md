## Summary

<!-- State what changes and why in one or two lines. -->

-

<!-- State the affected user or system, the current behavior, and why it is insufficient. -->

**Evidence:**

- <!-- Issue, observed result, ratified requirement, request, or measurement. -->

<!-- For a bug, add: **Root cause:** <responsible mechanism>. -->

**Issue linkage:**

<!-- Use one standalone `Closes #<number>.` line per issue this PR completes. Use `Refs` for partial work. -->

## Scope and compatibility

- Areas changed:
- User-visible behavior:
- Preserved behavior:
- Implementation choices and deliberate scope boundaries:
- Dependencies added: none
- Persisted-state or shipped-migration changes: none
- Install, update, removal, or copy-lifecycle changes: none

## Critical risk

<!-- Required for auth, permissions, migrations, data loss, privacy, billing, deployment, or other critical risk. Write "None" when no critical risk applies. -->

- Risk:
- Blast radius and guard:

## Validation

- [ ] `python3 scripts/suites` passes on a current Python.
- [ ] `/usr/bin/python3 scripts/suites` passes on the Python 3.9 floor.
- [ ] `ruff check src tests scripts/suites rundesk`
- [ ] The focused documentation gate passes for a README-only change, or the change is not README-only.
- [ ] Required install and uninstall checks ran with isolated disposable `RUNDESK_HOME` and `--bin-dir`, or the change does not affect those paths.
- [ ] Every new guarantee has a ratified requirement, a cited regression test observed failing without the implementation, and current documentation, or no guarantee was added.
- [ ] `git diff --check`
- [ ] Required GitHub checks pass for the exact head commit.

```text
# Exact focused, full-gate, and manual verification commands with observed results
```

<!-- Leave a box unchecked when its claim is not proven. Explain every unchecked or not-applicable item. -->

## Repository gates

- [ ] The diff contains no credential, private URL, customer data, owner-specific path, debug output, or unrelated artifact.
- [ ] Runtime code remains Python 3.9+ and standard-library only; no dependency was added without owner approval.
- [ ] Commands report only earned outcomes and expose no operation that is not implemented.
- [ ] Layer direction remains `commands` → `lifecycle` → `core` → `utils`; `utils` remains product-agnostic.
- [ ] Network behavior remains injected and every test remains offline.
- [ ] `docs/` remains true, including the complete operation list in `docs/commands.md`.
- [ ] Persisted-state, shipped-migration, deletion, and `AGENTS.md` approval gates were honored.
- [ ] The live `~/.rundesk` install is exactly as it was before validation.

## Release

- Version: `<before>` → `<after>`
- SemVer reason:
- Release or follow-up required after merge:

## Manual user path

<!-- Give the shortest representative checkout command, isolated environment, input, and observed result. Include a material refusal or failure path when behavior changed. -->

```text

```

## Agent

<!-- Replace the placeholder with the filing agent's display name. Do not add provider, model, tool, session, or generated-by branding. -->

🤖 by <Agent>
