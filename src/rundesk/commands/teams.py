"""Install, update, list, and reconcile version-controlled teams."""

import argparse
import contextlib
import sys
from contextlib import ExitStack
from typing import Callable, Iterator, List, NamedTuple, Optional, Protocol, Tuple

from rundesk.agents import directory
from rundesk.commands import Subcommands, failed
from rundesk.core import paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job, standing
from rundesk.skills import catalogs as skill_catalogs
from rundesk.skills import grants, library
from rundesk.teams import catalogs, reconcile, restoring
from rundesk.utils import archives, locking

#: Everything a team operation may meet and report rather than raise through. `reconcile.TROUBLE`
#: is folded in whole rather than restated: reconciliation is called from here, so anything it
#: answers with is something a caller of this module has to be able to name. Listed by hand, the
#: two drifted — `records.Unreadable` from one corrupt member escaped a per-team guard, took the
#: whole daily update down with it, and left the teams after it unchecked.
TROUBLE = (catalogs.Refused, reconcile.Refused, restoring.Refused, skill_catalogs.Refused,
           skill_catalogs.HalfInstalled, library.Refused, grants.Refused, grants.NotPresented,
           grants.HalfCopied, archives.Refused, locking.Stuck, OSError, *reconcile.TROUBLE)


class Gateways(Protocol):
    """Stand one member gateway down and restore it after team reconciliation."""

    def down(self, name: str) -> str:
        """Return why the gateway could not be stopped, or an empty string."""

    def up(self, name: str) -> str:
        """Return why the gateway could not be restored, or an empty string."""


class DependencyPlan(NamedTuple):
    dependency: catalogs.Dependency
    coming: Optional[skill_catalogs.Coming]


def register(sub: Subcommands) -> None:
    said = sub.add_parser("teams", help="version-controlled agent teams")
    what = said.add_subparsers(dest="what", metavar="<what>")
    what.add_parser("list", help="every installed team and its members")

    new = what.add_parser("install", help="install a team catalog and its stopped agents")
    new.add_argument("repository", metavar="<repository>",
                     help="a GitHub repository URL, or a directory on this machine")
    new.add_argument("--provider", metavar="<provider>", default=None,
                     help="provider for the new team members")
    new.add_argument("--confirm", action="store_true",
                     help="required — without it, nothing is installed or changed")

    moved = what.add_parser("update", help="update and reconcile an installed team")
    moved.add_argument("team", metavar="<team>", help="which installed team to update")
    moved.add_argument("--provider", metavar="<provider>", default=None,
                       help="provider for newly declared members")
    moved.add_argument("--confirm", action="store_true",
                       help="required — without it, nothing is changed")


def cmd_teams(args: argparse.Namespace,
              fetching: Optional[skill_catalogs.Fetching] = None) -> int:
    what = getattr(args, "what", None)
    if what in (None, "list"):
        return _listed()
    if what == "install":
        return _installed(args.repository, args.provider, args.confirm, fetching)
    if what == "update":
        return _updated(args.team, args.provider, args.confirm, fetching)
    raise AssertionError(f"teams {what} is registered on the parser and answered by nothing")


def refreshed(fetching: Optional[skill_catalogs.Fetching] = None,
              gateways: Optional[Gateways] = None,
              saying: Optional[Callable[[str], None]] = None) -> List[str]:
    """Refresh and reconcile every installed team independently.

    The caller owns the work-admission barrier. Each fetched declaration is validated before a
    gateway moves, then the catalog swap and all member writes share the install lock with turn
    admission. A failed team does not prevent the remaining teams from settling.
    """
    said = saying or (lambda _line: None)
    failures: List[str] = []
    try:
        names = [name for name in library.known() if library.is_team(name)]
    except TROUBLE as why:
        return [f"the installed teams could not be listed: {why}"]
    for name in names:
        try:
            _refreshed(name, fetching, gateways, said)
        except TROUBLE as why:
            failures.append(f"{name} could not be checked or reconciled: {why}")
    return failures


