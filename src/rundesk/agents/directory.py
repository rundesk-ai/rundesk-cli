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
from pathlib import Path
from typing import Any, List

from rundesk.agents import pages
from rundesk.agents.records import beside, stated
from rundesk.core import paths
from rundesk.utils import files, locking

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

#: A transient one-shot update handoff. Backups omit it so restoring owner data cannot replay one.
UPDATE_INTENT = "gateway-update.json"

#: What a firing leaves beside itself: the lock the running one holds, what started it, and what it
#: wrote. Inside the agent's directory, never beside it — the same rule as `gateway.lock`, and for
#: the same reason: `<schedule>.lock` inside `foo/` and inside `foo.log/` are two different files,
#: and no list anywhere has to say so.
SCHEDULES = "schedules"

#: What each configured channel keeps, one directory per channel:
#:
#:     channels/discord/lock                   the claim, held by the adapter for as long as it runs
#:     channels/discord/record.json            the pid, so a gateway can stop one it did not start
#:     channels/discord/stderr.log             what the adapter could not say in words; rotated
#:     channels/discord/in/<day>/<message>/    what arrived, swept by day
#:
#: **A channel is named for its adapter until there are two of them.** Adding Discord gives a channel
#: called `discord`; a second place on the same platform is the only thing that needs a name of the
#: owner's, because a private message and a room full of people carry different lists of who may
#: reach the agent and are therefore two channels rather than one that branches.
#:
#: **Three of those four are what a firing already keeps** — a lock, a record beside it, and the
#: output nothing else captures — so this is the existing shape rather than a new one. The fourth is
#: the reason a channel gets a directory where a firing gets three suffixed names: what arrives has
#: to land somewhere, and once there is a directory anyway, the next thing a channel needs is a name
#: inside it rather than another suffix that no channel may then be called.
#:
#: A directory under `channels/` rather than at the top of the agent's, for the reason `SCHEDULES`
#: gives: a channel's name is the owner's, and `dm.lock` beside `gateway.lock` would make every
#: fixed name a name no channel may have.
CHANNELS = "channels"

#: The note the install writes into `data/agents/`, and therefore a name no agent may have.
#: Where each (agent, provider) keeps whatever it keeps between turns — a sign-in, session files, a
#: running total it subtracts against. **Named to the adapter and never made by rundesk**: a real
#: brain pointed at a directory does not merely keep a sign-in there, it builds its whole state tree,
#: to tens of megabytes an agent.
PROVIDERS = "providers"

#: Where each exchange keeps its claim and the two files appended across its turns. One directory per
#: conversation rather than per turn: an agent taking fifty turns a day would otherwise leave seventy
#: thousand files a year, which is an accumulation rather than a layout.
CONVERSATIONS = "conversations"

NOTE = "README.md"

_HOME_NOTE = """# home/

Where **{name}** starts, and what {name} reads.

**If you are {name}, this directory is yours.** Put what you keep between turns in here; nothing
rundesk does tidies it, and no other agent has a reason to read it.

Use `plans/`, `research/`, `scripts/`, `retros/`, and `tasks/` for agent-owned work; the README in
each explains its boundary. Keep project-owned work in its project and disposable scratch temporary.

Written once, when this agent was made. Your own notes belong in a file of your own, beside this one.
"""


class Refused(Exception):
    """Something that may not be done to an agent, named with why.

    A sentence rather than a code, because every caller has to tell somebody what to type instead,
    and a caller left to invent that wording is a caller that invents a different one.
    """


def where(name: str) -> Path:
    """This agent's own directory: everything it is, in one place.

    **Refused when the name reaches somewhere else.** Checking the name is not enough, and this was
    measured rather than reasoned about: with `data/agents/cole` replaced by a symbolic link to
    another directory, `forgotten("cole")` removed that directory's `home/` and `logs/` — every
    individual removal below was correct, every one refused to follow a link, and the whole thing
    still reached a directory that had nothing to do with rundesk. The guard has to be here, on the
    way *in*, because by the time a path has been derived it is already outside.

    So the resolved directory has to stand directly under the resolved agents directory. Resolved on
    both sides: `data/agents` may itself be reached through a link — `/tmp` is `/private/tmp` on this
    platform — and comparing what was typed would refuse an ordinary install.

    A name nothing stands under yet resolves to itself, so making an agent passes and creating one
    over a link does not.

    The build this replaces had the same check and said the same thing about it: a name that does not
    stand where agents are kept is not that agent's name, whatever it looks like.
    """
    at = paths.agents() / name
    if files.escapes(at, paths.agents()):
        raise Refused(
            f"{name} does not stand where agents are kept — it reaches {at.resolve()}")
    return at


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


