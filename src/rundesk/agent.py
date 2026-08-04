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

import fcntl
import hashlib
import os
import re
import shutil
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from rundesk import data_home, gateway, instructions, migration, skill, store
from rundesk import handoff as handoffs
from rundesk import config

#: What a new agent's home is copied from. Ordinary Markdown files rather than text built
#: in code, because they are what an owner reads first and edits next, and a rule about how
#: an agent is reached is worth keeping where it can be read (R-AGT-42).
TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "agent"

#: The one thing new templates substitute on the way in. Everything else is copied as it
#: stands. `NAMED` remains accepted for templates an owner wrote before this spelling was
#: clarified.
AGENT = "{{agent}}"
NAMED = "{{name}}"

#: The directories inside an agent's home that are the agent's own to work in.
WORKING = "workspace", "skills"

#: A fresh agent's human spelling while its records are being created. It is removed only
#: after the database holds that spelling, so retrying an interrupted creation can finish
#: without treating an ordinary slug-valued display name as incomplete.
DISPLAY_PENDING = ".display-name.pending"


#: Where an owner keeps the templates they made their own — **inside** where agents are
#: kept, rather than beside it.
#:
#: Derived rather than given a variable of its own, so whatever redirects where agents live
#: redirects this with it: a second name to set is a second name to forget, and `MEMORY.md`
#: records what forgetting one cost. But derived *downwards*. Hung off the parent, it
#: resolved to a sibling of the agents directory — which for an owner is `~/.rundesk/data`
#: and is right, and for anything pointed at a scratch directory is whatever that scratch
#: directory happens to sit in. Every case in a suite then shared one, and one case's
#: template turned up in another's agent. Anything below the redirected root cannot do that.
#:
#: Dotted because it stands among the agents without being one: what makes a directory an
#: agent is a `home/` inside it, so nothing that walks this place can mistake it for one.
#:
#: It is still the owner's tier — above every agent, inside none of them, and outside the
#: program, which is the whole reason an update cannot reach it (R-AGT-23).
OVERRIDES = ".templates", "agent"
RETIRED_TEMPLATES = frozenset({"USER.md"})


def templates_home() -> Path:
    """Where an owner's own templates stand, resolved on every call.

    Never cached and never a default argument: an owner's directory is machine state, and
    binding it once at import is how a suite comes to write into the real one.
    """
    return agents_home().joinpath(*OVERRIDES)


def shipped() -> tuple[str, ...]:
    """The pages this install ships, whatever an owner has done beside them.

    Kept apart from `knowledge()` for one reason, and it only shows up once somebody has
    agents: an owner may add a page the install does not ship (R-AGT-24), and every agent
    made before they did has never heard of it. A diagnosis that looked for the *whole* set
    would report every one of those as missing a file it loads — a customisation that
    retroactively breaks the reading of agents it never touched. So what an agent is
    *judged* against is this, and what a new one is *made* from is the other.
    """
    if not TEMPLATES.is_dir():
        return ()
    return tuple(sorted(page.name for page in TEMPLATES.iterdir() if page.is_file()))


def sourced(overrides: Path | None = None) -> dict:
    """Every page a new agent's home is made from, and the file each really comes from.

    **The one place precedence is decided** (R-AGT-22), so `add` and a diagnosis can never
    disagree about which file an agent got. Per page rather than per set: an owner who wants
    their own `SOUL.md` and nothing else writes one file, and the other three stay whatever
    the install ships — including whatever a later release improves them into. Taking on all
    four to change one would mean never getting an improvement to any of them.

    An override directory that is missing, empty or unreadable is simply an owner who has
    not made one, which is the ordinary case and never an error.
    """
    from_install = {called: TEMPLATES / called for called in shipped()}
    where = templates_home() if overrides is None else overrides
    try:
        theirs = sorted(
            page for page in where.iterdir()
            if page.is_file() and page.name not in RETIRED_TEMPLATES
        )
    except OSError:
        return from_install
    return {**from_install, **{page.name: page for page in theirs}}


def knowledge(overrides: Path | None = None) -> tuple[str, ...]:
    """The files an agent's home holds, asked of what they are copied from.

    Read off the directories rather than listed here, so a template added later is written
    into a new agent's home and covered by the suite without anything being added to a list
    kept somewhere else — and so is one an *owner* adds.
    """
    return tuple(sorted(sourced(overrides)))


class NotAnAgentName(ValueError):
    """A name that would not stand where agents are kept, or would claim another's file."""


class InUse(Exception):
    """Something is still using this name, so nothing belonging to it was moved."""


def slug(name: str) -> str:
    """The lowercase filesystem name given to a newly created agent (R-AGT-39).

    An owner names an identity, not a path. Spaces and punctuation become one dash,
    accents become their ASCII spelling where Unicode defines one, and the result is
    checked by the same boundary every later command uses. Existing agent names are not
    rewritten: this is creation-time normalization, not a migration of persisted state.
    """
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    made = re.sub(r"[^a-zA-Z0-9]+", "-", plain).strip("-").lower()
    if not made:
        raise NotAnAgentName(
            f"'{name}' is not a usable name — include at least one letter or digit"
        )
    return checked(made)


def creation_name(name: str, existing=()) -> str:
    """The slug for a new agent, or the legacy spelling already holding that slug.

    Older releases accepted uppercase, dots and underscores. On a case-sensitive
    filesystem, blindly creating today's slug beside one of those would make two agents
    from one human name; on macOS it would silently address the old directory instead.
    Resolve that difference deliberately, and refuse an already-ambiguous legacy set.

    Exact spelling wins first, then an unambiguous case-insensitive legacy match is
    considered before ASCII slugging. Older releases admitted Unicode names that have no
    ASCII spelling; one such directory must remain reachable and must never stop an
    unrelated new agent from being made.
    """
    existing = tuple(existing)
    # Exact spelling is an identity, even on a case-sensitive machine that has both
    # `Winston` and `winston` from an older release. Only an alias may be ambiguous.
    if name in existing:
        return name
    same = sorted(one for one in existing if one.casefold() == name.casefold())
    if len(same) > 1:
        raise NotAnAgentName(
            f"'{name}' matches more than one existing agent: {', '.join(same)}"
        )
    if same:
        return same[0]
    made = slug(name)
    matches = []
    for one in existing:
        try:
            existing_slug = slug(one)
        except NotAnAgentName:
            continue
        if existing_slug == made:
            matches.append(one)
    matches.sort()
    if len(matches) > 1:
        raise NotAnAgentName(
            f"'{name}' matches more than one existing agent: {', '.join(matches)}"
        )
    return matches[0] if matches else made


