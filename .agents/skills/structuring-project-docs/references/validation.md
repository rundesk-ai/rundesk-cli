# Structuring Project Docs Validation

This is the current validation record for `structuring-project-docs`; the repository-wide method is
in [Validating Skills](../../../docs/guides/validation.md).

Two runs were observed on 2026-08-25 against a fixture whose documentation was split across three
homes — an `.ai/` orientation trio, a `docs/` directory holding both a surface reference and a survey
of other projects, and a plan file at the root — with source modules that are signatures and
docstrings over empty bodies. Cases those runs exercised carry a result; every other case remains
unrun, and no Codex run has happened at all.

## Boundary under test

The skill should activate when the question is **where a document belongs and what shape it takes**:
setting up a documentation home in a repository that has none, auditing one that has drifted,
converting one system to another, deciding which of several directories a file belongs in, or fixing
an index that no longer matches its directory.

It should not activate for writing or revising the prose of one page, for reasoning about what a
product must do, or for planning work that has not happened.

The dividing question is what a wrong answer costs. A badly written page is one bad page. A badly
placed page creates a second home for a fact, and from then on both homes are believed and one is
wrong.

## Trigger and exclusion cases

| ID | Request shape | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| SPD-T01 | This repository has no docs directory — set one up | Load | – | – |
| SPD-T02 | Our documentation is scattered across three places, sort it out | Load | ✅ | – |
| SPD-T03 | Where should this note about a competitor's pricing page go? | Load | – | – |
| SPD-T04 | The research index does not list half the notes | Load | – | – |
| SPD-T05 | Convert this project off its old documentation system | Load | – | – |
| SPD-T06 | Write the gateway page — explain how it fails | Do not load alone; page prose, not placement | ✅ | – |
| SPD-T07 | What should the product do about expired invites? | Do not load; product requirement content | – | – |
| SPD-T08 | Write the implementation plan for the new adapter | Do not load; work not yet done | – | – |
| SPD-T09 | This repository already has a documented docs template | Load, then defer to that template rather than replacing it | – | – |

## Placement cases

| ID | Situation | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| SPD-P01 | A file classifies into two homes | Split it into two files rather than picking the closer home | – | – |
| SPD-P02 | A dated log of a validation run | Keep it out of `docs/`; a research note only if it established something reusable | – | – |
| SPD-P03 | A plan for unbuilt work is found in `docs/` | Move it to the work, not to another documentation home | – | – |
| SPD-P04 | Asked to create the layout while the old system stays in place | Refuse the two-homes state; convert, or leave the old one alone | – | – |
| SPD-P05 | A repository with no published surface | Omit `api/` rather than creating it empty | – | – |
| SPD-P06 | A narrative guide to building against a published contract | Topic page, with the enumerable surface split into `api/` and linked | – | – |
| SPD-P07 | Material fits no home and seems to need a new one | Raise it rather than adding a directory without a rule | – | – |
| SPD-P08 | Moving the surface reference breaks links from outside the repository | Name the break as a cost and get it decided, rather than discovering it after | – | – |

## Orientation cases

| ID | Situation | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| SPD-O01 | The brief needs a Users section and the repository is a library with no stated audience | Mark it unsourced and ask; never infer an audience from the schema or the API | ✅ | – |
| SPD-O02 | Asked to write a codemap for an unfamiliar stack | Read the manifest, entry points, wiring, test layout, and build scripts before the folder tree | ✅ | – |
| SPD-O03 | A codemap entry describes a large file | Count artifacts, not lines | ✅ | – |
| SPD-O04 | A monorepo with four applications | One section per layer spanning the workspaces, not one section per application | – | – |
| SPD-O05 | A brief section has nothing to say | Delete the section rather than writing "none" | – | – |
| SPD-O06 | Source material contains a maintainer's name and a local path | Refer to the role; keep the path out of a committed file | – | – |

## Requirements cases

| ID | Situation | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| SPD-R01 | A requirement row cites `src/thing.ext:88` as its evidence | ❌ — a source path is not evidence | – | – |
| SPD-R02 | A requirement row cites a test that exists but was not run | ❌ — an unrun test is not an observed check | ✅ | – |
| SPD-R03 | A behavior is half implemented | Two rows, not a third glyph or a hedged one | – | – |
| SPD-R04 | Asked to delete requirement 7 of a namespace of twelve | Grep the whole repository for citations first; stop and ask if one cannot be updated in the same change | – | – |
| SPD-R05 | A requirement names a class and a method | Reword in product terms; the design belongs in the topic page | – | – |
| SPD-R06 | A requirement contains a semicolon | Split it; it is two requirements | – | – |
| SPD-R07 | Predecessor requirements that bind nothing today | Mark it in the index gloss, not by inventing a status field per file | – | – |
| SPD-R08 | The document grows while the row count does not | Recognize prose displacing requirements and route each part to its home | – | – |

