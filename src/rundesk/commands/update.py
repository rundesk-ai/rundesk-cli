"""What this install is, and moving it to what is published.

The owner-facing half of an update: what version this is and whether a newer one exists,
what an update *would* do before it does it, bringing every agent's records forward inside
the window the update already opens, and taking rundesk off a machine again.

The machine-wide half — standing every gateway down and putting it back — is
`update_worker.py`, because a process no gateway owns does that and no command does.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from rundesk import ROOT, __version__
from rundesk import agent as _agent
from rundesk import catalog
from rundesk import config
from rundesk import dependencies
from rundesk import migration
from rundesk import role
from rundesk import skill
from rundesk import store
from rundesk import update_request
from rundesk import update_worker
from rundesk import updater
from rundesk.commands.skills import _refresh_skill_catalogs

#: The installer as published, for the one case where this install has lost its own:
#: removing rundesk is exactly when a broken install has to be removable.
PUBLISHED_INSTALLER = (
    "https://raw.githubusercontent.com/rundesk-ai/rundesk-cli/main/install.sh"
)


def cmd_version(args: argparse.Namespace) -> int:
    if args.check:
        return updater.run(ROOT, __version__, check_only=True)
    print(f"rundesk {__version__}")
    return 0


def cmd_update(args: argparse.Namespace, gateways, machine, agents, catalogs=catalog) -> int:
    if args.after_replacing is not None:
        # This process *is* the release that just landed, so what it does to an owner's
        # records is what the release that shipped it says it should be (R-UPD-33). The
        # window is already open and every gateway named here is already down.
        waiting = [one for one in args.after_replacing.split(",") if one]
        code = updater.carry_on(
            ROOT, waiting,
            resume=lambda names: update_worker._bring_all_back(names, gateways, machine, agents),
            provision=_provisioned,
            carry=lambda: _carry_every(agents),
            # **This process's own version, never the one it was told about.** The release
            # that just landed is the code running this line, while `RUNDESK_UPDATE_VERSION`
            # in the environment is what the *previous* release reported before the window
            # opened — linking that would name the version an owner has just left (R-UPD-46).
            landed=__version__,
        )
        if code == 0:
            cataloged = _refresh_skill_catalogs(agents, skill, gateways, catalogs)
            if not os.environ.get("RUNDESK_UPDATE_WORKER"):
                scheduled = update_worker._install_automatic_updates(machine)
                return cataloged or scheduled
            return cataloged
        return code
    if args.worker:
        return update_worker._run_update_worker(gateways, machine, agents)
    if getattr(args, "automatic", False) is True:
        return update_worker._queue_automatic_update(machine)
    if args.status:
        try:
            row = update_request.read()
        except update_request.Unreadable as why:
            print(f"update: UNKNOWN — {why}", file=sys.stderr)
            return 1
        if row is None:
            print("no queued update")
            return 0
        print(update_request.summary(row))
        return 0 if row.get("state") != "failed" else 1
    # A check remains immediate and read-only even inside a provider turn.
    if args.check:
        update_root, current_version = _update_install()
        return updater.run(
            update_root, current_version, check_only=True,
            unfit=lambda: gateways.fitness(update_root),
            preview=lambda: _what_an_update_would_do(agents, update_root),
        )
    if os.environ.get("RUNDESK_RUN"):
        origin = update_worker._origin_of_update(agents)
        if origin.get("agent"):
            return update_worker._queue_update(machine, origin)
    update_root, current_version = _update_install()
    code = updater.run(
        update_root, current_version, check_only=False,
        busy=lambda: update_worker._in_flight(gateways, agents),
        pause=lambda: update_worker._stand_all_down(gateways, machine, agents, update_root),
        resume=lambda names: update_worker._bring_all_back(
            names, gateways, machine, agents, update_root
        ),
        provision=lambda: _provisioned(update_root),
        carry=lambda: _carry_every(agents),
        unfit=lambda: gateways.fitness(update_root),
        preview=lambda: _what_an_update_would_do(agents, update_root),
    )
    if code == 0:
        cataloged = _refresh_skill_catalogs(agents, skill, gateways, catalogs)
        scheduled = update_worker._install_automatic_updates(machine)
        return cataloged or scheduled
    return code


def _update_install() -> tuple[Path, str]:
    """The install this externally owned worker is driving."""
    return (
        Path(os.environ.get("RUNDESK_UPDATE_ROOT") or ROOT),
        os.environ.get("RUNDESK_UPDATE_VERSION") or __version__,
    )


def _what_an_update_would_do(agents, root: Path = ROOT) -> list:
    """What an update would install and what it would move, before it does either.

    Reads what is on disk and asks nothing of a network, a package index or a database that
    does not already exist (R-UPD-34). Silence where there is nothing to say: an owner who
    reads "nothing to install, nothing to move" every time stops reading it.
    """
    said = []
    for one in dependencies.unsatisfied(root):
        said.append(f"would install: {one}")
    standing = migration.what_would_run(agents.agents_home(), store.VERSION)
    for name, steps in sorted(standing.items()):
        if steps:
            said.append(f"would move {name}: " + ", ".join(repr(one) for one in steps))
    behind = sorted(name for name, steps in standing.items() if steps)
    if behind:
        said.append(f"agents to move: {len(behind)} of {len(standing)}")
    return said


def _carry_every(agents) -> str | None:
    """Bring every agent's records into the shape the new files expect (R-MIG-1).

    Called in the window an update already opens: after the files are replaced and before
    the first agent is brought back, which is the only moment nothing is reading them.
    Never lazily and never by whoever opens a database first — two gateways starting
    together would both begin moving one forward.

    Says what went wrong rather than raising it, because the updater is a decision and
    knows nothing of agents or of what they keep. What each step did, or failed to do, is
    already in that agent's own log.

    **And puts every agent back as it was when one of them cannot be moved** (R-MIG-19).
    Two agents are never at the same version, so the walk stops with earlier ones already
    carried — and the updater then puts the release back, which would leave exactly those
    agents holding records newer than the only code left to read them.
    """
    return migration.carry_every_or_put_back(
        agents.agents_home(), store.VERSION, note=_out_loud,
    )


def _out_loud(said: str) -> None:
    """Each agent as it is reached, so a long update is not a silent one."""
    print(f"        {said}")


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Take rundesk off this machine, or fail saying why.

    It printed instructions and exited zero. A control verb that is an instruction page
    makes someone find a second surface, and exiting zero says the uninstall ran when
    nothing was removed at all — which is the one failure this product is most careful
    about everywhere else.

    The installer owns removal, so this runs it rather than reimplementing it: one thing
    decides what is rundesk's and what is the owner's, and a second copy of that decision
    is how an uninstall comes to delete a home it should have kept.

    **Run where it stands**, which is what `install.sh --uninstall` by hand has always
    done. Running it from a copy elsewhere looked safer and was not: the installer finds
    the command it placed by comparing the symlink against its own directory, so a copy in
    a temporary directory matched nothing and left the command on the PATH — removing
    rundesk and leaving behind the one thing R-RM-1 is about.
    """
    installer = ROOT / "install.sh"
    if not installer.is_file():
        print(f"uninstall: FAILED — this install has no installer to run ({installer})",
              file=sys.stderr)
        print("        remove it with the published one:", file=sys.stderr)
        print(f"        curl -fsSL {PUBLISHED_INSTALLER} | bash -s -- --uninstall",
              file=sys.stderr)
        return 1
    asked = ["--uninstall"] + (["--purge"] if args.purge else [])
    # Looked up here rather than bound in the signature, so a test can put something else
    # in its place — running the real installer to prove this calls it would stop the
    # gateways of whoever ran the suite.
    try:
        ended = _remove_this_install(installer, asked)
    except OSError as why:
        print(f"uninstall: FAILED — could not run the installer: {why}", file=sys.stderr)
        return 1
    if ended != 0:
        # Said again in our own words: the installer has already explained what stopped
        # it, and a command that ended non-zero without saying so reads as a crash.
        print(f"uninstall: FAILED — nothing was removed (the installer ended {ended})",
              file=sys.stderr)
        return 1
    return 0


