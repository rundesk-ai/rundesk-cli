"""Moving this install to the newest published release.

The highest-consequence path in the product, so everything variable in it — what is published, how an
archive is fetched — arrives as an argument and the whole of it runs offline in a test.

The order is chosen so that the failure which cannot damage anything happens first:

1. Ask what is published. Cannot ask → **stop, non-zero**, and change nothing.
2. Not newer → settle the install anyway, and stop. Being on the newest release is not the same as
   being settled on it, and an update interrupted between the two would otherwise never finish.
3. Fetch the archive and check it is a rundesk tree, in a temporary directory. Nothing installed has
   been touched yet, so everything up to here is free to fail.
4. Stand down every online gateway, after all fetch/archive failures are behind us.
5. Replace `app/`, staged and renamed, putting back what was there if any part fails.
6. **Hand off to the release that just landed** to settle the install, then restart exactly those
   gateways with a one-shot notice proving which version came back.

## Why settling is a handoff and not two more lines here

Once the files are replaced, this process is still running **the old release** — its modules were
imported before the swap and they do not change underneath it. So the code sitting in memory to fill
in configuration and run migration steps is the code being replaced, and it would carry the install
forward using the *previous* release's steps and the previous release's idea of what a configuration
holds. Every step the new release ships would be skipped, and the install would be stamped as
carried.

So the settling is done by loading the new release from disk in a separate interpreter and calling
its `settle()`. Deliberately not a command-line flag: settling is a step of installing and updating
rather than an operation anybody performs, and the command surface stays exactly what it says it is.
"""

import argparse
import contextlib
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Protocol, Tuple

from rundesk import __version__
from rundesk.agents import directory, pages, records
from rundesk.agents import migration as agent_migration
from rundesk.commands import failed, skills, the_reason
from rundesk.commands.gateways import Cycled
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job, maintenance, standing
from rundesk.lifecycle import backups, home, migration, packages, release, tree
from rundesk.skills.catalogs import Fetching as Refreshing
from rundesk.utils import archives, locking, programs

#: How a release archive is brought down: given where it is and where to put it, it puts it there.
#: The second of the two things in this product that leave the machine, and like the first it is a
#: value a caller hands in rather than an import a test cannot reach past.
Fetching = Callable[[str, Path], None]

FETCH_SECONDS = 60

#: How long the newly installed release is given to settle the install. Generous: a migration step
#: may legitimately move a lot of files.
SETTLE_SECONDS = 300


class Attempt(NamedTuple):
    """The command result and whether work made this a durable queue request."""

    code: int
    queued: bool


class CouldNotKeep(Exception):
    """The configured pre-migration rollback copy could not be made."""


class Gateways(Protocol):
    """Standing one agent's gateway down, and starting it again. One name in, `""` when it was done.

    **A gateway holding an agent's records open while that agent is carried is the `database is
    locked` failure**, and a gateway left alive across a program swap keeps running the old imported
    release indefinitely. A new release therefore stands every online gateway down; an up-to-date
    settle still cycles only agents with migration work. Both start again **exactly** the gateways
    they stood down.

    **What answers this is `commands.gateways.Cycled`**, which is the two verbs a person types —
    `rundesk gateways stop` and `rundesk gateways start` — as something another command can be
    handed. A shape rather than an import: this stays a `Protocol` so the reasoning lives beside the
    caller that needs it and neither command has to reach into the other.

    **Resolved by whoever calls, and never bound as a default in a signature.** For a carry that
    means `settle`, which is the one function here that runs in an interpreter of its own — see what
    it says about why the process running the update cannot hand one across.

    Handed nothing, an agent with a live gateway and a step waiting is **named and not carried**,
    and the run ends non-zero saying so. Nothing in the product arrives here that way, and it stays
    the answer for a caller inside this codebase that does: carrying under a live gateway risks the
    failure above, and reporting an agent carried when nothing ran is the one thing this product
    refuses to do.

    A sentence rather than an exception, for `carry_one`'s reason: the caller's job is to go on to
    the next agent, and an exception is the shape that stops a loop.
    """

    def down(self, name: str) -> str:
        """Stand this agent's gateway down. `""` when it is down, else why it is not."""

    def up(self, name: str) -> str:
        """Start this agent's gateway again. `""` when it is up, else why it is not."""