def _refreshed(name: str, fetching: Optional[skill_catalogs.Fetching],
               gateways: Optional[Gateways], saying: Callable[[str], None]) -> None:
    """Refresh one installed team without exposing a partial member to turn admission.

    Nobody is here to answer a question, so everything this refresh needs is fetched and proved
    before it moves anything: the declaration, the agent names it may govern, and every shared
    catalog it depends on. A dependency that cannot be fetched or does not hold a required skill
    fails while the last working team, its members and their gateways are still untouched.
    """
    settled = library.read(name)
    if settled.provenance is None:
        raise reconcile.Refused(f"nothing is written down about where {name} came from")
    with skill_catalogs.brought(
            settled.provenance.source, settled.provenance.etag, fetching) as coming:
        incoming = (catalogs.installed(name) if coming.at is None or coming.manifest is None
                    else catalogs.read(coming.at, coming.manifest))
        reconcile.preflight_update(incoming)
        with _prepared_dependencies(incoming, fetching) as dependencies:
            stopped: List[str] = []
            failure: Optional[BaseException] = None
            changed: List[str] = []
            cycle = _the_gateways(gateways)
            restart_trouble = ""
            try:
                with locking.only_one(paths.gateway_transition_lock(),
                                      "team member gateways during this update",
                                      locking.WHILE_A_DIRECTORY_MOVES):
                    stopped, stop_trouble = _gateways_stood_down(incoming, cycle)
                    if stop_trouble:
                        failure = reconcile.Refused(stop_trouble)
                    else:
                        try:
                            with locking.only_one(paths.lock(), "this install",
                                                  locking.WHILE_A_DIRECTORY_MOVES):
                                reconcile.preflight_update(incoming)
                                for dependency in dependencies:
                                    if dependency.coming is not None:
                                        skill_catalogs.installed(dependency.coming, saying)
                                with restoring.kept(name, _declared(incoming)):
                                    moved = skill_catalogs.updated(
                                        name, coming, saying, validating=catalogs.read)
                                    grants.retired(name, moved.retired)
                                    changed = reconcile.apply(catalogs.installed(name))
                        except TROUBLE as why:
                            failure = why
            finally:
                # A newly started gateway takes the transition lock before claiming its name.
                # Release this side first while the caller's work-admission barrier still excludes
                # turns.
                restart_trouble = _gateways_started(stopped, cycle)
            if failure is not None:
                if restart_trouble:
                    raise reconcile.Refused(f"{failure}; {restart_trouble}") from failure
                raise failure
            if restart_trouble:
                raise reconcile.Refused(restart_trouble)
    for line in changed:
        saying(line)


def _gateways_stood_down(team: catalogs.Team, gateways: Gateways) -> Tuple[List[str], str]:
    """Stand down exactly the online declared members after proving all can be restored."""
    online: List[str] = []
    for member in team.members:
        how = standing.standing(directory.where(member.name))
        if how.how == standing.CANNOT_TELL:
            raise reconcile.Refused(
                f"nobody can tell whether the gateway for {member.name} is running — {how.why}")
        if how.how == standing.ONLINE:
            try:
                job.job(member.name, directory.where(member.name), paths.home())
            except (directory.Refused, job.Refused, paths.Refused) as why:
                raise reconcile.Refused(
                    f"the gateway for {member.name} is running but cannot be restored ({why})") \
                    from why
            online.append(member.name)

    stopped: List[str] = []
    for name in online:
        trouble = gateways.down(name)
        if trouble:
            return stopped, f"the gateway for {name} would not stand down ({trouble})"
        stopped.append(name)
    return stopped, ""


def _gateways_started(stopped: List[str], gateways: Gateways) -> str:
    """Restore every gateway this team refresh stood down and report all failures."""
    failures = []
    for name in stopped:
        trouble = gateways.up(name)
        if trouble:
            failures.append(f"the gateway for {name} could not be restored ({trouble})")
    return "; ".join(failures)


def _declared(team: catalogs.Team) -> List[str]:
    """The member names an incoming declaration governs, for the state a failure must put back."""
    return [one.name for one in team.members]


def _the_gateways(gateways: Optional[Gateways]) -> Gateways:
    """Resolve the real supervisor only for a production caller that supplied no seam."""
    if gateways is not None:
        return gateways
    from rundesk.commands.gateways import Cycled
    return Cycled(job.Launchd())


def _listed() -> int:
    try:
        teams = [catalogs.installed(name) for name in library.known() if library.is_team(name)]
    except TROUBLE as why:
        return _failed(str(why))
    print(f"teams in {library.where()}")
    if not teams:
        print("        no teams yet — install one with: rundesk teams install <repository>")
        return OK
    for team in teams:
        print(f"        {team.name} — {', '.join(one.name for one in team.members)}")
    return OK


