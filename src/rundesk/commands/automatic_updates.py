"""One launchd-owned daily update coordinator for each isolated Rundesk install."""

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import plistlib
import re
import shlex
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, Iterator, NamedTuple, Optional, Tuple

from rundesk.agents import directory, records
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job
from rundesk.providers import continuations, environment, turns
from rundesk.schedules import firing
from rundesk.utils import locking, logs, programs

UPDATE = "update"
UPDATE_LABEL = re.compile(
    rf"^{re.escape(job.FAMILY)}\.[0-9a-f]{{{job.FINGERPRINT}}}\.{UPDATE}$")
ORPHAN_GRACE_SECONDS = 24 * 60 * 60
CAPTURE_BYTES = 1024 * 1024
CAPTURES_KEPT = 3
LOG_DAYS = 30
AUTOMATIC = "RUNDESK_AUTOMATIC_UPDATE"
QUEUED = "RUNDESK_QUEUED_UPDATE"
QUEUE_POLL_SECONDS = 1.0
QUEUE_RETRY_SECONDS = 60.0
RUN = (
    "import sys;sys.path.insert(0,sys.argv[1]);"
    "from rundesk.commands.automatic_updates import run;raise SystemExit(run())"
)
RUN_QUEUED = (
    "import sys;sys.path.insert(0,sys.argv[1]);"
    "from rundesk.commands.automatic_updates import run_queued;raise SystemExit(run_queued())"
)


class Coordinator(NamedTuple):
    root: Path
    into: Path
    label: str


class Reconciled(NamedTuple):
    how: str
    why: str = ""


class Definition(NamedTuple):
    label: str
    root: Path


class Daily(NamedTuple):
    """One daily attempt, including work that must be queued after its claim is released."""

    code: int
    queue_reason: str = ""
    request_waiting: bool = False


class CouldNotStop(Exception):
    """An uninstall could not exclude every queued or running update."""


class InvalidContinuation(Exception):
    """A queued opt-in descriptor does not name one exact update handoff."""


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


def reconciliation_lock_at(one: Coordinator) -> Path:
    """The cross-install claim protecting coordinator definitions in one login directory."""
    if one.into.parent == one.root:
        # Embedded supervisors may remove their whole definition directory with the install. Keep
        # the lock as its stable sibling: a lock pathname must never be unlinked after another
        # process could have opened its inode, or a third caller can create and lock a second one.
        return one.root.with_name(f".{one.root.name}.rundesk-automatic-updates.lock")
    return one.into / ".rundesk-automatic-updates.lock"


def logs_at(one: Coordinator) -> Path:
    return one.root / "data" / "logs" / "automatic-updates"


def state_at(one: Coordinator) -> Path:
    return one.root / "data" / "automatic-update.json"


def receipt_at(one: Coordinator) -> Path:
    return one.root / "data" / "automatic-update-job.json"


def request_at(one: Coordinator) -> Path:
    """The durable manual request waiting for a quiet install."""
    return one.root / "data" / "queued-update.json"


def queue_lock_at(one: Coordinator) -> Path:
    """The claim held by the one detached process waiting to perform the request."""
    return one.root / ".rundesk-update-queue.lock"


def queue_log_at(one: Coordinator) -> Path:
    """What the detached runner says when nobody is waiting at a terminal."""
    return logs_at(one) / "queued.log"


def _claim_request(one: Coordinator) -> Optional[int]:
    """Hold the exact queued request this worker observed, or `None` when there was none.

    The open descriptor pins the file identity even if another command atomically replaces its
    pathname while an update is finishing. That lets settlement remove only the request it served,
    never a newer promise made after `attempt_update` released its admission/update locks.
    """
    try:
        return os.open(request_at(one), os.O_RDONLY)
    except FileNotFoundError:
        return None


