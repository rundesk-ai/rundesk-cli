# Structuring Project Docs source map

Read this before changing, challenging, or removing a rule in this package.

**This package is predominantly local practice, not distilled published guidance.** Almost every rule
here was derived from operating a documentation system across a set of repositories and watching
which parts survived. That is a weaker kind of evidence than a specification, and it is labeled as
such throughout so that a reader can weigh it. Where a rule is a preference rather than a response to
an observed failure, it says so.

## Separation of concerns with adjacent packages

The choice of *page type* — tutorial, how-to, reference, explanation, troubleshooting — and the
audience path through them is deliberately **not** covered here, and neither is how to trace a claim
to a contract or verify an example. Those belong to the documentation-writing package and its own
sources. This package answers only where a document lives and what shape it takes; the two are loaded
together when both questions are live.

Product requirement *content* — how to establish authority, resolve contradictions, and word an
outcome — likewise belongs to the product-requirements package. What this package fixes is the
**schema** a repository's requirements files take, so that a promise and its evidence sit in a
readable, auditable table. Where a repository's own template disagrees, the repository wins.

## Rules derived from an observed failure

Each of these is a local finding. The failure is what establishes the rule; the rule is the catalog's
conclusion from it, not a published recommendation.

| Rule | The failure it responds to |
|---|---|
| Never stand up a second documentation home beside a working one | A repository carrying two systems at once had the same facts in both, and readers could not tell which was current. The migration window is when this is created. |
| A page appears when the thing it describes works | Documents written ahead of their features could not be checked, and readers who found one learned to discount the rest of the directory. |
| The index row is added in the same change as the file | A research directory drifted roughly seven files ahead of its index with nothing complaining. A reader who finds most of a set stops looking for the remainder. |
| A count belongs in the row that owns it, never in a summary | Summary counts were stale the day after they were written, and unlike a stale row, nobody re-reads a summary to catch it. |
| Count artifacts, not lines, in a codemap | Line counts went stale on the next commit; artifact counts survived refactors and made real drift visible. |
| A ✅ requires an observed check, not a path or an unrun test | Rows citing a source path or an existing-but-unrun test read exactly like proven ones, and stayed green after the behavior changed. |
| Erasing a requirement row rewrites every citation at or after it | Renumbering left IDs that still resolved, to the wrong requirement. No check catches this, which is why it is a stop-and-ask. |
| Never infer an audience from a schema | An invented audience is loaded on every subsequent task, reads as confidently as a sourced one, and is never re-checked. |
| An ID is never renumbered, and a gap records a withdrawal | Applying the earlier "unbroken from 1" rule to a real repository would have repointed requirement citations held in shipped source and in test docstrings at different requirements, with nothing failing. The rule that forced the renumbering was the defect. |
| A requirement's length is a smell, not a limit | A 25-word ceiling, applied to a mature contract set, would have required rewording 57 of 161 carefully worded product conditions — including six in that repository's best-evidenced file, one of them 97 words. Rewording a contract to hit a count risks changing what it promises. |
| A repository's machine check belongs in its own test suite | A documentation gate outlived the system it checked and went on calling scripts that no longer existed, so every run was red for reasons unrelated to the change under review. A gate nobody can act on is a gate nobody reads. |
| The standards do not ship into each repository | A versioned payload copied the same standards files into every adopting repository, then carried a checksum manifest whose only purpose was proving the copies had not drifted. Holding the standards in one loadable place removes the payload, the version stamp, and the manifest together. |

## Rules that are preference, not evidence

Labeled so they can be argued with rather than defended as findings.

- The specific directory names — `api/`, `requirements/`, `research/`, `references/`. Any consistent
  set would work. What matters is that one set is chosen and every file classifies into it.
- Placing the orientation pair inside `docs/` rather than at the repository root.
- The four-heading requirements schema.
- Writing the orientation pair before the topic pages. It is cheap and settles later arguments, but a
  repository that starts elsewhere is not doing anything wrong.

## Material limits

- Every failure above was observed in a small set of repositories under one owner's practice. None of
  it is a controlled comparison, and none of it has been tested against a large multi-team codebase.
- The conversion order in `layout.md` was carried through one mature tree on 2026-08-25 and held.
  That is a single run, on a repository whose documentation was already unusually careful.
- No claim here is made about generated documentation sites, which this package does not address.
