# docs/

Everything written down about rundesk that is not the code itself.

**This is being rebuilt.** A page appears here when the thing it describes is built and works — not
before. A document written ahead of its feature is a document nobody can check, and the first thing
anyone learns from it is not to trust the rest.

| Page | What it answers |
|---|---|
| [layout.md](./layout.md) | Where an install keeps everything, and why it is one root |
| [commands.md](./commands.md) | Every operation the command offers, built or not |
| [development.md](./development.md) | Running and testing a checkout without installing it |

## Where the rest of it went

The project used to carry a `.knowledge/` system — ratified contracts, research notes, writing
standards and a linter that enforced their shape. It came out with the rebuild. What it held is
readable in this branch's history; what is worth keeping comes back here as an ordinary page, written
in ordinary prose, when there is something true to say.

The one thing to carry forward deliberately: **a guarantee is worth writing down only where a test
proves it.** Where this documentation states that rundesk does something, it is because a suite in
`tests/` fails if it stops being true.
