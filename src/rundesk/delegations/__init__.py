"""Work an agent hands to somebody else — another named agent, or a role it puts on.

There is one feature here and it has two targets. **A delegation to a named agent** is answered by
that agent as itself, out of its own home, by its own gateway. **A role run** is the same agent
working in a mode, with its identity withheld, carried by its own gateway in a disposable area. What
differs between them is where the turn stands, what it is told, and whether its history survives —
and nothing else, which is why one table and one set of rules hold both.

## A delegated turn is a turn

Almost all of this already exists. The brief is a `conversation_messages` row, a steer is another
one, the work is `turns` and its outcome is `turn_status`, and waking the delegator to review the
answer is a message on its own conversation — which is already how a person's message wakes an
agent. What is genuinely new is one row saying *"I handed this out and I am owed an answer"*, and
that is the whole of `kept`.

## The rule that holds everywhere

**A gateway writes only its own agent's store, and reads other agents' stores read-only.** The
delegation row belongs to the agent that made it; the agent doing the work never holds anybody
else's bookkeeping. `records.reading` opens a database `mode=ro`, so the rule is one SQLite enforces
rather than one a reviewer has to notice.

May depend on `agents`, `core` and `utils`, and on nothing else. In particular it may not reach
`providers`: **what has been handed over is a different question from what runs it**, and a module
that answered both could not be driven by a case with no brain and no subprocess anywhere near it.
The gateway imports this and hands it what it needs, the way it already does for `schedules` and
`channels`.

| Module | Answers |
|---|---|
| `kept` | the delegations one agent has made, and the only way in to them |
| `admitting` | whether one agent may hand this work to another, and writing it down when it may |
| `hosting` | the gateway's third tenant: answering what was handed here, collecting what went out |
"""
