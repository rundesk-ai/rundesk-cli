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
import hashlib
import os
import re
import shutil
from pathlib import Path

from rundesk import ROOT, skills_home

#: What a built-in is copied from. Beside the agent templates and read the same way — by
#: looking, so a skill added to a release is laid down, brought forward and marked without
#: a list kept anywhere else.
SHIPPED = ROOT / "src" / "templates" / "skills"

#: The file that makes a directory a skill. Every brain measured looks for this name.
NAMED = "SKILL.md"

#: The proof that a directory in the owner's library is ours to replace or remove.
#: A name matching what a release ships is not proof: a later release can introduce a
#: name the owner already used, and that coincidence does not transfer ownership.
OWNED = ".rundesk-built-in"

#: Exact fingerprints of the built-ins shipped immediately before ownership markers
#: existed. This is a one-release bridge for installs already on 0.10: only an untouched
#: directory can acquire the marker. A modified built-in is left alone, and a newly shipped
#: name can never appear here and claim an owner's work by coincidence.
LEGACY = {
    "building-a-channel-adapter": (
        "eeea76bac1c12db493ad823b1d89d4d42740ab7b17173459b3c0705353332466",
        "65c4e1f28f278ea29ac5e59317eb94ff99b6b43c1aeab855045f6823ac82db9b",
    ),
    "building-a-provider-adapter": (
        "699c7b9408c743115eb32fdf4e4c242201ff5dbabc34833510e26f4aac025ab1",),
    "managing-backups": (
        "dbe161e30d98c0f1cef541de6b63791005f794c8f2c27d4811a4d630b55f096a",),
    "reporting-a-rundesk-bug": (
        "4a00da98050dd3debbcba46c52c48f1fdbfa7684605c3bfb9c7fcd378c29d87b",),
    "using-rundesk": (
        "fee454e2f180769ab22f8c0a44274467ddc9d7036b17e717250f851236a08c30",),
    "writing-pull-requests": (
        "e0053196a485e2553b7a47bf7b35ed3583c3553c83b5e6c38db86be85ae739d1",),
    "writing-skills": (
        "ba4d002a005251f87f0343c9305823d2a2052584dfb92fe7a0586b99f23e28a2",),
}

#: Built-ins an earlier release shipped under another name, and the name each became.
#: A rename cannot be read off the directory the way everything else here is: the old name
#: is simply absent from what ships, which is indistinguishable from a name that never
#: shipped at all. So it is declared, for the same reason `LEGACY` is — the directory
#: cannot tell you a thing that only history knows.
RENAMED = {
    "reporting-a-rundesk-bug": "filing-rundesk-issues",
    "using-rundesk": "managing-rundesk",
    "managing-backups": "managing-rundesk-backups",
    "writing-pull-requests": "writing-rundesk-pull-requests",
    "writing-skills": "writing-rundesk-skills",
}

