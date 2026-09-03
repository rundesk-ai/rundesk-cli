# docs/

Everything written down about Rundesk that is not the code.

**A page appears when the thing it describes works.** A document written ahead of its feature cannot
be checked, and teaches readers to distrust the rest.

## Start here

| Page | Answers |
|---|---|
| [BRIEF.md](./BRIEF.md) | What Rundesk is, who it serves, what it refuses |
| [CODEMAP.md](./CODEMAP.md) | Where each layer lives |

## Homes

| Home | Holds |
|---|---|
| [api/](./api/) | Every operation, and what each guarantees |
| [concepts/](./concepts/) | How a subsystem works, and how it fails |
| [guides/](./guides/) | One task, start to finish |
| [extending/](./extending/) | Writing an adapter or catalog against a published contract |
| [requirements/](./requirements/) | What must be true, and whether anything proves it |
| [research/](./research/) | What was established about the world outside, and when |
| `assets/` | Images the pages embed |

## Research is separate on purpose

Pages above describe Rundesk **as it is** and are wrong the moment the product changes.
[`research/`](./research/) holds what somebody established by spending an afternoon on it — a
platform's real behavior, a previous build's incidents. It is wrong only when the world changes, and
says what it was true of.

## The rule the directory rests on

**A guarantee is worth writing down only where a test proves it.** Where this documentation says
Rundesk does something, a suite in `tests/` fails if it stops being true.

That rule is what survived the `.knowledge/` system this directory replaced. Its standards now live
in a skill loaded when documentation is written, rather than being copied into the repository behind
a manifest whose only job was proving the copies had not drifted.
