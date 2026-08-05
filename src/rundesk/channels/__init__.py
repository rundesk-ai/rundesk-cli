"""How an agent is reached, and how it reaches back.

A channel is a **connection to a platform**, not a place on one: connecting Discord gives an agent
one channel that handles private messages and every room it has been invited to, with nothing
per-place written down. One list of ids says who may reach the agent, and it says so wherever they
say it. The build this replaces wrote a channel per kind of place, each with its own list — a shape
that exists to govern a public room full of strangers, which is not what this is for.

**Where a reply goes is never configured, because it is wherever the message came from.** The one
exception is the channel marked `notified`, which is where things nobody asked for land: a gateway
that has just come up is answering nobody and has no conversation to reply into.

**An adapter is a program, never a plugin.** Rundesk does not load somebody else's code into the
gateway hosting every other agent, an adapter author is not obliged to write Python, and — the part
that decides it on this platform — a vendor library lives on the far side of that seam and never
enters the gateway. Everything crosses as newline-delimited JSON on a pipe.

May depend on `agents`, `core` and `utils`, and on nothing else. In particular it may not reach
`gateways`: what a channel *is* and what hosts it are different questions, and the module that
answered both would be untestable without a supervisor. When this is hosted, the gateway will import it and not the reverse — nothing in
`gateways` reaches here yet, which `gateways.host`'s own docstring says of everything it
will one day host.

| Module | Answers |
|---|---|
| `kept` | the channels one agent keeps, and the only way in to them |
| `adapters` | finding the program behind a channel, and the two questions asked of it |
| `arriving` | what came in, written where it can be read again |
| `files` | what a file may be called, where it lands, and when it is swept |
| `delivery` | what goes out, split to what the platform will take |
| `hosting` | starting an adapter, draining it, restarting it, and stopping it |

**Rundesk decides what state a turn is in; an adapter decides only how that looks.** An adapter that
worked out on its own when a message had been seen would be re-implementing the turn, and two
surfaces would eventually disagree about the same run with the run's own account matching neither.

**Correctness never degrades, only fidelity.** A surface with no reactions marks nothing; one that
cannot edit posts again instead; the poorest of them, which can only post text, is a first-class
channel rather than a broken one.
"""
