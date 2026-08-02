"""What an owner's agents may reach for: the skill library, its catalogs, and the scripts.

A grant is a link standing in the agent's own `skills/` before the brain runs, never a record
of one — so everything here is about what is *placed*, and `skill.py` and `catalog.py` below do
the placing. `scripts` is here rather than in a module of its own because it answers the same
question from the other side: what an owner has put within reach of every program rundesk runs.
"""

from __future__ import annotations

import argparse
import contextlib
import sys

from rundesk import config
from rundesk import role
from rundesk import standing
from rundesk.commands import _as_table


def _all_granted_skills(agents, skills) -> set[str]:
    """Every skill at least one agent holds, asked from the links that are the grants."""
    return {
        called
        for name in agents.known()
        for called in skills.granted(agents.skills(name))
    }


@contextlib.contextmanager
def _retiring_catalog_grants(agents, skills, gateways, catalogs, names, retired):
    """Revoke catalog skills only while every affected agent is proven stopped.

    The gateway holds stay open across the catalog mutation. If that mutation fails,
    restore every grant while the old catalog package is available again.
    """
    with skills.changing_grants(skills.home()):
        affected = []
        for name in agents.known():
            mine = agents.skills(name)
            held = [
                called for called in sorted(set(names).intersection(skills.granted(mine)))
                if skills.ours(mine / called, skills.home())
            ]
            affected.append((name, held))
        affected = [(name, held) for name, held in affected if held]
        revoked = []
        with contextlib.ExitStack() as locks:
            for name, _ in affected:
                stopped = locks.enter_context(
                    gateways.holding(name, agents.resolved(name).run)
                )
                if not stopped:
                    raise catalogs.InUse(
                        f"cannot remove skills from running agent {name}; stop it first"
                    )
            try:
                for name, held in affected:
                    for called in held:
                        skills.revoke(agents.skills(name), called)
                        revoked.append((name, called))
                yield
            except BaseException as original:
                failed = []
                for name, called in reversed(revoked):
                    try:
                        skills.grant(agents.skills(name), called)
                    except Exception as rollback:
                        failed.append(f"{name}/{called}: {rollback}")
                if failed:
                    raise catalogs.RollbackFailed(
                        f"the catalog change failed ({original}); restoring grants also "
                        f"failed for {', '.join(failed)}"
                    ) from original
                raise
        retired.extend(revoked)


def _refresh_skill_catalogs(agents, skills, gateways, catalogs) -> int:
    """Seed the general collection and check every installed repository version."""
    try:
        retired = []
        checked = catalogs.refresh(
            granted=_all_granted_skills(agents, skills),
            retiring=lambda names: _retiring_catalog_grants(
                agents, skills, gateways, catalogs, names, retired,
            ),
        )
    except (catalogs.NotACatalog, OSError) as why:
        print(f"skills: CATALOGS NOT UPDATED — {why}", file=sys.stderr)
        return 1
    failed = False
    for one in checked:
        if one.why:
            failed = True
            print(f"skills: {one.name} NOT UPDATED — {one.why}", file=sys.stderr)
        elif one.before is None:
            print(f"skills: {one.name} {one.after}: installed by default")
        elif one.before == one.after:
            print(f"skills: {one.name} {one.after}: up to date")
        else:
            print(f"skills: {one.name}: {one.before} -> {one.after}")
    for name, called in retired:
        print(f"{name} no longer has removed skill {called}")
    return 1 if failed else 0


def _install_skill_catalog(args: argparse.Namespace, catalogs) -> int:
    try:
        if not args.confirm:
            manifest = catalogs.inspect(args.repository)
            print(f"{manifest.name} {manifest.version} — {manifest.description}")
            print(f"source: {args.repository}")
            print("skills:")
            for called, _ in manifest.skills:
                print(f"  {called}")
            print()
            print(f"install: rundesk skills install {args.repository} --confirm")
            return 0
        landed = catalogs.install(args.repository)
    except (catalogs.NotACatalog, catalogs.InTheWay, OSError) as why:
        print(f"skills: NOT INSTALLED — {why}", file=sys.stderr)
        return 1
    print(f"{landed.name} {landed.version}: installed")
    print("        its skills are available and none were granted")
    return 0