## Index cases

| ID | Situation | Expected behavior | Claude | Codex |
|---|---|---|---|---|
| SPD-I01 | A page is added | The index row lands in the same change, not afterwards | – | – |
| SPD-I02 | Asked to add "12 of 18 requirements proven" to an index | Refuse the count in a summary; it belongs in the rows that own it | – | – |
| SPD-I03 | A page is deleted | Remove its row and say so | – | – |
| SPD-I04 | An index row points at a file that no longer exists | Report it rather than silently repairing the row to something plausible | – | – |

### What those runs observed

The placement run loaded this package first from a request that never named a layout, then loaded the
documentation-writing package second **because this one's body tells it to** — the routing between
the two held without being prompted. It read four of the five operational references. The near-miss
run declined to load this package at all and quoted the description's exclusion for one page's prose
back as its reason, so the boundary is doing work in both directions.

The placement run's judgment calls were the useful part. It routed the retired memory file's one
undated claim into an open question rather than inventing a topic page for it; left the unstarted
plan at the root and recorded that decision in the index so nobody re-files it later; and awarded no
✅ anywhere, stating that an empty test body is not an observed check even if running it would pass.
Asked for a brief's audience with only the word "developers" available, it marked the section
unconfirmed instead of filling it. It declined to invent a date for a research note that said only
"in March", left the filename without its date prefix, and recorded in the index that the file gets
renamed once the owner supplies one.

Three findings the cases did not anticipate:

- **`references/` and `assets/` were omitted rather than created empty**, unprompted. The empty-home
  rule reads clearly enough to be applied without a case covering it.
- **The run flagged that it could not tell whether this layout governs that repository at all**,
  since the fixture had no instruction file and the surrounding workspace convention uses `.ai/`. It
  converted, and said the conversion should run the other way if the owner's convention wins. That is
  the correct handling of SPD-T09 arrived at from the opposite direction.
- **It read `references/validation.md`** — this record — by listing the directory, despite nothing
  routing it there. The catalog's rule that validation records are maintainer artifacts is enforced
  only by not linking them, and not linking does not stop a directory listing. That applies to every
  package here, not only this one.

The two-homes window was reported honestly rather than claimed clean: the conversion and the old
home's removal happened inside one shell invocation, so both trees existed for part of it. The
package tells you to retire the old home in its own change, which a fixture with no version control
cannot do.

## What the first conversion established

The layout was carried through a mature documentation tree on 2026-08-25 — an index, thirteen topic
pages, a published surface, ten requirement contracts and thirty-three research notes. The layout,
the homes, the index discipline and the closed schema all held. Two rules in this package did not,
and both have been corrected here rather than defended:

- **The unbroken-numbering rule was actively dangerous.** Four requirement numbers were missing in
  that tree, and its requirement IDs are cited from shipped source and test docstrings. Closing the
  gaps would have repointed every citation at or after each gap at a different requirement, silently.
  The rule now forbids renumbering and treats a gap as a withdrawal.
- **The 25-word ceiling did not survive contact.** Fifty-seven of 161 rows exceeded it, including six
  in that repository's best-evidenced contract, one of them 97 words. Rewording contracts to satisfy
  a count risks changing what they promise. Length is now a smell rather than a limit.

Two placement judgments the cases did not anticipate also came up and were resolved the way the
package would want: 288 lines inside one requirements file were describing how a subsystem works
rather than asserting anything, and became a topic page; and evidence was recovered by finding which
tests cite each requirement ID and running them, rather than by trusting the prose already in the
evidence column.

## Next validation

Run every case in fresh supported provider sessions, with and without the package installed, using
ordinary requests that never name the boundary under test. Use a real repository with an existing,
partly drifted documentation tree rather than a clean fixture, since almost every rule here concerns
conversion and drift rather than a blank start.

Establish the tree's true state independently first — the file list, the index contents, and which
claims have observed evidence — so a correct answer can be told apart from a plausible one. Record
activation, whether a second documentation home was ever created, whether unsourced brief sections
were marked rather than filled, and whether any ✅ was awarded to a path or an unrun test.

The most valuable single run is a full conversion of a mature tree, because that is the limit named
in [sources.md](sources.md): the conversion order has been reasoned, not observed.
