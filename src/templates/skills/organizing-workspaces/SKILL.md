---
name: organizing-workspaces
description: Organize and clean agent workspaces without storing project repositories there. Use for workspace cleanup, continuity audits, recurring agent-home maintenance, file placement, stale artifacts, worktrees, clutter, or indexes.
---

# Organizing workspaces

Keep the workspace small, current, and easy for another agent to navigate. Organize around how
work is used, not around a universal folder template.

## Keep project repositories outside the workspace

The agent workspace is for coordination: plans, working notes, indexes, and durable references. It
is not a project directory.

- Do not clone a project, initialize Git, create a Git worktree, or copy a source tree into the
  agent workspace.
- Work in the project's established repository outside the workspace. Keep project-owned source,
  tests, documentation, configuration, generated output, and Git metadata with that project.
- Store a link or path to the canonical project instead of a convenience copy. If several projects
  need routing, maintain one lightweight index such as `ORGANIZATION.md`.
- If a repository or worktree already exists inside the workspace, inspect its remote, status,
  uncommitted work, unpushed commits, and references before proposing relocation. Never move it as
  ordinary clutter.

## Organize by lifecycle

Classify an artifact by what happens next:

| Lifecycle | Treatment |
| --- | --- |
| Active work | Keep it in the established process home, with a name that says what it is. |
| Durable reference | Give it one canonical home and link to it from the places that need it. |
| Completed record | Keep it only when history, audit, or future work needs it; otherwise clean it up. |
| Generated or temporary output | Put it in an existing ignored or temporary location and remove it when the task ends. |
| Unknown | Inspect its contents and references before moving or deleting it. |

Use existing conventions first. Create a folder or index only after repeated work needs a shared
home; do not make empty `clients/`, `projects/`, `notes/`, `inbox/`, or `archive/` scaffolding.
Keep nesting shallow and use stable names instead of `misc`, `stuff`, `new`, `final`, or version
chains such as `final-v2`.

Common routing defaults:

- Implementation plans go in `plans/`.
- Project truth stays in the project repository or its established tracker or documentation.
- Cross-project references, client or people mappings, and process entry points may share one
  compact workspace index. Link to authoritative systems rather than copying their contents.
- Short-lived outcomes go in an existing dated log when one exists.
- `MEMORY.md` holds only durable learned facts that change future action, or a minimal pointer to
  the canonical workspace reference. It is not a file index, project notebook, or status log.
- `AGENTS.md` holds stable operating rules and mandatory entry points, not inventories or current
  work. Changing it changes agent behavior, so obtain authorization unless the request includes it.

## Clean continuously

Inspect the workspace when finishing substantial work and when clutter obstructs navigation.
Identify:

- temporary exports, generated files, abandoned drafts, and empty directories;
- superseded notes or indexes that duplicate a canonical source;
- completed artifacts whose required outcome already lives elsewhere;
- stale project checkouts or Git worktrees, especially any stored inside the workspace.

Prove why something is stale. Age alone is not evidence. Compare suspected duplicates by content,
check inbound references, and identify the canonical copy. Prefer recoverable cleanup such as trash
when available.

Before destructive or difficult-to-reverse cleanup, identify whether a Rundesk backup contains the
target. For agent-home or workspace data, read and follow `managing-backups`. Take and verify the new backup
before cleanup. For excluded project or external material, establish its own recovery path. A backup
does not authorize cleanup or make an uncertain target safe to remove.

Moving, renaming, archiving, deleting, or overwriting existing material can erase context or break
links. When cleanup was not explicitly requested, list the exact proposed paths and obtain
authorization. When it was requested, keep the cleanup within the named scope and report exactly
what changed.

## Retire Git worktrees safely

Treat a worktree as repository state, not as an ordinary directory:

1. Find the owning repository and inspect `git worktree list --porcelain`.
2. Check the candidate worktree's status, branch, commits not present upstream, and any files that
   are ignored or untracked.
3. Confirm its work is merged, preserved elsewhere, or explicitly abandoned.
4. Use `git worktree remove <exact-path>` from the owning repository. Do not delete the directory
   directly or use a force flag to bypass unresolved work.
5. Treat deleting the associated branch as a separate action; do it only when explicitly included.
6. Re-run the worktree list and confirm the retained worktrees still resolve.

If any status, ownership, or merge state is uncertain, preserve the worktree and report what needs
confirmation.

## Verify the result

- Start from the workspace's normal entry point and confirm a new agent can find active processes
  and canonical references without guessing.
- Confirm the workspace contains no project repository, `.git` directory, or project worktree.
- Confirm each durable fact or artifact has one canonical home and every convenience reference
  points there.
- Confirm temporary output and verified stale material were removed or reported for cleanup.
- Confirm plans remain under `plans/` and project-owned files remain with their projects.
- Confirm no unrelated owner work, governing instruction, or uncertain artifact was disturbed.
- Report what was organized, what was cleaned up, and what was intentionally retained.
