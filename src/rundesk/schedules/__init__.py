"""Work an agent starts because the time came, rather than because somebody asked.

A schedule belongs to one agent and is kept in that agent's own records, which is what makes one
agent's schedules that agent's alone: no other agent can run them, report on them or change them,
and there is no install-wide table for two gateways to disagree over.

May depend on `agents`, `core` and `utils`, and on nothing else. In particular it may not reach
`gateways`: **when a schedule is due is a different question from what starts it**, and the module
that decides the first would otherwise be untestable without a supervisor, a launchd and a process.
The gateway imports this, not the other way round.

| Module | Answers |
|---|---|
| `due` | what a schedule says about when it runs, and whether it is due at a given minute |
| `kept` | the schedules one agent keeps, and the only way in to them |

**A schedule says when, and it carries what.** `due` never looks at what a schedule names — a
program today, a provider and a prompt when there is a provider process to run one — so the kind of
work is a branch in one place rather than a shape the whole subsystem knows about.

**Two things are said one of two ways and never both**, and the records enforce both with a `CHECK`:
a schedule states a repeating time or one moment, and it starts a program or asks an agent. A row
that broke either could not have been written, which is why nothing downstream re-derives it.
"""
