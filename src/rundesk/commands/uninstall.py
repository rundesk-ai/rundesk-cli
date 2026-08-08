"""Taking rundesk off this machine.

The command in the product with the least room for being approximately right, in both directions. A
removal that did not happen must never report success — somebody believes their machine is clean and
it is not. And a removal that happened cannot be undone, so what it reaches has to be decided rather
than swept.

So it names what it takes, one thing at a time, and never globs:

- **every gateway job this root derives a label for, by that full label, one agent at a time** —
  and **before `app/` goes**, because a job whose program has been removed is a machine that tries
  to start a command that is not there, at every login, for ever
- the PATH link, **only where it points into this install's own `app/`** — a second install on the
  machine keeps its command
- `app/`, whole, unless it looks like somebody's checkout
- `data/`, **only when `--purge` asks for it** — that is what the owner accumulated
- `backups/`, **never**. Not "not by default": there is no argument to this command that reaches
  them. A copy is worth nothing if the thing that takes the product away takes the copies too, and
  the way to guarantee that is for this file never to remove the directory. Copies now include
  credentials, so purging the live store does not remove every recoverable credential.
- `$RUNDESK_HOME` itself, only once nothing is left in it — so a purge tidies up and a plain removal
  leaves the root standing over the data it kept.

**A label is the one thing `RUNDESK_HOME` cannot isolate**, so the jobs are taken back by the full
label *this* root derives and never by a prefix, a family name or a sweep. The build this replaces
called every install's job `ai.rundesk.gateway`, and a second install's uninstall booted out the
live install's gateway. `gateways.job` refuses a label that does not fingerprint to its own root,
and this asks it for one label per agent, one at a time.

**Taking every job back is not the same as no gateway running**, and the gap between those two is
where this command was reaching past a live process. `rundesk gateways run <agent>` is a documented
foreground verb with **no launchd job at all**, so `job.remove` finds nothing to take back —
`bootout` answers `ALREADY_GONE`, which is correctly read as success — and every check here was
satisfied while a real gateway held a real lock on a real database. What came next removed `app/`
and, with `--purge`, `data/`, out from under it. So the kernel is asked directly, through
`gateways.standing`, once the jobs are back and **before anything comes off the disk**.
"""

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from rundesk.agents import directory
from rundesk.commands import failed
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job, standing
from rundesk.lifecycle import tree

#: How `gateways.job.remove` words the one failure that happens **after** the job really was taken
#: back and its two files really were removed — the trailing `enable` that makes the override record
#: inert. Matched rather than typed, because that function answers a sentence and not a shape, and
#: these two outcomes are genuinely different removals: one did not happen, the other did.
#: `tests/test_seam.py` drives `job.remove` itself into both, so a rewording there goes red here
#: rather than quietly turning every override failure back into a hard stop.
TAKEN_BACK_ANYWAY = "was taken back and its files removed"


def cmd_uninstall(args: argparse.Namespace,
                  supervising: Optional[job.Supervising] = None) -> int:
    """Remove rundesk, and say exactly what was taken and what was kept.

    `supervising` is the machine's supervisor and is resolved by `gateways.job` inside its own
    body — see `cli.main` for why this one seam has no safety net behind it.
    """
    try:
        root = paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    app = paths.app()
    if not app.exists() and not paths.data().exists():
        # Removing something that was never installed is not a failure; it is the state asked for.
        print(f"rundesk is not installed at {root}")
        return OK

    if not args.confirm:
        return _needs_confirming(root, args.purge)

    taken, kept = [], []

    # **First, and before `app/` is touched.** A job left behind points at a shim that hands off to
    # a release that is no longer on the disk, and launchd starts it at every login for ever —
    # failing, being throttled, and saying so only in the unified log. Nothing else here can be
    # undone by a later step, so this is the one that has to happen while the program is still
    # whole enough to be taken back cleanly.
    gone_wrong, jobs, by_hand = _the_jobs_taken_back(root, supervising)
    taken.extend(jobs)
    if gone_wrong:
        return _failed(gone_wrong, *(f"took   {one}" for one in jobs))
    for one in by_hand:
        # Said now rather than in the summary at the end: this is a job that really is gone, with one
        # thing left that somebody may have to finish by hand, and it belongs beside the removal it
        # is about rather than after everything else that happened.
        print(f"uninstall: {one}", file=sys.stderr)

    # **Before `app/` and before `data/`.** A gateway still holding a name at this point is one
    # launchd is not supervising — a `rundesk gateways run` in somebody's terminal — and removing the
    # program and the database underneath it is the reach past a live process this guard exists for.
    still_up = _the_gateways_still_holding_a_name()
    if still_up:
        return _failed(still_up[0], *still_up[1:], *(f"took   {one}" for one in taken))

    try:
        for at in tree.unlink(app, _where_the_command_went()):
            taken.append(str(at))
    except OSError as why:
        return _failed(f"the command could not be unlinked: {why}")

    try:
        if app.exists():
            tree.remove(app)
            taken.append(str(app))
    except (tree.Refused, OSError) as why:
        return _failed(str(why))

    if paths.data().exists():
        if args.purge:
            gone_wrong = _purge(paths.data())
            if gone_wrong:
                return _failed(gone_wrong)
            taken.append(str(paths.data()))
        else:
            kept.append(str(paths.data()))

    if paths.backups().exists():
        kept.append(f"{paths.backups()} (copies always survive removal)")
    if paths.projects().exists():
        kept.append(str(paths.projects()))

    _let_go_of_the_lock()
    _tidy(root)

    print("rundesk removed")
    for one in taken:
        print(f"        took   {one}")
    for one in kept:
        print(f"        kept   {one}")
    return OK


