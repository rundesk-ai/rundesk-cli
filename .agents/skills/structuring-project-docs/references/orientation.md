# Write the brief and the codemap

The orientation pair is loaded first and most often — by people arriving at the repository and by
agents starting a task — so both are held to a stricter standard than a topic page: short, current,
and free of anything invented.

Both are committed and world-readable. **No personal names, usernames, emails, phone numbers, or
addresses; no credentials or connection strings; no machine-specific paths.** Refer to people by
role, and to the project by its public name.

## BRIEF.md

One screen. What the project is, who it serves, and what it covers. Not how the code is built — that
is the codemap — and not how to work in it, which is the agent instruction file.

```md
# Brief — <project>

*What this is and why it exists. One screen, stable, and free of private detail.*

## Story

<One short paragraph a stranger understands: the project and the change it creates. A second
identity — a rewrite, a fork, a successor — goes in a clause, not a section.>

## Why it exists

<The problem, who feels it, and why the existing options fall short. When a later decision is
unclear, this is the section that resolves it.>

## Users

- <who uses it, what they are trying to accomplish, and the qualities that matter most to them>

## Scope

- **Covers:** <the product areas, features, or surfaces this project spans>
- **Refuses:** <the tempting scope it deliberately does not take, so the focus survives contact>

## External systems

- `<system>` — <what this project relies on it for>
```

### Where the answers come from

Work down this list and notice where it stops.

1. **The readme, product pages, a landing page** — the story and the pitch, usually already written.
2. **Existing agent instruction files or prior documentation** — these often carry the *why* and the
   refusals, which are the hardest parts to recover.
3. **Issues, milestones, a roadmap** — what is in scope now as against later.
4. **The code** — confirms *scope* and *external systems*: what it integrates with, what surfaces
   exist. It is evidence of what was built. It is never evidence of who it is for or why.

Then stop and ask. **Users and the refusals are owner knowledge.** A repository cannot tell you who
somebody sells to or what they decided not to build.

**Never infer an audience from a schema.** A plausible invented one is worse than a blank section,
because it is loaded on every future task, it reads exactly as confidently as a sourced one, and
nobody re-checks it. When converting an existing brief, list which sections are sourced and which are
inferred, and get the inferred ones confirmed before calling the work done.

### The bar

- Skimmable — short bullets, one idea per line, about one screen.
- No placeholder survives. Delete a section rather than writing "none".
- The shape is the same for any project. Adjust the words, not the headings.
- Change it when the project changed, not to reword it.

## CODEMAP.md

A structural inventory — the table of contents of a codebase. It answers "where does this kind of
thing live, and what exists?" layer by layer, so a reader can navigate without grepping first. It is
not a tutorial, not a set of conventions, and not a place for gotchas.

### Building one

Survey the repository systematically, not from memory.

1. **Identify the layers before opening any source file.** The dependency manifest, the entry points,
   the routing or wiring configuration, the test directory layout, and the build scripts name the
   layers in minutes. The folder tree alone will mislead you on any repository that does not follow
   its framework's defaults.
2. **Survey each layer** folder by folder, listing every artifact with a one-line purpose and its key
   relationships.
3. **Count what you inventory**, and put the count in the heading. Counts show completeness and make
   drift obvious the moment they stop matching.
4. **Compress** to names and terse notes. Aim for under about 200 lines. Density over prose.

**Count artifacts, not lines.** "5 modules", "77 commands", "201 tests" survive a refactor.
"client.py — 1,205 lines" is stale on the next commit and tells a reader nothing they can use.

### Sections are per-layer maps

There is no fixed section list, because the shape follows the code. One section per real layer, each
listing what exists; delete any section with nothing in it.

- A web application maps as its framework's layers — models, services, controllers, routes, jobs,
  pages, components.
- A command-line program maps as entry point, command modules, domain packages, shared utilities,
  adapters, templates, tests.
- A game or native project maps as build targets, scenes or entities, systems, assets, tests.

**A monorepo still maps by layer, not by application.** Sections span the workspaces — *Entry points
(3 — one per app)* — with the workspace named in each entry. A section per application duplicates
every layer and buries the thing a reader actually wants, which is where a *kind* of thing lives.

### Entry format

- Group by folder, with the count in the heading: `## Services (app/Services/ — 18)`.
- One line per artifact: name — terse purpose — key relationships.
- A table for dense relational layers; bullets for flat lists.
- Point at the source of truth rather than copying it. Never copy a credential or a real value;
  name the configuration file instead.

### Keeping it true

Refresh on drift, not on a timer. When a change adds or removes a layer or shifts a count, update
those sections and only those. A count that no longer matches the repository is the first visible
sign of staleness, which is most of why the counts are there. Record removals too.
