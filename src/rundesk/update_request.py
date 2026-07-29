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
from rundesk import updater

ACTIVE = {"pending", "running"}
FINAL = {"succeeded", "rolled_back", "failed"}


class Unreadable(RuntimeError):
    """The durable request exists but cannot be trusted."""


def path() -> Path:
    return data_home() / "update-request.json"


def maintenance_path(name: str, run_home: Path) -> Path:
    """The update marker shared by one gateway and its channel adapters.

    It lives with runtime state rather than owner data. A worker that is restarted after
    standing a gateway down can therefore find exactly which supervised gateway it owes
    back to the owner, without confusing one they deliberately stopped with maintenance.
    """
    # The adapter receives this exact path, so the filename is an internal identity rather
    # than a second opinion about which gateway names are valid. Encoding also keeps a dot
    # or non-ASCII name from becoming another path component (R-UPD-43, R-UPD-44).
    identity = name.encode("utf-8").hex()
    return run_home / f".{identity}.update-maintenance"


def begin_maintenance(name: str, run_home: Path) -> Path:
    target = maintenance_path(name, run_home)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            handle.write("Rundesk is installing an update.\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
    return target


def finish_maintenance(name: str, run_home: Path) -> None:
    maintenance_path(name, run_home).unlink(missing_ok=True)


def maintaining(name: str, run_home: Path) -> bool:
    return maintenance_path(name, run_home).is_file()


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
    """One outcome, as `rundesk update --status` prints it and as an agent delivers it."""
    state = str(row.get("state") or "unknown").replace("_", " ")
    result = str(row.get("result") or "").strip()
    # **Only what succeeded is linked** (R-UPD-46, R-UPD-47). The version on a failed or
    # rolled-back request is the one that answered afterwards, which for a rollback is the
    # release the owner was already on — a release note offered beside "rolled back" reads
    # as the target having landed, which is the one thing this outcome exists to deny.
    #
    # **Behind the number, and exactly once** (#108). This used to append the release note
    # as a line of its own, directly under the line the update had already printed — so a
    # worker-run update handed the owner the same URL on two consecutive lines. Two things
    # fixed it: the number carries the link rather than a line beside it, and the link is
    # added here only when the transcript this is wrapping does not already carry that URL.
    #
    # Compared against the URL itself, never against the wording around it, so this never
    # becomes a dependency on how the updater happens to phrase its own output.
    named = row.get("version")
    version = f" ({named})" if named else ""
    if named and row.get("state") == "succeeded":
        where = updater.release_url(named)
        if where and where not in result:
            version = f" ({updater.linked(named)})"
    return f"Rundesk update {state}{version}" + (f": {result}" if result else "")
