# Keep a page scannable

A correct page still fails if a reader has to read it all to find one fact. Most documentation is too
long, and the length is rarely the content — it is the run-up.

## Lead with the answer

The first line of a section is the fact. Reasoning, history, and the incident that taught it come
after, if at all.

```text
Bad:   It is worth understanding why gateways behave this way. Historically the build this
       replaces asked a file whether a gateway was alive, which turned out to be unreliable
       because a file survives the process that wrote it, and so the answer was often wrong.
       For that reason liveness is now asked of the kernel.
Good:  Liveness is asked of the kernel. No file decides it — a file outlives the process that
       wrote it, and the previous build shipped that bug.
```

## Budgets

Treat these as a smell, not a gate. A page past its budget usually contains two pages.

| Page | Budget |
|---|---|
| Orientation — brief, codemap | one screen; codemap under ~200 lines |
| Concept | under ~250 lines |
| Guide | under ~200 lines |
| One reference group | under ~300 lines |
| Home index | one row per page |

## Cut these on sight

- **The run-up.** "Before we look at X, it is worth noting…" Delete to the first fact.
- **The restatement.** A section that says what the previous section said, in other words.
- **The tour.** Narrating what the reader is about to read. The headings already do it.
- **The hedge.** "generally", "typically", "should usually". State it, or mark it unverified.
- **The aside.** A clause about something else, set off by dashes, that the sentence does not need.
- **Two examples that make one point.** Keep the better one.
- **The reassurance.** "Don't worry", "this is straightforward", "as you can see".

## Prefer a table when the content is tabular

Every state, every flag, every exit code, every field. Prose describing six parallel things is six
rows badly formatted. Give the table a column for the thing and a column for what it means, and put
the explanation in the cell rather than in a paragraph above it.

## One idea per paragraph, one question per heading

Three sentences is a long paragraph. A heading a reader cannot answer from the section beneath it is
the wrong heading. Where a section runs past a screen, it has become two.

## Voice earns its place

Character is not the enemy of concision — a line that carries the invariant *and* the failure it
prevents is doing two jobs at once, and is worth its length. What does not earn its place is a
sentence carrying only tone. Keep the one that changes what a reader does; cut the one that only
sets a mood.
