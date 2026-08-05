"""Why a skill an agent holds cannot be used, one verdict each.

A listing says what is there. This says what is **broken**, names the one thing to type, and is meant
to be read by an agent as much as by an owner — one fact per line, and each skill's own `about` text
carried through, so a brain understands what the integration is rather than only what its variables
are called.

## A verdict per thing there is to do about it, and no two share one

    READY       every profile is complete, and every command it ships would run
    PARTIAL     at least one profile is usable and at least one is not
    BLOCKED     no profile is usable: a required value is missing everywhere
    UNRUNNABLE  the credentials are fine and a command it ships is not executable
    STALE       a copied grant is behind the catalog it came from
    DANGLING    the grant no longer resolves — its skill left its catalog, or the catalog went
    BROKEN      the skill itself will not load, or what it declares cannot be read

**`PARTIAL` is the verdict multi-profile exists for.** Two working Jira sites and one
half-configured is neither a broken integration nor a healthy one. A diagnosis that collapsed it
either way would cry wolf on a working setup, or hide the site that fails at three in the morning —
and the second is the one that costs somebody a night.

`STALE` and `DANGLING` are kept apart for the same kind of reason: one is repaired by running
`rundesk update` and the other by revoking a grant, and telling somebody the wrong one sends them to
a command that cannot help.

## Nothing here reads a value and nothing here runs a program

Whether a credential is set is asked of `secrets.placed`, which answers yes or no. Whether a script
can run is decided from what the skill declares and what is on the disk. A diagnosis that had to
start somebody's program to find out would be a diagnosis nobody could run on a machine they were
worried about.

## It composes and it decides nothing new

Everything here is `grants`, `library` and `needs` put together. A verdict is product knowledge and
belongs a layer below the words a person reads, but no fact in it is discovered here — which is why
this module is short and why nothing else has to change when a rule does.
"""

from typing import List, NamedTuple, Optional

from rundesk.agents import directory
from rundesk.skills import grants, needs

#: Every profile is complete. The only verdict that is not something to do.
READY = "READY"

#: Some profiles are usable and some are not — the case three accounts of one thing produces.
PARTIAL = "PARTIAL"

#: No profile is usable. The skill is granted and cannot do the thing it was granted for.
BLOCKED = "BLOCKED"

#: A copied grant is behind the catalog it came from. Repaired by `rundesk update`.
STALE = "STALE"

#: The grant points at nothing. Its skill left its catalog, or the catalog was removed.
DANGLING = "DANGLING"

#: Every credential is in place and a command the skill ships will not run. Its own verdict because
#: the fix is its own action — `chmod +x`, and nothing to do with a value being missing.
UNRUNNABLE = "UNRUNNABLE"

#: What is wrong with the skill itself — its `SKILL.md` or what it declares. Rare, and it means a
#: catalog changed under an install in a way that would have been refused on the way in.
BROKEN = "BROKEN"

#: Which verdicts mean somebody has something to do. `PARTIAL` is among them deliberately: a
#: half-configured account is a thing to fix, and a check that exited zero on one is a check
#: nobody can gate on.
TROUBLE = (PARTIAL, BLOCKED, UNRUNNABLE, STALE, DANGLING, BROKEN)


class Finding(NamedTuple):
    """One skill one agent holds, and what is wrong with it.

    `about` maps each missing environment variable to why the skill needs it — carried so that a
    diagnosis explains the integration rather than reciting variable names, which is what makes this
    readable by an agent that has never seen the skill.

    `fix` is the exact command to type. One per finding, because a diagnosis whose reader has to
    work out what to do next is a diagnosis that gets read once.
    """

    agent: str
    skill: str
    catalog: str
    aliased: bool
    verdict: str
    said: str
    profiles: List[needs.Profile]
    about: dict
    fix: str

    @property
    def trouble(self) -> bool:
        """Whether this is something somebody has to do."""
        return self.verdict in TROUBLE


def of(grant: grants.Grant) -> Finding:
    """What is wrong with one grant, on its own.

    Public because a listing wants the same verdict a diagnosis gives, in one line rather than in
    several. Two answers to "how does this skill stand" is one of them being wrong eventually, so a
    table and a diagnosis read the same fact.
    """
    return _verdict(grant)


def looked_at(agent: str) -> List[Finding]:
    """Every skill this agent holds, and what is wrong with each. In the order they stand."""
    return [_verdict(one) for one in grants.held(agent)]


def looked_over(agent: Optional[str] = None) -> List[Finding]:
    """Every agent's skills, or one agent's. In agent order, then in the order they stand.

    An install with no agents, or an agent holding nothing, answers an empty list — that is not a
    discovery that found nothing, it is a machine nobody has finished setting up, which is ordinary
    and is the caller's to word.
    """
    if agent is not None:
        return looked_at(agent)
    return [one for name in directory.known() for one in looked_at(name)]


def counted(findings: List[Finding]) -> List[Finding]:
    """Only the findings somebody has to do something about, in the order they were found."""
    return [one for one in findings if one.trouble]


def fixes(findings: List[Finding]) -> List[str]:
    """Every command worth typing, once each, in the order they were first needed.

    Deduplicated because one missing value can block the same skill for six agents, and six
    identical lines is a list somebody stops reading. In the order they came rather than sorted, so
    the first thing named is the first thing wrong.
    """
    settled: List[str] = []
    for one in findings:
        if one.fix and one.fix not in settled:
            settled.append(one.fix)
    return settled


