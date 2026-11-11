# docs/

Everything written down about Rundesk that is not the code.

**[`wiki/`](./wiki/) is the source of truth.** Every sentence there names the code it came from, or
carries `{missing}`, and `./scripts/dev-wiki.sh check` fails the build when a page stops being fit to
read. The homes below it are legacy and are migrating into it.

## Start here

| Page | Answers |
|---|---|
| [BRIEF.md](./BRIEF.md) | What Rundesk is, who it serves, what it refuses |
| [CODEMAP.md](./CODEMAP.md) | Where each layer lives |

## Homes

| Home | Holds |
|---|---|
| [wiki/](./wiki/) | What Rundesk does, cited to the code — **the source of truth** |
| [api/](./api/) | Every operation, and what each guarantees — legacy |
| [concepts/](./concepts/) | How a subsystem works, and how it fails — legacy |
| [guides/](./guides/) | One task, start to finish — legacy |
| [extending/](./extending/) | Writing an adapter or catalog against a published contract — legacy |
| [requirements/](./requirements/) | What must be true, and whether anything proves it |
| [research/](./research/) | What was established about the world outside, and when |
| `assets/` | Images the pages embed |

## Research is separate on purpose

Pages above describe Rundesk **as it is** and are wrong the moment the product changes.
[`research/`](./research/) holds what somebody established by spending an afternoon on it — a
platform's real behavior, a previous build's incidents. It is wrong only when the world changes, and
says what it was true of.

## The two rules the directory rests on

**In [`wiki/`](./wiki/), every sentence cites the code it came from.** A statement nothing implements
yet carries `{missing}` until the change that builds it replaces the mark with a citation.

**In the legacy homes, a guarantee is worth writing down only where a test proves it.** Where they say
Rundesk does something, a suite in `tests/` fails if it stops being true.

The second rule is what survived the `.knowledge/` system this directory replaced. Its standards now live
in a skill loaded when documentation is written, rather than being copied into the repository behind
a manifest whose only job was proving the copies had not drifted.
