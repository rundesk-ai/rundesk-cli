"""Where one agent's things stand, what makes a directory an agent, and adding or removing one.

One directory per agent, named as that agent is, standing under `data/agents/`:

    data/agents/<name>/
      state.db      what makes this directory an agent
      home/         where the agent starts
      logs/         where its gateway writes

## Every file an agent has is inside the agent's own directory

The names are fixed — `state.db`, `home`, `logs`, `gateway.lock`, `gateway.json` — and they are the
same for every agent, because they are *inside* that agent's directory and nothing else is in there
to collide with.

The build this replaces put those beside the name instead: `<name>.lock`, `<name>.log`,
`<name>.json`, all in one flat directory next to `<name>/`. Which means an agent called `foo.log`
and an agent called `foo` want one file between them — one agent's log is the other agent's whole
existence. It grew a whole `reserved_suffixes()` machinery for that: the gateway published every
suffix it might ever write, the name checker read the list back and refused any name whose first
segment matched, and the list had to stay true through every sidecar anybody added afterwards. All
of it existed to make a flat namespace safe.

**This design deletes that entire class of problem rather than defending against it.** There is
nothing to publish, nothing to keep in step, and no name that can be refused for looking like
somebody else's file. `gateway.lock` inside `foo/` and `gateway.lock` inside `foo.log/` are two
different files, and no list anywhere has to say so.

## What makes a directory an agent

`state.db`, and only that. Not the directory existing — a half-made one exists — and not its home
or its logs, which an owner could have made by hand. The records are what a step created and what
everything else about that agent is kept in, so a directory without them has never been an agent
and a listing that counted it would offer somebody an agent that cannot answer.

Everything here is derived from `paths.agents()` on every call and cached nowhere: the one root is
the only location this product reads, and a path bound at import is how a suite comes to write into
the owner's live install.
"""

import os
import shutil
from pathlib import Path
from typing import List

from rundesk.agents.records import beside, stated
from rundesk.core import paths
from rundesk.utils import files

#: The records that make this directory an agent.
RECORDS = "state.db"

#: Where the agent starts, and what is the owner's to put things in.
HOME = "home"

#: Where this agent's gateway says what it has been doing.
LOGS = "logs"

#: Held by the one gateway running this agent. Inside the agent's directory, never beside it.
GATEWAY_LOCK = "gateway.lock"

#: What the running gateway wrote down about itself. Inside the agent's directory, never beside it.
GATEWAY_RECORD = "gateway.json"

#: The note the install writes into `data/agents/`, and therefore a name no agent may have.
NOTE = "README.md"

_HOME_NOTE = """# home/

Where **{name}** starts, and what {name} reads.

**If you are {name}, this directory is yours.** Put what you keep between turns in here; nothing
rundesk does tidies it, and no other agent has a reason to read it.

Written once, when this agent was made. Your own notes belong in a file of your own, beside this one.
"""


class Refused(Exception):
    """Something that may not be done to an agent, named with why.

    A sentence rather than a code, because every caller has to tell somebody what to type instead,
    and a caller left to invent that wording is a caller that invents a different one.
    """


def where(name: str) -> Path:
    """This agent's own directory: everything it is, in one place."""
    return paths.agents() / name


def records(name: str) -> Path:
    """The database this agent keeps — and the one thing that makes the directory an agent."""
    return where(name) / RECORDS


def home(name: str) -> Path:
    """Where this agent starts.

    A directory of its own inside the agent's rather than the agent's directory itself, so that what
    an owner or an agent writes is never mixed in with the records, the log and the lock rundesk
    keeps beside it — and so an uninstall that keeps what is the owner's has one thing to name.
    """
    return where(name) / HOME


def logs(name: str) -> Path:
    """Where this agent's gateway writes."""
    return where(name) / LOGS


def gateway_lock(name: str) -> Path:
    """The file one gateway at a time holds for this agent."""
    return where(name) / GATEWAY_LOCK


