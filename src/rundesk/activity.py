"""Safe, process-local facts about provider turns that are running now."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

DIRECTORY = "turns"


def _path(run_home: Path, run: str) -> Path:
    named = hashlib.sha256(run.encode("utf-8")).hexdigest()
    return Path(run_home) / DIRECTORY / f"{named}.json"


def began(run_home: Path, record: dict) -> None:
    """Publish one active turn atomically, without prompts or process arguments."""
    path = _path(run_home, record["run"])
    record = {
        key: record[key]
        for key in ("run", "source", "surface", "conversation", "pid", "since")
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def ended(run_home: Path, run: str) -> None:
    _path(run_home, run).unlink(missing_ok=True)


def active(run_home: Path | None) -> list[dict]:
    """Read live provider turns, ignoring malformed or no-longer-live records."""
    if run_home is None:
        return []
    directory = Path(run_home) / DIRECTORY
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            pid = row["pid"]
            if not isinstance(pid, int) or pid < 1:
                continue
            os.kill(pid, 0)
            if not all(isinstance(row.get(key), str)
                       for key in ("run", "source", "surface", "conversation")):
                continue
            found.append(row)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return sorted(found, key=lambda row: (row.get("since", 0), row["run"]))
