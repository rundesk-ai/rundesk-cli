"""Where skills stand, what makes a directory a catalog and a skill, and what is written beside one.

    data/skills/
      rundesk-skills/           a catalog, named as it calls itself
        catalog.json            where it came from and what was last fetched
        app/                    the catalog's own tree, verbatim
          manifest.json         what makes the directory a catalog
          skills/
            writing-plans/
              SKILL.md          what makes the directory a skill
      local/                    the owner's own, never fetched and never removed by rundesk
        app/skills/my-thing/SKILL.md

## Everything is in a catalog

The build this replaces kept one flat `data/skills/<name>` shared by every catalog, and the cost was
exactly what a flat namespace always costs: a second catalog offering a name the first already had
could not be installed at all — not the colliding skill, the whole catalog. An owner who wanted both
had to fork one.

Here a catalog is a directory and nothing is shared, so two catalogs offering `writing-plans` is
ordinary. The collision moves to the one place it is unavoidable — a single agent cannot hold two
directories under one name, because a brain finds a skill by its directory name — and `grants` is
where that is answered.

**The owner's own skills are a catalog too**, called `local`. Not a special case standing beside the
catalogs with its own rules, but the same shape with nothing fetching into it: one walker, one
address format, one answer to where a skill is. What makes it different is written down in one place,
`catalogs.may_be_fetched`, rather than spread across every function that walks the library.

## What makes a directory a catalog, and a directory a skill

`app/manifest.json` and `SKILL.md`, and nothing else — the same rule `agents` uses for `state.db`,
for the same reason. A directory half-built exists; a directory holding the file that describes it has
been finished. `catalog.json` is deliberately *not* the test: it records where a catalog was fetched
from, and `local` was never fetched from anywhere.

## Skills are found, not listed

`manifest.json` says what the catalog is and never which skills it holds — those are read off
`app/skills/*/SKILL.md`, the way migration steps, test suites and agents are already found in this
tree. The build this replaces listed each skill in the manifest with its path, which meant three
places had to agree about one name: the manifest entry, the directory, and the `SKILL.md` frontmatter.
They disagreed, and every disagreement was a catalog that installed and then behaved as though a skill
were not there. There is now one place, and it is the directory.

A catalog whose walk finds no skill is refused. Anything that finds its own work fails when it finds
none: a catalog with nothing in it is a repository somebody pointed at the wrong branch, and installing
it silently is how that goes unnoticed until an agent reaches for something.
"""

import datetime
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

from rundesk.core import paths
from rundesk.utils import files

#: The catalog that ships inside the release. **Version-coupled, and therefore never fetched.**
#:
#: What is in it is how to operate *this* rundesk and how to write a skill for it, so it has to move
#: when the release moves and must not be governed by a repository on its own schedule: a machine on
#: an older release would otherwise be handed instructions for a newer one. It is replaced out of the
#: release on every install and update, and it cannot be removed.
BUNDLED = "rundesk"

#: The general catalog rundesk depends on, fetched from GitHub like any other and equally undeletable.
#:
#: Kept apart from `BUNDLED` because nothing in it is coupled to a version — how to write a pull
#: request does not change when rundesk does — so it belongs on its own release schedule, where it can
#: be corrected without cutting a rundesk release.
DEPENDED = "rundesk-skills"

#: The catalog an owner's own skills stand in. Nothing fetches into it and nothing removes it.
MINE = "local"

#: The catalog's own tree, exactly as it was fetched. Everything rundesk writes about a catalog
#: stands *beside* this rather than inside it, so a re-fetch can replace the whole of it at once.
TREE = "app"

#: What makes the directory a catalog, inside the tree because the catalog's author wrote it.
MANIFEST = "manifest.json"

#: What rundesk wrote down about a catalog, beside the tree because rundesk wrote it.
PROVENANCE = "catalog.json"

#: Where a catalog keeps its skills, inside its tree.
INSIDE = "skills"

#: What makes the directory a skill. Every provider CLI already reads this name.
DECLARED = "SKILL.md"

#: How a skill's frontmatter block opens and closes. Public because `grants` rewrites a name inside
#: one, and two modules spelling the same convention are two modules that eventually spell it
#: differently.
FENCE = "---"

#: Where a skill keeps the commands it ships, if it ships any.
SCRIPTS = "scripts"

#: The note the install writes into the library, and therefore a name no catalog may have.
NOTE = "README.md"

#: The manifest contract this release understands. A catalog declaring anything else is refused
#: rather than read optimistically: a field this release has never heard of may be the one that says
#: the skills are somewhere different.
SCHEMA = 1

