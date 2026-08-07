"""Everything an adapter is told about one turn, and the whole of it.

This is the interface. An adapter is a program, so there is no object to hand it and no method to
call: what a turn *is* arrives as environment variables, its prompt arrives on the adapter's input,
and what the brain did comes back on its output. Everything rundesk will ever tell an adapter about a
turn is named here, which is what makes the surface readable in one screen and reviewable when it
grows.

**What is not here is as deliberate as what is.** No vendor variable, because which one a brain wants
is that brain's adapter's business and putting it here would put the vendor in the core.

**Anything left out is left unset rather than set to nothing.** An adapter asked to work with a model
called empty-string does something odd with it; one told nothing falls back to its own default, which
is what `${RUNDESK_MODEL:-default}` is written expecting.

**Built from nothing, never inherited.** `core.adapters.environment` starts from a named handful and
this adds to it. The alternative — copy this process's environment and strip what should not go — is
a list somebody has to keep true for ever, and a comparable product had to retrofit exactly that
after handing a coding subprocess every credential it held.

**The owner's own values may never take a name rundesk decided.** The rule is asked as *is this name
already spoken for*, against the environment as it has just been built, so it cannot come apart from
the builder as the builder grows — and a variable added here is protected from the moment it lands,
with nobody re-running anything.
"""

from pathlib import Path
from typing import Dict, Mapping, Optional

from rundesk.core import adapters, config, paths, secrets

#: Where a turn stands, and what stands beside it. The agent's own home, so the brain discovers the
#: files it lives by because **they are in the directory it is in** — that is the whole mechanism,
#: and the one thing every measured brain does natively.
CWD = "RUNDESK_CWD"

#: The directory this (agent, provider) may keep things in between turns: configuration, a sign-in,
#: session files. Named, never made — see `adapters.home`.
PROVIDER_HOME = "RUNDESK_PROVIDER_HOME"

#: Which turn this is, for anything the adapter keeps of its own. The turn's own id, so an adapter
#: writing a running total down beside it has a key that means something afterwards.
RUN = "RUNDESK_RUN"

#: Which agent this is. A turn id is unique inside one agent and names nobody outside it, so without
#: this a command run from inside a turn could tell that it was in one and not whose.
AGENT = "RUNDESK_AGENT"

#: How much of the machine this turn may touch — `read` or `work`. **A request, not containment.**
#: rundesk enforces nothing and has no way to; an adapter maps it onto whatever its brain really has,
#: or ignores it. Anything that described this as a boundary would be claiming a guarantee nobody
#: can keep.
ACCESS_MODE = "RUNDESK_ACCESS_MODE"

#: Which install this turn belongs to. **An agent runs `rundesk` from inside its own turn** — to read
#: its own history back, or to answer a question about this machine — and without this it reads the
#: default `~/.rundesk` rather than the install running it. Measured: a turn on a scratch install ran
#: `rundesk messages` and was told `cody is not an agent on this install` about the agent speaking.
#:
#: **Derived from `paths.home()`, never inherited.** This process may have the variable unset and
#: still resolve `~/.rundesk`, so carrying it through from the environment would carry nothing in the
#: ordinary case. `schedules.firing` and `gateways.job` already derive it for the two other
#: environments this product builds — a turn was the third, and it was the one left out.
#:
#: `paths.HOME_IS` rather than the string, because a second spelling of the only location this
#: product reads is the defect `core.paths` exists to have ended, in miniature.
INSTALL = paths.HOME_IS

#: The `rundesk` to run, as a whole path. **Not a convenience over `PATH` — the thing that works when
#: `PATH` does not.** One measured brain hands its own shell a `PATH` rebuilt from the owner's login
#: profile, so the directory `_reachable` puts in front is simply gone by the time an agent types
#: anything and a bare `rundesk` exits 127 on a healthy install. Environment variables it leaves
#: alone, so a name carrying the whole path survives where a path entry does not.
#:
#: `config.the_command()`, which is already the one answer to which `rundesk` this install means —
#: two answers is how a machine with two installs comes to reach one from a turn and the other from
#: a schedule.
COMMAND = "RUNDESK_COMMAND"

