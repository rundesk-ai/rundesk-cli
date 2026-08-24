"""Install, update, list, and reconcile version-controlled teams."""

import argparse
import contextlib
import sys
from contextlib import ExitStack
from typing import Iterator, List, NamedTuple, Optional

from rundesk.commands import Subcommands, failed
from rundesk.core import paths
from rundesk.exits import FAILED, OK
from rundesk.skills import catalogs as skill_catalogs
from rundesk.skills import grants, library
from rundesk.teams import catalogs, reconcile
from rundesk.utils import archives, locking

TROUBLE = (catalogs.Refused, reconcile.Refused, skill_catalogs.Refused,
           skill_catalogs.HalfInstalled, library.Refused, grants.Refused, grants.NotPresented,
           grants.HalfCopied, archives.Refused, locking.Stuck, OSError)


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
                    if library.manifest_at(team.name).is_file():
                        moved = skill_catalogs.promoted(team.name, coming, validating=catalogs.read)
                    else:
                        moved = skill_catalogs.installed(coming, as_team=True)
                    try:
                        grants.retired(team.name, moved.retired)
                        installed = catalogs.installed(team.name)
                        changed = reconcile.apply(installed, provider, installing=True)
                    except TROUBLE as why:
                        return _failed(str(why), "the team was not fully installed",
                                       f"retry with: {_update_command(team.name, provider)}")
    except TROUBLE as why:
        if dependencies_installed:
            return _failed(str(why), "the team was not fully installed",
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
            reconcile.preflight(incoming, provider)
            with _prepared_dependencies(incoming, fetching) as dependencies:
                if not confirm:
                    return _would_update(incoming, settled.provenance.source, provider,
                                         dependencies)
                with locking.only_one(paths.lock(), "this install",
                                      locking.WHILE_A_DIRECTORY_MOVES):
                    for dependency in dependencies:
                        if dependency.coming is not None:
                            skill_catalogs.installed(dependency.coming)
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
    command = f"rundesk teams install {source}"
    if provider:
        command += f" --provider {provider}"
    print(f"        {command} --confirm", file=sys.stderr)
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


def _failed(*why: str) -> int:
    return failed("teams", *why)
