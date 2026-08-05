"""What an agent holds, granting and revoking it, and standing it where a brain looks.

    data/agents/alan/home/
      skills/                                  the grant itself, and the source of truth
        writing-plans -> ../../../../skills/rundesk-skills/app/skills/writing-plans
        acme-plans/                            a copy, granted --as (see below)
      .claude/skills/writing-plans -> ../../skills/writing-plans
      .codex/skills/writing-plans  -> ../../skills/writing-plans
      .agents/skills/writing-plans -> ../../skills/writing-plans
      .grok/skills/writing-plans   -> ../../skills/writing-plans

## The grant is the thing standing there, not a record of one

There is no table of who holds what. A grant *is* the entry in the agent's own `skills/` directory,
so it is legible, diffable and revocable by hand, and there is no second register to fall out of step
with the first. The build this replaces made the same choice and it is the one thing about its skill
system that never went wrong.

## Presented, never injected

Nothing here puts a skill's text into a prompt. Each brain already walks the directory a turn stands
in looking for skills, so rundesk links each granted skill into the roots those brains read and
native discovery does the rest. Measured, not assumed — `docs/research/2026-07-27-skills-a-brain-
discovers.md` carries the table.

**One link per skill, never a link to the whole directory.** Linking `skills/` itself would make a
path a vendor owns an alias for rundesk's own, so that vendor's skill-installer would write into the
source of truth and anything aimed at that directory would destroy it.

**All four roots, whatever the agent's provider is.** Choosing by provider means every root has to be
re-presented when a provider is reconfigured, and the code that remembered to do that is the code
that eventually does not. Four links to one target cost nothing, and a CLI somebody runs by hand in
that home finds the skills whichever one it is.

**The pruning is deliberately narrow.** An entry goes only when it is a link rundesk made whose
target is inside this agent's own `skills/` and is no longer granted. A directory somebody wrote by
hand, and a link pointing somewhere else, are things this did not put there — and a dangling link is
not on its own evidence of anything, because a target can be briefly away. The build this replaces
deleted any dangling link it found, and an owner's own link to a volume that was not mounted looked
exactly like a revoked grant.

## One agent cannot hold two skills under one name

A brain finds a skill by its directory name, so the name a skill stands under here is the name it is
known by. Two catalogs may both hold `writing-plans` and either may be granted to anyone — but not
both to the same agent, because there is one directory name between them.

`--as` is the way out, and it is the one place a grant is a **copy** rather than a link: the copy's
frontmatter `name:` is rewritten to match the directory it stands in, because a brain that found the
two disagreeing would index it under a name nothing granted. A copy goes stale, so it carries
`.rundesk-grant.json` naming where it came from and what the source looked like, and `refreshed`
makes it again whenever the source has moved.
"""

import hashlib
import os
import shutil
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Set, Tuple

from rundesk.agents import directory
from rundesk.skills import library
from rundesk.utils import files

#: Where an agent's grants stand, inside its own home. The name is not a vendor's and is read by no
#: brain on its own — it is rundesk's canonical directory, and the vendor roots link into it.
INSIDE = "skills"

#: What a copied grant carries, naming where it came from. Inside the copy so it cannot be orphaned
#: from what it describes, and dot-prefixed so no brain reads it as part of the skill.
RECORD = ".rundesk-grant.json"

#: Every root a brain this product knows about reads, relative to the agent's home.
#:
#: Measured rather than read off documentation: claude reads only `.claude/skills`; codex reads
#: `.agents/skills` and `.codex/skills`; grok reads its own, `.agents`, `.claude` and `.cursor`. A
#: bare `skills/` is read by none of them, which is exactly why rundesk's own directory is safe to
#: call that.
VENDOR_ROOTS = (
    ".claude/skills",
    ".codex/skills",
    ".agents/skills",
    ".grok/skills",
)


class Refused(Exception):
    """Something that may not be done to a grant, named with why."""


class Occupied(Refused):
    """The name a grant would stand under is already taken by another skill.

    Its own kind, because it is the one refusal here with a way out — `--as` — and a caller has to be
    able to tell it apart from every other. Re-deriving it from the address afterwards does not work
    and was measured doing the wrong thing: `grant alan writing-plans` is refused for its *shape*, and
    an unknown catalog is refused for *not existing*, yet both leave a trailing name the agent may
    well hold, so both were offered an alias that would not have helped.

    Still a `Refused`, so anything catching that goes on working.
    """


