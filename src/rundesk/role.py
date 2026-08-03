"""A role: the specialist execution definition a named agent delegates work to.

**A role is something an agent does, never something it is** (R-ROL-1). A role has no
identity, no memory, no home it keeps between runs, no channels and no schedules. It is
two files an owner writes — what the specialty is, and the rules one execution of it
follows — and every named agent on this install may put it on.

The whole maintained unit is:

    .roles/<slug>/
    ├── role.json     description, skills, posture, provider, model — and nothing else
    └── AGENTS.md        the specialist execution rules

Everything else is derived rather than configured, because a setting is a thing somebody
has to keep true: the slug is the directory, the label is the slug read aloud, the
instruction filename is fixed by convention, the brief ceiling is one constant for the
whole install, and the revision is a digest of what the role actually is. A role
maintainer never increments a version and never compiles a skill list.

The definitions stand below `agent.agents_home()` rather than beside the program, so
whatever redirects where agents live redirects roles with them — which is what lets a
disposable station hold its own roles without reaching the live install's.
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
from rundesk import instructions, provider, skill

#: Where shared role definitions stand, below wherever agents are kept. Dotted, so it
#: stands among the agents without being one: what makes a directory an agent is a `home/`
#: inside it, so nothing that walks that place can mistake this for one — the same reason
#: `agent.OVERRIDES` is dotted, and the same guarantee.
ROLES = ".roles"

#: The roles this release ships, read off the directory rather than listed — the same
#: rule the skill library holds to, and for the same reason: a list in code disagrees with
#: the directory the day somebody adds one and forgets it.
SHIPPED = ROOT / "src" / "templates" / "roles"

#: The rules a role a command wrote starts life with. A file rather than a string in this
#: module, and standing among the roles it is the skeleton for: it is prose somebody edits,
#: and prose kept in source is prose nobody reads before changing the code around it.
#: Dotted and a file rather than a directory, so `shipped()` — which asks for a directory
#: holding both of a role's files — cannot mistake it for a role this release ships.
SKELETON = SHIPPED / ".skeleton.md"

#: The two files a role is made of. `AGENTS.md` is fixed by convention rather than
#: named in the manifest, because a filename an owner may choose is one every reader has
#: to look up before it can find the rules.
MANIFEST = "role.json"
INSTRUCTIONS = "AGENTS.md"

#: The whole of what a manifest may say (R-ROL-2). Closed on purpose: a field this
#: release does not know is a field somebody believes is doing something, and refusing it
#: is the only honest answer.
#:
#: `provider` and `model` are both optional, and absent means today's answer: the run
#: continues on whatever brain its parent turn resolved. A role is a specialist definition
#: rather than an inheritance of whoever asked, so one whose work only a particular brain
#: does well may say so — and a role that says neither is unchanged in every way, down to
#: its revision (R-ROL-33).
FIELDS = ("description", "skills", "posture", "provider", "model")

#: What a role may be called. The same shape a skill name takes, and for the same
#: reason — it is a directory name that appears in a run's identity and in what a person
#: reads, so a space or a dot in it is a path nobody can predict.
ALLOWED = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: How long a role's description may be. It is what a named agent reads when deciding
#: whether to delegate, so it is a sentence rather than a document.
DESCRIBED_LIMIT = 1024

#: How long a name may be, matching the library's own ceiling for the same reason: it is
#: a directory name, and one longer than this is one some filesystem refuses.
NAMED_LIMIT = 64

#: How long the brain or the model a role pins itself to may be written. A shipped
#: adapter's name and the path of a program somebody wrote both stand in this field, so it
#: is bounded rather than shaped: **there is no list of brains to check a name against**,
#: and there deliberately never will be — the provider seam enumerates nothing, so a brain
#: this release has never heard of is the ordinary case rather than a typo. What this
#: refuses is a field that cannot name anything at all; whether *this* machine has the one
#: named is asked when a run is admitted (R-ROL-35).
PINNED_LIMIT = 256

#: How much task brief a named agent may hand a role run, for the whole install
#: (R-ROL-6). One constant rather than a manifest field: a per-role ceiling is a
#: setting nobody can reason about, and the point of the limit is that the parent sends a
#: bounded brief rather than its conversation.
BRIEF_LIMIT = 8192


class NotARole(ValueError):
    """This is not a role, and the reason is the whole of the message.

    Every refusal here is complete: a manifest is read, validated and either usable or
    named as unusable in one answer, because a role that fails halfway through
    admitting a run has already started one.
    """


@dataclass(frozen=True)
class Role:
    """One shared role definition, resolved and whole.

    `revision` is what makes a run's locks provable afterwards: it is computed from the
    manifest, the rules and every resolved skill package, so two runs admitted from the
    same bytes carry the same word and a run admitted after an edit carries a different
    one (R-ROL-9).
    """

    slug: str
    label: str
    description: str
    #: The complete set of skills this role exposes, in sorted order. Never a subset
    #: chosen at task time and never inherited from the parent agent.
    skills: tuple
    #: The names this role asks for that this machine has no skill called. Kept rather than
    #: refused (R-ROL-8): a role is a specialist definition an owner may share between
    #: machines, and one that named a skill this install has not got would otherwise be
    #: unusable here for a capability the work may never need. Carried so a listing and a
    #: diagnosis can say which, because a set silently smaller than its manifest is the
    #: kind of difference nobody notices until the work comes back thin.
    missing: tuple
    posture: str
    #: The brain every run of this role uses, and the model on it — empty where the role
    #: names neither, which means the run continues on whatever its parent turn resolved
    #: (R-ROL-33). Held as what the owner wrote rather than as anything resolved: whether
    #: this machine has the brain named is a question admission asks, so a role written
    #: on one machine is still readable on another that has not got it.
    provider: str
    model: str
    #: The specialist rules, exactly as the owner wrote them.
    instructions: str
    at: Path
    revision: str

    def manifest(self) -> dict:
        """The maintained fields, normalized — what a run's locked copy holds.

        The skills as this machine resolved them, because that is what the run is actually
        given; what it asked for and did not get is `missing`, and is reported rather than
        written into a lock that would then never verify.

        **A field the role does not name is absent rather than empty.** A role that pins no
        brain is a role that is not about brains, and writing `"provider": ""` into its
        locked manifest would put a decision in the bundle that its owner never made.
        """
        said = {
            "description": self.description,
            "skills": list(self.skills),
            "posture": self.posture,
        }
        if self.provider:
            said["provider"] = self.provider
        if self.model:
            said["model"] = self.model
        return said


def home(where: Path | None = None) -> Path:
    """Where shared role definitions stand.

    Resolved downward from where agents are kept rather than from the program, so a
    station that redirects agents redirects roles too and no isolated run can reach
    the live install's definitions.
    """
    return (where or agents.agents_home()) / ROLES


def label(slug: str) -> str:
    """The slug read aloud — `code-review` is `Code Review`.

    Derived rather than configured, so a role has one display name and nobody has to
    keep a second copy of it true.
    """
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def known(where: Path | None = None) -> list[str]:
    """Every role slug installed here, in the order they are named.

    A directory without both of its files is not a role and is not listed — an owner
    half way through writing one has not broken anything, exactly as with a skill.
    """
    at = home(where)
    try:
        found = sorted(
            one.name for one in at.iterdir()
            if (one / MANIFEST).is_file() and (one / INSTRUCTIONS).is_file()
        )
    except OSError:
        # No roles at all is the ordinary case on every install that has never made
        # one, and it is never an error.
        return []
    return [name for name in found if ALLOWED.match(name)]


def offered(where: Path | None = None) -> str:
    """Every installed role as the lines an agent is told about, or nothing.

    Sorted by slug, because what a person and a brain read is never left to the order a
    directory happens to hand back. The description goes in whole: it is what a role
    promises, and the clause a truncation takes is usually the one deciding whether this
    is the right role for the work in front of the agent.

    **A definition that will not read is skipped rather than raised.** One unusable role
    must not cost every agent on this install the whole layer naming the others — and it
    is already refused where somebody tries to run it, which is where the error belongs
    and where it can name what is wrong.
    """
    lines = []
    for slug in known(where):
        try:
            one = read(slug, where)
        except NotARole:
            continue
        lines.append(f"- **{one.slug}** ({one.posture}) — {one.description}")
    return "\n".join(lines)


def shipped() -> tuple:
    """The role slugs this release ships, asked of the directory rather than listed."""
    if not SHIPPED.is_dir():
        return ()
    return tuple(sorted(
        one.name for one in SHIPPED.iterdir()
        if (one / MANIFEST).is_file() and (one / INSTRUCTIONS).is_file()
    ))


def lay_down(where: Path | None = None) -> list:
    """Put the roles this release ships where they are missing, and say which moved.

    **Never over one that is already there** (R-ROL-18), and this differs on purpose from
    how a built-in skill is laid down. A skill is release-owned and comes forward with the
    release; a role is what an owner writes their specialists as, and the shipped one is
    a starting point rather than a thing Rundesk keeps true. An update that replaced an
    edited role would silently change what every future run of it is allowed to do.

    Built whole under a hidden name and moved into place, so a failure part-way leaves
    nothing that reads as a role.
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


