"""The library of skills on this machine, and what makes one.

A skill is a directory holding a `SKILL.md` — YAML frontmatter naming it and saying when
to use it, then Markdown. That format is not ours: it is the open Agent Skills standard,
and all three brains that ship read it unchanged. What is ours is where a skill stands and
which agent was given it.

**Everything lives in one library**, `data/skills/`. Built-ins are copied there by the
install and brought forward by an update; an owner's own stand beside them and are never
touched. Nothing reads out of `app/`, so there is one directory to look at, back up or
carry to another machine, and the answer to "what skills are here" is `ls`.

**Rundesk does not load a skill and never sees one loaded.** A brain discovers what stands
in the agent's own home, by itself. So the only lever with any force is *what is placed
there before the brain runs*, which is why granting is a link in that directory rather
than a rule in a configuration file — a rule would describe what rundesk placed while the
brain went on reading whatever else it found.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
from pathlib import Path

from rundesk import ROOT, data_home

#: What a built-in is copied from. Beside the agent templates and read the same way — by
#: looking, so a skill added to a release is laid down, brought forward and marked without
#: a list kept anywhere else.
SHIPPED = ROOT / "src" / "templates" / "skills"

#: The file that makes a directory a skill. Every brain measured looks for this name.
NAMED = "SKILL.md"

#: What a name may be, and it is the tightest of the three brains rather than ours: grok
#: refuses anything else outright, and a name a loader rejects is a skill that is silently
#: absent rather than one that fails.
ALLOWED = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: How long a description may be. The limit is the specification's, and it is not
#: decoration: the description is the whole of what a brain sees every turn, and the one
#: thing that decides whether a skill is ever reached for.
DESCRIBED_LIMIT = 1024

#: How long a name may be — the shortest limit any of the three enforces.
NAMED_LIMIT = 64


def home() -> Path:
    """Where every skill on this machine stands.

    Derived downwards from the data root rather than given a variable of its own: a second
    name to set is a second name to forget, and `MEMORY.md` records what forgetting one
    cost. Downwards rather than beside, so a suite pointed at a scratch root cannot reach
    the owner's library through it.
    """
    return data_home() / "skills"


def shipped() -> tuple[str, ...]:
    """The skills this release ships, asked of the directory rather than listed.

    A list kept in code is a list that disagrees with the directory the day somebody adds
    a skill and forgets it — and the disagreement is invisible, because a skill that is
    never laid down is simply a skill nobody has.
    """
    if not SHIPPED.is_dir():
        return ()
    return tuple(sorted(one.name for one in SHIPPED.iterdir() if (one / NAMED).is_file()))


def library(where: Path | None = None) -> dict:
    """Every skill on this machine, by name, and the directory each really is.

    **The one place a name is resolved**, so granting, the catalog, a diagnosis and what an
    adapter places can never disagree about which directory a word means. A directory
    without a `SKILL.md` is not a skill and is not listed — an owner half way through
    writing one has not broken anything.
    """
    where = where or home()
    try:
        found = sorted(one for one in where.iterdir() if (one / NAMED).is_file())
    except OSError:
        # No library yet, or one that cannot be read. An owner who has never made a skill
        # is the ordinary case and never an error.
        return {}
    return {one.name: one for one in found}


def valid(at: Path) -> str | None:
    """Why this is not a skill, or `None` if it is one.

    Checked where a skill is granted rather than described in prose somewhere, because
    every one of these is a rule a *brain* enforces: a name with an underscore or a
    description that runs past the limit is not refused by rundesk, it is quietly dropped
    by the loader, and an owner is left with a skill that exists and never fires.
    """
    if not at.is_dir():
        return f"there is nothing at {at}"
    page = at / NAMED
    if not page.is_file():
        return f"{at.name} has no {NAMED} in it"
    if len(at.name) > NAMED_LIMIT:
        return f"the name {at.name} is longer than {NAMED_LIMIT} characters"
    if not ALLOWED.match(at.name):
        return (f"the name {at.name} is not lowercase letters, digits and single hyphens, "
                "which is the only shape every brain accepts")
    try:
        text = page.read_text(encoding="utf-8")
    except OSError as why:
        return f"{page} could not be read: {why}"
    said = _frontmatter(text)
    if said is None:
        return f"{at.name}'s {NAMED} does not open with a --- frontmatter block"
    if said.get("name") != at.name:
        return (f"{at.name}'s {NAMED} names it '{said.get('name') or ''}' — the name and the "
                "directory have to be the same word, or a brain indexes one and finds the other")
    described = said.get("description") or ""
    if not described.strip():
        return (f"{at.name} says nothing about when to use it, which is the whole of what a "
                "brain sees — it would never be reached for")
    if len(described) > DESCRIBED_LIMIT:
        return f"{at.name}'s description is longer than {DESCRIBED_LIMIT} characters"
    return None


def _frontmatter(text: str) -> dict | None:
    """The `name` and `description` out of a `SKILL.md`, or `None` if there is no block.

    Two keys read by hand rather than a YAML parser, because the standard library has
    none and the whole of what is needed here is two scalars at the top level. Anything
    else in the block is somebody's business and is neither read nor disturbed.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    said: dict = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return said
        what, _, rest = line.partition(":")
        if rest and what.strip() in ("name", "description") and not what.startswith((" ", "\t")):
            said[what.strip()] = rest.strip().strip("'\"")
    return None    # opened a block and never closed it, which is not a frontmatter


