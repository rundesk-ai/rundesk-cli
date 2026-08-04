"""This copy of rundesk on a machine: how it arrives, how it moves forward, and how it leaves.

May depend on `core` and `utils`, and on nothing else in the product — in particular not on
`commands`, which is the layer above. Every one of these is exercised with no network, no installer
and no command line anywhere near it, because everything variable arrives as an argument.

| Module | Answers |
|---|---|
| `release` | which version has been published, and how this install stands against it |
| `tree` | placing the program, replacing it, and taking it away |
| `backups` | copies of what the owner keeps, and where they are kept |
| `migration` | carrying an install forward when a newer release expects something different |
| `steps/` | one migration step per file, found rather than listed |

Three of these replace something on disk, and all three do it the same way — built beside what it
replaces, renamed into place only once all of it is there. That convention and its names are
`utils.staging`, so a swap and the walk that has to skip it cannot come to disagree about what a
half-written thing is called.
"""
