---
name: organizing-workspaces
description: Organize and tidy agent workspaces, project files, and lightweight maps of clients, organizations, people, projects, and their relationships. Use when a workspace is cluttered or hard to navigate, when deciding where plans or notes belong, when creating or repairing an index or directory structure, or when recurring work needs a clear canonical home—even if nobody explicitly asks for “organization.”
---

# Organizing workspaces

Make the smallest structure that lets a new agent find the right source quickly. Preserve the
workspace's existing conventions unless they are the cause of the problem.

## Inspect before organizing

1. Establish the exact workspace or project root in scope. Do not clean a broader parent directory.
2. Read its governing instructions and existing indexes, manifests, knowledge files, and maps.
3. Inventory the top-level tree and the specific clutter in question. In a repository, inspect its
   current changes so unrelated work remains untouched.
4. Identify the authoritative source for each kind of information. Distinguish it from generated
   files, temporary artifacts, caches, exports, and convenience copies.
5. State the proposed structure and exact moves before any cleanup that could break links or history.

## Route information by purpose

Use this routing order. An existing authoritative system or explicit local convention wins over
these defaults.

| Information | Canonical home | Rule |
| --- | --- | --- |
| Implementation plan | `plans/` in the agent workspace | Keep active and completed plans here according to the workspace's plan conventions. Do not scatter plan files through entity folders. |
| Project-owned technical truth | That project's repository, documentation, or knowledge system | Link to it; do not copy it into the agent workspace. |
| Client, organization, person, and project routing | `ORGANIZATION.md` in the agent workspace | Keep this a compact map to canonical records and relationships, not a second CRM. |
| Recurring context about one entity | An existing entity record, or a substantive file such as `clients/<key>.md`, `organizations/<key>.md`, `people/<key>.md`, or `projects/<key>.md` | Create a category only when multiple records or repeated use justify it. Link the record from `ORGANIZATION.md`. |
| Cross-project or client working notes | The relevant entity file or an existing notes system | Date time-sensitive entries and link to the project, meeting, tracker, or source. |
| Short-lived outcomes and carry-forward | The workspace's dated log, such as `daily/YYYY-MM-DD.md`, when one exists | Do not promote transient status into durable memory. |
| Durable learned fact that changes future action | `MEMORY.md` | Store only the minimum load-bearing fact or routing pointer; follow the file's own contract. |
| Stable rule or mandatory entry point that applies on every relevant turn | `AGENTS.md` | Add only with authorization. Rules belong here; entity facts, inventories, and current status do not. |

`MEMORY.md` is not a general index. Do not duplicate client rosters, contact details, project notes,
relationship tables, or volatile status there. A concise pointer such as “Consult
`ORGANIZATION.md` before client work” may qualify when forgetting it would change future behavior.

`AGENTS.md` is not a knowledge base. Use it only for stable operating constraints or required
entry points. Put project-specific instructions in that project's own instructions rather than the
agent-wide file. Editing governing instructions changes agent behavior: propose the exact change and
obtain authorization unless the request explicitly includes it.

If a workspace has one clear project and its existing documentation is easy to navigate, add no new
organization system. If several entities or roots need navigation, create one `ORGANIZATION.md` as
the routing index. Do not create `clients/`, `people/`, `projects/`, `notes/`, `inbox/`, or `archive/`
as empty scaffolding.

## Build a routing map

Use stable keys and only the sections the workspace needs. Prefer one directory table plus explicit
relationships; link to detailed records instead of repeating them.

```markdown
# Organization

## Directory
| Key | Type | Name | Canonical record | Aliases | Status |
| --- | --- | --- | --- | --- | --- |

## Relationships
| From | Relationship | To | Evidence or source | Status |
| --- | --- | --- | --- | --- |
```

- Keep people, organizations, clients, and projects as distinct entities. A client may be an
  organization, but `client` describes a relationship; do not collapse every organization into one.
- Reuse established identifiers. Record aliases explicitly instead of silently renaming an entity.
- Record only verified relationships. Mark uncertain rows `Unconfirmed`; never infer an employer,
  owner, client, or personal relationship from a filename, proximity, or similar name.
- Treat the map as navigation, not storage. A canonical record can be a repository, tracker, CRM,
  protected contact system, or substantive local entity file.
- Store the minimum useful identity and relationship context. Do not copy credentials, private
  conversations, sensitive personal data, or protected-system fields.
- Use relative links for local files and stable identifiers for remote systems. Do not link to
  ephemeral searches or temporary exports.
- Add status only when it changes routing, such as `active`, `paused`, `archived`, or `unconfirmed`.

When a local entity file is justified, keep it compact:

```markdown
# <Name>

- Key: `<stable-key>`
- Type: client | organization | person | project
- Canonical sources: <links>
- Related entities: <links or keys>

## Durable context

## Open questions
```

Do not turn an entity file into a meeting transcript, task tracker, or copy of project documentation.

## Keep the structure minimal

- Extend an existing documentation or knowledge system before adding another one.
- Split an index only when it is difficult to scan, distinct owners maintain separate sections, or
  part of it has a genuinely different lifecycle.
- Give every durable fact one canonical home and link to it elsewhere.
- Keep nesting shallow. Durable workspace information should normally be reachable within two
  directories from the workspace root.
- Use stable, descriptive names. Avoid `misc`, `stuff`, `new`, `final`, and version chains such as
  `final-v2`.
- Keep task state in the established tracker or log. Keep generated and temporary artifacts in an
  existing ignored or temporary location.
- Do not relocate an existing project merely to make the workspace tree look uniform. A routing link
  is often safer and clearer than moving a repository.

## Tidy safely

Safe cleanup includes fixing links, consolidating duplicate navigation, and placing newly created
artifacts correctly. Moving, renaming, archiving, deleting, or overwriting existing material can
break references or erase context: list the exact affected paths and obtain authorization unless the
request explicitly authorized that operation.

For suspected duplicates, compare contents and identify the canonical copy. Do not delete a file
merely because its name matches another. For stale files, prove why they are stale and propose a
destination or removal; age alone is not evidence. Preserve uncertain mappings as `Unconfirmed`
rather than forcing them into a neat but invented hierarchy.

## Verify the result

- Start at the workspace's normal entry point and confirm every changed link resolves.
- Confirm each durable fact has one canonical home and convenience references point there.
- Confirm plans remain under `plans/`, project-owned truth remains with its project, and
  `MEMORY.md` and `AGENTS.md` contain no duplicated entity data.
- Confirm existing user changes, runtime data, and project instructions were not disturbed.
- Confirm the tree is simpler: fewer ambiguous homes, no empty scaffolding, and no new category a
  reader must guess between.
- Confirm uncertain relationships remain explicitly `Unconfirmed`.
- Report what was created or reorganized, what remains intentionally untouched, and what still needs
  an owner to confirm.