def _remove_this_install(installer: Path, asked: list[str]) -> int:
    """Run the installer's own removal, where it stands, and say how it ended.

    Where it stands, because the installer works out what it placed relative to its own
    directory: run from anywhere else it recognises none of it, and the command it linked
    onto the PATH is left behind by the very thing meant to remove it. This is the same
    invocation someone types by hand, which is what the installer is written against.
    """
    return subprocess.run(["bash", str(installer), *asked],
                          cwd=str(installer.parent)).returncode


def _provisioned(root: Path = ROOT) -> str | None:
    """What an install is made of, brought forward: what it needs, then what it ships.

    Skills after dependencies, which is the same order the window itself keeps and for the
    same reason — the failure that cannot touch an owner's files happens first. Bringing a
    built-in forward is what makes it rundesk's rather than a copy an owner then owns, and
    it is the whole of "always the latest version" (R-AGT-30): the set is read off the
    release each time, while the ownership marker says which same-named directories may
    safely be replaced. A skill that could not be written is not an update that failed —
    `doctor` says which one, and everything else is already forward.
    """
    went_wrong = dependencies.provision(root)
    if went_wrong:
        return went_wrong
    # Values this release knows and an earlier one never wrote. Values already there are
    # never touched, so this cannot be how an owner's configuration is lost (R-UPD-48).
    config.ensure()
    skill.lay_down(force=True)
    # Shipped roles are laid down where they are missing and never over one that is
    # there. A role is what an owner writes their specialists as, so bringing one
    # "forward" the way a built-in skill is brought forward would rewrite what every
    # future run of an edited role is allowed to do (R-ROL-18).
    role.lay_down()
    # A persisted skill name can move only after both old and replacement packages are
    # proven as Rundesk built-ins. The earlier pass fills values; this one carries names.
    config.ensure()
    # Existing agents are brought forward too. Optional owner grants are not removed; the
    # configured list is the minimum every agent must hold, not its complete grant set.
    for name in _agent.known():
        _agent.require_skills(name)
    _agent.retire_renamed_skills()
    return None
