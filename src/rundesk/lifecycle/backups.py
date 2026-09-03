"""Copies of what the owner keeps, except provider-owned credential homes, and where they are kept.

A copy is the whole of `data/` under a name that says when it was made. New copies are compressed ZIP
archives; v0.40 directory copies remain valid restore inputs. Four things happen to them — they are
listed, one is made, one is put back, and the directory holding them is moved somewhere with more
room — and every one of them is written around the same fear: **a copy is the thing somebody reaches
for on the worst day they have had with this product.** Anything that leaves one damaged,
half-written, or quietly absent has failed at the only moment it existed for.

## A copy that did not finish is never named like one that did

Every data snapshot is built in a private directory on the configured backup filesystem. Its ZIP is
written beside the destination under a `.incoming` name through an interface that cannot seek, then
verified there and renamed into place. Nothing in `backups/` under a copy's name is ever partial.
This is the layer's shared convention and the reasoning is in `lifecycle/__init__.py`; it matters
more here than anywhere else it is used, because a half-copy that is *named* like a finished one is
worse than no copy at all — it is the one that gets restored.

## Putting one back keeps what it replaces

A restore replaces everything the owner has accumulated, from a name they typed. So it takes a copy
of what is there **first**, before anything is replaced, and says what that copy is called. The
restore is then a thing that can be undone, which a restore otherwise is not.

## A copy taken while an agent is live is consistent, and never refused

`data/` holds a SQLite database per agent now, and a gateway holds one of those open for days at a
time. Copying a database's bytes while somebody is writing to it is the torn-snapshot problem, and
here it is the **owner's backup** that is torn: `-wal` and `-shm` are copied at a different instant
from the database they belong to, so a restore puts back a write-ahead log that may not match its
database — which the next connection reads as that database's most recent truth.

**Consistent, and not refused, and the reasoning is two things rather than a preference.**

A backup somebody can only take with every gateway stopped is a backup nobody takes. That is the
whole of the product argument, and it is decided the same way `uninstall` decides what it names: the
operation has to work on an ordinary machine on an ordinary day.

And **this layer structurally cannot ask whether a gateway is running.** `lifecycle` may reach down
to `agents`, `core` and `utils`, and it may not reach across to `gateways` — checked by
`tests/test_layers.py`, not merely written down. So "refuse while a gateway holds it" is not a
policy that could be written here without inverting the tree, and a rule that would have to be
broken to be obeyed is the wrong rule.

**And this is true of `save` and false of `restore`, which is not a detail.** A copy taken under a
live gateway is a *read*: the lock file goes on being the file it was, the gateway's descriptor goes
on referring to the inode it referred to, and nothing the copy does can be noticed by the process
holding it. See `restore` for what changes when the same reasoning is carried across to putting one
back — it is the one operation here that changes what an agent's lock file *is*, and it is refused at
the layer that may ask rather than here.

SQLite documents the answer, and it is the one used: **the online backup API takes a consistent
snapshot of a live database**, from a read-only connection, without writing a byte to the original.
`docs/research/2026-07-26-sqlite-store-and-migrations.md` measured the surrounding behaviour on this
platform — WAL is sticky, readers do not block writers, and the busy timeout is the binding's rather
than anybody's decision — and the snapshot was measured here on both this project's 3.9 floor and a
current interpreter.

**The `-wal` and `-shm` are handled by name and never incidentally.** Both are removed from the copy
— named through `agents.records.beside`, which exists so that nothing globs for them — because a
sidecar copied at a different instant from its database is exactly the disagreement being removed.
What a copy keeps beside the snapshot is a **write-ahead log holding nothing, written here rather
than carried across**: measured, a WAL database standing alone with neither sidecar cannot be opened
read-only by the SQLite the 3.9 floor ships, and would be unreadable on the oldest machine this
product supports while looking perfectly fine on the newest. `_an_empty_log` has the measurement and
the rest of the reasoning. The shared-memory index is never kept at all.

**A database that cannot be read is copied as it stood, and said out loud.** An agent whose records
are corrupt is still the owner's, and a backup is the thing they reach for on the worst day they
have had — refusing to copy it, or dropping it, would be this command deciding what is worth keeping.

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

import contextlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import (
    BinaryIO,
    Callable,
    ContextManager,
    Dict,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Tuple,
)

from rundesk.agents import directory, records
from rundesk.agents import migration as agent_migration
from rundesk.core import config, paths, secrets
from rundesk.lifecycle import migration
from rundesk.utils import files, locking

#: What a copy is called: the moment it was made, to the second, in UTC.
#:
#: Hyphens where a clock has colons, because a colon in a filename is a path separator to some tools
#: and a directory Finder will not show you to others. The shape sorts lexically into the order it
#: happened. The suffix now distinguishes archive from directory, so ordering parses this value
#: rather than trusting the whole stored name lexically.
WHEN = "%Y-%m-%dT%H-%M-%SZ"

#: What counts as a copy. Nothing else in the directory is ever listed, moved, put back or removed —
#: an owner may keep their own things in here and rundesk is not entitled to any of them.
NAMED = re.compile(
    r"^(?P<when>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)"
    r"(?:-(?P<again>\d{2}))?(?P<archive>\.zip)?$")

#: The contract at the root of every archive this release writes and reads.
MANIFEST = "manifest.json"
FORMAT = "rundesk-backup"
FORMAT_VERSION = 1
DATA_PREFIX = "data/"

#: Archives from before the v0.40 rebuild used another layout. A matching name is called out rather
#: than reported missing, because guessing at old backup compatibility is a destructive mistake.
OLD_ARCHIVE = re.compile(r"^rundesk-data-.*\.zip$")

#: The write-ahead log, as `agents.records` names it — the first of the two files SQLite keeps
#: beside a database, the other being the shared-memory index. Named here rather than reached for by
#: position because a copy keeps one of them and never the other, and `tests/test_backups.py`
#: asserts this really is the log so a reordering there goes red instead of silently swapping which
#: file every copy carries.
WAL = records.SIBLINGS[0]

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


def _one_at_a_time(root: Path) -> ContextManager[None]:
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

    **`root` says which install**, and it is derived from the directory the caller was handed rather
    than from `RUNDESK_HOME`. An operation given somewhere to work that reaches outside it to take a
    lock is the defect this rebuild exists to have removed, in miniature — and it really happened:
    a call passed an explicit directory and left a lock file in a live install nothing else in that
    run went near.

    Re-entrant, and it must be: `restore` holds this and then settles the install, which writes the
    configuration, which takes it again. `flock` is held per open file description, so a second
    `open` in the same process conflicts with the first exactly as another process would.
    """
    return locking.only_one(paths.lock(root), "this install",
                            locking.WHILE_A_DIRECTORY_MOVES)


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
                 if not files.staged(one.name) and _identity(one.name) is not None
                 and ((one.name.endswith(".zip") and one.is_file())
                      or (not one.name.endswith(".zip") and one.is_dir()))]
    except FileNotFoundError:
        return []
    except OSError as why:
        raise Refused(f"{at} is there and cannot be read: {why}") from why
    return sorted(there, key=lambda name: _identity(name), reverse=True)


