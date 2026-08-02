"""Copies of everything the owner keeps, and putting one back.

What goes into a copy is `data_home()` and nothing else — the program is what a release
publishes, so a copy of it is a copy of something already downloadable. A restore borrows
the update worker's window rather than inventing a second one: the same gateways have to be
down for the same reason, and two answers to "is it safe to replace this" would eventually
disagree.
"""

from __future__ import annotations

import argparse
import sys

from rundesk import backup as backups
from rundesk import config
from rundesk import migration
from rundesk import store
from rundesk import updater
from rundesk.commands.update import _out_loud
from rundesk import backups_home, data_home
from rundesk import supervisor as _supervisor
from rundesk import update_worker
from rundesk.commands import _answered_within, _as_table, cmd_not_available

#: How long a command whose whole job is the backups waits for the same directory. Longer
#: than the glance health takes, because here the listing *is* the answer and a slow disk
#: is not an unreachable one — but still bounded, because the directory that blocks never
#: answers at all, and a command that waits forever cannot even name what it is waiting on
#: (R-BKP-29).
BACKUP_PATIENCE = 20.0


def cmd_backups(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Copies of everything this install keeps: what there is, taking one, putting one back.

    The listing is deliberately the bare form, because the question somebody asks after
    trouble is "what have I got" and it should cost them no second word.
    """
    if getattr(args, "where", False):
        # Said by the command rather than written into any prose: this is the one directory
        # an owner may point off the machine entirely, so a guide naming a path would be
        # wrong for exactly the people who moved it.
        print(backups_home())
        return 0
    act = getattr(args, "act", None)
    if act is None:
        return _list_backups()
    if act == "add":
        return _take_a_backup()
    if act == "restore":
        return _restore_a_backup(args, gateways, machine, agents)
    if act == "remove":
        return _remove_a_backup(args)
    if act in ("on", "off"):
        return _daily_backups(act, machine)
    return cmd_not_available(f"backups {act}")


def _remove_a_backup(args: argparse.Namespace) -> int:
    """Delete one copy, by name, having said what it holds."""
    where = backups_home()
    try:
        said = backups.manifest_of(where / args.backup)
    except backups.Unreadable:
        said = None                       # unreadable is exactly what somebody removes
    except backups.Refused as why:
        print(f"backups remove: FAILED — {why}", file=sys.stderr)
        return 1
    if said:
        print(f"{args.backup} holds {len(said.get('records', {}))} agents, "
              f"taken {said.get('taken_at', 'at an unknown moment')}")
    else:
        print(f"{args.backup} cannot be read, so what it holds is unknown")
    if not args.yes and not _agreed():
        print("nothing was removed")
        return 0
    try:
        backups.remove(where, args.backup)
    except (backups.Refused, OSError) as why:
        print(f"backups remove: FAILED — {why}", file=sys.stderr)
        return 1
    print(f"removed {args.backup}")
    return 0


def _daily_backups(act: str, machine) -> int:
    """Hand the daily backup to the machine, or take it back.

    rundesk supervises nothing itself, so this is the machine's job in exactly the way a
    gateway is — and it is the install's rather than any agent's, which is why it is not a
    schedule: a schedule is a row one agent keeps, and a backup that stopped when that agent
    was removed would be a backup nobody noticed had stopped.
    """
    if not machine.available():
        print("backups: there is no supervisor on this machine to hand a daily backup to",
              file=sys.stderr)
        return 1
    if act == "off":
        said = machine.remove_backup()
        if not said.ok:
            print(f"backups off: FAILED — {said.why}", file=sys.stderr)
            return 1
        print("the machine no longer takes a backup every day")
        return 0
    try:
        at = config.backups()["at"]
    except config.Unreadable as why:
        print(f"backups on: FAILED — {why}", file=sys.stderr)
        return 1
    said = machine.install_backup(at)
    if not said.ok:
        print(f"backups on: FAILED — {said.why}", file=sys.stderr)
        return 1
    print(f"the machine will take a backup every day at {at}")
    print(f"        kept for {config.backups()['keep_days']} days, in {backups_home()}")
    return 0


def _restore_a_backup(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Put one back, having said what it will change and been told to go ahead.

    **The window an update already opens is reused rather than a second one invented.**
    Standing every gateway down and refusing while work is in flight is exactly what
    `rundesk update` does before it replaces the files, it is already proved, and a restore
    needs the same thing for the same reason (R-UPD-21, R-UPD-23).
    """
    at = backups_home() / args.backup
    try:
        said = backups.manifest_of(at)
    except (backups.Refused, backups.Unreadable) as why:
        print(f"backups restore: FAILED — {why}", file=sys.stderr)
        return 1
    why = backups.refusals(said)
    if why:
        # Said before anything moves rather than after, which is the whole point of the
        # manifest being readable without unpacking anything.
        print(f"backups restore: REFUSED — {'; '.join(why)}", file=sys.stderr)
        return 1

    data = data_home()
    changing = backups.what_changes(said, data)
    print(f"this replaces everything under {data} with what is in {args.backup}")
    print(f"        taken {said.get('taken_at', 'at an unknown moment')} "
          f"by rundesk {said.get('rundesk', '?')}")
    for what, named in (("comes back", changing["comes_back"]),
                        ("goes away", changing["goes_away"]),
                        ("replaced", changing["stays"])):
        if named:
            print(f"        {what}:  {', '.join(named)}")
    if not args.yes and not _agreed():
        print("nothing was changed")
        return 0

    stopped_by = backups.restore(
        at, data, backups_home(),
        busy=lambda: update_worker._in_flight(gateways, agents),
        pause=lambda: update_worker._stand_all_down(gateways, machine, agents),
        resume=lambda names: update_worker._bring_all_back(names, gateways, machine, agents),
        carry=lambda incoming: migration.carry_every_or_put_back(
            incoming / "agents", store.VERSION, aside=incoming / ".carrying",
            note=_out_loud),
        note=_out_loud,
    )
    if stopped_by:
        print(f"backups restore: NOT DONE — {stopped_by}", file=sys.stderr)
        return 1
    print(f"put back {args.backup}")
    return 0


def _agreed() -> bool:
    """Ask, and take anything that is not yes as no.

    Never assumed from a pipe: a restore that went ahead because nothing was attached to
    answer is the failure this whole command is careful about.
    """
    try:
        return input("continue? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _take_a_backup() -> int:
    """Take one now, and say where it went and what it cost."""
    try:
        at = backups.take(data_home(), backups_home(), note=_out_loud)
    except (backups.Refused, config.Unreadable) as why:
        print(f"backups add: FAILED — {why}", file=sys.stderr)
        return 1
    except OSError as why:
        # The destination may be a disk that is not plugged in or a cloud directory that
        # will not answer, which is a different thing from having nothing to back up.
        print(f"backups add: FAILED — {backups_home()} could not be written to: {why}",
              file=sys.stderr)
        return 1
    said = backups.manifest_of(at)
    print(f"took a backup: {at}")
    print(f"        {len(said['records'])} agents, {updater.readable(at.stat().st_size)}")
    if said.get("copied_whole"):
        # Never silent. A copy that is not a consistent copy is still worth having and is
        # not the same thing, and the only moment anybody can act on the difference is now.
        for one in said["copied_whole"]:
            print(f"        WARNING: {one} could not be copied consistently and is in the "
                  f"backup exactly as it is on disk", file=sys.stderr)
    # Pruned here rather than on a second schedule of its own: the thing that makes an old
    # copy old is a newer one arriving, so this is the moment the question has a new answer,
    # and a machine that has stopped taking backups stops deleting them too.
    # Bounded like every other reading of this directory: the copy is already written and
    # safe, so a directory that stops answering costs the tidying and never the backup
    # itself, and the command says which of the two happened (R-BKP-29).
    keep_days = config.backups()["keep_days"]
    reached, gone = _answered_within(
        BACKUP_PATIENCE,
        lambda: backups.prune(backups_home(), keep_days, note=_out_loud),
        "rundesk-backups-prune",
    )
    if not reached:
        print(f"        WARNING: {backups_home()} did not answer within "
              f"{BACKUP_PATIENCE:.0f}s, so older copies were left as they are",
              file=sys.stderr)
    elif gone:
        print(f"        {len(gone)} older than {keep_days} days were removed")
    return 0


def _list_backups() -> int:
    """Every copy there is, oldest first, with what each cost and what it holds."""
    where = backups_home()

    def describe() -> list:
        # Read and described inside the bound together, because the size of each copy is
        # a `stat` of its own: a directory that answers `opendir` and then blocks on the
        # files in it would otherwise hang after the guard had already let go (R-BKP-29).
        return [(
            one.at.name,
            one.taken_at if one.readable else "-",
            updater.readable(one.held_bytes) if one.held_bytes is not None else "-",
            str(len(said.get("records", {}))) if one.readable else "-",
            said.get("why", "-") if one.readable else "UNREADABLE",
            one.why if not one.readable else None,
        ) for one, said in ((one, one.said or {}) for one in backups.every(where))]

    reached, rows = _answered_within(BACKUP_PATIENCE, describe, "rundesk-backups-list")
    if not reached:
        # Named, and never answered with the empty listing. "There are no backups" and
        # "the place they are kept did not answer" send an owner somewhere completely
        # different, and only one of them means their agents are unprotected (R-BKP-29).
        print(f"backups: FAILED — {where} did not answer within "
              f"{BACKUP_PATIENCE:.0f}s, so what is kept there is unknown", file=sys.stderr)
        return 1
    if not rows:
        print("no backups")
        print(f"        take one:  rundesk backups add")
        return 0
    _as_table(("BACKUP", "TAKEN", "SIZE", "AGENTS", "WHY"), [row[:5] for row in rows])
    print()
    print(f"kept in {where}")
    for row in rows:
        if row[5] is not None:
            print(f"        {row[0]}: {row[5]}", file=sys.stderr)
    return 0
