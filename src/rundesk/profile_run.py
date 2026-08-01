"""One isolated specialist execution, from the moment it is admitted to the moment it expires.

A named agent decides to delegate; this is everything that happens because it did. The
named agent stays the only durable identity, the only conversation owner and the only
thing that answers a person (R-PRF-1). What runs here is a fresh execution with the
agent's identity, memory, history and operational rules deliberately absent from it.

**What a run is admitted with never changes for that run** (R-PRF-10). The profile's rules,
its complete skill set and its manifest are copied into a bundle of the run's own before
the brain is started, and the bundle is what the brain is presented. Editing the shared
profile, or a skill it exposes, changes what the *next* run is admitted with and nothing
about this one — so a run resumed on day fourteen resumes with the bytes it started with,
and the digest recorded against it says which bytes those were.

**The bundle is built whole and moved into place.** A half-assembled run that a gateway
picked up would be a specialist execution missing some of its rules, which is worse than
one that never started: nothing would report it, and the work would simply be done wrong.

The layout is:

    <agent>/profile-runs/<run>/
    ├── home/
    │   ├── AGENTS.md      the locked profile rules, byte for byte
    │   └── workspace/     non-project artifacts only
    ├── skills/            the locked copy of the complete configured set
    ├── brief.md           the bounded task the parent handed over
    └── profile.json       the locked three-field manifest

Nothing mutable lives in it. Where the run got to, how long it stays resumable, which
provider session carries it and whether its parent has been told are all rows, because
those change while the locked bytes must not.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from rundesk import agent as agents
from rundesk import instructions, profile, provider, skill, store, turn

#: Where one agent's profile runs stand. Inside the agent's own directory, so a bundle is
#: backed up with the agent, removed with the agent, and reachable by nobody else.
RUNS = "profile-runs"

#: What a bundle is made of, once. Named here rather than spelled at each caller, because a
#: directory added in one place and forgotten in another is a run assembled incompletely.
LOCKED_RULES = "AGENTS.md"
LOCKED_MANIFEST = "profile.json"
LOCKED_BRIEF = "brief.md"

#: How long after its latest activity a profile run stays resumable (R-PRF-11). Measured
#: from activity rather than from admission: a run somebody is still steering on day
#: thirteen is work in progress, and a window counted from the start would sweep it.
RETAINED_DAYS = 14

#: What a run being assembled is called while it is not one yet. A dot, so nothing listing
#: profile runs ever shows a half-built one, and a fixed suffix so a crashed assembly is
#: recognisable as debris rather than as somebody's work.
COMING = ".coming"


class NotDelegable(Exception):
    """This work cannot be handed to a profile, and the reason is the whole message.

    Raised before anything durable is written or assembled. A refusal that arrives after a
    bundle exists has already left an owner something to clean up, and after a provider
    starts it has already spent their money.
    """


@dataclass(frozen=True)
class Admitted:
    """What one profile run was admitted with — settled, and never changed after."""

    id: str
    profile: str
    label: str
    revision: str
    skills: tuple
    posture: str
    parent_run: str
    parent_conversation: str
    target: str | None
    retained_until: str


def home(name: str, where: Path | None = None) -> Path:
    """Where this agent's profile runs stand."""
    return agents.directory(name, where) / RUNS


def bundle(name: str, run_id: str, where: Path | None = None) -> Path:
    """The one directory this profile run is, proved to stand where profile runs are kept.

    Both halves are asked exactly as an agent's directory asks them, and for the same
    reason: a run id reaches this from a durable row and from an environment variable, and
    one that resolved somewhere else would let a swept bundle take an owner's directory
    with it.
    """
    root = home(name, where)
    stands = root / _checked(run_id)
    if stands.exists() and stands.resolve().parent != root.resolve():
        raise NotDelegable(
            f"'{run_id}' does not stand where profile runs are kept — it reaches "
            f"{stands.resolve()}"
        )
    return stands


def paths(name: str, run_id: str, where: Path | None = None) -> dict:
    """Every place one profile run resolves, by what it is for."""
    at = bundle(name, run_id, where)
    return {
        "run": at,
        "home": at / "home",
        "workspace": at / "home" / "workspace",
        "skills": at / "skills",
        "rules": at / "home" / LOCKED_RULES,
        "manifest": at / LOCKED_MANIFEST,
        "brief": at / LOCKED_BRIEF,
    }


