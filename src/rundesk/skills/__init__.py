"""The skills this install keeps, where they came from, and which agent holds which.

A skill is a directory holding a `SKILL.md` — the format every provider CLI already reads, and the
reason nothing here injects anything into a prompt. Rundesk keeps them, stands them where a brain
looks, and stays out of the way.

**Everything is in a catalog, and a catalog is a directory.** One below `data/skills/`, named as the
catalog is, holding the tree it was fetched from. That is the decision the rest of this package rests
on, and it is the one the build this replaces got wrong: a single flat namespace shared by every
catalog, so a second catalog offering a skill name the first already had could not be installed at
all. Here nothing collides, because nothing shares a directory.

| Module | Answers |
|---|---|
| `library` | where skills stand, what makes a directory a catalog and a skill, and what is beside one |
| `catalogs` | fetching a catalog, keeping it up to date, and taking one away |
| `grants` | what an agent holds, granting and revoking it, and standing it where a brain looks |
| `needs` | what a skill says it needs, which profiles it has, and whether each of them is whole |
| `doctor` | why a skill an agent holds cannot be used, one verdict each |

May depend on `agents`, `core` and `utils`. It reaches `agents` because a grant is a directory entry
inside an agent's own home and there is nowhere else to ask where that is — but the traffic goes one
way only. **`agents` may not reach here**, so an agent is still a thing that can be made, carried and
removed by code that has never heard of a skill, and presenting a new agent's skills is done a layer
up in `commands`, which may reach both.

**Nothing here reads a credential's value.** Whether one is set is asked of `secrets.placed()`, which
answers yes or no; `secrets.value()` exists for the programs rundesk starts, and no listing, readout
or diagnosis is one of those. `tests/test_layers.py` checks that rather than trusting it.
"""