def _the_jobs_taken_back(
        root: Path, supervising: Optional[job.Supervising]) -> Tuple[str, List[str], List[str]]:
    """Take back every gateway job this root placed.

    `("", what went, what is left to finish by hand)`, or why it stopped in the first field.

    **One named label at a time, and never a sweep.** Every label is derived from the agent's name
    and *this* root's fingerprint, and `job.remove` refuses one that does not fingerprint back — so
    an uninstall here cannot reach a job belonging to another install of rundesk on the same
    machine, which is exactly what the build this replaces did.

    A job that could not be taken back **stops the removal**. Carrying on would take away the
    program a loaded job points at, and the machine would go on trying to start it at every login
    with no rundesk anywhere to say why.

    **"the job is gone and the override could not be cleared" is not that, and reading them as one
    reported a removal that had happened as one that had not.** `job.remove` can boot the job out,
    delete the plist and delete the shim — all of it — and then fail only its trailing `enable`, the
    call that makes the override record inert. It answers a sentence for that, this function treated
    any sentence as a hard stop, and three things went wrong at once: the label was left out of
    `taken` although its files really are gone, the command said "nothing further was removed" when
    something had been, and **every agent alphabetically after it never had its job touched at all**
    — for a reason that had nothing to do with them. So the two are told apart by
    `TAKEN_BACK_ANYWAY`, the second is carried out as a line somebody has to read, and the loop goes
    on.

    An agent whose name a launchd label cannot carry is passed over rather than reported: no
    gateway could ever have been placed for it, so there is nothing there to take back.
    """
    taken: List[str] = []
    by_hand: List[str] = []
    try:
        there = directory.known()
    except OSError as why:
        return (f"the agents could not be listed, so their gateway jobs cannot be taken back: {why}",
                taken, by_hand)

    for name in there:
        try:
            one = job.job(name, directory.where(name), root)
        except (job.Refused, directory.Refused):
            continue
        gone_wrong = job.remove(one, supervising)
        if gone_wrong and TAKEN_BACK_ANYWAY not in gone_wrong:
            return (f"the gateway job for {name} could not be taken back: {gone_wrong}",
                    taken, by_hand)
        taken.append(f"{one.label} (the gateway job for {name})")
        if gone_wrong:
            by_hand.append(gone_wrong)
    return "", taken, by_hand


def _the_gateways_still_holding_a_name() -> List[str]:
    """Why removal must stop: a gateway is still up. `[]` when none is, else the lines to print.

    **Asked of the kernel, once every job this root placed has been taken back.** A `bootout --wait`
    has already sent `SIGTERM` and waited for the process to really be gone, so a lock still held at
    this moment is one launchd was never supervising: `rundesk gateways run <agent>` is a documented
    foreground verb with no job at all, `job.remove` correctly reads a bootout of a label that was
    never bootstrapped as success, and nothing above this noticed the difference. What follows
    removes `app/` and, with `--purge`, the database that gateway is writing to.

    **Three answers, not two.** A lock nobody can open is not a lock nobody holds, and taking an
    install away under one is precisely what this refuses — `unreadable` is not a quiet form of
    `offline` here any more than it is anywhere else.

    Every agent is named, never the first: somebody about to be told to stop gateways by hand needs
    all of them, and a refusal that names one at a time is a command run four times.

    **Nothing here stops a gateway.** That is `rundesk gateways stop`, it is a verb that exists, and
    an uninstall quietly ending somebody's live process because it was in the way is a much larger
    decision than this command is entitled to make.
    """
    lines: List[str] = []
    try:
        there = directory.known()
    except OSError as why:
        return [f"the agents could not be listed, so it cannot be told whether a gateway is still "
                f"running: {why}",
                "removing an install under a live gateway takes its database away underneath it"]

    for name in there:
        try:
            how = standing.standing(directory.where(name))
        except directory.Refused as why:
            how = standing.Standing(standing.CANNOT_TELL, None, None, str(why))
        if how.how == standing.ONLINE:
            lines.append(f"a gateway is running for {name}{_as_pid(how.pid)}, and no job of this "
                         f"install's is behind it any more — stop it with: rundesk gateways stop "
                         f"{name}")
        elif how.how == standing.CANNOT_TELL:
            lines.append(f"nobody can tell whether a gateway is running for {name} — {how.why} — "
                         "and unreadable is not a quiet form of offline")

    if not lines:
        return []
    return [*lines,
            "a gateway started with `rundesk gateways run` has no launchd job to take back, and is "
            "stopped in the terminal it is running in"]