def _identity(name: str) -> Optional[Tuple[datetime, int]]:
    """The chronological identity carried by a directory or archive name."""
    matched = NAMED.fullmatch(name)
    if matched is None:
        return None
    try:
        made = datetime.strptime(matched.group("when"), WHEN).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return made, int(matched.group("again") or "1")


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
    if not _taken(at, stamp):
        return f"{stamp}.zip"
    for again in range(2, 100):
        taken = f"{stamp}-{again:02d}"
        if not _taken(at, taken):
            return f"{taken}.zip"
    raise Refused(f"there are already a hundred copies made in the second {stamp} names")


def _taken(at: Path, stem: str) -> bool:
    """Whether either representation has reserved this chronological identity."""
    directory_copy = at / stem
    archive_copy = at / f"{stem}.zip"
    return (directory_copy.exists() or directory_copy.is_symlink()
            or archive_copy.exists() or archive_copy.is_symlink())


def save(data: Optional[Path] = None, backups: Optional[Path] = None,
         when: Optional[datetime] = None, saying: Optional[Callable[[str], None]] = None) -> str:
    """Copy what the owner keeps, and hand back what the copy is called.

    The consistent directory snapshot is staged on the backup filesystem. Its archive is written
    there without seeking under a name no copy has, verified, and only then renamed into place, so
    an interruption leaves litter rather than a copy that is not one.

    **Every agent's records in the copy are a snapshot SQLite itself took**, not the bytes of a file
    somebody may be writing to — see the module docstring on why this is consistent rather than
    refused. `saying` is how a set of records that could not be read is named; without it the fact
    is still true and nobody hears it, which is why every caller in this product passes one.

    Removes nothing. What is kept and what is let go is `prune`, asked for separately, because the
    caller that wants a copy and the caller that wants a tidy directory are not always the same one —
    a restore takes a copy of what it is about to replace, and that copy must not be able to push
    the copy being restored out of the retention it never asked about.
    """
    from_where = data or paths.data()
    at = backups or paths.backups()
    said = saying or (lambda _line: None)
    if not from_where.is_dir():
        raise Refused(f"there is nothing to copy: {from_where} is not there")
    # The one entry point this guard did not reach. `mkdir(exist_ok=True)` still raises on a broken
    # link — the directory *entry* is there — so an unplugged disk came out of the most-likely-to-be
    # -unattended operation as a raw `[Errno 17] File exists`, while every other verb said plainly
    # what had happened.
    _reachable(at)

    at.mkdir(parents=True, exist_ok=True)
    with _one_at_a_time(at.parent):
        _destination_ready(at)
        # The name and the staging under it are one decision: worked out separately, two callers
        # land on the same second, stage into the same directory, and discard each other's work.
        name = named(when, at)
        archive = files.incoming_of(at / name)
        files.discard(archive)
        # Large staging belongs on the configured filesystem: relocating backups must also
        # relocate the capacity boundary. The ZIP writer below does not seek, so this remains safe
        # for cloud-backed destinations that reject ZIP's usual header rewrites. Made by hand rather
        # than as a context manager, because a context manager's cleanup stands between the verified
        # archive and its name — see below.
        staging = Path(tempfile.mkdtemp(prefix=".rundesk-backup-", dir=str(at)))
        try:
            pending = staging / "data"
            vanished: List[str] = []
            shutil.copytree(
                from_where, pending, symlinks=True,
                ignore=_without_provider_accounts(from_where),
                copy_function=_copying(from_where, vanished, said))
            _without_update_intents(pending)
            # **Before the rename, so a copy is never named like one until every database in it
            # is a snapshot.** After it, the window between a copy appearing under its own name
            # and its records being made consistent is a window a restore can happen in.
            _snapshotted(from_where, pending, said)
            _private_secrets(pending / "secrets")
            _packed(pending, archive, when, vanished)
            _verified(archive)
            os.rename(archive, at / name)
        except BaseException:
            # A Ctrl-C or a destination failure may leave staging litter, but never a finished name.
            files.discard(archive)
            files.discard(staging)
            raise
        # **The copy is whole and named before the staging goes, and litter never unmakes it**
        # (R-BKP-2). Everything in the staging directory is already inside the verified archive, so
        # a cloud-backed filesystem that will not let a file go while it is still syncing costs a
        # sentence and not the copy — the same rule `prune` and `files.discard` already keep, and
        # the opposite of what a context manager would have done here: raise out of its cleanup,
        # into the guard above, and discard a backup that was finished a moment before.
        files.discard(staging)
        if staging.exists():
            said(f"the staging directory {staging.name} could not be removed and is only litter — "
                 f"the copy {name} is whole and does not depend on it")
    return name