def lay_down(where: Path | None = None, force: bool = False) -> list[str]:
    """Put the skills this release ships into the library, and say which moved.

    `force` is what tells an install from an update. An install lays down what is missing
    and leaves anything already there, so a second install is not a thing that overwrites
    work. An update brings every shipped skill forward, because a built-in is rundesk's
    file and the point of it being ours is that it can improve.

    **That is the whole of "always the latest version"** — no record of what was laid down
    last time, no comparison, nothing to get out of step. The set is whatever the release
    ships, read off the directory each time.

    An owner who wants their own version of a built-in copies it under another name, which
    is then theirs and is never a name this touches.
    """
    where = where or home()
    moved = []
    for name in shipped():
        target = where / name
        if target.exists() and not force:
            continue
        try:
            where.mkdir(parents=True, exist_ok=True)
            # **Built whole beside it, then swapped in.** Removing the old one and copying
            # the new one in its place leaves, if anything fails between the two, a
            # directory that exists and has no `SKILL.md` — which is not a skill, is
            # skipped in silence by every brain, and leaves a grant that still resolves so
            # nothing reports it. Assembling under another name means the worst a failure
            # leaves is the version that was already working.
            coming = where / f".{name}.coming"
            shutil.rmtree(coming, ignore_errors=True)
            shutil.copytree(SHIPPED / name, coming)
            if target.exists():
                shutil.rmtree(target)
            os.replace(coming, target)
        except OSError:
            shutil.rmtree(where / f".{name}.coming", ignore_errors=True)
            # A library that cannot be written to is a thing to say elsewhere, in words,
            # rather than a traceback out of the middle of an install that otherwise
            # worked. What is missing is reported by a diagnosis.
            continue
        moved.append(name)
    return moved


def take_back(where: Path | None = None) -> list[str]:
    """Take the skills this release laid down back out of the library, and say which went.

    **The mirror of `lay_down`, and R-RM-7 is why it exists**: removing rundesk takes what
    the install put there for it. A built-in is rundesk's file — that is the whole of why it
    can be replaced by an update without asking — so leaving it behind is leaving a piece of
    the program on a machine somebody has removed the program from. It also left the library,
    and with it the whole install directory, standing after an uninstall that reported having
    left nothing.

    **Whatever the owner wrote stays.** The set taken is the set this release ships, read off
    the same directory `lay_down` reads, so a skill of their own — including one that is a
    copy of a built-in under another name, which is exactly what the built-ins tell them to
    make — is not a name this touches.

    An empty library goes too. A directory left holding nothing is not something the owner
    keeps, and it is the difference between an install directory that can be removed and one
    that cannot.
    """
    where = where or home()
    if not where.is_dir():
        return []
    gone = []
    for name in shipped():
        standing = where / name
        if not standing.is_dir() or standing.is_symlink():
            continue
        try:
            shutil.rmtree(standing)
        except OSError:
            # A library that cannot be written to is not a reason to fail a removal that has
            # already taken the program. What is left is reported by what is left.
            continue
        gone.append(name)
    with contextlib.suppress(OSError):
        where.rmdir()          # only when nothing of the owner's is in it
    return gone


