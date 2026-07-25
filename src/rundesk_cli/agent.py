"""An agent: the named identity rundesk runs work for, and the home it loads from.

An agent is what a person operates. It has a name, a home holding the rules, memory,
workspace and skills it loads, and exactly one gateway that runs it — see
`.knowledge/prd-drafts/agent-home.md` and `agent-gateway.md`.

**Everything that is one agent's lives in one directory.** Before agents, what a gateway
kept was sharded by kind — a run directory, a log directory, a schedules directory — with
the gateway's name as a filename prefix inside each. That is why a gateway named `foo.ran`
and one named `foo` share `foo.ran.json`: a name is only kept apart from its neighbours by
a convention about suffixes. A directory each ends the whole class of collision, and it
makes an agent one thing to look at, copy or take away.

**This module knows about gateways; a gateway knows nothing about agents.** `Gateway`
already takes the three directories it uses as arguments, so an agent resolves its own and
hands them over. The dependency runs one way — `cli` -> `agent` -> `gateway` -> `process` —
and a gateway that reached back for an agent would end it.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from rundesk_cli import gateway

#: What a new agent's home is copied from. Ordinary Markdown files rather than text built
#: in code, because they are what an owner reads first and edits next, and a rule about how
#: an agent is reached is worth keeping where it can be read.
TEMPLATES = Path(__file__).resolve().parent / "templates" / "agent"

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


def agents_home() -> Path:
    """Where agents are kept — one directory each, holding everything that is theirs.

    Beside the run, log and schedule directories rather than inside any of them: those
    three hold what rundesk wrote before there were agents to own it, and this is what an
    ordinary uninstall preserves because it is the owner's rather than rundesk's (R-AGT-3).
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
        raise NotAnAgentName(str(why).replace("gateway name", "agent name")) from None
    separators = {os.sep, os.altsep} - {None}
    if name in (os.curdir, os.pardir) or any(mark in name for mark in separators):
        raise NotAnAgentName(f"'{name}' is not one name — an agent's name is one word, not a path")
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

    A gateway writes `<name>.ran.json`, so an agent called `x.ran` and a gateway called `x`
    would want one file between them. Read off what the gateway says it writes, because a
    list of these kept here is a list that stops being true.
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
    so that what an owner writes is never mixed with the lock, the log and the schedules
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
    `.agents/skills`, `.grok/skills` — and that a plain one is read by nobody. Making those
    links is Phase 6's, and it waits for probes of the versions actually installed rather
    than for a layout that looks right. This is where an owner puts one until then.
    """
    return home(name, where) / "skills"


def provider_home(name: str, provider: str, where: Path | None = None) -> Path:
    """The private home a provider is given for this agent, and for no other (R-AGT-8).

    Outside the agent's home on purpose: a provider's configuration, sign-in and session
    history are rundesk-managed state about a pair, not knowledge the agent loads. Kept
    inside the home, a provider reading the agent's rules would be reading its own state.
    """
    return directory(name, where) / "providers" / gateway.checked(provider)


def run_home(name: str, where: Path | None = None) -> Path:
    """Where this agent's gateway keeps what it is doing now — cleared when it stops."""
    return directory(name, where) / "run"


def logs_home(name: str, where: Path | None = None) -> Path:
    """Where this agent's gateway writes what happened — history, which outlives it."""
    return directory(name, where) / "logs"


def schedules_home(name: str, where: Path | None = None) -> Path:
    """Where this agent's schedules and what became of each are kept — history."""
    return directory(name, where) / "schedules"


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
        "schedules": schedules_home(name, where),
    }


@dataclass(frozen=True)
class Where:
    """The three directories a gateway of this name keeps things in.

    `None` for each means the ones a gateway kept things in before there were agents to own
    them — which is what every gateway function already falls back to, so a name with no
    agent goes on being reached exactly as it always was.
    """

    run: Path | None
    logs: Path | None
    schedules: Path | None


def resolved(name: str, where: Path | None = None) -> Where:
    """Where this name's gateway keeps things.

    One answer, asked once and handed to whatever needs it, because a command resolving
    these itself in three places is how a gateway comes to write somewhere the command that
    configured it does not read (R-AGT-9).
    """
    if not exists(name, where):
        return Where(None, None, None)
    return Where(run_home(name, where), logs_home(name, where), schedules_home(name, where))


