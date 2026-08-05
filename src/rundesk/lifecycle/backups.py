"""Copies of what the owner keeps, and where they are kept.

A copy is the whole of `data/` under a name that says when it was made. Four things happen to them —
they are listed, one is made, one is put back, and the directory holding them is moved somewhere with
more room — and every one of them is written around the same fear: **a copy is the thing somebody
reaches for on the worst day they have had with this product.** Anything that leaves one damaged,
half-written, or quietly absent has failed at the only moment it existed for.

## A copy that did not finish is never named like one that did

Every copy is built under a `.incoming` name and renamed into place only once all of it is there, so
nothing in `backups/` under a copy's name is ever partial. This is the layer's shared convention and
the reasoning is in `lifecycle/__init__.py`; it matters more here than anywhere else it is used,
because a half-copy that is *named* like a finished one is worse than no copy at all — it is the one
that gets restored.

## Putting one back keeps what it replaces

A restore replaces everything the owner has accumulated, from a name they typed. So it takes a copy
of what is there **first**, before anything is replaced, and says what that copy is called. The
restore is then a thing that can be undone, which a restore otherwise is not.

## What comes back may be older than this release

Data that was copied three releases ago is data this release has never carried forward, so putting it
back is not finished when the files land: the restored `config.json` carries the *copy's* migration
mark, which may be behind. So a restore settles what it restored — it fills in settings this release
has added, and it carries the migration steps the copy never ran.

**This is the one place settling does not need its own interpreter.** An update hands off because the
process doing the replacing is still running the release being replaced, and would otherwise run the
previous release's steps. A restore replaces data and not code: the process doing it is already the
release that has to settle the result, so it settles it in place.

## Where they are kept is a link, not a second variable

`set-location` moves the copies to another disk and links `backups/` at the new place. It is a link
on purpose. `RUNDESK_HOME` stays the one location this product reads and `paths.backups()` keeps
answering `<root>/backups`, so the copies can live anywhere without there being a second place to
look — which is the defect this whole rebuild exists to have removed.
"""

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional

from rundesk.core import config, paths
from rundesk.lifecycle import migration
from rundesk.utils import files, locking

#: What a copy is called: the moment it was made, to the second, in UTC.
#:
#: Hyphens where a clock has colons, because a colon in a filename is a path separator to some tools
#: and a directory Finder will not show you to others. The shape sorts lexically into the order it
#: happened, which is what lets "newest first" be a `sorted()` and not a parse.
WHEN = "%Y-%m-%dT%H-%M-%SZ"

#: What counts as a copy. Nothing else in the directory is ever listed, moved, put back or removed —
#: an owner may keep their own things in here and rundesk is not entitled to any of them.
NAMED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z(-\d{2})?$")

#: What the note in a copy has to be for the copy to be one: every install writes `config.json`, so a
#: directory without a readable one is not a copy of an install's data whatever it is called.
THE_MARK = "config.json"


class Refused(Exception):
    """Something that must not be done to somebody's copies, named with why."""


class HalfRestored(Exception):
    """A restore failed and putting back what was there failed too.

    Its own exception because there is no clever recovery left to attempt: `data/` is neither what it
    was nor what was asked for. What makes this survivable is the copy taken before any of it
    started, and the only honest thing to say is which copy that is.
    """


class Restored(NamedTuple):
    """What a restore did, in the three parts that can differ.

    Three fields rather than a bare success, because they are three separate answers and a caller
    that collapses them reports something it did not do. `settled` being a reason rather than `None`
    is the case that matters: the data really is the copy that was asked for, and it has not been
    carried forward onto this release. Saying "restored" there would be the exact shape of failure
    this product is built to refuse.
    """

    name: str
    safety: Optional[str]
    settled: Optional[str]