#: The longest a skill's name may be — the shortest limit any of the three brains enforces.
NAMED_LIMIT = 64

#: The longest a description may be. It is the whole triggering mechanism, and it is loaded on every
#: turn whether the skill is used or not, so the limit is real rather than defensive.
DESCRIBED_LIMIT = 1024

#: What a skill may be called. The tightest of the three brains, because a name only one of them
#: accepts is a skill that silently does not exist for the other two.
CALLED = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: How a skill is addressed on the command line, and the reason it is not just a name: two catalogs
#: may both hold `writing-plans`, and a verb that took the bare name would have to guess.
ADDRESS = "<catalog>/<skill>"


class Refused(Exception):
    """Something the library will not do or cannot read, named with why.

    A sentence rather than a code, because every caller has to tell somebody what to type instead,
    and a caller left to invent that wording is a caller that invents a different one.
    """


class Manifest(NamedTuple):
    """What a catalog says it is. Four fields, and that is the whole contract.

    Deliberately small. Every field a catalog format carries is a field an author can get wrong, a
    field this release has to keep understanding for ever, and a field somebody has to document. The
    one thing genuinely worth declaring — which skills are here — is not declared at all, because the
    directory already says it and two answers to one question is the bug this format exists without.
    """

    schema: int
    name: str
    version: str
    description: str


class Provenance(NamedTuple):
    """Where a catalog came from and what was last brought down from there.

    `etag` is what makes a daily check cheap: it goes back out on the next fetch as `If-None-Match`,
    and a catalog nobody has touched answers `304` with no body at all. Empty when the source could
    not offer one, which is not an error — it only means the next check downloads.

    **`version` is recorded and never decides anything.** What is on the far end is authoritative
    whether its version moved or not, because a catalog whose author edited a skill without bumping
    a number is still a catalog this install should be running. Deciding on the version is how the
    build this replaces came to re-download every catalog on every update to find that out.
    """

    source: str
    etag: str
    version: str
    fetched_at: str


class Catalog(NamedTuple):
    """One catalog on this install: what it calls itself, where it stands, and what it says it is.

    `provenance` is `None` for a catalog nothing fetched — `local`, and any catalog whose record was
    lost. Absent rather than blank, because "never fetched" and "fetched from nowhere" are different
    facts and a caller that cannot tell them apart will offer to update the first one.
    """

    name: str
    at: Path
    manifest: Manifest
    provenance: Optional[Provenance]


class Skill(NamedTuple):
    """One skill: which catalog holds it, what it is called, where it stands, and what it is for.

    `description` is carried because it is the only part of a skill that is read on every turn
    whether the skill is used or not, so it is what a listing should show — and reading it means the
    frontmatter has already been validated, which is why nothing hands back a `Skill` it has not
    checked.
    """

    catalog: str
    name: str
    at: Path
    description: str

    @property
    def address(self) -> str:
        """How this skill is named on a command line."""
        return f"{self.catalog}/{self.name}"


def where() -> Path:
    """The library: one directory per catalog, and the skills inside each.

    Resolved through `paths` on every call and cached nowhere, like everything else in this product.
    """
    return paths.skills()


def stands(name: str) -> Path:
    """This catalog's own directory, refused when the name reaches somewhere else.

    **Checking the name is not enough, and this is not theoretical** — `agents.directory.where`
    carries the measurement: with a directory replaced by a symbolic link, every individual removal
    below it refused to follow a link, was individually correct, and the operation still reached a
    directory that had nothing to do with rundesk. The guard belongs on the way *in*, because once a
    path has been derived it is already outside.

    Resolved on both sides: the library may itself be reached through a link — `/tmp` is
    `/private/tmp` on this platform — so comparing what was typed would refuse an ordinary install. A
    name nothing stands under yet resolves to itself, so installing a catalog passes and installing
    one over a link does not.
    """
    trouble = name_trouble(name)
    if trouble:
        raise Refused(trouble)
    library = where()
    at = library / name
    if at.resolve().parent != library.resolve():
        raise Refused(f"{name} does not stand where catalogs are kept — it reaches {at.resolve()}")
    return at


def tree(name: str) -> Path:
    """This catalog's own tree — the part a fetch replaces whole."""
    return stands(name) / TREE