def cmd_update(_args: argparse.Namespace, asking: Optional[release.Asking] = None,
               fetching: Optional[Fetching] = None,
               refreshing: Optional[Refreshing] = None,
               building: Optional[Callable[..., programs.Ran]] = None,
               gateways: Optional[Gateways] = None) -> int:
    """Move to the newest published release, or say it is already up to date.

    Takes no flags. `asking` looks up what is published, `fetching` downloads it, `refreshing`
    brings down a catalog of skills, and `gateways` cycles live agents; all are resolved here rather
    than bound in the signature, so the whole command is driven with no network or launchd nearby.

    **The skill catalogs are checked on every run of this, including one that found nothing newer.**
    That is what makes them current daily rather than only when rundesk itself moves: a catalog is
    somebody else's repository and it changes on its own schedule. It happens last, it cannot change
    this command's exit code, and `commands.skills.refreshed` says why.
    """
    return attempt_update(
        _args, asking=asking, fetching=fetching, refreshing=refreshing,
        building=building, gateways=gateways).code


def attempt_update(_args: argparse.Namespace, asking: Optional[release.Asking] = None,
                   fetching: Optional[Fetching] = None,
                   refreshing: Optional[Refreshing] = None,
                   building: Optional[Callable[..., programs.Ran]] = None,
                   gateways: Optional[Gateways] = None) -> Attempt:
    """Run or durably queue one update, preserving that distinction for coordinators."""
    installed_before_waiting = paths.app().is_dir()
    try:
        with locking.only_one(paths.update_lock(), guarding="updating this install"):
            if installed_before_waiting and not paths.app().is_dir():
                return Attempt(_failed(
                    "this install was removed while the update waited; run install to place it "
                    "again"), False)
            # No update may take a gateway away from admitted work. The same admission barrier the
            # automatic coordinator uses closes the last-message race: once quiet is observed, no
            # new provider turn can begin until the whole gateway cycle has finished.
            with locking.only_one(paths.work_admission_lock(),
                                   guarding="starting this update safely"):
                from rundesk.commands import automatic_updates
                busy = automatic_updates._busy_reason()
                if busy:
                    said = automatic_updates.queued(busy)
                    print(said, file=sys.stderr if said.startswith("the update could not") else sys.stdout)
                    failed_to_queue = said.startswith("the update could not")
                    return Attempt(FAILED if failed_to_queue else OK, not failed_to_queue)
                return Attempt(
                    _cmd_update(_args, asking, fetching, refreshing, building, gateways), False)
    except locking.Stuck as why:
        return Attempt(_failed(str(why)), False)


