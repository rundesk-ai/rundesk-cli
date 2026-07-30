"""Durable, supervisor-owned gateway restart requests."""

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
FINAL = {"succeeded", "failed"}
DIRECTORY = "restart-requests"


class Unreadable(RuntimeError):
    """A durable restart request exists but cannot be trusted."""


def home() -> Path:
    return data_home() / DIRECTORY


def path(name: str) -> Path:
    identity = name.encode("utf-8").hex()
    return home() / f"{identity}.json"


@contextlib.contextmanager
def _locked(name: str):
    target = path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_suffix(".lock")
    with open(lock, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _read(name: str) -> dict | None:
    target = path(name)
    if not target.exists():
        return None
    try:
        row = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as why:
        raise Unreadable(f"restart request for '{name}' cannot be read: {why}") from why
    if not isinstance(row, dict) or row.get("name") != name:
        raise Unreadable(f"restart request for '{name}' has the wrong identity")
    return row


def _write(name: str, row: dict) -> None:
    target = path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            json.dump(row, handle, sort_keys=True)
            handle.write("\n")
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


def read(name: str) -> dict | None:
    with _locked(name):
        return _read(name)


def active() -> list[dict]:
    directory = home()
    if not directory.is_dir():
        return []
    rows = []
    for target in sorted(directory.glob("*.json")):
        try:
            name = bytes.fromhex(target.stem).decode("utf-8")
        except (UnicodeDecodeError, ValueError) as why:
            raise Unreadable(f"restart request has an invalid filename: {target.name}") from why
        row = read(name)
        if row and row.get("state") in ACTIVE:
            rows.append(row)
    return sorted(rows, key=lambda row: (row.get("requested_at", 0), row["name"]))


def queue(name: str, origin: dict) -> tuple[dict, bool]:
    """Queue one restart per gateway and coalesce an active duplicate (R-GW-43)."""
    with _locked(name):
        existing = _read(name)
        if existing and existing.get("state") in ACTIVE:
            return existing, False
        kept_origin = {
            key: origin[key]
            for key in ("agent", "run", "channel", "conversation")
            if isinstance(origin.get(key), str) and origin[key]
        }
        waits_for_delivery = all(
            kept_origin.get(key) for key in ("run", "channel", "conversation")
        )
        row = {
            "id": uuid.uuid4().hex,
            "name": name,
            "state": "pending",
            "requested_at": time.time(),
            "attempts": 0,
            "delivered": False,
            "ready": not waits_for_delivery,
            "origin": kept_origin,
        }
        _write(name, row)
        return row, True


def claim(name: str) -> dict | None:
    with _locked(name):
        row = _read(name)
        if not row or row.get("state") not in ACTIVE:
            return None
        row["state"] = "running"
        row["started_at"] = time.time()
        row["attempts"] = int(row.get("attempts") or 0) + 1
        _write(name, row)
        return row


def waiting(name: str, run: str | None) -> bool:
    if not run:
        return False
    row = read(name)
    origin = (row or {}).get("origin") or {}
    return bool(
        row and row.get("state") in ACTIVE and not row.get("ready")
        and origin.get("run") == run
    )


def ready(name: str, run: str) -> None:
    """Release a queued self-restart only after its final channel records were sent."""
    with _locked(name):
        row = _read(name)
        origin = (row or {}).get("origin") or {}
        if (row and row.get("state") in ACTIVE and origin.get("run") == run
                and not row.get("ready")):
            row["ready"] = True
            row["ready_at"] = time.time()
            _write(name, row)


def finish(name: str, request_id: str, state: str, result: str) -> dict:
    if state not in FINAL:
        raise ValueError(f"{state!r} is not a final restart state")
    with _locked(name):
        row = _read(name) or {"id": request_id, "name": name}
        if row.get("id") != request_id:
            raise RuntimeError("the restart request changed while its worker was running")
        row.update({
            "state": state,
            "finished_at": time.time(),
            "result": result[-20_000:],
            "delivered": False,
        })
        _write(name, row)
        return row


def deliverable(agent: str) -> dict | None:
    row = read(agent)
    if not row or row.get("state") not in FINAL or row.get("delivered"):
        return None
    origin = row.get("origin") or {}
    return row if origin.get("agent") == agent else None


def delivered(name: str, request_id: str) -> None:
    with _locked(name):
        row = _read(name)
        if row and row.get("id") == request_id:
            row["delivered"] = True
            row["delivered_at"] = time.time()
            _write(name, row)


def summary(row: dict) -> str:
    state = str(row.get("state") or "unknown").replace("_", " ")
    result = str(row.get("result") or "").strip()
    return f"Rundesk restart {state}" + (f": {result}" if result else "")