def _verdict(grant: grants.Grant) -> Finding:
    """What is wrong with one grant.

    The order the questions are asked in is the answer to "which of several true things do I say".
    A grant that points at nothing has no skill to read, so nothing below could be asked of it; a
    skill that will not load cannot usefully be told its credentials are missing. Each check
    therefore stands on the one above it, and the first that fires is the one worth saying.
    """
    if not grant.resolves:
        return _finding(grant, DANGLING, "the grant points at nothing",
                        fix=f"rundesk skills revoke {grant.agent} {grant.name}")

    trouble = needs.env_trouble(grant.at)
    if trouble:
        return _finding(grant, BROKEN, trouble,
                        fix=f"rundesk skills update {grant.catalog}" if grant.catalog else "")

    if grants.stale(grant):
        return _finding(grant, STALE,
                        f"the copy is behind {grant.catalog} and has not been made again",
                        fix="rundesk update")

    declared = needs.declared(grant.at)
    # Walked once. `needs.started` and `needs.usable` each call `needs.every` themselves, so asking
    # all three meant three passes over the same profile set — and every pass asks the credential
    # store whether each name is placed.
    every = needs.every(declared)
    started = [one for one in every if one.exists]
    usable = [one for one in started if one.whole]
    about = needs.about(declared)

    if declared and not usable:
        return _finding(grant, BLOCKED, "no profile is usable", every, about,
                        _configured(grant, started))
    if len(usable) < len(started):
        return _finding(grant, PARTIAL,
                        f"{len(usable)} of {len(started)} profiles are usable", every, about,
                        _configured(grant, started))

    # Asked last, because a missing credential is the more urgent of the two and naming both at once
    # would bury it. Asked at all because to an agent a script that is present and not executable
    # looks exactly like one that works, right up until it tries — and reporting it beside a `READY`
    # verdict, which is what an earlier version did, is a warning nothing can gate on.
    stuck = [one for one in needs.ships(grant.at) if not one.runnable]
    if stuck:
        # **The real file, not the path through the grant.** An ordinary grant is a link, so the
        # path this walked names the file by way of the agent holding it — and `chmod` through a link
        # works, so it would be a correct command. It would also be a *different* correct command per
        # agent, so six agents holding one skill print six lines for one file and the deduplication
        # in `fixes` cannot see they are the same. Resolving lands on the library, or on the copy
        # itself when the grant is one.
        return _finding(grant, UNRUNNABLE,
                        f"{', '.join(one.shown for one in stuck)} cannot be run as it stands",
                        every, about, f"chmod +x {stuck[0].at.resolve()}")
    return _finding(grant, READY,
                    _said_of(usable, grant) if declared else "needs nothing", every, about)


def _finding(grant: grants.Grant, verdict: str, said: str,
             profiles: Optional[List[needs.Profile]] = None,
             about: Optional[dict] = None, fix: str = "") -> Finding:
    """One finding, with the parts every verdict shares filled in the same way each time."""
    return Finding(grant.agent, grant.name, grant.catalog, grant.copied, verdict, said,
                   profiles or [], about or {}, fix)


def _configured(grant: grants.Grant, started: List[needs.Profile]) -> str:
    """The command that finishes the first profile that is not finished, or starts the default.

    Names one rather than all of them. A person fixes one thing and runs this again, and a list of
    four commands is a list where the second is typed against a machine the first has changed.
    """
    if not grant.address:
        return ""
    unfinished = next((one for one in started if not one.whole), None)
    where = f" --profile {unfinished.shown}" if unfinished and unfinished.name else ""
    return f"rundesk skills configure {grant.address}{where}"


def _said_of(usable: List[needs.Profile], grant: grants.Grant) -> str:
    """What a working skill's line says: how many accounts it has, and what they are called."""
    named = [one.shown for one in usable if one.name]
    if not named:
        return "one profile"
    return (f"{len(named)} profile{'s' if len(named) > 1 else ''}: " + ", ".join(named))


def readable(finding: Finding) -> List[str]:
    """A finding as the lines a person or an agent reads under it, without the heading.

    Here rather than in `commands` because the *shape* of an explanation is part of the diagnosis —
    which profile, which value, and what that value is for, in that order, because that is the
    order somebody needs them to act. `commands` decides the words around it and the columns.
    """
    if finding.verdict in (DANGLING, STALE, BROKEN, UNRUNNABLE):
        # Nothing. The whole story of these four *is* the summary sentence, and a caller prints that
        # already — returning it again put it out twice, once as the row and once indented beneath
        # itself. Only the verdicts with a per-profile breakdown have detail worth adding.
        return []

    # The profiles somebody has begun, and — when nobody has begun any — the default, so a skill
    # nothing has been set up for still says what setting it up would take. `every` puts the default
    # first, which is what makes that slice the right one.
    shown = [one for one in finding.profiles if one.exists] or finding.profiles[:1]

    lines = []
    for one in shown:
        if one.whole:
            lines.append(f"{one.shown}  ready")
            continue
        lines.append(f"{one.shown}  {'INCOMPLETE' if one.exists else 'not set'}")
        for env in one.missing:
            # The reason, every time, on the line with the name it belongs to. Without it this is a
            # list of variable names, and a brain reading a list of variable names knows no more
            # about the integration than it did before.
            reason = finding.about.get(env.split(needs.BETWEEN)[0], "")
            lines.append(f"    {env}" + (f" — {reason}" if reason else ""))
    return lines


def where(finding: Finding) -> str:
    """Which catalog a finding's skill came from, as a listing shows it."""
    return grants.source_shown(finding.catalog, finding.aliased)
