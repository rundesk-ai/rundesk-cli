"""The owner's shared integration commands.

Rundesk does not install, parse, or run these commands itself. It gives their directory
to every program it starts, and this module answers where that directory is and which
top-level entries are runnable.
"""

from __future__ import annotations

import os
from pathlib import Path

from rundesk import scripts_home


def home() -> Path:
    """Where owner-provided integration commands stand."""
    return Path(os.environ.get("RUNDESK_SCRIPTS") or scripts_home())


def commands(where: Path | None = None) -> dict[str, Path]:
    """Runnable top-level entries, by the name an agent invokes."""
    at = where if where is not None else home()
    if not at.is_dir():
        return {}
    found = {}
    for one in at.iterdir():
        if one.name.startswith("."):
            continue
        if one.is_file() and os.access(one, os.X_OK):
            found[one.name] = one
    return found