def _destination_ready(at: Path) -> None:
    """Prove a destination can write, reread and rename before the expensive snapshot begins.

    A cloud-backed directory may be immediately listable and still refuse the final rename. A tiny
    probe exercises the same destination-side operations first, so that refusal costs no archive
    construction and tells the owner how to choose another location.
    """
    staged: Optional[Path] = None
    landed: Optional[Path] = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".rundesk-backup-probe.", suffix=".incoming", dir=str(at))
        staged = Path(name)
        landed = staged.with_suffix("")
        with os.fdopen(descriptor, "w+b") as writing:
            writing.write(b"rundesk backup destination probe\n")
            writing.flush()
            os.fsync(writing.fileno())
        os.rename(staged, landed)
        if landed.read_bytes() != b"rundesk backup destination probe\n":
            raise OSError("the probe could not be read back")
    except OSError as why:
        raise Refused(
            f"the backups location {location(at)} cannot finish a copy safely: {why} — choose "
            "another with: rundesk backups set-location <path>") from why
    finally:
        if staged is not None:
            files.discard(staged)
        if landed is not None:
            files.discard(landed)


def _copying(from_where: Path, vanished: List[str], said: Callable[[str], None]
             ) -> Callable[..., str]:
    """A copy operation that distinguishes supported cleanup from every other read failure."""
    def copy(source: str, target: str, *, follow_symlinks: bool = True) -> str:
        try:
            return str(shutil.copy2(source, target, follow_symlinks=follow_symlinks))
        except FileNotFoundError:
            if Path(source).exists() or Path(source).is_symlink():
                raise
            under = Path(source).relative_to(from_where).as_posix()
            vanished.append(under)
            said(f"{under} was removed while the copy was being written — it is not in this copy")
            return str(target)
    return copy


class _SequentialArchive:
    """A write-only ZIP destination that cannot expose the seek operation cloud storage rejects."""

    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream

    def write(self, content: bytes) -> int:
        return self.stream.write(content)

    def flush(self) -> None:
        self.stream.flush()


def _packed(data: Path, archive: Path, when: Optional[datetime], vanished: List[str]) -> None:
    """Pack a finished staged data tree with the metadata restore needs to reproduce it."""
    made = when or datetime.now(timezone.utc)
    manifest = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "created_at": made.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_prefix": DATA_PREFIX,
        "vanished": sorted(vanished),
    }
    # Private from the first byte, not tightened afterwards: this archive carries sealed values and
    # the key that opens them, so a permissive umask must never create a readable window.
    descriptor = os.open(archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY, files.ONLY_MINE)
    with os.fdopen(descriptor, "wb") as stream:
        # Without tell or seek, ZipFile emits data descriptors and writes its central directory
        # forward. Passing the filesystem stream itself makes it rewrite earlier headers, which
        # cloud-backed files can reject with EDEADLK after accepting every write before it.
        with zipfile.ZipFile(
                _SequentialArchive(stream), "w", compression=zipfile.ZIP_DEFLATED) as opened:
            _written(opened, MANIFEST,
                     json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n",
                     stat.S_IFREG | 0o600, made)
            _written(opened, DATA_PREFIX, b"",
                     stat.S_IFDIR | (data.lstat().st_mode & 0o7777), made)
            for one in sorted(data.rglob("*")):
                under = DATA_PREFIX + one.relative_to(data).as_posix()
                mode = one.lstat().st_mode
                if stat.S_ISDIR(mode):
                    _written(opened, under + "/", b"", mode, made)
                elif stat.S_ISLNK(mode):
                    _written(opened, under, os.readlink(one).encode(), mode, made)
                elif stat.S_ISREG(mode):
                    _written_file(opened, under, one, mode, made)
                else:
                    raise Refused(f"{one} is not a file, directory or link and cannot be copied")
        stream.flush()
        os.fsync(stream.fileno())


def _zip_time(stamp: float, fallback: datetime) -> Tuple[int, int, int, int, int, int]:
    """A local filesystem time within ZIP's representable range."""
    held = datetime.fromtimestamp(stamp)
    if held.year < 1980 or held.year > 2107:
        held = fallback.astimezone().replace(tzinfo=None)
    return held.timetuple()[:6]


def _info(name: str, mode: int, made: datetime, stamp: Optional[float] = None) -> zipfile.ZipInfo:
    """One Unix ZIP member carrying its type and mode explicitly."""
    info = zipfile.ZipInfo(name, date_time=_zip_time(stamp if stamp is not None else made.timestamp(),
                                                    made))
    info.create_system = 3
    info.external_attr = (mode & 0xFFFF) << 16
    if stat.S_ISDIR(mode):
        info.external_attr |= 0x10
    return info


def _written(opened: zipfile.ZipFile, name: str, content: bytes, mode: int,
             made: datetime) -> None:
    """Write one small or metadata-only member."""
    info = _info(name, mode, made)
    info.compress_type = zipfile.ZIP_DEFLATED
    opened.writestr(info, content)