#: Where this agent's skills stand. **Where they are, not which brain looks where** — every measured
#: brain discovers skills itself and each reads a directory of its own, so what is presented and
#: where is the adapter's. Named rather than left to be worked out from the working directory, so an
#: adapter never holds a copy of rundesk's layout.
SKILLS = "RUNDESK_SKILLS"

#: `NAME=verb,…` — which of the files beside the agent are the ones it lives by, and what changing
#: one is called. Told for the same reason skills are: an adapter holding these names would silently
#: stop reporting them the day one is renamed here.
CONTINUITY = "RUNDESK_CONTINUITY"

#: Somewhere to append everything the *brain* said, verbatim. Offered, never required — an adapter
#: that ignores it is a whole adapter. Worth using: rundesk sees what the **adapter** reported and
#: never what the brain said, so a vendor changing its stream shape otherwise shows up as records
#: quietly going missing with nothing at all to compare against.
RAW = "RUNDESK_RAW"

#: The model asked for, or unset. A name the adapter understands, which rundesk does not enumerate.
MODEL = "RUNDESK_MODEL"

#: The handle this conversation got to last time on this brain, or unset for a new one.
RESUME = "RUNDESK_RESUME"

#: Which delegation this turn is answering, or unset when it is answering nobody. **Set only on a
#: turn another agent asked for**, and it is what makes depth one enforceable: a `rundesk ask` run
#: from inside one reads this and refuses, so work handed over cannot be handed on again.
#:
#: A correctness guard and not a security boundary — a brain determined to get around it can clear a
#: variable, and an agent already has the owner's shell. What it prevents is an honest mistake.
ANSWERING = "RUNDESK_DELEGATION"

#: Whatever the owner set, as one JSON object, with no keys rundesk defines. Written sorted, so the
#: same settings are the same bytes every turn and one turn can be compared with another.
SETTINGS = "RUNDESK_SETTINGS"

#: What rundesk wants said to the brain before it reads a word of the task. **Appended to whatever
#: the brain has for adding to its instructions, and never mapped onto anything that replaces its
#: system prompt** — measured on one brain, the replacing flag takes about 6,100 tokens of that
#: brain's own instructions with it, nothing reports that, the tools keep working, and the turn
#: merely behaves differently, which is the failure mode that gets blamed on the model.
PREFACE = "RUNDESK_PREFACE"

#: Which files an agent lives by, and what changing one is called. The names are rundesk's — they are
#: what a new agent is given — so the mapping belongs here rather than in an adapter, which knows
#: about a brain and nothing about what an agent is made of.
#:
#: **A file's name is not the test.** Every repository on the machine has an `AGENTS.md`; an agent
#: editing one in a checkout has not rewritten its own rules, and saying it did is worse than the
#: plain `edit` it would otherwise get, because it is untrue. What qualifies is the resolved path
#: standing directly in `RUNDESK_CWD`.
#:
#: **Exactly what `agents.pages` places, and nothing more.** It named a `SOUL.md` as well, which no
#: release ever wrote: every turn told every brain the agent lived by a file that was not there, and
#: an edit to one would have been classified as `identity` on a machine where nothing could produce
#: one. A name here is a promise that the file exists, so the two lists are compared by
#: `tests/test_layers.py` rather than kept in step by hand. `identity` stays in the ten words an
#: adapter may report — the vocabulary is the protocol's, and this is only which files rundesk gives.
LIVES_BY = {
    "AGENTS.md": "rules",
    "MEMORY.md": "memory",
}


