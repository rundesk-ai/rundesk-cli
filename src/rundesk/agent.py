"""An agent: the named identity rundesk runs work for, and the home it loads from.

An agent is what a person operates. It has a name, a home holding the rules, memory,
workspace and skills it loads, and exactly one gateway that runs it — see
`.knowledge/prd-drafts/agent-home.md` and `agent-gateway.md`.

**Everything that is one agent's lives in one directory.** Before agents, what a gateway
kept was sharded by kind — a run directory, a log directory, a schedules directory — with
the gateway's name as a filename prefix inside each. That is why a gateway named `foo.log`
and one named `foo` want one file between them: a name is only kept apart from its
neighbours by a convention about suffixes. A directory each ends the whole class of
collision, and it makes an agent one thing to look at, copy or take away.

**This module knows about gateways; a gateway knows nothing about agents.** `Gateway` takes
what it uses as arguments — the two directories it writes in, where agents are kept, and the
records it reads its schedules out of — so an agent resolves its own and hands them over. The
dependency runs one way — `cli` -> `agent` -> `gateway` -> `process` — and a gateway that
reached back for an agent would end it.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from rundesk import gateway, store

#: What a new agent's home is copied from. Ordinary Markdown files rather than text built
#: in code, because they are what an owner reads first and edits next, and a rule about how
#: an agent is reached is worth keeping where it can be read.
TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "agent"

#: The one thing substituted on the way in. Everything else is copied as it stands.
NAMED = "{{name}}"

#: The directories inside an agent's home that are the agent's own to work in.
WORKING = "workspace", "skills"


def knowledge() -> tuple[str, ...]:
    """The files an agent's home holds, asked of what they are copied from.

    Read off the directory rather than listed here, so a template added later is written
    into a new agent's home, looked for by a diagnosis and covered by the suite without
    anything being added to a list kept somewhere else.
    """
    if not TEMPLATES.is_dir():
        return ()
    return tuple(sorted(page.name for page in TEMPLATES.iterdir() if page.is_file()))


class NotAnAgentName(ValueError):
    """A name that would not stand where agents are kept, or would claim another's file."""


class InUse(Exception):
    """Something is still using this name, so nothing belonging to it was moved."""


def agents_home() -> Path:
    """Where agents are kept — one directory each, holding everything that is theirs.

    Beside the run and log directories rather than inside either: those hold what rundesk
    wrote before there were agents to own it, and this is what an ordinary uninstall
    preserves because it is the owner's rather than rundesk's (R-AGT-3).
    """
    return Path(os.environ.get("RUNDESK_AGENTS_DIR") or Path.home() / ".rundesk" / "agents")


def checked(name: str) -> str:
    """An agent's name, or why it cannot be one.

    Stricter than a gateway's, and for a reason a gateway does not have: the name becomes a
    directory holding everything the agent is, and it is also the name of the gateway that
    runs it. So it must be one path component (R-AGT-5), and it must not read as a file a
    gateway writes beside some other gateway's name (R-AGT-6) — those suffixes are asked
    for rather than restated, so a sidecar added later is covered the day it lands.
    """
    try:
        gateway.checked(name)
    except gateway.NotAName as why:
        # Said as it comes. What a name may be does not depend on who is asking, so the
        # rule is stated once and neither side rewrites the other's word for it.
        raise NotAnAgentName(str(why)) from None
    claimed = _claimed_stems()
    for part in name.split("."):
        if part in claimed:
            raise NotAnAgentName(
                f"'{name}' would read as a file a gateway writes — '{part}' is one of "
                f"{', '.join(sorted(claimed))}"
            )
    return name


def _claimed_stems() -> frozenset[str]:
    """The first word of every suffix a gateway writes after a name.

    A gateway writes `<name>.log`, so an agent called `x.log` and a gateway called `x` would
    want one file between them. Read off what the gateway says it writes, because a list of
    these kept here is a list that stops being true.
    """
    return frozenset(
        suffix.lstrip(".").split(".")[0] for suffix in gateway.reserved_suffixes() if suffix
    )


