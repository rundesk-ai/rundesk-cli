"""Which name a channel's credential stands under, and the value behind it.

**One bot is one identity, so a credential belongs to an agent and to nothing else.** Two agents
behind one Discord token are one presence: both receive every message, both may answer, and nobody
reading the room can tell which of them replied. That is not a preference — it is what a single bot
application *is*, and `docs/research/2026-08-05-designing-the-channel-system.md` settles it as one
application per agent.

The naming needs no new mechanism, and that is the point of it. A channel's credential is **a
profile of the adapter, named for the agent**, spelled exactly the way `skills.needs` already spells
a skill's several accounts: `DISCORD_BOT_TOKEN__ALAN`. `core.secrets` holds the separator so the two
layers cannot drift apart, and `rundesk env set` already accepts the name.

## One name, and there is no second one

What the adapter declares does not change, and neither does what it is handed. It publishes the
name it reads, `channels.kept` records that name exactly as it arrived, and it is given its value
**under that same declared name** — the recorded name and the name it looks in are one fact, and a
channel that passed `--check` must find the same value when it is hosted.

Where the value is *kept* is the agent's own name and only that:

    DISCORD_BOT_TOKEN__ALAN     alan's bot
    DISCORD_BOT_TOKEN__COLE     cole's bot

**A plain `DISCORD_BOT_TOKEN` is not read, ever.** It was a fallback for one release and it is gone:
a shared name is the shape that lets two agents be one bot by accident, and every way of keeping it
— read second, read only when no scoped name exists, read with a warning — is the same accident with
a longer path to it. A name nothing scoped holds is a channel that cannot be used, said plainly, at
the terminal, rather than an agent quietly signing in as somebody else.

**An unreadable name is not an absent one.** A scoped value this install can no longer open is
reported as itself: it is neither set nor unset, and telling somebody their token is missing when it
is really unreadable sends them to type a new one over something they may still want.

## An agent's name is used, or the agent has no credential — it is never mangled

An agent may be called things an environment variable may not, and this is exactly where the obvious
sanitising goes wrong: `a-b` and `a_b` both fold to `A_B`, and two agents quietly share one bot with
nothing anywhere saying so.

So no character is ever replaced. An agent already called something a profile can be called —
letters, digits and underscores, starting with a letter — has a name of its own, upper-cased because
that is the only case `secrets.NAMED` accepts. **Every other agent can hold no credential at all**,
and `name_trouble` is the sentence that says so. With the fallback gone that is a real refusal
rather than a quiet downgrade, and it is the honest one: the alternative is folding, and folding is
the collision this whole shape exists to prevent.

A channel that needs no credential is unaffected — an agent whose name cannot carry one may still
have as many of those as it likes.

That leaves case, and `agents.directory.taken` closed it before this was written: a name differing
from an existing agent's only by case is refused, because the volume macOS ships with cannot tell
the two directories apart. So at most one agent on an install folds to any given suffix, the map
from the agents an install can hold to their suffixes is injective, and there is no collision here
to defend against.

## Nothing here prints a value

`standing` answers *where* a value is, in three states — kept, not kept, and there but unreadable —
and is what a listing, a readout and `channels doctor` ask. `handed` is the only thing that reads
one, for the programs rundesk starts, which is what `secrets.value` exists for. Both are asked the
same question by the same rules, which is what makes a diagnosis and a running adapter agree about
which credential makes a channel usable.

May depend on `agents`, `core` and `utils`.
"""

import re
from typing import Dict, List, NamedTuple, Sequence

from rundesk.core import secrets