def command_name(name: str, existing=()) -> str:
    """Resolve a command alias without renaming an unmatched legacy gateway.

    Creation deliberately invents a lowercase slug. Other commands do not invent
    identities: an old supervisor may still invoke ``serve Winston`` before that
    gateway has an agent or any surviving state. Preserve that exact spelling when
    there is no known alias target (R-AGT-13, R-AGT-40).
    """
    existing = tuple(existing)
    resolved = creation_name(name, existing)
    if resolved in existing:
        return resolved
    return checked(name)


def agents_home() -> Path:
    """Where agents are kept — one directory each, holding everything that is theirs.

    Beside the run and log directories rather than inside either: those hold what rundesk
    wrote before there were agents to own it, and this is what an ordinary uninstall
    preserves because it is the owner's rather than rundesk's (R-AGT-3).

    Under `data_home()` rather than beside the program, so that what an owner keeps is one
    directory an uninstall cannot reach. Its own variable still wins, because a suite
    pointing one agent's directory somewhere is a narrower thing to ask for than moving
    everything an install keeps.
    """
    return Path(os.environ.get("RUNDESK_AGENTS_DIR") or data_home() / "agents")


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


def plans(name: str, where: Path | None = None) -> Path:
    """Where this agent keeps implementation plans, inside its own workspace (R-AGT-48)."""
    return workspace(name, where) / "plans"


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


def identities(
    where: Path | None = None,
    run: Path | None = None,
    logs: Path | None = None,
) -> list[str]:
    """Agent directories and legacy gateway spellings that commands can still address.

    A gateway predating agents may be represented only by shared run state or history.
    Those spellings must participate in alias resolution so ``Winston`` is not silently
    split into a new ``winston`` identity during adoption (R-AGW-1, R-AGT-13).
    """
    found = set(known(where))
    found.update(one.name for one in gateway.every(run))
    log_home = logs or gateway.logs_home()
    try:
        entries = tuple(log_home.iterdir())
    except OSError:
        entries = ()
    probe = "0"
    suffixes = tuple(
        path.name[len(probe):] for path, _ in _wrote_before(probe, log_home)
    ) + (".out", ".err")
    for entry in entries:
        if not entry.is_file():
            continue
        for suffix in suffixes:
            match = re.fullmatch(rf"(.+){re.escape(suffix)}(?:\.\d+|\.changing)?", entry.name)
            if not match:
                continue
            candidate = match.group(1)
            try:
                gateway.checked(candidate)
            except gateway.NotAName:
                continue
            found.add(candidate)
            break
    return sorted(found)


def exists(name: str, where: Path | None = None) -> bool:
    """Whether there is an agent of this name."""
    try:
        return home(name, where).is_dir()
    except NotAnAgentName:
        return False


def creation_pending(name: str, where: Path | None = None) -> bool:
    """Whether first creation still owes its human name to durable records."""
    pending = directory(name, where) / DISPLAY_PENDING
    return pending.is_symlink() or pending.exists()