def directory(name: str, where: Path | None = None) -> Path:
    """Everything this agent is, in one place.

    Both halves of "stands where agents are kept" are asked here (R-AGT-5): the name is one
    component, and the path it makes still has the agents directory as its parent once the
    machine has resolved it. The second catches what the first cannot — a link already
    standing under that name, pointing somewhere else entirely. Both sides are resolved,
    because the agents directory is itself often reached through a link.
    """
    where = where or agents_home()
    stands = where / checked(name)
    if stands.resolve().parent != where.resolve():
        raise NotAnAgentName(
            f"'{name}' does not stand where agents are kept — it reaches {stands.resolve()}"
        )
    return stands


def home(name: str, where: Path | None = None) -> Path:
    """The agent's home: what it loads, and nothing rundesk wrote (R-AGT-2).

    A directory of its own inside the agent's, rather than the agent's directory itself,
    so that what an owner writes is never mixed with the lock, the log and the records
    rundesk keeps beside it. It is also the whole of what an ordinary uninstall preserves.
    """
    return directory(name, where) / "home"


def workspace(name: str, where: Path | None = None) -> Path:
    """Where this agent works when nothing says otherwise. No two agents share one (R-AGT-7)."""
    return home(name, where) / "workspace"


def skills(name: str, where: Path | None = None) -> Path:
    """Where this agent's skills are kept — its own, and not its owner's.

    **No provider discovers a bare `skills/` directory**, and none is claimed to. Probes of
    the installed CLIs found each looks in a directory of its own — `.claude/skills`,
    `.agents/skills`, `.grok/skills` — and that a plain one is read by nobody. Presenting a
    skill where each brain already looks is Phase 12's, and it waits for probes of the
    versions actually installed rather than for a layout that looks right. This is where an
    owner puts one until then.
    """
    return home(name, where) / "skills"


def provider_home(name: str, provider: str, where: Path | None = None) -> Path:
    """The private home a provider is given for this agent, and for no other (R-AGT-8).

    Outside the agent's home on purpose: a provider's configuration, sign-in and session
    history are rundesk-managed state about a pair, not knowledge the agent loads. Kept
    inside the home, a provider reading the agent's rules would be reading its own state.
    """
    return directory(name, where) / "providers" / gateway.checked(provider)


def channel_home(name: str, channel: str, where: Path | None = None) -> Path:
    """The private home a channel is given for this agent, and for no other.

    The same reasoning as a provider's (R-AGT-8), and outside the agent's home for the
    same reason: what a surface must remember between restarts is rundesk-managed state
    about a pair, not knowledge the agent loads. Keyed by the channel's own name rather
    than by its kind, because two Discord channels on one agent are two channels.
    """
    return directory(name, where) / "channels" / gateway.checked(channel)


def run_home(name: str, where: Path | None = None) -> Path:
    """Where this agent's gateway keeps what it is doing now — cleared when it stops."""
    return directory(name, where) / "run"


def logs_home(name: str, where: Path | None = None) -> Path:
    """Where this agent's gateway writes what happened — history, which outlives it."""
    return directory(name, where) / "logs"


def paths(name: str, where: Path | None = None) -> dict[str, Path]:
    """Every place this agent resolves, by what it is for.

    One reader for `agents <agent>` and for diagnosing one, because an owner asking where
    an agent keeps things and a check asking whether it is all there want the same answer,
    and two of them would eventually give different ones.
    """
    return {
        "agent": directory(name, where),
        "home": home(name, where),
        "workspace": workspace(name, where),
        "skills": skills(name, where),
        "providers": directory(name, where) / "providers",
        "run": run_home(name, where),
        "logs": logs_home(name, where),
    }


def made_of(name: str, where: Path | None = None) -> dict[str, Path]:
    """Every directory an agent is made of — everything it resolves but itself.

    The one list that making an agent and diagnosing one both read. Written out at each of
    them instead, the two were a hand-kept copy of this and of each other: a directory added
    here and forgotten in `add` is one a new agent silently never gets, and forgotten in
    `diagnosed` is one whose absence is reported as ready.
    """
    return {what: at for what, at in paths(name, where).items() if what != "agent"}


