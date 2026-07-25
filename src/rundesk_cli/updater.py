"""What version is installed, what has been published, and moving between them.

Standard library only, and every network call is behind a seam a test can replace —
`latest` is a function passed in, so the whole of this module is exercised offline.

An update replaces the checkout in place and never touches the symlink that put
`rundesk` on your PATH, so the command keeps working across a version change.
"""

from __future__ import annotations

import json
import os
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

#: Why the last look-up came back empty, when it did. Set by `latest_version_online`.
why_unavailable: str | None = None

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


def _token() -> str | None:
    """A token, if the machine has one. Needed only for a repository you cannot see anonymously."""
    for name in ("RUNDESK_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    return None


def latest_version_online() -> str | None:
    """The newest published release, or None when it cannot be had.

    `why_unavailable` carries which kind of nothing it was, because "we could not ask" and
    "there is nothing there" send a reader somewhere completely different.
    """
    global why_unavailable
    why_unavailable = None
    headers = {"User-Agent": USER_AGENT}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(RELEASES_LATEST_URL, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        # 404 answers plainly: either nothing is published, or this repository is not visible
        # without credentials. Reporting that as "could not reach" sends someone to check
        # their network when the answer is that there is nothing to find.
        why_unavailable = NOTHING_PUBLISHED if err.code in (403, 404) else UNREACHABLE
        return None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        why_unavailable = UNREACHABLE
        return None
    # A shape we did not expect — an array, a rate-limit page parsed as JSON — reads as
    # "could not tell", never as a crash. This runs behind whatever the user typed.
    if not isinstance(payload, dict):
        return None
    tag = payload.get("tag_name")
    return tag if isinstance(tag, str) and tag else None


def tag_matches(tag: str, version: str) -> bool:
    """Does a release tag name the same version the command reports?

    The one rule holding the whole update story together. A release tagged differently from
    what `rundesk version` says is a release nobody can reason about: the command names one
    thing, the update it offers another, and `is_newer` compares against a number that was
    never true. Checked when a release is published, and here, so the rule itself is testable.
    """
    return tag.strip().lstrip("v") == version.strip()


def describe(current: str, latest: str | None, why: str | None = None) -> str:
    if latest is None and why == NOTHING_PUBLISHED:
        return f"rundesk {current} — no release has been published, or this install cannot see them."
    if latest is None:
        return f"rundesk {current} — could not reach the forge to check for a newer release."
    if is_newer(latest, current):
        return f"rundesk {current} — {latest} is available. Run: rundesk update"
    return f"rundesk {current} — up to date."


def run(
    repo_root: Path,
    current_version: str,
    check_only: bool = False,
    latest: Callable[[], str | None] | None = None,
    apply: Callable[[Path, str], int] | None = None,
) -> int:
    """Report where this install stands, and move it if asked.

    `latest` and `apply` are arguments so the decision can be tested without a
    network or a download — the part that is easy to get wrong is which of the
    three outcomes is chosen, not the tarball handling.

    Both resolve here rather than in the signature: a default argument is bound
    once, when the function is defined, so naming the function there would freeze
    it and quietly ignore anything that replaced it afterwards.
    """
    published = (latest or latest_version_online)()
    print(describe(current_version, published, why_unavailable))
    if published is None:
        return 1
    if not is_newer(published, current_version):
        return 0
    if check_only:
        return 0
    return (apply or download_and_apply)(repo_root, published)


def download_and_apply(repo_root: Path, tag: str) -> int:
    """Fetch that tag and lay it over the checkout, leaving the PATH symlink alone."""
    url = ARCHIVE_URL.format(tag=tag)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / "rundesk.tar.gz"
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                archive.write_bytes(response.read())
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            print(f"could not download {tag}: {err}")
            return 1

        unpacked = Path(work) / "unpacked"
        unpacked.mkdir()
        try:
            with tarfile.open(archive) as tar:
                _safe_extract(tar, unpacked)
        except (tarfile.TarError, ValueError, OSError) as err:
            print(f"{tag} did not unpack the way a release archive should: {err}")
            return 1

        roots = [p for p in unpacked.iterdir() if p.is_dir()]
        if len(roots) != 1:
            print(f"{tag} did not unpack the way a release archive should")
            return 1
        try:
            _copy_over(roots[0], repo_root)
        except OSError as err:
            # Whatever failed, the swaps are all-or-nothing per item, so what is on disk
            # is a working install — just possibly still the old one.
            print(f"could not put {tag} in place: {err}")
            return 1

    print(f"updated to {tag}")
    return 0


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
    That left `src/rundesk_cli` — the package implementing update, version and uninstall —
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