def _write_pending(pending: Path, display_name: str) -> None:
    """Publish a complete first display spelling once, without replacing one on retry."""
    beside = pending.with_name(f"{pending.name}.writing")
    try:
        opened = os.open(
            beside,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as why:
        raise store.Unreadable(f"{beside} could not be safely opened: {why}") from why
    with os.fdopen(opened, "r+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            opened_as = os.fstat(handle.fileno())
            try:
                published_as = pending.lstat()
            except FileNotFoundError:
                published_as = None
            same_published_inode = (
                published_as is not None
                and stat.S_ISREG(published_as.st_mode)
                and (opened_as.st_dev, opened_as.st_ino)
                == (published_as.st_dev, published_as.st_ino)
            )
            if opened_as.st_nlink != 1 and not (
                opened_as.st_nlink == 2 and same_published_inode
            ):
                raise store.Unreadable(
                    f"{beside} is linked to something other than pending creation state"
                )
            if not pending.is_symlink() and not pending.exists():
                handle.seek(0)
                staged = _display_from_record(handle.read())
                if staged is None:
                    handle.seek(0)
                    handle.truncate()
                    handle.write(_display_record(display_name))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(beside, pending)
            # Removed while the lock is still held. Another writer that already opened
            # this inode sees the published marker; a later one gets a fresh staging file
            # and sees it too. A crash leaves one fixed file a retry can safely resume.
            _unlink_durable(beside)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _unlink_durable(path: Path) -> None:
    """Remove one state path and make that absence survive power loss."""
    path.unlink(missing_ok=True)
    folder = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def _display_record(display_name: str) -> bytes:
    """A pending name framed so a retry can distinguish complete from partial."""
    payload = display_name.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest().encode("ascii")
    return digest + b"\n" + payload


def _display_from_record(record: bytes) -> str | None:
    """A complete, checksummed pending name, or None for interrupted staging."""
    try:
        digest, payload = record.split(b"\n", 1)
        if len(digest) != 64 or hashlib.sha256(payload).hexdigest().encode("ascii") != digest:
            return None
        display = payload.decode("utf-8")
    except (ValueError, UnicodeError):
        return None
    return display if display and display == display.strip() else None


def _pending_display(pending: Path) -> str | None:
    """The complete pending spelling, refusing anything unsafe or unreadable."""
    try:
        mode = pending.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as why:
        raise store.Unreadable(f"{pending} could not be read: {why}") from why
    if not stat.S_ISREG(mode):
        raise store.Unreadable(f"{pending} is not a regular file")
    try:
        record = pending.read_bytes()
    except OSError as why:
        raise store.Unreadable(f"{pending} could not be read: {why}") from why
    display = _display_from_record(record)
    if display is None:
        raise store.Unreadable(f"{pending} does not hold a complete display name")
    return display


def add(name: str, where: Path | None = None, display_name: str | None = None) -> list[str]:
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
    new_home = not home(name, where).exists()
    made = []
    agent_dir = directory(name, where)
    records = store.path_for(agent_dir)
    fresh = not records.exists()
    pending = agent_dir / DISPLAY_PENDING
    if fresh and display_name is not None:
        # Publish identity recovery before `home/` makes this count as an agent. If this
        # process dies first, retry still sees a new name; if it dies afterwards, retry
        # sees the durable marker and finishes the same creation.
        agent_dir.mkdir(parents=True, exist_ok=True)
        _write_pending(pending, display_name.strip())
    pending_display = _pending_display(pending)
    for path in made_of(name, where).values():
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            made.append(path.name + "/")
    plan_home = plans(name, where)
    if not plan_home.exists():
        plan_home.mkdir(parents=True, exist_ok=True)
        made.append("workspace/plans/")
    for called in knowledge():
        page = home(name, where) / called
        if not page.exists():
            page.write_text(
                _copied(called, pending_display or display_name or name),
                encoding="utf-8",
            )
            made.append(called)
    # Fresh agents receive the baseline here. Existing populations are reconciled by both
    # upgrade routes after this release's library has been laid down (R-AGT-36).
    if fresh:
        made.extend(require_skills(name, where))
    kept = store.Store(records)
    kept.made(fresh_home=new_home or pending_display is not None)
    if pending_display is not None:
        # A retry reads the first creation's spelling, not whichever alias happened to be
        # typed on the retry. The marker leaves only after the durable database write.
        kept.remember_display_name(pending_display)
        _unlink_durable(pending)
    if fresh:
        made.append(store.NAME)
    return sorted(made)


def _what_is_wrong_with_its_skills(name: str, where: Path | None = None) -> list:
    """What stands between this agent's skills and a brain reading them.

    Two things, and neither is a fault of the agent's own making. A grant whose skill has
    gone — a built-in dropped by a release, or one an owner deleted from the library —
    leaves a link pointing at nothing, which every brain skips in silence. And a built-in
    Rundesk or the install configuration requires that this agent does not hold, because it
    was made before the requirement was added or its grant was changed outside the command.
    A diagnosis is where an owner hears about it.
    """
    found = []
    mine = skills(name, where)
    for called in skill.granted(mine):
        standing = mine / called
        if standing.is_symlink() and not standing.exists():
            found.append(Complaint(
                str(standing), f"the skill {called} was granted and is no longer there",
                f"rundesk skills revoke {name} {called}"))
            continue
        # **Resolving is not being a skill.** A grant can point at a directory that exists
        # and holds nothing a brain would index — an update interrupted part way once did
        # exactly that. Every brain skips it in silence, so the only way an owner learns is
        # here.
        why = skill.valid(standing)
        if why:
            found.append(Complaint(
                str(standing), f"the skill {called} was granted and {why}",
                f"rundesk update"))
    held = skill.library()
    try:
        # Install configuration is not under the agents directory. `where` redirects where
        # this agent lives; the required baseline still belongs to the install (R-AGT-36).
        wanted = config.skills()["granted"]
    except config.Unreadable as why:
        # The one place an owner hears it without having to be making an agent at the time.
        return found + [Complaint(config.NAMED, str(why), f"edit {config.path(where)}")]
    for called in wanted:
        if called in held and called not in skill.granted(mine):
            found.append(Complaint(
                called, "this agent has not been given a skill this release ships",
                f"rundesk skills grant {name} {called}"))
    return found


def require_skills(name: str, where: Path | None = None) -> list[str]:
    """Attach every install-required skill this agent does not already hold.

    One of them is the skill that says how to write a skill, and it is the reason this
    happens without being asked for: an agent cannot be told to use `rundesk skills grant`
    to give itself the thing that explains what granting is. It is the bootstrap.

    **Which skills, and not simply every one that ships.** A release ships more than every
    agent should carry — how to write a skill, how to write a pull request — and a skill an
    agent will never reach for is not free: its description is read by the brain on every
    turn. So the set is `config.skills()["granted"]`: Rundesk's mandatory floor plus the
    optional baseline an owner states once in `config.json`. Creation, update, and installer
    reconciliation all come through this one policy (R-AGT-36).

    A library that has nothing in it yet is a checkout somebody is working in rather than
    an install, and is not a half-made agent.
    """
    given = []
    plan_home = plans(name, where)
    if not plan_home.exists():
        plan_home.mkdir(parents=True, exist_ok=True)
        given.append("workspace/plans/")
    mine = skills(name, where)
    with skill.changing_grants():
        already = set(skill.granted(mine))
        # Carry a Rundesk-made grant to the built-in's current name. Do this before the
        # configured floor so an optional authoring grant follows the rename too; never touch a
        # directory or foreign link an owner placed under the old spelling (R-AGT-49).
        for old, new in skill.RENAMED.items():
            old_grant = mine / old
            if (old not in already or not skill.ours(old_grant)
                    or not skill.built_in(old) or not skill.built_in(new)):
                continue
            try:
                if new not in already:
                    skill.grant(mine, new)
                    given.append(f"skills/{new}")
                elif not skill.ours(mine / new):
                    # An owner entry under the replacement name is not proof this agent can
                    # lose its old working built-in. Keep both owner data and old grant.
                    continue
                skill.revoke(mine, old)
            except (skill.Unknown, skill.NotASkill, skill.InTheWay, OSError):
                continue
            already.discard(old)
            already.add(new)
        # `where` is an agents directory, never the install's data directory. The baseline is
        # install-wide and resolves from the same file every agent shares (R-AGT-36).
        for called in config.skills()["granted"]:
            if called in already:
                continue
            try:
                skill.grant(mine, called)
            except (skill.Unknown, skill.NotASkill, skill.InTheWay, OSError):
                continue
            given.append(f"skills/{called}")
    return given


def retire_renamed_skills(where: Path | None = None) -> list[str]:
    """Retire old built-ins after every agent's grants had a chance to move (R-AGT-49)."""
    with skill.changing_grants():
        return skill.retire_renamed((skills(name, where) for name in known(where)))


def reconcile_skill_config() -> list[str]:
    """Carry configured names only after their replacement is proven in the library."""
    return config.ensure()


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
    pending = stands / DISPLAY_PENDING
    if pending.is_symlink() or pending.exists():
        pending.unlink()
        taken.append(pending.name)
    writing = pending.with_name(f"{pending.name}.writing")
    if writing.is_symlink() or writing.exists():
        writing.unlink()
        taken.append(writing.name)
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


#: What rundesk tells every turn of *this agent's*, before anything anybody else says
#: (R-AGT-17). `instructions.CORE_INSTRUCTIONS` stands in front of it and is stabler still —
#: the same bytes for every execution on the machine, a role's included.
#:
#: **Stable for one agent.** It is the front of what a brain is given, which is the part
#: prompt caching keys on — anything that varies per turn belongs after it, never inside it,
#: or every turn pays for a prefix that no longer matches. The agent's name and resolved
#: home/workspace paths are byte-for-byte identical from one turn to the next.
#:
#: The roles this install has are named directly after it and before anything per-turn:
#: install-wide and stable between turns, so the cached prefix holds — but varying with
#: the machine, which is why they are a layer of their own rather than a sentence in here.
#:
#: Said here rather than left to the home an agent loads, because a home is the owner's to edit
#: and this is the one thing that must be true whatever they wrote — an agent that has been
#: given no rules at all still knows what it is running inside and how to find out what it did.
STANDING = instructions.AGENT_IDENTITY


def instruction_variables(name: str, where: Path | None = None) -> dict[str, str]:
    """The agent-owned values Rundesk fills into every core instruction layer."""
    from rundesk import role          # local: role.py imports this module

    return {
        "agent": display_name(name, where) if exists(name, where) else name,
        "agent_slug": name,
        "agent_home": str(home(name, where)),
        "workspace": str(workspace(name, where)),
        # Install-wide rather than this agent's, and named here because an agent that has
        # to run a command to learn it has specialists at all is one that never does.
        "roles": role.offered(where),
    }


def standing(name: str, where: Path | None = None) -> str:
    """Rundesk's own words to a turn, for this agent. One place, so it is one wording."""
    return instructions.build(variables=instruction_variables(name, where))


def added_instructions(name: str, where: Path | None = None) -> str:
    """What this agent's owner adds to Rundesk's instructions, or nothing."""
    mine = chosen(name, where).get("instructions")
    return mine if isinstance(mine, str) and mine.strip() else ""


def told(name: str, where: Path | None = None, said: str = "",
         regardless: str = "") -> str:
    """What a turn for this agent is told about its situation, before it reads a prompt.

    **Rundesk's own words first, then every applicable layer** (R-AGT-16, R-AGT-17,
    R-AGT-34, R-AGT-38). `regardless` is Rundesk's trigger-specific context. The agent
    owner's stored instructions follow, then `said`, which is what this turn or schedule
    added. Empty layers disappear; no supplied instruction replaces one before it.
    """
    return instructions.build(
        variables=instruction_variables(name, where),
        append=(regardless, added_instructions(name, where), said),
    )


def remember(name: str, where: Path | None = None, provider: str | None = None,
             model: str | None = None, settings: dict | None = None,
             instructions: str | None = None, replace_brain: bool = False,
             forget_conversation: str | None = None) -> dict:
    """Keep what this agent should reach for when a turn does not say.

    What is not given is left exactly as it was, so naming a model later does not quietly
    forget the brain. When `replace_brain` names a provider that differs, omitted model
    and settings are cleared because they belonged to the old provider. The comparison
    and update share one transaction, so simultaneous changes are ordered rather than
    making stale decisions that erase one another.
    """
    kept = records(name, where)
    kept.remember_agent(provider=provider, model=model, settings=settings,
                        instructions=instructions, replace_brain=replace_brain,
                        forget_conversation=forget_conversation)
    return kept.agent()


@dataclass(frozen=True)
class Complaint:
    """One thing standing between an agent and a working turn, and the way out of it.

    **What is wrong and what to do about it are one answer, not two** (R-AGT-19). A
    diagnosis is what an owner runs *because* something is already wrong, so leaving them to
    work out the command from the fault is asking them to do the diagnosis twice. `fix` is
    what they would type; it is empty only where there is genuinely nothing to type.
    """

    about: str
    said: str
    fix: str = ""


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
        return [Complaint(str(where_it_is["home"]), "there is no agent of that name here",
                          f"rundesk add {name} --provider <provider>")]
    for what, path in sorted(made_of(name, where).items()):
        if what == "home":
            continue  # asked above, and its absence is "there is no agent", not a fault
        if not path.is_dir():
            found.append(Complaint(str(path), f"the agent's {what} is not there",
                                   f"rundesk add {name}"))
        elif not os.access(path, os.W_OK):
            found.append(Complaint(str(path), f"the agent's {what} cannot be written to",
                                   f"chmod u+w {path}"))
    # **What an agent is judged against is what the install ships** (R-AGT-24), never the
    # whole set an owner may have added to. An owner-added page reaches new agents; every
    # agent made before it has never heard of it, and reporting each of those as missing a
    # file it loads would be a customisation breaking the reading of agents it never touched.
    holds = shipped()
    if not holds:
        # Asked before the files are looked for, because an install with nothing to copy
        # from would otherwise find nothing missing and call a bare home a working agent.
        found.append(Complaint(str(TEMPLATES), "this install has nothing to make an agent from",
                               "reinstall rundesk"))
    for called in holds:
        page = where_it_is["home"] / called
        if not page.is_file():
            found.append(Complaint(str(page), "the agent is missing one of the files it loads",
                                   f"rundesk add {name}"))
    unfit = gateway.fitness(root)
    if unfit:
        found.append(Complaint("this install", unfit, "rundesk update"))
    found.extend(_what_is_wrong_with_its_skills(name, where))
    found.extend(_what_is_wrong_with_its_role_runs(name, where))
    # **Where these records stand against what this install expects** (R-AGT-20). Read
    # without opening a store, which refuses records it will not read — and refusing is the
    # right answer for a turn and the wrong one for the check that exists to explain it.
    at = store.path_for(directory(name, where))
    if at.exists():
        reached = migration.version_on_disk(at)
        if reached < store.VERSION:
            found.append(Complaint(
                str(at),
                f"these records are version {reached} and this rundesk expects "
                f"{store.VERSION}",
                "rundesk update"))
    try:
        named = chosen(name, where).get("provider")
    except (store.Unreadable, store.TooNew, store.Behind) as why:
        # A diagnosis is what an owner runs *because* something is already wrong, so
        # records this rundesk will not read are the answer rather than an exception out
        # of the middle of one. It is reported and the rest of the check still runs.
        found.append(Complaint(str(store.path_for(directory(name, where))), str(why),
                               "rundesk update"))
        named = None
    if not named:
        # **A brain nobody named is what stands between this agent and every turn** — and
        # this said READY, which is a diagnosis claiming a success it had not earned. The
        # turn refuses correctly and says how to fix it; the check that exists to find that
        # out first was the one place it did not (R-AGT-18).
        found.append(Complaint(str(store.path_for(directory(name, where))),
                               "nothing says which brain answers for this agent",
                               f"rundesk configure {name} --provider <provider>"))
    elif runnable is not None:
        try:
            runnable(named)
        except Exception as why:
            # The detail is what is *about* the complaint and the sentence is what is
            # said, because a diagnosis reads "<what is wrong>: <where>" everywhere else.
            found.append(Complaint(str(why), "the brain this agent reaches for",
                                   f"rundesk configure {name} "
                                   "--provider <one that is installed>"))
    return found


def _what_is_wrong_with_its_role_runs(name: str, where: Path | None = None) -> list:
    """What stands between this agent's specialist executions and being carried on.

    Nothing here starts a provider and nothing here writes (R-AGT-11, R-AGT-12). Every one
    of these is a fact an owner cannot see any other way: work that will never be carried
    on, a report nobody was ever told about, and a directory a run believes it is working
    in that is no longer there.
    """
    from rundesk import role as roles
    from rundesk import role_run as role_runs

    found: list = []
    at = store.path_for(directory(name, where))
    if not at.exists():
        return found
    try:
        kept = reading(name, where)
        runs = kept.role_runs(limit=200)
        owing = kept.owed_role_callbacks()
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed):
        return found   # already reported by the version and records checks above
    for row in runs:
        if row["state"] not in (store.ADMITTED, store.WORKING):
            continue
        try:
            role_runs.verified(name, row, where)
        except role_runs.NotDelegable as why:
            found.append(Complaint(row["id"], str(why), ""))
            continue
        target = row.get("target")
        if target and not Path(target).is_dir():
            found.append(Complaint(
                row["id"], "the directory this role run works in is not there", ""))
    for one in owing:
        found.append(Complaint(
            one["role_run"],
            "a role run has reported back and its parent has not been told yet",
            f"rundesk start {name}"))
    for slug in sorted({row["role"] for row in runs}):
        try:
            one = roles.read(slug, where)
        except roles.NotARole as why:
            found.append(Complaint(slug, f"a role this agent has used is unusable: {why}",
                                   ""))
            continue
        if one.missing:
            # Not a fault — a role runs without a skill this machine has not got — but it
            # is the difference between the work an owner expected and the work they get.
            found.append(Complaint(
                slug,
                "this role asks for skills this machine has not got, so runs of it go "
                f"without them: {', '.join(one.missing)}",
                f"rundesk skills install <repository>"))
    return found


def where_each_page_comes_from(overrides: Path | None = None) -> list:
    """Per page: whether a new agent would take it from the install or from the owner, and
    from which file (R-AGT-26).

    "Why does my new agent not have my rules" has to be answerable without reading source.
    Says it for every page rather than only the overridden ones, because an owner who
    misspelled a filename needs to see the four that are still the install's to notice that
    the fifth is not theirs.
    """
    return [
        (called, "install" if at.parent == TEMPLATES else "owner", at)
        for called, at in sorted(sourced(overrides).items())
    ]


def _copied(called: str, name: str, overrides: Path | None = None) -> str:
    """One template, with the agent's name put where the template asks for it.

    A copy and one substitution, so what an owner finds in a new home is what stands in the
    file it came from — editable there, readable as ordinary Markdown, and never a second
    version of the same words held in code.

    **Writing `{{agent}}` is optional** (R-AGT-25). The substitution is the whole of the
    contract an override has to honour, and honouring it is a choice: a template with no
    placeholder is one every agent gets verbatim, which is a legitimate thing to want.
    `{{name}}` remains an alias for owner templates written before the placeholder was
    clarified (R-AGT-41). Replacing absent strings is harmless, so both forms can be
    supported without interpreting any other part of the page.
    """
    return (sourced(overrides)[called].read_text(encoding="utf-8")
            .replace(AGENT, name)
            .replace(NAMED, name))


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
    #: The private directory this channel is given for this agent, resolved here for the
    #: same reason the other three are: a gateway keeps a little about a channel that
    #: outlives it — who it has already introduced the agent to (R-CH-33) — and reaching
    #: for it would mean the gateway knowing where an agent's things stand. Defaulted so a
    #: caller building one by hand for something with no home is still a whole Reachable.
    home: Path | None = None
    #: The names this surface's own adapter reads its credential from, which the install's
    #: values are **never** given to it under (R-SEC-29). Two agents may hold two different
    #: bots, so one install-wide `DISCORD_TOKEN` would silently make them the same bot,
    #: with each agent's record still naming a file nobody read. Carried rather than
    #: resolved by the gateway, for the reason everything else here is: a gateway that
    #: reached back for what an agent's channel declared would end the direction this file
    #: rests on. **The names and never the values** — this is the same list `secret` is
    #: kept out of, not a second copy of anything.
    channel_secrets: frozenset = frozenset()


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
                agent_name=display_name(name, where),
                allow=record.get("allow"), settings=record.get("settings"),
                secret=record.get("secret")),
            answering=_answering(name, one, record, where, carry, answers),
            home=home,
            # Read through `channel.named`, which normalizes the single-name-as-a-string
            # form an adapter may answer with. Iterating the raw reply would walk that
            # string's *characters*, and a one-letter exclusion set excludes nothing.
            channel_secrets=frozenset(
                (channels.named(record.get("secret")) or {}).get("env") or ()),
        ))
    return found