@dataclass(frozen=True)
class Where:
    """The two directories a gateway of this name keeps things in.

    `None` for each means the ones a gateway kept things in before there were agents to own
    them — which is what every gateway function already falls back to, so a name with no
    agent goes on being reached exactly as it always was.

    It was three. What a gateway is scheduled to do, what each schedule last did and when it
    was last up are rows an agent keeps, so there is no directory left for them to be in.
    """

    run: Path | None
    logs: Path | None


def resolved(name: str, where: Path | None = None) -> Where:
    """Where this name's gateway keeps things.

    One answer, asked once and handed to whatever needs it, because a command resolving
    these itself in three places is how a gateway comes to write somewhere the command that
    configured it does not read (R-AGT-9).
    """
    if not exists(name, where):
        return Where(None, None)
    return Where(run_home(name, where), logs_home(name, where))


def standing_before(name: str, logs: Path | None = None) -> list[Path]:
    """What a gateway of this name wrote before there were agents to own it.

    Read rather than moved, so a command can say what adopting would take on before it
    takes it on, and say nothing at all when there is nothing there.
    """
    return sorted(path for was, _ in _wrote_before(name, logs)
                  for path in _the_file_and_what_it_rotated_into(was))


def known(where: Path | None = None) -> list[str]:
    """Every agent this install has.

    An agent is one that has a home: a removal takes the home and leaves the log behind
    (R-AGW-5), so a directory that still stands is not by itself an agent that still does.
    """
    where = where or agents_home()
    if not where.is_dir():
        return []
    return sorted(
        found.name for found in where.iterdir()
        if found.is_dir() and (found / "home").is_dir()
    )


def exists(name: str, where: Path | None = None) -> bool:
    """Whether there is an agent of this name."""
    try:
        return home(name, where).is_dir()
    except NotAnAgentName:
        return False


def add(name: str, where: Path | None = None) -> list[str]:
    """Make this agent, and the one gateway that runs it (R-AGW-1).

    What is written is what is not already there, and nothing else (R-AGT-4). Making an
    agent that exists is how an owner repairs one they have half deleted, and it must not
    be how they lose the rules they spent a month writing — so a file that is there is left
    exactly as it is, whatever is in it.

    The gateway is the three directories beside the home. There is no separate step and no
    record naming one from the other: an agent's gateway is its name, so the two cannot
    come apart.

    What it keeps is built by walking the steps from nothing rather than by writing the
    tables here, so the migration path is exercised every time anybody makes an agent and
    a fresh install cannot drift from an upgraded one (R-MIG-9). Records already there are
    checked rather than rebuilt, which is what makes making an agent again a repair.
    """
    made = []
    for path in made_of(name, where).values():
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            made.append(path.name + "/")
    for called in knowledge():
        page = home(name, where) / called
        if not page.exists():
            page.write_text(_copied(called, name), encoding="utf-8")
            made.append(called)
    records = store.path_for(directory(name, where))
    fresh = not records.exists()
    store.Store(records).made()
    if fresh:
        made.append(store.NAME)
    return sorted(made)


def adopt(name: str, where: Path | None = None, logs: Path | None = None,
          run: Path | None = None) -> list[str]:
    """Move what a gateway of this name wrote before it had an agent into the agent's own.

    Only ever asked for: nothing here runs on its own, and nothing moves until an owner
    types the name.

    **The name is held for as long as the moving takes**, and nothing moves if it cannot be.
    A gateway binds the directory it writes in once, when it starts, and never looks again —
    so moving those files out from under a live one leaves it writing where nothing reads for
    the rest of its life. Asking whether it is running and then moving is two decisions with a
    gap between them, and a gateway can claim the name inside that gap; holding the name is
    what makes them one (R-AGT-9).

    The log moves, and the account of what the gateway never finished with it; what the
    gateway was *doing* does not, because a stopped gateway is not doing anything and its
    lock is an empty file whose name the next claim makes again.
    """
    goes = {"logs": logs_home(name, where)}
    moved = []
    with gateway.holding(name, run) as held:
        if not held:
            raise InUse(
                f"a gateway named '{name}' is still running, so nothing of its was moved")
        for was, into in _wrote_before(name, logs):
            for path in _the_file_and_what_it_rotated_into(was):
                goes[into].mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(goes[into] / path.name))
                moved.append(path.name)
    return sorted(moved)