def _cmd_update(_args: argparse.Namespace, asking: Optional[release.Asking] = None,
                fetching: Optional[Fetching] = None,
                refreshing: Optional[Refreshing] = None,
                building: Optional[Callable[..., programs.Ran]] = None,
                gateways: Optional[Gateways] = None) -> int:
    """The update transaction, with its per-install claim already held."""
    line, published, could_ask = release.standing(__version__, asking)
    if not could_ask:
        print(line, file=sys.stderr)
        return FAILED
    print(line)

    if not release.newer(published, __version__):
        # **Being on the newest release is not the same as being settled on it.** An update that
        # was interrupted between replacing the files and settling — a machine that slept, a
        # terminal that closed — leaves an install whose code is current and whose configuration and
        # migrations belong to the release before it. Asking GitHub then answers UP TO DATE for
        # ever, and the settling never happens: a value the new release added is never written, and
        # a migration step it shipped is never run.
        #
        # So this settles rather than checking whether settling is needed. Every part of it is
        # already idempotent — the directories are made if absent, configuration values are filled
        # in only where missing, and a migration step that has run is recorded and skipped — so
        # doing it unconditionally costs one process and makes the half-updated state impossible to
        # be left in, rather than merely unlikely.
        # **No `app/` is a checkout, not a reason to skip settling.** This returned `OK` here
        # without doing anything, which made `./dev update` — the only way this product is
        # developed — a command that printed `UP TO DATE` and settled nothing, for ever. An agent
        # added before a release that ships a migration step therefore stayed unsettled, and its
        # gateway refused to host it with a sentence nobody was going to read. `paths.code` answers
        # for both arrangements, so there is nothing left for this guard to protect against.
        try:
            gone_wrong = settled_by_the_new_release(paths.code())
        except paths.Refused as why:
            gone_wrong = str(why)
        if gone_wrong:
            return _failed(f"this install is on {__version__} and is not settled — {gone_wrong}")
        _catalogs_checked(refreshing)
        return OK

    try:
        root = paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    holding = tempfile.mkdtemp(prefix="rundesk-update-")
    were_up: List[str] = []
    update_failure = ""
    installed = False
    settled = False
    handed_to_the_tree = False
    normalized = published.lstrip("v")
    notes = release.release_url(normalized) or ""
    restart_trouble = ""
    try:
        try:
            landed = _brought_down(published, Path(holding), fetching)
        except (OSError, urllib.error.URLError, tarfile.TarError, ValueError) as why:
            return _failed(f"{published} could not be fetched: {why}")

        print(f"        installing {published}")
        try:
            # A host takes this same barrier before claiming an agent. One that wins first is
            # visible to the preflight; one that arrives later cannot import-and-run across the
            # swap, and refreshes its interpreter after the barrier opens.
            with locking.only_one(
                    paths.gateway_transition_lock(root), "gateways during this update",
                    locking.WHILE_A_DIRECTORY_MOVES):
                cycled = _the_gateways(gateways)
                gone_wrong, were_up = _gateways_stood_down_for_update(
                    root, normalized, cycled, _out_loud)
                if gone_wrong:
                    return _failed(gone_wrong)

                # From here on whichever coherent tree remains must restart the gateways. Set
                # before the call: an interrupt can land after `place` returns and before the
                # next Python assignment, when the files are already the new release.
                handed_to_the_tree = True
                try:
                    tree.place(landed, root)
                    installed = True
                except tree.HalfReplaced as why:
                    update_failure = str(why)
                except (tree.Refused, OSError) as why:
                    update_failure = f"{why} — this install is unchanged"

                if installed:
                    # Built from the tree that just landed, not the imported old release.
                    could_not = packages.built(paths.app(), building)
                    if could_not:
                        print(f"        packages   {could_not}", file=sys.stderr)
                        print("        channels cannot be started until this works", file=sys.stderr)

                    gone_wrong = settled_by_the_new_release(paths.code())
                    if gone_wrong:
                        update_failure = f"{published} is installed and was not settled — {gone_wrong}"
                    else:
                        settled = True
                        try:
                            config.moved(data=paths.data())
                        except (config.Unreadable, config.Refused, config.Stuck) as why:
                            print(f"update: {published} is installed and when it arrived was not "
                                  f"recorded — {why}", file=sys.stderr)
        except locking.Stuck as why:
            return _failed(f"the gateways could not be held offline — {why}")
    finally:
        shutil.rmtree(holding, ignore_errors=True)
        if were_up:
            if handed_to_the_tree:
                try:
                    installed_code = paths.code()
                except paths.Refused as why:
                    restart_trouble = f"the release on disk could not be loaded to restart gateways: {why}"
                else:
                    restart_trouble = restarted_by_the_new_release(
                        installed_code, were_up, normalized, notes, settled)
            else:
                restart_trouble = _said(_gateways_started_after_update(
                    were_up, cycled, normalized, notes, False, _out_loud))

    if update_failure:
        if installed:
            print(f"update: {update_failure}", file=sys.stderr)
            print("        running it again will carry on from where this stopped", file=sys.stderr)
        else:
            _failed(update_failure)
        if restart_trouble:
            print(f"        {restart_trouble}", file=sys.stderr)
        return FAILED
    if restart_trouble:
        return _failed(restart_trouble)

    print(f"rundesk updated to {published}")
    if notes:
        print(f"        what changed: {notes}")
    _catalogs_checked(refreshing)
    return OK