def _remove_claimed_request(one: Coordinator, claimed: Optional[int]) -> None:
    """Remove `claimed` only while it is still the request at the durable queue pathname."""
    if claimed is None:
        return
    with locking.only_one(paths.update_lock(), guarding="settling the queued update"):
        try:
            current = request_at(one).stat()
        except FileNotFoundError:
            return
        original = os.fstat(claimed)
        if (current.st_dev, current.st_ino) == (original.st_dev, original.st_ino):
            request_at(one).unlink()


@contextlib.contextmanager
def updates_stopped(waiting: float = 2.5) -> Iterator[None]:
    """Cancel queued work and exclude updates for an uninstall's whole transaction."""
    one = coordinator()
    held = contextlib.ExitStack()
    try:
        request_at(one).unlink(missing_ok=True)
        held.enter_context(locking.only_one(
            queue_lock_at(one), guarding="stopping the queued update worker", waiting=waiting))
        held.enter_context(locking.only_one(
            paths.update_lock(), guarding="stopping updates for uninstall", waiting=waiting))
        # A manual update may have queued while this caller waited for its update claim. Remove
        # that request only after both lifecycle locks belong to the uninstall.
        request_at(one).unlink(missing_ok=True)
    except (locking.Stuck, OSError) as why:
        held.close()
        raise CouldNotStop(str(why)) from why
    try:
        yield
    finally:
        held.close()


def cancel_queued(waiting: float = 2.5) -> str:
    """Cancel a durable request and prove no update owns either lifecycle claim."""
    try:
        with updates_stopped(waiting):
            pass
    except CouldNotStop as why:
        return str(why)
    return ""


def queued(reason: str, starting=None, environ: Optional[Dict[str, str]] = None,
           continuation: Optional[Tuple[str, int, int]] = None) -> str:
    """Keep one update request and ensure a detached runner is waiting for quiet.

    The request is written before the runner starts. If the process cannot begin, the request stays
    visible and the daily coordinator can retry it; losing a process must never lose the decision.
    """
    one = coordinator()
    values = os.environ if environ is None else environ
    request = {
        "requested_at": config.moment_of(),
        "reason": str(reason),
        "agent": str(values.get(environment.AGENT) or "") or None,
        "turn": (int(values[environment.RUN])
                 if str(values.get(environment.RUN) or "").isdigit() else None),
    }
    if continuation is not None:
        request["continuation"] = {
            "agent": continuation[0], "turn": continuation[1], "handoff": continuation[2]}
    try:
        # Settlement uses this same lock to compare-and-remove its observed request. Without the
        # writer joining that exclusion it could replace the pathname after the comparison and
        # before the unlink, reopening the exact completion race the identity check closes.
        with locking.only_one(paths.update_lock(), guarding="queueing this update"):
            existing = _read_request(request_at(one))
            existing_continuation = existing.get("continuation") if existing else None
            if existing_continuation is not None:
                if continuation is None or existing_continuation == request.get("continuation"):
                    _ensure_queued_runner(one, starting)
                    return ("update already queued until current work finishes — "
                            f"{existing.get('reason') or reason}")
                return ("the update could not be queued (another opted-in conversation already "
                        "owns the queued update)")
            _written_privately(
                request_at(one), (json.dumps(request, sort_keys=True) + "\n").encode(), 0o600)
            _ensure_queued_runner(one, starting)
    except (locking.Stuck, OSError, ValueError, programs.CouldNotStart) as why:
        return f"the update could not be queued ({why})"
    return f"update queued until current work finishes — {reason}"


def _ensure_queued_runner(one: Coordinator, starting=None) -> None:
    """Start one waiter when none owns the queue claim; an existing waiter is enough."""
    if locking.is_held(queue_lock_at(one)) is not True:
        (starting or _start_queued_runner)(one)


def _start_queued_runner(one: Coordinator) -> int:
    """Start outside every gateway and provider process group, with no inherited turn state."""
    return programs.start(
        [sys.executable, "-c", RUN_QUEUED, str(paths.code())],
        queue_log_at(one), where=one.root,
        env={paths.HOME_IS: str(one.root), QUEUED: "1", "HOME": str(Path.home()),
             "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"), "LANG": job.LANG})