def write(slug: str, description: str, skills, posture: str, provider_named: str = "",
          model: str = "", where: Path | None = None,
          library: dict | None = None) -> Role:
    """Write one new role, and hand back what this install resolved it to (R-ROL-39).

    **Everything refusable is refused before anything is written.** A refusal after a
    partial write leaves a directory that reads as half a role, and half a role shadows
    the role of that name in silence — so the order here is the whole of the guarantee:
    validate, build whole under a hidden name, move it into place, and only then read the
    finished pair back through the same `read()` every run is admitted through. Nothing
    here validates a manifest of its own; what refuses is what already refuses.

    The rules written are the generic skeleton, which is **not** about this specialty and
    says so in every section. What makes that safe is the answer the caller gives its
    reader: the path of the file, and that it is unwritten work.
    """
    root = home(where)
    stands = root / checked(slug)
    _nothing_standing(slug, stands)
    said = _asked(slug, description, skills, posture, provider_named, model)
    coming = root / f".{slug}.coming"
    try:
        root.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(coming, ignore_errors=True)
        coming.mkdir()
        (coming / MANIFEST).write_text(json.dumps(said, indent=2) + "\n",
                                       encoding="utf-8")
        (coming / INSTRUCTIONS).write_text(_skeleton(slug, said["description"]),
                                           encoding="utf-8")
        os.replace(coming, stands)
    except OSError:
        # Neither a role nor half of one is left standing under either name. A hidden
        # directory left behind is the next `add` of that slug refusing for a reason
        # nobody can see.
        shutil.rmtree(coming, ignore_errors=True)
        raise
    return read(slug, where, library)