def _gateways_stood_down_for_update(root: Path, version: str, gateways: Gateways,
                                      said: Callable[[str], None]) -> Tuple[str, List[str]]:
    """Preflight and stop every online gateway before replacing the program tree."""
    try:
        names = directory.known()
    except OSError as why:
        return f"the gateways could not be listed before the update: {why}", []

    online: List[str] = []
    for name in names:
        how = standing.standing(directory.where(name))
        if how.how == standing.CANNOT_TELL:
            return (f"nobody can tell whether the gateway for {name} is running — {how.why}; "
                    "the update was not installed"), []
        if how.how == standing.ONLINE:
            online.append(name)

    # Prove every live gateway can be restored before stopping the first. A foreground gateway with
    # a name launchd cannot carry is supported, but only the terminal that owns it can start it; an
    # unattended update therefore refuses while it is running instead of taking it away for good.
    for name in online:
        try:
            job.job(name, directory.where(name), root)
        except (directory.Refused, job.Refused, paths.Refused) as why:
            return (f"the gateway for {name} is running but cannot be restarted after the update "
                    f"({why}) — stop it in its terminal, then update", [])
    were_up: List[str] = []
    try:
        for name in online:
            at = directory.where(name)
            # Recorded before the marker too: an interrupt may land after its atomic rename and
            # before the next Python assignment, and recovery must consume that stale farewell.
            were_up.append(name)
            try:
                maintenance.installing(at, version)
            except (OSError, ValueError) as why:
                trouble = f"the update notice for {name} could not be prepared ({why})"
            else:
                try:
                    trouble = gateways.down(name)
                finally:
                    maintenance.clear(at)
            if trouble:
                restarted = _gateways_started_after_update(
                    were_up, gateways, version, "", False, said)
                also = f"; {_said(restarted)}" if restarted else ""
                return f"the gateway for {name} would not stand down ({trouble}){also}", []
            said(f"stood the gateway for {name} down for the update")
    except BaseException:
        # A second best-effort pass is intentional if recovery itself was interrupted. Starting an
        # already-started job is idempotent; leaving a candidate offline is not.
        _gateways_restarted_best_effort(were_up, gateways)
        raise
    return "", were_up


def _gateways_started_after_update(were_up: List[str], gateways: Gateways, version: str,
                                    notes: str, announce_installed: bool,
                                    said: Callable[[str], None]) -> Dict[str, str]:
    """Start exactly the gateways stopped for this update, with a proven success notice or none."""
    gone_wrong: Dict[str, str] = {}
    for index, name in enumerate(were_up):
        at = directory.where(name)
        try:
            if announce_installed:
                try:
                    maintenance.installed(at, version, notes)
                except (OSError, ValueError) as why:
                    gone_wrong[name] = (
                        f"the installed-update notice for {name} could not be prepared ({why})")
            else:
                maintenance.clear(at)

            trouble = gateways.up(name)
            if trouble:
                maintenance.clear(at)
                why = f"the gateway for {name} could not be started after the update ({trouble})"
                gone_wrong[name] = (
                    f"{gone_wrong[name]} — and {why}" if name in gone_wrong else why)
                continue
            said(f"started the gateway for {name} again")
        except BaseException:
            # The current call may have completed before interruption. Retry it and every untouched
            # candidate; both job placement and marker clearing are safe to repeat.
            _gateways_restarted_best_effort(were_up[index:], gateways)
            raise
    return gone_wrong


def _gateways_restarted_best_effort(names: List[str], gateways: Gateways) -> None:
    """Try every emergency restart even when marker cleanup or another restart fails."""
    for name in names:
        with contextlib.suppress(BaseException):
            maintenance.clear(directory.where(name))
        with contextlib.suppress(BaseException):
            gateways.up(name)


def _catalogs_checked(refreshing: Optional[Refreshing]) -> None:
    """Bring the skill catalogs up to date and say what could not be, changing no exit code.

    Deliberately returns nothing. What this command reports is whether *it* worked, and by the time
    this runs it has: the release landed, the data was carried, and the command answers. A catalog
    repository that has been deleted is a true thing to say and a false reason to tell a script the
    update failed.
    """
    for line in skills.refreshed(refreshing):
        print(f"        {line}", file=sys.stderr)


