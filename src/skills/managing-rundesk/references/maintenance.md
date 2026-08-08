# Agent continuity and workspace maintenance

Read this only when maintenance itself is the task. Ordinary work records newly useful durable
context and removes its own scratch; it does not inventory the whole home.

## Focused pass

1. Read `MEMORY.md` and only the home indexes it links. Inventory home loose files and scratch
   directories without following symlinks. Preserve and list `retros/` if present. Do not open
   files under `retros/`; the next phase owns that evidence.
2. Keep compact owner preferences, durable role and responsibilities, reusable cross-project
   process and gotchas, and small active-project pointers: stable location, purpose, role, and
   authoritative overview.
3. Correct or merge duplicates. Remove a mapping only when it is explicitly marked retired/stale
   or authoritative context confirms that; retain an unavailable active mapping and do not add
   availability status. Remove loops explicitly marked completed/delivered.
4. Remove commands or deliverable paths, working or draft paths, status, report formatting, dates
   or supersession history, and task-only methods from personal memory; keep them in the project.
   An earned shared index may keep a stable entrypoint that avoids repeated discovery. Use one
   purpose-named index such as `PROJECTS.md`, `CLIENTS.md`, or `OPEN_ITEMS.md` only when several
   entries earn it; never one home note per project or all three as boilerplate.
5. Remove each current-task temporary path wherever it is, plus confirmed agent-created obsolete
   clutter. Remove an agent-created scratch directory when left empty. Preserve deliverables,
   project or user files, files of uncertain ownership or value, provider-managed directories,
   symlinks, and their targets.
6. Reread every changed index, verify each removal and retained sentinel, and give one complete
   final report: what changed, what was preserved, what remains uncertain, and how it was checked.

Never infer that age, a missing mount, or an unavailable path makes a file or mapping stale. Never
move project state into home merely to organize it. If safe ownership or obsolescence cannot be
proved, preserve the item and report it.

## Tidy versus cluttered

A tidy home is small, canonical, and useful rather than empty:

```text
home/
  MEMORY.md                 compact first-read map; links to PROJECTS.md
  PROJECTS.md               one maintained index earned by the agent's role
  templates/
    owner-report.md         reusable agent-owned material
```

Project code, current status, and project decisions remain in each external project. A role that
does not need `PROJECTS.md` or `templates/` should not create them merely to match the example.

A cluttered home has signals worth investigating:

```text
home/
  MEMORY.md                 long history, closed loops, changing status
  PROJECTS.md
  projects-new.md           parallel index with overlapping truth
  acorn-copy/               copied project checkout
  report.md
  report-final.md
  report-final-2.md         competing deliverables with no canonical location
  notes.md                  detached context nothing links
  temp-output.txt
  scratch/old-result.txt    abandoned intermediates
```

Similarity to this tree is not deletion authority. Establish which file is canonical, who owns
each item, whether it is still needed, and where project state belongs. Preserve anything uncertain.

## Combined upkeep contract

Use one focused schedule for maintenance, retrospective, and self-improvement rather than competing
sweeps. Workspace and continuity maintenance runs first; the retrospective records the prior week;
the evidence review then starts from clean, verified continuity. The strict phase order and finish
gate are in the [self-improvement reference](self-improvement.md#combined-upkeep-contract).