def _nothing_standing(slug: str, stands: Path) -> None:
    """Refuse whatever is already standing under this name, and say what it is.

    **Never over a role that is already there** (R-ROL-18): a role is what an owner
    writes their specialists as, so an existing slug is a refusal and never an overwrite
    or a merge.

    The half-written case is the one that matters beyond this command. A directory
    holding one of the two files is not listed by `known()` and is skipped by
    `lay_down`, which asks only whether the directory is there — so it shadows the
    shipped role of that name in silence, and nothing else in the product says so. This
    is where the words get said.
    """
    if not stands.exists() and not stands.is_symlink():
        return
    changed = "nothing was changed"
    if stands.is_symlink() or not stands.is_dir():
        raise NotARole(f"{stands} is already there and is not a role directory — "
                       f"{changed}")
    manifest = (stands / MANIFEST).is_file()
    rules = (stands / INSTRUCTIONS).is_file()
    if manifest and rules:
        raise NotARole(
            f"'{slug}' is already a role, standing at {stands} — {changed}. A role is "
            f"what an owner writes their specialists as, so it is never written over: "
            f"edit that one, or write a new one under another name")
    if manifest or rules:
        raise NotARole(
            f"{stands} is half a role: it has no {INSTRUCTIONS if manifest else MANIFEST} "
            f"in it, which is why no role called '{slug}' is usable and why none of that "
            f"name is listed — {changed}. Finish that directory or take it away")
    raise NotARole(f"{stands} is already there with neither {MANIFEST} nor "
                   f"{INSTRUCTIONS} in it — {changed}")