def _wrote_before(name: str, logs: Path | None):
    """Each thing a gateway of this name wrote before it had an agent, and which of an
    agent's own directories it belongs in.

    One list, so what adopting says it would take on and what adopting takes on cannot come
    to disagree — a command that names one file and moves four is worse than either.
    """
    return (
        (gateway.log_path(name, logs), "logs"),
        (gateway.interrupted_path(name, logs), "logs"),
    )


def _the_file_and_what_it_rotated_into(path: Path):
    """This file, and anything a rotation left beside it — `x.log` brings `x.log.1` along."""
    if path.exists():
        yield path
    for beside in sorted(path.parent.glob(f"{path.name}.*")) if path.parent.is_dir() else []:
        if beside.is_file():
            yield beside


def forget(name: str, where: Path | None = None) -> list[str]:
    """Take this agent away, and everything of its own with it (R-AGW-2).

    The home goes with the agent, and so do its records and the private homes providers
    were given: adding the name back otherwise inherits work nobody asked for, from an
    agent that no longer exists (R-AGW-4).

    **And so does the account of what it did** (R-AGW-5). It used to be kept behind a
    second flag, on the argument that a reinstall after trouble is when the account of the
    trouble matters most — but an account nobody can name an agent for is an account
    nobody reads, and what it left behind was inherited by whoever took the name next.
    Taking an agent away takes an agent away.

    `state.db` is named rather than swept up by the glob below, along with the two files
    SQLite keeps beside it: the glob takes `*.json` and `*.changing`, which is none of
    them, and leaving those behind leaves a record of what was deleted.

    The run directory is emptied by the gateway's own removal, which holds the name's lock
    before unlinking it; anything still standing there belongs to something still using it,
    so it is left and not reported as taken.
    """
    stands = directory(name, where)
    taken = []
    for path in (home(name, where), directory(name, where) / "providers",
                 directory(name, where) / "channels"):
        if path.exists():
            shutil.rmtree(path)
            taken.append(path.name + "/")
    # Everything rundesk holds *about* this agent, by where it is rather than by name
    # (R-AGW-4). One rule, because naming the files one by one is a list that has already
    # been wrong once: which brain it reached for and where each conversation got to both
    # outlived the agent and were inherited by the next one to take the name. History is
    # never here — that is in the directories above, and only `--purge` takes it.
    #
    # It matters most for the channels a name was reachable on. An agent added back under
    # a name that was on somebody's server would be on it again, answering whoever was
    # allowed then, without anybody having asked for either.
    for path in sorted(stands.glob("*.json")) + sorted(stands.glob("*.changing")):
        if path.is_file():
            path.unlink()
            taken.append(path.name)
    for path in store.removes(stands):
        if path.exists():
            path.unlink()
            taken.append(path.name)
    for path in (logs_home(name, where),):
        if path.exists():
            shutil.rmtree(path)
            taken.append(path.name + "/")
    for empty in (run_home(name, where), stands):
        try:
            empty.rmdir()
        except OSError:
            pass  # something is still there, and something still there is still someone's
    return sorted(taken)


#: What an agent was made with, kept beside its home rather than inside it. Outside on
#: purpose: which brain answers for an agent is rundesk's record about it, not knowledge
#: the agent loads — a provider reading the agent's rules must not find our configuration
#: sitting among them.
def records(name: str, where: Path | None = None) -> store.Store:
    """What this agent keeps, ready to be written to — built if it is not there yet.

    The one place above the store that knows where an agent's records stand, so a caller
    asks this agent for them rather than building a path of its own.
    """
    kept = store.Store(store.path_for(directory(name, where)))
    kept.made()
    return kept


