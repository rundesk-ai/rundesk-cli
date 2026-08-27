"""Make installed team declarations true of their named agents.

Provider choice remains local. Team content owns role instructions, memory absence, description,
delegation scope, and the grants its own declaration names.

**A member's ``skills`` array is the set of grants this team manages, not everything that member
may hold.** Reconciliation compares the previously installed declaration with the incoming one: a
grant this team declared and no longer declares is taken away, a declared grant that is absent is
put back, and every other grant is left exactly where it stands. That is what lets an owner give
one specialist an extra skill without the next team update quietly removing it, and it is why the
comparison is against the *previous declaration* rather than against whatever the member holds —
"not declared" and "not this team's" are different facts, and only the first one is this
lifecycle's to act on.
"""

from typing import List, Optional

from rundesk.agents import delegating, directory, pages, records
from rundesk.skills import grants, library
from rundesk.teams import catalogs, restoring
from rundesk.utils import locking


class Refused(Exception):
    """A team cannot be reconciled safely or completely."""


TROUBLE = (catalogs.Refused, delegating.Refused, directory.Refused, records.NotThere,
           records.Unreadable, records.Refused, library.Refused, grants.Refused,
           grants.NotPresented, grants.HalfCopied, locking.Stuck, OSError, UnicodeError)


def missing(team: catalogs.Team) -> List[str]:
    known = set(directory.known())
    return [one.name for one in team.members if one.name not in known]


def preflight(team: catalogs.Team, provider: Optional[str] = None,
              previous: Optional[catalogs.Team] = None) -> None:
    """Prove ownership, provider availability, and grant-name collisions before changing agents.

    `previous` is the declaration installed before this one, and is what tells a grant this team
    is about to stop managing from a grant that was never this team's. Absent, every held grant
    outside the incoming declaration reads as somebody else's — which is the right answer for an
    install, where no member may exist yet.
    """
    owners = catalogs.owners()
    for one in team.members:
        owner = owners.get(one.name)
        if owner is not None and owner != team.name:
            raise Refused(f"{one.name} is already managed by team {owner}")
    absent = missing(team)
    if absent and (provider is None or not provider.strip()):
        raise Refused("a provider is required for new team members " + ", ".join(absent) +
                      " — add --provider <provider>")
    occupied = occupying(team, previous)
    if occupied:
        raise Refused("; ".join(occupied))


def preflight_install(team: catalogs.Team, provider: Optional[str] = None) -> None:
    """Require every member to begin as a new agent owned by this team."""
    known = set(directory.known())
    existing = [one.name for one in team.members if one.name in known]
    if existing:
        removals = ", ".join(
            f"{name} (rundesk agents remove {name} --confirm)" for name in existing)
        raise Refused("existing team members must be removed before installing this team: " +
                      removals)
    preflight(team, provider)


def preflight_update(team: catalogs.Team, provider: Optional[str] = None,
                     previous: Optional[catalogs.Team] = None) -> None:
    """Prove an update may govern every declared member before anything moves.

    `preflight_install` refuses every existing name so each member starts from catalog-owned
    content. An update has to make the same promise about the names it does not already own: a
    later catalog version naming an agent no team manages would otherwise be reconciled like a
    member, replacing its instructions, removing its memory, and rewriting its description,
    delegation scope and grants that nobody asked it to hand over.

    Read against ownership as it stands *before* the catalog swap, which is the only moment the
    distinction exists — afterwards the newly declared name is this team's own member.

    Every existing member's records are read here as well, and its pages are asked whether they
    could be put back, because reconciliation cannot finish without the one and cannot undo itself
    without the other. Left to `apply`, an unreadable set of records answered part-way through the
    member loop, with the catalog already replaced and some members moved to it — so both
    deterministic prerequisites are asked while nothing has moved yet, ahead of the gateways.

    `restoring` owns the page rule and is asked for it rather than repeating it, and asks it again
    itself under the install lock; between the two answers, the lock is what holds the shape of
    those paths still.

    `previous` is read here too, before the catalog swap, because afterwards it is gone: once the
    incoming declaration is installed there is nothing left to say which grants this team used to
    manage, and a name collision would be met with the member's pages and records already moved.
    """
    preflight(team, provider, previous)
    owners = catalogs.owners()
    known = set(directory.known())
    taken = [one.name for one in team.members if one.name in known and one.name not in owners]
    if taken:
        removals = ", ".join(
            f"{name} (rundesk agents remove {name} --confirm)" for name in taken)
        raise Refused(f"{team.name} declares agents no team manages and this update will not take "
                      "them over: " + removals)
    for one in team.members:
        if one.name not in known:
            continue
        try:
            records.read(directory.records(one.name))
        except TROUBLE as why:
            raise Refused(f"{one.name}'s records cannot be read, so {team.name} cannot be "
                          f"reconciled ({why})") from why
        trouble = restoring.page_trouble(one.name)
        if trouble:
            raise Refused(f"{team.name} cannot be reconciled: {trouble}")


def managed(team: Optional[catalogs.Team], name: str) -> List[str]:
    """The skill addresses a declaration manages for one member, and none for a name it omits."""
    if team is None:
        return []
    return next((one.skills for one in team.members if one.name == name), [])


def retiring(previous: Optional[catalogs.Team], one: catalogs.Member) -> List[grants.Grant]:
    """The exact team-managed grants the incoming declaration for this member no longer names.

    Matched on the installed name **and** the full address. A copy somebody made with `--as` from
    the same catalog skill stands under a name no declaration ever asked for, so it is not this
    team's to take away; a grant from another catalog under the same name was never declared here
    either, and reaching for it is what turned a declaration into an allowlist over everything the
    member held.
    """
    obsolete = set(managed(previous, one.name)) - set(one.skills)
    return [held for held in grants.held(one.name)
            if held.address in obsolete and held.name == held.skill]


