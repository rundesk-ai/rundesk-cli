"""The foundation: where things are, how a small file is kept, and how this install is configured.

**Nothing here imports anything above it.** That is the rule that makes this a layer rather than a
folder — `core` is reachable from every part of the product, including part-way through replacing
every other module, so it may never depend on one of them.

| Module | Answers |
|---|---|
| `paths` | where an install keeps everything — one root, everything derived downward |
| `jsonfile` | reading and writing a small JSON file safely |
| `config` | what this install is configured with, and how far it has been carried |
"""