def reading(name: str, where: Path | None = None) -> store.Store:
    """The same records, for a command that only asks — never built and never repaired.

    Told apart from `records` because the difference is a behaviour rather than a habit:
    `doctor` promises to change nothing (R-AGT-12) and `agents` only lists, and asking
    what shape records are in through anything that may also *make* them turns the command
    an owner runs when something is broken into the one that quietly repairs it.
    """
    kept = store.Store(store.path_for(directory(name, where)))
    kept.understood()
    return kept


def chosen(name: str, where: Path | None = None) -> dict:
    """Which brain answers for this agent, and with what — or nothing decided yet.

    A convenience, never an identity: provider and model are what a turn resolved, and
    this is only what the agent supplies for whatever a turn left out.

    Nothing at all where there is no agent, because `agents` and `doctor` both ask this of
    a name before anything has been made under it. Records that *are* there and cannot be
    read are not nothing and are not answered for here (R-STO-13): the store says so in
    the agent's own log and refuses, because a turn run against a brain nobody chose is
    worse than a turn that did not start.
    """
    try:
        at = store.path_for(directory(name, where))
    except NotAnAgentName:
        return {}
    if not at.exists():
        return {}
    return reading(name, where).agent()


#: What rundesk itself tells every turn, before anything anybody else says (R-AGT-17).
#:
#: **Small, and the same words every time.** It is the front of what a brain is given, which is
#: the part prompt caching keys on — anything that varies per turn belongs after it, never
#: inside it, or every turn pays for a prefix that no longer matches. Only the agent's own name
#: is filled in, so one agent's is byte-for-byte identical from one turn to the next.
#:
#: Said here rather than left to the home an agent loads, because a home is the owner's to edit
#: and this is the one thing that must be true whatever they wrote — an agent that has been
#: given no rules at all still knows what it is running inside and how to find out what it did.
STANDING = """\
You are {name}, an agent running inside rundesk.

Your memory is per conversation; rundesk's record is not. Work you did on a schedule, in \
another chat or in the terminal is written down and is not in your memory here. So when \
something refers to work you cannot place, look it up before answering rather than guessing \
or saying you have no access:

  rundesk messages {name}                      what was said, newest first
  rundesk messages {name} --conversation <id>  this room or direct message alone
  rundesk messages {name} --source schedule    only what the clock started

Narrow before you widen, and say you looked it up rather than implying you remembered. If \
nothing is there, say that. Do this when you cannot place something, not on every message.

Everything else rundesk does is in ~/.rundesk/USING-RUNDESK.md, and `rundesk --help` always \
works."""


def standing(name: str) -> str:
    """Rundesk's own words to a turn, for this agent. One place, so it is one wording."""
    return STANDING.format(name=name)


def told(name: str, where: Path | None = None, said: str = "", otherwise: str = "") -> str:
    """What a turn for this agent is told about its situation, before it reads a prompt.

    **Rundesk's own words first, and then the nearest thing anybody else said** (R-AGT-16,
    R-AGT-17). What an owner writes is *added to* ours rather than replacing it: they are
    answering different questions — ours says what the agent is and how to find out what it
    has done, theirs says what to do about the situation — and an agent that lost the first
    because its owner supplied the second would be told where it is by nobody.

    Among the rest the nearest still wins: the schedule's or the turn's own, then the surface
    it arrived on, then the agent's, then whatever rundesk would have said about that
    situation. `said` is whatever the nearer two came to and `otherwise` is rundesk's own
    sentence about the situation, so every caller hands in what it knows and none of them has
    to know the order.

    Written once because the order is the guarantee. Each caller working it out would be four
    orders that agree until one of them does not, and the way that fails is silent: an agent
    told the wrong thing about where it is answers perfectly well, and wrongly.
    """
    return "\n\n".join(part for part in (standing(name), _situation(name, where, said,
                                                                    otherwise)) if part)


def _situation(name: str, where: Path | None, said: str, otherwise: str) -> str:
    """The nearest thing anybody said about *this* turn's situation, or nothing."""
    if said and said.strip():
        return said
    mine = chosen(name, where).get("instructions")
    if isinstance(mine, str) and mine.strip():
        return mine
    return otherwise


