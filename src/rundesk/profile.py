"""A profile: the specialist execution definition a named agent delegates work to.

**A profile is not another named agent** (R-PRF-1). It has no identity, no memory, no
home it keeps between runs, no channels and no schedules. It is two files an owner
writes — what the specialty is, and the rules one execution of it follows — and every
named agent on this install may reach for it.

The whole maintained unit is:

    .profiles/<slug>/
    ├── profile.json     description, skills, posture — and nothing else
    └── AGENTS.md        the specialist execution rules

Everything else is derived rather than configured, because a setting is a thing somebody
has to keep true: the slug is the directory, the label is the slug read aloud, the
instruction filename is fixed by convention, the brief ceiling is one constant for the
whole install, and the revision is a digest of what the profile actually is. A profile
maintainer never increments a version and never compiles a skill list.

The definitions stand below `agent.agents_home()` rather than beside the program, so
whatever redirects where agents live redirects profiles with them — which is what lets a
disposable station hold its own profiles without reaching the live install's.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from rundesk import ROOT
from rundesk import agent as agents
from rundesk import provider, skill

#: Where shared profile definitions stand, below wherever agents are kept. Dotted, so it
#: stands among the agents without being one: what makes a directory an agent is a `home/`
#: inside it, so nothing that walks that place can mistake this for one — the same reason
#: `agent.OVERRIDES` is dotted, and the same guarantee.
PROFILES = ".profiles"

#: The profiles this release ships, read off the directory rather than listed — the same
#: rule the skill library holds to, and for the same reason: a list in code disagrees with
#: the directory the day somebody adds one and forgets it.
SHIPPED = ROOT / "src" / "templates" / "profiles"

#: The two files a profile is made of. `AGENTS.md` is fixed by convention rather than
#: named in the manifest, because a filename an owner may choose is one every reader has
#: to look up before it can find the rules.
MANIFEST = "profile.json"
INSTRUCTIONS = "AGENTS.md"

#: The whole of what a manifest may say (R-PRF-2). Closed on purpose: a field this
#: release does not know is a field somebody believes is doing something, and refusing it
#: is the only honest answer.
FIELDS = ("description", "skills", "posture")

#: What a profile may be called. The same shape a skill name takes, and for the same
#: reason — it is a directory name that appears in a run's identity and in what a person
#: reads, so a space or a dot in it is a path nobody can predict.
ALLOWED = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: How long a profile's description may be. It is what a named agent reads when deciding
#: whether to delegate, so it is a sentence rather than a document.
DESCRIBED_LIMIT = 1024

#: How long a name may be, matching the library's own ceiling for the same reason: it is
#: a directory name, and one longer than this is one some filesystem refuses.
NAMED_LIMIT = 64

#: How much task brief a named agent may hand a profile run, for the whole install
#: (R-PRF-6). One constant rather than a manifest field: a per-profile ceiling is a
#: setting nobody can reason about, and the point of the limit is that the parent sends a
#: bounded brief rather than its conversation.
BRIEF_LIMIT = 8192


class NotAProfile(ValueError):
    """This is not a profile, and the reason is the whole of the message.

    Every refusal here is complete: a manifest is read, validated and either usable or
    named as unusable in one answer, because a profile that fails halfway through
    admitting a run has already started one.
    """


@dataclass(frozen=True)
class Profile:
    """One shared profile definition, resolved and whole.

    `revision` is what makes a run's locks provable afterwards: it is computed from the
    manifest, the rules and every resolved skill package, so two runs admitted from the
    same bytes carry the same word and a run admitted after an edit carries a different
    one (R-PRF-9).
    """

    slug: str
    label: str
    description: str
    #: The complete set of skills this profile exposes, in sorted order. Never a subset
    #: chosen at task time and never inherited from the parent agent.
    skills: tuple
    posture: str
    #: The specialist rules, exactly as the owner wrote them.
    instructions: str
    at: Path
    revision: str

    def manifest(self) -> dict:
        """The three maintained fields, normalized — what a run's locked copy holds."""
        return {
            "description": self.description,
            "skills": list(self.skills),
            "posture": self.posture,
        }


