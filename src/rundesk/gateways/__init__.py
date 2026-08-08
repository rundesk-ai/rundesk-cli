"""A gateway: the process that hosts one agent.

One agent, one process, one name held for as long as that process lives. What a gateway *hosts* is
the part that grows — its own logs, the work its schedules start, the adapters its channels connect
through, and later the turns it delegates to a provider. Each of those arrived as something the
gateway hosts rather than as something that changed what a gateway is: the same three seams in the
same loop, and a shutdown budget divided among them rather than handed to each. That distinction is
the whole reason this layer is its own package: a host that keeps being rewritten to accommodate its
guests is a host nobody can say anything true about.

| Module | Answers |
|---|---|
| `awake` | holding and proving the macOS idle-system-sleep assertion for exactly one live gateway |
| `standing` | whether a gateway is online, offline, or something nobody can tell — and, when it never came up, where the only account of that is |
| `job` | handing one gateway to the machine's supervisor, and the four ways of asking whether it is really there |
| `maintenance` | one-shot update notices handed from the old gateway process to the new one |
| `host` | the gateway process itself: what it refuses to run for, and the one exit code launchd reads |

**`host` may not import `job`, and that is a rule rather than an accident.** A process never talks
to its own supervisor: a gateway that could bootstrap or boot out its own job could restart itself,
and the decision to keep a gateway running would sit inside the thing being kept running. It is also
what lets the whole of `host` be driven by a test with launchd nowhere near it.

**The supervisor arrives as an argument**, `job.Supervising`, in the shape `lifecycle.release.Asking`
and `commands.update.Fetching` already established — and for a stronger reason than either of those.
Those leave the machine, so a test that forgot to replace one fails loudly. This one does not: the
real implementation would answer a test perfectly well, against the owner's own login session, and
take down jobs that keep real work running.

**What a gateway says is not written here.** A file per day, appended to and swept after so many
days, is `utils.logs`: rundesk journals its own work the same way, and the layer that does that may
not reach across into this one. What stays here is the part that is genuinely the gateway's — where
its logs stand, and what the machine's supervisor called the two files it captured on the way up.

**Every function concerned with a gateway's identity takes the agent's own directory as an
argument.** Nothing in this package derives it, and nothing reads where the agents are — so a
gateway can be stood up in a scratch directory by a test, and the layer that knows what an agent is
stays the layer that decides where one lives. `awake` is the deliberate exception in subject rather
than in architecture: its identity is the current process id, which is exactly what macOS releases
the assertion against after a crash.

May depend on `core` and `utils`. The command line is one layer's business and it is not this one: a
module here taking a `Namespace` would be a module that cannot be driven except by typing at it, and
the check that keeps that true reads these files looking for the parser's own name.
"""