class Grant(NamedTuple):
    """One skill standing in one agent's directory.

    `catalog` and `skill` are where it came from, read back off the link's own target or off a
    copy's record — so a grant explains itself without anything having written a register. Both are
    `""` when it cannot be told, which is what an entry somebody made by hand looks like.

    `name` is the directory it stands under and therefore the name a brain knows it by. It differs
    from `skill` exactly when the grant was made with `--as`.

    `resolves` is whether there is still something on the other end. A grant whose catalog was
    removed, or whose skill left one, is still standing here and answers `False`.
    """

    agent: str
    name: str
    at: Path
    catalog: str
    skill: str
    copied: bool
    resolves: bool

    @property
    def address(self) -> str:
        """How the skill behind this grant is named on a command line. `""` when it cannot be told."""
        return f"{self.catalog}/{self.skill}" if self.catalog and self.skill else ""


def where(agent: str) -> Path:
    """Where this agent's grants stand."""
    return directory.home(agent) / INSIDE


def held(agent: str) -> List[Grant]:
    """Everything standing in this agent's own skills directory, in name order.

    Reads whatever is there rather than only what rundesk put there. An entry somebody made by hand
    is a real grant — the brain will load it — so a listing that showed only rundesk's own would be
    telling somebody about a smaller set than their agent actually has.
    """
    at = where(agent)
    if not at.is_dir():
        return []
    return [_read(agent, at / one.name)
            for one in sorted(at.iterdir(), key=lambda entry: entry.name)
            if not one.name.startswith(".") and not files.staged(one.name)]


def holding(agent: str, name: str) -> Optional[Grant]:
    """The grant standing under `name`, or `None` when there is not one."""
    return next((one for one in held(agent) if one.name == name), None)


def granted(agent: str, skill: library.Skill, alias: str = "") -> Grant:
    """Give this agent a skill. Returns the grant that now stands there.

    A link, unless `alias` names something different from the skill's own name — see the module
    docstring for why that case has to be a copy.

    The name is checked, then the collision, then anything is written. A refusal that has already
    made a directory is a refusal that leaves the agent in a state nobody asked for.
    """
    name = alias or skill.name
    trouble = library.skill_trouble(name)
    if trouble:
        raise Refused(trouble)
    _agent_must_exist(agent)

    at = where(agent)
    standing = at / name
    if standing.is_symlink() or standing.exists():
        raise Occupied(_already_holding(agent, name))

    at.mkdir(parents=True, exist_ok=True)
    if name == skill.name:
        # Relative, so moving or copying an agent's whole directory does not leave every grant
        # pointing at where some other machine kept its library.
        standing.symlink_to(os.path.relpath(skill.at, at))
    else:
        _copied(skill, standing)
    presented(agent)
    return _read(agent, standing)


def revoked(agent: str, name: str) -> Grant:
    """Take a grant away. Returns what was standing there.

    Read before it is removed, so the caller can say which catalog it came from — that is the one
    fact a person needs to grant it again, and after the removal there is nothing left to ask.
    """
    _agent_must_exist(agent)
    standing = holding(agent, name)
    if standing is None:
        raise Refused(f"{agent} does not hold {name} — rundesk skills list {agent} says what it has")
    files.remove_one(standing.at)
    presented(agent)
    return standing


def presented(agent: str) -> List[Path]:
    """Stand this agent's grants where each brain looks, and take away only what is ours. Returns
    every link made or removed.

    Safe to run on an agent whose links are already right, which is what makes it callable after
    every grant, every revoke, every catalog update and every `rundesk update` without anybody
    having to work out whether it is needed.

    **Nothing granted and no root already there means no directory is made at all.** An agent with
    no skills should not have four vendors' directories in its home to explain to itself.
    """
    home = directory.home(agent)
    wanted = {one.name for one in held(agent)}
    touched: List[Path] = []
    for root in VENDOR_ROOTS:
        at = home / root
        if not wanted and not at.is_dir():
            continue
        at.mkdir(parents=True, exist_ok=True)
        touched.extend(_linked(at, where(agent), wanted))
        touched.extend(_pruned(at, where(agent), wanted))
    return touched


def retired(catalog: str, gone: List[str]) -> Dict[str, List[str]]:
    """Take away every grant of a skill that is no longer in `catalog`. Maps agent to what went.

    Called when a catalog is updated or removed. A grant left pointing at a skill that is not there
    is a link every brain skips in silence, so an agent would go on being described as holding
    something it cannot use.

    **Matched on where the grant points rather than on its name**, so an agent holding
    `acme/writing-plans` keeps it when `rundesk-skills/writing-plans` goes away. The name is the same
    and the skill is not, and a match on the name would revoke the wrong one.
    """
    if not gone:
        return {}
    went: Dict[str, List[str]] = {}
    for agent in directory.known():
        for one in held(agent):
            if one.catalog != catalog or one.skill not in gone:
                continue
            files.remove_one(one.at)
            went.setdefault(agent, []).append(one.name)
        if agent in went:
            presented(agent)
    return went