def home(where: Path | None = None) -> Path:
    """Where shared profile definitions stand.

    Resolved downward from where agents are kept rather than from the program, so a
    station that redirects agents redirects profiles too and no isolated run can reach
    the live install's definitions.
    """
    return (where or agents.agents_home()) / PROFILES


def label(slug: str) -> str:
    """The slug read aloud — `code-review` is `Code Review`.

    Derived rather than configured, so a profile has one display name and nobody has to
    keep a second copy of it true.
    """
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def known(where: Path | None = None) -> list[str]:
    """Every profile slug installed here, in the order they are named.

    A directory without both of its files is not a profile and is not listed — an owner
    half way through writing one has not broken anything, exactly as with a skill.
    """
    at = home(where)
    try:
        found = sorted(
            one.name for one in at.iterdir()
            if (one / MANIFEST).is_file() and (one / INSTRUCTIONS).is_file()
        )
    except OSError:
        # No profiles at all is the ordinary case on every install that has never made
        # one, and it is never an error.
        return []
    return [name for name in found if ALLOWED.match(name)]


def shipped() -> tuple:
    """The profile slugs this release ships, asked of the directory rather than listed."""
    if not SHIPPED.is_dir():
        return ()
    return tuple(sorted(
        one.name for one in SHIPPED.iterdir()
        if (one / MANIFEST).is_file() and (one / INSTRUCTIONS).is_file()
    ))


def lay_down(where: Path | None = None) -> list:
    """Put the profiles this release ships where they are missing, and say which moved.

    **Never over one that is already there** (R-PRF-18), and this differs on purpose from
    how a built-in skill is laid down. A skill is release-owned and comes forward with the
    release; a profile is what an owner writes their specialists as, and the shipped one is
    a starting point rather than a thing Rundesk keeps true. An update that replaced an
    edited profile would silently change what every future run of it is allowed to do.

    Built whole under a hidden name and moved into place, so a failure part-way leaves
    nothing that reads as a profile.
    """
    root = home(where)
    laid = []
    for slug in shipped():
        stands = root / slug
        if stands.exists():
            continue
        root.mkdir(parents=True, exist_ok=True)
        coming = root / f".{slug}.coming"
        shutil.rmtree(coming, ignore_errors=True)
        try:
            shutil.copytree(SHIPPED / slug, coming)
            os.replace(coming, stands)
        except OSError:
            shutil.rmtree(coming, ignore_errors=True)
            continue
        laid.append(slug)
    return laid


def take_back(where: Path | None = None) -> list:
    """Take back the profiles this release laid down and nobody has touched (R-RM-7).

    **The mirror of `lay_down`.** A shipped profile still standing exactly as the release
    wrote it is a piece of the program, and leaving it behind leaves the install directory
    standing after an uninstall that reported having left nothing.

    **Whatever the owner wrote stays, including an edit to a shipped one.** There is no
    ownership marker here and deliberately not: a profile is what somebody writes their
    specialists as, so what proves this one is still Rundesk's is that it is still, byte
    for byte, what Rundesk wrote. One character different and it is theirs.
    """
    root = home(where)
    if not root.is_dir():
        return []
    gone = []
    for slug in shipped():
        standing = root / slug
        if not standing.is_dir() or standing.is_symlink():
            continue
        if not _as_shipped(standing, SHIPPED / slug):
            continue
        try:
            shutil.rmtree(standing)
        except OSError:
            # A directory that cannot be written to is not a reason to fail a removal that
            # has already taken the program. What is left is reported by what is left.
            continue
        gone.append(slug)
    with contextlib.suppress(OSError):
        root.rmdir()          # only when nothing of the owner's is in it
    with contextlib.suppress(OSError):
        # And the directory agents are kept in, when that is now empty too. Laying a
        # profile down is what brings it into being on an install that has never had an
        # agent, so leaving it behind is this feature leaving the whole install directory
        # standing after an uninstall that said it left nothing (R-RM-8). `rmdir` refuses
        # the moment anything of the owner's is in there, which is the whole guard.
        root.parent.rmdir()
    return gone