def _answering(name, one, record, where, carry, answers):
    """What carries a conversation on this channel, made once the gateway can write back.

    Made rather than passed, because two of the things it needs only exist once the
    gateway is running: how to write back to the adapter, and how to ask for the agent to
    be cycled. Both are handed in, so nothing here reaches down into a gateway and
    nothing there reaches back for an agent.
    """
    # Here rather than at the top: `query` composes its answers out of what this module
    # resolves, so it imports this one — and naming it up there would close a cycle
    # between the two. The same reason `answering` and `channel` are imported below.
    from rundesk import query as queries

    def made(sending, restarting=None, note=None,
             restart_waiting=None, restart_ready=None):
        return answers.Answering(name, one, record, sending, where=where, carry=carry,
                                 restarting=restarting, note=note,
                                 querying=lambda asked: queries.answered(name, asked, where),
                                 restart_waiting=restart_waiting,
                                 restart_ready=restart_ready)
    return made


def display_name(name: str, where: Path | None = None) -> str:
    """The human name this agent's owner chose, never its directory guessed again."""
    return reading(name, where).display_name()


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
        row = {} if one.backend else (reading(name, where).schedule(one.name) or {})
        channel = turns.UPDATE if one.backend else turns.SCHEDULE
        return await carrying(
            name, one.prompt, named, where=where,
            model=one.model or kept.get("model"),
            settings=kept.get("settings"),
            conversation=one.name, on=channel, kind=turns.SCHEDULE,
            fresh=True,
            # Rundesk's schedule layer for a turn nobody is waiting for, which is always
            # there (R-AGT-34), and then this schedule's own words or the agent's added to
            # it (R-AGT-16).
            preface=told(
                name, where, said=one.instructions or "",
                regardless="" if one.backend else schedules.by_default(one.name),
            ),
            source=turns.SCHEDULE,
            # What correlates this run with the schedule that started it, so what ran at
            # three in the morning is found by the name an owner already knows.
            schedule_id=row.get("id"),
        )

    return made


