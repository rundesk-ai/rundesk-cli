"""Install, update, list, and reconcile version-controlled teams.

Fetching and gateway supervision arrive as collaborators so the complete lifecycle is testable
without network access or touching the owner's login session.
"""

import argparse
import os
import sys
from typing import Optional, Protocol

from rundesk.commands import Subcommands, failed
from rundesk.exits import FAILED, OK
from rundesk.gateways import job
from rundesk.providers import environment
from rundesk.skills import catalogs as skill_catalogs
from rundesk.skills import grants, library
from rundesk.teams import catalogs, reconcile
from rundesk.utils import archives, locking


class Gateways(Protocol):
    def up(self, name: str) -> str:
        ...


TROUBLE = (catalogs.Refused, reconcile.Refused, skill_catalogs.Refused,
           skill_catalogs.HalfInstalled, library.Refused, grants.Refused, grants.NotPresented,
           grants.HalfCopied, archives.Refused, locking.Stuck, OSError)


def register(sub: Subcommands) -> None:
    said = sub.add_parser("teams", help="version-controlled agent teams")
    what = said.add_subparsers(dest="what", metavar="<what>")
    what.add_parser("list", help="every installed team and its members")

    new = what.add_parser("install", help="install and activate a team catalog")
    new.add_argument("repository", metavar="<repository>",
                     help="a GitHub repository URL, or a directory on this machine")
    new.add_argument("--provider", metavar="<provider>", default=None,
                     help="provider for members that do not exist on this install")
    new.add_argument("--confirm", action="store_true",
                     help="required — without it, nothing is installed or changed")

    moved = what.add_parser("update", help="update and reconcile an installed team")
    moved.add_argument("team", metavar="<team>", help="which installed team to update")
    moved.add_argument("--provider", metavar="<provider>", default=None,
                       help="provider for newly declared members")
    moved.add_argument("--confirm", action="store_true",
                       help="required — without it, nothing is changed")


def cmd_teams(args: argparse.Namespace, gateways: Gateways,
              fetching: Optional[skill_catalogs.Fetching] = None) -> int:
    what = getattr(args, "what", None)
    if what in ("install", "update") and args.confirm and os.environ.get(environment.AGENT):
        return _failed("a team catalog cannot install or update itself from inside an agent turn — "
                       "an owner must review and apply it from a terminal",
                       "nothing was installed or changed")
    if what in (None, "list"):
        return _listed()
    if what == "install":
        return _installed(args.repository, args.provider, args.confirm, gateways, fetching)
    if what == "update":
        return _updated(args.team, args.provider, args.confirm, gateways, fetching)
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


def _installed(source: str, provider: Optional[str], confirm: bool, gateways: Gateways,
               fetching: Optional[skill_catalogs.Fetching]) -> int:
    try:
        with skill_catalogs.brought(source, "", fetching) as coming:
            if coming.at is None or coming.manifest is None:
                return _failed(f"nothing was fetched from {source}")
            team = catalogs.read(coming.at, coming.manifest)
            _gateway_names_are_usable(team)
            reserved = skill_catalogs.reserved(team.name)
            if reserved:
                return _failed(reserved)
            reconcile.preflight(team, provider)
            if not confirm:
                return _would_install(team, source, provider)
            skill_catalogs.installed(coming)
    except TROUBLE as why:
        return _failed(str(why), "nothing was installed or changed")
    try:
        installed = catalogs.installed(team.name)
        changed = reconcile.apply(installed, provider)
    except TROUBLE as why:
        return _failed(str(why), "the team was not fully installed",
                       f"retry with: {_update_command(team.name, provider)}")
    return _activated(installed, changed, gateways, "installed")


def _updated(name: str, provider: Optional[str], confirm: bool, gateways: Gateways,
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
            _gateway_names_are_usable(incoming)
            reconcile.preflight(incoming, provider)
            if not confirm:
                return _would_update(incoming, settled.provenance.source, provider)
            moved = skill_catalogs.updated(name, coming, validating=catalogs.read)
            grants.retired(name, moved.retired)
        installed = catalogs.installed(name)
        changed = reconcile.apply(installed, provider)
    except TROUBLE as why:
        return _failed(str(why), f"{name} was not fully reconciled",
                       f"retry with: {_update_command(name, provider)}")
    return _activated(installed, changed, gateways, "updated")


def _activated(team: catalogs.Team, changed, gateways: Gateways, verb: str) -> int:
    failed_gateways = []
    print(f"team {team.name} {verb}")
    for line in changed:
        print(f"        {line}")
    for member in team.members:
        trouble = gateways.up(member.name)
        if trouble:
            failed_gateways.append(f"{member.name}: {trouble}")
    if failed_gateways:
        for why in failed_gateways:
            print(f"        gateway not active — {why}", file=sys.stderr)
        print(f"        retry with: rundesk teams update {team.name} --confirm", file=sys.stderr)
        return FAILED
    print(f"        active   {', '.join(one.name for one in team.members)}")
    return OK


def _would_install(team: catalogs.Team, source: str, provider: Optional[str]) -> int:
    print(f"install: this would install team {team.name} from {source}", file=sys.stderr)
    _preview_members(team, provider)
    print("        nothing was installed or changed. To go ahead:", file=sys.stderr)
    command = f"rundesk teams install {source}"
    if provider:
        command += f" --provider {provider}"
    print(f"        {command} --confirm", file=sys.stderr)
    return FAILED


def _would_update(team: catalogs.Team, source: str, provider: Optional[str]) -> int:
    print(f"update: this would reconcile team {team.name} from {source}", file=sys.stderr)
    _preview_members(team, provider)
    print("        repair   canonical instructions, memory absence, delegation and skill allowlist",
          file=sys.stderr)
    print("        nothing was changed. To go ahead:", file=sys.stderr)
    command = f"rundesk teams update {team.name}"
    if provider:
        command += f" --provider {provider}"
    print(f"        {command} --confirm", file=sys.stderr)
    return FAILED


def _preview_members(team: catalogs.Team, provider: Optional[str]) -> None:
    absent = set(reconcile.missing(team))
    for member in team.members:
        action = f"create with provider {provider}" if member.name in absent else "adopt/reconcile"
        print(f"        member   {member.name} — {action}", file=sys.stderr)
        allowed = ", ".join(member.skills) or "no optional skills"
        print(f"                 replace AGENTS.md and CLAUDE.md; remove MEMORY.md; "
              f"allow only {allowed} plus Rundesk-required skills; "
              "activate gateway", file=sys.stderr)
        if member.name not in absent:
            for held in reconcile.retiring(team, member):
                print(f"        revoke   {member.name}: {held.address or held.name} — not allowed",
                      file=sys.stderr)


def _gateway_names_are_usable(team: catalogs.Team) -> None:
    """Refuse a member whose name cannot have the supervised gateway a team promises."""
    for member in team.members:
        trouble = job.name_trouble(member.name)
        if trouble:
            raise catalogs.Refused(f"{member.name} cannot be a supervised team member: {trouble}")


def _update_command(name: str, provider: Optional[str]) -> str:
    command = f"rundesk teams update {name}"
    if provider:
        command += f" --provider {provider}"
    return command + " --confirm"


def _failed(*why: str) -> int:
    return failed("teams", *why)