def _one_at_a_time():
    """Hold the install while this operation moves directories about.

    **Every operation here renames or removes a whole directory, and none of them was serialised
    against anything.** `files` locks one file at a time, which is the wrong shape for this:
    `_swap` renames `data/` aside and back, and in the moment between those two renames the
    directory does not exist — so a `configure` landing there calls `mkdir(parents=True)` on the way
    to writing `config.json`, recreates `data/` from nothing, reports an ordinary success, and is
    then deleted by the restore's own rollback. A command that earned its success, silently taken
    back by a different command. Two concurrent `save` calls were no better: both computed the same
    name, both staged into it, and each discarded the other's half-written copy, so the pair of them
    produced nothing at all.

    Re-entrant, and it must be: `restore` holds this and then settles the install, which writes the
    configuration, which takes it again. `flock` is held per open file description, so a second
    `open` in the same process conflicts with the first exactly as another process would.
    """
    return locking.only_one(paths.lock(), "this install")


def location(backups: Optional[Path] = None) -> Path:
    """Where the copies really are, which is not where they are kept once they have been moved.

    `paths.backups()` answers where rundesk *looks*; this answers where the bytes are. They differ
    exactly when `set-location` has been used, and telling somebody the first when they asked the
    second is how a person comes to believe their copies are on the disk that just filled up.
    """
    at = backups or paths.backups()
    return at.resolve() if at.is_symlink() else at


def kept(backups: Optional[Path] = None) -> List[str]:
    """Every copy there is, newest first.

    **Nothing there and unable to look are different answers.** Nobody having made a copy is an
    ordinary empty list; a directory that cannot be read is raised, because answering "no copies" for
    it tells somebody their backups are gone at the moment they are merely unreachable — and the next
    thing that person does is make decisions on it.
    """
    at = backups or paths.backups()
    _reachable(at)
    try:
        there = [one.name for one in at.iterdir()
                 if not files.staged(one.name) and NAMED.match(one.name) and one.is_dir()]
    except FileNotFoundError:
        return []
    except OSError as why:
        raise Refused(f"{at} is there and cannot be read: {why}") from why
    return sorted(there, reverse=True)


def _reachable(at: Path) -> None:
    """Refuse when the copies cannot be reached at all, as distinct from there being none.

    **A third answer, and the one `set-location` created.** Once the copies can live on another disk,
    `backups/` is a link — and a link to a disk nobody has plugged in gives `FileNotFoundError` from
    every walk of it, which is the same thing a directory nobody has ever copied into gives. Reading
    the first as the second tells somebody their backups do not exist at the moment they are merely
    unplugged, and what that person does next is make a decision on it: take a fresh copy over
    nothing, or believe the copy they are trying to restore was never made.

    `status` already told these apart; nothing else did, because this function did not exist and the
    answer was being worked out in one command instead of at the level every command reads from.
    """
    if at.is_symlink() and not at.resolve().is_dir():
        raise Refused(
            f"{at} points at {at.resolve()}, which is not there — the copies are not gone, and "
            "this is not an install that has never made one")


def named(when: Optional[datetime] = None, backups: Optional[Path] = None) -> str:
    """What the next copy will be called: the moment it is made, and a counter only if that is taken.

    `when` arrives as an argument and is resolved here rather than in the signature, so a caller can
    ask for an exact name and a default bound at import cannot get between them.

    The counter is two digits so that a name with one still sorts after the name without it and
    before the next second — `-2` would sort before `-10` and quietly put "newest first" in the wrong
    order. Ninety-nine copies inside one second is past what copying a directory tree can do, and the
    hundredth is refused rather than named something that sorts wrongly.
    """
    at = backups or paths.backups()
    stamp = (when or datetime.now(timezone.utc)).strftime(WHEN)
    if not (at / stamp).exists():
        return stamp
    for again in range(2, 100):
        taken = f"{stamp}-{again:02d}"
        if not (at / taken).exists():
            return taken
    raise Refused(f"there are already a hundred copies made in the second {stamp} names")