def _installed(source: str, provider: Optional[str], confirm: bool,
               fetching: Optional[skill_catalogs.Fetching]) -> int:
    dependencies_installed: List[str] = []
    try:
        with skill_catalogs.brought(source, "", fetching) as coming:
            if coming.at is None or coming.manifest is None:
                return _failed(f"nothing was fetched from {source}")
            team = catalogs.read(coming.at, coming.manifest)
            reserved = skill_catalogs.reserved(team.name)
            if reserved:
                return _failed(reserved)
            if library.manifest_at(team.name).is_file():
                if library.is_team(team.name):
                    return _failed(f"{team.name} is already installed as a team — update it with: "
                                   f"rundesk teams update {team.name}")
            reconcile.preflight_install(team, provider)
            with _prepared_dependencies(team, fetching) as dependencies:
                if not confirm:
                    return _would_install(team, source, provider, dependencies)
                # One decision from the final clean-name check through dependency, team, and member
                # creation. The dependency fetches remain alive until their trees have landed.
                with locking.only_one(paths.lock(), "this install",
                                      locking.WHILE_A_DIRECTORY_MOVES):
                    reconcile.preflight_install(team, provider)
                    for dependency in dependencies:
                        if dependency.coming is not None:
                            skill_catalogs.installed(dependency.coming)
                            dependencies_installed.append(dependency.dependency.name)
                    # Entered before the catalog arrives, so what it holds is the absence a
                    # failure has to put back: a wholly new catalog is taken away again, and a
                    # skills-only catalog this promotes goes back to being one.
                    with restoring.kept(team.name, _declared(team)):
                        if library.manifest_at(team.name).is_file():
                            moved = skill_catalogs.promoted(team.name, coming,
                                                            validating=catalogs.read)
                        else:
                            moved = skill_catalogs.installed(coming, as_team=True)
                        grants.retired(team.name, moved.retired)
                        installed = catalogs.installed(team.name)
                        changed = reconcile.apply(installed, provider, installing=True)
    except restoring.Refused as why:
        # The one outcome that is neither installed nor undone: recover from what actually remains.
        # `teams update` exists only when the failed restore left a team catalog standing.
        if library.is_team(team.name):
            return _failed(str(why), "the team was not fully installed",
                           f"retry with: {_update_command(team.name, provider)}")
        left = [name for name in _declared(team) if directory.where(name).is_dir()]
        recovery = ["the team was not installed"]
        if left:
            commands = ", ".join(
                f"rundesk agents remove {name} --confirm" for name in left)
            recovery.append(f"remove agents left by the failed install: {commands}")
        if dependencies_installed:
            recovery.append("dependency catalogs installed: " +
                            ", ".join(dependencies_installed))
        recovery.append(f"retry with: {_install_command(source, provider)}")
        return _failed(str(why), *recovery)
    except TROUBLE as why:
        if dependencies_installed:
            return _failed(str(why), "no team was installed",
                           "dependency catalogs installed: " +
                           ", ".join(dependencies_installed),
                           "retry the same confirmed team install")
        return _failed(str(why), "nothing was installed or changed")
    return _completed(installed, changed, "installed")


def _updated(name: str, provider: Optional[str], confirm: bool,
             fetching: Optional[skill_catalogs.Fetching]) -> int:
    try:
        settled = library.read(name)
        if not library.is_team(name):
            return _failed(f"{name} is a skill catalog, not a team")
        if settled.provenance is None:
            return _failed(f"nothing is written down about where {name} came from")
        with skill_catalogs.brought(settled.provenance.source, settled.provenance.etag,
                                    fetching) as coming:
            incoming = (catalogs.installed(name) if coming.at is None or coming.manifest is None
                        else catalogs.read(coming.at, coming.manifest))
            reconcile.preflight_update(incoming, provider)
            with _prepared_dependencies(incoming, fetching) as dependencies:
                if not confirm:
                    return _would_update(incoming, settled.provenance.source, provider,
                                         dependencies)
                # One decision from the ownership re-check through dependency, catalog and member
                # writes. **The lock may not be released at the swap.** Once the new declaration is
                # installed, `catalogs.owners()` maps every name in it to this team, so a
                # same-named agent created in a gap here reads as a member this team already
                # managed and reconciliation adopts it — the exact thing the re-check exists to
                # refuse. Every nested catalog, agent, record and grant write takes this same
                # re-entrant install lock, so holding it across all of them costs nothing.
                with locking.only_one(paths.lock(), "this install",
                                      locking.WHILE_A_DIRECTORY_MOVES):
                    reconcile.preflight_update(incoming, provider)
                    for dependency in dependencies:
                        if dependency.coming is not None:
                            skill_catalogs.installed(dependency.coming)
                    with restoring.kept(name, _declared(incoming)):
                        moved = skill_catalogs.updated(name, coming, validating=catalogs.read)
                        grants.retired(name, moved.retired)
                        installed = catalogs.installed(name)
                        changed = reconcile.apply(installed, provider)
    except TROUBLE as why:
        return _failed(str(why), f"{name} was not fully reconciled",
                       f"retry with: {_update_command(name, provider)}")
    return _completed(installed, changed, "updated")


def _completed(team: catalogs.Team, changed, verb: str) -> int:
    print(f"team {team.name} {verb}")
    for line in changed:
        print(f"        {line}")
    print(f"        agents   {', '.join(one.name for one in team.members)}")
    print("        gateways stopped — start one with: rundesk gateways start <agent>")
    return OK


