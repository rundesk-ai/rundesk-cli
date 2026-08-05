"""Fetching a catalog, keeping it up to date, and taking one away.

A catalog is a repository somebody publishes and this install follows. Three things decide the shape
of everything here, and each of them is a failure the build this replaces had.

## What is on the far end is authoritative, and the version decides nothing

A catalog whose author edited a skill without bumping a number is still a catalog this install should
be running, so a check that compared versions would leave every such install permanently behind while
reporting itself up to date. The build this replaces solved that by re-downloading every catalog on
every update, unconditionally, which is correct and costs a whole archive per catalog per day.

**So the far end decides, and it is asked cheaply.** The `ETag` that came back with the last fetch
goes out again as `If-None-Match`, and a catalog nobody has touched answers `304` with no body at
all. When something *has* changed, the whole tree is replaced — which also repairs a skill somebody
edited in place, because the repository is the source of truth and a local edit inside a catalog is
drift rather than work.

## Nothing installed is touched until the new one is known to be good

Every fetch lands in a temporary directory, is read, and is validated there. A catalog that is not a
catalog, holds no skills, or holds a skill no brain would load is refused before anything below
`data/skills/` has been opened for writing. Only then is the swap made, staged and renamed, and put
back whole if any part of it fails.

## Two catalogs are not allowed to be one operation

`refresh` checks every catalog, each inside its own guard, and one that cannot be reached is reported
rather than raised. An install with four catalogs where the third repository has been deleted is
three catalogs that are fine, and an update that failed the whole run over it would leave a machine
unable to move forward at all. The same reasoning is why the caller runs this *after* the release has
already landed: a catalog is not allowed to roll back a healthy update of rundesk itself.
"""

import contextlib
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterator, List, NamedTuple, Optional

from rundesk.core import paths
from rundesk.skills import library, needs
from rundesk.utils import archives, files, locking

#: Where a catalog rundesk ships stands inside the release. Derived from this file rather than from
#: `paths.program()`, because it is a part of this package and moves with it.
SHIPPED = Path(__file__).resolve().parent / "bundled"

#: Where the general catalog rundesk depends on is fetched from. Not the version-coupled one, which
#: ships inside the release and is never fetched from anywhere.
DEPENDED_SOURCE = "https://github.com/rundesk-ai/rundesk-skills"

#: What `local` says it is. Written by the install, because a catalog is a directory holding a
#: manifest and the owner's own skills are a catalog like any other.
MINE_MANIFEST = {
    "schema": library.SCHEMA,
    "name": library.MINE,
    "version": "0",
    "description": "Skills you wrote yourself. Rundesk never fetches, updates or removes anything "
                   "in here.",
}

#: Where a repository's tree is asked for. The default branch's tip, as a tarball.
ARCHIVE = "https://api.github.com/repos/{slug}/tarball"

#: The only kind of published source this release understands. Narrow on purpose: every accepted
#: shape is one this product has to keep fetching correctly for ever, and a local directory already
#: covers "somewhere else entirely" for anybody who needs it.
REPOSITORY = re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")

#: What this product calls itself when it asks somebody else for something.
USER_AGENT = "rundesk"

#: How long a fetch is given before it is a failure rather than a wait.
FETCH_SECONDS = 60


class Refused(Exception):
    """Something that may not be done to a catalog, named with why."""


class HalfInstalled(Exception):
    """A swap that failed and could not be put back, naming what stands where.

    Its own kind, because every other failure here leaves the install exactly as it was found and
    this one does not. A caller that reported it in the same words as the others would be telling
    somebody nothing had happened while a catalog sat half-replaced.
    """


class Coming(NamedTuple):
    """A catalog that has been fetched and read, and has not been installed.

    Exists so that the decision to install is the caller's and is made on facts rather than on a
    promise. `rundesk skills install` shows every one of these fields and changes nothing; the same
    call with `--confirm` goes on to `installed`. One fetch, one validation, two outcomes.

    **`at` and `manifest` are `None` exactly when `fresh` is `False`** — the far end answered that
    nothing has changed, so there is nothing to look at and nothing to do.
    """

    source: str
    fresh: bool
    etag: str
    at: Optional[Path]
    manifest: Optional[library.Manifest]
    skills: List[str]