def schedules(name: str) -> Path:
    """Where this agent's firings keep their locks, their records and what they wrote.

    A directory of its own rather than three names beside `state.db`, because there is one set of
    these per schedule and a schedule's name is the owner's: putting them at the top of the agent's
    directory would put `nightly.lock` next to `gateway.lock` and make every future fixed name a
    name no schedule may have.
    """
    return where(name) / SCHEDULES


def channels(name: str) -> Path:
    """Where this agent's channels keep their locks, their records and what arrived through them.

    Made by whatever first writes into it rather than when the agent is made, because an agent with
    no channels configured should not carry an empty directory saying it might have.
    """
    return where(name) / CHANNELS


def providers(name: str) -> Path:
    """Where this agent's brains keep what they keep. Made by whatever first writes into it."""
    return where(name) / PROVIDERS


def conversations(name: str) -> Path:
    """Where this agent's exchanges keep their claims and their streams."""
    return where(name) / CONVERSATIONS


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


#: How long what an agent is for may be. **Short because every agent's costs every other agent's
#: prompt**: what this install has is listed for whoever might delegate, so ten agents at a thousand
#: characters would be ten thousand characters charged to every turn any of them ever takes. One
#: sentence is what the listing is for, and a paragraph there is somebody using the wrong field.
DESCRIBES_AT_MOST = 200


def describes_trouble(said: str) -> str:
    """Why `said` may not be what an agent is for, or `""` when it may.

    Says the limit **and the length given**, because a refusal that names only the rule leaves
    somebody counting characters by hand to find out how far over they are.
    """
    if len(said) > DESCRIBES_AT_MOST:
        return (f"what an agent is for goes in one sentence — at most {DESCRIBES_AT_MOST} "
                f"characters, and this is {len(said)}")
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
                  if not files.staged(one.name)
                  and not one.is_symlink()
                  and (one / RECORDS).is_file())


def not_an_agent(name: str) -> str:
    """Why this name is not an agent on this install, or `""` when it is.

    Asked of `known`, which is the one answer to what an agent is — a directory holding `state.db`.
    A check written against the directory merely existing would accept a half-made one and a
    directory somebody made by hand, and both are things to be told about rather than operated on.

    **Here rather than beside the verbs that ask it.** Three command groups need this same sentence
    before they touch an agent, and two had already written it out identically; the third would have
    been the third copy. What an agent *is* belongs to this module, and so does the sentence for a
    name that is not one — `taken` beside it already answers the mirror question for a name that
    cannot be used, in the same shape.
    """
    try:
        there = known()
    except OSError as why:
        return str(why)
    if name in there:
        return ""
    return f"{name} is not an agent on this install"


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


def made(name: str, provider: str, describes: str = "", role: str = pages.DEFAULT_ROLE) -> Path:
    """Make an agent, and hand back the directory it stands in.

    `describes` is what this agent is for, in one sentence, and it is optional because an install
    that predates the field has none and a made-up one would read as something its owner wrote.
    What it is *used* for is the listing another agent reads before delegating — see
    `providers.instructions`.

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

    **Held under the install's own lock, because staging alone is not enough here.** The staged name
    is derived from the agent's name, so two makes of the *same* name build in the same place: the
    second `discard`s the first's directory out from under it. Measured, and worse than it sounds —
    of five concurrent pairs, three ended with **no agent at all**, both callers having destroyed
    each other's work, and every loser got a bare `FileExistsError` from the rename instead of a
    sentence saying the name was taken. The same lock every other durable write in this product
    takes, for the same reason: `config.stated_all` and `config.fill_in` already hold it.
    """
    # Imported here rather than at the top of the file. `migration` reads an agent's paths through
    # this module, and making an agent is the single place the traffic goes the other way; a
    # module-level import in both directions is a cycle, and one deferred import at the one call
    # site is the smaller price. Everything else in this file stands on its own.
    from rundesk.agents import migration

    if not provider or not provider.strip():
        raise Refused(f"{name} needs a provider — an agent with nothing behind it cannot answer")
    trouble = describes_trouble(describes or "")
    if trouble:
        raise Refused(trouble)
    if role not in pages.ROLES:
        raise Refused(f"role must be one of {', '.join(pages.ROLES)}, and was {role!r}")

    agents = paths.agents()
    agents.mkdir(parents=True, exist_ok=True)
    with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
        # Asked *inside* the lock. Asking outside it is the same two-decisions-with-a-gap the
        # gateway's own claim exists to close: both callers would be told the name was free, and
        # both would go on to build under it.
        trouble = taken(name)
        if trouble:
            raise Refused(trouble)
        return _built(name, provider, describes or "", role, agents, migration)