@dataclass(frozen=True)
class Playing:
    """How a gateway carries this agent's role runs, and tells their parents.

    Handed over already made, for the reason `asking` is: a role run needs an agent, a
    brain, a bundle and an account, and a gateway knows none of the four. A gateway with
    no agent behind it is handed nothing here and simply never carries one.
    """

    waiting: object
    seen: object
    checking_in: object
    stopping: object
    stopped: object
    carry: object
    owed: object
    claiming: object
    reviewing: object
    reviewed: object
    giving_up: object
    sweep: object
    quiet: object


def playing(name: str, where: Path | None = None, carry=None) -> Playing:
    """Everything a gateway does about role runs, made where an agent is known.

    Five questions and no state: which runs are waiting to be carried, carrying one,
    which parent is still owed a review, that a review turn was admitted, that it was
    delivered, and clearing what has expired. The gateway holds which of them are in
    flight, exactly as it already holds which schedules are.
    """
    import asyncio

    from rundesk import role_run as role_runs

    def _unfinished() -> list:
        """Every run that was admitted and has not finished — oldest first."""
        kept = reading(name, where)
        found = [one for state in store.UNFINISHED_ROLES
                 for one in kept.role_runs(state=state, limit=200)]
        return sorted(found, key=lambda one: one["admitted_at"])

    def waiting() -> list:
        """Runs that are ready to be carried now — oldest first.

        A run left `working` by a gateway that died is here too, and is carried on rather
        than started again: its provider session is the conversation's, so resuming is
        what the ordinary turn machinery already does with one (R-ROL-11).

        **One whose last attempt threw is not ready yet.** Something is looking every five
        seconds, so a fault that raises every time would be three attempts inside fifteen
        seconds and a ceiling that bounded nothing worth bounding (R-ROL-29).
        """
        return [one for one in _unfinished() if handoffs.ready_to_carry(one)]

    def seen(run_id: str):
        """Where a run's activity is shown, and what to call it there.

        The parent's own conversation, because that is where somebody asked for the work
        and where they are waiting for it — the same place the review lands.

        Which role it is and how long it has been going come from `shown`, which is what
        `rundesk roles` already prints, so a line in a room and a listing in a terminal
        can never disagree about the same run.

        **How it ended, and who ended it, come off the row too** (R-ROL-43). A run that has
        settled is settled in the records before anything is told about it, so the three
        endings a surface distinguishes are read from the one place that decided them
        rather than worked out a second time from an outcome object. A run that has not
        reached a terminal state has no ending here — an attempt that threw and will be
        tried again is not a run that stopped and not a run that failed — and `stopped_by`
        is absent for a run nobody wrote an asker down for.
        """
        kept = reading(name, where)
        row = kept.role_run(run_id)
        if row is None:
            return None
        room = kept.conversation_of(row["parent_conversation"])
        if room is None:
            return None
        return {"channel": room.get("channel"), "conversation": room.get("space"),
                "label": row["label"] or row["role"], "role": row["role"],
                "elapsed": role_runs.shown(row)["elapsed"],
                # **Whether this is the first time or a carrying-on** (R-ROL-44). Read off
                # the outcome, which is written when a run settles and never cleared — so a
                # resumption carries one and a first execution does not, including a first
                # execution whose gateway died part-way. Nothing new is stored to know it.
                "carried_on": bool(row.get("outcome")),
                "said": records(name, where).words_said(run_id),
                # Off the row rather than through the listing, which is where how long it
                # has been is worked out and this needs no working out at all.
                "became": row["state"] if row["state"] in store.FINISHED_ROLES else "",
                "stopped_by": row.get("stop_asked_by") or ""}

    def checking_in(run_id: str, told: int = 0):
        """Whether this run owes a check-in now, and what to say in it.

        Answered here rather than in the gateway for the reason `seen` is: how long a run
        has been going and how often that is worth saying are facts about role runs, and a
        gateway that worked them out itself would be a second place they could be worked
        out differently.
        """
        where_it_shows = seen(run_id)
        if where_it_shows is None:
            return None
        due = handoffs.check_in_due(where_it_shows["elapsed"], told)
        return None if not due else {**where_it_shows, "due": due}

    def stopping() -> list:
        """Every unfinished run somebody has asked to end.

        Asked of every unfinished run rather than of the ones ready to be carried: a
        person who asked for a run to end wants it ended now, and a run waiting out a
        backoff is exactly one nobody should have to wait for (R-ROL-24).
        """
        return [one for one in _unfinished() if one.get("stop_asked_at")]

    def stopped(run_id: str) -> None:
        """Settle a run that was asked to end and that nothing was carrying.

        The same settlement a cancelled one reaches, so a stop looks like a stop however
        far the execution had got — including not having started at all.
        """
        role_runs.end(name, run_id, store.STOPPED,
                      "this run was stopped before it finished", where=where)

    async def carrying(run_id: str):
        """Carry one root, and leave it settled however that goes.

        **A run that cannot be carried is still a run its parent has to be told about.**
        A corrupt bundle, a brain the agent no longer has, a target directory that was
        moved — every one of them ends this execution, and one left unsettled would be
        picked up again on the next look for ever while nobody was ever told.
        """
        try:
            return await role_runs.carry(name, run_id, where=where, carrying=carry)
        except asyncio.CancelledError:
            # **A stop and a shutdown look identical here, and are not the same news.**
            # A gateway standing down leaves the run unfinished on purpose: its provider
            # session is the conversation's, so the next gateway carries it on. A person
            # who asked for it to end wants it ended — and left unfinished it would simply
            # start again on the way back up (R-ROL-24).
            asked = (reading(name, where).role_run(run_id) or {}).get("stop_asked_at")
            if not asked:
                raise
            role_runs.end(name, run_id, store.STOPPED,
                          "this run was stopped before it finished", where=where)
            return None
        except BaseException as why:  # noqa: BLE001 — a boundary, and see below
            # **Every other way this can fail ends the execution truthfully — after a
            # ceiling.** A corrupt bundle, a brain the agent no longer has, a target
            # directory somebody moved: each raises something different, and *what* went
            # wrong matters far less than the parent eventually hearing that it did
            # (R-ROL-15). But a blip and a fault raise identically here, so the attempt is
            # counted and the run left alone until three of them have been spent — then it
            # is settled with the reason, which owes the parent its one review (R-ROL-29).
            role_runs.carry_failed(
                name, run_id, str(why) or why.__class__.__name__, where=where)
            return None

    def owed() -> list:
        """Every review a parent is still owed, oldest first, with where to say each.

        **A list rather than the oldest one.** One review that cannot be delivered — a
        channel the owner has since removed — would otherwise sit at the head for ever and
        keep every later review behind it, so work that was done would never be reported
        and nothing would say why (R-ROL-15).

        How often each has been tried, and which role it was, come along with it: a caller
        bounding how many times one parent is woken has to be able to read the count it is
        bounding, and the notice it eventually sends may name the role and nothing else
        (R-ROL-19, R-ROL-37).
        """
        kept = reading(name, where)
        found = []
        for claimed in kept.owed_role_callbacks():
            room = kept.conversation_of(claimed["conversation"])
            if room is None:
                continue
            handoff = role_runs.handoff(name, claimed["role_run"], where)
            found.append({
                "role_run": claimed["role_run"],
                "role": handoff["role"],
                "attempts": int(claimed["attempts"] or 0),
                "channel": room.get("channel"),
                "conversation": room.get("space"),
                "handoff": handoff,
            })
        return found

    def claiming(role_run: str) -> None:
        """This review is being attempted now — counted where trying is what happened."""
        records(name, where).claim_role_callback(role_run, store.stamped())

    def reviewing(role_run: str, review_run: str) -> None:
        records(name, where).role_reviewing(role_run, review_run)

    def reviewed(role_run: str) -> None:
        records(name, where).role_reviewed(role_run, store.stamped())

    def giving_up(role_run: str) -> None:
        """This handoff will not be delivered, and it stops being owed (R-ROL-37).

        The same write a delivered review makes, because what has to stop is the same
        thing: a callback offered every few seconds for a fortnight to a parent that fails
        every time. Whoever calls this has already told the owner — settling it here and
        saying nothing would be the silence this exists to end.
        """
        records(name, where).role_reviewed(role_run, store.stamped())

    def sweep() -> list:
        return role_runs.sweep(name, where)

    def quiet() -> list:
        """Settle every run that has stopped producing anything (R-ROL-30).

        How long is the owner's to state and is read from `config.json` completely, the
        way every other configured value is: a reader that quietly fell back to a number
        in Python would make the file untrue about what governs the install.
        """
        return role_runs.gone_quiet(
            name, where, after_hours=config.roles()["quiet_hours"])

    return Playing(waiting=waiting, seen=seen, checking_in=checking_in,
                   stopping=stopping, stopped=stopped,
                   carry=carrying,
                   owed=owed, claiming=claiming, reviewing=reviewing, reviewed=reviewed,
                   giving_up=giving_up, sweep=sweep, quiet=quiet)