def edit(slug: str, where: Path | None = None, library: dict | None = None,
         **named) -> tuple:
    """Change what a role says about itself, whole or not at all (R-ROL-40).

    Hands back the role as it was and as it now is, because what a caller needs to say
    is what *moved* — and neither half can answer that on its own.

    **The manifest is the whole of what this changes.** A role's rules are prose their
    author wrote, and a command that rewrote them would throw that work away; a
    specialty that has moved is theirs to bring in line afterwards.

    **A field no flag named keeps what is there, and an empty one is a decision.** Those
    are different answers rather than two spellings of one: `provider=""` unpins a brain,
    because a field the role does not name is absent rather than empty (R-ROL-33), so
    there is nothing for a clearing flag of its own to do.

    The order is the guarantee, exactly as `write()`'s is. A manifest holding a field
    this release does not know is **refused rather than overlaid** — the owner put it
    there, and rewriting the file would discard it in silence. Everything refusable is
    then refused by `_asked`, which is the same proof `write` gets and the same one
    `read` will apply afterwards, so nothing here validates anything of its own. Only
    then is a whole manifest written beside the old one and renamed onto it: a truncated
    `role.json` is worse than the half-written directory `add` refuses, because
    `AGENTS.md` still stands, so `known()` goes on listing the role and every `read()`
    of it fails.
    """
    unknown = sorted(set(named) - set(FIELDS))
    if unknown:
        raise NotARole(f"'{slug}' has no such thing as {', '.join(unknown)} — a role "
                       f"holds only {', '.join(FIELDS)}")
    if not named:
        # An edit that changes nothing is a command that did nothing, and answering as
        # though it succeeded is the kind of quiet lie that gets believed.
        raise NotARole(f"nothing was named to change about '{slug}' — an edit names at "
                       f"least one of {', '.join(FIELDS)}")
    stands = _directory(slug, where)
    said = _manifest(stands)
    before = read(slug, where, library)
    overlaid = dict(said)
    overlaid.update(named)
    # Off the manifest rather than off what was resolved: a skill this machine has not
    # got is carried in the file and absent from `Role.skills` (R-ROL-8), so an overlay
    # taken from the role would quietly drop every name this library happens not to hold.
    written = _asked(slug, overlaid.get("description"), overlaid.get("skills"),
                     overlaid.get("posture"), overlaid.get("provider") or "",
                     overlaid.get("model") or "")
    coming = stands / f"{MANIFEST}.coming"
    try:
        coming.write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
        os.replace(coming, stands / MANIFEST)
    except OSError:
        # The manifest that was there is still there and still reads. What must never be
        # left is a partial file under either name.
        with contextlib.suppress(OSError):
            coming.unlink()
        raise
    return before, read(slug, where, library)


def _asked(slug: str, description: str, skills, posture: str, provider_named: str,
           model: str) -> dict:
    """The manifest this role would have, proved to be one a run could be admitted on.

    Built and checked with exactly the helpers `read` uses, so a definition this command
    writes can never be one the product then refuses to read — and so a rule about what a
    manifest may say goes on being decided in one place.

    **A field the role does not name is absent rather than empty** (R-ROL-33). Writing
    `"provider": ""` would put a decision in the file its author never made, and would
    move the revision of a role that pins nothing.
    """
    said = {"description": description,
            "skills": list(skills) if isinstance(skills, tuple) else skills,
            "posture": posture}
    if provider_named:
        said["provider"] = provider_named
    if model:
        said["model"] = model
    written = {"description": _described(slug, said),
               "skills": sorted(set(_named(slug, said.get("skills")))),
               "posture": _posture(slug, said)}
    for field in ("provider", "model"):
        pinned = _pinned(slug, said, field)
        if pinned:
            written[field] = pinned
    return written