#: What an agent must already be called to hold credentials at all: the alphabet a profile is
#: written in, before the upper-casing `secrets.NAMED` insists on. An agent named anything else can
#: hold none — refused rather than folded, because folding is what collides.
ITS_OWN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class Standing(NamedTuple):
    """One credential a channel names, and where its value would come from.

    `declared` is the adapter's own name, as the record holds it, and is the name the value is
    handed over as.

    `scoped` is this agent's own name for it, or `""` for an agent that can hold none — in which
    case `trouble` says why, and there is no command to suggest.

    `holding` is the name a value is really kept under right now, or `""` when nothing is. **This is
    the field that decides whether the channel can be used**, and it is read by the gateway starting
    an adapter and by `channels doctor` alike, so the two cannot disagree.

    `trouble` is the sentence for the two ways this is not simply unset: a name that is there and
    cannot be opened, and an agent that can hold no credential at all.
    """

    declared: str
    scoped: str
    holding: str
    trouble: str


def name_trouble(agent: str) -> str:
    """Why this agent can hold no credential of its own, or `""` when it can.

    A sentence rather than a `False`, because every caller has to tell somebody what to do about it
    — and what to do is *not* obvious, which is why it is written once here. There is no rename
    verb, so the honest answers are an agent whose name can carry a credential, or a channel that
    needs none.
    """
    if ITS_OWN.match(agent or ""):
        return ""
    return (f"{agent} cannot hold a credential of its own — an agent's credentials are kept under "
            f"its own name, and that name has to be letters, digits and underscores starting with "
            f"a letter, the way a shell variable is written. It is never folded to fit: a-b and a_b "
            f"would become one name, and two agents would share one bot. Give this channel to an "
            f"agent whose name can carry one, or use an adapter that needs no credential")


def suffix_for(agent: str) -> str:
    """The profile suffix this agent's credentials stand under. `""` for one that can hold none.

    Upper-cased and never otherwise altered. See the module docstring: an agent whose name is not
    already a name a profile can have gets no suffix rather than a folded one.
    """
    return agent.upper() if ITS_OWN.match(agent or "") else ""


def scoped_name(declared: str, agent: str) -> str:
    """The one name `declared` is kept under for `agent`, or `""` where the agent can hold none."""
    suffix = suffix_for(agent)
    return secrets.profiled(declared, suffix) if suffix else ""


def standing(agent: str, names: Sequence[str]) -> List[Standing]:
    """Where each of these credentials stands for this agent, in the order given.

    One read of the store for all of them rather than two questions per name, because `placed`
    opens and verifies the whole file each time it is asked and a caller here always has a list.
    """
    trouble = name_trouble(agent)
    if trouble:
        return [Standing(one, "", "", trouble) for one in names]
    held = secrets.kept()
    return [_where(one, scoped_name(one, agent), held) for one in names]


def handed(agent: str, names: Sequence[str]) -> Dict[str, str]:
    """Each credential this channel names, **keyed by the name the adapter declared**.

    The agent's own name is where the value is kept; the declared name is what it arrives as. An
    adapter reads the name it published and is never told anything about the profile behind it.

    A name holding nothing, one holding something this install can no longer open, and an agent that
    can hold no credential are all left out. An adapter started without its credential refuses and
    says which name it looked in, which is a better answer than a gateway inventing one — and far
    better than the shared value this deliberately no longer reaches for.
    """
    if name_trouble(agent):
        return {}
    held = secrets.kept()
    built = {}
    for declared in names:
        found = _where(declared, scoped_name(declared, agent), held)
        if found.holding:
            value = held[found.holding].value
            if value is not None:
                built[declared] = value
    return built


def _where(declared: str, scoped: str, held: Dict[str, secrets.Held]) -> Standing:
    """What this agent's own name holds, and nothing else is consulted.

    **A cleared name is unset and there is nowhere to fall through to.** Emptying
    `DISCORD_BOT_TOKEN__ALAN` switches this agent's bot off, and that is the whole answer: the plain
    name is not read, so nothing here can quietly start the agent as a different one.
    """
    one = held.get(scoped)
    if one is None:
        return Standing(declared, scoped, "", "")
    if one.value is not None:
        return Standing(declared, scoped, scoped, "")
    if one.trouble:
        return Standing(declared, scoped, "", f"{scoped} {one.trouble}")
    return Standing(declared, scoped, "", "")
