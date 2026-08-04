"""This copy of rundesk on a machine: how it arrives, how it moves forward, and how it leaves.

May depend on `core` and on nothing else in the product — in particular not on `commands`, which is
the layer above. Every one of these is exercised with no network, no installer and no command line
anywhere near it, because everything variable arrives as an argument.

| Module | Answers |
|---|---|
| `release` | which version has been published, and how this install stands against it |
| `tree` | placing the program, replacing it, and taking it away |
| `migration` | carrying an install forward when a newer release expects something different |
| `steps/` | one migration step per file, found rather than listed |
"""