def granted(skills_dir: Path) -> list[str]:
    """The skills this agent was given, which is what stands in its own skills directory.

    **The grant is the directory, not a record of one.** There is no second copy to
    disagree with it, `ls` reads it and `rm` revokes it — and it is the only thing with
    any force, because what a brain finds is what is standing there when it runs.
    """
    try:
        return sorted(one.name for one in skills_dir.iterdir()
                      if (one / NAMED).is_file() or one.is_symlink())
    except OSError:
        return []


def ours(entry: Path, where: Path | None = None) -> bool:
    """Whether this entry is a link rundesk made into the library.

    Asked before anything is removed. A real directory somebody wrote by hand, and a link
    pointing somewhere else entirely, are both things rundesk did not put there and has no
    business taking away — revoking has to be incapable of deleting an owner's work rather
    than careful about it.
    """
    if not entry.is_symlink():
        return False
    where = (where or home()).resolve()
    try:
        target = entry.resolve()
    except OSError:
        return False
    return where in target.parents


def _standing(skills_dir: Path, name: str) -> Path:
    """Where a grant by that name would stand, or a refusal.

    **A name is one path component and is checked before it is joined to anything.**
    `Path("/a/b") / "/elsewhere"` is `/elsewhere` — the left side is discarded outright —
    so a name taken from a command line and joined without looking is a way to name any
    file on the machine. `revoke` then unlinks it. Everything about confinement here rests
    on this one check, so it happens before the join rather than after.
    """
    # `os.altsep` is None everywhere but Windows, and `"" in name` is true of every string
    # — so testing it without the guard refuses every name there is. Caught by the suite
    # immediately, which is the only reason it is worth a comment rather than a scar.
    separators = [os.sep] + ([os.altsep] if os.altsep else [])
    if not name or name in (".", "..") or any(one in name for one in separators):
        raise Unknown(f"'{name}' is not a skill's name")
    return skills_dir / name


def grant(skills_dir: Path, name: str, where: Path | None = None) -> None:
    """Give this agent that skill, by standing a link to it in the agent's own directory.

    A link rather than a copy: an owner editing the library edits what every agent holding
    it reads, with nothing to re-run. Measured on all three brains, including through a
    link to a link, which is what an owner keeping their library elsewhere produces.
    """
    where = where or home()
    at = library(where).get(name)
    if at is None:
        raise Unknown(f"there is no skill called {name}")
    why = valid(at)
    if why:
        raise NotASkill(why)
    standing = _standing(skills_dir, name)
    skills_dir.mkdir(parents=True, exist_ok=True)
    if standing.is_symlink() or standing.exists():
        if not ours(standing, where):
            raise InTheWay(f"{standing} is not something rundesk put there")
        standing.unlink()
    # Relative, so moving or copying an agent's directory does not leave every grant
    # pointing at where the old machine kept its library.
    standing.symlink_to(os.path.relpath(at, skills_dir))


def revoke(skills_dir: Path, name: str, where: Path | None = None) -> None:
    """Take that skill away from this agent, and touch nothing else."""
    standing = _standing(skills_dir, name)
    if not standing.is_symlink() and not standing.exists():
        raise Unknown(f"this agent was never given {name}")
    if not ours(standing, where):
        raise InTheWay(f"{standing} is not something rundesk put there")
    standing.unlink()


class Unknown(Exception):
    """A skill nobody has, or one this agent was never given."""


class NotASkill(Exception):
    """A directory in the library that no brain would index."""


class InTheWay(Exception):
    """Something stands where a grant would, and rundesk did not put it there."""
