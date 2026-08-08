"""One launchd-owned daily update coordinator for each isolated Rundesk install."""

import argparse
import datetime
import hashlib
import json
import os
import plistlib
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Dict, NamedTuple, Optional

from rundesk.agents import directory
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job
from rundesk.providers import turns
from rundesk.schedules import firing
from rundesk.utils import locking, logs

UPDATE = "update"
CAPTURE_BYTES = 1024 * 1024
CAPTURES_KEPT = 3
LOG_DAYS = 30
AUTOMATIC = "RUNDESK_AUTOMATIC_UPDATE"
RUN = (
    "import sys;sys.path.insert(0,sys.argv[1]);"
    "from rundesk.commands.automatic_updates import run;raise SystemExit(run())"
)


class Coordinator(NamedTuple):
    root: Path
    into: Path
    label: str


class Reconciled(NamedTuple):
    how: str
    why: str = ""


def coordinator(root: Optional[Path] = None, into: Optional[Path] = None) -> Coordinator:
    """The job belonging to exactly one resolved install root."""
    settled = (root or paths.home()).resolve()
    # Resolve through the gateway job constructor because the test harness replaces that single
    # boundary; a second independently resolved LaunchAgents path would reopen the live-install hole.
    login_items = (Path(into) if into is not None
                   else job.job("automatic-update", settled, settled).into)
    return Coordinator(settled, login_items, f"{job.FAMILY}.{job.fingerprint(settled)}.{UPDATE}")


def shim_of(one: Coordinator) -> Path:
    return one.root / "rundesk-automatic-update"


def plist_of(one: Coordinator) -> Path:
    return one.into / f"{one.label}.plist"


def logs_at(one: Coordinator) -> Path:
    return one.root / "data" / "logs" / "automatic-updates"


def state_at(one: Coordinator) -> Path:
    return one.root / "data" / "automatic-update.json"


def receipt_at(one: Coordinator) -> Path:
    return one.root / "data" / "automatic-update-job.json"


def document(one: Coordinator, update_time: str) -> Dict[str, object]:
    """The local-time calendar job; launchd owns it outside every gateway tree."""
    hour, minute = (int(part) for part in update_time.split(":"))
    captures = logs_at(one)
    return {
        "Label": one.label,
        "ProgramArguments": [str(shim_of(one))],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "WorkingDirectory": str(one.root),
        "StandardOutPath": str(captures / "launchd.out"),
        "StandardErrorPath": str(captures / "launchd.err"),
        "EnvironmentVariables": {
            paths.HOME_IS: str(one.root),
            AUTOMATIC: "1",
            "HOME": str(Path.home()),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
            "LANG": job.LANG,
        },
    }


def reconcile(supervising: Optional[job.Supervising] = None,
              into: Optional[Path] = None) -> Reconciled:
    """Make configured update intent and the per-install supervisor job agree."""
    one = coordinator(into=into)
    # A checkout can settle scratch data but is not an installation launchd can update: its code is
    # not under this root and may disappear with the developer's checkout.
    if not paths.app().is_dir():
        return Reconciled(job.NOT_PLACED, "this root is running from a checkout, not an install")
    try:
        wanted = config.read(paths.data())
    except config.Unreadable as why:
        return Reconciled(job.CANNOT_TELL, str(why))
    if not wanted["update_enabled"]:
        why = remove(supervising, into)
        return Reconciled(job.NOT_PLACED if not why else job.CANNOT_TELL, why)

    desired = plistlib.dumps(document(one, wanted["update_time"]))
    shim = _shim(one)
    receipt = hashlib.sha256(desired + shim).hexdigest()
    try:
        current = plist_of(one).read_bytes()
        current_shim = shim_of(one).read_bytes()
    except FileNotFoundError:
        current = current_shim = b""
    except OSError as why:
        return Reconciled(job.CANNOT_TELL, str(why))

    by = supervising or job.Launchd()
    if current == desired and current_shim == shim and _receipt(one) == receipt:
        standing = by.asked_about(one.label)
        if standing.trouble is None and standing.code == 0:
            return Reconciled(job.PLACED)
    try:
        logs_at(one).mkdir(parents=True, exist_ok=True, mode=0o700)
        _written_privately(shim_of(one), shim, 0o700)
        _written_privately(plist_of(one), desired, 0o600)
    except OSError as why:
        return Reconciled(job.CANNOT_TELL, str(why))
    allowed = by.allow(one.label)
    if allowed.trouble is not None or allowed.code != 0:
        return Reconciled(job.CANNOT_TELL, _ran_wrong("enable", allowed))
    gone = by.take_back(one.label)
    if gone.trouble is not None or (gone.code not in (0, *job.ALREADY_GONE)):
        return Reconciled(job.CANNOT_TELL, _ran_wrong("take back", gone))
    landed = by.place(plist_of(one))
    if landed.trouble is not None or landed.code != 0:
        return Reconciled(job.CANNOT_TELL, _ran_wrong("bootstrap", landed))
    try:
        _written_privately(receipt_at(one), receipt.encode(), 0o600)
    except OSError as why:
        return Reconciled(job.CANNOT_TELL, f"the job was placed but its receipt was not saved ({why})")
    return Reconciled(job.PLACED)


