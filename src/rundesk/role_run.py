"""One isolated specialist execution, from the moment it is admitted to the moment it expires.

A named agent decides to delegate; this is everything that happens because it did. The
named agent stays the only durable identity, the only conversation owner and the only
thing that answers a person (R-ROL-1). What runs here is a fresh execution with the
agent's identity, memory, history and operational rules deliberately absent from it.

**What a run is admitted with never changes for that run** (R-ROL-10). The role's rules,
its complete skill set and its manifest are copied into a bundle of the run's own before
the brain is started, and the bundle is what the brain is presented. Editing the shared
role, or a skill it exposes, changes what the *next* run is admitted with and nothing
about this one — so a run resumed on day fourteen resumes with the bytes it started with,
and the digest recorded against it says which bytes those were.

**The bundle is built whole and moved into place.** A half-assembled run that a gateway
picked up would be a specialist execution missing some of its rules, which is worse than
one that never started: nothing would report it, and the work would simply be done wrong.

The layout is:

    <agent>/role-runs/<run>/
    ├── home/
    │   ├── AGENTS.md      the locked role rules, byte for byte
    │   └── workspace/     non-project artifacts only
    ├── skills/            the locked copy of the complete configured set
    ├── brief.md           the bounded task the parent handed over
    └── role.json       the locked manifest

Nothing mutable lives in it. Where the run got to, how long it stays resumable, which
provider session carries it and whether its parent has been told are all rows, because
those change while the locked bytes must not.

**Which brain carries it is settled at admission and recorded** (R-ROL-34), rather than
resolved again by whatever picks the run up. A run has to be able to say afterwards what
it actually ran on; a role edited in between must not change that answer; and a resumption
carries on a provider session that belongs to one brain and cannot be moved to another.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from rundesk import agent as agents
from rundesk import instructions, role, provider, skill, store, turn

#: Where one agent's role runs stand. Inside the agent's own directory, so a bundle is
#: backed up with the agent, removed with the agent, and reachable by nobody else.
RUNS = "role-runs"

#: What a bundle is made of, once. Named here rather than spelled at each caller, because a
#: directory added in one place and forgotten in another is a run assembled incompletely.
LOCKED_RULES = "AGENTS.md"
LOCKED_MANIFEST = "role.json"
LOCKED_BRIEF = "brief.md"

#: How long after its latest activity a role run stays resumable (R-ROL-11). Measured
#: from activity rather than from admission: a run somebody is still steering on day
#: thirteen is work in progress, and a window counted from the start would sweep it.
RETAINED_DAYS = 14

#: What a run being assembled is called while it is not one yet. A dot, so nothing listing
#: role runs ever shows a half-built one, and a fixed suffix so a crashed assembly is
#: recognisable as debris rather than as somebody's work.
COMING = ".coming"


class NotDelegable(Exception):
    """This work cannot be handed to a role, and the reason is the whole message.

    Raised before anything durable is written or assembled. A refusal that arrives after a
    bundle exists has already left an owner something to clean up, and after a provider
    starts it has already spent their money.
    """


@dataclass(frozen=True)
class Admitted:
    """What one role run was admitted with — settled, and never changed after."""

    id: str
    role: str
    label: str
    revision: str
    skills: tuple
    posture: str
    #: The brain this run was admitted to run on, and the model on it. Resolved once, from
    #: the flag, the role and the parent turn in that order, and recorded — so every turn
    #: of this run reaches the same brain however long afterwards it is carried on.
    provider: str
    model: str
    parent_run: str
    parent_conversation: str
    target: str | None
    retained_until: str


def home(name: str, where: Path | None = None) -> Path:
    """Where this agent's role runs stand."""
    return agents.directory(name, where) / RUNS


def bundle(name: str, run_id: str, where: Path | None = None) -> Path:
    """The one directory this role run is, proved to stand where role runs are kept.

    Both halves are asked exactly as an agent's directory asks them, and for the same
    reason: a run id reaches this from a durable row and from an environment variable, and
    one that resolved somewhere else would let a swept bundle take an owner's directory
    with it.
    """
    root = home(name, where)
    stands = root / _checked(run_id)
    if stands.exists() and stands.resolve().parent != root.resolve():
        raise NotDelegable(
            f"'{run_id}' does not stand where role runs are kept — it reaches "
            f"{stands.resolve()}"
        )
    return stands


def paths(name: str, run_id: str, where: Path | None = None) -> dict:
    """Every place one role run resolves, by what it is for."""
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
    """A role run's id, or why it cannot name a directory."""
    if not run_id or not run_id.startswith("rol-"):
        raise NotDelegable(f"'{run_id}' is not a role run")
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

    **Never inside the named agent's own home** (R-ROL-5). The provider stands in this
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
                "a role run cannot work inside the agent's own home — standing there "
                "would hand it that agent's rules, memory and identity"
            )
    return str(stands)


