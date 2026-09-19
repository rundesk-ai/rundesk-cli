# Assert what must be true, and whether anything proves it

A requirements document holds exactly that, and nothing else. It does not explain how the thing is
built, argue for the design, or narrate what happened. The schema is closed so a reader can tell at a
glance whether a promise is kept, and so a document cannot grow into an essay while the promises
underneath it stay unproven.

## The template

```md
---
id: NS
name: <what this contract owns>
last_verified: YYYY-MM-DD
---

## What this is

<At most three sentences, in the domain's own terms. What the thing is, not how it works.>

## Why it exists

<The reason these requirements are worth holding. Short.>

## Requirements

|    | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-NS-1 | <one assertion, in the language of the product> | `test_case_name` |
| ❌ | R-NS-2 | <built, but nothing proves it> | src/thing.ext:88 — no test |
| ❌ | R-NS-3 | <nothing exists yet> | — |

## Open questions

<One line each. What is undecided, and what would settle it.>
```

Four `##` headings, that order, nothing else. `last_verified` is present when at least one row is
✅, and it records when that evidence was last observed — not when the file was last edited.

## Wording a requirement

One assertion, present tense, in the language of the product rather than the code. Keep it short
enough to hold in one thought — but length is a smell, not a limit. A long requirement that names one
condition is fine; a short one hiding two is not, and rewording an existing contract to hit a word
count risks changing what it promises.

- **No implementation symbols.** A requirement that names a class or a function is describing a
  design, and it will be wrong after the next refactor while still reading as true.
- **No semicolons.** A semicolon in a requirement is almost always two requirements.
- **No numeric literals** where the number is a tunable. Name the setting; the value belongs where it
  is configured, and a requirement that hard-codes it makes an ordinary change a contract change.
- **One layer.** If a requirement is only meaningful when two things interact, it belongs to the
  higher of the two, cited by both — never written twice.

```text
Bad:   R-CH-4  The ChannelHost calls _reconcile() every 30s; if the adapter is gone it respawns it.
Good:  R-CH-4  A channel that goes offline is retried, and an adapter that stays gone is replaced.
```

## The glyph column, and what earns a ✅

The glyph is the first column and its header stays empty.

- **✅** — a named check was observed to pass. The evidence cell names it.
- **❌** — everything else, whether the behavior is unbuilt, built and untested, or tested by
  something nobody has run.

A source path is not evidence. **A test that exists is not evidence either** — the claim is that it
was observed to pass, and a suite nobody watched proves nothing. Where a check cannot be run, the row
stays ❌ with the reason in the evidence cell. A visible gap is safe; a ✅ that has quietly stopped
being true is the failure this column exists to prevent.

There is no third glyph. "Partly" is two rows.

## Identifiers

`R-<NS>-<n>`. The namespace is declared once, in the frontmatter `id:`.

- **One namespace per file, one file per namespace.** A second namespace means a second file, and so
  does a table much past fifteen rows.
- **An ID is never reused and never renumbered.** Withdraw a requirement by deleting its row and
  leaving the number missing. A gap records a withdrawal; it does not need closing.
- **A contract holds what is true now**, so a withdrawn requirement is erased rather than kept as
  struck history. Git has the history.
- **Renumbering is the thing to refuse.** Erase `R-THING-7`, close the gap, and the old `R-THING-8`
  becomes `R-THING-7`; every reference to either now points somewhere new, in the other contracts, in
  code comments, and in tests that name their requirement. Nothing warns you — the ID still resolves
  and the reader gets a confident wrong answer. Leaving the gap costs one question and no wrong
  answers. Grep the namespace across the repository before withdrawing anything, and if a citation is
  somewhere you cannot change in the same commit, stop and ask.
- **Never compound an ID.** `R-A-2 / R-B-2` is not a requirement, it is two requirements or one that
  belongs a layer up.

## Where the urge to write something else goes

If the file grows while the row count does not, you are writing prose instead of requirements.

| The urge | Where it goes |
|---|---|
| Explain how it is built | The topic page for that subsystem |
| Justify why it is built that way | `## Why it exists`, in one or two sentences |
| Say it is not built, or not proven | The ❌ already says it |
| The requirement belongs in another file | Move it. That is a decision to raise, not a row to write |
| It is undecided, so the requirement cannot be written | `## Open questions`, one line |
| Record what the tests do not cover | A ❌ on the row they do not prove |
| Restate a rule another document owns | Cite its ID |
| Record a value or a tunable | Cite where it is configured |

If none of those fit, you are about to write something with no home. Raise it rather than writing it.

## Documents that are not current promises

A repository being rebuilt often carries requirements from its predecessor: real, useful, and not
promises this build is making. The schema has no status field, and adding one per file invites a
vocabulary nobody maintains.

Mark it in one place instead — the `docs/requirements/README.md` row, whose gloss says plainly that
the document records the previous build's intent and binds nothing. A predecessor document whose rows
are all ❌ is honest as it stands. One nobody is going to revisit should be deleted; it is in the
history, and a directory of contracts that are not contracts teaches readers to discount the ones
that are.
