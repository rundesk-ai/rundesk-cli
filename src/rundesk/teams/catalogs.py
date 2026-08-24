"""Read and validate the team declaration carried by a skill catalog.

The repository is untrusted data. This module accepts no executable hook and resolves every
instruction path beneath the fetched tree before a command may install or update anything.
"""

from pathlib import Path
from typing import Dict, List, NamedTuple

from rundesk.agents import directory
from rundesk.skills import library
from rundesk.utils import files

SCHEMA = 2
LEGACY_SCHEMA = 1
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


class Dependency(NamedTuple):
    """A shared skill catalog a team requires, without copying it into the team."""

    name: str
    source: str


class Team(NamedTuple):
    name: str
    at: Path
    dependencies: List[Dependency]
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
            and held.get("schema") in (LEGACY_SCHEMA, SCHEMA)
            and set(held) == ({"schema", "name", "members"} if held.get("schema") == LEGACY_SCHEMA
                              else {"schema", "name", "catalogs", "members"})
            and isinstance(held.get("members"), list))


def read(at: Path, manifest: library.Manifest) -> Team:
    """Read a team from a fetched catalog tree, refusing the complete declaration at once."""
    declared = at / library.TEAM
    how, held = files.read_json(declared)
    if how == files.MISSING:
        raise Refused(f"there is no {library.TEAM} in {at} — this is a skill catalog, not a team")
    if how == files.UNREADABLE or not isinstance(held, dict):
        raise Refused(f"{declared} is not a readable JSON object")
    schema = held.get("schema")
    wanted = ({"schema", "name", "members"} if schema == LEGACY_SCHEMA
              else {"schema", "name", "catalogs", "members"})
    if schema not in (LEGACY_SCHEMA, SCHEMA):
        raise Refused(f"{declared} declares schema {held.get('schema')!r} and this release "
                      f"understands {LEGACY_SCHEMA} and {SCHEMA}")
    if set(held) != wanted:
        raise Refused(f"{declared} must contain exactly " + ", ".join(sorted(wanted)))
    if held.get("name") != manifest.name:
        raise Refused(f"{declared} calls this team {held.get('name')!r} and {library.MANIFEST} "
                      f"calls the catalog {manifest.name!r}")
    dependencies = [] if schema == LEGACY_SCHEMA else _dependencies(declared, held.get("catalogs"))
    if any(one.name == manifest.name for one in dependencies):
        raise Refused(f"{declared} declares its own catalog as a dependency")
    raw_members = held.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise Refused(f"{declared} needs at least one member")

    members = [_member(at, declared, raw, manifest.name, schema, dependencies)
               for raw in raw_members]
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
    return Team(manifest.name, at, dependencies, members)


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


def dependents(catalog: str) -> Dict[str, List[str]]:
    """Installed teams and the skills for which they rely on one shared catalog."""
    answer = {}
    for name in library.known():
        if not library.is_team(name):
            continue
        team = installed(name)
        needed = required(team).get(catalog)
        if needed is not None:
            answer[name] = needed
    return answer


def _dependencies(declared: Path, raw) -> List[Dependency]:
    if (not isinstance(raw, list)
            or any(not isinstance(one, dict) or set(one) != {"name", "source"} for one in raw)):
        raise Refused(f"{declared} needs catalogs containing exactly name and source")
    dependencies = []
    for one in raw:
        name, source = one.get("name"), one.get("source")
        if not isinstance(name, str) or library.name_trouble(name):
            raise Refused(f"{declared} has an invalid dependency catalog name {name!r}")
        if not isinstance(source, str) or not source.strip():
            raise Refused(f"{declared} needs a source for dependency catalog {name}")
        dependencies.append(Dependency(name, source.strip()))
    names = [one.name for one in dependencies]
    if len(names) != len(set(names)):
        raise Refused(f"{declared} names a dependency catalog more than once")
    return dependencies


def required(team: Team) -> Dict[str, List[str]]:
    """Required external skills, grouped by declared dependency catalog."""
    answer = {one.name: [] for one in team.dependencies}
    for member in team.members:
        for address in member.skills:
            catalog, skill = address.split("/", 1)
            if catalog in answer and skill not in answer[catalog]:
                answer[catalog].append(skill)
    return answer


def _member(at: Path, declared: Path, raw, team_name: str, schema: int,
            dependencies: List[Dependency]) -> Member:
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
    if schema == LEGACY_SCHEMA:
        skills = [f"{team_name}/{skill}" for skill in skills]
    addresses = []
    permitted = {team_name} | {one.name for one in dependencies}
    for skill in skills:
        parts = skill.split("/")
        if len(parts) != 2 or any(library.name_trouble(part) for part in parts):
            raise Refused(f"{declared} gives {name} an invalid skill address {skill!r}")
        if parts[0] not in permitted:
            raise Refused(f"{declared} gives {name} a skill from undeclared catalog {parts[0]}")
        addresses.append((parts[0], parts[1]))
    bare = [skill for _catalog, skill in addresses]
    if len(bare) != len(set(bare)):
        raise Refused(f"{declared} gives {name} two skills with the same installed name")
    available = set(library.found(at / library.INSIDE))
    missing = [skill for catalog, skill in addresses if catalog == team_name and skill not in available]
    if missing:
        raise Refused(f"{declared} gives {name} skills this catalog does not hold: "
                      f"{', '.join(missing)}")
    protected = [skill for _catalog, skill in addresses
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
