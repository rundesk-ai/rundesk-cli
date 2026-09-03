"""The copies of what rundesk keeps, and the four things anybody does with them.

`rundesk backups` on its own lists them, because listing is what somebody wants nine times in ten and
a verb they have to remember for it is a verb they will not remember. The other three are named:
`save`, `restore` and `set-location`.

The first group in this product with sub-verbs, and the shape is the same one the top level uses —
each sub-verb registered in this one small function, each answered below, and an unhandled one
raising rather than exiting `0` in silence.

**`restore` asks for `--confirm`.** It replaces everything the owner has accumulated, which puts it
in the same company as `uninstall`, and a flag rather than a prompt for the same reason: a prompt in
a script is a command that hangs, and one that assumes yes with no terminal is worse than none. It
takes a copy of what it replaces regardless, so the confirmation guards the interruption rather than
the loss — but the two together are what make a mistyped name cost nothing.

## And `restore` is where the gateways are stood down, because this is the layer that may ask

`lifecycle.backups` may not import `gateways` — the layer table forbids it, and that module is right
to refuse to break it for `save`, which never changes what a lock's path refers to. **`restore`
differs in exactly that one way**, and the consequence was measured rather than reasoned about: the
swap renames `data/` aside and a fresh copy into its place, so the file `<agent>/gateway.lock` names
is a *new inode* while the running gateway still holds a descriptor on the old one. A copy never
carries a held lock. From that moment every command reads the agent as not running while its process
is alive, the live gateway beats into a record that now resolves inside the restored copy, and a
second gateway can take the lock at that path — two processes each believing they are the one gateway
for that agent, which is the identity failure the whole design exists to prevent.

`commands` may reach `gateways.standing` freely, so that is asked here, **before anything moves**, and
the gateways that were up are stood down and started again in a `finally`.

Standing one down is `commands.gateways`, and reaching it is what `Gateways` is. **That type is
imported from `commands.update` rather than written out a second time here**, which is the
one-domain-verb-one-meaning rule applied to a seam: two verbs that both have to stand a gateway down
must not each carry their own idea of what that is, or the day somebody wires one of them the other
is wired to something subtly different. Nothing is *called* across the group boundary — what is
shared is the shape a caller passes in, and `commands.update` is where its reasoning is kept.

**What is passed in is `commands.gateways.Cycled`, and `cli.main` is what passes it**, because a
restore happens in the process somebody typed the command into and that is the process holding the
supervisor. `update` resolves its own, and only because the settling it wires runs in an interpreter
of its own — one seam, two callers, and each resolved by the one that can.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from rundesk import __version__
from rundesk.agents import directory
from rundesk.commands import Subcommands, failed
from rundesk.commands.update import Gateways
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import standing
from rundesk.lifecycle import backups
from rundesk.utils.terminal import as_table


def register(sub: Subcommands) -> None:
    """Put `backups` on the parser, with one sub-verb for each thing that happens to a copy."""
    kept = sub.add_parser("backups", help="the copies of what rundesk keeps for you")
    what = kept.add_subparsers(dest="what", metavar="<what>")

    what.add_parser("save", help="copy what rundesk keeps, now")

    back = what.add_parser("restore", help="put a copy back, keeping a copy of what it replaces")
    back.add_argument("backup", metavar="<backup>",
                      help="which copy, named as `rundesk backups` lists it")
    back.add_argument("--confirm", action="store_true",
                      help="required — a restore replaces everything rundesk keeps for you")

    moved = what.add_parser("set-location", help="keep the copies in another directory")
    moved.add_argument("path", metavar="<path>", help="the directory to keep them in")


def cmd_backups(args: argparse.Namespace, gateways: Optional[Gateways] = None) -> int:
    """Answer whichever of the four was asked for; with none of them, list what there is.

    `gateways` stands a gateway down and starts it again, and it is resolved by whoever calls rather
    than defaulted in this signature — the same shape `asking` and `fetching` and `supervising` have,
    and for the same reason. `cli.main` builds one from the supervisor it was given, so a restore
    typed at a terminal cycles the gateways that are up rather than refusing while one is; a caller
    inside this codebase that hands nothing in still gets the refusal `_restored` describes, which is
    the honest answer for a restore with no way to free a name. See `Gateways` in `commands.update`.
    """
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    what = getattr(args, "what", None)
    if what is None:
        return _listed()
    if what == "save":
        return _saved()
    if what == "restore":
        return _restored(args.backup, args.confirm, gateways)
    if what == "set-location":
        return _somewhere_else(Path(args.path).expanduser())

    # Unreachable while every sub-verb above is answered, and that is the point: one registered on
    # the parser and wired to nothing fails here loudly rather than exiting 0 having done nothing.
    raise AssertionError(f"backups {what} is registered on the parser and answered by nothing")


def _listed() -> int:
    """Every copy there is, newest first, and where they are kept.

    Where they are kept is printed even when there are none. "No copies" and "no copies *here*" are
    different things to learn, and somebody who has moved theirs to another disk needs to see which
    directory was just found empty.
    """
    at = paths.backups()
    try:
        there = backups.kept(at)
    except backups.Refused as why:
        return _failed(str(why), "nothing was listed")

    print(f"copies in {_where(at)}")
    if not there:
        print("        none yet — make one with: rundesk backups save")
        return OK
    as_table(("BACKUP",), [(one,) for one in there])
    return OK


def _saved() -> int:
    """Copy what rundesk keeps, then let go of the oldest past what the owner asked to keep.

    The copy is reported before anything is let go, and a retention that could not be applied is said
    out loud rather than passed over — but neither changes the exit code, because the operation
    somebody asked for was a copy and the copy is there. Reporting a failure it did not have is the
    mirror of reporting a success it did not earn, and costs the same trust.

    **Records that could not be snapshotted are said, and this command was throwing that away.**
    `save` copies a database it cannot read exactly as it stood — right, because an agent whose
    records are corrupt is still the owner's — and says so through `saying`. No `saying` was passed
    here at all, so the only account of it was discarded and the copy sat in `backups/` looking like
    every other one. `backup_enabled`, `backup_retention` and `update_time` are already in the
    configuration, plainly anticipating a scheduled backup; the moment that lands, a copy of a
    database nobody could read becomes a silent, permanent integrity event.

    **Said on stderr**, because that is the stream an unattended run's output is read from, and
    **without changing the exit code**, for `prune`'s reason above: what was asked for was a copy and
    the copy is there, holding the best of what could be read. An install with one corrupt agent
    would otherwise fail its backup every night for ever, which teaches whoever set it up to stop
    reading the result.
    """
    at, data = paths.backups(), paths.data()
    could_not_be_read: List[str] = []
    try:
        name = backups.save(data, at, saying=could_not_be_read.append)
    except (backups.Refused, OSError) as why:
        return _failed(str(why), "no copy was made")

    print(f"saved {name}")
    print(f"        from   {data}")
    print(f"        in     {_where(at)}")
    _as_they_stood(could_not_be_read)

    try:
        keeping = int(config.read(data)["backup_retention"])
        stuck = backups.prune(keeping, at, saying=lambda line: print(f"        {line}"))
    except (config.Unreadable, backups.Refused, TypeError, ValueError) as why:
        print(f"backups: the copy was saved and nothing was let go — {why}", file=sys.stderr)
        return OK

    for one in stuck:
        print(f"backups: {one} is past the {keeping} copies you keep and would not be removed",
              file=sys.stderr)
    return OK


def _as_they_stood(warnings: List[str]) -> None:
    """Say each save warning, and distinguish copied records from an omitted vanished member.

    Every one of them, never a count: a summary saying "2 agents" hides the one somebody has to look
    at, which is the same reason `update` names each agent it could not carry.

    **This belongs in the install's own journal as well, once there is one.** `data/logs/` is not
    built yet — another change owns it — so until then whoever ran the command is the only record
    that a copy holds records rundesk could not read. When the journal lands, these lines are written
    there too, and that is what makes the fact survive an unattended run nobody was watching.
    """
    for one in warnings:
        print(f"backups: {one}", file=sys.stderr)
    if any("copied as it stood" in one for one in warnings):
        print("        the copy is there and holds those records exactly as they stood — it is a "
              "copy of records rundesk could not read, not a snapshot of working ones",
              file=sys.stderr)


def _restored(name: str, confirming: bool, gateways: Optional[Gateways] = None) -> int:
    """Put a copy back, or — with nothing confirming it — say exactly what that would do.

    **No gateway may be holding an agent's name while the swap happens**, and this is the level that
    can say so — see the module docstring for the measurement. The order is the guarantee, and it is
    `update.carried_every_agent`'s order for the same reason:

    1. **Which gateways are up is asked before anything moves.** So the list of what to start again
       is exactly what was really up, and a gateway the owner had already stopped is never started
       by a restore.
    2. The ones that were up are stood down, and a restore only goes ahead once none is left holding
       a name. One that would not go stops the restore rather than being carried past — a restore is
       one operation over the whole of `data/`, so an agent that could not be freed is not a thing to
       report beside a success.
    3. **Every gateway this command stood down is started again in a `finally`**, so a restore that
       failed still leaves the machine as it found it.
    """
    at, data = paths.backups(), paths.data()
    if not confirming:
        return _needs_confirming(name, at, data)

    stood_down: List[str] = []
    trouble = _the_gateways_stood_down(gateways, stood_down)
    if trouble:
        # Whatever was already stood down goes back up: this call took them down and nothing was
        # restored, so leaving them down would be a refusal that cost more than the operation.
        _the_gateways_started_again(stood_down, gateways)
        return _failed(trouble, "nothing was restored")

    went = OK
    try:
        went = _put_back(name, at, data)
    finally:
        if _the_gateways_started_again(stood_down, gateways):
            # A gateway that was up and is now down is not a detail for a summary. It makes the
            # command non-zero even where the restore itself worked, because the machine was left in
            # a state nobody asked for and somebody has to be told.
            went = FAILED
    return went


def _put_back(name: str, at: Path, data: Path) -> int:
    """The restore itself, with no gateway left holding a name. See `_restored`."""
    try:
        done = backups.restore(name, data, at, saying=lambda line: print(f"        {line}"))
    except backups.HalfRestored as why:
        return _failed(str(why), f"{data} is neither what it was nor what you asked for")
    except (backups.Refused, OSError) as why:
        return _failed(str(why), "nothing was restored")

    # What was kept is not repeated here: `restore` says it before it replaces anything, which is
    # the only ordering under which the name survives a failure partway through.
    print(f"restored {done.name}")
    print(f"        into   {data}")

    if done.settled:
        # The files really are the copy that was asked for, and they have not been carried onto this
        # release. Saying "restored" and exiting 0 here would be a migration that silently never
        # fired — which is the shape of every defect this product is written against.
        return _failed(
            f"the copy is back and could not be settled: {done.settled}",
            f"{data} is the copy you asked for, on a release it has not been carried to.",
            "`rundesk update` settles an install and is safe to run again.")
    return OK


def _the_gateways_stood_down(gateways: Optional[Gateways], stood_down: List[str]) -> str:
    """Stand down every gateway that is up, recording which. `""` when nothing is holding a name.

    `stood_down` is filled in as it goes rather than returned, so the caller's `finally` has the
    exact list even when this gives up partway — which is the case where it matters most.

    **Three answers, not two**, because `standing` gives three. Offline is left alone and costs an
    agent nothing. `CANNOT_TELL` is named and refused rather than quietly read as either: a lock
    nobody can open may well be held, and a restore under one produces exactly the orphaned
    descriptor this whole path exists to prevent — while standing down and starting again cannot be
    exact for it either, there being nothing to be exact about.

    **A caller that hands nothing in is refused with the command to type**, and that is the answer
    rather than a placeholder: the restore has not happened, the owner's data is untouched, and two
    lines of typing is a much smaller cost than a live gateway writing into the copy that was just
    put back. `cli.main` always hands one in, so nothing a person types reaches that branch — what
    reaches it is a caller inside this codebase, and the type says it may.
    """
    try:
        up = _not_plainly_offline()
    except OSError as why:
        return f"the agents could not be listed, so their gateways cannot be stood down: {why}"

    for name, how in up:
        if how.how == standing.CANNOT_TELL:
            return (f"nobody can tell whether a gateway is running for {name} — {how.why} — and "
                    "unreadable is not a quiet form of offline")
        if gateways is None:
            return (f"a gateway is running for {name} and this call was handed nothing that can "
                    f"stand one down — a restore replaces the file that gateway's lock lives on, so "
                    f"it would go on writing into the copy that was just put back. Stop it with: "
                    f"rundesk gateways stop {name}")
        stuck = gateways.down(name)
        if stuck:
            return f"the gateway for {name} would not stand down ({stuck})"
        stood_down.append(name)
        print(f"        stood the gateway for {name} down")
    return ""


def _the_gateways_started_again(stood_down: List[str], gateways: Optional[Gateways]) -> bool:
    """Start again exactly the gateways this command stood down. `True` when one would not start.

    Exactly those: the list started empty and only a gateway a `down` really answered for is ever in
    it, so nothing that was already stopped is ever started by a restore.

    `gateways` cannot be `None` while `stood_down` holds anything — the only way a name gets in there
    is through a seam that answered — and the branch is here because the type says it may be.
    """
    left = False
    for name in stood_down:
        stuck = gateways.up(name) if gateways is not None else "there is nothing here to start one"
        if stuck:
            print(f"backups: the gateway for {name} was stood down for the restore and could not be "
                  f"started again ({stuck})", file=sys.stderr)
            print(f"        start it with: rundesk gateways start {name}", file=sys.stderr)
            left = True
            continue
        print(f"        started the gateway for {name} again")
    return left


def _not_plainly_offline() -> List[Tuple[str, standing.Standing]]:
    """Every agent whose gateway is not known to be down, with how it stands, in name order.

    Two states are in here and the caller keeps them apart: a gateway that is up, and one nobody can
    ask about. What is deliberately not in here is the ordinary case — an agent whose lock nobody
    holds costs a restore nothing, and asking anything else of it would be a price paid for nothing.

    **The kernel is what is asked**, through `gateways.standing`, and never a record a process wrote
    about itself: a gateway that was `SIGKILL`ed reads as offline here with its record still whole,
    which is the only reading a restore can safely act on.

    An agents directory that cannot be read raises rather than answering "none are up" — that is the
    reassuring sentence at the worst possible moment, and the caller turns it into a refusal.
    """
    stood = []
    for name in directory.known():
        try:
            how = standing.standing(directory.where(name))
        except directory.Refused as why:
            # A name that reaches outside where agents are kept. Nobody can say whether a gateway is
            # running for it, which is what `CANNOT_TELL` means, so it is answered as that rather
            # than skipped — a restore that passed over it would be one deciding it was safe on the
            # strength of not having been able to look.
            how = standing.Standing(standing.CANNOT_TELL, None, None, str(why))
        if how.how != standing.OFFLINE:
            stood.append((name, how))
    return stood


def _needs_confirming(name: str, at: Path, data: Path) -> int:
    """Say what a restore would replace, and replace none of it.

    The name is checked against what is actually there first, so somebody who mistyped it finds out
    now rather than after typing the confirmation for a copy that does not exist.

    **A gateway that is up is named here too, as something this restore will do to it.** It used to
    be named as something to go and do first, which was true while nothing could stand one down and
    is now the opposite of what happens: the restore takes them down itself and puts back exactly
    the ones that were up. Somebody deciding whether to confirm is deciding whether their agents may
    stop for the length of a restore, and that is the fact worth having before they type it rather
    than after.
    """
    try:
        backups._a_copy(at, name)
    except (backups.Refused, OSError) as why:
        # `OSError` since a copy that cannot be reached for a moment stopped being read as *not a
        # copy* — see `_a_copy`. Here the only honest answer is the same one: nothing was restored.
        return _failed(str(why), "nothing was restored")

    try:
        up = _not_plainly_offline()
    except OSError:
        # Not a refusal: nothing is being changed, and a description that could not read the agents
        # directory still answers the question that was asked about the copy.
        up = []

    print(f"restore: this would replace {data} with the copy {name}", file=sys.stderr)
    print(f"        keep   a copy of {data} as it is now, before anything is replaced",
          file=sys.stderr)
    print(f"        put    {name} in its place, from {_where(at)}", file=sys.stderr)
    print(f"        settle what comes back onto this release ({__version__})", file=sys.stderr)
    for one, how in up:
        # **Two of the three states are in `up`, and they are described apart.** A gateway that is
        # running is one this restore stands down and starts again; one nobody can ask about is one
        # it refuses over, and telling somebody it would be handled would be describing an operation
        # that is not going to run.
        if how.how == standing.CANNOT_TELL:
            print(f"        stop   nobody can tell whether a gateway is running for {one}, and a "
                  f"restore refuses while that is true — {how.why}", file=sys.stderr)
        else:
            print(f"        stop   the gateway for {one} for the length of it, and start it again "
                  f"after — a restore replaces the file its lock lives on", file=sys.stderr)
    print("        nothing was restored. To go ahead:", file=sys.stderr)
    print(f"        rundesk backups restore {name} --confirm", file=sys.stderr)
    return FAILED


def _somewhere_else(to: Path) -> int:
    """Keep the copies in another directory, and link the old place at it.

    **`HalfRestored` is caught here, and its absence was an unhandled traceback.** `_point_at` raises
    it when the new link could not be made *and* the old one could not be put back, which leaves
    nothing on this machine pointing at where the copies really are — the worst outcome this verb
    has. `cli.main` has no catch-all, so it reached whoever typed the command as a stack trace, in a
    product where every other failure is a worded sentence with what it leaves under it.
    """
    at = paths.backups()
    if backups.location(at).resolve() == to.resolve():
        print(f"rundesk already keeps its copies in {to}")
        return OK

    try:
        landed = backups.relocate(to, at, saying=lambda line: print(f"        {line}"))
    except backups.HalfRestored as why:
        return _failed(str(why), f"{at} points nowhere, so nothing on this machine says where the "
                                 "copies are — the message above is the path to link it at again")
    except (backups.Refused, paths.Refused, OSError) as why:
        return _failed(str(why), "the copies are where they were")

    print(f"rundesk keeps its copies in {landed}")
    print(f"        linked {at} → {landed}")
    return OK


def _where(at: Path) -> str:
    """Where the copies are kept, and where that points when they have been moved elsewhere.

    One string rather than two rows, so the answer to "where are my copies" cannot be read off the
    half of it that is only true until somebody moves them.
    """
    real = backups.location(at)
    return str(at) if real == at else f"{at} → {real}"


def _failed(why: str, *and_so: str) -> int:
    """Say what went wrong, and what that leaves — never one without the other."""
    return failed(f"backups: FAILED — {why}", *and_so)