class Installed(NamedTuple):
    """What installing or updating a catalog actually did.

    `before` is `""` when the catalog was not there. `retired` are the skills it used to hold and
    does not any more — named rather than counted, because each one is a grant somewhere that has to
    be taken away and somebody has to be told which.
    """

    name: str
    before: str
    after: str
    skills: List[str]
    retired: List[str]


class Refreshed(NamedTuple):
    """One catalog's outcome from a refresh. `why` is `""` when it worked.

    A sentence rather than an exception, because the caller's job is to go on to the next catalog and
    an exception is the shape that stops a loop.
    """

    name: str
    before: str
    after: str
    retired: List[str]
    why: str


#: How a catalog's tree is brought down: given where it is, the `ETag` last seen, and a directory to
#: work in, it puts the tree there and says what to send next time. `None` means the far end
#: answered that nothing has changed.
#:
#: An argument rather than an import, and resolved inside the body rather than bound in a signature,
#: because this is the only thing in this package that leaves the machine. Every suite drives the
#: whole of it offline.
Fetching = Callable[[str, str, Path], Optional["Brought"]]


class Brought(NamedTuple):
    """A tree that was fetched, and what to send next time to find out whether it changed."""

    at: Path
    etag: str


def may_be_fetched(name: str) -> bool:
    """Whether this catalog is one rundesk brings down from somewhere.

    Two are not. `local` is the owner's own directory and there is nothing on the far end of it. The
    catalog that ships in the release is version-coupled — what is in it is how to operate *this*
    rundesk — so it comes out of the release rather than off a repository that moves on its own
    schedule, and a machine on an older release is never handed a newer release's instructions.

    Asked here rather than at each verb that fetches, so the knowledge lives in one place. The build
    this replaces spread it across four functions and they came apart.
    """
    return name not in (library.MINE, library.BUNDLED)


def may_be_removed(name: str) -> bool:
    """Whether `rundesk skills remove` may take this catalog away.

    Three cannot. `local` is where the owner's own skills stand, and removing it would delete work
    rundesk did not write. The other two are dependencies of the product rather than choices made at
    install time: an agent is expected to be able to operate the thing running it, and the skills
    that teach it how are no more optional than the command is.
    """
    return name not in (library.MINE, library.BUNDLED, library.DEPENDED)


def reserved(name: str) -> str:
    """Why a catalog somebody is installing may not be called this, or `""` when it may.

    **Policy, asked where somebody typed something** — not in `installed`, which is the mechanism and
    has to be able to place the version-coupled catalog out of the release under exactly the name
    this refuses. Putting the rule in the mechanism made it refuse its own legitimate caller, which
    is the shape of thing that gets "fixed" with a flag that turns the check off.

    `rundesk-skills` is deliberately *not* reserved: it is installed by fetching it, which is the
    ordinary path, and reserving it would mean the ordinary path had to go round its own rule.
    """
    if name == library.MINE:
        return (f"{name} is where your own skills stand and is not installed from anywhere — put a "
                "skill of your own straight into it")
    if name == library.BUNDLED:
        return (f"{name} is the catalog that ships inside the release, and is replaced out of it on "
                "every update — a catalog installed under that name would be overwritten")
    return ""


def source_trouble(said: str) -> str:
    """Why `said` is not somewhere a catalog can be fetched from, or `""` when it is.

    Two shapes and no others: a directory on this machine, or a GitHub repository. Narrow because
    every shape accepted here is one this product has to go on fetching correctly for ever, and the
    local path already answers "somewhere else entirely" for anybody whose catalog is not on GitHub —
    they clone it themselves and point rundesk at the clone.
    """
    if not said or not said.strip():
        return "a catalog needs somewhere to come from"
    said = said.strip()
    if REPOSITORY.match(said):
        return ""
    at = Path(said).expanduser()
    if at.is_dir():
        return ""
    if at.exists():
        return f"{said} is a file — a catalog comes from a directory or a GitHub repository"
    return (f"{said} is neither a directory on this machine nor an "
            "https://github.com/<owner>/<repo> URL")