def _written_file(opened: zipfile.ZipFile, name: str, source: Path, mode: int,
                  made: datetime) -> None:
    """Stream one regular file rather than holding credential-bearing data in memory."""
    info = _info(name, mode, made, source.lstat().st_mtime)
    info.compress_type = zipfile.ZIP_DEFLATED
    with open(source, "rb") as reading, opened.open(info, "w") as writing:
        shutil.copyfileobj(reading, writing)


def _verified(archive: Path) -> None:
    """Close and reread an archive before its finished name can appear."""
    try:
        with zipfile.ZipFile(archive) as opened:
            bad = opened.testzip()
            if bad is not None:
                raise Refused(f"the copy could not be verified: {bad} is damaged")
            _archive_members(opened, archive.name)
    except zipfile.BadZipFile as why:
        raise Refused(f"the copy could not be verified: {why}") from why


def _snapshotted(from_where: Path, pending: Path, said: Callable[[str], None]) -> None:
    """Make every agent's records in this copy a snapshot of the live ones, rather than their bytes.

    **Found by the one name records have**, `agents.directory.RECORDS`, and not by knowing where
    agents stand. Nothing here has to be told that they live under `agents/`: a copy is a copy of
    `data/`, whatever shape a migration step gives it, and a second answer to where an agent stands
    is the kind of thing that goes stale in a release nobody connects it to.

    **The walk does not follow links.** `rglob` never recurses through a symbolic link, which is
    what keeps an agent directory replaced by a link to somebody's documents from having those
    documents walked — the copy already carries it as a link, and `directory.where` refuses one on
    the way in.
    """
    for copied in sorted(pending.rglob(directory.RECORDS)):
        if copied.is_file() and not copied.is_symlink():
            _a_snapshot(from_where / copied.relative_to(pending), copied, said)


def _without_update_intents(pending: Path) -> None:
    """Omit transient process handoffs from the agent directories in a staged copy."""
    for copied in sorted(pending.rglob(directory.RECORDS)):
        transient = copied.parent / directory.UPDATE_INTENT
        if transient.exists() or transient.is_symlink():
            files.remove_one(transient)


def _without_provider_accounts(data: Path) -> Callable[[str, List[str]], List[str]]:
    """Never read or copy provider-owned account homes into Rundesk backups.

    Skipping the registry at its top-level boundary means the backup walker never enters an account
    home. Aliases must therefore be registered and authorized again after restoring an install.
    """
    root = data.resolve()

    def ignored(where: str, names: List[str]) -> List[str]:
        try:
            here = Path(where).resolve()
        except OSError:
            return []
        return ["provider-accounts"] if here == root and "provider-accounts" in names else []

    return ignored


def _a_snapshot(live: Path, copied: Path, said: Callable[[str], None]) -> None:
    """Replace one set of copied records with a snapshot SQLite took of the live ones.

    **Read-only on the way in.** The source is opened through `agents.records.reading`, which asks
    SQLite for `mode=ro` at connect time rather than intending not to write — a backup that can
    write to what it is backing up is not a backup. Nothing here checkpoints the owner's database or
    touches its write-ahead log, which is the tempting shortcut and would be a write.

    **Staged beside the file it replaces and renamed into place**, so a snapshot that dies partway
    leaves the byte copy standing rather than half a database wearing its name.

    Then the `-wal` and `-shm` that came across with the byte copy are removed, **named through
    `records.beside` rather than globbed**, because a sidecar copied at a different instant from the
    database it belongs to is read by the next connection as that database's most recent truth. What
    stands beside the snapshot afterwards is a log this function wrote and nothing that was carried
    across — `_an_empty_log` says why there is one at all, and it is a measurement rather than a
    preference.

    A set of records that cannot be read is left exactly as it was copied, sidecars and all, and
    said out loud. That is the honest shape: rundesk cannot say what is in them, they are still the
    owner's, and a copy is what somebody reaches for on the worst day they have had.
    """
    staged = files.incoming_of(copied)
    _litter(staged)
    try:
        with records.reading(live) as source:
            with contextlib.closing(sqlite3.connect(str(staged))) as into:
                source.backup(into)
                _without_lifecycle_handoffs(into)
                in_wal = str(into.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
    except (records.NotThere, records.Unreadable, sqlite3.Error, OSError) as why:
        _litter(staged)
        said(f"{live} was copied as it stood rather than as a snapshot: {why}")
        return
    for one in records.beside(copied):
        if one != copied:
            files.remove_one(one)
    os.replace(staged, copied)
    # Whatever the interpreter's SQLite left beside the staged name. Two of them differ about this:
    # on the 3.9 floor a closed connection leaves both sidecars standing and on a current one it
    # does not, so they are taken away rather than assumed gone.
    _litter(staged)
    if in_wal:
        _an_empty_log(copied)


def _without_lifecycle_handoffs(copied: sqlite3.Connection) -> None:
    """Make transient continuations inert in a staged snapshot, never in the live records.

    A restored backup may be opened under a later gateway and process id.  Keeping an actionable
    lifecycle row there would turn restore into an unrelated wake, so only the snapshot's pending or
    claimed rows are suppressed.  Older databases do not have the optional ledger at all.
    """
    exists = copied.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'lifecycle_continuations'"
    ).fetchone()
    if exists is None:
        return
    copied.execute(
        "UPDATE lifecycle_continuations "
        "SET continuation_state = 'suppressed', "
        "continuation_outcome = 'backup restores do not replay lifecycle continuations' "
        "WHERE continuation_state IN ('requested', 'resuming')"
    )
    copied.commit()