def _would_install(team: catalogs.Team, source: str, provider: Optional[str],
                   dependencies: List[DependencyPlan]) -> int:
    print(f"install: this would install team {team.name} from {source}", file=sys.stderr)
    _preview_dependencies(team, dependencies)
    _preview_members(team, provider, installing=True)
    print("        nothing was installed or changed. To go ahead:", file=sys.stderr)
    print(f"        {_install_command(source, provider)}", file=sys.stderr)
    return FAILED


def _would_update(team: catalogs.Team, source: str, provider: Optional[str],
                  dependencies: List[DependencyPlan]) -> int:
    print(f"update: this would reconcile team {team.name} from {source}", file=sys.stderr)
    _preview_dependencies(team, dependencies)
    _preview_members(team, provider)
    print("        repair   instructions, memory absence, delegation, upkeep and skill allowlist",
          file=sys.stderr)
    print("        nothing was changed. To go ahead:", file=sys.stderr)
    command = f"rundesk teams update {team.name}"
    if provider:
        command += f" --provider {provider}"
    print(f"        {command} --confirm", file=sys.stderr)
    return FAILED


def _preview_members(team: catalogs.Team, provider: Optional[str], installing: bool = False) -> None:
    absent = set(reconcile.missing(team))
    for member in team.members:
        if installing or member.name in absent:
            action = f"create with provider {provider}"
        else:
            action = "reconcile"
        print(f"        member   {member.name} — {action}", file=sys.stderr)
        allowed = ", ".join(member.skills) or "no optional skills"
        print(f"                 replace AGENTS.md and CLAUDE.md; remove MEMORY.md; "
              f"allow only {allowed} plus Rundesk-required skills; "
              f"weekly upkeep {'on' if member.self_improve else 'off'}; leave gateway stopped",
              file=sys.stderr)
        if member.name not in absent:
            for held in reconcile.retiring(team, member):
                print(f"        revoke   {member.name}: {held.address or held.name} — not allowed",
                      file=sys.stderr)


def _preview_dependencies(team: catalogs.Team, dependencies: List[DependencyPlan]) -> None:
    required = catalogs.required(team)
    for plan in dependencies:
        action = "install" if plan.coming is not None else "reuse installed"
        skills = ", ".join(required[plan.dependency.name]) or "catalog only"
        print(f"        catalog  {plan.dependency.name} — {action} from "
              f"{plan.dependency.source}; require {skills}", file=sys.stderr)


@contextlib.contextmanager
def _prepared_dependencies(team: catalogs.Team,
                           fetching: Optional[skill_catalogs.Fetching]) \
        -> Iterator[List[DependencyPlan]]:
    """Validate every shared catalog before any team or dependency is changed."""
    plans: List[DependencyPlan] = []
    required = catalogs.required(team)
    with ExitStack() as stack:
        for dependency in team.dependencies:
            if library.manifest_at(dependency.name).is_file():
                settled = library.read(dependency.name)
                if library.is_team(dependency.name):
                    raise catalogs.Refused(
                        f"dependency {dependency.name} is installed as a team, not a shared catalog")
                if settled.provenance is None:
                    raise catalogs.Refused(
                        f"dependency {dependency.name} has no recorded source and cannot be reused")
                if settled.provenance.source != dependency.source:
                    raise catalogs.Refused(
                        f"dependency {dependency.name} is installed from "
                        f"{settled.provenance.source}, not {dependency.source}")
                available = set(library.found(library.inside(dependency.name)))
                missing = [skill for skill in required[dependency.name] if skill not in available]
                if missing:
                    raise catalogs.Refused(
                        f"dependency {dependency.name} is missing required skills: "
                        f"{', '.join(missing)} — update that catalog before retrying")
                plans.append(DependencyPlan(dependency, None))
                continue
            coming = stack.enter_context(
                skill_catalogs.brought(dependency.source, "", fetching))
            if coming.at is None or coming.manifest is None:
                raise catalogs.Refused(f"nothing was fetched for dependency {dependency.name}")
            if coming.manifest.name != dependency.name:
                raise catalogs.Refused(
                    f"dependency source {dependency.source} calls itself {coming.manifest.name}, "
                    f"not {dependency.name}")
            missing = [skill for skill in required[dependency.name] if skill not in coming.skills]
            if missing:
                raise catalogs.Refused(
                    f"dependency {dependency.name} does not hold required skills: "
                    f"{', '.join(missing)}")
            plans.append(DependencyPlan(dependency, coming))
        yield plans


def _update_command(name: str, provider: Optional[str]) -> str:
    command = f"rundesk teams update {name}"
    if provider:
        command += f" --provider {provider}"
    return command + " --confirm"


def _install_command(source: str, provider: Optional[str]) -> str:
    command = f"rundesk teams install {source}"
    if provider:
        command += f" --provider {provider}"
    return command + " --confirm"


def _failed(*why: str) -> int:
    return failed("teams", *why)