def archive_url(source: str) -> str:
    """Where a repository's tree is asked for. Refused when the source is not a repository."""
    found = REPOSITORY.match(source.strip())
    if found is None:
        raise Refused(f"{source} is not a GitHub repository")
    return ARCHIVE.format(slug=f"{found.group('owner')}/{found.group('repo')}")


@contextlib.contextmanager
def brought(source: str, etag: str = "", fetching: Optional[Fetching] = None) -> Iterator[Coming]:
    """Fetch a catalog and read it, without installing anything. Cleaned up on the way out.

    Everything that can fail on somebody else's account fails in here, before a byte below
    `data/skills/` has been opened for writing: unreachable, not an archive, not a catalog, holding
    no skills, holding a skill no brain would load. What comes out is either "nothing has changed" or
    a catalog that is known to be good.

    A context manager because the fetched tree lives in a temporary directory and every path out of
    here — installed, previewed, refused — has to remove it. Left to the caller, that is a cleanup
    three callers each have to remember, and the one that forgets leaves an archive in `/tmp` per
    update per catalog for ever.
    """
    trouble = source_trouble(source)
    if trouble:
        raise Refused(trouble)
    fetch = fetching or _brought_down
    working = Path(tempfile.mkdtemp(prefix="rundesk-catalog-"))
    try:
        came = fetch(source.strip(), etag, working)
        if came is None:
            yield Coming(source.strip(), False, etag, None, None, [])
            return
        tree = _the_tree_in(came.at)
        manifest = library.read_manifest(tree)
        yield Coming(source.strip(), True, came.etag, tree, manifest, _checked(tree, manifest.name))
    finally:
        shutil.rmtree(working, ignore_errors=True)


def installed(coming: Coming, saying: Optional[Callable[[str], None]] = None) -> Installed:
    """Put a fetched catalog in place for the first time. Refused when one of that name is there.

    Held under the install's own lock and built under a staged name, the same way an agent is: an
    interruption anywhere before the final rename leaves `.<name>.incoming`, which every walk skips
    and the next install discards, and never a directory wearing a catalog's own name that is not one.
    """
    if not coming.fresh or coming.at is None or coming.manifest is None:
        raise Refused("nothing was fetched, so there is nothing to install")
    name = coming.manifest.name
    said = saying or (lambda _line: None)

    with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
        at = library.stands(name)
        if (at / library.TREE / library.MANIFEST).is_file():
            raise Refused(f"{name} is already installed — rundesk skills update {name} checks it "
                          "for changes")
        at.parent.mkdir(parents=True, exist_ok=True)
        building = files.incoming_of(at)
        files.discard(building)
        try:
            building.mkdir(parents=True)
            shutil.copytree(coming.at, building / library.TREE, symlinks=False)
            library.stated_provenance(
                building, library.Provenance(coming.source, coming.etag,
                                             coming.manifest.version, library.stamped()))
            os.replace(building, at)
        except BaseException:
            files.discard(building)
            raise
    said(f"{name} {coming.manifest.version}: installed")
    return Installed(name, "", coming.manifest.version, coming.skills, [])


def update(name: str, fetching: Optional[Fetching] = None,
           saying: Optional[Callable[[str], None]] = None) -> Installed:
    """Check a catalog against where it came from, and replace its tree when it has changed.

    Returns what happened. `before == after` and an empty `retired` is the ordinary answer and means
    nothing was fetched at all — the far end said so, and this cost one conditional request.
    """
    settled = library.read(name)
    if not may_be_fetched(name):
        raise Refused(f"{name} is the catalog your own skills stand in — nothing fetches into it")
    if settled.provenance is None:
        raise Refused(f"nothing is written down about where {name} came from, so it cannot be "
                      f"checked — rundesk skills remove {name} --confirm and install it again")

    was = library.read_manifest(settled.at / library.TREE)
    holding = library.found(settled.at / library.TREE)
    said = saying or (lambda _line: None)

    with brought(settled.provenance.source, settled.provenance.etag, fetching) as coming:
        if not coming.fresh or coming.at is None or coming.manifest is None:
            said(f"{name} {was.version}: up to date")
            return Installed(name, was.version, was.version, holding, [])
        if coming.manifest.name != name:
            raise Refused(f"{settled.provenance.source} now calls itself {coming.manifest.name} "
                          f"and this install has it as {name} — install it under its new name and "
                          f"remove {name}")
        retired = [one for one in holding if one not in coming.skills]
        _swapped(settled.at, coming)
    said(f"{name} {was.version} -> {coming.manifest.version}")
    for one in retired:
        said(f"{one} is no longer in {name}")
    return Installed(name, was.version, coming.manifest.version, coming.skills, retired)


