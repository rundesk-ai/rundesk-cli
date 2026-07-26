"""What version is installed, what has been published, and moving between them.

Standard library only, and every network call is behind a seam a test can replace —
`latest` is a function passed in, so the whole of this module is exercised offline.

An update replaces the checkout in place and never touches the symlink that put
`rundesk` on your PATH, so the command keeps working across a version change.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Callable

REPO_SLUG = "rundesk-ai/rundesk-cli"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"
ARCHIVE_URL = f"https://github.com/{REPO_SLUG}/archive/refs/tags/{{tag}}.tar.gz"
HTTP_TIMEOUT = 5
DOWNLOAD_TIMEOUT = 60
USER_AGENT = "rundesk-cli-updater"

_VERSION_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(value: str) -> tuple[int, int, int] | None:
    """`v1.2.3` and `1.2` alike; anything that is not a version at all is None."""
    match = _VERSION_RE.match(value.strip())
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def is_newer(latest: str, local: str) -> bool:
    there, here = parse_version(latest), parse_version(local)
    # A version we cannot read is not a reason to claim an update: saying "behind"
    # on a garbled tag would send someone chasing a release that does not exist.
    if there is None or here is None:
        return False
    return there > here


#: Told apart because they need different things of the reader: one is "wait and try again",
#: the other is "nothing has been published, or you cannot see it".
UNREACHABLE = "unreachable"
NOTHING_PUBLISHED = "nothing-published"


def latest_version_online() -> tuple[str | None, str | None]:
    """The newest published release, and which kind of nothing it was when there is none.

    Both are returned rather than one being left somewhere for the caller to pick up. Which
    kind of nothing it was is part of this answer — "we could not ask" and "there is nothing
    there" send a reader somewhere completely different — and a look-up whose second half
    was a module global held whatever the last real call left in it, which is precisely
    wrong when the whole point of the seam is that a test replaces the call.

    The request carries no credentials. rundesk is published in the open, so a token would
    buy nothing but rate-limit headroom for a question asked once in a while — and an
    earlier version read GITHUB_TOKEN from the environment, which meant a machine that
    happened to have one exported sent it on a check nobody asked to authenticate.
    """
    request = urllib.request.Request(RELEASES_LATEST_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        # 404 answers plainly: either nothing is published, or this repository is not visible
        # without credentials. Reporting that as "could not reach" sends someone to check
        # their network when the answer is that there is nothing to find.
        #
        # 403 is the opposite and was lumped in with it. It means the question was refused,
        # almost always the anonymous rate limit — sixty an hour per address, which a shared
        # or NAT'd one reaches on somebody else's traffic. Answering "nothing is published"
        # there is a confident falsehood about a release that exists, and it is the same
        # mistake as reading "could not ask" as "you are current" (R-UPD-19), pointed the
        # other way. Not knowing is its own answer.
        return None, (NOTHING_PUBLISHED if err.code == 404 else UNREACHABLE)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None, UNREACHABLE
    # A shape we did not expect — an array, a rate-limit page parsed as JSON — reads as
    # "could not tell", never as a crash. This runs behind whatever the user typed.
    if not isinstance(payload, dict):
        return None, UNREACHABLE
    tag = payload.get("tag_name")
    if isinstance(tag, str) and tag:
        return tag, None
    return None, UNREACHABLE


def tag_matches(tag: str, version: str) -> bool:
    """Does a release tag name the same version the command reports?

    The one rule holding the whole update story together. A release tagged differently from
    what `rundesk version` says is a release nobody can reason about: the command names one
    thing, the update it offers another, and `is_newer` compares against a number that was
    never true. Checked when a release is published, and here, so the rule itself is testable.
    """
    return tag.strip().lstrip("v") == version.strip()


def describe(current: str, latest: str | None, why: str | None = None) -> str:
    """One line, state first. Whoever reads this needs to know which of four situations
    they are in before they need anything else about it."""
    if latest is None and why == NOTHING_PUBLISHED:
        return f"{current}: NO RELEASES — nothing is published, or this install cannot see them"
    if latest is None:
        return f"{current}: UNKNOWN — could not reach GitHub to check"
    if is_newer(latest, current):
        return f"{current}: OUT OF DATE — {latest} available, run: rundesk update"
    return f"{current}: UP TO DATE"


def run(
    repo_root: Path,
    current_version: str,
    check_only: bool = False,
    latest: Callable[[], tuple[str | None, str | None]] | None = None,
    apply: Callable[[Path, str], int] | None = None,
    busy: Callable[[], list] | None = None,
    pause: Callable[[], tuple] | None = None,
    resume: Callable[[list], list] | None = None,
) -> int:
    """Report where this install stands, and move it if asked.

    `latest`, `apply` and `busy` are arguments so the decision can be tested without a
    network, a download or a gateway — the part that is easy to get wrong is which of the
    outcomes is chosen, not the tarball handling.

    They resolve here rather than in the signature: a default argument is bound
    once, when the function is defined, so naming the function there would freeze
    it and quietly ignore anything that replaced it afterwards.
    """
    published, why = (latest or latest_version_online)()
    print(describe(current_version, published, why))
    if published is None:
        return 1
    if not is_newer(published, current_version):
        return 0
    if check_only:
        return 0
    # Asked before anything is fetched or laid down, and only when something is actually
    # going to be moved (R-UPD-23). An update replaces the files a running gateway is
    # made of while it is part-way through a turn — the process keeps the code it already
    # imported, so what breaks is whatever it imports *next*, minutes later, deep inside
    # a provider session, in a way that reads like anything but an update. Refusing is
    # the whole of the safety here: stopping the work would be deciding on the owner's
    # behalf that the turn was worth less than the release.
    working = (busy or (lambda: []))()
    if working:
        print(
            f"update: NOT APPLIED — work is in flight: {', '.join(sorted(working))}",
            file=sys.stderr,
        )
        print("        wait for it to finish, or stop it: rundesk stop", file=sys.stderr)
        return 1
    # Stopped before anything is laid down, and only what can be started again
    # (R-UPD-21). A gateway left running reads the new files for anything it has not
    # imported yet, and goes on serving the old code for everything it has.
    stopped, refused = (pause or (lambda: ([], None)))()
    if refused:
        print(f"update: NOT APPLIED — {refused}", file=sys.stderr)
        return 1
    try:
        moved = (apply or download_and_apply)(repo_root, published)
    finally:
        # Whatever became of the update, what was stopped to make room for it comes back
        # (R-UPD-22). The failure path is the one that matters: an update that fell over
        # must not also leave the machine's gateways down behind it.
        left_down = (resume or (lambda _names: []))(stopped)
    if left_down:
        print(
            f"update: {'applied' if moved == 0 else 'FAILED'}, but did not come back: "
            f"{', '.join(sorted(left_down))}",
            file=sys.stderr,
        )
        print("        why: rundesk logs <name>", file=sys.stderr)
        return 1
    return moved


@contextlib.contextmanager
def _only_one(repo_root: Path):
    """Hold the right to change this install, or say who already has it.

    Two updates running at once each replace what the other is mid-way through reading.
    The lock is advisory and only updates take it: a `rundesk version` racing an update is
    left to the swap being a rename, which is as close to instant as this gets.
    """
    lock = repo_root / ".update.lock"
    handle = open(lock, "w")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Busy(f"another update is already running (holding {lock})")
        yield
    finally:
        handle.close()


class Busy(Exception):
    """Something else is already changing this install."""


def download_and_apply(repo_root: Path, tag: str) -> int:
    """Fetch that tag and lay it over the checkout, leaving the PATH symlink alone."""
    try:
        with _only_one(repo_root):
            return _download_and_apply(repo_root, tag)
    except Busy as err:
        print(f"FAILED — could not update: {err}", file=sys.stderr)
        return 1


def _download_and_apply(repo_root: Path, tag: str) -> int:
    # An update replaces the program that is running it, over a network, on somebody's
    # machine. Saying which step is under way costs nothing and is the difference between
    # waiting and wondering whether to reach for Ctrl-C — which is the one thing that used
    # to break an install.
    url = ARCHIVE_URL.format(tag=tag)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / "rundesk.tar.gz"
        print(f"{tag}: downloading", flush=True)
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                archive.write_bytes(response.read())
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            print(f"{tag}: FAILED — could not download: {err}", file=sys.stderr)
            return 1

        unpacked = Path(work) / "unpacked"
        unpacked.mkdir()
        print(f"{tag}: unpacking {_size(archive)}", flush=True)
        try:
            with tarfile.open(archive) as tar:
                _safe_extract(tar, unpacked)
        except (tarfile.TarError, ValueError, OSError) as err:
            print(f"{tag}: FAILED — the download is not shaped like a release: {err}", file=sys.stderr)
            return 1

        roots = [p for p in unpacked.iterdir() if p.is_dir()]
        if len(roots) != 1:
            print(f"{tag}: FAILED — the download is not shaped like a release", file=sys.stderr)
            return 1
        print(f"{tag}: installing into {repo_root}", flush=True)
        try:
            _copy_over(roots[0], repo_root)
        except OSError as err:
            # Whatever failed, the swaps are all-or-nothing per item, so what is on disk
            # is a working install — just possibly still the old one.
            print(f"{tag}: FAILED — could not install: {err}", file=sys.stderr)
            return 1

    print(f"{tag}: UPDATED — run 'rundesk version' to confirm")
    return 0


def _size(path: Path) -> str:
    """A downloaded size a person can read, so 'unpacking' names something real."""
    try:
        kb = path.stat().st_size / 1024
    except OSError:
        return "the release"
    return f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Refuse a member that would land outside `dest` — an archive is untrusted input.

    Checking each member's own name is not enough. A link member's *target* is a second way
    out: an archive carrying a symlink to somewhere outside `dest`, followed by a file whose
    path runs through it, writes wherever the link points — the name check passes both,
    because at the time it runs the link does not exist yet for `resolve()` to follow.
    Verified against Python 3.9, the floor this project supports.

    The standard library only started refusing this by default in 3.14, so on every version
    this project targets the guard has to be ours.
    """
    root = dest.resolve()
    for member in tar.getmembers():
        if not _lands_inside(root, member.name):
            raise ValueError(f"refusing to extract outside the destination: {member.name}")
        if member.issym() or member.islnk():
            link = member.linkname
            if PurePosixPath(link).is_absolute():
                raise ValueError(f"refusing a link to an absolute path: {member.name} -> {link}")
            # A relative target is resolved from the directory the link sits in.
            if not _lands_inside(root, str(PurePosixPath(member.name).parent / link)):
                raise ValueError(f"refusing a link that points outside: {member.name} -> {link}")
    tar.extractall(dest)