def name_trouble(said: str) -> str:
    """Why `said` may not be a catalog name, or `""` when it may.

    A catalog name is a directory name and the same rules apply, plus the one this directory adds:
    the library holds the install's own note, so a catalog called `README.md` would want the same
    file. `agents.directory` refuses its own note's name for exactly this reason.
    """
    trouble = files.name_trouble(said)
    if trouble:
        return trouble
    if said == NOTE:
        return f"{NOTE} is the note standing in the library, so it cannot also be a catalog"
    return ""


def skill_trouble(said: str) -> str:
    """Why `said` may not be a skill name, or `""` when it may.

    Tighter than a catalog's, and the tightness is not ours: a skill's directory name is what a brain
    indexes it by, and the three we know about disagree about what they will accept. The narrowest of
    them refuses anything outside `CALLED` outright, so a name the others would have taken is a skill
    that silently does not exist on one machine in three. Refusing it here is the only place anybody
    finds out.
    """
    trouble = files.name_trouble(said)
    if trouble:
        return trouble
    if len(said) > NAMED_LIMIT:
        return f"a skill's name cannot be longer than {NAMED_LIMIT} characters, and {said!r} is " \
               f"{len(said)}"
    if not CALLED.match(said):
        return f"{said!r} is not a name every brain will accept — lowercase letters, digits and " \
               "single hyphens, such as writing-plans"
    return ""


def read_manifest(at: Path) -> Manifest:
    """What the catalog whose tree stands at `at` says it is. Refused when it does not say.

    Every failure names the file, because the person reading this is usually the person writing the
    catalog and "the manifest is wrong" is not something they can act on.
    """
    where_it_is = at / MANIFEST
    how, held = files.read_json(where_it_is)
    if how == files.MISSING:
        raise Refused(f"there is no {MANIFEST} in {at} — a catalog is a directory with one")
    if how == files.UNREADABLE:
        raise Refused(f"{where_it_is} is there and is not readable JSON")
    if not isinstance(held, dict):
        raise Refused(f"{where_it_is} holds {type(held).__name__}, and a manifest is an object")

    schema = held.get("schema")
    if schema != SCHEMA:
        # Refused rather than read anyway. A schema this release has never seen may be the one that
        # says the skills stand somewhere else, and a hopeful reading of it installs an empty catalog
        # while reporting success.
        raise Refused(f"{where_it_is} declares schema {schema!r} and this release understands "
                      f"{SCHEMA}")
    for field in ("name", "version", "description"):
        said = held.get(field)
        if not isinstance(said, str) or not said.strip():
            raise Refused(f"{where_it_is} needs a {field}, and has {said!r}")
    trouble = name_trouble(held["name"])
    if trouble:
        raise Refused(f"{where_it_is} calls this catalog {held['name']!r}, and {trouble}")
    return Manifest(SCHEMA, held["name"], held["version"].strip(), held["description"].strip())


def read_provenance(at: Path) -> Optional[Provenance]:
    """What rundesk wrote down about the catalog standing at `at`, or `None` when it wrote nothing.

    **An unreadable record answers `None` as well, and that is the safe direction here.** Everything
    a caller does with `None` is offer to fetch again, which rewrites this file — so the worst
    outcome of a record nobody can read is one download. Treating it as an error instead would leave
    a catalog no command could repair, which is the state this product refuses to be able to reach.
    """
    how, held = files.read_json(at / PROVENANCE)
    if how != files.READ or not isinstance(held, dict):
        return None
    source = held.get("source")
    if not isinstance(source, str) or not source.strip():
        return None
    return Provenance(source.strip(), _said(held, "etag"), _said(held, "version"),
                      _said(held, "fetched_at"))


def stated_provenance(at: Path, provenance: Provenance) -> None:
    """Write down where the catalog standing at `at` came from.

    Written whole and renamed into place, so a reader arriving mid-write sees the old record or the
    new one. Beside the tree rather than inside it, because the tree is replaced wholesale by the
    next fetch and a record inside it would be the record of the fetch before.
    """
    files.write_json(at / PROVENANCE, dict(provenance._asdict()))