def settle(gateways: Optional[Gateways] = None) -> int:
    """Make this install match the release now sitting in `app/`, agents and all.

    Self-determining rather than told which case it is: an install with no configuration file has
    never been settled and has nothing to carry, and one with a configuration file is being moved
    forward. Deciding it here means the caller never has to be right about it, and running this by
    hand on an install that was interrupted is always safe.

    **Two levels are settled here, and the second one had no caller at all.** The install's own
    steps run first — one of them may reshape where agents stand, and an agent step run before that
    would be run against a layout the release has not finished making. Then every agent this install
    has is carried, because an install whose agents are still on the release before it is an install
    that is not settled: `agents.migration.carry_every` existed, was tested, and was reached from
    nothing, so an update printed success while every agent stayed exactly where it was.

    **An agent that could not be carried makes this non-zero**, and that is the whole point of
    wiring it. `rundesk update` is documented as idempotent and safe to run again, so a named
    failure with a way out is worth more than a success nothing earned.

    **`gateways` is resolved here, in this body, and it is the one collaborator in this file that
    cannot be handed in from the command.** `cmd_update` never calls this: the settling is done by
    the release that just landed, in an interpreter of its own, and `_SETTLE` is what starts it —
    so the process that ran `rundesk update` has a process boundary between it and this line, and
    an object cannot cross one. The same is true of `cmd_install`.

    **And widening `_SETTLE` to build one there would be a promise the next release has to keep.**
    That string comes from the release being *replaced* and runs against the release that has just
    landed, so every name in it is a name every future release must go on exporting or updates from
    this one stop settling. `settle` is already such a name; adding a second is a cost paid for
    ever, and resolving here costs nothing and reaches every install updating *from* an older
    release as well.

    What that resolution reaches is the real `launchctl`, which is exactly what it should reach in
    the subprocess it really runs in. In this process it reaches `job.Launchd` by attribute, which
    is the name `tests/support.py:run_with` replaces with something that raises — so a case that
    somehow got here without saying ends loudly rather than booting out the owner's own jobs.
    """
    fresh = not config.where(paths.data()).exists()
    try:
        # Inside the guard, not before it. Laying the directories down is filesystem work like
        # everything below it — a stray *file* where a directory belongs raises, and outside the
        # `try` that came out of the subprocess an install settles in as a raw traceback, which
        # `install: FAILED —` then printed verbatim to whoever ran the installer.
        home.prepare(saying=_out_loud)
        if fresh:
            config.write_fresh(paths.data())
            # Nothing to carry: the directories were made correctly a moment ago, and the steps
            # describe changes from releases this install never had.
            migration.stamp_without_running(paths.data())
        else:
            config.fill_in(paths.data())
            kept = _kept_before_carrying()
            gone_wrong = migration.carry(paths.data(), saying=_out_loud)
            if gone_wrong:
                return _failed(f"{gone_wrong}{kept}")
        # **After the install's own steps, and outside the fresh/carried branch.** A fresh install
        # has no agents, so this costs it a listing that answers none — and an install whose
        # `config.json` was lost reads as fresh while its agents are still standing there, which is
        # exactly the case that must not skip them.
        left = carried_every_agent(_out_loud, _the_gateways(gateways))
        if left:
            return _failed(f"this install is carried and {_counted(left)} not: {_said(left)}")
        # After the carrying, and it cannot fail this command. A page an agent is missing is filled
        # in; one it already has is never touched, whatever it now says — see `agents.pages`. This
        # is what reaches an agent made by a release that shipped no pages at all, and a home
        # somebody deleted a file out of.
        pages.everybody_has_theirs(
            directory.known(), directory.home, _out_loud,
            lambda name: str(records.read(directory.records(name))["role"]))
        from rundesk.commands import automatic_updates
        scheduled = automatic_updates.reconcile()
        if scheduled.how == job.CANNOT_TELL:
            return _failed(f"automatic update scheduling could not be reconciled — {scheduled.why}")
    except (CouldNotKeep, config.Unreadable, config.Stuck, migration.Broken, OSError) as why:
        # Every write below `settle` goes through the configuration, including the stamp each
        # migration step lands with, so all of these are caught in one place rather than at each
        # of the calls that can give them.
        #
        # `OSError` is here because everything this function does is filesystem work, and the one
        # thing a settle must never do is end in a traceback: it runs in a subprocess whose stderr
        # is forwarded whole into the failure a person reads.
        #
        # `Broken` is here because steps that cannot be ordered are found by `stamp_without_running`
        # too, and that is the *fresh install* path — the one place a broken checkout is most likely
        # to be discovered. `carry` already answers it as a sentence; without this, the same fault a
        # second later came out of the other branch as a raw traceback, through a subprocess, into a
        # message somebody was meant to read.
        return _failed(str(why))
    return OK