def _lands_inside(root: Path, name: str) -> bool:
    """Whether `name`, taken relative to `root`, stays under it once '..' is worked out."""
    if PurePosixPath(name).is_absolute():
        return False
    target = os.path.normpath(str(root / name))
    return target == str(root) or target.startswith(str(root) + os.sep)


#: Laid down with the bit set, because a release archive does not carry one.
EXECUTABLE = {"rundesk", "install.sh"}


def _copy_over(src: Path, dst: Path) -> None:
    """Lay the new tree over the old, leaving anything the release does not ship.

    Every replacement is built beside its target first and swapped in with a rename, so an
    interruption leaves either the old thing or the new one and never half of either.

    The shape this replaces removed each directory and then copied the new one into place.
    That left `src/rundesk` — the package implementing update, version and uninstall —
    absent for the whole duration of a copy. A Ctrl-C or a full disk inside that window
    bricked every command, including the one that could have repaired it.
    """
    staged: list[tuple[Path, Path]] = []
    try:
        for item in sorted(src.iterdir()):
            pending = dst / f".{item.name}.incoming"
            _discard(pending)
            if item.is_dir():
                shutil.copytree(item, pending)
            else:
                shutil.copy2(item, pending)
                if item.name in EXECUTABLE:
                    pending.chmod(0o755)
            staged.append((pending, dst / item.name))
        # Everything is written and complete. Only now does anything the running install
        # depends on move, and each move is a rename that either happened or did not.
        for pending, target in staged:
            _swap(pending, target)
    finally:
        for pending, _ in staged:
            _discard(pending)


def _swap(pending: Path, target: Path) -> None:
    """Put `pending` where `target` is, atomically enough that no reader sees neither."""
    if target.is_dir() and not target.is_symlink():
        outgoing = target.with_name(f".{target.name}.outgoing")
        _discard(outgoing)
        os.rename(target, outgoing)
        try:
            os.rename(pending, target)
        except OSError:
            os.rename(outgoing, target)  # put back what was working
            raise
        shutil.rmtree(outgoing, ignore_errors=True)
    else:
        os.replace(pending, target)


def _discard(path: Path) -> None:
    """Remove a leftover staging path, whatever it turned out to be."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        try:
            path.unlink()
        except OSError:
            pass