def run_queued(sleeping: Callable[[float], None] = time.sleep,
               wait_seconds: Optional[float] = None) -> int:
    """Wait for every admitted turn and schedule, then perform one queued update.

    The queue claim prevents duplicate detached runners. The work-admission barrier closes the gap
    between the final quiet check and the update taking gateways down.
    """
    # Import the updater before waiting so this long-lived process uses one release generation.
    # While work remains active every other manual attempt queues behind this request; the queue
    # lock excludes the daily coordinator, so nobody can replace `app/` underneath this waiter.
    from rundesk.commands import update
    one = coordinator()
    try:
        with locking.only_one(queue_lock_at(one), guarding="running the queued update", waiting=0):
            deadline = time.monotonic() + wait_seconds if wait_seconds is not None else None
            while (request_at(one).is_file()
                   and (deadline is None or time.monotonic() < deadline)):
                busy = _busy_reason()
                if not busy:
                    # `attempt_update` repeats the quiet check while holding admission. If a turn
                    # wins this observation gap it says it queued, and this same sole worker keeps
                    # waiting — it must not exit and strand a request nobody else could start.
                    claimed = _claim_request(one)
                    try:
                        try:
                            continuation = _validated_continuation(_continuation(claimed))
                        except InvalidContinuation as why:
                            _note(one, f"FAILED — invalid queued continuation ({why})", logs.ERROR)
                            _remove_claimed_request(one, claimed)
                            return FAILED
                        if continuation is not None:
                            continuations.running(continuation[0], continuation[2])
                        attempt = update.attempt_update(argparse.Namespace())
                        if attempt.queued:
                            continue
                        if attempt.code == OK:
                            _finished_continuation(continuation, succeeded=True)
                            _remove_claimed_request(one, claimed)
                            return OK
                        if continuation is not None:
                            _finished_continuation(continuation, succeeded=False)
                            _remove_claimed_request(one, claimed)
                            return attempt.code
                        # The foreground command already returned after promising eventual work.
                        # Keep that promise even when daily updates are disabled: hold off, then
                        # retry this same durable request until it succeeds or uninstall cancels it.
                        if not _wait_to_retry(one, sleeping, deadline):
                            return OK if not request_at(one).is_file() else attempt.code
                    finally:
                        if claimed is not None:
                            os.close(claimed)
                sleeping(QUEUE_POLL_SECONDS)
            return OK
    except locking.Stuck:
        return OK


def _wait_to_retry(one: Coordinator, sleeping: Callable[[float], None],
                   deadline: Optional[float]) -> bool:
    """Wait interruptibly after a failed attempt; `False` once cancelled or timed out."""
    remaining = QUEUE_RETRY_SECONDS
    while request_at(one).is_file() and remaining > 0:
        if deadline is not None and time.monotonic() >= deadline:
            return False
        pause = min(QUEUE_POLL_SECONDS, remaining)
        sleeping(pause)
        remaining -= pause
    return request_at(one).is_file() and (deadline is None or time.monotonic() < deadline)


