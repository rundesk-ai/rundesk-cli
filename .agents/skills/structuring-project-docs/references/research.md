# Keep the outside world dated and separate

`docs/research/` and `docs/references/` are siblings, and both are easily confused with the topic
pages that describe this software.

- **A topic page describes this software as it is.** It is wrong the moment the product changes.
- **A research note describes the world outside this repository** on a stated day, against a stated
  version. It is wrong only when the world changes, and it says what it was true of.
- **A reference is material from elsewhere** that this project is measured against — a competitor's
  screen, a specification, a design somebody is matching.

Research is input, never truth. It informs a requirement; it is never the source of record for this
project's behavior.

## Research notes

One note, one question. The filename carries the date the finding was established, because a
measurement without a date is a recollection: `YYYY-MM-DD-<slug>.md`.

```md
# Research: <topic>

**Established:** YYYY-MM-DD
**True of:** <the versions, platforms, or builds this was measured against>
**Question it answers:** <one line — what can be decided after reading this>

## What they do

<Reporting only. Every non-obvious claim and every number carries a [n].>

## What we can borrow

<Ours. The transferable ideas, as short bullets.>

## What to avoid

<Ours. The traps — theirs, and the ones we would walk into.>

## Verdict for us

<Ours. What we are doing, deferring, or not doing, and what it feeds.>

## Open questions

<One line each. What was not learned, and what remains undecided.>
```

Close the note with a numbered citation list under a second-level `Sources` heading — one entry per
`[n]` used above, each a name and a URL, or `(internal)` naming what it was.

### Two rules that carry the whole format

**Say how you know.** Measured, read in a manual, and recalled are three different claims, and a
reader deciding whether to trust a line needs to know which it is. Mark the uncertain ones instead of
leaving them level with the rest. A note that reads uniformly confident is one nobody can use
selectively.

**Report the world, then say what you think — never both at once.** `What they do` is reporting;
borrow, avoid, and verdict are yours. The mechanism is sourcing at the point of claim: every
non-obvious sentence in the reporting section carries a `[n]`, so anything uncited is visibly your
own. An opinion smuggled into the reporting section becomes a borrowed idea, then a verdict, then a
requirement, and by then nobody can find where it entered.

### Keeping them

A research note is **not rewritten when the world moves on.** A rewritten measurement is a
recollection. Write a new dated note and, if the old one is now misleading, open it with what is
still true and what is not. Notes carried in from a previous build keep their original dates for the
same reason.

## References

Comparison material, organized by where it came from first: a directory per source — a competitor, a
platform, a specification — and inside it, a directory per thing being compared.

Every set carries a `NOTES.md` saying what inspires, what to avoid, and where the material came from.
A screenshot with no note is an image nobody can act on a year later, and it is the reason most
reference directories rot.

Respect licensing, and keep the material free of private detail — a captured screen showing somebody's
name, account, or data does not belong in a committed repository.

## Both have an index

`docs/research/README.md` lists every note, newest first, with the question each answers.
`docs/references/README.md` lists every set with its source and what is being compared. Add the row
in the same change that adds the file — a research index behind its directory is the most common
drift in this layout, because notes arrive in bursts and nothing complains when the table does not
move.