def save(data: Optional[Path] = None, backups: Optional[Path] = None,
         when: Optional[datetime] = None) -> str:
    """Copy what the owner keeps, and hand back what the copy is called.

    Staged under a name no copy has and renamed into place once all of it is there, so an
    interruption leaves litter rather than a copy that is not one.

    Removes nothing. What is kept and what is let go is `prune`, asked for separately, because the
    caller that wants a copy and the caller that wants a tidy directory are not always the same one —
    a restore takes a copy of what it is about to replace, and that copy must not be able to push
    the copy being restored out of the retention it never asked about.
    """
    from_where = data or paths.data()
    at = backups or paths.backups()
    if not from_where.is_dir():
        raise Refused(f"there is nothing to copy: {from_where} is not there")
    # The one entry point this guard did not reach. `mkdir(exist_ok=True)` still raises on a broken
    # link — the directory *entry* is there — so an unplugged disk came out of the most-likely-to-be
    # -unattended operation as a raw `[Errno 17] File exists`, while every other verb said plainly
    # what had happened.
    _reachable(at)

    at.mkdir(parents=True, exist_ok=True)
    with _one_at_a_time():
        # The name and the staging under it are one decision: worked out separately, two callers
        # land on the same second, stage into the same directory, and discard each other's work.
        name = named(when, at)
        pending = at / files.INCOMING.format(name=name)
        files.discard(pending)
        try:
            shutil.copytree(from_where, pending, symlinks=True)
            os.rename(pending, at / name)
        except Exception:
            files.discard(pending)
            raise
    return name


def prune(keeping: int, backups: Optional[Path] = None,
          saying: Optional[Callable[[str], None]] = None) -> List[str]:
    """Let go of the oldest copies past the number asked for. Returns the ones it could not remove.

    The only thing in this product that removes a copy, which is why it is this narrow: it considers
    **only** names that are copies, never sweeps the directory, and works from the oldest end of a
    list it sorted itself.

    Fewer than one is refused rather than obeyed. `configure` will not accept it, so the only way to
    arrive here with a zero is by a route nobody designed — and obeying it would remove every copy
    the owner has, immediately, on the strength of a number nothing checked.

    What it could not remove is returned rather than raised: the copy the caller asked for has
    already landed, and turning that into a failure would report the wrong outcome for the operation
    somebody actually ran. It still has to be said out loud, which is what returning it is for.
    """
    if keeping < 1:
        raise Refused(f"keeping fewer than one copy is not a retention, and was {keeping}")
    at = backups or paths.backups()
    said = saying or (lambda _line: None)

    # **Only copies that could actually be put back are counted, and only those are let go of.**
    # Retention is a promise about how many copies you have, and a directory that cannot be restored
    # is not one of them however it is named. Counting it meant an unreadable copy could sit at the
    # newest end of the list and evict the last good one — the owner asked to keep one copy and was
    # left with the only one that does not work.
    #
    # The broken ones are left alone rather than swept: they are still the owner's, rundesk cannot
    # say what is in them, and quietly deleting a directory because a file inside it would not parse
    # is not a decision this command is entitled to make. `save` says when it has made one.
    stuck = []
    with _one_at_a_time():
        for name in [one for one in kept(at) if restorable(at, one)][keeping:]:
            try:
                shutil.rmtree(at / name)
                said(f"let go of {name}")
            except OSError:
                stuck.append(name)
    return stuck


def restorable(at: Path, name: str) -> bool:
    """Whether this copy could actually be put back, as opposed to merely being named like one.

    The question retention has to ask before it lets anything go, and the question a listing has to
    ask before it lets somebody believe they are covered.
    """
    where = at / name
    return where.is_dir() and _has_the_mark(where)


