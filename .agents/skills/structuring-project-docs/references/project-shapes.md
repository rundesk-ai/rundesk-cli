# Fit the homes to the project

The homes are fixed in meaning, not in number. Create the ones this project has pages for and leave
the rest out. A directory nobody can fill is worse than a missing one, because the next person fills
it with something that does not belong.

## What each kind of project usually has

| Project | Homes it usually has | Notes |
|---|---|---|
| CLI | `api/` `concepts/` `guides/` `extending/` | `api/` is the verb reference, one page per command group |
| Library or SDK | `api/` `guides/` | `api/` is often generated; keep the hand-written entry path beside it |
| Web application | `concepts/` `guides/` | No `api/` unless something external calls it |
| Service with an HTTP API | `api/` `concepts/` `guides/` | `api/` mirrors the resources, not the controllers |
| Game | `concepts/` `guides/` | Concepts are systems: simulation, rendering, input, save |
| Content or skill catalog | `guides/` | The packages are the product; document authoring and publishing |
| Static site | `guides/` | Usually `BRIEF`, `CODEMAP`, and a build guide is the whole set |
| Internal tool | `guides/` | Often needs no `concepts/` at all |

`requirements/` and `research/` are not tied to a project kind. Add them when there is a contract to
assert or a finding to date.

## The three-file rule governs docs/, not the repository root

`README.md`, `LICENSE`, `CONTRIBUTING.md`, `RELEASING.md`, `CHANGELOG.md`, `SECURITY.md`, and the
agent instruction files stay where consumers and tooling expect them. They are ecosystem conventions,
not documentation pages, and moving them into a home breaks the expectation without organizing
anything. The rule is about the root of `docs/`.

A root file that is genuinely a page in disguise — a long setup walkthrough, an environment contract,
a deep architecture note — belongs in a home. The test is whether anything outside the repository
looks for it by name.

## The edge cases

**A repository with two audiences.** A published product with an internal build process has consumer
pages and maintainer pages. Do not split `docs/` in two. Sort by reader need as usual and let
`docs/README.md` open with two entry paths — "using it" and "working on it" — pointing into the same
homes.

**A repository that publishes a documentation site.** The site is the consumer surface and wins. Do
not build a second tree beside it. Put the maintainer material in `docs/` and let the site keep its
own directory, and say in `docs/README.md` which is which. Where the site builds *from* `docs/`,
follow the site's required layout and add only the homes it does not forbid.

**A monorepo.** One `docs/` at the root, with each page naming the package it describes. Do not give
every package its own `docs/` tree: a reader looking for how a *kind* of thing works then has to
guess which package it lives in. `CODEMAP.md` maps by layer across the workspaces.

**A very small repository.** Under about six pages, homes cost more than they return. Keep the three
root files and one home for everything else, and split when a home passes about eight pages.

**A repository that is mostly one huge reference.** Split it before it stops being searchable, and
keep one index page listing every entry on one line. Length is the trigger, not taste: a reference
page a reader scrolls instead of searching has failed at its only job.

**A repository with no code.** A specification, a dataset, a design system. `CODEMAP.md` maps
whatever the artifacts are — schemas, tokens, tables — and `api/` holds the published shape if
anything consumes it.

**A catalog of packages.** The packages are the product and each carries its own documentation, so
the repository needs orientation rather than homes: what the catalog is for, who it serves, what it
refuses, and where a package's parts live. Adding homes to hold three files is the mistake here.
Resist duplicating any package's own guidance at the repository level — a rule written in both places
is a rule that will disagree with itself.

**A fork or a rewrite.** The predecessor's documentation is research, not truth. Date it, mark what
it was true of, and never let it sit at the same level as pages describing what runs now.

## Naming a home the table does not cover

Keep the four reader questions. If a project genuinely has a fifth — a compliance record, an
operations runbook set — add one home, name it for the reader's need rather than the department, and
give it a `README.md` like every other. Adding a home is a decision to raise, not one to take
quietly: a home with no stated rule is one the next person fills wrongly.
