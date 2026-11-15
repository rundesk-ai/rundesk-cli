---
name: structuring-project-docs
description: Use when creating, auditing, or converting a repository's documentation home — deciding where the brief, the codemap, the surface reference, requirements, research, and comparison material live, and what each of those files must contain. It supplies one repository documentation layout, a template for every home, and the rules that keep an index level with the tree it describes. Do not use for writing or revising the prose of one page, for product requirement content, or for a repository that already publishes its own documentation template.
---

# Structure a repository's documentation

A repository accumulates documents faster than it accumulates places to put them. Once the same fact
has two homes, both are believed and one is wrong. This skill decides the homes.

It owns **where a document lives and what shape it takes**, and nothing about the prose inside one.
Load the documentation-writing skill alongside it for how a page is written and how its claims are
traced, and the product-requirements skill for how to reason about what the product must do.
Where a repository already publishes its own documentation template, that template wins over this
one; convert to it rather than over it.

## Audit before you create anything

List every documentation-bearing path before proposing a layout: `docs/`, `.ai/`, `.knowledge/`,
`wiki/`, a generated site, loose `PLAN-*.md` and `NOTES.md` at the root, and the agent instruction
files. For each, record what it holds, whether it is committed, and whether anything still reads it.

Then classify each file into exactly one of the homes below. A file that classifies into two is two
files. A file that classifies into none is the interesting case — it is usually one of:

- a plan for work that has not happened, which belongs with the work, not in `docs/`;
- a status report, which ages into a lie and belongs in the tracker or the pull request;
- somebody's private notes, which are not documentation and are not yours to move.

**Never stand up a second documentation home beside a working one.** Convert the existing one, or
leave it alone. Two homes is the failure this skill exists to prevent, and creating one while
migrating away from another produces exactly that state for however long the migration takes.

## Place every document in one home

**Three files sit at the root of `docs/`. Everything else is in a home.** A root that collects
pages stops being an index and becomes the pile it was meant to organize.

```text
docs/
  README.md            the index
  BRIEF.md             what this is, who it serves, what it refuses
  CODEMAP.md           where each layer lives, with counts
  api/                 the published surface, one page per group + an index of every verb
  concepts/            how a subsystem works, and how it fails
  guides/              how to perform one task, start to finish
  extending/           how to write something against a published contract
  requirements/        what must be true, and whether anything proves it
  research/            dated findings about the world outside
  references/          material from elsewhere you are measured against
  assets/<topic>/      images the pages embed
```

Each home carries a `README.md` listing what is in it.

`api/` and `references/` sit next to each other and are constantly confused. The distinction is one
line: **`api/` is the surface you publish; `references/` is material from outside that you compare
yourself against.** A screenshot of a competitor's settings page is a reference. Your own command
list is api.

**Required:** the three root files, `requirements/`, and `research/`. Add `api/` when the repository
publishes a surface somebody else calls. Add `concepts/`, `guides/`, and `extending/` when there is a
page for them.

**Never create an empty home.** A directory holding a placeholder teaches the reader that the layout
is decoration.

Sort a page by what the reader wants:

| They want | Home |
|---|---|
| To look up a verb, endpoint, or field | `api/` |
| To understand how something works, and how it fails | `concepts/` |
| To get one task done | `guides/` |
| To write an adapter, plugin, or catalog against your contract | `extending/` |

**One page per subsystem, and that page is the source of truth for it** — not a summary of a truth
kept elsewhere.

**Split a reference page before it stops being one.** A surface page you scroll rather than search
has failed at its only job. Give each group its own page and keep one index listing every verb on one
line, so completeness stays checkable.

Read [references/layout.md](references/layout.md) for what belongs in each home, material that fits
none of them, and the order to convert an existing tree.

Not every project has every home. A library, a game, a monorepo, and a repository that publishes its
own documentation site each need a different subset. Read
[references/project-shapes.md](references/project-shapes.md) before deciding which homes exist, and
before inventing one the table does not cover.

## Date anything that came from outside

Three kinds of page get filed as each other, and the cost is that a stale one is trusted. Separate
them by what would make each wrong:

- A **topic page** describes this software as it is. It is wrong the moment the product changes.
- A **research note** describes the world outside this repository — a platform's real behavior, how
  somebody else solved a problem, what a previous build learned. It is wrong only when the world
  changes, and it carries the date it was established and what it was true of.
- A **reference** is material from elsewhere this project is measured against, kept in a set with a
  note saying where it came from and what to take from it.

Research is input, never truth. It informs a requirement; it is never the source of record for this
project's own behavior, and a topic page should not cite one for a guarantee.