def stamped(when: Optional[datetime.datetime] = None) -> str:
    """Now, as a moment stored for a machine to compare rather than for a person to read.

    UTC and to the second, the same spelling `config.MOMENT` uses. Anything a person reads goes
    through `utils.logs.stamp` instead, which is local time and says its offset.
    """
    return (when or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def trouble_with(at: Path, called: str = "") -> str:
    """Why the directory at `at` is not a usable skill standing under `called`, or `""` when it is.

    Every rule here mirrors something a brain enforces in silence. A skill that breaks one of them is
    not a skill that works less well — it is one that is skipped without a word, on one machine and
    not another, and the owner's only symptom is an agent that does not seem to know something it was
    granted. Saying so at the moment a catalog is installed is the only point at which anybody finds
    out.

    **`called` is the name it will stand under, and it is not always the directory it is in now.**
    Anything built under a staged name is checked before it is renamed into place — which is the
    whole point of staging it — and a staged name begins with a dot, which is the first thing this
    refuses. Asked without it, this checks the directory it was handed, which is what every ordinary
    caller wants.
    """
    if not at.is_dir():
        return f"{at} is not a directory"
    said = at / DECLARED
    if not said.is_file():
        return f"there is no {DECLARED} in {at}"
    called = called or at.name
    trouble = skill_trouble(called)
    if trouble:
        return trouble
    try:
        text = said.read_text(encoding="utf-8")
    except (OSError, ValueError) as why:
        return f"{said} cannot be read: {why}"

    front = _frontmatter(text)
    if front is None:
        return f"{said} does not open with a --- block naming this skill"
    named = front.get("name", "")
    if named != called:
        return f"{said} calls this skill {named!r} and it stands in {called!r} — a brain indexes " \
               "it by the directory, so the two must agree"
    described = front.get("description", "")
    if not described:
        return f"{said} has no description, and the description is the whole of how a brain decides " \
               "to reach for a skill"
    if len(described) > DESCRIBED_LIMIT:
        return f"{said} has a description of {len(described)} characters and the limit is " \
               f"{DESCRIBED_LIMIT}"
    return ""


def read_skill(catalog: str, at: Path) -> Skill:
    """The skill standing at `at`, read and checked. Refused when it is not one."""
    trouble = trouble_with(at)
    if trouble:
        raise Refused(trouble)
    front = _frontmatter(at.joinpath(DECLARED).read_text(encoding="utf-8")) or {}
    return Skill(catalog, at.name, at, front.get("description", ""))


def found(at: Path) -> List[str]:
    """The names of the skills inside the catalog tree at `at`, in name order.

    Every directory holding a `SKILL.md`, and nothing else. A directory that is not a skill is passed
    over in silence rather than refused: a catalog may reasonably ship a `docs/` or a `.github/`
    beside its skills, and a walk that objected to those would refuse most real repositories.

    **A skill whose `SKILL.md` is invalid is still found here**, because a walk that hid it would
    make a broken skill indistinguishable from one nobody wrote. `trouble_with` is what says why, and
    the caller that installs a catalog is the one that has to care.
    """
    inside = at / INSIDE
    if not inside.is_dir():
        return []
    return sorted(one.name for one in inside.iterdir()
                  if one.is_dir() and not files.staged(one.name) and (one / DECLARED).is_file())


def known() -> List[str]:
    """Every catalog this install has, in name order.

    A directory holding `app/manifest.json`, skipping anything a swap is mid-way through and anything
    reached by a link. A link here would be somebody pointing the library at a directory rundesk
    would then feel free to replace, and following one is how a catalog update comes to overwrite a
    checkout somebody was working in.
    """
    library = where()
    if not library.is_dir():
        return []
    return sorted(one.name for one in library.iterdir()
                  if one.is_dir() and not one.is_symlink() and not files.staged(one.name)
                  and (one / TREE / MANIFEST).is_file())


def read(name: str) -> Catalog:
    """The catalog called `name`. Refused when there is not one."""
    at = stands(name)
    if not (at / TREE / MANIFEST).is_file():
        raise Refused(f"there is no catalog called {name} — rundesk skills catalogs says what "
                      "there is")
    return Catalog(name, at, read_manifest(at / TREE), read_provenance(at))


def catalogs() -> List[Catalog]:
    """Every catalog this install has, read, in name order.

    One that cannot be read is left out rather than raising, because this answers a listing and a
    listing that refuses to say anything about nine healthy catalogs on account of a tenth is worse
    than one that shows nine. `doctor` is where a catalog that cannot be read is somebody's problem.
    """
    settled = []
    for name in known():
        try:
            settled.append(read(name))
        except Refused:
            continue
    return settled


def held(name: str) -> List[Skill]:
    """Every readable skill in the catalog called `name`, in name order.

    A skill whose `SKILL.md` will not validate is left out for the same reason a catalog that cannot
    be read is left out of `catalogs`: this is a listing. What is wrong with it is `trouble_with`'s
    answer, said at install time and again by `doctor`.
    """
    at = tree(name)
    settled = []
    for one in found(at):
        try:
            settled.append(read_skill(name, at / INSIDE / one))
        except Refused:
            continue
    return settled


def every() -> List[Skill]:
    """Every skill this install has, across every catalog, in catalog then name order."""
    return [skill for name in known() for skill in held(name)]


def look_up(address: str) -> Skill:
    """The skill named `<catalog>/<skill>`. Refused when it is not one, saying which half was wrong.

    **A bare name is refused rather than resolved**, even when only one catalog holds it. That is the
    whole reason the address has two halves: a name that is unambiguous today stops being so the
    moment a second catalog is installed, and a command that guessed would then start doing something
    different without anybody changing it. The refusal names every catalog holding that skill, so the
    person is one copy-paste from the right answer rather than one guess from the wrong one.
    """
    catalog, sep, name = address.partition("/")
    if not sep:
        raise Refused(f"{address!r} is not {ADDRESS}{_also_in(address)}")
    if not catalog or not name or "/" in name:
        raise Refused(f"{address!r} is not {ADDRESS}")
    at = tree(catalog) / INSIDE / name
    trouble = skill_trouble(name)
    if trouble:
        raise Refused(trouble)
    if not (at / DECLARED).is_file():
        if catalog not in known():
            raise Refused(f"there is no catalog called {catalog} — rundesk skills catalogs says "
                          "what there is")
        raise Refused(f"{catalog} has no skill called {name} — rundesk skills list says what it has")
    return read_skill(catalog, at)


def _also_in(name: str) -> str:
    """Which catalogs hold a skill of this name, said as a suggestion. `""` when none do.

    The refusal this hangs off is about the *shape* of what was typed, so it must stand on its own
    when nothing matches — a person who mistyped a catalog name has not necessarily named a skill at
    all.
    """
    holding = [one.catalog for one in every() if one.name == name]
    if not holding:
        return ""
    return " — try " + ", or ".join(f"{one}/{name}" for one in holding)


def _said(held_in: Dict[str, object], field: str) -> str:
    """One string out of a record, or `""` when it is missing or is not one."""
    value = held_in.get(field)
    return value.strip() if isinstance(value, str) else ""


#: A block scalar — `description: >` and the indented lines under it. Accepted because the format is
#: YAML and authors write it, and because the alternative is worse in both directions: refusing it
#: rejects a valid skill, and reading only the first line records a description that is not the one
#: on disk. The build this replaces did the second, and its own shipped guide carried an example its
#: own validator would have truncated.
_FOLDED = (">", ">-", ">+", "|", "|-", "|+")


def _frontmatter(said: str) -> Optional[Dict[str, str]]:
    """The top-level keys of a `SKILL.md`'s opening block, or `None` when there is not one.

    **Hand-rolled, because the standard library has no YAML parser and this product has no
    dependencies.** That is a real constraint rather than a preference, so what is parsed is stated
    plainly: a fenced block at the very top, top-level `key: value` pairs, one layer of matching
    quotes stripped, and a folded or literal block gathered from the lines indented under it. Nested
    mappings and lists are ignored rather than misread — nothing here needs one, and the two keys
    that matter are both strings.

    A block that never closes answers `None`. An unterminated fence means the whole file is
    frontmatter as far as any reader is concerned, and guessing where it ended is how a description
    comes to be half a document.
    """
    lines = said.splitlines()
    if not lines or lines[0].strip() != FENCE:
        return None
    try:
        closes = next(at for at in range(1, len(lines)) if lines[at].strip() == FENCE)
    except StopIteration:
        return None

    front: Dict[str, str] = {}
    at = 1
    while at < closes:
        line = lines[at]
        at += 1
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            continue
        value = value.strip()
        if value in _FOLDED:
            value, at = _gathered(lines, at, closes)
        front[key.strip()] = _unquoted(value)
    return front


def _gathered(lines: List[str], at: int, closes: int) -> Tuple[str, int]:
    """The indented lines making up a block scalar, joined, and where reading should carry on.

    Joined with single spaces rather than newlines. Both `>` and `|` are folded the same way here on
    purpose: the two keys this reads are a name and a description, neither of which means anything
    different for having been written across lines, and a description whose line breaks were
    preserved would be measured against `DESCRIBED_LIMIT` including them.
    """
    gathered: List[str] = []
    while at < closes and (not lines[at].strip() or lines[at].startswith((" ", "\t"))):
        if lines[at].strip():
            gathered.append(lines[at].strip())
        at += 1
    return " ".join(gathered), at


def _unquoted(said: str) -> str:
    """One layer of matching quotes taken off a value, if it wears a pair."""
    if len(said) >= 2 and said[0] == said[-1] and said[0] in ("'", '"'):
        return said[1:-1]
    return said