def _checked(run_id: str) -> str:
    """A profile run's id, or why it cannot name a directory."""
    if not run_id or not run_id.startswith("prf-"):
        raise NotDelegable(f"'{run_id}' is not a profile run")
    if os.sep in run_id or (os.altsep and os.altsep in run_id) or run_id in (".", ".."):
        raise NotDelegable(f"'{run_id}' is not one name")
    return run_id


def retained_until(now=None, days: int = RETAINED_DAYS) -> str:
    """When a run whose latest activity is now stops being resumable."""
    at = store.moment(store.stamped(now))
    return store.stamped(lambda: (at + timedelta(days=days)).timestamp())


def target_of(said: str | None, whose: Path | None = None) -> str | None:
    """The project directory this run works in, proved to be one and proved to be apart.

    Resolved once, at admission, and recorded — so what a run says it worked on is what it
    stood in rather than whatever that path points at a fortnight later.

    **Never inside the named agent's own home** (R-PRF-5). The provider stands in this
    directory and its CLI discovers the instruction files standing there, which is the
    whole point — and it is exactly why a target inside the agent's home would hand the
    worker that agent's `AGENTS.md`, `SOUL.md` and `MEMORY.md` by the ordinary mechanism,
    with nothing in the preface to show for it. Refused rather than trusted to the prose
    floor, because the floor is words and this is the machine.
    """
    if said is None or not str(said).strip():
        return None
    at = Path(str(said)).expanduser()
    if not at.is_absolute():
        raise NotDelegable(f"'{said}' is not an absolute path to a project")
    if not at.is_dir():
        raise NotDelegable(f"there is no directory at {at}")
    stands = at.resolve()
    if whose is not None:
        home_at = whose.resolve()
        if stands == home_at or home_at in stands.parents:
            raise NotDelegable(
                "a profile run cannot work inside the agent's own home — standing there "
                "would hand it that agent's rules, memory and identity"
            )
    return str(stands)


def narrowed(parent: str | None, wanted: str) -> str:
    """The posture this execution actually runs under.

    **A profile may narrow what its parent could do and may never widen it.** The parent
    turn is the authority a worker acts under, so a profile asking to change the machine
    from a turn that was only allowed to read it is asking for authority nobody granted.
    """
    if parent == provider.READ or wanted == provider.READ:
        return provider.READ
    return provider.WORK


def safe_label(said: str | None, fallback: str) -> str:
    """A short task label safe to show where other people are reading (R-PRF-17).

    Never a local path and never a person's words verbatim: this is written into a thread
    title and into a listing, and a label carrying a private directory has published one.
    """
    text = " ".join(str(said or "").split())
    kept = "".join(ch for ch in text if ch.isalnum() or ch in " -_.,'()")
    kept = " ".join(kept.split())[:60].strip()
    return kept or fallback


def admit(name: str, slug: str, brief: str, parent_run: str,
          target: str | None = None, label: str | None = None,
          where: Path | None = None, library: dict | None = None,
          now=None, pick=None) -> Admitted:
    """Admit one profile run for this agent, and seal everything it will run with.

    The order is the whole of the safety here. Everything refusable is refused first and
    costs nothing; the durable record is written next, so a gateway that died a moment
    later still owes this parent a review rather than losing the request; the bundle is
    assembled last and atomically, so a run is either completely locked or is not there.
    """
    if not str(brief or "").strip():
        raise NotDelegable("a profile run needs a task brief, and none was given")
    if len(brief) > profile.BRIEF_LIMIT:
        raise NotDelegable(
            f"the brief is longer than {profile.BRIEF_LIMIT} characters — a profile is "
            "given a bounded task, never a conversation"
        )
    try:
        wanted = profile.read(slug, where, library)
    except profile.NotAProfile as why:
        raise NotDelegable(str(why)) from None
    stands = target_of(target, agents.home(name, where))
    kept = agents.records(name, where)
    parent, owed_to = _parent(kept, parent_run)
    posture = narrowed(parent.get("posture"), wanted.posture)
    at = store.stamped(now)
    until = retained_until(now)
    named_label = safe_label(label, wanted.label)
    try:
        run_id = kept.admit_profile(
            wanted.slug, wanted.revision, list(wanted.skills),
            _locks(wanted, brief, posture, library), named_label, posture,
            parent_run, owed_to, stands, at, until, pick=pick,
        )
    except store.Refused as why:
        raise NotDelegable(str(why)) from None
    _assemble(name, run_id, wanted, brief, posture, where, library)
    return Admitted(
        id=run_id, profile=wanted.slug, label=named_label,
        revision=wanted.revision, skills=wanted.skills, posture=posture,
        parent_run=parent_run, parent_conversation=owed_to,
        target=stands, retained_until=until,
    )