def for_turn(*, agent: str, home: Path, provider_home: Path, skills: Path, turn: int,
             access_mode: str, raw: Optional[Path] = None, model: Optional[str] = None,
             resume: Optional[str] = None, settings: Optional[str] = None,
             preface: str = "", owners: Optional[Mapping[str, str]] = None,
             answering: Optional[str] = None) -> Dict[str, str]:
    """Everything an adapter is told about this turn.

    Keyword-only throughout, and deliberately: this has thirteen things to say and a caller that got
    two of them the wrong way round would hand a brain the wrong agent's home without anything going
    wrong until much later.

    `owners` is the owner's own values, already produced. Handed in rather than read here because
    producing one may run somebody else's program, and this is called from inside a turn.
    """
    said = adapters.environment({
        CWD: str(home),
        PROVIDER_HOME: str(provider_home),
        SKILLS: str(skills),
        # **Derived here rather than taken as arguments.** Which install is running and where its
        # command stands are facts of this process, not of the turn — a caller asked for them is a
        # caller that can leave one out, which is exactly what `schedules.firing` records happening
        # when this product had several location variables and a job carried the wrong subset.
        INSTALL: str(paths.home()),
        COMMAND: config.the_command(),
        RUN: str(turn),
        AGENT: agent,
        ACCESS_MODE: access_mode,
        CONTINUITY: ",".join(f"{name}={verb}" for name, verb in sorted(LIVES_BY.items())),
    })
    # **Absent rather than empty**, each of them. See the module docstring — and for `ANSWERING` it
    # is the whole mechanism rather than a tidiness: a turn nobody delegated must not carry the
    # variable at all, because what reads it treats *present* as "this work was handed to you".
    for name, value in ((MODEL, model), (RESUME, resume), (SETTINGS, settings),
                        (RAW, str(raw) if raw is not None else None),
                        (ANSWERING, answering), (PREFACE, preface.strip() or None)):
        if value:
            said[name] = value
    said["PATH"] = _reachable(said.get("PATH", ""))
    return _also_the_owners(said, owners)


def _reachable(inherited: str) -> str:
    """`PATH`, with this install's own command directory in front of it.

    **An agent runs `rundesk` from inside its own turn** — to read its history back before answering
    a question about work it has no record of — so the command has to be reachable, and it has to be
    *this* install's rather than another one on the same machine.

    Recorded at install time rather than derived, because where the command was linked is a thing the
    owner chose. It is the exact shape of a prior failure worth naming: a fresh machine reported a
    working brain as "not on this machine's path" while the owner's own shell found it perfectly
    well, because the product had installed itself into a directory it then refused to look in.
    """
    front = []
    for at in config.where_the_command_stands():
        if at.is_dir() and str(at) not in front:
            front.append(str(at))
    return ":".join([*front, inherited]) if inherited else ":".join(front)


def _also_the_owners(said: Dict[str, str], owners: Optional[Mapping[str, str]]) -> Dict[str, str]:
    """The owner's own values, and **never over one of rundesk's**.

    Asked as `name not in said` rather than against a list kept here: whatever rundesk has just
    decided a program is told is exactly what a value may not be called, so the two cannot come apart
    however this file grows, and a name added above is refused from the moment it lands.

    Sorted, so the same set is the same bytes every start and one turn can be compared with another.
    """
    for name in sorted(owners or {}):
        if name not in said:
            said[name] = owners[name]
    return said


def owners_own() -> Dict[str, str]:
    """Every value this install keeps, for handing to a turn. **Never printed, never logged.**

    **Every one of them, and not scoped per agent.** A channel names the secrets it may have,
    because it is a program reaching one platform on the owner's behalf; a brain under `work` access
    already reads the owner's files and runs their shell, so an allowlist here would be a boundary
    that is not one — the same values are on disk a moment later. Decided by the owner, recorded
    here and in `docs/providers.md`, and said plainly rather than implied: an agent's brain can see
    every credential this install holds, including another provider's and a channel's.

    Produced once per turn by whoever admits it, and passed in — asking twice is two prompts in front
    of whoever keeps a vault that wants one, and a brain restarted mid-turn must be started with what
    the first one had rather than with whatever the vault says a minute later.

    A value that cannot be read is left out rather than raising. One unreadable value must not make
    every agent on this machine mute, **including the one somebody would ask to fix it** — and the
    turn writes down which names were not given, so the absence is visible rather than mysterious.
    """
    given = {}
    for name, held in secrets.kept().items():
        if held.value is not None:
            given[name] = held.value
    return given


def unreadable() -> list:
    """Which kept values could not be read at all, by name only.

    **Not the same as a value somebody deliberately emptied**, which `secrets.Held` keeps apart on
    purpose: an emptied name is a decision and there is nothing to report about it, while one that
    cannot be read is a fault a turn should say it ran without.

    **The name and never the keeper's own words.** A keeper that fails routinely prints what it was
    reading, and what a turn writes down stands under the data root, which a backup copies whole —
    the one place that must stay free of credentials. `rundesk env check <name>` shows the rest at a
    terminal, where nothing writes it down.
    """
    return sorted(name for name, held in secrets.kept().items() if held.trouble is not None)