#: Built-ins this release stopped shipping with nothing standing in their place. Not a
#: rename: what these held is documentation now — `docs/extending/` — because building an
#: adapter is a thing a person does once against the repository, not a thing an agent needs
#: in front of it on every turn. Retired the same way, so the library and every grant of one
#: goes rather than being left resolving to text no release will ever bring forward again.
RETIRED = (
    "building-a-channel-adapter",
    "building-a-provider-adapter",
    "building-integration-clis",
)

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
    return Path(os.environ.get("RUNDESK_SKILL_LIBRARY") or skills_home())


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

    **That is the whole of "always the latest version"** — the set is whatever the release
    ships, read off the directory each time. A marker records only ownership, never a
    version: it is the evidence that replacing a same-named directory is allowed.

    An owner who wants their own version of a built-in copies it under another name, which
    is then theirs and is never a name this touches.
    """
    where = where or home()
    moved = []
    for name in shipped():
        target = where / name
        if target.exists() and not force:
            continue
        if target.exists() and not _owned(target, name):
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
            (coming / OWNED).write_text("rundesk built-in\n", encoding="utf-8")
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


def _owned(at: Path, name: str) -> bool:
    """Whether Rundesk has evidence that this skill is its own."""
    if (at / OWNED).is_file():
        return True
    expected = LEGACY.get(name, ())
    if not expected or not at.is_dir() or at.is_symlink():
        return False
    return _fingerprint(at) in expected


def _fingerprint(at: Path) -> str:
    """The exact file tree of one legacy skill, or an empty fingerprint if unreadable."""
    found = hashlib.sha256()
    try:
        files = sorted(one for one in at.rglob("*") if one.is_file() and one.name != OWNED)
        for one in files:
            found.update(str(one.relative_to(at)).encode("utf-8") + b"\0")
            found.update(one.read_bytes() + b"\0")
    except OSError:
        return ""
    return found.hexdigest()


def take_back(where: Path | None = None) -> list[str]:
    """Take the skills this release laid down back out of the library, and say which went.

    **The mirror of `lay_down`, and R-RM-7 is why it exists**: removing rundesk takes what
    the install put there for it. A built-in is rundesk's file — that is the whole of why it
    can be replaced by an update without asking — so leaving it behind is leaving a piece of
    the program on a machine somebody has removed the program from. It also left the library,
    and with it the whole install directory, standing after an uninstall that reported having
    left nothing.

    **Whatever the owner wrote stays.** A directory is taken only when its name is in the set
    this release ships *and* its marker proves Rundesk laid it down. A skill of their own —
    including one that happens to have a newly shipped name — is not touched.

    An empty library goes too. A directory left holding nothing is not something the owner
    keeps, and it is the difference between an install directory that can be removed and one
    that cannot.
    """
    where = where or home()
    if not where.is_dir():
        return []
    gone = []
    for name in tuple(shipped()) + tuple(sorted(RENAMED)) + RETIRED:
        standing = where / name
        if not standing.is_dir() or standing.is_symlink() or not _owned(standing, name):
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


def retire(where: Path | None = None, holding: tuple[Path, ...] = ()) -> list[str]:
    """Take out a built-in this release renamed or dropped, and carry a grant where it goes.

    **Left alone, a rename is worse than a broken link.** `lay_down` puts the new name in
    the library and touches nothing else, so the old directory stands there with the old
    text in it and every grant of it still resolves. Nothing dangles, nothing is reported,
    and an agent goes on reading superseded instructions for as long as the machine lasts.

    **A grant is carried, never handed out.** Only an agent already holding the old name
    is given the new one, and one that has no new name — a built-in this release dropped
    rather than renamed — has its grant taken away rather than left pointing at nothing. An owner who revoked it keeps it revoked — the same reason
    `agent._given_what_ships` refuses to backfill, and the reason this cannot simply grant
    the new built-in to everybody.

    **Nothing of the owner's is moved.** A directory standing under the old name without
    the ownership marker is theirs, whatever it is called, so neither it nor any grant of
    it is touched — a rename in a release must not be able to take away work somebody did.

    `holding` is each agent's own skills directory, passed in rather than discovered here:
    `agent` reads this module, so this module cannot read it back.
    """
    where = where or home()
    standing_now = library(where)
    retired = []
    gone_for_good = [(one, None) for one in RETIRED]
    for old, new in sorted(RENAMED.items()) + gone_for_good:
        was = where / old
        if new is not None and new not in standing_now:
            continue     # the new name never landed, so a grant has nowhere to be carried
        if not was.is_dir() or was.is_symlink() or not _owned(was, old):
            continue     # nothing of ours under that name
        for mine in holding:
            grant_at = mine / old
            if not ours(grant_at, where):
                continue
            try:
                if new is not None:
                    # The new grant is made before the old one goes: an agent that loses
                    # power between the two is left holding both names rather than neither,
                    # and the next update takes the spare.
                    grant(mine, new, where)
                grant_at.unlink()
            except (Unknown, NotASkill, InTheWay, OSError):
                continue
        try:
            shutil.rmtree(was)
        except OSError:
            # A library that cannot be written to is said by a diagnosis, not raised out of
            # the middle of an update that has otherwise already gone forward.
            continue
        retired.append(old)
    return retired


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
