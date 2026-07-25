"""What version is installed, what has been published, and moving between them.

Standard library only, and every network call is behind a seam a test can replace —
`latest` is a function passed in, so the whole of this module is exercised offline.

An update replaces the checkout in place and never touches the symlink that put
`rundesk` on your PATH, so the command keeps working across a version change.
"""

from __future__ import annotations

import json
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
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


def latest_version_online() -> str | None:
    """The newest published release, or None when the forge cannot be reached."""
    request = urllib.request.Request(RELEASES_LATEST_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        # Unreachable is not the same as up to date, and `run` says so.
        return None
    tag = payload.get("tag_name")
    return tag if isinstance(tag, str) and tag else None


def describe(current: str, latest: str | None) -> str:
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
    print(describe(current_version, published))
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
        with tarfile.open(archive) as tar:
            _safe_extract(tar, unpacked)

        roots = [p for p in unpacked.iterdir() if p.is_dir()]
        if len(roots) != 1:
            print(f"{tag} did not unpack the way a release archive should")
            return 1
        _copy_over(roots[0], repo_root)

    print(f"updated to {tag}")
    return 0


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Refuse a member that would land outside `dest` — an archive is untrusted input."""
    root = dest.resolve()
    for member in tar.getmembers():
        target = (root / member.name).resolve()
        if not str(target).startswith(str(root)):
            raise ValueError(f"refusing to extract outside the destination: {member.name}")
    tar.extractall(dest)


def _copy_over(src: Path, dst: Path) -> None:
    """Lay the new tree over the old, leaving anything the release does not ship."""
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
            if item.name in {"rundesk", "install.sh"}:
                target.chmod(0o755)
