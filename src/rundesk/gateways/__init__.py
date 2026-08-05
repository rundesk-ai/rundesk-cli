"""A gateway: the process that hosts one agent.

One agent, one process, one name held for as long as that process lives. What a gateway *hosts* is
the part that grows — its logs today, and later its adapters, the work it delegates and the
subprocesses it starts. None of that is here yet, and when it arrives it arrives as something the
gateway hosts rather than as something that changes what a gateway is. That distinction is the whole
reason this layer is its own package: a host that keeps being rewritten to accommodate its guests is
a host nobody can say anything true about.

| Module | Answers |
|---|---|
| `standing` | whether a gateway is online, offline, or something nobody can tell — and, when it never came up, where the only account of that is |

**What a gateway says is not written here.** A file per day, appended to and swept after so many
days, is `utils.logs`: rundesk journals its own work the same way, and the layer that does that may
not reach across into this one. What stays here is the part that is genuinely the gateway's — where
its logs stand, and what the machine's supervisor called the two files it captured on the way up.

**Every function here takes the agent's own directory as an argument.** Nothing in this package
derives it, and nothing reads where the agents are — so a gateway can be stood up in a scratch
directory by a test, and the layer that knows what an agent is stays the layer that decides where one
lives.

May depend on `core` and `utils`. The command line is one layer's business and it is not this one: a
module here taking a `Namespace` would be a module that cannot be driven except by typing at it, and
the check that keeps that true reads these files looking for the parser's own name.
"""
