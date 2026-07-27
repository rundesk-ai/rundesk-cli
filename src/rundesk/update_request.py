"""One durable, supervisor-owned request to update this running install."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
import uuid
from pathlib import Path

from rundesk import data_home

ACTIVE = {"pending", "running"}
FINAL = {"succeeded", "rolled_back", "failed"}


class Unreadable(RuntimeError):
    """The durable request exists but cannot be trusted."""


def path() -> Path:
    return data_home() / "update-request.json"


def _lock_path() -> Path:
    return data_home() / "update-request.lock"


@contextlib.contextmanager
def _locked():
    try:
        data_home().mkdir(parents=True, exist_ok=True)
        with open(_lock_path(), "a+", encoding="utf-8") as handle:
            os.chmod(_lock_path(), 0o600)
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield
    except OSError as why:
        raise Unreadable(f"could not use {_lock_path()}: {why}") from why


def _read() -> dict | None:
    try:
        row = json.loads(path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as why:
        raise Unreadable(f"could not read {path()}: {why}") from why
    if not isinstance(row, dict):
        raise Unreadable(f"{path()} does not contain an update request")
    return row


def read() -> dict | None:
    with _locked():
        return _read()


def _write(row: dict) -> None:
    target = path()
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            handle.write(json.dumps(row, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def queue(origin: dict) -> tuple[dict, bool]:
    """Queue once; a duplicate observes the same request rather than starting another."""
    with _locked():
        existing = _read()
        if existing and existing.get("state") in ACTIVE:
            return existing, False
        row = {
            "id": uuid.uuid4().hex,
            "state": "pending",
            "requested_at": time.time(),
            "attempts": 0,
            "delivered": False,
            "origin": {
                key: origin[key]
                for key in ("agent", "run", "channel", "conversation")
                if isinstance(origin.get(key), str) and origin[key]
            },
        }
        _write(row)
        return row, True


def claim() -> dict | None:
    with _locked():
        row = _read()
        if not row or row.get("state") not in ACTIVE:
            return None
        row["state"] = "running"
        row["started_at"] = time.time()
        row["attempts"] = int(row.get("attempts") or 0) + 1
        _write(row)
        return row


def finish(request_id: str, state: str, result: str, version: str | None = None) -> dict:
    if state not in FINAL:
        raise ValueError(f"{state!r} is not a final update state")
    with _locked():
        row = _read() or {"id": request_id}
        if row.get("id") != request_id:
            raise RuntimeError("the update request changed while its worker was running")
        row.update({
            "state": state,
            "finished_at": time.time(),
            "result": result[-20_000:],
            "version": version,
            "delivered": False,
        })
        _write(row)
        return row


def deliverable(agent: str) -> dict | None:
    row = read()
    if not row or row.get("state") not in FINAL or row.get("delivered"):
        return None
    return row if (row.get("origin") or {}).get("agent") == agent else None


def delivered(request_id: str) -> None:
    with _locked():
        row = _read()
        if row and row.get("id") == request_id:
            row["delivered"] = True
            row["delivered_at"] = time.time()
            _write(row)


def summary(row: dict) -> str:
    state = str(row.get("state") or "unknown").replace("_", " ")
    version = f" ({row['version']})" if row.get("version") else ""
    result = str(row.get("result") or "").strip()
    return f"Rundesk update {state}{version}" + (f": {result}" if result else "")
