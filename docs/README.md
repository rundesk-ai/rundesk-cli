# docs/

Everything written down about rundesk that is not the code itself.

**This is being rebuilt.** A page appears here when the thing it describes is built and works — not
before. A document written ahead of its feature is a document nobody can check, and the first thing
anyone learns from it is not to trust the rest.

| Page | What it answers |
|---|---|
| [layout.md](./layout.md) | Where an install keeps everything, and why it is one root |
| [commands.md](./commands.md) | Every operation the command offers, and what each guarantees |
| [development.md](./development.md) | Running and testing a checkout without installing it |
| [research/](./research/) | What was found out, kept where it can be read after the thing that taught it is gone |

`commands.md` lists what rundesk can do and nothing else. There is no operation on that page that
does not work, because there is no verb in the command that does not work.

## Research is a different kind of page, kept separately

The pages above describe rundesk **as it is**, and one appears only when the thing it describes
works. [`research/`](./research/) holds the other thing: what somebody established by spending an
afternoon on it — what the platform really does, what a previous build learned by getting it wrong,
and the questions nobody has answered yet.

They are apart because they are read for different reasons and age in different ways. A page above is
wrong the moment the product changes; a research page is wrong only when the world does, and says
what it was true of.

## Where the rest of it went

The project used to carry a `.knowledge/` system — ratified contracts, research notes, writing
standards and a linter that enforced their shape. It came out with the rebuild. What it held is
readable in this branch's history, and what is still true has been brought across into
[`research/`](./research/) rather than left there to be deleted with it.

The one thing to carry forward deliberately: **a guarantee is worth writing down only where a test
proves it.** Where this documentation states that rundesk does something, it is because a suite in
`tests/` fails if it stops being true.