def narrowed(parent: str | None, wanted: str) -> str:
    """The posture this execution actually runs under.

    **A role may narrow what its parent could do and may never widen it.** The parent
    turn is the authority a worker acts under, so a role asking to change the machine
    from a turn that was only allowed to read it is asking for authority nobody granted.
    """
    if parent == provider.READ or wanted == provider.READ:
        return provider.READ
    return provider.WORK


def brain(asked: str | None, asked_model: str | None, wanted, parent: dict,
          chose: dict) -> tuple:
    """Which brain this run is admitted to run on, and the model on it.

    **Most specific first** (R-ROL-34): what the parent asked for on this one run, then
    what the role says every run of it uses, then whatever the parent turn itself resolved
    — the agent's own default being the last of those, exactly as it is for an ordinary
    turn. A role that names neither resolves to what it resolved before this field
    existed, which is what makes every installed role keep working untouched.

    **What belongs to one brain never crosses to another.** A model and a set of provider
    settings are a particular brain's, so where a role or a flag moves this run off the
    brain the parent turn was on, neither comes with it: a codex model handed to claude is
    a turn that fails on a name the owner never typed. Where the brain is the inherited
    one, the whole chain is exactly today's.

    Settings are not settled here: they are how this agent is configured for that brain
    now rather than part of what the run was admitted with, so `carried_with` reads them
    when the run is carried.
    """
    inherited = parent.get("provider") or chose.get("provider") or ""
    named = str(asked or "").strip() or wanted.provider or inherited
    model = str(asked_model or "").strip() or wanted.model
    if named == inherited:
        model = model or parent.get("model") or chose.get("model") or ""
    return named, model


def safe_label(said: str | None, fallback: str) -> str:
    """A short task label safe to show where other people are reading (R-ROL-17).

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
          now=None, pick=None, named: str | None = None, model: str | None = None,
          runnable=None) -> Admitted:
    """Admit one role run for this agent, and seal everything it will run with.

    The order is the whole of the safety here. Everything refusable is refused first and
    costs nothing; the durable record is written next, so a gateway that died a moment
    later still owes this parent a review rather than losing the request; the bundle is
    assembled last and atomically, so a run is either completely locked or is not there.

    `named` and `model` are this one run's brain, beating the role's own (R-ROL-34).
    `runnable` is asked whether this machine has the brain that was resolved, and is passed
    in rather than imported for the reason every other collaborator here is: what is being
    asked is a question about the machine, and a decision that reached for it itself could
    not be exercised against a machine that has a different one.
    """
    if not str(brief or "").strip():
        raise NotDelegable("a role run needs a task brief, and none was given")
    if len(brief) > role.BRIEF_LIMIT:
        raise NotDelegable(
            f"the brief is longer than {role.BRIEF_LIMIT} characters — a role is "
            "given a bounded task, never a conversation"
        )
    try:
        wanted = role.read(slug, where, library)
    except role.NotARole as why:
        raise NotDelegable(str(why)) from None
    stands = target_of(target, agents.home(name, where))
    kept = agents.records(name, where)
    parent, owed_to = _parent(kept, parent_run)
    posture = narrowed(parent.get("posture"), wanted.posture)
    on, model_named = brain(named, model, wanted, parent, kept.agent())
    _has_a_brain(name, on, runnable)
    at = store.stamped(now)
    until = retained_until(now)
    named_label = safe_label(label, wanted.label)
    try:
        run_id = kept.admit_role(
            wanted.slug, wanted.revision, list(wanted.skills),
            _locks(wanted, brief, posture, library), named_label, posture,
            parent_run, owed_to, stands, at, until,
            provider=on, model=model_named, pick=pick,
        )
    except store.Refused as why:
        raise NotDelegable(str(why)) from None
    _assemble(name, run_id, wanted, brief, posture, where, library)
    return Admitted(
        id=run_id, role=wanted.slug, label=named_label,
        revision=wanted.revision, skills=wanted.skills, posture=posture,
        provider=on, model=model_named,
        parent_run=parent_run, parent_conversation=owed_to,
        target=stands, retained_until=until,
    )


def _has_a_brain(name: str, on: str, runnable=None) -> None:
    """Prove this machine has the brain this run resolved, before anything is written.

    **At admission and never mid-carry** (R-ROL-35). A role pinned to a brain this install
    has not got is knowable from the manifest and the machine, and a run admitted on it
    costs an owner an assembled bundle, a gateway attempt and a handoff saying Rundesk
    could not carry the work — six seconds later, for something answerable up front.

    The refusal names the brain *and* the agent, because neither alone is the fix: which
    brain was asked for is in the role or the flag, and which agent has not got it is what
    decides whether the answer is to install one or to hand the work somewhere else.
    """
    if not on:
        raise NotDelegable(
            f"nothing says which brain answers for '{name}', so there is none to run this "
            f"with — rundesk configure {name} --provider <provider>"
        )
    try:
        (runnable or provider.program)(on)
    except provider.NotRunnable as why:
        raise NotDelegable(
            f"'{name}' has no brain called '{on}' to run this with: {why}"
        ) from None


def _locks(wanted, brief: str, posture: str, library: dict | None) -> dict:
    """A digest of every part of what this run is about to be locked to (R-ROL-10).

    Recorded per part rather than as the role's aggregate revision alone, because the
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
        "skills": {one: role.package_digest(resolved[one]) for one in wanted.skills},
    }


