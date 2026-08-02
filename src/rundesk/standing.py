"""How a gateway stands, asked from above it — and waiting for that to change.

Four questions the command surface and the update worker both ask: what is this gateway
doing, what gateways are there at all, is it up yet, and is it gone yet. They live here
rather than in `cli.py` because the worker that stands every gateway on the machine down
asks them too, and rather than in `gateway.py` because answering them means putting a
gateway together with the agent whose run directory it keeps — which is the one direction
this codebase does not go (a gateway never reaches for an agent).

Every collaborator is an argument. Nothing here opens a lock, starts a process or knows
how it was invoked, so all four are exercised with no gateway and no supervisor anywhere
near them.
"""

from __future__ import annotations

import time
from pathlib import Path

from rundesk import ROOT

#: How long to wait for a gateway to actually appear after the machine takes its job.
#: Generous enough for a cold start, short enough that a gateway which is never coming
#: is reported rather than waited on.
START_PATIENCE = 15.0

#: How long cycling waits for a gateway to actually go before giving up on it. Longer
#: than a gateway is allowed to take stopping, so a slow but correct shutdown is not
#: mistaken for one that is stuck.
CYCLE_PATIENCE = 20.0

#: How often either of those looks again while it waits. Named once rather than written
#: into each waiter, because how long to wait and how often to look are one decision: a
#: patience shorter than a couple of these leaves a wait that can only look once, and
#: whether it looks twice then depends on how loaded the machine is. That is exactly how
#: a correct cycle came to be reported as one that never restarted, on one platform and
#: not the other.
LOOK_AGAIN_SECONDS = 0.2


def of(name: str, gateways, agents):
    """What this gateway is doing, asked where that gateway actually keeps it.

    Where the two are put together, for every caller that has both. A command resolving
    the directory itself at each call is how one of them comes to ask the wrong place and
    report a running agent as stopped.

    One caller does not go through here: a listing handed an already-resolved agent asks
    `gateways.standing` with it directly, because threading the agent module through that
    signature to resolve what it was already given would be the longer way to the same
    answer. Anything that reaches for the run directory *without* one belongs here.
    """
    return gateways.standing(name, agents.resolved(name).run)


def every_name(gateways, machine, agents, root: Path = ROOT) -> list[str]:
    """Every gateway there is: one per agent, and any that has no agent yet.

    Four places, because there are four ways one can exist. An agent has a gateway
    whether or not it has ever run; a gateway from before there were agents left its record
    where gateways used to keep them; a job the machine holds names one that may have
    left nothing anywhere; and a name whose record was cleared and whose agent was taken
    away survives in what it was scheduled to do and what it never finished (R-GW-38).
    That last one is the name an owner wants after a crash, and it was the one they had
    to know already before any command would tell them anything about it. Asked of the
    agent module rather than of the gateway module for the first, so that a gateway still
    knows nothing of whose work it holds.
    """
    return sorted({*agents.known(), *(it.name for it in gateways.every()),
                   *machine.described(root=root), *gateways.remembered()})


def came_up(name: str, gateways, agents, patience: float | None = None):
    """The gateway, once it is actually there — or None if it never arrives.

    The patience resolves here rather than in the signature: a default argument is bound
    once, when this file is read, so naming the constant there freezes it and anything
    that changed it afterwards is quietly ignored.
    """
    deadline = time.monotonic() + (START_PATIENCE if patience is None else patience)
    while time.monotonic() < deadline:
        now = of(name, gateways, agents)
        if now.running:
            return now
        time.sleep(LOOK_AGAIN_SECONDS)
    return None


def gone(name: str, gateways, agents, patience: float | None = None) -> bool:
    """Has this gateway actually stopped? Asked of the gateway, not of the machine.

    The patience resolves here, not in the signature — see `came_up`.
    """
    deadline = time.monotonic() + (CYCLE_PATIENCE if patience is None else patience)
    while time.monotonic() < deadline:
        if not of(name, gateways, agents).running:
            return True
        time.sleep(LOOK_AGAIN_SECONDS)
    return not of(name, gateways, agents).running
