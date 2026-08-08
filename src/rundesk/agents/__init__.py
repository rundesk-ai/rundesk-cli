"""The agents this install keeps: where each one's things stand, what each one remembers.

One directory per agent under `data/agents/`, and one database inside it. Nothing is shared between
two agents — not a file, not a lock, not a row — which is what makes one agent that cannot be read,
or cannot be carried, exactly one agent's problem.

May depend on `core` and `utils`, and on nothing else in the product. In particular it may not reach
`gateways`, which is the layer above: whether an agent is *running* is a different question from
where its things stand, and a module here that asked it would be a module that could no longer be
tested without starting a program.

| Module | Answers |
|---|---|
| `directory` | where one agent's things stand, what makes a directory an agent, and adding or removing one |
| `pages` | the files an agent lives by, and putting the ones it is missing into its home |
| `records` | the database one agent keeps, and the only way in to it |
| `migration` | carrying one agent, and every agent, onto this release |
| `steps/` | one agent migration step per file, found rather than listed |

**An agent is a directory holding `state.db`.** Not a name in a list somewhere, and not a row in an
install-wide table: what an agent is, is on the disk in one place, so adding one is a directory
appearing and removing one is a directory going away. There is no second register to fall out of
step with the first.

Every file an agent has stands **inside** that agent's own directory, under a fixed name. The build
this replaces kept them beside it — `<name>.lock`, `<name>.log` — and needed a published list of
every suffix a gateway might write so that an agent called `foo.log` could be refused before it
collided with one called `foo`. `directory` says the rest.
"""