def remember(name: str, where: Path | None = None, provider: str | None = None,
             model: str | None = None, settings: dict | None = None,
             instructions: str | None = None) -> dict:
    """Keep what this agent should reach for when a turn does not say.

    What is not given is left exactly as it was, so naming a model later does not quietly
    forget the brain. Two commands each naming a different half used to read one whole
    file, merge only their own, and write it back — the later one erasing the other's with
    both reporting success. Each names its own columns now, and the read, the decision and
    the write are one transaction rather than one lock file.
    """
    kept = records(name, where)
    kept.remember_agent(provider=provider, model=model, settings=settings,
                        instructions=instructions)
    return kept.agent()


@dataclass(frozen=True)
class Complaint:
    """One thing standing between an agent and a working turn."""

    about: str
    said: str


def diagnosed(name: str, where: Path | None = None, root: Path | None = None,
              runnable=None) -> list[Complaint]:
    """What stands between this agent and a working turn, without starting anything.

    Nothing here starts a provider (R-AGT-11) and nothing here writes (R-AGT-12): an owner
    asking what is wrong is often asking because something is already wrong, and a check
    that repaired what it found would make the next answer a different question's.

    `runnable` is asked whether the brain this agent reaches for is there, and is passed
    in rather than imported: the seam sits above this module, and a diagnosis that reached
    up for it would invert the one dependency rule that matters. It is asked to *find* the
    program and never to run it — what a brain can do is a question for a turn, not for a
    check that promises to start nothing (R-PRV-12).
    """
    found = []
    where_it_is = paths(name, where)
    if not where_it_is["home"].is_dir():
        return [Complaint(str(where_it_is["home"]), "there is no agent of that name here")]
    for what, path in sorted(made_of(name, where).items()):
        if what == "home":
            continue  # asked above, and its absence is "there is no agent", not a fault
        if not path.is_dir():
            found.append(Complaint(str(path), f"the agent's {what} is not there"))
        elif not os.access(path, os.W_OK):
            found.append(Complaint(str(path), f"the agent's {what} cannot be written to"))
    holds = knowledge()
    if not holds:
        # Asked before the files are looked for, because an install with nothing to copy
        # from would otherwise find nothing missing and call a bare home a working agent.
        found.append(Complaint(str(TEMPLATES), "this install has nothing to make an agent from"))
    for called in holds:
        page = where_it_is["home"] / called
        if not page.is_file():
            found.append(Complaint(str(page), "the agent is missing one of the files it loads"))
    unfit = gateway.fitness(root)
    if unfit:
        found.append(Complaint("this install", unfit))
    try:
        named = chosen(name, where).get("provider")
    except (store.Unreadable, store.TooNew, store.Behind) as why:
        # A diagnosis is what an owner runs *because* something is already wrong, so
        # records this rundesk will not read are the answer rather than an exception out
        # of the middle of one. It is reported and the rest of the check still runs.
        found.append(Complaint(str(store.path_for(directory(name, where))), str(why)))
        named = None
    if runnable is not None and named:
        try:
            runnable(named)
        except Exception as why:
            # The detail is what is *about* the complaint and the sentence is what is
            # said, because a diagnosis reads "<what is wrong>: <where>" everywhere else.
            found.append(Complaint(str(why), "the brain this agent reaches for"))
    return found


def _copied(called: str, name: str) -> str:
    """One template, with the agent's name put where the template asks for it.

    A copy and one substitution, so what an owner finds in a new home is what stands in
    `templates/agent/` — editable there, readable as ordinary Markdown, and never a second
    version of the same words held in code.
    """
    return (TEMPLATES / called).read_text(encoding="utf-8").replace(NAMED, name)


@dataclass(frozen=True)
class Reachable:
    """One surface an agent is reachable on, resolved and ready for a gateway to hold.

    Everything a gateway needs and nothing it has to work out: the program to run, what
    it is told, and how to make the thing that carries what arrives on it. Resolved here
    because knowing what an agent is belongs above the gateway, and handed over made
    because a gateway that reached back for an agent would end the direction this whole
    file rests on (R-AGT-9, R-CAD-6).
    """

    name: str
    program: Path
    env: dict
    answering: object


