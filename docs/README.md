# docs/

Everything written down about Rundesk that is not the code itself.

**A page appears here when the thing it describes is built and works — not before.** A document
written ahead of its feature is one nobody can check, and the first thing anyone learns from it is
not to trust the rest.

## Start here

| Page | What it answers |
|---|---|
| [BRIEF.md](./BRIEF.md) | What Rundesk is, who it serves, and what it refuses |
| [CODEMAP.md](./CODEMAP.md) | Where each layer lives, and what is in it |

## The homes

| Home | What it holds |
|---|---|
| [api/](./api/) | The surface Rundesk publishes, and what each operation guarantees |
| [requirements/](./requirements/) | What must be true, and whether anything proves it |
| [research/](./research/) | What was found out about the world outside, kept where it can be read after the thing that taught it is gone |
| `assets/` | The images the pages embed |

## The subsystems

One page each, and each is the source of truth for its subsystem.

| Page | What it answers |
|---|---|
| [layout.md](./layout.md) | Where an install keeps everything, and why it is one root |
| [gateways.md](./gateways.md) | What a gateway is, and every state one can get stuck in |
| [providers.md](./providers.md) | What a turn is and what is written down about one — and writing the program behind a brain |
| [adapters.md](./adapters.md) | Writing the program behind a channel: the three invocations, and every record |
| [discord.md](./discord.md) | Creating and connecting a Discord bot, step by step |
| [schedules.md](./schedules.md) | What a schedule is, and every state one can get stuck in |
| [catalogs.md](./catalogs.md) | Writing a skill, and publishing a catalog of them |
| [teams.md](./teams.md) | What a team is once it is installed, and what reconciliation puts back |
| [instructions.md](./instructions.md) | What every turn is told, and who owns each layer of it |
| [permissions.md](./permissions.md) | What macOS lets Rundesk do, and why the answer depends on which process asks |
| [time.md](./time.md) | The three clocks, and which one answers what |
| [development.md](./development.md) | Running and testing a checkout without installing it |
| [live-agent-verification.md](./live-agent-verification.md) | Reproducing edge-case tests for rules, agent instructions, skills, and provider behavior |

## Research is a different kind of page, kept separately

The pages above describe Rundesk **as it is**, and one appears only when the thing it describes
works. [`research/`](./research/) holds the other thing: what somebody established by spending an
afternoon on it — what the platform really does, what a previous build learned by getting it wrong,
and the questions nobody has answered yet.

They are apart because they are read for different reasons and age in different ways. A page above is
wrong the moment the product changes; a research page is wrong only when the world does, and says
what it was true of.

## The rule the whole directory rests on

**A guarantee is worth writing down only where a test proves it.** Where this documentation states
that Rundesk does something, it is because a suite in `tests/` fails if it stops being true.

That is what survived the `.knowledge/` system this directory replaced — ratified contracts, research
notes, writing standards and a linter that enforced their shape. The standards now live in a skill
that is loaded when documentation is being written, rather than being copied into the repository
behind a manifest whose only job was proving the copies had not drifted. What the old system held is
readable in this branch's history, and what is still true was brought across into
[`research/`](./research/).