def _as_shipped(standing: Path, released: Path) -> bool:
    """Whether this profile is still exactly the two files the release wrote."""
    try:
        here = sorted(one.relative_to(standing) for one in standing.rglob("*"))
        there = sorted(one.relative_to(released) for one in released.rglob("*"))
    except OSError:
        return False
    if here != there:
        return False
    return all((standing / one).read_bytes() == (released / one).read_bytes()
               for one in there if (released / one).is_file())


def read(slug: str, where: Path | None = None, library: dict | None = None) -> Profile:
    """This profile, completely validated, or why it cannot be used (R-PRF-3).

    Validation is complete rather than progressive: every reason a definition is unusable
    is found before a run is admitted, because a profile that fails after its bundle has
    been assembled has already cost an owner a half-made run to clean up.

    `library` is how a skill name is resolved, passed in so this is decided offline and
    against a fixture rather than against whatever the machine happens to hold.
    """
    stands = _directory(slug, where)
    said = _manifest(stands)
    described = said.get("description")
    if not isinstance(described, str) or not described.strip():
        raise NotAProfile(f"'{slug}' says nothing about what it is for")
    if len(described) > DESCRIBED_LIMIT:
        raise NotAProfile(
            f"'{slug}' describes itself in more than {DESCRIBED_LIMIT} characters"
        )
    posture = said.get("posture")
    if posture not in provider.POSTURES:
        raise NotAProfile(
            f"'{slug}' asks for a posture of '{posture}' — it must be one of "
            f"{', '.join(provider.POSTURES)}"
        )
    skills = _skills(slug, said.get("skills"), library)
    rules = _instructions(slug, stands)
    resolved = library if library is not None else skill.library()
    return Profile(
        slug=slug, label=label(slug), description=described.strip(),
        skills=skills, posture=posture, instructions=rules, at=stands,
        revision=_revision(described.strip(), skills, posture, rules, resolved),
    )


def checked(slug: str) -> str:
    """This slug, or why it cannot be one.

    Stricter than a display name because it is a directory under the profiles root and it
    appears in a run's identity: one path component, no dot, and nothing that would make
    two profiles resolve to one directory.
    """
    if not isinstance(slug, str) or not slug:
        raise NotAProfile("no profile was named")
    if len(slug) > NAMED_LIMIT:
        raise NotAProfile(f"the name {slug} is longer than {NAMED_LIMIT} characters")
    if not ALLOWED.match(slug):
        raise NotAProfile(
            f"the name {slug} is not lowercase letters, digits and single hyphens"
        )
    return slug


def _directory(slug: str, where: Path | None) -> Path:
    """The directory this profile really is, proved to stand where profiles are kept.

    Both halves are asked, exactly as an agent's directory asks them: the name is one
    component, and what it resolves to still has the profiles root as its parent. The
    second catches what the first cannot — a link already standing under that name and
    pointing at somebody else's directory entirely.
    """
    root = home(where)
    stands = root / checked(slug)
    if not stands.is_dir():
        raise NotAProfile(f"there is no profile called '{slug}'")
    if stands.resolve().parent != root.resolve():
        raise NotAProfile(
            f"'{slug}' does not stand where profiles are kept — it reaches "
            f"{stands.resolve()}"
        )
    return stands


def _manifest(stands: Path) -> dict:
    """The three maintained fields, refusing anything else that is written beside them."""
    at = stands / MANIFEST
    if not at.is_file():
        raise NotAProfile(f"{stands.name} has no {MANIFEST} in it")
    try:
        said = json.loads(at.read_text(encoding="utf-8"))
    except (OSError, ValueError) as why:
        raise NotAProfile(f"{stands.name}'s {MANIFEST} could not be read: {why}") from None
    if not isinstance(said, dict):
        raise NotAProfile(f"{stands.name}'s {MANIFEST} is not a set of fields")
    unknown = sorted(set(said) - set(FIELDS))
    if unknown:
        # Refused rather than ignored: a field nobody reads is one an owner believes is
        # doing something, and a profile is the one place a silent setting would decide
        # what an isolated execution is allowed to do.
        raise NotAProfile(
            f"{stands.name}'s {MANIFEST} says {', '.join(unknown)}, which a profile has "
            f"no such thing as — it holds only {', '.join(FIELDS)}"
        )
    return said