def occupying(team: catalogs.Team, previous: Optional[catalogs.Team]) -> List[str]:
    """Every user-managed grant standing where this declaration needs a name, and the way out.

    Read before anything moves, because the answer is a refusal rather than a revocation: a grant
    this team never declared belongs to whoever made it, and reconciliation may not take its name.
    An alias is the recovery and the sentence names it, so nobody has to work out that `--as`
    exists from a failure that already happened.

    The conditional delegation grant is asked about on the same terms. Rundesk's own
    `delegating-work` has to stand under that exact name for a member that may delegate, and
    `grants` deliberately never replaces a name somebody else filled — so a declaration that turns
    an inbound-only member outbound while a different `delegating-work` occupies the name would
    otherwise report a member reconciled that cannot delegate at all. While the member stays
    inbound-only Rundesk needs no grant there and the custom one is simply left alone.
    """
    known = set(directory.known())
    trouble: List[str] = []
    for one in team.members:
        if one.name not in known:
            continue
        leaving = {held.at for held in retiring(previous, one)}
        for address in one.skills:
            standing = grants.holding(one.name, address.split("/", 1)[1])
            if standing is None or standing.address == address or standing.at in leaving:
                continue
            trouble.append(_occupied(
                one.name, standing, f"{team.name} declares {address} for {one.name}"))
        if one.delegates_to:
            standing = grants.holding(one.name, library.DELEGATING_SKILL)
            if standing is not None and standing.address != library.DELEGATING:
                trouble.append(_occupied(
                    one.name, standing,
                    f"{team.name} lets {one.name} delegate by name, which needs Rundesk's own "
                    f"{library.DELEGATING}"))
    return trouble


def _occupied(agent: str, standing: grants.Grant, why: str) -> str:
    """One collision and the two ways out of it, worded once for every caller that refuses."""
    keeping = (f"keep it under another name (rundesk skills grant {agent} {standing.address} "
               "--as <name>)" if standing.address else "grant it again under another name")
    return (f"{why}, and {agent} already holds {standing.address or standing.name} under that "
            f"name — revoke it (rundesk skills revoke {agent} {standing.name}) or {keeping}, "
            "then retry")


def apply(team: catalogs.Team, provider: Optional[str] = None,
          installing: bool = False, previous: Optional[catalogs.Team] = None) -> List[str]:
    """Reconcile every member and return concise evidence lines. Safe to run repeatedly.

    `previous` is the declaration this one replaces, read before the catalog swap. An install
    passes none, and needs none: `preflight_install` has already refused every existing name, so
    each member begins holding nothing but what this declaration gives it.
    """
    if installing:
        preflight_install(team, provider)
    else:
        preflight(team, provider, previous)
    known = set(directory.known())
    changed: List[str] = []
    for one in team.members:
        if one.name not in known:
            directory.made(one.name, provider or "", one.description)
            known.add(one.name)
            changed.append(f"{one.name}: agent created with provider {provider}")

    for one in team.members:
        changed.extend(_member(team, one, previous))
        changed.extend(grants.required_reconciled(one.name))
    return changed


def current(agent: str) -> List[str]:
    """Repair one managed member from installed data immediately before a turn is admitted."""
    try:
        owner = catalogs.owners().get(agent)
        if owner is None:
            return []
        team = catalogs.installed(owner)
        one = next(member for member in team.members if member.name == agent)
        # The installed declaration is both what is wanted and what was last applied, so nothing
        # is obsolete and nothing is taken away: this repairs the grants it manages and leaves
        # every other grant the member holds exactly as it is.
        preflight(team, previous=team)
        changed = _member(team, one, team)
        changed.extend(grants.required_reconciled(one.name))
        return changed
    except Refused:
        raise
    except TROUBLE as why:
        raise Refused(f"{agent}'s installed team state could not be reconciled ({why})") from why


def _member(team: catalogs.Team, one: catalogs.Member,
            previous: Optional[catalogs.Team]) -> List[str]:
    """Reconcile one existing member. The caller has proved the whole team first."""
    changed: List[str] = []
    text = (team.at / one.instructions).read_text(encoding="utf-8")
    page_changes = pages.replace_team(directory.home(one.name), text)
    if page_changes:
        changed.append(f"{one.name}: instructions and memory policy reconciled")

    scope = delegating.configured(one.name, one.delegates_to)
    wanted_scope = delegating.encoded(scope)
    settled = records.read(directory.records(one.name))
    moving = {}
    if settled.get("describes") != one.description:
        moving["describes"] = one.description
    if settled.get("delegates_to") != wanted_scope:
        moving["delegates_to"] = wanted_scope
    if bool(settled.get("self_improve")) != one.self_improve:
        moving["self_improve"] = int(one.self_improve)
    if moving:
        records.stated(directory.records(one.name), moving)
        changed.append(f"{one.name}: description, delegation and upkeep reconciled")

    for held in retiring(previous, one):
        grants.revoked(one.name, held.name)
        changed.append(f"{one.name}: revoked {held.address or held.name}")
    for address in one.skills:
        standing = grants.holding(one.name, address.split("/", 1)[1])
        if standing is not None and standing.address != address:
            # `preflight` refuses this while nothing has moved. Reaching it here means the name was
            # taken under the install lock, and taking it back is still not this lifecycle's to do.
            raise Refused(_occupied(
                one.name, standing, f"{team.name} declares {address} for {one.name}"))
        if standing is None:
            grants.granted(one.name, library.look_up(address))
            changed.append(f"{one.name}: granted {address}")
    return changed