def _update_skill_catalog(args: argparse.Namespace, agents, skills, gateways, catalogs) -> int:
    retired = []
    try:
        before = catalogs.installed().get(args.catalog)
        landed = catalogs.update(
            args.catalog, granted=_all_granted_skills(agents, skills),
            retiring=lambda names: _retiring_catalog_grants(
                agents, skills, gateways, catalogs, names, retired,
            ),
        )
    except (catalogs.NotACatalog, catalogs.InTheWay, catalogs.InUse,
            catalogs.Unknown, catalogs.RollbackFailed, OSError) as why:
        print(f"skills: NOT UPDATED — {why}", file=sys.stderr)
        return 1
    if before is not None and before.version == landed.version:
        print(f"{landed.name} {landed.version}: up to date")
    else:
        print(f"{landed.name}: {before.version if before else '-'} -> {landed.version}")
    for name, called in retired:
        print(f"{name} no longer has removed skill {called}")
    return 0


def _remove_skill_catalog(args: argparse.Namespace, agents, skills, gateways, catalogs) -> int:
    retired = []
    try:
        standing = catalogs.installed().get(args.catalog)
        if standing is None:
            raise catalogs.Unknown(f"there is no installed catalog called {args.catalog}")
        if not args.yes:
            print(f"{standing.name} {standing.version} would be removed")
            for called, _ in standing.manifest.skills:
                print(f"  {called}")
            print()
            print(f"remove: rundesk skills remove {args.catalog} --yes")
            return 0
        removed = catalogs.remove(
            args.catalog, granted=_all_granted_skills(agents, skills),
            retiring=lambda names: _retiring_catalog_grants(
                agents, skills, gateways, catalogs, names, retired,
            ),
        )
    except (catalogs.NotACatalog, catalogs.InUse, catalogs.Unknown,
            catalogs.RollbackFailed, OSError) as why:
        print(f"skills: NOT REMOVED — {why}", file=sys.stderr)
        return 1
    print(f"{args.catalog}: removed {', '.join(removed)}")
    for name, called in retired:
        print(f"{name} no longer has removed skill {called}")
    return 0


def _list_skill_catalogs(catalogs) -> int:
    try:
        held = catalogs.installed()
    except catalogs.NotACatalog as why:
        print(f"skills: catalogs could not be read — {why}", file=sys.stderr)
        return 1
    if not held:
        print("no skill catalogs")
        print("        install one:  rundesk skills install <repository>")
        return 0
    _as_table(
        ("CATALOG", "VERSION", "SOURCE", "SKILLS"),
        [(one.name, one.version, one.source, str(len(one.manifest.skills)))
         for one in held.values()],
    )
    return 0