def _the_gateways(gateways: Optional[Gateways]) -> Gateways:
    """Something that can stand a gateway down, resolved in a body and never in a signature.

    A default decided when this module was defined is one nothing can reach past — and what it
    cannot reach past here is `launchctl`, against the jobs of whoever is logged in.
    `commands.gateways._supervisor` is the same shape one layer down and for the same reason.
    """
    return gateways if gateways is not None else Cycled(job.Launchd())


def carried_every_agent(saying: Callable[[str], None],
                        gateways: Optional[Gateways] = None) -> Dict[str, str]:
    """Carry every agent this install has. Maps the ones that could not be carried to why.

    **One that fails is named and the others still carry**, which is `carry_every`'s whole contract
    and the reason the agent level is not the install level: twenty agents where the third has a
    corrupt database is nineteen agents that are fine.

    Three things happen in an order that is the guarantee:

    1. **Which agents have a step waiting** is asked first, before any gateway is touched. An
       install whose agents are all on this release is the ordinary case, and standing somebody's
       gateway down — or refusing their update because one is up — for an agent with nothing waiting
       would be a cost paid for nothing and a failure reported that did not happen.
    2. **The gateways of exactly those agents are stood down**, and which ones were up is written
       down before anything moves — asked of `gateways.standing`, which is the kernel's answer
       rather than something a process wrote about itself. See `Gateways` for what does the
       standing down.
    3. **Every gateway that was stood down is started again**, in a `finally`, so a carry that
       failed still leaves the machine as it found it. Never one that was already stopped: the list
       started empty and only a gateway this call really stood down is ever added to it.

    Being handed an install with no agents is not a discovery that found nothing — it is an install
    nobody has added an agent to, which is ordinary and silent.
    """
    names = directory.known()
    if not names:
        return {}

    waiting = [name for name in names if _has_a_step_waiting(name)]
    gone_wrong, were_up = _gateways_stood_down(waiting, gateways, saying)
    try:
        gone_wrong.update(agent_migration.carry_every(
            [name for name in names if name not in gone_wrong], saying=saying))
    finally:
        _gateways_started_again(were_up, gateways, gone_wrong, saying)
    return gone_wrong


def _has_a_step_waiting(name: str) -> bool:
    """Whether this agent has a step that has not run. `True` when the question cannot be answered.

    Asked so that an install whose agents are already on this release never has a gateway stood down
    for it, and never fails an update because one is running.

    **A question this cannot answer is answered `True` rather than skipped**, and the difference
    matters: records that are unreadable, or carried further than this release ships, are things
    `carry_every` names in its own words a moment later. Answering `False` here would be this
    function quietly deciding an agent needed nothing on the strength of not being able to look.
    """
    try:
        return bool(agent_migration.outstanding(
            agent_migration.recorded(directory.records(name))))
    except (agent_migration.Ahead, agent_migration.Backfilled, agent_migration.Broken,
            records.NotThere, records.Unreadable, directory.Refused, OSError):
        return True


def _gateways_stood_down(waiting: List[str], gateways: Optional[Gateways],
                         said: Callable[[str], None]) -> Tuple[Dict[str, str], List[str]]:
    """Stand down the gateway of every agent that has a step waiting. Returns what failed, and which
    gateways were really up.

    **Three answers, not two**, because `standing` gives three. A gateway nobody can ask about is
    not a gateway that is not running: carrying under one would be carrying under a live writer, and
    "cannot tell" is the one state where standing it down and starting it again cannot be exact
    either — there is nothing to be exact about. Named and left alone.
    """
    gone_wrong: Dict[str, str] = {}
    were_up: List[str] = []
    for name in waiting:
        how = standing.standing(directory.where(name)).how
        if how == standing.OFFLINE:
            continue
        if how == standing.CANNOT_TELL:
            gone_wrong[name] = (
                f"{name} was not carried: nobody can tell whether a gateway is running for it, and "
                "unreadable is not a quiet form of offline")
            continue
        if gateways is None:
            # Not a state `rundesk update` reaches: `settle` resolves one before it calls this.
            # Kept because the type says it may be `None`, and worded as what it is — this call was
            # handed nothing — rather than as a release that cannot do it, which is no longer true.
            gone_wrong[name] = (
                f"{name} was not carried: a gateway is running for it and this call was handed "
                "nothing that can stand one down — stop it, and `rundesk update` again carries it")
            continue
        trouble = gateways.down(name)
        if trouble:
            gone_wrong[name] = f"{name} was not carried: its gateway would not stand down ({trouble})"
            continue
        were_up.append(name)
        said(f"stood the gateway for {name} down")
    return gone_wrong, were_up