def restore(name: str, data: Optional[Path] = None, backups: Optional[Path] = None,
            when: Optional[datetime] = None, steps: Optional[Path] = None,
            saying: Optional[Callable[[str], None]] = None) -> Restored:
    """Put a copy back, keeping a copy of what it replaces, and settle what comes back.

    In that order, and the order is the guarantee. What is there now is copied **before** anything is
    replaced, so a restore of the wrong name — the thing somebody does at four in the morning — costs
    a command rather than everything they had.

    The copy is checked to be one before any of that starts. A directory with no readable
    `config.json` is not an install's data however it is named, and putting it back would leave
    rundesk unable to tell how far it has been carried: `migration` would read as unset, and the next
    thing to look would run every step this release ships over data that may already have had them.

    `steps` is where the migration steps are, passed straight through and defaulted by `migration`
    itself — the same escape hatch that module already offers, and for the same reason: a guarantee
    about carrying restored data forward that can only be driven by whichever steps a release happens
    to ship is a guarantee nothing proves on the day the directory is empty.
    """
    at = backups or paths.backups()
    into = data or paths.data()
    said = saying or (lambda _line: None)

    with _one_at_a_time():
        return _put_back_now(name, at, into, when, steps, said)


def _put_back_now(name, at, into, when, steps, said) -> Restored:
    """The restore itself, with the install already held. See `restore`."""
    a_copy = _a_copy(at, name)
    safety = save(into, at, when) if into.is_dir() else None
    if safety:
        # Said **before** anything is replaced, not in a summary afterwards. Every failure from here
        # on is one where knowing this name is the way back, and a summary is exactly the thing that
        # does not get printed when something goes wrong on the line above it.
        said(f"kept {safety} — a copy of {into} as it was")

    try:
        _swap(a_copy, into)
    except HalfRestored as why:
        # The one failure with nothing left to try, so the message has to carry the way out of it.
        # Naming the copy here rather than where the swap gave up, because this is the level that
        # knows there is one: `_swap` replaces a directory and has never heard of a safety copy.
        raise HalfRestored(f"{why}, and that copy is {safety}") from why
    return Restored(name, safety, _settle(into, steps, said))


def relocate(to: Path, backups: Optional[Path] = None,
             saying: Optional[Callable[[str], None]] = None) -> Path:
    """Keep the copies somewhere else, and link the old place at the new one. Returns where they are.

    **Copied to the new place first, and taken from the old one only once every one of them is
    there.** The failure that cannot lose anything therefore happens first: a move that dies partway
    has written some copies to a second disk and removed none, which is a tidying job. The other
    order has no such reading.

    The old directory itself is removed only when it was the install's own — the one being replaced
    by the link. A directory the owner named and pointed rundesk at is left standing and empty,
    because rundesk was told to keep its copies elsewhere and was not told the directory was its to
    delete.
    """
    at = backups or paths.backups()
    said = saying or (lambda _line: None)
    with _one_at_a_time():
        return _moved_now(to, at, said)


def _moved_now(to: Path, at: Path, said: Callable[[str], None]) -> Path:
    """The move itself, with the install already held. See `relocate`."""
    now_at = location(at)
    # Nothing to copy and nothing reachable to copy are different: the second would move no copies,
    # re-point the link, and leave every one of them orphaned on the old disk reporting success.
    _reachable(at)
    # **Kept, not merely asked.** `allowed` hands back the canonical form, and the whole reason it
    # does is that a value which passed the check and then went on being used as typed can still
    # resolve somewhere else afterwards. Throwing it away here meant the guard proved one path safe
    # and the link was made to another — the exact half-fix the resolving was introduced to close.
    to = paths.allowed(to, "the backups location")

    if to.exists() and not to.is_dir():
        raise Refused(f"{to} is not a directory")
    if _inside(to, now_at) or _inside(now_at, to):
        raise Refused(f"{to} and {now_at} stand inside one another — copies cannot be moved there")
    if to.is_dir() and any(to.iterdir()):
        raise Refused(f"{to} already has something in it, and rundesk moves copies only into an "
                      "empty directory or one that is not there yet")

    to.mkdir(parents=True, exist_ok=True)
    moved = _copy_across(now_at, to, said)

    absent = [one for one in moved if not (to / one).exists()]
    if absent:
        # Never reached while a rename that returned means the entry is there — and checked anyway,
        # because what comes next removes the originals and this is the sentence that earns it.
        raise Refused(f"{absent[0]} is not at {to} after being moved there — nothing was removed")

    _point_at(at, to)
    for one in _could_not_remove(now_at, moved) if now_at != at else []:
        said(f"{one} is still at {now_at} and could not be removed")
    if now_at == at:
        files.discard(at.parent / files.OUTGOING.format(name=at.name))
    return to