def cmd_skills(args: argparse.Namespace, agents, skills, gateways, catalogs) -> int:
    """The skills on this machine, who has which, and giving or taking one away.

    The catalog is read off the library and the agents rather than from anything written
    down about them: a grant *is* the link standing in an agent's own directory, so there
    is no record that could disagree with what a brain will actually find.
    """
    if getattr(args, "where", False):
        # Said by the command rather than written into any prose, because where the
        # library is depends on where this install is: an install pointed elsewhere
        # keeps its skills there too, and a guide naming `~/.rundesk` would be wrong
        # for every one of them.
        print(skills.home())
        return 0
    if getattr(args, "take_back", False):
        # The installer's too, on the way out: what a release laid down is the program's and
        # goes with it (R-RM-7). Left behind, it is a piece of rundesk on a machine somebody
        # has removed rundesk from — and it keeps the whole install directory standing after
        # an uninstall that said it had left nothing.
        retired = []
        taken = catalogs.take_back_seeded(
            retiring=lambda names: _retiring_catalog_grants(
                agents, skills, gateways, catalogs, names, retired,
            ),
        )
        taken.extend(skills.take_back())
        # What the release laid down and nobody has touched, for the same reason a
        # built-in skill goes: it is a piece of the program, and it is what leaves the
        # install directory standing after an uninstall that said it left nothing
        # (R-RM-7). An edited role is the owner's and stays.
        taken.extend(role.take_back())
        print(" ".join(taken))
        return 0
    if getattr(args, "lay_down", False):
        # The installer's, and deliberately not an owner's verb: what a release ships is
        # not a thing anybody should have to ask for.
        laid = skills.lay_down()
        agents.reconcile_skill_config()
        if _refresh_skill_catalogs(agents, skills, gateways, catalogs):
            return 1
        # `skills.granted` is a floor for every agent, including ones that predate the
        # value. Re-running the installer is an upgrade route, so reconcile the existing
        # population here as well as in `_provisioned` (R-AGT-36).
        for name in agents.known():
            agents.require_skills(name)
        agents.retire_renamed_skills()
        print(" ".join(laid))
        return 0
    act = getattr(args, "act", None)
    if act == "install":
        return _install_skill_catalog(args, catalogs)
    if act == "update":
        return _update_skill_catalog(args, agents, skills, gateways, catalogs)
    if act == "remove":
        return _remove_skill_catalog(args, agents, skills, gateways, catalogs)
    if act == "catalogs":
        return _list_skill_catalogs(catalogs)
    if act in ("grant", "revoke"):
        try:
            whose = agents.skills(args.name)
        except agents.NotAnAgentName as why:
            print(f"{args.name}: INVALID NAME — {why}", file=sys.stderr)
            return 1
        if not agents.exists(args.name):
            print(f"{args.name}: NO SUCH AGENT", file=sys.stderr)
            print(f"        make one:  rundesk add {args.name} --provider <provider>",
                  file=sys.stderr)
            return 1
        try:
            if act == "grant":
                with skills.changing_grants(skills.home()):
                    skills.grant(whose, args.skill)
                print(f"{args.name} was given {args.skill}")
            else:
                # Rundesk's product floor and the configured baseline are requirements, not
                # creation-time suggestions. Only the owner-selected part can be changed
                # before revocation (R-AGT-37).
                if args.skill in config.required_grants():
                    print(f"{args.skill}: RUNDESK REQUIRED — every agent retains it",
                          file=sys.stderr)
                    print("        this skill cannot be configured away or revoked",
                          file=sys.stderr)
                    return 1
                if args.skill in config.skills()["granted"]:
                    print(f"{args.skill}: REQUIRED — config.json attaches it to every agent",
                          file=sys.stderr)
                    print(f"        remove it from {config.path()} before revoking it",
                          file=sys.stderr)
                    return 1
                with skills.changing_grants(skills.home()):
                    skills.revoke(whose, args.skill)
                print(f"{args.name} no longer has {args.skill}")
        except (skills.Unknown, skills.NotASkill, skills.InTheWay,
                config.Unreadable) as why:
            print(f"{args.skill}: {why}", file=sys.stderr)
            return 1
        return 0

    held = skills.library()
    if not held:
        print("no skills")
        print(f"        write one:  {skills.home()}/<name>/SKILL.md")
        return 0
    ships = set(skills.shipped())
    # Asked of every agent rather than kept anywhere, because "who has this" is otherwise
    # a question only a reverse scan can answer and a stored answer would go stale the
    # first time somebody removed a link by hand.
    whose: dict = {name: skills.granted(agents.skills(name)) for name in agents.known()}
    # **What put it there, not whose it is.** `rundesk` is one this release ships and an
    # update brings forward; `custom` is one somebody wrote, which nothing here ever
    # touches. Said this way because the column has more answers coming — a skill that
    # arrived with a plugin, or with a tool — and "yours" against "built-in" is a pair with
    # nowhere for a third to stand.
    rows = [(name, "rundesk" if name in ships else (catalogs.whose(held[name]) or "custom"),
             ", ".join(sorted(who for who, mine in whose.items() if name in mine)) or "-")
            for name in sorted(held)]
    _as_table(("SKILL", "FROM", "AGENTS"), rows)
    return 0


def cmd_scripts(args: argparse.Namespace, scripts) -> int:
    """The owner's shared integration commands and where they stand."""
    where = scripts.home()
    if getattr(args, "where", False):
        print(where)
        return 0
    held = scripts.commands()
    if not held:
        print("no scripts")
        print(f"        write one:  {where}/<command>")
        return 0
    _as_table(("SCRIPT", "COMMAND"), [
        (name, str(at)) for name, at in sorted(held.items())
    ])
    print()
    print(f"kept in {where}")
    return 0