def _instructions(slug: str, stands: Path) -> str:
    """The specialist rules this profile runs under, proved to be its own file.

    A link out of the package is refused rather than followed: the rules are what replace
    a named agent's own operational instructions for a run, so a profile that could point
    them at any file on the machine is a profile that can be made to say anything.
    """
    at = stands / INSTRUCTIONS
    if not at.is_file():
        raise NotAProfile(f"'{slug}' has no {INSTRUCTIONS} — it has no rules to run under")
    if not _inside(at, stands):
        raise NotAProfile(f"'{slug}'s {INSTRUCTIONS} reaches outside the profile")
    try:
        rules = at.read_text(encoding="utf-8")
    except OSError as why:
        raise NotAProfile(f"'{slug}'s {INSTRUCTIONS} could not be read: {why}") from None
    if not rules.strip():
        raise NotAProfile(f"'{slug}'s {INSTRUCTIONS} is empty — it has no rules to run under")
    return rules


def _skills(slug: str, said: object, library: dict | None) -> tuple:
    """The complete skill set this profile exposes, normalized and resolved (R-PRF-8).

    **A set, written down in sorted order.** Reordering the JSON must not make a new
    revision — an owner tidying a list has not changed what the profile is — and a
    duplicate is refused rather than collapsed, because two entries of one name is an
    owner who believes one of them is doing something else.
    """
    if not isinstance(said, list) or not said:
        raise NotAProfile(f"'{slug}' names no skills — a profile exposes at least one")
    names = []
    for one in said:
        if not isinstance(one, str) or not ALLOWED.match(one):
            raise NotAProfile(f"'{slug}' names a skill that cannot be one: {one!r}")
        names.append(one)
    duplicated = sorted({one for one in names if names.count(one) > 1})
    if duplicated:
        raise NotAProfile(f"'{slug}' names {', '.join(duplicated)} more than once")
    resolved = library if library is not None else skill.library()
    missing = sorted(one for one in names if one not in resolved)
    if missing:
        raise NotAProfile(
            f"'{slug}' names {', '.join(missing)}, which this machine has no skill called"
        )
    return tuple(sorted(names))


def _revision(description: str, skills: tuple, posture: str, rules: str,
              library: dict) -> str:
    """What this profile is, in one word that changes when any part of it does.

    Computed rather than maintained (R-PRF-9). It covers the manifest as normalized, the
    rules as written, and the resolved content of every skill in the set — so editing a
    skill a profile exposes moves the profile's revision, which is what makes "this run
    used these exact bytes" a claim anybody can check afterwards.
    """
    digest = hashlib.sha256()
    digest.update(json.dumps(
        {"description": description, "skills": list(skills), "posture": posture},
        sort_keys=True,
    ).encode("utf-8"))
    digest.update(b"\0")
    digest.update(rules.encode("utf-8"))
    for name in skills:
        digest.update(b"\0")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(package_digest(library[name]).encode("utf-8"))
    return digest.hexdigest()


def package_digest(at: Path) -> str:
    """What one skill package holds, in one word (R-PRF-9).

    Every file below it, by sorted relative path, with whether it may be run — because a
    script that lost its executable bit is a skill that stopped working, and a digest
    that could not see the difference would report the package unchanged.

    A link out of the package is a refusal rather than a followed path: what is digested
    has to be what is copied, and a copy that reached outside would carry a file the
    owner never put in the skill.
    """
    digest = hashlib.sha256()
    for path in sorted(one for one in at.rglob("*") if one.is_file()):
        if not _inside(path, at):
            raise NotAProfile(f"{at.name} reaches outside itself at {path.name}")
        digest.update(str(path.relative_to(at)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(b"x" if os.access(path, os.X_OK) else b"-")
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    """Whether what this path really is still stands below this directory."""
    try:
        return root.resolve() in path.resolve().parents or path.resolve() == root.resolve()
    except OSError:
        return False