def _copy_across(now_at: Path, to: Path, said: Callable[[str], None]) -> List[str]:
    """Copy everything in the old place to the new one, taking back what landed if any of it fails.

    **Everything, not only the copies.** A move that carried the copies and left the owner's own
    files behind has reported a move it did not make, and the directory it left them in is the one
    about to be replaced by a link.

    What it has already written is taken back on failure so the same move can be asked for again;
    only names this call has just created are ever removed.
    """
    landed: List[str] = []
    try:
        for entry in sorted(now_at.iterdir()) if now_at.is_dir() else []:
            if files.staged(entry.name):
                continue
            os.rename(files.stage_copy(entry, to), to / entry.name)
            landed.append(entry.name)
            said(f"moved {entry.name}")
    except Exception:
        _could_not_remove(to, landed)
        raise
    return landed


def _point_at(at: Path, to: Path) -> None:
    """Make `backups/` a link to where the copies are now, whatever it was before.

    The old directory is renamed aside rather than removed, and put back if the link cannot be made:
    between removing a directory and creating a link there is a moment with neither, and this product
    has already been bitten once by a window exactly that size.
    """
    if at.is_symlink():
        # The same window as below, and it was missed here the first time round precisely because
        # this is the branch that only runs the *second* time somebody moves their copies. Losing
        # the link is worse here than losing the directory would be: the copies are still on the old
        # disk, and nothing left on this machine says where.
        was = os.readlink(str(at))
        at.unlink()
        try:
            at.symlink_to(to)
        except OSError as why:
            try:
                at.symlink_to(was)
            except OSError as also:
                # Both the new link and putting the old one back failed, so there is now no link at
                # all where the copies were reached through. Swallowing this was the worse bug of
                # the two: a missing directory is not a broken symlink, so `_reachable` never fires
                # on it, `kept` legitimately answers "none", and the owner is told they have no
                # copies while every one of them sits intact on the other disk.
                raise HalfRestored(
                    f"{at} no longer points anywhere ({why}), and could not be pointed back at "
                    f"{was} either ({also}) — the copies are still there, and this is the path to "
                    "link it at again") from also
            raise
        return

    aside = at.parent / files.OUTGOING.format(name=at.name)
    files.discard(aside)
    if at.exists():
        os.rename(at, aside)
    at.parent.mkdir(parents=True, exist_ok=True)
    try:
        at.symlink_to(to)
    except OSError:
        if aside.exists():
            os.rename(aside, at)
        raise


def _could_not_remove(where: Path, names: List[str]) -> List[str]:
    """Remove exactly these entries and no others. Returns the ones that would not go.

    Named for what it returns because that is the part a caller has to say out loud. It is only ever
    handed names this operation has just written or has just proved are somewhere else, which is what
    makes removing them something rundesk is entitled to do at all.
    """
    stuck = []
    for name in names:
        one = where / name
        try:
            if one.is_dir() and not one.is_symlink():
                shutil.rmtree(one)
            elif one.exists() or one.is_symlink():
                one.unlink()
        except OSError:
            stuck.append(name)
    return stuck