def gateway_record(name: str) -> Path:
    """What a running gateway wrote down about itself."""
    return where(name) / GATEWAY_RECORD


def name_trouble(said: str) -> str:
    """Why `said` may not be an agent's name, or `""` when it may.

    `utils.files.name_trouble` is the whole of the general answer — empty, a separator, a leading
    dot, a control character, too long for a filesystem to hold — and it is reused rather than
    reimplemented, because a second opinion about what a name may be is a second set of rules for
    somebody to fall between.

    One thing is added, and it belongs here rather than down there: **`README.md` is the note the
    install writes into `data/agents/`**, so an agent by that name would want the same entry the
    note already has. Compared without case, because the volume a Mac ships with does not tell
    `readme.md` and `README.md` apart and the collision is the same one either way.
    """
    trouble = files.name_trouble(said)
    if trouble:
        return trouble
    if said.lower() == NOTE.lower():
        return (f"{NOTE} is the note rundesk keeps in the agents directory, "
                "so it cannot also be an agent")
    return ""


def known() -> List[str]:
    """Every agent this install has, sorted by name.

    **An agent is a directory holding `state.db`.** So a stray file, a directory somebody made by
    hand, and a half-made one that never got as far as its records are all skipped — a listing that
    counted them would offer somebody an agent that cannot answer.

    Anything `utils.files.staged` recognises is skipped before that, because a name being built is
    not a name at all yet, and it would otherwise be listed for the moment between a make starting
    and finishing.

    **No agents is an answer, not a failure.** An install where nobody has added one yet says so,
    and so does one whose agents directory has not been laid down yet — that happens before the
    first install has run and is ordinary. A directory that is there and cannot be read is a
    different thing and is left to raise, because answering "none" would tell somebody their agents
    are gone at the moment they are merely unreadable.
    """
    at = paths.agents()
    if not at.is_dir():
        return []
    return sorted(one.name for one in at.iterdir()
                  if not files.staged(one.name) and (one / RECORDS).is_file())


def taken(name: str) -> str:
    """Why this name may not be used for a new agent, or `""` when it may.

    Three refusals, in the order that gives the most useful sentence.

    A name that could never be a directory is refused first — there is no point telling somebody
    what their name collides with when the trouble is the name itself.

    Then **a name that differs from an existing agent's only by case**. The volume macOS ships with
    is case-insensitive, so `Cole` and `cole` are one directory: allowing both would give two agents
    one `state.db`, each writing over the other's memory, with nothing anywhere saying so. The
    refusal names the agent that is already there, because that is the fact the person needs — and
    the name they typed is left exactly as they typed it. Nothing here slugs, folds or renames a
    name on somebody's behalf; an agent whose name is not the name its owner chose is a surprise
    that surfaces months later in something they have to type.

    Then anything else already standing under that name, which is not an agent and is therefore
    something a person has to look at rather than something to be replaced.
    """
    trouble = name_trouble(name)
    if trouble:
        return trouble
    for standing in known():
        if standing == name:
            return f"{name} is already an agent"
        if standing.lower() == name.lower():
            return (f"{standing} is already an agent, and this machine may not tell {standing} and "
                    f"{name} apart — they would be one directory sharing one {RECORDS}")
    at = where(name)
    if at.exists() or at.is_symlink():
        return f"{at} is already there and is not an agent, so rundesk will not write over it"
    return ""