def _as_pid(pid: Optional[int]) -> str:
    """` (pid N)`, or nothing when the gateway had nothing readable to say about itself."""
    return f" (pid {pid})" if pid else ""


def _the_jobs(root: Path) -> List[Tuple[str, str]]:
    """Every agent and the label this root derives for it, for saying what a removal would take.

    Nothing is asked of launchd here — a description of a removal must not change anything, and
    what somebody needs to see is the name that would be acted on.
    """
    try:
        there = directory.known()
    except OSError:
        return []
    named = []
    for name in there:
        try:
            named.append((name, job.label_for(name, root)))
        except job.Refused:
            continue
    return named


def _where_the_command_went() -> List[str]:
    """Every directory that might hold this install's command, the recorded one first.

    The install writes down where it put the link, because that directory is chosen at install time
    and can be anywhere. Without it a removal only knows the usual places, so an install linked
    somewhere else leaves a dangling link and says it removed everything.

    The usual places are still searched afterwards, so an install made before this was recorded is
    removed properly too. Every candidate is checked to be *this* install's before it is touched.
    """
    where = []
    try:
        recorded = config.read(paths.data()).get("command_link")
    except config.Unreadable:
        recorded = None
    if recorded:
        where.append(str(Path(recorded).parent))
    where.extend(one for one in tree.BIN_DIRS if one not in where)
    return where


def _needs_confirming(root: Path, purging: bool) -> int:
    """Say exactly what would be removed, and remove nothing.

    Confirmation is a required flag rather than a typed answer at a prompt, because this command has
    to work the same when nobody is watching it: a prompt in a script is a command that hangs, and a
    prompt that falls back to "yes" when there is no terminal is worse than no prompt at all.

    **A gateway that is up is named here too**, rather than only in the refusal a confirmation would
    meet. This is what somebody reads before they decide, and finding out afterwards means they typed
    the confirmation for a removal that was never going to run.
    """
    print(f"uninstall: this would remove rundesk from {root}", file=sys.stderr)
    for name, label in _the_jobs(root):
        # Named one at a time, before the program they point at: a job that outlived its program is
        # a machine starting a command that is gone, at every login.
        print(f"        take   {label} — the gateway job for {name}", file=sys.stderr)
    for line in _the_gateways_still_holding_a_name():
        print(f"        first  {line}", file=sys.stderr)
    print(f"        take   the command, and {paths.app()}", file=sys.stderr)
    if purging:
        print(f"        take   {paths.data()} — everything rundesk kept for you, the agents "
              "included", file=sys.stderr)
    else:
        print(f"        keep   {paths.data()}", file=sys.stderr)
    print(f"        keep   {paths.backups()}", file=sys.stderr)
    print("        nothing was removed. To go ahead:", file=sys.stderr)
    print(f"        rundesk uninstall --confirm{' --purge' if purging else ''}", file=sys.stderr)
    return FAILED


def _purge(data: Path) -> str:
    """Take what the owner accumulated, and say why not when it could not be taken. `""` when it was.

    Only ever the data directory, never a level above it. What was taken is recorded by the caller
    that asked, so this has one answer to give rather than one to give and one to append.
    """
    try:
        shutil.rmtree(data)
    except OSError as why:
        return f"{data} could not be removed: {why}"
    return ""


def _let_go_of_the_lock() -> None:
    """Take rundesk's own lock file, which is bookkeeping rather than anything the owner put there.

    Named here like everything else this command takes, and taken last: it is the file one process
    at a time holds while it changes the install, so nothing that might still want it is running by
    the time this happens. Not announced in what was taken — the owner never put it there and has
    no reason to have heard of it — but removed all the same, because a root left standing over one
    dotfile is a removal that visibly did not finish.
    """
    for one in (paths.lock(), paths.gateway_transition_lock()):
        try:
            one.unlink()
        except OSError:
            pass


def _tidy(root: Path) -> None:
    """Remove the root itself, but only once it is genuinely empty.

    `rmdir` rather than a recursive delete, on purpose: it fails while anything is still there, which
    is exactly the behaviour wanted. A removal that kept the data must leave the directory holding it.
    """
    try:
        root.rmdir()
    except OSError:
        pass


def _failed(why: str, *and_so: str) -> int:
    return failed(f"uninstall: FAILED — {why}", *and_so, "nothing further was removed")