def _gateways_started_again(were_up: List[str], gateways: Optional[Gateways],
                            gone_wrong: Dict[str, str], said: Callable[[str], None]) -> None:
    """Start again exactly the gateways this call stood down, and say when one would not.

    `gateways` cannot be `None` while `were_up` holds anything — the only way a name gets in there
    is a `down` that answered — so the seam is never called on a run that had none to call it with.

    A gateway that was up and is now down is not a detail to leave in a summary: it is added to what
    went wrong, beside whatever the carry said, so the update ends non-zero and names both.
    """
    for name in were_up:
        trouble = gateways.up(name) if gateways is not None else "there is nothing here to start one"
        if trouble:
            also = (f"the gateway for {name} was stood down and could not be started again "
                    f"({trouble})")
            gone_wrong[name] = f"{gone_wrong[name]} — and {also}" if name in gone_wrong else also
            continue
        said(f"started the gateway for {name} again")


def _counted(gone_wrong: Dict[str, str]) -> str:
    """How many agents were left behind, in words that read the same for one as for twenty."""
    return "one of its agents is" if len(gone_wrong) == 1 else f"{len(gone_wrong)} of its agents are"


def _said(gone_wrong: Dict[str, str]) -> str:
    """Every agent that was left behind, each in its own sentence, in name order.

    All of them rather than the first. A summary saying "3 failed" is the shape that hides the one
    an owner has to look at, and each of these sentences already begins with the agent's own name.
    """
    return "; ".join(gone_wrong[name] for name in sorted(gone_wrong))


def _kept_before_carrying() -> str:
    """Copy the data before any step touches it, and say which copy that is. `""` when none.

    **This is the rollback, and it is deliberately not a down-step.** A step that failed halfway
    has left the data in a shape only that step knew about, and an inverse written months earlier
    by somebody who never ran it is not a way back — it is a second untested change applied to an
    install that is already broken. A copy taken a moment before is the whole of the answer, it
    needs nothing written per step, and the way back is a command that already exists and is
    already proven: `rundesk backups restore <name> --confirm`.

    Taken only when there is something to carry, so an ordinary update that changes no data does
    not leave a copy behind every time. And only when the owner keeps copies at all: `backup_enabled`
    has been a setting that governed nothing until now, and an owner who turned it off should not
    be surprised by one appearing.

    When copies are enabled, failing to make this one stops before carrying. Otherwise
    backup-enabled would claim a rollback boundary the update did not actually have.
    """
    data = paths.data()
    settled = config.read(data)
    if not migration.outstanding(settled.get("migration")):
        return ""
    if not settled.get("backup_enabled"):
        return ""
    try:
        name = backups.save(data)
    except (backups.Refused, OSError) as why:
        raise CouldNotKeep(f"no copy was taken before carrying: {why}") from why
    _out_loud(f"kept {name} — the data as it was before carrying")
    return f" — {paths.data()} as it was before this is the copy {name}"


#: Loading the release that has just landed and asking it to settle the install. Run in a separate
#: interpreter on purpose, and **not** through a command-line flag: settling is a step of installing
#: and updating rather than an operation anybody performs, so it is not on the command surface.
_SETTLE = (
    "import sys;"
    "sys.path.insert(0, sys.argv[1]);"
    "from rundesk.commands.update import settle;"
    "raise SystemExit(settle())"
)

#: The companion handoff after the update barrier opens. Restarting here — in the release that now
#: stands on disk — keeps old imported job/shim/layout logic from recreating a superseded job.
_RESTART_AFTER_UPDATE = (
    "import sys;"
    "sys.path.insert(0, sys.argv[1]);"
    "from rundesk.commands.update import restart_after_update;"
    "raise SystemExit(restart_after_update(sys.argv[2],sys.argv[3],"
    "sys.argv[4]=='installed',sys.argv[5:]))"
)