def _an_empty_log(copied: Path) -> None:
    """Put a write-ahead log holding nothing beside a snapshot that is kept in WAL.

    **Measured, on the floor this project pins, and it is the reason this function exists at all.**
    A database whose header says WAL, standing alone with neither sidecar, **cannot be opened
    read-only** by the SQLite the 3.9 floor ships (3.51.0): the read needs the shared-memory index
    and a read-only connection may not create one, so every such copy answered `unable to open
    database file`. A current interpreter's SQLite (3.53.2) reads it perfectly well, which is the
    worst possible way round — the copy looks fine on the machine it was written on and is
    unreadable on the oldest one this product supports.

    A zero-length log is the documented way out and was measured to work on both: it holds no
    frames, so there is nothing in it that can disagree with the database beside it, and SQLite
    reads the database itself. It is **created here rather than carried across** — the one a copy
    was taken from belongs to a different instant, and this one is empty by construction.

    The shared-memory index is deliberately never kept. It is what live processes coordinate
    through, rebuilt from the log whenever it is wanted, and an archived one is a stale claim about
    processes that stopped running long ago.

    Keeping the mode rather than writing the copy out in the default rollback journal is the other
    half. A copy is put back as an agent's whole records, and `records` asks for WAL **once, when a
    database is made** — so a copy written in the default journal would restore an agent that had
    quietly lost WAL for good, with nothing anywhere saying so.
    """
    with open(str(copied.with_name(copied.name + WAL)), "wb"):
        pass


def _litter(staged: Path) -> None:
    """Let go of a staged snapshot and whatever SQLite left beside it.

    Never raises: this is a name this function chose and nothing an owner keeps, and turning a copy
    that worked into a reported failure over litter is the wrong answer. The copy's *own* sidecars
    are a different question and go through `files.remove_one`, which does raise — a stale
    write-ahead log that would not go is a copy that must not be named like a finished one.
    """
    for one in records.beside(staged):
        files.discard(one)


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

    Failure to finish the validation pass is different: nothing is removed, and the refusal lets the
    command report that the copy was saved while retention was not applied.
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
    with _one_at_a_time(at.parent):
        try:
            copies = [one for one in kept(at) if restorable(at, one)]
        except OSError as why:
            # One copy that could not be *checked* — not one that failed the check — ends the
            # pass with nothing removed. Retention decides against the whole set it validated,
            # and a set with a hole in it is not one to decide against.
            raise Refused(f"retention could not be applied because a copy could not be checked: "
                          f"{why}") from why
        for name in copies[keeping:]:
            try:
                files.remove_one(at / name)
                said(f"let go of {name}")
            except OSError:
                stuck.append(name)
    return stuck


def restorable(at: Path, name: str) -> bool:
    """Whether this copy could actually be put back, as opposed to merely being named like one.

    The question retention has to ask before it lets anything go, and the question a listing has to
    ask before it lets somebody believe they are covered. A structural refusal answers ``False``;
    an operational failure, including cleanup of a disposable extraction, remains a failure rather
    than reclassifying a valid copy.
    """
    try:
        with _opened_copy(at, name):
            pass
    except Refused:
        return False
    return True


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

    **No gateway may be running while this is called, and that is the caller's to guarantee.** It is
    not the same question `save` answers and skips — see the module docstring on why a copy taken
    under a live gateway is a read. `_swap` renames `data/` aside and a fresh copy into its place, so
    afterwards `<agent>/gateway.lock` names a **new inode**: a copy never carries a held lock. The
    running gateway keeps its descriptor on the old one, so `standing` opens the new path, takes its
    shared probe, succeeds — and every command reports that agent as not running while its process is
    alive, the gateway beats into a record that now resolves inside the restored copy, and a second
    gateway can take the lock at that path. Two processes each believing they are the one gateway for
    that agent is the identity failure the whole of `gateways.standing` exists to make impossible.

    **It cannot be prevented here**, and that is the layer rule rather than a preference: `lifecycle`
    may not import `gateways`, checked by `tests/test_layers.py`. So it is prevented in
    `commands.backups`, which may ask — it stands the running gateways down before this is called and
    starts exactly those again afterwards. Written down here as well because this is the function
    that does the renaming, and the next caller this grows will read this docstring and not that one.
    """
    at = backups or paths.backups()
    into = data or paths.data()
    said = saying or (lambda _line: None)

    with _one_at_a_time(into.parent):
        return _put_back_now(name, at, into, when, steps, said)


def _put_back_now(name: str, at: Path, into: Path, when: Optional[datetime],
                  steps: Optional[Path], said: Callable[[str], None]) -> Restored:
    """The restore itself, with the install already held. See `restore`."""
    with _opened_copy(at, name) as a_copy:
        safety = save(into, at, when, said) if into.is_dir() else None
        if safety:
            # Said **before** anything is replaced, not in a summary afterwards. Every failure from
            # here on is one where knowing this name is the way back, and a summary is exactly the
            # thing that does not get printed when something goes wrong on the line above it.
            said(f"kept {safety} — a copy of {into} as it was")

        try:
            _swap(a_copy, into)
        except HalfRestored as why:
            # The one failure with nothing left to try, so the message has to carry the way out.
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
    with _one_at_a_time(at.parent):
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
        files.discard(files.outgoing_of(at))
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
    except BaseException:
        # As above: a Ctrl-C partway through a move must still take back what it wrote.
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

    aside = files.outgoing_of(at)
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

    **Every one is tried, never stopping at the first that would not go.** The caller names each of
    these to whoever is watching, and a list that stopped early would be a list of what was reached
    rather than of what is still there.
    """
    stuck = []
    for name in names:
        try:
            files.remove_one(where / name)
        except OSError:
            stuck.append(name)
    return stuck


