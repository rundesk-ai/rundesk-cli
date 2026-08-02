"""Who a channel has already introduced this agent to, and who is still owed one.

One file per channel and the four questions asked of it (R-CH-33). Kept apart from the
gateway because none of it is about a gateway: the record belongs to a channel's own home,
the command that adds or removes a channel writes here while nothing is running, and the
gateway is only one of the two writers. It was reached out of `commands/channels.py`
through the gateway collaborator for exactly that reason — a command asking a gateway about
something a gateway does not own.

**A mapping and not a list is the whole feature.** `changing` hands back the empty value
for a file nobody has written, so an empty list would make "this channel is new, greet
everybody" and "this channel has greeted everybody already" the same answer — and those are
opposites. A missing key is the third answer: a channel from before any of this existed,
whose people have been talking to the agent for months and must never be greeted.
"""

from __future__ import annotations

from pathlib import Path

from rundesk.durable import changing

#: Where a channel keeps who it has already introduced this agent to (R-CH-33). Beside the
#: credential, in the private home that channel is given for this agent and for no other,
#: because that directory is what a channel *is* on disk: it outlives every restart and
#: every update, it goes away when the channel does, and no other channel can reach it.
#:
#: A dotfile, so an adapter listing its own home is not handed a file it did not write.
WELCOMED = ".welcomed.json"

#: What a channel that has never been looked at holds. **A mapping and not a list**, and
#: that is the whole of why anybody is ever welcomed: `changing` hands back exactly this
#: for a file nobody has written, so an empty list as the empty value would be
#: indistinguishable from a channel that has welcomed nobody yet — and those two mean
#: opposite things. A missing key is a channel from before any of this existed.
_NEVER_LOOKED: dict = {}

#: The key inside it. Sorted, and only ever user ids this channel allows.
_WELCOMED = "welcomed"


def welcomed_path(home: Path) -> Path:
    """Where this channel's record of who it has introduced the agent to stands."""
    return Path(home) / WELCOMED


def remember_no_one_welcomed(home: Path) -> None:
    """Write down that this channel is new and has introduced the agent to nobody.

    Written when the channel is *added*, and that is what tells a new channel from one an
    older release wrote. Without it, the first gateway to run this code would read no file
    at all for both and have no way to tell "everybody here is new" from "everybody here
    has been talking to this agent for months" — and the second of those must never be
    greeted (R-CH-33).
    """
    with changing(welcomed_path(home), dict(_NEVER_LOOKED), "who a channel has welcomed",
                  durable=True) as kept:
        kept[_WELCOMED] = []


def forget_welcomed(home: Path, users) -> None:
    """Drop these people from what this channel has written down.

    Called where somebody is taken off a channel's allowed list, so that adding them again
    later is a new introduction (R-CH-33). The gateway prunes the same names the next time
    it looks — this is for the case where nothing is running, which is exactly when an
    owner rearranges who may reach an agent.

    A channel nobody has written a record for is left alone: seeding one here would claim
    an older release's channel is new.
    """
    dropping = {str(one) for one in users}
    if not dropping:
        return
    with changing(welcomed_path(home), dict(_NEVER_LOOKED), "who a channel has welcomed",
                  durable=True) as kept:
        known = kept.get(_WELCOMED)
        if not isinstance(known, list):
            return
        kept[_WELCOMED] = sorted(one for one in known if one not in dropping)


def owed_a_welcome(home: Path, allow) -> list[str]:
    """Who this channel allows and has never introduced the agent to (R-CH-33).

    Three answers out of one file, and the difference between them is the whole feature:

    - **Nothing written** — a channel an older release added. What it allows now is written
      in and nobody is owed, so updating rundesk never greets people who have been using
      the agent for months.
    - **Written and empty** — a channel just added. Everybody it allows is owed one.
    - **Written with names in it** — anybody it allows who is not among them is owed one,
      and anybody among them it no longer allows is dropped in the same hold. That is what
      makes taking somebody off and putting them back a new introduction rather than
      silence.

    Read, decided and written under one hold, because the command that changes the allowed
    list writes here too and two writers that each read the same file lose one change.
    """
    allowed = [str(one) for one in (allow or [])]
    owed: list[str] = []
    with changing(welcomed_path(home), dict(_NEVER_LOOKED),
                  "who a channel has welcomed") as kept:
        known = kept.get(_WELCOMED)
        if not isinstance(known, list):
            kept[_WELCOMED] = sorted(set(allowed))
            return []
        keeping = sorted({str(one) for one in known} & set(allowed))
        if keeping != list(known):
            kept[_WELCOMED] = keeping
        owed = [one for one in allowed if one not in keeping]
    return owed


def remember_welcomed(home: Path, user: str) -> None:
    """Write down that this channel has now introduced the agent to somebody.

    **Only once it has actually happened.** A welcome written down before it was delivered
    is a person who is never greeted at all, and this is the one message that cannot be
    asked for again by whoever missed it.

    A channel nothing has been written for is left alone, the way forgetting leaves it:
    starting a record here would turn a channel an older release wrote into a new one,
    and every other person on it would then be greeted as though they had just arrived.
    Anything actually being greeted has been looked at first, and looking is what writes
    the record.
    """
    with changing(welcomed_path(home), dict(_NEVER_LOOKED), "who a channel has welcomed",
                  durable=True) as kept:
        known = kept.get(_WELCOMED)
        if not isinstance(known, list):
            return
        kept[_WELCOMED] = sorted({str(one) for one in known} | {str(user)})