def _locks(wanted, brief: str, posture: str, library: dict | None) -> dict:
    """A digest of every part of what this run is about to be locked to (R-PRF-10).

    Recorded per part rather than as the profile's aggregate revision alone, because the
    bundle is writable by the execution it governs — a run that stands in its own home has
    its rules under its own hand. One digest per part is what makes "these are the bytes
    that ran" checkable against the disk afterwards, and what names *which* part changed.
    """
    resolved = library if library is not None else skill.library()
    return {
        "rules": _digest(wanted.instructions),
        "manifest": _digest(json.dumps(
            {**wanted.manifest(), "posture": posture}, indent=2, sort_keys=True) + "\n"),
        "brief": _digest(brief),
        "skills": {one: profile.package_digest(resolved[one]) for one in wanted.skills},
    }


def _digest(text: str) -> str:
    """One part of a locked bundle, as the word its record holds."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parent(kept, parent_run: str):
    """The turn delegating this, and the conversation the answer is owed to.

    Only what the caller needs before the write: which turn, and where its answer is owed.
    **Whether that turn may delegate at all is settled inside the write that admits the
    run**, so nothing can change between the asking and the answer, and the whole rule is
    stated once rather than in two places that would drift.
    """
    row = kept.run(parent_run)
    if row is None:
        raise NotDelegable(f"'{parent_run}' is not a run of this agent's")
    where_it_is = row.get("conversation_id")
    if not where_it_is:
        raise NotDelegable(
            f"'{parent_run}' happened in no conversation, so there is nowhere to report back"
        )
    return row, where_it_is


def _assemble(name: str, run_id: str, wanted, brief: str, posture: str,
              where: Path | None, library: dict | None) -> Path:
    """Build this run's locked context whole, then move it into place.

    Copied rather than linked, and completely. A link into the shared library would make
    "the skills this run used" a question only answerable by what the library holds now,
    which is exactly the question a fortnight-old run has to be able to answer.
    """
    final = bundle(name, run_id, where)
    coming = final.parent / (run_id + COMING)
    if coming.exists():
        shutil.rmtree(coming)
    resolved = library if library is not None else skill.library()
    try:
        (coming / "home" / "workspace").mkdir(parents=True)
        (coming / "skills").mkdir()
        (coming / "home" / LOCKED_RULES).write_text(wanted.instructions, encoding="utf-8")
        (coming / LOCKED_MANIFEST).write_text(
            json.dumps({**wanted.manifest(), "posture": posture}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (coming / LOCKED_BRIEF).write_text(brief, encoding="utf-8")
        for one in wanted.skills:
            # `copytree` with `symlinks=True` keeps a link inside a package as a link and
            # never follows one out of it; `profile.package_digest` already refused a
            # package reaching outside itself, so what is copied is what was digested.
            shutil.copytree(resolved[one], coming / "skills" / one, symlinks=True)
        os.replace(coming, final)
    except BaseException:
        shutil.rmtree(coming, ignore_errors=True)
        raise
    return final


def locked(name: str, run_id: str, where: Path | None = None) -> dict:
    """What this run is actually going to run with, read back off its own bundle.

    Read rather than trusted: the row says which revision was locked and the bundle holds
    the bytes, and a resumption proves the two still agree before starting anything.
    """
    at = paths(name, run_id, where)
    if not at["rules"].is_file() or not at["manifest"].is_file():
        raise NotDelegable(f"'{run_id}' has no locked context left to run with")
    try:
        manifest = json.loads(at["manifest"].read_text(encoding="utf-8"))
    except (OSError, ValueError) as why:
        raise NotDelegable(f"'{run_id}'s locked manifest could not be read: {why}") from None
    return {
        "rules": at["rules"].read_text(encoding="utf-8"),
        "manifest": manifest,
        "brief": at["brief"].read_text(encoding="utf-8") if at["brief"].is_file() else "",
        "skills": sorted(one.name for one in at["skills"].iterdir() if one.is_dir())
        if at["skills"].is_dir() else [],
    }


def verified(name: str, row: dict, where: Path | None = None) -> dict:
    """The locked context, proved to be the one this run was admitted with (R-PRF-10).

    **The bytes, not the names.** A resumption that started against edited content would be
    a different execution wearing an old run's id — the one thing an immutable lock exists
    to prevent — and a check that only compared skill *names* would pass straight through
    an edited package. Every snapshot is digested again and compared with what was recorded
    when the run was admitted.

    Corruption is said out loud and refused rather than repaired: a bundle nobody can vouch
    for is not a bundle to carry work on in.
    """
    at = paths(name, row["id"], where)
    it = locked(name, row["id"], where)
    held = row.get("locked") or {}
    wanted = sorted(row.get("skills") or [])
    if sorted(it["skills"]) != wanted:
        raise NotDelegable(
            f"'{row['id']}'s locked skill snapshot is not what it was admitted with"
        )
    for what, found in (("rules", _digest(it["rules"])),
                        ("manifest", _digest(at["manifest"].read_text(encoding="utf-8"))),
                        ("brief", _digest(it["brief"]))):
        if held.get(what) != found:
            raise NotDelegable(
                f"'{row['id']}'s locked {what} is not what it was admitted with"
            )
    for one, digest in sorted((held.get("skills") or {}).items()):
        try:
            was = profile.package_digest(at["skills"] / one)
        except profile.NotAProfile as why:
            raise NotDelegable(f"'{row['id']}'s locked {one} could not be read: {why}") from None
        if was != digest:
            raise NotDelegable(
                f"'{row['id']}'s locked {one} is not the package it was admitted with"
            )
    return it


def preface(name: str, row: dict, rules: str, where: Path | None = None) -> str:
    """Everything this execution is told before it reads a word of the brief.

    Rundesk's floor, then the profile's own locked rules, then what is mechanically known
    about this run. The target project's own instruction files are deliberately not here:
    the brain stands in that directory and its CLI discovers them the way it always does,
    so a copy taken at admission could only be a staler one (R-PRF-7).
    """
    at = paths(name, row["id"], where)
    return instructions.for_profile(
        variables={
            "profile": profile.label(row["profile"]),
            "parent_agent": agents.display_name(name, where)
            if agents.exists(name, where) else name,
            "profile_run": row["id"],
            "target": row.get("target") or str(at["home"]),
            "workspace": str(at["workspace"]),
        },
        rules=rules,
    )


def execution(name: str, row: dict, where: Path | None = None) -> turn.Execution:
    """Where this profile execution stands, and what it is presented.

    The target project when there is one, so the CLI loads that repository's rules
    natively; the run's own home otherwise, where the locked profile rules stand and are
    discovered the same way (R-PRF-7).
    """
    at = paths(name, row["id"], where)
    return turn.Execution(
        cwd=Path(row["target"]) if row.get("target") else at["home"],
        skills=at["skills"],
        profile_run=row["id"],
        profile=row["profile"],
    )


async def carry(name: str, run_id: str, where: Path | None = None, carrying=None,
                now=None, watching=None, steering=None, admitted=None) -> turn.Outcome:
    """Run one profile execution's root turn, and settle what became of it.

    **Only the root settles the run.** A provider-native subagent inside this turn is the
    provider's business and returns to it; it never reaches here, never wakes the parent
    and never creates a run of its own (R-PRF-14). What this function returns is the one
    terminal outcome, and finishing it is what makes the parent's review owing.
    """
    kept = agents.records(name, where)
    row = kept.profile_run(run_id)
    if row is None:
        raise NotDelegable(f"there is no profile run called '{run_id}'")
    if row["state"] == store.EXPIRED:
        raise NotDelegable(
            f"'{run_id}' is past its retention window and can no longer be carried on"
        )
    if row["state"] in store.FINISHED_PROFILES:
        raise NotDelegable(f"'{run_id}' has already finished")
    it = verified(name, row, where)
    bundled = paths(name, run_id, where)
    parent = kept.run(row["parent_run"]) or {}
    chose = kept.agent()
    named = parent.get("provider") or chose.get("provider") or ""
    if not named:
        raise NotDelegable(f"'{name}' has no brain to run '{run_id}' with")
    at = store.stamped(now)
    kept.profile_working(run_id, at, retained_until(now))
    outcome = await (carrying or turn.carry)(
        name, it["brief"], named,
        where=where,
        model=parent.get("model") or chose.get("model"),
        settings=parent.get("settings") or chose.get("settings"),
        posture=row["posture"],
        conversation=run_id,
        on=turn.PROFILE,
        kind=turn.PROFILE,
        source=turn.PROFILE,
        preface=preface(name, row, it["rules"], where),
        prompt_author="rundesk",
        context=execution(name, row, where),
        watching=watching,
        steering=steering,
        admitted=admitted,
        now=now,
    )
    kept.profile_active(run_id, store.stamped(now), retained_until(now))
    # Before the outcome is settled, because settling is what makes the parent's review
    # owing — and a report that says the checkout was left as it was found should be true
    # by the time anybody reads it.
    unpresent(row.get("target"), bundled["skills"])
    settle(name, run_id, outcome, where=where, now=now)
    return outcome


#: How deep into a target project a presented skill may have been placed. Every adapter
#: measured puts them one or two components down — `.agents/skills/<name>`,
#: `.claude/skills/<name>`, `.grok/skills/<name>` — so three is the shape plus room, and a
#: bound is what keeps this from walking somebody's whole repository.
PRESENTED_DEPTH = 3


def unpresent(target: str | None, skills_root: Path) -> list:
    """Take back whatever an adapter stood in the target project on this run's behalf.

    **A profile execution stands in somebody's repository, and every adapter presents its
    skills beside the directory it stands in.** So a run that simply ended left a vendor
    directory inside that checkout, holding links into a bundle that is swept after
    fourteen days — dangling ones, in a repository the worker was told to leave exactly as
    it found it.

    Vendor-neutral by construction: this knows nothing about which directory any brain
    uses, and removes only a **link that resolves inside this run's own skill snapshot**.
    A directory is removed only once emptied by that, so anything of the owner's — even in
    the same place — is untouched. Nothing here raises: a project that cannot be tidied is
    worth saying nothing about beside the work that was done.
    """
    if not target:
        return []
    root = Path(target)
    try:
        mine = skills_root.resolve()
    except OSError:
        return []
    taken, emptied = [], []
    for at in _shallow(root, PRESENTED_DEPTH):
        try:
            if not at.is_symlink() or mine not in at.resolve().parents:
                continue
            at.unlink()
        except OSError:
            continue
        taken.append(at.name)
        emptied.append(at.parent)
    for at in sorted(set(emptied), key=lambda one: len(one.parts), reverse=True):
        while at != root and root in at.parents:
            try:
                at.rmdir()      # refuses the moment anything of the owner's is in it
            except OSError:
                break
            at = at.parent
    return sorted(taken)


def _shallow(root: Path, depth: int):
    """Everything standing within this many components of here, and no further."""
    found, edge = [], [root]
    for _ in range(depth):
        below = []
        for one in edge:
            try:
                below.extend(sorted(one.iterdir()))
            except OSError:
                continue
        found.extend(below)
        edge = [one for one in below if one.is_dir() and not one.is_symlink()]
    return found


def settle(name: str, run_id: str, outcome: turn.Outcome, where: Path | None = None,
           now=None) -> bool:
    """Write down what this execution came to, and owe its parent one review.

    Rundesk records what the provider reported and parses nothing out of it (R-PRF-16). A
    report claiming tests passed is a report claiming tests passed; whether they did is
    the named parent's to check, and a gateway that inferred it would be manufacturing the
    one fact the review exists to establish.
    """
    kept = agents.records(name, where)
    at = store.stamped(now)
    became = store.SUCCEEDED if outcome.ok else (
        store.STOPPED if outcome.became == turn.INTERRUPTED else store.FAILED
    )
    return kept.finish_profile(
        run_id, at, became, outcome.text or (outcome.why or ""), retained_until(now)
    )


def owed_review(name: str, run_id: str, where: Path | None = None) -> dict:
    """Whether this run's parent has been told, and how often it has been tried.

    Read for a listing rather than for a decision: a review that has been attempted many
    times and never delivered is the shape of a surface that is not coming back, and an
    owner cannot see that anywhere else.
    """
    kept = agents.reading(name, where)
    for one in kept.owed_profile_callbacks(limit=kept.OWED_AT_ONCE):
        if one["profile_run"] == run_id:
            return {"owed": True, "attempts": int(one["attempts"] or 0)}
    return {"owed": False, "attempts": 0}


def handoff(name: str, run_id: str, where: Path | None = None) -> dict:
    """The one report a named parent reviews, and what is mechanically known beside it.

    Nothing here is read out of the report. What Rundesk knows it knows — which run, whose
    behalf, which profile, where it worked, what it cost — and what the worker said stays
    the worker's words (R-PRF-16).
    """
    kept = agents.reading(name, where)
    row = kept.profile_run(run_id)
    if row is None:
        raise NotDelegable(f"there is no profile run called '{run_id}'")
    # Asked of the column the records keep it in, never found by scanning the newest
    # runs: a busy agent's profile turn falls off the end of a scan, and what the handoff
    # would then report is no usage, no files, and nothing verified — silently.
    carried = kept.runs(profile_run=run_id, limit=200)
    files, tokens = [], {"reported": False}
    for one in carried:
        if one.get("tokens_reported"):
            tokens = {
                "reported": True,
                "input": one.get("tokens_in"), "output": one.get("tokens_out"),
                "cached": one.get("tokens_cached"), "written": one.get("tokens_written"),
            }
        files += [
            said["event"].get("at")
            for said in kept.records(one["id"])
            if (said.get("event") or {}).get("type") == "file"
        ]
    return {
        "profile_run": row["id"],
        "parent_run": row["parent_run"],
        "parent_agent": name,
        "profile": row["profile"],
        "outcome": row["outcome"] or row["state"],
        "target": row["target"],
        "report": row["report"] or "",
        "files": [one for one in files if one],
        "usage": tokens,
        "verification_recorded": bool(carried),
    }


def sweep(name: str, where: Path | None = None, now=None) -> list:
    """Take away every execution context whose retention window has passed (R-PRF-12).

    What goes is the bundle and the provider session. What stays is every durable record
    of what was asked, what it cost and what it answered — an owner reading a month-old
    run back still gets the whole account, and only the ability to carry it on is gone.
    """
    kept = agents.records(name, where)
    gone = []
    for row in kept.expired_profiles(store.stamped(now)):
        # A run its gateway never got to finish still stood links in somebody's project.
        unpresent(row.get("target"), paths(name, row["id"], where)["skills"])
        with_it = bundle(name, row["id"], where)
        shutil.rmtree(with_it, ignore_errors=True)
        # The handle as well as the bundle. A session left behind is a run that could be
        # carried on with its locked rules gone, which is the one thing expiry must not
        # leave possible.
        kept.forget_session(store.conversation_id(turn.PROFILE, row["id"]))
        gone.append(row["id"])
    _tidy(home(name, where))
    return gone


def _tidy(root: Path) -> None:
    """Clear the debris a crashed assembly leaves, and nothing that is somebody's work."""
    try:
        for one in root.iterdir():
            if one.name.endswith(COMING) and one.is_dir():
                shutil.rmtree(one, ignore_errors=True)
    except OSError:
        return


def shown(row: dict, now=None) -> dict:
    """One profile run as a person is shown it — never a local path, never a prompt.

    A listing is read where other people can see it, so what a target directory is called
    is its last component and the private path it stands at is left in the records
    (R-PRF-17).
    """
    began = store.moment(row.get("admitted_at"))
    return {
        "id": row["id"],
        "profile": row["profile"],
        "label": row["label"],
        "revision": (row.get("revision") or "")[:12],
        "parent_run": row["parent_run"],
        "target": Path(row["target"]).name if row.get("target") else "",
        "state": row["state"],
        "outcome": row.get("outcome") or "",
        "skills": list(row.get("skills") or []),
        "posture": row.get("posture") or provider.WORK,
        "reviewed": bool(row.get("reviewed_at")),
        "retained_until": row.get("retained_until") or "",
        "elapsed": int(max(0, (now or time.time)() - began.timestamp())) if began else 0,
    }