@dataclass(frozen=True)
class Delegated:
    """How a gateway carries work handed to this agent, and delivers what came back.

    Handed over already made, for the reason `Playing` is: an ask needs an agent, a brain
    and an account, and a gateway knows none of the three. **Both halves live here**,
    because one gateway is on both sides of a delegation — it answers what was addressed to
    its agent, and it wakes its agent to review what its agent asked for.
    """

    waiting: object
    carry: object
    seen: object
    checking_in: object
    stopping: object
    stopped: object
    owed: object
    claiming: object
    collected: object
    giving_up: object
    sweep: object


def delegated(name: str, where: Path | None = None, carry=None) -> Delegated:
    """Everything a gateway does about delegations, made where an agent is known.

    No state of its own: the record outside every agent's store is what two gateways agree
    through, and the gateway holds which asks are in flight exactly as it already holds
    which role runs are.
    """
    import asyncio

    from rundesk import delegation as delegations

    def waiting() -> list:
        """Asks addressed to this agent that are ready to be carried now — oldest first.

        One left `working` by a gateway that died is here too, and is carried on rather
        than started again. **One whose last attempt threw is not ready yet**: something is
        looking every few seconds, so a fault that raises every time would be three
        attempts inside fifteen seconds and a ceiling that bounded nothing worth bounding.
        """
        return [one for one in delegations.waiting(name)
                if handoffs.ready_to_carry(one)]

    async def carrying(ask_id: str):
        """Answer one ask, and leave it settled however that goes.

        **An ask that cannot be carried is still an ask its caller has to be told about.**
        A brain the agent no longer has, a record nobody can vouch for — each ends this
        work, and one left unsettled would be picked up again on the next look for ever
        while the agent that asked was never told anything.
        """
        try:
            return await delegations.carry(name, ask_id, where=where, carrying=carry)
        except asyncio.CancelledError:
            # **A stop and a shutdown look identical here, and are not the same news.**
            # A gateway standing down leaves the ask unfinished on purpose: its provider
            # session belongs to the conversation, so the next gateway to claim this name
            # carries it on. An agent that asked for the work to end wants it ended — and
            # left unfinished it would simply start again on the way back up (R-DEL-18).
            if not (delegations.read(ask_id) or {}).get("stop_asked_at"):
                raise
            delegations.stopped(ask_id)
            return None
        except BaseException as why:  # noqa: BLE001 — a boundary, and see below
            # Every other way this can fail ends the work truthfully — after a ceiling. A
            # blip and a fault raise identically here, so the attempt is counted and the
            # ask left alone until three of them have been spent; then it is settled with
            # the reason, which owes the asking agent its one review (R-DEL-11).
            delegations.carry_failed(ask_id, str(why) or why.__class__.__name__)
            return None

    def seen(ask_id: str):
        """Where an ask's progress is shown, and what to call it there.

        The conversation the *asking* agent's turn happened in, because that is where
        somebody asked for the work and where they are waiting for it — the same place the
        review lands. **Never the answering agent's own room**: its turn is recorded in its
        own store and reads back with `rundesk messages`, and announcing it there would
        post one agent's work into another owner's room (R-DEL-16).
        """
        row = delegations.read(ask_id)
        if row is None:
            return None
        kept = reading(row["from"], where)
        room = kept.conversation_of(row.get("parent_conversation") or "")
        if room is None:
            return None
        it = delegations.shown(row)
        return {"channel": room.get("channel"), "conversation": room.get("space"),
                "delegation": row["id"], "label": it["label"], "to": it["to"],
                "elapsed": it["elapsed"],
                # The mirror of what a role run's `seen` answers, off the record's own
                # counters rather than off anything this gateway remembers (R-DEL-23).
                "carried_on": bool(int(row.get("resumes") or 0)),
                "said": int(row.get("said_count") or 0),
                "became": row["state"] if row["state"] in delegations.SETTLED else "",
                # Who ended it, off the row rather than worked out again. Only ever set on
                # an ask somebody stopped, and absent where nobody wrote an asker down —
                # which is what an ask stopped before there was anywhere to record it
                # already looks like (R-DEL-18).
                "stopped_by": row.get("stop_asked_by") or "",
                "ok": row["state"] == delegations.ANSWERED}

    def checking_in(ask_id: str, told: int = 0):
        """Whether this ask owes a check-in now, and what to say in it.

        Answered here rather than in the gateway for the reason `seen` is: how long an ask
        has been going and how often that is worth saying are facts about delegations, and
        a gateway that worked them out itself would be a second place they could be worked
        out differently.
        """
        where_it_shows = seen(ask_id)
        if where_it_shows is None:
            return None
        due = handoffs.check_in_due(where_it_shows["elapsed"], told)
        return None if not due else {**where_it_shows, "due": due}

    def stopping() -> list:
        """Every unfinished ask addressed to this agent that somebody has asked to end."""
        return delegations.stopping(name)

    def stopped(ask_id: str) -> None:
        """Settle an ask that was asked to end and that nothing here was carrying.

        The same settlement a cancelled one reaches, so a stop looks like a stop however far
        the work had got — including not having started at all (R-DEL-18).
        """
        delegations.stopped(ask_id)

    def owed() -> list:
        """Every answer this agent is still owed a review of, oldest first.

        **A list rather than the oldest one.** One answer that cannot be delivered — a
        channel the owner has since removed — would otherwise sit at the head for ever and
        keep every later one behind it, so work that was done would never be reported and
        nothing would say why (R-DEL-11).
        """
        kept = reading(name, where)
        found = []
        for row in delegations.owed(name):
            room = kept.conversation_of(row.get("parent_conversation") or "")
            if room is None:
                continue
            found.append({
                "delegation": row["id"],
                "to": row.get("to") or "",
                "label": row.get("label") or "",
                "attempts": int(row.get("review_attempts") or 0),
                "channel": room.get("channel"),
                "conversation": room.get("space"),
                "row": row,
            })
        return found

    def claiming(ask_id: str) -> None:
        """This review is being attempted now — counted where trying is what happened."""
        delegations.claim_review(ask_id)

    def collected(ask_id: str) -> None:
        delegations.collected(ask_id)

    def giving_up(ask_id: str) -> None:
        """This answer will not be reviewed, and it stops being owed (R-DEL-12).

        Whoever calls this has already told the owner — settling it here and saying nothing
        would be the silence this exists to end.
        """
        delegations.giving_up(ask_id)

    def sweep() -> dict:
        return delegations.sweep()

    return Delegated(waiting=waiting, carry=carrying, seen=seen, checking_in=checking_in,
                     stopping=stopping, stopped=stopped,
                     owed=owed, claiming=claiming, collected=collected,
                     giving_up=giving_up, sweep=sweep)


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