def stale(grant: Grant) -> bool:
    """Whether a copied grant no longer matches the skill it was copied from.

    Only ever true of a copy — a link cannot be out of date with what it points at, which is the
    whole reason the ordinary grant is one.

    Compared by content rather than by the catalog's version. A catalog author who edits a skill
    without bumping a number is the ordinary case this product is built to follow, so a version
    comparison would report a copy as current while it silently was not.
    """
    if not grant.copied:
        # Including a copy whose record has gone. Without it there is nothing saying rundesk put
        # this directory here, so it is read as something the owner made — and remaking it would be
        # overwriting work this cannot prove is its own. The same reasoning as the narrow pruning.
        return False
    source = library.where() / grant.catalog / library.TREE / library.INSIDE / grant.skill
    if not (source / library.DECLARED).is_file():
        # Dangling, which is a different answer and a different sentence. Reporting it out of date
        # would send somebody to a command that cannot help — there is nothing to remake it from.
        return False
    how, said = files.read_json(grant.at / RECORD)
    kept = said.get("digest") if how == files.READ and isinstance(said, dict) else None
    # A record with no digest in it — one written by a release before this one — compares unequal
    # to anything and the copy is simply made again, which is the cheap and correct answer.
    return kept != _digest(source)


def refreshed(saying: Optional[Callable[[str], None]] = None) -> List[str]:
    """Make every copied grant again where its source has moved. Returns the ones remade.

    Run after a catalog changes and on every `rundesk update`. A copy is the one thing in this
    package that can silently drift, so the thing that made it also has to be what keeps it, and it
    has to be called from somewhere that always runs rather than from wherever a copy happens to be
    made.
    """
    said = saying or (lambda _line: None)
    remade = []
    for agent in directory.known():
        for one in held(agent):
            if not stale(one):
                continue
            source = library.where() / one.catalog / library.TREE / library.INSIDE / one.skill
            _copied(library.read_skill(one.catalog, source), one.at)
            remade.append(f"{agent}/{one.name}")
            said(f"made {one.name} again for {agent}, from {one.catalog}")
    return remade


def _agent_must_exist(agent: str) -> None:
    """Refuse before anything is written when there is no such agent.

    `directory.home` answers a path for a name nothing stands under, so a grant to a misspelled
    agent would otherwise make the directory and report success — and the person would look for it
    under the name they meant.
    """
    if agent not in directory.known():
        raise Refused(f"there is no agent called {agent} — rundesk agents list says who there is")


def _already_holding(agent: str, name: str) -> str:
    """Why a second skill cannot stand under a name, and the two ways out.

    The words are here rather than at the caller because this is the refusal the whole
    catalog-scoped design leads to, and it is the one a person meets while doing something
    reasonable. It has to say what is in the way, and it has to be copy-pasteable.
    """
    standing = holding(agent, name)
    from_where = f", from {standing.catalog}" if standing and standing.catalog else ""
    return (f"{agent} already holds {name}{from_where} — a brain finds a skill by its directory "
            f"name, so two cannot stand as one")


def _read(agent: str, at: Path) -> Grant:
    """What is standing at `at`, and where it came from.

    A copy says so in its own record. A link says so by where it points, which is read with
    `readlink` rather than `resolve` — a link whose target has gone still names the catalog it came
    from, and that is exactly the case somebody needs told.
    """
    if at.is_symlink():
        catalog, skill = _pointed_at(at)
        return Grant(agent, at.name, at, catalog, skill, False, at.exists())
    how, said = files.read_json(at / RECORD)
    if how == files.READ and isinstance(said, dict):
        return Grant(agent, at.name, at, str(said.get("catalog", "")), str(said.get("skill", "")),
                     True, (at / library.DECLARED).is_file())
    return Grant(agent, at.name, at, "", "", False, (at / library.DECLARED).is_file())


def _pointed_at(at: Path) -> Tuple[str, str]:
    """The catalog and skill a grant's link names, or two empty strings when it names neither.

    **Read one hop, with `readlink`, and normalised rather than resolved.** The question is which
    catalog rundesk linked this into, and that is what the link itself says — not where a chain of
    them happens to end. A skill in the owner's own catalog may perfectly well be a link into a
    repository they are working in, which is the obvious way to write one; resolving would follow it
    straight out of the library and the grant could no longer say where it came from, so nothing
    could group it in a listing or retire it when its catalog went.
    """
    points = Path(os.readlink(at))
    if not points.is_absolute():
        points = at.parent / points
    settled = Path(os.path.normpath(str(points)))
    try:
        inside = settled.relative_to(Path(os.path.normpath(str(library.where()))))
    except ValueError:
        return "", ""
    parts = inside.parts
    if len(parts) == 4 and parts[1] == library.TREE and parts[2] == library.INSIDE:
        return parts[0], parts[3]
    return "", ""


