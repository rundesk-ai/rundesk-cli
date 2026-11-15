# Place every document in exactly one home

Use this reference when classifying an existing tree, when a file appears to fit no home, or when
converting a repository that already carries a documentation system.

## What each home holds

| Home | Holds | The question it answers |
|---|---|---|
| `README.md` | the index over everything below | what is written down here, and where |
| `BRIEF.md` | the project itself | what is this, who is it for, what does it refuse |
| `CODEMAP.md` | the structural inventory | where does each kind of thing live |
| `api/` | the published surface | what can a caller invoke, and what is guaranteed |
| `concepts/` | one subsystem each | how does this work, and how does it fail |
| `guides/` | one task each | how do I do this, start to finish |
| `extending/` | one contract each | how do I write one of these against your seam |
| `requirements/` | contracts and their evidence | what must be true, and does anything prove it |
| `research/` | dated external findings | what is true outside here, and when was that established |
| `references/` | comparison material | what are we measured against |
| `assets/` | images the pages embed | — |

Only `README.md`, `BRIEF.md`, and `CODEMAP.md` sit at the root of `docs/`.

## Concepts carry the weight

Most of a mature tree is `concepts/`, and it is where the layout succeeds or fails.

- **One page per subsystem**, named for the thing a reader is hunting. `gateways.md`, not
  `architecture-overview.md`.
- **The page is the source of truth for its subsystem** — not a summary of a truth held elsewhere.
  A fact in two places means one is wrong and no reader knows which.
- **A page appears when the thing it describes works**, not when it is planned. A document written
  ahead of its feature cannot be checked, and teaches readers to distrust the rest.
- **Say how it fails, and every state it can get stuck in.** That is what readers arrive for, and
  what is usually missing.

A guide is a task with an end: numbered steps, the expected observation after each meaningful one,
then the failures and how to get out of them. An `extending/` page is a guide whose reader is
building against your contract, so it carries the contract's bounds and refusals as well as the
steps.

## `api/` is reference, not explanation

`api/` holds the enumerable surface and its guarantees: every verb or endpoint, its arguments, its
outputs, its errors, its exit behavior. Dense, factual, complete — a reader looks something up here
rather than reading it through.

Narrative belongs in a topic page even when it describes a published contract. A page that teaches
somebody to *build against* an interface is a topic page; the list of what the interface offers is
`api/`. When a contract has both, split them and link, rather than burying the lookup inside the
tutorial.

Where the surface is small, `api/` holds one page. Where it is large, one page per group, with
`api/README.md` naming them.

## Material that fits no home

This is the useful part of the audit, because the reflex is to invent a home for it.

| What you found | Where it goes |
|---|---|
| A plan for work not yet done | With the work — the issue, the pull request, the branch. Not `docs/`. |
| A status report or progress log | The tracker. It ages into a lie in place. |
| "How we decided this" | The requirement's `## Why it exists`, or the research note that fed it. |
| A dated run log of a test or validation | The pull request, or a research note if it established something reusable. |
| Somebody's private working notes | Leave them. They are not documentation and not yours to move. |
| A rule about how to work in this repository | The agent instruction file, not `docs/`. |
| The same fact you already wrote somewhere else | Delete one. Cite the other. |

If none of those fit and it still seems to belong, that is a signal the layout is missing a home for
this project. Raise it rather than quietly adding a directory — a home added without a rule is a home
nobody else will use correctly.

## Converting an existing tree

Order matters, because the middle of a conversion is the two-homes state this layout exists to
prevent. Keep that window short and never ship in it.

1. **Audit and classify** every documentation-bearing path first, on paper. Do not move anything yet.
2. **Write `BRIEF.md` and `CODEMAP.md`.** They are cheap, they are read most, and writing them
   settles arguments about where the rest goes.
3. **Move the surface reference** into `api/`. Fix every internal link in the same change: the
   readme, the contributing guide, the agent instruction files, the pull-request template, and any
   test that asserts on a documentation path. Moving a page that is linked from outside the
   repository breaks those links permanently — decide that deliberately rather than discovering it.
4. **Reconcile the indexes** against what is actually on disk. This is where an old system's drift
   becomes visible; expect the count to be wrong.
5. **Normalize requirements last.** It is the only step that needs a judgment per row, and it will
   stall if it is attempted first.
6. **Retire the old home in its own change**, once nothing reads it. Deleting it in the same commit
   as the conversion makes the diff unreviewable.

An old system usually leaves a versioned payload behind — shipped standards files, a linter, a
version stamp, an integrity manifest. None of that survives into this layout. The standards live in
this skill; a repository that wants a machine check writes one against its own tree, in its own test
suite, where it fails for reasons its authors can act on.
