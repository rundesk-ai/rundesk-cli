"""Safe, process-local facts about provider turns that are running now."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path

DIRECTORY = "turns"

#: What is kept about one running turn, and the whole of it (R-AGW-14).
#:
#: `started` is the machine's own answer for when that process began. **A number on its own
#: does not identify a process**: the machine reissues them, and reissues them from low
#: numbers first after a reboot — which is exactly when a record written before that reboot
#: is read, because launchd starts the gateways and `claim` looks here. Without it a turn
#: killed with its gateway went on being reported as running by whatever inherited its pid,
#: and the update that would have replaced this install waited on work that had ended days
#: before.
KEPT = ("run", "source", "surface", "conversation", "pid", "since", "started")

#: What has to be a string before a row is worth answering with.
SAID = ("run", "source", "surface", "conversation")


def _path(run_home: Path, run: str) -> Path:
    named = hashlib.sha256(run.encode("utf-8")).hexdigest()
    return Path(run_home) / DIRECTORY / f"{named}.json"


def _machine_started(pid: int):
    """When the machine says the process under this pid began, or None.

    Imported inside rather than at the top: `gateway` imports this module, so naming it up
    there would close a cycle. Asked of the one place that already knows how, rather than
    spelled a second time — two answers to "when did this start" would eventually disagree
    about one process, and this comparison is only worth anything while they cannot.
    """
    from rundesk import gateway
    return gateway.started_at(pid)


def began(run_home: Path, record: dict, started=None) -> None:
    """Publish one active turn atomically, without prompts or process arguments.

    The fingerprint is taken here rather than handed in, so no caller can publish a record
    without one — which would leave exactly the row this cannot tell from a stranger's.
    """
    path = _path(run_home, record["run"])
    kept = {key: record[key] for key in KEPT if key != "started"}
    kept["started"] = (started or _machine_started)(kept["pid"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(kept, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def ended(run_home: Path, run: str) -> None:
    _path(run_home, run).unlink(missing_ok=True)


def _rows(run_home: Path | None):
    """Every record standing here, with the path it was read from.

    A row of `None` is one nothing could parse. Records are renamed into place whole, so a
    reader never catches half of one — anything unreadable is leftover rather than in
    progress.
    """
    if run_home is None:
        return
    directory = Path(run_home) / DIRECTORY
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            yield path, None
            continue
        if not isinstance(row, dict):
            yield path, None
            continue
        yield path, row


def _running(row: dict, started) -> bool:
    """Is the turn this record names still going?

    Two questions, and the second is the one that was missing. The pid has to be there at
    all; and where the record says when its process began, the machine has to still say the
    same thing. **Missing fingerprint keeps the row, a mismatched one drops it** — the same
    asymmetry `gateway._end_left_running` holds, and for the same reason: a record from
    before there were fingerprints still names real work, and settling a live turn is worse
    than carrying a dead one for one more look.
    """
    pid = row.get("pid")
    if not isinstance(pid, int) or pid < 1:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    if not all(isinstance(row.get(key), str) for key in SAID):
        return False
    was = row.get("started")
    if not was:
        return True
    return started(pid) == was


def active(run_home: Path | None, started=None) -> list[dict]:
    """Read live provider turns, ignoring malformed or no-longer-live records."""
    ask = started or _machine_started
    found = [row for _, row in _rows(run_home) if row is not None and _running(row, ask)]
    return sorted(found, key=lambda row: (row.get("since", 0), row["run"]))


def sweep(run_home: Path | None, started=None) -> list[str]:
    """Take away what is left of turns that are no longer running, and say what went.

    **Nothing else ever removes one.** `ended` is called from the turn's own `finally`,
    which a SIGKILL, an out-of-memory kill and a power cut all skip; `Gateway.release`
    takes the record file, and `forget` takes the record, the lock and the log. None of
    them looks here. So one file per crashed turn stood for the life of the install, cost a
    liveness check on every single look at what an agent is doing, and kept `agent.forget`
    from ever removing the agent's own `run/` directory.

    Reading is left pure: `active` answers a question and this one is the only thing that
    takes anything away.
    """
    ask = started or _machine_started
    gone = []
    for path, row in _rows(run_home):
        if row is not None and _running(row, ask):
            continue
        with contextlib.suppress(OSError):
            path.unlink()
            gone.append(path.name)
    return sorted(gone)
