# scripts/ — tooling & your workspace

Code, not prose — stack-neutral, standard-library only, runs with nothing installed.

The **shipped tooling** below is versioned by `knowledge-template`: don't rewrite it per project, it updates
by version bump. Everything else you drop in here is yours.

## Contents

| Script | What it does |
|---|---|
| [`doc-lint`](./doc-lint) | Enforces the standard on `.knowledge/` — namespaces, IDs, citations, glyph tables, catalogs, research notes, and the payload's own integrity. A red lint is a broken doc. |
| [`test_doc_lint.py`](./test_doc_lint.py) | The linter's teeth-test: a valid project passes, each mutation fails on its own rule. If this fails, the linter has lost a tooth. |

### This project's

_(none yet)_

The `gate`, `check-evidence`, `cli-reference` and `ci-suites` runners went with the build being replaced.
Each one resolved a path into the old `src/` or sharded the old suites, and two of them failed in the worst
available way once that tree moved: both globbed `src/**/*.py`, matched nothing, and reported `parse OK`.
They are rewritten against the new tree as the parts they check are built, and the replacement gate **fails
on an empty discovery** rather than passing vacuously.

## Usage

```
python3 .knowledge/scripts/doc-lint .knowledge     # lint this project's docs
python3 .knowledge/scripts/test_doc_lint.py        # prove the linter still works
```

Wire both into CI. A rule that matters is a check in `doc-lint`, teeth-tested beside it — prose that isn't
enforced is teaching, not law.

## Payload integrity

`../.payload-manifest` records a `sha256` for every file this project must never edit — the `docs-*.md`
standards and the two scripts above. `doc-lint` re-hashes them on every run, so a repo can **prove** it is
running the version stamped in `../.version` instead of taking it on trust. A drifted file is named in the
failure: restore it from that release, or upgrade the whole `.knowledge/` and re-stamp the version.

**Do not hand-edit the manifest.** Only the upstream release step rewrites it, after changing the payload:

```
python3 .knowledge/scripts/doc-lint --write-manifest .knowledge   # re-record the checksums (upstream only)
```

## Your scripts

This folder is also a workspace. Add project-specific helper scripts here — generators, build steps, one-off
checks, anything that helps an agent work in this repo. Keep the shipped `doc-lint` and `test_doc_lint.py`
unchanged (they're versioned); everything else here is yours to add and name.