def _built(name: str, provider: str, describes: str, role: str, agents: Path,
           migration: Any) -> Path:
    """Build the agent under a staged name and rename it into place. Held by `made`'s lock."""
    building = files.incoming_of(agents / name)
    files.discard(building)

    try:
        (building / HOME).mkdir(parents=True)
        (building / HOME / NOTE).write_text(_HOME_NOTE.format(name=name), encoding="utf-8")
        # The files this agent lives by, placed **inside the staging** and under the agent's own
        # name rather than the staged one — they are what the agent reads, so they say what it is
        # called and never where it was built. An agent that reached its first turn without them
        # would be one told by every prompt to read files nothing had written.
        #
        # **A release that ships none does not stop an agent being made**, which is the same
        # judgement `commands.agents` makes about the skill every agent holds: the fault is in the
        # tree this was run from, not in the agent, and refusing to make one would leave somebody
        # with a broken checkout unable to do anything at all. It is never silent — the command
        # layer asks `pages.wanted` afterwards and says which are missing. An `OSError` is not
        # caught here: that is this staging failing to be written, and half a home is not an agent.
        try:
            pages.place(building / HOME, name, role=role)
        except pages.Missing:
            pass
        (building / LOGS).mkdir()
        # Carried under the staged name, because that is where this agent's directory actually is
        # until the rename. The runner asks this module where an agent's things stand, so the name
        # it is given is the name of the directory it works in — there is no second answer to keep
        # in step, and nothing has to be told that a make is in flight.
        gone_wrong = migration.carry_one(building.name)
        if gone_wrong:
            raise Refused(f"{name} could not be made: {gone_wrong}")
        migration.stamp_without_running(building / RECORDS)
        # `describes` only when there is one. Writing `""` would be indistinguishable from an owner
        # who deliberately said nothing, and the listing has to be able to tell an agent nobody has
        # described from one described as nothing.
        said = {"agent_name": name, "provider_name": provider}
        if describes.strip():
            said["describes"] = describes.strip()
        said["role"] = role
        stated(building / RECORDS, said)
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

    **Held under the install's own lock, the same one `made` and a carry take.** A removal is a
    durable write like any other, and the one it collides with is a carry of the same agent: the
    carry copies the agent aside, the removal takes the agent away, the carry's step then fails and
    puts everything back — so the removal reports an agent gone that is standing there again. With
    the lock the two take turns, and whichever is second sees what the first actually did.
    """
    trouble = name_trouble(name)
    if trouble:
        raise Refused(trouble)
    with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
        return _forgotten(name)


def _forgotten(name: str) -> List[Path]:
    """Everything `forgotten` promises, with the lock already held."""
    at = where(name)
    if not at.is_dir():
        raise Refused(f"{name} is not an agent on this install")

    gone: List[Path] = []
    for one in beside(records(name)):          # state.db, and the two files SQLite keeps with it
        gone.extend(_removed(one))
    gone.extend(_removed(home(name)))
    gone.extend(_removed(logs(name)))
    gone.extend(_removed(schedules(name)))
    gone.extend(_removed(channels(name)))
    gone.extend(_removed(providers(name)))
    gone.extend(_removed(conversations(name)))
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
    """Take one named thing away, and say what went. Raises if it would not go.

    The removal itself is `utils.files.remove_one`, including the part that matters — a symlink goes
    as a link and is never followed. What is decided here is only what to do when it will not go:
    the `OSError` reaches the caller rather than being counted as tidy, because a removal that did
    not happen is never reported as one, and this is the list somebody reads to know what is gone.
    """
    return [one] if files.remove_one(one) else []