def reachable(name: str, where: Path | None = None, carry=None) -> list:
    """Every channel this agent is reachable on, ready to be held open (R-CAD-6).

    A channel whose kind is not on this machine is left out and said, rather than
    stopping the others: one surface that cannot be run must not make an agent deaf on
    every other one it has.
    """
    from rundesk import answering as answers
    from rundesk import channel as channels

    found = []
    for record in reading(name, where).channels():
        one = record["name"]
        try:
            at = channels.program(str(record.get("kind") or ""))
        except channels.NotRunnable:
            continue
        home = channel_home(name, one, where)
        found.append(Reachable(
            name=one, program=at,
            env=channels.environment(
                home=run_home(name, where), channel=one, agent=name, channel_home=home,
                allow=record.get("allow"), settings=record.get("settings"),
                secret=record.get("secret")),
            answering=_answering(name, one, record, where, carry, answers),
        ))
    return found


def _answering(name, one, record, where, carry, answers):
    """What carries a conversation on this channel, made once the gateway can write back.

    Made rather than passed, because two of the things it needs only exist once the
    gateway is running: how to write back to the adapter, and how to ask for the agent to
    be cycled. Both are handed in, so nothing here reaches down into a gateway and
    nothing there reaches back for an agent.
    """
    def made(sending, restarting=None, note=None):
        return answers.Answering(name, one, record, sending, where=where, carry=carry,
                                 restarting=restarting, note=note)
    return made


def asking(name: str, where: Path | None = None, carry=None):
    """How a gateway admits a turn for a schedule that asks one (R-SCH-28).

    Handed to the gateway already made, the way the surfaces it holds open are: a turn needs
    an agent, a brain and an account to write into, and a gateway knows none of the three.
    Made here because this is the layer that knows all of them, and the dependency goes one
    way — `cli` -> `agent` -> `gateway` (R-AGT-9).

    **A conversation of its own, per schedule, fresh every firing.** Named for the schedule on
    the surface `schedule`, so it is never the terminal's and never a channel's: untouched, a
    run at three in the morning resumed the session its owner types into. Fresh because a
    schedule is told what its situation is before it reads a word, and a brain that binds
    standing instructions when a conversation opens would be told once and never again.

    Which brain answers is the schedule's, then the agent's, and a schedule that reaches for
    neither cannot run — said as an outcome rather than passed over in silence.
    """
    from rundesk import schedule as schedules
    from rundesk import turn as turns

    carrying = carry if carry is not None else turns.carry

    async def made(one):
        kept = chosen(name, where)
        named = one.provider or kept.get("provider")
        if not named:
            raise gateway.Unrunnable(
                f"schedule '{one.name}' names no brain, and neither does this agent")
        row = reading(name, where).schedule(one.name) or {}
        return await carrying(
            name, one.prompt, named, where=where,
            model=one.model or kept.get("model"),
            settings=kept.get("settings"),
            conversation=one.name, on=turns.SCHEDULE, kind=turns.SCHEDULE,
            fresh=True,
            # This schedule's own, then the agent's, then the one line rundesk says to a
            # turn nobody is waiting for (R-AGT-16).
            preface=told(name, where, said=one.instructions or "",
                         otherwise=schedules.by_default(one.name)),
            source=turns.SCHEDULE,
            # What correlates this run with the schedule that started it, so what ran at
            # three in the morning is found by the name an owner already knows.
            schedule_id=row.get("id"),
        )

    return made


def unrunnable_channels(name: str, where: Path | None = None) -> list:
    """Which of this agent's channels name a kind that is not on this machine."""
    from rundesk import channel as channels

    missing = []
    for record in reading(name, where).channels():
        try:
            channels.program(str(record.get("kind") or ""))
        except channels.NotRunnable as why:
            missing.append((record["name"], str(why)))
    return missing