def _skeleton(slug: str, description: str) -> str:
    """The rules a new role starts life with, which are not yet about its specialty.

    A file beside the roles it is the skeleton for rather than a string in this module:
    it is prose an owner reads and edits, and prose kept in source is prose nobody looks
    at before changing the code around it.
    """
    try:
        skeleton = SKELETON.read_text(encoding="utf-8")
    except OSError as why:
        raise NotARole(
            f"this install has no role skeleton at {SKELETON} — {why}") from None
    return instructions.render(skeleton,
                               {"label": label(slug), "description": description})


def take_back(where: Path | None = None) -> list:
    """Take back the roles this release laid down and nobody has touched (R-RM-7).

    **The mirror of `lay_down`.** A shipped role still standing exactly as the release
    wrote it is a piece of the program, and leaving it behind leaves the install directory
    standing after an uninstall that reported having left nothing.

    **Whatever the owner wrote stays, including an edit to a shipped one.** There is no
    ownership marker here and deliberately not: a role is what somebody writes their
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
        # role down is what brings it into being on an install that has never had an
        # agent, so leaving it behind is this feature leaving the whole install directory
        # standing after an uninstall that said it left nothing (R-RM-8). `rmdir` refuses
        # the moment anything of the owner's is in there, which is the whole guard.
        root.parent.rmdir()
    return gone


def _as_shipped(standing: Path, released: Path) -> bool:
    """Whether this role is still exactly the two files the release wrote."""
    try:
        here = sorted(one.relative_to(standing) for one in standing.rglob("*"))
        there = sorted(one.relative_to(released) for one in released.rglob("*"))
    except OSError:
        return False
    if here != there:
        return False
    return all((standing / one).read_bytes() == (released / one).read_bytes()
               for one in there if (released / one).is_file())


def read(slug: str, where: Path | None = None, library: dict | None = None) -> Role:
    """This role, completely validated, or why it cannot be used (R-ROL-3).

    Validation is complete rather than progressive: every reason a definition is unusable
    is found before a run is admitted, because a role that fails after its bundle has
    been assembled has already cost an owner a half-made run to clean up.

    `library` is how a skill name is resolved, passed in so this is decided offline and
    against a fixture rather than against whatever the machine happens to hold.
    """
    stands = _directory(slug, where)
    said = _manifest(stands)
    described = _described(slug, said)
    posture = _posture(slug, said)
    # Refused here, with everything else refusable about a definition, rather than found
    # out mid-carry: a role pinned to a brain nobody can name is a run admitted, assembled
    # and then failed for something the manifest said on the first line.
    named = _pinned(slug, said, "provider")
    model = _pinned(slug, said, "model")
    resolved = library if library is not None else skill.library()
    skills, missing = _skills(slug, said.get("skills"), resolved)
    rules = _instructions(slug, stands)
    return Role(
        slug=slug, label=label(slug), description=described,
        skills=skills, missing=missing, posture=posture, provider=named, model=model,
        instructions=rules, at=stands,
        revision=_revision(described, skills, missing, posture, named, model,
                           rules, resolved),
    )


def checked(slug: str) -> str:
    """This slug, or why it cannot be one.

    Stricter than a display name because it is a directory under the roles root and it
    appears in a run's identity: one path component, no dot, and nothing that would make
    two roles resolve to one directory.
    """
    if not isinstance(slug, str) or not slug:
        raise NotARole("no role was named")
    if len(slug) > NAMED_LIMIT:
        raise NotARole(f"the name {slug} is longer than {NAMED_LIMIT} characters")
    if not ALLOWED.match(slug):
        raise NotARole(
            f"the name {slug} is not lowercase letters, digits and single hyphens"
        )
    return slug


def _directory(slug: str, where: Path | None) -> Path:
    """The directory this role really is, proved to stand where roles are kept.

    Both halves are asked, exactly as an agent's directory asks them: the name is one
    component, and what it resolves to still has the roles root as its parent. The
    second catches what the first cannot — a link already standing under that name and
    pointing at somebody else's directory entirely.
    """
    root = home(where)
    stands = root / checked(slug)
    if not stands.is_dir():
        raise NotARole(f"there is no role called '{slug}'")
    if stands.resolve().parent != root.resolve():
        raise NotARole(
            f"'{slug}' does not stand where roles are kept — it reaches "
            f"{stands.resolve()}"
        )
    return stands


def _manifest(stands: Path) -> dict:
    """The maintained fields, refusing anything else that is written beside them."""
    at = stands / MANIFEST
    if not at.is_file():
        raise NotARole(f"{stands.name} has no {MANIFEST} in it")
    try:
        said = json.loads(at.read_text(encoding="utf-8"))
    except (OSError, ValueError) as why:
        raise NotARole(f"{stands.name}'s {MANIFEST} could not be read: {why}") from None
    if not isinstance(said, dict):
        raise NotARole(f"{stands.name}'s {MANIFEST} is not a set of fields")
    unknown = sorted(set(said) - set(FIELDS))
    if unknown:
        # Refused rather than ignored: a field nobody reads is one an owner believes is
        # doing something, and a role is the one place a silent setting would decide
        # what an isolated execution is allowed to do.
        raise NotARole(
            f"{stands.name}'s {MANIFEST} says {', '.join(unknown)}, which a role has "
            f"no such thing as — it holds only {', '.join(FIELDS)}"
        )
    return said


def _described(slug: str, said: dict) -> str:
    """What this role is for, without its surrounding space, or why it says nothing.

    Asked of a manifest read off disk and of one a command is about to write, so what a
    description may be is decided here and never twice.
    """
    described = said.get("description")
    if not isinstance(described, str) or not described.strip():
        raise NotARole(f"'{slug}' says nothing about what it is for")
    if len(described) > DESCRIBED_LIMIT:
        # The length as well as the limit: a description trimmed to fit is an owner
        # counting characters, and the number they need is the one they wrote.
        raise NotARole(
            f"'{slug}' describes itself in {len(described)} characters, and a "
            f"description is {DESCRIBED_LIMIT} at most"
        )
    return described.strip()


def _posture(slug: str, said: dict) -> str:
    """How far a run of this role may reach, or why what is written is not a posture."""
    posture = said.get("posture")
    if posture not in provider.POSTURES:
        raise NotARole(
            f"'{slug}' asks for a posture of '{posture}' — it must be one of "
            f"{', '.join(provider.POSTURES)}"
        )
    return posture


def _instructions(slug: str, stands: Path) -> str:
    """The specialist rules this role runs under, proved to be its own file.

    A link out of the package is refused rather than followed: the rules are what replace
    a named agent's own operational instructions for a run, so a role that could point
    them at any file on the machine is a role that can be made to say anything.
    """
    at = stands / INSTRUCTIONS
    if not at.is_file():
        raise NotARole(f"'{slug}' has no {INSTRUCTIONS} — it has no rules to run under")
    if not _inside(at, stands):
        raise NotARole(f"'{slug}'s {INSTRUCTIONS} reaches outside the role")
    try:
        rules = at.read_text(encoding="utf-8")
    except OSError as why:
        raise NotARole(f"'{slug}'s {INSTRUCTIONS} could not be read: {why}") from None
    if not rules.strip():
        raise NotARole(f"'{slug}'s {INSTRUCTIONS} is empty — it has no rules to run under")
    return rules


def _pinned(slug: str, manifest: dict, field: str) -> str:
    """The brain or the model this role pins itself to, or why it names neither.

    **Absent is the answer, not a missing one** (R-ROL-33). A role that says nothing about
    which brain runs it continues on whatever its parent turn resolved, exactly as every
    role did before this field existed — so the empty string here is a whole answer and
    never a default standing in for one.

    **Written and present is a claim, and is held to one.** `null`, a number or an empty
    string in this field is somebody who believes they have pinned a brain and has not,
    and a role admitted on the parent's brain when its manifest appears to name another is
    the one failure this field could produce that nobody would ever see. So the field
    being *there* is asked, rather than what reading it happens to answer — `null` and
    absent are one value to a lookup with a default, and they are opposite claims here.

    What is *not* checked here is whether any such brain exists. There is no list of
    brains and there is deliberately never going to be one — the provider seam resolves a
    name or a path to a program and enumerates nothing, so a brain rundesk has never heard
    of is the ordinary case. Whether this machine has the one named is asked once, when a
    run is admitted, where the answer can name the agent it would have run for (R-ROL-35).
    """
    if field not in manifest:
        return ""
    said = manifest[field]
    if not isinstance(said, str) or not said.strip():
        raise NotARole(f"'{slug}' says {field} and names nothing")
    named = said.strip()
    if len(named) > PINNED_LIMIT:
        raise NotARole(
            f"'{slug}' names a {field} longer than {PINNED_LIMIT} characters"
        )
    if any(ch == "\n" or ord(ch) < 32 for ch in named):
        raise NotARole(f"'{slug}' names a {field} that cannot be one: {named!r}")
    return named


def _skills(slug: str, said: object, resolved: dict) -> tuple:
    """What this role exposes here, and what it named that this machine has not got.

    **A set, written down in sorted order.** Reordering the JSON must not make a new
    revision — an owner tidying a list has not changed what the role is — and a duplicate
    is refused rather than collapsed, because two entries of one name is an owner who
    believes one of them is doing something else.

    **A name this install has no skill for is left out rather than refused** (R-ROL-8). A
    role is a definition an owner may share between machines and write ahead of the
    library, and refusing the whole thing over one absent package would make a role
    unusable here for a capability the work in front of it may never need. What is missing
    is carried back rather than swallowed, so a listing and a diagnosis can name it.
    """
    names = _named(slug, said)
    return (tuple(sorted(one for one in names if one in resolved)),
            tuple(sorted(one for one in names if one not in resolved)))


def _named(slug: str, said: object) -> list:
    """The skill names this role asks for, proved to be a set of names.

    Split from the resolving above it because writing a role has to ask this question
    with no library in hand at all: what the machine happens to have decides what a run
    is *given*, and never whether the definition is one.
    """
    if not isinstance(said, list) or not said:
        raise NotARole(f"'{slug}' names no skills — a role exposes at least one")
    names = []
    for one in said:
        if not isinstance(one, str) or not ALLOWED.match(one):
            raise NotARole(f"'{slug}' names a skill that cannot be one: {one!r}")
        names.append(one)
    duplicated = sorted({one for one in names if names.count(one) > 1})
    if duplicated:
        raise NotARole(f"'{slug}' names {', '.join(duplicated)} more than once")
    return names


def _revision(description: str, skills: tuple, missing: tuple, posture: str,
              provider_named: str, model: str, rules: str, library: dict) -> str:
    """What this role is, in one word that changes when any part of it does.

    Computed rather than maintained (R-ROL-9). It covers the manifest as normalized, the
    rules as written, and the resolved content of every skill in the set — so editing a
    skill a role exposes moves the role's revision, which is what makes "this run
    used these exact bytes" a claim anybody can check afterwards.

    **Which brain a role pins itself to is part of what the role is**, so pinning one, or
    changing which one, is a new revision — the same work done on a different brain is
    different work, and a locked run has to be able to say which.

    **A field the role does not name is not in the digest at all** (R-ROL-33). Folding in
    an empty provider would move the revision of every role already written, and every
    installed role would read as edited by an update that touched none of them.
    """
    digest = hashlib.sha256()
    # The names this role asks for, whether or not this machine has them: a skill that
    # arrives later changes what a run admitted after it is given, and the revision has to
    # move with that.
    said = {"description": description, "skills": sorted([*skills, *missing]),
            "posture": posture}
    if provider_named:
        said["provider"] = provider_named
    if model:
        said["model"] = model
    digest.update(json.dumps(said, sort_keys=True).encode("utf-8"))
    digest.update(b"\0")
    digest.update(rules.encode("utf-8"))
    for name in skills:
        digest.update(b"\0")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(package_digest(library[name]).encode("utf-8"))
    return digest.hexdigest()


def package_digest(at: Path) -> str:
    """What one skill package holds, in one word (R-ROL-9).

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
            raise NotARole(f"{at.name} reaches outside itself at {path.name}")
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