def _a_copy(at: Path, name: str) -> Path:
    """The copy by that name, refusing anything that is not one this release can put back.

    Three separate refusals rather than one "no": a name that is not a copy's shape, a name nobody
    has made, and a directory that is there and is not a copy of an install's data are three
    different mistakes, and the person reading has to know which one they made.
    """
    if OLD_ARCHIVE.fullmatch(name):
        raise Refused(
            f"{name} is a pre-v0.40 backup archive whose layout this release does not support — "
            "it was not treated as a current copy and nothing was restored")
    if _identity(name) is None:
        raise Refused(f"{name} is not the name of a copy — `rundesk backups` lists what there is")
    # Before "there is no copy called that": on an unplugged disk every name is missing, and telling
    # somebody their copy does not exist is the worst available answer at the worst moment.
    _reachable(at)
    where = at / name
    expected = where.is_file() if name.endswith(".zip") else where.is_dir()
    if not expected:
        raise Refused(f"there is no copy called {name} in {at}")
    if name.endswith(".zip"):
        try:
            with zipfile.ZipFile(where) as opened:
                _archive_members(opened, name)
        except zipfile.BadZipFile as why:
            # **Only the shape of the bytes is a refusal.** An `OSError` here is the file being out
            # of reach for a moment — a cloud-backed archive still syncing, a disk answering EIO —
            # and is left to propagate: read as *not a copy*, it let retention delete the oldest
            # good copy on the strength of one unreadable second (R-BKP-4).
            raise Refused(f"{name} is not a readable Rundesk backup archive: {why}") from why
        return where
    if not _has_the_mark(where):
        raise Refused(
            f"{name} has no readable {THE_MARK}, so it is not a copy of an install's data — "
            "putting it back would leave rundesk unable to tell how far it has been carried")
    _valid_secrets(where / "secrets")
    _valid_agent_records(where / "agents")
    return where


@contextlib.contextmanager
def _opened_copy(at: Path, name: str) -> Iterator[Path]:
    """Yield either a v0.40 directory or a safely extracted current archive."""
    where = _a_copy(at, name)
    if where.is_dir():
        yield where
        return

    # Retention opens copies through this path immediately after a save. Keep that validation on
    # the configured filesystem too, or pruning can consume a second snapshot's worth of ambient
    # temporary space after the destination-side save has succeeded.
    with tempfile.TemporaryDirectory(prefix=".rundesk-restore-", dir=str(at)) as held:
        root = Path(held)
        try:
            with zipfile.ZipFile(where) as opened:
                members, _manifest = _archive_members(opened, name)
                _unpacked(opened, members, root)
        except (UnicodeError, zipfile.BadZipFile, ValueError) as why:
            # **Structural, and only structural, becomes `Refused`.** These say the bytes are not
            # a copy. An `OSError` says the bytes could not be reached just now — a cloud-backed
            # file still syncing, a disk that answered EIO — and is left to propagate: retention
            # that read it as *not a copy* deleted the oldest good one on the strength of a
            # moment's unreadability, which is the failure `prune` refuses over.
            raise Refused(f"{name} could not be safely read: {why}") from why
        data = root / DATA_PREFIX.rstrip("/")
        if not _has_the_mark(data):
            raise Refused(
                f"{name} has no readable {DATA_PREFIX}{THE_MARK}, so it is not a copy of an "
                "install's data")
        _valid_secrets(data / "secrets")
        _valid_agent_records(data / "agents")
        yield data


def _archive_members(opened: zipfile.ZipFile, name: str
                     ) -> Tuple[List[zipfile.ZipInfo], Dict[str, object]]:
    """Validate every archive member and manifest before extraction writes anything."""
    members = opened.infolist()
    seen = set()
    links = set()
    has_data_root = False
    manifest_member: Optional[zipfile.ZipInfo] = None

    for member in members:
        raw = member.filename
        written = raw[:-1] if raw.endswith("/") else raw
        path = PurePosixPath(written)
        canonical = path.as_posix()
        if (not written or raw.startswith("/") or "\\" in raw
                or any(part in ("", ".", "..") for part in written.split("/"))
                or canonical in ("", ".")):
            raise Refused(f"{name} has an unsafe or malformed member name: {raw!r}")
        if canonical in seen:
            raise Refused(f"{name} contains the member {canonical} more than once")
        seen.add(canonical)
        mode = member.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if member.create_system != 3 or kind not in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
            raise Refused(f"{name} contains unsupported or malformed metadata for {raw}")
        if (kind == stat.S_IFDIR) != raw.endswith("/"):
            raise Refused(f"{name} contains contradictory directory metadata for {raw}")

        if canonical == MANIFEST:
            if kind != stat.S_IFREG:
                raise Refused(f"{name} has a malformed {MANIFEST} member")
            manifest_member = member
        elif canonical == DATA_PREFIX.rstrip("/"):
            if kind != stat.S_IFDIR:
                raise Refused(f"{name} has a malformed {DATA_PREFIX} root")
            has_data_root = True
        elif not canonical.startswith(DATA_PREFIX):
            raise Refused(f"{name} contains an entry outside {DATA_PREFIX}: {raw}")

        if kind == stat.S_IFLNK:
            links.add(canonical)

    for canonical in seen:
        parents = list(PurePosixPath(canonical).parents)[:-1]
        if any(parent.as_posix() in links for parent in parents):
            raise Refused(f"{name} contains {canonical} beneath a symbolic link")

    if manifest_member is None:
        raise Refused(f"{name} has no {MANIFEST}, so it is not a current Rundesk backup")
    if not has_data_root:
        raise Refused(f"{name} has no single {DATA_PREFIX} root")
    try:
        manifest = json.loads(opened.read(manifest_member))
    except (UnicodeError, ValueError) as why:
        raise Refused(f"{name} has an unreadable {MANIFEST}: {why}") from why
    if not isinstance(manifest, dict):
        raise Refused(f"{name} has a {MANIFEST} that is not an object")
    if manifest.get("format") != FORMAT or manifest.get("version") != FORMAT_VERSION:
        raise Refused(f"{name} uses an unsupported backup format or version")
    if manifest.get("data_prefix") != DATA_PREFIX:
        raise Refused(f"{name} names an unsupported data prefix")
    created = manifest.get("created_at")
    if not isinstance(created, str):
        raise Refused(f"{name} has no valid creation moment in {MANIFEST}")
    try:
        datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as why:
        raise Refused(f"{name} has no valid creation moment in {MANIFEST}") from why
    vanished = manifest.get("vanished")
    if not isinstance(vanished, list) or not all(isinstance(one, str) for one in vanished):
        raise Refused(f"{name} has a malformed vanished-members list in {MANIFEST}")
    return members, manifest