def remove(supervising: Optional[job.Supervising] = None,
           into: Optional[Path] = None) -> str:
    """Remove this install's coordinator idempotently, before its program can disappear."""
    one = coordinator(into=into)
    by = supervising or job.Launchd()
    artifacts = plist_of(one).exists() or shim_of(one).exists()
    existed = artifacts
    if artifacts:
        gone = by.take_back(one.label)
        if gone.trouble is not None or (gone.code not in (0, *job.ALREADY_GONE)):
            return _ran_wrong("take back", gone)
    else:
        asked = by.asked_about(one.label)
        if asked.trouble is not None:
            return _ran_wrong("inspect before taking back", asked)
        if asked.code == 0:
            existed = True
            gone = by.take_back(one.label)
            if gone.trouble is not None or gone.code != 0:
                return _ran_wrong("take back", gone)
        elif asked.code != job.NOT_KNOWN:
            return _ran_wrong("inspect before taking back", asked)
    if existed:
        inert = by.allow(one.label)
        if inert.trouble is not None or inert.code != 0:
            return _ran_wrong("enable its inert record", inert)
    for path in (plist_of(one), shim_of(one), receipt_at(one)):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as why:
            return f"{path} could not be removed ({why})"
    # Test and embedded supervisors may deliberately keep their plist directory below the install.
    # The real ~/Library/LaunchAgents is never ours to remove, even when empty.
    if one.into.parent == one.root:
        try:
            one.into.rmdir()
        except OSError:
            pass
    return ""


def standing(supervising: Optional[job.Supervising] = None,
             into: Optional[Path] = None) -> Reconciled:
    """Whether a coordinator or remnant exists, including a loaded job with no files."""
    one = coordinator(into=into)
    by = supervising or job.Launchd()
    asked = by.asked_about(one.label)
    if asked.trouble is not None:
        return Reconciled(job.CANNOT_TELL, _ran_wrong("inspect", asked))
    if asked.code == 0:
        return Reconciled(job.PLACED)
    if (asked.code == job.NOT_KNOWN and not plist_of(one).exists()
            and not shim_of(one).exists()):
        return Reconciled(job.NOT_PLACED)
    return Reconciled(job.CANNOT_TELL, _ran_wrong("inspect", asked))


def run(now: Optional[datetime.datetime] = None, **updating: object) -> int:
    """Run today's automatic attempt, deferring safely while install work is active."""
    one = coordinator()
    moment = (now or datetime.datetime.now()).astimezone()
    today = moment.date().isoformat()
    for capture in (logs_at(one) / "launchd.out", logs_at(one) / "launchd.err"):
        logs.rotated(capture, CAPTURE_BYTES, CAPTURES_KEPT)
    try:
        with locking.only_one(paths.update_lock(), guarding="updating this install"):
            if _completed(one) == today:
                _note(one, "SKIPPED — today's automatic update already completed")
                return OK
            configured = config.read(paths.data())
            if not configured["update_enabled"]:
                _complete(one, today, "DISABLED")
                _note(one, "DISABLED — automatic updates are not enabled")
                return OK
            with locking.only_one(paths.work_admission_lock(),
                                   guarding="checking whether automatic update is safe"):
                busy = _busy_reason()
                if busy:
                    _complete(one, today, "DEFERRED")
                    _note(one, f"DEFERRED — {busy}", logs.WARNING)
                    return OK
                _note(one, "STARTED")
                from rundesk.commands import update
                result = update.cmd_update(argparse.Namespace(), **updating)
            outcome = "SUCCEEDED" if result == OK else "FAILED"
            _complete(one, today, outcome)
            _note(one, outcome, logs.INFO if result == OK else logs.ERROR)
            return result
    except (config.Unreadable, locking.Stuck, OSError) as why:
        _note(one, f"FAILED — {why}", logs.ERROR)
        return FAILED