def _read_request(where: Path) -> Dict[str, object]:
    """A queued request object, or an empty answer for absent/malformed state."""
    try:
        read = json.loads(where.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return {}
    return read if isinstance(read, dict) else {}


def _continuation(claimed: Optional[int]) -> Optional[Tuple[str, int, int]]:
    """Validated continuation provenance from the exact request descriptor this worker pinned."""
    if claimed is None:
        return None
    try:
        os.lseek(claimed, 0, os.SEEK_SET)
        request = json.loads(os.read(claimed, 16 * 1024).decode("utf-8"))
        if not isinstance(request, dict) or "continuation" not in request:
            return None
        value = request.get("continuation")
        agent = value.get("agent") if isinstance(value, dict) else None
        turn = value.get("turn") if isinstance(value, dict) else None
        handoff = value.get("handoff") if isinstance(value, dict) else None
        if isinstance(agent, str) and isinstance(turn, int) and isinstance(handoff, int):
            return agent, turn, handoff
    except (OSError, UnicodeError, ValueError) as why:
        raise InvalidContinuation("the queued request could not be read") from why
    raise InvalidContinuation("the queued continuation identity is malformed")


def _validated_continuation(
        reference: Optional[Tuple[str, int, int]]) -> Optional[Tuple[str, int, int]]:
    """Require the queue's agent, origin turn, and handoff id to identify the same row."""
    if reference is None:
        return None
    try:
        handoff = continuations.one(reference[0], reference[2])
    except (OSError, records.NotThere, records.Unreadable, ValueError) as why:
        raise InvalidContinuation(str(why)) from why
    if handoff.operation != continuations.UPDATE:
        raise InvalidContinuation(
            f"handoff {reference[2]} is {handoff.operation}, not an update")
    if handoff.origin_turn_id != reference[1]:
        continuations.suppressed(
            reference[0], reference[2],
            "the queued update did not match its originating turn")
        raise InvalidContinuation(
            f"handoff {reference[2]} belongs to turn {handoff.origin_turn_id}, not {reference[1]}")
    return reference


def _finished_continuation(reference: Optional[Tuple[str, int, int]], *, succeeded: bool) -> None:
    """Attach the queued update's terminal truth without changing its lifecycle result."""
    if reference is None:
        return
    try:
        continuations.finished(
            reference[0], reference[2], succeeded=succeeded,
            outcome=("the queued update completed and the install settled"
                     if succeeded else
                     "the queued update reached a terminal failure; queued logs record details"))
    except (OSError, ValueError):
        # The update result remains in its own durable queue log. Failure to attach an optional
        # continuation must never turn a completed lifecycle transaction into a false failure.
        return


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
            # A persisted job definition cannot depend on which shell happened to reconcile or
            # inspect it. The updater uses absolute program paths; the system path is enough for
            # commands it deliberately starts and contains no transient development directories.
            "PATH": os.pathsep.join(job.LAUNCHD_PATH),
            "LANG": job.LANG,
        },
    }