def _unpacked(opened: zipfile.ZipFile, members: List[zipfile.ZipInfo], root: Path) -> None:
    """Recreate validated members without delegating paths to `ZipFile.extract`."""
    directories: List[Tuple[Path, int]] = []
    for member in members:
        at = root.joinpath(*PurePosixPath(member.filename.rstrip("/")).parts)
        mode = member.external_attr >> 16
        if stat.S_ISDIR(mode):
            at.mkdir(parents=True, exist_ok=True)
            directories.append((at, stat.S_IMODE(mode)))
        elif stat.S_ISLNK(mode):
            at.parent.mkdir(parents=True, exist_ok=True)
            target = opened.read(member).decode("utf-8")
            if "\x00" in target:
                raise Refused(f"{member.filename} has a malformed symbolic-link target")
            at.symlink_to(target)
        else:
            at.parent.mkdir(parents=True, exist_ok=True)
            with opened.open(member) as reading, open(at, "xb") as writing:
                shutil.copyfileobj(reading, writing)
            at.chmod(stat.S_IMODE(mode))
    for at, mode in reversed(directories):
        at.chmod(mode)


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
    pending = files.incoming_of(into)
    aside = files.outgoing_of(into)
    into.parent.mkdir(parents=True, exist_ok=True)
    files.discard(pending)
    files.discard(aside)

    try:
        shutil.copytree(a_copy, pending, symlinks=True)
        _private_secrets(pending / "secrets")
        _valid_agent_records(pending / "agents")
    except BaseException:
        files.discard(pending)
        raise

    try:
        if into.exists() or into.is_symlink():
            os.rename(into, aside)
        os.rename(pending, into)
    except BaseException:
        # **`BaseException`, and the filesystem rather than a flag.** Two things go wrong here and
        # both were measured. `KeyboardInterrupt` does not inherit from `Exception`, so a rollback
        # catching `Exception` is one that does not run when a person presses Ctrl-C — the single
        # most likely interruption there is. And an interrupt can land between the rename returning
        # and any `swapped = True` on the next line, so a local variable says the swap never
        # happened while `data/` really has been moved aside. Asking whether the directory is there
        # is the fact; a variable is a claim about it, and the two disagree exactly when it matters.
        # Everything caught is re-raised, so catching more swallows nothing.
        files.discard(pending)
        if aside.exists():
            _put_back(aside, into)
        raise
    files.discard(aside)


def _private_secrets(at: Path) -> None:
    """Validate and tighten a copied secrets store when one is present.

    A backup contains the key beside the sealed values, so links are not an owner convenience here:
    they can make a copy claim credentials it does not contain or point a restore outside its staged
    tree. Every check happens before a staged copy receives its finished name or replaces `data/`.
    """
    _valid_secrets(at)
    if not at.exists() and not at.is_symlink():
        return
    at.chmod(secrets.ONLY_MINE)
    for name in (secrets.KEY_IN, secrets.KEPT_IN):
        one = at / name
        if one.exists():
            one.chmod(files.ONLY_MINE)


def _valid_secrets(at: Path) -> None:
    """Refuse a copied secrets store whose shape could escape or cannot be restored.

    Non-mutating so retention can ask whether a copy is genuinely restorable without changing the
    owner's backup. Permission tightening belongs only to a fresh staged save or restore.
    """
    if not at.exists() and not at.is_symlink():
        return
    if at.is_symlink():
        raise Refused(f"{at} is a link, and a secrets store may not be copied through one")
    try:
        mode = at.lstat().st_mode
    except OSError as why:
        raise Refused(f"{at} cannot be inspected: {why}") from why
    if not stat.S_ISDIR(mode):
        raise Refused(f"{at} is not a directory")

    for entry in at.iterdir():
        if entry.is_symlink():
            raise Refused(f"{entry} is a link, and a secrets store may not contain one")
        try:
            entry_mode = entry.lstat().st_mode
        except OSError as why:
            raise Refused(f"{entry} cannot be inspected: {why}") from why
        if not stat.S_ISREG(entry_mode):
            raise Refused(f"{entry} is not a regular file")

    values = at / secrets.KEPT_IN
    key = at / secrets.KEY_IN
    if key.exists() and len(key.read_bytes()) < 32:
        raise Refused(f"{key} is not a key this release can use")
    if not values.exists():
        return

    how, sealed = files.read_json(values)
    if how != files.READ or not isinstance(sealed, dict):
        raise Refused(f"{values} is not a readable store of sealed values")
    if any(value is not None for value in sealed.values()) and not key.exists():
        raise Refused(f"{values} holds sealed values without {key}, so they cannot be restored")
    for name, held in secrets.kept(at).items():
        trouble = secrets.name_trouble(name)
        if trouble:
            raise Refused(f"{values} contains {trouble}")
        if held.trouble:
            raise Refused(f"{values} contains {name}, which {held.trouble}")