def settled_by_the_new_release(code: Path) -> str:
    """Run the release now in `app/` to settle the install. `""` when it worked.

    **`code` is the directory holding `rundesk/`, handed in from `core.paths.code`** — not the
    install's `app/`, which this took and then appended `src` to. That spelling is right for an
    install and wrong for a checkout, where there is no `app/` at all: `./dev update` therefore
    handed the subprocess a path that had never existed, and the settle that carries every agent
    onto this release quietly did nothing while the command printed `UP TO DATE`. An agent added
    before a release that ships a migration step then stayed unsettled for ever, and its gateway —
    correctly — refused to host it. See `core.paths.code`.

    A subprocess rather than an `exec`, so the process that performed the update is still here to
    report what happened. The environment is inherited, which is what carries `RUNDESK_HOME` through
    — the new release must settle the same install this one just replaced.

    `sys.executable` rather than the launcher's `#!/usr/bin/env python3`: which interpreter that
    resolves to depends on the PATH of whoever started the command, so the two can differ on one
    machine. The update runs on the interpreter that is already running it.
    """
    ended = programs.run([sys.executable, "-c", _SETTLE, str(code)], SETTLE_SECONDS)
    if ended.out:
        sys.stdout.write(ended.out)
    if ended.trouble:
        return f"the installed release {ended.trouble}"
    if ended.code != 0:
        return the_reason(ended.err) or f"it ended {ended.code}"
    return ""


def restart_after_update(version: str, notes: str, announce_installed: bool,
                         names: List[str], gateways: Optional[Gateways] = None) -> int:
    """Restart update-stopped gateways using the release now imported in this process.

    A stable internal handoff, not a command surface. `gateways` exists only for direct tests; the
    update subprocess resolves the new release's own supervisor and job implementation here.
    """
    gone_wrong = _gateways_started_after_update(
        names, _the_gateways(gateways), version, notes, announce_installed, _out_loud)
    if gone_wrong:
        print(_said(gone_wrong), file=sys.stderr)
        return FAILED
    return OK


def restarted_by_the_new_release(code: Path, names: List[str], version: str, notes: str,
                                 announce_installed: bool) -> str:
    """Ask the release on disk to restart `names`. `""` only when every one came back."""
    phase = "installed" if announce_installed else "ordinary"
    ended = programs.run(
        [sys.executable, "-c", _RESTART_AFTER_UPDATE, str(code), version, notes, phase, *names],
        SETTLE_SECONDS + len(names) * job.KICK_SECONDS)
    if ended.out:
        sys.stdout.write(ended.out)
    if ended.trouble:
        return f"the installed release {ended.trouble} while restarting gateways"
    if ended.code != 0:
        return the_reason(ended.err) or f"the installed release ended {ended.code} restarting gateways"
    return ""


def _brought_down(tag: str, into: Path, fetching: Optional[Fetching] = None) -> Path:
    """Fetch and unpack a release, and hand back the tree inside it.

    **Unpacked through `utils.archives`, which is the one place that guard is written.** It used to be
    written here as well, and the two copies were the same fix for the same measured bug — including
    the same reasoning about the two kinds of link resolving their targets against different
    directories. A gap found in one would have been fixed in one, and nothing would have gone red for
    the other: two suites proved the same guarantee against two functions.
    """
    fetch = fetching or _downloaded
    archive = into / "release.tar.gz"
    fetch(release.archive_url(tag), archive)
    archives.unpacked(archive, into)

    inside = [at for at in into.iterdir() if at.is_dir()]
    for at in inside:
        if tree.is_rundesk(at):
            return at
    raise ValueError("the archive does not contain a rundesk tree")


def _downloaded(url: str, into: Path) -> None:
    """Fetch a URL to a file. The only thing here that leaves the machine."""
    asked = urllib.request.Request(url, headers={"User-Agent": release.USER_AGENT})
    with urllib.request.urlopen(asked, timeout=FETCH_SECONDS) as answered, open(into, "wb") as writing:
        shutil.copyfileobj(answered, writing)


def _out_loud(said: str) -> None:
    print(f"        {said}")


def _failed(why: str) -> int:
    """`NOT APPLIED` rather than `FAILED`, and the difference is the point: an update that declined
    to move — nothing newer published, nothing reachable to ask — is not a command that broke."""
    return failed(f"update: NOT APPLIED — {why}")