def _digest(text: str) -> str:
    """One part of a locked bundle, as the word its record holds."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prompt(kept, row: dict, it: dict) -> str:
    """What this turn is asked: the brief the first time, and what was said after that.

    **"Has this run ever finished" is the question, and the records already answer it.**
    An outcome is written when a run settles and is never cleared, so a resumption carries
    one and a first execution does not — including a first execution whose gateway died
    part-way, which must still be asked the brief rather than a word somebody steered it
    with. Nothing new is stored to know this, and nothing can drift out of step with it.
    """
    said = kept.words_for_role(row["id"], store.stamped())
    kept_words = [one for one in said if one.strip()]
    if not row.get("outcome"):
        # Anything said before this ever started is part of what it is being asked. Folded
        # in rather than left for the steering seam, because a brain that cannot be sent to
        # mid-turn would never read it there and the words would simply be lost.
        return "\n\n".join([it["brief"], *kept_words])
    return "\n\n".join(kept_words) or CARRY_ON


def _steering(name: str, run_id: str, where, now):
    """The parent's words, for a turn that was not handed a source of its own."""
    return steering(name, run_id, where, now=now)


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
            # never follows one out of it; `role.package_digest` already refused a
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
    """The locked context, proved to be the one this run was admitted with (R-ROL-10).

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
            was = role.package_digest(at["skills"] / one)
        except role.NotARole as why:
            raise NotDelegable(f"'{row['id']}'s locked {one} could not be read: {why}") from None
        if was != digest:
            raise NotDelegable(
                f"'{row['id']}'s locked {one} is not the package it was admitted with"
            )
    return it


def preface(name: str, row: dict, rules: str, where: Path | None = None) -> str:
    """Everything this execution is told before it reads a word of the brief.

    Rundesk's floor, then the role's own locked rules, then what is mechanically known
    about this run. The target project's own instruction files are deliberately not here:
    the brain stands in that directory and its CLI discovers them the way it always does,
    so a copy taken at admission could only be a staler one (R-ROL-7).
    """
    at = paths(name, row["id"], where)
    return instructions.for_role(
        variables={
            "role": role.label(row["role"]),
            "parent_agent": agents.display_name(name, where)
            if agents.exists(name, where) else name,
            "role_run": row["id"],
            "target": row.get("target") or str(at["home"]),
            "workspace": str(at["workspace"]),
        },
        rules=rules,
    )


def execution(name: str, row: dict, where: Path | None = None) -> turn.Execution:
    """Where this role execution stands, and what it is presented.

    The target project when there is one, so the CLI loads that repository's rules
    natively; the run's own home otherwise, where the locked role rules stand and are
    discovered the same way (R-ROL-7).
    """
    at = paths(name, row["id"], where)
    return turn.Execution(
        cwd=Path(row["target"]) if row.get("target") else at["home"],
        skills=at["skills"],
        role_run=row["id"],
        role=row["role"],
    )


async def steering(name: str, run_id: str, where: Path | None = None, every=None,
                   now=None):
    """Everything the parent says to this execution while it is still running.

    **Never ends of its own accord**, exactly as the terminal's own steering does not: what
    ends it is the turn ending, and `turn.carry` cancels this the moment the brain stops.
    A generator that ended early would close the input of a brain that is still working.

    Claimed from the records rather than handed over in memory, because the thing saying
    something is a different process — the agent's own next turn — and it may be talking to
    a gateway that did not exist when this execution started.
    """
    kept = agents.records(name, where)
    waited = STEER_SECONDS if every is None else every
    while True:
        for said in kept.words_for_role(run_id, store.stamped(now)):
            if said.strip():
                yield turn.Said(said, None)
        await asyncio.sleep(waited)


def say(name: str, run_id: str, said: str, where: Path | None = None, now=None) -> str:
    """Say something to this role run, and answer where it will land.

    One queue, because a word said to a role is one kind of thing. Where it goes is a fact
    about the run at the moment it is read: an execution in flight is steered, and one that
    is over and still retained is carried on by `resume`. Said plainly here rather than
    guessed at, so an agent that reached for the wrong verb is told which one it wanted.
    """
    kept = agents.records(name, where)
    row = _held(kept, run_id)
    if not str(said or "").strip():
        raise NotDelegable("nothing was said")
    if len(said) > role.BRIEF_LIMIT:
        raise NotDelegable(
            f"more than {role.BRIEF_LIMIT} characters — a word said to work in flight is "
            "guidance, and a task that large is a role run of its own"
        )
    if row["state"] not in (store.ADMITTED, store.WORKING):
        raise NotDelegable(
            f"'{run_id}' is not running — to carry it on with more work, resume it"
        )
    if not _can_be_sent_to(kept, run_id):
        # **Said rather than queued behind a brain that will never read it.** Not every
        # brain can be sent to mid-turn — of the four that ship, two say so plainly — and
        # a word accepted for one that cannot is a word that sits unread while the command
        # that took it reported success. Stopping it, or waiting and resuming it, are the
        # two things that do work.
        #
        # **Which brain, by name.** Now that a role may pin one, "cannot be steered" is a
        # property of the role rather than of whichever brain the parent happened to be on
        # — and an owner reading this needs to know which one to stop pinning.
        raise NotDelegable(
            f"{_which_brain(kept, run_id)} cannot be sent to while it works — stop "
            "it, or wait for it and resume it with what you wanted to say"
        )
    try:
        kept.say_to_role(run_id, said, store.stamped(now))
    except store.Refused as why:
        raise NotDelegable(str(why)) from None
    if row["state"] == store.WORKING:
        return "it reaches the work in flight; nothing is answered back here"
    return "it is added to what this run is asked when it starts"


def stop(name: str, run_id: str, where: Path | None = None, now=None) -> bool:
    """Ask this execution to end, and say whether there was one to end.

    The ask is durable and the acting is the gateway's: what has to be ended is a task it
    owns, and a person asking may not have reached the gateway carrying it.
    """
    kept = agents.records(name, where)
    _held(kept, run_id)
    try:
        return kept.ask_role_stop(run_id, store.stamped(now))
    except store.Refused as why:
        raise NotDelegable(str(why)) from None


def resume(name: str, run_id: str, more: str, where: Path | None = None, now=None) -> str:
    """Carry a finished role run on with more work, in the session it already has.

    **The locked bundle is not touched** (R-ROL-10). A continuation is the next thing said,
    never an edit to the brief this run was admitted with — the digests still have to
    verify before it is carried, and they are the whole reason a fortnight-old run can be
    trusted at all.
    """
    kept = agents.records(name, where)
    row = _held(kept, run_id)
    if not str(more or "").strip():
        raise NotDelegable("a resumed role run needs something more to do, and none was given")
    if len(more) > role.BRIEF_LIMIT:
        raise NotDelegable(
            f"the continuation is longer than {role.BRIEF_LIMIT} characters"
        )
    if row["state"] in (store.ADMITTED, store.WORKING):
        raise NotDelegable(
            f"'{run_id}' is still running — to guide the work it is doing now, say it"
        )
    at = store.stamped(now)
    kept.say_to_role(run_id, more, at)
    if not kept.resume_role(run_id, at, retained_until(now)):
        raise NotDelegable(f"'{run_id}' could not be carried on")
    return run_id


def _which_brain(kept, run_id: str) -> str:
    """The brain carrying this run, as a refusal names it.

    **Read off the turn actually carrying it**, which is the same row that answered
    whether it may be sent to at all: two rows would eventually name one brain and
    describe another's. A run nothing has started has no answer here and never reaches
    this — what is said to one is folded into what it is asked when it starts — and the
    sentence still reads without one, because a refusal saying `'' cannot be sent to`
    would be worse than one that named nothing.

    Never the raw name (R-ROL-17): a brain may be a path to a program somebody wrote, and
    this sentence is read wherever the agent is reached.
    """
    carried = kept.runs(role_run=run_id, limit=1)
    named = (carried[0].get("provider") or "") if carried else ""
    return f"{provider.label(named)}, the brain carrying '{run_id}'," if named else (
        f"the brain carrying '{run_id}'")


def _can_be_sent_to(kept, run_id: str) -> bool:
    """Whether the brain carrying this run reads anything after the prompt.

    Answered from what the turn recorded it could do when it was admitted (R-PRV-15), which
    is the only thing that knows — and never by asking an adapter again, because what this
    execution is being carried by is settled and asking twice could disagree with it.

    A run nothing has started yet has no answer, and is allowed: what is said to it is
    folded into what it is asked when it starts, so nothing is stranded either way.
    """
    carried = kept.runs(role_run=run_id, limit=1)
    if not carried:
        return True
    return bool((carried[0].get("can") or {}).get("steer"))


def _held(kept, run_id: str) -> dict:
    """The run this is about, refused where its execution context is gone."""
    row = kept.role_run(run_id)
    if row is None:
        raise NotDelegable(f"there is no role run called '{run_id}'")
    if row["state"] == store.EXPIRED:
        raise NotDelegable(
            f"'{run_id}' is past its retention window and can no longer be carried on"
        )
    return row


async def carry(name: str, run_id: str, where: Path | None = None, carrying=None,
                now=None, watching=None, steering=None, admitted=None) -> turn.Outcome:
    """Run one role execution's root turn, and settle what became of it.

    **Only the root settles the run.** A provider-native subagent inside this turn is the
    provider's business and returns to it; it never reaches here, never wakes the parent
    and never creates a run of its own (R-ROL-14). What this function returns is the one
    terminal outcome, and finishing it is what makes the parent's review owing.
    """
    kept = agents.records(name, where)
    row = kept.role_run(run_id)
    if row is None:
        raise NotDelegable(f"there is no role run called '{run_id}'")
    if row["state"] == store.EXPIRED:
        raise NotDelegable(
            f"'{run_id}' is past its retention window and can no longer be carried on"
        )
    if row["state"] in store.FINISHED_ROLES:
        raise NotDelegable(f"'{run_id}' has already finished")
    it = verified(name, row, where)
    bundled = paths(name, run_id, where)
    parent = kept.run(row["parent_run"]) or {}
    chose = kept.agent()
    named, model, settings = carried_with(row, parent, chose)
    if not named:
        raise NotDelegable(f"'{name}' has no brain to run '{run_id}' with")
    at = store.stamped(now)
    kept.role_working(run_id, at, retained_until(now))
    outcome = await (carrying or turn.carry)(
        name, _prompt(kept, row, it), named,
        where=where,
        model=model,
        settings=settings,
        posture=row["posture"],
        conversation=run_id,
        on=turn.ROLE,
        kind=turn.ROLE,
        source=turn.ROLE,
        preface=preface(name, row, it["rules"], where),
        prompt_author="rundesk",
        context=execution(name, row, where),
        watching=watching,
        # What the parent says to this execution while it runs. Handed over as the seam
        # `turn.carry` already has, so a word said to a role travels the same path as a
        # word typed at a terminal — into the account first, and then to the brain.
        steering=(steering if steering is not None
                  else _steering(name, run_id, where, now)),
        admitted=admitted,
        # A person asked for this to end, rather than a gateway going down under it. The
        # difference is the whole of what `rundesk runs` can answer afterwards about a
        # quiet night (R-RUN-13).
        stopped_by_owner=lambda: bool(
            (kept.role_run(run_id) or {}).get("stop_asked_at")),
        now=now,
    )
    kept.role_active(run_id, store.stamped(now), retained_until(now))
    # Before the outcome is settled, because settling is what makes the parent's review
    # owing — and a report that says the checkout was left as it was found should be true
    # by the time anybody reads it.
    unpresent(row.get("target"), bundled["skills"])
    settle(name, run_id, outcome, where=where, now=now)
    return outcome


def carried_with(row: dict, parent: dict, chose: dict) -> tuple:
    """The brain this turn of the run reaches, the model on it, and how it is configured.

    **Read back, never resolved again** (R-ROL-34). The run recorded which brain it was
    admitted on, and every turn of it — the first, and a resumption a fortnight later —
    goes to that one: the provider session a resumption carries on belongs to that brain
    and cannot be moved to another, and a role edited in between must not change what a
    run that has already started is running on.

    Settings are the exception and deliberately: they are how this agent is configured for
    that brain *now*, not part of what the run was admitted with, so they are read here.
    They belong to one brain, so a run moved off the brain the parent turn was on is given
    none of them rather than another brain's.

    A run admitted before a run recorded its own brain has none, and NULL means what it
    meant then: carry it on whatever the parent turn resolved.
    """
    inherited = parent.get("provider") or chose.get("provider") or ""
    settings = parent.get("settings") or chose.get("settings")
    if not row.get("provider"):
        return (inherited, parent.get("model") or chose.get("model"), settings)
    named = row["provider"]
    return (named, row.get("model") or None,
            settings if named == inherited else None)


#: What a resumed execution is asked when its parent moved it back into hand and said
#: nothing more. Prose rather than an empty prompt: a brain given nothing answers about
#: nothing, and the session it is carrying on already holds the work.
CARRY_ON = (
    "Carry on from where you stopped. Finish the task you were given, and report as your "
    "rules require."
)

#: How often a running execution looks for something its parent has said to it. Close to
#: the beat: a person who has just corrected their agent is waiting to see it land, and a
#: word that arrives after the work it was meant to change is a word that arrived too late.
STEER_SECONDS = 3.0


#: How often a run that is still working says so where the work was asked for. Twenty
#: minutes: long enough that an hour's job is four lines rather than forty, short enough
#: that somebody who came back to the room can tell a run that is going from one that is
#: gone. Counted from admission, which is what `shown` already reports as `elapsed`, so
#: the line and the listing can never disagree about how long it has been.
CHECK_IN_SECONDS = 1200.0


def check_in_due(elapsed: float, told: int = 0) -> int:
    """Which check-in this run has reached, or 0 when it owes none.

    A bucket number rather than a timestamp, so a gateway that restarted mid-run resumes
    the cadence from where the clock is rather than immediately saying something — and so
    two looks a second apart cannot produce two lines.
    """
    reached = int(max(0.0, float(elapsed)) // CHECK_IN_SECONDS)
    return reached if reached > max(0, int(told)) else 0


#: How deep into a target project a presented skill may have been placed. Every adapter
#: measured puts them one or two components down — `.agents/skills/<name>`,
#: `.claude/skills/<name>`, `.grok/skills/<name>` — so three is the shape plus room, and a
#: bound is what keeps this from walking somebody's whole repository.
PRESENTED_DEPTH = 3


def unpresent(target: str | None, skills_root: Path) -> list:
    """Take back whatever an adapter stood in the target project on this run's behalf.

    **A role execution stands in somebody's repository, and every adapter presents its
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

    Rundesk records what the provider reported and parses nothing out of it (R-ROL-16). A
    report claiming tests passed is a report claiming tests passed; whether they did is
    the named parent's to check, and a gateway that inferred it would be manufacturing the
    one fact the review exists to establish.
    """
    kept = agents.records(name, where)
    at = store.stamped(now)
    became = store.SUCCEEDED if outcome.ok else (
        store.STOPPED if outcome.became == turn.INTERRUPTED else store.FAILED
    )
    return kept.finish_role(
        run_id, at, became, outcome.text or (outcome.why or ""), retained_until(now)
    )


#: How many times carrying one run may throw before it is settled rather than tried again.
#: Three, because the fault this is a ceiling on is the one that happens every time: a
#: provider that has gone, a target directory somebody moved, a bundle nobody can vouch
#: for. Two more goes is enough for a blip to pass and few enough that a fault which costs
#: a real turn costs three of them and stops.
CARRY_CEILING = 3

#: How long after a throw the same run is left alone. Doubled per attempt, so three
#: attempts are spread over minutes rather than over the fifteen seconds a five-second
#: look would otherwise take — a ceiling on attempts is only a ceiling on cost if
#: something puts time between them.
CARRY_BACKOFF_SECONDS = 60.0

#: How many times a parent may be woken for one handoff before it is settled undelivered
#: (R-ROL-37). Three, matching what carrying a run is allowed: the faults this bounds are
#: the ones that happen every time — a session that hands every turn back, a brain that
#: answers nothing — and two more goes is enough for a blip to pass.
REVIEW_CEILING = 3

#: What an owner is told when a handoff could not be delivered at all.
#:
#: **Rundesk reporting on the delivery, and never a word of the report** (R-ROL-19). The
#: worker's account has still not been reviewed by anybody, so putting any of it here would
#: publish unreviewed work by the one route built to prevent it. What this says is which run,
#: which role, and that its report is still waiting — enough to go and ask for it.
REVIEW_UNDELIVERABLE = (
    "A role run finished and Rundesk could not get its report reviewed. This is Rundesk "
    "reporting on the delivery rather than on the work: the report has not been read by "
    "anybody and none of it is repeated here. Run {run}, role {role}, woken {attempts} "
    "times without the review ever answering."
)

#: How long a run may produce nothing at all before Rundesk settles it. The owner's
#: number, and measured on inactivity rather than on total runtime: a legitimately long
#: job keeps writing records, and ending one at six hours of honest work would be worse
#: than the wedged provider this exists for. Written into `config.json` by the install,
#: which is what an owner changes; this is the value that is written.
QUIET_HOURS = 6

#: What a parent is told when Rundesk could not carry the run at all.
#:
#: **Rundesk reporting on the run, never on the work** (R-ROL-16). Nothing was verified
#: and no worker said anything, so the one thing that must not happen is a parent reading
#: this as a specialist's report of a failed job — those are different claims and only one
#: of them is being made here.
COULD_NOT_CARRY = (
    "Rundesk could not carry this role run, and this is Rundesk reporting on the run "
    "rather than the role reporting on the work. Nothing was checked and the worker said "
    "nothing. It was attempted {attempts} times and each attempt ended the same way:\n\n"
    "{why}"
)

#: What a parent is told when a run stopped producing anything. Again about the run: the
#: work may have been half done or not started, and Rundesk does not know which.
WENT_QUIET = (
    "Rundesk settled this role run because it stopped producing any activity, and this is "
    "Rundesk reporting on the run rather than the role reporting on the work. Nothing was "
    "checked and the worker never reported. Its latest activity was at {seen}, more than "
    "{hours} hours before it was settled."
)

#: What a parent is told when a run reached the end of its retention window unsettled.
EXPIRED_UNSETTLED = (
    "Rundesk settled this role run because it reached the end of its retention window "
    "without ever finishing, and this is Rundesk reporting on the run rather than the "
    "role reporting on the work. Nothing was checked and the worker never reported."
)


def backoff_seconds(attempts: int) -> float:
    """How long to leave a run alone after this many failed attempts at carrying it."""
    return CARRY_BACKOFF_SECONDS * (2 ** max(0, int(attempts) - 1))


def ready_to_carry(row: dict, now=None) -> bool:
    """Whether enough time has passed since this run's latest failed carry.

    Wall time on both sides, and deliberately: the gateway deciding this is usually not
    the gateway that failed, so there is no monotonic clock the two share — the same
    reason a retention window is a durable stamp rather than an elapsed count.
    """
    failed = store.moment(row.get("carry_failed_at"))
    if failed is None:
        return True
    waited = backoff_seconds(row.get("carry_attempts") or 0)
    return (now or time.time)() - failed.timestamp() >= waited


def carry_failed(name: str, run_id: str, why: str, where: Path | None = None,
                 now=None) -> dict:
    """Count one attempt at carrying this run that threw, and settle it at the ceiling.

    Under the ceiling the run is left exactly as it was, so the next look picks it up
    again once the backoff has passed and a transient fault heals itself without anybody
    hearing about it. At the ceiling it is settled `failed` with what actually went wrong,
    which owes its parent the one review it is owed however a run ends (R-ROL-15).

    Answers how many attempts there have been and whether this one settled it.
    """
    kept = agents.records(name, where)
    at = store.stamped(now)
    attempts = kept.role_carry_failed(run_id, at)
    if attempts < CARRY_CEILING:
        return {"attempts": attempts, "settled": False}
    settled = kept.finish_role(
        run_id, at, store.FAILED,
        COULD_NOT_CARRY.format(attempts=attempts, why=why or "it gave no reason"),
        retained_until(now),
    )
    return {"attempts": attempts, "settled": settled}


def gone_quiet(name: str, where: Path | None = None, now=None,
               after_hours: int | None = None) -> list:
    """Settle every run that has produced nothing for the configured window.

    A run nobody can hear from is not a run that is going to report. Left alone it sits
    `working` until its retention window closes a fortnight later, and the parent that
    handed the work over is told nothing for the whole of it (R-ROL-15).

    Answers the runs this settled, so whatever is still carrying one can let it go.
    """
    kept = agents.records(name, where)
    hours = QUIET_HOURS if after_hours is None else int(after_hours)
    at = store.moment(store.stamped(now))
    quiet_before = store.stamped(lambda: (at - timedelta(hours=hours)).timestamp())
    settled = []
    for row in kept.role_runs_gone_quiet(quiet_before):
        if kept.finish_role(
            row["id"], store.stamped(now), store.FAILED,
            WENT_QUIET.format(seen=_latest_seen(row), hours=hours),
            retained_until(now),
        ):
            settled.append(row["id"])
    return settled


def _latest_seen(row: dict) -> str:
    """When this run was last heard from, as the handoff says it.

    What the records computed, never worked out again here: the moment that decided this
    run had gone quiet and the moment its parent is told about are the same moment.
    """
    return (row.get("latest_activity_at") or row.get("latest_at")
            or row.get("admitted_at") or "an unrecorded moment")


def owed_review(name: str, run_id: str, where: Path | None = None) -> dict:
    """Whether this run's parent has been told, and how often it has been tried.

    Read for a listing rather than for a decision: a review that has been attempted many
    times and never delivered is the shape of a surface that is not coming back, and an
    owner cannot see that anywhere else.
    """
    kept = agents.reading(name, where)
    for one in kept.owed_role_callbacks(limit=kept.OWED_AT_ONCE):
        if one["role_run"] == run_id:
            return {"owed": True, "attempts": int(one["attempts"] or 0)}
    return {"owed": False, "attempts": 0}


def handoff(name: str, run_id: str, where: Path | None = None) -> dict:
    """The one report a named parent reviews, and what is mechanically known beside it.

    Nothing here is read out of the report. What Rundesk knows it knows — which run, whose
    behalf, which role, where it worked, what it cost — and what the worker said stays
    the worker's words (R-ROL-16).
    """
    kept = agents.reading(name, where)
    row = kept.role_run(run_id)
    if row is None:
        raise NotDelegable(f"there is no role run called '{run_id}'")
    # Asked of the column the records keep it in, never found by scanning the newest
    # runs: a busy agent's role turn falls off the end of a scan, and what the handoff
    # would then report is no usage, no files, and nothing verified — silently.
    carried = kept.runs(role_run=run_id, limit=200)
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
        "role_run": row["id"],
        "parent_run": row["parent_run"],
        "parent_agent": name,
        "role": row["role"],
        "outcome": row["outcome"] or row["state"],
        "target": row["target"],
        "report": row["report"] or "",
        "files": [one for one in files if one],
        "usage": tokens,
        "verification_recorded": bool(carried),
    }


def sweep(name: str, where: Path | None = None, now=None) -> list:
    """Take away every execution context whose retention window has passed (R-ROL-12).

    What goes is the bundle and the provider session. What stays is every durable record
    of what was asked, what it cost and what it answered — an owner reading a month-old
    run back still gets the whole account, and only the ability to carry it on is gone.
    """
    kept = agents.records(name, where)
    gone = []
    # One moment for both halves. Read twice, a run could settle against one second and be
    # expired against an earlier one, which is a run finished and never taken away.
    at = store.stamped(now)
    _settle_the_unfinished(kept, at)
    for row in kept.expired_roles(at):
        # A run its gateway never got to finish still stood links in somebody's project.
        unpresent(row.get("target"), paths(name, row["id"], where)["skills"])
        with_it = bundle(name, row["id"], where)
        shutil.rmtree(with_it, ignore_errors=True)
        # The handle as well as the bundle. A session left behind is a run that could be
        # carried on with its locked rules gone, which is the one thing expiry must not
        # leave possible.
        kept.forget_session(store.conversation_id(turn.ROLE, row["id"]))
        gone.append(row["id"])
    _tidy(home(name, where))
    return gone


def _settle_the_unfinished(kept, at: str) -> list:
    """Settle every run reaching the end of its window without ever having finished.

    **Expiry used to be silent.** A run whose gateway died, or whose provider never came
    back, reached day fourteen `working`, had its bundle taken away, and the agent that
    handed the work over was never told anything — the one outcome R-ROL-15 exists to
    make impossible, arriving by the one route nothing was watching.

    Settled *before* the window is applied, so the run is finished with a report and its
    parent is owed a review, and then expires the way a finished one does. Its own
    `retained_until` is kept rather than moved on: this is a run ending, not one being
    given more time.
    """
    settled = []
    for state in store.UNFINISHED_ROLES:
        for row in kept.role_runs(state=state, limit=200):
            if row["retained_until"] > at:
                continue
            if kept.finish_role(row["id"], at, store.FAILED, EXPIRED_UNSETTLED,
                                row["retained_until"]):
                settled.append(row["id"])
    return settled


def _tidy(root: Path) -> None:
    """Clear the debris a crashed assembly leaves, and nothing that is somebody's work."""
    try:
        for one in root.iterdir():
            if one.name.endswith(COMING) and one.is_dir():
                shutil.rmtree(one, ignore_errors=True)
    except OSError:
        return