def _valid_agent_records(at: Path) -> None:
    """Refuse an agent-records path that settlement could follow outside restored data.

    Agent-directory links are not agents and are deliberately skipped by ``directory.known``. The
    agents root and a real agent's records are different: both are paths settlement opens for
    writes, so neither may be a symbolic link. This inspection never follows a link.
    """
    if not at.exists() and not at.is_symlink():
        return
    if at.is_symlink():
        raise Refused(f"{at} is a link, and restored agent records may not be reached through one")
    try:
        mode = at.lstat().st_mode
    except OSError as why:
        raise Refused(f"{at} cannot be inspected: {why}") from why
    if not stat.S_ISDIR(mode):
        raise Refused(f"{at} is not a directory")
    for agent in at.iterdir():
        if agent.is_symlink() or not agent.is_dir():
            continue
        copied = agent / directory.RECORDS
        if copied.is_symlink():
            raise Refused(
                f"{copied} is a link, and restored agent records may not point outside the copy")


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

    Three things, in this order: settings this release has added that the copy predates, then the
    install's migration steps the copy never ran, and then **the agents inside the copy**. Filling in
    first because a step is entitled to read the configuration, and a step written against a value
    this release introduced would otherwise find it missing on exactly the installs the step exists
    for. The install's steps before the agents' for the reason `update.settle` runs them in the same
    order: an install step may reshape where an agent's things stand, and an agent step run before
    that would be run against a layout this release has not finished making.

    **Being back is not the same as being settled, and that is as true of an agent as of the install
    around it.** The records in a copy taken three releases ago have run the steps of the release
    that took it, and nothing since. Putting them back and reporting a restore would leave every one
    of those agents on a layout this rundesk was never written against — the same defect this
    function already exists to prevent one level up.

    **Both under one guard, not just the first.** Every write here goes through the configuration —
    including the stamp each migration step lands with — so `carry` can give the same two answers
    `fill_in` can, and it reads the file before it runs anything. Catching only around the first call
    leaves the second free to come out as a traceback, and it would do it *after* `data/` had already
    been replaced: the loudest possible failure at the quietest possible moment, with the copy taken
    of what was there going unmentioned because nothing got as far as printing it. `update.settle`
    catches the pair in one place for this reason and this is the same shape of call.
    """
    lifecycle_trouble = _without_restored_lifecycle_handoffs(into)
    if lifecycle_trouble:
        return lifecycle_trouble
    try:
        config.fill_in(into)
        return migration.carry(into, steps, said) or _the_agents_carried(into, said)
    except (config.Unreadable, config.Refused, config.Stuck, ValueError) as why:
        return str(why)


def _without_restored_lifecycle_handoffs(into: Path) -> Optional[str]:
    """Suppress transient wakes after every restore, including byte-copy fallback backups.

    Save normally makes each readable SQLite snapshot inert. Records that could not be snapshotted
    are deliberately preserved byte-for-byte, so restore repeats the guard before gateways may be
    brought back. An unreadable restored database leaves the restore unsettled instead of allowing
    a later gateway to guess whether an old lifecycle request is actionable.
    """
    agents = into / paths.agents().relative_to(paths.data())
    try:
        _valid_agent_records(agents)
    except Refused as why:
        return str(why)
    if not agents.is_dir():
        return None
    for agent in sorted(agents.iterdir()):
        if agent.is_symlink() or not agent.is_dir():
            continue
        copied = agent / directory.RECORDS
        if not copied.is_file():
            continue
        try:
            with contextlib.closing(sqlite3.connect(str(copied))) as conn:
                _without_lifecycle_handoffs(conn)
        except (OSError, sqlite3.Error) as why:
            return f"{copied} could not suppress restored lifecycle work: {why}"
    return None


def _the_agents_carried(into: Path, said: Callable[[str], None]) -> Optional[str]:
    """Carry the agents that came back onto this release. `None` when every one of them is on it.

    **Only when the data being settled is this install's own, and that is a refusal rather than a
    tidiness.** `agents.directory` answers where an agent stands from `paths.agents()`, which is
    derived from the one root — there is no way to point it at a directory a caller handed in, and
    there must not be a second one. So a `restore` given some other directory to work on would, if
    this carried regardless, reach past what it was given and run migration steps against the
    **live install's** agents on the strength of somebody restoring somewhere else. That is the
    defect this whole rebuild exists to have removed, and it is said out loud rather than skipped
    quietly: a guarantee that silently never fires is the shape of every bug this product is written
    against.

    One agent that cannot be carried does not stop the others — `carry_every`'s contract — and every
    one that failed is named, because a summary counting them hides the one somebody has to look at.
    """
    if into.resolve() != paths.data().resolve():
        said(f"the agents in {into} were not carried: {into} is not where this install keeps its "
             "agents, and rundesk carries the agents of the install it was pointed at")
        return None
    try:
        gone_wrong = agent_migration.carry_every(directory.known(), saying=said)
    except OSError as why:
        return f"the agents that came back could not be carried: {why}"
    if not gone_wrong:
        return None
    return "; ".join(gone_wrong[name] for name in sorted(gone_wrong))


def _inside(child: Path, parent: Path) -> bool:
    """Whether one directory stands at or below another, compared as the filesystem resolves them.

    Resolved rather than compared as typed: `/tmp/x` and `/tmp/./x/../x` are the same directory, and
    a check that says otherwise is a check that lets a copy be moved inside itself.
    """
    settled, above = child.resolve(), parent.resolve()
    return settled == above or above in settled.parents