def _a_copy(at: Path, name: str) -> Path:
    """The copy by that name, refusing anything that is not one this release can put back.

    Three separate refusals rather than one "no": a name that is not a copy's shape, a name nobody
    has made, and a directory that is there and is not a copy of an install's data are three
    different mistakes, and the person reading has to know which one they made.
    """
    if not NAMED.match(name):
        raise Refused(f"{name} is not the name of a copy — `rundesk backups` lists what there is")
    # Before "there is no copy called that": on an unplugged disk every name is missing, and telling
    # somebody their copy does not exist is the worst available answer at the worst moment.
    _reachable(at)
    where = at / name
    if not where.is_dir():
        raise Refused(f"there is no copy called {name} in {at}")
    if not _has_the_mark(where):
        raise Refused(
            f"{name} has no readable {THE_MARK}, so it is not a copy of an install's data — "
            "putting it back would leave rundesk unable to tell how far it has been carried")
    return where


def _has_the_mark(where: Path) -> bool:
    """Whether this directory holds a readable `config.json`, which is what makes it a copy.

    **One definition, asked by everything that has an opinion about what a copy is.** It used to be
    asked only on the restore path, and the result was three functions quietly disagreeing: `kept`
    and `prune` counted anything shaped like a name, `_a_copy` refused anything without the mark.
    A copy that could not be put back therefore sat at the top of the list, counted towards the
    number the owner asked to keep, and pushed a real one out. See `restorable`.
    """
    how, said = files.read_json(where / THE_MARK)
    return how == files.READ and isinstance(said, dict)


def _swap(a_copy: Path, into: Path) -> None:
    """Replace `data/` with the copy, and put back what was there if any part of it fails.

    The same shape as replacing the program, for the same reason: the copy is built beside what it
    replaces and only renamed over it once all of it is there, so an interruption leaves `data/` as
    it was rather than as neither.
    """
    pending = into.parent / files.INCOMING.format(name=into.name)
    aside = into.parent / files.OUTGOING.format(name=into.name)
    into.parent.mkdir(parents=True, exist_ok=True)
    files.discard(pending)
    files.discard(aside)

    try:
        shutil.copytree(a_copy, pending, symlinks=True)
    except Exception:
        files.discard(pending)
        raise

    swapped = False
    try:
        if into.exists() or into.is_symlink():
            os.rename(into, aside)
            swapped = True
        os.rename(pending, into)
    except Exception:
        files.discard(pending)
        if swapped:
            _put_back(aside, into)
        raise
    files.discard(aside)


def _put_back(aside: Path, into: Path) -> None:
    """Undo a half-finished swap, or say that it could not be undone."""
    try:
        files.discard(into)
        os.rename(aside, into)
    except OSError as why:
        raise HalfRestored(
            f"{into} could not be put back ({why}) — what was there is at {aside}, and the copy "
            "taken before this started is the one to restore from") from why


def _settle(into: Path, steps: Optional[Path], said: Callable[[str], None]) -> Optional[str]:
    """Carry what came back onto this release. `None` when it is settled, otherwise why it is not.

    Two things, in this order: settings this release has added that the copy predates, and then the
    migration steps the copy never ran. Filling in first because a step is entitled to read the
    configuration, and a step written against a value this release introduced would otherwise find it
    missing on exactly the installs the step exists for.

    **Both under one guard, not just the first.** Every write here goes through the configuration —
    including the stamp each migration step lands with — so `carry` can give the same two answers
    `fill_in` can, and it reads the file before it runs anything. Catching only around the first call
    leaves the second free to come out as a traceback, and it would do it *after* `data/` had already
    been replaced: the loudest possible failure at the quietest possible moment, with the copy taken
    of what was there going unmentioned because nothing got as far as printing it. `update.settle`
    catches the pair in one place for this reason and this is the same shape of call.
    """
    try:
        config.fill_in(into)
        return migration.carry(into, steps, said)
    except (config.Unreadable, config.Refused, config.Stuck, ValueError) as why:
        return str(why)


def _inside(child: Path, parent: Path) -> bool:
    """Whether one directory stands at or below another, compared as the filesystem resolves them.

    Resolved rather than compared as typed: `/tmp/x` and `/tmp/./x/../x` are the same directory, and
    a check that says otherwise is a check that lets a copy be moved inside itself.
    """
    settled, above = child.resolve(), parent.resolve()
    return settled == above or above in settled.parents