def shown(row: dict, now=None) -> dict:
    """One role run as a person is shown it — never a local path, never a prompt.

    A listing is read where other people can see it, so what a target directory is called
    is its last component and the private path it stands at is left in the records
    (R-ROL-17).
    """
    began = store.moment(row.get("admitted_at"))
    return {
        "id": row["id"],
        "role": row["role"],
        "label": row["label"],
        "revision": (row.get("revision") or "")[:12],
        "parent_run": row["parent_run"],
        "target": Path(row["target"]).name if row.get("target") else "",
        "state": row["state"],
        "outcome": row.get("outcome") or "",
        "skills": list(row.get("skills") or []),
        "posture": row.get("posture") or provider.WORK,
        # Which brain this run actually ran on, as a person may safely read it: a brain
        # may be the path of a program somebody wrote, and a listing is read where other
        # people can see it (R-ROL-17). Empty for a run admitted before one was recorded,
        # which is the truth about it — nothing wrote down what it ran on.
        "provider": provider.label(row["provider"]) if row.get("provider") else "",
        "model": row.get("model") or "",
        "reviewed": bool(row.get("reviewed_at")),
        "retained_until": row.get("retained_until") or "",
        "elapsed": int(max(0, (now or time.time)() - began.timestamp())) if began else 0,
    }