def _copied(skill: library.Skill, to: Path) -> None:
    """Make a copy of a skill standing under a different name, and prove it is still a skill.

    Built under a staged name and renamed into place, so an interruption never leaves a directory
    that has a `SKILL.md` and is not the skill it claims to be. The rewrite is checked afterwards
    rather than trusted: a frontmatter this could not rewrite is a copy every brain would index
    under the source's name, which is the exact collision the alias existed to avoid.
    """
    building = files.incoming_of(to)
    files.discard(building)
    try:
        shutil.copytree(skill.at, building, symlinks=False)
        said = (building / library.DECLARED).read_text(encoding="utf-8")
        (building / library.DECLARED).write_text(_renamed(said, to.name), encoding="utf-8")
        files.write_json(building / RECORD, {
            "catalog": skill.catalog, "skill": skill.name, "as": to.name,
            "digest": _digest(skill.at), "copied_at": library.stamped()})
        trouble = library.trouble_with(building, to.name)
        if trouble:
            raise Refused(f"{skill.address} could not be copied as {to.name}: {trouble}")
        files.discard(to)
        os.replace(building, to)
    except BaseException:
        files.discard(building)
        raise


def _renamed(said: str, to: str) -> str:
    """A `SKILL.md` with its frontmatter `name:` changed, and the rest of it untouched.

    **Bounded to the opening block by construction rather than by a condition.** A `name:` in the
    body is prose the author wrote — a skill about writing skills contains a worked example of
    frontmatter, `name:` at the start of a line — and rewriting it would be this changing somebody's
    documentation to suit a directory. Slicing to the block is what makes that impossible; a
    condition inside a walk over the whole file would be one somebody could later relax without
    seeing what it was holding.

    The first `name:` in the block, because that is what `_frontmatter` would call the answer if
    there were only one. **Where there are two it is not**, and that is exactly the case
    `library.trouble_with` catches after this has run: the reader takes the last and this changes
    the first, so the copy comes out still naming the source and is refused rather than granted.
    """
    lines = said.splitlines(keepends=True)
    if not lines or lines[0].strip() != library.FENCE:
        return said
    closes = next((at for at in range(1, len(lines)) if lines[at].strip() == library.FENCE),
                  len(lines))
    for at in range(1, closes):
        if not lines[at].startswith((" ", "\t")) and lines[at].partition(":")[0].strip() == "name":
            lines[at] = f"name: {to}\n"
            break
    return "".join(lines)


def _digest(at: Path) -> str:
    """What a skill directory currently is, as one value that changes when any of it does.

    Every file's path and every file's bytes, in a fixed order. The path is in there as well as the
    contents because a file being renamed, added or removed is a change to the skill and hashing
    only contents would miss all three.
    """
    running = hashlib.sha256()
    for one in sorted(at.rglob("*")):
        if one.is_dir() or one.is_symlink():
            continue
        running.update(str(one.relative_to(at)).encode("utf-8"))
        running.update(b"\0")
        running.update(one.read_bytes())
        running.update(b"\0")
    return running.hexdigest()


def _linked(root: Path, grants: Path, wanted: Set[str]) -> List[Path]:
    """Stand every granted skill in one vendor's root. Returns the links made.

    An entry that is already the right link is left alone rather than remade, so running this on an
    agent whose links are correct writes nothing at all — which is what makes it safe to call after
    everything.
    """
    made = []
    for name in sorted(wanted):
        at = root / name
        points = os.path.relpath(grants / name, root)
        if at.is_symlink():
            if os.readlink(at) == points:
                continue
            at.unlink()
        elif at.exists():
            # Somebody else's, and not ours to replace. A real directory here is a skill a person
            # or a vendor's own installer put in this brain's root, and it is not rundesk's.
            continue
        at.symlink_to(points)
        made.append(at)
    return made


def _pruned(root: Path, grants: Path, wanted: Set[str]) -> List[Path]:
    """Take away the links in one vendor's root that rundesk made and no longer should. Returns them.

    **Ours is decided by where a link points, not by it being broken.** An owner's own link to a
    volume that is not mounted is dangling and is not ours; a link into this agent's own grants
    directory is ours whether it currently resolves or not. The build this replaced had it the other
    way round and deleted somebody's link while a drive was unplugged.
    """
    gone = []
    for one in sorted(root.iterdir(), key=lambda entry: entry.name):
        if not one.is_symlink() or one.name in wanted:
            continue
        points = Path(os.readlink(one))
        if not points.is_absolute():
            points = one.parent / points
        settled = Path(os.path.normpath(str(points)))
        if settled.parent != Path(os.path.normpath(str(grants))):
            continue
        one.unlink()
        gone.append(one)
    return gone
