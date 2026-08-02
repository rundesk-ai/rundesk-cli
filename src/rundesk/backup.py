"""Copies of everything the owner keeps, and putting one back.

**A backup is of the data and never of the program.** `app/` is what a release publishes: an
update replaces it and a reinstall fetches it again, so archiving it would store a second
copy of something already downloadable while doubling what an owner has to keep. What is
here is `data/` — the agents, their homes and workspaces, everything they have been told and
have said, the skills library, what the gateways wrote, and this install's own settings.
Nothing else on the machine is recoverable from anywhere, which is the whole test of what
belongs in one.

**What is deliberately left out is the half somebody will otherwise assume is there**, so it
is named in `EXCLUDED` with the reason attached rather than being merely absent.

**A database is snapshotted, never copied.** Copying `state.db` while a gateway is writing
to it produces a file that opens, looks healthy, and is subtly wrong — and the moment that
is discovered is a restore, which is the worst moment there is. SQLite has two ways of
taking a consistent copy of a live database and this uses them; `cp` is not one of them.

**Nothing is written under its final name until it is whole.** A backup directory may be
iCloud Drive or an external disk, so a half-written archive is a half-written archive that
*syncs*. One is built beside its destination and renamed into place, which is atomic on
every filesystem rundesk runs on.

This module knows nothing of gateways, of the machine's supervisor, or of how a command was
invoked. What has to be true before a restore may proceed — that nothing is running and
nothing is in flight — arrives as callables, the way `updater.run` already takes them, so
the whole module is exercised with no gateway anywhere near it.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

from rundesk import __version__, gateway, migration, store

#: What one is called. The stamp is UTC and fixed-width, so sorting these by name sorts them
#: by the moment they were taken — including across the hour a clock goes back, which a local
#: time would order wrongly twice a year and silently. `ls` is a listing.
NAMED_AS = "rundesk-data-%Y-%m-%d-%H%M%SZ"
SUFFIX = ".zip"

#: What an archive is called while it is still being written. In the destination directory
#: rather than a temporary one, so the move into place never crosses a filesystem — and named
#: so that anything reading the directory can tell it is not a backup yet.
#:
#: **Every writer gets a name of its own.** Derived from the final name alone, two rundesks
#: backing up in the same second opened the *same* part-written file and one of them died on
#: it — the machine's daily job firing while somebody types `backups add` is exactly that, and
#: the loser reported a disk that could not be written to. The name is made rather than
#: computed now, so no two writers can be holding one path whether they are two processes or
#: two threads of one.
PARTIAL = ".part"

#: What the archive says about itself, read without unpacking the rest of it.
MANIFEST = "manifest.json"

#: Where the tree sits inside the archive. Named rather than at the root so the manifest is
#: never mistaken for something an owner kept.
INSIDE = "data"

#: Why a backup was taken. Three, because there are three things that take one: a person
#: asking, the machine at its stated hour, and a restore protecting the owner from itself.
REASONS = ("asked", "daily", "before-restore")


class Refused(Exception):
    """This archive may not be read or put back, and the reason is already in the message."""


class Unreadable(Exception):
    """There is a file there and it is not a backup this rundesk can read."""


def named_at(now: datetime.datetime) -> str:
    """What a backup taken at this moment is called."""
    return now.strftime(NAMED_AS) + SUFFIX


def _placed(writing: Path, into: Path, now: datetime.datetime) -> Path:
    """Put a finished archive under the first name in this directory that is free, atomically.

    **A name is to the second, and two backups can happen inside one.** Taking one by hand
    immediately before a restore takes its own is exactly that case, and it is not contrived:
    it is what the safest path through this module does every time. The machine's daily job
    firing while somebody types `backups add` is the other.

    **Asking whether a name is free and then writing to it are two moments, and something can
    happen in between.** Two processes that both looked before either wrote would both find
    the same name free, and the second `os.replace` would silently discard the first
    archive — with both commands reporting success. So the name is not checked and then used;
    it is *claimed* with a link, which either creates the name or fails because somebody else
    already has it, with nothing in between. Whoever loses the race simply takes the next one.

    **Kept sorting by time, which decides the punctuation.** The stamp is fixed width and is
    compared first, so a disambiguated name still orders before the next second. What it must
    also do is order *after* the undisambiguated one it follows — and a hyphen would not:
    `-` comes before `.` in every byte ordering there is, so `…Z-2.zip` would sort ahead of
    `…Z.zip` and put the newer copy above the older one. `_` comes after `.`, which is the
    whole reason it is the separator here and a hyphen everywhere else in the name.
    """
    stem = named_at(now)[: -len(SUFFIX)]
    nth = 1
    while True:
        at = into / (f"{stem}{SUFFIX}" if nth == 1 else f"{stem}_{nth}{SUFFIX}")
        try:
            os.link(writing, at)
        except FileExistsError:
            nth += 1
            continue
        except OSError:
            # A filesystem that cannot link at all — some network and removable ones. There
            # is no atomic claim to be had there, so this falls back to looking first, which
            # is what every other backup tool does and is still right on the machine of one
            # owner. Said nowhere, because it changes nothing an owner can act on.
            if at.exists():
                nth += 1
                continue
            os.replace(writing, at)
            return at
        os.remove(writing)
        return at


def _now() -> datetime.datetime:
    """The wall clock, in UTC. Replaced by an argument everywhere it matters."""
    return datetime.datetime.now(datetime.timezone.utc)


def excluded(data: Path) -> dict:
    """What a backup leaves out of the directory it is given, and why — by relative path.

    **Worked out from the modules that own those directories rather than listed here.** A
    list of names written in a second place is a list that stops being true the day one of
    them moves, and the failure would be silent: an archive quietly holding live gateway
    state, put back, claims a gateway that is not running.

    **What is asked of those modules is the *name*, never the place.** They answer for the
    install this process is running against, and the directory being archived is very often
    not that one — a suite's scratch tree, or the copy inside an archive being read. Asking
    them for a path and testing whether it sits under `data` therefore answered "nothing is
    excluded" for every directory except the live one, which is the shape of failure that
    passes every test written against the real install and silently archives run state
    everywhere else.

    A directory an owner has pointed clean outside the data root has no name under it, and
    so is not named here: there is nothing in the archive to leave out.
    """
    leaving = {}
    for at, why in (
        (gateway.home(),
         "live gateway state — locks, records and part-written files. Putting it back would "
         "claim gateways that are not running."),
        (_rollback(),
         "a copy an update takes while it works. It belongs to that update, not to the "
         "owner, and it is walked as an agent by anything reading the agents directory."),
    ):
        called = _called_under_data(at)
        if called and (Path(data) / called).exists():
            leaving[called] = why
    return leaving


def _rollback() -> Path:
    """Where an update keeps what it may have to put back, asked of the module that owns it.

    Imported here rather than at the top: `agent` reaches this module's neighbours and a
    module-level import of it would put a cycle between them.
    """
    from rundesk import agent

    return agent.agents_home() / migration.ROLLBACK


def _called_under_data(at: Path) -> str | None:
    """What this directory is *called* inside a data directory, or nothing where it is outside one.

    The name rather than the path, so it can then be applied to whichever data directory is
    being archived. `agents/.update.rollback` and `run` are answers; an absolute path is not.
    """
    from rundesk import data_home

    try:
        return Path(at).relative_to(data_home()).as_posix()
    except ValueError:
        return None


#: What is never archived wherever it is found, because the snapshot beside it already holds
#: what it says. A write-ahead log put back next to a database it does not belong to is read
#: as that database's most recent truth, which is how a restore produces records nobody wrote.
BESIDE_A_DATABASE = ("-wal", "-shm")


#: How a database is copied — asked of the module that owns every connection there is, never
#: done here. `R-STO-15` is not a style rule: the store is the only way in precisely so that
#: nothing else has to be trusted to open one correctly, and a backup is the caller most
#: tempted to reach past it. The suite fails the day this file imports `sqlite3`.
snapshot = store.snapshot


def _agents_in(data: Path) -> dict:
    """Every agent under this data directory, and which version its records say they are.

    Read off the directory rather than asked of the agent module, because the directory being
    described may be one inside an archive rather than the one this install is using.
    """
    standing = {}
    agents = Path(data) / "agents"
    if not agents.is_dir():
        return standing
    for home in sorted(agents.iterdir()):
        if home.name == migration.ROLLBACK or not home.is_dir():
            continue
        if not any((home / one).exists() for one in migration.OF_AN_AGENT):
            continue
        standing[home.name] = migration.version_on_disk(home / migration.RECORDS)
    return standing


def describe(data: Path, now: datetime.datetime, why: str) -> dict:
    """What an archive says about itself, written beside the tree it describes.

    **The manifest is read before anything is moved**, which is the whole reason it is a file
    of its own at the top of the archive rather than something worked out by unpacking. A
    restore has to be able to refuse — because these records are newer than this rundesk
    understands, say — *before* it has touched a single thing an owner keeps.

    Both versions are here and they answer different questions. `rundesk` is which release
    took it, and is the one a person reads. `records` is what each agent's own database says
    its shape is, which is what a restore actually reasons about: two agents are never at the
    same version, so one number for "the data" would be a number that is wrong about somebody.
    """
    return {
        "taken_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "why": why,
        "rundesk": __version__,
        "records": _agents_in(data),
        "understands": store.VERSION,
        "excluded": excluded(data),
        # Filled in as the archive is written, because whether a database could be copied
        # honestly is not knowable until it is tried.
        "copied_whole": [],
    }


def _members(data: Path, leaving: dict):
    """Every path that goes into the archive, and what each is, in a settled order.

    Sorted, so two backups of an unchanged directory hold their entries in the same order
    rather than in whatever order the filesystem answered in — a listing nobody sorted is a
    listing that differs between two machines for no reason anybody can see.
    """
    data = Path(data)
    for at in sorted(data.rglob("*")):
        under = at.relative_to(data).as_posix()
        if any(under == one or under.startswith(one + "/") for one in leaving):
            continue
        if at.name.startswith(store.NAME + "-") and at.name.endswith(BESIDE_A_DATABASE):
            continue
        yield at, under


def _add(archive: zipfile.ZipFile, at: Path, under: str, when) -> None:
    """One entry, keeping what the filesystem knows about it that a zip does not by default.

    **Permissions and links are not free.** `zipfile` writes neither unless told: a member
    goes in with no mode at all, and a symlink is followed and stored as a copy of whatever it
    pointed at. Both matter here. An agent's granted skills are symlinks into the shared
    library, so following them would duplicate the library into every agent and quietly break
    revoking one; and a workspace may hold something an owner made executable, which comes
    back unrunnable if the bit is dropped.
    """
    kept = at.lstat()
    info = zipfile.ZipInfo(under, date_time=_when(kept.st_mtime, when))
    # The high half of `external_attr` is the Unix mode, which is where the executable bit and
    # the "this is a link" marker both live. `create_system = 3` is what says to read it that
    # way; without it the mode is written and never looked at again.
    info.external_attr = (kept.st_mode & 0xFFFF) << 16
    info.create_system = 3
    if stat.S_ISLNK(kept.st_mode):
        # The content of a link entry is where it points. Read without following it, so a link
        # to somewhere that no longer exists is still archived as the link it is.
        archive.writestr(info, os.readlink(at))
        return
    if at.is_dir():
        info.filename = under + "/"
        info.external_attr |= 0x10          # the directory flag, for readers that look there
        archive.writestr(info, b"")
        return
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, at.read_bytes())


def _when(stamp: float, fallback) -> tuple:
    """A modification time a zip can hold, or the moment this backup was taken.

    Zip cannot record anything before 1980, and a filesystem can report one — so rather than
    let a stray timestamp raise part way through writing an archive, it is replaced by the
    only other honest answer there is.
    """
    when = datetime.datetime.fromtimestamp(stamp)
    if when.year < 1980:
        when = fallback
    return when.timetuple()[:6]


def take(data: Path, into: Path, now=None, why: str = "asked", note=None) -> Path:
    """Take one, and say where it was put.

    **Written under another name and renamed into place.** The destination may be a synced
    directory, so an archive that appeared under its real name while it was still being
    written would be uploaded half-finished — and would then look, to every listing and to a
    restore, exactly like a backup. The rename is inside the destination directory so it never
    crosses a filesystem, and a rename that does not cross one cannot be partial.

    **A part-written archive is cleared up on the way out.** Not on the way in: something
    ending in `.part` may belong to another backup running right now, and the one thing worse
    than a stray file is deleting somebody else's work in progress.
    """
    data, into = Path(data), Path(into)
    if not data.is_dir():
        raise Refused(f"there is nothing to back up: {data} does not exist")
    say = note if note is not None else (lambda said: None)
    now = _now() if now is None else now
    leaving = excluded(data)
    into.mkdir(parents=True, exist_ok=True)
    # Made in the destination directory, so what follows is a move that never crosses a
    # filesystem, and made rather than named, so it is nobody else's.
    handle, said_at = tempfile.mkstemp(dir=into, prefix=named_at(now) + ".", suffix=PARTIAL)
    os.close(handle)
    writing = Path(said_at)
    said = describe(data, now, why)
    held = tempfile.mkdtemp(prefix="rundesk-backup-")
    try:
        with zipfile.ZipFile(writing, "w", zipfile.ZIP_DEFLATED) as archive:
            for one, under in _members(data, leaving):
                if one.name == store.NAME and one.is_file() and not one.is_symlink():
                    # Never the file as it sits. A database being written to is not a thing
                    # that can be copied byte for byte and still be a database.
                    copy = Path(held) / store.NAME
                    with contextlib.suppress(OSError):
                        os.remove(copy)
                    try:
                        snapshot(one, copy)
                    except Exception as trouble:   # noqa: BLE001 — see below
                        # **Kept as it is rather than abandoned.** A database too damaged to
                        # be copied honestly is exactly the one somebody will want the bytes
                        # of afterwards, and refusing the whole backup over it would leave
                        # every healthy agent uncopied as well — for as long as the damage
                        # lasts, which could be for ever. So the file goes in whole and the
                        # manifest says which ones did, because a copy that is not a
                        # consistent copy must never be silently indistinguishable from one.
                        said["copied_whole"].append(under)
                        say(f"{under} could not be copied consistently ({trouble}) — "
                            f"it is in the backup exactly as it is on disk")
                        _add(archive, one, f"{INSIDE}/{under}", now)
                        continue
                    _add(archive, copy, f"{INSIDE}/{under}", now)
                    continue
                _add(archive, one, f"{INSIDE}/{under}", now)
            # Last, because until every entry is written it is not yet known whether any of
            # them had to be copied whole — and where it sits costs a reader nothing: a zip
            # is read through its index, so asking for one entry by name never unpacks the
            # rest of it wherever that entry happens to be.
            archive.writestr(MANIFEST, json.dumps(said, indent=2, sort_keys=True))
        at = _placed(writing, into, now)
    except BaseException:
        # What was part written is this call's own and nobody else's, so it goes.
        with contextlib.suppress(OSError):
            os.remove(writing)
        raise
    finally:
        shutil.rmtree(held, ignore_errors=True)
    return at


def manifest_of(archive: Path) -> dict:
    """What this archive says about itself, without unpacking any of the rest of it.

    Every refusal a restore makes is decided from this, so it is read on its own and read
    first. A file that is not a zip, or a zip with nothing at the top saying what it is, is
    **not** an empty backup — it is something else entirely, and saying so is the difference
    between refusing and quietly restoring nothing.
    """
    archive = Path(archive)
    if not archive.is_file():
        if _evicted(archive):
            raise Refused(
                f"{archive.name} is not on this disk — the directory it is in syncs to the "
                f"cloud and this one has been evicted. Open it in Finder to download it, "
                f"then try again."
            )
        raise Refused(f"there is no backup called {archive.name} in {archive.parent}")
    try:
        with zipfile.ZipFile(archive) as opened:
            said = json.loads(opened.read(MANIFEST))
    except KeyError as trouble:
        raise Unreadable(f"{archive.name} has no {MANIFEST}, so it is not a rundesk backup"
                         ) from trouble
    except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as trouble:
        raise Unreadable(f"{archive.name} could not be read: {trouble}") from trouble
    if not isinstance(said, dict):
        raise Unreadable(f"{archive.name}: its {MANIFEST} is not an object")
    return said


def _evicted(archive: Path) -> bool:
    """Whether a cloud has taken this file away and left a placeholder for it.

    macOS names the placeholder for the file it stands in for, so the question is answerable
    without asking the cloud anything — which matters, because the machine may be offline and
    that is exactly when somebody reaches for a backup.
    """
    return (archive.parent / f".{archive.name}.icloud").exists()


class Backup:
    """One archive in the directory, and what can be said about it without unpacking it."""

    def __init__(self, at: Path, said: dict | None, why: str | None = None):
        self.at = at
        self.said = said
        self.why = why

    @property
    def readable(self) -> bool:
        return self.said is not None

    @property
    def taken_at(self) -> str:
        """When it was taken — from what it says, falling back to what it is called.

        The name is a fallback rather than the answer, because a file somebody renamed still
        knows when it was taken and a listing that trusted the name would say otherwise.
        """
        if self.said and isinstance(self.said.get("taken_at"), str):
            return self.said["taken_at"]
        stem = self.at.name[: -len(SUFFIX)] if self.at.name.endswith(SUFFIX) else self.at.name
        return stem

    @property
    def held_bytes(self) -> int | None:
        try:
            return self.at.stat().st_size
        except OSError:
            return None


#: What the tree is called while it is being unpacked, and what the old one is called while
#: the new one is being moved into place. Beside `data/` rather than in a temporary directory,
#: so the two renames that do the swap never cross a filesystem — a rename that does not cross
#: one is atomic, and both trees exist for every instant of it.
INCOMING = "{name}.incoming"
OUTGOING = "{name}.outgoing"


def refusals(said: dict, want: int | None = None, version: str | None = None) -> list:
    """Every reason this archive may not be put back, decided before anything is moved.

    **Read off what the archive says about itself**, so a restore that must not happen costs
    nothing and touches nothing. The alternative — unpacking and finding out — is a restore
    that has already written somewhere by the time it knows it should not have.

    Newer is refused in both of the ways an archive can be newer. Records written by a later
    rundesk are refused for the reason `store.TooNew` exists: this code cannot know what it
    is missing, so reading them would be reading a partial truth and writing over the rest.
    """
    want = store.VERSION if want is None else want
    version = __version__ if version is None else version
    why = []
    ahead = sorted(name for name, was in (said.get("records") or {}).items()
                   if isinstance(was, int) and was > want)
    if ahead:
        named = ", ".join(f"{name} at version {said['records'][name]}" for name in ahead)
        why.append(f"these records are newer than this rundesk understands — {named}, "
                   f"and this rundesk understands {want}")
    understood = said.get("understands")
    if isinstance(understood, int) and understood > want:
        why.append(f"this backup was taken by a rundesk that understands version {understood} "
                   f"and this one understands {want}")
    took = said.get("rundesk")
    if isinstance(took, str) and _is_newer(took, version):
        why.append(f"this backup was taken by rundesk {took} and this is {version}")
    return why


def _is_newer(there: str, here: str) -> bool:
    """Whether one release is later than another, asked of the module that already decides it.

    Imported where it is used rather than at the top: `updater` is a decision about releases
    and importing it for one predicate would tie every backup to it.
    """
    from rundesk import updater

    return updater.is_newer(there, here)


def what_changes(said: dict, data: Path) -> dict:
    """Which agents a restore would bring back, take away, and leave standing.

    **Said before it happens rather than discovered afterwards.** Putting a copy back replaces
    everything the owner keeps, so an agent removed since it was taken comes back and one made
    since it was taken goes — and neither of those is a thing to find out about later.
    """
    was = set((said.get("records") or {}).keys())
    now = set(_agents_in(data))
    return {
        "comes_back": sorted(was - now),
        "goes_away": sorted(now - was),
        "stays": sorted(was & now),
    }


def _unpacked(archive: Path, into: Path) -> None:
    """The tree inside this archive, put where it is told and nowhere else.

    **Every member is checked before any is written.** A zip says where each of its entries
    goes, and nothing stops one saying `../../../etc`; the standard library only began
    refusing that by default long after the oldest Python this runs on. A restore is the most
    privileged thing here, so the check is made rather than inherited.
    """
    into.mkdir(parents=True, exist_ok=True)
    root = into.resolve()
    with zipfile.ZipFile(archive) as opened:
        wanted = [one for one in opened.infolist()
                  if one.filename == INSIDE or one.filename.startswith(INSIDE + "/")]
        for one in wanted:
            under = one.filename[len(INSIDE):].lstrip("/")
            if not under:
                continue
            lands = (root / under).resolve()
            if lands != root and root not in lands.parents:
                raise Refused(f"{archive.name} holds an entry that would be written outside "
                              f"the directory it is being put in: {one.filename}")
        for one in wanted:
            under = one.filename[len(INSIDE):].lstrip("/")
            if not under:
                continue
            _put(opened, one, root / under)


def _put(opened: zipfile.ZipFile, one: zipfile.ZipInfo, at: Path) -> None:
    """One entry back onto disk, as what it was rather than as a file with its bytes."""
    mode = one.external_attr >> 16
    if stat.S_ISLNK(mode):
        at.parent.mkdir(parents=True, exist_ok=True)
        if at.is_symlink() or at.exists():
            os.remove(at)
        os.symlink(opened.read(one), at)
        return
    if one.filename.endswith("/"):
        at.mkdir(parents=True, exist_ok=True)
        return
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_bytes(opened.read(one))
    if mode & 0o777:
        # Only where the archive actually recorded one. A zip written by something else has
        # no mode at all, and chmod 0 would make what was restored unreadable.
        os.chmod(at, mode & 0o777)


def restore(archive: Path, data: Path, into: Path, now=None, want: int | None = None,
            busy=None, pause=None, resume=None, carry=None, note=None,
            keep_one_first: bool = True) -> str | None:
    """Put a backup back, or leave everything exactly as it was and say why.

    Says what went wrong rather than raising it, the shape `carry_every_or_put_back` and
    `dependencies.provision` already use, because the caller is a command and not a place to
    handle an archive error.

    **Nothing is moved until every refusal has been asked.** What the archive says about
    itself decides whether it may be put back at all, and that is read without unpacking
    anything (R-BKP-18).

    **Never in place, and never over live data.** The tree is unpacked *beside* the one it
    replaces, brought forward there, and only then swapped in by two renames. Everything that
    could fail — a bad archive, a migration that will not run, records that will not open —
    fails while the owner's own data is still sitting untouched where it always was. That is
    a stronger promise than restoring from a copy afterwards, and it is why the order is this
    way round rather than the obvious one (R-BKP-21).

    **A copy of what is here now is taken first**, because a restore is otherwise the one
    irreversible thing an owner can do to themselves (R-BKP-17).
    """
    say = note if note is not None else (lambda said: None)
    archive, data, into = Path(archive), Path(data), Path(into)
    now = _now() if now is None else now
    incoming = data.with_name(INCOMING.format(name=data.name))
    outgoing = data.with_name(OUTGOING.format(name=data.name))

    # **First, before the archive is even opened.** Whether the owner has a data directory at
    # all cannot depend on which archive somebody happened to name afterwards — and every step
    # below this can return early, so recovering further down leaves a refused restore having
    # walked away from an install with no data in it. That is not hypothetical: it is what the
    # case for it caught, on the first run, in this exact order.
    put_back = _finish_an_interrupted_swap(data, outgoing, say)
    if put_back:
        return put_back

    said = manifest_of(archive)                       # raises Refused / Unreadable, unmoved
    why = refusals(said, want=want)
    if why:
        return "; ".join(why)

    working = (busy or (lambda: []))()
    if working:
        return ("work is in flight: " + ", ".join(sorted(working))
                + " — wait for it to finish, or stop it")

    if keep_one_first and data.is_dir():
        kept = take(data, into, now=now, why="before-restore", note=say)
        say(f"what was here is in {kept.name}")

    stopped, refused = (pause or (lambda: ([], None)))()
    if refused:
        return refused

    _clear(incoming)
    _clear(outgoing)
    try:
        say(f"unpacking {archive.name}")
        _unpacked(archive, incoming)
        # **Brought forward before the swap, never after.** A migration that cannot run has
        # then touched nothing but a directory this call made and is about to delete.
        stopped_by = (carry or (lambda _at: None))(incoming)
        if stopped_by:
            _clear(incoming)
            (resume or (lambda _names: []))(stopped)
            return stopped_by
        if data.exists():
            os.rename(data, outgoing)
        os.rename(incoming, data)
    except BaseException as trouble:
        _clear(incoming)
        if outgoing.exists() and not data.exists():
            os.rename(outgoing, data)
        (resume or (lambda _names: []))(stopped)
        if isinstance(trouble, Refused):
            return str(trouble)
        raise
    _clear(outgoing)
    left_down = (resume or (lambda _names: []))(stopped)
    if left_down:
        return (f"the data was put back, but these did not start again: "
                f"{', '.join(sorted(left_down))}")
    return None


def _finish_an_interrupted_swap(data: Path, outgoing: Path, say) -> str | None:
    """Put back what an earlier restore had set aside and never came back for.

    **The swap is two renames, and a process can die between them.** No `except` can see that
    window: the machine loses power, or something takes the process out, and what is left on
    disk is `data/` gone and the owner's real records sitting in `data.outgoing`. Every
    guarantee this module makes is about that directory, and it is the only copy of it there
    is at that instant.

    So the state is *recognised* on the way in rather than swept. Clearing it — which is what
    a restore did before, unconditionally and before any other check — turned the ordinary act
    of running the command again after a crash into the one thing that destroys the data. That
    is the worst shape a bug can have here: it fires on the retry, silently, and reports
    success. `updater._set_aside` already reads a leftover this way for the release it swaps;
    this is the same reading for the data.

    Two leftovers are not one situation. With `data/` gone, the set-aside copy *is* the data
    and goes back. With `data/` there, the rename that matters already happened and what is
    set aside is the superseded copy, which is only cleanup.
    """
    if not outgoing.is_dir():
        return None
    if data.exists():
        return None                 # the swap finished; this is last time's cleanup
    try:
        os.rename(outgoing, data)
    except OSError as trouble:
        return (f"a restore was interrupted before this one and what was here is still in "
                f"{outgoing}. It could not be put back automatically ({trouble}) — move it "
                f"to {data} by hand before trying again.")
    say(f"an earlier restore was interrupted — what was here has been put back from "
        f"{outgoing.name}")
    return None


def _clear(at: Path) -> None:
    """Take a directory away if it is there, and say nothing if it is not."""
    shutil.rmtree(at, ignore_errors=True)


def past_the_last(into: Path, copies: int) -> list:
    """Which copies are beyond the number an owner keeps — never including the newest.

    **The newest is never surplus.** "Keep the last fourteen" must not come to mean "keep
    none" because of a number this code argued with afterwards: the whole point of a backup
    is the one you reach for after trouble, and a rule that can empty the directory is a rule
    that will, on exactly the day it matters. `config` refuses a number below one before it
    ever reaches here, and the newest file is held out of the candidates again here, where
    the deleting actually happens.

    Order is the name's, which sorts by the moment a copy was taken (R-BKP-7), so no clock is
    consulted at all — how many there are is a question this directory answers on its own.

    A copy this rundesk cannot read is never chosen, and is never counted towards the number
    either. Deciding to delete something on the strength of not understanding it is the one
    thing pruning must not do, and counting it as one of the copies an owner is keeping would
    delete a good one to make room for something that is not a backup.
    """
    oldest_first = sorted(every(into), key=lambda one: one.at.name)
    over = len([one for one in oldest_first if one.readable]) - copies
    if over <= 0:
        return []
    return [one for one in oldest_first[:-1] if one.readable][:over]


def prune(into: Path, copies: int, note=None) -> list:
    """Take away the copies beyond the number kept, and say which went."""
    say = note if note is not None else (lambda said: None)
    gone = []
    for one in past_the_last(into, copies):
        try:
            os.remove(one.at)
        except OSError as trouble:
            say(f"{one.at.name} could not be removed: {trouble}")
            continue
        gone.append(one.at.name)
        say(f"{one.at.name} is not one of the last {copies} copies and has been removed")
    return gone


def remove(into: Path, named: str) -> Path:
    """Take one copy away, by the name it is listed under, and only that one.

    Asked for by name and never derived from anything: "always kept" plus "no way to be rid of
    them" is a disk that fills, and the answer to that is a separate, explicit act rather than
    a flag on something else.
    """
    at = Path(into) / named
    if at.parent.resolve() != Path(into).resolve() or not at.name.endswith(SUFFIX):
        # A name is a name, not a path. Without this, `../../something` reaches out of the
        # directory entirely, and a command whose whole job is deleting is the wrong one to
        # be relaxed about that.
        raise Refused(f"{named!r} is not the name of a backup in {into}")
    if not at.is_file():
        raise Refused(f"there is no backup called {named} in {into}")
    os.remove(at)
    return at


def every(into: Path) -> list:
    """Every backup in this directory, newest last, including any that cannot be read.

    **An unreadable one is listed rather than skipped.** A file that is there and is not a
    backup this rundesk understands is exactly what somebody needs to be told about, and a
    listing that silently omitted it would be a listing that says an owner has fewer copies
    than they have — or none, on the day it matters.
    """
    into = Path(into)
    if not into.is_dir():
        return []
    found = []
    for at in sorted(into.iterdir()):
        if not at.name.endswith(SUFFIX) or not at.is_file():
            continue
        try:
            found.append(Backup(at, manifest_of(at)))
        except (Refused, Unreadable) as why:
            found.append(Backup(at, None, why=str(why)))
    return found