def remove(name: str) -> List[str]:
    """Take a catalog away whole. Returns the skills that went with it.

    Named rather than counted, because each is a grant standing in some agent's directory that the
    caller has to take away and somebody has to be told about.
    """
    settled = library.read(name)
    if not may_be_removed(name):
        raise Refused(_why_it_stays(name))
    holding = library.found(settled.at / library.TREE)
    with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
        going = files.outgoing_of(settled.at)
        files.discard(going)
        # Renamed aside and then removed, rather than removed where it stands. A `rmtree` that fails
        # halfway leaves a directory that is still a catalog by every test — it has a manifest — and
        # is missing an arbitrary half of its skills. The rename is the moment it stops being one,
        # and it is atomic.
        os.rename(settled.at, going)
        files.discard(going)
    return holding


def what_stays(name: str) -> str:
    """Why this catalog cannot be removed, or `""` when it can.

    The words are here rather than at the caller so that every place that has to explain it explains
    it the same way — the command that refuses, and the preview that says what a removal would do.
    """
    return "" if may_be_removed(name) else _why_it_stays(name)


def place_mine(saying: Optional[Callable[[str], None]] = None) -> bool:
    """Make the catalog the owner's own skills stand in, if it is not there. `True` when it was made.

    Made by the install rather than by whatever first writes a skill into it, so a fresh machine has
    the whole shape from the first moment and somebody looking for where to put a skill of their own
    finds a directory rather than having to know to create one.
    """
    at = library.stands(library.MINE)
    manifest = at / library.TREE / library.MANIFEST
    if manifest.is_file():
        return False
    (at / library.TREE / library.INSIDE).mkdir(parents=True, exist_ok=True)
    files.write_json(manifest, dict(MINE_MANIFEST))
    (saying or (lambda _line: None))(f"made {at}")
    return True


def place_bundled(saying: Optional[Callable[[str], None]] = None) -> bool:
    """Put the catalog rundesk ships in place if it is not there. `True` when it was placed.

    **From the release rather than from the network**, which is the difference from the build this
    replaces: there, a machine that could not reach GitHub finished installing with no skills at all
    and nothing saying why. Here the skills rundesk ships are part of the release, they are reviewed
    with the code that ships them, and a fresh install has them before it has a network.

    **Replaced out of the release every time, rather than only when it is absent.** What is in it is
    how to operate *this* rundesk and how to write a skill for it, so it is version-coupled: an
    install that moved forward and kept the previous release's copy would be handing every agent
    instructions for a rundesk it is no longer running. Making the release the source of truth
    unconditionally means there is no comparison here to get wrong, and the cost is a copy of four
    small files per update.

    **Takes no `fetching`, and that is the guarantee rather than an omission.** The tree is a
    directory inside this release, so there is no seam to replace and nothing here can reach the
    network however it is called — a machine with no network would otherwise fail at the one step
    that exists to work without one.
    """
    if not SHIPPED.is_dir():
        raise Refused(f"this release ships no catalog at {SHIPPED}")
    with brought(str(SHIPPED)) as coming:
        if library.BUNDLED not in library.known():
            installed(coming, saying)
            return True
        _swapped(library.stands(library.BUNDLED), coming)
    (saying or (lambda _line: None))(
        f"{library.BUNDLED} is the copy this release ships")
    return False