def made(name: str, provider: str) -> Path:
    """Make an agent, and hand back the directory it stands in.

    **All of it is built under a staged name and renamed into place once, at the end.** An
    interruption anywhere before that rename leaves `.<name>.incoming` — litter, which `known`
    skips and the next make discards — and never a directory standing under the agent's own name
    that looks like an agent and is not. Half an agent is worse than none, because it is the one
    somebody reaches for.

    The records are built by **running the first migration step against nothing**, and then every
    later step this release ships is stamped without being run — the same thing a fresh install
    does, for the same reason. The schema is never laid down by executing DDL from `records`: there
    would then be two descriptions of what an agent's records are, and the one the migration runner
    knows about is the one every agent on every machine is measured against.
    """
    # Imported here rather than at the top of the file. `migration` reads an agent's paths through
    # this module, and making an agent is the single place the traffic goes the other way; a
    # module-level import in both directions is a cycle, and one deferred import at the one call
    # site is the smaller price. Everything else in this file stands on its own.
    from rundesk.agents import migration

    trouble = taken(name)
    if trouble:
        raise Refused(trouble)
    if not provider or not provider.strip():
        raise Refused(f"{name} needs a provider — an agent with nothing behind it cannot answer")

    agents = paths.agents()
    agents.mkdir(parents=True, exist_ok=True)
    building = agents / files.INCOMING.format(name=name)
    files.discard(building)

    try:
        (building / HOME).mkdir(parents=True)
        (building / HOME / NOTE).write_text(_HOME_NOTE.format(name=name), encoding="utf-8")
        (building / LOGS).mkdir()
        # Carried under the staged name, because that is where this agent's directory actually is
        # until the rename. The runner asks this module where an agent's things stand, so the name
        # it is given is the name of the directory it works in — there is no second answer to keep
        # in step, and nothing has to be told that a make is in flight.
        gone_wrong = migration.carry_one(building.name)
        if gone_wrong:
            raise Refused(f"{name} could not be made: {gone_wrong}")
        migration.stamp_without_running(building / RECORDS)
        stated(building / RECORDS, {"agent_name": name, "agent_provider": provider})
        at = agents / name
        os.replace(building, at)
    except BaseException:
        # Whatever went wrong — a step, a full disk, somebody pressing ctrl-c — what is left is
        # litter under a staged name and never a directory wearing the agent's own name.
        files.discard(building)
        raise
    return at


def forgotten(name: str) -> List[Path]:
    """Take an agent away, one named thing at a time. Returns what was removed.

    **Named, never swept and never globbed.** Every entry below is spelled out, and the records'
    `-wal` and `-shm` siblings are spelled out with them — the old build recorded that a glob over
    the database's name misses them, and a stale write-ahead log left beside a database is read by
    the next connection as that database's most recent truth.

    The agent's directory itself is removed only if it is then empty. Anything else standing in
    there is something a person put there, and taking an agent away is not a licence to sweep.

    **This does not check whether a gateway is running.** That is the caller's job, and it has to
    be: `agents` sits below `gateways` and may not import it, and a layer that reached upward to
    ask would be the layer that could no longer be tested on its own. Removing an agent while its
    gateway is up leaves a running program with no records, which is the caller's to prevent.
    """
    trouble = name_trouble(name)
    if trouble:
        raise Refused(trouble)
    at = where(name)
    if not at.is_dir():
        raise Refused(f"{name} is not an agent on this install")

    gone: List[Path] = []
    for one in beside(records(name)):          # state.db, and the two files SQLite keeps with it
        gone.extend(_removed(one))
    gone.extend(_removed(home(name)))
    gone.extend(_removed(logs(name)))
    gone.extend(_removed(gateway_record(name)))
    gone.extend(_removed(gateway_lock(name)))
    try:
        at.rmdir()
    except OSError:
        # Something the owner left in here. Kept, along with the directory holding it.
        return gone
    gone.append(at)
    return gone


def _removed(one: Path) -> List[Path]:
    """Take one named thing away, and say whether there was one. Raises if it would not go.

    A removal that did not happen is never reported as one — that is the rule the whole product is
    built around — so an `OSError` here reaches the caller rather than being counted as tidy.

    A symlink is removed as a link and never followed: an agent's `home` replaced by a link to
    somebody's documents would otherwise have the documents deleted.
    """
    if one.is_dir() and not one.is_symlink():
        shutil.rmtree(one)
    elif one.exists() or one.is_symlink():
        one.unlink()
    else:
        return []
    return [one]