def status(supervising: Optional[job.Supervising] = None,
           into: Optional[Path] = None) -> str:
    """Configured intent and measured supervisor state in one status value."""
    one = coordinator(into=into)
    try:
        wanted = config.read(paths.data())
    except config.Unreadable as why:
        return f"? — {why}"
    if not paths.app().is_dir():
        return "not scheduled — this root is running from a checkout"
    by = supervising or job.Launchd()
    asked = by.asked_about(one.label)
    if not wanted["update_enabled"]:
        if asked.trouble is not None:
            return f"disabled in config; supervisor state is unknown — {asked.trouble}"
        if asked.code == 0 or plist_of(one).exists() or shim_of(one).exists():
            return "disabled in config — coordinator removal is incomplete"
        return "disabled"
    if asked.trouble is not None:
        return f"? — {asked.trouble}"
    if asked.code != 0:
        return f"not scheduled — launchd answered {asked.code}"
    try:
        desired = plistlib.dumps(document(one, wanted["update_time"]))
        if plist_of(one).read_bytes() != desired or shim_of(one).read_bytes() != _shim(one):
            return "placed — definition does not match configured update settings"
    except OSError as why:
        return f"placed — definition could not be read ({why})"
    return f"scheduled daily at {wanted['update_time']} local time"


def _busy_reason() -> str:
    try:
        agents = directory.known()
    except OSError as why:
        return f"agent activity could not be inspected ({why})"
    for agent in agents:
        active_turns = turns.activity(agent)
        if active_turns is None:
            return f"{agent}'s provider activity could not be inspected"
        if active_turns:
            return f"{agent} has an active provider turn (conversation {active_turns[0]})"
        active_schedules = firing.activity(agent)
        if active_schedules is None:
            return f"{agent}'s schedule activity could not be inspected"
        if active_schedules:
            return f"{agent} has an active schedule ({active_schedules[0]})"
    return ""


def _shim(one: Coordinator) -> bytes:
    command = f"exec {shlex.quote(sys.executable)} -c {shlex.quote(RUN)} {shlex.quote(str(one.root / 'app' / 'src'))}\n"
    return ("#!/bin/sh\n# Generated by Rundesk; reconciled from update settings.\n" + command).encode()


def _written_privately(where: Path, content: bytes, mode: int) -> None:
    where.parent.mkdir(parents=True, exist_ok=True)
    descriptor, named = tempfile.mkstemp(prefix=where.name + ".new-", dir=str(where.parent))
    temporary = Path(named)
    try:
        try:
            os.fchmod(descriptor, mode)
            os.write(descriptor, content)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, where)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _ran_wrong(action: str, ran: object) -> str:
    trouble = getattr(ran, "trouble", None)
    code = getattr(ran, "code", None)
    return f"the supervisor could not {action} {coordinator().label} ({trouble or f'exit {code}'})"


def _completed(one: Coordinator) -> str:
    try:
        return str(json.loads(state_at(one).read_text()).get("completed_local_date", ""))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return ""


def _receipt(one: Coordinator) -> str:
    try:
        return receipt_at(one).read_text()
    except OSError:
        return ""


def _complete(one: Coordinator, today: str, outcome: str) -> None:
    content = json.dumps({"completed_local_date": today, "outcome": outcome}, sort_keys=True).encode()
    _written_privately(state_at(one), content, 0o600)


def _note(one: Coordinator, said: str, level: str = logs.INFO) -> None:
    logs.note(logs_at(one), said, level)
    logs.swept(logs_at(one), LOG_DAYS)