def depended(fetching: Optional[Fetching] = None,
              saying: Optional[Callable[[str], None]] = None) -> bool:
    """Install the general catalog rundesk depends on if it is not there. `True` when it was.

    Fetched rather than shipped, and that is the difference from `place_bundled`. Nothing in it is
    coupled to a version — how to write a pull request does not change when rundesk does — so it
    lives on its own release schedule where it can be corrected without cutting a rundesk release.

    It follows that a machine with no network finishes an install without it, and says so. That is
    the honest answer and it is survivable: the version-coupled catalog is already in place, so the
    agent knows how to operate the thing running it and how to ask for the rest.
    """
    if library.DEPENDED in library.known():
        return False
    with brought(DEPENDED_SOURCE, "", fetching) as coming:
        if coming.manifest is not None and coming.manifest.name != library.DEPENDED:
            raise Refused(f"{DEPENDED_SOURCE} calls itself {coming.manifest.name} and this release "
                          f"expects {library.DEPENDED}")
        installed(coming, saying)
    return True


def refresh(fetching: Optional[Fetching] = None,
            saying: Optional[Callable[[str], None]] = None) -> List[Refreshed]:
    """Bring every catalog up to date, one at a time, and never let one stop the others.

    Run after an install or an update has already succeeded, and deliberately not part of it: a
    repository somebody deleted is not a reason to roll back a release that landed correctly.

    Each catalog is checked inside its own guard and a failure becomes a sentence in its own
    `Refreshed`. An install with four catalogs where the third has gone is three catalogs that are
    fine, and this is what makes that true rather than what hopes it.
    """
    said = saying or (lambda _line: None)
    outcomes: List[Refreshed] = []
    try:
        place_mine(said)
    except (Refused, library.Refused, OSError) as why:
        # Guarded like its siblings. Unguarded, a failure here escaped `refresh` altogether and the
        # caller reported one coarse "the catalogs could not be checked" for the whole install —
        # throwing away the per-catalog granularity every other step in this function preserves.
        outcomes.append(Refreshed(library.MINE, "", "", [], str(why)))
    try:
        place_bundled(said)
    except (Refused, library.Refused, archives.Refused, OSError, urllib.error.URLError) as why:
        outcomes.append(Refreshed(library.BUNDLED, "", "", [], str(why)))
    try:
        depended(fetching, said)
    except (Refused, library.Refused, archives.Refused, OSError, urllib.error.URLError) as why:
        outcomes.append(Refreshed(library.DEPENDED, "", "", [], str(why)))

    for name in library.known():
        if not may_be_fetched(name):
            continue
        try:
            did = update(name, fetching, said)
            outcomes.append(Refreshed(name, did.before, did.after, did.retired, ""))
        except (Refused, library.Refused, archives.Refused, OSError,
                urllib.error.URLError) as why:
            outcomes.append(Refreshed(name, "", "", [], str(why)))
            said(f"{name} could not be checked: {why}")
    return outcomes


def _why_it_stays(name: str) -> str:
    """The sentence explaining a catalog rundesk will not remove."""
    if name == library.MINE:
        return (f"{name} is where your own skills stand — removing it would delete work rundesk "
                "did not write")
    if name == library.BUNDLED:
        return (f"{name} ships inside this release and depends on its version, so it is not "
                "removable — revoke the skills you do not want instead")
    return (f"{name} is a catalog rundesk depends on and is not removable — revoke the skills you "
            "do not want instead")


def _swapped(at: Path, coming: Coming) -> None:
    """Replace a catalog's tree with the one just fetched, putting the old one back if it fails.

    Staged, then two renames, then the record. The order is the guarantee: the new tree is fully on
    disk under a staged name before anything that is standing gets moved, so the window in which
    neither is in place is one rename wide.

    **The record is written last and inside the lock.** A provenance naming the new `ETag` beside a
    tree that is still the old one is the state that makes every future check answer `304` forever,
    which is a catalog frozen at a version nobody can see is wrong.
    """
    if coming.at is None or coming.manifest is None:
        raise Refused("nothing was fetched, so there is nothing to swap")
    with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
        tree = at / library.TREE
        pending = files.incoming_of(tree)
        aside = files.outgoing_of(tree)
        files.discard(pending)
        files.discard(aside)
        shutil.copytree(coming.at, pending, symlinks=False)
        moved = False
        try:
            if tree.exists():
                os.rename(tree, aside)
                moved = True
            os.rename(pending, tree)
        except BaseException:
            files.discard(pending)
            if moved and not tree.exists():
                try:
                    os.rename(aside, tree)
                except OSError as put_back:
                    raise HalfInstalled(
                        f"{at.name} could not be replaced and its own tree could not be put back — "
                        f"it is at {aside} ({put_back})") from put_back
            raise
        library.stated_provenance(
            at, library.Provenance(coming.source, coming.etag, coming.manifest.version,
                                   library.stamped()))
        files.discard(aside)


