"""Read and validate the team declaration carried by a skill catalog.

The repository is untrusted data. This module accepts no executable hook and resolves every
instruction path beneath the fetched tree before a command may install or update anything.
"""

from pathlib import Path
from typing import List, NamedTuple

from rundesk.agents import directory
from rundesk.skills import library
from rundesk.utils import files

SCHEMA = 1
AGENTS = "agents"
INSTRUCTIONS = "AGENTS.md"


class Refused(Exception):
    """A team declaration that cannot safely govern agents."""


class Member(NamedTuple):
    name: str
    description: str
    instructions: Path
    skills: List[str]
    delegates_to: List[str]
    self_improve: bool


class Team(NamedTuple):
    name: str
    at: Path
    members: List[Member]


def declared(at: Path) -> bool:
    """Whether a fetched tree carries a structurally recognizable team declaration.

    This is deliberately narrower than file presence. An ordinary skill catalog may already use a
    file called ``team.json`` for its own data; only the exact team envelope routes installation to
    the guarded team lifecycle. Full validation remains ``read``'s job.
    """
    how, held = files.read_json(at / library.TEAM)
    return (how == files.READ
            and isinstance(held, dict)
            and set(held) == {"schema", "name", "members"}
            and held.get("schema") == SCHEMA
            and isinstance(held.get("members"), list))


def read(at: Path, manifest: library.Manifest) -> Team:
    """Read a team from a fetched catalog tree, refusing the complete declaration at once."""
    declared = at / library.TEAM
    how, held = files.read_json(declared)
    if how == files.MISSING:
        raise Refused(f"there is no {library.TEAM} in {at} — this is a skill catalog, not a team")
    if how == files.UNREADABLE or not isinstance(held, dict):
        raise Refused(f"{declared} is not a readable JSON object")
    if set(held) != {"schema", "name", "members"}:
        raise Refused(f"{declared} must contain exactly schema, name and members")
    if held.get("schema") != SCHEMA:
        raise Refused(f"{declared} declares schema {held.get('schema')!r} and this release "
                      f"understands {SCHEMA}")
    if held.get("name") != manifest.name:
        raise Refused(f"{declared} calls this team {held.get('name')!r} and {library.MANIFEST} "
                      f"calls the catalog {manifest.name!r}")
    raw_members = held.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise Refused(f"{declared} needs at least one member")

    members = [_member(at, declared, raw) for raw in raw_members]
    names = [one.name for one in members]
    if len(names) != len(set(names)):
        raise Refused(f"{declared} names a member more than once")
    known = set(names)
    for one in members:
        unknown = [name for name in one.delegates_to if name not in known]
        if unknown:
            raise Refused(f"{declared} lets {one.name} delegate outside this team to "
                          f"{', '.join(unknown)}")
        if one.name in one.delegates_to:
            raise Refused(f"{declared} lets {one.name} delegate to itself")
    return Team(manifest.name, at, members)


def installed(name: str) -> Team:
    """Read an installed team catalog."""
    settled = library.read(name)
    return read(settled.at / library.TREE, settled.manifest)


def owners() -> dict:
    """Map every managed agent name to its installed team, refusing ambiguous ownership."""
    answer = {}
    for name in library.known():
        if not library.is_team(name):
            continue
        for member in installed(name).members:
            previous = answer.get(member.name)
            if previous is not None and previous != name:
                raise Refused(f"{member.name} is declared by both {previous} and {name}")
            answer[member.name] = name
    return answer


def _member(at: Path, declared: Path, raw) -> Member:
    if not isinstance(raw, dict):
        raise Refused(f"a member in {declared} is not an object")
    wanted = {"name", "description", "instructions", "skills", "delegates_to", "self_improve"}
    if set(raw) != wanted:
        raise Refused(f"a member in {declared} must contain exactly " + ", ".join(sorted(wanted)))
    name = raw.get("name")
    if not isinstance(name, str) or directory.name_trouble(name):
        raise Refused(f"{declared} has an invalid member name {name!r}")
    description = raw.get("description")
    if not isinstance(description, str) or directory.describes_trouble(description):
        raise Refused(f"{declared} has an invalid description for {name}")
    skills = raw.get("skills")
    if (not isinstance(skills, list)
            or any(not isinstance(skill, str) for skill in skills)
            or len(skills) != len(set(skills))):
        raise Refused(f"{declared} needs a duplicate-free skills array for {name}")
    available = set(library.found(at / library.INSIDE))
    missing = [skill for skill in skills if skill not in available]
    if missing:
        raise Refused(f"{declared} gives {name} skills this catalog does not hold: "
                      f"{', '.join(missing)}")
    protected = [skill for skill in skills
                 if skill in (library.REQUIRED_SKILL, library.DELEGATING_SKILL)]
    if protected:
        raise Refused(f"{declared} gives {name} product-owned skills: {', '.join(protected)}")
    delegates = raw.get("delegates_to")
    if (not isinstance(delegates, list)
            or any(not isinstance(agent, str) for agent in delegates)
            or len(delegates) != len(set(delegates))):
        raise Refused(f"{declared} needs a duplicate-free delegates_to array for {name}")
    self_improve = raw.get("self_improve")
    if not isinstance(self_improve, bool):
        raise Refused(f"{declared} needs a true or false self_improve setting for {name}")
    instructions = raw.get("instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        raise Refused(f"{declared} needs an instructions path for {name}")
    relative = Path(instructions)
    if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != (AGENTS,):
        raise Refused(f"{declared} has an unsafe instructions path for {name}: {instructions!r}")
    page = at / relative
    try:
        page.resolve().relative_to(at.resolve())
        inside = True
    except ValueError:
        inside = False
    if page.name != INSTRUCTIONS or not page.is_file() or not inside:
        raise Refused(f"{declared} cannot read canonical AGENTS.md for {name} at {instructions}")
    try:
        instructions_text = page.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as why:
        raise Refused(f"{page} is not readable UTF-8 ({why})") from why
    if not instructions_text.strip():
        raise Refused(f"{page} cannot be an empty agent workflow")
    return Member(name, description.strip(), relative, list(skills), list(delegates), self_improve)