Read [references/research.md](references/research.md) for both templates, the two rules that make a
research note usable a year later, and why a note is never rewritten when the world moves on.

## Write the orientation pair before the topic pages

`BRIEF.md` and `CODEMAP.md` are read first and read most, by people and by agents. They are the two
files worth writing before anything else, because every later decision about where something goes is
easier once they exist.

Most of a brief is not in the code. Scope and external systems are; who it is for and what it
deliberately refuses are not. **Never infer an audience from a schema** — a plausible invented one is
worse than a blank section, because it is loaded on every future task and nobody re-checks it. Draft
what the repository can prove, mark the rest, and get it confirmed.

A codemap is an inventory, not a tutorial. One section per layer, each listing what exists, with a
count in the heading. **Count artifacts, not lines** — "18 services" survives a refactor and makes
drift obvious; "client.py — 1,205 lines" is stale on the next commit and tells a reader nothing.

Read [references/orientation.md](references/orientation.md) for both templates, where the answers
come from, and the quality bar each has to clear.

## Keep requirements a closed schema

A requirements document asserts what must be true and whether anything proves it. It never explains
how something is built, and it never argues for it. Four headings, that order, nothing else:

```md
---
id: NS
name: <what this contract owns>
last_verified: YYYY-MM-DD
---

## What this is
## Why it exists
## Requirements

|    | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-NS-1 | <one assertion, in the language of the product> | `test_case_name` |
| ❌ | R-NS-2 | <built, but nothing proves it> | src/thing.ext:88 — no test |
| ❌ | R-NS-3 | <nothing exists yet> | — |

## Open questions
```

The glyph is the first column and its header stays empty. A ✅ means a named check was observed to
pass; a source path is not evidence, and neither is a test that exists but was never run. Requirement
IDs are `R-<NS>-<n>`, one namespace per file. **An ID is never reused and never renumbered.**

Withdraw a requirement by deleting its row and leaving the number missing. A gap is information — it
says something was withdrawn — and it costs a reader one question. Closing the gap costs them a
confident wrong answer: renumbering repoints every citation of every ID at or after it, in the other
contracts, in code comments, and in tests that name their requirement, and nothing fails when it
happens. Grep the namespace across the whole repository before withdrawing anything, and if a
citation sits somewhere you cannot change in the same commit, stop and ask.

Read [references/requirements.md](references/requirements.md) for how to word a requirement, where to
put the urge to explain, and how a document that is not a current promise is marked as one.

## Keep each index level with its tree

Every home has a `README.md` that lists what is in it, one row per document, each row saying what
that document answers. `docs/README.md` does the same for the whole set.

An index behind its directory is worse than no index, because a reader who finds nine of your twelve
research notes stops looking for the other three. This is the single most common drift in this
layout: files land, the index does not move, and nothing complains.

- Add the row in the same change that adds the file. Not afterwards.
- Record what a row **is**, never how many of them are green. A count in a summary is stale the day
  after it is written, and unlike a stale row, nobody re-reads a summary to catch it.
- When a page is deleted, delete its row and say so.

## Keep every page scannable

Placing a page well is wasted if the page is a wall. Documentation is read by somebody hunting one
fact, not by somebody starting at the top.

- **Lead with the answer.** The first line of a section is the fact; reasoning comes after.
- **Use a table whenever the content is tabular** — states, flags, fields, exit codes. Prose
  describing six parallel things is six rows badly formatted.
- **One idea per paragraph, one question per heading.** A section past a screen has become two.
- **Cut the run-up, the restatement, the tour, and the hedge.** They are most of the length.
- **Split a page over its budget** rather than trimming it evenly. A long page is usually two pages.

Character is not the enemy of concision. A line carrying both an invariant and the failure it
prevents earns its length; a line carrying only tone does not.

Read [references/page-shape.md](references/page-shape.md) for the budgets, the full cut list, and
worked before-and-after.

## Verify the layout

Nothing here is enforced by a machine unless the repository chooses to enforce it, so the check is
deliberate:

1. List the tree and the indexes side by side. Every file appears in exactly one index; every row
   resolves to a file that exists.
2. Follow every relative link in every changed page.
3. Confirm no home was created empty, and no fact acquired a second home.
4. For each namespace, confirm no ID is duplicated and every ✅ names a check that exists. A
   missing number is a withdrawal, not a defect.
5. Read `BRIEF.md` as somebody who has never seen the repository. If a section reads as invented
   rather than sourced, mark it rather than leaving it level with the rest.
6. Check the longest page against its budget. If it is over, it is usually two pages.
7. Say which of these you did not do.

Read [references/sources.md](references/sources.md) before changing a rule in this package.