def _checked(tree: Path, name: str) -> List[str]:
    """Every skill in a fetched tree, refusing the catalog if any of them is unusable.

    **All of the broken ones, not the first.** A refusal naming one is a refusal somebody fixes and
    then meets again, and a catalog with three bad skills takes three rounds to install. Anything
    that finds its own work fails when it finds none, so a catalog holding no skills at all is
    refused here too: a repository pointed at the wrong branch installs silently otherwise, and the
    symptom arrives days later as an agent that does not know something.
    """
    holding = library.found(tree)
    if not holding:
        raise Refused(f"{name} declares no skills — there is nothing under "
                      f"{library.INSIDE}/ holding a {library.DECLARED}")
    trouble = []
    for one in holding:
        why = needs.env_trouble(tree / library.INSIDE / one)
        if why:
            trouble.append(why)
    if trouble:
        raise Refused(f"{name} holds {len(trouble)} skill(s) that cannot be used: "
                      + "; ".join(trouble))
    return holding


def _the_tree_in(at: Path) -> Path:
    """The catalog's own tree inside what was unpacked, allowing for one wrapper directory.

    A repository archive from GitHub holds everything under a single directory named for the
    repository and the commit, so the manifest is never at the top. Rather than knowing that, this
    looks: the tree is wherever the manifest is, at the top or one below it.

    Refused when there is no manifest either place, and the wording says what was expected — the
    person meeting this is usually somebody publishing a catalog for the first time, and "not a
    catalog" is not something they can act on.
    """
    if (at / library.MANIFEST).is_file():
        return at
    inside = [one for one in sorted(at.iterdir()) if one.is_dir() and not one.is_symlink()]
    if len(inside) == 1 and (inside[0] / library.MANIFEST).is_file():
        return inside[0]
    raise Refused(f"there is no {library.MANIFEST} at the top of what was fetched — a catalog is a "
                  f"directory with one, beside a {library.INSIDE}/ directory")


def _brought_down(source: str, etag: str, into: Path) -> Optional[Brought]:
    """Put a catalog's tree in `into`. The only thing in this package that leaves the machine.

    A local directory is copied rather than fetched, which is what makes the whole of this testable
    and is also how somebody works on a catalog before publishing it. It has no `ETag` and is read
    every time: a directory being edited is one whose whole point is that the last read is stale.
    """
    at = Path(source).expanduser()
    if at.is_dir():
        copied = into / "unpacked"
        shutil.copytree(at, copied, symlinks=False, ignore=shutil.ignore_patterns(".git"))
        return Brought(copied, "")

    asked = urllib.request.Request(archive_url(source),
                                   headers={"User-Agent": USER_AGENT})
    if etag:
        asked.add_header("If-None-Match", etag)
    archive = into / "catalog.tar.gz"
    try:
        with urllib.request.urlopen(asked, timeout=FETCH_SECONDS) as answered, \
                open(archive, "wb") as writing:
            came_back = answered.headers.get("ETag", "")
            shutil.copyfileobj(answered, writing)
    except urllib.error.HTTPError as answered:
        # `304 Not Modified` arrives as an error and is the ordinary, cheap answer this whole
        # mechanism exists to get: nothing has changed, no body was sent, and there is nothing to do.
        #
        # Closed rather than dropped. An `HTTPError` is a response as well as an exception — it
        # holds the connection — and this is the path a machine takes once per catalog per day for
        # ever, which is the shape of thing that has to let go of what it opened.
        if answered.code == 304:
            answered.close()
            return None
        raise
    return Brought(archives.unpacked(archive, into / "unpacked"), came_back)