def _coordinator_definition(candidate: Path, current: Coordinator,
                            named_as: Optional[Path] = None) -> Optional[Definition]:
    """The exact coordinator identity in one canonical or privately claimed definition."""
    canonical = named_as or candidate
    if canonical == plist_of(current):
        return None
    try:
        saved = plistlib.loads(candidate.read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(saved, dict):
        return None
    label = saved.get("Label")
    arguments = saved.get("ProgramArguments")
    root = saved.get("WorkingDirectory")
    environ = saved.get("EnvironmentVariables")
    if (not isinstance(label, str) or UPDATE_LABEL.fullmatch(label) is None
            or canonical.name != f"{label}.plist"
            or not isinstance(arguments, list) or len(arguments) != 1
            or not isinstance(arguments[0], str) or not isinstance(root, str)
            or not isinstance(environ, dict) or environ.get(paths.HOME_IS) != root):
        return None
    recorded_root = Path(root)
    if not recorded_root.is_absolute():
        return None
    try:
        other = coordinator(recorded_root.resolve(), current.into)
    except OSError:
        return None
    if (other.label != label or str(other.root) != root
            or arguments[0] != str(shim_of(other))):
        return None
    return Definition(label, recorded_root)


def _orphaned_coordinator_label(candidate: Path, current: Coordinator,
                                named_as: Optional[Path] = None) -> Optional[str]:
    """An aged coordinator proven to name a vanished root, never an ambiguous lookalike."""
    definition = _coordinator_definition(candidate, current, named_as)
    if definition is None:
        return None
    try:
        definition.root.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        return None
    else:
        return None
    try:
        if not definition.root.parent.is_dir():
            return None
        age = time.time() - candidate.stat().st_mtime
    except OSError:
        return None
    return definition.label if age >= ORPHAN_GRACE_SECONDS else None


def _claim_of(candidate: Path) -> Path:
    return candidate.with_name(f".{candidate.name}.orphaned")


def _restore_claims(supervising: job.Supervising, current: Coordinator) -> str:
    """Put an interrupted atomic claim back before deciding whether it is still orphaned."""
    try:
        claims = sorted(current.into.glob(".ai.rundesk.*.update.plist.orphaned"))
    except OSError as why:
        return f"orphaned automatic update claims could not be inspected ({why})"
    for claim in claims:
        canonical = claim.with_name(claim.name[1:-len(".orphaned")])
        definition = _coordinator_definition(claim, current, canonical)
        if definition is None:
            return f"automatic update claim {claim} could not be identified safely"
        try:
            os.link(claim, canonical)
        except FileExistsError:
            # A non-participating older installer won the canonical pathname. The claim is the
            # already-proven stale inode, so removing only that private link cannot touch its work.
            canonical_definition = _coordinator_definition(canonical, current)
            try:
                same_inode = os.path.samefile(claim, canonical)
            except OSError:
                same_inode = False
            if (not same_inode and (canonical_definition is None
                                    or not canonical_definition.root.exists())):
                return f"automatic update definition {canonical} changed while a claim was held"
        except OSError as why:
            return f"automatic update claim {claim} could not be restored ({why})"
        try:
            claim.unlink()
        except OSError as why:
            return f"automatic update claim {claim} could not be settled ({why})"
        if definition.root.exists():
            recovered = _restore_raced_coordinator(
                supervising, canonical, current, definition.label)
            if recovered:
                return recovered
    return ""


def _restore_raced_coordinator(supervising: job.Supervising, candidate: Path,
                               current: Coordinator, label: str) -> str:
    """Put back a canonical definition that appeared while its old launchd job was retired."""
    definition = _coordinator_definition(candidate, current)
    if (definition is None or definition.label != label or not definition.root.exists()
            or not shim_of(coordinator(definition.root, current.into)).is_file()):
        return f"reinstalled automatic update definition {candidate} could not be identified safely"
    standing = supervising.asked_about(label)
    if standing.trouble is None and standing.code == 0:
        return ""
    if standing.trouble is not None or standing.code != job.NOT_KNOWN:
        return _ran_wrong("inspect a reinstalled automatic update", standing, label)
    landed = supervising.place(candidate)
    if landed.trouble is None and landed.code == 0:
        return ""
    # An older installer may have bootstrapped between the inspection and this request.
    standing = supervising.asked_about(label)
    if standing.trouble is None and standing.code == 0:
        return ""
    return _ran_wrong("restore a reinstalled automatic update", landed, label)


def _remove_orphaned_coordinators(supervising: job.Supervising, current: Coordinator) -> str:
    """Take only structurally proven dead coordinator jobs from the shared login directory."""
    restored = _restore_claims(supervising, current)
    if restored:
        return restored
    try:
        candidates = sorted(current.into.iterdir())
    except FileNotFoundError:
        return ""
    except OSError as why:
        return f"automatic update definitions could not be inspected ({why})"
    for candidate in candidates:
        label = _orphaned_coordinator_label(candidate, current)
        if label is None:
            continue
        claim = _claim_of(candidate)
        try:
            candidate.rename(claim)
        except FileNotFoundError:
            continue
        except OSError as why:
            return f"orphaned automatic update definition {candidate} could not be claimed ({why})"
        # `rename` captured one exact inode. Revalidate it at the private pathname: an older
        # installer may have atomically replaced the canonical definition after classification.
        if _orphaned_coordinator_label(claim, current, candidate) != label:
            try:
                os.link(claim, candidate)
            except FileExistsError:
                pass
            except OSError as why:
                return f"automatic update claim {claim} could not be restored ({why})"
            return f"automatic update definition {candidate} changed while it was inspected"
        # A writer that ignored the shared lock may have returned after the atomic claim. Never
        # boot out its job merely because the old definition was already proven stale.
        claimed = _coordinator_definition(claim, current, candidate)
        if claimed is None:
            return f"automatic update claim {claim} could not be identified safely"
        if candidate.exists():
            replacement = _coordinator_definition(candidate, current)
            if replacement is None or replacement.label != label or not replacement.root.exists():
                return f"automatic update definition {candidate} changed while a claim was held"
            try:
                claim.unlink()
            except OSError as why:
                return f"orphaned automatic update claim {claim} could not be removed ({why})"
            continue
        if claimed.root.exists():
            try:
                os.link(claim, candidate)
                claim.unlink()
            except FileExistsError:
                pass
            except OSError as why:
                return f"automatic update claim {claim} could not be restored ({why})"
            return (f"automatic update root returned while {candidate} was being inspected; "
                    "its installer must finish reconciliation")
        gone = supervising.take_back(label)
        if gone.trouble is not None or gone.code not in (0, *job.ALREADY_GONE):
            try:
                os.link(claim, candidate)
            except (FileExistsError, OSError):
                pass
            return _ran_wrong("take back orphaned automatic update", gone, label)
        try:
            claimed = _coordinator_definition(claim, current, candidate)
            if claimed is None:
                return f"automatic update claim {claim} could not be identified safely"
            if candidate.exists():
                recovered = _restore_raced_coordinator(supervising, candidate, current, label)
                if recovered:
                    return recovered
            elif claimed.root.exists():
                try:
                    os.link(claim, candidate)
                except FileExistsError:
                    pass
                recovered = _restore_raced_coordinator(supervising, candidate, current, label)
                if recovered:
                    return recovered
            claim.unlink()
        except OSError as why:
            return f"orphaned automatic update claim {claim} could not be settled ({why})"
    return ""


def reconcile(supervising: Optional[job.Supervising] = None,
              into: Optional[Path] = None) -> Reconciled:
    """Make configured update intent and the per-install supervisor job agree."""
    one = coordinator(into=into)
    # A checkout can settle scratch data but is not an installation launchd can update: its code is
    # not under this root and may disappear with the developer's checkout.
    if not paths.app().is_dir():
        return Reconciled(job.NOT_PLACED, "this root is running from a checkout, not an install")
    try:
        with locking.only_one(
                reconciliation_lock_at(one), guarding="automatic update definitions"):
            return _reconcile(one, supervising)
    except (locking.Stuck, OSError) as why:
        return Reconciled(job.CANNOT_TELL, str(why))


def _reconcile(one: Coordinator, supervising: Optional[job.Supervising]) -> Reconciled:
    """Reconcile one coordinator while every install sharing its definitions is excluded."""
    try:
        wanted = config.read(paths.data())
    except config.Unreadable as why:
        return Reconciled(job.CANNOT_TELL, str(why))
    by = supervising or job.Launchd()
    orphaned = _remove_orphaned_coordinators(by, one)
    if orphaned:
        return Reconciled(job.CANNOT_TELL, orphaned)
    if not wanted["update_enabled"]:
        why = remove(by, one.into)
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
    try:
        with locking.only_one(
                reconciliation_lock_at(one), guarding="automatic update definitions"):
            result = _remove(one, supervising)
    except (locking.Stuck, OSError) as why:
        return str(why)
    if one.into.parent == one.root:
        try:
            one.into.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return result


def _remove(one: Coordinator, supervising: Optional[job.Supervising]) -> str:
    """Remove one coordinator while every install sharing its definitions is excluded."""
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
    """Run today's automatic attempt, queueing safely while install work is active."""
    one = coordinator()
    moment = (now or datetime.datetime.now()).astimezone()
    today = moment.date().isoformat()
    for capture in (logs_at(one) / "launchd.out", logs_at(one) / "launchd.err"):
        logs.rotated(capture, CAPTURE_BYTES, CAPTURES_KEPT)
    try:
        with locking.only_one(queue_lock_at(one), guarding="running the daily update", waiting=0):
            attempt = _run(one, today, **updating)
        if not attempt.queue_reason:
            return attempt.code
        try:
            if attempt.request_waiting:
                _ensure_queued_runner(one)
                said = f"update already queued until current work finishes — {attempt.queue_reason}"
            else:
                said = queued(attempt.queue_reason)
        except (OSError, ValueError, programs.CouldNotStart) as why:
            said = f"the update could not be queued ({why})"
        if said.startswith("the update could not"):
            _complete(one, today, "FAILED")
            _note(one, f"FAILED — {said}", logs.ERROR)
            return FAILED
        _complete(one, today, "DEFERRED")
        _note(one, f"DEFERRED — {said}", logs.WARNING)
        return OK
    except locking.Stuck:
        _note(one, "SKIPPED — another queued or daily update worker is active")
        return OK
    except (config.Unreadable, OSError) as why:
        _note(one, f"FAILED — {why}", logs.ERROR)
        return FAILED


def _run(one: Coordinator, today: str, **updating: object) -> Daily:
    """One serialised daily/queue-recovery attempt."""
    try:
        if _completed(one) == today and not request_at(one).is_file():
            _note(one, "SKIPPED — today's automatic update already completed")
            return Daily(OK)
        configured = config.read(paths.data())
        if not configured["update_enabled"] and not request_at(one).is_file():
            _complete(one, today, "DISABLED")
            _note(one, "DISABLED — automatic updates are not enabled")
            return Daily(OK)
        busy = _busy_reason()
        if busy:
            return Daily(OK, busy, request_at(one).is_file())
        _note(one, "STARTED")
        from rundesk.commands import update
        claimed = _claim_request(one)
        try:
            try:
                continuation = _validated_continuation(_continuation(claimed))
            except InvalidContinuation as why:
                _remove_claimed_request(one, claimed)
                _complete(one, today, "FAILED")
                _note(one, f"FAILED — invalid queued continuation ({why})", logs.ERROR)
                return Daily(FAILED)
            if continuation is not None:
                continuations.running(continuation[0], continuation[2])
            surface_notes = []
            external_reporting = updating.get("reporting")

            def report_surface(said: str, failed: bool) -> None:
                surface_notes.append((said, failed))
                if callable(external_reporting):
                    external_reporting(said, failed)

            updating["reporting"] = report_surface
            attempt = update.attempt_update(argparse.Namespace(), **updating)
            for surface_note, failed_surface in surface_notes:
                level = logs.WARNING if failed_surface else logs.INFO
                _note(one, surface_note, level)
            if attempt.queued:
                return Daily(OK, "work began before update admission closed", True)
            if attempt.code == OK:
                _finished_continuation(continuation, succeeded=True)
                _remove_claimed_request(one, claimed)
            elif continuation is not None:
                _finished_continuation(continuation, succeeded=False)
                _remove_claimed_request(one, claimed)
        finally:
            if claimed is not None:
                os.close(claimed)
        outcome = "SUCCEEDED" if attempt.code == OK else "FAILED"
        _complete(one, today, outcome)
        _note(one, outcome, logs.INFO if attempt.code == OK else logs.ERROR)
        return Daily(attempt.code)
    except (config.Unreadable, OSError) as why:
        _note(one, f"FAILED — {why}", logs.ERROR)
        return Daily(FAILED)


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


def _ran_wrong(action: str, ran: object, label: Optional[str] = None) -> str:
    trouble = getattr(ran, "trouble", None)
    code = getattr(ran, "code", None)
    return (f"the supervisor could not {action} {label or coordinator().label} "
            f"({trouble or f'exit {code}'})")


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
