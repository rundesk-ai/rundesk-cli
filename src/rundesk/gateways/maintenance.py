"""One-shot gateway notices that belong to an update rather than an ordinary start or stop.

The updater and gateway are different processes running different releases. A small intent beside
the agent is the handoff between them: the old gateway consumes `installing` on its way down, and the
new gateway consumes `installed` only when its imported version matches the target. Every read is
one-shot and expires; backups omit the transient file so a restore cannot replay maintenance.
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from rundesk.agents import directory
from rundesk.core import paths
from rundesk.utils import files

MARKER = directory.UPDATE_INTENT
VALID_FOR = 15 * 60

INSTALLING = (
    "🛠️ Installing an update — I'm installing the new rundesk update, be back shortly."
)
INSTALLED = (
    "👋 I'm back — new rundesk update installed, "
    "[release notes for v{version}]({notes})"
)

_VERSION = re.compile(r"^\d+\.\d+\.\d+$")

_FRESH = (
    "import sys;"
    "sys.path.insert(0, sys.argv[1]);"
    "from rundesk.gateways.host import run;"
    "raise SystemExit(run(sys.argv[2]))"
)


def installing(at: Path, version: str) -> None:
    """Ask the old gateway to use the update farewell once."""
    _write(at, "installing", version, None)


def installed(at: Path, version: str, notes: str) -> None:
    """Ask the target release to use the update return notice once."""
    _write(at, "installed", version, notes)


def stopping(at: Path) -> Optional[str]:
    """The update farewell, or `None` for an ordinary/malformed/stale stop. Always consumes."""
    intent = _take(at)
    return INSTALLING if intent and intent.get("phase") == "installing" else None


def starting(at: Path, version: str) -> Optional[str]:
    """The proven installed notice, or `None` for an ordinary start. Always consumes."""
    intent = _take(at)
    if not intent or intent.get("phase") != "installed" or intent.get("version") != version:
        return None
    notes = intent.get("notes")
    if not isinstance(notes, str) or not notes.startswith("https://"):
        return None
    return INSTALLED.format(version=version, notes=notes)


def clear(at: Path) -> None:
    """Remove an intent this update owns, without ever following a link."""
    try:
        files.remove_one(at / MARKER)
    except OSError:
        pass


def fresh(name: str) -> None:
    """Become a fresh gateway from the release now on disk. Returns only when exec fails.

    Used after this process waited behind an update barrier: every module it already imported may
    belong to the release that was replaced while it waited, so continuing in-process is unsafe.
    """
    os.execv(sys.executable, [sys.executable, "-c", _FRESH, str(paths.code()), name])


def _write(at: Path, phase: str, version: str, notes: Optional[str]) -> None:
    """Write one private intent whole, refusing a target version that cannot be proved later."""
    if not _VERSION.match(version):
        raise ValueError(f"{version!r} is not a release version")
    marker = at / MARKER
    if marker.is_symlink():
        raise OSError(f"{marker} is a link")
    files.write_json(marker, {
        "phase": phase,
        "version": version,
        "notes": notes,
        "issued_at": time.time(),
    }, private=True)


def _take(at: Path) -> Optional[Dict[str, Any]]:
    """Read and consume one fresh intent, returning no claim for any uncertain shape."""
    marker = at / MARKER
    if marker.is_symlink():
        clear(at)
        return None
    try:
        how, intent = files.read_json(marker)
    except OSError:
        clear(at)
        return None
    try:
        files.remove_one(marker)
    except OSError:
        # A notice is one-shot only when consumption is proved. Returning it while the marker is
        # still there would send the same maintenance message on every matching start or stop.
        return None
    if how != files.READ or not isinstance(intent, dict):
        return None
    issued = intent.get("issued_at")
    if not isinstance(issued, (int, float)):
        return None
    age = time.time() - float(issued)
    if age < 0 or age > VALID_FOR:
        return None
    version = intent.get("version")
    if not isinstance(version, str) or not _VERSION.match(version):
        return None
    return intent