def standing_before(name: str, logs: Path | None = None,
                    schedules: Path | None = None) -> list[Path]:
    """What a gateway of this name wrote before there were agents to own it.

    Read rather than moved, so a command can say what adopting would take on before it
    takes it on, and say nothing at all when there is nothing there.
    """
    return sorted(path for was, _ in _wrote_before(name, logs, schedules)
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
    """
    made = []
    for path in (home(name, where), workspace(name, where), skills(name, where),
                 directory(name, where) / "providers",
                 run_home(name, where), logs_home(name, where), schedules_home(name, where)):
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            made.append(path.name + "/")
    for called in knowledge():
        page = home(name, where) / called
        if not page.exists():
            page.write_text(_copied(called, name), encoding="utf-8")
            made.append(called)
    return sorted(made)


def adopt(name: str, where: Path | None = None, logs: Path | None = None,
          schedules: Path | None = None) -> list[str]:
    """Move what a gateway of this name wrote before it had an agent into the agent's own.

    Only ever asked for: nothing here runs on its own, and nothing moves until an owner
    types the name. The gateway must already be stopped when this is called — moving the
    files a running gateway is reading would leave it writing to one place while every
    command read another, which is the split that makes a schedule silently never run.

    The log and the schedules move; what the gateway was *doing* does not, because a
    stopped gateway is not doing anything and its lock is an empty file whose name the next
    claim makes again.
    """
    goes = {"logs": logs_home(name, where), "schedules": schedules_home(name, where)}
    moved = []
    for was, into in _wrote_before(name, logs, schedules):
        for path in _the_file_and_what_it_rotated_into(was):
            goes[into].mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(goes[into] / path.name))
            moved.append(path.name)
    return sorted(moved)


def _wrote_before(name: str, logs: Path | None, schedules: Path | None):
    """Each thing a gateway of this name wrote before it had an agent, and which of an
    agent's own directories it belongs in.

    One list, so what adopting says it would take on and what adopting takes on cannot come
    to disagree — a command that names one file and moves four is worse than either.
    """
    return (
        (gateway.log_path(name, logs), "logs"),
        (gateway.schedules_path(name, schedules), "schedules"),
        (gateway.ran_path(name, schedules), "schedules"),
        (gateway.seen_path(name, schedules), "schedules"),
        (gateway.interrupted_path(name, schedules), "schedules"),
    )


def _the_file_and_what_it_rotated_into(path: Path):
    """This file, and anything a rotation left beside it — `x.log` brings `x.log.1` along."""
    if path.exists():
        yield path
    for beside in sorted(path.parent.glob(f"{path.name}.*")) if path.parent.is_dir() else []:
        if beside.is_file():
            yield beside


def forget(name: str, where: Path | None = None, history: bool = False) -> list[str]:
    """Take this agent away (R-AGW-2).

    The home goes with the agent, and so do the schedules and the private homes providers
    were given: adding the name back otherwise inherits work nobody asked for, from an
    agent that no longer exists (R-AGW-4).

    What the agent *did* is kept until a removal is asked to take that too (R-AGW-5). A
    reinstall after trouble is exactly the moment the account of the trouble matters most,
    and it was being deleted by the command someone runs to fix the trouble.

    The run directory is emptied by the gateway's own removal, which holds the name's lock
    before unlinking it; anything still standing there belongs to something still using it,
    so it is left and not reported as taken.
    """
    stands = directory(name, where)
    taken = []
    for path in (home(name, where), directory(name, where) / "providers"):
        if path.exists():
            shutil.rmtree(path)
            taken.append(path.name + "/")
    # The schedules go and the account of them stays, and they sit side by side: what is
    # scheduled is work the name would inherit, and what each schedule last did is the
    # account. Taking the directory would take both, so the file is named.
    scheduled = gateway.schedules_path(name, schedules_home(name, where))
    if scheduled.exists():
        scheduled.unlink()
        taken.append(scheduled.name)
    if history:
        for path in (logs_home(name, where), schedules_home(name, where)):
            if path.exists():
                shutil.rmtree(path)
                taken.append(path.name + "/")
    for empty in (run_home(name, where), schedules_home(name, where), stands):
        try:
            empty.rmdir()
        except OSError:
            pass  # something is still there, and something still there is still someone's
    return sorted(taken)


@dataclass(frozen=True)
class Complaint:
    """One thing standing between an agent and a working turn."""

    about: str
    said: str


def diagnosed(name: str, where: Path | None = None, root: Path | None = None) -> list[Complaint]:
    """What stands between this agent and a working turn, without starting anything.

    Nothing here starts a provider (R-AGT-11) and nothing here writes (R-AGT-12): an owner
    asking what is wrong is often asking because something is already wrong, and a check
    that repaired what it found would make the next answer a different question's.
    """
    found = []
    where_it_is = paths(name, where)
    if not where_it_is["home"].is_dir():
        return [Complaint(str(where_it_is["home"]), "there is no agent of that name here")]
    for what in ("workspace", "skills", "providers", "run", "logs", "schedules"):
        path = where_it_is[what]
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
    return found


def _copied(called: str, name: str) -> str:
    """One template, with the agent's name put where the template asks for it.

    A copy and one substitution, so what an owner finds in a new home is what stands in
    `templates/agent/` — editable there, readable as ordinary Markdown, and never a second
    version of the same words held in code.
    """
    return (TEMPLATES / called).read_text(encoding="utf-8").replace(NAMED, name)
