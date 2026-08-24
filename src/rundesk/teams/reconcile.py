"""Make installed team declarations true of their named agents.

Provider choice remains local. Team content owns role instructions, memory absence, description,
delegation scope, and the exact optional skill allowlist.
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


def preflight(team: catalogs.Team, provider: Optional[str] = None) -> None:
    """Prove ownership, provider availability, and skill-name collisions before changing agents."""
    owners = catalogs.owners()
    for one in team.members:
        owner = owners.get(one.name)
        if owner is not None and owner != team.name:
            raise Refused(f"{one.name} is already managed by team {owner}")
    absent = missing(team)
    if absent and (provider is None or not provider.strip()):
        raise Refused("a provider is required for new team members " + ", ".join(absent) +
                      " — add --provider <provider>")


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


def preflight_update(team: catalogs.Team, provider: Optional[str] = None) -> None:
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
    """
    preflight(team, provider)
    managed = catalogs.owners()
    known = set(directory.known())
    taken = [one.name for one in team.members if one.name in known and one.name not in managed]
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


def retiring(team: catalogs.Team, one: catalogs.Member) -> List[grants.Grant]:
    """Every current grant outside this member's positive allowlist, excluding product grants."""
    desired = set(one.skills)
    return [held for held in grants.held(one.name)
            if held.address not in desired
            and held.name != library.REQUIRED_SKILL
            and not (held.name == library.DELEGATING_SKILL
                     and held.address == library.DELEGATING)]


def apply(team: catalogs.Team, provider: Optional[str] = None,
          installing: bool = False) -> List[str]:
    """Reconcile every member and return concise evidence lines. Safe to run repeatedly."""
    if installing:
        preflight_install(team, provider)
    else:
        preflight(team, provider)
    known = set(directory.known())
    changed: List[str] = []
    for one in team.members:
        if one.name not in known:
            directory.made(one.name, provider or "", one.description)
            known.add(one.name)
            changed.append(f"{one.name}: agent created with provider {provider}")

    for one in team.members:
        changed.extend(_member(team, one))
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
        preflight(team)
        changed = _member(team, one)
        changed.extend(grants.required_reconciled(one.name))
        return changed
    except Refused:
        raise
    except TROUBLE as why:
        raise Refused(f"{agent}'s installed team state could not be reconciled ({why})") from why


def _member(team: catalogs.Team, one: catalogs.Member) -> List[str]:
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

    for held in retiring(team, one):
        grants.revoked(one.name, held.name)
        changed.append(f"{one.name}: revoked {held.address or held.name}")
    for address in one.skills:
        skill_name = address.split("/", 1)[1]
        holding = grants.holding(one.name, skill_name)
        if holding is not None and holding.address != address:
            grants.revoked(one.name, skill_name)
            changed.append(f"{one.name}: revoked {holding.address or holding.name}")
            holding = None
        if holding is None:
            grants.granted(one.name, library.look_up(address))
            changed.append(f"{one.name}: granted {address}")
    return changed
